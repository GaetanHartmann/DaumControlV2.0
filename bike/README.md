# DAUM Studio

Lokale Bike-Web-App für GHAPI3 (Raspberry Pi 3 B+, aarch64), entwickelt unter Windows.

## Start am Laptop

```powershell
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Frontend vorher mit `npm ci` und `npm run build` in `frontend` bauen. Für Entwicklung: Backend wie oben und `npm run dev` im Frontend. Browser: http://localhost:8000 (Build) oder http://localhost:5173 (Entwicklung).

## Pi

Quellcode, requirements.txt und frontend/dist nach `/home/gha/daum-studio` übertragen. Python-Venv erstellen, Anforderungen installieren. User-Service aus `deploy/daum-studio.service` nach `~/.config/systemd/user` kopieren, `systemctl --user daemon-reload` und `systemctl --user enable --now daum-studio`. Für Start ohne Benutzeranmeldung ist `loginctl enable-linger gha` mit Administratorrechten erforderlich. Genau **ein** Worker: Er besitzt die Bike-Verbindung und den Trainingszustand.

Weboberfläche: http://ghapi3.local:8000. API-Dokumentation: `/docs`. SQLite speichert Pläne und abgeschlossene Trainings; aktive Trainings werden nach Neustart nicht automatisch fortgesetzt.

## Funktionen und Grenzen

- Wattsteuerung 25–400 W (bewusst konservative App-Grenze), freie Trainings und zeitbasierte Trainingspläne. Pause und Stopp setzen bei echtem Bike 25 W und Stopp gibt anschließend die Steuerung ans Cockpit zurück. Ein Verbindungsabbruch kann nicht garantieren, dass das Bike einen Stopp empfängt: am Cockpit bedienbar halten.
- Standard ist **Demo**. Leistung, Kadenz und Geschwindigkeit sind dabei simuliert und entsprechend gekennzeichnet. Kein künstlicher Puls.
- Daum-Premium-TCP-Adapter mit V00-Prüfung, S20/S23-Steuerung, X70-Livewerten, Prüfsummen, Bestätigungen und Zeitlimits. Gegen Mock-TCP getestet, echter 8i-Test steht aus. Erfordert Pi-LAN 192.168.10.2/24, Bike 192.168.10.1/24, Fernsteuerung EIN, Bedienung sperren AUS, Automatisch, Standardprotokoll, Port 51955. WLAN behält die Standardroute; LAN braucht kein Gateway.
- Garmin: BLE Heart Rate Service über Bleak. Suche und Verbindung laufen auf dem Server/Pi. Nur Gurte mit Bluetooth, nicht reine ANT+-Gurte. Livewerte verfallen nach 10 Sekunden ohne Signal. Physischer Garmin-Test steht aus.
- **Zwift FTMS (Testversion)**: Direkter BlueZ-GATT-Server über dbus-next, unabhängig von Bleak. Dienste: Fitness Machine, Cycling Power, Heart Rate. BLE-Sender zuerst starten, dann Zwift-Steuerung explizit freigeben. In Zwift `DAUM Studio` als Leistungsquelle und steuerbaren Trainer wählen. ERG-Vorgaben 25–400 W, SIM-Road-Load-Modell mit Fahrer-/Radgewicht, Wind, Steigung, Crr und Cw. Leistungsänderungen maximal 25 W/s. Nur ein BLE-Gerät darf steuern; lokale Pläne und Wattbedienung sind während der Freigabe gesperrt. Lokaler Stopp, Verbindungsabbruch und fehlende Indikationsbestätigung stoppen das Training und entziehen die Freigabe. BLE-Wiederverbindung startet kein Training automatisch. Noch keine Bluetooth-Zertifizierung oder praktische Prüfung in Zwift.
- Mobil/Touch: responsive Vue-Oberfläche, WebSocket-Livewerte, lokale SVG-Radanimation. Fonts optional von Google; Systemfonts funktionieren offline.
- Für das eigene, vertrauenswürdige Heimnetz vorgesehen. Keine Internetfreigabe eingerichtet. Kein Login implementiert.

## Konditionsaufbau und Pulsmodus

Neun zusätzliche, idempotent angelegte Vorlagen (bestehende Pläne bleiben erhalten):

| Dauer | Grundlage | Tempo | Aerobe Intervalle / VO₂max-Ziel |
| --- | --- | --- | --- |
| 35 min | Einrollen + 20 min Grundlage + Ausrollen | 3×4 min, 3 min aktive Erholung | 3×3 min, 3 min aktive Erholung + Grundlage |
| 45 min | Einrollen + 32 min Grundlage + Ausrollen | 3×8 min, 3 min aktive Erholung | 4×4 min, 3 min aktive Erholung |
| 60 min | Einrollen + 45 min Grundlage + Ausrollen | 3×10 min, 5 min aktive Erholung | 4×4 min + 15 min Grundlage |

Watt-Startpunkte sind eigene, editierbare App-Vorschläge relativ zur persönlichen FTP: Einrollen 50 %, Grundlage 65 %, Tempo 85 %, intensive Intervalle 105 %, aktive Erholung 50 %, Ausrollen 40 %. Nicht als individuell passende oder wissenschaftlich festgelegte Wattwerte verstehen. Ohne FTP können alle Wattvorlagen direkt mit der sichtbar gekennzeichneten Beispielbasis 150 W gestartet werden. Dabei wird keine persönliche FTP gespeichert. Intensität und Profilanpassung ändern die angezeigte und gefahrene Wattkurve. Alternativ „Wattwerte bearbeiten“ und eigene absolute Werte speichern. Intensität für Watttraining ist zwischen 50 und 130 % der Vorlage veränderbar.

Cockpit-Ansichten: Rad, Zeitachse und Watt-Berg. Die Zeitachse zeigt Planblöcke, Live-Zeitmarke, angelegtes Ziel und tatsächliche Leistung. Im Pulsmodus sind Plan-Wattwerte nur Orientierung; entscheidend ist die persönliche Pulszone. Der Watt-Berg ist eine visuelle Lastdarstellung, keine gemessene Streckensteigung. Messspur wird alle 10 Sekunden erfasst und im Speicher begrenzt; SQLite speichert weiterhin Fahrtzusammenfassungen.

Pulsmodus: persönliche HFmax, bewusst gewählte Puls-Stoppgrenze und Wattgrenzen eintragen. Kein altersbasiert vorbesetzter Maximalpuls. Freies Puls-Cardio in 35/45/60 min oder pulsgeführte Vorlagen. Zielzonen in Prozent HFmax: Grundlage 60–70 %, Tempo 75–85 %, intensive Intervalle 85–95 % (später im Intervall); die obere Zielgrenze wird auf mindestens 3 bpm unter der persönlichen Stoppgrenze gedeckelt. Dies ist keine medizinische Sicherheitsgarantie. Bei Medikamenten oder Vorerkrankungen müssen geeignete Ziele individuell geklärt werden.

Regelung: kein Integralanteil; 45 Sekunden Einschwingphase je Abschnitt, sanfte Annäherung an die geplante Wattbasis, danach maximal +5 W je 15 Sekunden bei zu niedrigem Puls; Senkung bei zu hohem Puls. Kein Hochregeln bei niedriger Kadenz. Nach 3 Sekunden ohne frische Messung 25 W und Zeitachse anhalten; nach 10 Sekunden automatische Pause. Fortsetzen erfordert ein frisches Signal. Persönliche Pulsgrenze erreicht: Training stoppen, auf 25 W reduzieren und Steuerung freigeben. Bei Verbindungsfehlern kann die App den tatsächlichen Stopp am Gerät nicht garantieren.

Quellen und praktische Einordnung stehen direkt bei den Trainingsvorschlägen:

- [NTNU / CERG](https://www.ntnu.edu/cerg/regimen): Vorbild für die 4×4-Struktur und die verzögerte Pulsreaktion. Unsere 35/45/60-min-Varianten und Wattfaktoren sind eigene Anpassungen.
- [AHA](https://www.heart.org/en/healthy-living/exercise-and-physical-activity/fitness-basics/target-heart-rates): allgemeine Pulsorientierung und individuelle Einflüsse.
- [CDC](https://www.cdc.gov/physical-activity-basics/measuring/index.html): relative Intensität und Sprechtest.

Die Software misst oder schätzt keine VO₂max und verspricht keine Leistungsverbesserung. Der Regelalgorithmus ist mit simulierten Eingangssignalen getestet, noch nicht als vollständiges pulsgeführtes Training am echten Daum.

### Prüfen

### Orientierungsfahrt bei unbekannten Werten

Eine zusätzliche 20-minütige Einstiegsfahrt fährt 5 Minuten bei 25 W, fünf jeweils zweiminütige Stufen bei 40/50/60/70/80 W und 5 Minuten Ausrollen bei 25 W. Kein Maximaltest und keine automatische FTP-, HFmax- oder VO₂max-Bestimmung. Nur bei subjektiv lockerem Sprechen kann nach mindestens 60 Sekunden stabiler Stufe bewusst „Gut sprechbar“ gewählt werden. Aufzeichnung als `comfortable_watts`, ausdrücklich keine FTP. Speichern erfordert echtes Daum-Training, Messwerte und ausreichende Kadenz; Demo-Werte werden abgelehnt. Damit können die drei Grundlagenpläne an diese Ausgangsleistung angepasst werden, andere Vorlagen verwenden ohne FTP die gekennzeichnete Beispielbasis 150 W und können ebenfalls gestartet werden. Bei zu hoher Belastung direkt stoppen, nicht alle Stufen erzwingen.

### Export und iPhone

Unter Aktivitäten stehen pro Fahrt TCX-, CSV- und JSON-Downloads bereit. Neue Fahrten speichern zusätzlich die Messspur mit UTC-Zeitstempel, aktiver Trainingszeit, Ist-/Zielwatt, verfügbarem Puls, Kadenz, Geschwindigkeit und Strecke. Alte Fahrten behalten ihre Zusammenfassung; fehlende Messreihen werden nicht erfunden. UTC-Messzeitpunkte berücksichtigen reale Pausen. Demo-Exporte tragen `DEMO-` im Dateinamen und eine entsprechende Kennzeichnung im Inhalt. Das TCX-Sportformat ist Biking ohne GPS, mit Garmin-Power-Extensions. TCX wird gegen Garmins offizielles TrainingCenterDatabase-v2-XSD geprüft (optionaler Test mit lxml). Mechanische kJ sind keine Kalorien; das zwingende TCX-Feld Calories wird mit 0 und einem ausdrücklichen Hinweis ausgegeben. Importverhalten hängt von der Ziel-App ab.

TCX kann man bei kompatiblen Trainingsplattformen importieren, z. B. [Stravas Datei-Upload](https://support.strava.com/en-us/articles/15402066-how-do-i-get-my-activities-to-strava). Es gibt keinen automatischen Account-Upload. Apple Health benötigt eine native iPhone-App mit HealthKit-Schreibberechtigung und ggf. TCX-Importfunktion; die Pi-Web-App implementiert keine direkte HealthKit-Synchronisierung. [Apple-Dokumentation zur Berechtigung](https://developer.apple.com/documentation/healthkit/authorizing-access-to-health-data).

iPhone als Bediengerät: im selben WLAN Safari → `http://ghapi3.local:8000` oder Pi-IP. Optional in Safari „Teilen → Zum Home-Bildschirm“. Dies ist eine Verknüpfung zur zentralen Pi-App, kein offline arbeitender HealthKit-Client. Für Zwift auf iPhone ist zusätzlich die BLE-Trainerverbindung vorgesehen. Es gibt Anleitungen direkt unter Verbindungen → iPhone verbinden sowie Aktivitäten → Apple Health & Export.

### Prüfkommandos

Trainings- und FTMS-Backend-Tests auf Windows und ARM64-Pi bestanden. Tatsächlicher BLE-Rundlauf zwischen Windows-Bleak-Client und isolierter Pi-Demo getestet: Advertising-Name/UUIDs, Verbindungsaufbau, Control-Point-Indications, Live-Notifications, ERG/SIM und lokaler Entzug der Steuerung. Browserprüfung für Freigabe/Sperre und Mobilansicht bestanden. Dies ersetzt noch keinen Test in der Zwift-App mit echtem Daum.

### Zwift benutzen

1. Daum verbinden (oder bewusst die Demo benutzen).
2. Verbindungen → Zwift Connect → BLE-Sender starten.
3. Fahrer- und Radgewicht eintragen; Zwift-Steuerung freigeben.
4. In Zwift DAUM Studio sowohl als Leistungsquelle als auch als steuerbaren Trainer wählen; optional Kadenz und Herzfrequenz.
5. Training in Zwift starten. ERG und SIM werden anhand der empfangenen FTMS-Befehle umgeschaltet. Lokales Stoppen entzieht sofort die Freigabe; nach einem Abbruch erneut freigeben.

```powershell
.venv\Scripts\python -m pytest -q
```

## Quellen

- https://github.com/incyclist/devices – Daum-Premium-Protokollreferenz, MIT. Kein Quellcode kopiert.
- https://ackstorm.de/projects/daum/daum.html – 8i-Netzwerkdokumentation.
- https://ergo.ub-online.de/index.php/de/konfiguration/verbindung-ergometer-app/konfiguration-daum-8-8i – Cockpit-Einstellungen.
- https://bleak.readthedocs.io/ – BLE-Client.
- https://bluez.readthedocs.io/en/latest/gatt-api/ – direkter Linux-GATT-Server.
- https://www.bluetooth.com/specifications/specs/fitness-machine-service-1-0/ – FTMS-Protokoll.



## Benutzerprofile und Trainingsstart

Oben im Kopfbereich den Benutzer auswählen. Unter „Profile“ neue Benutzer anlegen, umbenennen und eigene FTP-, Ausgangsleistungs- und Pulswerte speichern. Der aktive Benutzer bleibt nach einem Neustart erhalten. Die Auswahl gilt gemeinsam für alle Bediengeräte am selben Bike. Während einer Fahrt oder freigegebener Zwift-Steuerung ist der Wechsel gesperrt. Bestehende Werte und Aktivitäten werden einmalig dem Benutzer „Standard“ zugeordnet. Aktivitäten werden nach aktivem Benutzer angezeigt; dies ist keine Anmeldung oder Zugriffstrennung. Trainingspläne bleiben gemeinsam nutzbar und werden mit den persönlichen Werten berechnet.

„Ride starten“ öffnet zuerst den Vorabcheck. Dort Benutzer, Plan, Demo/Daum und Pulssignal prüfen, bei Bedarf Daum oder einen Bluetooth-Pulssensor verbinden und dann „Training jetzt starten“ wählen. Watttraining geht auch ohne Pulsgurt, Pulssteuerung benötigt ein frisches Signal und persönliche Pulsgrenzen. Fehler bleiben im Dialog sichtbar.

Apple Watch: Die App unterstützt keine native GymKit-Kopplung. Eine BLE-Brücke wie HeartCast auf iPhone und Watch kann das Pulssignal als Bluetooth-Sensor bereitstellen: Übertragung dort starten, iPhone nahe am Pi halten, im Vorabcheck suchen und den HeartCast-Sensor verbinden. Anleitung: https://www.heartcast.app/faq-help-support-issues/ . Die konkrete Kombination mit dem Pi ist noch nicht praktisch geprüft.

### Leistungsanpassung und Alles verbinden

Im Benutzerprofil „Leistungsanpassung (W)“ mit Minus/Plus in 5-W-Schritten ändern und persönliche Werte speichern. Bereich −100 bis +100 W. Planabschnitte werden zuerst mit der Intensität skaliert, dann um diesen Wert angepasst und abschließend auf 25–400 W begrenzt. Vorschau und Start verwenden dieselbe Berechnung. Dies gilt für Vorlagen und eigene Pläne; die Orientierungsfahrt behält ihre festen Wattstufen. Freies Watttraining hat weiterhin seine manuelle Zielleistung. Pulsmodus behält Watt- und Pulsgrenzen.

„Alles verbinden“ im Kopfbereich oder Vorabcheck verbindet Daum und einen Bluetooth-Pulssensor. Gerätefehler werden unabhängig angezeigt. Ein einzelner gefundener Pulssensor wird verbunden, bei mehreren muss der Benutzer auswählen. Ein Training oder eine Zwift-Steuerfreigabe wird dadurch nicht gestartet. Verbindungsänderungen sind während aktiver Trainings gesperrt; ein Sensor kann bei pausiertem Training gewechselt werden.

Nach 300 Sekunden ohne Bedienung zeigt der Pi ein schwarzes Vollbild; Berührung oder Tastatureingabe holt die Trainingsansicht zurück. Das HDMI-Signal bleibt dabei aktiv, damit der Monitor keine „No Signal“-Meldung einblendet. Die Hintergrundbeleuchtung bleibt eingeschaltet. Backend und laufende Fahrten bleiben aktiv. Einrichtung mit `python3 deploy/install-display-idle.py` als Desktop-Benutzer. Der Benutzer-Service `daum-studio-display-idle.service` startet über Desktop-Autostart. Der gerätespezifische Prüfer `deploy/check-display-idle.py` prüft das schwarze Bild und das Aufwecken über ADS7846-Touch und stellt Anzeige und Timer anschließend wieder her; nur bei gestopptem Training ausführen.

## Zeitraster und virtuelle Bergstrecken

In der Zeitachse lassen sich Zeitraster (Automatisch, 30 s, 1/2/5/10 min) und Wattraster (Automatisch, 25/50/100 W) einstellen. Die Auswahl bleibt pro Browser gespeichert. Die Leistungsstufen zeigen ihre genaue Dauer, einschließlich Sekunden; eine scrollbar bedienbare Stufenübersicht ergänzt kurze Diagrammblöcke. Schmale Displays können das Diagramm horizontal verschieben.

Unter „Berg & Tal“ gibt es sechs zusätzliche Vorlagen: Hügelrunde und Bergfahrt (35 min), Passstraße und Doppelpass (45 min), Alpenrunde und Gipfeltour (60 min). Die Wattkurven ändern sich in 30-Sekunden-Schritten mit weichen Übergängen, Plateauphasen und leichteren Abfahrten. Die Bergansicht zeigt die virtuelle Steigung und die Position im schematischen Streckenprofil. Das sind zeitbasierte ERG-Szenarien relativ zur persönlichen FTP bzw. zur ausdrücklich angezeigten Beispielbasis 150 W, keine physikalische Streckensimulation oder gemessenen Höhenmeter.

## Automatisch herunterfahren, wenn der Daum aus ist

Der optionale Systemdienst beobachtet den **direkten** LAN-Link auf `eth0`. Nach fünf Minuten ohne Link beendet und speichert er ein laufendes Training über die App und fährt den Pi sauber herunter. Kommt die Verbindung vorher zurück, beginnt die Wartezeit beim nächsten Ausfall neu. Ein unbekannter LAN-Status oder ein fehlgeschlagenes Speichern löst kein Herunterfahren aus. WLAN wird dafür nicht ausgewertet. Auch beim Start ohne eingeschalteten Daum gilt die Wartezeit. Ein zwischengeschalteter Switch kann den Link aktiv halten; diese Lösung setzt das direkte Kabel zum Daum voraus.

Auf dem Pi installieren (Installer, `daum-power-watch.py` und `toggle-power-watch.py` aus `deploy` im selben Verzeichnis):

```sh
sudo sh deploy/install-daum-power-watch.sh
systemctl status daum-power-watch.service
```

Deaktivieren: `sudo systemctl disable --now daum-power-watch.service`. Zum Prüfen ohne Herunterfahren und ohne Trainingsänderungen: `python3 deploy/daum-power-watch.py --dry-run`.

Der Raspberry Pi 3 B+ unterstützt kein normales Wake-on-LAN. Nach dem Herunterfahren startet er bei erneutem Anschließen des Netzteils. Automatischer Start allein durch Einschalten des Daum benötigt zusätzliche Hardware.

Die Abschaltautomatik lässt sich unter Einstellungen in der App oder mit „Daum Autoabschalten EIN-AUS“ auf dem Pi-Desktop ohne Passwort umschalten. Der Status bleibt in `/var/lib/daum-studio/power-watch.json` nach Neustarts erhalten. Ausschalten der Automatik setzt die laufende Wartezeit zurück. Der Systemdienst bleibt dafür im Hintergrund aktiv.
