"""Refresh only the dedicated DAUM browser profile, never personal Chromium."""
import os
from pathlib import Path
import signal
import shlex
import subprocess
import time

profile='--user-data-dir=/home/gha/.config/daum-studio-browser'
subprocess.run(['systemctl','--user','stop','daum-studio-display'],capture_output=True)
for process in Path('/proc').iterdir():
    if not process.name.isdigit():
        continue
    try:
        raw=(process/'cmdline').read_bytes().rstrip(b'\0')
        args=raw.decode(errors='replace').split('\0')
        # Chromium may rewrite argv into one process-title string.
        if len(args)==1:
            args=shlex.split(args[0])
        executable=os.readlink(process/'exe')
        if (profile in args and executable.endswith('/chromium')
                and not any(arg.startswith('--type=') for arg in args)):
            os.kill(int(process.name),signal.SIGTERM)
            for _ in range(50):
                if not process.exists() or not (process/'cmdline').read_bytes():
                    break
                time.sleep(.1)
    except (OSError,ProcessLookupError,ValueError):
        pass
subprocess.run(['systemd-run','--user','--collect','--unit=daum-studio-display',
    '/usr/bin/chromium','--ozone-platform=x11','--kiosk','--no-first-run','--no-default-browser-check',
    '--password-store=basic','--disable-gpu','--disable-extensions',profile,'http://127.0.0.1:8000'],check=True)
