"""BLE output never upgrades a requested/unverified value to measured power."""
import struct
import time
from types import SimpleNamespace

from backend.ftms import indoor_bike_data
from backend.zwift import ZwiftBridge, uuid
from backend.main import Engine


class Peripheral:
    def __init__(self):
        self.notifications = []

    def update(self, characteristic, value):
        self.notifications.append((characteristic, value))


def field(value, available=True, stale=False, quality=None):
    return dict(value=value, available=available, stale=stale, quality=quality)


def state(**changes):
    fields = dict(speed=field(28.5), cadence=field(82.5),
                  power=field(None, False, quality='device_reported_unverified'),
                  reported_power=field(35, quality='device_reported_unverified'),
                  heart_rate=field(140))
    fields.update(changes)
    # These are deliberately plausible but untrusted compatibility placeholders.
    return dict(speed=0, cadence=0, power=0, heart_rate=0, measurements=fields)


def publisher():
    bridge = ZwiftBridge(SimpleNamespace())
    bridge.server = Peripheral()
    return bridge


def test_unverified_daum_speed_unit_is_disclosed_and_not_broadcast_as_known_kmh():
    engine = Engine()
    engine.mode, engine.running = 'daum', True
    engine.speed, engine.cadence, engine.reported_power = 20, 80, 35
    engine.available_metrics = {'speed', 'cadence', 'reported_power'}
    engine.last_measurement_at = time.monotonic()
    snapshot = engine.snapshot()
    assert snapshot['speed_measurement_note']
    assert snapshot['measurements']['speed']['quality'] == 'device_reported_unverified'
    assert indoor_bike_data(snapshot) == b''
    engine.mode = 'demo'
    assert indoor_bike_data(engine.snapshot())  # Explicit simulation remains usable.


def test_ftms_omits_unverified_power_and_uses_known_speed_cadence_heart_rate():
    packet = indoor_bike_data(state())
    assert struct.unpack('<HHHB', packet) == ((1 << 2) | (1 << 9), 2850, 165, 140)
    assert not struct.unpack_from('<H', packet)[0] & (1 << 6)


def test_ftms_canonical_known_power_keeps_legacy_field_layout():
    values = state(power=field(156, quality='verified_measured'))
    packet = indoor_bike_data(values)
    legacy = indoor_bike_data(dict(speed=28.5, cadence=82.5, power=156, heart_rate=140))
    assert packet == legacy == struct.pack('<HHHhB', 580, 2850, 165, 156, 140)


def test_unknown_power_never_generates_cps_zero_but_ftms_and_fresh_hr_continue():
    bridge = publisher()
    bridge.publish(state())
    values = dict(bridge.server.notifications)
    assert uuid('2a63') not in values
    assert struct.unpack('<HHHB', values[uuid('2ad2')]) == (516, 2850, 165, 140)
    assert values[uuid('2a37')] == bytes([0, 140])


def test_explicit_unverified_or_stale_power_cannot_be_broadcast_as_measurement():
    for value in (field(35, quality='device_reported_unverified'), field(100, stale=True),
                  field(None), field(float('nan')), field(True)):
        bridge = publisher()
        bridge.publish(state(power=value))
        values = dict(bridge.server.notifications)
        assert uuid('2a63') not in values
        assert not struct.unpack_from('<H', values[uuid('2ad2')])[0] & (1 << 6)


def test_known_measured_zero_is_distinct_from_missing_power():
    bridge = publisher()
    bridge.publish(state(power=field(0, quality='verified_measured')))
    values = dict(bridge.server.notifications)
    assert struct.unpack_from('<Hh', values[uuid('2a63')]) == (32, 0)
    assert struct.unpack_from('<H', values[uuid('2ad2')])[0] & (1 << 6)


def test_stale_or_absent_hr_omits_hr_flag_and_notification():
    for value in (field(140, stale=True), field(None, False), field(0)):
        bridge = publisher()
        bridge.publish(state(heart_rate=value))
        values = dict(bridge.server.notifications)
        assert uuid('2a37') not in values
        assert struct.unpack('<HHH', values[uuid('2ad2')]) == (4, 2850, 165)


def test_missing_speed_skips_ftms_instead_of_manufacturing_zero_speed():
    bridge = publisher()
    bridge.publish(state(speed=field(None, False), power=field(100)))
    values = dict(bridge.server.notifications)
    assert uuid('2ad2') not in values
    assert uuid('2a63') in values


def test_missing_cadence_is_omitted_from_ftms_and_cps_crank_fields():
    bridge = publisher()
    bridge.publish(state(cadence=field(None, False), power=field(156)))
    values = dict(bridge.server.notifications)
    assert struct.unpack('<HHhB', values[uuid('2ad2')]) == (576, 2850, 156, 140)
    assert struct.unpack('<Hh', values[uuid('2a63')]) == (0, 156)


def test_legacy_valid_notification_layout_stays_compatible():
    bridge = publisher()
    bridge.publish(dict(speed=28.5, cadence=82.5, power=156, heart_rate=140))
    values = dict(bridge.server.notifications)
    assert struct.unpack('<HhHH', values[uuid('2a63')]) == (32, 156, 0, 0)
    assert struct.unpack('<HHHhB', values[uuid('2ad2')]) == (580, 2850, 165, 156, 140)


def test_bridge_details_never_call_requested_target_applied_power():
    engine = SimpleNamespace(remote_mode='ERG', simulation={'grade': 0}, remote_target=150,
                             target=120, applied_target_watts=None, rider_kg=75, bike_kg=10)
    bridge = ZwiftBridge(engine)
    assert bridge.details()['requested_power'] == 150
    assert bridge.details()['applied_power'] is None
    engine.applied_target_watts = 110
    assert bridge.details()['applied_power'] == 110


def test_daums_target_power_control_does_not_advertise_measured_power():
    from backend.connectors import DaumConnector
    engine = SimpleNamespace(mode='daum', connector=SimpleNamespace(capabilities=DaumConnector.capabilities))
    bridge = ZwiftBridge(engine)
    measured, controllable = struct.unpack('<II', bridge.features())
    assert not measured & (1 << 14)
    assert measured & (1 << 1)
    assert controllable & (1 << 3) and controllable & (1 << 13)
    engine.mode = 'demo'
    assert struct.unpack('<II', bridge.features())[0] & (1 << 14)


def test_feature_reads_are_updated_when_changing_from_simulation_to_real_device():
    from backend.connectors import DaumConnector
    engine = SimpleNamespace(mode='demo', connector=SimpleNamespace(capabilities=DaumConnector.capabilities))
    bridge = ZwiftBridge(engine)
    bridge.server = Peripheral()
    bridge.publish(state())
    assert dict(bridge.server.notifications)[uuid('2acc')] == bridge.features()
    assert struct.unpack('<II', bridge.features())[0] & (1 << 14)
    bridge.server.notifications.clear()
    engine.mode = 'daum'
    bridge.publish(state())
    assert not struct.unpack('<II', dict(bridge.server.notifications)[uuid('2acc')])[0] & (1 << 14)
