# Apple-Sensorbrücke: Quellcode-Spike

Status: **auf Windows vorbereitet, nicht mit Apple-SDK gebaut oder am Gerät getestet**. Kein veröffentlichbares Produkt und kein Ersatz für das Browsercockpit. Die zugehörige Architektur-/Testplanung steht in [CR-10–12](../../docs/change-requests/cr10-12-feasibility.md).

## Enthalten

- Swift-Paket `BridgeMessages`: zeitgestempelte, sequenzierte Pulswerte, standardisierter 8-/16-Bit-BLE-Parser und Frischeprüfung; Unit-Tests.
- `iOS`: SwiftUI-Testoberfläche, BLE-Heart-Rate-Leser, Empfang von WatchConnectivity und ausdrücklich aktivierbarer Versand an separaten HTTPS-Testempfänger.
- `watchOS`: aktive HealthKit-Indoor-Cycling-Session mit Livepulserfassung und unmittelbarer Übertragung an erreichbares iPhone. Workout wird nach Ende verworfen; kein automatischer Apple-Health-Import/Export.
- `receiver.py`: begrenzter authentifizierter TLS-Testempfänger, keine Produktdatenbank und keine Messwertlogs.

Die automatische Auswahl des ersten BLE-Gurts ist ausschließlich für den beaufsichtigten Spike mit einem bekannten Gurt gedacht. Eine Produkt-App benötigt eine Geräte-/Pulsquellenauswahl. Der Spike registriert keine Hintergrundmodi auf Vorrat; Hintergrundzuverlässigkeit ist Teil der offenen Abnahme.

## Auf macOS einrichten

1. Mit installiertem Xcode zuerst `cd spikes/apple-bridge && swift test` ausführen. Diese Tests benötigen weder iPhone noch HealthKit; sie wurden hier nicht ausgeführt.
2. In Xcode ein iOS-App-Projekt mit SwiftUI und dazu eine gekoppelte watchOS-App anlegen, Zielversion mindestens iOS 17/watchOS 10. Das Paket dieses Ordners als lokale Package Dependency aufnehmen; `BridgeMessages` beiden Targets zuordnen.
3. Generierte App-Quellen durch die passenden Quellen in `iOS/` bzw. `watchOS/` ersetzen. In jedem Target darf genau ein `@main` existieren. Swift-Sprachmodus zunächst Swift 5 verwenden; Swift-6-Concurrency-Migration separat prüfen.
4. Eigene Bundle-IDs und dasselbe Entwicklerteam wählen; Companion-Zuordnung der Watch-App in Xcode prüfen. HealthKit-Capability im Watch-Target und Hintergrundmodus »Workout processing« aktivieren.
5. iOS-Info-Zwecktexte: `NSBluetoothAlwaysUsageDescription` (Pulsgurt lesen) und `NSLocalNetworkUsageDescription` (gewählten lokalen Testempfänger erreichen). Watch: `NSHealthShareUsageDescription` (Livepuls lesen), `NSHealthUpdateUsageDescription` (Workout-Session). Zwecktexte müssen den tatsächlichen Test erklären. Keine globale Deaktivierung von ATS/TLS.
6. Simulatorbuild beider Targets durchführen. Danach reale gekoppelte Geräte signieren/installieren; BLE/Watch-Sensorwerte werden im Simulator nicht als realer Gerätenachweis gewertet.

Ein vollständiges signiertes `.xcodeproj` wird erst auf dem macOS-System mit festgelegtem Entwicklerteam erzeugt und überprüft. Für wiederholbare CI-Builds dieses Projekt danach versionieren und `xcodebuild -list` sowie die konkreten Simulator-Destinations aus der installierten Xcode-Version verwenden. Kein Workflow lädt aktuell Secrets hoch oder verteilt eine App.

## Separaten Empfänger starten

Eigenes Testzertifikat mit korrektem DNS-/IP-SAN und dazugehörigem Key vorbereiten; dem ausstellenden Test-CA-Zertifikat auf dem iPhone ausdrücklich vertrauen. Keine Zertifikatsprüfung im App-Code umgehen. Token nur als temporäre Umgebungsvariable setzen, mindestens 32 zufällige Zeichen, nicht im Git oder in Shell-Ausgaben ablegen:

```sh
python3 receiver.py --host 192.168.1.123 --cert /path/to/test-cert.pem --key /path/to/test-key.pem
```

Ohne `--host` hört der Empfänger nur auf localhost. Keine Internetweiterleitung einrichten. App auf HTTPS-Testadresse `/pulse` und dasselbe Token konfigurieren. Zunächst einmalig senden; kontinuierlichen Versand nur für die beaufsichtigte Testsession einschalten. Bei Fehler wird dieser beendet, es gibt keinen Replay alter Werte. App-Prozessende löscht Token und Zustimmung aus dem Speicher.

Der Empfänger ist nicht `/api` des Fitness-Cockpits. Seine letzte Probe steht ausschließlich serverintern in `latest_sample`; es gibt absichtlich keinen unauthentifizierten Abruf. Für Latenztests kann die Messauswertung im lokalen Debugger erfolgen, ohne Gesundheitsdaten zu protokollieren. Auf dem Produktbackend fehlen noch explizite mobile Paarung, Benutzerbindung, Rechte und widerrufbare Tokens.

## Offene Tests

Compiler-/SDK-Kompatibilität, Signing/Entitlements, reale BLE-Verbindung, HealthKit-Berechtigungswiderruf, gesperrtes iPhone, aktive zweite Workout-App, WatchConnectivity-Ausfall und Uhrenabweichung sind ungeprüft. Die Python-Validierung wird im Repository unter `bike/tests/test_native_spike.py` getestet. Erst die reale Testmatrix im Machbarkeitsbericht entscheidet über WatchConnectivity gegenüber Workout-Mirroring.
