import json
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.request.post('http://127.0.0.1:8000/api/stop',data={})
    page.goto('http://127.0.0.1:8000')
    page.get_by_role('button',name='Trainingspläne',exact=True).click()
    page.get_by_role('button',name='45 min',exact=True).click()
    assert page.locator('.plan-card').count()==5
    page.screenshot(path=str(Path(__file__).parents[1]/'training-plans-preview.png'),full_page=True)
    page.get_by_role('button',name='Persönliche Werte',exact=True).click()
    page.get_by_label('FTP / Schwellenleistung (W)',exact=True).fill('160')
    page.get_by_label('Persönliche HFmax (bpm)',exact=True).fill('180')
    page.get_by_label('Persönliche Pulsgrenze (bpm)',exact=True).fill('165')
    page.get_by_role('button',name='Persönliche Werte speichern',exact=True).click()
    page.get_by_role('dialog').wait_for(state='hidden')
    card=page.locator('.plan-card').filter(has=page.get_by_role('heading',name='VO₂max 45 · 4×4',exact=True))
    card.get_by_role('button',name='Vorschau & auswählen',exact=True).click()
    page.get_by_role('img',name='Trainings-Zeitachse mit Planleistung, tatsächlicher Leistung und aktueller Zeitposition').wait_for()
    page.get_by_role('button',name='Ride starten',exact=True).click()
    page.get_by_role('dialog',name='Training vorbereiten').wait_for()
    page.get_by_role('button',name='Training jetzt starten',exact=True).click()
    page.get_by_role('button',name='Pause',exact=True).wait_for()
    page.wait_for_timeout(2200)
    assert page.locator('.block-label').count()>0
    assert page.get_by_role('button',name='Leistung um 10 Watt erhöhen').is_disabled()
    page.screenshot(path=str(Path(__file__).parents[1]/'timeline-preview.png'),full_page=True)
    page.get_by_role('button',name='Berg',exact=True).click()
    page.get_by_role('img',name='Bergvisualisierung abhängig von der aktuellen Wattzahl').wait_for()
    page.get_by_role('button',name='Rad',exact=True).click()
    page.get_by_role('img',name='Animierte Radfahrt durch eine Berglandschaft').wait_for()
    page.get_by_role('button',name='Training beenden').click()
    page.get_by_role('button',name='Pulsgeführt',exact=True).click()
    page.get_by_role('button',name='Ride starten',exact=True).click()
    page.get_by_role('alert').filter(has_text='frisches Pulssignal').wait_for()
    assert page.get_by_role('button',name='Training jetzt starten',exact=True).is_disabled()
    page.get_by_role('button',name='Schließen',exact=True).click()
    page.get_by_role('button',name='Zeitachse',exact=True).click()
    for width,height in [(390,844),(800,480)]:
        page.set_viewport_size({'width':width,'height':height})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        page.screenshot(path=str(Path(__file__).parents[1]/f'training-{width}-preview.png'),full_page=True)
    assert not errors,errors
    print(json.dumps({'plans':'35/45/60 filters','timeline':True,'mountain':True,'profile':True,'pulse_sensor_gate':True,'errors':errors}))
    browser.close()
