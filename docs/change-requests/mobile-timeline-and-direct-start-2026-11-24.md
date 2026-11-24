# Mobile Zeitachse, direkter Start und Wattkurven-Anpassung

Stand: 24.11.2026. Der bisherige Gesamtstand wurde als `9488cec` auf `feat/fitness-cockpit` committed und gepusht. Diese Ergänzung behandelt die anschließenden Änderungswünsche.

## Verhalten

- Die Zeitachse verwendet ihre tatsächliche Bildschirmbreite und -höhe als SVG-Koordinaten. Die bisherige 620-px-Mindestbreite entfällt. Schrift und Zeitraster passen sich der verfügbaren Fläche an; Handy-Hochformat, Querformat, normale Ansicht und Vollbild sind berücksichtigt.
- Kurze Stufen lassen sich antippen. Details mit Vor/Zurück/Schließen haben 44-px-Touchziele. Originalplan, angeforderte und gemessene Leistung bleiben unterscheidbar; unbekannte Ist-Leistung bleibt unbekannt.
- −10 W / +10 W sind direkt an der normalen Zeitachse und im Vollbild sichtbar. Sie benutzen dieselbe gedrosselte Befehlswarteschlange wie der Schieberegler. Bei laufendem Watt-Stufenplan verschiebt die Änderung die gesamte Kurve: Planwert 60 W → Wunsch 145 W ergibt +85 W; die nächste Originalstufe 100 W fährt damit 185 W. Jede Stufe wird auf die Geräte-/Nutzergrenzen begrenzt. „Zurück zum Trainingsplan“ entfernt den Versatz. Im freien Training und Pulsmodus bleibt die manuelle Vorgabe absolut.
- Angepasste Profilblöcke werden gefüllt und mit gestrichelter Oberkante angezeigt; das Original bleibt als schwache Referenz erhalten. Labels und Stufendetails zeigen angepasste und ursprüngliche Wattzahlen. Originalprofile und aufgezeichnete Messkurven werden nicht umgeschrieben.
- „Training vorbereiten“ wählt ein bereits geladenes Profil lokal aus. Die bisherigen drei seriellen Prüf-POSTs und der vollständige `/session`-Abruf entfallen bei der Auswahl.
- Ein bewusster Klick auf „Training starten“ genügt. Profil, aktuelle Grenzen und Gerätezustand werden intern geprüft. Unveränderte Prüfnachweise werden wiederverwendet; ein ausdrücklich als veraltet abgelehnter Nachweis wird einmal automatisch erneuert. Netzwerkfehler starten keinen automatischen zweiten Versuch. Doppelklicks erzeugen nur einen Start.
- Katalog-/Coach-Auswahl startet keine Einheit. Ein fehlender Pulsgurt oder andere Startblocker werden verständlich gemeldet; „Ohne Pulsgurt starten · Watttraining“ bleibt eine bewusste eigene Aktion.

## Messung auf dem Pi

Vier rein lesende lokale HTTP-Abfragen je Endpunkt, vor der Änderung:

| Endpunkt | Median | Nutzlast |
| --- | ---: | ---: |
| Einzelprofil `/api/catalog/1` | 18,4 ms | 588 B |
| Gesamte Sitzung `/api/session` | 314,7 ms | 148.217 B |
| Katalog `/api/catalog` | 188,4 ms | 89.847 B |
| Laufzeitstatus `/api/state` | 19,7 ms | 7.140 B |

Die gemessene CPU-Last lag bei 0,18. Das ist kein End-to-End-Messwert des Handys; es zeigt den unnötigen Umfang der bisherigen Vorbereitungsabfolge. Der neue Browsercheck belegt die Auswahl ohne Prüf-POST und ohne Sitzungs-GET.

## Dateien

`training-ui.ts` und `timeline-responsive.css` enthalten die adaptive Grafik. `timeline-power-controls.ts/.css` kapseln nur die Bedienelemente. `main.ts` und `immersive-cockpit.ts/.css` binden die bestehenden Daten und Steuerereignisse ein; konkurrierende alte CSS-Regeln sind entfernt. `workout-library.ts` übernimmt vorhandene Profile direkt. Der bestehende Backend-Versatz wird wiederverwendet; dieser UI-Schritt fügt keine neue Geräteaktion hinzu.

## Prüfung

210 Python-Tests und fünf Downloader-Tests bestanden vor dem Git-Abschluss; Backend und Datenmodell bleiben in dieser Ergänzung unverändert. Vite-Produktionsbuild und TypeScript-Prüfung bestanden.

- `browser_mobile_timeline_check.py --serve`: 30 Profil-/Gerätekombinationen, zusätzlich drei aktive Vollbildverträge mit +25-W-Versatz; lesbare Achsen, keine Labelkollision, keine erzwungene horizontale Diagrammverschiebung, antippbare kurze Stufen und unbekannte Ist-Leistung geprüft. Kein Steuer-POST und keine JS-Fehler.
- `browser_direct_start_check.py --serve`: lokale Auswahl, direkter Start, Doppelklickschutz, Wiederverwendung/Erneuerung von Prüfnachweisen, Grenzverletzung, expliziter Puls-Fallback und fehlender automatischer Netzwerk-Retry geprüft.
- `browser_live_power_check.py --serve`: Timeline-±10 W vor und nach Stufenwechsel, vollständiger Profilversatz, Pause/Fortsetzen, finaler Sliderwert, Originalerhalt, Ereignisse und passende normale Pi-/Tablet-Darstellung geprüft.
- `browser_fullscreen_check.py --serve`: sechs Displaygrößen, native Fullscreen-API/CSS-Fallback, Fokusführung, direkte ±10-W-Tasten ohne geöffneten Schieberegler, Gerätefehleranzeige und vorhandene Steuerelemente geprüft.
- Katalog-/Coach- und Provenienz-Browserprüfungen bestanden. Sämtliche Steuerprüfungen laufen gegen isolierte Demo-Server oder ausdrücklich synthetische UI-Verträge, ohne physisches Ergometer.

Screenshots aus der mobilen Browserprüfung (Vorschau, keine echten Messwerte): [normale Zeitachse](../screenshots/mobile-timeline-390x844.png), [Vollbild](../screenshots/mobile-timeline-fullscreen-390x844.png).

## Auslieferung auf den Pi

Der fertige Code ist als `2c342c5` auf `feat/fitness-cockpit` committed und gepusht. Das Paket wurde zunächst ausschließlich bereitgelegt, während eine echte 25-Minuten-Einheit lief. Erst nach Planende, erfolgreichem Speichern und zwei bestätigten Leerlaufzuständen wurde installiert. Die Fahrt wurde weder pausiert noch vorzeitig gestoppt.

- Paket: 52 Dateien, SHA-256 `edc0f6c774439df0613b6d6cf0ff8408f5db6a9d1db38b66af0e0b90080776fb`.
- Stage: `/home/gha/fitness-cockpit-stage-20261124-mobile-edc0f6c7`.
- Rücknahme-Backup: `/home/gha/daum-studio/backups/before-cockpit-20261124-203819-906882`.
- Originaldaten vollständig erhalten: 2 Benutzer, 22 Pläne, **7 Fahrten einschließlich der gerade beendeten Einheit**, 2 Einstellungen und 5 Profilprüfungen; alle zehn Anwendungstabellen wurden auf unveränderte Bestandszeilen geprüft.
- Sämtliche 52 installierten Dateien stimmen mit dem Manifest überein. Die Abschaltkonfiguration blieb unverändert. Anschließend war der Daum wieder verbunden; es wurde keine neue Trainingseinheit und kein Watt-Test ausgeführt.
- **207 Pi-Tests bestanden, ein optionaler XSD-Test übersprungen**. Die zwei Windows-Native-Bridge-Tests werden nicht auf den Pi kopiert.
- Die tatsächlich vom Pi ausgelieferte Oberfläche wurde in einem separaten Windows-Browser bei 390×844 und 800×480 geprüft: adaptive ViewBox, erreichbare direkte Watt-Tasten und Auswahl ohne zusätzliche POSTs oder `/session`-Abruf. Gemessene Auswahlzeit dieses Clients: etwa 180 ms; kein Messwert eines physischen Handys. Alle Steuer-POSTs waren für diese Prüfung ausdrücklich blockiert; Backend blieb im Leerlauf und ohne JS-Fehler.

Frontend-Build: `index-BCRUVb22.js`, `index-mQTP8dpA.css`. Auf bereits geöffneten Handy-/Pi-Seiten einmal neu laden, damit das neue JavaScript aktiv wird. Die automatische Wiederaufnahme eines Trainings bleibt ausgeschlossen.
