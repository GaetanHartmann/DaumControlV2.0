import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':390,'height':844},accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.request.post('http://127.0.0.1:8000/api/stop',data={})
    page.request.post('http://127.0.0.1:8000/api/start',data={})
    page.wait_for_timeout(1500)
    page.request.post('http://127.0.0.1:8000/api/stop',data={})
    page.goto('http://127.0.0.1:8000')
    page.get_by_role('button',name='Aktivitäten',exact=True).click()
    for format in ['TCX','CSV','JSON']:
        with page.expect_download() as event:
            page.get_by_role('link',name=f'{format} für Fahrt',exact=False).first.click()
        download=event.value
        assert download.suggested_filename.startswith('DEMO-')
        assert not download.failure()
    page.get_by_role('button',name='Apple Health & Export',exact=True).click()
    page.get_by_role('heading',name='Export & Apple Health',exact=True).wait_for()
    page.get_by_text('Noch keine direkte HealthKit-Synchronisation.',exact=False).wait_for()
    page.get_by_role('button',name='Schließen',exact=True).click()
    page.get_by_role('button',name='Verbindungen',exact=True).click()
    page.get_by_role('button',name='iPhone verbinden',exact=True).click()
    page.get_by_role('dialog').get_by_role('link',name='http://127.0.0.1:8000',exact=True).wait_for()
    page.get_by_role('button',name='Schließen',exact=True).click()
    page.get_by_role('button',name='Trainingspläne',exact=True).click()
    page.get_by_role('button',name='20 min',exact=True).click()
    assert page.locator('.plan-card').count()==1
    page.get_by_role('button',name='Vorschau & auswählen',exact=True).click()
    page.get_by_role('button',name='Ride starten',exact=True).click()
    page.get_by_role('heading',name='Wie fühlt sich diese Stufe an?',exact=True).wait_for()
    assert page.get_by_role('button',name='Gut sprechbar · diese Wattstufe merken',exact=True).is_disabled()
    page.get_by_role('button',name='Zu anstrengend · beenden',exact=True).click()
    page.get_by_role('button',name='Aktivitäten',exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(Path(__file__).parents[1]/'export-mobile-preview.png'),full_page=True)
    assert not errors,errors
    print(json.dumps({'downloads':['TCX','CSV','JSON'],'iphone_instructions':True,'orientation_demo_guard':True,'errors':errors}))
    browser.close()
