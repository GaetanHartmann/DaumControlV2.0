# Fremdkomponenten und Quellen

Die [MIT-Lizenz](LICENSE) gilt für den eigenen Quellcode und die eigene Dokumentation von DaumControlV2.0 / DAUM Studio. Abhängigkeiten behalten ihre jeweiligen Lizenzen und Urhebervermerke. Die Installation über npm und pip bezieht diese separat; `node_modules`, virtuelle Umgebungen und Build-Ausgaben sind nicht Teil des Git-Repositorys.

## Frontend

| Komponente | Lizenz | Quelle |
| --- | --- | --- |
| Vue und die Vue-Pakete | MIT | [vuejs/core](https://github.com/vuejs/core) |
| Lucide Vue Icons | ISC, mit MIT-Anteilen von Feather | [lucide-icons/lucide](https://github.com/lucide-icons/lucide) |
| Vite, Build-Werkzeug | MIT | [vitejs/vite](https://github.com/vitejs/vite) |
| TypeScript, Entwicklungswerkzeug | Apache-2.0 | [microsoft/TypeScript](https://github.com/microsoft/TypeScript) |

Die Schriftarten DM Sans und Manrope werden optional von Google Fonts geladen, nicht mit dem Quellcode ausgeliefert. Ohne Netzverbindung verwendet die App Systemschriften. Ihre jeweiligen Schriftlizenzen bleiben unabhängig von der Projektlizenz.

## Backend

FastAPI, Uvicorn, Bleak, dbus-next, HTTPX und pytest werden über [requirements.txt](bike/requirements.txt) installiert. Ihre vollständigen Lizenztexte und die ihrer transitiven Abhängigkeiten stehen in den installierten Distributionen. Für eine Weitergabe gebündelter Umgebungen müssen diese Hinweise mitgeführt werden.

## Garmin-TCX-Schema

Das externe `TrainingCenterDatabasev2.xsd` wird nicht unter MIT gestellt und nicht im öffentlichen Repository oder in den Source-Releases mitgeliefert. Für den optionalen Validierungstest kann es separat von [Garmins Originalquelle](https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd) bezogen werden; Anleitung unter [Tests](docs/TESTING.md). Ohne lokale Schema-Datei oder lxml wird nur dieser zusätzliche Test übersprungen.

## Protokoll- und Trainingsreferenzen

Die Daum-Implementierung nutzt öffentlich dokumentierte Protokollbeschreibungen; aus [incyclist/devices](https://github.com/incyclist/devices) wurde kein Quellcode übernommen. Trainingsreferenzen sind in der [technischen Dokumentation](bike/README.md#quellen) verlinkt. Verlinkte Inhalte werden durch die Projektlizenz nicht umgelizenziert.

Raspberry Pi, Daum, Garmin, Apple und Zwift werden zur Beschreibung der verwendeten Hardware und Schnittstellen genannt. Das Projekt ist unabhängig und keine offizielle Anwendung dieser Hersteller.
