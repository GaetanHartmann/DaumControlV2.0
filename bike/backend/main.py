import asyncio
import contextlib
import json
import math
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from .devices import Daum, HeartRate
from .ftms import simulation_watts
from .training import TrainingProfile, PulseController, seed_templates, read_profile, resolve_plan
from .exports import migrate_exports, payload as export_payload, csv_export, tcx_export
from .power_settings import read_settings as read_power_settings, save_settings as save_power_settings
from . import __version__
from .connectors import DaumConnector, measurement
from .metrics import SessionMetrics, normalize_summary

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.getenv('BIKE_DB', str(ROOT / 'bike.db')))
POWER_CONFIG = Path(os.getenv('BIKE_POWER_CONFIG', '/var/lib/daum-studio/power-watch.json'))
PRODUCT_NAME = os.getenv('FITNESS_PRODUCT_NAME', 'Fitness-Cockpit')
# Inherit the existing server handler so connection phases reach the Pi journal.
logger = logging.getLogger('uvicorn.error.fitness_cockpit')


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
    watts: int = Field(ge=0, le=10000, strict=True)
    source: Literal['manual_slider', 'manual_button'] = 'manual_button'
    expected_user_id: int | None = Field(default=None, ge=1)
    expected_session_id: str | None = Field(default=None, min_length=1, max_length=64)


class ReturnToPlan(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)
    expected_session_id: str | None = Field(default=None, min_length=1, max_length=64)


class Start(BaseModel):
    expected_user_id: int | None = Field(default=None, ge=1)
    plan_id: int | None = None
    validation_token: str | None = Field(default=None, max_length=128)
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
    devices: list[Literal['daum', 'hr', 'zwift']] = Field(default_factory=lambda: ['daum', 'hr'], max_length=3)


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
        columns = {r[1] for r in db.execute('PRAGMA table_info(rides)')}
        for name, definition in [('finish_reason', 'TEXT'), ('summary_json', "TEXT NOT NULL DEFAULT '{}'"),
                                 ('activity_type', "TEXT NOT NULL DEFAULT 'indoor_cycling'"),
                                 ('control_events_json', "TEXT NOT NULL DEFAULT '[]'")]:
            if name not in columns:
                db.execute(f'ALTER TABLE rides ADD COLUMN {name} {definition}')
        from .cockpit import migrate
        migrate(db)
        from .catalog import migrate as migrate_catalog
        migrate_catalog(db)
        from .routes import migrate as migrate_routes
        migrate_routes(db)


def ride_record(row):
    record = dict(row)
    record['summary'] = normalize_summary(json.loads(record.pop('summary_json', '{}') or '{}'), record.get('mode'))
    if record.get('mode') == 'daum' and not record['summary'].get('power_measurement_verified'):
        record['reported_unverified_energy_kj'] = record.get('energy')
        record['energy'] = None
    if 'control_events_json' in record:
        record['control_events'] = json.loads(record.pop('control_events_json') or '[]')
        if record.get('mode') == 'daum' and not record['summary'].get('power_measurement_verified'):
            for event in record['control_events']:
                if event.get('measured_watts') is not None:
                    event['reported_unverified_power_watts'] = event['measured_watts']
                    event['measured_watts'] = None
                if event.get('applied_target_watts') is not None and event.get('target_confirmation_detail') != 'echoed_value':
                    event['reported_unverified_applied_target_watts'] = event['applied_target_watts']
                    event['applied_target_watts'] = None
    return record


def visible_plans(db):
    values = []
    rows = db.execute('SELECT p.* FROM plans p LEFT JOIN plan_catalog c ON c.plan_id=p.id WHERE c.owner_user_id IS NULL OR c.owner_user_id=?', (engine.user_id,))
    for row in rows:
        try:
            values.append(resolve_plan(row, engine.profile))
        except (ValueError, TypeError, KeyError, OverflowError):
            values.append(dict(id=row['id'], name=row['name'], steps=[], meta={}, valid=False,
                               validation_error='Gespeicherte Segmente ungültig; im Katalog prüfen'))
    return values


class Engine:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.hr_lock = asyncio.Lock()
        self.daum = Daum()
        self.connector = DaumConnector(self.daum)
        self.hr = HeartRate()
        self.mode = 'demo'
        self.running = False
        self.paused = False
        self.target = 100
        self.elapsed = self.distance = self.energy = 0.0
        self.power = self.cadence = self.speed = 0
        self.reported_power = None
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
        self.metrics = SessionMetrics()
        self.completion = None
        self.pending_save = None
        self.last_measurement_at = None
        self.available_metrics = set()
        self.connections = {}
        self.connection_events = []
        self.manual_override = None
        self.request_source = 'plan'
        self.applied_target_watts = None
        self.target_confirmation_source = None
        self.target_confirmation_detail = None
        self.target_command_status = 'idle'
        self.target_error = ''
        self.control_revision = 0
        self.last_command_at = None
        self.control_events = []
        self.control_events_trimmed = 0
        self.manual_adjustments = 0
        self.pause_count = 0
        self.pause_seconds = 0.0
        self.pause_started_at = None
        self.session_id = None
        self.workout_id = None
        self.stopping = False
        self.session_state = 'idle'
        self.command_in_flight = False
        self.stop_requested = False

    def reset_recording(self):
        if self.pending_save is not None:
            raise RuntimeError('Trainingsdaten noch nicht gespeichert. Bitte erneut stoppen/speichern.')
        self.metrics = SessionMetrics()
        self.completion = None
        self.last_measurement_at = None
        self.available_metrics = set()
        self.manual_override = None
        self.applied_target_watts = None
        self.target_confirmation_source = None
        self.target_confirmation_detail = None
        self.reported_power = None
        self.target_command_status = 'idle'
        self.target_error = ''
        self.control_revision += 1
        self.last_target = None
        self.last_command_at = None
        self.control_events = []
        self.control_events_trimmed = 0
        self.manual_adjustments = self.pause_count = 0
        self.pause_seconds = 0.0
        self.pause_started_at = None
        self.session_id = uuid.uuid4().hex
        self.workout_id = None
        self.session_state = 'idle'
        self.stop_requested = False

    def power_limits(self, training_mode=None):
        caps = self.connector.capabilities
        low = caps.get('power_min_watts', 25)
        high = caps.get('power_max_watts', 400)
        configured_low = getattr(self.profile, 'power_min_watts', None)
        configured_high = getattr(self.profile, 'power_max_watts', None)
        low = max(low, configured_low) if configured_low is not None else low
        high = min(high, configured_high) if configured_high is not None else high
        if (self.training_mode if training_mode is None else training_mode) == 'hr':
            low, high = max(low, self.profile.hr_min_watts), min(high, self.profile.hr_max_watts)
        step = caps.get('power_step_watts', 5)
        return dict(minimum=low, maximum=high, step=step, min_watts=low, max_watts=high, step_watts=step)

    def safe_power(self):
        # A safe pause/stop uses the device minimum, even when the configured
        # training minimum is higher. A read-only adapter receives no write.
        return self.connector.capabilities.get('power_min_watts', 25)

    def planned_power(self):
        remaining = self.elapsed
        for step in self.steps:
            if remaining < step['seconds']:
                return step['watts']
            remaining -= step['seconds']
        return self.steps[-1]['watts'] if self.steps else None

    def control_mode(self):
        if self.control_owner == 'zwift':
            return 'remote'
        if self.manual_override is not None or (not self.steps and self.training_mode != 'hr'):
            return 'manual_override'
        return 'hr' if self.training_mode == 'hr' else 'plan'

    def control_event(self, source, event='requested', **details):
        value = dict(timestamp=datetime.now(timezone.utc).isoformat(),
                     elapsed_seconds=round(self.elapsed, 3), source=source, event=event,
                     requested_target_watts=self.target,
                     applied_target_watts=self.applied_target_watts,
                     target_confirmation_source=self.target_confirmation_source,
                     target_confirmation_detail=self.target_confirmation_detail,
                     measured_watts=self.measurements()['power']['value'],
                     command_status=self.target_command_status, **details)
        self.control_events.append(value)
        if len(self.control_events) > 2000:
            self.control_events_trimmed += len(self.control_events) - 2000
            self.control_events = self.control_events[-2000:]
        logger.info('target_control %s', json.dumps(value, ensure_ascii=False))

    def request_target(self, watts, source='plan', manual=False):
        if manual:
            self.manual_override = (watts - self.planned_power() if self.running and self.steps and self.training_mode == 'power' else watts)
            self.manual_adjustments += 1
        changed = self.target != watts or manual or source == 'return_to_plan'
        self.target = watts
        self.request_source = source
        if changed:
            self.control_revision += 1
            self.target_error = ''
            self.target_command_status = 'paused' if self.paused else 'pending' if self.running else 'idle'
            if self.running and not self.paused and not self.command_in_flight and self.last_target == watts:
                if self.mode == 'demo':
                    self.target_command_status = 'simulated'
                elif self.applied_target_watts == watts and self.target_confirmation_source:
                    self.target_command_status = 'applied'
                elif self.applied_target_watts is not None and self.target_confirmation_source:
                    self.target_command_status = 'adjusted'
            self.control_event(source)

    def clear_override(self, source='safety'):
        self.manual_override = None
        self.control_revision += 1
        self.request_source = source

    def mark_paused(self, source='pause/resume'):
        if not self.paused:
            self.pause_started_at = time.monotonic()
            self.pause_count += 1
        self.paused = True
        self.session_state = 'paused'
        self.target_command_status = 'paused'
        self.control_event(source, 'paused')

    def mark_resumed(self):
        if self.pause_started_at is not None:
            self.pause_seconds += max(0, time.monotonic() - self.pause_started_at)
        self.pause_started_at = None
        self.paused = False
        self.session_state = 'running'
        self.target_command_status = 'pending'
        self.last_target = None
        self.control_event('pause/resume', 'resumed')

    async def flush_target(self, now=None, force=False):
        """One latest-value slot; no queue of obsolete slider commands."""
        if not self.running or self.paused or self.stopping:
            return False
        now = time.monotonic() if now is None else now
        if self.last_target == self.target:
            if self.mode == 'demo':
                self.target_command_status = 'simulated'
            elif not self.command_in_flight and self.applied_target_watts == self.target and self.target_confirmation_source:
                self.target_command_status = 'applied'
            elif not self.command_in_flight and self.applied_target_watts is not None and self.target_confirmation_source:
                self.target_command_status = 'adjusted'
            return False
        if not force and self.last_command_at is not None and now - self.last_command_at < .35:
            return False
        desired, revision, source = self.target, self.control_revision, self.request_source
        limits = self.power_limits()
        if not limits['minimum'] <= desired <= limits['maximum'] and not (source == 'safety' and desired == self.safe_power()):
            self.target_error = 'Angeforderte Leistung liegt außerhalb der Geräte-/Nutzergrenzen'
            self.target_command_status = 'error'
            self.control_event(source, 'rejected', error=self.target_error)
            raise ValueError(self.target_error)
        if self.mode == 'demo':
            self.last_target = desired
            self.last_command_at = now
            self.applied_target_watts = None
            self.target_confirmation_source = None
            self.target_confirmation_detail = None
            self.target_command_status = 'simulated'
            self.control_event(source, 'simulated', command_target_watts=desired)
            return True
        await self.apply_power(desired, source=source, revision=revision)
        return True

    async def apply_power(self, watts, source='safety', revision=None):
        if 'power' not in self.connector.capabilities.get('control', []):
            self.applied_target_watts = None
            self.target_confirmation_source = None
            self.target_confirmation_detail = None
            self.target_command_status = 'unsupported'
            self.last_target = watts
            self.control_event(source, 'unsupported', command_target_watts=watts)
            return False
        self.command_in_flight = True
        if isinstance(self.connector, DaumConnector):
            self.connector.request_guard = (None if source in ('safety', 'pause/resume') else
                                           lambda: self.running and not self.stopping and not self.stop_requested and self.target == watts)
        try:
            result = await self.connector.set_power(watts)
        except Exception as exc:
            self.applied_target_watts = None
            self.target_confirmation_source = None
            self.target_confirmation_detail = None
            self.target_command_status = 'error'
            self.target_error = str(exc) or 'Zeitüberschreitung'
            self.control_event(source, 'error', command_target_watts=watts, error=self.target_error)
            raise
        finally:
            self.command_in_flight = False
            if isinstance(self.connector, DaumConnector):
                self.connector.request_guard = None
        if isinstance(result, dict) and result.get('superseded'):
            self.target_command_status = 'paused' if self.paused else 'pending'
            self.last_command_at = time.monotonic()
            self.control_event(source, 'superseded', command_target_watts=watts)
            return False
        accepted = result.get('watts') if isinstance(result, dict) else None
        confirmed = (isinstance(result, dict) and result.get('confirmed') is True and
                     type(accepted) in (float, int) and math.isfinite(accepted) and
                     bool(result.get('source')))
        self.applied_target_watts = accepted if confirmed else None
        self.target_confirmation_source = result.get('source') if confirmed else None
        self.target_confirmation_detail = result.get('detail') if confirmed else None
        self.last_command_at = time.monotonic()
        self.last_target = watts
        self.target_error = ''
        self.target_command_status = ('paused' if self.paused else
                                      'pending' if self.target != watts else
                                      'unconfirmed' if not confirmed else
                                      'applied' if accepted == self.target else 'adjusted')
        self.control_event(source, 'confirmed' if confirmed else 'unconfirmed', command_target_watts=watts)
        if confirmed:
            limits = self.power_limits()
            if source not in ('safety', 'pause/resume') and not limits['minimum'] <= accepted <= limits['maximum']:
                self.target_command_status = 'error'
                self.target_error = 'Gerät bestätigt eine Leistung außerhalb der Nutzergrenzen'
                self.control_event('safety', 'rejected', command_target_watts=watts, error=self.target_error)
                raise ValueError(self.target_error)
            if source in ('safety', 'pause/resume') and accepted != watts:
                self.target_command_status = 'error'
                self.target_error = 'Gerät bestätigt den angeforderten sicheren Sollwert nicht exakt'
                self.control_event('safety', 'rejected', command_target_watts=watts, error=self.target_error)
                raise ValueError(self.target_error)
        return confirmed

    async def release_device(self):
        if 'release' in self.connector.capabilities.get('control', []):
            await self.connector.release()

    def connection_event(self, device, phase, status, message='', **details):
        event = dict(device=device, phase=phase, status=status, message=message,
                     timestamp=datetime.now(timezone.utc).isoformat(), **details)
        self.connections[device] = event
        self.connection_events = (self.connection_events + [event])[-60:]
        logger.info('device_connection %s', json.dumps(event, ensure_ascii=False))

    def measurements(self):
        fresh = bool(self.running and not self.paused and self.last_measurement_at is not None
                     and time.monotonic() - self.last_measurement_at < 4)
        source = 'demo' if self.mode == 'demo' else getattr(self.connector, 'device_id', 'device')
        power_quality = ('simulated' if self.mode == 'demo' else
                         self.connector.capabilities.get('measurement_quality', {}).get('power', 'unverified'))
        power_verified = self.mode == 'demo' or power_quality == 'verified_measured'
        hr = self.hr.value()
        return dict(
            power=measurement(self.power, 'W', source, fresh and power_verified and 'power' in self.available_metrics,
                              quality=power_quality),
            reported_power=measurement(self.reported_power, 'W', 'daum_x70_field_6',
                                       fresh and 'reported_power' in self.available_metrics,
                                       quality='device_reported_unverified'),
            cadence=measurement(self.cadence, 'rpm', source, fresh and 'cadence' in self.available_metrics),
            speed=measurement(self.speed, 'km/h', source, fresh and 'speed' in self.available_metrics, quality='simulated' if self.mode=='demo' else self.connector.capabilities.get('speed_quality')),
            heart_rate=measurement(hr, 'bpm', 'ble', hr is not None and hr > 0 and self.hr.age() < 3,
                                   stale=hr is not None and self.hr.age() >= 3),
            energy=measurement(self.energy, 'kJ', 'integrated_power', power_verified and bool(self.metrics.coverage['power_watts'])),
            calories=measurement(None, 'kcal', None, False))

    def snapshot(self):
        next_step = self.steps[self.step_index + 1] if self.steps and self.step_index + 1 < len(self.steps) else None
        measured = self.measurements()
        return dict(user_id=self.user_id, mode=self.mode, running=self.running, paused=self.paused, target=self.target,
                    elapsed=round(self.elapsed), distance=round(self.distance, 3),
                    energy=round(self.energy) if measured['energy']['available'] else None,
                    power=self.power, cadence=self.cadence, speed=self.speed,
                    hr_fresh=self.hr.value() is not None and self.hr.value()>0 and self.hr.age()<3, heart_rate=self.hr.value(), hr_connected=bool(self.hr.client and self.hr.client.is_connected), hr_reconnecting=bool(self.hr.reconnect_task and not self.hr.reconnect_task.done()),
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
                    hr_sample_age=round(self.hr.age(),1) if self.hr.updated else None,
                    measurements=measured, capabilities=self.connector.capabilities,
                    speed_measurement_note=self.connector.capabilities.get('speed_measurement_note') if self.mode!='demo' else None, completion=self.completion, pending_save=self.pending_save is not None, connections=self.connections,
                    connection_events=self.connection_events,
                    session_id=self.session_id, workout_id=self.workout_id, session_state=self.session_state,
                    control_mode=self.control_mode(), planned_target_watts=self.planned_power(), power_offset_watts=self.manual_override if self.running and self.steps and self.training_mode == 'power' else None,
                    requested_target_watts=self.target, applied_target_watts=self.applied_target_watts,
                    measured_watts=measured['power']['value'], power_limits=self.power_limits(), next_step=next_step,
                    target_command_status=self.target_command_status,
                    target_confirmation_source=self.target_confirmation_source, target_error=self.target_error,
                    target_confirmation_detail=self.target_confirmation_detail,
                    power_measurement_note='' if self.mode == 'demo' else self.connector.capabilities.get('power_measurement_note', ''),
                    control_events=self.control_events[-200:])

    def pulse_zone(self):
        if self.training_mode != 'hr' or not self.steps:
            return None
        step=self.steps[min(self.step_index,len(self.steps)-1)]
        return dict(low=step.get('hr_low'),high=step.get('hr_high'),ceiling=self.profile.hr_ceiling)

    async def regulate_pulse(self, now):
        step=self.steps[self.step_index]
        prior_target = self.target
        limits = self.power_limits()
        self.target, action=self.pulse.update(self.target,self.hr.value(),self.hr.age(),
            step['hr_low'],step['hr_high'],self.profile.hr_ceiling,
            limits['minimum'],limits['maximum'],now,self.step_index,step['watts'])
        if self.manual_override is not None and action == 'run' and self.hr.value() <= step['hr_high'] and self.cadence >= 30:
            self.target = self.manual_override
            self.pulse.note = 'Manuell angepasst · Pulsgrenze bleibt aktiv'
        elif self.manual_override is not None:
            self.clear_override('safety')
            self.control_event('safety', 'override_cleared', reason=self.pulse.note)
        if action=='run' and self.cadence<30:
            self.target=self.safe_power()
            self.pulse.last_change=now
            self.pulse.settle_until=now+45
            self.pulse.note='Trittfrequenz niedrig – keine Lasterhöhung'
        if self.target != prior_target:
            self.control_revision += 1
            self.request_source = 'safety' if action != 'run' or self.cadence < 30 else 'plan'
            self.target_command_status = 'pending'
            self.control_event(self.request_source, reason=self.pulse.note)
        # A stale signal requires explicit resume once it returns; no hidden
        # automatic resumption after a BLE reconnect/notification interruption.
        if action == 'wait':
            action = 'pause'
        if action in ('pause','stop'):
            self.error=self.pulse.note
            if action=='stop':
                await self.stop(reason='safety')
            else:
                self.mark_paused('safety')
                if self.mode=='daum':
                    await self.apply_power(self.safe_power(), source='safety')
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
        limits = self.power_limits(training_mode='power')
        desired = max(limits['minimum'], min(limits['maximum'], round(self.target + delta)))
        self.request_target(desired, 'remote')
        self.step_name = self.remote_mode

    async def remote_command(self, opcode, value):
        if opcode == 5:
            self.remote_target, self.remote_mode = value, 'ERG'
        elif opcode == 17:
            self.simulation, self.remote_mode = value, 'SIM'
        elif opcode == 1:
            await self.stop(keep_remote=True)
            if self.pending_save is not None:
                raise RuntimeError('Trainingsdaten konnten nicht gespeichert werden')
            self.elapsed = self.distance = self.energy = 0
            self.history, self.samples, self.steps = [], [], []
            self.reset_recording()
            self.remote_target = self.target = 25
            self.remote_mode = 'ERG'
        elif opcode == 7:
            if self.pending_save is not None:
                raise RuntimeError('Zuerst ungespeichertes Training erneut speichern')
            if self.mode == 'daum' and not self.connected:
                raise ConnectionError('Daum ist nicht verbunden')
            if self.running and not self.paused:
                return
            if not self.running:
                self.elapsed = self.distance = self.energy = 0
                self.history, self.steps = [], []
                self.samples = []
                self.reset_recording()
                self.started_at=datetime.now(timezone.utc).isoformat()
            self.training_mode = 'power'
            self.calibrating = False
            self.target = 25
            if self.mode == 'daum':
                await self.apply_power(25)
            self.last_target = None
            self.plan_name, self.step_name = 'Zwift', self.remote_mode
            self.running, self.paused = True, False
            self.session_state = 'running'
            self.error = ''
        elif opcode == 8:
            if value == 1:
                await self.stop(keep_remote=True)
            else:
                if self.mode == 'daum' and self.connected:
                    await self.apply_power(25)
                self.mark_paused()
                self.power = self.cadence = self.speed = 0
                self.last_target = None

    def select_step(self):
        remaining = self.elapsed
        for index, step in enumerate(self.steps):
            if remaining < step['seconds']:
                if self.training_mode != 'hr':
                    limits = self.power_limits()
                    adjusted = step['watts'] + (self.manual_override or 0)
                    self.request_target(max(limits['minimum'], min(limits['maximum'], adjusted)), 'plan' if self.manual_override is None else 'manual_offset')
                self.step_name = step['name']
                self.step_index, self.step_remaining = index, step['seconds']-remaining
                return True
            remaining -= step['seconds']
        return not self.steps

    async def stop(self, save=True, keep_remote=False, reason='manual'):
        was_running, was_paused = self.running, self.paused
        if was_paused:
            self.available_metrics = set()
            self.last_measurement_at = None
        if save and was_running and self.elapsed > 0:
            if not self.samples or self.samples[-1][0] < round(self.elapsed):
                self.samples.append(self.measurement())
        if self.pause_started_at is not None:
            self.pause_seconds += max(0, time.monotonic() - self.pause_started_at)
            self.pause_started_at = None
        self.running = self.paused = False
        self.stopping = True
        failed_target_error = self.target_error
        self.clear_override('safety')
        self.target = self.safe_power()
        if not keep_remote and self.zwift:
            self.zwift.revoke()
        if self.mode == 'daum' and self.connected:
            try:
                await self.apply_power(self.safe_power(), source='safety')
                await self.release_device()
            except Exception as exc:
                self.error = f'Stopp nicht bestätigt – bitte am Cockpit stoppen: {exc}'
                reason = 'error'
        if failed_target_error:
            self.target_error = failed_target_error
        self.session_state = 'completed' if reason == 'completed' else 'error' if reason in ('error', 'safety') else 'stopped'
        self.target_command_status = 'error' if self.target_error else 'idle'
        if was_running:
            self.control_event('safety' if reason in ('error', 'safety') else 'pause/resume', 'ended', finish_reason=reason)
        if save and was_running and self.elapsed > 0:
            summary = self.metrics.summary(self.elapsed, self.mode == 'demo', getattr(self.profile, 'weight_kg', None),
                                           getattr(self.connector, 'device_id', 'device'),
                                           measurement_quality={'power_watts':self.connector.capabilities.get('measurement_quality', {}).get('power', 'unverified')} if self.mode != 'demo' else None)
            summary = normalize_summary(summary, self.mode)
            summary.update(speed_measurement_note=self.connector.capabilities.get('speed_measurement_note') if self.mode!='demo' else None, plan_steps=[dict(step) for step in self.steps],
                           manual_adjustments=self.manual_adjustments, pause_count=self.pause_count,
                           pause_seconds=round(self.pause_seconds, 3), control_events_trimmed=self.control_events_trimmed,
                           session_id=self.session_id)
            self.pending_save = dict(
                values=(self.elapsed,self.distance,summary['mechanical_energy_kj'],self.mode,json.dumps(self.samples),self.plan_name,
                        self.training_mode,self.started_at,self.user_id,reason,json.dumps(summary),
                        self.connector.capabilities.get('activity_type', 'indoor_cycling'),json.dumps(self.control_events)),
                user_id=self.user_id, reason=reason, summary=summary,
                plan_name=self.plan_name, simulated=self.mode == 'demo')
        if save and self.pending_save is not None:
            pending = self.pending_save
            try:
                with database() as db:
                    cur = db.execute('INSERT INTO rides (seconds,distance,energy,mode,samples_json,plan_name,training_mode,started_at,user_id,finish_reason,summary_json,activity_type,control_events_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                     pending['values'])
                self.completion = dict(ride_id=cur.lastrowid,
                                       **{key: pending[key] for key in ('user_id', 'reason', 'summary', 'plan_name', 'simulated')})
                self.pending_save = None
                self.session_state = 'completed' if pending['reason'] == 'completed' else 'error' if pending['reason'] in ('error', 'safety') else 'stopped'
                if self.error.startswith('Training gestoppt, Speichern fehlgeschlagen.'):
                    self.error = ''
            except (sqlite3.Error, OSError) as exc:
                self.error = f'Training gestoppt, Speichern fehlgeschlagen. Bitte erneut stoppen/speichern: {exc}'
                logger.exception('Training save failed; data retained in memory for retry')
        self.power = self.cadence = self.speed = 0
        self.last_target = None
        self.stopping = False
        self.stop_requested = False

    def measurement(self):
        return [round(self.elapsed), self.power if 'power' in self.available_metrics else None, self.target,
                self.hr.value() if self.hr.age() < 3 and self.hr.value() and self.hr.value() > 0 else None,
                self.cadence if 'cadence' in self.available_metrics else None,
                self.speed if 'speed' in self.available_metrics else None,
                round(self.distance,4) if 'speed' in self.available_metrics else None,
                datetime.now(timezone.utc).isoformat(), self.planned_power(), self.applied_target_watts,
                self.target_command_status, self.request_source,
                self.reported_power if 'reported_power' in self.available_metrics else None]

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
                        active_dt = 0 if self.training_mode=='hr' and self.hr.age()>=3 else dt
                        total = sum(step['seconds'] for step in self.steps)
                        if total and self.control_owner != 'zwift':
                            active_dt = min(active_dt, max(0, total - self.elapsed))
                        self.elapsed += active_dt
                        completed = bool(total and self.control_owner != 'zwift' and self.elapsed >= total)
                        if self.control_owner == 'zwift':
                            # Smooth external changes to at most 25 W per real second.
                            self.update_remote_target(dt)
                        elif not completed:
                            self.select_step()
                        if self.training_mode=='hr':
                            action=await self.regulate_pulse(now)
                            if action in ('pause','stop'):
                                continue
                        if self.control_owner != 'zwift' and self.training_mode != 'hr' and self.profile.hr_ceiling and self.hr.age() < 3 and self.hr.value() is not None and self.hr.value() >= self.profile.hr_ceiling:
                            self.error = 'Persönliche Pulsgrenze erreicht'
                            await self.stop(reason='safety')
                            continue
                        await self.flush_target(now)
                        if self.stop_requested:
                            self.available_metrics = set()
                            self.last_measurement_at = None
                            continue
                        if self.mode == 'demo':
                            self.available_metrics = {'power', 'cadence', 'speed'}
                            self.power = max(0, round(self.target + math.sin(self.elapsed / 3) * 4))
                            self.cadence = round(78 + math.sin(self.elapsed / 7) * 5)
                            self.speed = round((self.power / 4) ** (1 / 3) * 8, 1)
                        else:
                            live = await self.connector.read()
                            if self.connector.capabilities.get('measurement_quality', {}).get('power') != 'verified_measured':
                                if live.get('power') is not None and getattr(self.connector, 'device_id', None) == 'daum':
                                    live.setdefault('reported_power', live['power'])
                                live['power'] = None
                            self.available_metrics = {key for key, value in live.items() if value is not None}
                            for key, value in live.items():
                                setattr(self, key, value)
                        self.last_measurement_at = time.monotonic()
                        if 'speed' in self.available_metrics:
                            self.distance += self.speed * active_dt / 3600
                        if 'power' in self.available_metrics:
                            self.energy += self.power * active_dt / 1000
                        self.metrics.add(active_dt, self.power if 'power' in self.available_metrics else None,
                                         self.hr.value() if self.hr.age() < 3 else None,
                                         self.cadence if 'cadence' in self.available_metrics else None)
                        self.history.append(self.power if 'power' in self.available_metrics else None)
                        self.history = self.history[-90:]
                        if not self.samples or self.elapsed-self.samples[-1][0]>=10:
                            self.samples.append(self.measurement())
                            # Profiles can be longer than one hour; keep a bounded trace.
                            if len(self.samples)>720:
                                self.samples=self.samples[::2]
                        if completed:
                            await self.stop(reason='completed')
                except Exception as exc:
                    self.error = f'Verbindung unterbrochen: {exc}'
                    # A failed read does not produce an endpoint sample merely
                    # because the previous poll still fits the freshness window.
                    self.available_metrics = set()
                    self.last_measurement_at = None
                    await self.stop(reason='error')
                    self.connected = False
                    self.applied_target_watts = None
                    self.target_confirmation_source = None
                    self.target_confirmation_detail = None
                    await self.connector.close()
                if self.zwift:
                    try:
                        self.zwift.publish(self.snapshot())
                    except Exception:
                        self.zwift.status = 'Senderfehler · bitte neu starten'
                        if self.control_owner == 'zwift':
                            await self.stop(reason='error')
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
    await engine.connector.close()
    await engine.hr.disconnect()
    if engine.zwift:
        await engine.zwift.stop()


app = FastAPI(title=PRODUCT_NAME, version=__version__, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    # Do not echo untrusted NaN/Infinity or arbitrary original JSON into the
    # response; non-finite error inputs otherwise fail JSON serialization.
    issues = ['.'.join(map(str, item['loc'])) + ': ' + item['msg'] for item in error.errors()]
    return JSONResponse(status_code=422, content={'detail':'Eingaben prüfen: ' + '; '.join(issues)})


@app.middleware('http')
async def revalidate_entry_page(request, call_next):
    response = await call_next(request)
    if request.url.path in ('/', '/index.html'):
        response.headers['Cache-Control'] = 'no-cache'
    return response


@app.get('/api/config')
async def config():
    return dict(product_name=PRODUCT_NAME, version=__version__)


@app.get('/api/state')
async def state():
    return engine.snapshot()


@app.get('/api/plans')
async def plans():
    with database() as db:
        return visible_plans(db)


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
                plans=visible_plans(db),
                rides=[ride_record(r) for r in db.execute('SELECT id,created,seconds,distance,energy,mode,plan_name,training_mode,started_at,finish_reason,summary_json,activity_type,control_events_json FROM rides WHERE user_id=? ORDER BY id DESC LIMIT 30', (engine.user_id,))],
                profile=engine.profile.model_dump(),
                users=[dict(r) for r in db.execute('SELECT id,name FROM users ORDER BY id')],
                active_user_id=engine.user_id,
            )


def require_user_change():
    if engine.pending_save is not None:
        raise HTTPException(409, 'Zuerst ungespeichertes Training erneut stoppen/speichern')
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
                async with engine.hr_lock:
                    await engine.hr.disconnect()
            db.execute("INSERT OR REPLACE INTO settings VALUES ('active_user',?)", (str(user_id),))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('training_profile',?)", (profile.model_dump_json(),))
        engine.user_id, engine.profile = user_id, profile
        engine.steps, engine.samples, engine.history = [], [], []
        engine.reset_recording()
        engine.connections, engine.connection_events = {}, []
        engine.elapsed = engine.distance = engine.energy = 0
        engine.target = 25
        engine.plan_name = engine.step_name = 'Freies Training'
        engine.calibrating = False
        engine.workout_id = None
        engine.session_state = 'idle'
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
        data = body.model_dump(exclude={'expected_user_id'})
        # Older browsers do not know these additive profile fields. An omitted
        # field must survive their save; explicit null still clears it.
        for key in ('birth_year', 'weight_kg', 'height_cm', 'sex', 'power_min_watts', 'power_max_watts'):
            if key not in body.model_fields_set:
                data[key] = getattr(engine.profile, key, None)
        values = TrainingProfile.model_validate(data)
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


def check_power_request(expected_user_id, expected_session_id):
    require_expected_user(expected_user_id)
    if expected_session_id is not None and (expected_session_id != engine.session_id or not engine.running):
        raise HTTPException(409, 'Die Trainingseinheit wurde beendet oder gewechselt. Bitte aktuellen Zustand prüfen.')
    if engine.stopping or engine.stop_requested or engine.pending_save is not None:
        raise HTTPException(409, 'Training wird beendet oder muss noch gespeichert werden')
    if engine.locally_locked() or engine.control_owner == 'zwift':
        raise HTTPException(409, 'Zwift-Steuerung ist freigegeben. Zuerst im Cockpit sperren.')
    if engine.mode != 'demo' and 'power' not in engine.connector.capabilities.get('control', []):
        raise HTTPException(409, 'Dieses Gerät unterstützt keine Wattsteuerung')


@app.post('/api/power')
async def power(body: Power):
    # No I/O/await inside the request mutation: desired state can be updated even
    # while a slow adapter command/read is in flight under the engine lock. The
    # polling loop sends only the newest slot and never enqueues slider writes.
    check_power_request(body.expected_user_id, body.expected_session_id)
    limits = engine.power_limits()
    if not limits['minimum'] <= body.watts <= limits['maximum']:
        detail = f"Leistung muss zwischen {limits['minimum']} und {limits['maximum']} W liegen"
        engine.control_event(body.source, 'rejected', attempted_target_watts=body.watts, error=detail)
        raise HTTPException(422, detail)
    if engine.running and engine.training_mode == 'hr' and not engine.paused:
        bpm = engine.hr.value()
        if bpm is None or engine.hr.age() >= 3 or bpm >= engine.profile.hr_ceiling:
            raise HTTPException(409, 'Kein sicheres frisches Pulssignal; zuerst pausieren und Signal prüfen')
        if (engine.cadence < 30 or bpm > engine.steps[engine.step_index]['hr_high']) and body.watts > engine.target:
            raise HTTPException(409, 'Puls-/Trittfrequenzregel begrenzt eine Lasterhöhung')
    engine.request_target(body.watts, body.source, manual=True)
    return engine.snapshot()


@app.post('/api/power/plan')
async def return_to_plan(body: ReturnToPlan):
    check_power_request(body.expected_user_id, body.expected_session_id)
    if not engine.running or not engine.steps:
        raise HTTPException(409, 'Kein laufender Stufenplan vorhanden')
    engine.manual_override = None
    planned = engine.planned_power()
    if engine.training_mode == 'hr':
        # Hand back to the slow pulse controller with its existing settling
        # rules; do not bypass it by applying an aggressive planned reference.
        engine.pulse.reset()
        planned = min(planned, engine.target)
    limits = engine.power_limits()
    engine.request_target(max(limits['minimum'], min(limits['maximum'], planned)), 'return_to_plan')
    return engine.snapshot()


@app.post('/api/start')
async def start(body: Start):
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        if engine.pending_save is not None:
            raise HTTPException(409, 'Zuerst ungespeichertes Training erneut stoppen/speichern')
        if engine.locally_locked():
            raise HTTPException(409, 'Zwift-Steuerung ist freigegeben. Lokaler Stopp bleibt möglich.')
        if engine.running:
            raise HTTPException(409, 'Training läuft bereits')
        if engine.mode == 'daum' and not engine.connected:
            raise HTTPException(409, 'Zuerst Daum verbinden')
        limits = engine.power_limits(training_mode=body.training_mode)
        if limits['minimum'] > limits['maximum']:
            raise HTTPException(422, 'Geräte- und Nutzergrenzen überschneiden sich nicht')
        steps, name = [], 'Freies Training'
        calibrating=False
        if body.plan_id is not None:
            from .catalog import plan_for_start
            with database() as db:
                row = plan_for_start(db, engine, body.plan_id, body.validation_token, body.intensity_percent, body.training_mode)
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
        engine.reset_recording()
        engine.workout_id = body.plan_id
        engine.started_at=datetime.now(timezone.utc).isoformat()
        engine.error = ''
        engine.pulse.reset()
        engine.step_index=0
        if body.training_mode=='hr':
            engine.target=max(limits['minimum'],min(50,limits['maximum'],steps[0]['watts']))
        elif not steps:
            engine.target=max(limits['minimum'],min(limits['maximum'],engine.target))
        engine.select_step()
        engine.running, engine.paused = True, False
        engine.session_state = 'running'
        engine.target_command_status = 'pending'
        engine.control_event('plan', 'started')
    return engine.snapshot()


@app.post('/api/calibration/comfortable')
async def calibration_comfortable():
    async with engine.lock:
        if not engine.running or engine.paused or not engine.calibrating or engine.training_mode!='power':
            raise HTTPException(409,'Zuerst die Orientierungsfahrt wattgeführt starten')
        if engine.mode!='daum' or not engine.connected:
            raise HTTPException(409,'Demo-Daten nicht als persönliche Belastung speichern')
        if engine.manual_override is not None:
            raise HTTPException(409, 'Manuell angepasste Last nicht als Orientierungsstufe übernehmen; zuerst zum Plan zurückkehren')
        if not 1<=engine.step_index<=5 or engine.steps[engine.step_index]['seconds']-engine.step_remaining<60:
            raise HTTPException(409,'Erst mindestens 60 Sekunden einer Wattstufe beobachten; noch kein Wert gespeichert')
        if engine.cadence<30:
            raise HTTPException(409,'Dafür bitte gleichmäßig treten; noch kein Wert gespeichert')
        if engine.applied_target_watts is None or engine.applied_target_watts != engine.target or engine.target_confirmation_detail != 'echoed_value':
            raise HTTPException(409, 'Dafür muss der angeforderte Lastwert vom Gerät bestätigt sein; keine Ist-Leistungsmessung wird daraus abgeleitet')
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
        if engine.paused:
            if engine.training_mode == 'hr':
                if engine.hr.value() is None or engine.hr.age() >= 3:
                    raise HTTPException(409, 'Zum Fortsetzen braucht der Pulsmodus ein frisches Gurtsignal')
                if engine.hr.value() >= engine.profile.hr_ceiling:
                    raise HTTPException(409, 'Persönliche Pulsgrenze erreicht')
                engine.pulse.reset()
                if engine.manual_override is None:
                    engine.target = engine.safe_power()
                engine.error = ''
            engine.mark_resumed()
        else:
            engine.mark_paused()
            if engine.mode == 'daum':
                try:
                    await engine.apply_power(engine.safe_power(), source='pause/resume')
                except Exception as exc:
                    await engine.stop(reason='error')
                    raise HTTPException(503, str(exc))
            engine.last_target = None
        engine.power = engine.cadence = engine.speed = 0
    return engine.snapshot()


@app.post('/api/stop')
async def stop():
    if engine.running:
        # Set intent before waiting for an in-flight network operation. A
        # pending S201 handshake checks this before sending an obsolete S23.
        engine.stop_requested = True
        engine.clear_override('safety')
        engine.target = engine.safe_power()
        engine.session_state = 'stopping'
        engine.control_event('safety', 'stop_requested')
    async with engine.lock:
        await engine.stop()
        if engine.pending_save is not None:
            raise HTTPException(503, engine.error)
    return engine.snapshot()


@app.post('/api/mode')
async def mode(body: Mode):
    async with engine.lock:
        require_expected_user(body.expected_user_id)
        if engine.locally_locked():
            raise HTTPException(409, 'Zwift-Steuerung vor dem Moduswechsel sperren')
        if engine.running:
            raise HTTPException(409, 'Training vor dem Moduswechsel beenden')
        await engine.connector.close()
        engine.connected = False
        engine.applied_target_watts = None
        engine.target_confirmation_source = None
        engine.target_confirmation_detail = None
        engine.clear_override('safety')
        engine.target = engine.safe_power()
        engine.last_target = None
        engine.target_command_status = 'idle'
        engine.mode, engine.error = body.mode, ''
        if body.mode == 'daum':
            try:
                await engine.connector.connect()
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
        sensors = []

        async def attempt(device):
            nonlocal sensors
            started = time.monotonic()
            engine.connection_event(device, 'start', 'connecting')
            try:
                if device == 'daum':
                    if engine.mode == 'daum' and engine.connected:
                        message = 'Daum bereits verbunden'
                    else:
                        engine.connected, engine.mode, engine.error = False, 'daum', ''
                        engine.applied_target_watts = None
                        engine.target_confirmation_source = None
                        engine.target_confirmation_detail = None
                        engine.clear_override('safety')
                        engine.target = engine.safe_power()
                        engine.last_target = None
                        engine.target_command_status = 'idle'
                        engine.connection_event(device, 'close', 'connecting')
                        await asyncio.wait_for(engine.connector.close(), 3)
                        engine.connection_event(device, 'connect', 'connecting')
                        await asyncio.wait_for(engine.connector.connect(), 12)
                        engine.connected = True
                        message = 'Daum verbunden'
                elif device == 'hr':
                    async with engine.hr_lock:
                        if engine.hr.client and engine.hr.client.is_connected:
                            message = 'Pulssensor bereits verbunden'
                        else:
                            engine.connection_event(device, 'scan', 'connecting')
                            sensors = await asyncio.wait_for(engine.hr.scan(), 10)
                            engine.connection_event(device, 'scan', 'scanned', sensor_count=len(sensors))
                            if len(sensors) == 1:
                                engine.connection_event(device, 'connect', 'connecting')
                                await asyncio.wait_for(engine.hr.connect(sensors[0]['address']), 20)
                                message = 'Pulssensor verbunden · warte auf frisches Signal'
                            elif sensors:
                                raise ValueError('Mehrere Pulssensoren gefunden – bitte deinen Sensor auswählen')
                            else:
                                raise ValueError('Kein Pulssensor gefunden. Gurt anlegen und Bluetooth aktivieren.')
                else:
                    # Zwift is an optional sender, never a required sensor or
                    # automatic permission for external resistance control.
                    from .zwift import ZwiftBridge
                    if not engine.zwift:
                        engine.zwift = ZwiftBridge(engine)
                    if not engine.zwift.server:
                        await asyncio.wait_for(engine.zwift.start(), 15)
                    message = 'Zwift-Sender aktiv · Steuerung bleibt gesperrt'
                result = dict(device=device, ok=True, message=message)
            except Exception as exc:
                detail = str(exc) or 'Zeitüberschreitung'
                if device == 'daum':
                    engine.error = f'Daum nicht erreichbar: {detail}'
                    detail = engine.error
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(engine.connector.close(), 3)
                elif device == 'zwift' and engine.zwift:
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(engine.zwift.stop(), 5)
                result = dict(device=device, ok=False, message=detail)
            duration_ms = round((time.monotonic() - started) * 1000)
            engine.connection_event(device, 'finished', 'connected' if result['ok'] else 'failed',
                                    result['message'], duration_ms=duration_ms)
            return dict(**result, phase='finished', duration_ms=duration_ms)

        selected = list(dict.fromkeys(body.devices))
        # TCP and BLE sensor attempts are independent. Keep all BLE sender work
        # sequential with the HR operation on the same adapter.
        results = await asyncio.gather(*(attempt(device) for device in selected if device != 'zwift'))
        if 'zwift' in selected:
            results.append(await attempt('zwift'))
        return dict(state=engine.snapshot(), sensors=sensors, results=results, needs_sensor_choice=len(sensors) > 1)


@app.get('/api/hr/scan')
async def scan():
    async with engine.hr_lock:
        engine.connection_event('hr', 'scan', 'connecting')
        try:
            sensors = await asyncio.wait_for(engine.hr.scan(), 10)
            engine.connection_event('hr', 'scan', 'scanned', sensor_count=len(sensors))
            return sensors
        except Exception as exc:
            engine.connection_event('hr', 'scan', 'failed', str(exc) or 'Zeitüberschreitung')
            raise HTTPException(503, f'Bluetooth-Suche fehlgeschlagen: {str(exc) or "Zeitüberschreitung"}')


@app.post('/api/hr/connect')
async def connect_hr(sensor: Sensor):
    async with engine.hr_lock:
        require_expected_user(sensor.expected_user_id)
        engine.connection_event('hr', 'connect', 'connecting')
        try:
            await asyncio.wait_for(engine.hr.connect(sensor.address), 20)
            engine.connection_event('hr', 'finished', 'connected', 'Verbunden · frisches Signal separat prüfen')
        except Exception as exc:
            engine.connection_event('hr', 'finished', 'failed', str(exc) or 'Zeitüberschreitung')
            raise HTTPException(503, f'Pulsgurt nicht verbunden: {str(exc) or "Zeitüberschreitung"}')
    return engine.snapshot()


@app.post('/api/hr/disconnect')
async def disconnect_hr(body: ConnectionRequest = ConnectionRequest()):
    async with engine.hr_lock:
        require_expected_user(body.expected_user_id)
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
        return [ride_record(r) for r in db.execute('SELECT id,created,seconds,distance,energy,mode,plan_name,training_mode,started_at,finish_reason,summary_json,activity_type,control_events_json FROM rides WHERE user_id=? ORDER BY id DESC LIMIT 30', (engine.user_id,))]


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
        row=db.execute('SELECT * FROM rides WHERE id=? AND (user_id=? OR (user_id IS NULL AND ?=(SELECT MIN(id) FROM users)))',
                       (ride_id,engine.user_id,engine.user_id)).fetchone()
    if not row:
        raise HTTPException(404,'Fahrt nicht gefunden')
    data=export_payload(dict(row))
    prefix='DEMO-' if data['simulated'] else ''
    filename=f'{prefix}Fitness-Cockpit-{ride_id}.{format}'
    if format=='tcx':
        if data['summary'].get('distance') is None:
            raise HTTPException(422, 'TCX benötigt eine bekannte Distanz. JSON oder CSV erhält fehlende Werte.')
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


from .cockpit import install_routes
install_routes(app, get_engine=lambda: engine, database=database,
               require_expected_user=require_expected_user, require_user_change=require_user_change)

from .catalog import install_routes as install_catalog_routes
install_catalog_routes(app, get_engine=lambda: engine, database=database,
                       require_expected_user=require_expected_user, require_user_change=require_user_change)
from .coach import install_routes as install_coach_routes
install_coach_routes(app, get_engine=lambda: engine, database=database,
                     require_expected_user=require_expected_user, require_user_change=require_user_change)
from .routes import install_routes as install_route_routes
install_route_routes(app, get_engine=lambda: engine, database=database, require_expected_user=require_expected_user)

dist = ROOT / 'frontend' / 'dist'
if dist.exists():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
