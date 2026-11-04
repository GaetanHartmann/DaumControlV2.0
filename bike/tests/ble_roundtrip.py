"""Actual BLE central test against isolated Pi demo instance on port 8001."""
import asyncio
import struct
import json
import httpx
from bleak import BleakScanner, BleakClient
from backend.zwift import uuid

BASE='http://192.168.178.125:8001/api'


async def main():
    async with httpx.AsyncClient(timeout=25) as api:
        state=(await api.get(BASE+'/state')).json()
        assert state['mode']=='demo' and not state['running']
        response=await api.post(BASE+'/zwift/start')
        response.raise_for_status()
        print('Pi BLE advertiser started',flush=True)
        client=None
        try:
            device=await BleakScanner.find_device_by_filter(
                lambda device,adv: 'daum' in (adv.local_name or device.name or '').lower()
                or (device.address.replace(':','').lower()=='b827eb852484'),timeout=15)
            if not device:
                raise RuntimeError('DAUM Studio wurde vom Laptop-Bluetooth nicht gefunden')
            print('Peripheral found: '+device.address,flush=True)
            async with BleakClient(device,timeout=15) as client:
                responses=asyncio.Queue()
                measurements=[]
                await client.start_notify(uuid('2ad9'),lambda _,data: responses.put_nowait(bytes(data)))
                await client.start_notify(uuid('2ad2'),lambda _,data: measurements.append(bytes(data)))
                features=bytes(await client.read_gatt_char(uuid('2acc')))
                assert len(features)==8
                async def command(data,expected):
                    await client.write_gatt_char(uuid('2ad9'),data,response=True)
                    result=await asyncio.wait_for(responses.get(),8)
                    assert result==bytes([128,data[0],expected]),result.hex()
                await command(b'\x00',5)
                response=await api.post(BASE+'/zwift/control',json={'enabled':True})
                response.raise_for_status()
                await command(b'\x00',1)
                await command(b'\x05'+struct.pack('<h',60),1)
                await command(b'\x07',1)
                await asyncio.sleep(3)
                state=(await api.get(BASE+'/state')).json()
                assert state['running'] and state['control_owner']=='zwift'
                assert measurements
                await command(b'\x11'+struct.pack('<hhBB',0,200,40,51),1)
                await asyncio.sleep(1)
                assert (await api.get(BASE+'/state')).json()['zwift_detail']['mode']=='SIM'
                await api.post(BASE+'/stop')
                await command(b'\x07',5)
                print(json.dumps(dict(ble_pairing=True,ftms_indications=True,indoor_bike_notifications=len(measurements),erg=True,simulation=True,local_stop=True)),flush=True)
        finally:
            await api.post(BASE+'/stop')
            await api.post(BASE+'/zwift/stop')

asyncio.run(main())
