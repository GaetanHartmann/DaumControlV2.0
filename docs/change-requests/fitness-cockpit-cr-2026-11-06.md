Fitness-Cockpit – Change Requests aus dem ersten Training
Stand: 2026-11-06
Status: Anforderungssammlung / noch nicht gegen den aktuellen Repository-Code geprüft
Bisheriger Projektname: Daum-dev (Arbeitsbezeichnung)
Zielbild: Herstellerunabhängiges Fitness-Cockpit als Webanwendung, mit modularen Geräte-Connectors und optionaler nativer iPhone-/Apple-Watch-Erweiterung.

Diese Anforderungen wurden aus mündlichem Feedback abgeleitet. Sie dokumentieren Wünsche, beobachtete Probleme und mögliche Lösungswege. Bestehende Implementierungen zunächst prüfen; nichts ohne Prüfung ersetzen. Keine Annahmen über vorhandene Codebasis, Datenbankstruktur oder konkrete Geräte-APIs treffen.

Leitlinien für die Umsetzung
Bestehende Funktionen, Trainingsprofile, Ansichten, Datenbank und die Daum-Anbindung erhalten und inkrementell erweitern.

Produkt-Branding neutral gestalten (z. B. „Fitness-Cockpit“ als vorläufiger Name); „Daum“ nur dort nennen, wo konkret der Daum-Adapter oder ein kompatibles Gerät gemeint ist. Markenname wird noch final entschieden.

Browser/Tablet/Smartphone bleiben der primäre Bedienweg. Keine zusätzliche iPhone-App als Voraussetzung für die Grundfunktionen.

Herstellerunabhängige Connector-Schnittstelle: Messwerte, Gerätefähigkeiten, Verbindung und Fehlerzustände klar trennen; gerätespezifische Protokolle in Adaptern kapseln.

Benutzerprofile und Trainingseinheiten einheitlich verwalten; alle Geräte verwenden dieselbe Trainingshistorie und Auswertung.

Keine erfundenen Messwerte: nicht verfügbare Werte als „nicht verfügbar“ anzeigen und Sensor-/Berechnungsquelle kennzeichnen.

Fitnesskennzahlen sind orientierend, keine medizinische Diagnose oder verlässliche Messung der allgemeinen Fitness aus einer einzelnen Einheit.

Bestehendes Layout und Verbindungsprotokolle zuerst im Repo untersuchen; konkrete Bibliotheken oder API-Designs erst danach auswählen.

Übersicht
ID	Titel	Kategorie	Vorgeschlagene Priorität
CR-01	Responsives Trainingscockpit	UX / Feature	Hoch
CR-02	Konfigurierbarer Zeitmarker im Leistungsdiagramm	UX / Feature	Mittel
CR-03	Abschlussanimation und Auswertung	Feature	Hoch
CR-04	„Alles verbinden“: Pulsgurt und Geräteauswahl	Bug / UX	Hoch
CR-05	Raspberry-Pi-Display beim Start aktivieren	Bug	Hoch
CR-06	Automatischer Trainingsprofil-Generator	Feature	Mittel
CR-07	Fitnessanalyse, Profilfelder und Folgetraining	Feature	Mittel
CR-08	Optionales Kraftmodul vor oder nach Radtraining	Feature	Niedrig–Mittel
CR-09	Neutrales Branding und modulare Gerätearchitektur	Architektur	Hoch (Design vor neuen Adaptern)
CR-10	Taurus-Laufband / Sensor / mobiler Connector	Research / Feature	Später
CR-11	Apple-Watch-Livepuls / Apple Health	Research / Feature	Später
CR-12	Native iOS-/watchOS-Erweiterung und App-Store-Pfad	Research / Spike	Später
CR-01 – Responsives Trainingscockpit
Beobachtung: Vorhandene Ansichten sind grundsätzlich gut, aber wichtige Werte nicht gleichzeitig sichtbar.

Anforderungen: Eine kompakte, gut ablesbare Trainingsansicht für Tablet und Smartphone mit bestehendem Leistungsdiagramm sowie Instrumenten/Kacheln für:

Geschwindigkeit (km/h)

Puls (bpm)

aktuelle Leistung (Watt) und bei vorhandenem Stufenmodell aktuelle Leistungsstufe

Trittfrequenz (U/min)

Kalorienverbrauch (kcal; berechnet oder vom Gerät, mit Kennzeichnung)

vergangene Trainingszeit sowie verbleibende Trainingszeit (Time to End)

Akzeptanzkriterien: Alle verfügbaren Werte auf Tablet ohne View-Wechsel erkennbar; Smartphone-Layout lesbar und responsiv; bei fehlenden Sensoren keine fingierten Zahlen; vorhandene Diagrammfunktion bleibt nutzbar.

CR-02 – Zeitmarker im Leistungsdiagramm
Anforderungen: Am mitlaufenden Positions-/Zeitmarker optional die aktuelle Wattzahl und den Puls anzeigen. Beide Einblendungen separat ein-/ausschaltbar, um visuelle Überlastung zu vermeiden.

Akzeptanzkriterien: Ein-/Ausschalten ist persistent oder zumindest pro Sitzung konfigurierbar; Zeitmarker und Kurve bleiben gut lesbar.

CR-03 – Trainingsabschluss mit Motivation und Zusammenfassung
Anforderungen: Nach regulärem Trainingsende kurze Jubel-/Erfolgsanimation und Zusammenfassung mit Durchschnittspuls, durchschnittlicher Leistung, erbrachter Gesamtarbeit (wenn aus Messwerten berechenbar, z. B. kJ), Kalorien (kcal), durchschnittlicher Trittfrequenz und Trainingsdauer. Ergebnis in der Historie speichern; Nutzern eine Folgetraining-Empfehlung anbieten (vgl. CR-07).

Akzeptanzkriterien: Anzeige nur bei passenden Abschlusszuständen; nachvollziehbare Einheiten und Berechnungen; bei Datenlücken korrekte Kennzeichnung statt Null als vermeintlicher Messwert.

Hinweis: Eine bereits vorhandene Radfahrer-Animation wurde erwähnt; Bestand und mögliche Wiederverwendung prüfen, ohne unbestätigte Funktionsanforderungen daran zu erfinden.

CR-04 – „Alles verbinden“ und Pulsgurt
Reproduktion aus Training 1: Beim Trainingsstart wurde der Pulsgurt über „Alles verbinden“ nicht gekoppelt. Manuelles „Pulsgurt verbinden“ im Verbindungsdialog war erfolgreich.

Anforderungen: Ursache untersuchen (u. a. Fehlerbehandlung, Reihenfolge, Timeouts, parallele Geräteversuche). Im Startdialog auswählbare Checkboxen für zu verbindende Geräte (Pulsgurt, vorhandene weitere Bluetooth-/Trainingsgeräte, ggf. Zwift-Anbindung). Fehlgeschlagene optionale Verbindung darf andere Geräte nicht blockieren. Pro-Gerät-Status und klare Fehlermeldung.

Akzeptanzkriterien: Pulsgurt verbindet sich bei Auswahl zuverlässig; Fehler eines anderen Geräts blockiert Pulsgurt nicht; alle Versuche und Ergebnisse nachvollziehbar protokolliert.

CR-05 – Lokales Pi-Display beim Hochfahren dunkel
Beobachtung: Raspberry Pi soll sich nach fünf Minuten ohne Daum-Verbindung automatisch herunterfahren; danach blieb beim nächsten Hochfahren das lokale Display dunkel. Browserzugriff über das Netzwerk funktioniert.

Anforderungen: Startpfad, Display-/Backlight-Zustand, Kiosk-/UI-Dienst und Shutdown-Logik untersuchen; Display nach regulärem Boot wieder einschalten. Vorhandene 5-Minuten-Abschaltung erhalten; Start ohne Geräteverbindung und im Fehlerfall testen.

Akzeptanzkriterien: Nach Kaltstart und Wiederstart wird das Display aktiviert; Timeout-Logik ist unverändert und löst nicht versehentlich sofort aus.

CR-06 – Generator für Trainingsprofile
Anforderungen: Automatisch verschiedene Trainingsprofile erstellen: Dauer, Wattstufen, Ausdauer-/Intervall-/Regenerationseinheiten sowie Aufwärm- und Cooldown-Phasen; erzeugte Profile speichern, anzeigen, bearbeiten und wiederverwenden.

Akzeptanzkriterien: Profil ist vor Start verständlich visualisiert; Grenzen des Ergometers und vernünftige Leistungsbereiche berücksichtigt; keine automatische Überforderung aus Einzelmessungen ableiten.

CR-07 – Profil, Fitnessanalyse und nächster Trainingsvorschlag
Anforderungen: Bestehende Benutzerprofile um Alter oder Geburtsjahr, Gewicht, Körpergröße und optional Geschlecht ergänzen, soweit noch nicht vorhanden; jeweils nur für begründete Berechnungen verwenden. Training anhand von Puls, Dauer, Leistung, Trittfrequenz und zeitlichem Verlauf analysieren; Watt/kg, grobe Intensität, Entwicklung gegenüber vorherigen Einheiten und nachvollziehbare Hinweise darstellen. Nach Abschluss konkreten Vorschlag für nächste Einheit machen; mit einem Klick in bestehenden Trainingsplan übernehmen können.

Akzeptanzkriterien: Herkunft und Grenzen der Einstufung sichtbar; keine Diagnose oder behauptete VO2max ohne geeignete Datengrundlage; persönliche Daten bearbeitbar; Folgetraining nur mit Zustimmung in den Plan übernehmen.

CR-08 – Ergänzendes Oberkörper-/Kraftmodul
Anforderungen: Optionales kurzes, anpassbares Kraftprogramm rund um das Ergometertraining, bevorzugt vor der Radeinheit, wenn der Nutzer danach erschöpft ist. Zum Beispiel Liegestütze (auch Wand-/erhöhte Variante), Aufwärmen, Sätze, Wiederholungen, Pausen; Abschlussstatus und Fortschritt erfassen. Je nach Belastungsziel Übungen vor oder nach dem Cardio anbieten.

Akzeptanzkriterien: Modul ist vollständig optional, Übungsreihenfolge und Intensität konfigurierbar; keine Aufforderung zu Hantel-/Armübungen während des Tretens; Einträge erscheinen im Trainingsplan.

CR-09 – Herstellerunabhängiges Branding und Device-Connector-Architektur
Anforderungen: Produktname vorläufig „Fitness-Cockpit“ statt „Daum“ in allgemeinen Screens und Dokumentation; proprietäre Gerätetypen in spezialisierten Adaptern belassen. Geräte-Connector mit standardisiertem Modell für Verbindung, Fähigkeiten, Live-Messwerte (Zeit, Puls, Leistung, Geschwindigkeit, Kadenz, Steigung etc.), Start/Stopp und Fehlerzustände. Nicht jedes Gerät liefert oder steuert jede Metrik. Bestehenden Daum-Adapter möglichst unverändert über Interface anbinden. Zentrale Datenbank/API und UI hardwareunabhängig gestalten.

Akzeptanzkriterien: Vorhandener Daum-Workflow funktioniert weiterhin; Architektur gestattet später weiteren Connector ohne Änderungen an Kern-Trainingslogik; Markenbezeichnung anpassbar.

CR-10 – Älteres Taurus-Laufband integrieren
Bekannte Angaben: Hersteller Taurus; mindestens ca. 10 Jahre alt; ursprünglicher Preis grob 1.600 EUR; ca. 90 kg; laut Erinnerung bis etwa 18 km/h und 16 % Steigung; ältere Konsole mit rotem Display, umlaufenden LEDs, Handpulssensoren und Handgriff-Steuerung für Tempo/Steigung. Exaktes Modell und Schnittstellen unbekannt.

Zu prüfen:

Hersteller-/Modellidentifikation anhand Typenschild oder Konsolenfoto.

Native Schnittstelle (z. B. Bluetooth FTMS), falls überhaupt vorhanden.

Bluetooth-Nachrüstsensor (z. B. NPE Runn): tatsächliche mechanische Kompatibilität, Messwerte, Kalibrierung und Preis vor Beschaffung verifizieren.

Manuelle Laufbandtraining-Erfassung als Fallback.

Mobilgerät in Laufbandnähe als möglicher Sensor-Connector, während Raspberry Pi beim Daum bleibt: Übertragung per WLAN/API an zentrale Anwendung.

Browser zuerst: Web Bluetooth unter unterstützten Browsern; Safari auf iPhone bietet derzeit nicht dieselbe direkte Web-Bluetooth-Möglichkeit; native Bluetooth-Brücke nur optional (vgl. CR-12).

Nicht im ersten Scope: Automatische Steuerung von Laufbandgeschwindigkeit/-steigung; nur nach Modellprüfung und Sicherheitskonzept.

Akzeptanzkriterien: Rad- und Laufdaten werden demselben Profil zugeordnet; Laufbandtraining kann auch ohne externe Sensoren erfasst werden; keine zusätzliche iPhone-App als Pflicht.

CR-11 – Apple-Watch-Puls und HealthKit
Anforderungen: Machbarkeit einer optionalen Apple-Watch-Anbindung für Live-Pulsanzeige im Fitness-Cockpit untersuchen. Geräteübertragung über passende native watchOS-/iOS-Komponenten (HealthKit, aktive Workout-Session, WatchConnectivity oder geeignete Datenübertragung) prototypisch testen. Optionaler Apple-Health-Datenaustausch, nur mit expliziter Nutzerberechtigung und Datenschutzkonzept. Bestehender Pulsgurt bleibt unabhängig nutzbar.

Akzeptanzkriterien (Spike): Dokumentierter Test, ob Live-Puls stabil und mit sinnvoller Latenz im Cockpit ankommt; Verhalten bei gesperrtem iPhone, Trainingsunterbrechung und Verbindungsabbruch geprüft; kein Browser-only-Zugriff auf Live-Watch-Puls vorausgesetzt.

CR-12 – Native iPhone-/Apple-Watch-App, ohne doppelte Produktlogik
Ziel: Langfristig optional native iPhone-/Watch-Erweiterung und mögliche App-Store-Veröffentlichung. Bestehende Web-App, API, Trainingsplan und Datenbank bleiben das gemeinsame Produkt; native App übernimmt bei Bedarf Bluetooth, Apple-Watch-Integration und iOS-spezifische Funktionen.

Machbarkeitsphase:

iPhone-Prototyp für Sensor-BLE und Authentifizierung an zentraler API.

Watch-Prototyp mit Trainingssession/Live-Puls; Kommunikation zum iPhone/Backend testen.

Abwägen, ob native Oberfläche, eingebettete Weboberfläche oder Hybridansatz angemessen ist; App-Store-Richtlinien und Datenschutz von Gesundheitsdaten berücksichtigen.

Entwicklung weiter in Git/VS Code/Codex unter Windows; macOS/Xcode-basierte Builds und Signierung bei Bedarf über Cloud-macOS/GitHub-Actions-Runner; reale iOS-/Watch-Tests separat planen.

Apple Developer Program, Signierung, TestFlight, Privacy Disclosures und App-Review erst vor Veröffentlichung final klären.

Akzeptanzkriterien (Spike): Machbarkeitsbericht mit Architekturentscheidung, Build-/Testprozess, Berechtigungs- und Datenschutzanforderungen, Risiken und grober Aufwandsschätzung. Kein Zwang, unmittelbar eine App zu veröffentlichen.

Empfohlene Reihenfolge für Codex
Phase 0 – Bestandsaufnahme: Repo-Struktur, UI, Datenmodell, Raspberry-Pi-Autostart, Geräte-/Pulsgurt-Code, Trainingspläne und Tests analysieren. Je CR erfassen: bereits vorhanden / teilweise vorhanden / fehlt / unklar. Vor jeder Implementierung vorhandenen Code prüfen.

Phase 1 – Fehlerbehebung: CR-04 und CR-05 inklusive reproduzierbarer Tests und Logs.

Phase 2 – Nutzbarer Trainingsablauf: CR-01, CR-02, CR-03, danach CR-07 (Profil/Folgetraining) soweit vom Datenmodell her sinnvoll.

Phase 3 – Architektur und zusätzliche Features: CR-09 als vorbereitender Refactor ohne Funktionsverlust; anschließend CR-06 und CR-08; Reihenfolge je nach Abhängigkeiten abstimmen.

Phase 4 – Machbarkeitsprüfungen: CR-10, CR-11, CR-12 zuerst als technische Spikes, noch keine Hardwarekäufe und keine App-Store-Veröffentlichung voraussetzen.

Übergabe an Codex
Bitte lies docs/change-requests/fitness-cockpit-cr-2026-11-06.md, untersuche zuerst den tatsächlichen Repository-Stand und erstelle eine priorisierte, technische Umsetzungsplanung. Gib pro CR vorhandene Komponenten, notwendige Änderungen, Abhängigkeiten, Risiken und Tests an. Kennzeichne offene Punkte ausdrücklich. Implementiere zunächst nichts ohne Freigabe. Schlage möglichst kleine, getrennte Branches/PRs vor, beginnend mit CR-04 und CR-05. Erhalte die vorhandene Daum-Anbindung, alle bestehenden Trainingsprofile und die Datenbankmigrationen abwärtskompatibel. Die Produktbezeichnung „Fitness-Cockpit“ ist vorläufig.

Offene Angaben
URL/Provider des eigenen Git-Repositories (nicht das fremde Beispielprojekt MyBleTrainer).

Endgültiger Produktname.

Konkretes Taurus-Modell und Sensor-Kompatibilität.

Bestandsaufnahme der bestehenden Radfahrer-Animation, Benutzerprofile und Trainingsplandaten.

Zielplattformen/Browserversionen und bevorzugte Datenspeicherung.

Für CR-12: Verfügbarkeit von Apple-Entwicklerkonto und macOS-Buildumgebung.

⋮⋮⋮⋮
