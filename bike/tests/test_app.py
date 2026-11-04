import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.devices import frame, parse_training, parse_heart_rate, Daum


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'test.db')
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as client:
        yield client


def test_power_validation_and_plan_ownership(client):
    assert client.post('/api/power', json={'watts':401}).status_code == 422
    assert client.post('/api/power', json={'watts':20}).status_code == 422
    assert client.post('/api/power', json={'watts':130}).json()['target'] == 130
    plan = client.get('/api/plans').json()[0]
    assert client.post('/api/start', json={'plan_id':plan['id']}).status_code == 200
    assert client.post('/api/power', json={'watts':150}).status_code == 409
    assert client.post('/api/mode', json={'mode':'daum'}).status_code == 409
    assert client.post('/api/start', json={}).status_code == 409


def test_plan_persistence_pause_and_session_history(client):
    plan = dict(name='Test', steps=[dict(name='Intervall', seconds=10, watts=125)])
    response = client.post('/api/plans', json=plan)
    assert response.status_code == 201
    plan_id = response.json()['id']
    assert any(p['id']==plan_id for p in client.get('/api/plans').json())
    assert client.post('/api/start', json={'plan_id':plan_id}).json()['target'] == 125
    assert client.post('/api/pause').json()['paused']
    assert not client.post('/api/pause').json()['paused']
    main.engine.elapsed = 5
    assert not client.post('/api/stop').json()['running']
    client.post('/api/stop')
    assert len(client.get('/api/rides').json()) == 1
    assert client.post('/api/start', json={'plan_id':99999}).status_code == 404


def test_plan_step_boundaries():
    engine = main.Engine()
    engine.steps = [dict(name='A', seconds=10, watts=50), dict(name='B', seconds=20, watts=100)]
    engine.elapsed = 9
    assert engine.select_step() and engine.target == 50
    engine.elapsed = 10
    assert engine.select_step() and engine.target == 100
    engine.elapsed = 30
    assert not engine.select_step()


def test_heart_rate_8_and_16_bit():
    assert parse_heart_rate(bytes([0,145])) == 145
    assert parse_heart_rate(bytes([1,44,1])) == 300
    with pytest.raises(ValueError):
        parse_heart_rate(bytes([1,44]))


def test_training_decode():
    data = parse_training('\x1d'.join(['5','120','10','0','20','80','150']))
    assert data == dict(power=150, cadence=80, speed=36.0)


def test_daum_mock_tcp_round_trip():
    async def run():
        async def serve(reader, writer):
            assert await reader.readuntil(b'\x17') == frame('V00')
            writer.write(b'\x06' + frame('V0010'))
            await writer.drain()
            assert await reader.readexactly(1) == b'\x06'
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        daum = Daum()
        daum.reader, daum.writer = await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
        assert await daum.command('V00') == '10'
        await daum.close()
        server.close()
        await server.wait_closed()
    asyncio.run(run())


def test_websocket_and_frontend(client):
    with client.websocket_connect('/ws') as ws:
        assert ws.receive_json()['mode']=='demo'
    if main.dist.exists():
        assert client.get('/').status_code == 200


def test_session_values_belong_to_active_user(client):
    first = client.get('/api/users').json()['active_user_id']
    client.post('/api/profile', json={'ftp_watts': 200})
    client.post('/api/start', json={})
    main.engine.elapsed = 20
    client.post('/api/stop')
    session = client.get('/api/session').json()
    assert session['active_user_id'] == first
    assert session['profile']['ftp_watts'] == 200
    assert len(session['rides']) == 1
    second = client.post('/api/users', json={'name': 'Zweiter Benutzer'}).json()['id']
    client.post(f'/api/users/{second}/activate', json={})
    session = client.get('/api/session').json()
    assert session['active_user_id'] == second
    assert session['profile']['ftp_watts'] is None
    assert session['rides'] == []
    assert len(session['users']) == 2
    assert any(plan['power_basis'] == 'example' for plan in session['plans'])
    assert not any(plan['requires_ftp'] for plan in session['plans'])


def test_auto_off_controls_persist_without_changing_training(client, tmp_path, monkeypatch):
    path = tmp_path / 'power-watch.json'
    monkeypatch.setattr(main, 'POWER_CONFIG', path)
    assert client.get('/api/power-settings').json()['available'] is False
    assert client.post('/api/power-settings', json={'enabled': True}).status_code == 503
    path.write_text('{"enabled":true}')
    assert client.get('/api/power-settings').json()['enabled'] is True
    assert client.post('/api/start', json={}).status_code == 200
    assert client.post('/api/power-settings', json={'enabled': False}).json()['enabled'] is False
    assert client.get('/api/state').json()['running'] is True
    assert json.loads(path.read_text()) == {'enabled': False}
    assert client.post('/api/power-settings', json={'enabled': True}).json()['enabled'] is True
    assert client.post('/api/power-settings', json={'enabled': 'yes'}).status_code == 422
    client.post('/api/stop')


def test_connect_all_partial_failure_still_finds_pulse_sensor(client, monkeypatch):
    daum = main.engine.daum
    monkeypatch.setattr(daum, 'connect', AsyncMock(side_effect=ConnectionError('Bike aus')))
    scan = AsyncMock(return_value=[{'address': 'strap', 'name': 'Mein Gurt'}])
    connect = AsyncMock()
    monkeypatch.setattr(main.engine.hr, 'scan', scan)
    monkeypatch.setattr(main.engine.hr, 'connect', connect)
    response = client.post('/api/connect/all', json={})
    assert response.status_code == 200
    data = response.json()
    assert [(r['device'], r['ok']) for r in data['results']] == [('daum', False), ('hr', True)]
    connect.assert_awaited_once_with('strap')
    assert not data['needs_sensor_choice']
    assert not data['state']['running']


def test_connect_all_requires_choice_among_multiple_pulse_sensors(client, monkeypatch):
    monkeypatch.setattr(main.engine.daum, 'connect', AsyncMock())
    monkeypatch.setattr(main.engine.hr, 'scan', AsyncMock(return_value=[
        {'address': 'a', 'name': 'Gurt A'}, {'address': 'b', 'name': 'Gurt B'},
    ]))
    connect = AsyncMock()
    monkeypatch.setattr(main.engine.hr, 'connect', connect)
    data = client.post('/api/connect/all', json={}).json()
    assert data['needs_sensor_choice']
    assert data['state']['connected']
    connect.assert_not_awaited()


def test_connect_all_keeps_existing_connections_and_does_not_scan(client, monkeypatch):
    main.engine.mode, main.engine.connected = 'daum', True
    main.engine.hr.client = SimpleNamespace(is_connected=True, disconnect=AsyncMock())
    scan = AsyncMock()
    connect = AsyncMock()
    monkeypatch.setattr(main.engine.hr, 'scan', scan)
    monkeypatch.setattr(main.engine.daum, 'connect', connect)
    data = client.post('/api/connect/all', json={}).json()
    assert all(r['ok'] for r in data['results'])
    scan.assert_not_awaited()
    connect.assert_not_awaited()


def test_connection_changes_reject_stale_user_and_active_training(client, monkeypatch):
    user_id = main.engine.user_id
    connect = AsyncMock()
    monkeypatch.setattr(main.engine.hr, 'connect', connect)
    requests = [
        ('connect/all', {'expected_user_id': user_id + 1}),
        ('hr/connect', {'address': 'strap', 'expected_user_id': user_id + 1}),
        ('hr/disconnect', {'expected_user_id': user_id + 1}),
        ('mode', {'mode': 'demo', 'expected_user_id': user_id + 1}),
    ]
    for path, body in requests:
        assert client.post('/api/' + path, json=body).status_code == 409
    connect.assert_not_awaited()
    client.post('/api/start', json={})
    assert client.post('/api/connect/all', json={}).status_code == 409
    assert client.post('/api/hr/connect', json={'address': 'strap'}).status_code == 409
    assert client.post('/api/hr/disconnect', json={}).status_code == 409
    client.post('/api/pause')
    assert client.post('/api/hr/connect', json={'address': 'strap'}).status_code == 200


def test_connect_all_reports_missing_or_failed_scan_without_starting(client, monkeypatch):
    monkeypatch.setattr(main.engine.daum, 'connect', AsyncMock())
    monkeypatch.setattr(main.engine.hr, 'scan', AsyncMock(return_value=[]))
    data = client.post('/api/connect/all', json={}).json()
    assert data['results'][0]['ok']
    assert not data['results'][1]['ok']
    assert not data['state']['running']
    monkeypatch.setattr(main.engine.hr, 'scan', AsyncMock(side_effect=TimeoutError()))
    data = client.post('/api/connect/all', json={}).json()
    assert not data['results'][1]['ok']
    assert 'Zeitüberschreitung' in data['results'][1]['message']
