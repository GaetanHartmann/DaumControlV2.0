# Architektur

## Komponenten

| Bereich | Dateien / Aufgabe |
| --- | --- |
| Web-App | `bike/frontend/src/main.ts`, `style.css`, `training-ui.ts`; Vue, SVG, WebSocket-Livewerte |
| HTTP-API | `bike/backend/main.py`; FastAPI, genau ein Worker, gemeinsamer Bike-Zustand |
| Trainingslogik | `training.py`; Vorlagen, Benutzerwerte, Watt-Skalierung und Pulsregelung |
| Bike / Sensor | `devices.py`; Daum Premium TCP und BLE Heart Rate über Bleak |
| Connector-Vertrag | `connectors.py`; Fähigkeiten, Messwertqualität und dünne Daum-Hülle |
| Statistik | `metrics.py`; zeitgewichtete Aggregate unabhängig von der Diagrammspur |
| Planung / Analyse | `cockpit.py`; Generator, persönlicher Plan, Kraftblöcke und manuelle Laufdaten |
| Zwift | `zwift.py`, `bluez.py`, `ftms.py`; experimenteller BlueZ-GATT-Server |
| Export | `exports.py`; TCX, CSV und JSON |
| Abschalteinstellung | `power_settings.py`; atomarer Austausch der gemeinsamen JSON-Konfiguration |
| Pi-Automatik | `deploy/daum-power-watch.py`; eigener Systemdienst für Linküberwachung und Herunterfahren |

## Datenfluss

Das Frontend spricht `/api/...` an und erhält Zustandsupdates über `/ws`. Der Backend-Prozess besitzt Trainingszustand und Geräteverbindungen. Eine asynchrone Sperre schützt Steuerungswechsel und Trainingsaktionen. Mehrere Backend-Worker würden mehrere unabhängige Zustände erzeugen und sind nicht vorgesehen.

SQLite speichert Benutzer, Profile, Pläne und abgeschlossene Fahrten. `GET /api/session` liefert die Werte des aktiven Benutzers gemeinsam, damit Clients keine Benutzerwerte mischen. Fahrten werden beim Beenden gespeichert; ein Prozessneustart setzt eine aktive Fahrt nicht fort.

Neue Tabellen/Spalten werden additiv und idempotent angelegt: persönliche `training_entries`, Abschlussgrund, Statistik-JSON und Aktivitätsart. Bestehende Plan- und Messspurformate bleiben lesbar. Alte Fahrten ohne Aggregation werden nicht mit erfundenen Mittelwerten ergänzt. Fehlschlagendes Speichern hält einen unveränderlichen Datensatz im Arbeitsspeicher für einen erneuten Stopp-/Speicherversuch bereit; die API bestätigt bis dahin keinen erfolgreichen Stopp für die Abschaltautomatik. Ein Prozessabbruch kann diesen Arbeitsspeicher verlieren.

`state.measurements` unterscheidet Wert, Einheit, Quelle, Verfügbarkeit und Frische. `state.completion` wird erst nach dem Datenbank-Commit veröffentlicht. Der Abschlussgrund trennt reguläres Ende, manuellen Stopp und Fehler-/Sicherheitsfälle. Statistiken integrieren nur gültige aktive Messintervalle und geben die erfasste Dauer je Messgröße an. Mechanische kJ bleiben von nicht verfügbaren Stoffwechselkalorien getrennt.

Daum-TCP und BLE-Puls werden bei Auswahl unabhängig versucht; die gemeinsame Engine-Sperre verhindert einen Trainingsstart währenddessen. Zwift-Senderarbeit folgt danach, damit keine unkoordinierten BLE-Versuche auf demselben Adapter entstehen. Strukturierte Phasen werden über den Serverlogger und als begrenzte Live-Ereignisliste bereitgestellt. Pulsgurt-Verbindung und frisches Signal sind unterschiedliche Zustände.

Der Produktname kommt aus `FITNESS_PRODUCT_NAME` (Standard Fitness-Cockpit) und `/api/config`. Bestehende Dienst-, Dateipfad- und LocalStorage-Namen bleiben kompatibel. Native Prototypen unter `spikes/` sind separate Machbarkeitsartefakte und öffnen keinen ungeschützten Sensor-Uplink zur Produkt-API.

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
- Chromium-Kiosk: auf dem geprüften Pi Desktop-Autostart mit eigenem Profil; `refresh-display.py` kann einen dedizierten temporären `daum-studio-display`-Dienst starten.
- `daum-studio-display-idle.service`: optionaler schwarzer Bildschirmschoner.
- `daum-power-watch.service`: optionaler Systemdienst; benötigt Administratorrechte zum Herunterfahren.
- `bike.db`: lokale Trainingsdatenbank.
- `/var/lib/daum-studio/power-watch.json`: vom App-Benutzer schreibbare Ein/Aus-Einstellung; der Systemdienst liest sie.

Der Abschaltdienst liest `eth0/carrier`. Unbekannter Linkstatus oder ausgeschaltete Automatik setzen den Timer zurück. Vor einem Poweroff ruft er lokal `/api/stop` auf und prüft anschließend Einstellung und Link erneut. Scheitert das Beenden/Speichern, wird das Herunterfahren zurückgestellt.

Die App startet diesen privilegierten Dienst nicht selbst und stellt keinen allgemeinen Poweroff-Endpunkt bereit. Der Desktop-Helfer verwendet dieselbe lokale Einstellungs-API wie die App.

Der Display-Starthelfer erkennt eine verfügbare Wayland-Sitzung und tatsächliche Ausgänge. Seine Aktivierung im grafischen Autostart und im Idle-Dienst verändert weder den 300-Sekunden-Bildschirmschoner noch die getrennte LAN-Abschaltfrist. Installation mit Sicherung und Rücknahme: [Deployment](change-requests/cockpit-deployment.md).
