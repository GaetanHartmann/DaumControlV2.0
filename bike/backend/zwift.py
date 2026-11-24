"""FTMS trainer, Cycling Power and Heart Rate peripheral for Zwift."""
import struct
import sys
import time
import contextlib
from .ftms import decode_control, indoor_bike_data, telemetry_value, SUCCESS, UNSUPPORTED, INVALID, FAILED, DENIED


def uuid(short):
    return f'0000{short}-0000-1000-8000-00805f9b34fb'


class ZwiftBridge:
    def __init__(self, engine):
        self.engine = engine
        self.server = None
        self.status = 'Aus'
        self.owner = None
        self.armed = False
        self.last_command = self.last_result = ''
        self.commands = 0
        self.revolutions = 0.0
        self.event_time = 0
        self.last_update = None
        self.last_features = None

    def features(self):
        """Measurement support is independent of accepting a target-power write."""
        simulated = getattr(self.engine, 'mode', None) == 'demo'
        connector = getattr(self.engine, 'connector', None)
        capabilities = getattr(connector, 'capabilities', {})
        reads = capabilities.get('read', [])
        quality = capabilities.get('measurement_quality') or {}
        measured_power = (simulated or ('power' in reads and
                          capabilities.get('measured_power_supported', True) is True and
                          capabilities.get('power_quality') != 'device_reported_unverified' and
                          quality.get('power') != 'device_reported_unverified'))
        measurement_flags = (1 << 10)  # An independent BLE heart-rate sensor can be added.
        if simulated or 'cadence' in reads:
            measurement_flags |= 1 << 1
        if measured_power:
            measurement_flags |= 1 << 14
        control_flags = ((1 << 3) | (1 << 13)) if simulated or 'power' in capabilities.get('control', []) else 0
        return struct.pack('<II', measurement_flags, control_flags)

    def details(self):
        return dict(active=self.server is not None, armed=self.armed, owner=self.owner,
                    mode=self.engine.remote_mode, grade=self.engine.simulation['grade'],
                    requested_power=self.engine.remote_target, applied_power=getattr(self.engine, 'applied_target_watts', None),
                    last_command=self.last_command, last_result=self.last_result, commands=self.commands,
                    rider_kg=self.engine.rider_kg, bike_kg=self.engine.bike_kg)

    async def start(self):
        if sys.platform != 'linux':
            raise RuntimeError('Der Zwift-Sender läuft auf dem Linux-Pi; Laptop dient zur Entwicklung')
        from .bluez import Peripheral
        self.server = Peripheral(self.disconnected)
        ftms = self.server.service(uuid('1826'))
        self.last_features = self.features()
        self.server.characteristic(ftms, uuid('2acc'), ['read'], self.last_features)
        self.server.characteristic(ftms, uuid('2ad2'), ['notify'], indoor_bike_data(self.engine.snapshot()))
        self.server.characteristic(ftms, uuid('2ad8'), ['read'], struct.pack('<hhH',25,400,1))
        self.server.characteristic(ftms, uuid('2ad9'), ['write','indicate'], write=self.control, lost=self.connection_lost)
        self.server.characteristic(ftms, uuid('2ada'), ['notify'], b'\x01')
        cps = self.server.service(uuid('1818'))
        self.server.characteristic(cps, uuid('2a65'), ['read'], struct.pack('<I',8))
        self.server.characteristic(cps, uuid('2a5d'), ['read'], b'\x0d')
        # No initial zero-power measurement: notify only after a known sample.
        self.server.characteristic(cps, uuid('2a63'), ['notify'])
        hr = self.server.service(uuid('180d'))
        self.server.characteristic(hr, uuid('2a37'), ['notify'])
        try:
            await self.server.start()
        except Exception:
            await self.server.stop()
            self.server = None
            raise
        self.status = 'Sendet · FTMS bereit'

    async def control(self, data, peer):
        opcode = data[0] if data else 0
        try:
            opcode, value = decode_control(data)
        except ValueError:
            return bytes([0x80,opcode,INVALID])
        if opcode not in (0,1,5,7,8,17):
            return bytes([0x80,opcode,UNSUPPORTED])
        async with self.engine.lock:
            result = DENIED
            if peer != '/' and self.armed and (self.owner is None or self.owner == peer):
                if opcode == 0:
                    if not self.engine.running or self.engine.control_owner == 'zwift':
                        self.owner = peer
                        self.engine.control_owner = 'zwift'
                        self.status = 'Sendet · Zwift steuert'
                        result = SUCCESS
                elif self.owner == peer:
                    try:
                        await self.engine.remote_command(opcode,value)
                        result = SUCCESS
                    except Exception as exc:
                        self.engine.error = f'Zwift-Befehl fehlgeschlagen: {exc}'
                        await self.engine.stop()
                        result = FAILED
            self.commands += 1
            self.last_command = {0:'Steuerung anfordern',1:'Zurücksetzen',5:'Zielleistung',7:'Start / Weiter',8:'Stopp / Pause',17:'Streckensimulation'}[opcode]
            self.last_result = {SUCCESS:'Bestätigt',DENIED:'Steuerung nicht freigegeben',FAILED:'Fehler'}[result]
            if result == SUCCESS and opcode != 0 and self.server:
                if opcode == 1: status = b'\x01'
                elif opcode == 5: status = b'\x08'+struct.pack('<h',value)
                elif opcode == 7: status = b'\x04'
                elif opcode == 8: status = bytes([2,value])
                else: status = b'\x12'+data[1:]
                self.server.update(uuid('2ada'),status)
            return bytes([0x80,opcode,result])

    def revoke(self):
        had_owner = self.owner is not None
        self.owner, self.armed = None, False
        self.engine.control_owner = 'local'
        if self.server:
            self.status = 'Sendet · Steuerung gesperrt'
            if had_owner:
                with contextlib.suppress(Exception):
                    self.server.update(uuid('2ada'),b'\xff')

    async def connection_lost(self):
        async with self.engine.lock:
            if self.owner:
                await self.engine.stop()
                self.engine.error = 'Zwift-Verbindung beendet. Training gestoppt; Steuerung erneut freigeben.'

    async def disconnected(self,peer):
        if self.owner == peer:
            await self.connection_lost()

    def publish(self,state):
        if not self.server:
            return
        features = self.features()
        if features != self.last_features:
            # Keep subsequent feature reads honest after switching demo/device.
            # Clients caching features still need to reconnect the sender.
            self.server.update(uuid('2acc'), features)
            self.last_features = features
        now = time.monotonic()
        dt = min(3,now-self.last_update) if self.last_update else 0
        self.last_update = now
        cadence = telemetry_value(state, 'cadence')
        if cadence is not None:
            previous = int(self.revolutions)
            self.revolutions += cadence*dt/60
            if int(self.revolutions)>previous and cadence:
                self.event_time = int((now-(self.revolutions%1)*60/cadence)*1024)%65536
        power = telemetry_value(state, 'power')
        if power is not None:
            flags = 32 if cadence is not None else 0
            packet = struct.pack('<Hh', flags, max(-32768, min(32767, round(power))))
            if cadence is not None:
                packet += struct.pack('<HH', int(self.revolutions)%65536, self.event_time)
            self.server.update(uuid('2a63'), packet)
        ftms = indoor_bike_data(state)
        if ftms:
            self.server.update(uuid('2ad2'), ftms)
        hr = telemetry_value(state, 'heart_rate')
        if hr is not None:
            self.server.update(uuid('2a37'),bytes([0,max(0,min(255,round(hr)))]))

    async def stop(self):
        self.revoke()
        if self.server:
            await self.server.stop()
            self.server = None
        self.status = 'Aus'
