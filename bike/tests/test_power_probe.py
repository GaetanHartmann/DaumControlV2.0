import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


spec = importlib.util.spec_from_file_location('power_probe', Path(__file__).with_name('pi_power_control_smoke.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def connector():
    class Connector:
        connect = AsyncMock()
        close = AsyncMock()
        release = AsyncMock()
        read = AsyncMock(return_value={'power':0,'cadence':0})
        set_power = AsyncMock(side_effect=lambda watts:dict(confirmed=True, watts=watts, source='protocol_ack'))
    return Connector()


def test_supervised_probe_preserves_real_zero_and_restores_local_control():
    device = connector()
    values = asyncio.run(probe.probe(device, lambda:None))
    assert [v['requested_watts'] for v in values] == [25,35,25]
    assert values[1]['measured_watts'] == 0  # Never equate the ACK with measured W.
    assert device.set_power.await_args_list[-1].args == (25,)
    device.release.assert_awaited_once()
    device.close.assert_awaited_once()


def test_failed_real_probe_read_still_requests_safe_minimum_and_release():
    device = connector()
    device.read.side_effect = TimeoutError('no telemetry')
    with pytest.raises(TimeoutError):
        asyncio.run(probe.probe(device, lambda:None))
    assert device.set_power.await_args_list[-1].args == (25,)
    device.release.assert_awaited_once()
    device.close.assert_awaited_once()
