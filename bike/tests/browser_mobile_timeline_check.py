r"""Check mobile timeline geometry on an isolated, idle demo installation.

    .venv\Scripts\python.exe tests/browser_mobile_timeline_check.py --serve

Only plan data are created. No training, power, connection or physical device
endpoint is called. Screenshots go to the OS temporary directory.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright

from browser_cockpit_check import isolated_server, safe_url


VIEWPORTS = [(320, 740), (390, 844), (430, 932), (844, 390), (800, 480)]


def fixture(name, phases):
    return dict(name=name, steps=[dict(name=title, seconds=seconds, watts=watts)
                                 for title, seconds, watts in phases])


PROFILES = [
    fixture('Mobile Grundlage 35 min', [
        ('Einrollen', 300, 60), ('Grundlage', 900, 110),
        ('Etwas zügiger', 600, 140), ('Ausrollen', 300, 65)]),
    fixture('Mobile kurze Intervalle', [('Einrollen', 300, 60)] +
            [(f'Intervall {i+1}', 20, 150) if i % 2 == 0 else
             (f'Erholung {i+1}', 40, 75) for i in range(30)] +
            [('Ausrollen', 300, 50)]),
    fixture('Mobile lange Fahrt 90 min', [
        ('Einrollen', 600, 60), ('Grundlage A', 900, 100),
        ('Grundlage B', 1200, 120), ('Grundlage C', 1200, 135),
        ('Grundlage D', 900, 110), ('Ausrollen', 600, 55)]),
]


def chart_report(timeline):
    return timeline.evaluate(r'''root=>{
      const chart=root.querySelector('.timeline-chart-scroll');
      const svg=chart.querySelector('svg'), box=svg.getBoundingClientRect();
      const toBox=n=>{const r=n.getBoundingClientRect(),m=n.getScreenCTM();
        return {text:n.textContent,x:r.x,y:r.y,right:r.right,bottom:r.bottom,
          width:r.width,height:r.height,
          font:Number.parseFloat(getComputedStyle(n).fontSize)*Math.hypot(m.c,m.d)}};
      const x=[...svg.querySelectorAll('text.axis-label')].filter(n=>!n.closest('.watt-grid-line')).map(toBox);
      const y=[...svg.querySelectorAll('.watt-grid-line text')].map(toBox);
      const blocks=[...svg.querySelectorAll('text.block-label')].map(toBox);
      return {width:box.width,height:box.height,left:box.left,right:box.right,
        scrollWidth:chart.scrollWidth,clientWidth:chart.clientWidth,
        viewBox:{width:svg.viewBox.baseVal.width,height:svg.viewBox.baseVal.height},
        xLabels:x,yLabels:y,blockLabels:blocks,
        plotRects:[...svg.querySelectorAll('rect')].filter(n=>n.closest('[data-segment-index]')).map(n=>n.getBoundingClientRect().toJSON())};
    }''')


def assert_labels(report, size, context):
    for axis in ['xLabels', 'yLabels', 'blockLabels']:
        labels = report[axis]
        for label in labels:
            assert label['font'] >= 10, (context, size, axis, 'text shrunk', label)
            assert label['x'] >= report['left'] - 1, (context, size, axis, 'text clipped left', label)
            assert label['right'] <= report['right'] + 1, (context, size, axis, 'text clipped right', label)
        for index, first in enumerate(labels):
            for second in labels[index+1:]:
                intersection_x = min(first['right'], second['right']) - max(first['x'], second['x'])
                intersection_y = min(first['bottom'], second['bottom']) - max(first['y'], second['y'])
                assert not (intersection_x > .5 and intersection_y > .5), (context, size, axis, 'overlapping labels', first, second)
    assert 2 <= len(report['xLabels']) <= (7 if report['width'] < 440 else 16), (context, size, report)
    assert 2 <= len(report['yLabels']) <= int(report['height']/30)+2, (context, size, report)


def verify_chart(page, timeline, size, context):
    expect(timeline).to_be_visible()
    svg = timeline.locator('.timeline-chart-scroll > svg')
    expect(svg).to_be_visible()
    # ResizeObserver updates after each viewport or fullscreen transition.
    assert timeline.evaluate(r'''async root=>{
      for(let attempt=0;attempt<60;attempt++){
        const svg=root.querySelector('.timeline-chart-scroll > svg'),box=svg.getBoundingClientRect();
        if(Math.abs(Number(root.dataset.chartWidth)-box.width)<.15&&Math.abs(Number(root.dataset.chartHeight)-box.height)<.15)return true;
        await new Promise(resolve=>requestAnimationFrame(resolve));
      }return false;
    }'''), (context, size, 'ResizeObserver did not settle')
    report = chart_report(timeline)
    expect(timeline).to_have_attribute('data-responsive-mode', 'compact' if report['width'] < 620 else 'wide')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (context, size)
    assert report['scrollWidth'] <= report['clientWidth'] + 1, (context, size, 'forced horizontal plot scroll', report)
    assert abs(report['viewBox']['width'] - report['width']) <= 1, (context, size, 'plot width does not follow device', report)
    assert abs(report['viewBox']['height'] - report['height']) <= 1, (context, size, 'plot height does not follow device', report)
    assert report['height'] >= (175 if size[0] < 621 else 75), (context, size, 'plot too short', report)
    assert_labels(report, size, context)
    # An idle plan preview must not draw a fabricated actual-power curve.
    actual = svg.locator(':scope > path[stroke="#be633b"]')
    assert actual.count() == 1 and not (actual.get_attribute('d') or '').strip(), (context, size, 'invented actual trace')
    expect(timeline.locator('.timeline-legend')).to_contain_text('Ursprünglicher Plan')
    expect(timeline.locator('.timeline-legend')).to_contain_text('Angeforderter Sollwert')
    expect(timeline.locator('.timeline-legend')).to_contain_text('Gemessene Leistung')
    return report


def inspect_short_step(page, timeline, profile, size, context):
    """Tiny intervals remain usable by plot tapping and large adjacent buttons."""
    index = 15
    bar = timeline.locator(f'[data-segment-index="{index}"]')
    bar.scroll_into_view_if_needed()
    box = bar.bounding_box()
    page.touchscreen.tap(box['x'] + box['width']/2, box['y'] + box['height']/2)
    detail = timeline.locator('.timeline-selected-step')
    expect(detail).to_be_visible()
    expect(detail).to_contain_text(profile['steps'][index]['name'])
    expect(detail).to_contain_text(str(profile['steps'][index]['watts']) + ' W')
    for name in ['Vorherige Leistungsstufe', 'Nächste Leistungsstufe', 'Stufendetails schließen']:
        button = detail.get_by_role('button', name=name, exact=True)
        bounds = button.bounding_box()
        assert bounds['width'] >= 44 and bounds['height'] >= 44, (context, size, name, bounds)
    detail.get_by_role('button', name='Nächste Leistungsstufe', exact=True).click()
    expect(detail).to_contain_text(profile['steps'][index+1]['name'])
    detail.get_by_role('button', name='Vorherige Leistungsstufe', exact=True).click()
    expect(detail).to_contain_text(profile['steps'][index]['name'])
    detail.get_by_role('button', name='Stufendetails schließen', exact=True).click()
    expect(detail).to_have_count(0)


def run(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport=dict(width=390, height=844), has_touch=True,
                                      is_mobile=True, device_scale_factor=2)
        page = context.new_page()
        page.set_default_timeout(10000)
        errors, control_posts = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def request_seen(request):
            endpoint = request.url.rsplit('/api/', 1)[-1]
            if request.method == 'POST' and endpoint.split('/')[0] in (
                    'start', 'stop', 'pause', 'power', 'mode', 'hr', 'connect', 'zwift'):
                control_posts.append(endpoint)
        page.on('request', request_seen)
        # Safari/iPhone commonly uses the viewport fallback for browser fullscreen.
        page.add_init_script("Element.prototype.requestFullscreen=function(){return Promise.reject(new Error('Mobile fullscreen fallback fixture'))}")
        try:
            state = page.request.get(base + '/api/state').json()
            assert state['mode'] == 'demo' and not state['running']
            assert not page.request.get(base + '/api/session').json()['rides']
            plans = []
            for profile in PROFILES:
                response = page.request.post(base + '/api/plans', data=profile)
                assert response.status == 201, response.text()
                plans.append((response.json()['id'], profile))
            page.goto(base + '/#/training')
            expect(page.get_by_label('Training auswählen', exact=True)).to_be_visible()
            page.get_by_role('button', name='Zeitachse', exact=True).click()
            reports = []
            for size in VIEWPORTS:
                page.set_viewport_size(dict(width=size[0], height=size[1]))
                for identifier, profile in plans:
                    page.get_by_label('Training auswählen', exact=True).select_option(str(identifier))
                    timeline = page.locator('.ride-scene .workout-timeline')
                    timeline.scroll_into_view_if_needed()
                    report = verify_chart(page, timeline, size, 'normal')
                    assert timeline.locator('[data-segment-index]').count() == len(profile['steps'])
                    reports.append(dict(size=size, mode='normal', profile=profile['name'],
                                        width=report['width'], height=report['height'],
                                        x_labels=len(report['xLabels'])))
                    if size == (390, 844) and identifier == plans[0][0]:
                        page.screenshot(path=str(Path(tempfile.gettempdir()) / 'fitness-mobile-timeline-390x844.png'))
                    # Preserve user-selected grid semantics while thinning labels.
                    if identifier == plans[1][0] and size == (390, 844):
                        timeline.get_by_label('Zeitraster', exact=True).select_option('30')
                        timeline.get_by_label('Wattraster', exact=True).select_option('25')
                        verify_chart(page, timeline, size, 'normal explicit grid')
                        timeline.get_by_label('Zeitraster', exact=True).select_option('0')
                        timeline.get_by_label('Wattraster', exact=True).select_option('0')
                        inspect_short_step(page, timeline, profile, size, 'normal')
                    page.get_by_role('button', name='Zeitachse im Vollbild', exact=True).click()
                    dialog = page.get_by_role('dialog', name='Zeitachse im Vollbild', exact=True)
                    expect(dialog).to_be_visible()
                    full_timeline = dialog.locator('.workout-timeline')
                    full_report = verify_chart(page, full_timeline, size, 'fullscreen')
                    assert full_report['height'] >= min(180, size[1]*.35), (size, full_report)
                    assert dialog.evaluate('n=>n.scrollWidth<=innerWidth+1'), size
                    close = dialog.get_by_role('button', name='Vollbild schließen', exact=True)
                    assert close.bounding_box()['width'] >= 44 and close.bounding_box()['height'] >= 44
                    if identifier == plans[1][0]:
                        inspect_short_step(page, full_timeline, profile, size, 'fullscreen')
                    if size == (390, 844) and identifier == plans[0][0]:
                        page.screenshot(path=str(Path(tempfile.gettempdir()) / 'fitness-mobile-timeline-fullscreen-390x844.png'))
                    close.click()
                    expect(page.locator('.fullscreen-training-view')).to_have_count(0)
            # CSS has a separate compact running layout. Exercise it with an
            # explicitly synthetic UI session while every actual measurement
            # remains unknown and the real backend stays idle.
            fake = dict(state)
            active_profile = PROFILES[1]
            fake.update(running=True, paused=False, session_id='synthetic-mobile-layout',
                        session_state='running', elapsed=400,
                        duration=sum(step['seconds'] for step in active_profile['steps']),
                        steps=active_profile['steps'], step_name='Erholung', step_index=4,
                        plan_name='Synthetischer aktiver UI-Vertrag', samples=[[400, None, 75]],
                        history=[None], requested_target_watts=100, target=100,
                        planned_target_watts=75, measured_watts=None, power=None,
                        target_command_status='simulated', control_mode='manual_override',
                        power_offset_watts=25,
                        control_events=[])
            for value in fake.get('measurements', {}).values():
                value.update(value=None, available=False)
            page.route_web_socket('**/ws', lambda socket:socket.send(json.dumps(fake)))
            page.reload()
            expect(page.locator('.shell')).to_have_class('shell training-active')
            for size in [(390, 844), (844, 390), (800, 480)]:
                page.set_viewport_size(dict(width=size[0], height=size[1]))
                page.get_by_role('button', name='Zeitachse im Vollbild', exact=True).click()
                active = page.get_by_role('dialog', name='Zeitachse im Vollbild', exact=True)
                timeline = active.locator('.workout-timeline')
                verify_chart(page, timeline, size, 'active fullscreen')
                assert timeline.locator('[data-segment-index]').count() == len(active_profile['steps'])
                adjusted = timeline.locator('.adjusted-segment')
                expect(adjusted).to_have_count(len(active_profile['steps']))
                for index, step in enumerate(active_profile['steps']):
                    expect(timeline.locator(f'[data-adjusted-segment-index="{index}"]')).to_have_attribute('data-adjusted-watts', str(step['watts']+25))
                inspect_short_step(page, active.locator('.workout-timeline'), active_profile,
                                   size, 'active fullscreen')
                for name in ['Pause', 'Stopp']:
                    button = active.get_by_role('button', name=name, exact=True)
                    box = button.bounding_box()
                    assert box['width'] >= 44 and box['height'] >= 44
                    assert 0 <= box['y'] and box['y'] + box['height'] <= size[1], (size, name, box)
                active.get_by_role('button', name='Vollbild schließen', exact=True).click()
            after = page.request.get(base + '/api/state').json()
            assert after['mode'] == 'demo' and not after['running']
            assert not page.request.get(base + '/api/session').json()['rides']
            assert not control_posts, control_posts
            assert not errors, errors
            print(json.dumps(dict(responsive_mobile_timeline=True, normal_and_fullscreen=True,
                                  profiles=len(PROFILES), viewports=len(VIEWPORTS),
                                  labels_legible=True, no_forced_plot_scroll=True,
                                  no_fake_actual_power=True, no_device_commands=True,
                                  javascript_errors=errors, geometry=reports)))
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    base, parsed = safe_url(os.environ.get('BIKE_TEST_URL', 'http://127.0.0.1:8038'))
    with isolated_server(base, parsed, args.serve):
        run(base)
