# Installation

## Voraussetzungen

Die Entwicklung und Prüfung erfolgten mit Python 3.13 unter Windows und auf einem ARM64-Pi. Für das Frontend werden Node.js und npm benötigt. Die getestete Hardware ist unter [Hardwarebasis](HARDWARE.md) beschrieben.

```sh
git clone https://github.com/GaetanHartmann/DaumControlV2.0.git
cd DaumControlV2.0/bike
```

## Windows

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`http://127.0.0.1:8000` öffnen. In einem zusätzlichen Terminal kann `npm.cmd --prefix frontend run dev` die Entwicklungsansicht unter Port 5173 starten; Vite leitet API und WebSocket an Port 8000 weiter.

## Raspberry Pi

Linux mit funktionierendem Netzwerk, BlueZ und Python-Venv-Unterstützung vorbereiten. Für das lokale Display werden zusätzlich Chromium und ein Desktop benötigt. Nur die Backend-Funktion kann auch ohne Display laufen.

Die vorhandenen Servicevorlagen verwenden den Benutzer `gha` und das Verzeichnis `/home/gha/daum-studio`. Entweder diese Struktur verwenden oder alle Pfade in den Vorlagen anpassen. Das Verzeichnis `bike` aus dem Checkout enthält die eigentliche App und wird als `daum-studio` installiert.

```sh
cd /home/gha/daum-studio
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Das Frontend kann auf dem Entwicklungsrechner mit `npm ci` und `npm run build` gebaut werden. Den Inhalt von `frontend/dist` mit übertragen; npm ist dann für den laufenden Pi-Server nicht erforderlich.

```sh
mkdir -p ~/.config/systemd/user
cp deploy/daum-studio.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now daum-studio.service
sudo loginctl enable-linger gha
```

Genau ein Backend-Worker darf das Bike und den Trainingszustand besitzen. Auf dem Pi erreichbar unter `http://ghapi3.local:8000`, die API-Dokumentation unter `/docs`.

## Bike-LAN und Bluetooth

Die direkten LAN-Adressen und Cockpit-Einstellungen stehen in [Hardwarebasis](HARDWARE.md). `deploy/configure-pi.sh` ist ein Helfer für die vorhandene NetworkManager-Verbindung `netplan-eth0`; auf einer anderen Installation zuerst den tatsächlichen Verbindungsnamen prüfen. WLAN und dessen Standardroute sollen erhalten bleiben.

## Optionale Abschaltautomatik

Nach Installation der App als Administrator auf dem Pi:

```sh
sudo sh deploy/install-daum-power-watch.sh
systemctl status daum-power-watch.service
```

Der Installer benötigt `eth0`, einen Desktop-Benutzer und `xdg-user-dir`. Er installiert den Systemdienst, die Konfiguration unter `/var/lib/daum-studio/power-watch.json` und die Desktop-Verknüpfung. Die Automatik ist nach der ersten Installation eingeschaltet. Weitere Umschaltungen über App oder Desktop benötigen kein Passwort.

```sh
sudo systemctl disable --now daum-power-watch.service
```

Dieser Befehl deaktiviert den gesamten Dienst. Für normales Ein/Aus besser den App-Schalter verwenden, damit er ohne erneute Administrator-Anmeldung wieder eingeschaltet werden kann.

## Updates und Sicherung

Vor einem Update Training beenden und Zwift-Steuerung sperren. Den Dienst stoppen, `bike.db` separat sichern, Backend und Frontend-Build aktualisieren und wieder starten. Der vorhandene `deploy/install-profile-update.py` führt einen solchen Austausch samt Code- und SQLite-Sicherung für ein vorbereitetes Staging-Verzeichnis durch; seine Pfadprüfungen beachten.

`bike.db` und `/var/lib/daum-studio/power-watch.json` sind Laufzeitdaten und gehören nicht in Git. Während eines laufenden Trainings keinen App-Neustart durchführen: aktive Trainings werden nach einem Neustart nicht automatisch fortgesetzt.
