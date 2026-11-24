r"""Exercise live power controls on a fresh temporary loopback demo server.

    $env:BIKE_TEST_URL='http://127.0.0.1:8032'
    .venv\Scripts\python tests/browser_live_power_check.py --serve

Only simulated telemetry is used. This script never connects hardware or AI.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from browser_cockpit_check import isolated_server, safe_url


def wait_state(page, base, predicate, seconds=8):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        state=page.request.get(base+'/api/state').json()
        if predicate(state):
            return state
        page.wait_for_timeout(80)
    raise AssertionError('State condition timed out: '+json.dumps(state))


def run(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(10000)
        errors, commands = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def record(request):
            if request.method == 'POST' and urlsplit(request.url).path == '/api/power':
                commands.append(request.post_data_json)
        page.on('request', record)
        try:
            state = page.request.get(base + '/api/state').json()
            session = page.request.get(base + '/api/session').json()
            assert state['mode'] == 'demo' and not state['running']
            assert len(session['users']) == 1 and not session['rides'], 'Fresh temporary database required.'
            original = dict(name='Browser Live-Steuerung', category='Browserprüfung',
                            description='Zwei unveränderliche Plansegmente.', duration_seconds=20,
                            steps=[dict(name='Erste Stufe', seconds=10, watts=60),
                                   dict(name='Zweite Stufe', seconds=10, watts=100)],
                            expected_user_id=session['active_user_id'])
            created = page.request.post(base + '/api/catalog', data=original)
            assert created.status == 201, created.text()
            profile = created.json()['plan']
            page.goto(base + '/#/trainings')
            card = page.locator('.catalog-card').filter(has=page.get_by_role('heading', name=original['name'], exact=True))
            card.get_by_role('button', name='Training vorbereiten', exact=True).click()
            expect(page.get_by_role('dialog', name='Training vorbereiten', exact=True)).to_be_visible()
            assert not page.request.get(base + '/api/state').json()['running']
            page.get_by_role('button', name='Training jetzt starten', exact=True).click()
            expect(page.get_by_role('button', name='Pause', exact=True)).to_be_visible()
            wait_state(page,base,lambda s:s['elapsed']>=1)
            first = page.request.get(base + '/api/state').json()
            session_id = first['session_id']
            assert first['planned_target_watts'] == 60 and first['applied_target_watts'] is None

            slider = page.get_by_role('slider', name='Zielleistung in Watt', exact=True)
            expect(slider).to_be_enabled()
            before_count = len(commands)
            # One burst in a single browser task must collapse to its last value.
            slider.evaluate("n=>{for(const value of [80,100,125,145,155]){n.value=value;n.dispatchEvent(new Event('input',{bubbles:true}));}}")
            wait_state(page,base,lambda s:s['requested_target_watts']==155)
            page.wait_for_timeout(100)  # Drain Playwright's network callback queue.
            burst = commands[before_count:]
            assert 1 <= len(burst) <= 2, {'burst':burst,'all':commands,'before':before_count,'state':page.request.get(base+'/api/state').json()['requested_target_watts']}
            assert burst[-1]['watts'] == 155 and burst[-1]['source'] == 'manual_slider'
            expect(page.locator('.control-source')).to_have_text('Profil verschoben (+95 W)')
            assert page.locator('.workout-timeline svg path[stroke-dasharray="6 4"]').count() == 2
            page.get_by_role('button', name='Leistung um 10 Watt erhöhen', exact=True).click()
            wait_state(page,base,lambda s:s['requested_target_watts']==165)
            assert commands[-1]['source'] == 'manual_button'

            # Pausing freezes the timeline while still allowing preparation of
            # another target. The simulator must not pretend a physical ACK.
            page.get_by_role('button', name='Pause', exact=True).click()
            expect(page.get_by_role('button', name='Fortsetzen', exact=True)).to_be_visible()
            frozen = page.request.get(base + '/api/state').json()
            slider.evaluate("n=>{n.value=145;n.dispatchEvent(new Event('input',{bubbles:true}));}")
            wait_state(page,base,lambda s:s['paused'] and s['requested_target_watts']==145)
            page.wait_for_timeout(1300)
            paused = page.request.get(base + '/api/state').json()
            assert paused['elapsed'] == frozen['elapsed'] and paused['session_id'] == session_id
            assert paused['distance'] == frozen['distance'] and paused['applied_target_watts'] is None
            assert paused['target_command_status'] == 'paused'

            page.reload()
            expect(page.get_by_role('button', name='Fortsetzen', exact=True)).to_be_visible()
            reloaded = page.request.get(base + '/api/state').json()
            assert reloaded['paused'] and reloaded['session_id'] == session_id
            assert reloaded['elapsed'] == frozen['elapsed'] and reloaded['requested_target_watts'] == 145

            for width, height in [(1024, 768), (800, 480), (390, 844)]:
                page.set_viewport_size({'width': width, 'height': height})
                page.evaluate('scrollTo(0,0)')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
                expect(slider).to_be_visible()
                assert slider.evaluate("n=>getComputedStyle(n).display!=='none' && n.getBoundingClientRect().height>=44")
                for control in [page.get_by_role('button', name='Leistung um 10 Watt reduzieren', exact=True),
                                page.get_by_role('button', name='Leistung um 10 Watt erhöhen', exact=True),
                                page.get_by_role('button', name='Fortsetzen', exact=True),
                                page.get_by_role('button', name='Training beenden', exact=True)]:
                    box = control.bounding_box()
                    assert box and box['height'] >= 44 and box['width'] >= 44, (width, control.get_attribute('aria-label'), box)
                capture = Path(tempfile.gettempdir()) / f'fitness-live-power-{width}x{height}.png'
                page.screenshot(path=str(capture), full_page=width < 621)
                print('Live screenshot: ' + str(capture), flush=True)
                if width >= 800:
                    power = page.locator('.live-power-card')
                    metrics = page.get_by_label('Aktuelle Trainingswerte', exact=True)
                    geometry = dict(power=power.bounding_box(), metrics=metrics.bounding_box())
                    print('Viewport geometry: ' + json.dumps({'width': width, 'height': height, **geometry}), flush=True)
                    assert power.evaluate('n=>n.getBoundingClientRect().top>=0 && n.getBoundingClientRect().bottom<=innerHeight'), 'Power controls must fit the Pi/tablet viewport.'
                    assert metrics.evaluate('n=>n.getBoundingClientRect().top>=0 && n.getBoundingClientRect().bottom<=innerHeight'), 'Metrics must fit the Pi/tablet viewport.'

            page.set_viewport_size({'width': 1024, 'height': 768})
            page.get_by_role('button', name='Fortsetzen', exact=True).click()
            wait_state(page,base,lambda s:s['elapsed']>=11,seconds=14)
            crossed = page.request.get(base + '/api/state').json()
            assert crossed['session_id'] == session_id and crossed['step_index'] == 1
            assert crossed['requested_target_watts'] == 185 and crossed['planned_target_watts'] == 100
            assert crossed['control_mode'] == 'manual_override' and crossed['distance'] >= first['distance']
            page.get_by_role('button', name='Zurück zum Trainingsplan', exact=True).click()
            wait_state(page,base,lambda s:s['requested_target_watts']==100 and s['control_mode']=='plan')
            returned = page.request.get(base + '/api/state').json()
            assert returned['session_id'] == session_id and returned['elapsed'] >= crossed['elapsed']
            assert returned['step_index'] == 1 and returned['distance'] >= crossed['distance']
            assert returned['applied_target_watts'] is None
            expect(page.locator('.target-ack')).to_contain_text('keine reale Gerätebestätigung')
            page.get_by_role('button', name='Training beenden', exact=True).click()
            wait_state(page,base,lambda s:not s['running'] and s['completion'])
            stopped = page.request.get(base + '/api/state').json()
            assert stopped['completion']['reason'] == 'manual' and not stopped['pending_save']
            rides = page.request.get(base + '/api/rides').json()
            assert len(rides) == 1
            data = page.request.get(base + f"/api/rides/{rides[0]['id']}/export/json").json()
            sources = {event['source'] for event in data['control_events']}
            assert {'plan', 'manual_slider', 'manual_button', 'return_to_plan', 'pause/resume'} <= sources
            assert all(event.get('applied_target_watts') is None for event in data['control_events'])
            assert [step['watts'] for step in data['summary']['statistics']['plan_steps']] == [60, 100]
            saved_profile = page.request.get(base + f"/api/catalog/{profile['id']}").json()
            assert [step['watts'] for step in saved_profile['steps']] == [60, 100]
            page.get_by_role('button', name='Historie', exact=True).click()
            row = page.locator('.activity-row').filter(has_text=original['name'])
            expect(row).to_be_visible()
            row.get_by_role('button', name='Verlauf & Eingriffe', exact=True).click()
            trace = page.get_by_role('dialog', name='Trainingsverlauf', exact=True)
            expect(trace).to_be_visible()
            expect(trace).to_contain_text('Manuell · Schieberegler')
            expect(trace).to_contain_text('Zurück zum Plan')
            assert not errors, errors
            print(json.dumps({'slider_burst_requests': len(burst), 'last_target_wins': True,
                              'override_across_phase': True, 'return_current_phase': True,
                              'pause_prepares_without_ack': True, 'preserved_plan': True,
                              'reload_does_not_resume': True,
                              'history_events': True, 'touch_and_responsive': True,
                              'javascript_errors': errors}))
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    base, parsed = safe_url(os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8032'))
    with isolated_server(base, parsed, args.serve):
        run(base)
