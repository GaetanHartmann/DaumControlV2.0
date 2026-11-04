"""Run manually with playwright installed; uses existing Edge installation."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1440, 'height':1000}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.request.post('http://127.0.0.1:8000/api/stop', data={})
    page.request.post('http://127.0.0.1:8000/api/power', data={'watts':100})
    page.goto('http://127.0.0.1:8000')
    page.get_by_role('heading', name='Zeit für deinen Ride.').wait_for()
    page.wait_for_function("document.querySelector('.statusline').textContent.includes('Studio verbunden')")
    page.get_by_role('button', name='Leistung um 10 Watt erhöhen').click()
    page.wait_for_function("document.querySelector('.target-control b').textContent.includes('110')")
    page.get_by_role('button', name='Ride starten').click()
    page.get_by_role('button', name='Pause', exact=True).wait_for()
    page.wait_for_timeout(2200)
    assert int(page.locator('.power-number').inner_text().replace('W','').strip()) > 0
    page.screenshot(path=str(Path(__file__).parents[1] / 'desktop-preview.png'), full_page=True)
    page.get_by_role('button', name='Pause', exact=True).click()
    page.get_by_role('button', name='Weiter', exact=True).wait_for()
    page.get_by_role('button', name='Training beenden').click()
    page.get_by_role('button', name='Trainingspläne', exact=True).click()
    page.get_by_role('button', name='Plan erstellen', exact=True).click()
    plan_name = f'Browser-Testplan {time.time_ns()}'
    page.get_by_label('Planname').fill(plan_name)
    page.get_by_role('button', name='Trainingsplan speichern').click()
    page.get_by_role('heading', name=plan_name, exact=True).wait_for()
    page.get_by_role('button', name='Verbindungen', exact=True).click()
    page.get_by_role('heading', name='Garmin Pulsgurt', exact=True).wait_for()
    page.get_by_role('button', name='Cockpit', exact=True).click()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(Path(__file__).parents[1] / 'mobile-preview.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
    page.get_by_role('button', name='Einstellungen', exact=True).click()
    page.get_by_role('dialog').wait_for()
    page.get_by_role('button', name='Schließen', exact=True).click()
    assert not errors, errors
    print(json.dumps({'browser_errors':errors,'mobile_overflow':False,'interactions':'power/start/pause/stop/create plan/navigation/settings passed'}))
    browser.close()
