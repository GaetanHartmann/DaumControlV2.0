"""Install a staged update on an idle Pi, with code and SQLite rollback."""
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen


def api(path, body=None):
    request = Request(
        'http://127.0.0.1:8000/api/' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'},
    )
    return json.load(urlopen(request, timeout=20))


def service(action):
    subprocess.run(['systemctl', '--user', action, 'daum-studio'], check=True)


def wait_ready():
    for attempt in range(30):
        try:
            state = api('state')
            session = api('session')
            assert state['user_id'] == session['active_user_id']
            assert session['users'] and 'hr_fresh' in state
            assert 'power_adjustment_watts' in session['profile']
            return state
        except Exception:
            if attempt == 29:
                raise
            time.sleep(1)


def main():
    live = Path.home() / 'daum-studio'
    stage = Path(sys.argv[1]).resolve()
    if stage.parent != Path.home() or not stage.name.startswith('daum-studio-profile-'):
        raise SystemExit('Unexpected staging directory')
    state = api('state')
    if state['running'] or (state.get('zwift_detail') or {}).get('armed'):
        raise SystemExit('Update angehalten: Training aktiv oder Zwift freigegeben.')
    reconnect = state['mode'] == 'daum'
    backup = live / 'backups' / ('before-profiles-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True)
    service('stop')
    saved = False
    try:
        shutil.copytree(live / 'backend', backup / 'backend', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(live / 'frontend' / 'dist', backup / 'dist')
        for name in ['README.md', 'requirements.txt']:
            shutil.copy2(live / name, backup / name)
        with sqlite3.connect(live / 'bike.db') as source, sqlite3.connect(backup / 'bike.db') as target:
            source.backup(target)
        saved = True
        shutil.copytree(stage / 'backend', live / 'backend', dirs_exist_ok=True)
        shutil.copytree(stage / 'frontend' / 'dist', live / 'frontend' / 'dist', dirs_exist_ok=True)
        for name in ['README.md', 'requirements.txt']:
            shutil.copy2(stage / name, live / name)
        service('start')
        state = wait_ready()
        with sqlite3.connect(live / 'bike.db') as db:
            assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    except Exception:
        service('stop')
        if saved:
            shutil.copytree(backup / 'backend', live / 'backend', dirs_exist_ok=True)
            shutil.copytree(backup / 'dist', live / 'frontend' / 'dist', dirs_exist_ok=True)
            for name in ['README.md', 'requirements.txt']:
                shutil.copy2(backup / name, live / name)
            with sqlite3.connect(backup / 'bike.db') as source, sqlite3.connect(live / 'bike.db') as target:
                source.backup(target)
        service('start')
        raise
    if reconnect:
        for attempt in range(3):
            try:
                state = api('mode', {'mode': 'daum'})
                break
            except Exception as error:
                if attempt == 2:
                    print('Daum bitte erneut verbinden:', str(error))
                    state = api('state')
                else:
                    time.sleep(3)
    print(json.dumps({'updated': True, 'backup': str(backup), 'mode': state['mode'],
                      'connected': state['connected'], 'running': state['running']}))


if __name__ == '__main__':
    main()
