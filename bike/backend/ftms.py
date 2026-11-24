"""Bluetooth Fitness Machine Service wire formats and road-load model."""
import math
import struct

SUCCESS, UNSUPPORTED, INVALID, FAILED, DENIED = range(1, 6)


def decode_control(data):
    if not data:
        raise ValueError('Leerer Befehl')
    op = data[0]
    sizes = {0:1, 1:1, 5:3, 7:1, 8:2, 17:7}
    if op not in sizes:
        return op, None
    if len(data) != sizes[op]:
        raise ValueError('Ungültige Befehlslänge')
    if op == 5:
        watts = struct.unpack('<h', data[1:])[0]
        if not 25 <= watts <= 400:
            raise ValueError('Leistung außerhalb 25–400 W')
        return op, watts
    if op == 8:
        if data[1] not in (1, 2):
            raise ValueError('Ungültiger Stoppmodus')
        return op, data[1]
    if op == 17:
        wind, grade, crr, cw = struct.unpack('<hhBB', data[1:])
        return op, dict(wind=wind/1000, grade=grade/100, crr=crr/10000, cw=cw/100)
    return op, None


def simulation_watts(speed, cadence, parameters, rider_kg=85, bike_kg=10):
    if cadence <= 0:
        return 25
    v = max(1, speed / 3.6)
    angle = math.atan(parameters['grade']/100)
    gravity = (rider_kg+bike_kg)*9.80665*math.sin(angle)
    rolling = (rider_kg+bike_kg)*9.80665*parameters['crr']*math.cos(angle)
    wind = v+parameters['wind']
    return max(25, min(400, round((gravity+rolling+parameters['cw']*wind*abs(wind))*v)))


def telemetry_value(state, key):
    """Prefer canonical availability over compatibility numeric placeholders.

    Legacy standalone packet fixtures may omit the measurements map. Once that
    map exists, an absent field or an explicitly unverified value is unknown;
    neither a requested setpoint nor reported_power may replace measured power.
    """
    if 'measurements' in state:
        fields = state.get('measurements')
        item = fields.get(key) if isinstance(fields, dict) else None
        if not isinstance(item, dict) or item.get('available') is not True or item.get('stale'):
            return None
        if item.get('quality') in ('device_reported_unverified', 'unverified', 'unknown', 'unavailable'):
            return None
        value = item.get('value')
    else:
        value = state.get(key)
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    if key in ('speed', 'cadence') and value < 0 or key == 'heart_rate' and value <= 0:
        return None
    return value


def indoor_bike_data(state):
    """Encode only known fields; power and heart rate are optional in FTMS.

    The existing single-record publisher always includes instantaneous speed.
    Without a fresh speed it sends no record, rather than inventing zero or
    setting More Data as if a second fragment containing speed would follow.
    Fitness Machine Service 1.0.1, Indoor Bike Data (0x2AD2):
    https://www.bluetooth.com/specifications/specs/fitness-machine-service-1-0-1/
    """
    speed = telemetry_value(state, 'speed')
    if speed is None:
        return b''
    cadence = telemetry_value(state, 'cadence')
    power = telemetry_value(state, 'power')
    hr = telemetry_value(state, 'heart_rate')
    flags = ((1 << 2) if cadence is not None else 0) | ((1 << 6) if power is not None else 0) | ((1 << 9) if hr is not None else 0)
    value = struct.pack('<HH', flags, max(0, min(65535, round(speed * 100))))
    if cadence is not None:
        value += struct.pack('<H', max(0, min(65535, round(cadence * 2))))
    if power is not None:
        value += struct.pack('<h', max(-32768, min(32767, round(power))))
    if hr is not None:
        value += bytes([max(0, min(255, round(hr)))])
    return value
