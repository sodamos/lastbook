#!/usr/bin/env python3
"""content/topics-i18n/<lang>/<id>.json: translated guide words (format: content/topics-i18n/README.md).

  python3 -B -m unittest app.tests.test_topic_translations

Every key must be a string the English guide still has (a stale translation fails), every guide string must have a
translation in a language that claims to be complete, and server.py must put the translation in place for that
language only, leaving readings, page numbers and English untouched.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOPICS = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'content' / 'topics').glob('*.json'))}
I18N = ROOT / 'content' / 'topics-i18n'
COMPLETE = {'nl'}       # languages whose every guide string is translated; a missing one fails


def guide_strings(t):
    """The English strings a translation covers, in the fields server.translate_topic translates."""
    out = [t.get(k) for k in ('title', 'short', 'intro')]
    for c in t.get('choices', []):
        out += [c.get('label'), c.get('hint')]
    out += [x.get('text') for x in t.get('limits', [])]
    for s in t.get('route', []):
        out += [s.get('title'), s.get('goal')]
    return [s for s in out if isinstance(s, str) and s.strip()]


def translations(lang):
    return {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in sorted((I18N / lang).glob('*.json'))}


class Files(unittest.TestCase):
    def test_every_translation_is_sound_and_current(self):
        for folder in sorted(p for p in I18N.iterdir() if p.is_dir()):
            for name, data in translations(folder.name).items():
                with self.subTest(lang=folder.name, guide=name):
                    self.assertIn(name, TOPICS, 'a translation for a guide that does not exist')
                    self.assertEqual(data.get('id'), name)
                    self.assertLessEqual(set(data), {'id', 'tile', 'keywords', 'text'})
                    self.assertTrue(isinstance(data.get('tile'), str) and data['tile'].strip())
                    words = data.get('keywords', [])
                    self.assertTrue(all(isinstance(w, str) and w.strip() and w == w.lower() for w in words), words)
                    self.assertEqual(len(words), len(set(words)), 'a keyword listed twice')
                    english = set(guide_strings(TOPICS[name]))
                    stale = [k for k in data['text'] if k not in english]
                    self.assertEqual(stale, [], 'keys that match no English string of the guide (the English changed?)')
                    empty = [k for k, v in data['text'].items() if not (isinstance(v, str) and v.strip())]
                    self.assertEqual(empty, [])

    def test_complete_languages_cover_every_guide_string(self):
        for lang in COMPLETE:
            have = translations(lang)
            for name, topic in TOPICS.items():
                with self.subTest(lang=lang, guide=name):
                    self.assertIn(name, set(have), 'guide has no translation')
                    missing = [s for s in guide_strings(topic) if s not in have[name]['text']]
                    self.assertEqual(missing, [])


class Dutch(unittest.TestCase):
    """The Dutch guides keep docs/i18n.md#dutch-nl: "je", never "u"; and a US emergency number is never left alone."""

    @classmethod
    def setUpClass(cls):
        cls.nl = translations('nl')
        cls.values = [v for d in cls.nl.values() for v in d['text'].values()] + [d['tile'] for d in cls.nl.values()]

    def test_informal_address_only(self):
        formal = [v for v in self.values if re.search(r'\b(u|uw|uzelf)\b', v, flags=re.IGNORECASE)]
        self.assertEqual(formal, [])

    def test_us_numbers_name_the_dutch_one(self):
        for v in self.values:
            if re.search(r'\b9-?1-?1\b', v):
                with self.subTest(text=v):
                    self.assertIn('112', v)

    def test_no_space_before_ellipsis_and_no_english_left(self):
        for name, data in self.nl.items():
            for en, nl in data['text'].items():
                with self.subTest(guide=name, text=en):
                    self.assertNotIn(' …', nl)
                    if len(en.split()) > 2:
                        self.assertNotEqual(en, nl, 'left in English')


class Server(unittest.TestCase):
    """server.translate_topic and topics_resolved: translated words in place, everything else as it was."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        import server
        cls.server = server

    def test_dutch_words_replace_english_only_where_translated(self):
        s = self.server
        water = TOPICS['water']
        out = s.translate_topic(water, s.topic_translations('nl')['water'], 'nl')
        self.assertEqual(out['title'], 'Veilig drinkwater')
        self.assertEqual(out['tile'], 'Drinkwater')
        self.assertEqual(out['lang'], 'nl')
        self.assertIn('kraanwater', out['keywords'])
        self.assertTrue(set(water['keywords']) <= set(out['keywords']))       # English searches still find it
        for a, b in zip(water['choices'], out['choices']):
            self.assertEqual(a['id'], b['id'])
            self.assertEqual(a.get('read'), b.get('read'))                     # readings and pages untouched
            self.assertEqual(set(a), set(b))
        for a, b in zip(water['limits'], out['limits']):
            self.assertEqual({k: v for k, v in a.items() if k != 'text'}, {k: v for k, v in b.items() if k != 'text'})
        self.assertNotEqual(water['title'], out['title'])
        self.assertEqual(TOPICS['water']['title'], 'Get safe drinking water')   # the source is not changed in place

    def test_untranslated_string_stays_english(self):
        s = self.server
        tr = {'id': 'water', 'tile': 'Drinkwater', 'text': {'Get safe drinking water': 'Veilig drinkwater'}}
        out = s.translate_topic(TOPICS['water'], tr, 'nl')
        self.assertEqual(out['short'], TOPICS['water']['short'])

    def test_english_unknown_and_odd_languages_get_no_translation(self):
        s = self.server
        for lang in (None, '', 'en', 'xx', '../topics', 'nl/../../etc', 'NL', 'nl\x00'):
            with self.subTest(lang=lang):
                self.assertEqual(s.topic_translations(lang), {})
        self.assertIn('water', s.topic_translations('nl'))


if __name__ == '__main__':
    unittest.main()
