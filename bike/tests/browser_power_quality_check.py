r"""UI contract test for unavailable/unverified Daum power, without hardware.

    $env:BIKE_TEST_URL='http://127.0.0.1:8035'
    .venv\Scripts\python tests/browser_power_quality_check.py --serve

The server stays in its fresh idle demo state. A routed in-browser WebSocket
delivers explicitly synthetic contract messages; no control endpoint is called.
This is not evidence of a real Daum load or measured power.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright
from browser_cockpit_check import isolated_server, safe_url


def measurement(value, unit, source, available=True, quality=None):
    return dict(value=value, unit=unit, source=source, available=available,
                stale=False, quality=quality)


def run(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 800, 'height': 480})
        page.set_default_timeout(10000)
        errors, posts, sockets = [], [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
        try:
            real = page.request.get(base + '/api/state').json()
            session = page.request.get(base + '/api/session').json()
            assert real['mode'] == 'demo' and not real['running']
            assert len(session['users']) == 1 and not session['rides'], 'Use a fresh isolated installation.'
            fake = copy.deepcopy(real)
            fake.update(mode='daum', running=True, paused=False, connected=True,
                        session_id='synthetic-ui-contract', session_state='running',
                        elapsed=75, duration=600, distance=1.1, energy=0, power=0,
                        speed=25, cadence=80, target=165, requested_target_watts=165,
                        applied_target_watts=155, measured_watts=None,
                        reported_power=150, planned_target_watts=140,
                        control_mode='manual_override', target_command_status='adjusted',
                        target_confirmation_source='device_target_readback',
                        power_measurement_note='Synthetischer UI-Vertrag: X70-Rohwert ist keine nachgewiesene unabhängige Ist-Leistung.',
                        speed_measurement_note='Synthetischer UI-Vertrag: Geschwindigkeitseinheit noch ungeprüft.',
                        plan_name='Synthetischer Anzeigevertrag', step_name='Aktuelle Phase',
                        step_index=0, step_remaining=225, next_step=dict(name='Folgephase', seconds=300, watts=160),
                        steps=[dict(name='Aktuelle Phase', seconds=300, watts=140),
                               dict(name='Folgephase', seconds=300, watts=160)],
                        samples=[], history=[None], control_events=[], completion=None,
                        hr_connected=False, hr_fresh=False, heart_rate=None)
            fake['measurements'] = dict(
                power=measurement(None, 'W', 'daum', False, 'device_reported_unverified'),
                reported_power=measurement(150, 'W', 'daum_x70_field_6', True, 'device_reported_unverified'),
                speed=measurement(25, 'km/h', 'daum', True, 'device_reported_unverified'),
                cadence=measurement(80, 'rpm', 'daum'),
                heart_rate=measurement(None, 'bpm', 'ble', False),
                energy=measurement(None, 'kJ', 'integrated_power', False),
                calories=measurement(None, 'kcal', None, False))
            def routed(socket):
                sockets.append(socket)
                socket.send(json.dumps(fake))
            page.route_web_socket('**/ws', routed)
            page.goto(base + '/#/training')
            expect(page.locator('.power-number')).to_have_text('—W')
            expect(page.locator('.power-card .muted')).to_contain_text('Ist nicht nachgewiesen')
            expect(page.locator('.power-card .muted')).to_contain_text('150 W')
            expect(page.locator('.target-control b')).to_have_text('165 W')
            expect(page.locator('.target-ack')).to_have_text('155 W zurückgemeldet · Vorgabe abweichend')
            assert sockets, 'The synthetic WebSocket must be the only live-state source.'
            energy = page.get_by_label('Aktuelle Trainingswerte', exact=True).locator('article').filter(has_text='ENERGIE')
            expect(energy).to_contain_text('— kJ mechanisch')
            expect(energy).not_to_contain_text('0 kJ')
            speed = page.get_by_label('Aktuelle Trainingswerte', exact=True).locator('article').filter(has_text='GESCHWINDIGKEIT')
            expect(speed).to_contain_text('km/h*')
            expect(speed).to_contain_text('Einheit ungeprüft')
            expect(page.get_by_role('slider', name='Zielleistung in Watt', exact=True)).to_have_value('165')
            for element in [page.locator('.live-power-card'), page.get_by_label('Aktuelle Trainingswerte', exact=True)]:
                assert element.evaluate('n=>n.getBoundingClientRect().top>=0&&n.getBoundingClientRect().bottom<=innerHeight'), element.bounding_box()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            path = Path(tempfile.gettempdir()) / 'fitness-daum-unverified-ui-800x480.png'
            page.screenshot(path=str(path))
            print('Synthetic UI contract screenshot: ' + str(path))

            page.get_by_role('button', name='Berg', exact=True).click()
            expect(page.locator('.mountain-copy h2')).to_have_text('— Watt')
            expect(page.locator('.mountain-copy p')).to_have_text('Keine verifizierte Ist-Leistung verfügbar.')
            expect(page.locator('.mountain-copy h2')).not_to_have_text('0 Watt')
            fake.update(target_command_status='unconfirmed', applied_target_watts=None)
            sockets[-1].send(json.dumps(fake))
            expect(page.locator('.target-ack')).to_have_text('Gerätevorgabe nicht bestätigt')
            expect(page.locator('.target-control b')).to_have_text('165 W')
            expect(page.locator('.power-number')).to_have_text('—W')
            assert not posts, posts
            after = page.request.get(base + '/api/state').json()
            assert after['mode'] == 'demo' and not after['running'], 'The real server must remain untouched.'
            assert not errors, errors
            print(json.dumps({'synthetic_ui_contract_only': True,
                              'unknown_actual_power': True, 'raw_value_separate': True,
                              'requested_vs_returned': True, 'no_zero_work_claim': True,
                              'mountain_unknown': True, 'unconfirmed_state': True,
                              'pi_layout': True, 'physical_io': False,
                              'javascript_errors': errors}))
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    base, parsed = safe_url(os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8035'))
    with isolated_server(base, parsed, args.serve):
        run(base)
