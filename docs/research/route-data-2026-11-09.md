# Reales Streckenmaterial – 09.11.2026

Zwei tatsächlich heruntergeladene, offline mitgelieferte Rundkurse stehen unter
`bike/data/routes/`. Alle 1813 Punkte stammen unverändert aus OSM-Knoten; alle
1813 Höhenwerte lieferte der amtliche Bayerische Höhendienst. Es wurden keine
Streckenpunkte, Schließkanten oder Höhen erfunden. Die Daten dienen der
Indoor-Visualisierung, ohne automatische Widerstandssteuerung.

| Datensatz | Linie | Punkte | Amtliche Geländehöhen |
| --- | ---: | ---: | --- |
| Grafrath – Ampermoos | 7,385 km | 185 | 534,2–554,7 m |
| Rund um den Ammersee | 45,997 km | 1628 | 533,0–606,7 m |

## OSM-Geometrie und tatsächlicher Ringschluss

Die [OSM-Lizenzseite](https://www.openstreetmap.org/copyright) gestattet Weitergabe
und Bearbeitung unter ODbL mit Namensnennung und Weitergabe unter derselben
Datenlizenz. Der Hinweis und direkte Lizenzlink liegen in `LICENSE.md`, Index und
Datensätzen. Die Daten stehen separat von der Code-Lizenz des Projekts.

Für die kurze Runde wurden die vollständigen OSM-Relationen
[6795968](https://www.openstreetmap.org/relation/6795968),
[6805329](https://www.openstreetmap.org/relation/6805329),
[13235623](https://www.openstreetmap.org/relation/13235623),
[6332283](https://www.openstreetmap.org/relation/6332283),
[6424952](https://www.openstreetmap.org/relation/6424952) und
[2871713](https://www.openstreetmap.org/relation/2871713) über die offizielle
OSM-API geladen. Aus ihrem verbundenen Weggraph wird deterministisch die längste
einfache DFS-Grundschleife ausgewählt; der Name beschreibt unsere Auswahl, keine
Behauptung einer amtlich ausgeschilderten Rundroute.

Die [Relation 551290](https://www.openstreetmap.org/relation/551290) beschreibt die
Ammerseerunde. Allein bildet sie derzeit keinen durchgehenden großen Ring: bei
Fischen enden zwei Abschnitte ohne gemeinsame OSM-Verbindung. Statt die rund
14 m entfernten Endpunkte willkürlich zu verbinden, ergänzt das Werkzeug den
offiziellen [OSM-Kartenausschnitt bei Fischen](https://api.openstreetmap.org/api/0.6/map?bbox=11.147,47.944,11.153,47.949).
Der ausgewählte vollständige Ring nutzt ausschließlich dort bereits kartierte,
an echten Knoten verbundene Wege einschließlich eines Straßenabschnitts.
Manche kleine Seitenrunden oder Sackgassen der Relation werden dadurch nicht
übernommen. Es erfolgt keine Glättung, Resampling oder künstliche Schließung.
Punkte und Segment-Wegkennungen sind vollständig im `provenance` dokumentiert.

Offenkundig für Radfahrer gesperrte/private Wege, Treppen und Autobahn-/Schnellstraßen
werden beim Extrahieren verworfen. Das Werkzeug ist dennoch kein vollständiger
Fahrrad-Router: Einbahnrichtungen, Abbiegebeschränkungen, saisonale Sperrungen und
die tatsächliche Befahrbarkeit wurden nicht verifiziert. Die Beispiele daher nicht
als geprüfte Außenrouten oder identisch mit aktuellen touristischen GPX vermarkten.

## Amtliche Höhen ohne Schlüssel oder großen Rasterdownload

Der [Bayerische Höhendienst](https://geodatenonline.bayern.de/geodatenonline/seiten/dienste/rest_hoehe.html)
benötigt keine Authentifizierung und erlaubt GET für Einzelkoordinaten sowie POST
für Listen. Die tatsächlich abgerufene [OpenAPI-Beschreibung](https://geoservices.bayern.de/bvvapi/od/hoehen/openapi.json)
dokumentiert maximal 4000 Punkte pro Anfrage, EPSG:4326 mit Länge/Breite,
unveränderte Punktreihenfolge, `null` bei nicht bestimmbarer Höhe und DHHN2016 als
Höhenbezugssystem. Ihr HTML-Beispiel benennt DGM1 als Berechnungsgrundlage.

Verwendet wurde `POST https://geoservices.bayern.de/bvvapi/od/hoehen/v1/elevation/list`
mit `{"srid":4326,"coords":[[Länge,Breite],...]}`. Eine Sammelanfrage mit allen
1813 Punkten lieferte bei der Prüfung HTTP 500. Aufeinanderfolgende Pakete mit
höchstens 150 Punkten waren erfolgreich. Rückgaben werden auf Punktzahl,
Koordinatenposition und endliche Höhenwerte geprüft. Fehlende Höhe bleibt `null`.
Die Ergebniswerte sind Geländehöhen; Brücken oder Straßenaufbauten können davon
abweichen. Abtastung und Messauflösung dürfen nicht mit Vermessungsgenauigkeit
jedes OSM-Straßenpunkts verwechselt werden.

Die amtlichen [OpenData-Nutzungsbedingungen](https://www.geodaten.bayern.de/odd/m/3/html/nutzungsbedingungen.html)
erlauben Weitergabe/Bearbeitung unter CC BY 4.0. Die geforderte Namensnennung,
Lizenz-URL und Angabe der Datenveränderung sind in den Dateien enthalten. Es
wird kein kostenpflichtiger Dienst und kein privater API-Schlüssel benötigt.

Als Alternativen wurden [Bayerns DGM5-Download](https://geodaten.bayern.de/opengeodata/OpenDataDetail.html?pn=dgm5)
(CC BY 4.0, 1-km-Kacheln, UTM32) und die öffentlichen
[AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) untersucht.
Für letztere sind [Terrarium-Format](https://github.com/tilezen/joerd/blob/master/docs/formats.md)
und [quellenabhängige Attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
dokumentiert. Für diese Lieferung sind sie nicht erforderlich; keine fremden
Rasterkacheln oder ungeprüfte Tourismus-GPX werden ins Repository aufgenommen.

## Wiederholen und prüfen

Ab Repository-Wurzel, mit Python 3.11+ ohne weitere Bibliotheken:

```powershell
python bike/deploy/fetch-route-material.py
python bike/deploy/fetch-route-material.py --offline
python bike/deploy/fetch-route-material.py --refresh
```

Der Standardlauf verwendet vorhandene Antworten im ignorierten Ordner
`.cache/fitness-material/`; `--offline` verbietet neue Downloads, `--refresh`
fordert diese ausdrücklich neu an. Eine spätere OSM-Änderung kann die gewählte
Linie verändern; Plausibilitätsgrenzen verhindern eine unbemerkte völlig andere
Rundenlänge. Ein neuer Lauf schreibt neue Abrufzeit und Inhaltsprüfsummen.
Der Backend-Loader `routes_material.library()`/`load_route(id)` lädt nur lokale
Dateien. Er prüft Dateipfade, SHA-256, Metadaten, Punktzahl und Zahlenwerte.
Import in den persönlichen Katalog bleibt eine gesonderte Benutzeraktion.

Gezielte Tests:

```powershell
cd bike
.venv/Scripts/python.exe -m pytest tests/test_route_material.py tests/test_routes.py -q
```

Die Tests prüfen die beiden realen Linien, Ringschluss, Distanz, Höhen/Lizenzen,
Kompatibilität mit der vorhandenen RouteInput-Grenze, Offlinebetrieb,
Prüfsummenerkennung, Pfadmanipulation, ungültige Zahlen, fehlende Höhen und die
Ablehnung eines nur scheinbar geschlossenen Wegs. Eine zusätzliche lokale Prüfung
vergleicht jeden gebündelten Punkt und jede Kante mit den heruntergeladenen
OSM-Antworten. Es erfolgt kein Hardwarezugriff und keine automatische Sitzung.

Prüfergebnis am 09.11.2026: **17 Tests bestanden** (13 neue Materialtests und
4 bestehende Importtests). Alle 1813 Koordinaten und 1811 Wegkanten wurden
zusätzlich exakt gegen die heruntergeladenen OSM-Quellen geprüft. Die einzige
Testwarnung betrifft die bereits verwendete FastAPI/Starlette-Testclient-Abhängigkeit.
