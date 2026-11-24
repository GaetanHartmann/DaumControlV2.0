r"""Exercise the cockpit on a fresh, isolated loopback demo installation.

    $env:BIKE_TEST_URL='http://127.0.0.1:8027'
    .venv\Scripts\python tests/browser_cockpit_check.py --serve

--serve creates a temporary database/config and owns its temporary server.
Without --serve BIKE_TEST_URL defaults to port 8026 and must be a fresh demo
server. The script refuses remote hosts, existing users/rides or real training.
No physical connection endpoint is called. Screenshots go to the OS temp folder.
"""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


def safe_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or not parsed.port or parsed.port < 1024 or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise SystemExit('Browser test requires an isolated HTTP loopback server on an explicit unprivileged port.')
    return value.rstrip('/'), parsed


@contextmanager
def isolated_server(base, parsed, serve):
    if not serve:
        yield
        return
    with socket.socket() as probe:
        if probe.connect_ex((parsed.hostname, parsed.port)) == 0:
            raise SystemExit('Refusing to reuse an existing server with --serve; choose a free port.')
    with tempfile.TemporaryDirectory(prefix='fitness-cockpit-browser-') as directory:
        root = Path(directory)
        config = root / 'power.json'
        config.write_text('{"enabled":false}', encoding='utf-8')
        env = {**os.environ, 'BIKE_DB': str(root / 'browser.db'), 'BIKE_POWER_CONFIG': str(config)}
        with (root / 'server.log').open('w+', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:app',
                                        '--host', '127.0.0.1', '--port', str(parsed.port)],
                                       cwd=Path(__file__).resolve().parents[1], env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    try:
                        with urlopen(base + '/api/state', timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        if process.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(log.read())
                        time.sleep(.1)
                else:
                    raise RuntimeError('Temporary demo server did not start.')
                yield
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def run(base):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        page.set_default_timeout(10000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            state = page.request.get(base + '/api/state').json()
            session = page.request.get(base + '/api/session').json()
            assert state['mode'] == 'demo' and not state['running'], 'Use an idle isolated demo server.'
            assert not (state.get('zwift_detail') or {}).get('active'), 'Do not run against a BLE sender.'
            assert len(session['users']) == 1 and session['users'][0]['name'] == 'Standard', 'Use a fresh temporary database.'
            assert not session['rides'] and not page.request.get(base + '/api/planner').json(), 'Use a fresh temporary database.'

            page.goto(base)
            page.get_by_role('button', name='Profile', exact=True).click()
            page.get_by_label('Benutzername', exact=True).fill('Cockpit Browserprüfung')
            page.get_by_role('button', name='Neues Profil anlegen', exact=True).click()
            expect(page.get_by_text('Aktiv: Cockpit Browserprüfung.', exact=False)).to_be_visible()
            page.get_by_label('Gewicht (kg, für Watt/kg)', exact=True).fill('78.5')
            page.get_by_label('Geschlecht (optional)', exact=False).select_option('diverse')
            page.get_by_label('Geburtsjahr (optional)', exact=True).fill('1980')
            page.get_by_role('button', name='Persönliche Werte speichern', exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0)
            profile = page.request.get(base + '/api/profile').json()
            assert profile['weight_kg'] == 78.5 and profile['sex'] == 'diverse' and profile['hr_max'] is None
            user_id = page.request.get(base + '/api/session').json()['active_user_id']

            page.get_by_label('Watt am Zeitmarker', exact=True).check()
            page.get_by_label('Puls am Zeitmarker', exact=True).check()
            page.reload()
            expect(page.get_by_label('Watt am Zeitmarker', exact=True)).to_be_checked()
            expect(page.get_by_label('Puls am Zeitmarker', exact=True)).to_be_checked()
            expect(page.locator('.marker-values')).to_contain_text('Puls: —')

            page.get_by_role('button', name='Trainingskatalog', exact=True).click()
            page.get_by_role('button', name='Trainingsprofil generieren', exact=True).click()
            page.get_by_label('Trainingsart', exact=False).select_option('interval')
            page.get_by_label('Dauer (min)', exact=True).fill('23')
            page.get_by_label('Belastungsleistung (W)', exact=True).fill('85')
            page.get_by_label('Name (optional)', exact=True).fill('Browser Intervalle 23')
            page.get_by_role('button', name='Profilvorschau erstellen', exact=True).click()
            expect(page.locator('.generated-preview')).to_contain_text('Intervall 1')
            page.get_by_role('button', name='Profil speichern & auswählen', exact=True).click()
            expect(page.get_by_label('Training auswählen', exact=True).locator('option:checked')).to_contain_text('Browser Intervalle 23')
            generated = next(plan for plan in page.request.get(base + '/api/plans').json() if plan['name'] == 'Browser Intervalle 23')
            assert sum(step['seconds'] for step in generated['steps']) == 23 * 60

            page.get_by_role('button', name='Planer', exact=True).click()
            page.get_by_role('button', name='Einheit planen', exact=True).click()
            page.get_by_label('Radprofil', exact=False).select_option(str(generated['id']))
            page.get_by_label('Datum (optional)', exact=True).fill('2026-11-10')
            page.get_by_role('button', name='Optionale Kraftübung hinzufügen', exact=True).click()
            page.get_by_label('Wiederholungen', exact=True).fill('6')
            page.get_by_role('button', name='Einheit speichern', exact=True).click()
            entry = page.locator('article.feature-form').filter(has=page.get_by_role('heading', name='Browser Intervalle 23', exact=True))
            expect(entry).to_be_visible()
            entry.get_by_role('checkbox').check()
            expect(entry.get_by_role('checkbox')).to_be_checked()
            entry.get_by_role('button', name='Bearbeiten', exact=True).click()
            page.get_by_label('Wiederholungen', exact=True).fill('8')
            page.get_by_label('Kraftprogramm', exact=False).select_option('after')
            page.get_by_role('button', name='Einheit speichern', exact=True).click()
            expect(entry).to_contain_text('nach dem Radtraining')
            expect(entry.get_by_role('checkbox')).not_to_be_checked()
            entry.get_by_role('button', name='Einheit abgeschlossen', exact=True).click()
            expect(entry).to_contain_text('Abgeschlossen')

            page.get_by_role('button', name='Einheit planen', exact=True).click()
            page.get_by_role('button', name='Aufwärmübung hinzufügen', exact=True).click()
            page.get_by_role('button', name='Einheit speichern', exact=True).click()
            strength_only = page.locator('article.feature-form').filter(has=page.get_by_role('heading', name='Optionales Krafttraining', exact=True))
            expect(strength_only).to_be_visible()
            expect(strength_only.get_by_role('button', name='Radprofil auswählen', exact=True)).to_have_count(0)
            entries = page.request.get(base + '/api/planner').json()
            assert len(entries) == 2 and any(e['plan_id'] is None and e['strength'] for e in entries)

            page.get_by_role('button', name='Historie', exact=True).click()
            page.get_by_role('button', name='Laufbandtraining manuell erfassen', exact=True).click()
            page.get_by_label('Bezeichnung', exact=True).fill('Browser Laufband ohne Sensor')
            page.get_by_label('Dauer (min)', exact=True).fill('12')
            page.get_by_role('button', name='Laufbandtraining speichern', exact=True).click()
            manual = page.locator('.activity-row').filter(has_text='Browser Laufband ohne Sensor')
            expect(manual).to_be_visible()
            expect(manual).to_contain_text('— km')
            expect(manual).to_contain_text('— kJ')
            expect(manual.get_by_role('link', name='TCX', exact=True)).to_have_count(0)
            ride = page.request.get(base + '/api/rides').json()[0]
            assert ride['distance'] is None and ride['energy'] is None
            data = page.request.get(base + f"/api/rides/{ride['id']}/export/json").json()
            assert data['summary']['statistics']['source'] == 'manual' and not data['samples']
            assert page.request.get(base + f"/api/rides/{ride['id']}/export/csv").ok

            # Create a real ten-second demo plan; do not forge WebSocket state,
            # completion events, telemetry or measured timing in the browser.
            short = page.request.post(base + '/api/plans', data=dict(name='Browser Abschluss 10 s', steps=[dict(name='Kurz', seconds=10, watts=60)]))
            assert short.status == 201
            page.reload()
            page.get_by_role('button', name='Training', exact=True).click()
            page.get_by_label('Training auswählen', exact=True).select_option(str(short.json()['id']))
            page.get_by_role('button', name='Training starten', exact=True).click()
            expect(page.get_by_role('button', name='Pause', exact=True)).to_be_visible()
            deadline = time.monotonic() + 8
            while page.request.get(base + '/api/state').json()['elapsed'] < 1:
                assert time.monotonic() < deadline, 'Demo did not produce a live training tick.'
                page.wait_for_timeout(80)
            expect(page.locator('.power-number')).not_to_contain_text('—')
            expect(page.locator('.now-label')).not_to_have_text('0:00')
            expect(page.locator('.marker-values')).to_contain_text(' W')
            for width, height in [(1024, 768), (390, 844), (800, 480)]:
                page.set_viewport_size({'width': width, 'height': height})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                expect(page.get_by_role('region', name='Zeitachse, an Bildschirmbreite angepasst')).to_be_visible()
                metrics = page.get_by_label('Aktuelle Trainingswerte', exact=True)
                expect(metrics.locator('article')).to_have_count(6)
                assert metrics.locator('article>b').evaluate_all('(nodes)=>nodes.every(n=>parseFloat(getComputedStyle(n).fontSize)>=17)')
                capture = Path(tempfile.gettempdir()) / f'fitness-cockpit-active-{width}x{height}.png'
                page.screenshot(path=str(capture))
                print(f'Active screenshot: {capture}; metrics bottom={metrics.bounding_box()["y"] + metrics.bounding_box()["height"]:.0f}/{height}', flush=True)
                if width >= 800:
                    assert metrics.evaluate('(n)=>n.getBoundingClientRect().top>=0 && n.getBoundingClientRect().bottom<=innerHeight'), 'All Pi/tablet metrics must fit during active training.'
            completion = page.get_by_role('dialog', name='Training abgeschlossen', exact=True)
            expect(completion).to_be_visible(timeout=18000)
            expect(completion).to_contain_text('Geschafft!')
            expect(completion).to_contain_text('00:10')
            expect(completion).to_contain_text('Nicht verfügbar')
            state = page.request.get(base + '/api/state').json()
            assert not state['running'] and state['completion']['reason'] == 'completed'
            assert state['completion']['user_id'] == user_id
            assert state['completion']['summary']['averages']['power_watts'] is not None
            assert state['completion']['summary']['averages']['heart_rate_bpm'] is None
            page.get_by_role('button', name='Auswertung & nächstes Training', exact=True).click()
            expect(page.locator('.activity-row').filter(has_text='Browser Abschluss 10 s')).to_be_visible()
            assert len(page.request.get(base + '/api/rides').json()) == 2
            assert not errors, errors
            print('Browser OK: optional profile, generator preview/save/select, persistent markers, '
                  'planner create/edit/progress/strength-only, manual missing metrics/exports, '
                  'actual 10-second completion, Pi/mobile layout, no JavaScript errors.')
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true', help='Start and stop a fresh temporary demo server.')
    arguments = parser.parse_args()
    target, parsed_target = safe_url(os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8026'))
    with isolated_server(target, parsed_target, arguments.serve):
        run(target)
