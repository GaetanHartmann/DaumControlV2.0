"""Check one-click starts and local profile selection on an owned demo server.

No physical device is connected. Catalog loading never starts or validates a
workout; only explicit Start clicks can prepare/start the temporary demo engine.
"""
import argparse
import os
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from browser_cockpit_check import isolated_server, safe_url


def run(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport=dict(width=1024, height=768))
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append((request.method, urlsplit(request.url).path)))
        try:
            session = page.request.get(base+'/api/session').json()
            assert len(session['users']) == 1 and not session['rides']
            state = page.request.get(base+'/api/state').json()
            assert state['mode'] == 'demo' and not state['running']
            created = page.request.post(base+'/api/catalog', data=dict(
                expected_user_id=session['active_user_id'], name='Direktstart Browserprofil',
                steps=[dict(name='Locker', seconds=300, watts=60), dict(name='Weiter', seconds=300, watts=80)]))
            assert created.status == 201, created.text()
            identifier = created.json()['plan']['id']
            page.goto(base+'/#/trainings')
            card = page.locator('.catalog-card').filter(has=page.get_by_role('heading', name='Direktstart Browserprofil', exact=True))
            expect(card).to_be_visible()
            page.wait_for_timeout(150)
            requests.clear()
            card.get_by_role('button', name='Training vorbereiten', exact=True).click()
            expect(page.get_by_label('Training auswählen', exact=True)).to_have_value(str(identifier))
            expect(page.get_by_role('dialog')).to_have_count(0)
            assert not page.request.get(base+'/api/state').json()['running']
            assert not any(method == 'POST' or path == '/api/session' for method, path in requests), requests
            assert page.get_by_role('button', name='Profil & Grenzen erneut prüfen', exact=True).count() == 0

            def post_paths():
                return [path for method, path in requests if method == 'POST']

            def stop():
                page.get_by_role('button', name='Training beenden', exact=True).click()
                expect(page.get_by_role('button', name='Training starten', exact=True)).to_be_visible()
                expect(page.get_by_label('Benutzer auswählen')).to_be_enabled()
                assert not page.request.get(base+'/api/state').json()['running']

            # Two synchronous clicks exercise the in-flight latch before Vue has
            # updated disabled attributes. Only one preparation/start is allowed.
            requests.clear()
            page.get_by_role('button', name='Training starten', exact=True).evaluate('n=>{n.click();n.click()}')
            expect(page.get_by_role('button', name='Pause', exact=True)).to_be_visible()
            expect(page.get_by_role('dialog')).to_have_count(0)
            assert post_paths() == [f'/api/catalog/{identifier}/accept', f'/api/catalog/{identifier}/validate',
                                    f'/api/catalog/{identifier}/prepare', '/api/start'], post_paths()
            first = page.request.get(base+'/api/state').json()
            assert first['workout_id'] == identifier and first['running']
            stop()

            # Same plan and configuration: re-use the successful receipt.
            requests.clear()
            page.get_by_role('button', name='Training starten', exact=True).click()
            expect(page.get_by_role('button', name='Pause', exact=True)).to_be_visible()
            assert post_paths() == ['/api/start'], post_paths()
            second = page.request.get(base+'/api/state').json()
            assert second['session_id'] != first['session_id']
            stop()

            # Another client changes the profile. The server rejects the old
            # receipt before starting; the UI automatically refreshes it once.
            profile = page.request.get(base+'/api/profile').json()
            changed = page.request.post(base+'/api/profile', data={**profile, 'weight_kg': 82})
            assert changed.ok, changed.text()
            requests.clear()
            page.get_by_role('button', name='Training starten', exact=True).click()
            expect(page.get_by_role('button', name='Pause', exact=True)).to_be_visible()
            assert post_paths() == ['/api/start', f'/api/catalog/{identifier}/accept',
                                    f'/api/catalog/{identifier}/validate', f'/api/catalog/{identifier}/prepare',
                                    '/api/start'], post_paths()
            expect(page.get_by_role('dialog')).to_have_count(0)
            stop()

            # An unsafe actual profile is still refused, without a manual check
            # dialog and without reaching the start endpoint.
            profile = page.request.get(base+'/api/profile').json()
            assert page.request.post(base+'/api/profile', data={**profile, 'power_max_watts': 50}).ok
            page.reload()
            expect(page.get_by_label('Training auswählen', exact=True)).to_be_visible()
            page.get_by_label('Training auswählen', exact=True).select_option(str(identifier))
            requests.clear()
            page.get_by_role('button', name='Training starten', exact=True).click()
            expect(page.get_by_role('alert').filter(has_text='Profil überschreitet erlaubte Leistung')).to_be_visible()
            assert '/api/start' not in post_paths(), post_paths()
            assert not page.request.get(base+'/api/state').json()['running']

            # The pulse fallback remains a separate, explicit user decision.
            profile = page.request.get(base+'/api/profile').json()
            assert page.request.post(base+'/api/profile', data={**profile, 'power_max_watts': None}).ok
            page.reload()
            page.get_by_role('button', name='Pulsgeführt', exact=True).click()
            requests.clear()
            page.get_by_role('button', name='Training starten', exact=True).click()
            expect(page.get_by_role('alert').filter(has_text='Persönliche HFmax und Pulsgrenze fehlen.')).to_be_visible()
            assert not post_paths(), post_paths()
            page.get_by_role('button', name='Ohne Pulsgurt starten · Watttraining', exact=True).click()
            expect(page.get_by_role('button', name='Pause', exact=True)).to_be_visible()
            assert page.request.get(base+'/api/state').json()['training_mode'] == 'power'
            stop()

            # A failed transport/server response is not automatically repeated.
            page.route('**/api/start', lambda route: route.fulfill(status=503, json={'detail': 'Synthetischer Startfehler'}))
            requests.clear()
            page.get_by_role('button', name='Training starten', exact=True).click()
            expect(page.get_by_role('alert').filter(has_text='Synthetischer Startfehler')).to_be_visible()
            assert post_paths() == ['/api/start'], post_paths()
            assert not page.request.get(base+'/api/state').json()['running']
            page.unroute('**/api/start')
            assert not errors, errors
            print('Direct start OK: local profile selection without session reload or validation POST, '
                  'one-click/double-click guard, unchanged receipt reuse, automatic stale-receipt recovery, '
                  'real bounds retained, explicit pulse fallback, no transport retry, no physical I/O.')
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    base, parsed = safe_url(os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8039'))
    with isolated_server(base, parsed, args.serve):
        run(base)
