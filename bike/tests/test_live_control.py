"""Live override semantics with an isolated DB and protocol/mock adapters."""
import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.connectors import DaumConnector
from backend.devices import frame
from backend.training import TrainingProfile


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'live-control.db')
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as client:
        yield client


def short_plan(client):
    return client.post('/api/plans', json={'name':'Override', 'steps':[
        {'name':'A','seconds':10,'watts':60}, {'name':'B','seconds':20,'watts':100}]}).json()['id']


def test_override_keeps_progress_and_baseline_across_segment_change(client):
    plan_id = short_plan(client)
    started = client.post('/api/start', json={'plan_id':plan_id}).json()
    main.engine.elapsed, main.engine.distance = 8, 1.25
    response = client.post('/api/power', json={'watts':155, 'source':'manual_slider',
                                              'expected_session_id':started['session_id']})
    assert response.status_code == 200
    assert response.json()['target'] == 155 and response.json()['control_mode'] == 'manual_override'
    assert main.engine.elapsed == 8 and main.engine.distance == 1.25
    main.engine.elapsed = 12
    main.engine.select_step()
    assert main.engine.target == 195 and main.engine.step_index == 1
    assert main.engine.planned_power() == 100 and main.engine.step_remaining == 18
    restored = client.post('/api/power/plan', json={'expected_session_id':started['session_id']}).json()
    assert restored['target'] == 100 and restored['control_mode'] == 'plan'
    assert restored['elapsed'] == 12 and main.engine.steps[0]['watts'] == 60
    assert next(p for p in client.get('/api/plans').json() if p['id'] == plan_id)['steps'][1]['watts'] == 100


def test_override_uses_user_and_device_limits_server_side(client):
    profile = client.get('/api/profile').json()
    profile.update(power_min_watts=40, power_max_watts=160)
    assert client.post('/api/profile', json=profile).status_code == 200
    state = client.get('/api/state').json()
    assert state['power_limits']['minimum'] == 40 and state['power_limits']['maximum'] == 160
    for watts in (39, 161, -1, 401, 100.5, True, '100'):
        assert client.post('/api/power', json={'watts':watts}).status_code == 422
    assert client.post('/api/power', json={'watts':155}).status_code == 200
    assert client.post('/api/power', json={'watts':100, 'expected_user_id':9999}).status_code == 409


def test_paused_override_prepares_without_device_write_and_resume_same_position(client):
    plan_id = short_plan(client)
    client.post('/api/start', json={'plan_id':plan_id})
    main.engine.elapsed, main.engine.distance = 7, .5
    main.engine.mode, main.engine.connected = 'daum', True
    writer = AsyncMock(return_value={'confirmed':True,'watts':25,'source':'protocol_ack'})
    main.engine.connector.set_power = writer
    paused = client.post('/api/pause').json()
    assert paused['paused'] and paused['applied_target_watts'] == 25
    assert paused['requested_target_watts'] == 60
    assert writer.await_count == 1
    prepared = client.post('/api/power', json={'watts':145}).json()
    assert prepared['requested_target_watts'] == 145 and prepared['applied_target_watts'] == 25
    assert prepared['target_command_status'] == 'paused' and writer.await_count == 1
    resumed = client.post('/api/pause').json()
    assert resumed['running'] and not resumed['paused']
    assert resumed['requested_target_watts'] == 145
    assert resumed['elapsed'] == 7 and resumed['distance'] == .5
    assert main.engine.pause_count == 1


def test_paused_manual_event_does_not_log_placeholder_zero_as_measurement(client):
    client.post('/api/start',json={'plan_id':short_plan(client)})
    main.engine.power=88
    main.engine.available_metrics={'power','cadence','speed'}
    main.engine.last_measurement_at=time.monotonic()
    client.post('/api/pause')
    assert main.engine.power==0  # compatibility placeholder, not a reading
    result=client.post('/api/power',json={'watts':145,'source':'manual_slider'}).json()
    event=next(e for e in reversed(result['control_events']) if e['source']=='manual_slider')
    assert event['measured_watts'] is None
    assert result['measurements']['power']['value'] is None


def test_latest_slot_throttles_and_sends_final_target_only():
    async def run():
        engine = main.Engine()
        engine.mode, engine.connected, engine.running = 'daum', True, True
        sent=[]
        async def ack(watts):
            sent.append(watts)
            return dict(confirmed=True, watts=watts, source='protocol_ack')
        engine.connector.set_power = ack
        engine.request_target(100, 'manual_button', manual=True)
        await engine.flush_target(now=0)
        engine.last_command_at = 0
        for watts in range(105,181,5):
            engine.request_target(watts, 'manual_slider', manual=True)
            await engine.flush_target(now=.1)
        assert sent == [100]
        await engine.flush_target(now=.5)
        assert sent == [100,180]
        assert engine.applied_target_watts == 180
    asyncio.run(run())


def test_same_confirmed_value_and_reverted_pending_value_do_not_stay_pending():
    async def run():
        engine=main.Engine()
        engine.mode,engine.connected,engine.running='daum',True,True
        async def ack(watts):
            return dict(confirmed=True,watts=watts,source='protocol_ack')
        engine.connector.set_power=AsyncMock(side_effect=ack)
        engine.request_target(70,'manual_button',manual=True)
        await engine.flush_target(force=True)
        engine.request_target(90,'manual_slider',manual=True)
        engine.request_target(70,'manual_slider',manual=True)
        await engine.flush_target(force=True)
        assert engine.target_command_status=='applied' and engine.applied_target_watts==70
        assert engine.connector.set_power.await_count==1
        engine.request_target(70,'manual_button',manual=True)
        assert engine.target_command_status=='applied'
        engine.mode='demo'
        await engine.flush_target(force=True)
        assert engine.target_command_status=='simulated'
    asyncio.run(run())


def test_nonfinite_untrusted_power_request_is_rejected_without_server_error(client):
    for value in ('NaN','Infinity','-Infinity'):
        response=client.post('/api/power',content='{"watts":'+value+'}',headers={'Content-Type':'application/json'})
        assert response.status_code==422


def test_free_training_initial_target_obeys_custom_maximum(client):
    profile=client.get('/api/profile').json()
    profile.update(power_min_watts=25,power_max_watts=70)
    client.post('/api/profile',json=profile)
    started=client.post('/api/start',json={}).json()
    assert started['requested_target_watts']==70


def test_later_request_while_old_command_in_flight_remains_pending_until_ack():
    async def run():
        engine = main.Engine()
        engine.mode, engine.connected, engine.running = 'daum', True, True
        entered, release = asyncio.Event(), asyncio.Event()
        sent=[]
        async def ack(watts):
            sent.append(watts)
            if len(sent) == 1:
                entered.set()
                await release.wait()
            return dict(confirmed=True,watts=watts,source='protocol_ack')
        engine.connector.set_power = ack
        engine.request_target(100,'manual_button',manual=True)
        task=asyncio.create_task(engine.flush_target(force=True))
        await entered.wait()
        engine.request_target(155,'manual_slider',manual=True)
        release.set()
        await task
        assert engine.target == 155 and engine.applied_target_watts == 100
        assert engine.target_command_status == 'pending'
        await engine.flush_target(force=True)
        assert sent == [100,155] and engine.applied_target_watts == 155
        assert engine.target_command_status == 'applied'
    asyncio.run(run())


def test_demo_never_claims_real_applied_target_or_confuses_measured():
    async def run():
        engine=main.Engine()
        engine.running=True
        engine.power=81
        engine.request_target(155,'manual_slider',manual=True)
        await engine.flush_target(force=True)
        assert engine.applied_target_watts is None
        assert engine.target_command_status == 'simulated'
        assert engine.power == 81 and engine.target == 155
    asyncio.run(run())


def test_unconfirmed_adapter_and_rejection_never_claim_applied():
    async def run():
        engine=main.Engine()
        engine.mode,engine.running,engine.connected='daum',True,True
        engine.connector.set_power=AsyncMock(return_value=None)
        await engine.flush_target(force=True)
        assert engine.applied_target_watts is None and engine.target_command_status == 'unconfirmed'
        engine.connector.set_power=AsyncMock(side_effect=TimeoutError())
        engine.request_target(155,'manual_button',manual=True)
        with pytest.raises(TimeoutError):
            await engine.flush_target(force=True)
        assert engine.applied_target_watts is None and engine.target_command_status == 'error'
        assert engine.control_events[-1]['event'] == 'error'
    asyncio.run(run())


def test_stale_session_rejects_late_slider_after_stop_and_new_start(client):
    first=client.post('/api/start',json={}).json()
    client.post('/api/stop')
    request={'watts':155,'expected_session_id':first['session_id']}
    assert client.post('/api/power',json=request).status_code == 409
    second=client.post('/api/start',json={}).json()
    assert first['session_id'] != second['session_id']
    assert client.post('/api/power',json=request).status_code == 409


def test_persistent_control_events_and_original_plan_survive_edit(client):
    plan_id=short_plan(client)
    client.post('/api/start',json={'plan_id':plan_id})
    main.engine.elapsed=12
    main.engine.select_step()
    client.post('/api/power',json={'watts':155,'source':'manual_slider'})
    saved=client.post('/api/stop').json()
    summary=saved['completion']['summary']
    assert summary['plan_steps'][1]['watts'] == 100
    assert summary['manual_adjustments'] == 1
    with main.database() as db:
        db.execute('UPDATE plans SET steps=? WHERE id=?',(json.dumps([dict(name='Edited',seconds=10,watts=40)]),plan_id))
    ride=client.get('/api/rides').json()[0]
    assert ride['summary']['plan_steps'][1]['watts'] == 100
    event=next(e for e in ride['control_events'] if e['source']=='manual_slider')
    assert event['requested_target_watts'] == 155 and event['elapsed_seconds'] == 12
    assert event['applied_target_watts'] is None


def test_hr_safety_clears_override_and_requires_explicit_resume_on_stale_signal():
    async def run():
        engine=main.Engine()
        engine.profile=TrainingProfile(hr_max=180,hr_ceiling=170)
        engine.running=True
        engine.training_mode='hr'
        engine.steps=[dict(name='Cardio',seconds=300,watts=80,hr_low=110,hr_high=125)]
        engine.cadence=80
        engine.request_target(130,'manual_button',manual=True)
        engine.hr.bpm,engine.hr.updated=120,time.monotonic()
        assert await engine.regulate_pulse(time.monotonic())=='run'
        assert engine.target==130 and engine.manual_override==130
        engine.hr.updated=time.monotonic()-4
        assert await engine.regulate_pulse(time.monotonic())=='pause'
        assert engine.paused and engine.manual_override is None and engine.target==25
        engine.hr.updated=time.monotonic()
        assert engine.paused
    asyncio.run(run())


def test_adapter_confirmation_is_protocol_ack_only():
    async def run():
        confirmed=dict(confirmed=True,watts=155,source='protocol_ack',detail='echoed_value')
        device=type('Device',(),{'set_power':AsyncMock(return_value=confirmed)})()
        result=await DaumConnector(device).set_power(155)
        assert result==confirmed
        device.set_power.assert_awaited_once_with(155)
    asyncio.run(run())


def test_superseded_s201_handshake_does_not_write_old_s23():
    async def run():
        engine=main.Engine()
        engine.mode,engine.connected,engine.running='daum',True,True
        commands=[]
        entered,release=asyncio.Event(),asyncio.Event()
        async def command(value):
            commands.append(value)
            if len(commands)==1:
                entered.set()
                await release.wait()
            return '1' if value == 'S201' else value[3:]
        engine.daum.command=command
        engine.request_target(100,'manual_slider',manual=True)
        task=asyncio.create_task(engine.flush_target(force=True))
        await entered.wait()
        engine.request_target(155,'manual_slider',manual=True)
        release.set()
        await task
        assert commands==['S201']
        assert engine.applied_target_watts is None and engine.target_command_status=='pending'
        await engine.flush_target(force=True)
        assert commands==['S201','S201','S23155.00']
        assert engine.applied_target_watts==155
    asyncio.run(run())


def test_stop_intent_cancels_unsent_old_target_before_acquiring_engine_lock(monkeypatch):
    async def run():
        engine=main.Engine()
        monkeypatch.setattr(main,'engine',engine)
        engine.mode,engine.connected,engine.running='daum',True,True
        commands=[]
        entered,release=asyncio.Event(),asyncio.Event()
        async def command(value):
            commands.append(value)
            if len(commands)==1:
                entered.set()
                await release.wait()
            return '1' if value == 'S201' else value[3:]
        engine.daum.command=command
        engine.request_target(155,'manual_slider',manual=True)
        async def locked_flush():
            async with engine.lock:
                await engine.flush_target(force=True)
        sending=asyncio.create_task(locked_flush())
        await entered.wait()
        stopping=asyncio.create_task(main.stop())
        await asyncio.sleep(0)
        assert engine.stop_requested and engine.session_state=='stopping'
        release.set()
        await sending
        await stopping
        assert commands==['S201','S201','S2325.00']
        assert not engine.running and not engine.stop_requested
        assert engine.session_state=='stopped'
    asyncio.run(run())


def test_mock_tcp_confirms_s201_s23_without_inventing_measured_power():
    async def run():
        received=[]
        async def serve(reader,writer):
            try:
                for command in ('S201','S23155.00'):
                    received.append(await reader.readuntil(b'\x17'))
                    writer.write(b'\x06'+frame(command))
                    await writer.drain()
                    assert await reader.readexactly(1)==b'\x06'
            finally:
                writer.close()
                await writer.wait_closed()
        server=await asyncio.start_server(serve,'127.0.0.1',0)
        engine=main.Engine()
        engine.daum.reader,engine.daum.writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
        engine.mode,engine.connected,engine.running='daum',True,True
        engine.request_target(155,'manual_slider',manual=True)
        await engine.flush_target(force=True)
        assert received==[frame('S201'),frame('S23155.00')]
        assert engine.applied_target_watts==155 and engine.target_confirmation_source=='protocol_ack'
        assert engine.snapshot()['measured_watts'] is None
        await engine.connector.close()
        server.close()
        await server.wait_closed()
    asyncio.run(run())


def test_reconnect_discards_old_override_without_sending_it(client,monkeypatch):
    client.post('/api/power',json={'watts':155})
    monkeypatch.setattr(main.engine.daum,'connect',AsyncMock())
    writer=AsyncMock()
    monkeypatch.setattr(main.engine.daum,'set_power',writer)
    state=client.post('/api/mode',json={'mode':'daum'}).json()
    assert state['connected'] and state['requested_target_watts']==25
    assert main.engine.manual_override is None and state['applied_target_watts'] is None
    writer.assert_not_awaited()


def test_offset_clamps_each_stage_and_can_be_reversed(client):
    profile = client.get('/api/profile').json()
    profile.update(power_min_watts=40, power_max_watts=160)
    assert client.post('/api/profile', json=profile).status_code == 200
    started = client.post('/api/start', json={'plan_id':short_plan(client)}).json()
    session = started['session_id']
    assert client.post('/api/power', json={'watts':140}).json()['power_offset_watts'] == 80
    main.engine.elapsed = 12
    main.engine.select_step()
    assert main.engine.target == 160
    assert main.engine.manual_override == 80
    assert client.post('/api/power', json={'watts':40}).json()['power_offset_watts'] == -60
    main.engine.elapsed = 1
    main.engine.select_step()
    assert main.engine.target == 40
    assert main.engine.manual_override == -60
    assert client.post('/api/power/plan', json={'expected_session_id':session}).json()['target'] == 60
