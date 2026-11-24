# Fitness-Cockpit: Training, Planung und Datengrundlage

Fitness-Cockpit ist der vorläufige Produktname. Die bestehende Daum-Verbindung,
SQLite-Datenbank, Radprogramme und Exporte werden weiterverwendet. Die folgenden
Erweiterungen benötigen keine zusätzliche Smartphone-App.

## Generierte Trainingsprofile

Der Generator erzeugt Ausdauer-, Intervall- und Regenerationsprogramme mit
Aufwärmen und Ausrollen. Gesamtdauer, gewählte Wattbasis und Phasendauern werden
vor dem Speichern als Leistungsprofil gezeigt. Die Erzeugung verändert keine
vorhandene Vorlage und startet kein Training. Das gespeicherte Ergebnis kann wie
ein eigener Radplan ausgewählt und als Kopie bearbeitet werden.

Grenzen: 10–120 Minuten Gesamtdauer, 1–20 Minuten je Aufwärm-/Cooldownphase, beide
Phasen zusammen kürzer als die Gesamtdauer. Bei den Standardphasen von je fünf
Minuten muss das Training deshalb mindestens elf Minuten dauern. Die Wattbasis
liegt innerhalb der bisherigen Daum-Grenzen von 25–400 W; diese technische Grenze
ist keine persönliche Belastungsempfehlung. Es wird keine FTP erfunden und keine
automatische Steigerung aus einer einzelnen Einheit erzeugt.

## Profil und Analyse

Geburtsjahr, Gewicht, Größe und Geschlecht sind optional. Die vorhandenen
Leistungs- und Pulsfelder bleiben erhalten. Nur ein zur Fahrt gespeichertes
Gewicht wird für Watt/kg verwendet. Eine spätere Gewichtsänderung schreibt keine
historischen Werte um. Aus Alter, Größe oder Geschlecht werden weder HFmax,
Kalorien, FTP noch Diagnosen abgeleitet; diese Felder bleiben beschreibend.

Die Analyse verwendet reale Radeinheiten. Demo- und manuelle Laufbandeinträge sind
von Radempfehlungen ausgeschlossen. Leistungsabhängige Hinweise werden erst bei
mindestens 80 % gültiger Leistungsabdeckung angezeigt. Bei alten Einheiten ohne
gespeicherte Aggregation oder ausreichende Datengrundlage bleiben diese Hinweise
nicht verfügbar. Mittelwerte werden über gültige Messzeit gewichtet; ihre
Datenabdeckung gehört zur Aussage. Null ist ein möglicher echter Leistungswert,
kein Ersatz für eine fehlende Messung.

Watt/kg beschreibt die Leistung bezogen auf Körpergewicht. Die angezeigte
Relation zu einer hinterlegten FTP ist eine Rechenrelation, keine medizinische
Einstufung. Ein Vergleich berücksichtigt nur reale Radeinheiten derselben Person
mit ähnlicher Dauer (±20 %) und ausreichender Leistungsabdeckung. Unterschiede
können auch vom gewählten Plan, Pausen oder Tagesform abhängen. Die Verlaufswerte
aus dem ersten und letzten Drittel basieren auf gespeicherten Stichproben und
werden ausdrücklich als Näherung gekennzeichnet.

Zusätzlich ist unabhängig verifizierte Leistungsmessung erforderlich:
`power_measurement_verified: true` und
`measurement_quality.power_watts: verified_measured`. Die beim Daum-Test auch im
Stillstand dem Sollwert folgende X70-Angabe erfüllt das nicht. Alte Daum-Aggregate
bleiben unverändert archiviert, werden aber nicht für Watt/kg, Intensität,
Leistungsvergleich, Leistungstrend oder belastungsabhängige Empfehlungen genutzt.
Eine Gerätebestätigung ist keine Messung der Tretleistung. Ohne verifizierte
Quelle bleiben diese Kennzahlen und mechanische Arbeit nicht verfügbar.

Kalorien sind nicht gemessen und bleiben nicht verfügbar. Mechanische Arbeit in
kJ ist eine andere Größe und wird nicht als Stoffwechselverbrauch in kcal
ausgegeben. Die Auswertung misst keine VO₂max und erlaubt keine verlässliche
allgemeine Fitnessbestimmung aus einer Einheit.

## Nächste Einheit und persönlicher Plan

Bei ausreichenden realen Leistungsdaten wird eine bewusst lockere, bearbeitbare
Folgeeinheit vorgeschlagen. Erst das ausdrückliche Übernehmen speichert eine neue
Planvorlage und einen persönlichen Planeintrag. Wiederholtes Übernehmen derselben
Empfehlung erzeugt keinen zweiten Eintrag. Ein Vorschlag ist kein automatischer
Trainingsauftrag; Erholung und Tagesform sind vor dem Start zu prüfen.
Nach einem Verbindungsfehler oder Sicherheitsstopp wird aus der betreffenden
Einheit kein Folgetraining erzeugt.

Der persönliche Plan ergänzt die gemeinsame Bibliothek bestehender Radpläne.
Einträge können einem Datum zugeordnet und als geplant, abgeschlossen oder
übersprungen markiert werden. Ein Radplan ist nicht zwingend: Einträge können auch
nur ein optionales Kraftprogramm enthalten.

Kraftübungen werden ausschließlich vor oder nach dem Radtraining geplant. Name,
Variante, Reihenfolge, Sätze, Wiederholungen und Pausen sind konfigurierbar;
einzelne Übungen können als erledigt markiert werden. Das Modul ist vollständig
optional. Änderungen an Übungen, Reihenfolge, Zuordnung zum Radplan oder Position
setzen den bisherigen Abschlussstatus zurück. Reine Namens-/Datumsänderungen
erhalten den Fortschritt. Übungen werden nicht während des Tretens angeleitet.

## Laufband ohne Sensor erfassen

Ein manueller Laufbandeintrag speichert Trainingsdauer und optional Distanz,
Durchschnittspuls, Steigung sowie eine Startzeit mit Zeitzone. Alle Werte sind als
manuell gekennzeichnet. Ohne Angaben bleiben Distanz, Puls, Leistung, Arbeit und
Kalorien unbekannt. Es wird keine zeitliche Messspur erfunden und keine
Sensorabdeckung behauptet. Die Aktivität gehört zum aktiven Benutzer und erscheint
in derselben Historie wie Radfahrten. Das steuert kein Laufband und setzt keinen
bestimmten Taurus-Typ oder Bluetooth-Sensor voraus.

## API-Ergänzungen

Die laufende App liefert die vollständigen validierten Modelle unter `/docs`.
Schreibzugriffe können `expected_user_id` zur Erkennung eines zwischenzeitlichen
Benutzerwechsels mitsenden. Benutzerprofile sind weiterhin eine Auswahl innerhalb
einer vertrauenswürdigen lokalen Installation, keine Anmeldung.

| Schnittstelle | Verhalten |
| --- | --- |
| `GET /api/generator/preview` | Vorschau; Parameter `kind`, `minutes`, `watts`, `warmup_minutes`, `cooldown_minutes` |
| `POST /api/generator/preview` | Vorschau mit demselben Modell als JSON, ohne Speicherung |
| `POST /api/generator/save` | Neues Programm speichern; Antwort `plan_id`, `plan` |
| `GET /api/analysis?ride_id=…` | Reale Einheit auswerten; ohne ID letzte reale Radeinheit |
| `POST /api/recommendation/adopt` | Empfehlung ausdrücklich übernehmen; optionale `ride_id`, `scheduled_for` |
| `GET /api/planner` | Planeinträge des aktiven Benutzers |
| `POST /api/planner` | Eintrag mit optionalem Radplan, Datum und Kraftblöcken erstellen |
| `PUT /api/planner/{id}` | Konfiguration eines eigenen Eintrags ersetzen |
| `POST /api/planner/{id}/edit` | Gleichwertige Alternative zum PUT-Endpunkt |
| `POST /api/planner/{id}/status` | `status` und erledigte Übungsindizes `strength_completed` speichern |
| `POST /api/manual/treadmill` | Laufbandtraining manuell erfassen |

`kind` akzeptiert `endurance`, `interval`, `recovery`; Standard sind 30 Minuten,
100 W und je fünf Minuten Aufwärmen/Ausrollen. Ein Kraftblock hat die Felder
`name`, `variant`, `sets`, `repetitions`, `rest_seconds`. Die Position heißt
`strength_position` (`before` oder `after`). Statuswerte sind `planned`,
`completed`, `skipped`. Indizes in `strength_completed` beginnen bei null.

Die Tabelle `training_entries` wird additiv und idempotent angelegt. Bestehende
Pläne werden nicht überschrieben; die Eigentümerzuordnung des persönlichen Plans
ist unabhängig von der gemeinsamen Programmbibliothek. Ein neues Profilfeld kann
explizit mit `null` geleert werden. Vor einem Softwarewechsel ist weiterhin eine
konsistente Sicherung der Datenbank erforderlich.
