import csv
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.exports import TCX,EXT


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'export.db')
    monkeypatch.setattr(main,'engine',main.Engine())
    with TestClient(main.app) as client:
        yield client


def saved_ride(client, heart_rate=120):
    client.post('/api/start',json={})
    main.engine.started_at='2026-10-31T10:00:00+00:00'
    main.engine.elapsed,main.engine.distance,main.engine.energy=20,0.1,2.4
    main.engine.samples=[[0,100,100,heart_rate,80,18,0,'2026-10-31T10:00:00+00:00'],
                         [20,120,120,heart_rate,85,18,.1,'2026-10-31T10:00:40+00:00']]
    client.post('/api/stop')
    return client.get('/api/rides').json()[0]['id']


def test_exports_round_trip_samples_and_real_wall_timestamps(client):
    ride_id=saved_ride(client)
    response=client.get(f'/api/rides/{ride_id}/export/json')
    assert response.status_code==200
    assert 'DEMO-' in response.headers['content-disposition']
    data=response.json()
    assert data['samples'][1][7]=='2026-10-31T10:00:40+00:00'
    assert data['simulated'] and data['summary']['seconds']==20
    assert 'samples_json' not in client.get('/api/rides').json()[0]
    csv_data=client.get(f'/api/rides/{ride_id}/export/csv').text.lstrip('\ufeff')
    rows=list(csv.reader(io.StringIO(csv_data)))
    assert len(rows)==4
    assert all(len(r)==len(rows[0]) for r in rows)
    assert rows[-1][7]=='120'
    tcx=client.get(f'/api/rides/{ride_id}/export/tcx')
    root=ET.fromstring(tcx.content)
    points=root.findall(f'.//{{{TCX}}}Trackpoint')
    assert len(points)==2
    assert points[-1].find(f'{{{TCX}}}Time').text=='2026-10-31T10:00:40Z'
    assert points[-1].find(f'{{{TCX}}}Extensions/{{{EXT}}}TPX/{{{EXT}}}Watts').text=='120'
    assert root.find(f'.//{{{TCX}}}Calories').text=='0'
    assert 'DEMO' in root.find(f'.//{{{TCX}}}Notes').text


def test_tcx_validates_against_official_garmin_schema(client):
    etree=pytest.importorskip('lxml.etree')
    schema_path = Path(__file__).parent/'fixtures'/'TrainingCenterDatabasev2.xsd'
    if not schema_path.is_file():
        pytest.skip('Optional Garmin schema missing; see docs/TESTING.md for the separate download')
    ride_id=saved_ride(client)
    schema=etree.XMLSchema(etree.parse(str(schema_path)))
    schema.assertValid(etree.fromstring(client.get(f'/api/rides/{ride_id}/export/tcx').content))


def test_missing_heart_rate_and_legacy_ride_export(client):
    ride_id=saved_ride(client,heart_rate=None)
    root=ET.fromstring(client.get(f'/api/rides/{ride_id}/export/tcx').content)
    assert not root.findall(f'.//{{{TCX}}}HeartRateBpm')
    with main.database() as db:
        row=db.execute('INSERT INTO rides (seconds,distance,energy,mode) VALUES (60,0.2,6,"daum")')
        legacy=row.lastrowid
    data=client.get(f'/api/rides/{legacy}/export/json').json()
    assert data['start_time_estimated'] and data['samples']==[] and not data['simulated']
    assert client.get('/api/rides/999999/export/tcx').status_code==404
    assert client.get(f'/api/rides/{ride_id}/export/exe').status_code==422
