import json
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.zwift import ZwiftBridge


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'users.db')
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as client:
        yield client


def test_users_isolate_values_plans_and_rides(client):
    first = client.get('/api/users').json()['active_user_id']
    client.post('/api/profile', json={'ftp_watts': 200})
    assert client.post('/api/start', json={}).status_code == 200
    main.engine.elapsed = 30
    client.post('/api/stop')
    assert len(client.get('/api/rides').json()) == 1
    second = client.post('/api/users', json={'name': 'Anna'}).json()['id']
    assert client.post(f'/api/users/{second}/activate', json={}).status_code == 200
    assert client.get('/api/profile').json()['ftp_watts'] is None
    assert client.get('/api/rides').json() == []
    template = next(p for p in client.get('/api/plans').json() if p['meta'].get('relative_ftp'))
    assert client.post('/api/start', json={'plan_id': template['id']}).status_code == 200
    assert client.get('/api/profile').json()['ftp_watts'] is None
    client.post('/api/stop')
    client.post('/api/profile', json={'ftp_watts': 100})
    assert client.post('/api/start', json={'plan_id': template['id']}).status_code == 200
    assert main.engine.steps[0]['watts'] == 50
    client.post('/api/stop')
    client.post(f'/api/users/{first}/activate', json={})
    assert client.get('/api/profile').json()['ftp_watts'] == 200
    assert len(client.get('/api/rides').json()) == 1


def test_user_changes_locked_during_training_and_zwift(client):
    user_id = client.get('/api/users').json()['active_user_id']
    client.post('/api/start', json={})
    for path, body in [('users', {'name': 'Anna'}), (f'users/{user_id}/activate', {}), (f'users/{user_id}/rename', {'name': 'Neu'})]:
        assert client.post('/api/' + path, json=body).status_code == 409
    client.post('/api/stop')
    main.engine.zwift = ZwiftBridge(main.engine)
    main.engine.zwift.armed = True
    assert client.post(f'/api/users/{user_id}/activate', json={}).status_code == 409
    main.engine.zwift.armed = False


def test_user_validation_and_missing_user(client):
    assert client.post('/api/users', json={'name': '   '}).status_code == 422
    assert client.post('/api/users/999/activate', json={}).status_code == 404
    assert client.post('/api/users/999/rename', json={'name': 'Name'}).status_code == 404


def test_active_user_and_values_survive_restart(client, monkeypatch):
    user_id = client.post('/api/users', json={'name': 'Anna'}).json()['id']
    client.post(f'/api/users/{user_id}/activate', json={})
    client.post('/api/profile', json={'ftp_watts': 175, 'hr_max': 180, 'hr_ceiling': 165})
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as restarted:
        assert restarted.get('/api/users').json()['active_user_id'] == user_id
        assert restarted.get('/api/profile').json()['ftp_watts'] == 175


def test_legacy_migration_preserves_values_and_rides(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    monkeypatch.setattr(main, 'DB', path)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT INTO settings VALUES (?, ?)', ('training_profile', json.dumps({'ftp_watts': 190})))
        db.execute('CREATE TABLE rides (id INTEGER PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP, seconds REAL, distance REAL, energy REAL, mode TEXT)')
        db.execute("INSERT INTO rides (seconds,distance,energy,mode) VALUES (30,0.1,2,'demo')")
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as client:
        assert client.get('/api/profile').json()['ftp_watts'] == 190
        assert len(client.get('/api/rides').json()) == 1
        main.init_db()
        assert len(client.get('/api/users').json()['users']) == 1


def test_stale_device_cannot_overwrite_another_user_or_start_its_ride(client):
    first = client.get('/api/users').json()['active_user_id']
    client.post('/api/profile', json={'ftp_watts': 190})
    second = client.post('/api/users', json={'name': 'Anna'}).json()['id']
    client.post(f'/api/users/{second}/activate', json={})

    response = client.post('/api/profile', json={'expected_user_id': first, 'ftp_watts': 250})
    assert response.status_code == 409
    assert client.get('/api/profile').json()['ftp_watts'] is None
    response = client.post('/api/start', json={'expected_user_id': first})
    assert response.status_code == 409
    assert client.get('/api/state').json()['running'] is False

    assert client.post('/api/start', json={'expected_user_id': second}).status_code == 200
    client.post('/api/stop')
    client.post(f'/api/users/{first}/activate', json={})
    assert client.get('/api/profile').json()['ftp_watts'] == 190


def test_expected_user_metadata_is_not_saved_in_training_values(client):
    user_id = client.get('/api/users').json()['active_user_id']
    response = client.post('/api/profile', json={'expected_user_id': user_id, 'ftp_watts': 180})
    assert response.status_code == 200
    assert response.json()['ftp_watts'] == 180
    assert 'expected_user_id' not in response.json()
    assert type(main.engine.profile) is main.TrainingProfile
    with main.database() as db:
        saved = json.loads(db.execute('SELECT profile FROM users WHERE id=?', (user_id,)).fetchone()[0])
        legacy = json.loads(db.execute("SELECT value FROM settings WHERE key='training_profile'").fetchone()[0])
    assert saved == legacy == response.json()


def test_actual_user_switch_disconnects_previous_users_pulse_sensor(client):
    first = client.get('/api/users').json()['active_user_id']
    sensor = SimpleNamespace(is_connected=True, disconnect=AsyncMock())
    main.engine.hr.client = sensor
    main.engine.hr.bpm, main.engine.hr.updated = 120, time.monotonic()

    assert client.post(f'/api/users/{first}/activate', json={}).status_code == 200
    sensor.disconnect.assert_not_awaited()
    assert client.get('/api/state').json()['hr_fresh'] is True

    second = client.post('/api/users', json={'name': 'Anna'}).json()['id']
    assert client.post(f'/api/users/{second}/activate', json={}).status_code == 200
    sensor.disconnect.assert_awaited_once()
    state = client.get('/api/state').json()
    assert state['heart_rate'] is None
    assert state['hr_connected'] is False
    assert state['hr_fresh'] is False
    client.post('/api/profile', json={'hr_max': 180, 'hr_ceiling': 165})
    assert client.post('/api/start', json={'training_mode': 'hr'}).status_code == 409


def test_power_adjustment_is_personal_and_survives_restart(client, monkeypatch):
    first = client.get('/api/users').json()['active_user_id']
    plan_id = client.post('/api/plans', json={'name': 'Gemeinsam', 'steps': [{'name': 'Basis', 'seconds': 60, 'watts': 100}]}).json()['id']
    assert client.post('/api/profile', json={'power_adjustment_watts': 20}).status_code == 200
    first_preview = next(p for p in client.get('/api/plans').json() if p['id'] == plan_id)
    assert first_preview['steps'][0]['watts'] == 120

    second = client.post('/api/users', json={'name': 'Anna'}).json()['id']
    client.post(f'/api/users/{second}/activate', json={})
    assert client.get('/api/profile').json()['power_adjustment_watts'] == 0
    client.post('/api/profile', json={'power_adjustment_watts': -20})
    assert client.post('/api/start', json={'plan_id': plan_id}).json()['target'] == 80
    client.post('/api/stop')

    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as restarted:
        assert restarted.get('/api/profile').json()['power_adjustment_watts'] == -20
        assert next(p for p in restarted.get('/api/plans').json() if p['id'] == plan_id)['steps'][0]['watts'] == 80
        restarted.post(f'/api/users/{first}/activate', json={})
        assert restarted.get('/api/profile').json()['power_adjustment_watts'] == 20
        assert next(p for p in restarted.get('/api/plans').json() if p['id'] == plan_id)['steps'][0]['watts'] == 120


def test_delete_ride_is_scoped_to_active_user(client):
    first = client.get('/api/users').json()['active_user_id']
    client.post('/api/start', json={})
    main.engine.elapsed = 30
    client.post('/api/stop')
    ride = client.get('/api/rides').json()[0]['id']
    second = client.post('/api/users', json={'name': 'Other'}).json()['id']
    client.post(f'/api/users/{second}/activate', json={})
    assert client.post(f'/api/rides/{ride}/delete', json={'expected_user_id': first}).status_code == 409
    assert client.post(f'/api/rides/{ride}/delete', json={'expected_user_id': second}).status_code == 404
    client.post(f'/api/users/{first}/activate', json={})
    assert client.post(f'/api/rides/{ride}/delete', json={'expected_user_id': first}).status_code == 200
    assert client.get('/api/rides').json() == []
    assert client.get(f'/api/rides/{ride}/export/json').status_code == 404
