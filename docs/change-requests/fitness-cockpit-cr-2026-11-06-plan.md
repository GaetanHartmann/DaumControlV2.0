# Fitness-Cockpit: technische Umsetzungsplanung

Historische Planfassung vor der anschließenden Nutzerfreigabe »Alles umsetzen«. Der aktuelle Stand steht im [Umsetzungsbericht](implementation-status.md).

Bestandsprüfung: 2026-11-09. Anforderungsstand: 2026-11-06.
Basis: lokaler Commit `e7f2687` (Release v2.0.0), vor Beginn sauberer Arbeitsbaum.
Repository laut Git-Remote: https://github.com/GaetanHartmann/DaumControlV2.0.git

Dies ist eine Planung, keine Implementierungsfreigabe. Es wurden weder Produktcode noch Datenbank oder Pi-Konfiguration geändert. Die in der Übergabe genannte Datei `docs/change-requests/fitness-cockpit-cr-2026-11-06.md` fehlt im Checkout; Grundlage ist der vollständig gelesene Textanhang des Nutzers. Remote und lokaler Stand wurden nicht mit dem laufenden Pi abgeglichen.

## Bestand und Prüfgrenzen

- Vue 3, TypeScript und Vite; Oberfläche in `bike/frontend/src/main.ts`, Diagramme in `training-ui.ts`, responsive Regeln in `style.css`. Kein neues Webprojekt erforderlich.
- FastAPI mit WebSocket und genau einem zustandsführenden Prozess; `Engine` in `bike/backend/main.py` besitzt Training, Gerätezustand und eine gemeinsame asynchrone Sperre.
- `devices.py`: Daum Premium über TCP mit Framing, Prüfsummen und Zeitlimits; Pulsgurt über Bleak. `zwift.py`, `bluez.py`, `ftms.py`: experimenteller FTMS-Sender mit externer Steuerung. Zwift ist hier kein weiterer normaler Messwertsensor.
- SQLite: `users` mit JSON-Profil, `plans` mit JSON-Schritten und Metadaten, `rides` mit Benutzerzuordnung und JSON-Messspur, `settings`. Bestehende Migrationen in `init_db`, `seed_templates`, `migrate_exports` sind beizubehalten.
- Benutzerwerte und Fahrten sind benutzerbezogen. Die Pläne sind aktuell eine gemeinsame Bibliothek; das ist noch kein terminierter persönlicher Trainingskalender. Die Prüfung `expected_user_id` schützt vor veralteten Clients, ersetzt aber keine Authentifizierung.
- Vorhanden: FTP/Komfortleistung, individuelle Wattanpassung, Pulsgrenzen, pulsgeführte Regelung, Grundlagen-/Tempo-/Intervallvorlagen, sechs virtuelle Bergstrecken, Orientierungseinheit, Planvorschau und Bearbeitung als eigene Kopie, Aktivitäten und TCX/CSV/JSON-Export.
- `energy` bezeichnet mechanische Arbeit in kJ: Integration `power * dt / 1000`, keine gemessenen kcal. Messspur etwa alle zehn Trainingssekunden, bei mehr als 720 Punkten ausgedünnt; für exakte zeitgewichtete Mittelwerte und Datenabdeckung allein nicht ausreichend.
- Display: schwarzes Wayland-Overlay mit Touch-Aufwecken; separater LAN-Abschaltdienst. Der Abschaltdienst überwacht den physikalischen `eth0`-Link, nicht eine erfolgreiche Daum-Protokollverbindung.

Lokal ausgeführt: **62 Backend-Tests bestanden**, eine Deprecation-Warnung aus FastAPI/Starlette/httpx; **Frontend-Produktionsbuild erfolgreich**. Das Build-Skript führt Vite aus, keinen separaten TypeScript-Typcheck. Hardware-, Browser- und Kaltstarttests wurden nicht neu ausgeführt. Vorhandene Prüfskripte und frühere Release-Aussagen sind kein Nachweis für das gemeldete Verhalten auf dem aktuellen Pi. Die persönliche `bike.db` wurde nicht für Tests geöffnet oder migriert; Backend-Tests verwenden temporäre Datenbanken.

## CR-04: Geräte verbinden — zuerst, teilweise vorhanden

**Bestand:** `main.py:connect_all`, `ConnectionRequest`, `devices.py:HeartRate`, Frontend `connectAll` und Vorab-Dialog. Daum und Puls haben getrennte Fehlerbehandlung; der Pulsgurtversuch folgt auch nach Daum-Fehler. Automatische Auswahl nur bei genau einem Sensor, sonst manuelle Auswahl. Bereits verbundene Geräte bleiben erhalten. Tests in `test_app.py` decken diese Fälle bereits ab; `test_devices.py` prüft Abbruchbereinigung und verspätete Sensorcallbacks.

**Befund:** Kein belegter vollständiger Fehlerkurzschluss. Versuche laufen jedoch seriell unter der Engine-Sperre: bis zu 3 s Schließen + 12 s Daum + 10 s Scan + 20 s Pulsgurtverbindung als äußere nominelle Zeitlimits; Bereinigung kann zusätzlich dauern. Das Frontend wartet 55 s und zeigt Ergebnisse erst mit der Gesamtantwort. Der eigentliche Scan dauert sechs Sekunden und filtert auf angekündigten Heart-Rate-Service. Checkboxen, laufender Status und strukturierte Versuchshistorie fehlen. Ein kurzer Scan, verzögertes Advertising, mehrere Sensoren, BLE-Belegung oder abweichender Pi-Code sind Hypothesen, keine bestätigten Ursachen.

**Änderungen:** Zuerst Pi-Version und reproduzierbare Protokolle erfassen: Start/Ende, Dauer, Gerät, Scananzahl, Phase, Fehlerart und Zeitüberschreitung; keine unnötigen personenbezogenen Sensoradressen protokollieren. Anschließend optionale Geräteauswahl additiv im Request, bisherige Standardauswahl für alte Clients erhalten. Verbindung und frisches Pulssignal getrennt darstellen. Begrenzten Wiederholungsversuch bzw. gespeicherte Sensorauswahl erst nach Befund wählen. Daum und BLE können unabhängig angestoßen werden; BLE-Operationen auf demselben Adapter nicht blind parallelisieren. Zwift separat als Sender/Steuerungsoption behandeln.

**Abhängigkeiten/Risiken:** Nutzerwechsel, Trainingsstart und Zwift-Steuerung müssen während einer Verbindungsoperation weiter zuverlässig gesperrt bleiben. Eine Parallelisierung darf die bestehende Sperre nicht einfach entfernen. Abbruch, verspätete Antworten und Ressourcenbereinigung berücksichtigen; Frontend-Abbruch beendet Backend-Arbeit nicht automatisch.

**Tests:** vorhandene Tests erhalten; Auswahl nur Puls/nur Daum/keines, verzögertes Advertising, Scan-/Connect-Timeout und Wiederholung, Fehler beider Richtungen, fehlendes frisches Signal trotz BLE-Verbindung, mehrere Gurte, konkurrierende Clients, Nutzerwechsel und Abbruch. Auf Pi mit echtem Gurt bei ausgeschaltetem und eingeschaltetem Daum wiederholen, jeweils Logs und Zeit bis Signal festhalten.

## CR-05: Display nach Boot — Ursache unklar

**Bestand:** `deploy/install-display-idle.py`, `display-black-overlay.py`, `refresh-display.py`, `inspect-display.py`, `check-display-idle.py`; Backend-Servicevorlage und `install-daum-power-watch.sh`. Der Idle-Installer erzeugt User-Units und Desktop-Autostart. `wlopm --on HDMI-A-1` steht im Stop-Nachlauf des Idle-Dienstes, nicht als explizite Aktivierung beim Start. `refresh-display.py` startet einen dedizierten Chromium-Prozess, beschreibt aber keinen vollständigen dauerhaften Kiosk-Bootpfad.

**Änderungen:** Vor dem Fix auf dem Pi tatsächliche Units/Overrides, Desktop-Autostart, labwc/Wayland-/X11-Umgebung, Ausgabeanschlüsse, HDMI-/Backlight-Zustand, Overlay-Prozess und Journale aus aktuellem/vorherigem Boot lesen. Netzwerk-Erreichbarkeit beweist nur den Backend-Start. Erst danach gezielt Displayaktivierung nach verfügbarer grafischer Sitzung, Overlay-Bereinigung und gegebenenfalls Kiosk-Startreihenfolge reparieren; Anschluss nicht ungeprüft fest verdrahten. Kein pauschaler Austausch der Displaykonfiguration.

**Abhängigkeiten/Risiken:** `WAYLAND_DISPLAY=wayland-0` und HDMI-A-1 sind vorhandene Installationsannahmen. Unterscheiden: schwarzes Overlay, abgeschalteter Ausgang, Backlight und fehlender Browser. Physikalisches Wiederhochfahren nach vollständigem Poweroff hängt von Stromversorgung/Startmechanismus ab. Die bestehende Semantik »300 s ohne LAN-Träger« unverändert lassen; »ohne Daum-Verbindung« bedeutet derzeit nicht Protokollprüfung.

**Tests:** `test_power_watch.py` behalten; neue isolierte Tests für Starthelfer und fehlende grafische Sitzung. Vorhandener Display-Prüfer testet Overlay/HDMI/Touch, jedoch keinen Boot. Auf Hardware Kaltstart, Reboot, Start nach automatischem Shutdown, mit/ohne LAN, grafischer Dienstfehler und unbekannter Linkstatus prüfen. Timer je Dienststart neu, kein sofortiges Abschalten, Speichern vor Poweroff weiterhin erforderlich. Reales Poweroff erst im beaufsichtigten Testfenster ohne laufendes Training.

## CR-01: kompaktes Trainingscockpit — teilweise vorhanden

**Bestand:** Leistung, Puls, Kadenz, Zeit, verbleibende Zeit bei Plantraining sowie Geschwindigkeit und kJ sind vorhanden; Geschwindigkeit/Arbeit klein in der Distanzkachel. Responsive Regeln bis Smartphone und 800×480, Diagramm und alternative Ansichten vorhanden. kcal und ein kompaktes Gesamtinstrument fehlen.

**Änderungen:** Trainingsansicht mit Diagramm und gut lesbaren Metriken; Istleistung, Sollleistung und zeitliche Planphase unterscheiden. Keine erfundene Geräte-Leistungsstufe. Für freies Training ohne Endzeit Restzeit als nicht festgelegt. Fehlende/veraltete Messungen explizit kennzeichnen; aktuelle Nullinitialisierung ist kein generelles Verfügbarkeitsmodell. kcal zunächst nicht verfügbar oder später ausdrücklich als Schätzung mit Methode/Quelle; kJ nicht als Stoffwechselkalorien umetikettieren.

**Abhängigkeiten/Risiken:** Braucht ein additives Qualitäts-/Quellenmodell aus CR-09, aber keinen vollständigen Architekturumbau. Sichtbarkeit ohne Ansichtswechsel ist von Sichtbarkeit ohne Scrollen zu unterscheiden; Referenzgrößen vor Abnahme festlegen.

**Tests:** Browserprüfungen bei 800×480, Tablet Hoch-/Querformat und 390 px erweitern; Diagramm, Bedienelemente, alle verfügbaren Werte und fehlende/veraltete Daten prüfen. Demo deutlich gekennzeichnet. Touchziele, Textgröße und freie Restzeit kontrollieren.

## CR-02: Watt/Puls am Zeitmarker — teilweise vorhanden

**Bestand:** `training-ui.ts:WorkoutTimeline` mit mitlaufendem Zeitmarker und persistentem Zeit-/Wattraster. Marker zeigt bisher nur Zeit; Puls ist kein übergebenes Prop.

**Änderungen:** Zwei unabhängige Schalter, defensive lokale Speicherung, nullable Livewerte samt Frische übergeben. Label an Diagrammrändern begrenzen, ausblendbare Werte und fehlendes Signal klar darstellen.

**Abhängigkeiten/Risiken:** CR-01/Qualitätsmodell; keine Datenbankmigration nötig. Nach Trainingsende oder in Planvorschau keine alten Livewerte als aktuelle Messung anzeigen.

**Tests:** Vier Schalterkombinationen, Reload, gesperrter Storage, langer Text und Randpositionen, fehlender Puls sowie Smartphone ohne Überdeckung von Kurve/Zeit.

## CR-03: regulärer Abschluss und Auswertung — teilweise vorhanden

**Bestand:** `Engine.stop` speichert Fahrten und Messspur; derselbe Pfad wird für reguläres Ende, manuellen Stopp und Fehler verwendet. Ein expliziter Abschlussgrund fehlt. Animierter Radfahrer mit kadenzabhängig rotierenden Rädern und Reduced-Motion-Regeln ist vorhanden; keine Abschlussanimation oder Statistikzusammenfassung gefunden.

**Änderungen:** Additiver Abschlussgrund und stabile Fahrtkennung, danach kurze optionale Erfolgsanzeige nur bei regulärem Planende. Zeitgewichtete Leistungs-/Puls-/Kadenzstatistik mit jeweiliger gültiger Messdauer während der Erfassung sammeln; Pausen und Lücken ausweisen. kJ-Integration bei normalem Ende und Fehlern überprüfen: aktuell wird das Ende vor dem nächsten Mess-/Integrationsschritt erkannt. kcal nur mit nachvollziehbarer Quelle/Methode. Ergebnis dauerhaft mit der Fahrt speichern, Aktualisierung der Historie auch bei automatischem Ende sicherstellen.

**Abhängigkeiten/Risiken:** Datenqualität, additive Migration und Entscheidung über gültige aktive Zeit. Sparse/ausgedünnte Altmessspuren erlauben nur als solche markierte Näherungen; alte Fahrten erhalten keinen erfundenen Abschlussgrund. CR-07 liefert später Empfehlungen.

**Tests:** reguläres Ende genau einmal speichern/anzeigen; manueller Stopp, Puls-Sicherheitsstopp, Fehler, Shutdown und Zwift getrennt. Konstante und unregelmäßige Messintervalle, Pause, Teilabdeckung, fehlender Puls, Neustart/Reload und alte Datenbanken. Bestehende Exporte und unbekannte Zusatzfelder kompatibel halten.

## CR-07: Profil, Analyse und Folgetraining — teilweise vorhanden

**Bestand:** persönliche Leistungs-/Pulsparameter, Nutzerwechsel und Historie vorhanden. Alter/Geburtsjahr, Gewicht, Größe und Geschlecht fehlen in `TrainingProfile`; Zwift-Gewicht ist ein separater Engine-Parameter und kein persönliches Körperprofil. Keine Verlaufsauswertung oder terminierte persönliche Planung gefunden.

**Änderungen:** Optionale validierte Profilfelder nur mit benanntem Nutzen; Watt/kg benötigt Gewicht, Größe/Geschlecht sind dafür nicht nötig. Alte JSON-Profile mit fehlenden Feldern weiter lesen; bewusst behandeln, wie ältere Versionen unbekannte Felder beim Speichern erhalten. Historische Auswertung braucht Gewicht zum Trainingszeitpunkt oder sichtbare Kennzeichnung einer nachträglichen Neuberechnung. Vergleich nur passender realer Einheiten mit ausreichender Abdeckung; Regeln und Grenzen offenlegen, keine VO₂max ableiten. Konkreter konservativer Vorschlag mit Vorschau und ausdrücklichem Übernehmen.

**Abhängigkeiten/Risiken:** CR-03, Profilvalidierung und Entscheidung: »in Plan übernehmen« bedeutet zunächst eigene Planvorlage oder echter persönlicher Kalender. Kalender erfordert additive eigene Tabellen/API, keine Umdeutung bestehender globaler Pläne. Für späteren mobilen Zugriff fehlen Authentifizierung und Zugriffsschutz.

**Tests:** optionale/ungültige Werte, Nutzerisolation, alte Profile, Gewicht zum Messzeitpunkt, fehlende Datengrundlage, Demo ausgeschlossen, mehrfaches Übernehmen ohne Duplikate, keine automatische Änderung bestehender Pläne. Empfehlungsregeln fachlich separat prüfen.

## CR-09: neutrales Branding und Connectoren — teilweise vorhanden

**Bestand:** Geräteprotokolle bereits in `devices.py` gekapselt; Engine ist direkt an Daum, `mode='daum'`, Radmetriken und feste Grenzen 25–400 W gekoppelt. FTMS, Exporte und UI enthalten zusätzliche Annahmen. Kein allgemeines Connector-Interface. Allgemeines Branding lautet DAUM Studio.

**Änderungen:** Zuerst kleine Architekturentscheidung: Fähigkeiten (lesen/steuern separat), Verbindung, standardisierte nullable Messwerte mit Einheit/Quelle/Frische, Befehlsfehler und Aktivitätsart. Daum über dünne Hülle anbinden, TCP-Protokoll erhalten; Pulsgurt als unabhängige Messquelle, Zwift als gesonderten Ausgabepfad/Steuerungseigentümer behandeln. Engine schrittweise auf Fähigkeiten umstellen, ohne Laufband in Wattsteuerung zu zwingen. Produktname zentral konfigurierbar, vorläufig Fitness-Cockpit.

**Abhängigkeiten/Risiken:** Design früh vor neuen Adaptern; Implementierung nach den ersten Fehlerfixes in kleinen Schritten. Persistierte Modi, Datenbankpfade, Dienstnamen, LocalStorage-Schlüssel und Exportversionen nicht als Branding-Massenersetzung ändern. Langfristige Aktivitätsart additiv ergänzen, alte Fahrten bleiben Radfahrten.

**Tests:** Connector-Vertrag mit Fakes für fehlende Metriken, reine Lesegeräte, Abbruch und Reconnect; bestehende Daum-Roundtrips, Pulsregelung, Lastgrenzen, Zwift-Steuerung, Nutzerwechsel und Exporte unverändert weiter prüfen. Branding inklusive Dokumentation/Downloadnamen kontrollieren.

## CR-06: Trainingsgenerator — teilweise vorhanden

**Bestand:** `training.py:templates`, `terrain_templates`, `resolve_plan`; feste Vorlagen, persönliche Skalierung, Warm-up/Cooldown sowie speicherbare eigene Pläne. Freie parametrisierte Erzeugung fehlt; Editor erstellt auch beim Bearbeiten einer Vorlage eine Kopie.

**Änderungen:** Deterministischer Generator für gewünschte Dauer, Typ und Belastungsparameter; exakte Phasenlängen, explizite Grenzen, Vorschau vor Speichern. Bestehende Plan-API und Editor wiederverwenden; Originalvorlagen unverändert. Regeneration als klarer eigener Typ.

**Abhängigkeiten/Risiken:** CR-09-Fähigkeiten und CR-07 nur falls persönliche Vorschläge genutzt werden. Kein automatisches Hochsetzen aus einer einzelnen Einheit; bestehende Beispielbasis 150 W weiterhin eindeutig kennzeichnen.

**Tests:** kürzeste/längste Dauer, exakte Gesamtdauer, Mindestschrittdauer 10 s, maximal 100 Schritte und 25–400 W für Daum, Warm-up/Cooldown, fehlende FTP, Speichern/Ändern/Reload ohne Vorlagenverlust.

## CR-08: optionales Kraftmodul — fehlt

**Bestand:** heutige `Step`-Validierung verlangt Watt und Dauer; kein Kraft-/Satzmodell und kein persönlicher Kalender.

**Änderungen:** Eigene optionale Übungsblöcke mit Reihenfolge, Variante, Sätzen, Wiederholungen, Pausen und Abschlussstatus; vor/nach Cardio wählbar. Bestehende Radschritte unverändert lassen. Plan-/Einheitenzuordnung aus CR-07 wiederverwenden, keine Übungen während des Tretens.

**Abhängigkeiten/Risiken:** Kalenderentscheidung CR-07 und hardwareunabhängiges Aktivitätsmodell. Kein Aufweichen der Radvalidierung für scheinbare Kraftschritte.

**Tests:** vollständige Optionalität, Reihenfolge, Konfiguration, Nutzerisolation, Fortschritt über Reload und unveränderte Durchführung vorhandener Radpläne.

## CR-10: Taurus und mobiler Connector — unklar / fehlt

**Bestand:** zentraler Browserzugriff vorhanden; kein Taurus-/Runn-Adapter, manueller Laufdatensatz oder mobiler Sensor-Uplink gefunden. Modell unbekannt.

**Spike:** Typenschild/Konsole und tatsächliche Schnittstellen ermitteln. Danach aktuelle Herstellerunterlagen, mechanische Sensor-Kompatibilität, Kalibrierung und Preise prüfen; heute keine Kaufempfehlung. Browserfähigkeiten je realem Zielgerät verifizieren. Manuelle Lauftraining-Erfassung als eigener kleiner, sensorunabhängiger Schritt mit Nutzer, Dauer, optionalen Werten und Quelle »manuell« planen. Mobiler Uplink benötigt Identität, Authentifizierung, geordnete Zeitstempel, Offline-/Duplikatbehandlung und sicheren Netzwerkzugriff.

**Abhängigkeiten/Risiken:** CR-09/07; kein Rückschluss vom Alter/Preis auf Modell oder FTMS. Keine automatische Tempo-/Steigungssteuerung im Scope.

**Tests/Ergebnis:** Modell-/Schnittstellenbericht und Go/No-Go; später manuelle Erfassung ohne Sensor, korrektes Profil, Liveübertragung/Latenz und Verbindungsverlust. Ohne Hardwareangaben keine belastbare Integrationsschätzung.

## CR-11: Watch-Livepuls und HealthKit — fehlt

**Bestand:** BLE-Pulsgurt und Export vorhanden, außerdem ungetesteter HeartCast-Hinweis in der UI. Kein eigener Watch-/HealthKit-Code; Export ist keine native Apple-Health-Integration.

**Spike:** Aktuelle Apple-Primärdokumentation erst bei Durchführung prüfen; aktives Workout, Live-Herzfrequenz und Übertragung Watch/iPhone/Backend mit realen Geräten prototypisch messen. Pulsgurt unabhängig erhalten, eindeutige Auswahl/Qualität der Pulsquelle. Health-Datenaustausch getrennt und nur nach expliziter Berechtigung.

**Abhängigkeiten/Risiken:** Apple-Geräte, native Entwicklungsumgebung, CR-09 und abgesicherter Backend-Zugriff. Hintergrundverhalten und Latenz sind bis zum Test offen; kein Browser-only-Livepuls voraussetzen.

**Tests/Ergebnis:** Messprotokoll mit Latenz, Ausfällen, gesperrtem iPhone, Unterbrechung, Widerruf und Reconnect; Berechtigungs-/Datenschutzkonzept. Kein Versprechen zur Stabilität ohne Praxistest.

## CR-12: native Erweiterung — fehlt

**Bestand:** Web-App/API unter Windows entwickelbar; keine iOS-/watchOS-Projekte, Signierung oder native Buildpipeline gefunden.

**Spike:** Kleine Architekturentscheidung zwischen nativer Sensorbrücke, eingebetteter Weboberfläche und nativer Oberfläche. Gemeinsame Trainingslogik/API behalten. BLE und API-Authentifizierung prototypisieren; macOS/Xcode-Build und Gerätebereitstellung separat planen. Apple-Vorgaben, Runner-Verfügbarkeit/Kosten und Signierungsanforderungen bei Spike-Beginn anhand aktueller offizieller Quellen prüfen.

**Abhängigkeiten/Risiken:** CR-10/11-Ergebnisse, Entwicklerkonto/macOS und reale Geräte unbekannt. Lokaler HTTP-Heimnetzbetrieb ist noch keine abgesicherte mobile API. Keine Veröffentlichung oder Hardwarebeschaffung beauftragt.

**Tests/Ergebnis:** dokumentierter Build von sauberem Checkout, reale BLE-/Watch-Tests, Hintergrund/Offline/Widerruf, Berechtigungen, Datenschutz und Architekturentscheidung mit Aufwandsspanne. Grobe Größenordnung bei vorhandenen Konten/Geräten: mehrere getrennte Spikes von jeweils mehreren Arbeitstagen; Produktreife erst nach deren Ergebnissen schätzen.

## Kleine Branches und PRs

Jeder Branch startet vom jeweils freigegebenen Basisstand; keine Branches oder Remote-PRs wurden angelegt.

| Reihenfolge | Branchvorschlag | Abgegrenzter Umfang | Abhängigkeit |
| --- | --- | --- | --- |
| 1 | `fix/cr04-connection-diagnostics` | Reproduktion, Phasenlogs, Timeout-/Scan-Regressionen | Pi-Stand lesen |
| 2 | `fix/cr05-display-boot` | belegte Bootursache gezielt beheben, Display-/Timer-Nachweis | Pi-Diagnose/Testfenster; unabhängig von 1 |
| 3 | `feat/cr04-device-selection` | Checkboxen, Status, begrenzte unabhängige Versuche | 1 |
| 4 | `docs/cr09-connector-design` | Interface-/Qualitäts-/Kompatibilitätsentscheidung | Fehlerbefunde |
| 5 | `refactor/cr09-daum-connector` | dünne Daum-Hülle, Qualitätsmodell, Vertragsprüfungen | 4 |
| 6 | `feat/cr01-compact-cockpit` | kompakte Werteansicht, fehlende Werte/Quellen | 5 oder dessen minimaler Qualitätsvertrag |
| 7 | `feat/cr02-marker-values` | zwei persistente Markerschalter | 6 |
| 8 | `feat/cr03-session-summary` | Abschlussgrund, Aggregation, Migration, Historie | 5 |
| 9 | `feat/cr03-completion-feedback` | reduzierte Animation und Zusammenfassung | 8 |
| 10 | `feat/cr07-profile-analysis` | optionale Felder, transparente Auswertung | 8 |
| 11 | `feat/cr07-next-session` | Vorschlag mit ausdrücklicher Übernahme | 10; Kalenderentscheidung |
| 12 | `refactor/cr09-product-branding` | zentraler vorläufiger Produktname | unabhängig nach 4 |
| 13 | `feat/cr06-profile-generator` | parametrisierte Profile mit Vorschau | 5, vorhandener Editor |
| 14 | `feat/cr08-strength-module` | optionale Kraftblöcke | 11 |
| später | `spike/cr10-treadmill`, `spike/cr11-watch`, `spike/cr12-native` | getrennte Machbarkeitsberichte/Prototypen | jeweilige Hardware-/Kontovoraussetzungen |

Die Diagnose-PRs dürfen mit offenem Hardwarebefund keine angebliche Behebung behaupten. Falls ein Fix ohne Pi-Nachweis vorbereitet wird, bleibt die Hardwareabnahme ausdrücklich ausstehend.

## Kompatibilität und Abnahme

Bestehende Daum-Befehle, Sicherheitsreduktion, Zwift-Steuerung, Profile, Vorlagen und Exporte als Regression erhalten. Schema nur additiv erweitern; idempotente Migrationen gegen Kopien alter Datenbanken sowie alte Profile/Messspuren prüfen. Nullable neue Felder und unbekannter Abschlussgrund statt erfundener Bestandsdaten. Rückwärtslesbarkeit und Downgrade unterscheiden: additive Spalten garantieren nicht, dass ältere Programme neue Profilfelder beim erneuten Speichern erhalten. Vor Migration konsistente Datenbanksicherung und Restore-Pfad testen; bei Bedarf Downgrade nur mit Backup unterstützen.

Je Code-PR passende Backend-Tests und Produktionsbuild; UI-PRs zusätzlich isolierte Browserprüfungen. Deployment, reale Trainingssteuerung und Shutdown gehören nicht zur heutigen Bestandsaufnahme. Bei neuem Connector Daum-Regression am Gerät vor Freigabe.

## Offene Entscheidungen

1. Installierter Pi-Commit, aktive Services/Overrides, Boot-Journale und genaues Displayverhalten nach Einschalten; Ursache CR-04/05 erst damit bestätigbar.
2. Ziel-Tablet/Browsersysteme und verbindliche Abnahmeauflösungen; Bedeutung »alle Werte sichtbar« hinsichtlich Scrollen.
3. kcal-Methode oder zunächst »nicht verfügbar«; Definition gültiger Messdauer und erlaubter Datenlücken.
4. Persönlicher terminierter Kalender oder Übernahme als wiederverwendbare Planvorlage; heutige Bibliothek bleibt erhalten.
5. Endgültiger Name; Fitness-Cockpit bleibt Arbeitsname. SQLite zunächst beibehalten, kein unbegründeter Datenbankwechsel.
6. Taurus-Modell/Fotos, Sensorhardware, Apple-Geräte, Entwicklerkonto und macOS-Buildmöglichkeit.

Nächster freizugebender Schritt: CR-04-Diagnose und CR-05-Bootdiagnose mit getrennten kleinen Fixes auf Basis belegter Ursachen. Bis zur Freigabe bleibt es bei dieser Planung.
