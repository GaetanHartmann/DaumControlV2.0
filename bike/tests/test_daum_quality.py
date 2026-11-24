"""Unknown X70 load must never become independently measured mechanical work."""
import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.connectors import DaumConnector
from backend.devices import Daum
from backend.metrics import normalize_summary


def wire(cadence,power):
    return '\x1d'.join(map(str,[2180,0,0.00,0,18178,cadence,power,196.4,965.1,119.4,0,0,0]))


@pytest.mark.parametrize('cadence',[0,80])
def test_x70_raw_power_is_not_independently_measured_even_with_cadence(cadence):
    async def run():
        device=Daum()
        device.command=AsyncMock(return_value=wire(cadence,35))
        data=await DaumConnector(device).read()
        assert data['reported_power']==35
        assert data['power'] is None and data['cadence']==cadence
    asyncio.run(run())


def test_normalized_idle_telemetry_has_no_power_coverage_or_mechanical_energy(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'idle.db')
    main.init_db()
    async def run():
        engine=main.Engine()
        engine.mode,engine.running,engine.connected,engine.user_id='daum',True,True,1
        engine.elapsed=10
        engine.daum.command=AsyncMock(return_value=wire(0,35))
        data=await engine.connector.read()
        engine.available_metrics={key for key,value in data.items() if value is not None}
        for key,value in data.items():setattr(engine,key,value)
        engine.last_measurement_at=time.monotonic()
        engine.metrics.add(10, data['power'],None,data['cadence'])
        state=engine.snapshot()
        assert state['measured_watts'] is None and state['measurements']['power']['value'] is None
        assert state['measurements']['reported_power']['value']==35
        assert state['energy'] is None
        assert engine.measurement()[12]==35 and engine.measurement()[1] is None
        engine.daum.set_power=AsyncMock(return_value=dict(confirmed=True,watts=25,source='protocol_ack',detail='echoed_value'))
        engine.daum.release=AsyncMock()
        await engine.stop()
        summary=engine.completion['summary']
        assert summary['averages']['power_watts'] is None
        assert summary['coverage_seconds']['power_watts']==0
        assert summary['mechanical_energy_kj'] is None and summary['power_measurement_verified'] is False
        with main.database() as db:
            assert db.execute('SELECT energy FROM rides').fetchone()[0] is None
    asyncio.run(run())


def test_s23_echoed_nearest_value_is_shown_separately_without_retry_flood():
    async def run():
        engine=main.Engine()
        engine.mode,engine.running,engine.connected='daum',True,True
        engine.daum.command=AsyncMock(side_effect=['1','35.00'])
        engine.request_target(37,'manual_button',manual=True)
        await engine.flush_target(force=True)
        assert engine.target==37 and engine.applied_target_watts==35
        assert engine.target_command_status=='adjusted'
        assert engine.target_confirmation_detail=='echoed_value'
        await engine.flush_target(force=True)
        assert engine.daum.command.await_count==2
        engine.request_target(37,'manual_slider',manual=True)
        assert engine.target_command_status=='adjusted'
    asyncio.run(run())


def test_transport_ack_without_s23_value_never_confirms_requested_watts():
    async def run():
        engine=main.Engine()
        engine.mode,engine.running,engine.connected='daum',True,True
        engine.daum.command=AsyncMock(side_effect=['1',''])
        engine.request_target(35,'manual_button',manual=True)
        await engine.flush_target(force=True)
        assert engine.applied_target_watts is None
        assert engine.target_command_status=='unconfirmed'
    asyncio.run(run())


def test_declined_control_does_not_send_s23():
    async def run():
        device=Daum()
        device.command=AsyncMock(return_value='0')
        with pytest.raises(ConnectionError):await DaumConnector(device).set_power(35)
        device.command.assert_awaited_once_with('S201')
    asyncio.run(run())


def test_legacy_daum_read_normalization_preserves_raw_without_rewriting_database(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB',tmp_path/'legacy.db')
    monkeypatch.setattr(main,'engine',main.Engine())
    with TestClient(main.app) as client:
        original=dict(averages={'power_watts':150,'heart_rate_bpm':120},coverage_seconds={'power_watts':300},mechanical_energy_kj=45)
        with main.database() as db:
            db.execute('INSERT INTO rides(seconds,distance,energy,mode,user_id,summary_json) VALUES(?,?,?,?,?,?)',
                       (300,2,45,'daum',main.engine.user_id,json.dumps(original)))
        ride=client.get('/api/rides').json()[0]
        assert ride['energy'] is None and ride['reported_unverified_energy_kj']==45
        assert ride['summary']['averages']['power_watts'] is None
        assert ride['summary']['reported_unverified_power_watts']==150
        with main.database() as db:
            stored=db.execute('SELECT energy,summary_json FROM rides').fetchone()
            assert stored[0]==45 and json.loads(stored[1])==original


def test_explicit_verified_provenance_remains_usable_for_future_real_power_sensor():
    summary=dict(averages={'power_watts':150},mechanical_energy_kj=45,power_measurement_verified=True,
                 measurement_quality={'power_watts':'verified_measured'})
    assert normalize_summary(summary,'daum')==summary
