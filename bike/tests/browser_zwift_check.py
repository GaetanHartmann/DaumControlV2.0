"""UI test against the isolated demo server on the Pi."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    try:
        page.goto('http://192.168.178.125:8001')
        page.get_by_role('button',name='Verbindungen',exact=True).click()
        page.get_by_role('button',name='BLE-Sender starten',exact=True).click()
        page.get_by_text('Nur Daten senden · Steuerung gesperrt',exact=True).wait_for()
        page.get_by_label('Fahrergewicht (kg)').fill('76')
        page.get_by_role('button',name='Zwift-Steuerung freigeben',exact=True).click()
        page.get_by_text('Wartet auf Steuerungsanfrage von Zwift',exact=True).wait_for()
        page.screenshot(path=str(Path(__file__).parents[1]/'zwift-preview.png'),full_page=True)
        page.get_by_role('button',name='Cockpit',exact=True).click()
        assert page.get_by_role('button',name='Ride starten',exact=True).is_disabled()
        assert page.get_by_role('button',name='Leistung um 10 Watt erhöhen').is_disabled()
        page.get_by_role('button',name='Verbindungen',exact=True).click()
        page.get_by_role('button',name='Steuerung sperren & stoppen',exact=True).click()
        page.get_by_text('Nur Daten senden · Steuerung gesperrt',exact=True).wait_for()
        page.get_by_role('button',name='Sender stoppen',exact=True).click()
        page.get_by_role('button',name='BLE-Sender starten',exact=True).wait_for()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print(json.dumps({'zwift_ui':'start/arm/lock local controls/revoke/stop passed','errors':errors}))
    finally:
        page.request.post('http://192.168.178.125:8001/api/stop',data={})
        page.request.post('http://192.168.178.125:8001/api/zwift/stop',data={})
        browser.close()
