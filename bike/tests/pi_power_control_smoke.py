"""Explicit, supervised 25/35 W protocol test; never runs under pytest.

Run on the Pi with its live venv, on an UNUSED stationary bike:
  .venv/bin/python tests/pi_power_control_smoke.py --execute-idle-bike

Temporarily disconnects the backend (demo mode), verifies S201/S23 protocol
acknowledgements and X70 readings via the existing adapter, restores 25 W/local
control, then reconnects the original backend mode. No ride/profile is created.
Protocol ACK does not prove physical resistance while pedalling.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.connectors import DaumConnector
from backend.devices import Daum


def api(path, body=None):
    req = Request('http://127.0.0.1:8000/api/' + path,
                  data=None if body is None else json.dumps(body).encode(),
                  headers={'Content-Type':'application/json'})
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def idle(state):
    if state.get('running') or state.get('pending_save') or (state.get('zwift_detail') or {}).get('armed'):
        raise RuntimeError('Prüfung verweigert: Training/Steuerung aktiv oder Speichern ausstehend')


async def probe(connector, assert_idle):
    results = []
    connected = False
    try:
        await connector.connect()
        connected = True
        for watts in (25, 35, 25):
            assert_idle()
            result = await connector.set_power(watts)
            if not isinstance(result, dict) or result.get('confirmed') is not True or result.get('watts') != watts:
                raise RuntimeError('Keine nachgewiesene Protokollbestätigung')
            telemetry = await connector.read()
            results.append(dict(requested_watts=watts, acknowledgement=result,
                                measured_watts=telemetry.get('power'), reported_power_watts=telemetry.get('reported_power'), cadence=telemetry.get('cadence')))
        return results
    finally:
        try:
            if connected:
                # This recovery also runs if the intermediate read/ACK fails.
                try:
                    await connector.set_power(25)
                finally:
                    await connector.release()
        finally:
            await connector.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-idle-bike', action='store_true',
                        help='Bestätigt: Bike steht still, ist unbenutzt, 25/35 W-Test ist ausdrücklich freigegeben')
    args = parser.parse_args()
    state = api('state')
    idle(state)
    if not args.execute_idle_bike:
        print(json.dumps(dict(executed=False, writes=[25,35,25], commands=['S201','S23<watts>','S200'],
                              requirement='Ausdrückliche Freigabe und unbenutztes stillstehendes Bike erforderlich')))
        return
    original_mode, user_id = state['mode'], state['user_id']
    # API mode changes only disconnect/connect; they do not start a workout.
    api('mode', {'mode':'demo', 'expected_user_id':user_id})
    try:
        result = asyncio.run(asyncio.wait_for(probe(DaumConnector(Daum()), lambda: idle(api('state'))), 45))
        print(json.dumps(dict(executed=True, protocol_test=result,
                              physical_resistance_verified=False, workout_started=False)))
    finally:
        latest = api('state')
        if not latest.get('running') and latest.get('user_id') == user_id and original_mode != 'demo':
            api('mode', {'mode':original_mode, 'expected_user_id':user_id})


if __name__ == '__main__':
    main()
