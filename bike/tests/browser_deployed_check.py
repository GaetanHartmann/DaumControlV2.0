"""Read-only smoke check of the deployed Pi app; never starts a ride."""
import os

from playwright.sync_api import expect, sync_playwright


base = os.environ.get('BIKE_TEST_URL', 'http://192.168.178.125:8000')
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 800, 'height': 480})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    page.get_by_role('button', name='Trainingspläne', exact=True).click()
    page.get_by_label('Trainingsziel filtern', exact=True).select_option('Berg & Tal')
    expect(page.locator('.plan-card')).to_have_count(6)
    page.locator('.plan-card').first.get_by_role('button', name='Vorschau & auswählen', exact=True).click()
    expect(page.get_by_label('Zeitraster', exact=True)).to_be_visible()
    expect(page.locator('.timeline-stages li').first).to_contain_text('30 s')
    page.get_by_role('button', name='Berg', exact=True).click()
    expect(page.get_by_role('img', name='Virtuelles Streckenprofil mit Auffahrten, Abfahrten und aktueller Position')).to_be_visible()
    page.get_by_role('button', name='Einstellungen', exact=True).click()
    toggle = page.get_by_role('button', name='Automatisches Abschalten ausschalten', exact=True)
    expect(toggle).to_be_enabled()
    expect(toggle).to_have_attribute('aria-pressed', 'true')
    assert page.request.get(base + '/api/state').json()['running'] is False
    assert not errors, errors
    browser.close()
    print('Pi browser OK: six routes, timeline grid, stage durations, terrain view, enabled auto-off control, no JS errors.')
