"""Offline, integrity-checked library of explicitly attributed geographic examples."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re


DATA_DIR = Path(__file__).resolve().parents[1] / 'data' / 'routes'
_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,79}\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def _read_json(path: Path, limit: int):
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError('Streckendatensatz ist zu groß')
    def reject_constant(_):
        raise ValueError('Streckendatensatz enthält keine endlichen Zahlen')
    return raw, json.loads(raw, parse_constant=reject_constant)


def library() -> list[dict]:
    """Return public metadata only. No download, user data write or device command."""
    _, value = _read_json(DATA_DIR / 'index.json', 100_000)
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('Ungültiger Streckenkatalog')
    ids = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('Ungültiger Streckenkatalogeintrag')
        identifier = item.get('id', '')
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier) or identifier in ids:
            raise ValueError('Ungültige oder doppelte Streckenkennung')
        ids.add(identifier)
        if item.get('file') != f'{identifier}.json' or not _SHA256.fullmatch(str(item.get('sha256', ''))):
            raise ValueError('Ungültige Streckendatei oder Prüfsumme')
        if item.get('source') != 'openstreetmap' or not item.get('attribution') or not item.get('license_url'):
            raise ValueError('Streckenquelle oder Lizenzangabe fehlt')
    return value


def load_route(identifier: str) -> dict:
    """Read one checked data payload. Unknown id raises KeyError; bad data ValueError."""
    metadata = next((item for item in library() if item['id'] == identifier), None)
    if metadata is None:
        raise KeyError(identifier)
    base = DATA_DIR.resolve()
    path = (base / metadata['file']).resolve()
    if path.parent != base:
        raise ValueError('Streckendatei liegt außerhalb des Katalogs')
    raw, value = _read_json(path, 2_000_000)
    if hashlib.sha256(raw).hexdigest() != metadata['sha256']:
        raise ValueError('Prüfsumme der Streckendatei stimmt nicht')
    if not isinstance(value, dict) or any(value.get(k) != metadata[k] for k in ('id', 'name', 'source', 'attribution', 'license_url')):
        raise ValueError('Streckendatei passt nicht zum Katalog')
    points = value.get('points')
    if not isinstance(points, list) or not 2 <= len(points) <= 3000:
        raise ValueError('Ungültige Anzahl von Streckenpunkten')
    for point in points:
        if not isinstance(point, dict):
            raise ValueError('Ungültiger Streckenpunkt')
        for key, lower, upper, optional in (('longitude', -180, 180, False), ('latitude', -90, 90, False),
                                            ('elevation_m', -500, 9000, True)):
            number = point.get(key)
            if number is None and optional:
                continue
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not lower <= number <= upper:
                raise ValueError(f'Ungültiger Streckenwert: {key}')
    if len(points) != metadata.get('point_count'):
        raise ValueError('Streckenpunktzahl passt nicht zum Katalog')
    return value
