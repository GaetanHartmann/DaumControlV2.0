# Trainingskatalog, Live-Wattsteuerung und Coach

Umsetzung am 2026-11-09 auf dem bestehenden Arbeitsbranch `feat/fitness-cockpit`.
Auftrag: [Fitness-Cockpit-Implementierungsauftrag](fitness-cockpit-p0-p1-2026-11-09.md).
Bestehende Daum-/BLE-Verbindung, Profile, Historie, Planer und SQLite werden weiterverwendet.
Der Produktname bleibt bis zu einer Namensentscheidung Fitness-Cockpit.

## Architektur und geänderte Dateien

| Bereich | Dateien | Entscheidung |
| --- | --- | --- |
| Laufende Steuerung | `bike/backend/main.py` | Ein gewünschter Sollwert mit Revision, persistenter manueller Override, explizite Sitzung und getrennte Bestätigung/Messung |
| Protokoll | `devices.py`, `connectors.py` | Bestehendes TCP-Framing weiterverwenden, veraltete Vorgabe zwischen Modus- und Wattbefehl verwerfen |
| Katalog | `catalog.py` | Bestehende `plans`, additive Metadaten/Favoriten/Prüfnachweise und Revisionen; Vorlagen bearbeiten als Kopie |
| Coach | `coach.py` | Lokaler Vorschlag ohne KI-Schlüssel; optionaler strukturierter OpenAI-Adapter nur nach ausdrücklicher Einwilligung |
| Benutzergrenzen | `training.py` | Optionale `power_min_watts`/`power_max_watts`, Schnittmenge mit Geräte- und gegebenenfalls Pulsgrenzen |
| Historie/Export | `main.py`, `exports.py` | Aufgezeichnete Soll-/Istwerte, unveränderliche Plansegmente, Steuerereignisse und Messabdeckung |
| Oberfläche | `main.ts`, `live-training.css`, `training-ui.ts` | Getrennte Soll-/Ist-Anzeige, dauerhafter Slider, ±10 W, Rückkehr zum Plan; bestehende Diagramme erweitert |
| Katalog/Coach-UI | `workout-library.ts`, `workout-library.css` | Gemeinsame datengetriebene SVG-Vorschau, vollständiger Bearbeitungs-/Prüfablauf |
| P2-Grenze | `routes.py`, `virtual-routes.ts` | Benutzerbezogener GPX-/GeoJSON-Koordinatenimport, echte Daten in 2D; keine automatische Widerstandssteuerung |
| Bereitstellung | `install-cockpit-update.py`, `package-cockpit-update.py` | Prüfsummen, Sicherung/Rücknahme und unveränderte Bestandsdaten einschließlich neuer Tabellen |

Weitere Tests liegen in `test_live_control.py`, `test_catalog_coach.py`, `test_routes.py`,
`test_power_probe.py` und den erweiterten bestehenden Suites. Browserprüfer heißen
`browser_live_power_check.py`, `browser_catalog_coach_check.py`, `browser_routes_check.py`
und `browser_cockpit_check.py`.

## Bedienung und Zustände

Die vorhandene Einseitenanwendung erhält direkt aufrufbare Hash-Routen:
`/#/training`, `/#/trainings`, `/#/coach`, `/#/history`, `/#/planner`, `/#/routes`, `/#/devices`.
Die URL ist keine Startanweisung. Neuladen oder Verbinden startet keine neue Einheit.

Im Katalog erscheinen vier zusätzliche Anfangsprofile: Lockere Runde, Intervalle,
Bergfahrt und Ausdauerfahrt. Die Vorschau berechnet Segmentbreiten aus der Dauer und
Höhen aus den tatsächlichen Wattwerten. Suche, Kategorie/Dauer, Favoriten, Details,
Erstellen, Kopieren, Bearbeiten und bestätigtes Löschen sind verfügbar. Mitgelieferte
Vorlagen werden als eigene Kopie bearbeitet; Profile mit persönlicher Planreferenz
können nicht versehentlich gelöscht werden. Neue private Profile sind benutzerbezogen.

Katalog und Coach führen über Übernehmen/Prüfen in den Vorab-Check. Ein Profil mit
fehlenden/ungültigen Segmenten wird abgewiesen. Ein Prüfnachweis bindet Segmente,
Konfiguration, Intensität, Steuerungsart und Fähigkeiten. Änderungen machen ihn ungültig.
Erst der zusätzliche Startklick steuert ein Training. Fehlende Verbindung kann im
Vorab-Check hergestellt werden; danach ist gegebenenfalls erneut zu prüfen.

Während einer Einheit setzt Slider oder ±10 W einen absoluten manuellen Sollwert.
Dieser bleibt bei weiteren Segmenten bestehen. Die Uhr, Distanz, Messspur und Position
werden dadurch nicht zurückgesetzt. »Zurück zum Trainingsplan« übernimmt den Sollwert
der aktuellen Position; die Pulsregelung behält ihre Sicherheits-/Einschwingregeln.
Sicherheitsregeln haben Vorrang und können den Override aufheben. Im Zwift-Fernbetrieb
bleiben lokale konkurrierende Sollwertschreiber gesperrt.

Der Browser sammelt schnelle Slideränderungen 180 ms lang und überträgt seriell nur
die neueste verbleibende Vorgabe. Das Backend führt einen einzelnen aktuellen Slot,
begrenzt die Befehlshäufigkeit und verwirft überholte Revisionen. Ein Sitzungsbezeichner
verhindert verspätete Änderungen aus einer beendeten Einheit. Ein Stoppsignal verwirft
einen noch nicht gesendeten alten Wattbefehl auch während der Modusbestätigung.

Bei Pause wird nur die vom Adapter unterstützte sichere Minimalvorgabe angefordert.
Ein anderer Trainings-Sollwert kann vorbereitet werden, wird aber erst nach bewusstem
Fortsetzen verwendet. Fortsetzen erhält Position und Zeit. Bei Fehler/Verbindungsabbruch
wird nicht heimlich wieder aufgenommen. Die Daum-Protokollzeitlimits und ein nicht
bestätigter Stopp ersetzen keine physische Bedienung am Cockpit.

## Gewünschter, bestätigter und gemessener Wert

- `requested_target_watts`: aktuell gewünschte Vorgabe, Quelle separat protokolliert.
- `applied_target_watts`: tatsächlich vom Stellbefehl zurückgegebener Wert oder `null`; ein Transport-ACK allein reicht nicht.
- `measured_watts`: gültiger frischer Messwert aus `X70` oder `null`.

Daum verwendet weiterhin `S201` für den Steuerungsmodus und `S23<watts mit zwei
Dezimalstellen>` für die Wattvorgabe; `S200` gibt die externe Kontrolle frei. Der
Parser prüft ACK, Antwortkennung und Prüfsumme. Zusätzlich muss `S201` den Wert 1
bestätigen und `S23` einen endlichen akzeptierten Wattwert zurückgeben. Ein
abweichender Rückgabewert erscheint als `adjusted`, eine fehlende Rückgabe als
`unconfirmed` mit bestätigtem Wert `null`. Die Quelle heißt weiterhin `protocol_ack`,
das Detail ausdrücklich `echoed_value`. Das ist keine separate Messung mechanisch
umgesetzter Schwungradlast. Simulation setzt keinen real bestätigten Sollwert.

Die sichere Pause-/Stoppvorgabe ist das Geräteminimum. Sie kann unter einer ausdrücklich
höher konfigurierten Trainingsuntergrenze liegen; die Untergrenze ist kein Grund,
während einer Pause eine höhere Last anzufordern. Normale Vorgaben werden im Frontend,
Backend und Adapter innerhalb der jeweiligen Fähigkeiten geprüft.

Die Daum-Hülle verwendet zunächst die bereits vorhandene Softwarefreigabe von
25–400 W mit 5-W-Sliderraster als konservativen Adapterbereich. Das ist keine
automatisch abgefragte Aussage über die theoretische maximale Geräteleistung.
Andere Adapter können eigene Grenzen melden; der konkrete reale Nachweis dieser
Übergabe beschränkt sich auf die ausdrücklich freigegebenen niedrigen Testwerte.

Ergebnisse speichern die Originalsegmente in `summary.plan_steps` und Steuerereignisse
mit Zeit/Quelle/Wunsch/Bestätigung/Fehler in `control_events_json`. Die ersten acht
Messspurpositionen bleiben kompatibel, neue Spuren ergänzen Planwert, bestätigten
Sollwert, Befehlstatus und Quelle. JSON-Exporte benennen diese Zusatzfelder ausdrücklich;
ältere Spuren dürfen kürzer sein. CSV/TCX behalten ihre bisherigen Kernformate.
Die Historie zeigt Eingriffe und den ursprünglichen, angeforderten und gemessenen Verlauf.

## Start und Simulation

```powershell
cd C:\Daten\Raspy\bike
npm.cmd --prefix frontend run build
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Ein neu gestartetes Backend ist zunächst im Demo-Modus. In »Verbindungen« kann bewusst
zwischen Simulation und Daum gewechselt werden. Der Demo-Modus simuliert Radwerte,
erfindet keinen Pulssensor und behauptet keine reale Gerätebestätigung. Für die
Frontend-Entwicklung zusätzlich `npm.cmd --prefix frontend run dev`; die bestehende
Vite-Konfiguration verwendet das Backend auf Port 8000.

Persönliche Datenbanken vor Änderungen sichern. Browser-Trainingsprüfer ausschließlich
mit ihrer frischen temporären `--serve`-Installation benutzen; sie dürfen nicht auf
eine echte Daum-Einheit angewandt werden.

## Coach und Datenübertragung

Ohne externe Konfiguration erzeugt der lokale Coach nachvollziehbare konservative
Vorschläge. Er wird als lokal bezeichnet, nicht als ausgeführte KI-Anfrage. Externe
Vorschläge erhalten nur bei tatsächlichem externem Provider die Herkunft `ai`.
Jeder Vorschlag ist vor Übernahme editierbar; Änderungen nach Übernahme aktualisieren
dasselbe Profil und verlangen eine neue Prüfung. Die KI hat keine Geräteschnittstelle.

Optional müssen `OPENAI_API_KEY` und ein ausdrücklich gewähltes `OPENAI_MODEL` in der
Serverumgebung gesetzt werden. Schlüssel gelangen nicht in Browserantworten. Ein
Aufruf erfolgt nur über die externe Schaltfläche mit bewusstem Einwilligungshäkchen
für diese Anfrage. Übertragen werden Ziel/Dauer/Grenzen und Zusammenfassungen der
letzten zehn realen Radeinheiten, keine Namen, Körpermaße, Sensoradressen oder Rohspuren.
Die Oberfläche zeigt vorab den Umfang. `store=false` und striktes JSON-Schema sind
gesetzt; jede Antwort wird nochmals lokal validiert und löst keinen Gerätebefehl aus.
Siehe [offizielle Structured-Outputs-Dokumentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
und [Bedienung/Datenschutzdetails](../TRAINING_CATALOG_AND_COACH.md).

## P2 und offene Nachweise

Die separate Streckenseite importiert eine zusammenhängende GPX-/GeoJSON-Linie.
Distanz wird aus Koordinaten berechnet und entsprechend gekennzeichnet. Fehlende
Höhen bleiben unbekannt. Ein Höhenprofil wird nur bei vollständig importierten Höhen
gezeigt. Der Fortschritt verwendet erfasste beziehungsweise klar simulierte Radwerte.
Automatische OSM-Rundstreckensuche, ein externer Höhendatendienst, 3D-Rendering und
Gelände-Widerstandssteuerung sind **nicht** fertig integriert; die Daten-/UI-Grenze
ist vorbereitet und beeinflusst keine manuelle Wattvorgabe.

**Hardwarestatus:** Daum-Befehle sind im Bestand vorhanden und mit Mock-TCP-Rahmen
getestet. Der neue vollständige Leistungsablauf darf erst nach echtem Interface-Test
als hardwaregeprüft gelten. Der vorbereitete Prüfer `tests/pi_power_control_smoke.py`
hat einen lesenden Standardmodus und sendet erst mit ausdrücklichem Flag 25/35/25 W,
liest Telemetrie, stellt 25 W/lokale Kontrolle wieder her und legt keine Trainingsdaten
an. Dafür ist eine Bestätigung nötig, dass das Bike unbenutzt stillsteht. Aktueller
Freigabe-/Teststand und Pi-Bereitstellung werden nach Abschluss unten ergänzt.

## Softwareprüfung

Vollständiger Windows-Lauf nach Protokoll-/Qualitätskorrektur: **195 Tests bestanden**, bestehende httpx-Deprecation-Warnung.
Vite-Build und zusätzlicher TypeScript-Typcheck bestanden. Der Live-Browserablauf prüft
echte Zeit über einen Segmentwechsel, Slider-Bündelung, manuellen Override, Pause,
Fortsetzen, Rückkehr, gespeicherte Eingriffe und den unveränderten ursprünglichen Plan.
Katalog-/Coach- und Streckenimport-Browserabläufe prüfen Datenvorschauen, CRUD,
Einwilligung, erneute Validierung, Gerätevorbereitung ohne Start sowie fehlende Höhen.

Bei 800 × 480 passen aktive Steuerung und alle Messkacheln in den sichtbaren Bereich;
Slider und ±-/Pause-/Stopptasten bleiben verfügbar. Tablet und Smartphone wurden
zusätzlich geprüft. Die Screenshots werden in das Betriebssystem-Tempverzeichnis
geschrieben: `fitness-live-power-*.png`, `fitness-trainingskatalog-*.png`,
`fitness-ki-coach-*.png`. Externe KI-Aufrufe sind bisher ausschließlich gemockt;
ein realer Schlüssel/Providerlauf wird damit nicht behauptet.

Gesicherte Beispielaufnahmen aus den isolierten Testläufen:

- [Trainingskatalog mit Datenkurven](../screenshots/p0-training-catalog.png)
- [Live-Training mit manuellem Sollwert bei 800 × 480](../screenshots/p0-live-training-800x480.png)
- [Editierbarer lokaler Coach-Vorschlag](../screenshots/p1-local-coach-preview.png)

Der letzte Live-Browsertest prüft außerdem Reload im pausierten Zustand ohne
automatisches Fortsetzen. Fünf schnelle Sliderereignisse ergeben einen API-Aufruf;
die letzte gewünschte Vorgabe kommt an. Auch »Zurück zum Trainingsplan« besitzt
mindestens 44 Pixel Touchhöhe. Die aktive rechte Steuerung endet bei 466 Pixeln,
die Messkacheln bei 469,5 Pixeln im 480 Pixel hohen Pi-Viewport.

## Erkenntnis aus dem freigegebenen Hardwaretest

Der erste reale Niedriglasttest zeigte: X70-Feld 6 meldet 25/35/25 W bei 0 U/min.
Damit ist aus diesem Feld keine unabhängige physische Ist-Leistung nachgewiesen.
Die Herstellerunterlage nennt es zwar »power«, bestätigt damit aber keinen eigenen
Leistungsmesser. Das Feld bleibt deshalb ausdrücklich als `reported_power`
verfügbar. Kanonische Ist-Watt, Leistungsabdeckung, mechanische Arbeit und Watt/kg
bleiben ohne zusätzliche verifizierte Quelle unbekannt. Historische numerische
Daum-Werte werden nicht aus SQLite gelöscht oder überschrieben; die Lese-/Export-
ansicht stellt sie getrennt als unverifizierte Gerätemeldung dar.

Die Herstellerunterlage SP-KOMM-PM1 §1.2 verlangt außerdem die Auswertung des
zurückgegebenen akzeptierten Werts. Der bisherige Transport-ACK allein war dafür
nicht ausreichend. Entsprechende Echo-/Abweichungs-/Ablehnungsprüfungen wurden
ergänzt. [Herstellerdokument als Reproduktion](https://manualzz.com/doc/1228127/daum-electronic-bike--lyps--run-family-user-manual),
[archivierter Originalverweis](https://web.archive.org/web/20150514085335/http://www.daum-electronic.de/de/download/bedaprem/SP-KOMM-PM1.pdf).

Herstellerdokument und bisheriger Decoder widersprechen sich bei der X70-
Geschwindigkeitseinheit. Ohne Vergleich während einer echten Fahrt wird die
bisherige Umrechnung nicht stillschweigend umgestellt: Geschwindigkeit und daraus
abgeleitete Distanz sind mit Stern/Einheitenhinweis gekennzeichnet. Das ist keine
abgenommene Geschwindigkeitskalibrierung. Unverifizierte Watt- und Geschwindigkeits-
werte werden nicht als bekannte Messwerte an FTMS/CPS ausgegeben. Die bestätigte
Wattsteuerung bleibt von dieser Messfähigkeitsgrenze getrennt.

Zusätzlich geändert: `ftms.py`/`zwift.py` geben keine Null-Platzhalter als Messung aus;
die Leistungs-Messfähigkeit wird getrennt von der Zielwatt-Steuerfähigkeit behandelt.
Der separate Apple-Spike-Empfänger leert kleine abgewiesene HTTP-Request-Bodies
begrenzt vor einer 401-Antwort, damit die Windows-Prüfung keine TCP-Reset-Rennen zeigt.

Neue Prüfungen: `test_telemetry_quality.py`, `test_export_quality.py` und
`browser_power_quality_check.py`. Sie unterscheiden unbekannt von tatsächlich
gemessener Null, erhalten archivierte Rohwerte, verhindern fingierte Arbeit/Coach-
Ableitungen und prüfen unveränderte ursprüngliche Datenbankzeilen.

## Abschließende Pi-Abnahme

Der korrigierte Stand ist auf `ghapi3.local:8000` installiert. Finales Paket:
`dd927250301161f6ef6b5d146a0f5743d1d45bf54184aa8480185beb9d9c8dfc` (45 Dateien),
Frontend `index-CENVb3UI.js` / `index-BhtJ2Rke.css`.
**192 Tests bestanden auf dem ARM64-Pi**, ein optionaler Export-Schematest wurde
übersprungen. Windows: **195 bestanden**, Vite-Build und separater TypeScript-Check
bestanden. Katalog/Coach, bestehender Cockpitablauf, Live-Override und synthetischer
Qualitätsvertrag wurden in getrennten frischen Browserinstallationen geprüft.

Der Nutzer bestätigte ausdrücklich ein unbenutztes stillstehendes Bike und gab den
25/35/25-W-Test frei. Nach der Echo-Korrektur wurde derselbe freigegebene Test erneut
durchgeführt. Alle drei Antworten enthielten den tatsächlich akzeptierten Sollwert:

| Anforderung | Vom Stellbefehl zurückgegeben | X70-Gerätemeldung | Unabhängig gemessene Leistung |
| --- | --- | --- | --- |
| 25 W | 25,0 W, `echoed_value` | 25 W, 0 U/min | nicht nachgewiesen |
| 35 W | 35,0 W, `echoed_value` | 35 W, 0 U/min | nicht nachgewiesen |
| 25 W | 25,0 W, `echoed_value` | 25 W, 0 U/min | nicht nachgewiesen |

Danach wurden sichere Minimalvorgabe und `S200` gesendet. Eine zusätzliche **lesende**
`S20`-Abfrage ergab `0`: die externe Laststeuerung war freigegeben. Die kanonische
Ist-Leistung blieb `null`, die separate Gerätemeldung 25 W. Es wurde keine
Trainingseinheit angelegt. Abschließend: Daum verbunden, `running=false`, kein
ausstehender Speichervorgang; **2 Benutzer, 22 Profile und 3 Fahrten** unverändert.

Die vor dem neuen Auftrag vorhandenen 18 Profile blieben erhalten; vier neue
Katalogvorlagen wurden genau einmal ergänzt. Alle vorhandenen Zeilen sämtlicher
zehn Datentabellen wurden bei beiden Updates auf unveränderte alte Spalten geprüft.
Die Abschalteinstellungsdatei blieb unverändert. Aktuelle Sicherung von Code und
SQLite: `/home/gha/daum-studio/backups/before-cockpit-20261109-184542-706213`.

Der lokale Pi-Kiosk zeigt die neue Navigation und die Hinweise zu unbekannter
Ist-Leistung/Geschwindigkeitseinheit. Es wurden kein Neustart und kein Poweroff
ausgelöst. Ein Training mit tretender Person, die Geschwindigkeitskalibrierung,
unabhängige mechanische Leistungsmessung, reales Zwift-Verhalten und ein echter
externer KI-Aufruf bleiben **offen**. Die Geräte-Steuerbefehle sind hingegen mit
den genannten niedrigen Werten gegen die echte Schnittstelle nachgewiesen.

[Darstellung unbekannter Ist-Leistung](../screenshots/p0-daum-value-provenance.png)
zeigt den synthetischen UI-Vertrag, keinen zusätzlichen Hardwaretest.

Eine abschließende externe Browserprüfung gegen die tatsächlich installierte App
bestätigte alle vier neuen Katalogvorlagen, mindestens 22 Datenkurven, Coach-Seite,
Ist-Leistung »—« und verbundene untätige Daum-Sitzung. Keine JavaScriptfehler und
keine Steuer-POSTs wurden dabei ausgelöst. Der externe Coach ist auf dem Pi aktuell
**nicht konfiguriert**; der lokale Ablauf bleibt verfügbar. Es wurde kein echter
externer KI-Aufruf ausgeführt.
