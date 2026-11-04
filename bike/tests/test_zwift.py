import asyncio
import struct
import pytest
from backend import main
from backend.ftms import decode_control, indoor_bike_data, simulation_watts
from backend.zwift import ZwiftBridge, uuid
from fastapi.testclient import TestClient


class FakePeripheral:
    def __init__(self): self.values = {}
    def update(self, key, value): self.values[key] = value
    async def stop(self): pass


def test_control_encoding_and_validation():
    assert decode_control(b'\x05\x96\x00') == (5,150)
    assert decode_control(b'\x11'+struct.pack('<hhBB',2000,500,40,51)) == (17,dict(wind=2,grade=5,crr=.004,cw=.51))
    for packet in [b'',b'\x05',b'\x05\x00\x00',b'\x05\x91\x01',b'\x08\x03',b'\x00\x00',b'\x11\x00']:
        with pytest.raises(ValueError): decode_control(packet)


def test_metrics_layout_and_missing_heart_rate():
    state = dict(speed=28.5,cadence=82.5,power=156,heart_rate=140)
    assert struct.unpack('<HHHhB',indoor_bike_data(state)) == (580,2850,165,156,140)
    state['heart_rate'] = None
    assert struct.unpack('<HHHh',indoor_bike_data(state)) == (68,2850,165,156)


def test_slope_model_limits_and_weights():
    flat = dict(wind=0,grade=0,crr=.004,cw=.51)
    assert simulation_watts(30,80,{**flat,'grade':8}) > simulation_watts(30,80,flat)
    assert simulation_watts(30,80,{**flat,'grade':-15}) == 25
    assert simulation_watts(100,80,{**flat,'grade':20}) == 400
    assert simulation_watts(30,0,flat) == 25
    assert simulation_watts(20,80,{**flat,'grade':3},100) > simulation_watts(20,80,{**flat,'grade':3},50)


def test_external_power_ramp():
    engine = main.Engine()
    engine.target, engine.remote_target = 50, 400
    engine.update_remote_target(1)
    assert engine.target == 75
    engine.update_remote_target(.2)
    assert engine.target == 80
    engine.remote_target = 25
    engine.update_remote_target(1)
    assert engine.target == 55


def test_control_api_blocks_local_operations_and_stop_revokes(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'test.db')
    engine = main.Engine()
    monkeypatch.setattr(main,'engine',engine)
    bridge = engine.zwift = ZwiftBridge(engine)
    bridge.server = FakePeripheral()
    with TestClient(main.app) as client:
        assert client.post('/api/zwift/control',json={'enabled':True,'rider_kg':1}).status_code == 422
        assert client.post('/api/zwift/control',json={'enabled':True,'rider_kg':75}).status_code == 200
        assert engine.rider_kg == 75
        for route,body in [('start',{}),('power',{'watts':100}),('pause',{}),('mode',{'mode':'daum'})]:
            assert client.post('/api/'+route,json=body).status_code == 409
        assert client.post('/api/stop').status_code == 200
        assert not bridge.armed
        assert client.post('/api/start',json={}).status_code == 200
        assert client.post('/api/zwift/control',json={'enabled':True}).status_code == 409


def test_control_ownership_commands_disconnect_and_local_stop(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'test.db')
    main.init_db()
    async def run():
        engine = main.Engine()
        bridge = engine.zwift = ZwiftBridge(engine)
        bridge.server = FakePeripheral()
        a,b = '/org/bluez/hci0/dev_A','/org/bluez/hci0/dev_B'
        assert await bridge.control(b'\x00',a) == b'\x80\x00\x05'
        bridge.armed = True
        assert await bridge.control(b'\x05\x96\x00',a) == b'\x80\x05\x05'
        assert await bridge.control(b'\x00',a) == b'\x80\x00\x01'
        assert await bridge.control(b'\x00',b) == b'\x80\x00\x05'
        assert await bridge.control(b'\x05\x96\x00',a) == b'\x80\x05\x01'
        assert engine.remote_target == 150
        assert await bridge.control(b'\x07',a) == b'\x80\x07\x01'
        assert engine.running and engine.target == 25
        assert await bridge.control(b'\x08\x02',a) == b'\x80\x08\x01'
        assert engine.paused
        await bridge.disconnected(b)
        assert engine.running
        await bridge.disconnected(a)
        assert not engine.running and not bridge.armed and engine.control_owner=='local'
        assert await bridge.control(b'\x07',a) == b'\x80\x07\x05'
        bridge.armed = True
        await bridge.control(b'\x00',a)
        await bridge.control(b'\x07',a)
        await engine.stop()
        assert not bridge.owner and not bridge.armed
        assert bridge.server.values[uuid('2ada')] == b'\xff'
    asyncio.run(run())


def test_local_plan_cannot_be_overridden_and_failed_hardware_is_reported(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'test.db')
    main.init_db()
    async def run():
        engine = main.Engine()
        bridge = engine.zwift = ZwiftBridge(engine)
        bridge.armed = True
        engine.running = True
        assert await bridge.control(b'\x00','/client') == b'\x80\x00\x05'
        engine.running = False
        await bridge.control(b'\x00','/client')
        engine.mode,engine.connected = 'daum',False
        assert await bridge.control(b'\x07','/client') == b'\x80\x07\x04'
        assert not engine.running and not bridge.armed
        assert await bridge.control(b'\x15','/client') == b'\x80\x15\x02'
    asyncio.run(run())
