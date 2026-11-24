r"""Catalog and coach checks on an isolated loopback demo server only.

    $env:BIKE_TEST_URL='http://127.0.0.1:8031'
    .venv\Scripts\python tests/browser_catalog_coach_check.py --serve

No hardware connection endpoint is called and no real workout is started.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright
from browser_cockpit_check import isolated_server, safe_url


def run(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(12000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            state = page.request.get(base + '/api/state').json()
            session = page.request.get(base + '/api/session').json()
            assert state['mode'] == 'demo' and not state['running'], 'Fresh demo installation required.'
            assert len(session['users']) == 1 and not session['rides'], 'Fresh temporary data required.'
            page.goto(base)
            page.get_by_role('button', name='Trainingskatalog', exact=True).click()
            expect(page.locator('.catalog-card').first).to_be_visible()
            assert page.locator('.catalog-card .segment-preview svg').count() == page.locator('.catalog-card').count()
            page.get_by_role('button', name='Profil erstellen', exact=True).click()
            editor = page.get_by_role('dialog', name='Trainingsprofil bearbeiten', exact=True)
            expect(editor).to_be_visible()
            editor.get_by_label('Name', exact=True).fill('Browser Katalogprofil')
            editor.get_by_label('Beschreibung', exact=True).fill('Profil aus echten Zeit- und Wattsegmenten.')
            editor.get_by_role('button', name='Abschnitt 3 entfernen', exact=True).click()
            editor.get_by_role('button', name='Abschnitt 2 entfernen', exact=True).click()
            editor.get_by_label('Sekunden Abschnitt 1', exact=True).fill('20')
            editor.get_by_label('Watt Abschnitt 1', exact=True).fill('80')
            # A second unequal segment makes the step curve and timing meaningful.
            editor.get_by_role('button', name='Abschnitt hinzufügen', exact=True).click()
            editor.get_by_label('Sekunden Abschnitt 2', exact=True).fill('40')
            editor.get_by_label('Watt Abschnitt 2', exact=True).fill('120')
            first_curve = editor.locator('.segment-preview path').nth(3).get_attribute('d')
            editor.get_by_label('Watt Abschnitt 1', exact=True).fill('60')
            assert editor.locator('.segment-preview path').nth(3).get_attribute('d') != first_curve
            editor.get_by_role('button', name='Trainingsprofil speichern', exact=True).click()
            expect(editor).to_have_count(0)
            expect(page.locator('.library-notice')).to_contain_text('Profil gespeichert')
            page.get_by_role('button', name='Details schließen', exact=True).click()
            library = page.request.get(base + '/api/catalog').json()
            profile = next(plan for plan in library['plans'] if plan['name'] == 'Browser Katalogprofil')
            assert profile['duration_seconds'] == 60 and len(profile['steps']) == 2
            assert not page.request.get(base + '/api/state').json()['running']

            page.get_by_label('Profil suchen', exact=True).fill('Browser Katalogprofil')
            card = page.locator('.catalog-card').filter(has=page.get_by_role('heading', name='Browser Katalogprofil', exact=True))
            expect(card).to_have_count(1)
            card.get_by_role('button', name='Als Favorit markieren: Browser Katalogprofil', exact=True).click()
            page.get_by_label('Nur Favoriten', exact=True).check()
            expect(page.locator('.catalog-card')).to_have_count(1)
            page.get_by_label('Nur Favoriten', exact=True).uncheck()
            card.get_by_role('button', name='Duplizieren', exact=True).click()
            expect(page.locator('.catalog-card')).to_have_count(2)
            copy = page.locator('.catalog-card').filter(has=page.get_by_role('heading', name='Browser Katalogprofil · Kopie', exact=True))
            page.once('dialog', lambda dialog: dialog.dismiss())
            copy.get_by_role('button', name='Löschen', exact=True).click()
            expect(copy).to_have_count(1)
            page.once('dialog', lambda dialog: dialog.accept())
            copy.get_by_role('button', name='Löschen', exact=True).click()
            expect(copy).to_have_count(0)
            card.get_by_role('button', name='Bearbeiten', exact=True).click()
            editor.get_by_label('Watt Abschnitt 2', exact=True).fill('110')
            editor.get_by_role('button', name='Trainingsprofil speichern', exact=True).click()
            expect(editor).to_have_count(0)
            expect(page.locator('.library-notice')).to_contain_text('Profil gespeichert')
            page.get_by_role('button', name='Details schließen', exact=True).click()
            current = next(plan for plan in page.request.get(base + '/api/catalog').json()['plans'] if plan['id'] == profile['id'])
            assert current['revision'] > profile['revision']
            card.get_by_role('button', name='Training vorbereiten', exact=True).click()
            expect(page.get_by_role('dialog', name='Training vorbereiten', exact=True)).to_be_visible()
            assert not page.request.get(base + '/api/state').json()['running'], 'Preparation must not start.'
            page.get_by_role('button', name='Schließen', exact=True).click()

            # A missing physical connection must still lead to the preparation
            # dialog, where the user can connect. This response is intercepted;
            # the test never attempts a connection to real hardware.
            prepare_url = f'**/api/catalog/{profile["id"]}/prepare'
            page.route(prepare_url, lambda route: route.fulfill(
                status=422, content_type='application/json', body=json.dumps({
                    'detail': 'Ergometer nicht verbunden. Verbinden oder bewusst Demo wählen.'})))
            page.get_by_role('button', name='Trainingskatalog', exact=True).click()
            card.get_by_role('button', name='Training vorbereiten', exact=True).click()
            expect(page.get_by_role('dialog', name='Training vorbereiten', exact=True)).to_be_visible()
            expect(page.get_by_role('dialog', name='Training vorbereiten', exact=True)).to_contain_text('Ergometer nicht verbunden')
            assert not page.request.get(base + '/api/state').json()['running']
            page.unroute(prepare_url)
            page.get_by_role('button', name='Schließen', exact=True).click()

            page.get_by_role('button', name='KI-Coach', exact=True).click()
            page.get_by_text('Optionalen KI-Dienst verwenden', exact=True).click()
            consent = page.get_by_role('checkbox', name='Ich stimme der beschriebenen Übertragung für diesen Vorschlag zu.', exact=True)
            expect(page.get_by_text('KI-Dienst noch nicht eingerichtet.', exact=True)).to_be_visible()
            consent.check()
            expect(page.get_by_role('button', name='Vorschlag beim KI-Dienst anfordern', exact=True)).to_be_disabled()
            consent.uncheck()

            # Exercise external consent using an intercepted, local-only response.
            observed = []
            page.route('**/api/coach/config', lambda route: route.fulfill(
                status=200, content_type='application/json', body=json.dumps({
                    'external_available': True, 'disclosure': 'Testdaten nur nach Zustimmung.'})))
            def mock_external(route):
                payload = route.request.post_data_json
                observed.append(dict(payload))
                payload['provider'] = 'local'
                payload['external_consent'] = False
                route.fulfill(response=route.fetch(post_data=json.dumps(payload)))
            page.route('**/api/coach/suggest', mock_external)
            page.get_by_role('button', name='Trainingskatalog', exact=True).click()
            page.get_by_role('button', name='KI-Coach', exact=True).click()
            page.get_by_text('Optionalen KI-Dienst verwenden', exact=True).click()
            consent = page.get_by_role('checkbox', name='Ich stimme der beschriebenen Übertragung für diesen Vorschlag zu.', exact=True)
            expect(page.get_by_text('KI-Dienst eingerichtet.', exact=False)).to_be_visible()
            for width, height in [(800, 480), (390, 844)]:
                page.set_viewport_size({'width': width, 'height': height})
                consent.check()
                expect(consent).to_be_checked()
                consent.uncheck()
            consent.check()
            page.get_by_role('button', name='Vorschlag beim KI-Dienst anfordern', exact=True).click()
            expect(page.locator('.coach-proposal')).to_be_visible()
            assert observed and observed[0]['provider'] == 'openai' and observed[0]['external_consent'] is True
            expect(consent).not_to_be_checked()
            expect(page.get_by_role('button', name='Vorschlag beim KI-Dienst anfordern', exact=True)).to_be_disabled()
            page.unroute('**/api/coach/config')
            page.unroute('**/api/coach/suggest')
            page.get_by_role('button', name='Trainingskatalog', exact=True).click()
            page.get_by_role('button', name='KI-Coach', exact=True).click()
            page.get_by_role('button', name='Lokalen Vorschlag erzeugen', exact=True).click()
            proposal = page.locator('.coach-proposal')
            expect(proposal).to_be_visible()
            expect(proposal).to_contain_text('LOKALER VORSCHLAG')
            expect(proposal.get_by_role('img', name='Leistungskurve des Coach-Vorschlags', exact=True)).to_be_visible()
            expect(page.get_by_role('button', name='Start im Cockpit vorbereiten', exact=True)).to_be_disabled()
            proposal.get_by_role('button', name='Vorschlag übernehmen', exact=True).click()
            proposal.get_by_role('button', name='Übernommenes Profil prüfen', exact=True).click()
            expect(page.get_by_role('button', name='Start im Cockpit vorbereiten', exact=True)).to_be_enabled()
            # Any edit removes the old acceptance/validation receipt in the UI.
            old_watts = int(proposal.get_by_label('Watt Abschnitt 1', exact=True).input_value())
            proposal.get_by_label('Watt Abschnitt 1', exact=True).fill(str(old_watts + 1))
            expect(page.get_by_role('button', name='Start im Cockpit vorbereiten', exact=True)).to_be_disabled()
            expect(page.get_by_role('button', name='Übernommenes Profil prüfen', exact=True)).to_be_disabled()
            proposal.get_by_role('button', name='Vorschlag übernehmen', exact=True).click()
            proposal.get_by_role('button', name='Übernommenes Profil prüfen', exact=True).click()
            for width, height in [(1440, 1000), (800, 480), (390, 844)]:
                page.set_viewport_size({'width': width, 'height': height})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
                capture = Path(tempfile.gettempdir()) / f'fitness-coach-preview-{width}.png'
                proposal.screenshot(path=str(capture))
                print('Coach preview screenshot: ' + str(capture))
            proposal.get_by_role('button', name='Start im Cockpit vorbereiten', exact=True).click()
            expect(page.get_by_role('dialog', name='Training vorbereiten', exact=True)).to_be_visible()
            assert not page.request.get(base + '/api/state').json()['running']
            page.get_by_role('button', name='Schließen', exact=True).click()

            for label in ['Trainingskatalog', 'KI-Coach']:
                page.get_by_role('button', name=label, exact=True).click()
                for width, height in [(1440, 1000), (800, 480), (390, 844)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), (label, width)
                    if label == 'Trainingskatalog':
                        page.locator('.catalog-grid').evaluate("n=>n.scrollIntoView({block:'start'})")
                    capture = Path(tempfile.gettempdir()) / f'fitness-{label.lower()}-{width}.png'
                    page.screenshot(path=str(capture))
                    print('Screenshot: ' + str(capture))
            assert not errors, errors
            print(json.dumps({'catalog_crud': True, 'real_segment_preview': True,
                              'favorite': True, 'preparation_no_start': True,
                              'coach_offline': True, 'edit_invalidates_validation': True,
                              'responsive': True, 'javascript_errors': errors}))
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    base, parsed = safe_url(os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8031'))
    with isolated_server(base, parsed, args.serve):
        run(base)
