# Fitness-Cockpit – Codex-Implementierungsauftrag

**Stand:** 09.11.2026\
**Projekt:** Fitness-Cockpit / Daum Ergometer / Raspberry Pi / Browser-Frontend\
**Priorität:** P0 = Trainingskatalog, Trainings-Cockpit, sichere Laufzeit-Leistungsanpassung; P1 = KI-Trainingscoach; P2 = 3D-Rundstrecken-Simulation

> **An Codex:** Bitte dieses Dokument als Entwicklungsauftrag für das **bestehende Repository** verwenden. Zuerst die vorhandene Architektur, Geräteschnittstelle, Trainingsprofile, Datenhaltung, UI und Tests untersuchen. Bereits funktionierende Bestandteile wiederverwenden; keine parallele zweite Anwendung aufbauen. Die beschriebenen URLs, Komponenten und Datentypen sind *Vorschläge*, keine Behauptungen über den Ist-Stand. Fehlende Hardware-Fähigkeiten ausdrücklich feststellen und einen sicheren Simulationsmodus anbieten. Anschließend die Anforderungen schrittweise implementieren, testen und Änderungen dokumentieren.

## 1. Zielbild

Ein webbasiertes Fitness-Cockpit, bedienbar auf Smartphone, Tablet, PC und Raspberry-Pi-Touchscreen. Die Anwendung verbindet das bestehende Daum-Ergometer und optional einen BLE-Pulsgurt. Trainings können aus einem **eigenständigen Trainingskatalog** gestartet, live gefahren, manuell in der Leistung angepasst, gespeichert und analysiert werden. Ein optionaler **KI-Trainingscoach** schlägt auf Basis absolvierter Einheiten die nächste Einheit vor. Später gibt es reale virtuelle Rundstrecken mit OpenStreetMap-Daten.

**Wichtigste neue Anforderung:** Die **Soll-Leistung (Watt) muss während eines laufenden Trainings über einen Schieberegler und große ±-Tasten geändert werden können**, ohne die Trainingseinheit zu beenden oder zurückzusetzen.

## 2. Navigationsstruktur / Seiten

1. **Cockpit / Training** (`/training` oder bestehende Route): Live-Werte, Leistungskurve, Wattregler, Start/Pause/Stopp.
2. **Trainingskatalog** (`/trainings`): Profilkarten mit Mini-Vorschau der Leistungskurve, Kategorien, Filter, Details, Erstellen/Bearbeiten/Kopieren/Löschen, Favoriten.
3. **KI-Coach** (`/coach`): Trainingsvorschlag mit Begründung, Vorschau, Anpassen, Übernehmen, Prüfen, Start vorbereiten.
4. **Trainingshistorie / Analyse** (`/history`): Abgeschlossene Einheiten und tatsächlich gefahrene Leistung.
5. **Virtuelle Strecken** (`/routes`, P2): Übersicht realer Rundstrecken, Höhendiagramm und optional 3D-Fahrt.

Routen und Dateinamen an das Projekt anpassen.

## 3. Trainingskatalog (P0)

- Trainingsprofile als anklickbare Karten mit **kleinem Vorschaudiagramm der Soll-Leistung über die Zeit** anzeigen.
- Metadaten: Name, Kategorie, Gesamtdauer, min./max. Watt, Intensität, Beschreibung, Quelle (`manual`, `preset`, `ai`), optional Favorit.
- Anfangsprofile: „Lockere Runde“, „Intervalle“, „Bergfahrt“, „Ausdauerfahrt“.
- Profile müssen als **Zeit-/Leistungssegmente** gespeichert werden; Profile ohne valide Segmente dürfen nicht gestartet werden.
- Katalog: suchen/filtern, Profil anzeigen, bearbeiten, duplizieren, löschen (mit Bestätigung), speichern.
- Ein Vorschaubild ist eine **generierte Kurve (SVG/Canvas)** aus echten Profildaten, nicht ein statisches Deko-Bild.
- Beim Klick auf „Training vorbereiten“ das Profil in die Trainingsseite übernehmen; **nicht automatisch starten**.
- Live-Diagramm zeigt geplante Wattkurve, tatsächliche Wattwerte und aktuelle Zeitposition als getrennte, klar unterscheidbare Ebenen.

## 4. Trainings-Cockpit und Touch-Bedienung (P0)

### 4.1 Live-Anzeigen

Mindestens:
- aktuelle **Ist-Leistung** (gemessen), **Soll-Leistung** (an Gerät angefordert), Puls, Trittfrequenz, Geschwindigkeit;
- vergangene Zeit, Restzeit, Distanz, ggf. Kalorien;
- Verbindungsstatus **Ergometer** und **Pulsgurt** getrennt;
- aktive Profilphase und nächste geplante Wattstufe;
- geplanter vs. tatsächlicher Leistungsverlauf (nicht verwechseln).

Nicht verfügbare Werte als `—` bzw. „nicht verbunden“ anzeigen; keine erfundenen Messwerte. Tacho-/Cockpit-Kacheln später konfigurierbar.

### 4.2 Start/Pause/Stopp als große Hotspots

- **Start**: Training nach erfolgreicher Prüfung und bewusster Benutzeraktion starten.
- **Pause/Fortsetzen**: Trainingszeit-/Profilfortschritt pausieren und nach Fortsetzung an derselben Stelle weitermachen. Die konkrete Widerstandsreaktion bei Pause muss die Gerätefähigkeit berücksichtigen (sichere Minimalleistung / Pause-Befehl, soweit unterstützt).
- **Stopp**: Training kontrolliert beenden, ggf. Geräte-Sollwert sicher zurücknehmen, Ergebnis sichern und Analyse anzeigen. Optional Bestätigung gegen versehentliches Stoppen; Stopp muss dennoch jederzeit schnell erreichbar sein.
- Touch-Ziele ausreichend groß und weit genug voneinander entfernt; Rückmeldung bei jedem Klick, sichtbarer Statuswechsel.
- Keine versteckte automatische Wiederaufnahme nach Browser-Reload, Reconnect oder Geräteabbruch.

## 5. Live-Leistungsanpassung während des Trainings – KERNANFORDERUNG (P0)

### 5.1 Bedienelemente

Auf der **laufenden** Trainingsseite dauerhaft sichtbar:
- Watt-Slider mit gut sichtbarem aktuellen **Sollwert in W**;
- große Schaltflächen **−10 W** und **+10 W** (optionale feinere Schritte, z. B. ±5 W);
- Aktion **„Zurück zum Trainingsplan“**;
- Kennzeichnung `Trainingsplan` versus `Manuell angepasst`;
- optional numerische Eingabe für Desktop, aber nie als einzige Möglichkeit.

Slider-Minimum, Maximum und Schrittweite aus **Gerätefähigkeit und Nutzerkonfiguration** bestimmen, nicht blind 30–350 W hart codieren. Unmögliche Werte verhindern und verständlich erklären.

### 5.2 Exakte Semantik

- Normalbetrieb: Sollwatt folgt dem aktiven Segment des gewählten Profils.
- **Manuell eingreifen:** Slider- oder ±-Eingabe setzt sofort einen **temporären absoluten Sollwert** (z. B. Plan = 140 W → Benutzer wählt 155 W). Die Trainingsuhr und die Segmentposition laufen weiter.
- Der manuelle Wert bleibt **auch beim nächsten Segmentwechsel bestehen**, bis der Benutzer „Zurück zum Trainingsplan“ auswählt, das Training endet oder eine Sicherheitsregel greift. Dieser Modus muss im UI klar sichtbar sein.
- „Zurück zum Trainingsplan“ übernimmt ab sofort den **für die aktuelle Trainingsposition** vorgesehenen Wert – nicht den Startwert eines alten Segments.
- Die ursprüngliche Sollkurve bleibt unverändert und sichtbar; die manuelle Änderung wird als eigener Sollwert-/Steuerverlauf geloggt.
- Während Pause: Eingabe kann vorbereitet werden, aber Gerät nur entsprechend sicherer Pausenlogik ansteuern; beim Fortsetzen klar anzeigen, welcher Sollwert gilt.
- Leistungsänderungen dürfen **nicht** den Timer, die Distanz, die aufgezeichneten Werte oder den aktuellen Trainingsabschnitt zurücksetzen.
- Eingaben schnell visualisieren, aber Gerätebefehle bei schnellem Slidern **drosseln/entprellen** (z. B. kurzer Debounce/Rate-Limit; finalen Sollwert zuverlässig senden). Nur letzte gewünschte Änderung zählt; keine veralteten Befehle nach neuer Eingabe.

### 5.3 Soll-/Ist-Unterscheidung und Befehlsbestätigung

Drei getrennte Zustände führen:
1. `requested_target_watts`: vom Nutzer bzw. Trainingsplan gewünschter Wert;
2. `applied_target_watts`: letzter **vom Gerät bestätigter** Wert, sofern Rückmeldung möglich;
3. `measured_watts`: vom Gerät **gemessene** Leistung.

Bei fehlender Gerätebestätigung nicht „angewendet“ als Tatsache anzeigen. UI zeigt z. B. „150 W angefordert“, „Geräterückmeldung ausstehend“ oder „Steuerung nicht unterstützt“. Keine fiktive Kopplung von Soll- und Ist-Leistung.

### 5.4 Technische Anforderungen

- Geräteschnittstelle kapseln, z. B. `ErgometerAdapter` mit `connect`, `getCapabilities`, `setTargetWatts`, `readTelemetry`, `pauseOrSafeState`, `stopOrSafeState`, `disconnect`; konkrete Methodennamen an vorhandenen Code anpassen.
- Prüfen, **ob das vorhandene Daum-Protokoll das Schreiben eines Watt-Sollwertes tatsächlich unterstützt**. Bis dahin nur Simulations-/Vorschaumodus, nicht vermeintlich reale Widerstandssteuerung.
- Sollte das Daum-Gerät eine andere Steuergröße statt Watt nutzen, Konvertierung dokumentieren und Anzeige korrekt beschriften.
- Befehlsergebnis, Timeout, Ablehnung und Verbindungsabbrüche behandeln; nach Reconnect kein unbestätigtes automatisches Wiedersenden eines möglicherweise gefährlichen alten Wertes.
- Sicherheitsgrenzen sowohl im Frontend als auch an der Backend-/Adapter-Grenze validieren; KI darf nie direkt Gerätebefehle versenden.
- Bei Stop, Verbindungsfehler oder Fehlerzustand die **vom Gerät unterstützte sichere Reaktion** auslösen; niemals einen nicht unterstützten „Notstopp“ behaupten. Physische Sicherheit/Herstellerbedienung bleibt maßgeblich.

### 5.5 Ereignisprotokoll

Jede Änderung mit Zeitstempel und Quelle protokollieren: `plan`, `manual_slider`, `manual_button`, `return_to_plan`, `safety`, `pause/resume`. Auch Wunschwert, bestätigter Wert (falls vorhanden) und Fehlermeldungen erfassen. Im Trainingsergebnis markieren, wo manuell angepasst wurde.

## 6. KI-Coach: Vorschlag → Übernahme → Prüfung → Start (P1)

1. **Analyse** abgeschlossener Trainingseinheiten: Dauer, Soll-/Ist-Watt, Puls (sofern vorhanden), Trittfrequenz, Pausen, manuelle Eingriffe, Trainingshäufigkeit und gewünschtes Ziel.
2. **Vorschlag erzeugen:** Profil mit Abschnitten (Dauer + Sollwatt), Titel, Ziel und verständlicher Begründung. Fehlende Daten offenlegen. Kein medizinisches Urteil, keine automatische Belastungssteigerung ohne Benutzerkontrolle.
3. **Vorschau:** Gleiche Leistungskurvenkomponente wie im Katalog; Dauer und Intensität anzeigen.
4. **Anpassen:** Dauer, Watt, Segmente und ggf. Intensität bearbeiten. Änderungen setzen vorhandene Validierung zurück.
5. **Übernehmen:** Als bearbeitbares Profil mit `source: ai` im Katalog speichern; **nicht** sofort an das Gerät senden.
6. **Prüfen:** Schema und Zeitsegmente; individuell konfigurierte Belastungsgrenzen; Geräte-Maximum/-Minimum; Verbindungs- und Steuerungsfähigkeit; für den Start erforderliche Sensorik nach Konfiguration.
7. **Start vorbereiten:** In das Cockpit wechseln, Endkontrolle durchführen; erst nach aktivem **Start-Klick** das Profil fahren.
8. **Nach dem Training:** Ergebnisse persistieren und für einen **neuen** Vorschlag verwenden. Trainingsdaten an externen KI-Dienst nur nach bewusst aktivierter Anbindung und mit transparenter Datennutzung übertragen.

KI-Ausgaben sind **untrusted input**: robustes Schema-Parsing, numerische Grenzen, Zeitvalidierung, keine direkten Gerätebefehle. Ohne KI-Schlüssel funktioniert die komplette Trainingsfunktion mit lokalen Profilen.

## 7. Vorschlag Datenmodell / Zustandsmodell

*Bestehendes Schema nach Inspektion bevorzugen; andernfalls dieses Modell sinngemäß verwenden.*

```json
{
  "id": "workout-001",
  "name": "Moderate Ausdauerfahrt",
  "source": "ai",
  "duration_seconds": 1800,
  "segments": [
    { "duration_seconds": 300, "target_watts": 80 },
    { "duration_seconds": 600, "target_watts": 120 },
    { "duration_seconds": 600, "target_watts": 140 },
    { "duration_seconds": 300, "target_watts": 75 }
  ],
  "status": "draft"
}
```

**Validierung:** Summe der Segmente = `duration_seconds`; alle Dauern positiv, Wattwerte endlich und innerhalb zulässiger Grenzen; leere/ungültige Profile ablehnen.

**Profilstatus:** `draft → accepted → validated → ready`.\
**Sitzungsstatus:** `idle → ready → running ↔ paused → completed` sowie `stopped` und `error` als explizite End-/Fehlerzustände.\
Profil und tatsächliche Trainingseinheit **getrennt** speichern; eine absolvierte Einheit verändert nicht das Originalprofil.

Beispiel Laufzeitstatus:

```json
{
  "session_id": "session-123",
  "workout_id": "workout-001",
  "state": "running",
  "elapsed_seconds": 754,
  "control_mode": "manual_override",
  "planned_target_watts": 140,
  "requested_target_watts": 155,
  "applied_target_watts": null,
  "measured_watts": 148,
  "device_connected": true,
  "target_command_status": "pending"
}
```

Bei `applied_target_watts: null` darf kein bestätigter Sollwert behauptet werden.

## 8. Virtuelle Rundstrecke / Simulation (P2, anschlussfähig vorbereiten)

- Auswahl echter Rundstrecken aus OpenStreetMap, z. B. rund um Grafrath/Ammersee; Anzeige von Route, Distanz, Höhenprofil.
- Perspektivisch 3D-Fahrt im Browser; Raspberry Pi bleibt Geräte-Connector, komplexes Rendering kann auf Tablet/PC erfolgen.
- Virtuelle Geschwindigkeit aus realen Messwerten und geeignetem Fahrmodell ableiten, nicht aus frei erfundenen Werten.
- Streckenneigung kann später in einen Leistungsvorschlag übersetzt werden; darf die manuelle Laufzeit-Leistungssteuerung **nicht überschreiben**.
- Vorrang der Sollwertquellen: **Sicherheitsbegrenzung > bewusste manuelle Eingabe > aktives Trainingsprofil oder Routensteuerung**.
- Die 3D-Simulation ist nicht Voraussetzung für die P0-Freigabe.

## 9. Umsetzungsschritte für Codex

### Phase A: Bestand prüfen
- Repo-Struktur, UI-Framework, Backend, Datenbank, vorhandene Profiles/Diagramme, Geräteschnittstelle, Daum-Protokoll und Teststrategie dokumentieren.
- Ermitteln, ob Watt-Sollwerte bereits geschrieben werden können; falls ja die vorhandene Funktion nutzen. Falls nein die benötigte Adapter-Schnittstelle ohne erfundene Hardware-Unterstützung vorsehen.

### Phase B: Kernfunktion P0 implementieren
- Trainingskatalog mit Kurven-Vorschaubildern und Profildetails.
- Eigenständige Trainingsseite mit Cockpit-Kacheln und Touch-Start/Pause/Stopp.
- Verlässliche Trainings-Zustandsmaschine und persistierbare Trainingseinheiten.
- **Wattänderung im laufenden Training (Slider, ±10 W, Rückkehr zum Plan)** einschließlich Vorrang, Rate-Limit und Rückmeldung.
- Zeit-/Leistungsdiagramm mit geplanter, angeforderter und gemessener Kurve.
- Simulationsmodus für UI-/Logiktests ohne Ergometer.

### Phase C: KI P1
- Profile über strukturierten KI-Adapter vorschlagen lassen; JSON validieren.
- Vorschlag ansehen, ändern, übernehmen, prüfen, starten und auswerten.
- Funktionierender Offline-/KI-loser Fallback.

### Phase D: Strecken P2
- Architektur für Routen und Gelände vorsehen; OSM-Routing/-Höhendaten und 3D-Darstellung separat implementieren.

## 10. Akzeptanzkriterien / Tests

- [ ] Trainingskatalog hat eine eigene Seite mit **echten Vorschau-Leistungskurven** aus den Profilsegmenten.
- [ ] Auswahl eines Profils öffnet die Trainingsvorbereitung; kein automatischer Start.
- [ ] Start/Pause/Fortsetzen/Stopp sind große, gut bedienbare Touch-Hotspots.
- [ ] Während `running` lässt sich der Sollwert per Slider sowie ±10 W ändern **ohne Neustart** der Einheit.
- [ ] Mehrfaches schnelles Ziehen des Sliders führt nicht zu einer unkontrollierten Befehlsflut; letzter gültiger Zielwert wird zuverlässig übernommen/angefordert.
- [ ] Manuelle Wattänderung bleibt über Segmentwechsel hinweg aktiv, bis „Zurück zum Trainingsplan“ gedrückt wird.
- [ ] „Zurück zum Trainingsplan“ übernimmt den **aktuellen** planmäßigen Zielwert.
- [ ] Geplante, angeforderte und gemessene Wattwerte sind klar getrennt; fehlende Gerätebestätigung wird transparent angezeigt.
- [ ] Slider und ±-Tasten respektieren konfigurierbare Geräte-/Benutzergrenzen, auch serverseitig.
- [ ] Pause stoppt die Trainingszeit; Fortsetzen springt nicht an den Anfang.
- [ ] Stop speichert den bisherigen Verlauf und beendet die Gerätesteuerung im Rahmen der tatsächlichen Adapterfähigkeit.
- [ ] Verbindungsverlust/Timeout zeigt einen Fehler, statt eine erfolgreiche Gerätesteuerung vorzutäuschen.
- [ ] KI-Profile können vor dem Start bearbeitet werden; jede Änderung erzwingt eine erneute Validierung.
- [ ] KI-Vorschläge führen **nie** ohne explizite Benutzeraktion zu einem realen Gerätebefehl.
- [ ] Mindestens Unit-Tests für Statuswechsel, Watt-Override, Segmentwechsel, Validierung und Grenzwerte; Integrationstest mit Mock-Gerät.
- [ ] App und Kernsteuerung bleiben ohne KI und ohne 3D-Simulation nutzbar.
- [ ] Bestehende Tests werden ausgeführt; relevante neue Tests dokumentieren.

## 11. Ergebnis / Übergabe von Codex

Bitte am Ende liefern:
1. Übersicht der geänderten Dateien und wichtigsten Architekturentscheidungen.
2. Kurze Anleitung zum Starten von Backend/Frontend und zum Aktivieren des Simulationsmodus.
3. Beschreibung, wie die Watt-Anpassung live funktioniert und welcher Daum-Steuerbefehl verwendet wird (falls nachgewiesen).
4. Testresultate mit gekennzeichneten offenen Punkten.
5. Screenshot(s) oder nachvollziehbare UI-Beschreibung für Trainingskatalog, Trainingsseite und KI-Vorschau (wenn im Arbeitsumfeld möglich).

**Keine Hardware-Funktion als erledigt markieren, solange sie nicht gegen die echte Daum-Schnittstelle verifiziert ist.**
