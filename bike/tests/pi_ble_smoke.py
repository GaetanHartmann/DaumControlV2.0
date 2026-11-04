"""Exercise actual BlueZ registration without pairing or controlling a bike."""
import asyncio
import json
from backend.main import Engine
from backend.zwift import ZwiftBridge,uuid


async def main():
    engine=Engine()
    bridge=engine.zwift=ZwiftBridge(engine)
    try:
        await bridge.start()
        bridge.publish(engine.snapshot())
        server=bridge.server
        objects={obj.path:obj.properties() for obj in server.objects}
        cp=server.chars[uuid('2ad9')]
        assert set(cp.flags)=={'write','indicate'}
        print(json.dumps(dict(registered=server.gatt_registered,advertising=server.advertisement_registered,
                              gatt_objects=len(objects),ftms=True,cps=True,heart_rate=True,armed=bridge.armed)))
    finally:
        await bridge.stop()

asyncio.run(main())
