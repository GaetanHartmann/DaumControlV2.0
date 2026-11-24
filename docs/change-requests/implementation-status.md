# Fitness-Cockpit: Umsetzung und Abnahme

Stand: 2026-11-09. Arbeitsbranch: `feat/fitness-cockpit`.

Der anschließende Auftrag ergänzt Trainingskatalog, Live-Wattsteuerung und Coach.
Der aktuelle Software-/Hardwarestand (195 Windows-Tests, 192 Pi-Tests und echter
25/35/25-W-Echo-Test einschließlich Kontrollfreigabe) steht in der
[P0/P1-Übergabe](p0-p1-implementation-2026-11-09.md). Dabei wurde die frühere Annahme
einer unabhängig gemessenen Daum-Istleistung korrigiert; historische Rohwerte bleiben
erhalten, werden aber nicht mehr als verifizierte Leistungs-/Arbeitswerte behandelt.

Die Freigabe »Alles umsetzen« ersetzt die vorherige Beschränkung auf Planung. Die ursprünglichen Anforderungen liegen in [fitness-cockpit-cr-2026-11-06.md](fitness-cockpit-cr-2026-11-06.md); die [Bestandsplanung](fitness-cockpit-cr-2026-11-06-plan.md) dokumentiert den Zustand vor der Freigabe.

| CR | Ergebnis | Grenze der Abnahme |
| --- | --- | --- |
| 01 | Kompaktes Cockpit mit Leistung, Puls, Geschwindigkeit, Kadenz, Zeit/Restzeit, Distanz und Energie; Quellen und fehlende Werte erkennbar | kcal ohne geeignete Quelle nicht verfügbar; keine erfundene Leistungsstufe |
| 02 | Watt/Puls unabhängig am Zeitmarker einblendbar, lokal persistent | In Vorschau/ohne frische Messung keine alten Livewerte |
| 03 | Erfolgsanzeige nur bei regulärem Ende; persistente zeitgewichtete Mittelwerte, Arbeit, Messdauer und Abschlussgrund | Kalorien unbekannt; alte Fahrten ohne Aggregate bleiben entsprechend unvollständig |
| 04 | Gerätecheckboxen, unabhängiger TCP-/BLE-Versuch, Zwift separat, Status und strukturierte begrenzte Ereignisliste | Ursprüngliche Gurtursache nicht bewiesen; kein Gurt für echten BLE-Test angelegt |
| 05 | Displayaktivierung nach Verfügbarkeit grafischer Sitzung und erkannter Ausgänge; reversible Installation | Aktueller HDMI-/Diensttest ersetzt keinen Kaltstart oder Test nach echtem Poweroff |
| 06 | Parametrischer Ausdauer-/Intervall-/Regenerationsgenerator mit Warm-up/Cooldown, Vorschau, Speicherung und Bearbeitung als Kopie | Keine automatische Belastungssteigerung aus einer Einheit |
| 07 | Optionale Profilfelder, historisches Gewicht, Watt/kg, transparente Intensitätsrelation/Verlauf/Vergleich; ausdrückliche Übernahme einer Folgeeinheit | Empfehlungen nur mit ausreichenden realen Messwerten, keine Fitnessdiagnose/VO₂max |
| 08 | Optionales Kraftprogramm vor/nach Cardio; Varianten, Reihenfolge, Sätze, Wiederholungen, Pausen und Fortschritt; reine Kraftplaneinträge möglich | Kein Kraftprogramm während des Tretens; Abschluss wird bewusst bestätigt |
| 09 | Neutraler konfigurierbarer Name, Connector-Vertrag mit Daum-Hülle, Fähigkeiten und Messwertqualität | Weitere reale Adapter benötigen eigene Implementierung/Hardwareabnahme; Betriebsnamen bleiben kompatibel |
| 10 | Manuelle Laufbanderfassung in gemeinsamer Benutzerhistorie; Browser-BLE-Probe und Herstellerrecherche | Taurus-Modell/Montage unbekannt; kein Kauf, keine automatische Laufbandsteuerung |
| 11 | Watch-/iPhone-Sensorquellen und isolierter HTTPS-Transport-Spike samt Testmatrix vorbereitet | Kein Xcode-/Gerätebuild, keine reale Latenzmessung oder produktive Watch-Anbindung |
| 12 | Native Architektur-/Build-/Berechtigungs-/Datenschutzentscheidung und Aufwandsspannen dokumentiert; getrennte Swift-Nachrichten-/Brückenquellen | Entwicklerteam/macOS/Apple-Geräte offen; keine App-Store-Veröffentlichung |

## Verifikation

- Windows: **107 Tests bestanden**; bestehende Deprecation-Warnung im Testclient. Produktionsbuild und separater TypeScript-Typcheck bestanden.
- Pi-Stage mit isolierten Testdatenbanken: **104 bestanden, ein optionaler Export-Schematest übersprungen**. Native Spike-Tests sind bewusst nicht Teil des Pi-Pakets.
- Bestehende Browserprüfungen für Timeline und persönliche Profile bestanden.
- Neuer isolierter Browserablauf prüft Profile, Generator, Planer einschließlich Bearbeitung/Kraftfortschritt, fehlende manuelle Messwerte/Exporte und tatsächlichen zehnsekündigen Demoabschluss. Alle Messkacheln liegen bei aktivem Training bei 800 × 480 und 1024 × 768 im sichtbaren Viewport. Smartphone 390 × 844 ohne horizontalen Seitenüberlauf. Keine JavaScript-Laufzeitfehler in den geprüften Abläufen.
- Speicherfehler erzeugen keine voreilige Abschlussbestätigung: Datensatz bleibt im Speicher wiederholbar, die Oberfläche bietet einen erneuten Speicherversuch. Start und Nutzerwechsel sind währenddessen gesperrt. Diese Wiederholung ist keine Wiederherstellung nach Prozessverlust.
- Bestehende Benutzer-/Plan-/Fahrtspalten und Abschalteinstellung werden beim Update auf unveränderten Inhalt geprüft; Migrationen sind additiv. Späterer Downgrade benötigt bewusste Daten-/Backupsicherung, damit neue Daten nicht verloren gehen.

## Pi-Betrieb

Das Update wurde über das geprüfte [Paket-/Rollbackverfahren](cockpit-deployment.md) auf `gha@ghapi3.local` installiert, einschließlich Display-Starthelfer. **2 Benutzer, 18 Trainingsprofile und 2 Fahrten** sind für alle vorher vorhandenen Spalten unverändert erhalten. Die Abschalteinstellungsdatei besitzt denselben SHA-256 wie vor dem Update. Backend- und Idle-Dienst sind aktiv; HDMI-A-1 ist eingeschaltet. Der Idle-Timer und die LAN-Abschaltung bleiben bei 300 Sekunden.

Sicherung von Code, SQLite und Displaykonfiguration: `/home/gha/daum-studio/backups/before-cockpit-20261109-123629-224733`. Das Paket wurde vor Installation anhand seiner Prüfsummen kontrolliert; Archiv-SHA-256: `a1f1422e8fbaf665cd9dad8a95f38892f9fa734b5e94bbc207af51e4e67550ac`.

Nach Installation wurde ausschließlich der Daum ausgewählt und per API verbunden: erfolgreich in 136 ms; anschließend `mode=daum`, `connected=true`, `running=false`, kein ausstehender Speichervorgang. Dabei wurde kein Training gestartet und keine Wattvorgabe gesendet. Die lesende Browserprüfung gegen die installierte App bestand: sechs virtuelle Strecken, Zeitachsenraster, Stufendauern, Bergansicht und aktivierter Abschaltschalter, keine JavaScript-Fehler. Der Pulsgurt war laut Nutzer nicht angelegt; eine reale BLE-Abnahme wurde deshalb nicht behauptet.

Es wurden weder Neustart noch Poweroff ausgelöst. Die Web-App ist unter `http://ghapi3.local:8000` erreichbar.

Der lokale Kiosk wurde ausschließlich über sein dediziertes Browserprofil neu geladen. Ein alter Index im Chromium-Cache erforderte einmaliges Laden mit einer Build-Kennung in der URL. Danach wurde die tatsächliche lokale Seite geprüft: Titel Fitness-Cockpit, fünf Navigationspunkte einschließlich Planer, drei Geräteoptionen, sechs Messkacheln und korrekt unbekannte Istleistung im Leerlauf. Der vorhandene private Browser wurde nicht verändert. Der kurzzeitige Kiosk-Debugzugang ist auf localhost beschränkt.

## Noch erforderliche reale Abnahmen

Pulsgurt angelegt: Auswahl, Advertising, Mehrsensorfall, tatsächliche Signalfrische und Verhalten neben Daum prüfen. Kaltstart, Reboot und Start nach automatischem Herunterfahren beaufsichtigt testen; beide 300-Sekunden-Mechanismen getrennt abnehmen. Ein vollständiges reales Training einschließlich Puls-Sicherheitsverhalten und Zwift-Steuerung bleibt erforderlich. Für Taurus und Apple gelten die [Spikes und offenen Voraussetzungen](cr10-12-feasibility.md).

Weitere Bedienung: [Fitness-Cockpit](../FITNESS_COCKPIT.md). Displaybefund: [CR-05](cr05-display-boot.md).
