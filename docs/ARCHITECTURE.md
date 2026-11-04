# Architektur

## Komponenten

| Bereich | Dateien / Aufgabe |
| --- | --- |
| Web-App | `bike/frontend/src/main.ts`, `style.css`, `training-ui.ts`; Vue, SVG, WebSocket-Livewerte |
| HTTP-API | `bike/backend/main.py`; FastAPI, genau ein Worker, gemeinsamer Bike-Zustand |
| Trainingslogik | `training.py`; Vorlagen, Benutzerwerte, Watt-Skalierung und Pulsregelung |
| Bike / Sensor | `devices.py`; Daum Premium TCP und BLE Heart Rate über Bleak |
| Zwift | `zwift.py`, `bluez.py`, `ftms.py`; experimenteller BlueZ-GATT-Server |
| Export | `exports.py`; TCX, CSV und JSON |
| Abschalteinstellung | `power_settings.py`; atomarer Austausch der gemeinsamen JSON-Konfiguration |
| Pi-Automatik | `deploy/daum-power-watch.py`; eigener Systemdienst für Linküberwachung und Herunterfahren |

## Datenfluss

Das Frontend spricht `/api/...` an und erhält Zustandsupdates über `/ws`. Der Backend-Prozess besitzt Trainingszustand und Geräteverbindungen. Eine asynchrone Sperre schützt Steuerungswechsel und Trainingsaktionen. Mehrere Backend-Worker würden mehrere unabhängige Zustände erzeugen und sind nicht vorgesehen.

SQLite speichert Benutzer, Profile, Pläne und abgeschlossene Fahrten. `GET /api/session` liefert die Werte des aktiven Benutzers gemeinsam, damit Clients keine Benutzerwerte mischen. Fahrten werden beim Beenden gespeichert; ein Prozessneustart setzt eine aktive Fahrt nicht fort.

## Wichtige Schnittstellen

| Endpoint | Zweck |
| --- | --- |
| `GET /api/session`, `GET /api/state` | Daten und Livezustand |
| `POST /api/start`, `/api/pause`, `/api/stop` | Training steuern |
| `POST /api/profile` | Profilwerte speichern |
| `GET /api/rides` | Aktivitäten des aktiven Benutzers |
| `POST /api/rides/{id}/delete` | Fahrt des aktiven Benutzers löschen |
| `GET /api/rides/{id}/export/{tcx,csv,json}` | Aktivität exportieren |
| `GET/POST /api/power-settings` | Installationsstatus und Ein/Aus der Abschaltautomatik |

Die vollständige Schnittstellenbeschreibung wird vom laufenden Backend unter `/docs` erzeugt. Benutzerprofile sind eine Auswahl für ein gemeinsam benutztes Bike, keine Anmeldung oder Zugriffstrennung.

## Dienste und Laufzeitdateien

- `daum-studio.service`: Backend als Benutzer-Service.
- `daum-studio-display.service`: dedizierter Chromium-Kioskprozess.
- `daum-studio-display-idle.service`: optionaler schwarzer Bildschirmschoner.
- `daum-power-watch.service`: optionaler Systemdienst; benötigt Administratorrechte zum Herunterfahren.
- `bike.db`: lokale Trainingsdatenbank.
- `/var/lib/daum-studio/power-watch.json`: vom App-Benutzer schreibbare Ein/Aus-Einstellung; der Systemdienst liest sie.

Der Abschaltdienst liest `eth0/carrier`. Unbekannter Linkstatus oder ausgeschaltete Automatik setzen den Timer zurück. Vor einem Poweroff ruft er lokal `/api/stop` auf und prüft anschließend Einstellung und Link erneut. Scheitert das Beenden/Speichern, wird das Herunterfahren zurückgestellt.

Die App startet diesen privilegierten Dienst nicht selbst und stellt keinen allgemeinen Poweroff-Endpunkt bereit. Der Desktop-Helfer verwendet dieselbe lokale Einstellungs-API wie die App.
