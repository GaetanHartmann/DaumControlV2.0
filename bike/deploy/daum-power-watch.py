"""Power off after sustained loss of the direct Daum Ethernet link.

Installed as a root system service. Does not provide Wake-on-LAN.
"""
import argparse
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen


class LinkTimer:
    def __init__(self, delay):
        self.delay = delay
        self.missing_since = None

    def update(self, carrier, now):
        # An unavailable/unknown interface is a configuration error, not bike off.
        if carrier is not False:
            self.missing_since = None
            return False
        if self.missing_since is None:
            self.missing_since = now
        return now - self.missing_since >= self.delay


def read_carrier(path):
    try:
        value = path.read_text().strip()
        return value == '1' if value in ('0', '1') else None
    except OSError:
        return None


def auto_off_enabled(path):
    try:
        return json.loads(path.read_text())['enabled'] is True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def stop_training(base):
    # Never power off until the app confirms that training was stopped/saved.
    request = Request(base + '/api/stop', data=b'{}',
                      headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=20) as response:
        state = json.load(response)
    if state.get('running') is not False:
        raise RuntimeError('App hat das Trainingsende nicht bestätigt')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', default='eth0')
    parser.add_argument('--delay', type=int, default=300)
    parser.add_argument('--config', type=Path, default=Path('/var/lib/daum-studio/power-watch.json'))
    parser.add_argument('--dry-run', action='store_true', help='Nur protokollieren, weder Training stoppen noch herunterfahren')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Nur für den Linux-Pi vorgesehen')
    if args.delay < 60 or '/' in args.interface or args.interface in ('', '.', '..'):
        parser.error('Mindestens 60 Sekunden und einen gültigen Schnittstellennamen angeben')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    carrier_path = Path('/sys/class/net') / args.interface / 'carrier'
    if not carrier_path.exists():
        parser.error(f'LAN-Schnittstelle fehlt: {carrier_path}')
    timer = LinkTimer(args.delay)
    previous = object()
    logging.info('Daum-LAN-Überwachung: %s, Wartezeit %s s, Testmodus %s', args.interface, args.delay, args.dry_run)
    while True:
        carrier = read_carrier(carrier_path)
        if carrier != previous:
            logging.info('LAN-Status: %s', {True: 'verbunden', False: 'getrennt', None: 'unbekannt, kein Abschalten'}[carrier])
            previous = carrier
        enabled = auto_off_enabled(args.config)
        if timer.update(carrier if enabled else True, time.monotonic()):
            try:
                if args.dry_run:
                    logging.info('Testmodus: würde jetzt das Training speichern und den Pi herunterfahren')
                else:
                    stop_training('http://127.0.0.1:8000')
                    # The bike may have returned while the app saved the ride.
                    if read_carrier(carrier_path) is not False or not auto_off_enabled(args.config):
                        timer.update(True, time.monotonic())
                        continue
                    logging.info('Training beendet. Pi wird heruntergefahren.')
                    subprocess.run(['systemctl', 'poweroff'], check=True, timeout=30)
                    return
            except Exception:
                logging.exception('Abschalten zurückgestellt; erneuter Versuch nach Ablauf der Wartezeit')
            timer.missing_since = time.monotonic()
        time.sleep(5)


if __name__ == '__main__':
    main()
