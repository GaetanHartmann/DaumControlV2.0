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


def indoor_bike_data(state):
    hr = state.get('heart_rate')
    flags = (1<<2)|(1<<6)|((1<<9) if hr is not None else 0)
    value = struct.pack('<HHHh', flags, max(0,min(65535,round(state['speed']*100))),
                        max(0,min(65535,round(state['cadence']*2))), max(-32768,min(32767,round(state['power']))))
    return value + (bytes([max(0,min(255,hr))]) if hr is not None else b'')
