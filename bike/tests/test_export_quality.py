import json

from backend.exports import payload, csv_export, tcx_export, TCX, EXT
import xml.etree.ElementTree as ET


def test_old_daum_raw_power_is_preserved_without_becoming_physical_power_or_work():
    summary = dict(averages=dict(power_watts=150), coverage_seconds=dict(power_watts=20),
                   mechanical_energy_kj=3, sources=dict(power_watts='daum'))
    sample = [20,150,150,None,0,0,0,'2026-11-09T10:00:20Z']
    data = payload(dict(id=1,mode='daum',seconds=20,distance=0,energy=3,
                        started_at='2026-11-09T10:00:00Z',summary_json=json.dumps(summary),
                        samples_json=json.dumps([sample]), control_events_json=json.dumps([
                            dict(source='manual_slider', measured_watts=150)])))
    assert data['samples'][0][1] is None and data['samples'][0][12] == 150
    assert data['summary']['energy'] is None
    assert data['summary']['reported_unverified_energy_kj'] == 3
    assert data['summary']['statistics']['averages']['power_watts'] is None
    assert data['control_events'][0]['measured_watts'] is None
    assert ',150,' in csv_export(data)  # Requested target still exists distinctly.
    root=ET.fromstring(tcx_export(data))
    assert not root.findall(f'.//{{{EXT}}}Watts')
    assert root.findall(f'.//{{{TCX}}}Trackpoint')


def test_explicit_simulation_keeps_simulated_measurements_in_export():
    data=payload(dict(id=1,mode='demo',seconds=20,distance=.1,energy=3,
                      started_at='2026-11-09T10:00:00Z',samples_json=json.dumps([
                          [20,150,155,None,80,20,.1,'2026-11-09T10:00:20Z']])))
    assert data['simulated'] and data['samples'][0][1] == 150
    assert data['summary']['energy'] == 3
