"""Run against an isolated demo server; exercises a demo ride and deletes it."""
import json
import os
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright


base = os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8019')
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    page.get_by_role('button', name='Einstellungen', exact=True).click()
    page.get_by_role('button', name='Automatisches Abschalten ausschalten', exact=True).click()
    assert page.request.get(base + '/api/power-settings').json()['enabled'] is False
    page.get_by_role('button', name='Automatisches Abschalten einschalten', exact=True).click()
    assert page.request.get(base + '/api/power-settings').json()['enabled'] is True
    page.get_by_role('button', name='Schließen', exact=True).click()
    session = page.request.get(base + '/api/session').json()
    assert session['profile']['ftp_watts'] is None, 'Use a fresh isolated demo server'
    terrain = [plan for plan in session['plans'] if plan['meta'].get('terrain')]
    assert len(terrain) == 6
    plan = next(plan for plan in terrain if plan['meta']['minutes'] == 35)
    page.get_by_label('Training auswählen', exact=True).select_option(str(plan['id']))
    expect(page.locator('.training-hint')).to_contain_text('Ohne FTP')
    expect(page.locator('.timeline-stages li')).to_have_count(len(plan['steps']))
    page.get_by_label('Zeitraster', exact=True).select_option('60')
    expect(page.locator('.time-grid-line')).to_have_count(36)
    page.get_by_label('Zeitraster', exact=True).select_option('300')
    expect(page.locator('.time-grid-line')).to_have_count(8)
    page.get_by_label('Wattraster', exact=True).select_option('25')
    detailed = page.locator('.watt-grid-line').count()
    page.get_by_label('Wattraster', exact=True).select_option('100')
    assert page.locator('.watt-grid-line').count() < detailed
    page.get_by_role('button', name='Berg', exact=True).click()
    expect(page.get_by_role('img', name='Virtuelles Streckenprofil mit Auffahrten, Abfahrten und aktueller Position')).to_be_visible()
    expect(page.locator('.terrain-grade')).to_contain_text('virtuelle Steigung')
    page.get_by_role('button', name='Zeitachse', exact=True).click()
    expect(page.get_by_label('Zeitraster', exact=True)).to_have_value('300')
    page.reload()
    expect(page.get_by_label('Wattraster', exact=True)).to_have_value('100')
    expect(page.get_by_label('Zeitraster', exact=True)).to_have_value('300')
    page.get_by_label('Training auswählen', exact=True).select_option(str(plan['id']))
    page.get_by_role('button', name='Pulsgeführt', exact=True).click()
    page.get_by_role('button', name='Ride starten', exact=True).click()
    expect(page.get_by_role('button', name='Training jetzt starten', exact=True)).to_be_disabled()
    page.get_by_role('button', name='Ohne Pulsgurt starten · Watttraining', exact=True).click()
    page.get_by_role('button', name='Pause', exact=True).wait_for()
    state = page.request.get(base + '/api/state').json()
    assert state['running'] and state['training_mode'] == 'power'
    assert page.request.get(base + '/api/profile').json()['ftp_watts'] is None
    page.wait_for_timeout(1500)  # Allow at least one real demo telemetry tick.
    assert page.request.get(base + '/api/state').json()['elapsed'] > 0
    page.get_by_role('button', name='Training beenden', exact=True).click()
    page.get_by_role('button', name='Aktivitäten', exact=True).click()
    delete = page.get_by_role('button', name='Fahrt 1 löschen', exact=True)
    page.once('dialog', lambda dialog: dialog.dismiss())
    delete.click()
    expect(delete).to_be_visible()
    page.once('dialog', lambda dialog: dialog.accept())
    delete.click()
    expect(delete).to_have_count(0)

    # An uneven short plan must display seconds exactly, including its endpoint.
    session['plans'].append(dict(id=9999, name='Kurze Stufen', steps=[
        dict(name='Kurz', seconds=10, watts=50), dict(name='Länger', seconds=90, watts=75),
        dict(name='Ende', seconds=35, watts=40)], meta={}, power_basis='absolute'))
    page.route('**/api/session', lambda route: route.fulfill(
        content_type='application/json', body=json.dumps(session)))
    page.reload()
    page.get_by_label('Training auswählen', exact=True).select_option('9999')
    expect(page.locator('.timeline-stages li').nth(0)).to_contain_text('10 s')
    expect(page.locator('.timeline-stages li').nth(1)).to_contain_text('1 min 30 s')
    expect(page.locator('.timeline-stages li').nth(2)).to_contain_text('35 s')
    expect(page.locator('.timeline-chart-scroll svg')).to_contain_text('2:15')
    for width, height in [(1440, 1100), (800, 480), (390, 844)]:
        page.set_viewport_size({'width': width, 'height': height})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        expect(page.get_by_label('Zeitraster', exact=True)).to_be_visible()
        page.get_by_label('Training auswählen', exact=True).select_option(str(plan['id']))
        page.screenshot(path=str(Path(tempfile.gettempdir()) / f'bike-timeline-{width}.png'), full_page=True)
        page.get_by_role('button', name='Berg', exact=True).click()
        page.screenshot(path=str(Path(tempfile.gettempdir()) / f'bike-terrain-{width}.png'), full_page=True)
        page.get_by_role('button', name='Zeitachse', exact=True).click()
    assert not errors, errors
    browser.close()
    print('Browser OK: grid settings, persistence, exact stage durations, six terrain routes, '
          'start without FTP/strap, ride deletion, desktop/Pi/mobile layout.')
