#!/usr/bin/env python3
"""Offline Dutch province builder: python3 -B -m unittest app.tests.test_build_region_nl.

No network: the BAG and boundary services are stand-ins that answer as PDOK does, and the OpenStreetMap extract is a
small GeoPackage written here, so whole builds and their checks run on made-up provinces: Zuid-Holland around Delft,
and Fryslân with Leeuwarden and the four Frisian Wadden islands."""
import gzip
import json
import sqlite3
import struct
import tempfile
import unittest
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path
from unittest import mock

import tools.build_region_nl as nl


def gpkg(wkb):
    """A GeoPackage geometry blob: magic, version, flags (little-endian, no envelope), SRS 4326, WKB."""
    return b'GP' + bytes([0, 1]) + struct.pack('<i', 4326) + wkb


def point(x, y):
    return struct.pack('<BIdd', 1, 1, x, y)


def line(*xy):
    return struct.pack('<BII', 1, 2, len(xy)) + b''.join(struct.pack('<dd', *p) for p in xy)


def square(x, y, d=0.001):
    ring = [(x, y), (x + d, y), (x + d, y + d), (x, y + d), (x, y)]
    return struct.pack('<BII', 1, 3, 1) + struct.pack('<I', len(ring)) + b''.join(struct.pack('<dd', *p) for p in ring)


def osm_extract(path, roads, pois, places=(), ferries=None):
    """The tables tools/build_map.py reads from a Geofabrik GeoPackage. roads: (x, y) starts of short streets; pois:
    (class, name, x, y); ferries: (name, x, y) in a transport layer, or None for an extract without one."""
    db = sqlite3.connect(path)
    for table in ('gis_osm_water_a_free', 'gis_osm_natural_a_free', 'gis_osm_landuse_a_free', 'gis_osm_waterways_free',
                  'gis_osm_railways_free', 'gis_osm_buildings_a_free', 'gis_osm_pois_free', 'gis_osm_pois_a_free',
                  'gis_osm_natural_free'):
        db.execute(f'CREATE TABLE {table}(geom BLOB, fclass TEXT, name TEXT)')
    db.execute('CREATE TABLE gis_osm_protected_areas_a_free(geom BLOB, fclass TEXT)')
    db.execute('CREATE TABLE gis_osm_roads_free(geom BLOB, fclass TEXT, name TEXT, ref TEXT)')
    db.execute('CREATE TABLE gis_osm_places_free(geom BLOB, fclass TEXT, population INTEGER, name TEXT)')
    db.executemany('INSERT INTO gis_osm_roads_free VALUES (?,?,?,?)',
                   [(gpkg(line((x, y), (x + 0.001, y + 0.001))), 'residential', 'Straat', None) for x, y in roads])
    db.executemany('INSERT INTO gis_osm_pois_free VALUES (?,?,?)', [(gpkg(point(x, y)), cls, name) for cls, name, x, y in pois])
    db.execute('INSERT INTO gis_osm_buildings_a_free VALUES (?,?,?)', (gpkg(square(*roads[0])), 'house', None))
    db.executemany('INSERT INTO gis_osm_places_free VALUES (?,?,?,?)', [(gpkg(point(x, y)), cls, 0, name) for cls, name, x, y in places])
    if ferries is not None:
        db.execute('CREATE TABLE gis_osm_transport_free(geom BLOB, fclass TEXT, name TEXT)')
        db.executemany('INSERT INTO gis_osm_transport_free VALUES (?,?,?)',
                       [(gpkg(point(x, y)), 'ferry_terminal', name) for name, x, y in ferries] +
                       [(gpkg(point(5.80, 53.20)), 'bus_stop', 'Station')])
    db.commit()
    db.close()


def feature(i, street='Mekelweg', number='2', letter=None, addition=None, code='2628CD', place='Delft', town=None,
            prov='ZH', prov_name='Zuid-Holland', lon=4.3735, lat=51.9990):
    """One address as PDOK's OGC API gives it."""
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'properties': {
        'identificatie': f'03632000{i:08d}', 'openbare_ruimte_naam': street, 'huisnummer': number, 'huisletter': letter,
        'toevoeging': addition, 'postcode': code, 'woonplaats_naam': place, 'bronhouder_naam': town or place,
        'provincie_afkorting': prov, 'provincie_naam': prov_name, 'adresseerbaar_object_type': 'Verblijfsobject'}}


def seh_xlsx(path, rows, sheet='Reguliere vragenlijst'):
    """A workbook as the RIVM publishes its SEH answers, cut down to the columns read: a reading guide first, then the
    answers, with two rows above the header as in the real file. Written with the standard library only."""
    header = ['Naam ziekenhuis', 'Plaats', 'Adres', 'Postcode',
              'Volgens onze informatie heeft uw ziekenhuis het aanbod aan SEH en acute verloskunde zoals hiernaast aangegeven:',
              'Toelichting indien anders:', 'Heeft uw ziekenhuislocatie een spoedeisende hulpafdeling en wat zijn de openingstijden van deze SEH?',
              'Overdag (circa 08-17 uur)', '’s Avonds (circa 17-23 uur)', '’s Nachts (circa 23-08 uur)', 'Wat is het aantal SEH-behandelkamers?',
              'Overdag', 'Is er op deze ziekenhuislocatie een huisartsenpost (HAP) aanwezig?']
    table = [['Vraag Kwaliteitskader'], [None, None, 'Deel 1'], header] + rows

    def cell(r, c, v):
        ref = ''
        c += 1
        while c:
            c, rest = divmod(c - 1, 26)
            ref = chr(65 + rest) + ref
        text = str(v).replace('&', '&amp;').replace('<', '&lt;')
        return f'<c r="{ref}{r}" t="inlineStr"><is><t>{text}</t></is></c>'
    sheet_xml = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                 + ''.join(f'<row r="{i + 1}">' + ''.join(cell(i + 1, j, v) for j, v in enumerate(row) if v is not None) + '</row>'
                           for i, row in enumerate(table)) + '</sheetData></worksheet>')
    guide = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">'
             '<c r="A1" t="inlineStr"><is><t>Overzicht</t></is></c></row></sheetData></worksheet>')
    with zipfile.ZipFile(path, 'w') as book:
        book.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                      '<sheet name="Leeswijzer" sheetId="1" r:id="rId1"/>'
                      f'<sheet name="{sheet}" sheetId="2" r:id="rId2"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                      '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/>'
                      '</Relationships>')
        book.writestr('xl/worksheets/sheet1.xml', guide)
        book.writestr('xl/worksheets/sheet2.xml', sheet_xml)
    return path


SEH_ROWS = [
    ['Reinier de Graaf', 'Delft', 'Reinier de Graafweg 3-11', '2625 AD', 'Zowel een SEH alsook acute verloskunde', None,
     'De SEH is 24 uur per dag 7 dagen per week (24/7) geopend', None, None, None, '30', None,
     'Ja, de HAP is in het ziekenhuis gevestigd en heeft een gezamenlijke ingang met de SEH'],
    ['Franciscus Vlietland', 'Schiedam', 'Vlietlandplein 2', '3118 JH', 'Wel een SEH (dag- en avond openstelling), geen acute verloskunde',
     None, 'De SEH is niet 24/7 geopend maar heeft beperkte openingstijden:', 'Doordeweeks_x000D_\nWeekend/feestdagen',
     'Doordeweeks', None, '12', 'Doordeweeks', 'Nee'],
    ['Ziekenhuis Elders', 'Groningen', 'Hanzeplein 1', '9713 GZ', 'Zowel een SEH alsook acute verloskunde', None,
     'De SEH is 24 uur per dag 7 dagen per week (24/7) geopend', None, None, None, '40', None, 'Nee'],
]


class Spelling(unittest.TestCase):
    def test_street_keys(self):
        self.assertEqual(nl.normalize_nl('Burg. Jansenstraat'), 'burg jansenstr')
        self.assertEqual(nl.normalize_nl('Ruïnelaan'), 'ruinelaan')
        self.assertEqual(nl.normalize_nl("'s-Gravenhage"), 's gravenhage')
        self.assertEqual(nl.normalize_nl('Straat'), 'straat')                 # a street called just "Straat" keeps its name
        self.assertEqual(nl.normalize_nl('Mekelweg'), nl.normalize_nl('MEKELWEG'))

    def test_house_numbers_and_postcodes(self):
        self.assertEqual(nl.house('374', 'a'), '374A')
        self.assertEqual(nl.house('012', None, '3'), '12-3')
        self.assertEqual(nl.house('6', None, 'BS'), '6-BS')                   # Jansdam 6-BS, Utrecht
        self.assertEqual(nl.house('', 'A'), '')
        self.assertEqual(nl.postcode('2628 cd'), '2628CD')
        self.assertEqual(nl.postcode('0123AB'), '')                          # Dutch postcodes never start with 0
        self.assertEqual(nl.postcode(None), '')


class Provinces(unittest.TestCase):
    def test_every_province_has_a_name_a_code_and_a_box(self):
        self.assertEqual(len(nl.PROVINCES), 12)
        self.assertEqual(sorted(v[2] for v in nl.PROVINCES.values()), [str(n) for n in range(20, 32)])   # CBS PV20-PV31
        for code, (name, slug, cbs, (w, s, e, n)) in nl.PROVINCES.items():
            with self.subTest(code=code):
                self.assertTrue(3.2 < w < e < 7.3 and 50.7 <= s < n < 53.7, (w, s, e, n))
                self.assertRegex(slug, r'^[a-z-]+$')
        with self.assertRaises(SystemExit):
            nl.select('XX')

    def test_islands_lie_in_their_province(self):
        for code, islands in nl.ISLANDS.items():
            w, s, e, n = nl.PROVINCES[code][3]
            for island, (iw, i_s, ie, i_n) in islands:
                with self.subTest(island=island):
                    self.assertTrue(w <= iw < ie <= e and s <= i_s < i_n <= n, island)
        # each island has a sample address of its own, by its main village
        places = {place for rows in nl.SAMPLE_ADDRESSES.values() for *_, place in rows}
        self.assertLessEqual({'Oudeschild', 'Vlieland', 'West-Terschelling', 'Nes', 'Schiermonnikoog'}, places)
        self.assertEqual(sorted(i for v in nl.ISLANDS.values() for i, _ in v),
                         ['Ameland', 'Schiermonnikoog', 'Terschelling', 'Texel', 'Vlieland'])

    def test_province_codes_are_matched_without_case_and_accents(self):
        """PDOK writes 'ZH', 'NH' and 'NB' but 'Fr', 'Gr' and 'Ut'; and Fryslân has an accent."""
        self.assertTrue(nl.in_province({'prov': 'Fr', 'prov_name': 'Fryslân'}, 'FR', 'Fryslân'))
        self.assertTrue(nl.in_province({'prov': None, 'prov_name': 'Frysla\u0302n'}, 'FR', 'Fryslân'))   # decomposed â
        self.assertTrue(nl.in_province({'prov': 'ut', 'prov_name': None}, 'UT', 'Utrecht'))
        self.assertFalse(nl.in_province({'prov': 'Gr', 'prov_name': 'Groningen'}, 'FR', 'Fryslân'))
        self.assertFalse(nl.in_province({}, 'FR', 'Fryslân'))

    def test_every_province_has_sample_addresses(self):
        self.assertEqual(set(nl.SAMPLE_ADDRESSES), set(nl.PROVINCES))
        for code, rows in nl.SAMPLE_ADDRESSES.items():
            for street, number, code6, place in rows:
                with self.subTest(code=code, street=street):
                    self.assertEqual(nl.postcode(code6), code6)
                    self.assertRegex(number, r'^[1-9][0-9]*[A-Z]?(-[A-Z0-9]+)?$')


class Boxes(unittest.TestCase):
    """Each province's box comes from its official boundary, islands included, and the BAG grid is one for the country."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(nl, 'SHARED', Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_boxes_from_the_boundaries_include_far_islands(self):
        mainland = [[[5.4, 52.8], [6.4, 52.8], [6.4, 53.3], [5.4, 53.3], [5.4, 52.8]]]
        vlieland = [[[4.87, 53.22], [5.10, 53.22], [5.10, 53.30], [4.87, 53.30], [4.87, 53.22]]]
        answer = {'timeStamp': '2026-11-25T10:00:00Z', 'features': [
            {'properties': {'naam': 'Fryslân', 'code': '21'}, 'geometry': {'type': 'MultiPolygon', 'coordinates': [mainland, vlieland]}},
            {'properties': {'naam': 'Unknown', 'code': 'PV24'}, 'geometry': {'type': 'Polygon', 'coordinates': mainland}}]}
        with mock.patch.object(nl, 'get_json', lambda url: answer):
            nl.fetch_boxes()
        saved = json.loads((nl.SHARED / 'provinces.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['boxes']['FR'], [4.87, 52.8, 6.4, 53.3])
        self.assertIn('FL', saved['boxes'])                                  # matched by its CBS code
        self.assertIn('GR', saved['fallback_for'])
        self.assertEqual(saved['licence'], nl.BOUNDARY_LICENCE)
        outlines = json.loads((nl.SHARED / 'outlines.json').read_text(encoding='utf-8'))
        self.assertEqual(outlines['outlines']['FR']['coordinates'], [mainland, vlieland])     # kept for labelling places
        nl.select('FR')
        self.assertEqual(nl.BBOX, (4.86, 52.79, 6.41, 53.31))                 # with the margin
        nl.select('GR')
        self.assertEqual(nl.BBOX, nl.PROVINCES['GR'][3])                      # no official box: the fallback

    def test_cells_cover_the_box_on_one_grid(self):
        cells = nl.tiles((4.86, 52.79, 6.41, 53.31))
        boxes = [nl.tile_box(c) for c in cells]
        self.assertLessEqual(min(b[0] for b in boxes), 4.86)
        self.assertLessEqual(min(b[1] for b in boxes), 52.79)
        self.assertGreaterEqual(max(b[2] for b in boxes), 6.41)
        self.assertGreaterEqual(max(b[3] for b in boxes), 53.31)
        shared = set(nl.tiles(nl.PROVINCES['ZH'][3])) & set(nl.tiles(nl.PROVINCES['UT'][3]))
        self.assertTrue(shared)                                               # a border cell is the same cell for both


class FetchTile(unittest.TestCase):
    def test_pages_follow_next_and_keep_every_province(self):
        pages = {
            'first': {'timeStamp': '2026-11-25T10:00:00Z', 'links': [{'rel': 'next', 'href': 'second'}],
                      'features': [feature(1), feature(2, prov='Ut', prov_name='Utrecht')]},
            'second': {'links': [], 'features': [feature(3, number='4')]},
        }
        asked = []

        def answer(url, tries=None):
            asked.append(url)
            return pages['first' if url.startswith(nl.BAG_API) else url]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(nl, 'SHARED', Path(tmp)), \
                mock.patch.object(nl, 'get_json', answer):
            path, stamp = nl.fetch_tile((87, 1039))
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                rows = [json.loads(line) for line in f]
            again = nl.fetch_tile((87, 1039))
        self.assertEqual(stamp, '2026-11-25T10:00:00Z')
        self.assertEqual([(r['number'], r['prov']) for r in rows], [('2', 'ZH'), ('2', 'Ut'), ('4', 'ZH')])
        self.assertIn('bbox=4.35%2C51.95%2C4.4%2C52.0', asked[0])
        self.assertEqual(len(asked), 2)                                      # the finished cell is not asked again
        self.assertEqual(again[1], None)


class FetchResumes(unittest.TestCase):
    """A cell PDOK keeps failing on is left for the next fetch; the others are fetched and kept."""

    def test_failing_cell_leaves_the_rest_done(self):
        nl.select('FL')
        cells = nl.tiles()[:3]
        bad = nl.tile_box(cells[1])

        def answer(url, tries=None):      # the network fails for this cell (not a 500): no splitting
            if 'bbox=' + '%2C'.join(map(str, bad)) in url:
                raise SystemExit('connection reset')
            return {'links': [], 'features': []}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(nl, 'SHARED', Path(tmp)), \
                mock.patch.object(nl, 'get_json', answer), mock.patch.object(nl, 'log', lambda *a: None):
            results = [nl.try_cell(c) for c in cells]
            done = [nl.tile_path(c).exists() for c in cells]
        self.assertEqual(done, [True, False, True])
        self.assertEqual(results[1], (None, None))


class FakePDOK:
    """The BAG OGC API in miniature: addresses in a box, PAGE at a time, each page linking the next with a cursor.
    fail(box, offset) says which pages answer HTTP 500, every time they are asked."""

    def __init__(self, points, fail):
        self.points, self.fail, self.asked = points, fail, []

    def __call__(self, url, tries=None):
        import urllib.parse as up
        q = dict(up.parse_qsl(up.urlsplit(url).query))
        box = tuple(float(v) for v in q['bbox'].split(','))
        offset = int(q.get('cursor', 0))
        self.asked.append((box, offset))
        if self.fail(box, offset):
            raise nl.ServerError(f'{url}: HTTP Error 500: Internal Server Error; run fetch again')
        inside = [f for f in self.points if box[0] <= f['geometry']['coordinates'][0] <= box[2]
                  and box[1] <= f['geometry']['coordinates'][1] <= box[3]]
        page = inside[offset:offset + nl.PAGE]
        links = [{'rel': 'next', 'href': url.split('&cursor=')[0] + f'&cursor={offset + nl.PAGE}'}] if offset + nl.PAGE < len(inside) else []
        return {'timeStamp': '2026-11-26T06:00:00Z', 'features': page, 'links': links}


class SplitOnServerErrors(unittest.TestCase):
    """PDOK answers some deep pages of a busy cell with HTTP 500 every time (25-26 November 2026): the cell is split."""

    CELL = (87, 1040)          # 4.35-4.40 E, 52.00-52.05 N

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for target, value in (('SHARED', Path(tmp.name)), ('PAGE', 3), ('log', lambda *a: None)):
            patcher = mock.patch.object(nl, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        w, s, e, n = nl.tile_box(self.CELL)
        self.points = [feature(i, number=str(i), lon=w + 0.0013 + (i % 6) * 0.0081, lat=s + 0.0017 + (i // 6) * 0.0079)
                       for i in range(36)]

    def rows(self):
        with gzip.open(nl.tile_path(self.CELL), 'rt', encoding='utf-8') as f:
            return [json.loads(line) for line in f]

    def test_deep_pages_failing_on_the_whole_cell(self):
        server = FakePDOK(self.points, lambda box, offset: offset >= 6 and box[2] - box[0] > 0.04)
        with mock.patch.object(nl, 'get_json', server):
            nl.fetch_tile(self.CELL)
        self.assertEqual(sorted(r['number'] for r in self.rows()), sorted(str(i) for i in range(36)))   # all, once
        self.assertFalse(nl.holes_path(self.CELL).exists())

    def test_one_bad_spot_is_a_hole_that_the_next_fetch_fills(self):
        bad = self.points[14]['geometry']['coordinates']

        def fail(box, offset):
            return box[0] <= bad[0] <= box[2] and box[1] <= bad[1] <= box[3]
        with mock.patch.object(nl, 'get_json', FakePDOK(self.points, fail)):
            nl.fetch_tile(self.CELL)
        holes = json.loads(nl.holes_path(self.CELL).read_text(encoding='utf-8'))['holes']
        self.assertEqual(len(holes), 1)
        w, s, e, n = holes[0]
        self.assertTrue(w <= bad[0] <= e and s <= bad[1] <= n)
        self.assertLessEqual(e - w, nl.TILE / 2 ** nl.SPLIT_DEPTH + 1e-9)            # about 200 m
        self.assertEqual(len(self.rows()), 35)                                     # everything but the one spot
        self.assertEqual(nl.cell_holes([self.CELL]), [(self.CELL, holes[0])])
        server = FakePDOK(self.points, lambda box, offset: False)                    # PDOK serves it later
        with mock.patch.object(nl, 'get_json', server):
            nl.fetch_tile(self.CELL)
        self.assertEqual([b for b, _ in server.asked], [tuple(holes[0])])          # only the hole is asked for
        self.assertEqual(len(self.rows()), 36)
        self.assertFalse(nl.holes_path(self.CELL).exists())

    def test_an_outage_is_not_split_into_thousands_of_asks(self):
        calls = []

        def down(url, tries=None):
            calls.append(url)
            raise SystemExit(f'{url}: <urlopen error timed out>')
        with mock.patch.object(nl, 'get_json', down):
            self.assertEqual(nl.try_cell(self.CELL), (None, None))
        self.assertEqual(len(calls), 1)
        self.assertFalse(nl.tile_path(self.CELL).exists())

    def test_get_json_stops_asking_once_pdok_is_down(self):
        with mock.patch.dict(nl.FAILS, {'in_a_row': nl.GIVE_UP}), \
                mock.patch.object(nl.urllib.request, 'urlopen', side_effect=AssertionError('must not ask')):
            with self.assertRaises(SystemExit) as raised:
                nl.get_json('https://api.pdok.nl/x')
        self.assertNotIsInstance(raised.exception, nl.ServerError)

    def test_get_json_tells_a_500_from_a_network_failure(self):
        import urllib.error
        e500 = urllib.error.HTTPError('u', 500, 'Internal Server Error', {}, None)
        with mock.patch.dict(nl.FAILS, {'in_a_row': 0}), mock.patch.object(nl.time, 'sleep'):
            with mock.patch.object(nl.urllib.request, 'urlopen', side_effect=e500), self.assertRaises(nl.ServerError):
                nl.get_json('https://api.pdok.nl/x', 2)
            with mock.patch.object(nl.urllib.request, 'urlopen', side_effect=TimeoutError('timed out')), \
                    self.assertRaises(SystemExit) as raised:
                nl.get_json('https://api.pdok.nl/x', 2)
            self.assertNotIsInstance(raised.exception, nl.ServerError)
            self.assertEqual(nl.FAILS['in_a_row'], 2)

    def test_build_without_a_finished_fetch_says_so(self):
        nl.select('GR')
        with tempfile.TemporaryDirectory() as tmp, mock.patch.multiple(nl, SOURCE=Path(tmp) / 'source', BASE=Path(tmp)):
            with self.assertRaises(SystemExit) as raised:
                nl.build()
        self.assertIn('fetch --province GR', str(raised.exception))


def flat(f):
    """A feature as fetch_tile keeps it."""
    p = f['properties']
    return {'id': p['identificatie'], 'street': p['openbare_ruimte_naam'], 'number': p['huisnummer'], 'letter': p['huisletter'],
            'addition': p['toevoeging'], 'postcode': p['postcode'], 'place': p['woonplaats_naam'],
            'municipality': p['bronhouder_naam'], 'prov': p['provincie_afkorting'], 'prov_name': p['provincie_naam'],
            'type': 'Verblijfsobject', 'lon': f['geometry']['coordinates'][0], 'lat': f['geometry']['coordinates'][1]}


class WholeBuild(unittest.TestCase):
    """fetch's output in, a checked data folder out."""

    LOW = {'roads': 10, 'addresses': 100, 'hospital': 1, 'pharmacy': 1, 'fire_station': 1, 'police': 1,
           'island_roads': 3, 'island_addresses': 20, 'aeds': 2}

    def build(self, code, features, roads, pois, places=(), ferries=None, aeds=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        shared, base = root / 'NL-shared', root / f'NL-{code}'
        source = base / 'source'
        source.mkdir(parents=True)
        if getattr(self, 'seh_rows', None):
            shared.mkdir(parents=True, exist_ok=True)
            seh_xlsx(shared / 'seh.xlsx', self.seh_rows)
        with mock.patch.object(nl, 'SHARED', shared):
            nl.select(code)
            if getattr(self, 'outlines', None):
                shared.mkdir(parents=True, exist_ok=True)
                nl.save_outlines({'timeStamp': '2026-11-28T10:00:00Z'}, self.outlines)
            cells = {}
            for f in features:
                lon, lat = f['geometry']['coordinates']
                cells.setdefault((int(lon // nl.TILE), int(lat // nl.TILE)), []).append(flat(f))
            cells.setdefault(next(iter(cells)), []).append(flat(features[0]))      # an address on a cell edge, twice
            for cell, rows in cells.items():
                nl.tile_path(cell).parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(nl.tile_path(cell), 'wt', encoding='utf-8') as out:
                    out.writelines(json.dumps(r) + '\n' for r in rows)
            extract = root / 'extract.gpkg'
            osm_extract(extract, roads, pois, places, ferries)
            with zipfile.ZipFile(source / 'osm.gpkg.zip', 'w') as archive:
                archive.write(extract, f'{nl.SLUG}-latest-free.gpkg')
            fetched = {'fetched': '2026-11-25T10:00:00+00:00', 'files': {
                'osm.gpkg.zip': {'name': f'{nl.SLUG}-261124.gpkg.zip', 'data_as_of': '2026-11-24T21:00:00Z'},
                'bag': {'served_at': '2026-11-25T10:00:00Z'}}}
            (source / 'fetched.json').write_text(json.dumps(fetched), encoding='utf-8')
            if aeds is not None:
                (source / 'aeds.json').write_text(json.dumps({'fetched': '2026-11-26T18:00:00+00:00', 'osm_as_of': '2026-11-26T17:55:00Z',
                                                              'points': aeds, 'not_public_left_out': 0}), encoding='utf-8')
            with mock.patch.multiple(nl, BASE=base, SOURCE=source, DATA=base / 'data', MINIMUM=self.LOW, log=lambda *a: None):
                try:
                    nl.build()
                    data = base / 'data'
                except SystemExit:          # its checks failed: the build stays in data.new to look at
                    data = base / 'data.new'
                failures = nl.check(data)
        return failures, data / 'derived' / 'geo'

    def test_zuid_holland(self):
        features = [feature(i, number=str(i), lon=4.3700 + i * 1e-5) for i in range(1, 400)]
        features += [feature(1000, street='Rotterdamseweg', number='374', letter='A', code='2629HG'),
                     feature(1001, street='Lorentzweg', number='1', code='2628CJ'), feature(1002, number='4'),
                     feature(1003, street='Burg. Jansenstraat', number='7', code='2611AA', place='Den Haag'),
                     feature(1005, number='2', addition='ts', code=None),        # an outbuilding: no postcode, as in the BAG
                     feature(1004, street='Jansdam', number='6', addition='BS', code='3512HB', place='Utrecht',
                             prov='Ut', prov_name='Utrecht', lon=5.12, lat=52.09)]      # another province: left out
        roads = [(4.37 + i * 1e-4, 52.0) for i in range(30)]
        pois = [('hospital', 'Reinier de Graaf', 4.36, 52.01), ('pharmacy', 'Apotheek Delft', 4.358, 52.012),
                ('fire_station', 'Kazerne Delft', 4.355, 52.0), ('police', 'Politie Delft', 4.357, 52.008)]
        failures, geo = self.build('ZH', features, roads, pois, [('town', 'Delft', 4.357, 52.011)])
        self.assertEqual(failures, [])
        addr = sqlite3.connect(geo / 'addresses' / 'NL-ZH.sqlite')
        self.assertEqual(addr.execute('SELECT count(*) FROM addr').fetchone()[0], 404)     # the duplicate once; Utrecht's out
        self.assertEqual(addr.execute("SELECT zip FROM addr WHERE num='2-ts'").fetchall(), [('',)])
        self.assertEqual(addr.execute("SELECT street,zip,city FROM addr WHERE norm='burg jansenstr' AND num='7'").fetchall(),
                         [('Burg. Jansenstraat', '2611AA', 'Den Haag')])
        self.assertEqual(dict(addr.execute('SELECT key,value FROM meta'))['norm'], 'nl-1')
        addr.close()
        places = sqlite3.connect(geo / 'places.sqlite')
        kinds = dict(places.execute('SELECT kind,count(*) FROM place GROUP BY kind'))
        hit = places.execute("SELECT kind FROM place_fts f JOIN place p ON p.id=f.rowid WHERE place_fts MATCH '\"2628 CD\"'").fetchall()
        osm = places.execute("SELECT source FROM place WHERE name='Reinier de Graaf'").fetchall()
        places.close()
        self.assertEqual(kinds['postcode area'], 3)                       # 2611, 2628 and 2629
        self.assertIn(('postcode',), hit)
        self.assertEqual(osm, [('OpenStreetMap',)])

    def test_fryslan_with_the_wadden_islands(self):
        """Leeuwarden and the four Frisian islands, each with its streets, its addresses and a ferry terminal."""
        islands = dict(nl.ISLANDS['FR'])
        samples = {place: (street, number, code) for street, number, code, place in nl.SAMPLE_ADDRESSES['FR']}
        town_of = {'Vlieland': 'Vlieland', 'West-Terschelling': 'Terschelling', 'Nes': 'Ameland',
                   'Schiermonnikoog': 'Schiermonnikoog', 'Leeuwarden': 'Leeuwarden'}
        centre = {'Leeuwarden': (5.79, 53.20)}
        for place, town in town_of.items():
            if town in islands:
                w, s, e, n = islands[town]
                centre[place] = ((w + e) / 2, (s + n) / 2)
        features, i = [], 0
        for place, (x, y) in centre.items():
            street, number, code = samples[place]
            features.append(feature(i := i + 1, street=street, number=number[:-1] if number[-1].isalpha() else number,
                                    letter=number[-1] if number[-1].isalpha() else None, code=code, place=place,
                                    town=town_of[place], prov='Fr', prov_name='Fryslân', lon=x, lat=y))
            features += [feature(i := i + 1, street='Dorpsstraat', number=str(k), code=code, place=place, town=town_of[place],
                                 prov='Fr', prov_name='Fryslân', lon=x + k * 1e-5, lat=y) for k in range(1, 30)]
        roads = [(x + k * 1e-4, y) for x, y in centre.values() for k in range(5)]
        pois = [('hospital', 'MCL', 5.80, 53.19), ('pharmacy', 'Apotheek', 5.79, 53.20),
                ('fire_station', 'Brandweer', 5.78, 53.20), ('police', 'Politie', 5.79, 53.21)]
        ferries = [('Veerhaven West-Terschelling', *centre['West-Terschelling']), ('Harlingen', 5.41, 53.17),
                   ('Newcastle', -1.4499, 54.9920)]          # the far end of a route that leaves from the province
        failures, geo = self.build('FR', features, roads, pois, ferries=ferries)
        self.assertEqual(failures, [])
        nat = sqlite3.connect(geo / 'national.sqlite')
        self.assertEqual(nat.execute("SELECT count(*) FROM poi WHERE cls='ferry_terminal'").fetchone()[0], 2)
        nat.close()
        addr = sqlite3.connect(geo / 'addresses' / 'NL-FR.sqlite')
        self.assertEqual(addr.execute("SELECT city,district FROM addr WHERE norm='heereweg' AND num='8'").fetchall(),
                         [('Schiermonnikoog', 'Schiermonnikoog')])
        addr.close()

    def test_a_saved_aed_list_goes_into_the_build(self):
        features = [feature(i, number=str(i), lon=4.3700 + i * 1e-5) for i in range(1, 200)]
        features += [feature(1000, street='Rotterdamseweg', number='374', letter='A', code='2629HG'),
                     feature(1001, street='Lorentzweg', number='1', code='2628CJ'), feature(1002, number='4'),
                     feature(1003, street='Burg. Jansenstraat', number='7', code='2611AA', place='Den Haag')]
        pois = [('hospital', 'Reinier de Graaf', 4.36, 52.01), ('pharmacy', 'Apotheek Delft', 4.358, 52.012),
                ('fire_station', 'Kazerne Delft', 4.355, 52.0), ('police', 'Politie Delft', 4.357, 52.008)]
        aeds = [['AED: gevel sporthal (24/7)', 4.36, 52.005], ['AED', 4.361, 52.006]]
        failures, geo = self.build('ZH', features, [(4.37 + i * 1e-4, 52.0) for i in range(30)], pois,
                                   [('town', 'Delft', 4.357, 52.011)], aeds=aeds)
        self.assertEqual(failures, [])
        nat = sqlite3.connect(geo / 'national.sqlite')
        self.assertEqual(sorted(n for n, in nat.execute("SELECT name FROM poi WHERE cls='defibrillator'")),
                         ['AED', 'AED: gevel sporthal (24/7)'])
        self.assertIn('AEDs: OpenStreetMap via the Overpass API', dict(nat.execute('SELECT key, value FROM meta'))['help_points'])
        nat.close()
        report = json.loads((geo.parents[1] / 'build.json').read_text(encoding='utf-8'))
        self.assertEqual(report['counts']['aeds'], 2)
        saved = report['sources']['files']['aeds.json']
        self.assertEqual((saved['points'], saved['file'], len(saved['sha256'])), (2, 'source/aeds.json', 64))

    def test_the_seh_list_goes_into_the_build(self):
        """Reinier de Graaf is placed at its BAG address in the built Zuid-Holland; Groningen's is not this province's."""
        features = [feature(i, number=str(i), lon=4.3700 + i * 1e-5) for i in range(1, 200)]
        features += [feature(1000, street='Rotterdamseweg', number='374', letter='A', code='2629HG'),
                     feature(1001, street='Lorentzweg', number='1', code='2628CJ'), feature(1002, number='4'),
                     feature(1003, street='Burg. Jansenstraat', number='7', code='2611AA', place='Den Haag'),
                     feature(1006, street='Reinier de Graafweg', number='5', code='2625AD', lon=4.36, lat=52.01)]
        pois = [('hospital', 'Reinier de Graaf', 4.36, 52.01), ('pharmacy', 'Apotheek Delft', 4.358, 52.012),
                ('fire_station', 'Kazerne Delft', 4.355, 52.0), ('police', 'Politie Delft', 4.357, 52.008)]
        self.seh_rows = SEH_ROWS
        failures, geo = self.build('ZH', features, [(4.37 + i * 1e-4, 52.0) for i in range(30)], pois,
                                   [('town', 'Delft', 4.357, 52.011)])
        self.assertEqual(failures, [])
        nat = sqlite3.connect(geo / 'national.sqlite')
        self.assertEqual([n for n, in nat.execute("SELECT name FROM poi WHERE cls='emergency_department'")],
                         ['SEH 24/7 · Reinier de Graaf (Delft) · huisartsenpost in het gebouw · acute verloskunde'])
        nat.close()
        report = json.loads((geo.parents[1] / 'build.json').read_text(encoding='utf-8'))
        xlsx = report['sources']['files']['seh.xlsx']['xlsx']
        self.assertEqual((xlsx['file'], len(xlsx['sha256'])), ('NL-shared/seh.xlsx', 64))
        self.assertEqual(report['sources']['files']['bag']['cut']['field'], 'provincie_afkorting')

    def test_an_island_left_out_fails_the_check(self):
        """A box or an extract that misses Schiermonnikoog must not pass as Fryslân."""
        features = [feature(i, street='Dorpsstraat', number=str(i), code='8911HG', place='Leeuwarden', prov='Fr',
                            prov_name='Fryslân', lon=5.79 + i * 1e-5, lat=53.20) for i in range(1, 200)]
        pois = [('hospital', 'MCL', 5.80, 53.19), ('pharmacy', 'Apotheek', 5.79, 53.20),
                ('fire_station', 'Brandweer', 5.78, 53.20), ('police', 'Politie', 5.79, 53.21)]
        failures, _ = self.build('FR', features, [(5.79 + k * 1e-4, 53.20) for k in range(20)], pois)
        self.assertTrue(any('island Schiermonnikoog' in f for f in failures), failures)
        self.assertTrue(any('Heereweg 8' in f for f in failures), failures)

    def brabant(self, places):
        """Noord-Brabant around 's-Hertogenbosch, with its sample addresses, help points and the given OSM places."""
        samples = nl.SAMPLE_ADDRESSES['NB']
        features = [feature(i, street=street, number=number.rstrip('F'), letter='F' if number.endswith('F') else None,
                            code=code, place=place, prov='NB', prov_name='Noord-Brabant', lon=5.30, lat=51.69)
                    for i, (street, number, code, place) in enumerate(samples, 1)]
        features += [feature(i, street='Kerkstraat', number=str(i), code='5211AB', place="'s-Hertogenbosch", prov='NB',
                             prov_name='Noord-Brabant', lon=5.30 + i * 1e-5, lat=51.69) for i in range(10, 130)]
        features += [feature(i, street='Dorpsstraat', number=str(i), code='5241AA', place='Rosmalen', town="'s-Hertogenbosch",
                             prov='NB', prov_name='Noord-Brabant', lon=5.36, lat=51.71 - i * 1e-5) for i in range(200, 210)]
        pois = [('hospital', 'Jeroen Bosch Ziekenhuis', 5.29, 51.70), ('pharmacy', 'Apotheek', 5.30, 51.69),
                ('fire_station', 'Brandweer', 5.31, 51.69), ('police', 'Politie', 5.30, 51.68)]
        return self.build('NB', features, [(5.30 + k * 1e-4, 51.69) for k in range(30)], pois, places)

    def test_an_exclave_is_labelled_outside_the_province(self):
        """Baarle-Hertog is Belgian ground inside Noord-Brabant: in the place finder, but not as Noord-Brabant."""
        self.outlines = {'NB': Outlines.BRABANT, 'ZE': Outlines.ZEELAND}
        failures, geo = self.brabant([('town', "'s-Hertogenbosch", 5.30, 51.69), ('village', 'Baarle-Hertog', 4.925, 51.445)])
        self.assertEqual(failures, [])
        places = sqlite3.connect(geo / 'places.sqlite')
        self.assertEqual(places.execute("SELECT detail FROM place WHERE name='Baarle-Hertog'").fetchall(),
                         [('outside the Dutch provinces (OpenStreetMap)',)])
        self.assertEqual(places.execute("SELECT detail FROM place WHERE name='Jeroen Bosch Ziekenhuis'").fetchall(),
                         [('Noord-Brabant (OpenStreetMap)',)])
        places.close()
        report = json.loads((geo.parents[1] / 'build.json').read_text(encoding='utf-8'))
        self.assertEqual(report['counts']['osm_places_outside'], {'other_province': 0, 'outside_provinces': 1})
        cut = report['sources']['files']
        self.assertEqual((cut['bag']['cut']['value'], cut['bag']['cut']['as_written']), ('NB', 'NB'))
        self.assertIn('official outlines', cut['osm.gpkg.zip']['cut']['places_labelled_by'])

    def test_an_exclave_labelled_as_the_province_fails_the_check(self):
        """Without the official outlines every OSM place is labelled Noord-Brabant, Baarle-Hertog too: check says so."""
        failures, _ = self.brabant([('town', "'s-Hertogenbosch", 5.30, 51.69), ('village', 'Baarle-Hertog', 4.925, 51.445)])
        self.assertTrue(any('exclave Baarle-Hertog' in f for f in failures), failures)

    def test_the_outline_step_labels_a_built_map_in_place(self):
        """A province built before the outlines were fetched is labelled afterwards without a rebuild; build.json and
        map-set.json follow, so check passes on the changed file."""
        features = [feature(i, number=str(i), lon=4.3700 + i * 1e-5) for i in range(1, 200)]
        features += [feature(1000, street='Rotterdamseweg', number='374', letter='A', code='2629HG'),
                     feature(1001, street='Lorentzweg', number='1', code='2628CJ'), feature(1002, number='4'),
                     feature(1003, street='Burg. Jansenstraat', number='7', code='2611AA', place='Den Haag')]
        pois = [('hospital', 'Reinier de Graaf', 4.36, 52.01), ('pharmacy', 'Apotheek Delft', 4.358, 52.012),
                ('fire_station', 'Kazerne Delft', 4.355, 52.0), ('police', 'Politie Delft', 4.357, 52.008)]
        failures, geo = self.build('ZH', features, [(4.37 + i * 1e-4, 52.0) for i in range(30)], pois,
                                   [('town', 'Delft', 4.357, 52.011)])
        self.assertEqual(failures, [])
        base = geo.parents[2]
        holland = {'type': 'Polygon', 'coordinates': [[[4.0, 51.9], [4.359, 51.9], [4.359, 52.1], [4.0, 52.1], [4.0, 51.9]]]}
        with mock.patch.object(nl, 'SHARED', base.parent / 'NL-shared'):
            nl.select('ZH')
            with mock.patch.multiple(nl, BASE=base, SOURCE=base / 'source', DATA=base / 'data', MINIMUM=self.LOW,
                                     log=lambda *a: None):
                nl.save_outlines({'timeStamp': '2026-11-28T10:00:00Z'}, {'ZH': holland})
                nl.outline()
                failures = nl.check(base / 'data')
        self.assertEqual(failures, [])
        places = sqlite3.connect(geo / 'places.sqlite')
        self.assertEqual(places.execute("SELECT detail FROM place WHERE name='Reinier de Graaf'").fetchall(),
                         [('outside the Dutch provinces (OpenStreetMap)',)])          # east of this test's outline
        self.assertEqual(places.execute("SELECT detail FROM place WHERE name='Delft' AND source='OpenStreetMap'").fetchall(),
                         [('Zuid-Holland (OpenStreetMap)',)])
        hit = places.execute("SELECT p.name FROM place_fts f JOIN place p ON p.id=f.rowid WHERE place_fts MATCH 'outside'").fetchall()
        places.close()
        self.assertIn(('Reinier de Graaf',), hit)                    # the text index follows the new label
        report = json.loads((base / 'data' / 'build.json').read_text(encoding='utf-8'))
        self.assertEqual(report['counts']['osm_places_outside']['outside_provinces'], 1)
        self.assertEqual(report['sources']['files']['bag']['cut']['field'], 'provincie_afkorting')
        self.assertEqual(report['sources']['files']['bag']['served_at'], '2026-11-25T10:00:00Z')   # kept, not replaced


class ReportAfterAnInPlaceChange(unittest.TestCase):
    """aed, seh and outline change a built file in place; build.json must then hold the new size and SHA-256 of that
    file and of map-set.json, which lists its size, or check fails on the next run (as it did on 28 November)."""

    def test_build_json_follows_the_changed_file_and_map_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            geo = data / 'derived' / 'geo'
            geo.mkdir(parents=True)
            places = geo / 'places.sqlite'
            places.write_bytes(b'a' * 100)
            (data / 'map-set.json').write_text(json.dumps({'name': 'NL-ZH', 'files': {'derived/geo/places.sqlite': 100},
                                                           'bytes': 100}, indent=1), encoding='utf-8')
            (data / 'build.json').write_text(json.dumps({'counts': {}, 'sources': {'files': {'bag': {'rows': 3}}},
                                                         'outputs': {}}), encoding='utf-8')
            places.write_bytes(b'b' * 250)                              # the file changed size in place
            nl.refresh_report(data, {'x': 1}, {'bag': {'cut': {'field': 'provincie_afkorting'}}}, changed=('places.sqlite',))
            report = json.loads((data / 'build.json').read_text(encoding='utf-8'))
            listed = json.loads((data / 'map-set.json').read_text(encoding='utf-8'))
            self.assertEqual((listed['files']['derived/geo/places.sqlite'], listed['bytes']), (250, 250))
            for name, path in (('derived/geo/places.sqlite', places), ('map-set.json', data / 'map-set.json')):
                self.assertEqual(report['outputs'][name], {'bytes': path.stat().st_size, 'sha256': nl.de.sha256(path)})
            self.assertEqual(report['sources']['files']['bag'], {'rows': 3, 'cut': {'field': 'provincie_afkorting'}})

class Outlines(unittest.TestCase):
    """The official outlines decide which province an OpenStreetMap place is in: Geofabrik's Noord-Brabant takes in
    Baarle-Hertog's Belgian enclaves, which the province's outline leaves out as holes (with Dutch ground in them)."""

    BRABANT = {'type': 'MultiPolygon', 'coordinates': [
        [[[4.5, 51.3], [5.5, 51.3], [5.5, 51.8], [4.5, 51.8], [4.5, 51.3]],                 # the province
         [[4.92, 51.43], [4.95, 51.43], [4.95, 51.45], [4.92, 51.45], [4.92, 51.43]]],      # a Belgian enclave: a hole
        [[[4.93, 51.435], [4.94, 51.435], [4.94, 51.44], [4.93, 51.44], [4.93, 51.435]]]]}  # Dutch ground inside it
    ZEELAND = {'type': 'Polygon', 'coordinates': [[[3.5, 51.3], [4.5, 51.3], [4.5, 51.7], [3.5, 51.7], [3.5, 51.3]]]}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(nl, 'SHARED', Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_islands_holes_and_ground_inside_a_hole(self):
        brabant = nl.Outline(self.BRABANT)
        self.assertIn((5.0, 51.5), brabant)
        self.assertNotIn((4.925, 51.445), brabant)          # Belgian
        self.assertIn((4.935, 51.4375), brabant)            # Dutch ground inside the Belgian enclave
        self.assertNotIn((4.0, 51.5), brabant)              # Zeeland
        self.assertNotIn((5.0, 52.5), brabant)

    def test_places_are_labelled_by_the_outline_that_holds_them(self):
        nl.select('NB')
        self.assertEqual(nl.where(4.925, 51.445), 'Noord-Brabant')          # no outlines yet: this province's name
        nl.save_outlines({'timeStamp': '2026-11-28T10:00:00Z'}, {'NB': self.BRABANT, 'ZE': self.ZEELAND})
        self.assertEqual(nl.where(5.0, 51.5), 'Noord-Brabant')
        self.assertEqual(nl.where(4.0, 51.5), 'Zeeland')
        self.assertEqual(nl.osm_detail(4.925, 51.445), 'outside the Dutch provinces (OpenStreetMap)')
        self.assertIn('served 2026-11-28T10:00:00Z', nl.osm_cut({'files': {}})['places_labelled_by'])


class AEDs(unittest.TestCase):
    """AEDs from OpenStreetMap through the Overpass API (no network here: a stand-in answers as Overpass does)."""

    ANSWER = {'osm3s': {'timestamp_osm_base': '2026-11-26T17:55:00Z'}, 'elements': [
        {'type': 'node', 'id': 1, 'lat': 53.2, 'lon': 5.8,
         'tags': {'emergency': 'defibrillator', 'defibrillator:location': 'Aan de gevel van de sporthal', 'opening_hours': '24/7'}},
        {'type': 'node', 'id': 2, 'lat': 53.21, 'lon': 5.81, 'tags': {'emergency': 'defibrillator'}},
        {'type': 'way', 'id': 3, 'center': {'lat': 53.22, 'lon': 5.82},
         'tags': {'emergency': 'defibrillator', 'name': 'AED Dorpshuis', 'opening_hours': 'Mo-Fr 08:00-17:00'}},
        {'type': 'node', 'id': 4, 'lat': 53.23, 'lon': 5.83, 'tags': {'emergency': 'defibrillator', 'access': 'private'}},
        {'type': 'relation', 'id': 5, 'tags': {'emergency': 'defibrillator'}}]}          # no position: skipped

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name) / 'NL-FR'
        patcher = mock.patch.multiple(nl, SHARED=Path(tmp.name) / 'NL-shared', log=lambda *a: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        nl.select('FR')
        patcher = mock.patch.multiple(nl, BASE=self.base, SOURCE=self.base / 'source', DATA=self.base / 'data')
        patcher.start()
        self.addCleanup(patcher.stop)

    def overpass(self, *answers):
        """A stand-in for urlopen: each call takes the next answer, an exception is raised."""
        calls = []

        class Reply:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps(self.body).encode('utf-8')

        def urlopen(request, timeout=None):
            calls.append((request.full_url, urllib.parse.parse_qs(request.data.decode('utf-8'))['data'][0]))
            answer = answers[len(calls) - 1]
            if isinstance(answer, Exception):
                raise answer
            return Reply(answer)
        return urlopen, calls

    def test_names_say_where_and_when(self):
        points, private = nl.aed_points(self.ANSWER)
        self.assertEqual([p[0] for p in points], ['AED: Aan de gevel van de sporthal (24/7)', 'AED',
                                                  'AED: AED Dorpshuis (Mo-Fr 08:00-17:00)'])
        self.assertEqual(points[2][1:], (5.82, 53.22))       # a way: its centre
        self.assertEqual(private, 1)

    def test_fetch_asks_by_the_province_boundary_and_keeps_the_list(self):
        urlopen, calls = self.overpass(self.ANSWER)
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen):
            saved = nl.fetch_aeds()
            again = nl.fetch_aeds()                           # younger than OSM_MAX_AGE: not asked again
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], nl.OVERPASS[0])
        self.assertIn('area["ISO3166-2"="NL-FR"]', calls[0][1])
        self.assertIn('nwr["emergency"="defibrillator"]', calls[0][1])
        self.assertEqual(saved['url'], nl.OVERPASS[0])
        self.assertEqual(saved['osm_as_of'], '2026-11-26T17:55:00Z')
        self.assertEqual(len(saved['points']), 3)
        self.assertEqual(again['points'], saved['points'])
        self.assertTrue((self.base / 'source' / 'aeds.json').is_file())

    def test_a_failing_instance_hands_over_to_the_next(self):
        down = urllib.error.HTTPError(nl.OVERPASS[0], 502, 'Bad Gateway', {}, None)
        urlopen, calls = self.overpass(down, self.ANSWER)
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen), mock.patch.object(nl.time, 'sleep') as slept:
            saved = nl.fetch_aeds()
        self.assertEqual([url for url, _ in calls], nl.OVERPASS[:2])
        slept.assert_not_called()                             # the next instance straight away, no waiting
        self.assertEqual(saved['url'], nl.OVERPASS[1])
        self.assertEqual(len(saved['points']), 3)

    def test_an_instance_that_hangs_hands_over_too(self):
        """Python 3.9 raises socket.timeout, an OSError that is not yet a TimeoutError, when an instance never answers."""
        class Hung(OSError):
            pass
        urlopen, calls = self.overpass(Hung('The read operation timed out'), ConnectionResetError(54, 'reset'), self.ANSWER)
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen), mock.patch.object(nl.time, 'sleep') as slept:
            saved = nl.fetch_aeds()
        self.assertEqual([url for url, _ in calls], nl.OVERPASS[:3])
        slept.assert_not_called()
        self.assertEqual(saved['url'], nl.OVERPASS[2])

    def test_all_down_waits_and_tries_them_again(self):
        busy = [urllib.error.HTTPError(u, 504, 'Gateway Timeout', {}, None) for u in nl.OVERPASS]
        urlopen, calls = self.overpass(*busy, self.ANSWER)
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen), mock.patch.object(nl.time, 'sleep') as slept:
            saved = nl.fetch_aeds()
        self.assertEqual(len(calls), len(nl.OVERPASS) + 1)
        slept.assert_called_once_with(60)
        self.assertEqual(saved['url'], nl.OVERPASS[0])

    def test_nobody_answering_saves_nothing(self):
        down = [urllib.error.URLError('no route') for _ in range(nl.OVERPASS_ROUNDS * len(nl.OVERPASS))]
        urlopen, calls = self.overpass(*down)
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen), mock.patch.object(nl.time, 'sleep'), \
                self.assertRaises(SystemExit) as stopped:
            nl.fetch_aeds()
        self.assertEqual(len(calls), nl.OVERPASS_ROUNDS * len(nl.OVERPASS))
        self.assertIn('aed --province FR later', str(stopped.exception))
        self.assertFalse((self.base / 'source' / 'aeds.json').exists())

    def test_no_aeds_at_all_means_the_boundary_was_not_found(self):
        urlopen, _ = self.overpass({'osm3s': {}, 'elements': []})
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen), self.assertRaises(SystemExit) as stopped:
            nl.fetch_aeds()
        self.assertIn('ISO3166-2=NL-FR', str(stopped.exception))
        self.assertFalse((self.base / 'source' / 'aeds.json').exists())

    def test_an_unfinished_query_is_not_kept(self):
        urlopen, _ = self.overpass({'remark': 'runtime error: Query timed out', 'elements': []})
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen), self.assertRaises(SystemExit):
            nl.fetch_aeds()
        self.assertFalse((self.base / 'source' / 'aeds.json').exists())

    def test_the_aed_step_adds_them_to_a_built_map_in_place(self):
        geo = self.base / 'data' / 'derived' / 'geo'
        geo.mkdir(parents=True)
        db = sqlite3.connect(geo / 'national.sqlite')
        db.executescript("CREATE TABLE poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL);"
                         "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);"
                         "INSERT INTO poi(cls, name, lon, lat) VALUES ('pharmacy', 'Apotheek', 5.79, 53.2);"
                         "INSERT INTO meta VALUES ('help_points', 'all classes: OpenStreetMap (ODbL 1.0)');")
        db.commit()
        db.close()
        (self.base / 'data' / 'build.json').write_text(json.dumps({'counts': {}, 'outputs': {}}), encoding='utf-8')
        (self.base / 'data' / 'map-set.json').write_text(json.dumps({'files': {'derived/geo/national.sqlite': 1}, 'bytes': 1}),
                                                         encoding='utf-8')
        urlopen, _ = self.overpass(self.ANSWER)
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen):
            nl.aed()
            nl.aed()                                          # again: the same AEDs, not twice
        db = sqlite3.connect(geo / 'national.sqlite')
        self.assertEqual(db.execute("SELECT count(*) FROM poi WHERE cls='defibrillator'").fetchone()[0], 3)
        self.assertEqual(db.execute("SELECT count(*) FROM poi WHERE cls='pharmacy'").fetchone()[0], 1)
        help_points = dict(db.execute('SELECT key, value FROM meta'))['help_points']
        db.close()
        self.assertEqual(help_points.count('; AEDs'), 1)
        report = json.loads((self.base / 'data' / 'build.json').read_text(encoding='utf-8'))
        size = (geo / 'national.sqlite').stat().st_size
        self.assertEqual(report['counts']['aeds'], 3)
        self.assertEqual(report['outputs']['derived/geo/national.sqlite']['bytes'], size)
        self.assertEqual(report['sources']['files']['aeds.json']['not_public_left_out'], 1)
        map_set = json.loads((self.base / 'data' / 'map-set.json').read_text(encoding='utf-8'))
        self.assertEqual(map_set['bytes'], size)

    def test_a_province_not_built_keeps_its_list_for_the_build(self):
        urlopen, _ = self.overpass(self.ANSWER)
        with mock.patch.object(nl.urllib.request, 'urlopen', urlopen):
            nl.aed()
        self.assertTrue((self.base / 'source' / 'aeds.json').is_file())
        self.assertFalse((self.base / 'data').exists())


class SEHs(unittest.TestCase):
    """The RIVM's list of emergency departments, placed at their BAG address."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.xlsx = seh_xlsx(self.root / 'seh.xlsx', SEH_ROWS)

    def index(self, folder, rows, region='NL-ZH'):
        (folder / 'addresses').mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(folder / 'addresses' / f'{region}.sqlite')
        db.execute('CREATE TABLE addr(num TEXT, street TEXT, norm TEXT, city TEXT, state TEXT, zip TEXT, lat REAL, lon REAL, district TEXT)')
        db.executemany('INSERT INTO addr VALUES (?,?,?,?,?,?,?,?,?)', rows)
        db.commit()
        db.close()
        national = sqlite3.connect(folder / 'national.sqlite')
        national.executescript("CREATE TABLE poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL);"
                               "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);"
                               "INSERT INTO meta VALUES ('help_points', 'all classes: OpenStreetMap (ODbL 1.0); AEDs: OpenStreetMap');")
        national.commit()
        national.close()

    ZH = [('3', 'Reinier de Graafweg', 'reinier de graafweg', 'Delft', 'NL-ZH', '2625AD', 52.0, 4.36, 'Delft'),
          ('5', 'Reinier de Graafweg', 'reinier de graafweg', 'Delft', 'NL-ZH', '2625AD', 52.1, 4.37, 'Delft'),
          ('4', 'Vlietlandplein', 'vlietlandplein', 'Schiedam', 'NL-ZH', '3118JH', 51.93, 4.39, 'Schiedam'),
          ('6', 'Vlietlandplein', 'vlietlandplein', 'Schiedam', 'NL-ZH', '3118JH', 51.95, 4.41, 'Schiedam')]

    def test_the_answers_are_read_by_their_headers(self):
        found = nl.seh_locations(self.xlsx)
        self.assertEqual([f['name'] for f in found], ['Reinier de Graaf', 'Franciscus Vlietland', 'Ziekenhuis Elders'])
        delft, schiedam = found[0], found[1]
        self.assertTrue(delft['all_hours'])
        self.assertEqual((delft['postcode'], delft['obstetrics'], delft['gp_post']), ('2625AD', True, 'in building'))
        self.assertFalse(schiedam['all_hours'])
        self.assertEqual(schiedam['periods'], ['overdag', "'s avonds"])       # the first Overdag column, not the later one
        self.assertEqual((schiedam['obstetrics'], schiedam['gp_post']), (False, None))

    def test_names_say_hours_place_and_what_else_is_there(self):
        found = nl.seh_locations(self.xlsx)
        self.assertEqual(nl.seh_name(found[0]), 'SEH 24/7 · Reinier de Graaf (Delft) · huisartsenpost in het gebouw · acute verloskunde')
        self.assertEqual(nl.seh_name(found[1]), "SEH niet 24/7 (overdag en 's avonds) · Franciscus Vlietland (Schiedam)")

    def test_fetch_keeps_the_workbook_and_where_it_came_from(self):
        shared = self.root / 'NL-shared'

        def download(url, path):
            with zipfile.ZipFile(path, 'w') as archive:
                archive.write(self.xlsx, 'Antwoorden vragenlijst 2026 tbv data.rivm.nl.xlsx')
            return url
        with mock.patch.multiple(nl, SHARED=shared, download=mock.Mock(side_effect=download), log=lambda *a: None):
            first = nl.fetch_seh()
            again = nl.fetch_seh()                            # recent: not downloaded again
            self.assertEqual(nl.download.call_count, 1)
        self.assertEqual(first, again)
        about = json.loads((shared / 'seh.json').read_text(encoding='utf-8'))
        self.assertEqual((about['locations'], about['licence']), (3, 'Public Domain Mark 1.0'))

    def test_a_changed_sheet_is_noticed(self):
        other = seh_xlsx(self.root / 'other.xlsx', SEH_ROWS, sheet='Antwoorden')
        with self.assertRaises(SystemExit):
            nl.seh_locations(other)

    def test_placed_at_the_house_the_first_of_a_range_or_the_postcode(self):
        self.index(self.root / 'geo', self.ZH)
        index = sqlite3.connect(self.root / 'geo' / 'addresses' / 'NL-ZH.sqlite')
        self.assertEqual(nl.place_at(index, 'Reinier de Graafweg 3-11', '2625AD'), (52.0, 4.36))   # 3, the first
        self.assertEqual(nl.place_at(index, 'Vlietlandplein 2', '3118JH'), (51.94, 4.4))           # no 2: its postcode
        self.assertIsNone(nl.place_at(index, 'Hanzeplein 1', '9713GZ'))                           # another province
        index.close()

    def test_the_seh_step_adds_this_provinces_in_place(self):
        base = self.root / 'NL-ZH'
        geo = base / 'data' / 'derived' / 'geo'
        self.index(geo, self.ZH)
        (base / 'data' / 'build.json').write_text(json.dumps({'counts': {}}), encoding='utf-8')
        shared = self.root / 'NL-shared'
        shared.mkdir()
        (shared / 'seh.xlsx').write_bytes(self.xlsx.read_bytes())
        (shared / 'seh.json').write_text(json.dumps({'fetched': '2026-11-26T19:00:00+00:00', 'title': nl.SEH_TITLE}), encoding='utf-8')
        with mock.patch.multiple(nl, SHARED=shared, log=lambda *a: None):
            nl.select('ZH')
            with mock.patch.multiple(nl, BASE=base, SOURCE=base / 'source', DATA=base / 'data', SEH_PLACED=set()):
                nl.seh()
                nl.seh()                                      # again: the same SEHs, not twice
                placed = set(nl.SEH_PLACED)
        db = sqlite3.connect(geo / 'national.sqlite')
        names = sorted(n for n, in db.execute("SELECT name FROM poi WHERE cls='emergency_department'"))
        help_points = dict(db.execute('SELECT key, value FROM meta'))['help_points']
        db.close()
        self.assertEqual(len(names), 2)
        self.assertTrue(names[0].startswith('SEH 24/7 · Reinier de Graaf (Delft)'))
        self.assertTrue(names[1].startswith("SEH niet 24/7 (overdag en 's avonds) · Franciscus Vlietland"))
        self.assertEqual(placed, {('Reinier de Graaf', '2625AD'), ('Franciscus Vlietland', '3118JH')})
        self.assertIn('; AEDs: OpenStreetMap', help_points)                                # the other notes stay
        self.assertEqual(help_points.count('; SEH: '), 1)
        report = json.loads((base / 'data' / 'build.json').read_text(encoding='utf-8'))
        self.assertEqual(report['counts']['seh'], 2)
        self.assertEqual(report['sources']['files']['seh.xlsx']['title'], nl.SEH_TITLE)


class MapBesideTheLibrary(unittest.TestCase):
    """server.py --map (LASTBOOK_MAP): a province's map is read from its own folder and the library is left as it is."""

    def test_the_map_folder_replaces_the_librarys_own(self):
        import server
        with tempfile.TemporaryDirectory() as tmp:
            geo = Path(tmp) / 'NL-FR' / 'data' / 'derived' / 'geo'
            with mock.patch.object(server, 'MAP_DIR', str(geo)), \
                    mock.patch.object(server.address_search, 'find_addresses', return_value=[]) as lookup:
                self.assertEqual(server.geo_dir(), geo)
                server.places('18003 nine mile')
                lookup.assert_called_once_with('18003 nine mile', geo, limit=8, near=None)

    def test_without_it_the_library_holds_the_map(self):
        import server
        with mock.patch.object(server, 'MAP_DIR', None):
            self.assertEqual(server.geo_dir(), server.HERE / 'derived' / 'geo')


class MergeTheCountry(unittest.TestCase):
    """merge: the provinces already built as one map of the whole country, without downloading anything."""

    def province(self, root, code, pois, places, box):
        geo = root / 'derived' / 'regions' / f'NL-{code}' / 'data' / 'derived' / 'geo'
        (geo / 'addresses').mkdir(parents=True)
        db = sqlite3.connect(geo / 'national.sqlite')
        db.executescript('CREATE TABLE feat(id INTEGER PRIMARY KEY, layer TEXT, cls TEXT, name TEXT, minz INTEGER, geom BLOB);'
                         'CREATE VIRTUAL TABLE feat_idx USING rtree(id, minx, maxx, miny, maxy, minz, maxz);'
                         'CREATE TABLE poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL);'
                         'CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);'
                         'CREATE INDEX poi_cls ON poi(cls, lon, lat);')
        for i in (1, 2):
            db.execute('INSERT INTO feat VALUES (?, ?, ?, ?, ?, ?)', (i, 'road', 'primary', f'{code} weg {i}', 8, b'x'))
            db.execute('INSERT INTO feat_idx VALUES (?, ?, ?, ?, ?, ?, ?)', (i, box[0], box[2], box[1], box[3], 8, 20))
        db.executemany('INSERT INTO poi(cls, name, lon, lat) VALUES (?, ?, ?, ?)', pois)
        db.executemany('INSERT INTO meta VALUES (?, ?)', [('region', f'NL-{code}'), ('bounds', ','.join(map(str, box))),
                                                           ('data_as_of', '2026-11-24T21:21:23Z'),
                                                           ('help_points', 'all classes: OpenStreetMap (ODbL 1.0); AEDs: OpenStreetMap via the Overpass API, as of 2026-11-26T17:55:00Z (ODbL 1.0)')])
        db.commit()
        db.close()
        m = sqlite3.connect(geo / 'map.sqlite')
        m.execute('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)')
        m.execute('INSERT INTO meta VALUES (?, ?)', ('region', f'NL-{code}'))
        m.commit()
        m.close()
        p = sqlite3.connect(geo / 'places.sqlite')
        p.executescript('CREATE TABLE place(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, detail TEXT, lat REAL, lon REAL, rank INTEGER, source TEXT);'
                        "CREATE VIRTUAL TABLE place_fts USING fts5(name, detail, content='place', content_rowid='id', tokenize='unicode61');")
        p.executemany('INSERT INTO place(name, kind, detail, lat, lon, rank, source) VALUES (?, ?, ?, ?, ?, ?, ?)', places)
        p.execute("INSERT INTO place_fts(place_fts) VALUES ('rebuild')")
        p.commit()
        p.close()
        (geo / 'addresses' / f'NL-{code}.sqlite').write_bytes(b'')
        return geo

    def test_two_provinces_become_one_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            border = ('fire_station', 'Brandweer Grens', 5.30, 52.90)          # in both extracts
            self.province(root, 'FR', [border, ('pharmacy', 'Apotheek Noord', 5.80, 53.20)],
                          [('Grensdorp', 'place (woonplaats)', 'Fryslân', 52.90, 5.30, 1, 'Kadaster BAG')], (4.8, 52.7, 6.4, 53.6))
            self.province(root, 'NH', [border, ('police', 'Politie Zuid', 4.90, 52.37)],
                          [('Grensdorp', 'place (woonplaats)', 'Fryslân', 52.9005, 5.3005, 1, 'Kadaster BAG'),
                           ('Amsterdam', 'place (woonplaats)', 'Noord-Holland', 52.37, 4.90, 1, 'Kadaster BAG')], (4.4, 52.1, 5.4, 53.2))
            with mock.patch.object(nl, 'ROOT', root):
                data = nl.merge(['FR', 'NH', 'ZH'])
            geo = data / 'derived' / 'geo'
            db = sqlite3.connect(geo / 'national.sqlite')
            self.assertEqual(db.execute('SELECT count(*) FROM feat').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT count(*) FROM feat_idx').fetchone()[0], 4)
            self.assertEqual(sorted(n for n, in db.execute('SELECT name FROM poi')), ['Apotheek Noord', 'Brandweer Grens', 'Politie Zuid'])
            meta = dict(db.execute('SELECT key, value FROM meta').fetchall())
            db.close()
            self.assertEqual(meta['region'], 'NL')
            self.assertIn('; AEDs: OpenStreetMap via the Overpass API', meta['help_points'])
            self.assertEqual(meta['bounds'], '4.4000,52.1000,6.4000,53.6000')
            p = sqlite3.connect(geo / 'places.sqlite')
            self.assertEqual(p.execute('SELECT count(*) FROM place').fetchone()[0], 2)          # Grensdorp once
            self.assertEqual(p.execute("SELECT count(*) FROM place_fts WHERE place_fts MATCH 'amsterdam'").fetchone()[0], 1)
            p.close()
            self.assertTrue((geo / 'addresses' / 'NL-FR.sqlite').is_symlink())
            self.assertEqual(sorted(f.name for f in (geo / 'addresses').iterdir()), ['NL-FR.sqlite', 'NL-NH.sqlite'])
            report = json.loads((data / 'build.json').read_text(encoding='utf-8'))
            self.assertEqual(report['not_built'], ['NL-ZH'])
            self.assertEqual(report['help_points_in_two_provinces'], 1)
            with mock.patch.object(nl, 'ROOT', root):              # a second merge replaces the first
                nl.merge(['FR'])
            self.assertEqual(sorted(f.name for f in (geo / 'addresses').iterdir()), ['NL-FR.sqlite'])

    def test_nothing_built_says_so(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(nl, 'ROOT', Path(tmp)):
            with self.assertRaises(SystemExit):
                nl.merge(['FR'])


if __name__ == '__main__':
    unittest.main()
