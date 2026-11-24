import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location('cockpit_installer', Path(__file__).parents[1] / 'deploy/install-cockpit-update.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def make_stage(stage):
    names = ['backend/main.py', 'backend/connectors.py', 'backend/metrics.py', 'backend/cockpit.py',
             'backend/catalog.py', 'backend/coach.py', 'backend/routes.py', 'backend/routes_material.py',
             'data/routes/index.json', 'data/routes/LICENSE.md',
             'frontend/dist/index.html', 'deploy/install-display-idle.py', 'deploy/display-boot.py']
    values = {}
    stage.mkdir()
    for name in names:
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('new code', encoding='utf-8')
        values[name] = installer.digest(path)
    (stage / 'manifest.json').write_text(json.dumps(dict(format_version=1, files=values)))
    return values


def test_manifest_rejects_tampered_and_escaping_files(tmp_path):
    stage = tmp_path / 'stage'
    values = make_stage(stage)
    assert len(installer.stage_files(stage)) == 13
    (stage / 'backend/main.py').write_text('tampered')
    with pytest.raises(ValueError, match='Prüfsumme'):
        installer.stage_files(stage)
    (tmp_path / 'outside.py').write_text('outside')
    values['../outside.py'] = installer.digest(tmp_path / 'outside.py')
    values['backend/main.py'] = installer.digest(stage / 'backend/main.py')
    (stage / 'manifest.json').write_text(json.dumps(dict(format_version=1, files=values)))
    with pytest.raises(ValueError, match='Manifestpfad'):
        installer.stage_files(stage)


def test_existing_data_invariant_allows_additive_migration_but_detects_changed_profiles(tmp_path):
    path = tmp_path / 'bike.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY,name TEXT,profile TEXT)')
        db.execute("INSERT INTO users VALUES (1,'A','{}')")
    before = installer.data_snapshot(path)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE users ADD COLUMN notes TEXT')
    installer.assert_preserved(path, before)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE users SET profile='changed'")
    with pytest.raises(RuntimeError, match='Bestandsdaten verändert'):
        installer.assert_preserved(path, before)


def test_failed_healthcheck_rolls_back_code_new_files_and_database(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    live = home / 'daum-studio'
    (live / 'backend').mkdir(parents=True)
    (live / 'backend/main.py').write_text('old code')
    with sqlite3.connect(live / 'bike.db') as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY,name TEXT)')
        db.execute("INSERT INTO users VALUES (1,'Preserved')")
    stage = home / 'fitness-cockpit-stage-test'
    make_stage(stage)
    monkeypatch.setattr(installer.Path, 'home', staticmethod(lambda: home))
    monkeypatch.setattr(installer, 'gate_idle', lambda: {'running': False})
    calls = []
    monkeypatch.setattr(installer, 'service', lambda action: calls.append(action))
    monkeypatch.setattr(installer.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))

    def broken_health():
        with sqlite3.connect(live / 'bike.db') as db:
            db.execute("UPDATE users SET name='Broken'")
            db.execute('CREATE TABLE new_table (id INTEGER)')
        raise RuntimeError('failed healthcheck')

    monkeypatch.setattr(installer, 'wait_ready', broken_health)
    with pytest.raises(RuntimeError, match='failed healthcheck'):
        installer.install(stage)
    assert (live / 'backend/main.py').read_text() == 'old code'
    assert not (live / 'backend/connectors.py').exists()
    with sqlite3.connect(live / 'bike.db') as db:
        assert db.execute('SELECT name FROM users').fetchone()[0] == 'Preserved'
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='new_table'").fetchone()
    assert calls == ['stop', 'start', 'start']


def test_recursive_removal_refuses_root_or_path_outside_owned_workspace(tmp_path):
    root = tmp_path / 'live'
    root.mkdir()
    with pytest.raises(RuntimeError, match='Unsicherer'):
        installer.remove_owned(root, root)
    with pytest.raises(RuntimeError, match='Unsicherer'):
        installer.remove_owned(tmp_path / 'outside', root)


def test_existing_private_profile_json_and_composite_favorites_preserved_with_new_seeds(tmp_path):
    path = tmp_path / 'catalog.db'
    exact_profile = '{ "power_max_watts": 130, "weight_kg": 82.50 }'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY,profile TEXT)')
        db.execute('INSERT INTO users VALUES (?,?)', (1, exact_profile))
        db.execute('CREATE TABLE plans (id INTEGER PRIMARY KEY,name TEXT)')
        db.execute("INSERT INTO plans VALUES (1,'Vorhanden')")
        db.execute('CREATE TABLE plan_favorites (plan_id INTEGER,user_id INTEGER,PRIMARY KEY(plan_id,user_id))')
        db.executemany('INSERT INTO plan_favorites VALUES (?,?)', [(1, 1), (1, 2)])
    before = installer.data_snapshot(path)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE plans ADD COLUMN extra TEXT')
        db.executemany('INSERT INTO plans (id,name) VALUES (?,?)', [(2, 'Lockere Runde'), (3, 'Intervalle'), (4, 'Bergfahrt'), (5, 'Ausdauerfahrt')])
    installer.assert_preserved(path, before)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT profile FROM users').fetchone()[0] == exact_profile
        db.execute('DELETE FROM plan_favorites WHERE user_id=1')
    with pytest.raises(RuntimeError, match='plan_favorites'):
        installer.assert_preserved(path, before)


def test_database_backup_restores_all_catalog_coach_and_route_tables(tmp_path):
    live, backup = tmp_path / 'live.db', tmp_path / 'backup.db'
    tables = ['plan_catalog', 'plan_checks', 'plan_favorites', 'coach_drafts', 'virtual_routes']
    with sqlite3.connect(live) as db:
        for table in tables:
            db.execute('CREATE TABLE '+table+' (id INTEGER PRIMARY KEY,data TEXT)')
            db.execute('INSERT INTO '+table+' VALUES (?,?)', (1, '{ "original": true }'))
    before = installer.data_snapshot(live)
    installer.copy_database(live, backup)
    with sqlite3.connect(live) as db:
        for table in tables:
            db.execute('DELETE FROM '+table)
    installer.copy_database(backup, live)
    installer.assert_preserved(live, before)


def test_wait_ready_checks_new_endpoints_without_mutations_or_external_coach_calls(monkeypatch):
    state = dict(user_id=1, running=False, measurements=dict(reported_power=dict(value=None)), capabilities={},
                 session_state='idle', planned_target_watts=None, requested_target_watts=25,
                 applied_target_watts=None, measured_watts=None, target_command_status='idle',
                 power_limits=dict(minimum=25,maximum=400), control_events=[])
    replies = {'state': state, 'session': dict(active_user_id=1,profile=dict(weight_kg=None,power_min_watts=None,power_max_watts=None)),
               'config': dict(product_name='Fitness-Cockpit'), 'planner': [], 'analysis': {},
               'catalog': dict(plans=[],power_limits={}), 'coach/config': dict(default_provider='local',disclosure='Data use'),
               'coach/context': {}, 'routes': [], 'routes/library': [dict(id='a'), dict(id='b')],
               'routes/library/a': dict(closed_loop=True,elevation_available=True,resistance_control=False),
               'routes/library/b': dict(closed_loop=True,elevation_available=True,resistance_control=False)}
    calls = []
    def api(path):
        calls.append(path)
        return replies[path]
    monkeypatch.setattr(installer, 'api', api)
    assert installer.wait_ready() == state
    assert {'catalog', 'coach/config', 'coach/context', 'routes', 'routes/library', 'routes/library/a', 'routes/library/b'} <= set(calls)
    assert not any(path in ('start', 'stop', 'power', 'coach/suggest') for path in calls)


def test_package_requires_catalog_coach_and_route_modules_before_archiving(tmp_path):
    spec = importlib.util.spec_from_file_location('cockpit_packager', Path(__file__).parents[1] / 'deploy/package-cockpit-update.py')
    packager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packager)
    root = tmp_path / 'bike'
    files = []
    for name in ['backend/'+name for name in packager.REQUIRED_BACKEND] + ['frontend/dist/index.html', 'data/routes/index.json', 'data/routes/LICENSE.md']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('test', encoding='utf-8')
        files.append(path)
    assert 'backend/coach.py' in packager.verify_payload(root, files)
    without_coach = [path for path in files if path.name != 'coach.py']
    with pytest.raises(ValueError, match='backend/coach.py'):
        packager.verify_payload(root, without_coach)
