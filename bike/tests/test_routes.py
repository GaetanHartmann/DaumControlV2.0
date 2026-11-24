import json

from fastapi.testclient import TestClient
import pytest
from backend import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'routes.db')
    monkeypatch.setattr(main, 'engine', main.Engine())
    with TestClient(main.app) as value:
        yield value


def geometry(**values):
    return dict(name='Importierte Testrunde', points=[
        dict(longitude=11.16, latitude=48.12),
        dict(longitude=11.161, latitude=48.121),
        dict(longitude=11.16, latitude=48.12)], **values)


def test_route_import_is_data_only_and_does_not_invent_elevation(client):
    response = client.post('/api/routes', json=geometry())
    assert response.status_code == 201
    data = response.json()
    assert 200 < data['distance_metres'] < 400
    assert data['closed_loop'] and not data['elevation_available']
    assert data['resistance_control'] is False
    assert all(point['elevation_m'] is None for point in data['points'])
    state = client.get('/api/state').json()
    assert not state['running'] and state['mode'] == 'demo'
    assert client.get('/api/routes').json()[0]['id'] == data['id']


def test_route_points_validate_source_finite_coordinates_and_nonzero_distance(client):
    assert client.post('/api/routes', json=geometry(source='openstreetmap')).status_code == 422
    value = geometry()
    value['points'][0]['longitude'] = 200
    assert client.post('/api/routes', json=value).status_code == 422
    value['points'][0]['longitude'] = 11.16
    value['points'] = value['points'][:1] * 2
    assert client.post('/api/routes', json=value).status_code == 422
    value['points'][0]['latitude'] = float('nan')
    assert client.post('/api/routes', content=json.dumps(value), headers={'Content-Type':'application/json'}).status_code == 422


def test_route_elevation_only_if_every_imported_point_has_height(client):
    value = geometry(source='openstreetmap', attribution='© OpenStreetMap contributors')
    for index, point in enumerate(value['points']):
        point['elevation_m'] = 500 + index
    response = client.post('/api/routes', json=value)
    assert response.status_code == 201 and response.json()['elevation_available']
    assert response.json()['attribution'] == value['attribution']


def test_route_user_isolation_and_explicit_deletion(client):
    first = client.get('/api/state').json()['user_id']
    route = client.post('/api/routes', json=geometry()).json()
    other = client.post('/api/users', json={'name':'Route-B'}).json()['id']
    client.post(f'/api/users/{other}/activate', json={})
    assert client.get('/api/routes').json() == []
    assert client.post(f'/api/routes/{route["id"]}/delete', json={'confirm':True}).status_code == 404
    assert client.post('/api/routes', json={**geometry(), 'expected_user_id':first}).status_code == 409
    client.post(f'/api/users/{first}/activate', json={})
    assert client.post(f'/api/routes/{route["id"]}/delete', json={}).status_code == 422
    assert client.post(f'/api/routes/{route["id"]}/delete', json={'confirm':True}).status_code == 200
    assert client.get('/api/routes').json() == []


def test_bundled_real_routes_preview_without_write_then_explicit_user_import(client):
    first = client.get('/api/state').json()['user_id']
    before = client.get('/api/routes').json()
    listing = client.get('/api/routes/library').json()
    assert len(listing) >= 2
    for entry in listing:
        detail = client.get('/api/routes/library/'+entry['id']).json()
        assert detail['closed_loop'] and detail['elevation_available']
        assert detail['resistance_control'] is False
        assert detail['license_url'] == entry['license_url']
        assert len(detail['points']) == entry['point_count']
        assert detail['distance_metres'] == pytest.approx(entry['distance_metres'], rel=.001)
        assert detail['provenance']['elevation']['vertical_datum'] == 'DHHN2016'
    assert client.get('/api/routes').json() == before
    route_id = listing[0]['id']
    assert client.get('/api/routes/library/missing').status_code == 404
    imported = client.post('/api/routes/library/'+route_id+'/import', json={'expected_user_id': first})
    assert imported.status_code == 201
    assert imported.json()['library_id'] == route_id
    assert imported.json()['license_url'] == listing[0]['license_url']
    assert len(client.get('/api/routes').json()) == len(before)+1
    other = client.post('/api/users', json={'name':'Library-B'}).json()['id']
    client.post(f'/api/users/{other}/activate', json={})
    assert client.get('/api/routes').json() == []
    assert client.post('/api/routes/library/'+route_id+'/import', json={'expected_user_id': first}).status_code == 409
    state = client.get('/api/state').json()
    assert not state['running'] and state['mode'] == 'demo'
