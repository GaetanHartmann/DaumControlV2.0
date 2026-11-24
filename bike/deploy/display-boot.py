"""Recover the local display once the graphical session is ready.

Run as the desktop user, never as root. Discovers the compositor socket and
output names instead of assuming wayland-0 / HDMI-A-1. Does not touch the LAN
shutdown service, its configuration, or the 300-second timers.
"""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import time


LOG = logging.getLogger('fitness-display-boot')
IDLE = 'daum-studio-display-idle.service'
BLANK = 'daum-studio-display-blank.service'


def session_environment(environ, runtime):
    """Only use a real socket owned by this runtime, never a stale lock file."""
    env = dict(environ)
    env['XDG_RUNTIME_DIR'] = str(runtime)
    preferred = env.get('WAYLAND_DISPLAY', '')
    if preferred and (runtime / preferred).is_socket():
        return env
    sockets = sorted(p for p in runtime.glob('wayland-*') if p.is_socket())
    if len(sockets) != 1:
        raise RuntimeError('Grafische Sitzung noch nicht bereit oder mehrere Wayland-Sitzungen; WAYLAND_DISPLAY eindeutig setzen')
    env['WAYLAND_DISPLAY'] = sockets[0].name
    return env


def output_names(text):
    names = []
    for line in text.splitlines():
        match = re.fullmatch(r'\s*([A-Za-z0-9_.:-]+)\s+(?:on|off)\s*', line)
        if match:
            names.append(match[1])
    return list(dict.fromkeys(names))


def run(command, env):
    return subprocess.run(command, env=env, check=True, capture_output=True,
                          text=True, timeout=5)


def wait_for_outputs(environ, runtime, seconds=30, runner=run, now=time.monotonic, sleep=time.sleep):
    deadline = now() + seconds
    while True:
        try:
            env = session_environment(environ, runtime)
            outputs = output_names(runner(['wlopm'], env).stdout)
            if outputs:
                return env, outputs
            reason = 'Compositor meldet noch keine Ausgänge'
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            reason = str(error)
        if now() >= deadline:
            raise RuntimeError('Display-Start abgebrochen: ' + reason)
        sleep(min(1, max(0, deadline - now())))


def recover(env, outputs, runner=run, start_idle=False, dry_run=False):
    """One-shot restoration; never start, stop or reconfigure the power watch."""
    commands = [['systemctl', '--user', 'stop', BLANK]]
    commands += [['wlopm', '--on', name] for name in outputs]
    if start_idle:
        commands += [
            ['systemctl', '--user', 'import-environment', 'XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY'],
            ['systemctl', '--user', 'restart', IDLE],
        ]
    for command in commands:
        LOG.info('Display-Start: %s', ' '.join(command))
        if not dry_run:
            runner(command, env)
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-idle', action='store_true', help='Nach grafischem Login den Idle-Dienst mit der erkannten Sitzung starten')
    parser.add_argument('--wait', type=int, default=30)
    parser.add_argument('--dry-run', action='store_true', help='Nur Sitzung und Ausgänge lesen; keine Änderung')
    args = parser.parse_args()
    if os.name != 'posix' or os.getuid() == 0:
        parser.error('Als angemeldeter Linux-Desktop-Benutzer ausführen, nicht als root')
    if not 0 <= args.wait <= 120:
        parser.error('--wait muss zwischen 0 und 120 Sekunden liegen')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    try:
        env, outputs = wait_for_outputs(os.environ, runtime, args.wait)
        recover(env, outputs, start_idle=args.start_idle, dry_run=args.dry_run)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        LOG.error('%s', error)
        raise SystemExit(1)
    print(json.dumps(dict(wayland_display=env['WAYLAND_DISPLAY'], outputs=outputs, dry_run=args.dry_run)))


if __name__ == '__main__':
    main()
