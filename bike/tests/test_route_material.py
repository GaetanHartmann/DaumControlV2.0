import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from backend import routes_material
from backend.routes import RouteInput, route_data, segment_distance


BIKE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fetch_route_material', BIKE / 'deploy' / 'fetch-route-material.py')
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)


def isolated_library(tmp_path, monkeypatch):
    destination = tmp_path / 'routes'
    shutil.copytree(routes_material.DATA_DIR, destination)
    monkeypatch.setattr(routes_material, 'DATA_DIR', destination)
    return destination


def replace_payload(directory, identifier, change):
    manifest = json.loads((directory / 'index.json').read_text(encoding='utf-8'))
    item = next(item for item in manifest if item['id'] == identifier)
    path = directory / item['file']
    payload = json.loads(path.read_text(encoding='utf-8'))
    change(payload)
    raw = json.dumps(payload, ensure_ascii=False).encode()
    path.write_bytes(raw)
    item['sha256'] = hashlib.sha256(raw).hexdigest()
    (directory / 'index.json').write_text(json.dumps(manifest), encoding='utf-8')


@pytest.mark.parametrize('identifier,minimum,maximum,count', [
    ('grafrath-ampermoos', 7000, 8000, 185),
    ('ammersee-runde', 45000, 47000, 1628),
])
def test_real_bundled_loops_fit_import_contract_and_preserve_provenance(identifier, minimum, maximum, count):
    metadata = next(item for item in routes_material.library() if item['id'] == identifier)
    value = routes_material.load_route(identifier)
    body = RouteInput(name=value['name'], source=value['source'],
                      attribution=value['attribution'], points=value['points'])
    imported = route_data(body)
    assert minimum < imported['distance_metres'] < maximum
    assert abs(imported['distance_metres'] - metadata['distance_metres']) < 0.1
    assert imported['closed_loop'] and imported['elevation_available']
    assert len(value['points']) == metadata['point_count'] == count
    assert value['points'][0] == value['points'][-1]
    assert imported['resistance_control'] is False
    assert metadata['outdoor_navigation_verified'] is False
    provenance = value['provenance']
    assert len(provenance['osm_node_ids']) == count
    assert provenance['osm_node_ids'][0] == provenance['osm_node_ids'][-1]
    assert len(set(provenance['osm_node_ids'][:-1])) == count - 1
    assert len(provenance['osm_segment_way_ids']) == count - 1
    assert all(source['url'].startswith('https://api.openstreetmap.org/') for source in provenance['osm_sources'])
    assert provenance['elevation']['vertical_datum'] == 'DHHN2016'
    assert provenance['elevation']['license_url'] == 'https://creativecommons.org/licenses/by/4.0/'
    assert sum(batch['point_count'] for batch in provenance['elevation']['batches']) == count
    for point in value['points']:
        assert 11.08 < point['longitude'] < 11.18 and 47.90 < point['latitude'] < 48.13
        assert 500 < point['elevation_m'] < 700
    # Preserve OSM's straight sections (up to 428 m here); reject kilometre-scale jumps.
    assert max(segment_distance(a, b) for a, b in zip(body.points, body.points[1:])) < 500


def test_bundled_library_never_fetches_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline route library attempted network access')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    assert len(routes_material.library()) == 2
    assert routes_material.load_route('ammersee-runde')['points']
    with pytest.raises(KeyError):
        routes_material.load_route('../../other')


def test_route_checksum_detects_modified_dataset(tmp_path, monkeypatch):
    destination = isolated_library(tmp_path, monkeypatch)
    path = destination / 'grafrath-ampermoos.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Prüfsumme'):
        routes_material.load_route('grafrath-ampermoos')


def test_manifest_prevents_arbitrary_file_reads(tmp_path, monkeypatch):
    destination = isolated_library(tmp_path, monkeypatch)
    path = destination / 'index.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest[0]['file'] = '../outside.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='Streckendatei'):
        routes_material.library()


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), True, 999])
def test_even_rehashed_payload_rejects_invalid_coordinates(tmp_path, monkeypatch, bad):
    destination = isolated_library(tmp_path, monkeypatch)
    replace_payload(destination, 'grafrath-ampermoos', lambda p: p['points'][0].update(longitude=bad))
    with pytest.raises(ValueError):
        routes_material.load_route('grafrath-ampermoos')


def test_missing_height_stays_missing(tmp_path, monkeypatch):
    destination = isolated_library(tmp_path, monkeypatch)
    replace_payload(destination, 'grafrath-ampermoos', lambda p: p['points'][0].update(elevation_m=None))
    assert routes_material.load_route('grafrath-ampermoos')['points'][0]['elevation_m'] is None


def test_downloader_will_not_invent_a_closing_edge_for_nearby_endpoints():
    raw = b'''<osm><node id="1" lon="11.16" lat="48.12"/>
        <node id="2" lon="11.17" lat="48.12"/><node id="3" lon="11.160001" lat="48.120001"/>
        <way id="100"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="cycleway"/></way></osm>'''
    nodes, graph = downloader.road_graph([raw])
    with pytest.raises(ValueError, match='genuinely closed'):
        downloader.longest_cycle(nodes, graph)


def test_elevation_adapter_checks_position_and_preserves_unknown_height(monkeypatch):
    monkeypatch.setattr(downloader, 'fetch', lambda *args, **kwargs:
                        b'{"srid":4326,"coords":[[11.16,48.12,null]]}')
    points, _ = downloader.add_elevations([(11.16, 48.12)])
    assert points == [dict(longitude=11.16, latitude=48.12, elevation_m=None)]
    monkeypatch.setattr(downloader, 'fetch', lambda *args, **kwargs:
                        b'{"srid":4326,"coords":[[11.17,48.12,540.2]]}')
    with pytest.raises(ValueError, match='changed coordinate'):
        downloader.add_elevations([(11.16, 48.12)])
