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

## Fitness-Cockpit-Erweiterungen, 2026-11-09

- Windows: 107 Backend-/Deployment-/Spike-Tests bestanden; bestehende httpx-Deprecation-Warnung.
- Vite-Produktionsbuild und zusätzlicher TypeScript-Typcheck bestanden.
- Bestehende Browserprüfungen für Timeline und persönliche Wattprofile bestanden.
- Neuer Browserablauf: Generatorvorschau/Speichern, persönliche Profilfelder, Planer/Kraftmodul einschließlich Bearbeitung/Fortschritt, manuelle Laufdaten, fehlende Werte/Exporte, persistente Markerschalter sowie regulärer Abschluss einer tatsächlichen zehnsekündigen Demo-Einheit.
- Alle sechs Messkacheln bei aktivem Training ohne Scrollen im Viewport: 800 × 480 und 1024 × 768; 390 × 844 ohne horizontalen Seitenüberlauf. Smartphone darf vertikal scrollen. Keine JavaScript-Laufzeitfehler in den geprüften Abläufen.

Der neue Test startet mit `--serve` selbst einen temporären Demo-Server und beendet ihn anschließend. Er verweigert fremde Hosts und die Wiederverwendung einer laufenden Installation:

```powershell
$env:BIKE_TEST_URL = 'http://127.0.0.1:8027'
.venv\Scripts\python tests/browser_cockpit_check.py --serve
frontend\node_modules\.bin\tsc.cmd --noEmit --target ES2022 --module ESNext --moduleResolution bundler --skipLibCheck --allowSyntheticDefaultImports frontend/src/main.ts frontend/src/training-ui.ts frontend/src/cockpit-features.ts
```

Screenshots werden ins temporäre Betriebssystemverzeichnis geschrieben. Reale Pulsgurt-, Boot-/Poweroff- und Apple-Gerätetests bleiben getrennt; ihr Stand steht im [Umsetzungsbericht](change-requests/implementation-status.md).

## Trainingskatalog, Coach und laufende Wattsteuerung

Der anschließende P0/P1-Auftrag erweitert die Suite auf **165 bestandene Tests**.
Neu sind unter anderem dauerhafter manueller Override, Segmentwechsel/Rückkehr,
Pausenvorbereitung, neueste Vorgabe bei laufendem Modus-ACK, Stoppriorität,
Sitzungswechsel, Nutzer-/Gerätegrenzen und fehlende Bestätigung. Katalog-/Coachtests
prüfen Revisionen, Benutzerzuordnung, erneute Validierung nach Änderungen,
Einwilligung und manipulierte/nicht endliche KI-Ausgaben.

Zusätzlich zum bisherigen Cockpit-Prüfer laufen diese isolierten Browserprüfungen:

```powershell
.venv\Scripts\python tests/browser_catalog_coach_check.py --serve
.venv\Scripts\python tests/browser_live_power_check.py --serve
.venv\Scripts\python tests/browser_routes_check.py
```

Alle drei starten ausschließlich eigene temporäre Loopback-Server. Es werden keine
realen Geräte verbunden und keine Daten an einen externen Coach übertragen. Der
Streckenprüfer importiert ausdrücklich eine Testgeometrie; er ist kein Nachweis
einer geografisch geprüften Straßenroute oder eines 3D-Renderers.

`tests/pi_power_control_smoke.py` ist **kein** automatisch ausgeführter Test. Sein
Standardmodus liest nur Zustand und zeigt die beabsichtigten Befehle. Das Flag
`--execute-idle-bike` setzt eine ausdrückliche Freigabe für ein stillstehendes,
unbenutztes Gerät voraus. Es prüft echte Adapter-ACKs bei 25/35/25 W und danach lokale
Kontrollfreigabe; es legt keine Trainingsdaten an. Eine Protokollbestätigung wird
nicht als Nachweis tatsächlicher Leistung beim Treten bezeichnet.

Aktueller [Übergabe-/Abnahmestand](change-requests/p0-p1-implementation-2026-11-09.md).

Ergänzung vom 09.11.: [Getrennte Vollbildansichten und echte Offline-Strecken](change-requests/fullscreen-and-route-material-2026-11-09.md). Aktuell 208 Windows-Tests und 205 Pi-Tests bestanden (ein optionaler Pi-Skip); fünf separate Downloader-Tests bestanden. `browser_fullscreen_check.py --serve` prüft zwei Ansichten, native Fullscreen-API und CSS-Fallback, Fehleranzeige und vier Displaygrößen. `browser_routes_check.py` prüft zusätzlich die echte Offline-Bibliothek, amtliche Höhen und explizite persönliche Übernahme, ohne Gerätebefehle.

Nach dem realen Niedriglasttest kamen Echo-/Provenienzkorrekturen hinzu:
**195 Windows-Tests bestanden; 192 Pi-Tests bestanden, ein optionaler Skip**.
Unverifizierte Daum-Wattwerte werden weder als Istleistung integriert noch als
bekannte Messwerte per Bluetooth gesendet. Archivierte Rohwerte bleiben erhalten.
`browser_power_quality_check.py --serve` prüft diesen Anzeigekontrakt mit einem
synthetischen WebSocket; das Backend bleibt dabei ohne jeden Steuer-POST im Demo-
Leerlauf. Der ausdrücklich freigegebene reale 25/35/25-W-Test mit numerischem Echo
und anschließendem lesendem S20-Freigabenachweis steht separat in der Übergabe.
