"""Local workout exports. No account upload or direct HealthKit integration."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

TCX='http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'
EXT='http://www.garmin.com/xmlschemas/ActivityExtension/v2'
ET.register_namespace('',TCX)
ET.register_namespace('ae',EXT)


def migrate_exports(db):
    columns={r[1] for r in db.execute('PRAGMA table_info(rides)')}
    for name,definition in [('samples_json',"TEXT NOT NULL DEFAULT '[]'"),('plan_name',"TEXT NOT NULL DEFAULT ''"),
                            ('training_mode',"TEXT NOT NULL DEFAULT 'power'"),('started_at','TEXT')]:
        if name not in columns:
            db.execute(f'ALTER TABLE rides ADD COLUMN {name} {definition}')


def utc_time(ride):
    if ride.get('started_at'):
        value=datetime.fromisoformat(ride['started_at'])
    else:
        # Legacy records only stored the end timestamp; preserve this distinction.
        value=datetime.fromisoformat(ride['created']).replace(tzinfo=timezone.utc)-timedelta(seconds=ride['seconds'])
    return value.astimezone(timezone.utc)


def iso(value):
    return value.isoformat(timespec='seconds').replace('+00:00','Z')


def payload(ride):
    samples=json.loads(ride.pop('samples_json','[]'))
    return dict(format_version=1,source='DAUM Studio',activity='indoor_cycling',
                simulated=ride['mode']=='demo',start_time=iso(utc_time(ride)),
                start_time_estimated=not bool(ride.get('started_at')),summary=ride,
                sample_columns=['elapsed_seconds','power_watts','target_watts','heart_rate_bpm','cadence_rpm','speed_kmh','distance_km','timestamp_utc'],
                samples=samples,notes='Mechanische Arbeit in kJ, keine gemessenen Kalorien. Fehlende Werte bleiben leer.')


def csv_export(data):
    output=io.StringIO(newline='')
    writer=csv.writer(output)
    writer.writerow(['record_type','ride_id','mode','start_utc','elapsed_seconds','power_watts','target_watts',
                     'heart_rate_bpm','cadence_rpm','speed_kmh','distance_km','sample_utc','mechanical_energy_kj'])
    ride=data['summary']
    writer.writerow(['summary',ride['id'],ride['mode'],data['start_time'],ride['seconds'],'','','','','',ride['distance'],'',ride['energy']])
    for sample in data['samples']:
        row=(sample+[None]*7)[:7]
        writer.writerow(['sample',ride['id'],ride['mode'],data['start_time'],*row,sample[7] if len(sample)>7 else '', ''])
    return '\ufeff'+output.getvalue()


def tcx_export(data):
    root=ET.Element(f'{{{TCX}}}TrainingCenterDatabase')
    def add(parent,name,value=None,namespace=TCX,**attributes):
        node=ET.SubElement(parent,f'{{{namespace}}}{name}',attributes)
        if value is not None:
            node.text=str(value)
        return node
    activities=add(root,'Activities')
    activity=add(activities,'Activity',Sport='Biking')
    ride=data['summary']
    start=utc_time(ride)
    add(activity,'Id',iso(start))
    lap=add(activity,'Lap',StartTime=iso(start))
    add(lap,'TotalTimeSeconds',round(ride['seconds'],3))
    add(lap,'DistanceMeters',round(ride['distance']*1000,3))
    # Required by TCX schema, but not measured: explicitly explain the zero below.
    add(lap,'Calories',0)
    heart_rates=[s[3] for s in data['samples'] if len(s)>3 and s[3] is not None and 0<s[3]<=255]
    if heart_rates:
        add(add(lap,'AverageHeartRateBpm'),'Value',round(sum(heart_rates)/len(heart_rates)))
        add(add(lap,'MaximumHeartRateBpm'),'Value',max(heart_rates))
    add(lap,'Intensity','Active')
    add(lap,'TriggerMethod','Manual')
    if data['samples']:
        track=add(lap,'Track')
        for sample in data['samples']:
            elapsed,power,target,hr,cadence,speed,distance=(sample+[None]*7)[:7]
            point=add(track,'Trackpoint')
            timestamp=datetime.fromisoformat(sample[7]) if len(sample)>7 else start+timedelta(seconds=elapsed)
            add(point,'Time',iso(timestamp))
            if distance is not None:
                add(point,'DistanceMeters',round(distance*1000,3))
            if hr is not None and 0<hr<=255:
                add(add(point,'HeartRateBpm'),'Value',hr)
            if cadence is not None:
                add(point,'Cadence',max(0,min(254,round(cadence))))
            extensions=add(point,'Extensions')
            tpx=add(extensions,'TPX',namespace=EXT)
            if speed is not None:
                add(tpx,'Speed',round(speed/3.6,5),namespace=EXT)
            add(tpx,'Watts',max(0,round(power)),namespace=EXT)
    prefix='DEMO / SIMULIERTE WERTE. ' if data['simulated'] else ''
    add(activity,'Notes',prefix+(ride.get('plan_name') or 'Indoor Cycling')+
        '. Indoor-Radfahrt ohne GPS. Kalorien nicht gemessen (Pflichtfeld Calories=0). Mechanische Arbeit: '+str(round(ride['energy'],1))+
        ' kJ. Keine VO2max-Messung.'+(' Nur Zusammenfassung; keine gespeicherte Messspur.' if not data['samples'] else ''))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
