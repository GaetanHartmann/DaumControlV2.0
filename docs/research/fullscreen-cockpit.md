# Getrennte Vollbildansichten im Fitness-Cockpit

Stand: 09.11.2026.

Der Pi startet Chromium bereits mit `--kiosk`, eigener Browserkonfiguration und
der lokalen App. Das war beim ausschließlich lesenden SSH-Abgleich nachweisbar.
Die App enthielt die normalen Ansichten Rad, Zeitachse und Berg. Browser-Kiosk
allein blendete die App-Navigation und die übrigen Cockpit-Bereiche nicht aus.

Die App bietet jetzt zwei eigene Einstiege: **Zeitachse im Vollbild** und
**Kennzahlen im Vollbild**. Die Zeitachse nutzt die vorhandene
`WorkoutTimeline` mit Plan, angefordertem Sollwert, Messkurve und Zeitmarker.
Die Kennzahlenansicht zeigt 17 Felder einschließlich getrennter Ist-Leistung,
Anforderung, Geräterückmeldung, unverifizierter Gerätemeldung und der beiden
Geräteverbindungen. Fehlende Messwerte bleiben `—`; Daum-Messgrenzen bleiben
sichtbar. Die ursprüngliche Rad-/Bergansicht bleibt vorhanden.

Pause/Fortsetzen, Stopp und Schließen sind oben erreichbar. Die Wattsteuerung
klappt unten auf und benutzt die vorhandene gedrosselte Sollwertsteuerung:
Slider, ±10 W und Rückkehr zum aktuellen Trainingsplan. Ein Ansichtswechsel
sendet keinen Gerätebefehl und verändert weder Einheit noch Uhr oder Profil.
Bei einer abgeschlossenen Einheit öffnet die App nach dem Schließen der
Vollbildansicht die vorhandene Ergebnisanzeige.

`useCockpitFullscreen(tab, state)` verwaltet ausschließlich die Ansicht.
`enter('timeline'|'metrics')` ruft nach dem Benutzerklick nach Möglichkeit die
Fullscreen API auf. Bei fehlender Unterstützung oder Ablehnung bleibt die
Ansicht innerhalb des Browserfensters bildfüllend benutzbar. Schließen und
Escape beenden sie; Browser-Reload stellt sie nicht ungefragt wieder her.
Der normale Seiteninhalt ist währenddessen `inert` und für Screenreader
ausgeblendet. Der Tastaturfokus bleibt im Dialog und kehrt anschließend zum
Einstieg zurück. Für die physischen Gerätefähigkeiten ist weiterhin die
bestehende Backend-Steuerung maßgeblich.

Geänderte/ergänzte Dateien:

- `bike/frontend/src/immersive-cockpit.ts`: Ansichtsverwaltung und Dialog.
- `bike/frontend/src/immersive-cockpit.css`: Bildschirm-, Touch- und
  Orientierungsanpassung, einschließlich 800 × 480.
- `bike/frontend/src/main.ts`: Einstieg, Daten-/Ereignisbindung und inerte
  Unterlage.
- `bike/frontend/src/live-training.css`: platzsparende Einstiegsbuttons im
  bestehenden Cockpit.
- `bike/tests/browser_fullscreen_check.py`: isolierter Browser-Vertragstest.

Prüfung lokal aus `bike`:

```powershell
npm.cmd --prefix frontend run build
.venv\Scripts\python.exe tests/browser_fullscreen_check.py --serve
```

Der Test startet eine frische temporäre SQLite-Installation auf Loopback-Port
8036. Ein ausdrücklich synthetischer WebSocket liefert laufende Daum-Werte;
Steueraufrufe werden ausschließlich im Browser beantwortet. Die echte
Testinstallation bleibt unverbunden, im Demo-Modus und ohne Trainingseintrag.
Geprüft werden beide Ansichten, 17 Kennzahlen, unbekannte Werte, die abgelehnte
Fullscreen API, Escape, Fokus, inerte Unterlage, ≥44-px-Bedienziele, die
bestehende Ereignisbindung der Watt-/Pause-/Stoppsteuerung und 800 × 480,
1024 × 768, 390 × 844 sowie 844 × 390. Eine zweite Seite versucht zusätzlich
die echte Browser-Fullscreen-API. Screenshots gehen in das temporäre
Windows-Verzeichnis; ihre Werte sind synthetisch. Das ist kein neuer
Hardware-Nachweis. Die tatsächliche Pi-Auslieferung wird durch den separaten
Bereitstellungsablauf geprüft.
