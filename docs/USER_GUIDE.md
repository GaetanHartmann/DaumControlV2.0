# Bedienung

## Erste Fahrt

1. App im Browser öffnen und oben den Benutzer wählen oder unter „Profile“ anlegen.
2. Für einen ersten Blick im Demo-Modus bleiben. Für die echte Fahrt „Daum verbinden“ wählen.
3. Freies Training oder einen Trainingsplan auswählen. Watttraining benötigt weder FTP noch Pulsgurt.
4. Watt-Intensität und gegebenenfalls Leistungsanpassung im Profil einstellen.
5. „Training starten“ anklicken. Die App prüft das gewählte Profil und die aktuellen Grenzen automatisch und startet bei gültigen Angaben direkt. Zusätzliche Prüf- oder Bestätigungsdialoge entfallen; ein Hindernis wird als Meldung angezeigt.

Ohne FTP verwenden relative Vorlagen die ausdrücklich gekennzeichnete Beispielbasis **150 W**. Das ist keine gemessene persönliche FTP. Eine hinterlegte lockere Ausgangsleistung wird bei Grundlagenplänen berücksichtigt. Eigene absolute Wattpläne lassen sich über „Wattwerte bearbeiten“ speichern.

## Watt oder Puls

„Wattgeführt“ folgt den angezeigten Wattstufen. Während eines laufenden Stufenplans verschieben Schieberegler und ±10-W-Tasten die gesamte Wattkurve nach oben oder unten, ohne die Fahrt zurückzusetzen. Der Versatz bleibt beim Stufenwechsel erhalten. „Zurück zum Trainingsplan“ entfernt ihn und übernimmt den für die aktuelle Position gültigen Planwert. Geräte- und Nutzergrenzen begrenzen jede Stufe.

„Pulsgeführt“ benötigt persönliche HFmax, Pulsgrenze und ein frisches Signal vom verbundenen BLE-Pulssensor. Die Regelung reagiert auf den Puls und kann daher von der geplanten Wattkurve abweichen. „Ohne Pulsgurt starten · Watttraining“ wechselt bewusst in den Wattmodus. Fehlende FTP ist auch dabei kein Startblocker.

## Zeitachse

„⛶ Zeitachse“ öffnet das Diagramm als eigene Vollbildansicht. „⛶ Kennzahlen“ öffnet eine separate Übersicht mit allen 17 Live- und Statusfeldern. Oben zwischen den Ansichten wechseln; „Schließen“ oder Escape führt zurück. Pause/Fortsetzen und Stopp bleiben während einer Fahrt oben erreichbar. „Wattsteuerung“ klappt die vorhandenen Leistungsregler auf. Das Öffnen oder Wechseln der Ansicht verändert keine Trainingswerte und sendet keinen Gerätebefehl. Fehlende oder nicht nachgewiesene Messwerte bleiben als `—` gekennzeichnet.

Unter „Zeitraster“ Automatisch, 30 Sekunden oder 1/2/5/10 Minuten wählen. Das Wattraster bietet Automatisch und 25/50/100 W. Die Auswahl bleibt pro Browser erhalten. Die Zeitachse zeigt geplante Wattwerte, angelegtes Ziel, Ist-Leistung und die aktuelle Zeitposition.

Die Zeitachse passt ihre Zeichnung und Beschriftungsdichte an die tatsächliche Displaygröße an, auch im Hoch- und Querformat. Die ganze Kurve bleibt auf dem Bildschirm. Größere Blöcke tragen Watt- und Dauerangaben; kurze Stufen lassen sich antippen und über Vor/Zurück durchgehen. Die darunterliegende Stufenliste lässt sich weiterhin horizontal verschieben.

Direkt an der Zeitachse stehen −10 W und +10 W; im Vollbild sind sie ohne Aufklappen erreichbar. „Plan +10 W“ zeigt beispielsweise den Versatz. Die verschobene Kurve wird gefüllt dargestellt, das Original bleibt als dezente Referenz sichtbar. Die Tasten für einen ausgewählten Stufenplan werden mit laufendem Training aktiv. Vorher lassen sich Intensität und Profilwerte einstellen. „Wattsteuerung“ öffnet zusätzlich Schieberegler und Planrückkehr.

## Berg & Tal

| Dauer | Szenarien |
| --- | --- |
| 35 Minuten | Hügelrunde · drei Wellen; Bergfahrt · zum Aussichtspunkt |
| 45 Minuten | Passstraße · lange Auffahrt; Doppelpass · zwei Anstiege |
| 60 Minuten | Alpenrunde · drei Anstiege; Gipfeltour · der lange Pass |

Im Planfilter „Berg & Tal“ wählen. Die Wattkurven bauen Last allmählich auf und senken sie auf Abfahrten. Rampen bestehen aus 30-Sekunden-Stufen; gleichbleibende Abschnitte können zusammengefasst sein. In der Bergansicht erscheinen Streckenprofil, Position und virtuelle Steigung. Die lokalen Programme berechnen keine realen Strecken-Höhenmeter und kein physikalisches Fahrmodell.

## Profile und Aktivitäten

Unter „Strecken“ stehen Grafrath–Ampermoos (7,4 km) und eine Ammerseerunde (46,0 km) mit OSM-Koordinaten und amtlichen Bayerischen Geländehöhen offline zur Auswahl. Anklicken zeigt die 2D-Geometrie und das Höhenprofil; „Als eigene Strecke übernehmen“ speichert eine persönliche Kopie. Die Vorschau verändert keine Wattvorgabe. Quellen und Lizenzen werden angezeigt. Eine 3D-Fahrt ist noch offen. Details: [Streckendaten](research/route-data-2026-11-09.md).

Profile speichern Namen, optionale FTP und Pulswerte sowie Leistungsanpassung von −100 bis +100 W. Die aktiven Werte gelten gemeinsam auf allen Bediengeräten am Bike. Während einer Fahrt ist der Benutzerwechsel gesperrt.

Unter „Aktivitäten“ stehen beendete Fahrten des aktiven Benutzers. TCX, CSV und JSON enthalten die vorhandenen Messwerte. Mit „Löschen“ und anschließender Bestätigung wird eine Fahrt samt Messspur dauerhaft entfernt; Abbrechen lässt sie bestehen. Demo-Fahrten und -Exporte sind gekennzeichnet.

## Abschalten

App → Einstellungen → „Automatisch abschalten“ zeigt den Status. Ein Klick auf den Ein/Aus-Button speichert die Einstellung für den Pi, auch über Neustarts hinweg. Die Desktop-Verknüpfung „Daum Autoabschalten EIN-AUS“ schaltet dieselbe Einstellung um und zeigt das Ergebnis an.

Bei eingeschalteter Automatik folgen nach fünf Minuten ohne direkten Daum-LAN-Link: laufende Fahrt beenden und speichern, danach Pi herunterfahren. Wiederverbindung vor Ablauf setzt die Wartezeit zurück. Nach dem Herunterfahren startet der Pi durch erneutes Anschließen des Netzteils; Daum-Einschalten allein reicht ohne Zusatzhardware nicht.

Der schwarze Bildschirmschoner ist unabhängig davon. Touch oder Tastatur holt das Bild zurück; eine laufende Fahrt bleibt aktiv.


Während einer Fahrt kann der BLE-Pulsgurt im Pulsdialog gesucht und verbunden werden. Nach einem Verbindungsabbruch versucht die App den zuletzt verbundenen Gurt alle fünf Sekunden erneut zu verbinden; bewusstes Trennen beendet diese Versuche. Ein pausiertes pulsgesteuertes Training wird dadurch nicht automatisch fortgesetzt.

Bei wattgeführten Stufenplänen verschieben Slider und ±10 W die gesamte Kurve um die Differenz zur aktuellen Planstufe. Jede Stufe wird auf die eingestellten Geräte- und Nutzergrenzen begrenzt. Der Originalplan bleibt erhalten; „Zurück zum Trainingsplan“ entfernt die Verschiebung. Im freien Training und bei Pulssteuerung bleibt die manuelle Vorgabe ein absoluter Wattwert.

Der zuletzt ausgewählte Benutzer bleibt auf dem gemeinsamen Cockpit gespeichert und wird auch nach einem Neustart wieder geladen. Der aktive Benutzer ist oben im Cockpit sichtbar; ein Training startet erst nach deinem Start-Klick. „Training vorbereiten“ übernimmt das bereits geladene Profil sofort ins Cockpit und startet keine Einheit.
