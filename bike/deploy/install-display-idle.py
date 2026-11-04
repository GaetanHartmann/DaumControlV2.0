"""Install a five-minute black display saver while preserving the HDMI signal.

Run as desktop user, with display-black-overlay.py beside this installer.
HDMI and the backlight stay powered, avoiding the monitor's No Signal OSD.
"""
from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


def ensure_layer_typelib(destination):
    check = ['python3', '-c', "import gi; gi.require_version('GtkLayerShell', '0.1')"]
    paths = list((destination / 'vendor/usr/lib').glob('*/girepository-1.0'))
    env = {**os.environ, 'GI_TYPELIB_PATH': os.pathsep.join(map(str, paths))}
    if subprocess.run(check, env=env, capture_output=True).returncode == 0:
        return
    # Fetch just the matching GIR from official configured APT repositories.
    version = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}', 'libgtk-layer-shell0'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='daum-layer-shell-') as directory:
        subprocess.run(['apt-get', 'download', 'gir1.2-gtklayershell-0.1=' + version], cwd=directory, check=True)
        package = next(Path(directory).glob('gir1.2-gtklayershell-0.1_*.deb'))
        subprocess.run(['dpkg-deb', '--extract', str(package), str(destination / 'vendor')], check=True)
    paths = list((destination / 'vendor/usr/lib').glob('*/girepository-1.0'))
    env = {**os.environ, 'GI_TYPELIB_PATH': os.pathsep.join(map(str, paths))}
    subprocess.run(check, env=env, check=True)


def install():
    if os.getuid() == 0:
        raise SystemExit('Run as the logged-in desktop user, not root.')
    for program in ('swayidle', 'wlopm', 'systemctl', 'python3'):
        if shutil.which(program) is None:
            raise SystemExit(f'Missing program: {program}')
    source = Path(__file__).resolve().with_name('display-black-overlay.py')
    if not source.exists():
        raise SystemExit('Place display-black-overlay.py beside this installer.')
    destination = Path.home() / '.local/share/daum-studio/display-idle'
    destination.mkdir(parents=True, exist_ok=True)
    ensure_layer_typelib(destination)
    unit = Path.home() / '.config/systemd/user/daum-studio-display-idle.service'
    blank = unit.with_name('daum-studio-display-blank.service')
    autostart = Path.home() / '.config/autostart/daum-studio-display-idle.desktop'
    helper = destination / source.name
    backup = Path.home() / '.local/share/daum-studio/display-idle-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    for path in (unit, blank, autostart, helper):
        if path.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup / path.name)
        path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, helper)
    blank.write_text('''[Unit]
Description=DAUM black Wayland display overlay with touch wake

[Service]
Type=simple
Environment=XDG_RUNTIME_DIR=%t
Environment=WAYLAND_DISPLAY=wayland-0
Environment=GDK_BACKEND=wayland
ExecStart=/usr/bin/python3 %h/.local/share/daum-studio/display-idle/display-black-overlay.py
ExecStopPost=/usr/bin/rm -f %t/daum-display-saver.ready
TimeoutStopSec=4
''', encoding='utf-8')
    unit.write_text('''[Unit]
Description=DAUM black display saver after five idle minutes

[Service]
Type=simple
Environment=XDG_RUNTIME_DIR=%t
Environment=WAYLAND_DISPLAY=wayland-0
ExecStart=/usr/bin/swayidle -w -C /dev/null timeout 300 "/usr/bin/systemctl --user start daum-studio-display-blank.service" resume "/usr/bin/systemctl --user kill --kill-whom=main --signal=USR1 daum-studio-display-blank.service 2>/dev/null || true"
ExecStopPost=-/usr/bin/systemctl --user stop daum-studio-display-blank.service
ExecStopPost=-/usr/bin/wlopm --on HDMI-A-1
Restart=on-failure
RestartSec=3
TimeoutStopSec=5
''', encoding='utf-8')
    # Raspberry Pi labwc does not activate graphical-session.target here.
    autostart.write_text('''[Desktop Entry]
Type=Application
Name=DAUM black display saver
Comment=Black screen after five idle minutes; touch to wake, HDMI stays active
Exec=/usr/bin/systemctl --user restart daum-studio-display-idle.service
Terminal=false
NoDisplay=true
''', encoding='utf-8')
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'restart', unit.name], check=True)
    subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit.name], check=True)
    print('Black display saver installed: 300 seconds; HDMI/backlight stay powered.')
    if backup.exists():
        print('Backup:', backup)


if __name__ == '__main__':
    install()
