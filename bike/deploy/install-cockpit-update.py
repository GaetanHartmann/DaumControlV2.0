"""Install a checksummed Fitness-Cockpit stage on an idle Pi, with rollback.

Does not start a training, connect hardware, reboot, change power settings or
power off. Run as the existing desktop/app user. No external dependencies.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
from urllib.request import urlopen


SERVICE = 'daum-studio.service'
DATA_TABLES = ('users', 'plans', 'rides', 'settings', 'training_entries',
               'plan_catalog', 'plan_favorites', 'plan_checks', 'coach_drafts', 'virtual_routes')
DISPLAY_PATHS = [
    '.config/systemd/user/daum-studio-display-idle.service',
    '.config/systemd/user/daum-studio-display-blank.service',
    '.config/autostart/daum-studio-display-idle.desktop',
    '.local/share/daum-studio/display-idle',
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def api(path):
    with urlopen('http://127.0.0.1:8000/api/' + path, timeout=5) as response:
        return json.load(response)


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, capture_output=True, timeout=90, **kwargs)


def service(action):
    return run(['systemctl', '--user', action, SERVICE])


def stage_files(stage):
    manifest = json.loads((stage / 'manifest.json').read_text())
    if manifest.get('format_version') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Ungültiges Manifest')
    files = []
    for name, checksum in manifest['files'].items():
        relative = Path(name)
        source = stage / relative
        if relative.is_absolute() or '..' in relative.parts or source.resolve().parent == stage.parent:
            raise ValueError('Ungültiger Manifestpfad')
        if stage not in source.resolve().parents or source.is_symlink() or not source.is_file():
            raise ValueError('Unsichere oder fehlende Staging-Datei')
        parts = relative.parts
        allowed_code = parts[0] in ('backend', 'deploy', 'tests') and relative.suffix == '.py'
        allowed_build = len(parts) >= 3 and parts[:2] == ('frontend', 'dist') and relative.suffix in ('.html', '.js', '.css', '.svg', '.png', '.woff2')
        allowed_routes = len(parts) == 3 and parts[:2] == ('data', 'routes') and (relative.suffix == '.json' or relative.as_posix() == 'data/routes/LICENSE.md')
        if not (allowed_code or allowed_build or allowed_routes or relative.as_posix() in ('README.md', 'requirements.txt')):
            raise ValueError('Laufzeitdaten oder unerwartete Datei im Manifest')
        if digest(source) != checksum:
            raise ValueError('Prüfsumme falsch: ' + name)
        files.append(relative)
    required = {'backend/main.py', 'backend/connectors.py', 'backend/metrics.py', 'backend/cockpit.py',
                'backend/catalog.py', 'backend/coach.py', 'backend/routes.py', 'backend/routes_material.py',
                'data/routes/index.json', 'data/routes/LICENSE.md',
                'frontend/dist/index.html', 'deploy/install-display-idle.py', 'deploy/display-boot.py'}
    if not required.issubset({p.as_posix() for p in files}):
        raise ValueError('Pflichtdateien fehlen')
    return files


def gate_idle():
    state = api('state')
    if state.get('running') or (state.get('zwift_detail') or {}).get('armed') or state.get('pending_save'):
        raise RuntimeError('Update angehalten: Training/Steuerung aktiv oder Speichern ausstehend')
    config = Path('/var/lib/daum-studio/power-watch.json')
    try:
        enabled = json.loads(config.read_text()).get('enabled') is True
    except (OSError, ValueError, TypeError):
        enabled = False
    if enabled:
        try:
            carrier = Path('/sys/class/net/eth0/carrier').read_text().strip()
        except OSError:
            carrier = ''
        if carrier != '1':
            raise RuntimeError('Update angehalten: Abschaltautomatik aktiv, kein bestätigter Bike-LAN-Link')
    return state


def data_snapshot(database):
    result = {}
    with sqlite3.connect(database) as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        for table in DATA_TABLES:
            columns = [r[1] for r in db.execute('PRAGMA table_info(' + table + ')')]
            if not columns:
                continue
            rows = db.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
            result[table] = dict(columns=columns, rows=rows)
    return result


def assert_preserved(database, before):
    with sqlite3.connect(database) as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        for table, snapshot in before.items():
            columns = ','.join('"' + name.replace('"', '""') + '"' for name in snapshot['columns'])
            # Composite keys (favorites/checks) cannot be compared by the first
            # column alone. Preserve every old tuple byte-for-byte, including
            # JSON strings, while allowing additive schema and new preset rows.
            existing = Counter(db.execute('SELECT ' + columns + ' FROM ' + table).fetchall())
            expected = Counter(snapshot['rows'])
            if expected - existing:
                raise RuntimeError('Bestandsdaten verändert: ' + table)


def copy_database(source, destination):
    with sqlite3.connect(source) as origin, sqlite3.connect(destination) as target:
        origin.backup(target)


def wait_ready():
    last = None
    for _ in range(40):
        try:
            state, session, config = api('state'), api('session'), api('config')
            assert state['user_id'] == session['active_user_id']
            assert not state['running'] and 'measurements' in state and 'capabilities' in state
            assert 'weight_kg' in session['profile'] and config
            assert {'session_state', 'planned_target_watts', 'requested_target_watts',
                    'applied_target_watts', 'measured_watts', 'target_command_status',
                    'power_limits', 'control_events'} <= state.keys()
            assert 'reported_power' in state['measurements']
            if state['capabilities'].get('power_quality') == 'device_reported_unverified':
                assert state['capabilities'].get('measured_power_supported') is False
                assert 'power' not in state['capabilities'].get('read', [])
            assert {'power_min_watts', 'power_max_watts'} <= session['profile'].keys()
            assert isinstance(api('planner'), list)
            assert isinstance(api('analysis'), dict)
            catalog = api('catalog')
            assert isinstance(catalog, dict) and isinstance(catalog.get('plans'), list)
            assert 'power_limits' in catalog
            coach = api('coach/config')
            assert coach.get('default_provider') == 'local' and 'disclosure' in coach
            context = api('coach/context')
            assert isinstance(context, dict)
            for session_data in context.get('sessions', []):
                if not session_data.get('power_measurement_verified'):
                    assert (session_data.get('averages') or {}).get('power_watts') is None
            assert isinstance(api('routes'), list)
            bundled = api('routes/library')
            assert isinstance(bundled, list) and len(bundled) >= 2
            for route in bundled:
                detail = api('routes/library/'+route['id'])
                assert detail['closed_loop'] and detail['elevation_available']
                assert detail['resistance_control'] is False
            return state
        except Exception as error:
            last = error
            time.sleep(1)
    raise RuntimeError('Neue Anwendung nicht bereit: ' + str(last))


def graphical_environment():
    env = dict(os.environ)
    output = run(['systemctl', '--user', 'show-environment']).stdout
    for line in output.splitlines():
        key, _, value = line.partition('=')
        if key in ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'DISPLAY', 'XAUTHORITY'):
            env[key] = value
    if not env.get('XDG_RUNTIME_DIR'):
        env['XDG_RUNTIME_DIR'] = f'/run/user/{os.getuid()}'
    return env


def backup_display(backup):
    present = []
    for name in DISPLAY_PATHS:
        source, destination = Path.home() / name, backup / 'display' / name
        if source.exists():
            present.append(name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
    return present


def remove_owned(path, root):
    resolved = path.resolve()
    if root.resolve() not in resolved.parents or resolved == root.resolve() or path.is_symlink():
        raise RuntimeError('Unsicherer Rücknahmepfad')
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def restore_display(backup, present, was_active):
    run(['systemctl', '--user', 'stop', 'daum-studio-display-idle.service'])
    for name in DISPLAY_PATHS:
        target, saved = Path.home() / name, backup / 'display' / name
        remove_owned(target, Path.home())
        if name in present:
            target.parent.mkdir(parents=True, exist_ok=True)
            if saved.is_dir():
                shutil.copytree(saved, target)
            else:
                shutil.copy2(saved, target)
    run(['systemctl', '--user', 'daemon-reload'])
    if was_active:
        run(['systemctl', '--user', 'start', 'daum-studio-display-idle.service'])


def install(stage, include_display=False):
    live = (Path.home() / 'daum-studio').resolve()
    if not live.is_dir() or live.parent != Path.home().resolve():
        raise RuntimeError('Unerwartetes Installationsverzeichnis')
    files = stage_files(stage)
    gate_idle()
    backup = live / 'backups' / ('before-cockpit-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True, mode=0o700)
    power = Path('/var/lib/daum-studio/power-watch.json')
    power_hash = digest(power) if power.exists() else None
    display_active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'daum-studio-display-idle.service']).returncode == 0
    display_present = backup_display(backup) if include_display else []
    saved_files, missing = [], []
    stopped = False
    database_saved = False
    display_started = False
    try:
        gate_idle()  # Recheck immediately before stopping the state owner.
        service('stop')
        stopped = True
        before = data_snapshot(live / 'bike.db')
        copy_database(live / 'bike.db', backup / 'bike.db')
        database_saved = True
        for relative in files:
            destination, saved = live / relative, backup / 'files' / relative
            if live not in destination.resolve().parents or destination.is_symlink():
                raise RuntimeError('Unsicherer Installationspfad')
            if destination.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, saved)
                saved_files.append(relative)
            else:
                missing.append(relative)
        (backup / 'rollback.json').write_text(json.dumps(dict(
            saved=[p.as_posix() for p in saved_files], added=[p.as_posix() for p in missing],
            display_present=display_present, display_was_active=display_active), indent=2))
        shutil.copy2(stage / 'manifest.json', backup / 'manifest.json')
        for relative in files:
            target = live / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / relative, target)
        service('start')
        state = wait_ready()
        assert_preserved(live / 'bike.db', before)
        if (digest(power) if power.exists() else None) != power_hash:
            raise RuntimeError('Abschalteinstellung wurde während des Updates verändert')
        if include_display:
            display_started = True
            run(['python3', str(live / 'deploy/install-display-idle.py')], env=graphical_environment())
        report = dict(updated=True, backup=str(backup), display_updated=include_display,
                      running=state['running'], mode=state['mode'], connected=state['connected'],
                      preserved={table: len(value['rows']) for table, value in before.items()})
        (backup / 'result.json').write_text(json.dumps(report, indent=2))
        return report
    except Exception:
        if stopped:
            subprocess.run(['systemctl', '--user', 'stop', SERVICE], check=False)
            for relative in saved_files:
                shutil.copy2(backup / 'files' / relative, live / relative)
            for relative in missing:
                remove_owned(live / relative, live)
            if database_saved:
                copy_database(backup / 'bike.db', live / 'bike.db')
            try:
                if display_started:
                    restore_display(backup, display_present, display_active)
            finally:
                service('start')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', type=Path)
    parser.add_argument('--check', action='store_true', help='Nur Manifest und aktuelle Bereitschaft lesen')
    parser.add_argument('--display', action='store_true', help='Auch den rücknehmbaren Display-Starthelfer installieren')
    args = parser.parse_args()
    if os.name != 'posix' or os.getuid() == 0:
        parser.error('Als angemeldeter Linux-App-Benutzer ausführen, nicht als root')
    stage = args.stage.resolve()
    if stage.parent != Path.home().resolve() or not stage.name.startswith('fitness-cockpit-stage-'):
        parser.error('Stage muss direkt im Benutzerverzeichnis liegen und fitness-cockpit-stage- heißen')
    if args.check:
        print(json.dumps(dict(validated_files=len(stage_files(stage)), state=gate_idle())))
    else:
        print(json.dumps(install(stage, args.display), ensure_ascii=False))


if __name__ == '__main__':
    main()
