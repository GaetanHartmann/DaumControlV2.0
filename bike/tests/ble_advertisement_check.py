import asyncio
import json
import httpx
from bleak import BleakScanner

async def main():
    async with httpx.AsyncClient(timeout=20) as api:
        (await api.post('http://192.168.178.125:8001/api/zwift/start')).raise_for_status()
        try:
            found=await BleakScanner.discover(timeout=6,return_adv=True)
            for device,adv in found.values():
                if device.address=='B8:27:EB:85:24:84':
                    print(json.dumps({'advertised_name':adv.local_name,'service_uuids':adv.service_uuids,'service_data':{k:v.hex() for k,v in adv.service_data.items()}}))
                    assert adv.local_name=='DAUM Studio'
                    assert '00001826-0000-1000-8000-00805f9b34fb' in adv.service_uuids
                    break
            else:
                raise AssertionError('Pi advertisement not found')
        finally:
            await api.post('http://192.168.178.125:8001/api/zwift/stop')

asyncio.run(main())
