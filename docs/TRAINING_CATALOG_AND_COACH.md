# Trainingskatalog und optionaler Coach

Stand: 2026-11-09. Diese Erweiterung verwendet die vorhandene SQLite-Tabelle
`plans`, vorhandene Segmentdarstellung und dieselbe Trainings-Engine.

## Katalog und Profilzustand

Der Katalog ergänzt Name/Segmente um Quelle, Kategorie, Beschreibung,
Intensitätsangabe, Revision und benutzerbezogene Favoriten. Quellen sind
`preset`, `manual` und `ai`. Ein lokal regelbasiert erzeugter Coach-Vorschlag
bleibt `manual` und wird sichtbar als lokaler Vorschlag gekennzeichnet; er wird
nicht als Ergebnis eines KI-Dienstes ausgegeben. `ai` wird ausschließlich nach
einer tatsächlich erfolgreichen strukturierten externen Anfrage vergeben.

Die vier Anfangsvorlagen heißen Lockere Runde, Intervalle, Bergfahrt und
Ausdauerfahrt. Die bestehenden Trainingsvorlagen einschließlich der sechs
virtuellen Bergstrecken bleiben erhalten. Vorlagen werden vor Bearbeitung
kopiert; eigene Profile unterstützen Bearbeiten, Kopieren und bestätigtes
Löschen. Verwendet ein persönlicher Planeintrag ein Profil, verhindert die API
das Löschen mit einer Erklärung, statt die Verknüpfung still zu zerstören.

Neue Profilmetadaten stehen in `plan_catalog`, Favoriten in `plan_favorites`
und Validierungsnachweise in `plan_checks`. Eine Migration ändert keine
bestehenden Profilzeilen. Neue eigene Katalogprofile gehören dem aktiven
Benutzer; bisher gemeinsam genutzte Profile bleiben gemeinsam sichtbar.

Neue Profile beginnen als Entwurf. Übernahme/Annahme führt zu `accepted`, die
ausdrückliche Prüfung zu `validated`, Startvorbereitung zu `ready`. Die Prüfung
validiert endliche ganzzahlige Wattwerte, positive Segmentdauern, Gesamtdauer,
Geräte-/Benutzergrenzen und vorhandene Struktur. Die Geräteprüfung bei der
Vorbereitung beachtet Verbindung und Wattsteuerfähigkeit sowie bei Pulsmodus
benötigte persönliche Pulsgrenzen und ein frisches Signal.

Jeder Nachweis bindet Profilinhalt, Nutzerkonfiguration, Gerätefähigkeiten,
Gerätemodus, Intensität und Trainingssteuerung. Änderungen machen den Nachweis
ungültig. Start eines neuen Katalog-/Coach-Profils benötigt einen gültigen
`validation_token`; Weglassen des Tokens umgeht die Prüfung nicht. Alte
Programme aus den bisherigen Schnittstellen können weiter ohne Token gestartet
werden, durchlaufen aber die strukturelle Prüfung und Leistungsgrenzen.

Optimistische Revisionen verhindern das Überschreiben zwischenzeitlicher
Änderungen durch einen zweiten Browser. Übernommene Trainingseinheiten verändern
die gespeicherte Originalkurve nicht.

## Coach ohne externe Verbindung

Ohne API-Schlüssel funktioniert die Anwendung vollständig mit Katalog,
Generator und lokalem Coach. Dieser erzeugt einen bewusst konservativen,
bearbeitbaren Vorschlag aus ausreichend erfassten realen Einheiten oder klar
gekennzeichneten Beispielwerten. Er bietet keine medizinische Einstufung und
keine automatische Belastungssteigerung. Demo-Einheiten werden nicht als reale
Trainingsgrundlage ausgegeben. Fehlende Daten werden erklärt.

Der Ablauf ist: Vorschlag erzeugen, Kurve ansehen, Segmente ändern, übernehmen,
ins Cockpit wechseln und dort bewusst starten. Die Profil-/Grenzenprüfung läuft
beim Start automatisch; eine freiwillige Prüfung im Coach bleibt verfügbar. Alle
Coach-/Katalogendpunkte bleiben von Gerätebefehlen getrennt. Erneute Übernahme
desselben Vorschlags erzeugt kein zweites Profil. Nach einer nachträglichen
Bearbeitung wird das vorhandene übernommene Profil mit neuer Revision gespeichert
und wird beim nächsten Start automatisch erneut geprüft.

## Optionaler externer OpenAI-Adapter

Nur der Backendprozess liest `OPENAI_API_KEY` und `OPENAI_MODEL`. Ohne beide
Werte meldet die API den externen Provider als nicht konfiguriert. Es gibt
keinen eingebauten Modell-Fallback und keinen automatischen externen Aufruf.
Schlüssel gehören nicht in Frontenddateien, Git oder Diagnoseausgaben. Die
Anbindung wurde mit einer simulierten Responses-Antwort geprüft; ein echter
kostenpflichtiger Aufruf wurde nicht ausgeführt.

Für den systemd-Benutzerdienst auf dem Pi können die beiden Werte in einer
privaten Datei hinterlegt und per Drop-in eingebunden werden:

```sh
mkdir -p ~/.config/daum-studio ~/.config/systemd/user/daum-studio.service.d
chmod 700 ~/.config/daum-studio
nano ~/.config/daum-studio/coach.env
chmod 600 ~/.config/daum-studio/coach.env
nano ~/.config/systemd/user/daum-studio.service.d/coach.conf
```

In `coach.env` stehen `OPENAI_API_KEY=...` und `OPENAI_MODEL=...`, jeweils in
einer eigenen Zeile mit einem gültigen Schlüssel und einem ausgewählten,
verfügbaren Modell. Die Drop-in-Datei enthält:

```ini
[Service]
EnvironmentFile=%h/.config/daum-studio/coach.env
```

Nach dem Speichern `systemctl --user daemon-reload` und anschließend bei
gestopptem Training `systemctl --user restart daum-studio.service` ausführen.
Die Oberfläche zeigt dann den Einrichtungsstatus; er bestätigt das Vorhandensein
der Werte, nicht deren Gültigkeit oder die Erreichbarkeit des Dienstes. Schlüssel
nicht ins Repository übernehmen oder in Screenshots und Logs ausgeben.

Für jede externe Anfrage muss der Benutzer die Datenübertragung bewusst
freigeben. Die Oberfläche zeigt vorher die Datennutzung an. Übertragen werden
Trainingsziel, gewünschte Dauer, aktuelle Wattgrenzen und Zusammenfassungen der
letzten zehn realen Radeinheiten: Dauer, mittlere Leistung/Puls/Kadenz,
Messabdeckung, geplante/angeforderte Leistungsbereiche, manuelle Eingriffe,
Pausen und Häufigkeit der letzten 14 Tage. Namen, Körpermaße, Geburtsdaten,
Sensoradressen und vollständige Messspuren werden nicht versendet.

Der Adapter nutzt `POST https://api.openai.com/v1/responses`, `store: false`
und ein striktes JSON-Schema unter `text.format`, einschließlich
`additionalProperties: false`. Die serverseitige Profilvalidierung läuft
zusätzlich unabhängig vom Modellschema. Verweigerte/unvollständige Antworten,
falsche Gesamtdauern, Zusatzfelder, NaN, gebrochene Segmente und überschrittene
Grenzen werden abgewiesen. HTTP-/Timeoutfehler erzeugen keine Profile und keine
Gerätebefehle. Während einer Anfrage geänderte Benutzer-/Belastungskonfiguration
verwirft das Ergebnis. Es werden keine Tools oder Gerätefunktionen an das Modell
angeboten. Die übrigen API-Datenverarbeitungsbedingungen bleiben maßgeblich;
`store: false` ist kein allgemeines Versprechen über sämtliche Providerprozesse.

Implementierungsquelle: [OpenAI Structured Outputs, Responses API](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

## Schnittstellen

| Schnittstelle | Verhalten |
| --- | --- |
| `GET /api/catalog` | Katalog mit Metadaten, Favoriten und aktuellen Leistungsgrenzen |
| `POST /api/catalog` | Eigenes Profil als Entwurf erstellen |
| `GET /api/catalog/{id}` | Profildetails |
| `POST /api/catalog/{id}/update` | Eigene Profile mit `expected_revision` ändern |
| `POST /api/catalog/{id}/duplicate` | Eigene Kopie erzeugen |
| `POST /api/catalog/{id}/delete` | Nach ausdrücklichem `confirm: true` löschen |
| `POST /api/catalog/{id}/favorite` | Persönlichen Favoriten setzen/entfernen |
| `POST /api/catalog/{id}/accept` | Aktuelles Profil ausdrücklich annehmen |
| `POST /api/catalog/{id}/validate` | Segment-/Grenzprüfung, neuen Nachweis ausstellen |
| `POST /api/catalog/{id}/prepare` | Nachweis und Startvoraussetzungen prüfen, kein Start |
| `GET /api/coach/config` | Providerverfügbarkeit und Erklärung der Datenverwendung |
| `GET /api/coach/context` | Lokale Zusammenfassung, niemals externer Aufruf |
| `POST /api/coach/suggest` | Lokalen oder ausdrücklich freigegebenen externen Vorschlag erzeugen |
| `POST /api/coach/adopt` | Bearbeitbaren Vorschlag übernehmen, kein Gerätebefehl |

Die vorhandene API bleibt zusätzlich bestehen. Vollständige Requestmodelle stehen
auf der laufenden Installation unter `/docs`. `expected_user_id` schützt
Schreibzugriffe gegen einen zwischenzeitlichen Wechsel des gemeinsam aktiven
Benutzers; es ersetzt weiterhin keine Anmeldung für ein öffentliches Netzwerk.

## Nachweis der Leistungsquelle

Beim beaufsichtigten Daum-Test am 2026-11-09 folgte das bisher als Leistung
interpretierte X70-Feld den Sollwerten 25/35/25 W auch bei Trittfrequenz null.
Das weist keine unabhängig gemessene Tretleistung nach. Eine bestätigte
Wattvorgabe ist ein Steuerzustand und darf nicht als physische Leistung oder
mechanische Arbeit ausgegeben werden.

Leistungsabhängige Auswertung und Empfehlungen verwenden deshalb nur Einheiten
mit beiden expliziten Nachweisen: `power_measurement_verified: true` und
`measurement_quality.power_watts: verified_measured`. Protokoll-ACK,
`device_reported_unverified`, eine bloße Quellenangabe `daum` oder fehlende
Altdaten-Herkunft reichen nicht. Ohne Nachweis bleiben Watt/kg, Leistungsintensität,
Leistungstrend und Leistungsvergleich nicht verfügbar. Die direkte Empfehlung
aus einer Einheit wird unterdrückt. Der lokale Coach bietet dann nur einen klar
gekennzeichneten, bearbeitbaren Beispielvorschlag oder nutzt bewusst hinterlegte
Komfortparameter; er interpretiert alte Gerätewerte nicht als Belastbarkeit.

Alte Datenbankwerte werden nicht rückwirkend umgeschrieben. Die Analyse stellt
einen archivierten, unverifizierten Mittelwert bei Bedarf ausdrücklich getrennt
von der nicht verfügbaren Messgröße bereit. Externe Coach-Anfragen erhalten
solche Mittelwerte nicht als gemessene Leistung; Sollwertbereiche bleiben als
Steuerbefehle bezeichnet. Unabhängige Pulsdaten, Kadenz und Dauer können mit ihren
jeweiligen Grenzen weiter angezeigt werden.
