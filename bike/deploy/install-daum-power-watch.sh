#!/bin/sh
set -eu
# Install on the Pi with sudo; the direct Daum cable must use eth0.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test -d /sys/class/net/eth0 || { echo 'eth0 fehlt; nichts installiert.' >&2; exit 1; }
install -d -m 755 /usr/local/lib/daum-studio
install -m 644 "$script_dir/daum-power-watch.py" /usr/local/lib/daum-studio/daum-power-watch.py
account=${SUDO_USER:-gha}
account_home=$(getent passwd "$account" | cut -d: -f6)
test -n "$account_home" || { echo 'Benutzerverzeichnis fehlt' >&2; exit 1; }
install -d -o "$account" -m 750 /var/lib/daum-studio
if [ ! -f /var/lib/daum-studio/power-watch.json ]; then
    printf '%s\n' '{"enabled":true}' > /var/lib/daum-studio/power-watch.json
fi
chown "$account" /var/lib/daum-studio/power-watch.json
chmod 600 /var/lib/daum-studio/power-watch.json
install -d -o "$account" -m 755 "$account_home/.local/share/daum-studio"
install -o "$account" -m 644 "$script_dir/toggle-power-watch.py" "$account_home/.local/share/daum-studio/toggle-power-watch.py"
desktop_dir=$(su -s /bin/sh "$account" -c 'xdg-user-dir DESKTOP')
test -d "$desktop_dir" || { echo 'Desktop-Verzeichnis fehlt' >&2; exit 1; }
cat > "$desktop_dir/Daum-Autoabschalten.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Daum Autoabschalten EIN-AUS
Comment=Automatisches Herunterfahren ohne Daum umschalten
Exec=/usr/bin/python3 $account_home/.local/share/daum-studio/toggle-power-watch.py
Icon=system-shutdown
Terminal=false
Categories=Utility;
DESKTOP
chown "$account" "$desktop_dir/Daum-Autoabschalten.desktop"
chmod 755 "$desktop_dir/Daum-Autoabschalten.desktop"
cat > /etc/systemd/system/daum-power-watch.service <<'UNIT'
[Unit]
Description=Daum ausschalten: Pi nach fuenf Minuten ohne direkten LAN-Link herunterfahren
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/lib/daum-studio/daum-power-watch.py --interface eth0 --delay 300
Restart=on-failure
RestartSec=30
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable daum-power-watch.service
systemctl restart daum-power-watch.service
echo 'Aktiv: nach 5 Minuten ohne eth0-Link Training speichern und Pi herunterfahren.'
echo 'Abschalten: sudo systemctl disable --now daum-power-watch.service'
echo 'App-Einstellungen oder Desktop-Button: Automatik ohne Passwort ein-/ausschalten.'
