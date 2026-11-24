"""Additive training planning, transparent analysis and manual activities.

All recommendations are conservative, editable suggestions. No medical or
fitness diagnosis and no VO2max/calorie estimate is derived from a workout.
"""
import json
import math
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator


class OwnedRequest(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)


class GeneratorRequest(OwnedRequest):
    kind: Literal['endurance', 'interval', 'recovery'] = 'endurance'
    minutes: int = Field(default=30, ge=10, le=120)
    watts: int = Field(default=100, ge=25, le=400)
    warmup_minutes: int = Field(default=5, ge=1, le=20)
    cooldown_minutes: int = Field(default=5, ge=1, le=20)
    name: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode='after')
    def phases_fit(self):
        if self.warmup_minutes + self.cooldown_minutes >= self.minutes:
            raise ValueError('Aufwärmen und Ausrollen müssen kürzer als die Gesamtdauer sein')
        return self


def generate_plan(body: GeneratorRequest):
    def step(name, seconds, factor):
        return dict(name=name, seconds=seconds,
                    watts=max(25, min(400, math.floor(body.watts * factor + .5))))
    middle = (body.minutes - body.warmup_minutes - body.cooldown_minutes) * 60
    steps = [step('Aufwärmen', body.warmup_minutes * 60, .55)]
    if body.kind == 'interval':
        # Fixed, reproducible distribution; no single-ride-driven progression.
        pairs = min(6, max(1, middle // 180))
        remaining = middle
        for index in range(pairs):
            pair_duration = remaining // (pairs - index)
            work = pair_duration * 2 // 3
            steps.extend([step(f'Intervall {index + 1}', work, 1),
                          step(f'Erholung {index + 1}', pair_duration - work, .55)])
            remaining -= pair_duration
    else:
        steps.append(step('Regeneration' if body.kind == 'recovery' else 'Ausdauer',
                          middle, .70 if body.kind == 'recovery' else 1))
    steps.append(step('Ausrollen', body.cooldown_minutes * 60, .45))
    title = {'endurance': 'Ausdauer', 'interval': 'Intervalle', 'recovery': 'Regeneration'}[body.kind]
    return dict(name=body.name or f'{title} {body.minutes}', steps=steps,
                meta=dict(category=title, minutes=body.minutes, generated=True,
                          relative_ftp=False, generator=body.model_dump(exclude={'expected_user_id'}),
                          description='Manuell gewählte Wattbasis; vor Start prüfen und anpassen. Keine automatische Leistungssteigerung.'))


class StrengthExercise(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    variant: str = Field(default='Wand / erhöht', max_length=80)
    sets: int = Field(default=2, ge=1, le=6)
    repetitions: int = Field(default=8, ge=1, le=50)
    rest_seconds: int = Field(default=60, ge=10, le=600)


class PlannerRequest(OwnedRequest):
    plan_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    scheduled_for: date | None = None
    strength_position: Literal['before', 'after'] = 'before'
    strength: list[StrengthExercise] = Field(default_factory=list, max_length=12)


class ProgressRequest(OwnedRequest):
    status: Literal['planned', 'completed', 'skipped'] = 'planned'
    strength_completed: list[int] = Field(default_factory=list, max_length=12)


class AdoptRequest(OwnedRequest):
    ride_id: int | None = Field(default=None, ge=1)
    scheduled_for: date | None = None


class ManualTreadmill(OwnedRequest):
    seconds: int = Field(ge=60, le=43200)
    distance_km: float | None = Field(default=None, ge=0, le=200, allow_inf_nan=False)
    heart_rate_bpm: int | None = Field(default=None, ge=30, le=250)
    incline_percent: float | None = Field(default=None, ge=-20, le=40, allow_inf_nan=False)
    started_at: datetime | None = None
    name: str = Field(default='Laufband · manuell', min_length=1, max_length=80)

    @model_validator(mode='after')
    def timestamp_has_zone(self):
        if self.started_at is not None and self.started_at.tzinfo is None:
            raise ValueError('Startzeit muss eine Zeitzone enthalten')
        if self.started_at is not None and self.started_at > datetime.now(timezone.utc):
            raise ValueError('Startzeit darf nicht in der Zukunft liegen')
        return self


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS training_entries (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, plan_id INTEGER,
        name TEXT NOT NULL, scheduled_for TEXT, strength_position TEXT NOT NULL DEFAULT 'before',
        strength_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'planned',
        strength_completed_json TEXT NOT NULL DEFAULT '[]', source_ride_id INTEGER,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, source_ride_id))''')


def entry_record(row):
    value = dict(row)
    value['strength'] = json.loads(value.pop('strength_json'))
    value['strength_completed'] = json.loads(value.pop('strength_completed_json'))
    return value


def safe_summary(row):
    try:
        value = json.loads(row['summary_json'] or '{}')
        return value if isinstance(value, dict) else {}
    except (KeyError, IndexError, TypeError, ValueError):
        return {}


def power_is_verified(summary):
    """Only explicit independent measurement provenance enables power analysis.

    A protocol acknowledgement or a device's numeric report is not such proof.
    Legacy aggregates remain on disk unchanged and fail this gate by default.
    """
    quality = summary.get('measurement_quality')
    return (summary.get('power_measurement_verified') is True and
            isinstance(quality, dict) and quality.get('power_watts') == 'verified_measured')


def finite_value(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def analysis_for(db, engine, ride_id=None):
    sql = 'SELECT * FROM rides WHERE user_id=? AND mode<>? AND activity_type=?'
    args = [engine.user_id, 'demo', 'indoor_cycling']
    if ride_id is not None:
        sql += ' AND id=?'
        args.append(ride_id)
    row = db.execute(sql + ' ORDER BY id DESC LIMIT 1', args).fetchone()
    limitations = ['Orientierende Auswertung, keine Diagnose oder VO₂max-Messung.',
                  'Ein einzelnes Training erlaubt keine verlässliche Einstufung der allgemeinen Fitness.',
                  'Puls hängt unter anderem von Belastungsverlauf und Messqualität ab; persönliche HFmax wird nicht aus Alter geschätzt.']
    if row is None:
        return dict(available=False, ride_id=None, proposal=None, limitations=limitations + [
            'Noch keine reale Radeinheit vorhanden. Demo- und manuelle Laufbanddaten werden nicht für Radempfehlungen verwendet.'])
    summary = safe_summary(row)
    averages = dict(summary['averages']) if isinstance(summary.get('averages'), dict) else {}
    coverage = dict(summary['coverage_seconds']) if isinstance(summary.get('coverage_seconds'), dict) else {}
    seconds = finite_value(row['seconds']) or 0
    verified = power_is_verified(summary)
    archived_watts = finite_value(averages.get('power_watts'))
    watts = archived_watts if verified else None
    power_seconds = finite_value(coverage.get('power_watts')) or 0
    if not verified:
        averages['power_watts'] = None
        coverage['power_watts'] = 0
        power_seconds = 0
        limitations.append('Leistungswerte sind nicht als unabhängig gemessene Tretleistung verifiziert. Alte Geräteangaben bleiben archiviert, werden aber nicht für Watt/kg, Intensität, Leistungsvergleiche oder belastungsabhängige Empfehlungen verwendet.')
    valid = verified and watts is not None and watts >= 0 and seconds > 0 and power_seconds >= seconds * .8
    weight = summary.get('weight_kg')
    per_kg = round(watts / weight, 2) if valid and finite_value(weight) is not None and weight > 0 else None
    if not valid:
        limitations.append('Leistungsdaten fehlen oder decken weniger als 80 % der Trainingszeit ab; keine belastungsabhängige Empfehlung.')
    if per_kg is None:
        limitations.append('Watt/kg nur bei ausreichender Leistungsabdeckung und gespeichertem Gewicht zur Einheit verfügbar.')
    ftp = getattr(engine.profile, 'ftp_watts', None)
    intensity = dict(label='nicht verfügbar', ratio=None, basis=None)
    if valid and ftp:
        ratio = watts / ftp
        intensity = dict(label='unter 60 % FTP' if ratio < .6 else '60–80 % FTP' if ratio <= .8 else 'über 80 % FTP',
                         ratio=round(ratio, 2), basis='Durchschnittsleistung / aktuell hinterlegte FTP; keine physiologische Diagnose')
    comparison = None
    if valid:
        previous = db.execute('SELECT * FROM rides WHERE user_id=? AND id<? AND mode<>? AND activity_type=? ORDER BY id DESC LIMIT 20',
                              (engine.user_id, row['id'], 'demo', 'indoor_cycling')).fetchall()
        for older in previous:
            old = safe_summary(older)
            if not power_is_verified(old):
                continue
            old_averages = old.get('averages') if isinstance(old.get('averages'), dict) else {}
            old_coverage = old.get('coverage_seconds') if isinstance(old.get('coverage_seconds'), dict) else {}
            old_average = finite_value(old_averages.get('power_watts'))
            old_cover = finite_value(old_coverage.get('power_watts')) or 0
            old_duration = finite_value(older['seconds'])
            if (power_is_verified(old) and old_duration and .8 <= old_duration / seconds <= 1.2 and
                    old_average is not None and old_cover >= old_duration * .8):
                comparison = dict(ride_id=older['id'], power_delta_watts=round(watts - old_average, 1),
                                  note='Ähnliche Dauer (±20 %); Leistungsunterschied ist kein Nachweis eines Fitnessgewinns.')
                break
    trend = None
    try:
        samples = json.loads(row['samples_json'] or '[]') if valid else []
        points = [(finite_value(s[0]), finite_value(s[1])) for s in samples if isinstance(s, list) and len(s)>1]
        points = [(elapsed, power) for elapsed, power in points if elapsed is not None and power is not None]
        first = [power for elapsed, power in points if elapsed <= seconds / 3]
        last = [power for elapsed, power in points if elapsed >= seconds * 2 / 3]
        if valid and first and last:
            trend = dict(first_third_watts=round(sum(first) / len(first), 1), last_third_watts=round(sum(last) / len(last), 1),
                         note='Näherung aus gespeicherten Stichproben, nicht zeitgewichtet; Planphasen beeinflussen den Verlauf.')
    except (TypeError, ValueError):
        pass
    proposal = None
    if valid and row['finish_reason'] not in ('error', 'safety'):
        comfortable = getattr(engine.profile, 'comfortable_watts', None)
        target = max(25, min(100, math.floor(watts * .7), comfortable or 100))
        proposal = generate_plan(GeneratorRequest(kind='recovery', minutes=20, watts=target,
                                                  name='Nächste Einheit · locker 20'))
        proposal['reason'] = 'Bewusst lockerer Vorschlag ohne automatische Steigerung; Tagesform und Erholung selbst prüfen.'
    elif row['finish_reason'] in ('error', 'safety'):
        limitations.append('Die Einheit endete mit einem Fehler oder Sicherheitsstopp; daraus wird kein Folgetraining erzeugt.')
    return dict(available=valid, ride_id=row['id'], duration_seconds=seconds, averages=averages,
                coverage_seconds=coverage, watts_per_kg=per_kg, weight_kg=weight,
                intensity=intensity, comparison=comparison, trend=trend,
                power_measurement_verified=verified,
                reported_unverified_power_watts=archived_watts if not verified else None,
                proposal=proposal, limitations=limitations)


def install_routes(app, get_engine, database, require_expected_user, require_user_change):
    """Use a getter so tests/restarts never retain a stale Engine instance."""
    @app.get('/api/generator/preview')
    async def preview(kind: Literal['endurance', 'interval', 'recovery'] = 'endurance',
                      minutes: int = 30, watts: int = 100, warmup_minutes: int = 5, cooldown_minutes: int = 5):
        try:
            return generate_plan(GeneratorRequest(kind=kind, minutes=minutes, watts=watts,
                                                 warmup_minutes=warmup_minutes, cooldown_minutes=cooldown_minutes))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post('/api/generator/preview')
    async def preview_post(body: GeneratorRequest):
        return generate_plan(body)

    @app.post('/api/generator/save', status_code=201)
    async def save_generated(body: GeneratorRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            plan = generate_plan(body)
            with database() as db:
                cur = db.execute('INSERT INTO plans (name,steps,meta) VALUES (?,?,?)',
                                 (plan['name'], json.dumps(plan['steps']), json.dumps(plan['meta'])))
                return dict(plan_id=cur.lastrowid, plan=plan)

    @app.get('/api/analysis')
    async def analysis(ride_id: int | None = None):
        engine = get_engine()
        async with engine.lock:
            with database() as db:
                return analysis_for(db, engine, ride_id)

    @app.get('/api/planner')
    async def planner():
        engine = get_engine()
        async with engine.lock:
            with database() as db:
                return [entry_record(r) for r in db.execute('SELECT * FROM training_entries WHERE user_id=? ORDER BY COALESCE(scheduled_for,created) DESC,id DESC', (engine.user_id,))]

    @app.post('/api/planner', status_code=201)
    async def add_entry(body: PlannerRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            with database() as db:
                if body.plan_id:
                    from .catalog import assert_plan_access
                    assert_plan_access(db, engine, body.plan_id)
                plan = db.execute('SELECT name FROM plans WHERE id=?', (body.plan_id,)).fetchone() if body.plan_id else None
                if body.plan_id and plan is None:
                    raise HTTPException(404, 'Trainingsplan nicht gefunden')
                if body.plan_id is None and not body.strength:
                    raise HTTPException(422, 'Trainingsplan oder Kraftübungen auswählen')
                cur = db.execute('INSERT INTO training_entries (user_id,plan_id,name,scheduled_for,strength_position,strength_json) VALUES (?,?,?,?,?,?)',
                                 (engine.user_id, body.plan_id, body.name or (plan['name'] if plan else 'Optionales Krafttraining'),
                                  body.scheduled_for.isoformat() if body.scheduled_for else None, body.strength_position,
                                  json.dumps([s.model_dump() for s in body.strength])))
                return entry_record(db.execute('SELECT * FROM training_entries WHERE id=?', (cur.lastrowid,)).fetchone())

    @app.post('/api/planner/{entry_id}/status')
    @app.post('/api/planner/{entry_id}/progress')
    async def progress(entry_id: int, body: ProgressRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            with database() as db:
                row = db.execute('SELECT * FROM training_entries WHERE id=? AND user_id=?', (entry_id, engine.user_id)).fetchone()
                if row is None:
                    raise HTTPException(404, 'Planeintrag nicht gefunden')
                count = len(json.loads(row['strength_json']))
                if any(i < 0 or i >= count for i in body.strength_completed):
                    raise HTTPException(422, 'Ungültiger Übungsindex')
                completed = sorted(set(body.strength_completed))
                db.execute('UPDATE training_entries SET status=?,strength_completed_json=? WHERE id=?',
                           (body.status, json.dumps(completed), entry_id))
                return entry_record(db.execute('SELECT * FROM training_entries WHERE id=?', (entry_id,)).fetchone())

    @app.put('/api/planner/{entry_id}')
    @app.post('/api/planner/{entry_id}/edit')
    async def edit_entry(entry_id: int, body: PlannerRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            with database() as db:
                old = db.execute('SELECT * FROM training_entries WHERE id=? AND user_id=?', (entry_id, engine.user_id)).fetchone()
                if old is None:
                    raise HTTPException(404, 'Planeintrag nicht gefunden')
                if body.plan_id:
                    from .catalog import assert_plan_access
                    assert_plan_access(db, engine, body.plan_id)
                plan = db.execute('SELECT name FROM plans WHERE id=?', (body.plan_id,)).fetchone() if body.plan_id else None
                if body.plan_id and plan is None:
                    raise HTTPException(404, 'Trainingsplan nicht gefunden')
                if body.plan_id is None and not body.strength:
                    raise HTTPException(422, 'Trainingsplan oder Kraftübungen auswählen')
                exercises = [s.model_dump() for s in body.strength]
                unchanged_training = (old['plan_id'] == body.plan_id and
                                      json.loads(old['strength_json']) == exercises and
                                      old['strength_position'] == body.strength_position)
                # A changed exercise or reordered block must not inherit the
                # completion tick of a different exercise at the same index.
                db.execute('''UPDATE training_entries SET plan_id=?,name=?,scheduled_for=?,
                    strength_position=?,strength_json=?,status=?,strength_completed_json=? WHERE id=?''',
                           (body.plan_id, body.name or (plan['name'] if plan else 'Optionales Krafttraining'),
                            body.scheduled_for.isoformat() if body.scheduled_for else None,
                            body.strength_position, json.dumps(exercises),
                            old['status'] if unchanged_training else 'planned',
                            old['strength_completed_json'] if unchanged_training else '[]', entry_id))
                return entry_record(db.execute('SELECT * FROM training_entries WHERE id=?', (entry_id,)).fetchone())

    @app.post('/api/recommendation/adopt')
    @app.post('/api/planner/adopt')
    async def adopt(body: AdoptRequest):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            with database() as db:
                data = analysis_for(db, engine, body.ride_id)
                if not data.get('proposal'):
                    raise HTTPException(409, 'Keine ausreichend belegte Empfehlung verfügbar')
                existing = db.execute('SELECT * FROM training_entries WHERE user_id=? AND source_ride_id=?',
                                      (engine.user_id, data['ride_id'])).fetchone()
                if existing:
                    return dict(plan_id=existing['plan_id'], entry=entry_record(existing), already_adopted=True)
                plan = data['proposal']
                cur = db.execute('INSERT INTO plans (name,steps,meta) VALUES (?,?,?)',
                                 (plan['name'], json.dumps(plan['steps']), json.dumps(plan['meta'])))
                plan_id = cur.lastrowid
                cur = db.execute('INSERT INTO training_entries (user_id,plan_id,name,scheduled_for,source_ride_id) VALUES (?,?,?,?,?)',
                                 (engine.user_id, plan_id, plan['name'], body.scheduled_for.isoformat() if body.scheduled_for else None, data['ride_id']))
                return dict(plan_id=plan_id, entry=entry_record(db.execute('SELECT * FROM training_entries WHERE id=?', (cur.lastrowid,)).fetchone()), already_adopted=False)

    @app.post('/api/manual/treadmill', status_code=201)
    async def manual_treadmill(body: ManualTreadmill):
        engine = get_engine()
        async with engine.lock:
            require_expected_user(body.expected_user_id)
            require_user_change()
            summary = dict(duration_seconds=body.seconds, averages=dict(power_watts=None, heart_rate_bpm=body.heart_rate_bpm, cadence_rpm=None),
                           coverage_seconds=dict(power_watts=0, heart_rate_bpm=0, cadence_rpm=0),
                           mechanical_energy_kj=None, calories_kcal=None, simulated=False,
                           weight_kg=getattr(engine.profile, 'weight_kg', None),
                           sources=dict(power_watts=None, heart_rate_bpm='manual' if body.heart_rate_bpm is not None else None, cadence_rpm=None),
                           source='manual', incline_percent=body.incline_percent,
                           note='Manuelle Zusammenfassung; keine zeitliche Messspur oder gemessene Datenabdeckung.')
            with database() as db:
                cur = db.execute('''INSERT INTO rides (seconds,distance,energy,mode,samples_json,plan_name,training_mode,started_at,user_id,activity_type,finish_reason,summary_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                                 (body.seconds, body.distance_km, None, 'manual', '[]', body.name, 'manual',
                                  body.started_at.astimezone(timezone.utc).isoformat() if body.started_at else None,
                                  engine.user_id, 'treadmill', 'manual', json.dumps(summary)))
                return dict(ride_id=cur.lastrowid, summary=summary, activity_type='treadmill')
