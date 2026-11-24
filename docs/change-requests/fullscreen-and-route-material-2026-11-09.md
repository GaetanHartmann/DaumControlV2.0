# Vollbild-Cockpit und geladenes Streckenmaterial

Stand: 09.11.2026. Ergänzung zur [P0/P1-Übergabe](p0-p1-implementation-2026-11-09.md).

## Bedienung

Im Training öffnen die beiden Knöpfe **⛶ Zeitachse** und **⛶ Kennzahlen** getrennte bildfüllende Ansichten. Die Zeitachse zeigt ausschließlich das große Diagramm samt Legende; die Kennzahlenansicht zeigt 17 Mess-, Zeit-, Profil- und Verbindungsfelder. Pause/Fortsetzen, Stopp und Schließen bleiben oben erreichbar. Unten klappt „Wattsteuerung“ die bestehenden Schieberegler-/±10-W-/Planrückkehr-Aktionen auf. Schließen oder Escape führt zurück. Fehlende Messwerte bleiben leer; Anforderungen, Geräterückmeldungen und unverifizierte Gerätewerte sind getrennt.

Ein Ansichtswechsel verändert keinen Trainingszustand und sendet keinen Gerätebefehl. Native Browser-Fullscreen-API und bildfüllender CSS-Fallback werden unterstützt. Die Unterlage ist währenddessen inert, der Tastaturfokus bleibt im Dialog. Ein Reload öffnet das Vollbild nicht automatisch. API-Fehler sind auch innerhalb der Ansicht sichtbar. Die Leistungsanzeige verwendet dieselben Daten und dieselbe Steuerlogik wie das bisherige Cockpit.

Unter **Strecken** sind zwei offline geladene OSM-Rundkurse auswählbar: Grafrath–Ampermoos (7,385 km) und Ammersee (45,997 km). Alle 1813 Wegpunkte haben amtliche Bayerische Geländehöhen. Vorschau öffnet keine Trainingseinheit; eine persönliche Kopie wird erst mit „Als eigene Strecke übernehmen“ gespeichert. 2D-Linie und Höhenprofil sind vorhanden. Eine 3D-Fahrt bleibt offen. Die Daten sind keine geprüfte Außennavigation. [Geometrie, Höhen, Herkunft und Lizenzen](../research/route-data-2026-11-09.md).

## Dateien und Architektur

- `bike/frontend/src/immersive-cockpit.ts` / `.css`: beide Ansichten, Anzeigezustand und Fokusführung.
- `bike/frontend/src/main.ts`, `live-training.css`: Einstieg, Daten- und Ereignisbindung, platzsparende Pi-Darstellung.
- `bike/frontend/src/virtual-routes.ts`: Offline-Bibliothek, Vorschau und explizite persönliche Übernahme; veraltete Antworten nach Benutzerwechsel werden verworfen.
- `bike/backend/routes.py`, `routes_material.py`: schreibfreie Bibliotheks-Endpunkte, geprüfter Loader und benutzergebundener Import.
- `bike/data/routes/`: zwei JSON-Datensätze, Index, Prüfsummen, Herkunft und separate Datenlizenz.
- `bike/deploy/fetch-route-material.py`: reproduzierbarer OSM-/Höhendownload mit Offline-Rebuild.
- `bike/deploy/package-cockpit-update.py`, `install-cockpit-update.py`: Daten/Lizenzdatei im geprüften Paket, API-/Datensatzprüfung und bestehender Rücknahmeablauf.
- `bike/tests/browser_fullscreen_check.py`, `browser_routes_check.py`, `test_route_material.py`, `test_routes.py`, `test_cockpit_deploy.py`: Anzeige-, Daten-, Isolations- und Installationsprüfung.
- `tools/download_daum_material.py`, `tools/tests/`: 11 fest versionierte Referenzdateien mit Hashprüfung im ignorierten privaten Cache. Keine Downloads werden als Code ausgeführt. [Daum-Befunde und offene Messfragen](../research/daum-material-2026-11-09.md).

Das bestehende Backend, die SQLite-Datenhaltung, der Daum-Adapter und die Laufzeit-Wattsteuerung werden weiterverwendet. Öffnen/Schließen der Ansichten führt keine neue Geräteaktion ein. Die Hardware-Messqualität wurde durch die neuen Dokumente nicht als verifiziert freigegeben.

## Prüfung

- Windows: **208 Tests bestanden**; fünf zusätzliche Offline-Downloader-Tests bestanden.
- Pi: **205 Tests bestanden, ein optionaler Test übersprungen**. Die zwei Windows-Native-Bridge-Tests werden nicht ausgeliefert; der optionale Pi-Skip betrifft die Garmin-XSD-Prüfung.
- Vite-Produktionsbuild und TypeScript-Prüfung erfolgreich.
- Browser: getrennte Ansichten, 17 Kennzahlen, vier Bildschirmgrößen, 44-px-Touchziele, Escape/Fokus, inert-Unterlage, abgelehnte und echte native Fullscreen-API, sichtbare Fehler sowie ausschließlich gemockte Steuerereignisse geprüft. Kein physischer Gerätezugriff dieser Tests.
- Bestehender Live-Watt-Browsertest: letzter Sliderwert, Override über Stufenwechsel, Rückkehr zum aktuellen Plan, Pause/Fortsetzen, unverändertes Originalprofil und persistiertes Ereignisprotokoll bestanden.
- Bestehender Provenienz-Browsertest und erweiterter Strecken-Browsertest bestanden. Keine JS-Fehler; normale Pi-Ansicht passt weiterhin in 800×480.

Start und Demo-Modus bleiben wie in [bike/README.md](../../bike/README.md) beschrieben. Die Streckenbibliothek braucht im Laufzeitbetrieb keinen Internetzugang oder API-Schlüssel. Zum erneuten Prüfen aus `bike`:

```powershell
.venv\Scripts\python.exe -m pytest -q tests --import-mode=importlib
npm.cmd --prefix frontend run build
.venv\Scripts\python.exe tests/browser_fullscreen_check.py --serve
.venv\Scripts\python.exe tests/browser_routes_check.py
```

## Pi-Auslieferung

52 geprüfte Dateien; finales Archiv SHA-256:
`a4122d6dc4c2bebed6706b100bc0ba1748e0b34f6de98e0ab5efbaa37cc07583`.
Installations-Stage: `/home/gha/fitness-cockpit-stage-20261109-fullscreen-final-a4122d6d`.
Rücknahme-Backup: `/home/gha/daum-studio/backups/before-cockpit-20261109-215330-484193`.

Der Installer hat alle ursprünglichen Datensätze unverändert erhalten: 2 Benutzer, 22 Pläne, 4 Fahrten, 2 Einstellungen und eine Profilprüfung. Auch die übrigen fünf Katalog-/Planer-/Streckentabellen sind geprüft. Die Abschaltkonfiguration blieb unverändert. Vor dem Dienstneustart wurde die unbenutzte Daum-Verbindung lediglich geschlossen; anschließend nur wieder verbunden. Kein neues Watt-Testprogramm und keine Trainingseinheit wurden ausgeführt.

Frontend-Build: `index-DyKQ1FZs.js`, `index-DF7Yofp_.css`.
Die lokale Pi-App ist unter `http://ghapi3.local:8000` erreichbar.

Anschließend wurden beide Ansichten im tatsächlichen Pi-Chromium über dessen nur lokal erreichbare Debugschnittstelle geöffnet und geschlossen. Beide meldeten natives Browser-Vollbild bei 800×480, keine horizontale Überbreite und eine inerte Unterlage. Alle 17 Kennzahlenkacheln lagen vollständig im Bildschirm. Während der Prüfung gab es keinen Steuer-POST, keinen Trainingsstart und keine Änderung von Benutzer, Daum-Modus oder Verbindungszustand. Die App kehrte in das normale Training zurück. Die Screenshots zeigen den tatsächlichen Leerlauf ohne erfundene Live-Messwerte:

- [Zeitachse auf dem Pi](../screenshots/pi-fullscreen-timeline-800x480.png)
- [Kennzahlen auf dem Pi](../screenshots/pi-fullscreen-metrics-800x480.png)

Auch die Streckenansicht wurde im Pi-Browser geöffnet: zwei Bibliothekseinträge, echte Geometrie, amtliches Höhenprofil und sichtbare Namensnennung bestätigt; keine persönliche Übernahme und kein Steuer-POST. [Pi-Streckenauswahl](../screenshots/pi-offline-routes-800x480.png).

Die Darstellung mit laufendem Training und die Schaltflächen Pause/Stopp wurden ausschließlich gegen den synthetischen Browservertrag geprüft. Ein neuer physischer Belastungs- oder Pulsgurttest gehört nicht zu dieser UI-Auslieferung.
