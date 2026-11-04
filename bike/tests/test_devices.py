import asyncio
import sys
from types import SimpleNamespace

import pytest

from backend.devices import Daum, HeartRate


class FakeBleakClient:
    def __init__(self, address, disconnected_callback):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self.notify = None
        self.is_connected = False
        self.disconnect_error = None
        self.connect_gate = None

    async def connect(self):
        self.is_connected = True
        if self.connect_gate:
            await self.connect_gate.wait()

    async def start_notify(self, uuid, callback):
        self.notify = callback

    async def disconnect(self):
        self.is_connected = False
        self.disconnected_callback(self)
        if self.disconnect_error:
            raise self.disconnect_error


def install_fake_bleak(monkeypatch, factory=FakeBleakClient):
    monkeypatch.setitem(sys.modules, 'bleak', SimpleNamespace(BleakClient=factory))


def test_previous_sensor_callbacks_cannot_change_replacement(monkeypatch):
    install_fake_bleak(monkeypatch)

    async def run():
        heart = HeartRate()
        await heart.connect('first')
        previous = heart.client
        previous.notify(None, bytes([0, 110]))
        assert heart.value() == 110
        await heart.connect('second')
        current = heart.client
        current.notify(None, bytes([0, 140]))
        previous.notify(None, bytes([0, 190]))
        previous.disconnected_callback(previous)
        assert heart.client is current
        assert heart.name == 'second'
        assert heart.value() == 140
        current.disconnected_callback(current)
        assert heart.client is None
        assert heart.value() is None
        assert heart.updated == 0

    asyncio.run(run())


def test_disconnect_failure_still_clears_sensor_and_ignores_late_data(monkeypatch):
    install_fake_bleak(monkeypatch)

    async def run():
        heart = HeartRate()
        await heart.connect('first')
        previous = heart.client
        previous.notify(None, bytes([0, 120]))
        previous.disconnect_error = OSError('Bluetooth failed')
        with pytest.raises(OSError, match='Bluetooth failed'):
            await heart.disconnect()
        previous.notify(None, bytes([0, 180]))
        assert heart.client is None
        assert heart.value() is None
        assert heart.name == ''
        assert heart.updated == 0

    asyncio.run(run())


def test_cancelled_connect_releases_partial_connection(monkeypatch):
    created = []

    def factory(*args, **kwargs):
        client = FakeBleakClient(*args, **kwargs)
        client.connect_gate = asyncio.Event()
        created.append(client)
        return client

    install_fake_bleak(monkeypatch, factory)

    async def run():
        heart = HeartRate()
        task = asyncio.create_task(heart.connect('first'))
        await asyncio.sleep(0)
        assert created[0].is_connected
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not created[0].is_connected
        assert heart.client is None
        assert heart.updated == 0

    asyncio.run(run())


@pytest.mark.parametrize('failure', ['reset', 'hang'])
def test_daum_close_detaches_socket_on_reset_or_timeout(monkeypatch, failure):
    class Writer:
        closed = False

        def close(self):
            self.closed = True

        async def wait_closed(self):
            if failure == 'reset':
                raise ConnectionResetError('peer reset')
            await asyncio.Event().wait()

    monkeypatch.setattr(Daum, 'CLOSE_TIMEOUT', 0.01)

    async def run():
        daum = Daum()
        writer = Writer()
        daum.writer = writer
        daum.reader = object()
        await asyncio.wait_for(daum.close(), 1)
        assert writer.closed
        assert daum.writer is None and daum.reader is None
        await daum.close()

    asyncio.run(run())
