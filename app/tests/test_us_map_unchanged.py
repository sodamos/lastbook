"""A US map set still opens and searches as before with the Dutch changes in place (asked in #31). This fork changes
three things around the map: --map / LASTBOOK_MAP loads a map set from outside the library, place search tries a Dutch
address index first, and the server finds the map folder through geo_dir(). Without LASTBOOK_MAP and without a Dutch
index, none of them may change what a library with a US state map does. Every street, number and place is invented."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server
from engine.address_search import normalize


class USMapStillOpens(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.library = Path(tmp.name)
        self.geo = self.library / 'derived' / 'geo'
        (self.geo / 'addresses').mkdir(parents=True)
        # A US state map as the installer leaves it: map-set.json, the national map with its help points, and the
        # state's address index (the US table, no meta norm).
        db = sqlite3.connect(self.geo / 'national.sqlite')
        db.execute('CREATE TABLE poi(id INTEGER PRIMARY KEY, cls TEXT, name TEXT, lon REAL, lat REAL)')
        db.executemany('INSERT INTO poi(cls,name,lon,lat) VALUES (?,?,?,?)',
                       [('hospital', 'Valley Test Hospital', -118.38, 34.17), ('pharmacy', 'Test Pharmacy', -118.37, 34.16)])
        db.commit()
        db.close()
        (self.library / 'map-set.json').write_text(json.dumps({'name': 'CA', 'files': {'derived/geo/national.sqlite': 1}}),
                                                   encoding='utf-8')
        db = sqlite3.connect(self.geo / 'addresses' / 'CA.sqlite')
        db.execute('CREATE TABLE addr(num TEXT,street TEXT,norm TEXT,city TEXT,state TEXT,zip TEXT,lat REAL,lon REAL)')
        db.execute('CREATE INDEX addr_num_norm ON addr(num,norm)')
        db.execute('INSERT INTO addr VALUES(?,?,?,?,?,?,?,?)',
                   ('123', 'Main Street', normalize('Main Street'), 'North Hollywood', 'CA', '91601', 34.17, -118.38))
        db.commit()
        db.close()
        for target, value in (('MAP_DIR', None), ('HERE', self.library), ('MAPDB', self.geo / 'map.sqlite'),
                              ('PLACEDB', self.geo / 'places.sqlite')):
            patcher = mock.patch.object(server, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.forget()
        self.addCleanup(self.forget)

    @staticmethod
    def forget():
        """The server keeps the open map per thread and the map's contents once; a test starts from neither."""
        if hasattr(server._tls, 'national_map'):
            server._tls.national_map.close()
            del server._tls.national_map
        server.map_contents.cache_clear()

    def test_the_library_map_folder_is_used_without_lastbook_map(self):
        self.assertEqual(server.geo_dir(), self.geo)
        with mock.patch.object(server, 'MAP_DIR', str(self.library / 'elsewhere')):
            self.assertEqual(server.geo_dir(), self.library / 'elsewhere')         # only when asked for
        self.assertEqual(server.geo_dir(), self.geo)

    def test_the_us_map_opens_with_its_help_points(self):
        national = server.national_mapdb()
        self.assertIsNotNone(national)
        self.assertEqual(national.execute('SELECT count(*) FROM poi').fetchone()[0], 2)
        contents = server.map_contents()
        self.assertTrue({'hospital', 'pharmacy'} <= set(contents['layers']))
        self.assertTrue(contents['detail'])                              # the map's own box is known

    def test_a_us_address_is_found_as_before_and_the_dutch_search_is_not_asked(self):
        with mock.patch.object(server.address_nl, 'find') as dutch:
            found = server.places('123 Main St, North Hollywood, CA 91601')
        dutch.assert_not_called()
        self.assertEqual((found[0]['name'], found[0]['detail']), ('123 Main Street', 'North Hollywood, CA, 91601'))

    def test_a_us_index_is_not_taken_for_a_dutch_one(self):
        self.assertFalse(server.address_nl.has_index(self.geo))


if __name__ == '__main__':
    unittest.main()
