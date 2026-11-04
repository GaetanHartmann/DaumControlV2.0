"""Training suggestions, not individual prescriptions or a VO2max measurement.

Sources: https://www.ntnu.edu/cerg/regimen (4x4 structure / late HR response),
https://www.heart.org/en/healthy-living/exercise-and-physical-activity/fitness-basics/target-heart-rates
https://www.cdc.gov/physical-activity-basics/measuring/index.html
Watt/FTP factors are editable application starting points, not NTNU prescriptions.
"""
import json
import math
from pydantic import BaseModel, Field, model_validator


class TrainingProfile(BaseModel):
    ftp_watts: int | None = Field(default=None, ge=50, le=400)
    power_adjustment_watts: int = Field(default=0, ge=-100, le=100)
    comfortable_watts: int | None = Field(default=None, ge=25, le=250)
    hr_max: int | None = Field(default=None, ge=100, le=230)
    hr_ceiling: int | None = Field(default=None, ge=70, le=220)
    hr_min_watts: int = Field(default=25, ge=25, le=200)
    hr_max_watts: int = Field(default=150, ge=30, le=400)

    @model_validator(mode='after')
    def validate_limits(self):
        if self.hr_ceiling is not None and (self.hr_max is None or self.hr_ceiling > self.hr_max):
            raise ValueError('Pulsgrenze muss unter oder gleich der persönlichen HFmax liegen')
        if self.hr_min_watts >= self.hr_max_watts:
            raise ValueError('Watt-Untergrenze muss kleiner als Watt-Obergrenze sein')
        return self


ZONES = {'warm':(.50,.65), 'base':(.60,.70), 'tempo':(.75,.85), 'vo2':(.85,.95),
         'recovery':(.55,.70), 'cool':(.50,.60)}


def section(name, minutes, factor, zone):
    return dict(name=name, seconds=round(minutes*60), watts=round(150*factor), ftp_factor=factor, zone=zone)


def repeats(count, work_minutes, factor, recovery_minutes, zone):
    steps=[]
    for i in range(count):
        steps.append(section(f'Intervall {i+1}/{count}',work_minutes,factor,zone))
        if i < count-1:
            steps.append(section('Aktive Erholung',recovery_minutes,.50,'recovery'))
    return steps


def templates():
    w=lambda mins: section('Einrollen',mins,.50,'warm')
    c=lambda mins: section('Ausrollen',mins,.40,'cool')
    b=lambda mins: section('Grundlage',mins,.65,'base')
    specs=[
        ('base35','Grundlage 35',35,'Grundlage',[w(5),section('Sanft steigern',5,.55,'warm'),b(20),c(5)]),
        ('tempo35','Tempo 35 · 3×4',35,'Tempo',[w(7),*repeats(3,4,.85,3,'tempo'),b(5),c(5)]),
        ('vo235','Intervall-Einstieg 35 · 3×3',35,'VO₂max',[w(8),*repeats(3,3,1.05,3,'vo2'),b(7),c(5)]),
        ('base45','Grundlage 45',45,'Grundlage',[w(8),b(32),c(5)]),
        ('tempo45','Tempo 45 · 3×8',45,'Tempo',[w(8),*repeats(3,8,.85,3,'tempo'),c(7)]),
        ('vo245','VO₂max 45 · 4×4',45,'VO₂max',[w(10),*repeats(4,4,1.05,3,'vo2'),c(10)]),
        ('base60','Grundlage 60',60,'Grundlage',[w(10),b(45),c(5)]),
        ('tempo60','Tempo 60 · 3×10',60,'Tempo',[w(10),*repeats(3,10,.85,5,'tempo'),c(10)]),
        ('vo260','VO₂max + Grundlage 60',60,'VO₂max',[w(12),*repeats(4,4,1.05,3,'vo2'),b(15),c(8)])]
    descriptions={
        'Grundlage':'Ruhige Ausdauer. Sprechen in ganzen Sätzen soll möglich bleiben.',
        'Tempo':'Längere kontrollierte Belastungen; kein Sprint und kein All-out.',
        'VO₂max':'Intensive aerobe Intervalle mit aktiver Erholung. Für an intensive Belastung gewöhnte Personen.'}
    for key,name,minutes,category,steps in specs:
        assert sum(s['seconds'] for s in steps)==minutes*60
        yield dict(key=key,name=name,steps=steps,meta=dict(category=category,description=descriptions[category],minutes=minutes,relative_ftp=True))
    yield from terrain_templates()


def terrain_templates():
    """Fictional routes: FTP-based ERG targets, not a road-load simulation.

    Each phase eases into its next grade and effort in 30-second increments.
    Flat phases are combined so these templates remain editable as custom plans.
    """
    # Each phase ends at (virtual grade %, fraction of personal FTP).
    specs = [
        ('hills35', 'Hügelrunde 35 · drei Wellen', 35, [
            ('Einrollen', 5, 0, .55),
            ('Erster Hügel', 4, 3, .75), ('Erste Abfahrt', 3, -3, .45),
            ('Zweiter Hügel', 4, 4, .80), ('Zweite Abfahrt', 3, -4, .42),
            ('Dritter Hügel', 4, 3, .75), ('Letzte Abfahrt', 3, -3, .45),
            ('Talstraße', 4, 0, .55), ('Ausrollen', 5, 0, .40)]),
        ('climb35', 'Bergfahrt 35 · zum Aussichtspunkt', 35, [
            ('Einrollen', 5, 0, .55), ('Anfahrt', 3, 1, .60),
            ('Auffahrt', 8, 5, .85), ('Oben am Berg', 3, 5, .85),
            ('Über die Kuppe', 3, 0, .65), ('Abfahrt', 4, -5, .40),
            ('Zurück ins Tal', 4, 0, .50), ('Ausrollen', 5, 0, .40)]),
        ('pass45', 'Passstraße 45 · lange Auffahrt', 45, [
            ('Einrollen', 6, 0, .55), ('Anfahrt', 4, 1, .60),
            ('Passauffahrt', 10, 6, .90), ('Gleichmäßig bergauf', 5, 6, .90),
            ('Über den Pass', 3, 0, .65), ('Lange Abfahrt', 6, -6, .38),
            ('Talstraße', 5, 0, .55), ('Ausrollen', 6, 0, .40)]),
        ('double45', 'Doppelpass 45 · zwei Anstiege', 45, [
            ('Einrollen', 5, 0, .55), ('Erste Auffahrt', 7, 4, .80),
            ('Erste Kuppe', 2, 0, .65), ('Erste Abfahrt', 4, -4, .42),
            ('Zwischen den Pässen', 4, 0, .55), ('Zweite Auffahrt', 8, 6, .90),
            ('Zweite Kuppe', 2, 0, .65), ('Zweite Abfahrt', 5, -6, .38),
            ('Talstraße', 3, 0, .50), ('Ausrollen', 5, 0, .40)]),
        ('alpine60', 'Alpenrunde 60 · drei Anstiege', 60, [
            ('Einrollen', 6, 0, .55), ('Erste Auffahrt', 5, 3, .75),
            ('Erster Höhenweg', 4, 3, .75), ('Erste Abfahrt', 4, -3, .45),
            ('Zweite Auffahrt', 6, 5, .85), ('Zweiter Höhenweg', 4, 5, .85),
            ('Zweite Abfahrt', 5, -5, .40), ('Talstraße', 3, 0, .55),
            ('Dritte Auffahrt', 7, 6, .90), ('Dritter Höhenweg', 4, 6, .90),
            ('Letzte Abfahrt', 5, -6, .38), ('Ausrollen', 7, 0, .40)]),
        ('summit60', 'Gipfeltour 60 · der lange Pass', 60, [
            ('Einrollen', 7, 0, .55), ('Anfahrt', 5, 1, .60),
            ('Untere Passstraße', 9, 4, .80), ('Am Berghang', 6, 4, .80),
            ('Zum Gipfel', 7, 7, .95), ('Gipfelpassage', 6, 7, .95),
            ('Über die Kuppe', 3, 0, .65), ('Lange Abfahrt', 7, -7, .35),
            ('Zurück ins Tal', 4, 0, .50), ('Ausrollen', 6, 0, .40)]),
    ]
    for key, name, minutes, phases in specs:
        steps = []
        grade, effort = 0, .45
        for label, duration, next_grade, next_effort in phases:
            count = duration * 2
            for i in range(count):
                t = (i + .5) / count
                eased = t * t * (3 - 2 * t)
                factor = round(effort + (next_effort - effort) * eased, 4)
                virtual_grade = round(grade + (next_grade - grade) * eased, 2)
                zone = 'warm' if label == 'Einrollen' else 'cool' if label == 'Ausrollen' else 'tempo' if factor > .78 else 'base' if factor >= .56 else 'recovery'
                step = dict(name=label, seconds=30, watts=round(150 * factor),
                            ftp_factor=factor, grade_percent=virtual_grade, zone=zone)
                if steps and all(steps[-1][field] == step[field] for field in ('name', 'ftp_factor', 'grade_percent')):
                    steps[-1]['seconds'] += 30
                else:
                    steps.append(step)
            grade, effort = next_grade, next_effort
        assert sum(s['seconds'] for s in steps) == minutes * 60
        assert len(steps) <= 100
        yield dict(key=key, name=name, steps=steps, meta=dict(
            category='Berg & Tal', minutes=minutes, relative_ftp=True, terrain=True,
            description='Virtuelle Strecke mit allmählichem Lastaufbau an Anstiegen und leichteren Abfahrten. Wattkurve relativ zu deiner FTP; Steigungswerte sind ein Streckenszenario.'))


def seed_templates(db):
    columns={r[1] for r in db.execute('PRAGMA table_info(plans)')}
    if 'template_key' not in columns:
        db.execute('ALTER TABLE plans ADD COLUMN template_key TEXT')
    if 'meta' not in columns:
        db.execute("ALTER TABLE plans ADD COLUMN meta TEXT NOT NULL DEFAULT '{}'")
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS plans_template_key ON plans(template_key)')
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    for plan in templates():
        db.execute('INSERT OR IGNORE INTO plans (name,steps,template_key,meta) VALUES (?,?,?,?)',
                   (plan['name'],json.dumps(plan['steps']),plan['key'],json.dumps(plan['meta'])))
    orientation=[dict(name='Locker einrollen',seconds=300,watts=25,zone='warm')]
    orientation += [dict(name=f'Orientierung {watts} W',seconds=120,watts=watts,zone='base') for watts in [40,50,60,70,80]]
    orientation += [dict(name='Ausrollen',seconds=300,watts=25,zone='cool')]
    db.execute('INSERT OR IGNORE INTO plans (name,steps,template_key,meta) VALUES (?,?,?,?)',
        ('Orientierungsfahrt 20 · locker starten',json.dumps(orientation),'orientation20',json.dumps(dict(
            category='Einstieg',calibration=True,description='Kein Maximaltest: niedrige Wattstufen, Sprechtest und freiwillige Einordnung. Keine Bestimmung von FTP, HFmax oder VO₂max.'))))


def read_profile(db):
    row=db.execute("SELECT value FROM settings WHERE key='training_profile'").fetchone()
    return TrainingProfile.model_validate_json(row[0]) if row else TrainingProfile()


def resolve_plan(row, profile, intensity=100):
    steps=json.loads(row['steps'])
    meta=json.loads(row['meta'])
    comfortable_basis=bool(not profile.ftp_watts and profile.comfortable_watts and meta.get('category')=='Grundlage')
    calibration=bool(meta.get('calibration'))
    adjustment=0 if calibration else profile.power_adjustment_watts
    effective_intensity=100 if calibration else intensity
    reference=profile.comfortable_watts/.65 if comfortable_basis else profile.ftp_watts or 150
    for step in steps:
        # Keep the exact personal basis so preview scaling does not round or clamp
        # twice. Half-up rounding matches JavaScript's Math.round for watt values.
        step['reference_watts']=step['ftp_factor']*reference if meta.get('relative_ftp') else step['watts']
        scaled=math.floor(step['reference_watts']*effective_intensity/100+.5)
        step['watts']=max(25,min(400,scaled+adjustment))
        if profile.hr_max and profile.hr_ceiling:
            lo,hi=ZONES.get(step.get('zone'),ZONES['base'])
            step['hr_high']=min(round(hi*profile.hr_max),profile.hr_ceiling-3)
            step['hr_low']=min(round(lo*profile.hr_max),step['hr_high']-4)
    return dict(id=row['id'],name=row['name'],steps=steps,meta=meta,power_adjustment_watts=adjustment,
                requires_ftp=False,
                power_basis='comfortable' if comfortable_basis else 'ftp' if profile.ftp_watts and meta.get('relative_ftp') else 'example' if meta.get('relative_ftp') else 'absolute',
                reference_ftp=profile.ftp_watts or 150)


class PulseController:
    """Slow band controller: +5W/15s after 45s settling; decreases sooner.

    No integral term; sensor loss cannot accumulate an increase. This is not a
    medical safety controller; the user's limit is a stop condition, not a diagnosis.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.last_change=0.0
        self.phase=None
        self.settle_until=0.0
        self.note='Bereit'

    def update(self, watts, bpm, age, low, high, ceiling, minimum, maximum, now, phase, reference):
        if bpm is not None and bpm >= ceiling:
            self.note='Persönliche Pulsgrenze erreicht'
            return 25,'stop'
        if bpm is None or bpm < 30 or age >= 10:
            self.note='Pulssignal fehlt – pausiert'
            return 25,'pause'
        if age >= 3:
            self.note='Pulssignal veraltet – Last reduziert'
            self.settle_until=now+45
            return 25,'wait'
        if phase != self.phase:
            self.phase=phase
            self.settle_until=now+45
            self.last_change=now
            watts=min(watts,reference,maximum)
        watts=max(minimum,min(maximum,watts))
        if bpm > high:
            if now-self.last_change >= 10:
                watts=max(minimum,watts-5)
                self.last_change=now
            self.note='Über Zielzone · Last senken'
        elif bpm < low:
            # During the first 45s, approach only the planned FTP-based feedforward
            # value. Do not chase a delayed pulse beyond that value.
            if now < self.settle_until and watts<min(reference,maximum) and now-self.last_change>=5:
                watts=min(reference,maximum,watts+5)
                self.last_change=now
            elif now >= self.settle_until and now-self.last_change >= 15:
                watts=min(maximum,watts+5)
                self.last_change=now
            self.note='An Wattgrenze' if watts>=maximum else 'Puls steigt verzögert · ruhig nachregeln'
        else:
            self.note='In deiner Zielzone'
        return watts,'run'
