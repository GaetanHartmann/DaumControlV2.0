"""P2 route data boundary: real imported geometry, no resistance commands."""
import json
import math
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator


class RoutePoint(BaseModel):
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000, allow_inf_nan=False)


class RouteInput(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=80)
    points: list[RoutePoint] = Field(min_length=2, max_length=3000)
    source: Literal['file', 'openstreetmap'] = 'file'
    attribution: str = Field(default='', max_length=300)

    @model_validator(mode='after')
    def validate_geometry(self):
        if not self.name.strip():
            raise ValueError('Streckenname fehlt')
        if self.source == 'openstreetmap' and not self.attribution.strip():
            raise ValueError('OpenStreetMap-Quellenangabe erforderlich')
        distance = sum(segment_distance(a, b) for a, b in zip(self.points, self.points[1:]))
        if not 0 < distance <= 2_000_000:
            raise ValueError('Import benötigt eine positive Strecke bis höchstens 2000 km')
        return self


class LibraryImportRequest(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1, strict=True)


class DeleteRequest(LibraryImportRequest):
    confirm: bool = Field(default=False, strict=True)


def segment_distance(a, b):
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat, dlon = lat2-lat1, math.radians(b.longitude-a.longitude)
    value = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6_371_000 * 2 * math.asin(min(1, math.sqrt(value)))


def route_data(body):
    distances = [0.0]
    for a, b in zip(body.points, body.points[1:]):
        distances.append(distances[-1] + segment_distance(a, b))
    return dict(name=body.name.strip(), points=[p.model_dump() for p in body.points],
                cumulative_metres=distances, distance_metres=distances[-1],
                closed_loop=segment_distance(body.points[0], body.points[-1]) <= 25,
                elevation_available=all(p.elevation_m is not None for p in body.points),
                source=body.source, attribution=body.attribution,
                distance_source='Aus importierter Koordinatenlinie berechnet; keine Routing-/Straßenprüfung',
                resistance_control=False, rendering='2d_preview')


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS virtual_routes (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, route_json TEXT NOT NULL,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')


def install_routes(app, get_engine, database, require_expected_user):
    @app.get('/api/routes/library')
    async def route_library():
        from .routes_material import library
        return library()

    def library_route(route_id):
        from .routes_material import load_route
        try:
            original = load_route(route_id)
        except (ValueError, KeyError, FileNotFoundError) as error:
            raise HTTPException(404, 'Streckendatensatz nicht verfügbar') from error
        body = RouteInput(name=original['name'], points=original['points'],
                          source=original['source'], attribution=original['attribution'])
        return dict(**route_data(body), library_id=route_id,
                    license_url=original['license_url'],
                    provenance=original.get('provenance') or {})

    @app.get('/api/routes/library/{route_id}')
    async def route_library_detail(route_id: str):
        return dict(id='library:'+route_id, **library_route(route_id))

    @app.post('/api/routes/library/{route_id}/import', status_code=201)
    async def route_library_import(route_id: str, body: LibraryImportRequest):
        # Explicit per-user copy; merely viewing the bundled library writes
        # nothing and never enables automatic resistance control.
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            data = library_route(route_id)
            with database() as db:
                cur = db.execute('INSERT INTO virtual_routes (user_id,route_json) VALUES (?,?)',
                                 (engine.user_id, json.dumps(data)))
                return dict(id=cur.lastrowid, **data)

    @app.get('/api/routes')
    async def listing():
        engine = get_engine()
        async with engine.lock:
            with database() as db:
                return [dict(id=r['id'], **json.loads(r['route_json'])) for r in db.execute(
                    'SELECT * FROM virtual_routes WHERE user_id=? ORDER BY id DESC', (engine.user_id,))]

    @app.post('/api/routes', status_code=201)
    async def create(body: RouteInput):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            data = route_data(body)
            with database() as db:
                cur = db.execute('INSERT INTO virtual_routes (user_id,route_json) VALUES (?,?)',
                                 (engine.user_id, json.dumps(data)))
                return dict(id=cur.lastrowid, **data)

    @app.post('/api/routes/{route_id}/delete')
    async def delete(route_id: int, body: DeleteRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            if body.confirm is not True:
                raise HTTPException(422, 'Löschen ausdrücklich bestätigen')
            with database() as db:
                if not db.execute('DELETE FROM virtual_routes WHERE id=? AND user_id=?',
                                  (route_id, engine.user_id)).rowcount:
                    raise HTTPException(404, 'Strecke nicht gefunden')
            return dict(deleted=route_id)
