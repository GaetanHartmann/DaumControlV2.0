"""Build the bundled indoor route examples from public, attributed source data.

Run from the repository with Python 3.11+: python bike/deploy/fetch-route-material.py
No runtime network service or additional Python package is required. Raw responses
stay in the ignored cache; only derived ODbL route data is distributed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET


BIKE = Path(__file__).resolve().parents[1]
ROOT = BIKE.parent if BIKE.name == 'bike' else BIKE
CACHE = ROOT / '.cache' / 'fitness-material'
OUTPUT = BIKE / 'data' / 'routes'
OSM_API = 'https://api.openstreetmap.org/api/0.6/'
HEIGHT_URL = 'https://geoservices.bayern.de/bvvapi/od/hoehen/v1/elevation/list'
ODBL = 'https://opendatacommons.org/licenses/odbl/1-0/'
CC_BY = 'https://creativecommons.org/licenses/by/4.0/'
ATTRIBUTION = ('© OpenStreetMap contributors (ODbL); Geobasisdaten: Bayerische '
               'Vermessungsverwaltung – www.geodaten.bayern.de (Daten verändert), CC BY 4.0')
USER_AGENT = 'Fitness-Cockpit route-material (github.com/GaetanHartmann/DaumControlV2.0)'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def fetch(name, url, *, body=None, offline=False, refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    destination = CACHE / name
    if destination.exists() and not refresh:
        return destination.read_bytes()
    if offline:
        raise ValueError(f'Offline cache missing: {destination}')
    headers = {'User-Agent': USER_AGENT}
    if body is not None:
        headers.update({'Content-Type': 'application/json', 'Accept': 'application/json'})
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        value = response.read(20_000_001)
    if len(value) > 20_000_000:
        raise ValueError('Source response exceeds the 20 MB research limit')
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    temporary.write_bytes(value)
    temporary.replace(destination)
    return value


def distance(a, b):
    lat_a, lat_b = math.radians(a[1]), math.radians(b[1])
    value = (math.sin((lat_b - lat_a) / 2) ** 2
             + math.cos(lat_a) * math.cos(lat_b) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2)
    return 12_742_000 * math.asin(min(1, math.sqrt(value)))


def road_graph(responses):
    """Use only actual OSM nodes/edges; never join nearby unconnected endpoints."""
    nodes, ways = {}, {}
    for raw in responses:
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('Unexpected XML declarations in OSM data')
        root = ET.fromstring(raw)
        if root.tag != 'osm':
            raise ValueError('Expected OSM XML')
        nodes.update({n.attrib['id']: (float(n.attrib['lon']), float(n.attrib['lat']))
                      for n in root.findall('node')})
        ways.update({w.attrib['id']: w for w in root.findall('way')})
    graph = defaultdict(dict)
    for way_id in sorted(ways, key=int):
        way = ways[way_id]
        tags = {t.attrib['k']: t.attrib['v'] for t in way.findall('tag')}
        bicycle = tags.get('bicycle')
        if not tags.get('highway') or bicycle in ('no', 'use_sidepath'):
            continue
        if tags.get('highway') in ('motorway', 'motorway_link', 'trunk', 'trunk_link',
                                    'steps', 'construction', 'proposed'):
            continue
        if tags.get('access') in ('no', 'private') and bicycle not in ('yes', 'designated', 'permissive'):
            continue
        if tags.get('highway') == 'footway' and bicycle not in ('yes', 'designated', 'permissive'):
            continue
        path = [n.attrib['ref'] for n in way.findall('nd')]
        for a, b in zip(path, path[1:]):
            if a not in nodes or b not in nodes:
                raise ValueError('OSM way references an absent coordinate')
            if a == b or distance(nodes[a], nodes[b]) == 0:
                continue
            graph[a].setdefault(b, way_id)
            graph[b].setdefault(a, way_id)
    return nodes, graph


def longest_cycle(nodes, graph):
    """Select the longest simple fundamental cycle, deterministically.

    These are data examples for indoor riding, not a full bicycle router: turn
    restrictions, directional access, surfaces and temporary closures are not
    evaluated. Every returned segment must be an actual OSM way edge.
    """
    seen, depth, parent, candidates = set(), {}, {}, []
    for start in sorted(graph, key=int):
        if start in seen:
            continue
        seen.add(start)
        depth[start], parent[start] = 0, None
        stack = [(start, iter(sorted(graph[start], key=int)))]
        while stack:
            current, neighbours = stack[-1]
            following = next(neighbours, None)
            if following is None:
                stack.pop()
                continue
            if following == parent[current]:
                continue
            if following not in seen:
                seen.add(following)
                parent[following], depth[following] = current, depth[current] + 1
                stack.append((following, iter(sorted(graph[following], key=int))))
            elif depth[following] < depth[current]:
                cycle = [current]
                while cycle[-1] != following:
                    ancestor = parent[cycle[-1]]
                    if ancestor is None:
                        raise ValueError('Non-ancestral OSM graph cycle')
                    cycle.append(ancestor)
                cycle.append(current)
                candidates.append(cycle)
    if not candidates:
        raise ValueError('No genuinely closed road cycle in the source data')
    return max(candidates, key=lambda c: sum(distance(nodes[a], nodes[b]) for a, b in zip(c, c[1:])))


def add_elevations(coordinates, *, offline=False, refresh=False):
    """Small sequential batches avoid service errors seen with a 1813-point POST."""
    output, receipts = [], []
    for start in range(0, len(coordinates), 150):
        batch = coordinates[start:start + 150]
        body = canonical({'srid': 4326, 'coords': batch})
        digest = hashlib.sha256(body).hexdigest()
        raw = fetch(f'bavaria-height-{digest}.json', HEIGHT_URL, body=body,
                    offline=offline, refresh=refresh)
        response = json.loads(raw)
        values = response.get('coords', [])
        if response.get('srid') != 4326 or len(values) != len(batch):
            raise ValueError('Elevation response does not match its request')
        for coordinate, result in zip(batch, values):
            if len(result) != 3 or any(abs(float(result[i]) - coordinate[i]) > 0.000001 for i in (0, 1)):
                raise ValueError('Elevation service changed coordinate order or position')
            height = result[2]
            if height is not None and (not math.isfinite(height) or not -500 <= height <= 9000):
                raise ValueError('Invalid returned elevation')
            output.append(dict(longitude=coordinate[0], latitude=coordinate[1], elevation_m=height))
        receipts.append({'request_sha256': digest, 'response_sha256': hashlib.sha256(raw).hexdigest(),
                         'point_count': len(batch)})
    return output, receipts


def build(*, offline=False, refresh=False):
    definitions = [
        dict(id='grafrath-ampermoos', name='Grafrath – Ampermoos',
             relations=[6795968, 6805329, 13235623, 6332283, 6424952, 2871713],
             minimum_metres=6000, maximum_metres=15000,
             description='Kurze Runde aus verbundenen OSM-Radwegen südlich von Grafrath.'),
        dict(id='ammersee-runde', name='Rund um den Ammersee', relations=[551290],
             bbox='11.147,47.944,11.153,47.949', minimum_metres=40000, maximum_metres=55000,
             description='Seeumrundung aus OSM-Radwegen mit kartierter Verbindung bei Fischen.'),
    ]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    index = []
    retrieved = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for definition in definitions:
        sources, responses = [], []
        for relation in definition['relations']:
            url = f'{OSM_API}relation/{relation}/full'
            raw = fetch(f'relation-{relation}.osm', url, offline=offline, refresh=refresh)
            responses.append(raw)
            root = ET.fromstring(raw)
            element = root.find(f"relation[@id='{relation}']")
            sources.append({'url': url, 'sha256': hashlib.sha256(raw).hexdigest(),
                            'relation_id': relation, 'version': element.attrib.get('version'),
                            'timestamp': element.attrib.get('timestamp')})
        if 'bbox' in definition:
            url = f"{OSM_API}map?bbox={definition['bbox']}"
            raw = fetch('fischen-gap.osm', url, offline=offline, refresh=refresh)
            responses.append(raw)
            sources.append({'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
        nodes, graph = road_graph(responses)
        cycle = longest_cycle(nodes, graph)
        # Rotate to the northernmost actual node; no resampling, synthetic closure or simplification.
        ring = cycle[:-1]
        beginning = max(range(len(ring)), key=lambda i: (nodes[ring[i]][1], nodes[ring[i]][0]))
        ring = ring[beginning:] + ring[:beginning]
        cycle = ring + ring[:1]
        coordinates = [nodes[n] for n in cycle]
        total = sum(distance(a, b) for a, b in zip(coordinates, coordinates[1:]))
        if not definition['minimum_metres'] <= total <= definition['maximum_metres'] or len(cycle) > 3000:
            raise ValueError(f"Changed source geometry for {definition['id']}: {total:.0f} m, {len(cycle)} points")
        points, elevation_receipts = add_elevations(coordinates, offline=offline, refresh=refresh)
        data = {
            'id': definition['id'], 'name': definition['name'], 'description': definition['description'],
            'source': 'openstreetmap', 'attribution': ATTRIBUTION, 'license_url': ODBL, 'points': points,
            'provenance': {
                'retrieved_at': retrieved, 'osm_sources': sources,
                'osm_node_ids': [int(n) for n in cycle],
                'osm_segment_way_ids': [int(graph[a][b]) for a, b in zip(cycle, cycle[1:])],
                'selection': 'Longest simple fundamental cycle of connected OSM way edges; deterministic DFS; no interpolated closure.',
                'outdoor_navigation_verified': False, 'directional_access_verified': False,
                'elevation': {'source': 'Bayerische Vermessungsverwaltung Höhendienst (DGM1)',
                              'url': HEIGHT_URL, 'license_url': CC_BY, 'vertical_datum': 'DHHN2016',
                              'documentation_url': 'https://geoservices.bayern.de/bvvapi/od/hoehen/openapi.json',
                              'method': 'Official coordinate-height lookup at each unchanged OSM point; no missing-height substitution.',
                              'note': 'Geländehöhen; keine vermessene Fahrbahn-/Brückenhöhe. Dienstwerte in Metern.',
                              'batches': elevation_receipts},
            },
        }
        filename = f"{definition['id']}.json"
        raw = canonical(data) + b'\n'
        (OUTPUT / filename).write_bytes(raw)
        heights = [p['elevation_m'] for p in points if p['elevation_m'] is not None]
        index.append({
            'id': definition['id'], 'name': definition['name'], 'file': filename,
            'description': definition['description'], 'source': 'openstreetmap', 'attribution': ATTRIBUTION,
            'license_url': ODBL, 'source_urls': [s['url'] for s in sources] + [HEIGHT_URL],
            'sha256': hashlib.sha256(raw).hexdigest(), 'point_count': len(points),
            'distance_metres': round(total, 1), 'closed_loop': points[0] == points[-1],
            'elevation_available': len(heights) == len(points),
            'elevation_min_m': min(heights) if heights else None,
            'elevation_max_m': max(heights) if heights else None,
            'elevation_source': 'Bayerische Vermessungsverwaltung (DGM1), DHHN2016',
            'elevation_license_url': CC_BY, 'retrieved_at': retrieved,
            'outdoor_navigation_verified': False,
        })
        print(f"{definition['id']}: {len(points)} OSM points, {total / 1000:.2f} km, {len(heights)} official heights")
    (OUTPUT / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return index


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Rebuild using only previously cached responses')
    parser.add_argument('--refresh', action='store_true', help='Explicitly refresh public source responses')
    options = parser.parse_args()
    if options.offline and options.refresh:
        parser.error('--offline and --refresh are mutually exclusive')
    build(offline=options.offline, refresh=options.refresh)
