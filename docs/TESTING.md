# Tests

Alle Befehle für Backend-Tests werden aus dem Verzeichnis `bike` ausgeführt. Dafür die gleiche virtuelle Umgebung wie für die App verwenden.

```powershell
.venv\Scripts\python -m pytest -q tests --import-mode=importlib
npm.cmd --prefix frontend run build
```

Auf dem Pi:

```sh
.venv/bin/python -m pytest -q tests --import-mode=importlib
```

Die explizite Angabe `tests` vermeidet Konflikte mit alten Testdateien außerhalb dieses Verzeichnisses. Tests benutzen temporäre SQLite-Dateien und gemockte Geräte. Sie starten kein echtes Bike-Training.

## Optionaler TCX-Schematest

`lxml` und Garmins Originalschema sind optional. Das Schema wird wegen ungeklärter Weitergabelizenz nicht mit dem Repository verteilt. Es kann für die lokale Prüfung separat von Garmin heruntergeladen werden:

```powershell
.venv\Scripts\python -m pip install lxml
.venv\Scripts\python -c "from pathlib import Path; from urllib.request import urlretrieve; p=Path('tests/fixtures'); p.mkdir(exist_ok=True); urlretrieve('https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd', str(p/'TrainingCenterDatabasev2.xsd'))"
```

Die heruntergeladene Datei wird von Git ignoriert. Ohne Schema oder lxml wird ausschließlich der zusätzliche Schema-Validierungstest übersprungen; die übrigen Exporttests prüfen weiterhin Struktur und Inhalte.

## Browserprüfungen

Die Browser-Skripte verwenden Playwright mit Microsoft Edge und sind für den Windows-Entwicklungsrechner eingerichtet:

```powershell
.venv\Scripts\python -m pip install playwright
```

Einen isolierten Demo-Server mit frischer Datenbank verwenden. Der Vorlagen-/Timeline-Prüfer setzt außerdem eine eigene, temporäre Power-Konfigurationsdatei voraus; niemals gegen eine aktive Trainingsinstallation ausführen.

```powershell
$env:BIKE_DB = Join-Path $env:TEMP 'daum-browser-test.db'
$env:BIKE_POWER_CONFIG = Join-Path $env:TEMP 'daum-browser-power.json'
Set-Content -LiteralPath $env:BIKE_POWER_CONFIG -Value '{"enabled":true}'
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8019
```

In einem weiteren Terminal:

```powershell
$env:BIKE_TEST_URL = 'http://127.0.0.1:8019'
.venv\Scripts\python tests/browser_timeline_check.py
.venv\Scripts\python tests/browser_profiles_check.py
```

Der Timeline-Prüfer startet und löscht eine kurze Demo-Fahrt. Der Profil-Prüfer legt Testbenutzer an. `browser_deployed_check.py` prüft dagegen lesend das bereits installierte Pi-Frontend und startet keine Fahrt.

## Stand der Prüfung zu 2.0.0

- Windows: 62 Backend-Tests bestanden, einschließlich optionaler Schema-Prüfung mit lokalem Schema und lxml.
- ARM64-Pi: 61 bestanden, ein optionaler Schema-Test wegen fehlendem lxml übersprungen.
- Browser: Desktop, Pi-Auflösung 800 × 480 und Smartphonebreite 390 px; Raster, Stufendauern, Start ohne FTP/Pulsgurt, Ride-Löschen und Abschaltschalter geprüft.
- Bereitgestelltes Pi-Frontend und Desktop-Umschaltung separat geprüft.

Automatisches reales Ausschalten, eine vollständige pulsgeführte Fahrt und Training in der Zwift-App wurden in dieser Prüfung nicht erzwungen. Diese Prüfungen ersetzen keinen Praxistest am eigenen Gerät.
