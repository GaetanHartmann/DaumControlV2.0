# Fitness-Cockpit: rücknehmbares Pi-Update

Der bestehende App-Pfad bleibt `~/daum-studio`, der Backend-Dienst bleibt `daum-studio.service`; Branding ändert diese Betriebsnamen nicht. Die Abschalteinstellung unter `/var/lib/daum-studio/power-watch.json` wird weder überschrieben noch umgeschaltet.

## Paket erstellen

Nach bestandenen Tests und dem finalen Frontendbuild auf Windows:

```powershell
cd bike
.venv\Scripts\python.exe deploy/package-cockpit-update.py "$env:TEMP\fitness-cockpit-update.tar.gz"
```

Das Paket enthält die Backendmodule, Produktionsassets, benötigte Display-/Updatehelfer und Backendtests. Es enthält keine Datenbank, Schlüssel, Umgebungsdateien oder native App-Artefakte. Der native Test wird ausgeschlossen, da seine separaten Spike-Quellen nicht Teil der Pi-Installation sind. Das Manifest nennt SHA-256 für jede Datei; die Ausgabe enthält zusätzlich den Archivhash.

## Auf dem Pi vorprüfen

Archiv in ein neues Verzeichnis unmittelbar unter dem Benutzerverzeichnis entpacken, beispielsweise `~/fitness-cockpit-stage-20261109`. Keine bestehende Installation überschreiben. Als App-Benutzer:

```sh
python3 ~/fitness-cockpit-stage-20261109/deploy/install-cockpit-update.py ~/fitness-cockpit-stage-20261109 --check
```

`--check` liest Manifest und Livezustand. Training, freigegebene Zwift-Steuerung und ausstehendes Speichern sperren das Update. Bei eingeschalteter LAN-Abschaltautomatik muss ein positiver physikalischer `eth0`-Link vorliegen, damit ein Update nicht in ein drohendes Poweroff-Zeitfenster fällt.

Backendtests aus dem Stage mit dem bestehenden Pi-Venv ausführen; sie verwenden temporäre Datenbanken und gemockte Geräte. Nicht die Browser-Trainingsprüfer gegen den Liveport ausführen:

```sh
cd ~/fitness-cockpit-stage-20261109
~/daum-studio/.venv/bin/python -m pytest -q tests --import-mode=importlib
```

Zusätzlich einen isolierten Stage-Server mit eigener temporärer `BIKE_DB`, eigener `BIKE_POWER_CONFIG` und anderem Port starten, falls HTTP-/Browserprüfungen erforderlich sind. Die Live-Datenbank wird dafür nicht verwendet.

## Installation

Nach erfolgreicher Vorprüfung ohne aktive Einheit:

```sh
python3 ~/fitness-cockpit-stage-20261109/deploy/install-cockpit-update.py ~/fitness-cockpit-stage-20261109 --display
```

Der Installer prüft die Untätigkeit unmittelbar vor dem Dienststopp erneut, stoppt den Backendprozess, sichert SQLite über dessen Backup-API sowie sämtliche überschriebenen Dateien und bei `--display` die bestehenden Displaydateien. Nach dem Start prüft er Zustand, Benutzerzuordnung, Konfiguration, Analyse und Planer ausschließlich lesend. Jede vorhandene Benutzer-/Plan-/Fahrtzeile wird für die zuvor vorhandenen Spalten auf unveränderten Inhalt verglichen; zusätzliche Spalten/Tabellen sind zulässig. SQLite-Integrität und unveränderte Abschalteinstellung werden kontrolliert.

Die Displayinstallation übernimmt beim SSH-Aufruf ausschließlich grafische Sitzungsvariablen aus dem bestehenden User-Service-Manager; sie startet keine neue grafische Sitzung. Der Helfer aktiviert vorhandene Ausgänge und startet den bestehenden Idle-Dienst neu. Kein Reboot oder Poweroff, kein Training und keine Wattvorgabe werden ausgelöst. Der Benutzer sollte während des kurzen Updates keine neue Einheit in einem zweiten Browser starten.

Eine zuvor vorhandene Geräteverbindung wird nicht automatisch wiederhergestellt. Nach dem Update kann »Daum verbinden« gezielt geprüft werden; das ist ein eigener Schritt und kein Trainingsstart.

## Rücknahme und Nachweise

Bei einem Installations-/Healthcheckfehler werden vorhandene Code-/Assetdateien, hinzugefügte Dateien, die konsistente Datenbanksicherung und gegebenenfalls Displaydateien automatisch zurückgenommen; der ursprüngliche Backenddienst wird wieder gestartet. Das Sicherungsverzeichnis lautet `~/daum-studio/backups/before-cockpit-…` und enthält `rollback.json`, `manifest.json`, die Datenbank und bei Erfolg `result.json`.

Ein späteres manuelles Zurückspielen der Datenbank würde nach dem Update neu erfasste Trainingsdaten verlieren. Deshalb vor einer nachträglichen Rücknahme erneut sichern und die Daten bewusst abgleichen; die automatische Rücknahme ist für das unmittelbare Updatefenster vorgesehen.

Vier lokale Installertests prüfen manipulierte Pfade/Prüfsummen, additive Datenmigration, unveränderte Bestandsdaten, simulierten fehlgeschlagenen Healthcheck mit Code-/Datenbankrücknahme und Begrenzung rekursiver Dateientfernung auf das Installationsverzeichnis. Reale Kaltstart-/Display- und vollständige Trainingsabnahme bleiben gesonderte Hardwaretests.

## Durchgeführtes Update am 2026-11-09

- Paket: 33 manifestierte Dateien, Assets `index-CGOdMnm2.css` und `index-yB7TpUzC.js`; Archiv-SHA-256 `a1f1422e8fbaf665cd9dad8a95f38892f9fa734b5e94bbc207af51e4e67550ac`.
- Separates Staging: `/home/gha/fitness-cockpit-stage-20261109-a1f1422e`; Archivhash nach Übertragung identisch.
- Tests im Stage mit dem bestehenden ARM64-Pi-Venv: **104 bestanden, ein optionaler Schema-Test übersprungen**, bestehende FastAPI/Starlette/httpx-Deprecation-Warnung. Keine Verbindung zu echter Trainingshardware aus den Tests.
- `--check` bestätigte untätigen Demo-Zustand und gültige 33 Prüfsummen; danach Installation mit `--display` erfolgreich.
- Konsistente Sicherung: `/home/gha/daum-studio/backups/before-cockpit-20261109-123629-224733`.
- **2 Benutzer, 18 Pläne und 2 Fahrten erhalten**; sämtliche zuvor vorhandenen Spalten dieser Bestandszeilen unverändert.
- Backend und neuer Display-Idle-Dienst aktiv; HDMI-A-1 eingeschaltet, Idle-Zeit weiterhin 300 s. Beim ersten Neuladen zeigte der Kiosk noch einen gecachten alten HTML-Einstieg. Er wurde anschließend ausschließlich über das dedizierte Browserprofil mit `/?build=fitness-20261109-a1f1422e` neu geladen. Die tatsächliche Chromium-Seite wurde über lokal gebundenes CDP geprüft: Titel »Fitness-Cockpit · Training«, Header »DEIN FITNESS-COCKPIT«, fünf Navigationseinträge einschließlich Planer, drei Gerätecheckboxen, sechs Messkacheln und im Leerlauf fehlende Leistung als »— W« mit Gerätequelle. Bildschirmaufnahme `fitness-cockpit-display-new-20261109.png` im lokalen Temp-Verzeichnis bestätigt die neue Oberfläche bei 800×480. Eine Chromium-Übersetzungsblase war weiterhin sichtbar; keine Tastatur-/Touchaktionen wurden injiziert. Das zwischenzeitlich regulär aktivierte schwarze Idle-Overlay wurde zur Bildschirmprüfung mit dem neuen Displayhelfer beendet, ohne Timer- oder Trainingseingriff.
- Abschalteinstellung unverändert: SHA-256 `d31e41ab7a034e2124860978b6e38a3c4449578e14bae1fdf2e29ef84a604687` vor/nach Installation.
- Root-Agent prüfte anschließend den bereitgestellten Browser lesend (sechs Routen, Zeitachse/Stufen/Berg/Einstellungen, keine JavaScriptfehler) und verband ausschließlich den Daum über die neue Geräteauswahl: erfolgreich in 136 ms; `connected=true`, `running=false`, kein ausstehendes Speichern.
- Kein Pulsgurt vorhanden; keine echte Trainingsbelastung, kein Reboot/Poweroff. Reale Trainings-, Pulsgurt- und Kaltstartabnahme bleiben offen.

## P0-Katalog/Coach-Update und anschließende Provenienzkorrektur

Das Katalog-/Live-Override-/Coach-Paket wurde anschließend zunächst mit Archiv-SHA
`a4f978feafe3b6b7cf446b3a4589fbac4290366b451607fc8925395e99a2fd52`
installiert. Dessen Pi-Stage bestand 162 Tests bei einem optionalen Skip. Dabei
wurden 2 Benutzer, 18 bereits vorhandene Profile und 3 zu diesem Zeitpunkt
vorhandene Fahrten unverändert erhalten; die vier neuen Vorlagen führten zu 22
Profilen. Sicherung dieses Zwischenstands:
`/home/gha/daum-studio/backups/before-cockpit-20261109-183008-030743`.

Der danach ausdrücklich freigegebene, getrennte Hardwaretest zeigte, dass die
Daum-X70-Wattangabe auch bei Kadenz null dem Sollwert folgte. Der Zwischenstand
ist deshalb kein Nachweis einer unabhängig gemessenen Tretleistung. Die folgende
Korrektur ersetzt ihn und trennt Protokollbestätigung, unverifizierte Gerätemeldung
und physische Leistung. Originaldaten werden nicht rückwirkend umgeschrieben.

**Endgültiges Softwarepaket der Korrektur, 2026-11-09:**

- 45 manifestierte Dateien, Build `index-CENVb3UI.js` / `index-BhtJ2Rke.css`.
- Archiv-SHA-256: `dd927250301161f6ef6b5d146a0f5743d1d45bf54184aa8480185beb9d9c8dfc`.
- Separater Stage: `/home/gha/fitness-cockpit-stage-20261109-quality-dd927250`;
  Hash nach Übertragung identisch.
- Pi-Stage: **192 Tests bestanden, 1 optionaler Schema-Test übersprungen**;
  bestehende Testclient-Deprecation-Warnung. Die Tests verwenden Mock-Geräte und
  temporäre Datenbanken; der mitgelieferte reale Probe-Helfer wurde dabei nicht
  ausgeführt.
- Vor Dienststopp erneut untätigen Zustand geprüft und die bisherige
  Daum-Verbindung über `POST /api/mode` auf Demo geschlossen. Dieser
  Verbindungswechsel sendet keine Wattvorgabe. Dadurch löst auch der spätere
  Backend-Shutdown keine Pause-/Stopp-Wattvorgabe am verbundenen Altadapter aus.
- `--check` prüfte alle 45 Dateihashes. Installation ohne erneutes `--display`
  erfolgreich; Displaykonfiguration und 300-Sekunden-Timer bleiben bestehen.
- Vollständige Sicherung: `/home/gha/daum-studio/backups/before-cockpit-20261109-184542-706213`.
- Originalspalten/-zeilen aller zehn inzwischen vorhandenen Datentabellen
  erhalten: 2 Benutzer, 22 Profile, 3 Fahrten, 2 Einstellungen, jeweils null
  Planeinträge/Katalogmetadaten/Favoriten/Prüfnachweise/Coach-Entwürfe/Routen.
  Die vier Vorlagen wurden nicht erneut dupliziert. SQLite `quick_check`: `ok`.
- Abschalteinstellung weiterhin identisch, SHA-256:
  `d31e41ab7a034e2124860978b6e38a3c4449578e14bae1fdf2e29ef84a604687`.
- Nach Installation ausschließlich Daum-Handschlag wiederhergestellt:
  `connected=true`, `running=false`, angefordert 25 W, angewendet `null`,
  gemessen `null`, Befehlsstatus `idle`. Kein Trainingsstart oder Wattbefehl
  durch das Softwaredeployment.
- Neue Fähigkeiten melden `measured_power_supported=false`; Power-Gerätemeldung
  und Geschwindigkeit sind als `device_reported_unverified` getrennt ausgewiesen.
  Coach zählt keine unbestätigte Leistungsmessung als verifiziert; die aktuelle
  leistungsabhängige Analyse bleibt nicht verfügbar.
- Der vorhandene dedizierte Kiosk wurde über seinen lokalen Debugkanal auf
  `/?build=fitness-quality-20261109-dd927250` neu geladen. Tatsächliche Seite:
  sieben Navigationspunkte einschließlich Trainingskatalog und KI-Coach, 25 W
  angefordert, Ist-Leistung `— W`, Hinweis »Ist nicht nachgewiesen« und
  Geschwindigkeit »Einheit ungeprüft«. Kein anderer Browser wurde verändert.

Ein erneuter realer 25/35/25-W-Test mit der korrigierten Echo-Auswertung ist ein
eigener, beaufsichtigter Nachweis und gehört nicht zu diesem Softwaredeployment.
Sein Ergebnis wird im aktuellen Übergabebericht festgehalten. Es gab keinen
Reboot oder Poweroff.
