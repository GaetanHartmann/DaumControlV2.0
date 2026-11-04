"""Direct BlueZ peripheral. https://bluez.readthedocs.io/en/latest/gatt-api/"""
import asyncio
import contextlib
from dbus_next import Variant, DBusError, Message
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType, PropertyAccess, MessageType
from dbus_next.service import ServiceInterface, method, dbus_property


class Service(ServiceInterface):
    def __init__(self, path, uuid):
        super().__init__('org.bluez.GattService1')
        self.path, self.uuid = path, uuid

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> 's': return self.uuid

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> 'b': return True

    def properties(self):
        return {'UUID':Variant('s',self.uuid),'Primary':Variant('b',True)}


class Characteristic(ServiceInterface):
    def __init__(self, path, service, uuid, flags, value=b'', write=None, lost=None):
        super().__init__('org.bluez.GattCharacteristic1')
        self.path, self.service, self.uuid, self.flags = path, service, uuid, flags
        self.value, self.notifying = bytes(value), False
        self.write, self.lost = write, lost
        self.lock = asyncio.Lock()
        self.indication_pending = False
        self.confirm_timer = None

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> 's': return self.uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> 'o': return self.service

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> 'as': return self.flags

    @dbus_property(access=PropertyAccess.READ)
    def Value(self) -> 'ay': return self.value

    @dbus_property(access=PropertyAccess.READ)
    def Notifying(self) -> 'b': return self.notifying

    @method()
    def ReadValue(self, options: 'a{sv}') -> 'ay':
        if 'read' not in self.flags:
            raise DBusError('org.bluez.Error.NotPermitted','Not readable')
        return self.value[options.get('offset',Variant('q',0)).value:]

    @method()
    async def WriteValue(self, value: 'ay', options: 'a{sv}'):
        if not self.write or not self.notifying:
            raise DBusError('org.bluez.Error.NotPermitted','Subscribe to indications first')
        if self.lock.locked() or self.indication_pending:
            raise DBusError('org.bluez.Error.InProgress','Previous procedure not confirmed')
        if options.get('offset',Variant('q',0)).value:
            raise DBusError('org.bluez.Error.InvalidOffset','Offset writes unsupported')
        async with self.lock:
            result = await self.write(bytes(value),options.get('device',Variant('o','/')).value)
            self.indication_pending = True
            self.confirm_timer = asyncio.get_running_loop().call_later(10,self._timeout)
            self.update(result)

    def _timeout(self):
        self.indication_pending = False
        if self.lost:
            asyncio.create_task(self.lost())

    @method()
    def Confirm(self):
        self.indication_pending = False
        if self.confirm_timer:
            self.confirm_timer.cancel()

    @method()
    def StartNotify(self):
        self.notifying = True
        self.emit_properties_changed({'Notifying':True})

    @method()
    def StopNotify(self):
        self.notifying = False
        self.Confirm()
        self.emit_properties_changed({'Notifying':False})
        if self.lost:
            asyncio.create_task(self.lost())

    def update(self,value):
        self.value = bytes(value)
        if self.notifying:
            self.emit_properties_changed({'Value':self.value})

    def properties(self):
        return {'UUID':Variant('s',self.uuid),'Service':Variant('o',self.service),
                'Flags':Variant('as',self.flags),'Value':Variant('ay',self.value),'Notifying':Variant('b',self.notifying)}


class Application(ServiceInterface):
    def __init__(self,objects):
        super().__init__('org.freedesktop.DBus.ObjectManager')
        self.objects = objects

    @method()
    def GetManagedObjects(self) -> 'a{oa{sa{sv}}}':
        return {obj.path:{obj.name:obj.properties()} for obj in self.objects}


class Advertisement(ServiceInterface):
    def __init__(self,uuids):
        super().__init__('org.bluez.LEAdvertisement1')
        self.uuids = uuids

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> 's': return 'peripheral'

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> 'as': return self.uuids

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> 's': return 'DAUM Studio'

    @dbus_property(access=PropertyAccess.READ)
    def ServiceData(self) -> 'a{sv}':
        return {'00001826-0000-1000-8000-00805f9b34fb':Variant('ay',b'\x01\x20\x00')}

    @method()
    def Release(self): pass


class Peripheral:
    ROOT, ADV = '/org/daumstudio/gatt', '/org/daumstudio/advertisement'

    def __init__(self,disconnected):
        self.bus = None
        self.objects, self.chars, self.uuids = [],{},[]
        self.disconnected = disconnected
        self.gatt = self.advertising = None
        self.gatt_registered = self.advertisement_registered = False

    def service(self,uuid):
        obj = Service(f'{self.ROOT}/service{len(self.uuids)}',uuid)
        self.objects.append(obj)
        self.uuids.append(uuid)
        return obj.path

    def characteristic(self,service,uuid,flags,value=b'',write=None,lost=None):
        obj = Characteristic(f'{service}/char{len(self.chars)}',service,uuid,flags,value,write,lost)
        self.objects.append(obj)
        self.chars[uuid] = obj

    async def start(self):
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        proxy = self.bus.get_proxy_object('org.bluez','/',await self.bus.introspect('org.bluez','/'))
        objects = await proxy.get_interface('org.freedesktop.DBus.ObjectManager').call_get_managed_objects()
        adapter = next((p for p,i in objects.items() if 'org.bluez.GattManager1' in i and 'org.bluez.LEAdvertisingManager1' in i),None)
        if not adapter:
            raise RuntimeError('Bluetooth-Adapter unterstützt keinen GATT-Server')
        if not objects[adapter]['org.bluez.Adapter1']['Powered'].value:
            raise RuntimeError('Bluetooth am Pi ist ausgeschaltet')
        proxy = self.bus.get_proxy_object('org.bluez',adapter,await self.bus.introspect('org.bluez',adapter))
        self.gatt = proxy.get_interface('org.bluez.GattManager1')
        self.advertising = proxy.get_interface('org.bluez.LEAdvertisingManager1')
        self.bus.export(self.ROOT,Application(self.objects))
        for obj in self.objects:
            self.bus.export(obj.path,obj)
        self.bus.export(self.ADV,Advertisement(self.uuids))
        self.bus.add_message_handler(self._signal)
        match = "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'"
        await self.bus.call(Message(destination='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='AddMatch',signature='s',body=[match]))
        await self.gatt.call_register_application(self.ROOT,{})
        self.gatt_registered = True
        await self.advertising.call_register_advertisement(self.ADV,{})
        self.advertisement_registered = True

    def _signal(self,msg):
        if (msg.message_type == MessageType.SIGNAL and msg.interface == 'org.freedesktop.DBus.Properties'
                and msg.member == 'PropertiesChanged' and msg.body[0] == 'org.bluez.Device1'):
            connected = msg.body[1].get('Connected')
            if connected is not None and not connected.value:
                asyncio.create_task(self.disconnected(msg.path))

    def update(self,uuid,value):
        self.chars[uuid].update(value)

    async def stop(self):
        for char in self.chars.values():
            if char.confirm_timer:
                char.confirm_timer.cancel()
        if self.bus:
            if self.advertisement_registered:
                with contextlib.suppress(Exception):
                    await self.advertising.call_unregister_advertisement(self.ADV)
            if self.gatt_registered:
                with contextlib.suppress(Exception):
                    await self.gatt.call_unregister_application(self.ROOT)
            self.bus.disconnect()
            self.bus = None
