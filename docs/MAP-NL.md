# Detailed maps for the Netherlands: a working province builder

Streets, named places, help points and every street address of a Dutch province, for any of the twelve and for all of
them at once, Wadden islands included, built from redistributable sources by one command and kept in its own folder. It follows the shape of [REGIONS-DE.md](REGIONS-DE.md) and
[MAP-DE-BE.md](MAP-DE-BE.md) and the file formats in [MAPS.md](MAPS.md). The builder is
[`tools/build_region_nl.py`](../tools/build_region_nl.py); its offline test is `app/tests/test_build_region_nl.py`.

This is the data half, as for Berlin: a builder, a map set that passes its own checks, and an address index with its
normalisation scheme recorded. Searching the index the Dutch way in the app, and offering a province in Setup, is the
runtime half that the region issues (#25, #31, #79) still have open.

**How things were checked.** On 25 November 2026, by opening the pages named below. Marks as in REGIONS-DE.md:
**opened** (the page itself was read) or **search only** (seen in a search result from the publisher's own site).

## What a region is

One province, ID `NL-<code>` (ISO 3166-2:NL): `NL-ZH` for Zuid-Holland, `NL-NH` for Noord-Holland and so on. The
hyphen keeps them apart from US state codes, as for `DE-BE`. A province is a sensible unit: the twelve range from about
180,000 addresses (Flevoland) to about two million (Zuid-Holland), the size of a US state map, and Geofabrik cuts its
OpenStreetMap extracts by province.

## Build it

```sh
python3 tools/build_region_nl.py fetch --province ZH   # OpenStreetMap from Geofabrik, addresses from the BAG (resumes)
python3 tools/build_region_nl.py build --province ZH   # builds beside the last build, replaces data/ once it passes check
python3 tools/build_region_nl.py check --province ZH   # validates it; exits non-zero on any failure
python3 tools/build_region_nl.py demo  --province ZH   # adds an empty library beside it for trying the map alone
python3 server.py --data derived/regions/NL-ZH/demo --no-index
```

`--province all` runs a step for the twelve provinces in turn; a province that fails is reported at the end and does
not stop the others. Python 3.9 or newer and its standard library; no GDAL.

How fetch asks for the BAG: first each province's official boundary (Kadaster, BRK Bestuurlijke Gebieden via PDOK,
CC BY 4.0), only to take its box, islands included; the boxes are kept in `derived/regions/NL-shared/provinces.json`,
and a province the service does not answer for keeps a fallback box written in the builder. Then the BAG, through
PDOK's OGC API, in cells of 0.05° on one grid for the whole country, with the service's own paging. A cell holds every
address in it, whatever its province, and is kept in `NL-shared/bag-tiles/`, so a border area fetched for one province
is not asked for again by its neighbour, and a stopped fetch picks up at the first unfinished cell. build keeps the
records of the province it builds.

PDOK answers some pages deep into a busy cell with HTTP 500, and the same page again when asked hours later (seen on
25 and 26 November 2026, in ten of the twelve provinces). So a cell that keeps getting a 500 is split in four and each
quarter asked on its own, down to boxes of about 200 m. A box that still fails is a hole: the cell keeps everything
else, the hole is listed beside it (`<cell>.holes.json`) and in `fetched.json`, check reports the count, and the next
fetch asks for the holes only. A network failure is not split; nor is a run in which 60 pages in a row fail, which stops
asking and says to try later. A repeated fetch reuses an OpenStreetMap extract younger than a week (`--refresh`
downloads it again).

## The first full build (26 November 2026)

All twelve provinces, from Geofabrik's extracts of 24 November 2026 and the BAG as PDOK served it on 25 and 26
November; every check passed, with no BAG box left out.

| Province | Addresses | without postcode | Ferry terminals | Points dropped | Size |
|---|---:|---:|---:|---:|---:|
| NL-GR Groningen | 379,059 | 19,103 | 33 | 0 | 174 MB |
| NL-FR Fryslân | 415,126 | 16,596 | 95 | 0 | 259 MB |
| NL-DR Drenthe | 299,633 | 12,734 | 18 | 0 | 178 MB |
| NL-OV Overijssel | 691,268 | 27,637 | 54 | 0 | 348 MB |
| NL-FL Flevoland | 238,815 | 5,914 | 25 | 0 | 117 MB |
| NL-GE Gelderland | 1,250,394 | 44,040 | 143 | 5 | 590 MB |
| NL-UT Utrecht | 801,372 | 28,221 | 98 | 2 | 324 MB |
| NL-NH Noord-Holland | 1,879,854 | 76,885 | 207 | 3 | 669 MB |
| NL-ZH Zuid-Holland | 2,293,923 | 91,506 | 199 | 9 | 793 MB |
| NL-ZE Zeeland | 291,893 | 21,836 | 53 | 0 | 143 MB |
| NL-NB Noord-Brabant | 1,556,918 | 77,905 | 78 | 0 | 692 MB |
| NL-LI Limburg | 700,384 | 31,531 | 46 | 4 | 315 MB |
| **Netherlands** | **10,798,639** | **453,908** | | | **about 4.5 GB** |

The islands: Texel 15,615 addresses and 8 ferry terminals; Vlieland 1,654 and 3; Terschelling 5,391 and 5; Ameland
4,939 and 6; Schiermonnikoog 1,748 and 1. Fetching took most of a day, nearly all of it in the densest cells of the
Randstad, where PDOK's 500s made the builder split cells; building all twelve took about eight minutes on a Mac mini.
"Points dropped" are points of the extract beyond the province, such as the Newcastle end of the IJmuiden ferry.
No address had a postcode in another form than 1234AB.

## Sources, layer by layer

| Layer (file) | Source | Publisher | Licence | Checked |
|---|---|---|---|---|
| Streets, water, land use, buildings, named places, help points (`national.sqlite`) | OpenStreetMap, Geofabrik province extract `<province>-latest-free.gpkg.zip` | OSM contributors, Geofabrik | ODbL 1.0 | Geofabrik's Netherlands page: opened (12 provinces listed) |
| Street addresses (`addresses/NL-<code>.sqlite`) | Basisregistratie Adressen en Gebouwen (BAG), PDOK OGC API Features, collection `adres` | Kadaster | Public Domain Mark 1.0 (the API); CC0 1.0 (the BAG downloads); "Publiek domein" on data.overheid.nl | collections and an items page: opened; licence on data.overheid.nl: search only |
| Places, municipalities, postcodes, streets (`places.sqlite`) | Derived from the BAG addresses, plus named OSM places and points | Kadaster; OSM contributors | as above | |
| Province boxes (not shipped) | BRK Bestuurlijke Gebieden, collection `provinciegebied` | Kadaster | CC BY 4.0 | collections: opened; items: opened (`naam`, CBS `code`, MultiPolygon) |

What one BAG `adres` record holds (opened: an items page for Delft): street name (`openbare_ruimte_naam`), house number,
letter and addition (`huisnummer`, `huisletter`, `toevoeging`), postcode, place (`woonplaats_naam`), municipality
(`bronhouder_naam`), province (`provincie_naam`, `provincie_afkorting`) and a point in WGS 84. The API filters by box;
`provincie_naam` is listed as queryable, but a filtered request failed when tried, so the builder asks by box and keeps
the records whose `provincie_afkorting` is the province's.

## The Wadden islands

They belong to their provinces, in the BAG as in Geofabrik's extracts: Texel to `NL-NH`; Vlieland, Terschelling,
Ameland and Schiermonnikoog to `NL-FR` (each its own municipality); Rottumeroog and Rottumerplaat, uninhabited and
without addresses, to `NL-GR`. Because they lie far from the mainland, a box or an extract that misses one would still
look like a whole province, so check asks for each inhabited island, inside a box around it (`ISLANDS` in the
builder): at least 20 drawn streets, at least 100 addresses of its municipality, the municipality in the place finder,
and a sample address in its main village. Ferry terminals, the islands' link to the mainland, are added to the help
points from OpenStreetMap's transport layer (`tools/build_map.py` keeps no transport points); check reports how many
lie on each island but does not fail on none, since that depends on OpenStreetMap's tagging there.

## How the provinces are told apart

Each BAG address names its province. Checked on 25 November 2026 with one address per province: the code is `ZH`,
`NH` and `NB` but `Gr`, `Fr`, `Dr`, `Ov`, `Fl`, `Ge`, `Ut`, `Ze` and `Li`, and Friesland's name is `Fryslân`; so the
builder compares codes without case and names without accents. Those addresses, and one on each inhabited island, are
the samples check looks up (`SAMPLE_ADDRESSES`).

## How addresses are written

`<street> <number><letter>-<addition>, <postcode> <place>`: "Rotterdamseweg 374A, 2629 HG Delft". Postcodes are four
digits (never starting with 0) and two capital letters; the index stores them without the space. Some BAG addresses have
no postcode at all: outbuildings with an addition such as "ts" or "gs" ("Pieperij 5-ts"), caravan pitches and berths,
which PostNL does not deliver to; about 4% in Drenthe, 7% in Zeeland (built 26 November 2026). They are kept with an
empty postcode and check reports them; a postcode that is there but is not "1234AB" fails. Scheme `nl-1`, stored
in the `norm` column and in the index's `meta`: lower case, accents off ("Ruïnelaan" → "ruinelaan"), punctuation to
spaces, and a word ending in "straat" shortened to "str" ("Burg. Jansenstraat" → "burg jansenstr"), so "Kanaalstr" finds
"Kanaalstraat" the way the Berlin scheme folds "Straße". The postcode has an index of its own (`zip, num`), because
"2628 CD 2" is how many people give an address.

## What this build does not have yet

- **Official help points.** Hospitals, pharmacies, fire and police stations come from OpenStreetMap only. No national,
  openly licensed list of these was found to replace them the way Berlin's Geoportal does; this is worth a second look.
- **AEDs.** `tools/build_map.py` keeps no defibrillator class, so AEDs mapped in OpenStreetMap are not on this map, and
  whether the national AED register can be reused was not checked.
- **Terrain, crops and building heights.** AHN (elevation), BRP Gewaspercelen (crops) and 3D BAG are candidates for these
  layers; their licences were not checked here and none is wired in yet.
- **The runtime.** The app does not yet offer a province in Setup or search `nl-1` keys; see Berlin's note on the same.
