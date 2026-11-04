import asyncio
import contextlib
import json
import math
import os
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel, Field
from .devices import Daum, HeartRate
from .ftms import simulation_watts
from .training import TrainingProfile, PulseController, seed_templates, read_profile, resolve_plan
from .exports import migrate_exports, payload as export_payload, csv_export, tcx_export
from .power_settings import read_settings as read_power_settings, save_settings as save_power_settings
from . import __version__

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.getenv('BIKE_DB', str(ROOT / 'bike.db')))
POWER_CONFIG = Path(os.getenv('BIKE_POWER_CONFIG', '/var/lib/daum-studio/power-watch.json'))


class Step(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    seconds: int = Field(ge=10, le=7200)
    watts: int = Field(ge=25, le=400)


class Plan(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    steps: list[Step] = Field(min_length=1, max_length=100)


class UserProfile(BaseModel):
    name: str = Field(min_length=1, max_length=60, pattern=r".*\S.*")


class ProfileUpdate(TrainingProfile):
    expected_user_id: int | None = Field(default=None, ge=1)


class Power(BaseModel):
    watts: int = Field(ge=25, le=400)


class Start(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)
    plan_id: int | None = None
    training_mode: Literal['power', 'hr'] = 'power'
    intensity_percent: int = Field(default=100, ge=50, le=130)
    duration_minutes: Literal[35,45,60] = 35
    hr_target_low: int | None = Field(default=None, ge=50, le=210)
    hr_target_high: int | None = Field(default=None, ge=55, le=215)


class Mode(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)
    mode: Literal['demo', 'daum']


class Sensor(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)
    address: str = Field(min_length=1, max_length=150)


class ConnectionRequest(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)


class PowerSettings(BaseModel):
    enabled: bool = Field(strict=True)


class ZwiftControl(BaseModel):
    enabled: bool
    rider_kg: float = Field(default=85, ge=35, le=200)
    bike_kg: float = Field(default=10, ge=5, le=40)


@contextmanager
def database():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    with database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY, name TEXT, steps TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS rides (id INTEGER PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP, seconds REAL, distance REAL, energy REAL, mode TEXT)')
        if not db.execute('SELECT id FROM plans LIMIT 1').fetchone():
            seeds = [dict(name='Locker einrollen', steps=[dict(name='Warm-up', seconds=300, watts=60), dict(name='Grundlage', seconds=900, watts=110), dict(name='Ausrollen', seconds=300, watts=50)]),
                     dict(name='Kurze Intervalle', steps=[dict(name='Warm-up', seconds=300, watts=70)] + [dict(name=name, seconds=secs, watts=watts) for _ in range(5) for name, secs, watts in [('Belastung', 60, 180), ('Erholung', 120, 80)]] + [dict(name='Ausrollen', seconds=180, watts=50)])]
            for plan in seeds:
                db.execute('INSERT INTO plans (name, steps) VALUES (?, ?)', (plan['name'], json.dumps(plan['steps'])))
        seed_templates(db)
        migrate_exports(db)
        db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, profile TEXT NOT NULL)')
        if not db.execute('SELECT id FROM users LIMIT 1').fetchone():
            old = read_profile(db)
            cur = db.execute('INSERT INTO users (name,profile) VALUES (?,?)', ('Standard', old.model_dump_json()))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('active_user',?)", (str(cur.lastrowid),))
        if 'user_id' not in {r[1] for r in db.execute('PRAGMA table_info(rides)')}:
            db.execute('ALTER TABLE rides ADD COLUMN user_id INTEGER')
            db.execute('UPDATE rides SET user_id=(SELECT MIN(id) FROM users)')


class Engine:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.daum = Daum()
        self.hr = HeartRate()
        self.mode = 'demo'
        self.running = False
        self.paused = False
        self.target = 100
        self.elapsed = self.distance = self.energy = 0.0
        self.power = self.cadence = self.speed = 0
        self.steps = []
        self.plan_name = 'Freies Training'
        self.step_name = 'Freies Training'
        self.error = ''
        self.connected = False
        self.last_target = None
        self.history = []
        self.zwift = None
        self.control_owner = 'local'
        self.remote_mode = 'ERG'
        self.remote_target = 100
        self.rider_kg, self.bike_kg = 85, 10
        self.simulation = dict(wind=0, grade=0, crr=0.004, cw=0.51)
        self.user_id = None
        self.profile = TrainingProfile()
        self.training_mode = 'power'
        self.pulse = PulseController()
        self.step_index = 0
        self.step_remaining = 0
        self.samples = []
        self.calibrating = False
        self.started_at = None

    def snapshot(self):
        return dict(user_id=self.user_id, mode=self.mode, running=self.running, paused=self.paused, target=self.target,
                    elapsed=round(self.elapsed), distance=round(self.distance, 3), energy=round(self.energy),
                    power=self.power, cadence=self.cadence, speed=self.speed,
                    hr_fresh=self.hr.value() is not None and self.hr.age()<3, heart_rate=self.hr.value(), hr_connected=bool(self.hr.client and self.hr.client.is_connected),
                    plan_name=self.plan_name, step_name=self.step_name,
                    duration=sum(s['seconds'] for s in self.steps), connected=self.connected,
                    error=self.error, history=self.history[-90:],
                    zwift=self.zwift.status if self.zwift else 'Aus',
                    control_owner=self.control_owner,
                    zwift_detail=self.zwift.details() if self.zwift else None,
                    training_mode=self.training_mode, steps=self.steps, step_index=self.step_index,
                    step_remaining=round(self.step_remaining), samples=self.samples,
                    hr_target=self.pulse_zone(), pulse_status=self.pulse.note,
                    calibrating=self.calibrating,
                    hr_sample_age=round(self.hr.age(),1) if self.hr.updated else None)

    def pulse_zone(self):
        if self.training_mode != 'hr' or not self.steps:
            return None
        step=self.steps[min(self.step_index,len(self.steps)-1)]
        return dict(low=step.get('hr_low'),high=step.get('hr_high'),ceiling=self.profile.hr_ceiling)

    async def regulate_pulse(self, now):
        step=self.steps[self.step_index]
        self.target, action=self.pulse.update(self.target,self.hr.value(),self.hr.age(),
            step['hr_low'],step['hr_high'],self.profile.hr_ceiling,
            self.profile.hr_min_watts,self.profile.hr_max_watts,now,self.step_index,step['watts'])
        if action=='run' and self.cadence<30:
            self.target=25
            self.pulse.last_change=now
            self.pulse.settle_until=now+45
            self.pulse.note='Trittfrequenz niedrig – keine Lasterhöhung'
        if action in ('pause','stop'):
            self.error=self.pulse.note
            if action=='stop':
                await self.stop()
            else:
                self.paused=True
                if self.mode=='daum':
                    await self.daum.set_power(25)
                self.last_target=None
                self.power=self.cadence=self.speed=0
        return action

    def locally_locked(self):
        return bool(self.zwift and self.zwift.armed)

    def update_remote_target(self, dt):
        desired = self.remote_target if self.remote_mode == 'ERG' else simulation_watts(
            self.speed, self.cadence, self.simulation, self.rider_kg, self.bike_kg)
        if self.remote_mode == 'SIM':
            self.remote_target = desired
        delta = max(-25 * dt, min(25 * dt, desired - self.target))
        self.target = max(25, min(400, round(self.target + delta)))
        self.step_name = self.remote_mode

    async def remote_command(self, opcode, value):
        if opcode == 5:
            self.remote_target, self.remote_mode = value, 'ERG'
        elif opcode == 17:
            self.simulation, self.remote_mode = value, 'SIM'
        elif opcode == 1:
            await self.stop(keep_remote=True)
            self.elapsed = self.distance = self.energy = 0
            self.remote_target = self.target = 25
            self.remote_mode = 'ERG'
        elif opcode == 7:
            if self.mode == 'daum' and not self.connected:
                raise ConnectionError('Daum ist nicht verbunden')
            if self.running and not self.paused:
                return
            if not self.running:
                self.elapsed = self.distance = self.energy = 0
                self.history, self.steps = [], []
                self.samples = []
                self.started_at=datetime.now(timezone.utc).isoformat()
            self.training_mode = 'power'
            self.calibrating = False
            self.target = 25
            if self.mode == 'daum':
                await self.daum.set_power(25)
            self.last_target = None
            self.plan_name, self.step_name = 'Zwift', self.remote_mode
            self.running, self.paused = True, False
            self.error = ''
        elif opcode == 8:
            if value == 1:
                await self.stop(keep_remote=True)
            else:
                if self.mode == 'daum' and self.connected:
                    await self.daum.set_power(25)
                self.paused = True
                self.power = self.cadence = self.speed = 0
                self.last_target = None

    def select_step(self):
        remaining = self.elapsed
        for index, step in enumerate(self.steps):
            if remaining < step['seconds']:
                if self.training_mode != 'hr':
                    self.target = step['watts']
                self.step_name = step['name']
                self.step_index, self.step_remaining = index, step['seconds']-remaining
                return True
            remaining -= step['seconds']
        return not self.steps

    async def stop(self, save=True, keep_remote=False):
        was_running = self.running
        self.running = self.paused = False
        if not keep_remote and self.zwift:
            self.zwift.revoke()
        if self.mode == 'daum' and self.connected:
            try:
                await self.daum.set_power(25)
                await self.daum.release()
            except Exception as exc:
                self.error = f'Stopp nicht bestätigt – bitte am Cockpit stoppen: {exc}'
        if save and was_running and self.elapsed > 0:
            if not self.samples or self.samples[-1][0]<round(self.elapsed):
                self.samples.append(self.measurement())
            with database() as db:
                db.execute('INSERT INTO rides (seconds,distance,energy,mode,samples_json,plan_name,training_mode,started_at,user_id) VALUES (?,?,?,?,?,?,?,?,?)',
                           (self.elapsed,self.distance,self.energy,self.mode,json.dumps(self.samples),self.plan_name,self.training_mode,self.started_at,self.user_id))
        self.power = self.cadence = self.speed = 0
        self.last_target = None

    def measurement(self):
        return [round(self.elapsed),self.power,self.target,self.hr.value(),self.cadence,self.speed,round(self.distance,4),datetime.now(timezone.utc).isoformat()]

    async def loop(self):
        previous = time.monotonic()
        while True:
            await asyncio.sleep(1)
            now = time.monotonic()
            dt, previous = min(now - previous, 3), now
            async with self.lock:
                try:
                    if self.running and not self.paused:
                        # No progress while a pulse-control signal is stale.
                        if not (self.training_mode=='hr' and self.hr.age()>=3):
                            self.elapsed += dt
                        if self.control_owner == 'zwift':
                            # Smooth external changes to at most 25 W per real second.
                            self.update_remote_target(dt)
                        elif not self.select_step():
                            await self.stop()
                            continue
                        if self.training_mode=='hr':
                            action=await self.regulate_pulse(now)
                            if action in ('pause','stop'):
                                continue
                        if self.mode == 'demo':
                            self.power = max(0, round(self.target + math.sin(self.elapsed / 3) * 4))
                            self.cadence = round(78 + math.sin(self.elapsed / 7) * 5)
                            self.speed = round((self.power / 4) ** (1 / 3) * 8, 1)
                        else:
                            if self.target != self.last_target:
                                await self.daum.set_power(self.target)
                                self.last_target = self.target
                            data = await self.daum.command('X70')
                            from .devices import parse_training
                            for key, value in parse_training(data).items():
                                setattr(self, key, value)
                        self.distance += self.speed * dt / 3600
                        self.energy += self.power * dt / 1000
                        self.history.append(self.power)
                        self.history = self.history[-90:]
                        if not self.samples or self.elapsed-self.samples[-1][0]>=10:
                            self.samples.append(self.measurement())
                            # Profiles can be longer than one hour; keep a bounded trace.
                            if len(self.samples)>720:
                                self.samples=self.samples[::2]
                except Exception as exc:
                    self.error = f'Verbindung unterbrochen: {exc}'
                    await self.stop()
                    self.connected = False
                    await self.daum.close()
                if self.zwift:
                    try:
                        self.zwift.publish(self.snapshot())
                    except Exception:
                        self.zwift.status = 'Senderfehler · bitte neu starten'
                        if self.control_owner == 'zwift':
                            await self.stop()
                            self.error = 'Bluetooth-Senderfehler. Zwift-Steuerung beendet.'


engine = Engine()


@asynccontextmanager
async def lifespan(app):
    init_db()
    with database() as db:
        active = db.execute("SELECT value FROM settings WHERE key='active_user'").fetchone()
        user = db.execute('SELECT * FROM users WHERE id=?', (int(active[0]) if active else 0,)).fetchone()
        if user is None:
            user = db.execute('SELECT * FROM users ORDER BY id LIMIT 1').fetchone()
        engine.user_id = user['id']
        engine.profile = TrainingProfile.model_validate_json(user['profile'])
    task = asyncio.create_task(engine.loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await engine.stop(save=False)
    await engine.daum.close()
    await engine.hr.disconnect()
    if engine.zwift:
        await engine.zwift.stop()


app = FastAPI(title='DAUM Studio', version=__version__, lifespan=lifespan)


@app.get('/api/state')
async def state():
    return engine.snapshot()


@app.get('/api/plans')
async def plans():
    with database() as db:
        return [resolve_plan(r,engine.profile) for r in db.execute('SELECT * FROM plans')]


@app.get('/api/users')
async def users():
    with database() as db:
        return dict(active_user_id=engine.user_id, users=[dict(id=r['id'], name=r['name']) for r in db.execute('SELECT id,name FROM users ORDER BY id')])


@app.get('/api/session')
async def session():
    # Return values and their owner together, even while another client switches users.
    async with engine.lock:
        with database() as db:
            return dict(
                plans=[resolve_plan(r, engine.profile) for r in db.execute('SELECT * FROM plans')],
                rides=[dict(r) for r in db.execute('SELECT id,created,seconds,distance,energy,mode,plan_name,training_mode,started_at FROM rides WHERE user_id=? ORDER BY id DESC LIMIT 30', (engine.user_id,))],
                profile=engine.profile.model_dump(),
                users=[dict(r) for r in db.execute('SELECT id,name FROM users ORDER BY id')],
                active_user_id=engine.user_id,
            )


def require_user_change():
    if engine.running or engine.locally_locked():
        raise HTTPException(409, 'Benutzer nur bei gestopptem Training und gesperrter Zwift-Steuerung ändern')


def require_expected_user(expected_user_id: int | None):
    if expected_user_id is not None and expected_user_id != engine.user_id:
        raise HTTPException(409, 'Der aktive Benutzer wurde geändert. Bitte Benutzer und Trainingswerte erneut prüfen.')


@app.post('/api/users', status_code=201)
async def create_user(body: UserProfile):
    async with engine.lock:
        require_user_change()
        with database() as db:
            cur = db.execute('INSERT INTO users (name,profile) VALUES (?,?)', (body.name.strip(), TrainingProfile().model_dump_json()))
            return dict(id=cur.lastrowid, name=body.name.strip())


@app.post('/api/users/{user_id}/rename')
async def rename_user(user_id: int, body: UserProfile):
    async with engine.lock:
        require_user_change()
        with database() as db:
            if not db.execute('UPDATE users SET name=? WHERE id=?', (body.name.strip(), user_id)).rowcount:
                raise HTTPException(404, 'Benutzer nicht gefunden')
    return dict(id=user_id, name=body.name.strip())


@app.post('/api/users/{user_id}/activate')
async def activate_user(user_id: int):
    async with engine.lock:
        require_user_change()
        with database() as db:
            user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if user is None:
                raise HTTPException(404, 'Benutzer nicht gefunden')
            profile = TrainingProfile.model_validate_json(user['profile'])
            if user_id != engine.user_id:
                await engine.hr.disconnect()
            db.execute("INSERT OR REPLACE INTO settings VALUES ('active_user',?)", (str(user_id),))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('training_profile',?)", (profile.model_dump_json(),))
        engine.user_id, engine.profile = user_id, profile
        engine.steps, engine.samples, engine.history = [], [], []
        engine.elapsed = engine.distance = engine.energy = 0
        engine.target = 25
        engine.plan_name = engine.step_name = 'Freies Training'
        engine.calibrating = False
    return await users()


@app.get('/api/profile')
async def profile():
    return engine.profile.model_dump()


@app.get('/api/power-settings')
async def power_settings():
    return read_power_settings(POWER_CONFIG)


@app.post('/api/power-settings')
async def update_power_settings(body: PowerSettings):
    try:
        return save_power_settings(POWER_CONFIG, body.enabled)
    except (OSError, ValueError) as error:
        raise HTTPException(503, str(error))


@app.post('/api/profile')
async def save_profile(body: ProfileUpdate):
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        if engine.running or engine.locally_locked():
            raise HTTPException(409,'Persönliche Werte nur bei gestopptem Training ändern')
        values = TrainingProfile.model_validate(body.model_dump(exclude={'expected_user_id'}))
        with database() as db:
            db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('training_profile',?)",(values.model_dump_json(),))
            db.execute('UPDATE users SET profile=? WHERE id=?', (values.model_dump_json(), engine.user_id))
        engine.profile=values
    return values.model_dump()


@app.post('/api/plans', status_code=201)
async def save_plan(plan: Plan):
    with database() as db:
        cur = db.execute('INSERT INTO plans (name,steps) VALUES (?,?)', (plan.name, json.dumps([s.model_dump() for s in plan.steps])))
        return dict(id=cur.lastrowid)


@app.post('/api/power')
async def power(body: Power):
    async with engine.lock:
        if engine.locally_locked():
            raise HTTPException(409, 'Zwift-Steuerung ist freigegeben. Zuerst im Studio sperren.')
        if engine.steps and engine.running:
            raise HTTPException(409, 'Leistung wird vom Trainingsplan gesteuert')
        engine.target = body.watts
    return engine.snapshot()


@app.post('/api/start')
async def start(body: Start):
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        if engine.locally_locked():
            raise HTTPException(409, 'Zwift-Steuerung ist freigegeben. Lokaler Stopp bleibt möglich.')
        if engine.running:
            raise HTTPException(409, 'Training läuft bereits')
        if engine.mode == 'daum' and not engine.connected:
            raise HTTPException(409, 'Zuerst Daum verbinden')
        steps, name = [], 'Freies Training'
        calibrating=False
        if body.plan_id is not None:
            with database() as db:
                row = db.execute('SELECT * FROM plans WHERE id=?', (body.plan_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Plan nicht gefunden')
            plan=resolve_plan(row,engine.profile,body.intensity_percent)
            if plan['meta'].get('calibration'):
                plan=resolve_plan(row,engine.profile,100)
            steps, name = plan['steps'],plan['name']
            calibrating=bool(plan['meta'].get('calibration'))
        if body.training_mode=='hr':
            profile=engine.profile
            if not profile.hr_max or not profile.hr_ceiling:
                raise HTTPException(422,'Für Pulssteuerung zuerst persönliche HFmax und Pulsgrenze hinterlegen')
            if engine.hr.value() is None or engine.hr.age()>=3 or engine.hr.value()<30:
                raise HTTPException(409,'Pulsmodus braucht ein frisches Signal vom verbundenen Gurt')
            if engine.hr.value()>=profile.hr_ceiling:
                raise HTTPException(409,'Persönliche Pulsgrenze bereits erreicht')
            if not steps:
                lo=body.hr_target_low or round(profile.hr_max*.60)
                hi=body.hr_target_high or round(profile.hr_max*.70)
                if not 50<=lo<hi<profile.hr_ceiling:
                    raise HTTPException(422,'Pulsziel muss unter deiner Pulsgrenze liegen; Untergrenze kleiner als Obergrenze')
                warm_low=min(round(profile.hr_max*.50),lo-5)
                steps=[dict(name='Einrollen',seconds=300,watts=50,hr_low=warm_low,hr_high=lo),
                       dict(name='Cardio-Zielzone',seconds=(body.duration_minutes-10)*60,watts=75,hr_low=lo,hr_high=hi),
                       dict(name='Ausrollen',seconds=300,watts=40,hr_low=warm_low,hr_high=lo)]
                name=f'Puls-Cardio {body.duration_minutes}'
            elif any(not s.get('hr_low') or not s.get('hr_high') for s in steps):
                raise HTTPException(422,'Dieser Plan hat keine geeigneten Pulszonen')
        engine.training_mode=body.training_mode
        engine.calibrating=calibrating
        engine.steps, engine.plan_name = steps, name
        engine.elapsed = engine.distance = engine.energy = 0
        engine.history = []
        engine.samples = []
        engine.started_at=datetime.now(timezone.utc).isoformat()
        engine.error = ''
        engine.pulse.reset()
        engine.step_index=0
        if body.training_mode=='hr':
            engine.target=max(engine.profile.hr_min_watts,min(50,engine.profile.hr_max_watts,steps[0]['watts']))
        engine.select_step()
        engine.running, engine.paused = True, False
    return engine.snapshot()


@app.post('/api/calibration/comfortable')
async def calibration_comfortable():
    async with engine.lock:
        if not engine.running or engine.paused or not engine.calibrating or engine.training_mode!='power':
            raise HTTPException(409,'Zuerst die Orientierungsfahrt wattgeführt starten')
        if engine.mode!='daum' or not engine.connected:
            raise HTTPException(409,'Demo-Daten nicht als persönliche Belastung speichern')
        if not 1<=engine.step_index<=5 or engine.steps[engine.step_index]['seconds']-engine.step_remaining<60:
            raise HTTPException(409,'Erst mindestens 60 Sekunden einer Wattstufe beobachten; noch kein Wert gespeichert')
        if engine.cadence<30 or engine.power<10:
            raise HTTPException(409,'Dafür bitte gleichmäßig treten; noch kein Wert gespeichert')
        profile=engine.profile.model_copy(update={'comfortable_watts':engine.target})
        with database() as db:
            db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('training_profile',?)",(profile.model_dump_json(),))
            db.execute('UPDATE users SET profile=? WHERE id=?', (profile.model_dump_json(), engine.user_id))
        engine.profile=profile
    return engine.snapshot()


@app.post('/api/pause')
async def pause():
    async with engine.lock:
        if engine.locally_locked():
            raise HTTPException(409, 'Pause über Zwift bedienen oder lokal stoppen')
        if not engine.running:
            raise HTTPException(409, 'Kein Training aktiv')
        if engine.training_mode=='hr' and engine.paused:
            if engine.hr.value() is None or engine.hr.age()>=3:
                raise HTTPException(409,'Zum Fortsetzen braucht der Pulsmodus ein frisches Gurtsignal')
            if engine.hr.value()>=engine.profile.hr_ceiling:
                raise HTTPException(409,'Persönliche Pulsgrenze erreicht')
            engine.pulse.reset()
            engine.target=25
            engine.error=''
        engine.paused = not engine.paused
        if engine.mode == 'daum' and engine.paused:
            try:
                await engine.daum.set_power(25)
            except Exception as exc:
                await engine.stop()
                raise HTTPException(503, str(exc))
        engine.last_target = None
        engine.power = engine.cadence = engine.speed = 0
    return engine.snapshot()


@app.post('/api/stop')
async def stop():
    async with engine.lock:
        await engine.stop(save=engine.running)
    return engine.snapshot()


@app.post('/api/mode')
async def mode(body: Mode):
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        if engine.locally_locked():
            raise HTTPException(409, 'Zwift-Steuerung vor dem Moduswechsel sperren')
        if engine.running:
            raise HTTPException(409, 'Training vor dem Moduswechsel beenden')
        await engine.daum.close()
        engine.connected = False
        engine.mode, engine.error = body.mode, ''
        if body.mode == 'daum':
            try:
                await engine.daum.connect()
                engine.connected = True
            except Exception as exc:
                reason=str(exc) or 'Zeitüberschreitung – keine Antwort vom Daum'
                engine.error = f'Daum nicht erreichbar: {reason}'
                raise HTTPException(503, engine.error)
    return engine.snapshot()


@app.post('/api/connect/all')
async def connect_all(body: ConnectionRequest):
    # Connections can take several seconds. Keep the bike idle throughout the
    # operation rather than allowing a second client to start halfway through it.
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        if engine.running or engine.locally_locked():
            raise HTTPException(409, 'Verbindungen nur bei gestopptem Training und gesperrter Zwift-Steuerung herstellen')
        results, sensors = [], []
        if engine.mode == 'daum' and engine.connected:
            results.append(dict(device='daum', ok=True, message='Daum bereits verbunden'))
        else:
            engine.connected, engine.mode, engine.error = False, 'daum', ''
            try:
                await asyncio.wait_for(engine.daum.close(), 3)
                await asyncio.wait_for(engine.daum.connect(), 12)
                engine.connected = True
                results.append(dict(device='daum', ok=True, message='Daum verbunden'))
            except Exception as exc:
                reason = str(exc) or 'Zeitüberschreitung – keine Antwort vom Daum'
                engine.error = f'Daum nicht erreichbar: {reason}'
                results.append(dict(device='daum', ok=False, message=engine.error))
        if engine.hr.client and engine.hr.client.is_connected:
            results.append(dict(device='hr', ok=True, message='Pulssensor bereits verbunden'))
        else:
            try:
                sensors = await asyncio.wait_for(engine.hr.scan(), 10)
                if len(sensors) == 1:
                    await asyncio.wait_for(engine.hr.connect(sensors[0]['address']), 20)
                    results.append(dict(device='hr', ok=True, message='Pulssensor verbunden · warte auf frisches Signal'))
                elif sensors:
                    results.append(dict(device='hr', ok=False, message='Mehrere Pulssensoren gefunden – bitte deinen Sensor auswählen'))
                else:
                    results.append(dict(device='hr', ok=False, message='Kein Pulssensor gefunden. Gurt anlegen und Bluetooth aktivieren.'))
            except Exception as exc:
                results.append(dict(device='hr', ok=False, message=f'Pulssensor nicht verbunden: {str(exc) or "Zeitüberschreitung"}'))
        return dict(state=engine.snapshot(), sensors=sensors, results=results, needs_sensor_choice=len(sensors) > 1)


@app.get('/api/hr/scan')
async def scan():
    try:
        return await engine.hr.scan()
    except Exception as exc:
        raise HTTPException(503, f'Bluetooth-Suche fehlgeschlagen: {exc}')


@app.post('/api/hr/connect')
async def connect_hr(sensor: Sensor):
    async with engine.lock:
        require_expected_user(sensor.expected_user_id)
        if engine.running and not engine.paused:
            raise HTTPException(409, 'Zum Wechseln des Pulssensors Training zuerst pausieren')
        try:
            await asyncio.wait_for(engine.hr.connect(sensor.address), 20)
        except Exception as exc:
            raise HTTPException(503, f'Pulsgurt nicht verbunden: {str(exc) or "Zeitüberschreitung"}')
    return engine.snapshot()


@app.post('/api/hr/disconnect')
async def disconnect_hr(body: ConnectionRequest = ConnectionRequest()):
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        if engine.running and not engine.paused:
            raise HTTPException(409, 'Zum Trennen des Pulssensors Training zuerst pausieren')
        try:
            await asyncio.wait_for(engine.hr.disconnect(), 5)
        except Exception as exc:
            raise HTTPException(503, f'Pulssensor konnte nicht getrennt werden: {str(exc) or "Zeitüberschreitung"}')
    return engine.snapshot()


@app.post('/api/zwift/start')
async def zwift_start():
    from .zwift import ZwiftBridge
    async with engine.lock:
        if engine.zwift and engine.zwift.server:
            return engine.snapshot()
        engine.zwift = ZwiftBridge(engine)
        try:
            await asyncio.wait_for(engine.zwift.start(), 15)
        except Exception as exc:
            with contextlib.suppress(Exception):
                await engine.zwift.stop()
            engine.zwift.status = 'Fehler'
            raise HTTPException(503, f'BLE-Sender konnte nicht starten: {exc}')
    return engine.snapshot()


@app.post('/api/zwift/stop')
async def zwift_stop():
    async with engine.lock:
        if engine.control_owner == 'zwift':
            await engine.stop()
        if engine.zwift:
            await engine.zwift.stop()
    return engine.snapshot()


@app.post('/api/zwift/control')
async def zwift_control(body: ZwiftControl):
    async with engine.lock:
        if not engine.zwift or not engine.zwift.server:
            raise HTTPException(409, 'Zuerst Bluetooth-Sender starten')
        if body.enabled:
            if engine.running:
                raise HTTPException(409, 'Training vor der Freigabe beenden')
            if engine.mode == 'daum' and not engine.connected:
                raise HTTPException(409, 'Zuerst Daum verbinden oder Demo wählen')
            engine.rider_kg, engine.bike_kg = body.rider_kg, body.bike_kg
            engine.remote_target = 100
            engine.remote_mode = 'ERG'
            engine.zwift.armed = True
            engine.zwift.status = 'Sendet · Steuerung freigegeben'
        else:
            if engine.control_owner == 'zwift':
                await engine.stop()
            engine.zwift.revoke()
    return engine.snapshot()


@app.get('/api/rides')
async def rides():
    with database() as db:
        return [dict(r) for r in db.execute('SELECT id,created,seconds,distance,energy,mode,plan_name,training_mode,started_at FROM rides WHERE user_id=? ORDER BY id DESC LIMIT 30', (engine.user_id,))]


@app.post('/api/rides/{ride_id}/delete')
async def delete_ride(ride_id: int, body: ConnectionRequest):
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        with database() as db:
            deleted = db.execute('DELETE FROM rides WHERE id=? AND user_id=?', (ride_id, engine.user_id))
            if deleted.rowcount == 0:
                raise HTTPException(404, 'Fahrt nicht gefunden')
    return {'deleted': ride_id}


@app.get('/api/rides/{ride_id}/export/{format}')
async def export_ride(ride_id:int, format:Literal['tcx','csv','json']):
    with database() as db:
        row=db.execute('SELECT * FROM rides WHERE id=?',(ride_id,)).fetchone()
    if not row:
        raise HTTPException(404,'Fahrt nicht gefunden')
    data=export_payload(dict(row))
    prefix='DEMO-' if data['simulated'] else ''
    filename=f'{prefix}DAUM-Studio-{ride_id}.{format}'
    if format=='tcx':
        content,media=tcx_export(data),'application/vnd.garmin.tcx+xml'
    elif format=='csv':
        content,media=csv_export(data),'text/csv'
    else:
        content,media=json.dumps(data,ensure_ascii=False,indent=2),'application/json'
    return Response(content=content,media_type=media,headers={'Content-Disposition':f'attachment; filename="{filename}"','Cache-Control':'no-store'})


@app.websocket('/ws')
async def websocket(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(engine.snapshot())
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass


dist = ROOT / 'frontend' / 'dist'
if dist.exists():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
