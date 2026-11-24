r"""Verify separate fullscreen timeline/metrics on an isolated demo server.

    $env:BIKE_TEST_URL='http://127.0.0.1:8036'
    .venv\Scripts\python tests/browser_fullscreen_check.py --serve

A synthetic WebSocket supplies an active, unverified Daum display contract.
Device/training POSTs are intercepted in-browser; the real temporary server
remains idle in demo mode. This test never connects to physical hardware.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
import time

from playwright.sync_api import expect, sync_playwright
from browser_cockpit_check import isolated_server, safe_url


def item(value, unit, source, available=True, stale=False):
    return dict(value=value, unit=unit, source=source, available=available, stale=stale)


def visible_in_viewport(locator):
    assert locator.evaluate('n=>{const r=n.getBoundingClientRect();return r.top>=0&&r.left>=0&&r.bottom<=innerHeight+.5&&r.right<=innerWidth+.5}'), locator.bounding_box()


def touch_target(locator):
    visible_in_viewport(locator)
    box = locator.bounding_box()
    assert box['height'] >= 44 and box['width'] >= 44, box


def run(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 800, 'height': 480})
        page.set_default_timeout(10000)
        errors, posts, sockets, commands = [], [], [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
        # Exercise the denied/unsupported browser API fallback deliberately.
        page.add_init_script("Element.prototype.requestFullscreen=function(){return Promise.reject(new Error('Synthetic browser permission rejection'))}")
        try:
            real = page.request.get(base + '/api/state').json()
            session = page.request.get(base + '/api/session').json()
            assert real['mode'] == 'demo' and not real['running']
            assert len(session['users']) == 1 and not session['rides'], 'Use a fresh isolated installation.'
            fake = copy.deepcopy(real)
            fake.update(mode='daum', connected=True, running=True, paused=False,
                        session_id='synthetic-fullscreen-contract', session_state='running',
                        elapsed=75, duration=600, distance=1.1, energy=None,
                        power=0, cadence=80, speed=25, target=165,
                        requested_target_watts=165, applied_target_watts=155,
                        target_command_status='adjusted', measured_watts=None,
                        planned_target_watts=140, control_mode='manual_override', power_offset_watts=25,
                        plan_name='Synthetischer Vollbildvertrag', step_name='Aktuelle Phase',
                        step_index=0, step_remaining=225,
                        next_step=dict(name='Folgephase', seconds=300, watts=160),
                        steps=[dict(name='Aktuelle Phase', seconds=300, watts=140),
                               dict(name='Folgephase', seconds=300, watts=160)],
                        samples=[[0, None, 140], [75, None, 165]], history=[None],
                        power_measurement_note='Synthetischer Vertrag: keine unabhängige Ist-Leistung.',
                        speed_measurement_note='Synthetischer Vertrag: Geschwindigkeitseinheit ungeprüft.',
                        hr_connected=False, hr_fresh=False, heart_rate=None,
                        control_events=[], completion=None)
            fake['measurements'] = dict(
                power=item(None, 'W', 'daum', False),
                reported_power=item(150, 'W', 'daum_x70_field_6'),
                cadence=item(80, 'rpm', 'daum'), speed=item(25, 'km/h', 'daum'),
                heart_rate=item(None, 'bpm', 'ble', False),
                energy=item(None, 'kJ', 'integrated_power', False),
                calories=item(None, 'kcal', None, False))

            def routed(socket):
                sockets.append(socket)
                socket.send(json.dumps(fake))
            page.route_web_socket('**/ws', routed)
            page.goto(base + '/#/training')
            expect(page.locator('.target-control b')).to_have_text('165 W')
            timeline_entry = page.get_by_role('button', name='Zeitachse im Vollbild', exact=True)
            timeline_entry.click()
            dialog = page.get_by_role('dialog', name='Zeitachse im Vollbild', exact=True)
            expect(dialog).to_be_visible()
            assert page.evaluate('document.fullscreenElement===null'), 'Fallback must survive a browser rejection.'
            assert page.locator('main').evaluate('n=>n.inert')
            assert page.locator('.sidebar').evaluate('n=>n.inert')
            expect(dialog.locator('.timeline-chart-scroll')).to_be_visible()
            expect(dialog.locator('.fullscreen-metric-grid')).to_have_count(0)
            touch_target(dialog.get_by_role('button', name='Pause', exact=True))
            touch_target(dialog.get_by_role('button', name='Stopp', exact=True))
            close = dialog.get_by_role('button', name='Vollbild schließen', exact=True)
            expect(close).to_be_focused()
            page.keyboard.press('Tab')
            assert dialog.evaluate('n=>n.contains(document.activeElement)'), 'Tab must stay in the modal.'
            page.keyboard.press('Escape')
            expect(page.locator('.fullscreen-training-view')).to_have_count(0)
            expect(timeline_entry).to_be_focused()
            assert not page.locator('main').evaluate('n=>n.inert')
            assert not posts, posts

            page.get_by_role('button', name='Kennzahlen im Vollbild', exact=True).click()
            dialog = page.get_by_role('dialog', name='Kennzahlen im Vollbild', exact=True)
            expect(dialog).to_be_visible()
            dialog = page.locator('.fullscreen-training-view')
            metrics = dialog.locator('.fullscreen-metric')
            expect(metrics).to_have_count(17)
            expect(dialog.locator('[data-metric="actual"]')).to_contain_text('— W')
            expect(dialog.locator('[data-metric="actual"]')).to_contain_text('Ist nicht nachgewiesen')
            expect(dialog.locator('[data-metric="requested"]')).to_contain_text('165 W')
            expect(dialog.locator('[data-metric="applied"]')).to_contain_text('155 W')
            expect(dialog.locator('[data-metric="reported"]')).to_contain_text('150 W')
            expect(dialog.locator('[data-metric="sensor"]')).to_contain_text('Nicht verbunden')
            expect(dialog.locator('[data-metric="speed"]')).to_contain_text('Einheit ungeprüft')
            expect(dialog.locator('[data-metric="energy"]')).to_contain_text('— kJ')
            expect(dialog.locator('[data-metric="elapsed"]')).to_contain_text('01:15')
            for width, height in [(800, 480), (1024, 768), (390, 844), (844, 390), (320, 568), (1920, 1080)]:
                page.set_viewport_size(dict(width=width, height=height))
                touch_target(dialog.get_by_role('button', name='Pause', exact=True))
                touch_target(dialog.get_by_role('button', name='Stopp', exact=True))
                touch_target(dialog.get_by_role('button', name='Vollbild schließen', exact=True))
                assert dialog.evaluate('n=>n.scrollWidth<=innerWidth'), (width, height)
                # Long values and descriptions must fit inside their tiles;
                # the grid may scroll when the viewport is short.
                for tile in metrics.all():
                    assert tile.evaluate('n=>n.scrollHeight<=n.clientHeight+1 && n.scrollWidth<=n.clientWidth+1'), (width, height, tile.get_attribute('data-metric'))
                last = metrics.last
                last.scroll_into_view_if_needed()
                visible_in_viewport(last)
                dialog.get_by_role('button', name='Zeitachse', exact=True).click()
                expect(dialog.locator('.timeline-chart-scroll')).to_be_visible()
                visible_in_viewport(dialog.locator('.timeline-chart-scroll'))
                chart = dialog.locator('.timeline-chart-scroll svg')
                assert chart.evaluate("n=>{const m=n.getScreenCTM();return Math.abs(Math.hypot(m.a,m.b)-Math.hypot(m.c,m.d))<0.001}"), (width, height)
                assert chart.locator('path[stroke-dasharray="6 4"]').count() == 2
                assert chart.locator('text.axis-label').last.text_content().endswith(' min')
                dialog.get_by_role('button', name='Kennzahlen', exact=True).click()
            assert not posts, posts
            page.set_viewport_size(dict(width=800, height=480))
            path = Path(tempfile.gettempdir()) / 'fitness-fullscreen-metrics-800x480.png'
            page.screenshot(path=str(path))
            print('Synthetic fullscreen metrics screenshot: ' + str(path))
            dialog.get_by_role('button', name='Zeitachse', exact=True).click()
            path = Path(tempfile.gettempdir()) / 'fitness-fullscreen-timeline-800x480.png'
            page.screenshot(path=str(path))
            print('Synthetic fullscreen timeline screenshot: ' + str(path))
            dialog.get_by_role('button', name='Kennzahlen', exact=True).click()

            # Browser-only mock responses verify the existing command wiring.
            def command(route):
                request = route.request
                payload = request.post_data_json or {}
                endpoint = request.url.rsplit('/', 1)[-1]
                commands.append((endpoint, payload))
                if endpoint == 'power':
                    fake.update(target=payload['watts'], requested_target_watts=payload['watts'])
                elif endpoint == 'pause':
                    fake['paused'] = not fake['paused']
                elif endpoint == 'plan':
                    fake.update(target=140, requested_target_watts=140, control_mode='plan')
                elif endpoint == 'stop':
                    fake.update(running=False, session_state='stopped')
                route.fulfill(json=fake)
                sockets[-1].send(json.dumps(fake))
            for endpoint in ['power', 'pause', 'stop', 'power/plan']:
                page.route('**/api/' + endpoint, command)
            dialog.get_by_role('button', name='Wattsteuerung', exact=False).click()
            for tile in dialog.locator('.fullscreen-metric').all():
                assert tile.evaluate('n=>n.scrollHeight<=n.clientHeight+1 && n.scrollWidth<=n.clientWidth+1')
            slider = dialog.get_by_role('slider', name='Vollbild: Zielleistung in Watt', exact=True)
            touch_target(slider)
            touch_target(dialog.get_by_role('button', name='Vollbild: Leistung um 10 Watt erhöhen', exact=True))
            touch_target(dialog.get_by_role('button', name='Zurück zum Trainingsplan', exact=True))
            dialog.get_by_role('button', name='Vollbild: Leistung um 10 Watt erhöhen', exact=True).click()
            expect(slider).to_have_value('175')
            expect(dialog.locator('[data-metric="elapsed"]')).to_contain_text('01:15')
            dialog.get_by_role('button', name='Pause', exact=True).click()
            expect(dialog.get_by_role('button', name='Fortsetzen', exact=True)).to_be_visible()
            dialog.get_by_role('button', name='Fortsetzen', exact=True).click()
            expect(dialog.get_by_role('button', name='Pause', exact=True)).to_be_visible()
            dialog.get_by_role('button', name='Zurück zum Trainingsplan', exact=True).click()
            expect(slider).to_have_value('140')
            slider.fill('180')
            expect(slider).to_have_value('180')
            expect(dialog.locator('[data-metric="requested"]')).to_contain_text('180 W')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not any(endpoint == 'power' and payload.get('watts') == 180 for endpoint, payload in commands):
                page.wait_for_timeout(30)
            assert any(endpoint == 'power' and payload.get('watts') == 180 and payload.get('source') == 'manual_slider' for endpoint, payload in commands), commands
            def rejected_power(route):
                route.fulfill(status=400, json={'detail': 'Synthetische Wattablehnung'})
            page.route('**/api/power', rejected_power)
            dialog.get_by_role('button', name='Vollbild: Leistung um 10 Watt erhöhen', exact=True).click()
            expect(dialog.get_by_role('alert')).to_have_text('Synthetische Wattablehnung')
            expect(slider).to_have_value('180')
            touch_target(dialog.get_by_role('button', name='Stopp', exact=True))
            dialog.get_by_role('button', name='Stopp', exact=True).click()
            expect(dialog.get_by_role('button', name='Stopp', exact=True)).to_have_count(0)
            dialog.get_by_role('button', name='Vollbild schließen', exact=True).click()
            expect(page.locator('.fullscreen-training-view')).to_have_count(0)
            page.reload()
            expect(page.locator('.fullscreen-training-view')).to_have_count(0)
            actual = page.request.get(base + '/api/state').json()
            assert actual['mode'] == 'demo' and not actual['running']
            assert not page.request.get(base + '/api/session').json()['rides']
            assert not errors, errors
            # Also try the browser's real Fullscreen API on a separate page.
            native_page = browser.new_page(viewport={'width': 800, 'height': 480})
            native_page.on('pageerror', lambda error: errors.append(str(error)))
            native_page.goto(base + '/#/training')
            native_page.get_by_role('button', name='Zeitachse im Vollbild', exact=True).click()
            expect(native_page.locator('.fullscreen-training-view')).to_be_visible()
            native_entered = native_page.evaluate('document.fullscreenElement!==null')
            native_page.get_by_role('button', name='Vollbild schließen', exact=True).click()
            expect(native_page.locator('.fullscreen-training-view')).to_have_count(0)
            assert native_page.evaluate('document.fullscreenElement===null')
            native_page.close()
            assert not errors, errors
            print(json.dumps(dict(separate_timeline_and_metrics=True, css_fallback=True,
                                  escape_and_focus=True, inert_background=True,
                                  seventeen_metrics=True, unknown_values_preserved=True,
                                  touch_targets=True, six_viewports=True,
                                  mock_controls_only=True, server_unchanged=True,
                                  rejected_command_visible=True,
                                  native_fullscreen_entered=native_entered,
                                  physical_io=False, javascript_errors=errors)))
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    base, parsed = safe_url(os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8036'))
    with isolated_server(base, parsed, args.serve):
        run(base)
