import asyncio
import json
import time
import sqlite3
from contextlib import contextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.metrics import SessionMetrics
from backend.connectors import DaumConnector


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'cockpit.db')
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as client:
        yield client


def test_selected_devices_skip_unselected_and_keep_demo(client, monkeypatch):
    daum = AsyncMock()
    monkeypatch.setattr(main.engine.daum, 'connect', daum)
    monkeypatch.setattr(main.engine.hr, 'scan', AsyncMock(return_value=[]))
    data = client.post('/api/connect/all', json={'devices': ['hr']}).json()
    assert [r['device'] for r in data['results']] == ['hr']
    assert data['state']['mode'] == 'demo'
    daum.assert_not_awaited()
    assert data['state']['connection_events'][-1]['status'] == 'failed'
    assert client.post('/api/connect/all', json={'devices': []}).json()['results'] == []


def test_pulse_attempt_runs_before_slow_tcp_finishes(client, monkeypatch):
    pulse_started = asyncio.Event()

    async def connect_tcp():
        await asyncio.wait_for(pulse_started.wait(), 1)
        raise ConnectionError('TCP failed')

    async def scan():
        pulse_started.set()
        return [{'address': 'private-address', 'name': 'Gurt'}]

    monkeypatch.setattr(main.engine.daum, 'connect', connect_tcp)
    monkeypatch.setattr(main.engine.hr, 'scan', scan)
    monkeypatch.setattr(main.engine.hr, 'connect', AsyncMock())
    data = client.post('/api/connect/all', json={}).json()
    assert [result['ok'] for result in data['results']] == [False, True]
    assert 'private-address' not in json.dumps(data['state']['connection_events'])
    assert all(result['duration_ms'] >= 0 for result in data['results'])


def test_time_weighted_metrics_omit_missing_pulse_and_zero_is_valid_power():
    metrics = SessionMetrics()
    metrics.add(2, 100, None, 80)
    metrics.add(6, 200, 120, None)
    metrics.add(2, 0, 0, 0)
    result = metrics.summary(12)
    assert result['averages']['power_watts'] == 140
    assert result['coverage_seconds']['power_watts'] == 10
    assert result['averages']['heart_rate_bpm'] == 120
    assert result['coverage_seconds']['heart_rate_bpm'] == 6
    assert result['mechanical_energy_kj'] == 1.4
    assert result['calories_kcal'] is None


def test_missing_and_stale_measurements_do_not_become_zero(client):
    data = client.get('/api/state').json()
    assert data['measurements']['power']['value'] is None
    assert data['measurements']['calories']['value'] is None
    main.engine.hr.bpm, main.engine.hr.updated = 130, time.monotonic() - 5
    hr = client.get('/api/state').json()['measurements']['heart_rate']
    assert not hr['available'] and hr['value'] is None and hr['stale']


def test_completed_summary_is_durable_once_and_user_scoped(client):
    user = main.engine.user_id
    client.post('/api/start', json={})
    main.engine.elapsed = 10
    main.engine.metrics.add(10, 120, None, 80)
    asyncio.run(main.engine.stop(reason='completed'))
    data = client.get('/api/state').json()['completion']
    assert data['reason'] == 'completed' and data['user_id'] == user
    assert data['summary']['averages']['power_watts'] == 120
    ride = client.get('/api/rides').json()[0]
    assert ride['id'] == data['ride_id'] and ride['finish_reason'] == 'completed'
    assert ride['summary']['averages']['heart_rate_bpm'] is None
    client.post('/api/stop')
    assert len(client.get('/api/rides').json()) == 1
    client.post('/api/start', json={})
    assert client.get('/api/state').json()['completion'] is None
    client.post('/api/stop')
    other = client.post('/api/users', json={'name': 'Other'}).json()['id']
    client.post(f'/api/users/{other}/activate', json={})
    assert client.get(f"/api/rides/{ride['id']}/export/json").status_code == 404
    assert client.get('/api/state').json()['completion'] is None


def test_legacy_client_profile_update_retains_additive_personal_fields(client):
    client.post('/api/profile', json={'weight_kg': 75, 'birth_year': 1980})
    assert client.post('/api/profile', json={'ftp_watts': 200}).json()['weight_kg'] == 75
    assert client.post('/api/profile', json={'weight_kg': None}).json()['weight_kg'] is None


def test_read_only_connector_missing_fields_never_become_fabricated_metrics():
    class ReadOnly:
        device_id = 'test_sensor'
        capabilities = dict(activity_type='running', read=['speed'], control=[])

    async def run():
        engine = main.Engine()
        engine.connector = ReadOnly()
        engine.mode = 'daum'  # Legacy transport mode remains API compatible.
        engine.running = True
        engine.last_measurement_at = time.monotonic()
        engine.available_metrics = {'speed'}
        engine.speed = 8
        await engine.apply_power(100)  # No unsupported command is attempted.
        await engine.release_device()
        values = engine.measurements()
        assert values['speed']['value'] == 8
        assert values['speed']['source'] == 'test_sensor'
        assert values['power']['value'] is None
        assert values['cadence']['value'] is None
        sample = engine.measurement()
        assert sample[1] is None and sample[4] is None

    asyncio.run(run())


def test_final_interval_is_integrated_before_regular_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'final.db')
    main.init_db()

    async def run():
        engine = main.Engine()
        engine.user_id = 1
        engine.running = True
        engine.elapsed = 9.5
        engine.steps = [dict(name='End', seconds=10, watts=100)]
        engine.target = 100
        engine.metrics.add(9.5, 100, None, 80)
        engine.energy = 0.95
        engine.select_step()
        original_sleep = asyncio.sleep

        async def one_tick(_):
            if engine.completion:
                raise asyncio.CancelledError
            await original_sleep(0)

        times = iter([0, 1])
        # Patch only the application time namespace through a facade, leaving
        # asyncio's event loop monotonic clock untouched.
        class Clock:
            @staticmethod
            def monotonic():
                return next(times, 1)

        monkeypatch.setattr(main, 'time', Clock)
        monkeypatch.setattr(main.asyncio, 'sleep', one_tick)
        with pytest.raises(asyncio.CancelledError):
            await engine.loop()
        assert engine.elapsed == 10
        assert engine.completion['reason'] == 'completed'
        summary = engine.completion['summary']
        assert summary['coverage_seconds']['power_watts'] == 10
        assert summary['mechanical_energy_kj'] > 0.95

    asyncio.run(run())


def test_failed_transaction_is_retryable_without_duplicate_or_false_completion(client, monkeypatch):
    client.post('/api/start', json={})
    main.engine.elapsed = 5
    main.engine.metrics.add(5, 100, None, 80)
    original_database = main.database
    fail_once = [True]

    @contextmanager
    def database_with_failed_commit():
        with original_database() as db:
            yield db
            if fail_once[0]:
                fail_once[0] = False
                raise sqlite3.OperationalError('simulated transaction failure')

    monkeypatch.setattr(main, 'database', database_with_failed_commit)
    assert client.post('/api/stop').status_code == 503
    state = client.get('/api/state').json()
    assert not state['running'] and state['pending_save']
    assert state['completion'] is None
    assert client.post('/api/start', json={}).status_code == 409
    assert client.post('/api/users', json={'name': 'Blocked'}).status_code == 409
    saved = client.post('/api/stop')
    assert saved.status_code == 200
    assert not saved.json()['pending_save']
    assert saved.json()['completion']['summary']['averages']['power_watts'] == 100
    assert saved.json()['error'] == ''
    client.post('/api/stop')
    assert len(client.get('/api/rides').json()) == 1


def test_remote_reset_clears_previous_summary_and_recording(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'remote.db')
    main.init_db()

    async def run():
        engine = main.Engine()
        engine.user_id = 1
        engine.running, engine.elapsed = True, 10
        engine.metrics.add(10, 100, None, 80)
        await engine.remote_command(1, None)
        assert engine.completion is None
        assert engine.samples == [] and engine.metrics.coverage['power_watts'] == 0
        await engine.remote_command(7, None)
        assert engine.running and engine.completion is None

    asyncio.run(run())


def test_cancelled_daum_handshake_closes_partial_socket():
    async def cancelled_connect():
        raise asyncio.CancelledError

    async def run():
        class Device:
            connect = staticmethod(cancelled_connect)
            close = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            await DaumConnector(Device()).connect()
        Device.close.assert_awaited_once()

    asyncio.run(run())


def test_failed_read_has_elapsed_gap_but_no_fabricated_endpoint_or_statistics(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'read-failure.db')
    main.init_db()

    async def run():
        engine = main.Engine()
        engine.user_id = 1
        engine.mode, engine.running, engine.elapsed = 'daum', True, 4
        engine.connector.capabilities = dict(engine.connector.capabilities, measurement_quality={'power':'verified_measured'})
        engine.power, engine.cadence, engine.speed = 100, 80, 20
        engine.available_metrics = {'power', 'cadence', 'speed'}
        engine.last_measurement_at = 0
        engine.last_target = engine.target
        engine.metrics.add(4, 100, None, 80)
        engine.energy = 0.4
        engine.connector.read = AsyncMock(side_effect=ConnectionError('read failed'))
        original_sleep = asyncio.sleep

        async def one_tick(_):
            if engine.completion:
                raise asyncio.CancelledError
            await original_sleep(0)

        times = iter([0, 1])

        class Clock:
            @staticmethod
            def monotonic():
                return next(times, 1)

        monkeypatch.setattr(main, 'time', Clock)
        monkeypatch.setattr(main.asyncio, 'sleep', one_tick)
        with pytest.raises(asyncio.CancelledError):
            await engine.loop()
        assert engine.elapsed == 5
        assert engine.completion['reason'] == 'error'
        assert engine.completion['summary']['coverage_seconds']['power_watts'] == 4
        assert engine.samples[-1][1] is None and engine.samples[-1][4] is None

    asyncio.run(run())
