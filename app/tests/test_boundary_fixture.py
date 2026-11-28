"""The Baarle boundary fixture (app/tests/fixtures/nl_nb_boundary.json), as asked in #31: one place on either side of
the border where Belgian enclaves lie inside Noord-Brabant, with the label the place finder must give each. The test
reads the fixture's own small outline; where the real official outlines have been fetched (NL-shared/outlines.json,
on a machine that built the map) it checks the same places against those too."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.build_region_nl as nl

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / 'app' / 'tests' / 'fixtures' / 'nl_nb_boundary.json').read_text(encoding='utf-8'))
REAL = ROOT / 'derived' / 'regions' / 'NL-shared' / 'outlines.json'


class BaarleOnBothSides(unittest.TestCase):
    def setUp(self):
        nl.select(FIXTURE['region'][3:])

    def labels(self, shared):
        with mock.patch.object(nl, 'SHARED', shared):
            outlines = nl.load_outlines()
            return {p['name']: nl.osm_detail(p['lon'], p['lat'], outlines) for p in FIXTURE['places']}

    def test_one_place_on_either_side(self):
        self.assertEqual(sorted(p['side'] for p in FIXTURE['places']), ['Belgium', 'Netherlands'])

    def test_the_fixture_outline_labels_each_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(nl, 'SHARED', Path(tmp)):
                nl.save_outlines({'timeStamp': FIXTURE['checked_against_official']['served_at']}, FIXTURE['outlines'])
            self.assertEqual(self.labels(Path(tmp)), {p['name']: p['expected_detail'] for p in FIXTURE['places']})

    @unittest.skipUnless(REAL.is_file(), 'the official outlines are fetched by a map build (receipts --province NB)')
    def test_the_official_outline_labels_each_place_the_same(self):
        self.assertEqual(self.labels(REAL.parent), {p['name']: p['expected_detail'] for p in FIXTURE['places']})


if __name__ == '__main__':
    unittest.main()
