"""Run against an isolated demo server; creates test users and a short demo ride."""
import json
import os

from playwright.sync_api import expect, sync_playwright


base = os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8017')
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    page.get_by_role('button', name='Profile', exact=True).click()
    page.get_by_label('Benutzername', exact=True).fill('Browser-Test')
    page.get_by_role('button', name='Neues Profil anlegen', exact=True).click()
    expect(page.get_by_text('Aktiv: Browser-Test.', exact=False)).to_be_visible()
    page.get_by_label('FTP / Schwellenleistung (W)', exact=True).fill('165')
    for _ in range(3):
        page.get_by_role('button', name='Profil-Leistung um 5 Watt erhöhen').click()
    page.get_by_role('button', name='Profil-Leistung um 5 Watt reduzieren').click()
    expect(page.get_by_label('Leistungsanpassung (W)', exact=True)).to_have_value('10')
    page.get_by_role('button', name='Persönliche Werte speichern', exact=True).click()
    page.get_by_role('dialog').wait_for(state='hidden')
    profile = page.request.get(base + '/api/profile').json()
    assert profile['power_adjustment_watts'] == 10
    plans = page.request.get(base + '/api/plans').json()
    plan = next(plan for plan in plans if plan['name'] == 'Grundlage 35')
    page.get_by_label('Training auswählen', exact=True).select_option(str(plan['id']))
    page.get_by_label('Trainingsintensität in Prozent').fill('80')
    page.get_by_role('button', name='Ride starten', exact=True).click()
    dialog = page.get_by_role('dialog', name='Training vorbereiten')
    expect(dialog).to_be_visible()
    expect(dialog.locator('p').filter(has_text='Leistungsanpassung:')).to_contain_text('10 W')
    assert not page.request.get(base + '/api/state').json()['running']
    dialog.get_by_role('button', name='Training jetzt starten', exact=True).click()
    page.get_by_role('button', name='Pause', exact=True).wait_for()
    state = page.request.get(base + '/api/state').json()
    assert state['target'] == 76, state
    expect(page.get_by_label('Benutzer auswählen')).to_be_disabled()
    page.get_by_role('button', name='Training beenden', exact=True).click()
    second = browser.new_page()
    second.goto(base)
    second.get_by_label('Benutzer auswählen').select_option(label='Standard')
    expect(page.get_by_label('Benutzer auswählen')).to_have_value('1')
    page.get_by_role('button', name='Profile', exact=True).click()
    expect(page.get_by_label('Leistungsanpassung (W)', exact=True)).to_have_value('0')
    page.get_by_role('button', name='Schließen', exact=True).click()
    second.close()

    # Verify partial-connection feedback and explicit choice without real hardware.
    state = page.request.get(base + '/api/state').json()
    result = dict(state=state, sensors=[dict(address='test-a', name='Gurt A'),
                                       dict(address='test-b', name='Gurt B')],
                  results=[dict(device='daum', ok=False, message='Test: Daum nicht erreichbar'),
                           dict(device='hr', ok=False, message='Mehrere Pulssensoren gefunden')],
                  needs_sensor_choice=True)
    page.route('**/api/connect/all', lambda route: route.fulfill(
        status=200, content_type='application/json', body=json.dumps(result)))
    page.get_by_role('button', name='Alles verbinden', exact=True).click()
    page.get_by_role('dialog', name='Pulsgurt verbinden').wait_for()
    expect(page.get_by_role('button', name='Gurt A test-a')).to_be_visible()
    expect(page.get_by_role('button', name='Gurt B test-b')).to_be_visible()
    page.get_by_role('button', name='Schließen', exact=True).click()
    for width, height in [(390, 844), (800, 480)]:
        page.set_viewport_size({'width': width, 'height': height})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        page.get_by_role('button', name='Profile', exact=True).click()
        expect(page.get_by_label('Leistungsanpassung (W)', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        page.get_by_role('button', name='Schließen', exact=True).click()
    assert not errors, errors
    print('Browser OK: per-user +/- watts, exact plan target, preflight, multi-device switch, '
          'Connect All partial results and sensor choice, mobile widths; no JS errors.')
    browser.close()
