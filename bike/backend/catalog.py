"""One catalog over the existing plans; additive metadata and validation receipts.

No catalog operation starts a workout or sends a device command. Original plan
rows are untouched during migration; per-user state lives in separate tables.
"""
import hashlib
import json
import uuid
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .training import resolve_plan


class Segment(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    seconds: int = Field(strict=True, ge=1, le=7200)
    watts: int = Field(strict=True, ge=25, le=400)


class PlanInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    steps: list[Segment] = Field(min_length=1, max_length=100)
    duration_seconds: int | None = Field(default=None, strict=True, ge=1, le=43200)
    category: str = Field(default='Eigene', min_length=1, max_length=60)
    description: str = Field(default='', max_length=2000)
    intensity: str = Field(default='Selbst gewählt', max_length=120)

    @model_validator(mode='after')
    def exact_duration(self):
        if not self.name.strip():
            raise ValueError('Profilname darf nicht leer sein')
        total = sum(step.seconds for step in self.steps)
        if total > 43200 or (self.duration_seconds is not None and total != self.duration_seconds):
            raise ValueError('Segmentdauer muss der Gesamtdauer entsprechen und höchstens zwölf Stunden betragen')
        return self


class CreateRequest(PlanInput):
    expected_user_id: int | None = Field(default=None, ge=1)


class UpdateRequest(CreateRequest):
    expected_revision: int = Field(ge=1)


class ActionRequest(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)
    expected_revision: int | None = Field(default=None, ge=1)


class DuplicateRequest(ActionRequest):
    name: str | None = Field(default=None, min_length=1, max_length=80)


class DeleteRequest(ActionRequest):
    confirm: bool = Field(strict=True, default=False)


class FavoriteRequest(ActionRequest):
    favorite: bool = Field(strict=True)


class CheckRequest(ActionRequest):
    intensity_percent: int = Field(default=100, ge=50, le=130)
    training_mode: Literal['power', 'hr'] = 'power'
    validation_token: str | None = Field(default=None, max_length=100)


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS plan_catalog (
        plan_id INTEGER PRIMARY KEY, owner_user_id INTEGER, source TEXT NOT NULL,
        category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', intensity TEXT NOT NULL DEFAULT '',
        revision INTEGER NOT NULL DEFAULT 1)''')
    db.execute('''CREATE TABLE IF NOT EXISTS plan_favorites (
        plan_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        PRIMARY KEY(plan_id,user_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS plan_checks (
        plan_id INTEGER NOT NULL, user_id INTEGER NOT NULL, status TEXT NOT NULL,
        signature TEXT, token TEXT, PRIMARY KEY(plan_id,user_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS coach_drafts (
        token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, provider TEXT NOT NULL,
        proposal_json TEXT NOT NULL, context_json TEXT NOT NULL, adopted_plan_id INTEGER,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    seeds = [
        ('catalog-easy', 'Lockere Runde', 'Regeneration', [(300, 50), (900, 70), (300, 40)]),
        ('catalog-interval', 'Intervalle', 'Intervalle', [(300, 60), (120, 100), (120, 60), (120, 100), (120, 60), (300, 40)]),
        ('catalog-hill', 'Bergfahrt', 'Bergfahrt', [(300, 50), (300, 80), (300, 110), (300, 80), (300, 40)]),
        ('catalog-endurance', 'Ausdauerfahrt', 'Ausdauer', [(300, 50), (1500, 90), (300, 40)]),
    ]
    for key, name, category, phases in seeds:
        steps = [dict(name='Aufwärmen' if i == 0 else 'Ausrollen' if i == len(phases)-1 else f'Abschnitt {i}', seconds=seconds, watts=watts)
                 for i, (seconds, watts) in enumerate(phases)]
        db.execute('INSERT OR IGNORE INTO plans (name,steps,template_key,meta) VALUES (?,?,?,?)',
                   (name, json.dumps(steps), key, json.dumps(dict(category=category,
                    description='Editierbare Ausgangswerte über Kopie; vor dem Training passend wählen.', catalog_seed=True))))


def metadata(db, row):
    record = db.execute('SELECT * FROM plan_catalog WHERE plan_id=?', (row['id'],)).fetchone()
    if record:
        return dict(record)
    try:
        meta = json.loads(row['meta'] or '{}')
    except (TypeError, ValueError):
        meta = {}
    return dict(plan_id=row['id'], owner_user_id=None,
                source='preset' if row['template_key'] else 'ai' if meta.get('source') == 'ai' else 'manual',
                category=meta.get('category') or 'Eigene', description=meta.get('description') or '',
                intensity=meta.get('intensity') or ('Relativ zur FTP' if meta.get('relative_ftp') else 'Selbst gewählt'), revision=1)


def assert_plan_access(db, engine, plan_id):
    row = db.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Trainingsprofil nicht gefunden')
    info = metadata(db, row)
    if info['owner_user_id'] is not None and info['owner_user_id'] != engine.user_id:
        raise HTTPException(404, 'Trainingsprofil nicht gefunden')
    return row


def limits(engine, training_mode='power'):
    if hasattr(engine, 'power_limits'):
        return engine.power_limits(training_mode=training_mode)
    cap = engine.connector.capabilities
    return dict(minimum=max(cap.get('power_min_watts', 25), getattr(engine.profile, 'power_min_watts', None) or 25),
                maximum=min(cap.get('power_max_watts', 400), getattr(engine.profile, 'power_max_watts', None) or 400),
                step=cap.get('power_step_watts', 5))


def checked_plan(row, engine, intensity_percent=100, training_mode='power'):
    try:
        steps = json.loads(row['steps'])
        # Legacy metadata (zones, relative FTP, virtual grade) stays in storage.
        PlanInput(name=row['name'], steps=steps)
        plan = resolve_plan(row, engine.profile, intensity_percent)
        bounds = limits(engine, training_mode)
        if bounds['minimum'] > bounds['maximum']:
            raise ValueError('Geräte- und Nutzergrenzen überschneiden sich nicht')
        if any(not bounds['minimum'] <= step['watts'] <= bounds['maximum'] for step in plan['steps']):
            raise ValueError(f"Profil überschreitet erlaubte Leistung {bounds['minimum']}–{bounds['maximum']} W")
        return plan
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise HTTPException(422, 'Ungültiges Trainingsprofil: ' + str(error))


def signature(row, engine, intensity_percent=100, training_mode='power'):
    value = dict(id=row['id'], name=row['name'], steps=row['steps'], meta=row['meta'],
                 profile=engine.profile.model_dump(), capabilities=engine.connector.capabilities,
                 mode=engine.mode, intensity_percent=intensity_percent, training_mode=training_mode)
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def plan_for_start(db, engine, plan_id, validation_token=None, intensity_percent=100, training_mode='power'):
    row = assert_plan_access(db, engine, plan_id)
    checked_plan(row, engine, intensity_percent, training_mode)
    if db.execute('SELECT 1 FROM plan_catalog WHERE plan_id=?', (plan_id,)).fetchone() and not validation_token:
        raise HTTPException(409, 'Dieses Profil zuerst im Trainingskatalog prüfen und Start vorbereiten.')
    if validation_token:
        receipt = db.execute('SELECT * FROM plan_checks WHERE plan_id=? AND user_id=?', (plan_id, engine.user_id)).fetchone()
        if not receipt or receipt['status'] != 'ready' or receipt['token'] != validation_token or receipt['signature'] != signature(row, engine, intensity_percent, training_mode):
            raise HTTPException(409, 'Profil oder Konfiguration geändert. Bitte erneut prüfen und Start vorbereiten.')
    return row


def catalog_record(db, engine, row):
    info = metadata(db, row)
    error = None
    try:
        plan = checked_plan(row, engine)
    except HTTPException as exc:
        error = exc.detail
        try:
            raw_steps = json.loads(row['steps'])
            raw_steps = [Segment.model_validate(step).model_dump() for step in raw_steps]
        except (TypeError, ValueError):
            raw_steps = []
        plan = dict(id=row['id'], name=row['name'], steps=raw_steps, meta={})
    receipt = db.execute('SELECT * FROM plan_checks WHERE plan_id=? AND user_id=?', (row['id'], engine.user_id)).fetchone()
    status = receipt['status'] if receipt and (not receipt['signature'] or receipt['signature'] == signature(row, engine)) else 'draft'
    favorite = db.execute('SELECT 1 FROM plan_favorites WHERE plan_id=? AND user_id=?', (row['id'], engine.user_id)).fetchone() is not None
    watts = [step['watts'] for step in plan['steps']]
    return dict(**plan, source=info['source'], category=info['category'], description=info['description'],
                intensity=info['intensity'], revision=info['revision'], status=status,
                duration_seconds=sum(step['seconds'] for step in plan['steps']),
                min_watts=min(watts) if watts else None, max_watts=max(watts) if watts else None,
                favorite=favorite, editable=info['source'] != 'preset', valid=error is None, validation_error=error)


def check_revision(info, expected):
    if expected is not None and info['revision'] != expected:
        raise HTTPException(409, 'Profil wurde inzwischen geändert. Bitte neu laden.')


def create_plan(db, engine, body, source='manual', provider=None):
    meta = dict(category=body.category, description=body.description, intensity=body.intensity,
                source=source, relative_ftp=False)
    if provider:
        meta['coach_provider'] = provider
    cur = db.execute('INSERT INTO plans (name,steps,meta) VALUES (?,?,?)',
                     (body.name.strip(), json.dumps([step.model_dump() for step in body.steps]), json.dumps(meta)))
    plan_id = cur.lastrowid
    db.execute('INSERT INTO plan_catalog (plan_id,owner_user_id,source,category,description,intensity) VALUES (?,?,?,?,?,?)',
               (plan_id, engine.user_id, source, body.category, body.description, body.intensity))
    return plan_id


def install_routes(app, get_engine, database, require_expected_user, require_user_change):
    @app.get('/api/catalog')
    async def catalog():
        engine = get_engine()
        async with engine.lock:
            with database() as db:
                plans = []
                for row in db.execute('SELECT * FROM plans ORDER BY id'):
                    info = metadata(db, row)
                    if info['owner_user_id'] in (None, engine.user_id):
                        plans.append(catalog_record(db, engine, row))
                return dict(plans=plans, power_limits=limits(engine))

    @app.get('/api/catalog/{plan_id}')
    async def detail(plan_id: int):
        engine = get_engine()
        async with engine.lock:
            with database() as db:
                return catalog_record(db, engine, assert_plan_access(db, engine, plan_id))

    @app.post('/api/catalog', status_code=201)
    async def create(body: CreateRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            with database() as db:
                plan_id = create_plan(db, engine, body)
                return dict(plan_id=plan_id, plan=catalog_record(db, engine, assert_plan_access(db, engine, plan_id)))

    @app.post('/api/catalog/{plan_id}/update')
    async def update(plan_id: int, body: UpdateRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            with database() as db:
                row = assert_plan_access(db, engine, plan_id)
                info = metadata(db, row)
                check_revision(info, body.expected_revision)
                if info['source'] == 'preset':
                    raise HTTPException(409, 'Vorlagen bleiben erhalten. Bitte zuerst eine eigene Kopie erstellen.')
                meta = dict(category=body.category, description=body.description, intensity=body.intensity,
                            source=info['source'], relative_ftp=False)
                db.execute('UPDATE plans SET name=?,steps=?,meta=? WHERE id=?',
                           (body.name.strip(), json.dumps([step.model_dump() for step in body.steps]), json.dumps(meta), plan_id))
                db.execute('INSERT OR REPLACE INTO plan_catalog VALUES (?,?,?,?,?,?,?)',
                           (plan_id, info['owner_user_id'], info['source'], body.category, body.description, body.intensity, info['revision']+1))
                db.execute('DELETE FROM plan_checks WHERE plan_id=?', (plan_id,))
                return dict(plan_id=plan_id, plan=catalog_record(db, engine, assert_plan_access(db, engine, plan_id)))

    @app.post('/api/catalog/{plan_id}/duplicate', status_code=201)
    async def duplicate(plan_id: int, body: DuplicateRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            with database() as db:
                row = assert_plan_access(db, engine, plan_id)
                check_revision(metadata(db, row), body.expected_revision)
                plan = catalog_record(db, engine, row)
                value = PlanInput(name=body.name or (plan['name'][:70]+' · Kopie'), steps=plan['steps'],
                                  category=plan['category'], description=plan['description'], intensity=plan['intensity'])
                new_id = create_plan(db, engine, value)
                return dict(plan_id=new_id, plan=catalog_record(db, engine, assert_plan_access(db, engine, new_id)))

    @app.post('/api/catalog/{plan_id}/delete')
    async def delete(plan_id: int, body: DeleteRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            with database() as db:
                row = assert_plan_access(db, engine, plan_id)
                info = metadata(db, row)
                check_revision(info, body.expected_revision)
                if not body.confirm:
                    raise HTTPException(422, 'Löschen ausdrücklich bestätigen')
                if info['source'] == 'preset':
                    raise HTTPException(409, 'Mitgelieferte Vorlage bleibt erhalten; eigene Kopien können gelöscht werden.')
                if db.execute('SELECT 1 FROM training_entries WHERE plan_id=? LIMIT 1', (plan_id,)).fetchone():
                    raise HTTPException(409, 'Profil wird in einem persönlichen Planeintrag verwendet und bleibt erhalten.')
                db.execute('DELETE FROM plans WHERE id=?', (plan_id,))
                for table in ('plan_catalog', 'plan_favorites', 'plan_checks'):
                    db.execute('DELETE FROM '+table+' WHERE plan_id=?', (plan_id,))
                return dict(deleted=plan_id)

    @app.post('/api/catalog/{plan_id}/favorite')
    async def favorite(plan_id: int, body: FavoriteRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            with database() as db:
                assert_plan_access(db, engine, plan_id)
                if body.favorite:
                    db.execute('INSERT OR IGNORE INTO plan_favorites VALUES (?,?)', (plan_id, engine.user_id))
                else:
                    db.execute('DELETE FROM plan_favorites WHERE plan_id=? AND user_id=?', (plan_id, engine.user_id))
                return dict(plan_id=plan_id, favorite=body.favorite)

    @app.post('/api/catalog/{plan_id}/accept')
    async def accept(plan_id: int, body: ActionRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            with database() as db:
                row = assert_plan_access(db, engine, plan_id)
                check_revision(metadata(db, row), body.expected_revision)
                db.execute('INSERT OR REPLACE INTO plan_checks VALUES (?,?,?,?,?)', (plan_id, engine.user_id, 'accepted', None, None))
                return dict(plan_id=plan_id, status='accepted')

    @app.post('/api/catalog/{plan_id}/validate')
    async def validate(plan_id: int, body: CheckRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            with database() as db:
                row = assert_plan_access(db, engine, plan_id)
                check_revision(metadata(db, row), body.expected_revision)
                plan = checked_plan(row, engine, body.intensity_percent, body.training_mode)
                token = uuid.uuid4().hex
                db.execute('INSERT OR REPLACE INTO plan_checks VALUES (?,?,?,?,?)',
                           (plan_id, engine.user_id, 'validated', signature(row, engine, body.intensity_percent, body.training_mode), token))
                return dict(valid=True, plan_id=plan_id, status='validated', validation_token=token,
                            plan=catalog_record(db, engine, row), power_limits=limits(engine))

    @app.post('/api/catalog/{plan_id}/prepare')
    async def prepare(plan_id: int, body: CheckRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            with database() as db:
                row = assert_plan_access(db, engine, plan_id)
                check_revision(metadata(db, row), body.expected_revision)
                checked_plan(row, engine, body.intensity_percent, body.training_mode)
                check = db.execute('SELECT * FROM plan_checks WHERE plan_id=? AND user_id=?', (plan_id, engine.user_id)).fetchone()
                if not check or check['status'] not in ('validated', 'ready') or not body.validation_token or check['token'] != body.validation_token or check['signature'] != signature(row, engine, body.intensity_percent, body.training_mode):
                    raise HTTPException(409, 'Profil oder Konfiguration geändert. Zuerst erneut prüfen.')
                if engine.mode != 'demo':
                    if not engine.connected:
                        raise HTTPException(422, 'Ergometer nicht verbunden. Verbinden oder bewusst Demo wählen.')
                    if 'power' not in engine.connector.capabilities.get('control', []):
                        raise HTTPException(422, 'Gerät unterstützt keine Wattsteuerung. Demo/Vorschau verwenden.')
                if body.training_mode == 'hr' and (not engine.profile.hr_max or not engine.profile.hr_ceiling or engine.hr.value() is None or engine.hr.age() >= 3):
                    raise HTTPException(422, 'Pulsmodus benötigt persönliche Pulsgrenzen und ein frisches Sensorsignal.')
                db.execute('UPDATE plan_checks SET status=? WHERE plan_id=? AND user_id=?', ('ready', plan_id, engine.user_id))
                return dict(ready=True, plan_id=plan_id, status='ready', validation_token=check['token'])
