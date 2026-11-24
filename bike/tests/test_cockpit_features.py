import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import main
from backend.cockpit import GeneratorRequest, generate_plan, migrate
from backend.training import TrainingProfile


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'cockpit.db')
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as client:
        yield client


@pytest.mark.parametrize('kind', ['endurance', 'interval', 'recovery'])
@pytest.mark.parametrize('minutes', [11, 20, 37, 120])
def test_generated_phases_exact_and_inside_device_limits(kind, minutes):
    body = GeneratorRequest(kind=kind, minutes=minutes, watts=400)
    plan = generate_plan(body)
    assert plan == generate_plan(body)
    assert sum(s['seconds'] for s in plan['steps']) == minutes * 60
    assert 1 <= len(plan['steps']) <= 100
    assert all(10 <= s['seconds'] <= 7200 and 25 <= s['watts'] <= 400 for s in plan['steps'])
    assert plan['steps'][0]['name'] == 'Aufwärmen'
    assert plan['steps'][-1]['name'] == 'Ausrollen'


def test_profile_optional_fields_validate_without_inventing_heart_rate():
    value = TrainingProfile(birth_year=1980, weight_kg=80, height_cm=180, sex='unspecified')
    assert value.hr_max is None and value.ftp_watts is None
    assert TrainingProfile.model_validate_json(value.model_dump_json()) == value
    for data in ({'weight_kg': float('nan')}, {'birth_year': 9999}, {'height_cm': 0}, {'sex': 'other'}):
        with pytest.raises(ValidationError):
            TrainingProfile(**data)


def test_generator_preview_has_no_write_and_saved_profile_is_editable(client):
    before = client.get('/api/plans').json()
    preview = client.get('/api/generator/preview?kind=interval&minutes=37&watts=125')
    assert preview.status_code == 200
    assert client.get('/api/plans').json() == before
    saved = client.post('/api/generator/save', json={'kind': 'interval', 'minutes': 37, 'watts': 125})
    assert saved.status_code == 201
    plan = next(p for p in client.get('/api/plans').json() if p['id'] == saved.json()['plan_id'])
    assert sum(s['seconds'] for s in plan['steps']) == 37 * 60
    assert client.post('/api/start', json={'plan_id': plan['id']}).status_code == 200
    client.post('/api/stop')
    assert client.get('/api/generator/preview?minutes=10').status_code == 422
    assert client.post('/api/generator/save', json={'minutes': 30, 'expected_user_id': 9999}).status_code == 409


def real_ride(seconds=1200, watts=100, coverage=1200, weight=80):
    summary = dict(duration_seconds=seconds, averages=dict(power_watts=watts, heart_rate_bpm=None, cadence_rpm=80),
                   coverage_seconds=dict(power_watts=coverage, heart_rate_bpm=0, cadence_rpm=coverage),
                   mechanical_energy_kj=watts * coverage / 1000, calories_kcal=None, weight_kg=weight,
                   sources=dict(power_watts='independent_test_meter'),
                   power_measurement_verified=True, measurement_quality=dict(power_watts='verified_measured'))
    with main.database() as db:
        cur = db.execute('''INSERT INTO rides (seconds,distance,energy,mode,user_id,summary_json,activity_type,finish_reason)
            VALUES (?,?,?,?,?,?,?,?)''', (seconds, 5, watts * coverage / 1000, 'daum', main.engine.user_id,
                                         json.dumps(summary), 'indoor_cycling', 'completed'))
        return cur.lastrowid


def unverify_ride(ride_id):
    with main.database() as db:
        row = db.execute('SELECT summary_json FROM rides WHERE id=?', (ride_id,)).fetchone()
        summary = json.loads(row['summary_json'])
        summary.pop('power_measurement_verified', None)
        summary.pop('measurement_quality', None)
        summary['sources'] = dict(power_watts='daum')
        encoded = json.dumps(summary)
        db.execute('UPDATE rides SET summary_json=?,samples_json=? WHERE id=?',
                   (encoded, json.dumps([[0, 200, 200], [1200, 300, 300]]), ride_id))
        return encoded


def test_old_daum_reported_averages_cannot_produce_physical_analysis_and_are_not_rewritten(client):
    ride_id = real_ride(watts=300)
    stored = unverify_ride(ride_id)
    result = client.get('/api/analysis').json()
    assert result['available'] is False and result['power_measurement_verified'] is False
    assert result['averages']['power_watts'] is None and result['coverage_seconds']['power_watts'] == 0
    assert result['reported_unverified_power_watts'] == 300
    assert result['watts_per_kg'] is None and result['intensity']['ratio'] is None
    assert result['comparison'] is None and result['trend'] is None and result['proposal'] is None
    assert any('nicht als unabhängig gemessene' in note for note in result['limitations'])
    assert client.post('/api/planner/adopt', json={'ride_id': ride_id}).status_code == 409
    with main.database() as db:
        assert db.execute('SELECT summary_json FROM rides WHERE id=?', (ride_id,)).fetchone()[0] == stored


def test_verified_measurement_does_not_compare_against_unverified_old_daum_average(client):
    old = real_ride(watts=300)
    unverify_ride(old)
    real_ride(watts=100)
    result = client.get('/api/analysis').json()
    assert result['available'] and result['watts_per_kg'] == 1.25
    assert result['comparison'] is None


@pytest.mark.parametrize('summary', [
    dict(power_measurement_verified=True),
    dict(measurement_quality=dict(power_watts='verified_measured')),
    dict(power_measurement_verified=True, measurement_quality=dict(power_watts='protocol_ack')),
    dict(power_measurement_verified=False, measurement_quality=dict(power_watts='verified_measured')),
])
def test_independent_power_provenance_requires_both_explicit_measurement_fields(summary):
    from backend.cockpit import power_is_verified
    assert not power_is_verified(summary)


def test_analysis_requires_real_coverage_and_consent_then_adoption_is_idempotent(client):
    client.post('/api/start', json={})
    main.engine.elapsed = 30
    client.post('/api/stop')
    assert not client.get('/api/analysis').json()['available']  # Demo excluded.
    old = real_ride(watts=90)
    current = real_ride(watts=100)
    analysis = client.get('/api/analysis').json()
    assert analysis['ride_id'] == current
    assert analysis['watts_per_kg'] == 1.25
    assert analysis['comparison']['ride_id'] == old
    assert analysis['comparison']['power_delta_watts'] == 10
    assert analysis['proposal']['steps'][1]['watts'] <= 100
    assert client.get('/api/planner').json() == []
    first = client.post('/api/recommendation/adopt', json={'ride_id': current}).json()
    again = client.post('/api/planner/adopt', json={'ride_id': current}).json()
    assert first['plan_id'] == again['plan_id']
    assert again['already_adopted']
    assert len(client.get('/api/planner').json()) == 1
    insufficient = real_ride(coverage=100)
    assert client.get(f'/api/analysis?ride_id={insufficient}').json()['proposal'] is None
    assert client.post('/api/recommendation/adopt', json={'ride_id': insufficient}).status_code == 409


def test_personal_calendar_strength_progress_and_user_isolation(client):
    body = dict(name='Vor dem Rad', strength_position='before', scheduled_for='2026-11-10',
                strength=[dict(name='Liegestütze', variant='Wand', sets=2, repetitions=6, rest_seconds=60),
                          dict(name='Armkreisen', variant='Aufwärmen', sets=1, repetitions=10, rest_seconds=30)])
    created = client.post('/api/planner', json=body)
    assert created.status_code == 201
    entry = created.json()
    assert entry['strength'][0]['variant'] == 'Wand'
    progress = client.post(f"/api/planner/{entry['id']}/status", json={'status': 'planned', 'strength_completed': [0]})
    assert progress.json()['strength_completed'] == [0]
    assert client.post(f"/api/planner/{entry['id']}/status", json={'strength_completed': [9]}).status_code == 422
    user = client.post('/api/users', json={'name': 'Andere Person'}).json()['id']
    client.post(f'/api/users/{user}/activate', json={})
    assert client.get('/api/planner').json() == []
    assert client.post(f"/api/planner/{entry['id']}/status", json={'status': 'completed'}).status_code == 404
    with main.database() as db:
        migrate(db)
        migrate(db)
        assert db.execute('SELECT COUNT(*) FROM training_entries').fetchone()[0] == 1


def test_manual_treadmill_keeps_absent_metrics_missing_and_belongs_to_user(client):
    result = client.post('/api/manual/treadmill', json={'seconds': 1200, 'incline_percent': 3})
    assert result.status_code == 201
    summary = result.json()['summary']
    assert summary['source'] == 'manual'
    assert summary['averages']['power_watts'] is None
    assert summary['calories_kcal'] is None
    ride = client.get('/api/rides').json()[0]
    assert ride['distance'] is None and ride['energy'] is None
    assert ride['activity_type'] == 'treadmill'
    assert not client.get('/api/analysis').json()['available']
    assert client.post('/api/manual/treadmill', json={'seconds': 1200, 'started_at': '2026-11-09T10:00:00'}).status_code == 422
    assert client.post('/api/manual/treadmill', json={'seconds': 1200, 'distance_km': -2}).status_code == 422
    assert client.post('/api/manual/treadmill', json={'seconds': 1200, 'expected_user_id': 999}).status_code == 409


def test_analysis_does_not_apply_todays_weight_to_old_unweighted_ride(client):
    client.post('/api/profile', json={'weight_kg': 75})
    ride = real_ride(weight=None)
    data = client.get(f'/api/analysis?ride_id={ride}').json()
    assert data['available'] and data['watts_per_kg'] is None


def test_plan_edit_preserves_progress_for_date_change_but_resets_changed_exercises(client):
    body = dict(name='Kraft optional', strength_position='before', strength=[
        dict(name='Liegestütze', variant='Wand', sets=2, repetitions=6, rest_seconds=60)])
    entry_id = client.post('/api/planner', json=body).json()['id']
    client.post(f'/api/planner/{entry_id}/progress', json={'status': 'completed', 'strength_completed': [0]})
    edited = client.put(f'/api/planner/{entry_id}', json={**body, 'scheduled_for': '2026-11-11'})
    assert edited.status_code == 200
    assert edited.json()['status'] == 'completed'
    assert edited.json()['strength_completed'] == [0]
    body['strength'][0]['repetitions'] = 8
    changed = client.post(f'/api/planner/{entry_id}/edit', json=body).json()
    assert changed['status'] == 'planned' and changed['strength_completed'] == []
    assert client.put(f'/api/planner/{entry_id}', json={**body, 'expected_user_id': 999}).status_code == 409
    other = client.post('/api/users', json={'name': 'Andere Person'}).json()['id']
    client.post(f'/api/users/{other}/activate', json={})
    assert client.put(f'/api/planner/{entry_id}', json=body).status_code == 404


def test_manual_exports_preserve_unknown_values_and_reject_other_users(client):
    missing = client.post('/api/manual/treadmill', json={'seconds': 1200}).json()['ride_id']
    data = client.get(f'/api/rides/{missing}/export/json').json()
    assert data['activity'] == 'treadmill'
    assert data['summary']['distance'] is None and data['summary']['energy'] is None
    assert data['summary']['statistics']['source'] == 'manual'
    assert client.get(f'/api/rides/{missing}/export/csv').status_code == 200
    assert client.get(f'/api/rides/{missing}/export/tcx').status_code == 422
    known = client.post('/api/manual/treadmill', json={'seconds': 1200, 'distance_km': 2}).json()['ride_id']
    tcx = client.get(f'/api/rides/{known}/export/tcx')
    assert tcx.status_code == 200
    assert 'Sport="Running"' in tcx.text and '<DistanceMeters>2000' in tcx.text
    other = client.post('/api/users', json={'name': 'Andere Person'}).json()['id']
    client.post(f'/api/users/{other}/activate', json={})
    for ride_id in [missing, known]:
        for format in ['json', 'csv', 'tcx']:
            assert client.get(f'/api/rides/{ride_id}/export/{format}').status_code == 404


def test_recommendation_does_not_cross_users_or_follow_safety_stop(client):
    ride_id = real_ride()
    with main.database() as db:
        db.execute('UPDATE rides SET finish_reason=? WHERE id=?', ('safety', ride_id))
    data = client.get(f'/api/analysis?ride_id={ride_id}').json()
    assert data['available'] and data['proposal'] is None
    assert client.post('/api/recommendation/adopt', json={'ride_id': ride_id}).status_code == 409
    other = client.post('/api/users', json={'name': 'Andere Person'}).json()['id']
    client.post(f'/api/users/{other}/activate', json={})
    assert client.get(f'/api/analysis?ride_id={ride_id}').json()['ride_id'] is None
    assert client.post('/api/recommendation/adopt', json={'ride_id': ride_id}).status_code == 409
