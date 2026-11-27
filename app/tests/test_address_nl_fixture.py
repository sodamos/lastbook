"""The Flevoland fixture (app/tests/fixtures/nl_fl_queries.json), as posted in #31 for the Dutch lookup work: six invented
addresses and seventeen queries, street first and postcode first, with the houses each must find. The rows are not BAG
data; the streets and postcodes do not exist in the BAG (checked against all twelve provinces on 27 November 2026)."""
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import address_nl as nl
import tools.build_region_nl as builder

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / 'app' / 'tests' / 'fixtures' / 'nl_fl_queries.json').read_text(encoding='utf-8'))
ROWS = {row['id']: row for row in FIXTURE['address_rows']}
ID_RULE = r'[A-Z]{2}(-[A-Za-z0-9_]{1,48})?'     # the address-index id rule in #486


def detail(row):
    """How the lookup shows where a house is, by the fixture's display rule: '8307 XZ Ens (Noordoostpolder)'."""
    place = ' '.join(x for x in (nl.show_postcode(row['zip']), row['city']) if x)
    return place + (f" ({row['district']})" if row['district'] != row['city'] else '')


class SchemeAndIds(unittest.TestCase):
    def test_fixture_engine_and_builder_name_the_same_scheme(self):
        """The index records meta norm = nl-1 and the lookup chooses its reading by that key, so all three must agree."""
        self.assertEqual(FIXTURE['norm'], nl.NORM)
        self.assertEqual(FIXTURE['norm'], builder.NORM)
        self.assertEqual(FIXTURE['index_contract']['meta']['norm'], nl.NORM)
        self.assertEqual(FIXTURE['index_contract']['meta']['region'], FIXTURE['region'])
        self.assertEqual(FIXTURE['index_filename'], f"{FIXTURE['region']}.sqlite")

    def test_province_ids_keep_one_spelling(self):
        """Every id the builder can make fits #486's rule, is upper case as in ISO 3166-2 and differs from the others
        ignoring case; an upgrade finds installed files by that name, and a bare FL, NH or UT is a US state."""
        ids = [f'NL-{code}' for code in builder.PROVINCES]
        self.assertEqual(len(ids), 12)
        for region in ids:
            with self.subTest(region=region):
                self.assertRegex(region, f'^{ID_RULE}$')
                self.assertEqual(region, region.upper())
        self.assertEqual(len({region.casefold() for region in ids}), len(ids))
        self.assertIn(FIXTURE['region'], ids)

    def test_spellings_people_type_meet_in_one_key(self):
        for example in FIXTURE['normalization_examples']:
            with self.subTest(text=example['input']):
                self.assertEqual(nl.normalize(example['input']), example['expected'])
                self.assertEqual(builder.normalize_nl(example['input']), example['expected'])


class RowsFollowTheContract(unittest.TestCase):
    def test_rows_are_written_as_the_builder_writes_them(self):
        for row in ROWS.values():
            with self.subTest(row=row['id']):
                self.assertEqual(row['norm'], builder.normalize_nl(row['street']))
                self.assertEqual(row['state'], FIXTURE['region'])
                self.assertRegex(row['num'], r'^[1-9][0-9]*([A-Z]|-[A-Za-z0-9]+)?$')
                self.assertRegex(row['zip'], r'^([1-9][0-9]{3}[A-Z]{2})?$')
                self.assertTrue(row['city'] and row['district'])

    def test_queries_cover_both_orders_and_name_only_fixture_rows(self):
        forms = [case['form'] for case in FIXTURE['queries']]
        self.assertEqual(set(forms), {'street-first', 'postcode-first', 'no-house'})
        self.assertEqual((forms.count('street-first'), forms.count('postcode-first'), forms.count('no-house')), (8, 5, 4))
        for case in FIXTURE['queries']:
            for key in case['expected_fixture_ids']:
                self.assertIn(key, ROWS)


class LookupFindsTheExpectedHouses(unittest.TestCase):
    """Runs engine/address_nl.py over an index built from the six rows, the files a Dutch map set would carry."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.geo = Path(cls.tmp.name)
        path = cls.geo / 'addresses' / FIXTURE['index_filename']
        path.parent.mkdir(parents=True)
        db = sqlite3.connect(path)
        db.execute(f"CREATE TABLE {FIXTURE['index_contract']['table']}")
        db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)')
        for index in FIXTURE['index_contract']['indexes']:
            db.execute(f'CREATE INDEX {index}')
        db.executemany('INSERT INTO meta VALUES (?,?)', FIXTURE['index_contract']['meta'].items())
        db.executemany('INSERT INTO addr VALUES (?,?,?,?,?,?,?,?,?)',
                       [(r['num'], r['street'], r['norm'], r['city'], r['state'], r['zip'], r['lat'], r['lon'], r['district'])
                        for r in ROWS.values()])
        db.commit()
        db.close()
        cls.by_display = {(f"{row['street']} {row['num']}", detail(row)): key for key, row in ROWS.items()}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def found(self, query):
        return [self.by_display.get((r['name'], r['detail']), f"not a fixture row: {r['name']} | {r['detail']}")
                for r in nl.find(query, self.geo)]

    def test_each_query_finds_its_houses_in_order(self):
        for case in FIXTURE['queries']:
            with self.subTest(form=case['form'], query=case['query']):
                self.assertEqual(self.found(case['query']), case['expected_fixture_ids'])

    def test_the_index_is_read_by_its_norm_key(self):
        self.assertTrue(nl.has_index(self.geo))


if __name__ == '__main__':
    unittest.main()
