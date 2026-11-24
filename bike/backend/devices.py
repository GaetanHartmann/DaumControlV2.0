"""Daum Premium ASCII framing and BLE Heart Rate Service.

Protocol references: https://github.com/incyclist/devices (MIT),
https://ackstorm.de/projects/daum/daum.html . Independently implemented.
"""
import asyncio
import contextlib
import math
import time


def frame(command: str) -> bytes:
    payload = command.encode('ascii')
    return b'\x01' + payload + f'{sum(payload) % 100:02}'.encode() + b'\x17'


def parse_training(payload: str) -> dict:
    fields = payload.split('\x1d')
    if len(fields) < 7:
        raise ValueError('Unvollständige Daum-Messdaten')
    return dict(power=round(float(fields[6])), cadence=round(float(fields[5])),
                speed=round(float(fields[2]) * 3.6, 1))


def parse_heart_rate(data: bytes) -> int:
    if len(data) < 2 or (data[0] & 1 and len(data) < 3):
        raise ValueError('Unvollständiges Pulssignal')
    return int.from_bytes(data[1:3], 'little') if data[0] & 1 else data[1]


class Daum:
    CLOSE_TIMEOUT = 2

    def __init__(self):
        self.reader = self.writer = None
        self.lock = asyncio.Lock()
        self.power_guard = None

    async def connect(self):
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection('192.168.10.1', 51955), 5)
        try:
            return await self.command('V00')
        except Exception:
            await self.close()
            raise

    async def command(self, command):
        async with self.lock:
            if not self.writer:
                raise ConnectionError('Daum ist nicht verbunden')
            self.writer.write(frame(command))
            await self.writer.drain()
            if await asyncio.wait_for(self.reader.readexactly(1), 4) != b'\x06':
                raise ConnectionError('Daum hat den Befehl nicht bestätigt')
            response = await asyncio.wait_for(self.reader.readuntil(b'\x17'), 4)
            if not response.startswith(b'\x01') or len(response) < 7:
                raise ValueError('Ungültiger Daum-Antwortrahmen')
            body, checksum = response[1:-3], response[-3:-1]
            if checksum != f'{sum(body) % 100:02}'.encode() or body[:3] != command[:3].encode():
                self.writer.write(b'\x15')
                await self.writer.drain()
                raise ValueError('Daum-Prüfsumme oder Antwortbefehl ungültig')
            self.writer.write(b'\x06')
            await self.writer.drain()
            return body[3:].decode('ascii')

    async def set_power(self, watts):
        control = await self.command('S201')
        if control.strip() != '1':
            raise ConnectionError('Daum hat die Laststeuerung nicht bestätigt')
        # S201 can wait for a network reply. Re-check the current request before
        # actually writing S23 so a superseded slider/stop request is not sent.
        if self.power_guard is not None and not self.power_guard():
            return False
        echo = await self.command(f'S23{watts:.2f}')
        # SP-KOMM-PM1 §1.2: the response payload is the accepted value and may
        # differ from the request. A transport ACK alone is not that value.
        try:
            accepted = float(echo.strip())
        except (TypeError, ValueError):
            return dict(confirmed=False, watts=None, source=None)
        if not math.isfinite(accepted) or accepted < 0:
            raise ValueError('Ungültige Watt-Rückmeldung vom Daum')
        return dict(confirmed=True, watts=accepted, source='protocol_ack', detail='echoed_value')

    async def release(self):
        if self.writer:
            await self.command('S200')

    async def close(self):
        async with self.lock:
            writer = self.writer
            self.reader = self.writer = None
            if writer:
                with contextlib.suppress(OSError, asyncio.TimeoutError):
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), self.CLOSE_TIMEOUT)


class HeartRate:
    UUID = '00002a37-0000-1000-8000-00805f9b34fb'
    RETRY_DELAY = 5

    def __init__(self):
        self.client = None
        self.bpm = None
        self.updated = 0
        self.name = ''
        self._generation = 0
        self.reconnect_address = None
        self.reconnect_task = None

    async def scan(self):
        from bleak import BleakScanner
        found = await BleakScanner.discover(timeout=6, return_adv=True)
        return [dict(address=d.address, name=d.name or a.local_name or 'Pulssensor')
                for d, a in found.values()
                if '0000180d-0000-1000-8000-00805f9b34fb' in (a.service_uuids or [])]

    async def connect(self, address):
        await self.disconnect()
        self.reconnect_address = address
        await self._connect(address)

    async def _connect(self, address):
        from bleak import BleakClient
        generation = self._generation
        client = BleakClient(address, disconnected_callback=lambda source: self._disconnected(source, generation))
        self.client = client
        try:
            await client.connect()
            await client.start_notify(self.UUID, lambda sender, data: self._notify_current(client, generation, sender, data))
            if self.client is not client or self._generation != generation:
                raise ConnectionError('Pulssensor-Verbindung wurde zwischenzeitlich getrennt')
            self.name = address
        except BaseException:
            # A cancelled connect must release its BLE connection too. An old
            # request may clean up only its own client, never a replacement.
            with contextlib.suppress(Exception):
                if self.client is client and self._generation == generation:
                    self.client = None
                    self._generation += 1
                    self._clear()
                    await client.disconnect()
                else:
                    await client.disconnect()
            raise

    def _clear(self):
        self.bpm = None
        self.updated = 0
        self.name = ''

    def _disconnected(self, client, generation):
        if self.client is client and self._generation == generation:
            self.client = None
            self._generation += 1
            self._clear()
            if self.reconnect_address and not (self.reconnect_task and not self.reconnect_task.done()):
                self.reconnect_task = asyncio.create_task(self._reconnect())

    async def _reconnect(self):
        while self.reconnect_address and self.client is None:
            await asyncio.sleep(self.RETRY_DELAY)
            address = self.reconnect_address
            if not address:
                return
            try:
                await asyncio.wait_for(self._connect(address), 20)
                return
            except Exception:
                continue

    def _notify_current(self, client, generation, sender, data):
        if self.client is client and self._generation == generation:
            self._notify(sender, data)

    def _notify(self, _, data):
        try:
            self.bpm = parse_heart_rate(data)
            self.updated = time.monotonic()
        except ValueError:
            pass

    def value(self):
        return self.bpm if time.monotonic() - self.updated < 10 else None

    def age(self):
        return time.monotonic()-self.updated if self.updated else float('inf')

    async def disconnect(self):
        self.reconnect_address = None
        task, self.reconnect_task = self.reconnect_task, None
        if task and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        client = self.client
        self.client = None
        self._generation += 1
        generation = self._generation
        self._clear()
        try:
            if client:
                await client.disconnect()
        finally:
            if self._generation == generation and self.client is None:
                self._clear()
