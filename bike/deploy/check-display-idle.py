"""Prove black overlay, HDMI signal, and wake-tap absorption on an idle bike.

The test injects ADS7846 touch input, including a held contact. It does not
start a training. It always restores the visible UI and 300-second idle timer.
"""
import fcntl
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
from urllib.request import urlopen
from PIL import Image

UNIT = 'daum-studio-display-idle.service'
BLANK = 'daum-studio-display-blank.service'
ENV = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}', 'WAYLAND_DISPLAY': 'wayland-0'}
READY = Path(ENV['XDG_RUNTIME_DIR']) / 'daum-display-saver.ready'


def assert_hdmi_on():
    state = subprocess.check_output(['wlopm'], env=ENV, text=True)
    assert 'HDMI-A-1 on' in state.splitlines(), state


def image_is_black(path):
    subprocess.run(['grim', str(path)], env=ENV, check=True)
    with Image.open(path) as image:
        return all(hi == 0 for _, hi in image.convert('RGB').getextrema())


def wait_ready(ready):
    for _ in range(100):
        if READY.exists() == ready:
            return
        time.sleep(.1)
    status = subprocess.run(['systemctl','--user','status',BLANK,'--no-pager'], capture_output=True, text=True)
    raise RuntimeError(f'Overlay did not reach expected ready={ready}:\n' + status.stdout + status.stderr)


def check():
    state = json.load(urlopen('http://127.0.0.1:8000/api/state', timeout=5))
    if state['running'] or (state.get('zwift_detail') or {}).get('armed'):
        raise SystemExit('Display test skipped: training or Zwift control is active.')
    try:
        subprocess.run(['systemctl','--user','restart',UNIT], check=True)
        time.sleep(1)  # Let swayidle register its compositor idle notifications.
        subprocess.run(['systemctl','--user','kill','--kill-whom=main','--signal=USR1',UNIT], check=True)
        wait_ready(True)
        time.sleep(.6)
        with tempfile.TemporaryDirectory(prefix='daum-blank-check-') as directory:
            capture = Path(directory) / 'screen.png'
            assert READY.exists(), 'Overlay dismissed itself without user input'
            assert image_is_black(capture), 'Overlay did not cover the display with solid black'
            assert_hdmi_on()
            print('Verified: solid black fullscreen, HDMI-A-1 on, no immediate auto-wake', flush=True)
            event = struct.Struct('llHHi')
            device_path = '/dev/input/by-path/platform-3f204000.spi-cs-1-event'
            with open(device_path, 'r+b', buffering=0) as device:
                xinfo, yinfo = bytearray(24), bytearray(24)
                fcntl.ioctl(device.fileno(), 0x80184540, xinfo)
                fcntl.ioctl(device.fileno(), 0x80184541, yinfo)
                xmin, ymin = struct.unpack('6i', xinfo)[1], struct.unpack('6i', yinfo)[1]
                def send(events):
                    now = time.time()
                    sec, usec = int(now), int((now % 1) * 1_000_000)
                    device.write(b''.join(event.pack(sec,usec,kind,code,value) for kind,code,value in events))
                try:
                    send([(3,0,xmin),(3,1,ymin),(3,24,50),(1,330,1),(0,0,0)])
                    time.sleep(.8)
                    assert READY.exists(), 'Overlay disappeared while waking touch was held'
                    assert image_is_black(capture), 'Held waking touch exposed underlying controls'
                    assert_hdmi_on()
                    print('Verified: held ADS7846 touch stays absorbed by black overlay', flush=True)
                finally:
                    send([(3,24,0),(1,330,0),(0,0,0)])
            wait_ready(False)
            assert_hdmi_on()
            assert not image_is_black(capture), 'UI did not return after releasing wake touch'
            assert not json.load(urlopen('http://127.0.0.1:8000/api/state', timeout=5))['running']
            print('Verified: releasing wake touch restores UI; no training started', flush=True)
    finally:
        subprocess.run(['systemctl','--user','stop',BLANK], check=True)
        subprocess.run(['wlopm','--on','HDMI-A-1'], env=ENV, check=True)
        subprocess.run(['systemctl','--user','restart',UNIT], check=True)
        print('Restored: visible UI, HDMI on, normal idle timeout 300 seconds', flush=True)


if __name__ == '__main__':
    check()
