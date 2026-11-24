# Daum: heruntergeladenes Protokoll- und Vergleichsmaterial

Stand: 09.11.2026. Ergebnis dieser Recherche: **11 echte Dateien, insgesamt 213.414 Bytes**, lokal geladen und mit SHA-256 geprüft. Das deutsche Hersteller-Protokoll liegt jetzt als PDF vor. Es bestätigt die Feldbelegung, löst den Widerspruch bei der Geschwindigkeitseinheit aber nicht auf. Es wurde bei dieser Recherche kein Gerätebefehl gesendet und keine laufende Installation geändert.

## Lokal verfügbar und reproduzierbar

```powershell
python tools/download_daum_material.py
python -m unittest discover -s tools/tests -v
```

Ziel ist standardmäßig `.cache/fitness-material/daum/`, unabhängig vom Arbeitsverzeichnis. `manifest.json` enthält für jede Datei Original-URL, feste Git-Revision, Abrufzeit, Bytezahl, SHA-256 und Lizenzstatus. Der Downloader prüft fest hinterlegte Hashes, Dateityp und Größenlimit, bevor er vorhandene Dateien ersetzt. Heruntergeladener Code wird weder importiert noch ausgeführt. Die fünf Offline-Tests prüfen beschädigte Antworten, Prüfsummenabweichung, Größenlimit, Herkunftsmetadaten und Pfadbegrenzung; alle bestanden.

Der Cache ist durch `/.cache/` in der bestehenden `.gitignore` ausgeschlossen. Die Herstellerunterlage bleibt dort: Die MIT-Lizenz eines spiegelnden Projekts erteilt nicht automatisch Rechte an darin abgelegten Daum-Dokumenten. Eine Weiterverteilung dieses PDFs wurde nicht als erlaubt festgestellt.

| Lokale Dateien | Herkunft / fester Stand | Lizenzbewertung |
|---|---|---|
| `SP-KOMM-PM1.pdf` | Herstellerdokument, 11 Seiten; Spiegel im Premium-Bridge-Repository, Revision `546e13f6d0db9992644fbe18154e9f070cae0d7c` | Herstellerrechte; nur lokales Rechercheexemplar |
| `incyclist-utils.ts`, `incyclist-utils.unit.test.ts`, `incyclist-LICENSE.txt` | Incyclist, Revision `a77985fc581d35670af83c604cd41643a1c204f1` | MIT, Lizenzdatei mitgeladen |
| `premium-daumPremium.js`, `premium-protocol-tests.js`, `premium-README.md`, `premium-LICENSE.txt` | sta-hems/daumUSB2BLE, Revision `546e13f6d0db9992644fbe18154e9f070cae0d7c` | Software MIT; Hersteller-PDF separat beurteilt |
| `qz-DaumUSB.cpp` | QZ, Revision `6d6bb41fa58ba2485d5e6f30385cf71809717aa7` | Dateikopf: GPL-2.0-or-later |
| `ergoface-rs232.py`, `ergoface-LICENSE.txt` | weinzmi/ergoFACE, Revision `6cd85cd093cb86c590a78f749346057ba515e16d` | Repository: MPL-2.0 |

PDF-Prüfsumme: `11f521eaf0d3078ce4923741c50ccfde5ef7dcc28252087d8601e9caa53de4f9`. Alle weiteren vollständigen Prüfsummen stehen zusätzlich direkt im Downloader. Der ursprüngliche Hersteller-Link ist über [ackstorms eigene Untersuchung zum Premium 8i](https://ackstorm.de/projects/daum/daum.html) und deren Archivverweis nachvollziehbar; der funktionierende Dateidownload verwendet den festen Git-Spiegel.

## Was das Herstellerdokument belegt

SP-KOMM-PM1, Version 1.0, §2.1.21, beschreibt `X70` ab Version 1.380. Die Felder werden durch `GS` getrennt:

| Index | Interpretation laut Dokument |
|---|---|
| 0 | Gerätesekunden |
| 1 | Herzschläge pro Minute |
| 2 | Tempo, km/h |
| 3 | Gefälle/Anstieg, Prozent |
| 4 | Gerätestrecke, Meter |
| 5 | Pedalumdrehungen pro Minute |
| 6 | Geräte-Leistungsangabe, Watt |
| 7 | Energieangabe I (physikalisch), kJ |
| 8 | Energieangabe II (realistisch), kJ |
| 9 | Moment, Nm |
| 10 | Gangcodierung mit Offset 1 |
| 11 | Ein/Aus-Zustand |
| 12 | Trittfrequenzbewertung mit Offset 1; zu langsam/zu schnell kann das Erreichen der Last verhindern |

`X00` hat dagegen ausdrücklich m/s und Puls pro Sekunde. §1.2 unterscheidet Transportquittung und Antwortinhalt: Ein nicht einstellbarer Wunsch kann durch einen benachbarten akzeptierten Wert beantwortet werden. `S20` steuert die externe Lastregelung, `S23` die Wattlast. `L70` beschreibt aktive Grenzen je Limitart einschließlich Minimum, Maximum und Standardwert. Diese Limitfunktion kann auch schreiben; eine spätere reine Abfrage muss daher gesondert gegen das Gerät geprüft werden. [Hersteller-PDF im festen Spiegel](https://github.com/sta-hems/daumUSB2BLE/blob/546e13f6d0db9992644fbe18154e9f070cae0d7c/manual/SP-KOMM-PM1.pdf)

Die Feldbezeichnung allein beantwortet die Frage nach einer unabhängig gemessenen Ist-Leistung nicht. Die bereits dokumentierten eigenen Standversuche zeigen lediglich, dass Feld 6 bei null Trittfrequenz mit dem angeforderten Wert mitging. Daraus lässt sich nicht ableiten, wie das Feld während des Tretens entsteht. Die bestehenden Qualitätskennzeichen bleiben deshalb erforderlich.

## Vergleich mit Originalimplementierungen

**Incyclist:** Der Decoder multipliziert X70-Feld 2 mit 3,6. Der zugehörige Test erwartet aus dem konstruierten Rohwert 10 den Wert 36. Die Energie- und Drehmomentfelder sind im heutigen Decoder auskommentiert. Der Faktor existiert bereits im Initialstand vom 19.02.2023. In den untersuchten Dateiänderungen wurde keine Begründung oder Firmwarezuordnung für diese Einheitenwahl gefunden. Ein passender Test beweist die Programmlogik, nicht die Einheit auf unserem Gerät. [Decoder](https://github.com/incyclist/devices/blob/a77985fc581d35670af83c604cd41643a1c204f1/src/serial/daum/premium/utils.ts#L274), [Tests](https://github.com/incyclist/devices/blob/a77985fc581d35670af83c604cd41643a1c204f1/src/serial/daum/premium/utils.unit.test.ts#L267), [Initialstand](https://github.com/incyclist/devices/blob/0c859d1f364cc29f441aecd04ea47e5cc18793cb/src/serial/daum/premium/utils.ts)

**Neue Premium-Bridge:** Der Autor meldet reale 8i-Tests für einen Fallback aus `X00`, `S21` und `S23`, wenn X70 zwar quittiert, aber nicht beantwortet wird. Der X70-Decoder verweist auf Incyclist, übernimmt dessen Faktor und setzt bei fehlender Trittfrequenz Leistung und Tempo auf null. Der veröffentlichte echte X00-Test enthält Tempo null; er entscheidet die Einheit deshalb ebenfalls nicht. Das ist ein nützlicher Hinweis auf Firmwareunterschiede und ein Ansatz für Diagnose-Fallbacks, aber keine zweite unabhängige Messbestätigung. [Einführungsänderung mit Hardwarebericht](https://github.com/sta-hems/daumUSB2BLE/commit/9c3b3b02d5d5ac2379bd6d866b4ef5cae8d335fa), [Decoder](https://github.com/sta-hems/daumUSB2BLE/blob/546e13f6d0db9992644fbe18154e9f070cae0d7c/USB/daumPremium.js#L98), [Tests](https://github.com/sta-hems/daumUSB2BLE/blob/546e13f6d0db9992644fbe18154e9f070cae0d7c/test/daumPremium_test_protocol.js#L82)

**QZ und ursprüngliches ergoFACE:** Beide untersuchten Treiber betreffen Daum Classic. QZ verwendet binäre Abfrage `0x40` und Zielwertbefehl `0x51`; ergoFACE beschreibt seinen Datenabruf ausdrücklich als Classic 8008 TRS. Diese Implementierungen liefern Vergleichsmaterial für Classic, entscheiden aber die Premium-X70-Frage nicht. [QZ-Treiber](https://github.com/cagnulein/qdomyos-zwift/blob/6d6bb41fa58ba2485d5e6f30385cf71809717aa7/src/devices/daumbike/DaumUSB.cpp#L259), [ursprüngliches ergoFACE](https://github.com/weinzmi/ergoFACE/blob/6cd85cd093cb86c590a78f749346057ba515e16d/src/rs232.py)

## Konkreter nächster Nutzen im bestehenden Cockpit

1. **Erweiterte Rohdaten sichtbar machen:** Gerätestrecke, Energiewerte, Moment, Gerätezustand und unbekannte Statuscodes lassen sich als Geräteangaben speichern und diagnostisch anzeigen. Fehlende oder ungültige Felder bleiben leer. Der im eigenen Standversuch beobachtete Statuswert `0` darf nicht stillschweigend als dokumentierter Normalstatus interpretiert werden.
2. **Tempo während einer normalen Fahrt klären:** Eine rein lesende Aufzeichnung vergleicht Rohwert, Cockpit-Anzeige und Gerätestreckenänderung über hinreichend lange Intervalle. Das kann zwischen `raw` und `raw * 3.6` unterscheiden. Firmwarekennung und Ergebnis gehören zusammen gespeichert; eine vom Nutzer gewählte Einheit bleibt bis zur Prüfung eine Konfiguration, kein Messnachweis. Ein Stillstand mit Rohwert null kann diese Frage nicht entscheiden.
3. **Energie als zusätzliche Plausibilisierung prüfen:** Aus aufeinanderfolgenden kJ-Zählerständen ließe sich `1000 * delta_kJ / delta_s` als durchschnittliche, abgeleitete Leistung berechnen. Das ist zunächst eine eigene Hypothese. Zählerauflösung, Rücksprünge, Aktualisierungsrate, Fahrtunterbrechung und Ursprung des Zählers müssen beobachtet werden. Selbst gute Übereinstimmung beweist noch keinen unabhängigen Leistungssensor, weil der Zähler auch intern aus einer Lastvorgabe berechnet sein könnte.
4. **Erst anschließend Messqualität freigeben:** Wattwunsch, Gerätebestätigung, rohe Geräte-Leistungsangabe und verifizierte Messung weiter getrennt behandeln. Ein bloßer Vergleich mit anderem Open-Source-Code rechtfertigt keine neue Freigabe für mechanische Arbeit, W/kg, Coach-Belastungsanalyse oder BLE-Leistungsmessung.

Diese Recherche liefert belastbares Material und reproduzierbare Downloads. Offene Hardwarefragen bleiben ausdrücklich offen; es wurde keine physische Widerstandsprüfung oder fahrende Kalibrierung nachgeholt. Die frühere Freigabe für den einmaligen Standtest wird dafür nicht erneut verwendet.
