# Bedienung

## Erste Fahrt

1. App im Browser öffnen und oben den Benutzer wählen oder unter „Profile“ anlegen.
2. Für einen ersten Blick im Demo-Modus bleiben. Für die echte Fahrt „Daum verbinden“ wählen.
3. Freies Training oder einen Trainingsplan auswählen. Watttraining benötigt weder FTP noch Pulsgurt.
4. Watt-Intensität und gegebenenfalls Leistungsanpassung im Profil einstellen.
5. „Ride starten“ öffnet den Vorabcheck. Angaben prüfen und „Training jetzt starten“ wählen.

Ohne FTP verwenden relative Vorlagen die ausdrücklich gekennzeichnete Beispielbasis **150 W**. Das ist keine gemessene persönliche FTP. Eine hinterlegte lockere Ausgangsleistung wird bei Grundlagenplänen berücksichtigt. Eigene absolute Wattpläne lassen sich über „Wattwerte bearbeiten“ speichern.

## Watt oder Puls

„Wattgeführt“ fährt die angezeigten Wattstufen. Im freien Training lässt sich die Zielleistung manuell verändern. Bei laufendem Plan ist die manuelle Wattbedienung gesperrt.

„Pulsgeführt“ benötigt persönliche HFmax, Pulsgrenze und ein frisches Signal vom verbundenen BLE-Pulssensor. Die Regelung reagiert auf den Puls und kann daher von der geplanten Wattkurve abweichen. „Ohne Pulsgurt starten · Watttraining“ wechselt bewusst in den Wattmodus. Fehlende FTP ist auch dabei kein Startblocker.

## Zeitachse

Unter „Zeitraster“ Automatisch, 30 Sekunden oder 1/2/5/10 Minuten wählen. Das Wattraster bietet Automatisch und 25/50/100 W. Die Auswahl bleibt pro Browser erhalten. Die Zeitachse zeigt geplante Wattwerte, angelegtes Ziel, Ist-Leistung und die aktuelle Zeitposition.

Größere Blöcke tragen Watt- und Dauerangaben. Unter dem Diagramm zeigt „Dauer pro Leistungsstufe“ alle Stufen mit genauer Dauer, auch bei kurzen Abschnitten. Diagramm und Stufenliste lassen sich auf schmalen Displays horizontal verschieben.

## Berg & Tal

| Dauer | Szenarien |
| --- | --- |
| 35 Minuten | Hügelrunde · drei Wellen; Bergfahrt · zum Aussichtspunkt |
| 45 Minuten | Passstraße · lange Auffahrt; Doppelpass · zwei Anstiege |
| 60 Minuten | Alpenrunde · drei Anstiege; Gipfeltour · der lange Pass |

Im Planfilter „Berg & Tal“ wählen. Die Wattkurven bauen Last allmählich auf und senken sie auf Abfahrten. Rampen bestehen aus 30-Sekunden-Stufen; gleichbleibende Abschnitte können zusammengefasst sein. In der Bergansicht erscheinen Streckenprofil, Position und virtuelle Steigung. Die lokalen Programme berechnen keine realen Strecken-Höhenmeter und kein physikalisches Fahrmodell.

## Profile und Aktivitäten

Profile speichern Namen, optionale FTP und Pulswerte sowie Leistungsanpassung von −100 bis +100 W. Die aktiven Werte gelten gemeinsam auf allen Bediengeräten am Bike. Während einer Fahrt ist der Benutzerwechsel gesperrt.

Unter „Aktivitäten“ stehen beendete Fahrten des aktiven Benutzers. TCX, CSV und JSON enthalten die vorhandenen Messwerte. Mit „Löschen“ und anschließender Bestätigung wird eine Fahrt samt Messspur dauerhaft entfernt; Abbrechen lässt sie bestehen. Demo-Fahrten und -Exporte sind gekennzeichnet.

## Abschalten

App → Einstellungen → „Automatisch abschalten“ zeigt den Status. Ein Klick auf den Ein/Aus-Button speichert die Einstellung für den Pi, auch über Neustarts hinweg. Die Desktop-Verknüpfung „Daum Autoabschalten EIN-AUS“ schaltet dieselbe Einstellung um und zeigt das Ergebnis an.

Bei eingeschalteter Automatik folgen nach fünf Minuten ohne direkten Daum-LAN-Link: laufende Fahrt beenden und speichern, danach Pi herunterfahren. Wiederverbindung vor Ablauf setzt die Wartezeit zurück. Nach dem Herunterfahren startet der Pi durch erneutes Anschließen des Netzteils; Daum-Einschalten allein reicht ohne Zusatzhardware nicht.

Der schwarze Bildschirmschoner ist unabhängig davon. Touch oder Tastatur holt das Bild zurück; eine laufende Fahrt bleibt aktiv.
