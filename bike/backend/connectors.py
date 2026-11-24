"""Hardware-independent connector contract; Daum framing stays in devices.py."""
from typing import Protocol
import asyncio
import contextlib
from .devices import parse_training


class DeviceConnector(Protocol):
    capabilities: dict

    async def connect(self): ...
    async def close(self): ...
    async def read(self) -> dict: ...
    async def set_power(self, watts: int): ...
    async def release(self): ...


class DaumConnector:
    device_id = 'daum'
    capabilities = dict(activity_type='indoor_cycling',
                        read=['reported_power', 'cadence', 'speed'],
                        control=['power', 'release'],
                        power_min_watts=25, power_max_watts=400,
                        power_step_watts=5, target_confirmation='protocol_ack',
                        power_quality='device_reported_unverified',
                        speed_quality='device_reported_unverified',
                        speed_measurement_note='Die X70-Geschwindigkeitseinheit ist am fahrenden Gerät noch nicht abgeglichen: Herstellerdokument und bisheriger Decoder widersprechen sich. Angezeigte Geschwindigkeit und abgeleitete Distanz sind bis dahin ungeprüfte Gerätewerte.',
                        measurement_quality={'power':'device_reported_unverified'},
                        measured_power_supported=False,
                        power_measurement_note='X70 meldet einen Wattwert auch im Stillstand. Eine unabhängige Ist-Leistungsmessung ist nicht nachgewiesen; dieser Rohwert wird nicht als mechanische Arbeit integriert.')

    def __init__(self, device):
        self.device = device
        self.request_guard = None

    async def connect(self):
        try:
            return await self.device.connect()
        except BaseException:
            # Cancellation during the protocol handshake may follow successful
            # TCP connection establishment. Release that partial socket as well.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.device.close(), 3)
            raise

    async def close(self):
        await self.device.close()

    async def read(self):
        raw = parse_training(await self.device.command('X70'))
        # X70 field 6 is called power in the protocol, but the real idle probe
        # tracks S23 at 0 rpm. Its independent physical measurement provenance
        # is unverified even with cadence; do not turn a set load into work.
        return dict(power=None, reported_power=raw['power'], cadence=raw['cadence'], speed=raw['speed'])

    async def set_power(self, watts):
        if not self.capabilities['power_min_watts'] <= watts <= self.capabilities['power_max_watts']:
            raise ValueError('Leistung außerhalb der Gerätefähigkeiten')
        if hasattr(self.device, 'power_guard'):
            self.device.power_guard = self.request_guard
        try:
            result = await self.device.set_power(watts)
        finally:
            if hasattr(self.device, 'power_guard'):
                self.device.power_guard = None
        if result is False:
            return dict(confirmed=False, superseded=True, watts=watts)
        # devices.Daum.command verifies ACK, response command and checksum for
        # S201 and S23. This confirms protocol acceptance, not measured power or
        # a separately verified mechanical resistance at the flywheel.
        if isinstance(result, dict):
            accepted = result.get('watts')
            if result.get('confirmed') is True and isinstance(accepted, (float,int)):
                if not self.capabilities['power_min_watts'] <= accepted <= self.capabilities['power_max_watts']:
                    raise ValueError('Bestätigter Daum-Wert liegt außerhalb der freigegebenen Grenzen')
                return result
        return dict(confirmed=False, watts=None, source=None)

    async def release(self):
        await self.device.release()


def measurement(value, unit, source, available=True, stale=False, quality=None):
    available = bool(available and value is not None)
    result = dict(value=value if available else None, unit=unit, source=source,
                  available=available, stale=bool(stale))
    if quality is not None:
        result['quality'] = quality
    return result
