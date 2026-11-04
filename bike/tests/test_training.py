import asyncio
import json
import time
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.training import PulseController, TrainingProfile, resolve_plan, templates


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'training.db')
    monkeypatch.setattr(main,'engine',main.Engine())
    with TestClient(main.app) as client:
        yield client


def test_templates_exact_duration_and_categories():
    plans=[p for p in templates() if not p['meta'].get('terrain')]
    assert len(plans)==9
    assert {p['meta']['minutes'] for p in plans}=={35,45,60}
    for minutes in (35,45,60):
        group=[p for p in plans if p['meta']['minutes']==minutes]
        assert {p['meta']['category'] for p in group}=={'Grundlage','Tempo','VO₂max'}
        assert all(sum(s['seconds'] for s in p['steps'])==minutes*60 for p in group)
    four_by_four=next(p for p in plans if p['key']=='vo245')
    assert [s['seconds'] for s in four_by_four['steps'] if s['zone']=='vo2']==[240]*4


def test_terrain_routes_have_ramps_descents_and_exact_durations():
    plans = [p for p in templates() if p['meta'].get('terrain')]
    assert len(plans) == 6
    for minutes in (35, 45, 60):
        assert sum(p['meta']['minutes'] == minutes for p in plans) == 2
    for plan in plans:
        steps = plan['steps']
        assert sum(s['seconds'] for s in steps) == plan['meta']['minutes'] * 60
        assert len(steps) <= 100  # Also editable through the custom-plan API.
        assert min(s['grade_percent'] for s in steps) < -2
        assert max(s['grade_percent'] for s in steps) >= 2.9
        assert max(abs(b['ftp_factor'] - a['ftp_factor']) for a, b in zip(steps, steps[1:])) < .10
        assert max(s['ftp_factor'] for s in steps if s['grade_percent'] < -2) < .65


def test_terrain_start_and_descent_follow_personal_watt_curve(client):
    plan = next(p for p in client.get('/api/plans').json() if p['meta'].get('terrain'))
    assert client.post('/api/start', json={'plan_id': plan['id']}).status_code == 200
    assert client.get('/api/profile').json()['ftp_watts'] is None
    client.post('/api/stop')
    client.post('/api/profile', json={'ftp_watts': 200, 'power_adjustment_watts': 5})
    result = client.post('/api/start', json={'plan_id': plan['id'], 'intensity_percent': 80})
    assert result.status_code == 200
    steps = result.json()['steps']
    assert result.json()['training_mode'] == 'power'
    assert all(s['watts'] == max(25, min(400, int(s['ftp_factor'] * 200 * .8 + .5) + 5)) for s in steps)
    ascent = next(s for s in steps if s['grade_percent'] > 2.5)
    descent_index = next(i for i, s in enumerate(steps) if s['grade_percent'] < -2)
    main.engine.elapsed = sum(s['seconds'] for s in steps[:descent_index]) + 1
    assert main.engine.select_step()
    assert main.engine.target == steps[descent_index]['watts'] < ascent['watts']


def test_migration_idempotent_and_custom_plans_preserved(client):
    custom=dict(name='Behalten',steps=[dict(name='Test',seconds=60,watts=90)])
    plan_id=client.post('/api/plans',json=custom).json()['id']
    before=len(client.get('/api/plans').json())
    main.init_db()
    plans=client.get('/api/plans').json()
    assert len(plans)==before
    assert next(p for p in plans if p['id']==plan_id)['steps'][0]['watts']==90


def test_profile_scaling_and_preview_gate(client):
    template=next(p for p in client.get('/api/plans').json() if p['meta'].get('category')=='VO₂max')
    assert not template['requires_ftp'] and template['power_basis'] == 'example'
    assert client.post('/api/start',json={'plan_id':template['id']}).status_code==200
    assert client.get('/api/profile').json()['ftp_watts'] is None
    client.post('/api/stop')
    assert client.post('/api/profile',json={'ftp_watts':200}).status_code==200
    updated=next(p for p in client.get('/api/plans').json() if p['id']==template['id'])
    assert max(s['watts'] for s in updated['steps'])==210
    response=client.post('/api/start',json={'plan_id':template['id'],'intensity_percent':80})
    assert response.status_code==200
    assert max(s['watts'] for s in response.json()['steps'])==168
    assert client.post('/api/profile',json={'ftp_watts':180}).status_code==409
    client.post('/api/stop')
    with main.database() as db:
        assert json.loads(db.execute("SELECT value FROM settings WHERE key='training_profile'").fetchone()[0])['ftp_watts']==200


def test_pulse_profile_validation_and_no_sensor_start(client):
    assert client.post('/api/profile',json={'hr_max':170,'hr_ceiling':180}).status_code==422
    assert client.post('/api/profile',json={'hr_min_watts':150,'hr_max_watts':100}).status_code==422
    assert client.post('/api/start',json={'training_mode':'hr'}).status_code==422
    assert client.post('/api/profile',json={'hr_max':180,'hr_ceiling':170}).status_code==200
    assert client.post('/api/start',json={'training_mode':'hr'}).status_code==409


def test_pulse_start_custom_target_and_resume_gate(client):
    client.post('/api/profile',json={'hr_max':180,'hr_ceiling':170})
    main.engine.hr.bpm,main.engine.hr.updated=110,time.monotonic()
    assert client.post('/api/start',json={'training_mode':'hr','hr_target_low':160,'hr_target_high':175}).status_code==422
    response=client.post('/api/start',json={'training_mode':'hr','duration_minutes':45,'hr_target_low':110,'hr_target_high':125})
    assert response.status_code==200
    assert response.json()['duration']==2700
    assert response.json()['training_mode']=='hr'
    client.post('/api/pause')
    main.engine.hr.updated=time.monotonic()-11
    assert client.post('/api/pause').status_code==409
    main.engine.hr.bpm,main.engine.hr.updated=110,time.monotonic()
    assert client.post('/api/pause').status_code==200


def test_pulse_controller_delayed_increase_band_and_caps():
    controller=PulseController()
    def run(now,bpm=100,watts=70,age=0,phase=0,reference=70):
        return controller.update(watts,bpm,age,110,125,170,25,100,now,phase,reference)
    assert run(0)==(70,'run')
    assert run(30)==(70,'run')
    assert run(45)==(75,'run')
    assert run(50,watts=75)==(75,'run')
    assert run(60,watts=100)==(100,'run')
    assert run(75,bpm=120,watts=80)==(80,'run')
    assert run(90,bpm=140,watts=80)==(75,'run')
    assert run(91,bpm=140,watts=75)==(75,'run')
    assert run(100,age=4,watts=90)==(25,'wait')
    assert run(105,age=11,watts=90)==(25,'pause')
    assert run(106,bpm=0)==(25,'pause')
    assert run(107,bpm=170)==(25,'stop')


def test_signal_loss_and_limit_reduce_real_adapter_to_25(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'guard.db')
    main.init_db()
    async def run():
        engine=main.Engine()
        engine.profile=TrainingProfile(hr_max=180,hr_ceiling=170)
        engine.training_mode='hr'
        engine.steps=[dict(name='Cardio',seconds=300,watts=80,hr_low=110,hr_high=125)]
        engine.running,engine.connected,engine.mode=True,True,'daum'
        engine.daum.set_power=AsyncMock()
        engine.daum.release=AsyncMock()
        engine.hr.bpm,engine.hr.updated=100,time.monotonic()-11
        assert await engine.regulate_pulse(time.monotonic())=='pause'
        assert engine.paused and engine.target==25
        engine.daum.set_power.assert_awaited_with(25)
        engine.hr.bpm,engine.hr.updated=170,time.monotonic()
        assert await engine.regulate_pulse(time.monotonic())=='stop'
        assert not engine.running
        engine.daum.release.assert_awaited_once()
    asyncio.run(run())


def test_low_cadence_cannot_raise_pulse_mode_load():
    async def run():
        engine=main.Engine()
        engine.profile=TrainingProfile(hr_max=180,hr_ceiling=170)
        engine.training_mode='hr'
        engine.steps=[dict(name='Cardio',seconds=300,watts=100,hr_low=110,hr_high=125)]
        engine.target,engine.cadence=80,0
        engine.hr.bpm,engine.hr.updated=90,time.monotonic()
        assert await engine.regulate_pulse(time.monotonic())=='run'
        assert engine.target==25
    asyncio.run(run())


def test_pulse_phase_countdown_preserves_regulated_target():
    engine=main.Engine()
    engine.training_mode='hr'
    engine.steps=[dict(name='Warm',seconds=60,watts=50),dict(name='Cardio',seconds=120,watts=100)]
    engine.target,engine.elapsed=75,70
    assert engine.select_step()
    assert engine.target==75 and engine.step_index==1 and engine.step_remaining==110


def test_orientation_does_not_invent_ftp_and_unlocks_only_base(client):
    orientation=next(p for p in client.get('/api/plans').json() if p['meta'].get('calibration'))
    assert sum(s['seconds'] for s in orientation['steps'])==1200
    assert client.post('/api/start',json={'plan_id':orientation['id'],'intensity_percent':130}).status_code==200
    assert max(s['watts'] for s in main.engine.steps)==80
    assert client.post('/api/calibration/comfortable').status_code==409
    client.post('/api/stop')
    client.post('/api/profile',json={'comfortable_watts':60})
    plans=client.get('/api/plans').json()
    base=next(p for p in plans if p['meta'].get('category')=='Grundlage')
    assert base['power_basis']=='comfortable' and not base['requires_ftp']
    assert max(s['watts'] for s in base['steps'])==60
    intense=next(p for p in plans if p['meta'].get('category')=='VO₂max')
    assert not intense['requires_ftp'] and intense['power_basis'] == 'example'
    assert client.get('/api/profile').json()['ftp_watts'] is None


def test_subjective_calibration_saves_only_comfortable_load(client):
    orientation=next(p for p in client.get('/api/plans').json() if p['meta'].get('calibration'))
    client.post('/api/start',json={'plan_id':orientation['id']})
    engine=main.engine
    engine.mode,engine.connected='daum',True
    engine.daum.set_power=AsyncMock()
    engine.daum.release=AsyncMock()
    engine.step_index,engine.step_remaining=2,60
    engine.cadence,engine.power,engine.target=70,50,50
    assert client.post('/api/calibration/comfortable').status_code==200
    values=client.get('/api/profile').json()
    assert values['comfortable_watts']==50
    assert values['ftp_watts'] is None and values['hr_max'] is None
    client.post('/api/stop')


def test_power_adjustment_applies_after_intensity_for_relative_and_custom_plans(client):
    client.post('/api/profile', json={'ftp_watts': 200, 'power_adjustment_watts': 20})
    template = next(p for p in client.get('/api/plans').json() if p['meta'].get('category') == 'VO₂max')
    assert template['power_adjustment_watts'] == 20
    assert max(s['reference_watts'] for s in template['steps']) == 210
    response = client.post('/api/start', json={'plan_id': template['id'], 'intensity_percent': 80})
    assert response.status_code == 200
    assert max(s['watts'] for s in response.json()['steps']) == 188
    client.post('/api/stop')

    custom = client.post('/api/plans', json={'name': 'Eigene Watt', 'steps': [{'name': 'Basis', 'seconds': 60, 'watts': 100}]}).json()['id']
    response = client.post('/api/start', json={'plan_id': custom, 'intensity_percent': 80})
    assert response.status_code == 200
    assert response.json()['steps'][0]['reference_watts'] == 100
    assert response.json()['target'] == 100


def test_reference_watts_avoid_double_clamping_and_match_half_up_preview_rounding():
    row = {'id': 1, 'name': 'Referenz', 'meta': json.dumps({'relative_ftp': True}),
           'steps': json.dumps([{'name': 'Spitze', 'seconds': 60, 'watts': 158, 'ftp_factor': 1.05}])}
    resolved = resolve_plan(row, TrainingProfile(ftp_watts=400, power_adjustment_watts=20), 50)
    assert resolved['steps'][0]['reference_watts'] == 420
    assert resolved['steps'][0]['watts'] == 230

    row['meta'] = '{}'
    row['steps'] = json.dumps([{'name': 'Niedrig', 'seconds': 60, 'watts': 25}])
    resolved = resolve_plan(row, TrainingProfile(power_adjustment_watts=100), 50)
    assert resolved['steps'][0]['reference_watts'] == 25
    assert resolved['steps'][0]['watts'] == 113


@pytest.mark.parametrize('adjustment,watts,intensity,expected', [(100,400,130,400), (-100,25,50,25)])
def test_adjusted_watts_stay_inside_device_limits(adjustment, watts, intensity, expected):
    row = {'id': 1, 'name': 'Grenzen', 'meta': '{}', 'steps': json.dumps([{'name': 'Block', 'seconds': 60, 'watts': watts}])}
    assert resolve_plan(row, TrainingProfile(power_adjustment_watts=adjustment), intensity)['steps'][0]['watts'] == expected


def test_orientation_ignores_profile_offset_and_intensity_in_preview_and_execution(client):
    client.post('/api/profile', json={'power_adjustment_watts': 100})
    orientation = next(p for p in client.get('/api/plans').json() if p['meta'].get('calibration'))
    expected = [25,40,50,60,70,80,25]
    assert orientation['power_adjustment_watts'] == 0
    assert [s['reference_watts'] for s in orientation['steps']] == expected
    with main.database() as db:
        row = db.execute('SELECT * FROM plans WHERE id=?', (orientation['id'],)).fetchone()
    assert [s['watts'] for s in resolve_plan(row, main.engine.profile, 130)['steps']] == expected
    assert client.post('/api/start', json={'plan_id': orientation['id'], 'intensity_percent': 130}).status_code == 200
    assert [s['watts'] for s in main.engine.steps] == expected


def test_offset_validation_and_pulse_limits_remain_independent(client):
    for offset in (-101,101):
        assert client.post('/api/profile', json={'power_adjustment_watts': offset}).status_code == 422
    values = {'ftp_watts': 200, 'hr_max': 180, 'hr_ceiling': 165, 'hr_max_watts': 100}
    client.post('/api/profile', json=values)
    baseline = next(p for p in client.get('/api/plans').json() if p['meta'].get('category') == 'VO₂max')
    client.post('/api/profile', json={**values, 'power_adjustment_watts': 100})
    adjusted = next(p for p in client.get('/api/plans').json() if p['id'] == baseline['id'])
    assert [(s['hr_low'],s['hr_high']) for s in adjusted['steps']] == [(s['hr_low'],s['hr_high']) for s in baseline['steps']]
    step = adjusted['steps'][0]
    watts, action = PulseController().update(step['watts'], 100, 0, step['hr_low'], step['hr_high'], 165, 25, 100, 0, 0, step['watts'])
    assert watts <= 100 and action == 'run'
    assert PulseController().update(100, 165, 0, step['hr_low'], step['hr_high'], 165, 25, 100, 0, 0, step['watts']) == (25,'stop')
