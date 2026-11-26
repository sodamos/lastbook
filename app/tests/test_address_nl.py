"""Dutch address search (engine/address_nl.py) over a small, invented BAG-style index. Every street and house here is made
up for the test, apart from the shape of the rows, which is what tools/build_region_nl.py writes."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import address_nl as nl
import tools.build_region_nl as builder

ROWS = [   # num, street, city (woonplaats), zip, lat, lon, district (municipality)
    ('12', 'Dorpsstraat', 'Voorbeeldum', '9999AA', 53.10, 5.70, 'Voorbeeldland'),
    ('12A', 'Dorpsstraat', 'Voorbeeldum', '9999AA', 53.1001, 5.70, 'Voorbeeldland'),
    ('12-2', 'Dorpsstraat', 'Voorbeeldum', '9999AA', 53.1002, 5.70, 'Voorbeeldland'),
    ('14', 'Dorpsstraat', 'Voorbeeldum', '9999AB', 53.1003, 5.70, 'Voorbeeldland'),
    ('12', 'Dorpsstraat', 'Ander Dorp', '9998BB', 53.30, 5.90, 'Voorbeeldland'),
    ('3', 'Dorpsstraatje', 'Voorbeeldum', '9999AC', 53.11, 5.71, 'Voorbeeldland'),
    ('1', 'Burgemeester Voorbeeldlaan', 'Voorbeeldum', '9999AD', 53.12, 5.72, 'Voorbeeldland'),
    ('2', 'Burg. Proeflaan', 'Voorbeeldum', '9999AE', 53.13, 5.73, 'Voorbeeldland'),
    ('5', 'Dr. A. Testmanlaan', 'Voorbeeldum', '9999AF', 53.14, 5.74, 'Voorbeeldland'),
    ('7', 'Laan 1940-1945', 'Voorbeeldum', '9999AG', 53.15, 5.75, 'Voorbeeldland'),
    ('1', 'Hofweg', "'s-Gravenhage", '2511AA', 52.08, 4.31, "'s-Gravenhage"),
    ('9', 'Schuurpad', 'Voorbeeldum', '', 53.16, 5.76, 'Voorbeeldland'),   # an outbuilding: no postcode
]


def make_index(folder, region='NL-XX', norm='nl-1'):
    path = Path(folder) / 'addresses' / f'{region}.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript('CREATE TABLE addr(num TEXT, street TEXT, norm TEXT, city TEXT, state TEXT, zip TEXT, lat REAL, lon REAL, district TEXT);'
                     'CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);')
    db.executemany('INSERT INTO addr VALUES (?,?,?,?,?,?,?,?,?)',
                   [(n, s, builder.normalize_nl(s), c, region, z, la, lo, d) for n, s, c, z, la, lo, d in ROWS])
    db.execute('CREATE INDEX addr_norm ON addr(norm, num)')
    db.execute('CREATE INDEX addr_zip ON addr(zip, num)')
    db.execute("INSERT INTO meta VALUES ('norm', ?)", (norm,))
    db.commit()
    db.close()


class DutchAddresses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.geo = Path(self.tmp.name)
        make_index(self.geo)

    def tearDown(self):
        self.tmp.cleanup()

    def names(self, query, near=None):
        return [(r['name'], r['detail']) for r in nl.find(query, self.geo, near=near)]

    def test_street_and_number_finds_that_house_first_then_the_real_ones_sharing_it(self):
        found = self.names('Dorpsstraat 12', near=(53.10, 5.70))
        self.assertEqual(found[:3], [('Dorpsstraat 12', '9999 AA Voorbeeldum (Voorbeeldland)'),
                                     ('Dorpsstraat 12', '9998 BB Ander Dorp (Voorbeeldland)'),
                                     ('Dorpsstraat 12A', '9999 AA Voorbeeldum (Voorbeeldland)')])
        self.assertIn(('Dorpsstraat 12-2', '9999 AA Voorbeeldum (Voorbeeldland)'), found)
        self.assertNotIn('Dorpsstraat 14', [name for name, _ in found])

    def test_letters_and_additions_as_people_write_them(self):
        for query in ('Dorpsstraat 12a', 'dorpsstraat 12 A', 'Dorpsstraat 12-a', 'Dorpsstr 12A'):
            with self.subTest(query=query):
                self.assertEqual(self.names(query)[0][0], 'Dorpsstraat 12A')
        self.assertEqual(self.names('Dorpsstraat 12-2'), [('Dorpsstraat 12-2', '9999 AA Voorbeeldum (Voorbeeldland)')])

    def test_postcode_and_number(self):
        for query in ('9999 AA 12', '9999AA 12', '9999aa12', '9999 aa 12, Voorbeeldum'):
            with self.subTest(query=query):
                self.assertEqual(self.names(query)[0], ('Dorpsstraat 12', '9999 AA Voorbeeldum (Voorbeeldland)'))
        self.assertEqual(self.names('Dorpsstraat 12 9998 BB'), [('Dorpsstraat 12', '9998 BB Ander Dorp (Voorbeeldland)')])

    def test_the_place_narrows_by_woonplaats_or_municipality(self):
        self.assertEqual(self.names('Dorpsstraat 12, Ander Dorp'), [('Dorpsstraat 12', '9998 BB Ander Dorp (Voorbeeldland)')])
        self.assertEqual(len(self.names('Dorpsstraat 12 Voorbeeldland')), 4)
        self.assertEqual(self.names('Hofweg 1 Den Haag'), [('Hofweg 1', "2511 AA 's-Gravenhage")])
        self.assertEqual(self.names('Dorpsstraat 12 Elders'), [])

    def test_titles_either_way_and_a_street_known_by_its_main_word(self):
        self.assertEqual(self.names('Burg. Voorbeeldlaan 1')[0][0], 'Burgemeester Voorbeeldlaan 1')
        self.assertEqual(self.names('Burgemeester Proeflaan 2')[0][0], 'Burg. Proeflaan 2')
        self.assertEqual(self.names('Dr. Testmanlaan 5')[0][0], 'Dr. A. Testmanlaan 5')

    def test_a_number_inside_the_street_name(self):
        self.assertEqual(self.names('Laan 1940-1945 7')[0][0], 'Laan 1940-1945 7')

    def test_an_address_without_a_postcode(self):
        self.assertEqual(self.names('Schuurpad 9'), [('Schuurpad 9', 'Voorbeeldum (Voorbeeldland)')])

    def test_never_a_guessed_house(self):
        for query in ('Dorpsstraat 13', 'Dorpsstraat 12B', 'Dorpsstraat 99999', '9999 AA 13', 'Nergensweg 1'):
            with self.subTest(query=query):
                self.assertEqual(self.names(query), [])

    def test_what_is_not_an_address_is_left_to_the_place_finder(self):
        for query in ('Voorbeeldum', '9999 AA', '9999', 'Dorpsstraat', '12 ', ''):
            with self.subTest(query=query):
                self.assertEqual(nl.readings(query) if query.strip() in ('Voorbeeldum', 'Dorpsstraat', '') else self.names(query), [])

    def test_an_index_with_another_normalization_is_not_read(self):
        other = Path(self.tmp.name) / 'other'
        make_index(other, norm='nl-0')
        self.assertEqual(nl.find('Dorpsstraat 12', other), [])

    def test_the_rule_matches_the_builder(self):
        for text in ("'s-Gravenhage", 'Burg. Jansenstraat', 'Ruïnelaan', 'De Bûgel', 'Laan 1940-1945', 'Straat', 'Pr Willem-Alexanderstr'):
            with self.subTest(text=text):
                self.assertEqual(nl.normalize(text), builder.normalize_nl(text))


class PlaceFinderRoute(unittest.TestCase):
    """server.places reads Dutch addresses when the map has a Dutch index, and leaves the rest to the place finder."""

    def test_dutch_map_reads_dutch_addresses(self):
        import server
        with tempfile.TemporaryDirectory() as tmp:
            make_index(tmp)
            with mock.patch.object(server, 'MAP_DIR', tmp), \
                    mock.patch.object(server.address_search, 'find_addresses') as us:
                self.assertEqual(server.places('Dorpsstraat 12A')[0]['name'], 'Dorpsstraat 12A')
                self.assertEqual(server.places('Dorpsstraat 12A')[0]['source'], 'Kadaster BAG')
                server.places('12 Main St')
                us.assert_not_called()

    def test_no_such_house_goes_on_to_the_place_finder(self):
        import server
        with tempfile.TemporaryDirectory() as tmp:
            make_index(tmp)
            with mock.patch.object(server, 'MAP_DIR', tmp), mock.patch.object(server, 'PLACEDB', Path(tmp) / 'none.sqlite'):
                self.assertEqual(server.places('Dorpsstraat 13'), [])


if __name__ == '__main__':
    unittest.main()
