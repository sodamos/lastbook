#!/usr/bin/env python3
"""A Dutch province (NL-ZH, NL-FR, ...): a self-contained offline map set with places, help points and street addresses.

  python3 tools/build_region_nl.py fetch --province ZH   # downloads the sources (resumes where it stopped)
  python3 tools/build_region_nl.py build --province ZH   # writes derived/regions/NL-ZH/data/ once it passes check
  python3 tools/build_region_nl.py check --province ZH   # validates it; exits non-zero on any failure
  python3 tools/build_region_nl.py demo  --province ZH   # adds an empty library beside it, then prints the command below
  python3 server.py --data derived/regions/NL-ZH/demo --no-index   # the map and the place finder, offline

--province all runs a step for all twelve provinces in turn. The Wadden islands are in their provinces, as they are
in the BAG and in Geofabrik's extracts: Texel in NL-NH; Vlieland, Terschelling, Ameland and Schiermonnikoog in NL-FR;
Rottumeroog and Rottumerplaat (uninhabited, no addresses) in NL-GR. check makes sure each inhabited island has its
streets and addresses (ISLANDS below).

Everything goes under derived/regions/NL-<code>/, so no other map set is touched; the BAG tiles and the province boxes
are kept once for all provinces under derived/regions/NL-shared/, so a border area is asked for only once. Plan, sources and what this build lacks: docs/MAP-NL.md. It follows tools/build_region_de_be.py and runs
tools/build_map.py unchanged; it imports nothing from engine/ or server.py. Searching the address index the Dutch way
(scheme nl-1 below) is runtime work, the same open question as for Berlin (#79, #31).

Sources (dates and checksums end up in derived/regions/NL-<code>/data/build.json):
  - OpenStreetMap via Geofabrik, <province>-latest-free.gpkg.zip: streets, water, land use, buildings, named places
    and points, help points included (ODbL 1.0, "© OpenStreetMap contributors").
  - Basisregistratie Adressen en Gebouwen (BAG), Kadaster, through the PDOK OGC API Features service (collection
    "adres"): every address with street, house number, letter, addition, postcode, place and municipality. Public
    domain (the service states the Public Domain Mark 1.0; the BAG downloads CC0 1.0). No attribution duty.
  - The provinces' boundaries (Kadaster, BRK Bestuurlijke Gebieden via PDOK, CC BY 4.0), used to know which box of the
    BAG to ask for, so an island far out in the Wadden Sea is not missed, and to label OpenStreetMap places by the
    province that really holds them: Geofabrik's extract for Noord-Brabant takes in Baarle-Hertog's Belgian enclaves.
    Nothing of them ships.

  python3 tools/build_region_nl.py outline --province all   # labels a built map's OpenStreetMap places by the official
                                                            # outlines and records how each source was cut; no rebuild

The fetch step needs the network and resumes where it stopped (each finished tile of the BAG is kept); build and check
do not. Python 3.9+ standard library only.
"""
import argparse
import concurrent.futures
import datetime
import gzip
import http.client
import json
import math
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_region_de_be as de  # noqa: E402  (point and GeoPackage helpers, shared with Berlin)

# code -> (name as the BAG and the boundary service write it, Geofabrik file name, CBS province code, box W, S, E, N).
# The box is a fallback: fetch takes each province's box from its official boundary (BOUNDARIES) and keeps it in
# NL-shared/provinces.json. Every BAG address says its own province, and only those of the province being built are kept.
PROVINCES = {
    'GR': ('Groningen', 'groningen', '20', (6.12, 52.80, 7.28, 53.60)),
    'FR': ('Fryslân', 'friesland', '21', (4.80, 52.76, 6.48, 53.56)),
    'DR': ('Drenthe', 'drenthe', '22', (6.06, 52.56, 7.15, 53.26)),
    'OV': ('Overijssel', 'overijssel', '23', (5.74, 52.03, 7.13, 52.88)),
    'FL': ('Flevoland', 'flevoland', '24', (5.07, 52.20, 6.07, 52.92)),
    'GE': ('Gelderland', 'gelderland', '25', (4.95, 51.68, 6.88, 52.58)),
    'UT': ('Utrecht', 'utrecht', '26', (4.74, 51.87, 5.68, 52.36)),
    'NH': ('Noord-Holland', 'noord-holland', '27', (4.44, 52.11, 5.38, 53.24)),
    'ZH': ('Zuid-Holland', 'zuid-holland', '28', (3.78, 51.63, 5.05, 52.38)),
    'ZE': ('Zeeland', 'zeeland', '29', (3.31, 51.15, 4.35, 51.83)),
    'NB': ('Noord-Brabant', 'noord-brabant', '30', (4.13, 51.16, 6.09, 51.88)),
    'LI': ('Limburg', 'limburg', '31', (5.51, 50.70, 6.28, 51.83)),
}
# The inhabited Wadden islands, by province: (municipality as the BAG names it, a box around the island). check wants
# streets and addresses on each, so an island lost from a box or an extract is noticed.
ISLANDS = {
    'NH': [('Texel', (4.70, 52.98, 4.93, 53.19))],
    'FR': [('Vlieland', (4.86, 53.21, 5.13, 53.32)), ('Terschelling', (5.10, 53.33, 5.61, 53.47)),
           ('Ameland', (5.59, 53.41, 5.95, 53.51)), ('Schiermonnikoog', (6.07, 53.45, 6.35, 53.52))],
}
# Another country's ground inside a province: Geofabrik's extract takes it in, the BAG does not (it holds Dutch
# addresses only). check wants each place named here labelled as outside the province in the place finder, so a
# Belgian village is not offered as one in Noord-Brabant. (place as OpenStreetMap names it, country)
EXCLAVES = {
    'NB': [('Baarle-Hertog', 'Belgium')],
}
SHARED = ROOT / 'derived' / 'regions' / 'NL-shared'
BOUNDARIES = 'https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1/collections/provinciegebied/items'
BOUNDARY_LICENCE = 'CC BY 4.0 (Kadaster, BRK Bestuurlijke Gebieden)'
OUTSIDE = 'outside the Dutch provinces'   # how the place finder labels an OpenStreetMap place that no province holds
OUTLINE_BAND = 0.01  # degrees: an outline's edges are kept by band of latitude, so a point test reads a few hundred
MARGIN = 0.01        # degrees around a province's official box
POINT_MARGIN = 0.15  # degrees: points of the extract further out than this from the box are another map's
GEOFABRIK = 'https://download.geofabrik.de/europe/netherlands/{slug}-latest-free.gpkg.zip'
# Geofabrik added GeoPackages to its server in April 2026; if the "-free" name is gone, the newer name is tried.
GEOFABRIK_ALT = 'https://download.geofabrik.de/europe/netherlands/{slug}-latest.gpkg.zip'
BAG_API = 'https://api.pdok.nl/kadaster/bag/ogc/v2/collections/adres/items'
BAG_LICENCE = 'Public domain (PDOK: Public Domain Mark 1.0; BAG downloads: CC0 1.0)'
TILE = 0.05          # degrees, on one grid for the whole country; a city tile holds tens of thousands of addresses
PAGE = 1000
WORKERS = 6          # parallel cells; PDOK is a public service, so keep this modest
TRIES, TRIES_SPLIT = 5, 3   # asks of one page before a box is split (fetch_box): about 30 s for a cell, 3 s for a quarter
SPLIT_DEPTH = 4      # 0.05 degrees halved four times: a box of about 200 m
OSM_MAX_AGE = 7      # days a downloaded extract is used again by a repeated fetch (--refresh: always download)
NORM = 'nl-1'

# Filled in by select(): the province this run builds.
CODE = REGION = NAME = SLUG = None
REFRESH = False      # --refresh
BBOX = None
BASE = SOURCE = DATA = None


def select(code):
    global CODE, REGION, NAME, SLUG, BBOX, BASE, SOURCE, DATA
    code = code.upper().removeprefix('NL-')
    if code not in PROVINCES:
        raise SystemExit(f'unknown province {code!r}; one of: {", ".join(PROVINCES)} or all')
    CODE, REGION = code, f'NL-{code}'
    NAME, SLUG = PROVINCES[code][:2]
    BBOX = box_for(code)
    BASE = ROOT / 'derived' / 'regions' / REGION
    SOURCE, DATA = BASE / 'source', BASE / 'data'


def box_for(code):
    """The province's official box from NL-shared/provinces.json (written by fetch), widened by MARGIN; the fallback
    box in PROVINCES while there is none."""
    try:
        found = json.loads((SHARED / 'provinces.json').read_text(encoding='utf-8'))['boxes'][code]
        w, s, e, n = found
        return (round(w - MARGIN, 4), round(s - MARGIN, 4), round(e + MARGIN, 4), round(n + MARGIN, 4))
    except (OSError, ValueError, KeyError, TypeError):
        return PROVINCES[code][3]


def fold(text):
    """Lower case without accents: 'Fryslân', 'Fryslan' and 'FRYSLÂN' are one name."""
    text = unicodedata.normalize('NFKD', str(text or '')).lower()
    return ''.join(c for c in text if not unicodedata.combining(c)).strip()


def in_province(row, code=None, name=None):
    """Does a BAG row belong to this province? The service writes the code as 'ZH', 'NH', 'NB' but 'Fr', 'Gr', 'Ut'
    (checked on 25 November 2026), so the code is compared without case, and the name without accents."""
    code, name = code or CODE, name or NAME
    return str(row.get('prov') or '').upper() == code or (fold(row.get('prov_name')) == fold(name) and bool(name))


def normalize_nl(text):
    """Scheme 'nl-1', stored in the index's norm column: 'Burg. Jansenstraat' -> 'burg jansenstr', 'Ruïnelaan' ->
    'ruinelaan', "'s-Gravenhage" -> 's gravenhage'. A search over this index folds the query with the same rule; the
    rule is recorded as meta norm = nl-1."""
    text = unicodedata.normalize('NFKD', str(text)).lower().replace('’', "'")
    text = ''.join(c for c in text if not unicodedata.combining(c))
    words = re.sub(r'[^a-z0-9 ]+', ' ', text).split()
    return ' '.join(w[:-len('straat')] + 'str' if w.endswith('straat') and len(w) > len('straat') else w for w in words)


def house(number, letter=None, addition=None):
    """'12', '12A', '12-3', '12A-bis': the BAG's house number, letter and addition, written as on a letter."""
    number = str(number or '').strip().lstrip('0')
    if not number:
        return ''
    out = number + (letter or '').strip().upper()
    addition = (addition or '').strip()
    return f'{out}-{addition}' if addition else out


def postcode(code):
    """'2628 cd' -> '2628CD'; '' for anything that is not a Dutch postcode."""
    code = re.sub(r'\s+', '', str(code or '')).upper()
    return code if re.fullmatch(r'[1-9][0-9]{3}[A-Z]{2}', code) else ''


def log(*args):
    print(time.strftime('%H:%M:%S'), *args, flush=True)


# ------------------------------------------------------------------ fetch ----

class ServerError(SystemExit):
    """A page the service answered with HTTP 5xx every time it was asked: fetch_box splits the box around it."""


FAILS = {'in_a_row': 0}
FAILS_LOCK = threading.Lock()
GIVE_UP = 60         # failed pages in a row, across all cells: the service is down, so stop asking and try later


def get_json(url, tries=8):
    """A JSON answer, asked again after a busy or broken reply: up to `tries` times, waiting 1, 2, 4 ... seconds (at
    most a minute) in between. A page that keeps getting HTTP 5xx raises ServerError; a network that keeps failing,
    or GIVE_UP failed pages in a row anywhere, raises SystemExit, so a whole outage is not split into thousands of asks."""
    if FAILS['in_a_row'] >= GIVE_UP:
        raise SystemExit(f'{GIVE_UP} BAG pages in a row failed; PDOK seems to be down, run fetch again later')
    failure, server = None, False
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'lastbook-region-builder', 'Accept': 'application/geo+json'})
            with urllib.request.urlopen(request, timeout=120) as response:
                answer = json.loads(response.read())
            with FAILS_LOCK:
                FAILS['in_a_row'] = 0
            return answer
        except urllib.error.HTTPError as error:
            if error.code < 500 and error.code != 429:
                raise
            failure, server = error, error.code >= 500
        # a dropped connection, a timeout, an answer cut short (IncompleteRead) or cut-off JSON
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as error:
            failure, server = error, False
        if attempt < tries - 1:
            time.sleep(min(60, 2 ** attempt))
    with FAILS_LOCK:
        FAILS['in_a_row'] += 1
    message = f'{url}: {failure}; run fetch again, finished cells are kept'
    raise ServerError(message) if server else SystemExit(message)


def try_cell(cell):
    """fetch_tile, but a cell that keeps failing is reported, not fatal: the other cells go on, and the next fetch
    asks only for the cells still missing."""
    try:
        return fetch_tile(cell)
    except SystemExit as error:
        log('cell', cell, 'not fetched:', error)
        return None, None


def download(url, path):
    """Streams url to path; returns the address it ended at (Geofabrik's 'latest' redirects to the dated file)."""
    request = urllib.request.Request(url, headers={'User-Agent': 'lastbook-region-builder'})
    part = path.with_suffix(path.suffix + '.part')
    with urllib.request.urlopen(request, timeout=300) as response, open(part, 'wb') as out:
        final = response.geturl()
        shutil.copyfileobj(response, out, 1 << 22)
    part.replace(path)
    return final


def geometry_box(geometry):
    """(W, S, E, N) of a GeoJSON Polygon or MultiPolygon, islands included."""
    xs, ys = [], []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for part in c:
                walk(part)
    walk(geometry['coordinates'])
    return (min(xs), min(ys), max(xs), max(ys))


def boundaries():
    """(the service's answer, {code: GeoJSON geometry}) for the provinces' official boundaries."""
    page = get_json(BOUNDARIES + '?' + urllib.parse.urlencode({'f': 'json', 'limit': 50}))
    by_name = {fold(v[0]): k for k, v in PROVINCES.items()}
    by_cbs = {v[2]: k for k, v in PROVINCES.items()}
    found = {}
    for f in page.get('features', []):
        p = f.get('properties') or {}
        code = by_name.get(fold(p.get('naam'))) or by_cbs.get(str(p.get('code') or '').lstrip('PV'))
        if code and f.get('geometry'):
            found[code] = f['geometry']
    return page, found


def save_outlines(page, found):
    """The outlines themselves, kept in NL-shared/outlines.json for labelling places (they do not ship)."""
    (SHARED / 'outlines.json').write_text(json.dumps({
        'source': BOUNDARIES, 'licence': BOUNDARY_LICENCE, 'served_at': page.get('timeStamp'),
        'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'outlines': found}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    OUTLINES.clear()


def fetch_outlines():
    """The official outlines on their own, without touching the boxes the BAG cells were fetched by."""
    SHARED.mkdir(parents=True, exist_ok=True)
    page, found = boundaries()
    if sorted(found) != sorted(PROVINCES):
        raise SystemExit(f'province outlines: the service answered for {len(found)} of 12 provinces; try again later')
    save_outlines(page, found)
    log('province outlines:', len(found), 'official')


def fetch_boxes():
    """Each province's box from its official boundary, kept in NL-shared/provinces.json, and the outlines in
    NL-shared/outlines.json. A province the service does not answer for keeps its fallback box, and the file says so."""
    SHARED.mkdir(parents=True, exist_ok=True)
    page, found = boundaries()
    boxes = {code: [round(v, 5) for v in geometry_box(geometry)] for code, geometry in found.items()}
    if found:
        save_outlines(page, found)
    missing = sorted(set(PROVINCES) - set(boxes))
    (SHARED / 'provinces.json').write_text(json.dumps({
        'source': BOUNDARIES, 'licence': BOUNDARY_LICENCE, 'served_at': page.get('timeStamp'),
        'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'boxes': boxes, 'fallback_for': missing}, indent=1, ensure_ascii=False), encoding='utf-8')
    log('province boxes:', len(boxes), 'official' + (f', fallback for {", ".join(missing)}' if missing else ''))


class Outline:
    """A province's official outline, for telling whether a point lies in it. The even-odd rule over all its rings
    takes in the islands and leaves out the holes, such as Baarle-Hertog's Belgian enclaves in Baarle-Nassau. The
    edges are kept by band of latitude, so a test reads only the edges a ray at that latitude can cross."""

    def __init__(self, geometry):
        self.box = geometry_box(geometry)
        polygons = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
        self.bands = {}
        for polygon in polygons:
            for ring in polygon:
                for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:] + ring[:1]):
                    if y1 == y2:
                        continue
                    edge = (x1, y1, x2, y2)
                    for band in range(math.floor(min(y1, y2) / OUTLINE_BAND), math.floor(max(y1, y2) / OUTLINE_BAND) + 1):
                        self.bands.setdefault(band, []).append(edge)

    def __contains__(self, point):
        x, y = point
        west, south, east, north = self.box
        if not (west <= x <= east and south <= y <= north):
            return False
        inside = False
        for x1, y1, x2, y2 in self.bands.get(math.floor(y / OUTLINE_BAND), ()):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside


OUTLINES = {}        # code: Outline, read once from NL-shared/outlines.json


def load_outlines():
    """{code: Outline} from NL-shared/outlines.json (written by fetch and by outline); {} when it is not there."""
    path = SHARED / 'outlines.json'
    if OUTLINES.get('_path') != str(path):
        OUTLINES.clear()
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        OUTLINES.update({code: Outline(geometry) for code, geometry in saved.get('outlines', {}).items()})
        OUTLINES['_about'] = {k: saved.get(k) for k in ('source', 'licence', 'served_at', 'fetched')}
        OUTLINES['_path'] = str(path)
    return {k: v for k, v in OUTLINES.items() if not k.startswith('_')}


def where(lon, lat, outlines=None):
    """The province's name whose official outline holds the point, this province's first; OUTSIDE when none does;
    this province's own name when there are no outlines (an older fetch)."""
    outlines = load_outlines() if outlines is None else outlines
    if not outlines:
        return NAME
    for code in [CODE] + [c for c in outlines if c != CODE]:
        if code in outlines and (lon, lat) in outlines[code]:
            return PROVINCES[code][0]
    return OUTSIDE


def osm_detail(lon, lat, outlines=None):
    """The place finder's detail for an OpenStreetMap row: 'Noord-Brabant (OpenStreetMap)', or for a point across the
    border 'outside the Dutch provinces (OpenStreetMap)'. Geofabrik cuts its extracts by an outline of its own."""
    return f'{where(lon, lat, outlines)} (OpenStreetMap)'


def bag_cut():
    """How the BAG was cut to this province, for build.json: the field, the value it is compared with, and how the
    service wrote it in the first row kept."""
    first = next(addresses(), {})
    return {'by': 'the record\'s own province field, not the box', 'field': 'provincie_afkorting', 'value': CODE,
            'compared': 'without case', 'as_written': first.get('prov'),
            'or_field': 'provincie_naam', 'or_value': NAME, 'or_compared': 'without case or accents',
            'or_as_written': first.get('prov_name'), 'box_used_for': 'which BAG cells to ask for'}


def osm_cut(fetched):
    """How OpenStreetMap was cut, for build.json."""
    osm = (fetched.get('files') or {}).get('osm.gpkg.zip') or {}
    about = (load_outlines() and OUTLINES.get('_about')) or {}
    return {'by': "Geofabrik's own outline of the province (its extract)", 'extract': osm.get('name'),
            'places_labelled_by': ('the official outlines, Kadaster BRK Bestuurlijke Gebieden provinciegebied '
                                   f"(CC BY 4.0, served {about.get('served_at')})") if about else
                                  'this province (no official outlines fetched yet)',
            'outside_label': OUTSIDE,
            'help_points': 'kept as the extract has them: a help point across the border is still one'}


def tiles(box=None):
    """The grid cells (ix, iy) of TILE degrees that cover a box: one grid for the whole country, so two provinces that
    share a border ask for the same cells and the second one finds them done."""
    west, south, east, north = box or BBOX
    return [(ix, iy) for iy in range(math.floor(south / TILE), math.ceil(north / TILE))
            for ix in range(math.floor(west / TILE), math.ceil(east / TILE))]


def tile_box(cell):
    ix, iy = cell
    return (round(ix * TILE, 4), round(iy * TILE, 4), round((ix + 1) * TILE, 4), round((iy + 1) * TILE, 4))


def tile_path(cell):
    return SHARED / 'bag-tiles' / ('%d_%d.ndjson.gz' % cell)


def holes_path(cell):
    return SHARED / 'bag-tiles' / ('%d_%d.holes.json' % cell)


def page_through(box, tries):
    """(rows, timeStamp) for one box, paged with the service's own 'next' links; SystemExit if a page keeps failing."""
    url = BAG_API + '?' + urllib.parse.urlencode({'f': 'json', 'limit': PAGE, 'bbox': ','.join(map(str, box))})
    rows, stamp = [], None
    while url:
        page = get_json(url, tries)
        stamp = stamp or page.get('timeStamp')
        for f in page.get('features', []):
            p = f.get('properties') or {}
            lon, lat = ((f.get('geometry') or {}).get('coordinates') or [None, None])[:2]
            rows.append({'id': p.get('identificatie'), 'street': p.get('openbare_ruimte_naam'), 'number': p.get('huisnummer'),
                         'letter': p.get('huisletter'), 'addition': p.get('toevoeging'), 'postcode': p.get('postcode'),
                         'place': p.get('woonplaats_naam'), 'municipality': p.get('bronhouder_naam'),
                         'prov': p.get('provincie_afkorting'), 'prov_name': p.get('provincie_naam'),
                         'type': p.get('adresseerbaar_object_type'), 'lon': lon, 'lat': lat})
        url = next((link['href'] for link in page.get('links', []) if link.get('rel') == 'next'), None)
    return rows, stamp


def fetch_box(box, depth=0):
    """(rows, timeStamp, holes) for a box. PDOK answers some pages deep into a busy cell with HTTP 500 every time it is
    asked (seen on 25 and 26 November 2026), so a box that keeps failing is split in four and each quarter asked on its
    own, down to SPLIT_DEPTH (a box of about 200 m). One that still fails there is a hole: left out, listed, and asked
    for again by the next fetch."""
    try:
        rows, stamp = page_through(box, TRIES if depth == 0 else TRIES_SPLIT)
        return rows, stamp, []
    except ServerError as error:        # anything else (the network, PDOK down) ends this cell for this fetch
        if depth >= SPLIT_DEPTH:
            log('left out for now:', box, str(error).split(';')[0][-60:])
            return [], None, [list(box)]
    w, s, e, n = box
    mx, my = round((w + e) / 2, 7), round((s + n) / 2, 7)
    rows, stamps, holes = [], [], []
    for quarter in ((w, s, mx, my), (mx, s, e, my), (w, my, mx, n), (mx, my, e, n)):
        r, stamp, h = fetch_box(quarter, depth + 1)
        rows += r
        holes += h
        if stamp:
            stamps.append(stamp)
    return rows, (max(stamps) if stamps else None), holes


def depth_of(box):
    """How many times a box was split from a whole cell (a cell is 0)."""
    return max(0, round(math.log2(TILE / max(box[2] - box[0], 1e-9))))


def fetch_tile(cell):
    """Every address in one grid cell, whatever its province, kept as one JSON line per address. Written under a
    temporary name and renamed when complete, so a stopped fetch redoes only this cell, and a cell already fetched for
    a neighbouring province is not asked for again. A cell with holes (fetch_box) keeps the rows it has; the next fetch
    asks for the holes only and adds what comes back."""
    path, holes_file = tile_path(cell), holes_path(cell)
    if path.exists() and not holes_file.exists():
        return path, None
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        boxes = [tuple(b) for b in json.loads(holes_file.read_text(encoding='utf-8'))['holes']]
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            rows = [json.loads(line) for line in f]
    else:
        boxes, rows = [tile_box(cell)], []
    stamps, holes = [], []
    for box in boxes:
        r, stamp, h = fetch_box(box, depth_of(box))
        rows += r
        holes += h
        if stamp:
            stamps.append(stamp)
    seen, unique = set(), []
    for r in rows:          # quarters share their edges, so an address there came twice
        if r.get('id') not in seen:
            seen.add(r.get('id'))
            unique.append(r)
    part = path.with_name(path.name + '.part')
    with gzip.open(part, 'wt', encoding='utf-8') as out:
        out.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in unique)
    part.replace(path)
    if holes:
        holes_file.write_text(json.dumps({'holes': holes}), encoding='utf-8')
    elif holes_file.exists():
        holes_file.unlink()
    return path, (max(stamps) if stamps else None)


def cell_holes(cells):
    """[(cell, box), ...] still left out in these cells."""
    out = []
    for cell in cells:
        f = holes_path(cell)
        if f.exists():
            out += [(cell, b) for b in json.loads(f.read_text(encoding='utf-8'))['holes']]
    return out


def fetch():
    SOURCE.mkdir(parents=True, exist_ok=True)
    fetched = {'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'files': {}}
    osm, osm_url = SOURCE / 'osm.gpkg.zip', SOURCE / 'osm-url.txt'
    age = (time.time() - osm.stat().st_mtime) / 86400 if osm.exists() and osm_url.exists() else None
    if age is not None and age < OSM_MAX_AGE and not REFRESH:
        final = osm_url.read_text(encoding='utf-8').strip()
        log('Geofabrik: using the extract downloaded', round(age, 1), 'days ago (--refresh downloads it again)')
    else:
        for template in (GEOFABRIK, GEOFABRIK_ALT):
            url = template.format(slug=SLUG)
            log('Geofabrik', url)
            try:
                final = download(url, osm)
                break
            except urllib.error.HTTPError as error:
                if error.code != 404 or template is GEOFABRIK_ALT:
                    raise
        osm_url.write_text(final + '\n', encoding='utf-8')
    with zipfile.ZipFile(osm) as archive:
        readme = next((archive.read(n).decode('utf-8', 'replace') for n in archive.namelist() if n.upper().startswith('README')), '')
    as_of = re.search(r'data as of (\S+)', readme)
    fetched['files']['osm.gpkg.zip'] = {
        'url': final, 'name': final.rsplit('/', 1)[1], 'data_as_of': as_of.group(1) if as_of else None,
        'licence': 'Open Database License 1.0 (ODbL)', 'attribution': '© OpenStreetMap contributors',
        'bytes': osm.stat().st_size, 'sha256': de.sha256(osm)}
    cells = tiles()
    log('BAG', NAME, len(cells), 'cells of', TILE, 'degrees in', BBOX)
    stamps, done = [], 0
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for _, stamp in pool.map(try_cell, cells):
            done += 1
            if stamp:
                stamps.append(stamp)
            if done % 50 == 0 or done == len(cells):
                log('BAG cells', done, 'of', len(cells))
    missing = [c for c in cells if not tile_path(c).exists()]
    if missing:      # no fetched.json: build refuses a province with whole cells missing
        raise SystemExit(f'{NAME}: {len(missing)} of {len(cells)} BAG cells could not be fetched; run fetch again for '
                         f'--province {CODE}, the {len(cells) - len(missing)} finished cells are kept')
    holes = cell_holes(cells)
    if holes:
        log(f'BAG: {len(holes)} small box(es) of about 200 m left out after PDOK errors; the next fetch asks for them again')
    count = sum(1 for _ in addresses())
    boxes = json.loads((SHARED / 'provinces.json').read_text(encoding='utf-8')) if (SHARED / 'provinces.json').exists() else {}
    # When every cell came from an earlier fetch there is no new timeStamp: the cells' own write times say when.
    written = sorted(tile_path(c).stat().st_mtime for c in cells)
    iso = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat(timespec='seconds')
    fetched['files']['bag'] = {'url': BAG_API, 'collection': 'adres', 'province': NAME, 'box': BBOX, 'cells': len(cells),
                               'served_at': max(stamps) if stamps else None, 'rows': count,
                               'cells_written': [iso(written[0]), iso(written[-1])] if written else None,
                               'holes': [box for _, box in holes],
                               'licence': BAG_LICENCE, 'attribution': 'Kadaster, Basisregistratie Adressen en Gebouwen (BAG)'}
    fetched['files']['boundary'] = {'url': boxes.get('source', BOUNDARIES), 'licence': BOUNDARY_LICENCE,
                                    'served_at': boxes.get('served_at'), 'used_for': 'the box of BAG cells to fetch',
                                    'official_box': CODE in boxes.get('boxes', {})}
    (SOURCE / 'fetched.json').write_text(json.dumps(fetched, indent=1, ensure_ascii=False), encoding='utf-8')
    log('fetched', REGION, '; BAG addresses in', NAME, count)
    try:
        fetch_aeds(force=REFRESH)
    except SystemExit as error:      # the map is complete without them; aed --province fetches them later
        log('AEDs not fetched:', error)
    try:
        fetch_seh(force=REFRESH)
    except (SystemExit, OSError, urllib.error.URLError, zipfile.BadZipFile) as error:   # seh --province fetches it later
        log('SEH list not fetched:', error)


# ------------------------------------------------------------------ build ----

def addresses():
    """This province's BAG rows from the cells over its box, each address once (one on a cell edge comes with both)."""
    seen = set()
    for cell in tiles():
        path = tile_path(cell)
        if not path.exists():
            continue
        with gzip.open(path, 'rt', encoding='utf-8') as lines:
            for line in lines:
                row = json.loads(line)
                if row.get('id') in seen or not in_province(row):
                    continue
                seen.add(row.get('id'))
                yield row


def build_map(fetched, geo):
    """OpenStreetMap through the existing map builder into national.sqlite; map.sqlite stays empty, as in a US state map."""
    osm = fetched['files']['osm.gpkg.zip']
    gpkg = BASE / 'work' / 'osm.gpkg'
    gpkg.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE / 'osm.gpkg.zip') as archive:
        member = next(n for n in archive.namelist() if n.endswith('.gpkg'))
        with archive.open(member) as src, open(gpkg, 'wb') as dst:
            shutil.copyfileobj(src, dst, 1 << 22)
    national = geo / 'national.sqlite'
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_map.py'), str(gpkg), str(national)],
                   check=True, stdout=subprocess.DEVNULL)
    terminals, layer = ferry_terminals(gpkg)
    db = sqlite3.connect(national)
    try:
        # build_map.py writes the Southern California metadata; this map's own source, date and box replace it.
        db.executemany('INSERT OR REPLACE INTO meta VALUES (?,?)', [
            ('source', f"OpenStreetMap contributors, via Geofabrik {osm['name']} (ODbL 1.0)"),
            ('data_as_of', osm['data_as_of'] or ''), ('bounds', ','.join(map(str, BBOX))),
            ('help_points', 'all classes: OpenStreetMap (ODbL 1.0)'), ('region', REGION)])
        # The Wadden islands are reached by ferry; tools/build_map.py keeps no transport points, so their terminals
        # are added here, placed as build_map.py places a point (the middle of the feature's box).
        db.executemany('INSERT INTO poi(cls,name,lon,lat) VALUES (?,?,?,?)',
                       [('ferry_terminal', name, lon, lat) for name, lon, lat in terminals])
        # Geofabrik's extract carries whole ferry routes, so the far end comes along (Newcastle with Noord-Holland,
        # Urk with Noord-Holland's Enkhuizen ferry), and some offshore points. A point that far out belongs to
        # another map, if any: it goes, and the count is kept in build.json.
        west, south, east, north = BBOX
        outside = db.execute('DELETE FROM poi WHERE lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?',
                             (west - POINT_MARGIN, east + POINT_MARGIN, south - POINT_MARGIN, north + POINT_MARGIN)).rowcount
        db.commit()
        db.execute('VACUUM')
    finally:
        db.close()
    empty = sqlite3.connect(geo / 'map.sqlite')
    try:
        empty.executescript('''CREATE TABLE feat(id INTEGER PRIMARY KEY, layer TEXT, cls TEXT, name TEXT, minz INTEGER, geom BLOB);
          CREATE VIRTUAL TABLE feat_idx USING rtree(id, minx, maxx, miny, maxy, minz, maxz);
          CREATE TABLE poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL);
          CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);''')
        # The app reads the map's source and data date from this file's meta (server.py map_info), so it carries them too.
        meta = sqlite3.connect(f'file:{national}?mode=ro', uri=True)
        empty.executemany('INSERT INTO meta VALUES (?,?)', meta.execute(
            "SELECT key,value FROM meta WHERE key IN ('source','data_as_of','bounds','help_points','region')").fetchall())
        meta.close()
        empty.commit()
    finally:
        empty.close()
    gpkg.unlink()
    kept = sqlite3.connect(f'file:{national}?mode=ro', uri=True)
    ferries = kept.execute("SELECT count(*) FROM poi WHERE cls='ferry_terminal'").fetchone()[0]
    kept.close()
    return {'ferry_terminals': ferries, 'transport_layer': layer, 'points_outside_dropped': outside}


TRANSPORT_TABLES = ('gis_osm_transport_free', 'gis_osm_transport_a_free')


def ferry_terminals(gpkg):
    """([(name, lon, lat), ...], whether the extract has a transport layer at all) for OpenStreetMap's ferry terminals."""
    src = sqlite3.connect(f'file:{gpkg}?mode=ro', uri=True)
    found, layer = [], False
    try:
        have = {name for name, in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TRANSPORT_TABLES:
            if table not in have:
                continue
            layer = True
            for blob, name in src.execute(f"SELECT geom,name FROM {table} WHERE fclass='ferry_terminal'"):
                if blob is None:
                    continue
                try:
                    found.append((name, *de.gpkg_middle(blob)))
                except (ValueError, IndexError, struct.error):     # as in build_map.py: an unreadable geometry is skipped
                    continue
    finally:
        src.close()
    return found, layer


# ------------------------------------------------------------------- AEDs ----

# Geofabrik's free extract keeps no AEDs, so they come from OpenStreetMap itself through the Overpass API: the same data
# and licence as the rest of the map, one query per province by its official ISO 3166-2 boundary in OpenStreetMap.
# Public Overpass instances, asked in this order: when one is down or busy (502, 503, 504, 429, no answer) the next is
# asked straight away, and only when all have failed is there a wait before another round. --overpass puts one first.
OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter',
            'https://maps.mail.ru/osm/tools/overpass/api/interpreter']
OVERPASS_ROUNDS = 3
AED_QUERY = ('[out:json][timeout:180];'
             'area["ISO3166-2"="{region}"]["boundary"="administrative"]->.province;'
             'nwr["emergency"="defibrillator"](area.province);out center tags;')
AED_LICENCE = 'Open Database License 1.0 (ODbL)'
NOT_PUBLIC = {'private', 'no'}      # access=private or no: behind a door the public cannot open, so not on this map


def aed_name(tags):
    """'AED', where it hangs and when it can be reached, in OpenStreetMap's own words: 'AED: gevel sporthal (24/7)'."""
    where = next((tags[k].strip() for k in ('defibrillator:location:nl', 'defibrillator:location', 'name', 'operator')
                  if (tags.get(k) or '').strip()), '')
    hours = (tags.get('opening_hours') or '').strip()
    name = 'AED' + (f': {where}' if where else '') + (f' ({hours})' if hours else '')
    return name[:160]


def aed_points(answer):
    """([(name, lon, lat), ...], how many were left out as not public) from an Overpass answer."""
    points, private = [], 0
    for element in answer.get('elements', []):
        tags = element.get('tags') or {}
        centre = element.get('center') or {}
        lat, lon = element.get('lat', centre.get('lat')), element.get('lon', centre.get('lon'))
        if lat is None or lon is None:
            continue
        if (tags.get('access') or '').strip().lower() in NOT_PUBLIC:
            private += 1
            continue
        points.append((aed_name(tags), round(float(lon), 7), round(float(lat), 7)))
    return points, private


def fetch_aeds(force=False):
    """This province's AEDs, saved to source/aeds.json; a list younger than OSM_MAX_AGE days is used again unless force
    (--refresh). Returns what was saved."""
    path = SOURCE / 'aeds.json'
    if path.exists() and not force:
        age = (time.time() - path.stat().st_mtime) / 86400
        if age < OSM_MAX_AGE:
            log('AEDs: using the list fetched', round(age, 1), 'days ago (--refresh asks again)')
            return json.loads(path.read_text(encoding='utf-8'))
    query = AED_QUERY.format(region=REGION)
    log('AEDs (OpenStreetMap, Overpass API)', REGION)
    body = urllib.parse.urlencode({'data': query}).encode('utf-8')
    answer, served_by, failures = None, None, []
    for round_ in range(OVERPASS_ROUNDS):
        if round_:
            log('every Overpass instance busy or unreachable; trying them again in', 60 * round_, 's')
            time.sleep(60 * round_)
        for url in OVERPASS:
            try:
                request = urllib.request.Request(url, data=body, headers={'User-Agent': 'lastbook-region-builder'})
                with urllib.request.urlopen(request, timeout=200) as response:   # the query's own limit is 180 s
                    answer = json.loads(response.read().decode('utf-8'))
                served_by = url
                break
            # OSError covers a refused or dropped connection and, on Python 3.9, socket.timeout (a busy instance that
            # accepts the request and then says nothing), which is not yet a TimeoutError there.
            except (OSError, http.client.HTTPException, ValueError) as error:
                host = urllib.parse.urlsplit(url).hostname
                failures.append(f'{host}: {error}')
                log('Overpass', host, 'busy or unreachable:', error)
        if answer is not None:
            break
    if answer is None:
        raise SystemExit(f'{REGION}: no Overpass instance answered ({"; ".join(failures[-len(OVERPASS):])}); '
                         f'run aed --province {CODE} later')
    if answer.get('remark'):         # a query that ran out of time or memory still answers 200, with a remark
        raise SystemExit(f'{REGION}: Overpass did not finish the query: {answer["remark"]}')
    if not answer.get('elements'):   # a province always has some: none means the boundary was not found
        raise SystemExit(f'{REGION}: Overpass ({served_by}) found no AEDs at all; the province boundary '
                         f'(ISO3166-2={REGION}) may not be in its data. Nothing saved.')
    points, private = aed_points(answer)
    saved = {'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
             'osm_as_of': (answer.get('osm3s') or {}).get('timestamp_osm_base'), 'url': served_by, 'query': query,
             'licence': AED_LICENCE, 'attribution': '© OpenStreetMap contributors',
             'not_public_left_out': private, 'points': [list(p) for p in points]}
    SOURCE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
    log('AEDs in', NAME, len(points), f'({private} marked private, left out)')
    return saved


def aed_source(saved):
    """What build.json records about the AED list: where and when it was asked, the query, and the size and SHA-256 of
    source/aeds.json as saved (an Overpass answer is not a file to hash; the saved list is)."""
    info = {k: saved.get(k) for k in ('url', 'query', 'osm_as_of', 'fetched', 'licence', 'attribution', 'not_public_left_out')}
    info['points'] = len(saved.get('points') or [])
    path = SOURCE / 'aeds.json'
    if path.is_file():
        info.update({'file': 'source/aeds.json', 'bytes': path.stat().st_size, 'sha256': de.sha256(path)})
    return info


def add_aeds(national, saved):
    """The AEDs as help points of class 'defibrillator', in place of any already there; returns how many."""
    db = sqlite3.connect(national)
    try:
        db.execute("DELETE FROM poi WHERE cls = 'defibrillator'")
        db.executemany('INSERT INTO poi(cls, name, lon, lat) VALUES (?, ?, ?, ?)',
                       [('defibrillator', name, lon, lat) for name, lon, lat in saved['points']])
        add_note(db, 'AEDs', f"OpenStreetMap via the Overpass API, as of {saved.get('osm_as_of') or saved.get('fetched')} (ODbL 1.0)")
        db.commit()
    finally:
        db.close()
    return len(saved['points'])


def aed():
    """Fetches this province's AEDs and adds them to its built map in place, without a rebuild; build.json and
    map-set.json follow. A later build keeps them (it reads source/aeds.json)."""
    saved = fetch_aeds(force=REFRESH)
    data = BASE / 'data'
    national = data / 'derived' / 'geo' / 'national.sqlite'
    if not national.is_file():
        log(REGION, 'is not built yet: its AEDs are saved and go in with its build')
        return
    count = add_aeds(national, saved)
    refresh_report(data, {'aeds': count}, {'aeds.json': aed_source(saved)})
    log(REGION, count, 'AEDs on the map')


# -------------------------------------------------------------------- SEH ----

# Every hospital location with an emergency department (SEH) answers the RIVM's yearly questionnaire; the answers per
# location are on data.rivm.nl under the Public Domain Mark: opening hours, acute obstetrics, a GP out-of-hours post
# (huisartsenpost) in the building. Each SEH becomes a help point of class 'emergency_department', placed at its own
# address in the BAG, so nothing is geocoded online. The list is the whole country's, kept in NL-shared/.
SEH_URL = ('https://data.rivm.nl/meta/srv/api/records/afbdf4b9-00f0-4d4e-a67e-fd3bbc8c833c/attachments/'
           'Antwoorden%20vragenlijst%202026%20tbv%20data.rivm.nl.zip')
SEH_TITLE = "RIVM, Vragenlijst aanbod SEH's en Acute Verloskunde 2026"
SEH_LICENCE = 'Public Domain Mark 1.0'
SEH_SHEET = 'Reguliere vragenlijst'
SEH_MAX_AGE = 30     # days; the RIVM publishes the answers once a year
SEH_PLACED = set()   # (name, postcode) placed by seh() in this run, to tell which were placed in no province


def xlsx_rows(path, sheet):
    """The rows of one sheet of an .xlsx file as lists of strings (None for an empty cell), read with the standard
    library only: a workbook is a zip of XML parts."""
    m = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    with zipfile.ZipFile(path) as book:
        shared = []
        if 'xl/sharedStrings.xml' in book.namelist():
            shared = [''.join(t.text or '' for t in si.iter(m + 't'))
                      for si in ElementTree.fromstring(book.read('xl/sharedStrings.xml')).iter(m + 'si')]
        workbook = ElementTree.fromstring(book.read('xl/workbook.xml'))
        targets = {rel.get('Id'): rel.get('Target') for rel in ElementTree.fromstring(book.read('xl/_rels/workbook.xml.rels'))}
        found = [s.get(r + 'id') for s in workbook.iter(m + 'sheet') if s.get('name') == sheet]
        if not found:
            raise SystemExit(f'{path.name}: no sheet named {sheet!r}')
        part = targets[found[0]].lstrip('/')
        part = part if part.startswith('xl/') else 'xl/' + part
        rows = []
        for row in ElementTree.fromstring(book.read(part)).iter(m + 'row'):
            cells = {}
            for cell in row.iter(m + 'c'):
                letters = ''.join(ch for ch in cell.get('r', '') if ch.isalpha())
                column = 0
                for ch in letters:
                    column = column * 26 + ord(ch.upper()) - 64
                value = cell.find(m + 'v')
                if cell.get('t') == 's' and value is not None:
                    text = shared[int(value.text)]
                elif cell.get('t') == 'inlineStr':
                    text = ''.join(t.text or '' for t in cell.iter(m + 't'))
                else:
                    text = value.text if value is not None else None
                cells[column - 1] = text.replace('_x000D_', '').strip() if isinstance(text, str) else text
            rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
        return rows


def seh_locations(path):
    """Each SEH in the RIVM's answers: {name, place, street, postcode, all_hours, periods, obstetrics, gp_post}."""
    rows = xlsx_rows(path, SEH_SHEET)
    header_at = next((i for i, row in enumerate(rows) if row and (row[0] or '').startswith('Naam ziekenhuis')), None)
    if header_at is None:
        raise SystemExit(f'{path.name}: no header row starting with "Naam ziekenhuis" in sheet {SEH_SHEET!r}')
    header = [(h or '').strip() for h in rows[header_at]]

    def column(start, after=-1):
        hit = next((i for i, h in enumerate(header) if i > after and h.lower().startswith(start.lower())), None)
        if hit is None:
            raise SystemExit(f'{path.name}: no column starting with {start!r}; the RIVM changed its sheet')
        return hit
    hours = column('Heeft uw ziekenhuislocatie een spoedeisende hulpafdeling')
    cols = {'name': column('Naam ziekenhuis'), 'place': column('Plaats'), 'street': column('Adres'),
            'postcode': column('Postcode'), 'offer': column('Volgens onze informatie'), 'hours': hours,
            'day': column('Overdag', hours), 'evening': column('’s Avonds', hours), 'night': column('’s Nachts', hours),
            'gp': column('Is er op deze ziekenhuislocatie een huisartsenpost')}
    out = []
    for row in rows[header_at + 1:]:
        value = {k: (row[i] if i < len(row) else None) for k, i in cols.items()}
        if not value['name']:
            continue
        offer, gp = (value['offer'] or '').lower(), (value['gp'] or '').lower()
        out.append({
            'name': ' '.join(value['name'].split()), 'place': value['place'], 'street': value['street'],
            'postcode': (value['postcode'] or '').replace(' ', '').upper(),
            'all_hours': '24/7' in (value['hours'] or '') and 'niet 24/7' not in (value['hours'] or ''),
            'periods': [p for p, k in (('overdag', 'day'), ("'s avonds", 'evening'), ("'s nachts", 'night')) if value[k]],
            'obstetrics': 'acute verloskunde' in offer and 'geen acute verloskunde' not in offer,
            'gp_post': 'in building' if gp.startswith('ja, de hap is in het ziekenhuis') else
                       'nearby' if gp.startswith('ja') else None})
    return out


def seh_name(seh):
    """'SEH 24/7 · Noordwest Ziekenhuisgroep Alkmaar · acute verloskunde'; the hours when not day and night, and the
    place when the name does not say it ('Dijklander Ziekenhuis (Hoorn)')."""
    when = '24/7' if seh['all_hours'] else 'niet 24/7 (' + ' en '.join(seh['periods'] or ['beperkt']) + ')'
    extra = [{'in building': 'huisartsenpost in het gebouw', 'nearby': 'huisartsenpost vlakbij'}.get(seh['gp_post']),
             'acute verloskunde' if seh['obstetrics'] else None]
    title = seh['name']
    if seh.get('place') and fold(seh['place']) not in fold(title):
        title += f" ({seh['place']})"
    return ' · '.join([f'SEH {when}', title] + [e for e in extra if e])[:160]


def fetch_seh(force=False):
    """The RIVM's answers, kept as NL-shared/seh.xlsx with NL-shared/seh.json saying when and from where; a copy
    younger than SEH_MAX_AGE days is used again unless force (--refresh). Returns the .xlsx path."""
    xlsx, about = SHARED / 'seh.xlsx', SHARED / 'seh.json'
    if xlsx.exists() and about.exists() and not force and (time.time() - xlsx.stat().st_mtime) / 86400 < SEH_MAX_AGE:
        return xlsx
    SHARED.mkdir(parents=True, exist_ok=True)
    log('SEH (RIVM)', SEH_URL)
    archive = SHARED / 'seh.zip'
    download(SEH_URL, archive)
    with zipfile.ZipFile(archive) as z:
        member = next((n for n in z.namelist() if n.lower().endswith('.xlsx')), None)
        if not member:
            raise SystemExit(f'{SEH_URL}: no .xlsx in the archive')
        xlsx.write_bytes(z.read(member))
    found = seh_locations(xlsx)
    about.write_text(json.dumps({'url': SEH_URL, 'title': SEH_TITLE, 'licence': SEH_LICENCE, 'file': member,
                                 'fetched': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                                 'locations': len(found)}, indent=1, ensure_ascii=False), encoding='utf-8')
    log('SEH locations in the RIVM list:', len(found))
    return xlsx


def seh_source():
    """What build.json records about the RIVM list: NL-shared/seh.json, with the size and SHA-256 of the archive as
    downloaded and of the spreadsheet in it."""
    about = json.loads((SHARED / 'seh.json').read_text(encoding='utf-8')) if (SHARED / 'seh.json').exists() else {'title': SEH_TITLE}
    for key, path in (('archive', SHARED / 'seh.zip'), ('xlsx', SHARED / 'seh.xlsx')):
        if path.is_file():
            about[key] = {'file': f'NL-shared/{path.name}', 'bytes': path.stat().st_size, 'sha256': de.sha256(path)}
    return about


def place_at(index, street, postcode):
    """(lat, lon) of a BAG address: the house itself ('Wilhelminalaan 12', '1815JD'), else the first of a range
    ('3-11'), else the middle of its postcode; None when the postcode is not in this index."""
    m = re.fullmatch(r'(.*?)\s+(\d+)\s*([A-Za-z])?(?:\s*-\s*(\S+))?', (street or '').strip())
    number, letter = (m.group(2), m.group(3)) if m else (None, None)
    tries = [house(number, letter), number] if number else []
    for num in [t for t in tries if t]:
        hit = index.execute('SELECT avg(lat), avg(lon) FROM addr WHERE zip=? AND upper(num)=upper(?)', (postcode, num)).fetchone()
        if hit[0] is not None:
            return hit
    hit = index.execute('SELECT avg(lat), avg(lon) FROM addr WHERE zip=?', (postcode,)).fetchone()
    return hit if hit[0] is not None else None


def add_seh(geo, xlsx, region=None):
    """The SEHs whose address is in this province's BAG index, as help points of class 'emergency_department' (in
    place of any already there). Returns (name, postcode) of each placed."""
    region = region or REGION
    index = sqlite3.connect(f"file:{geo / 'addresses' / (region + '.sqlite')}?mode=ro", uri=True)
    try:
        points = []
        for seh in seh_locations(xlsx):
            spot = place_at(index, seh['street'], seh['postcode'])
            if spot:
                points.append((seh_name(seh), spot[1], spot[0], (seh['name'], seh['postcode'])))
    finally:
        index.close()
    about = json.loads((xlsx.parent / 'seh.json').read_text(encoding='utf-8')) if (xlsx.parent / 'seh.json').exists() else {}
    db = sqlite3.connect(geo / 'national.sqlite')
    try:
        db.execute("DELETE FROM poi WHERE cls = 'emergency_department'")
        db.executemany('INSERT INTO poi(cls, name, lon, lat) VALUES (?, ?, ?, ?)',
                       [('emergency_department', name, lon, lat) for name, lon, lat, _ in points])
        add_note(db, 'SEH', f"{SEH_TITLE} ({SEH_LICENCE}), fetched {about.get('fetched', '?')[:10]}, placed at their BAG address")
        db.commit()
    finally:
        db.close()
    return [plain for *_, plain in points]


def add_note(db, label, text):
    """Records in the map's meta where one kind of help point comes from: '...; AEDs: ...; SEH: ...'."""
    meta = dict(db.execute('SELECT key, value FROM meta').fetchall())
    parts = [p for p in (meta.get('help_points') or 'all classes: OpenStreetMap (ODbL 1.0)').split('; ')
             if not p.startswith(label + ':')]
    db.execute('INSERT OR REPLACE INTO meta VALUES (?, ?)', ('help_points', '; '.join(parts + [f'{label}: {text}'])))


def refresh_report(data, counts=None, source=None, changed=('national.sqlite',)):
    """After a map file was changed in place: build.json's counts, its sources (each entry updated, not replaced) and
    the changed files' size and hash, and map-set.json's sizes, follow."""
    files = [data / 'derived' / 'geo' / name for name in changed]
    map_set = data / 'map-set.json'
    if map_set.exists():                    # first, so build.json below records map-set.json as it now is
        listed = json.loads(map_set.read_text(encoding='utf-8'))
        for f in files:
            name = f.relative_to(data).as_posix()
            if name in listed.get('files', {}):
                listed['files'][name] = f.stat().st_size
        listed['bytes'] = sum(listed.get('files', {}).values())
        map_set.write_text(json.dumps(listed, indent=1), encoding='utf-8')
        files.append(map_set)
    report_path = data / 'build.json'
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report.setdefault('counts', {}).update(counts or {})
        listed = report.setdefault('sources', {}).setdefault('files', {})
        for key, info in (source or {}).items():
            listed[key] = {**(listed.get(key) or {}), **info}
        for f in files:
            report.setdefault('outputs', {})[f.relative_to(data).as_posix()] = {'bytes': f.stat().st_size, 'sha256': de.sha256(f)}
        report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')


def seh():
    """Adds the RIVM's SEHs to this province's built map in place; a later build keeps them (it reads NL-shared/)."""
    xlsx = fetch_seh(force=REFRESH)
    data = BASE / 'data'
    if not (data / 'derived' / 'geo' / 'national.sqlite').is_file():
        log(REGION, 'is not built yet: its SEHs go in with its build')
        return
    placed = add_seh(data / 'derived' / 'geo', xlsx)
    SEH_PLACED.update(placed)
    refresh_report(data, {'seh': len(placed)}, {'seh.xlsx': seh_source()})
    log(REGION, len(placed), 'SEH(s):', ', '.join(name for name, _ in placed) or '-')


# ---------------------------------------------------------------- outline ----

def label_places(places, outlines):
    """Labels every OpenStreetMap row of a place finder by the outline that holds it; returns how many lie outside this
    province: {'other_province': n, 'outside_provinces': n}."""
    db = sqlite3.connect(places)
    try:
        rows = db.execute("SELECT id, lon, lat FROM place WHERE source = 'OpenStreetMap'").fetchall()
        labels = [(where(lon, lat, outlines), id_) for id_, lon, lat in rows]
        db.executemany('UPDATE place SET detail = ? WHERE id = ?', [(f'{label} (OpenStreetMap)', id_) for label, id_ in labels])
        db.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
        db.commit()
        db.execute('VACUUM')
    finally:
        db.close()
    return {'other_province': sum(1 for label, _ in labels if label not in (NAME, OUTSIDE)),
            'outside_provinces': sum(1 for label, _ in labels if label == OUTSIDE)}


def outline():
    """Without a rebuild: labels this province's OpenStreetMap places by the official outlines (fetched once into
    NL-shared/ when not there), and records in build.json how each source was cut and the size and SHA-256 of the AED
    and SEH files. A later build does all of this itself."""
    if not (SHARED / 'outlines.json').is_file():
        fetch_outlines()
    outlines = load_outlines()
    data = BASE / 'data'
    places = data / 'derived' / 'geo' / 'places.sqlite'
    if not places.is_file():
        log(REGION, 'is not built yet: its build labels the places itself')
        return
    outside = label_places(places, outlines)
    report = json.loads((data / 'build.json').read_text(encoding='utf-8'))
    source = {'bag': {'cut': bag_cut()}, 'osm.gpkg.zip': {'cut': osm_cut(report.get('sources') or {})}}
    if (SOURCE / 'aeds.json').is_file():
        source['aeds.json'] = aed_source(json.loads((SOURCE / 'aeds.json').read_text(encoding='utf-8')))
    if (SHARED / 'seh.json').is_file() and 'seh.xlsx' in (report.get('sources') or {}).get('files', {}):
        source['seh.xlsx'] = seh_source()
    refresh_report(data, {'osm_places_outside': outside}, source, changed=('places.sqlite',))
    log(REGION, 'OpenStreetMap places labelled by the official outlines;', outside['other_province'], 'in another province,',
        outside['outside_provinces'], OUTSIDE)


def build_addresses(fetched, geo):
    path = geo / 'addresses' / f'{REGION}.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    try:
        db.executescript('PRAGMA page_size=8192; PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;'
                         'CREATE TABLE addr(num TEXT, street TEXT, norm TEXT, city TEXT, state TEXT, zip TEXT, lat REAL, lon REAL, district TEXT);'
                         'CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);')
        rows, skipped, no_code, odd_code = [], 0, 0, 0
        for a in addresses():
            num, street = house(a.get('number'), a.get('letter'), a.get('addition')), (a.get('street') or '').strip()
            if not num or not street or a.get('lon') is None or a.get('lat') is None:
                skipped += 1
                continue
            if not str(a.get('postcode') or '').strip():
                no_code += 1           # an outbuilding ("12-ts") or a caravan pitch: PostNL gives no postcode
            elif not postcode(a.get('postcode')):
                odd_code += 1
            rows.append((num, street, normalize_nl(street), (a.get('place') or '').strip(), REGION, postcode(a.get('postcode')),
                         round(a['lat'], 6), round(a['lon'], 6), (a.get('municipality') or '').strip()))
        db.executemany('INSERT INTO addr VALUES (?,?,?,?,?,?,?,?,?)', rows)
        db.execute('CREATE INDEX addr_norm ON addr(norm, num)')
        db.execute('CREATE INDEX addr_zip ON addr(zip, num)')     # '2628CD 5', the way Dutch people write an address
        info = fetched['files']['bag']
        db.executemany('INSERT INTO meta VALUES (?,?)', [
            ('region', REGION), ('norm', NORM), ('count', str(len(rows))), ('source', f'Kadaster BAG via PDOK ({BAG_LICENCE})'),
            ('served', info.get('served_at') or (info.get('cells_written') or [None, ''])[-1] or ''),
            ('built', time.strftime('%Y-%m-%dT%H:%M:%S'))])
        db.commit()
    finally:
        db.close()
    return {'addresses': len(rows), 'address_records_without_house_number_or_point': skipped,
            'addresses_without_postcode': no_code, 'addresses_with_malformed_postcode': odd_code}


def middle(points):
    points.sort()
    return points[len(points) // 2]


def build_places(fetched, geo):
    """The place finder: places (woonplaatsen), municipalities, postcode areas (four digits) and postcodes, street names,
    and named OpenStreetMap places and points. Each row names the source it came from."""
    path = geo / 'places.sqlite'
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    counts = {}
    try:
        db.executescript('''CREATE TABLE place(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, detail TEXT, lat REAL, lon REAL, rank INTEGER, source TEXT);
          CREATE VIRTUAL TABLE place_fts USING fts5(name, detail, content='place', content_rowid='id', tokenize='unicode61');''')
        insert = 'INSERT INTO place(name,kind,detail,lat,lon,rank,source) VALUES (?,?,?,?,?,?,?)'

        def add(kind, rows):
            db.executemany(insert, rows)
            counts[kind] = len(rows)
        places, towns, areas, codes, streets = {}, {}, {}, {}, {}
        for a in addresses():
            if a.get('lon') is None or a.get('lat') is None:
                continue
            xy = (a['lon'], a['lat'])
            where, town, code = (a.get('place') or '').strip(), (a.get('municipality') or '').strip(), postcode(a.get('postcode'))
            street = (a.get('street') or '').strip()
            if where:
                places.setdefault((where, town), []).append(xy)
            if town:
                towns.setdefault(town, []).append(xy)
            if code:
                areas.setdefault(code[:4], []).append(xy)
                codes.setdefault(code, []).append(xy)
            if street and where:
                streets.setdefault((street, where), []).append(xy)
        source = 'Kadaster BAG'
        add('place', [(w, 'place (woonplaats)', f'{t}, {NAME}' if t and t != w else NAME, *middle(p)[::-1], 1, source)
                      for (w, t), p in sorted(places.items())])
        add('municipality', [(t, 'municipality (gemeente)', NAME, *middle(p)[::-1], 1, source) for t, p in sorted(towns.items())])
        add('postcode_area', [(c, 'postcode area', NAME, *middle(p)[::-1], 2, source) for c, p in sorted(areas.items())])
        add('postcode', [(f'{c[:4]} {c[4:]}', 'postcode', NAME, *middle(p)[::-1], 2, source) for c, p in sorted(codes.items())])
        add('street', [(s, 'street', f'{w}, {NAME}', *middle(p)[::-1], 3, source) for (s, w), p in sorted(streets.items())])
        # Geofabrik cuts its extract by an outline of its own, which takes in Baarle-Hertog's Belgian enclaves, so an
        # OpenStreetMap row is labelled by the official outline that holds it (Noord-Brabant, a neighbour, or OUTSIDE).
        outlines = load_outlines()
        national = sqlite3.connect(f"file:{geo / 'national.sqlite'}?mode=ro", uri=True)
        add('osm_point', [(name, cls.replace('_', ' '), osm_detail(lon, lat, outlines), lat, lon, 4, 'OpenStreetMap')
                          for cls, name, lon, lat in national.execute(
                              "SELECT cls,name,lon,lat FROM poi WHERE name IS NOT NULL AND name<>''")])
        rows = []
        for cls, name, geom in national.execute("SELECT cls,name,geom FROM feat WHERE layer='place' AND name IS NOT NULL"):
            _, _, x, y = struct.unpack_from('<iiii', geom)
            rows.append((name, cls, osm_detail(x / 1e6, y / 1e6, outlines), y / 1e6, x / 1e6, 1, 'OpenStreetMap'))
        add('osm_place', rows)
        national.close()
        labels = [detail for detail, in db.execute("SELECT detail FROM place WHERE source = 'OpenStreetMap'")]
        outside = {'other_province': sum(1 for d in labels if d not in (f'{NAME} (OpenStreetMap)', f'{OUTSIDE} (OpenStreetMap)')),
                   'outside_provinces': labels.count(f'{OUTSIDE} (OpenStreetMap)')}
        db.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
        db.commit()
        db.execute('VACUUM')
    finally:
        db.close()
    return {'places': counts, 'osm_places_outside': outside}


def build():
    """Builds into data.new/ beside the previous output and puts it in place of data/ only once it passes check, so a
    rebuild that fails or stops leaves the last good data/ (with its build.json) as it was."""
    if not (SOURCE / 'fetched.json').is_file():
        raise SystemExit(f'{REGION}: its fetch has not finished (no {SOURCE / "fetched.json"}); run fetch --province {CODE} again')
    fetched = json.loads((SOURCE / 'fetched.json').read_text(encoding='utf-8'))
    data, staging, previous = BASE / 'data', BASE / 'data.new', BASE / 'data.old'
    if previous.exists() and not data.exists():
        previous.rename(data)         # an earlier build stopped between the two renames at the end
    for leftover in (staging, previous):
        if leftover.exists():
            shutil.rmtree(leftover)
    geo = staging / 'derived' / 'geo'
    geo.mkdir(parents=True)
    started = time.time()
    counts = {}
    log('map (OpenStreetMap)')
    counts.update(build_map(fetched, geo))
    if (SOURCE / 'aeds.json').is_file():
        saved = json.loads((SOURCE / 'aeds.json').read_text(encoding='utf-8'))
        counts['aeds'] = add_aeds(geo / 'national.sqlite', saved)
        fetched.setdefault('files', {})['aeds.json'] = aed_source(saved)
    log('addresses (BAG)')
    counts.update(build_addresses(fetched, geo))
    if (SHARED / 'seh.xlsx').is_file():          # placed at their BAG address, so after the address index
        counts['seh'] = len(add_seh(geo, SHARED / 'seh.xlsx'))
        fetched.setdefault('files', {})['seh.xlsx'] = seh_source()
    log('places')
    counts.update(build_places(fetched, geo))
    files = fetched.setdefault('files', {})
    files.setdefault('bag', {})['cut'] = bag_cut()
    files.setdefault('osm.gpkg.zip', {})['cut'] = osm_cut(fetched)
    map_files = {f.relative_to(staging).as_posix(): f.stat().st_size for f in sorted(geo.glob('*.sqlite'))}
    (staging / 'map-set.json').write_text(json.dumps({'name': REGION, 'files': map_files, 'bytes': sum(map_files.values()),
                                                   'seconds': round(time.time() - started)}, indent=1), encoding='utf-8')
    outputs = {}
    for f in sorted(staging.rglob('*')):
        if f.is_file():
            outputs[f.relative_to(staging).as_posix()] = {'bytes': f.stat().st_size, 'sha256': de.sha256(f)}
    report = {'region': REGION, 'province': NAME, 'built': time.strftime('%Y-%m-%dT%H:%M:%S'), 'bbox': BBOX,
              'sources': fetched, 'counts': counts, 'outputs': outputs,
              'note': 'map-set.json lists the map files; the address index is a separate sidecar, as for US states.'}
    (staging / 'build.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    log('built in', round(time.time() - started), 's;', json.dumps(counts, ensure_ascii=False))
    failures = check(staging)
    if failures:
        raise SystemExit(f'{len(failures)} check(s) failed: {data} is unchanged; the failed build is in {staging}')
    if data.exists():
        data.rename(previous)
    try:
        staging.rename(data)
    except OSError:
        if previous.exists():
            previous.rename(data)
        raise
    if previous.exists():
        shutil.rmtree(previous)
    log('in place:', data)


# ------------------------------------------------------------------ check ----

# Addresses looked up in the BAG (PDOK OGC API, 25 November 2026), per province: (street, house number, postcode, place).
# Each province has one from its capital or largest city, and each inhabited Wadden island one of its own.
SAMPLE_ADDRESSES = {
    'GR': [('Jacobijnerstraat', '6', '9712HZ', 'Groningen'), ('Rodeweeshuisstraat', '55', '9712ET', 'Groningen')],
    'FR': [('Beijerstraat', '2', '8911HG', 'Leeuwarden'), ('Nieuwestraat', '33', '8899AR', 'Vlieland'),
           ('Europalaan', '38', '8881EK', 'West-Terschelling'), ('Miedenweg', '8', '9163JN', 'Nes'),
           ('Heereweg', '8', '9166SE', 'Schiermonnikoog')],
    'DR': [('Brink', '3A', '9401HS', 'Assen'), ('Brink', '1', '9401HS', 'Assen')],
    'OV': [('Aan de Stadsmuur', '79', '8011VD', 'Zwolle'), ('Aplein', '11', '8011TJ', 'Zwolle')],
    'FL': [('Waagpassage', '49', '8232DS', 'Lelystad'), ('Waagpassage', '140', '8232DW', 'Lelystad')],
    'GE': [('Jansplaats', '3', '6811GB', 'Arnhem'), ('Jansplaats', '33A', '6811GB', 'Arnhem')],
    'UT': [('Jansdam', '6-BS', '3512HB', 'Utrecht'), ('Janskerkhof', '3A', '3512BK', 'Utrecht')],
    'NH': [('Beurspassage', '1', '1012LW', 'Amsterdam'), ('Commandeurssingel', '20', '1792AT', 'Oudeschild')],
    'ZH': [('Mekelweg', '2', '2628CD', 'Delft'), ('Mekelweg', '4', '2628CD', 'Delft'), ('Lorentzweg', '1', '2628CJ', 'Delft'),
           ('Rotterdamseweg', '374A', '2629HG', 'Delft')],
    'ZE': [('Groenmarkt', '1', '4331BH', 'Middelburg'), ('Groenmarkt', '3', '4331BH', 'Middelburg')],
    'NB': [('Lombardje', '2', '5211HM', "'s-Hertogenbosch"), ('Korte Putstraat', '1F', '5211KP', "'s-Hertogenbosch")],
    'LI': [('Nieuwstraat', '15', '6211CR', 'Maastricht'), ('Nieuwstraat', '17', '6211CR', 'Maastricht')],
}
# The least a province holds; Flevoland, the smallest, has about 180,000 addresses. Per inhabited island: streets drawn
# and addresses (Vlieland, the smallest, has about a thousand people).
MINIMUM = {'roads': 10000, 'addresses': 100000, 'hospital': 1, 'pharmacy': 10, 'fire_station': 5, 'police': 2,
           'island_roads': 20, 'island_addresses': 100, 'aeds': 20}


def check(data=None):
    """The data only: nothing here imports engine/ or server.py. How the app searches it is tested in
    app/tests/test_address_nl.py.

    Returns what failed; build runs it on the new folder before putting it in place."""
    data = data or DATA
    failures = []
    geo = data / 'derived' / 'geo'

    def expect(ok, what):
        print(('ok    ' if ok else 'FAIL  ') + what)
        if not ok:
            failures.append(what)
    if not (data / 'build.json').is_file():
        expect(False, f'{REGION}: no build in {data} (run fetch, then build)')
        return failures
    report = json.loads((data / 'build.json').read_text(encoding='utf-8'))
    for rel, info in report['outputs'].items():
        f = data / rel
        expect(f.is_file() and f.stat().st_size == info['bytes'] and de.sha256(f) == info['sha256'], f'{rel}: size and SHA-256 as built')
    map_set = json.loads((data / 'map-set.json').read_text(encoding='utf-8'))
    expect(map_set['name'] == REGION, f'map-set.json name is {REGION}')
    expect(all((data / rel).stat().st_size == size for rel, size in map_set['files'].items()), 'map-set.json sizes match the files')
    for rel in [*map_set['files'], f'derived/geo/addresses/{REGION}.sqlite']:
        db = sqlite3.connect(f'file:{data / rel}?mode=ro', uri=True)
        expect(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', f'{rel}: SQLite integrity')
        db.close()
    west, south, east, north = BBOX
    nat = sqlite3.connect(f"file:{geo / 'national.sqlite'}?mode=ro", uri=True)
    roads = nat.execute("SELECT count(*) FROM feat WHERE layer='road'").fetchone()[0]
    expect(roads > MINIMUM['roads'], f'streets drawn from OpenStreetMap: {roads:,} road features')
    for cls in ('hospital', 'pharmacy', 'fire_station', 'police'):
        n = nat.execute('SELECT count(*) FROM poi WHERE cls=?', (cls,)).fetchone()[0]
        expect(n >= MINIMUM[cls], f'help points {cls}: {n:,} (expected at least {MINIMUM[cls]:,})')
    outside = nat.execute('SELECT count(*) FROM poi WHERE lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?',
                          (west - POINT_MARGIN, east + POINT_MARGIN, south - POINT_MARGIN, north + POINT_MARGIN)).fetchone()[0]
    expect(outside == 0, f'every help point within {NAME} plus the {POINT_MARGIN}° margin ({outside} outside)')
    meta = dict(nat.execute('SELECT key,value FROM meta'))
    expect(meta.get('region') == REGION and 'OpenStreetMap' in meta.get('source', ''), f"map meta: region {meta.get('region')}, source named")
    counts = report.get('counts', {})
    aeds = nat.execute("SELECT count(*) FROM poi WHERE cls='defibrillator'").fetchone()[0]
    sehs = nat.execute("SELECT count(*) FROM poi WHERE cls='emergency_department'").fetchone()[0]
    if 'seh' in counts or sehs:      # every province has at least one hospital with an SEH
        expect(sehs >= 1, f'SEHs (RIVM): {sehs}')
    if 'aeds' in counts or aeds:
        expect(aeds >= MINIMUM['aeds'], f"AEDs (OpenStreetMap): {aeds:,} (expected at least {MINIMUM['aeds']})")
    else:          # a map without them still works; aed --province adds them
        print(f'note  no AEDs on this map yet (python3 tools/build_region_nl.py aed --province {CODE})')
    holes = (report.get('sources', {}).get('files', {}).get('bag') or {}).get('holes') or []
    # Reported, not failed: a box PDOK will not serve is about 200 m across; fetch asks for it again each time.
    print(('note  ' if holes else 'ok    ') + f'BAG boxes left out after PDOK errors: {len(holes)}'
          + (f' (first: {holes[0]}; run fetch again to retry them)' if holes else ''))
    for island, (w, s, e, n) in ISLANDS.get(CODE, []):
        roads = nat.execute("SELECT count(*) FROM feat f JOIN feat_idx i ON i.id=f.id WHERE f.layer='road' "
                            "AND i.minx>=? AND i.maxx<=? AND i.miny>=? AND i.maxy<=?", (w, e, s, n)).fetchone()[0]
        expect(roads >= MINIMUM['island_roads'], f'island {island}: {roads:,} road features on the island')
        ferries = nat.execute("SELECT count(*) FROM poi WHERE cls='ferry_terminal' AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?",
                              (w, e, s, n)).fetchone()[0]
        # Reported, not failed: whether a terminal is in the extract depends on OpenStreetMap's tagging there.
        print(('ok    ' if ferries else 'note  ') + f'island {island}: {ferries} ferry terminal(s)'
              + ('' if counts.get('transport_layer', True) else ' (the extract has no transport layer)'))
    nat.close()
    addr = sqlite3.connect(f"file:{geo / 'addresses' / (REGION + '.sqlite')}?mode=ro", uri=True)
    n, bad_zip, outside, cities = addr.execute(
        "SELECT count(*), sum(zip NOT GLOB '[1-9][0-9][0-9][0-9][A-Z][A-Z]'), sum(lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?),"
        " count(DISTINCT city) FROM addr", (west, east, south, north)).fetchone()
    expect(n >= MINIMUM['addresses'], f'addresses: {n:,}')
    # The BAG has addresses without a postcode: outbuildings ("Pieperij 5-ts", Drenthe has about 12,500), caravan
    # pitches and berths, which PostNL does not deliver to. Those are reported. A postcode that is there but is not
    # 1234AB is a fault in the data or in this builder, and fails.
    malformed = counts.get('addresses_with_malformed_postcode', 0)
    expect(malformed <= n * 0.001, f'addresses whose postcode is not 1234AB: {malformed:,}')
    print(f'ok    addresses with a postcode: {n - (bad_zip or 0):,} of {n:,} '
          f'({bad_zip or 0:,} without one: outbuildings, caravan pitches, berths)')
    expect(not outside, f'every address inside the {NAME} box ({outside} outside)')
    expect(cities > 1, f'{cities:,} places (woonplaatsen)')
    meta = dict(addr.execute('SELECT key,value FROM meta'))
    expect(meta.get('region') == REGION and meta.get('norm') == NORM, f"index meta: region {meta.get('region')}, norm {meta.get('norm')}")
    expect(meta.get('count') == str(n), f"index meta count {meta.get('count')} matches its {n:,} rows")
    wrong = [street for street, norm in addr.execute('SELECT DISTINCT street,norm FROM addr') if normalize_nl(street) != norm]
    expect(not wrong, f'every stored street key follows scheme {NORM} ({len(wrong)} do not{": " + ", ".join(wrong[:3]) if wrong else ""})')
    for street, number, code, place in SAMPLE_ADDRESSES.get(CODE, []):
        found = addr.execute('SELECT zip,city FROM addr WHERE norm=? AND num=?', (normalize_nl(street), number)).fetchall()
        expect((code, place) in found, f'index has {street} {number}, {code} {place} ({found})')
    if not SAMPLE_ADDRESSES.get(CODE):
        print(f'note  no sample addresses recorded for {REGION}; add a few from the BAG to SAMPLE_ADDRESSES')
    for island, (w, s, e, n) in ISLANDS.get(CODE, []):
        count = addr.execute('SELECT count(*) FROM addr WHERE district=? AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?',
                             (island, w, e, s, n)).fetchone()[0]
        expect(count >= MINIMUM['island_addresses'], f'island {island}: {count:,} addresses on the island')
    addr.close()
    places = sqlite3.connect(f"file:{geo / 'places.sqlite'}?mode=ro", uri=True)
    kinds = dict(places.execute('SELECT kind, count(*) FROM place GROUP BY kind'))
    for kind in ('place (woonplaats)', 'municipality (gemeente)', 'postcode area', 'postcode', 'street'):
        expect(kinds.get(kind, 0) > 0, f'place finder has {kinds.get(kind, 0):,} rows of kind {kind}')
    for island, _ in ISLANDS.get(CODE, []):
        hit = places.execute("SELECT count(*) FROM place WHERE name=? AND kind='municipality (gemeente)'", (island,)).fetchone()[0]
        expect(hit == 1, f'place finder has the island municipality {island}')
    beyond = places.execute('SELECT count(*) FROM place WHERE lon NOT BETWEEN ? AND ? OR lat NOT BETWEEN ? AND ?',
                            (west - .15, east + .15, south - .15, north + .15)).fetchone()[0]
    expect(beyond == 0, f'every place-finder row within {NAME} plus the margin ({beyond} beyond)')
    outlines = load_outlines()
    if outlines.get(CODE):
        claimed = places.execute("SELECT name, lon, lat FROM place WHERE source = 'OpenStreetMap' AND detail = ?",
                                 (f'{NAME} (OpenStreetMap)',)).fetchall()
        wrong = [name for name, lon, lat in claimed if (lon, lat) not in outlines[CODE]]
        expect(not wrong, f'every OpenStreetMap place labelled {NAME} lies inside its official outline '
                          f'({len(wrong)} do not{": " + ", ".join(wrong[:3]) if wrong else ""})')
    else:
        print(f'note  no official outlines in {SHARED.name}/ yet, so OpenStreetMap places are labelled {NAME} '
              f'(python3 tools/build_region_nl.py outline --province {CODE})')
    for place, country in EXCLAVES.get(CODE, []):
        labels = [d for d, in places.execute("SELECT detail FROM place WHERE name = ? AND source = 'OpenStreetMap'", (place,))]
        expect(bool(labels) and f'{NAME} (OpenStreetMap)' not in labels,
               f'exclave {place} ({country}) is in the place finder and not labelled {NAME} ({", ".join(sorted(set(labels))) or "not found"})')
    places.close()
    cut = (report.get('sources', {}).get('files', {}).get('bag') or {}).get('cut') or {}
    print(('ok    ' if cut else 'note  ') + 'build.json says how the BAG was cut: '
          + (f"{cut.get('field')} = {cut.get('value')} ({cut.get('compared')}; written {cut.get('as_written')!r})" if cut
             else f'not yet (outline --province {CODE} adds it)'))
    if not failures:
        print('all checks passed (the data; the app\'s address search has its own tests: app/tests/test_address_nl.py)')
    return failures


def demo():
    """A data folder for trying the map on its own: the app also needs a library, so this adds an empty one.

    The map files stay in data/ (what a map download would hold); demo/ links to them."""
    folder = BASE / 'demo'
    (folder / 'library-data').mkdir(parents=True, exist_ok=True)
    (folder / 'library-data' / 'catalog.json').write_text('[]\n', encoding='utf-8')
    link = folder / 'derived'
    if not link.exists():
        try:
            link.symlink_to(Path('..') / 'data' / 'derived', target_is_directory=True)
        except OSError:       # Windows without symlink rights: a copy works the same
            shutil.copytree(DATA / 'derived', link)
    print(f'python3 server.py --data {folder.relative_to(ROOT)} --no-index')


def merge(codes=None, out=None):
    """One map set for the whole country, derived/regions/NL/data, from the provinces already built: their streets,
    water, buildings and help points in one map, their place finders in one, and their address indexes beside it
    (linked, not copied). Nothing is downloaded. A road or a point near a province border is in both extracts: a point
    or a place is kept once, a line twice (it draws the same). Returns the data folder."""
    regions = ROOT / 'derived' / 'regions'
    wanted = list(codes or PROVINCES)
    built = [(c, regions / f'NL-{c}' / 'data' / 'derived' / 'geo') for c in wanted]
    built = [(c, g) for c, g in built if (g / 'national.sqlite').is_file() and (g / 'places.sqlite').is_file()]
    if not built:
        raise SystemExit('no built province found: build one or more first (build --province ...)')
    missing = [c for c in wanted if c not in {c for c, _ in built}]
    if missing:
        log('not built, so not in the merged map:', ', '.join(missing))
    base = out or regions / 'NL'
    data, staging = base / 'data', base / 'data.new'
    if staging.exists():
        shutil.rmtree(staging)
    geo = staging / 'derived' / 'geo'
    (geo / 'addresses').mkdir(parents=True)
    started = time.time()

    first = sqlite3.connect(built[0][1] / 'national.sqlite')
    schema = [sql for name, sql in first.execute('SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL')
              if not name.startswith('feat_idx_')]                      # the R-tree makes its own shadow tables
    first.close()
    db = sqlite3.connect(geo / 'national.sqlite')
    db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA page_size=8192;')
    for sql in schema:
        db.execute(sql)
    bounds, as_of, kept, twice, aed_note = [], [], 0, 0, ''
    for code, g in built:
        log('merging', f'NL-{code}')
        db.execute('ATTACH ? AS src', (str(g / 'national.sqlite'),))
        offset = db.execute('SELECT coalesce(max(id), 0) FROM main.feat').fetchone()[0]
        db.execute('INSERT INTO main.feat SELECT id + ?, layer, cls, name, minz, geom FROM src.feat', (offset,))
        db.execute('INSERT INTO main.feat_idx SELECT id + ?, minx, maxx, miny, maxy, minz, maxz FROM src.feat_idx', (offset,))
        before = db.execute('SELECT count(*) FROM main.poi').fetchone()[0]
        offered = db.execute('SELECT count(*) FROM src.poi').fetchone()[0]
        db.execute('INSERT INTO main.poi(cls, name, lon, lat) SELECT s.cls, s.name, s.lon, s.lat FROM src.poi s '
                   'WHERE NOT EXISTS (SELECT 1 FROM main.poi p WHERE p.cls = s.cls '
                   'AND p.lon BETWEEN s.lon - 1e-6 AND s.lon + 1e-6 AND p.lat BETWEEN s.lat - 1e-6 AND s.lat + 1e-6 '
                   "AND coalesce(p.name, '') = coalesce(s.name, ''))")
        added = db.execute('SELECT count(*) FROM main.poi').fetchone()[0] - before
        kept, twice = kept + added, twice + offered - added
        meta = dict(db.execute('SELECT key, value FROM src.meta').fetchall())
        if meta.get('bounds'):
            bounds.append([float(v) for v in meta['bounds'].split(',')])
        if meta.get('data_as_of'):
            as_of.append(meta['data_as_of'])
        if '; ' in meta.get('help_points', ''):       # AEDs, SEH: where they come from
            aed_note = meta['help_points'].split('; ', 1)[1]
        db.commit()
        db.execute('DETACH src')
    box = ','.join(f'{v:.4f}' for v in (min(b[0] for b in bounds), min(b[1] for b in bounds),
                                        max(b[2] for b in bounds), max(b[3] for b in bounds)))
    db.executemany('INSERT OR REPLACE INTO meta VALUES (?, ?)', [
        ('region', 'NL'), ('bounds', box), ('built', time.strftime('%Y-%m-%dT%H:%M:%S')),
        ('data_as_of', min(as_of) if as_of else ''),
        ('source', 'OpenStreetMap contributors, via Geofabrik province extracts (ODbL 1.0): '
                   + ', '.join(f'NL-{c}' for c, _ in built)),
        ('help_points', 'all classes: OpenStreetMap (ODbL 1.0)' + (f'; {aed_note}' if aed_note else ''))])
    db.commit()
    db.close()

    # map.sqlite: the same small file each province has, saying which region this is.
    shutil.copyfile(built[0][1] / 'map.sqlite', geo / 'map.sqlite')
    m = sqlite3.connect(geo / 'map.sqlite')
    m.executemany('INSERT OR REPLACE INTO meta VALUES (?, ?)', [('region', 'NL'), ('bounds', box)])
    m.commit()
    m.close()
    if (built[0][1] / 'socal-cells.json').exists():
        shutil.copyfile(built[0][1] / 'socal-cells.json', geo / 'socal-cells.json')

    # places.sqlite: every province's places, once (a street or a place on a border is in both).
    p = sqlite3.connect(geo / 'places.sqlite')
    p.executescript(
        'CREATE TABLE place(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, detail TEXT, lat REAL, lon REAL, rank INTEGER, source TEXT);'
        "CREATE VIRTUAL TABLE place_fts USING fts5(name, detail, content='place', content_rowid='id', tokenize='unicode61');"
        'CREATE INDEX place_key ON place(name, kind);')
    for code, g in built:
        p.execute('ATTACH ? AS src', (str(g / 'places.sqlite'),))
        p.execute('INSERT INTO place(name, kind, detail, lat, lon, rank, source) '
                  'SELECT s.name, s.kind, s.detail, s.lat, s.lon, s.rank, s.source FROM src.place s '
                  'WHERE NOT EXISTS (SELECT 1 FROM main.place q WHERE q.name = s.name AND q.kind = s.kind '
                  "AND coalesce(q.detail, '') = coalesce(s.detail, '') AND abs(q.lat - s.lat) < 0.002 AND abs(q.lon - s.lon) < 0.002)")
        p.commit()
        p.execute('DETACH src')
    p.execute('DROP INDEX place_key')
    p.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
    p.commit()
    places = p.execute('SELECT count(*) FROM place').fetchone()[0]
    p.close()

    # The address indexes stay where they are: a link each, so ten million addresses are not copied.
    for code, g in built:
        index = g / 'addresses' / f'NL-{code}.sqlite'
        if index.exists():
            (geo / 'addresses' / index.name).symlink_to(index.resolve())

    report = {'region': 'NL', 'merged': [f'NL-{c}' for c, _ in built], 'not_built': [f'NL-{c}' for c in missing],
              'help_points': kept, 'help_points_in_two_provinces': twice, 'places': places,
              'seconds': round(time.time() - started)}
    (staging / 'build.json').write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    if data.exists():
        shutil.rmtree(data)
    staging.rename(data)
    log('whole country:', len(built), 'provinces,', kept, 'help points,', places, 'places, in', report['seconds'], 's ->',
        data / 'derived' / 'geo')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('step', choices=('fetch', 'build', 'check', 'demo', 'merge', 'aed', 'seh', 'outline'))
    parser.add_argument('--province', required=True, help='two-letter code (' + ', '.join(PROVINCES) + ') or all')
    parser.add_argument('--refresh', action='store_true', help='fetch, aed, seh: download the OpenStreetMap extract, the AEDs and the SEH list even if recent')
    parser.add_argument('--overpass', help='fetch, aed: the Overpass instance to ask first (its .../api/interpreter URL)')
    args = parser.parse_args()
    if args.step == 'merge':      # the provinces already built, as one map of the whole country
        merge(None if args.province.lower() == 'all' else [c.strip().upper().removeprefix('NL-') for c in args.province.split(',')])
        return
    global REFRESH
    REFRESH = args.refresh
    if args.overpass:
        OVERPASS[:] = [args.overpass] + [u for u in OVERPASS if u != args.overpass]
    codes = list(PROVINCES) if args.province.lower() == 'all' else [args.province]
    if args.step == 'fetch':
        try:
            fetch_boxes()
        except (SystemExit, OSError, ValueError, urllib.error.URLError) as error:
            log('province boundaries not available, the fallback boxes are used:', error)
    failed = []
    for code in codes:
        select(code)
        if len(codes) > 1:
            log('====', REGION, NAME)
        if args.step == 'check':
            if check():
                failed.append(REGION)
            continue
        try:
            {'fetch': fetch, 'build': build, 'demo': demo, 'aed': aed, 'seh': seh, 'outline': outline}[args.step]()
        except SystemExit as error:     # with all provinces, one that fails does not stop the others
            if len(codes) == 1:
                raise
            log(REGION, 'failed:', error)
            failed.append(REGION)
    if args.step == 'seh' and len(codes) == len(PROVINCES) and (SHARED / 'seh.xlsx').is_file():
        unplaced = [f"{s['name']} ({s['postcode']})" for s in seh_locations(SHARED / 'seh.xlsx')
                    if (s['name'], s['postcode']) not in SEH_PLACED]
        log('SEHs placed:', len(SEH_PLACED), '; not found at their address in any province:', ', '.join(unplaced) or 'none')
    if failed:
        again = ' '.join(r.removeprefix('NL-') for r in failed)
        raise SystemExit(f'{args.step} not finished for {", ".join(failed)}; run it again for those '
                         f'(for code in {again}; do python3 tools/build_region_nl.py {args.step} --province $code; done)')


if __name__ == '__main__':
    main()
