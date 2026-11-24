# Fitness-Cockpit

Lokales, erweiterbares Trainingscockpit mit bestehender Anbindung an den **Daum Premium 8i** und einen **Raspberry Pi 3 B+**. Das Bike verbindet sich per direktem LAN mit dem Pi; bedient wird es am Touchdisplay oder im Browser über WLAN. Fitness-Cockpit ist der vorläufige Produktname und über `FITNESS_PRODUCT_NAME` anpassbar. Repository- und Dienstnamen bleiben für vorhandene Installationen kompatibel.

Version **2.0.0** · [MIT-Lizenz](LICENSE) · [Release Notes](RELEASE_NOTES.md)

## Funktionen

- Freies Watttraining und Trainingspläne von 20 bis 60 Minuten, auch ohne FTP und Pulsgurt.
- Sechs virtuelle Bergstrecken mit Auffahrten, Abfahrten und abgestuften Wattkurven.
- Zeitachse mit einstellbarem Zeit-/Wattraster, Stufendauer und Livewerten.
- Benutzerprofile, persönliche Leistungsanpassung und optionale Pulssteuerung mit Bluetooth-Sensor.
- Aktivitäten mit TCX-, CSV- und JSON-Export sowie Löschen einzelner Fahrten.
- Optionales Herunterfahren nach fünf Minuten ohne Daum-LAN; Schalter in der App und auf dem Pi-Desktop.
- Demo-Modus und experimentelle Zwift-FTMS-Anbindung über Bluetooth.
- Kompakte Trainingswerte mit Quellenangaben, schaltbare Watt-/Pulswerte am Zeitmarker und gespeicherte Abschlussauswertung.
- Trainingsgenerator, persönlicher Trainingsplan, optionale Kraftblöcke und manuelle Laufbanderfassung.
- Herstellerunabhängiger Connector-Vertrag; Apple-/mobile Sensorbrücken liegen als gesonderte, noch nicht am Gerät geprüfte Spikes vor.
- Eigenständiger Trainingskatalog, dauerhafte Live-Wattanpassung mit Rückkehr zum aktuellen Plan und lokaler/optional externer Trainingscoach.

## Dokumentation

| Thema | Anleitung |
| --- | --- |
| Hardware, Kabel und Netzwerk | [Hardwarebasis](docs/HARDWARE.md) |
| Windows-Entwicklung und Raspberry-Pi-Installation | [Installation](docs/INSTALLATION.md) |
| Training, Profile, Export und Abschaltautomatik | [Bedienung](docs/USER_GUIDE.md) |
| Tests und optionale Garmin-Validierung | [Tests](docs/TESTING.md) |
| Backend, Daten und Dienste | [Architektur](docs/ARCHITECTURE.md) |
| Generator, Auswertung, persönlicher Plan und Laufband | [Fitness-Cockpit](docs/FITNESS_COCKPIT.md) |
| Änderungspaket, Tests und verbleibende Hardwareabnahme | [Umsetzungsstand](docs/change-requests/implementation-status.md) |
| Trainingskatalog, manuelle Live-Wattsteuerung und Coach | [P0/P1-Umsetzung](docs/change-requests/p0-p1-implementation-2026-11-09.md) |
| Ausführliche Protokoll- und Trainingshinweise | [Technische Dokumentation](bike/README.md) |
| Abhängigkeiten und Fremdmaterial | [Lizenzhinweise](THIRD_PARTY_NOTICES.md) |

## Schnellstart unter Windows

Python 3.13 und Node.js mit npm müssen installiert sein. Im geklonten Repository:

```powershell
cd bike
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Danach `http://127.0.0.1:8000` öffnen. Der erste Start verwendet Demo-Daten. Die App ist für ein vertrauenswürdiges Heimnetz vorgesehen und implementiert keine Benutzeranmeldung. Keine direkte Internetfreigabe des laufenden Servers einrichten.

Ohne FTP werden sichtbar gekennzeichnete Beispiel-Wattwerte verwendet; es wird keine FTP geschätzt oder im Profil erfunden. Die lokalen Bergstrecken sind zeitbasierte Wattprogramme mit virtuellen Steigungen. Ein echter Bike-Stopp kann bei Verbindungsverlust nicht garantiert werden; das Cockpit muss bedienbar bleiben.

Persönliche Trainingsdatenbanken, Zugangsschlüssel, virtuelle Umgebungen, Build-Ausgaben und erzeugte Screenshots bleiben außerhalb von Git. Die Skripte für den bestehenden Pi verwenden teilweise den Beispielbenutzer `gha` und lokale Pfade; vor Nutzung an die eigene Installation anpassen.
