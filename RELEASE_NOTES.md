# Release Notes

## 2.0.0 — 4. November 2026

Erste dokumentierte öffentliche Version von **DaumControlV2.0 / DAUM Studio** für den Daum Premium 8i mit Raspberry Pi 3 B+.

### Training und Oberfläche

- Watttraining und alle Wattvorlagen starten ohne persönliche FTP. Die Beispielbasis 150 W bleibt sichtbar und wird nicht als persönliche FTP gespeichert.
- Watttraining funktioniert ohne Pulsgurt. Im Vorabcheck kann aus dem Pulsmodus ausdrücklich in Watttraining gewechselt werden.
- Sechs neue Berg-/Tal-Szenarien in 35, 45 und 60 Minuten mit sanften Rampen, Kuppen, Plateaus und leichteren Abfahrten.
- Bergansicht mit virtuellem Streckenprofil, aktueller Position und Steigungsanzeige.
- Einstellbares Zeit- und Wattraster, gespeicherte Browserauswahl sowie genaue Dauer pro Leistungsstufe.
- Benutzerprofile mit persönlicher Leistungsanpassung; verbesserte Button-Anordnung auf kleinen Displays.
- Einzelne Aktivitäten lassen sich mit Rückfrage löschen; TCX-, CSV- und JSON-Export bleiben verfügbar.
- Verbesserte mobile Kopfzeile und zugängliche Beschriftung der Symbol-Navigation.

### Raspberry Pi

- Optionaler Systemdienst fährt nach fünf Minuten ohne direkten Daum-LAN-Link sauber herunter.
- Laufende Fahrten werden vorher beendet und gespeichert; unbekannter Linkstatus und Speicherausfälle führen nicht zum sofortigen Herunterfahren.
- Dauerhafter Ein/Aus-Schalter in den App-Einstellungen und Desktop-Verknüpfung ohne erneute Passwortabfrage.
- Der Bildschirmschoner bleibt eine unabhängige Funktion; HDMI bleibt dabei aktiv.

### Dokumentation und Lizenz

- Hardwarebasis mit ausgelesenem Pi-Modell, 800-×-480-HDMI-Display und ADS7846-Touch dokumentiert.
- Installations-, Bedienungs-, Architektur- und Testanleitung ergänzt.
- Eigener Quellcode und eigene Dokumentation unter MIT; Fremdkomponenten behalten ihre Lizenzen.
- Externes Garmin-Testschema wird separat bezogen und nicht mit dem öffentlichen Quellcode verteilt.

### Prüfung

62 Backend-Tests unter Windows bestanden; auf dem ARM64-Pi 61 bestanden und ein optionaler Schema-Test übersprungen. Browserprüfungen für Desktop, Pi und Handy sowie Prüfung des bereitgestellten Pi-Frontends und der Desktop-Umschaltung bestanden. Weitere Details unter [Tests](docs/TESTING.md).

### Bekannte Grenzen

Die App ist für das vertrauenswürdige Heimnetz bestimmt und besitzt keine Anmeldung. Bergstrecken sind zeitbasierte Wattprogramme mit virtuellen Steigungen. Pulsregelung benötigt persönliche Pulswerte und einen frischen BLE-Sensor. Zwift-FTMS bleibt experimentell. Der Pi 3 B+ startet nach Poweroff durch erneutes Anschließen des Netzteils; Einschalten allein durch den Daum benötigt zusätzliche Hardware. Ein echter Stopp am Bike kann bei Verbindungsverlust nicht garantiert werden.
