# Geographic example data

The JSON route coordinates, node identifiers and way identifiers in this directory
are derived from OpenStreetMap and are made available under the
[Open Data Commons Open Database License 1.0 (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/).
© OpenStreetMap contributors. See [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).
These data files are excluded from any different code license of the surrounding repository.

Elevation values were obtained from the Bayerische Vermessungsverwaltung's public
Höhendienst and are available under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Required credit: **Geobasisdaten: Bayerische Vermessungsverwaltung –
www.geodaten.bayern.de (Daten verändert), Lizenz: CC BY 4.0**.
The modification consists of selecting coordinate-height results and associating
them with the route points. No endorsement by either data provider is implied.
The elevation source uses DGM1 and the vertical reference DHHN2016; these are terrain
heights, which need not coincide with the ridden surface, particularly on bridges.

`index.json` records source URLs, retrieval date, content checksums and attribution.
Each route's `provenance` also records source-response SHA-256 hashes, OSM object
versions/timestamps, every original node and segment way ID, and the height request
and response hashes. The download/rebuild script is `bike/deploy/fetch-route-material.py`.

The examples serve indoor visualization. They are not verified outdoor navigation
routes; directional access, turn restrictions, temporary closures and suitability
are not verified. No artificial edge closes a gap in the source data.
