"""Exercise P2 geometry import on a fresh owned demo server, never real hardware."""
import json
import os
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright
from browser_cockpit_check import isolated_server, safe_url


base, parsed = safe_url(os.getenv('BIKE_TEST_URL', 'http://127.0.0.1:8033'))
with isolated_server(base, parsed, True), sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1024,'height':768})
    errors = []
    control_posts = []
    page.on('pageerror', lambda error:errors.append(str(error)))
    page.on('request', lambda request:control_posts.append(request.url) if request.method == 'POST' and request.url.rsplit('/api/',1)[-1] in ('start','stop','pause','power','power/plan','mode') else None)
    try:
        page.goto(base + '/#/routes')
        expect(page.get_by_role('heading', name='Reale Streckendaten · P2-Vorschau')).to_be_visible()
        library = page.request.get(base + '/api/routes/library').json()
        assert len(library) >= 2
        page.get_by_role('button', name=library[0]['name'], exact=False).click()
        expect(page.get_by_role('heading', name='Amtliches Höhenprofil · Bayern')).to_be_visible()
        expect(page.get_by_role('img', name='Höhenprofil aus importierten Höhendaten')).to_be_visible()
        assert page.request.get(base + '/api/routes').json() == []
        page.get_by_role('button', name='Als eigene Strecke übernehmen').click()
        expect(page.get_by_role('button', name='Als eigene Strecke übernehmen')).to_have_count(0)
        assert len(page.request.get(base + '/api/routes').json()) == 1
        page.once('dialog', lambda dialog:dialog.accept())
        page.locator('.route-list').get_by_role('button', name='Löschen', exact=True).click()
        expect(page.get_by_text('Noch keine Strecke importiert.', exact=False)).to_be_visible()
        geometry = {'type':'LineString','coordinates':[[11.16,48.12],[11.161,48.121],[11.16,48.12]]}
        page.get_by_label('GPX / GeoJSON importieren').set_input_files({
            'name':'Test-Geometrie.geojson','mimeType':'application/geo+json','buffer':json.dumps(geometry).encode()})
        expect(page.get_by_label('Streckenname', exact=True)).to_have_value('Test-Geometrie')
        page.get_by_role('button', name='Strecke speichern', exact=True).click()
        expect(page.get_by_role('img', name='Vorschau der importierten Streckenkoordinaten')).to_be_visible()
        expect(page.get_by_text('Höhenprofil nicht verfügbar:', exact=False)).to_be_visible()
        routes = page.request.get(base + '/api/routes').json()
        assert len(routes) == 1 and routes[0]['closed_loop'] and not routes[0]['resistance_control']
        assert not page.request.get(base + '/api/state').json()['running']
        page.reload()
        expect(page.get_by_role('heading', name='Reale Streckendaten · P2-Vorschau')).to_be_visible()
        page.get_by_role('button', name='Test-Geometrie ·', exact=False).click()
        expect(page.get_by_role('img', name='Vorschau der importierten Streckenkoordinaten')).to_be_visible()
        for width,height in [(800,480),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.once('dialog', lambda dialog:dialog.accept())
        page.locator('.route-list').get_by_role('button', name='Löschen', exact=True).click()
        expect(page.get_by_text('Noch keine Strecke importiert.', exact=False)).to_be_visible()
        assert not errors, errors
        assert not control_posts, control_posts
        print('Browser OK: offline OSM library and official heights, read-only preview, explicit import, file geometry, unknown elevations, persistence, deletion, responsive layout; no device commands.')
    finally:
        browser.close()
