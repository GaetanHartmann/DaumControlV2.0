import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from backend import main, catalog, coach, cockpit
from backend.training import TrainingProfile


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'catalog.db')
    monkeypatch.setattr(main, 'engine', main.Engine())
    main.init_db()
    with main.database() as db:
        catalog.migrate(db)
    main.engine.user_id = 1
    main.engine.profile = TrainingProfile()
    app = FastAPI()
    for module in (cockpit, catalog, coach):
        module.install_routes(app, lambda: main.engine, main.database, main.require_expected_user, main.require_user_change)
    with TestClient(app) as client:
        yield client


def workout(**values):
    return dict(name='Eigene Runde', steps=[dict(name='Warm', seconds=60, watts=50),
                                           dict(name='Mitte', seconds=120, watts=80),
                                           dict(name='Cool', seconds=60, watts=40)],
                duration_seconds=240, **values)


def new_plan(client, **values):
    result = client.post('/api/catalog', json=workout(**values))
    assert result.status_code == 201, result.text
    return result.json()['plan']


def validated(client, plan_id):
    response = client.post(f'/api/catalog/{plan_id}/validate', json={})
    assert response.status_code == 200, response.text
    return response.json()['validation_token']


def test_catalog_migration_preserves_original_rows_and_seeds_once(client):
    with main.database() as db:
        before = [tuple(row) for row in db.execute('SELECT * FROM plans ORDER BY id')]
        catalog.migrate(db)
        assert before == [tuple(row) for row in db.execute('SELECT * FROM plans ORDER BY id')]
    plans = client.get('/api/catalog').json()['plans']
    assert {'Lockere Runde', 'Intervalle', 'Bergfahrt', 'Ausdauerfahrt'} <= {p['name'] for p in plans}
    assert all(p['source'] == 'preset' and not p['editable'] for p in plans if p['name'] in {'Lockere Runde', 'Intervalle', 'Bergfahrt', 'Ausdauerfahrt'})
    assert len([p for p in plans if p['meta'].get('terrain')]) == 6


def test_catalog_owner_favorite_and_optimistic_revision(client):
    plan = new_plan(client)
    assert plan['source'] == 'manual' and plan['revision'] == 1 and plan['status'] == 'draft'
    plan_id = plan['id']
    assert client.post(f'/api/catalog/{plan_id}/favorite', json={'favorite': True}).json()['favorite']
    changed = workout(expected_revision=1)
    changed['name'] = 'Geändert'
    result = client.post(f'/api/catalog/{plan_id}/update', json=changed)
    assert result.json()['plan']['revision'] == 2
    assert client.post(f'/api/catalog/{plan_id}/update', json=changed).status_code == 409
    main.engine.user_id = 2
    assert client.get(f'/api/catalog/{plan_id}').status_code == 404
    assert plan_id not in {p['id'] for p in client.get('/api/catalog').json()['plans']}
    assert client.post(f'/api/catalog/{plan_id}/favorite', json={'favorite': True}).status_code == 404
    main.engine.user_id = 1
    assert client.get(f'/api/catalog/{plan_id}').json()['favorite']
    assert client.post('/api/catalog', json=workout(expected_user_id=999)).status_code == 409


def test_presets_duplicate_and_deletion_respects_confirmation_and_references(client):
    preset = next(p for p in client.get('/api/catalog').json()['plans'] if p['source'] == 'preset')
    assert client.post(f"/api/catalog/{preset['id']}/update", json=workout(expected_revision=1)).status_code == 409
    copied = client.post(f"/api/catalog/{preset['id']}/duplicate", json={}).json()['plan']
    assert copied['source'] == 'manual' and copied['editable']
    assert client.post(f"/api/catalog/{copied['id']}/delete", json={}).status_code == 422
    with main.database() as db:
        db.execute('INSERT INTO training_entries (user_id,plan_id,name) VALUES (?,?,?)', (1, copied['id'], 'Verknüpft'))
    assert client.post(f"/api/catalog/{copied['id']}/delete", json={'confirm': True}).status_code == 409
    own = new_plan(client)
    assert client.post(f"/api/catalog/{own['id']}/delete", json={'confirm': True, 'expected_revision': 1}).status_code == 200
    assert client.get(f"/api/catalog/{own['id']}").status_code == 404


@pytest.mark.parametrize('change', [dict(steps=[]), dict(duration_seconds=241),
    dict(steps=[dict(name='Bad', seconds=0, watts=50)]), dict(steps=[dict(name='Bad', seconds=60, watts=True)]),
    dict(steps=[dict(name='Bad', seconds=60, watts=50.5)]), dict(steps=[dict(name='Bad', seconds=60, watts=401)])])
def test_untrusted_segments_and_totals_rejected(client, change):
    body = workout()
    body.update(change)
    assert client.post('/api/catalog', json=body).status_code == 422


def test_invalid_legacy_plan_is_not_startable_and_bad_limits_are_explicit(client):
    with main.database() as db:
        cur = db.execute('INSERT INTO plans (name,steps) VALUES (?,?)', ('Defekt', '[]'))
        plan_id = cur.lastrowid
        with pytest.raises(HTTPException) as raised:
            catalog.plan_for_start(db, main.engine, plan_id)
        assert raised.value.status_code == 422
    assert client.get(f'/api/catalog/{plan_id}').json()['valid'] is False
    plan = new_plan(client)
    main.engine.profile = TrainingProfile(power_min_watts=25, power_max_watts=70)
    result = client.post(f"/api/catalog/{plan['id']}/validate", json={})
    assert result.status_code == 422 and '70' in result.text


def test_receipt_needs_prepare_and_invalidates_on_edit_profile_mode_or_intensity(client):
    plan = new_plan(client)
    plan_id = plan['id']
    token = validated(client, plan_id)
    with main.database() as db:
        with pytest.raises(HTTPException) as missing:
            catalog.plan_for_start(db, main.engine, plan_id)
        assert missing.value.status_code == 409
        with pytest.raises(HTTPException):
            catalog.plan_for_start(db, main.engine, plan_id, token)
    assert client.post(f'/api/catalog/{plan_id}/prepare', json={'validation_token': token}).status_code == 200
    with main.database() as db:
        assert catalog.plan_for_start(db, main.engine, plan_id, token)['id'] == plan_id
        with pytest.raises(HTTPException):
            catalog.plan_for_start(db, main.engine, plan_id, token, intensity_percent=110)
    main.engine.profile = TrainingProfile(weight_kg=80)
    assert client.post(f'/api/catalog/{plan_id}/prepare', json={'validation_token': token}).status_code == 409
    token = validated(client, plan_id)
    main.engine.mode = 'daum'
    assert client.post(f'/api/catalog/{plan_id}/prepare', json={'validation_token': token}).status_code == 409
    token = validated(client, plan_id)
    assert client.post(f'/api/catalog/{plan_id}/prepare', json={'validation_token': token}).status_code == 422
    main.engine.mode = 'demo'
    token = validated(client, plan_id)
    client.post(f'/api/catalog/{plan_id}/update', json=workout(expected_revision=1))
    assert client.post(f'/api/catalog/{plan_id}/prepare', json={'validation_token': token}).status_code == 409


def test_catalog_and_coach_never_send_device_commands(client, monkeypatch):
    write = AsyncMock()
    monkeypatch.setattr(main.engine.connector, 'set_power', write)
    plan = new_plan(client)
    token = validated(client, plan['id'])
    assert client.post(f"/api/catalog/{plan['id']}/prepare", json={'validation_token': token}).status_code == 200
    assert client.post('/api/coach/suggest', json={}).status_code == 200
    write.assert_not_awaited()
    main.engine.connector.capabilities = dict(main.engine.connector.capabilities, control=[])
    main.engine.mode, main.engine.connected = 'daum', True
    token = validated(client, plan['id'])
    assert client.post(f"/api/catalog/{plan['id']}/prepare", json={'validation_token': token}).status_code == 422


def test_coach_offline_flow_edited_adoption_and_true_provenance(client, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    network = Mock(side_effect=AssertionError('No network allowed'))
    monkeypatch.setattr(coach, 'urlopen', network)
    assert not client.get('/api/coach/config').json()['external_available']
    assert client.get('/api/coach/context').json()['history_count'] == 0
    result = client.post('/api/coach/suggest', json={'goal': 'endurance', 'minutes': 20}).json()
    assert result['provider'] == 'local' and result['proposal']['source'] == 'manual'
    proposal = result['proposal']
    proposal['name'] = 'Bearbeiteter Vorschlag'
    proposal['source'] = 'ai'  # Client labels cannot upgrade local provenance.
    proposal['steps'][1]['watts'] = 55
    body = dict(proposal=proposal, proposal_token=result['proposal_token'])
    adopted = client.post('/api/coach/adopt', json=body)
    assert adopted.status_code == 201, adopted.text
    plan = adopted.json()['plan']
    assert plan['name'] == 'Bearbeiteter Vorschlag' and plan['source'] == 'manual' and plan['status'] == 'accepted'
    assert plan['steps'][1]['watts'] == 55
    second = client.post('/api/coach/adopt', json=body)
    assert second.json()['plan_id'] == plan['id'] and second.json()['already_adopted']
    assert main.engine.running is False
    main.engine.user_id = 2
    assert client.post('/api/coach/adopt', json=body).status_code == 404
    network.assert_not_called()


def test_external_requires_explicit_consent_and_server_key_and_model(client, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    network = Mock(side_effect=AssertionError('No network allowed'))
    monkeypatch.setattr(coach, 'urlopen', network)
    assert client.post('/api/coach/suggest', json={'provider': 'openai'}).status_code == 422
    assert client.post('/api/coach/suggest', json={'provider': 'openai', 'external_consent': True}).status_code == 503
    network.assert_not_called()


def external_value():
    return dict(name='Strukturierter Vorschlag', steps=[dict(name='Warm', seconds=300, watts=40),
        dict(name='Locker', seconds=1200, watts=60), dict(name='Cool', seconds=300, watts=35)],
        duration_seconds=1800, category='Ausdauer', description='Vor Start prüfen', intensity='Locker', reason='Aus Zusammenfassungen erstellt.')


def fake_response(value):
    return json.dumps(dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(value))])])).encode()


@contextmanager
def bytes_response(raw):
    yield SimpleNamespace(read=lambda limit: raw[:limit])


def test_structured_external_output_and_disclosed_data_minimization(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-not-returned')
    monkeypatch.setenv('OPENAI_MODEL', 'configured-test-model')
    calls = []
    def request(req, timeout):
        calls.append((req, timeout))
        return bytes_response(fake_response(external_value()))
    monkeypatch.setattr(coach, 'urlopen', request)
    result = client.post('/api/coach/suggest', json={'provider': 'openai', 'external_consent': True})
    assert result.status_code == 200, result.text
    assert result.json()['proposal']['source'] == 'ai'
    body = json.loads(calls[0][0].data)
    assert body['model'] == 'configured-test-model' and body['store'] is False
    assert body['text']['format']['strict'] is True and body['text']['format']['type'] == 'json_schema'
    assert body['text']['format']['schema']['additionalProperties'] is False
    context = json.loads(body['input'])
    assert set(context) == {'goal', 'duration_seconds', 'power_limits', 'recent_14_days', 'sessions'}
    assert 'test-key-not-returned' not in result.text
    result = result.json()
    adopted = client.post('/api/coach/adopt', json=dict(proposal=result['proposal'], proposal_token=result['proposal_token']))
    assert adopted.json()['plan']['source'] == 'ai'
    assert not main.engine.running


@pytest.mark.parametrize('change', [dict(duration_seconds=1900), dict(tool_calls=[]),
    dict(steps=[dict(name='Bad', seconds=1800, watts=1000)]),
    dict(steps=[dict(name='Bad', seconds=1800, watts=50.5)]),
    dict(steps=[dict(name='Bad', seconds=1800, watts=float('nan'))])])
def test_invalid_external_payload_cannot_be_adopted(client, monkeypatch, change):
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setenv('OPENAI_MODEL', 'configured-test-model')
    value = external_value()
    value.update(change)
    monkeypatch.setattr(coach, 'urlopen', lambda *args, **kwargs: bytes_response(fake_response(value)))
    before = len(client.get('/api/catalog').json()['plans'])
    result = client.post('/api/coach/suggest', json={'provider': 'openai', 'external_consent': True})
    assert result.status_code == 422, result.text
    assert len(client.get('/api/catalog').json()['plans']) == before
    with main.database() as db:
        assert db.execute('SELECT COUNT(*) FROM coach_drafts').fetchone()[0] == 0


def test_external_result_discarded_if_user_changes_during_request(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setenv('OPENAI_MODEL', 'configured-test-model')
    def request(*args, **kwargs):
        main.engine.user_id = 2
        return bytes_response(fake_response(external_value()))
    monkeypatch.setattr(coach, 'urlopen', request)
    assert client.post('/api/coach/suggest', json={'provider': 'openai', 'external_consent': True}).status_code == 409


def test_adoption_rechecks_current_user_limits_after_preview(client):
    result = client.post('/api/coach/suggest', json={'goal': 'endurance'}).json()
    main.engine.profile = TrainingProfile(power_max_watts=40)
    assert client.post('/api/coach/adopt', json=dict(proposal=result['proposal'], proposal_token=result['proposal_token'])).status_code == 422


def test_planner_cannot_reference_another_users_private_catalog_plan(client):
    plan = new_plan(client)
    main.engine.user_id = 2
    assert client.post('/api/planner', json={'plan_id': plan['id']}).status_code == 404
    entry = client.post('/api/planner', json={'strength': [dict(name='Wandliegestütze')]}).json()
    assert client.post(f"/api/planner/{entry['id']}/edit", json={'plan_id': plan['id']}).status_code == 404


def test_context_summarizes_target_ranges_manual_changes_and_pause_without_raw_trace(client):
    summary = dict(averages=dict(power_watts=85, heart_rate_bpm=110, cadence_rpm=75),
                   coverage_seconds=dict(power_watts=600, heart_rate_bpm=590, cadence_rpm=600),
                   power_measurement_verified=True, measurement_quality=dict(power_watts='verified_measured'),
                   manual_adjustments=2, pause_count=1, pause_seconds=15,
                   plan_steps=[dict(name='P', seconds=600, watts=70)])
    with main.database() as db:
        db.execute('''INSERT INTO rides (seconds,mode,user_id,summary_json,samples_json,activity_type,finish_reason)
                      VALUES (?,?,?,?,?,?,?)''', (600, 'daum', 1, json.dumps(summary),
                    json.dumps([[0, 80, 70], [600, 100, 100]]), 'indoor_cycling', 'completed'))
    data = client.get('/api/coach/context').json()['sessions'][0]
    assert data['manual_changes'] == 2 and data['pauses'] == 1 and data['pause_seconds'] == 15
    assert data['planned_target_range_watts'] == [70, 70]
    assert data['sampled_requested_target_range_watts'] == [70, 100]
    assert not {'samples', 'name', 'user_id', 'weight_kg'} & set(data)


def test_coach_excludes_unverified_old_daum_power_from_local_and_external_context(client, monkeypatch):
    legacy = dict(averages=dict(power_watts=350, heart_rate_bpm=115, cadence_rpm=75),
                  coverage_seconds=dict(power_watts=1200, heart_rate_bpm=1200, cadence_rpm=1200),
                  sources=dict(power_watts='daum'))
    encoded = json.dumps(legacy)
    with main.database() as db:
        db.execute('''INSERT INTO rides (seconds,mode,user_id,summary_json,activity_type,finish_reason)
                      VALUES (?,?,?,?,?,?)''', (1200, 'daum', 1, encoded, 'indoor_cycling', 'completed'))
    context = client.get('/api/coach/context').json()
    summary = context['sessions'][0]
    assert summary['averages']['power_watts'] is None and summary['coverage_seconds']['power_watts'] == 0
    assert not summary['power_measurement_verified']
    assert summary['averages']['heart_rate_bpm'] == 115  # Independent pulse remains usable.
    result = client.post('/api/coach/suggest', json={'goal':'endurance'}).json()
    assert max(step['watts'] for step in result['proposal']['steps']) == 60
    assert 'Beispielvorschlag' in result['reason']
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setenv('OPENAI_MODEL', 'configured-test-model')
    payloads = []
    def request(req, timeout):
        payloads.append(json.loads(req.data))
        return bytes_response(fake_response(external_value()))
    monkeypatch.setattr(coach, 'urlopen', request)
    assert client.post('/api/coach/suggest', json={'provider':'openai','external_consent':True}).status_code == 200
    submitted = json.loads(payloads[0]['input'])['sessions'][0]
    assert submitted['averages']['power_watts'] is None and not submitted['power_measurement_verified']
    assert '350' not in json.dumps(submitted)
    with main.database() as db:
        assert db.execute('SELECT summary_json FROM rides').fetchone()[0] == encoded


@pytest.mark.parametrize('response', [[], dict(status='completed', output=['invalid']),
    dict(status='completed', output=[dict(type='message', content=['invalid'])]),
    dict(status='incomplete', output=[]), dict(status='completed', output=[dict(type='message', content=[dict(type='refusal', refusal='No')])])])
def test_malformed_provider_envelope_and_refusal_are_rejected(client, monkeypatch, response):
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setenv('OPENAI_MODEL', 'configured-test-model')
    raw = json.dumps(response).encode()
    monkeypatch.setattr(coach, 'urlopen', lambda *args, **kwargs: bytes_response(raw))
    result = client.post('/api/coach/suggest', json={'provider': 'openai', 'external_consent': True})
    assert result.status_code == 422
