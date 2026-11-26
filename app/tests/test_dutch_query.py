#!/usr/bin/env python3
"""Dutch searches: engine/dutch_query.py (the library's English words for a Dutch search) and the guide search in Dutch.

  python3 -B -m unittest app.tests.test_dutch_query

The guide search part runs web/words.js in Node over the guides as the Dutch interface gets them (server.translate_topic)
with the Dutch stop words from web/app.js; it is skipped without Node.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine import dutch_query as D  # noqa: E402

NODE = shutil.which('node')


class ToEnglish(unittest.TestCase):
    def test_dutch_searches_become_english(self):
        for q, want in [
            ('brandwond op mijn hand', 'burn hand'),
            ('geen stroom koelkast', 'power outage refrigerator'),
            ('mijn kind heeft koorts', 'child fever'),
            ('gebroken been', 'broken leg'),
            ('ik ruik gas', 'gas leak'),
            ('wespensteek', 'wasp sting'),
            ('Weeën begonnen', 'labor begonnen'),          # accents fold; an unknown word stays
            ('accu’s opladen', 'batteries charging'),      # curly apostrophe
            ('ramen en deuren dicht', 'shelter in place'),   # a phrase's English is not read again ("in" is Dutch too)
            ('stroomstoring', 'power outage'),
            ('hoe zuiver ik water', 'purify water'),
        ]:
            with self.subTest(q=q):
                self.assertEqual(D.to_english(q)[0], want)

    def test_english_and_other_searches_pass_through(self):
        for q in ('how to purify water', 'boil water', 'brand of bleach', 'door is stuck', 'brand', 'been bitten by a dog',
                  '112', 'Berlin', '', 'kind of rash on my arm', 'the power is out'):
            with self.subTest(q=q):
                self.assertEqual(D.to_english(q), (q, []))

    def test_shared_words_are_dutch_only_in_a_dutch_search(self):
        self.assertEqual(D.to_english('brand')[0], 'brand')
        self.assertEqual(D.to_english('brand', 'nl')[0], 'fire')                 # the person chose Dutch
        self.assertEqual(D.to_english('brand in de keuken')[0], 'fire kitchen')  # "de" and "keuken" are only Dutch
        self.assertEqual(D.to_english('been gebroken')[0], 'leg broken')
        self.assertEqual(D.to_english('the brand', 'nl')[0], 'the brand')        # an English-only word keeps it English

    def test_found_pairs_say_what_was_translated(self):
        english, found = D.to_english('geen stroom en koorts')
        self.assertEqual(english, 'power outage fever')
        self.assertEqual(found, [('geen stroom', 'power outage'), ('koorts', 'fever')])


@unittest.skipUnless(NODE, 'needs node on PATH')
class DutchGuideSearch(unittest.TestCase):
    """Dutch everyday words find the guide and situation that cover them, in the Dutch interface."""

    CASES = {
        'brandwond': ['hurt', 'burn'], 'ik heb mijn hand verbrand': ['hurt', 'burn'], 'geen stroom': ['power', 'first-hours'],
        'de stroom is uitgevallen': ['power', 'first-hours'], 'kraanwater onveilig': ['water', 'unsafe'],
        'wat moet ik doen bij een overstroming': ['disaster', 'flood'], 'wc trekt niet door': ['sanitation', 'noflush'],
        'ik ruik gas': ['power', 'gas'], 'gaslucht': ['power', 'gas'], 'hartaanval': ['hurt', 'sudden'],
        'reanimeren': ['hurt', 'breathing'], 'slangenbeet': ['hurt', 'snakebite'], 'wespensteek': ['hurt', 'sting'],
        'teek': ['hurt', 'sting'], 'aardbeving': ['disaster', 'earthquake-now'], 'dijkdoorbraak': ['disaster', 'flood'],
        'hoogwater': ['disaster', 'flood'], 'noodpakket': ['disaster', 'pack'], 'nl-alert': ['comms', 'alerts-radio'],
        'koolmonoxide': ['power', 'generator'], 'powerbank': ['power', 'batteries-solar'],
        'telefoon opladen': ['power', 'batteries-solar'], 'koelkast stroomuitval': ['food', 'outage'],
        'ik heb geen eten meer': ['food', 'lowfood'], 'hittegolf': ['shelter', 'heat'],
        'het vriest en de verwarming is uit': ['shelter', 'cold'], 'diarree baby': ['hurt', 'diarrhea'],
        'botbreuk': ['hurt', 'bone'], 'verstuikte enkel': ['hurt', 'bone'], 'hersenschudding': ['hurt', 'head'],
        'allergische reactie': ['hurt', 'allergy'], 'vergiftiging': ['hurt', 'poison'], 'zelfmoord': ['health', 'mind'],
        'zaad bewaren': ['grow', 'save-seed'], 'kiespijn': ['health', 'teeth'], 'lassen': ['repair', 'weld'],
        'kompas': ['comms', 'navigate'], 'zendamateur': ['comms', 'ham'], 'afval': ['sanitation', 'garbage'],
        'handen wassen': ['sanitation', 'hands'], 'geen verwarming': ['shelter', 'cold'],
        # the example searches on Home (web/app.js HOME_EXAMPLES.nl); "wc" becomes "toilet" there, as here
        'water koken': ['water', 'boil'], 'snee blijft bloeden': ['hurt', 'bleeding'], 'toilet werkt niet': ['sanitation', 'noflush'],
    }

    @classmethod
    def setUpClass(cls):
        import server
        app = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        qstop = re.search(r"const QSTOP = new Set\('([^']*)'\.split", app).group(1).split(' ')
        nl = re.search(r"const QSTOP_NL = new Set\(\[\.\.\.QSTOP, \.\.\.'([^']*)'\.split", app).group(1).split(' ')
        tr = server.topic_translations('nl')
        topics = [server.translate_topic(t, tr[t['id']], 'nl') for t in server.topics()]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'cases.json'
            p.write_text(json.dumps({'stop': qstop + nl, 'topics': topics, 'queries': list(cls.CASES)}, ensure_ascii=False),
                         encoding='utf-8')
            r = subprocess.run([NODE, str(ROOT / 'app' / 'tests' / 'topic_search_nl.mjs'), str(ROOT / 'web' / 'words.js'), str(p)],
                               capture_output=True, text=True, encoding='utf-8', timeout=60)
        if r.returncode:
            raise AssertionError(r.stderr[-1500:])
        cls.found = json.loads(r.stdout)

    def test_first_guide_and_situation(self):
        for q, want in self.CASES.items():
            with self.subTest(q=q):
                self.assertTrue(self.found[q], 'found nothing')
                self.assertEqual(self.found[q][0], want)


if __name__ == '__main__':
    unittest.main()
