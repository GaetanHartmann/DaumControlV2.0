# CR-05: Display beim grafischen Start aktivieren

Stand: 2026-11-09. Implementierung geprüft und mit Sicherung auf dem Pi installiert; Kaltstartabnahme noch offen.

## Beobachtungen am vorhandenen Pi

Rein lesender SSH-Zugriff auf `gha@ghapi3.local` gelang mit dem vorhandenen expliziten SSH-Schlüssel. Zum Prüfzeitpunkt:

- labwc lief; Chromium wurde direkt durch einen Desktop-Autostart mit eigenem Browserprofil gestartet, unter X11/XWayland.
- `wlopm` meldete `HDMI-A-1 on`; der schwarze Overlay-Dienst war inaktiv.
- `daum-studio-display-idle.service` lief. Ein dauerhafter `daum-studio-display.service` war nicht installiert.
- Idle-Start enthielt bisher keine Displayaktivierung; `wlopm --on HDMI-A-1` stand nur im Stop-Nachlauf.
- `daum-power-watch.service` lief mit `--interface eth0 --delay 300`.
- Zweite reine Leseprüfung bei eingeschaltetem Pi/Daum: `/api/state` lieferte `mode=demo`, `running=false`, `connected=false`, `hr_connected=false`, kein Fehler, Zwift aus. `eth0/carrier=1`: Kabelverbindung vorhanden, aber die App hatte noch keine Daum-TCP-Verbindung gewählt. Daraus folgt kein Hardwaredefekt.
- Backend meldete v2.0.0; `backend/devices.py` auf dem Pi entsprach per SHA-256 dem unveränderten lokalen Protokolladapter. Die neue Implementierung war zu diesem Zeitpunkt noch nicht ausgerollt.
- Kein brauchbares vorheriges Bootjournal war verfügbar. Die Uhr-/Journalzeit war nicht konsistent mit der gemeldeten Uptime; daraus werden keine Bootzeitdiagnosen abgeleitet.

Ein aktuell eingeschalteter HDMI-Ausgang bestätigt nicht die Ursache des früheren dunklen Displays. Backlight-Hardware ist nicht eindeutig identifiziert. Es wurden weder Konfiguration noch Dienste oder Trainingszustand verändert.

Die vorstehenden Beobachtungen stammen aus der ursprünglichen rein lesenden Diagnose. Nach Freigabe wurde das Änderungspaket einschließlich Displayhelfer installiert: beide Dienste aktiv, HDMI-A-1 eingeschaltet und Abschalteinstellung unverändert. Sicherung und genaue Abnahme stehen im [Umsetzungsbericht](implementation-status.md). Ein Neustart oder echtes Poweroff wurden weiterhin nicht ausgeführt.

## Änderung

`bike/deploy/display-boot.py` wartet begrenzt auf eine echte Wayland-Socketdatei und Ausgänge des Compositors. Die vorhandene Sitzungsvariable hat Vorrang; bei mehreren nicht eindeutig zugeordneten Sitzungen bricht der Helfer verständlich ab. Er stoppt das schwarze Overlay, schaltet die vom Compositor gemeldeten Ausgänge ein und kann anschließend die tatsächliche Sitzungsumgebung in den User-Service-Manager übernehmen und den Idle-Dienst starten.

`install-display-idle.py` kopiert den Helfer mit, sichert bestehende Dateien und bindet ihn vor dem Idle-Start, beim Stop-Nachlauf und in den Desktop-Autostart ein. Harte Annahmen `wayland-0` und `HDMI-A-1` entfallen in diesen Units. Die bestehende Chromium-Autostartdatei wird nicht ersetzt.

Der Helfer verändert keine LAN-Abschalteinstellung und keine 300-Sekunden-Frist. Er schreibt nicht blind in unbekannte Backlight-Sysfs-Dateien. Falls HDMI eingeschaltet ist, das Panel aber physikalisch dunkel bleibt, ist eine separate Untersuchung von Stromversorgung und Backlight erforderlich.

## Installation und Rückweg

Im bestehenden Pi-Checkout als angemeldeter Desktop-Benutzer, mit sichtbarer grafischer Sitzung:

```sh
python3 deploy/display-boot.py --dry-run
python3 deploy/install-display-idle.py
systemctl --user status daum-studio-display-idle.service --no-pager
```

Der Dry-run liest nur Sitzung/Ausgänge. Installation startet den Bildschirmschoner neu, beendet ein eventuell sichtbares schwarzes Overlay und aktiviert Ausgänge. Vor einer Installation daher keine aktive Trainingseinheit verwenden.

Der Installer meldet ein Sicherungsverzeichnis unter `~/.local/share/daum-studio/display-idle-backups/`. Zur Rücknahme den Idle-Dienst stoppen, die gesicherten gleichnamigen Dateien an ihre bisherigen Ziele zurückkopieren (Units nach `~/.config/systemd/user/`, `.desktop` nach `~/.config/autostart/`, Python-Helfer nach `~/.local/share/daum-studio/display-idle/`), neu hinzugefügten Helfer entfernen und `systemctl --user daemon-reload` ausführen. Danach den ursprünglichen Idle-Autostart wieder starten. `daum-power-watch.service` bleibt unberührt.

## Prüfung

Lokal sechs Tests in `bike/tests/test_display_boot.py`: unterschiedliche Anschlüsse, ungültige Ausgabezeilen, Dry-run ohne Mutationen, fehlender Compositor mit begrenzter Wartezeit, verzögerte Bereitschaft und Erhalt der Timer. Auf dem Pi bestand die gesamte bereitgestellte Suite mit 104 bestandenen Tests und einem optional übersprungenen Schema-Test.

Nach Installation lief der Idle-Dienst mit dem neuen `ExecStartPre`, weiterhin `timeout 300`, und `wlopm` meldete `HDMI-A-1 on`. Der lokale Chromium wurde ausschließlich über sein dediziertes App-Profil neu geladen; eine Bildschirmaufnahme bestätigte anschließend die sichtbare Cockpitoberfläche bei 800×480. Der LAN-Abschaltkonfigurationshash blieb unverändert. Kein Neustart/Poweroff oder Trainingsstart wurde ausgelöst; daher keine reale Kaltstartabnahme behauptet. Details im [Deploymentprotokoll](cockpit-deployment.md).

Auf Hardware noch zu prüfen: Kaltstart, Reboot, Start nach automatischem Herunterfahren, mit/ohne Bike-LAN, Ausfall grafischer Sitzung, Berühren nach schwarzem Overlay und unverändertes Poweroff erst nach 300 s ohne LAN-Träger. `deploy/check-display-idle.py` ergänzt Overlay-/Touchprüfung, ersetzt keinen Boottest.
