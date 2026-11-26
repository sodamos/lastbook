"""Catalogue schema, deterministic generation and the release staging gate."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packaging'))
import i18n_catalogs as catalogues  # noqa: E402


class Catalogues(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.english = self.work / 'en.json'
        self.spanish = self.work / 'es-419.json'
        self.english.write_text('{"hi":"Hello, {name}", "files":{"=0":"None", "other":"{count} files"}}', encoding='utf-8')
        self.spanish.write_text('{"hi":"Hola, {name}"}', encoding='utf-8')

    def test_rejects_missing_catalogues(self):
        for file in (self.english, self.spanish):
            with self.subTest(file=file.name):
                contents = file.read_bytes()
                file.unlink()
                with self.assertRaisesRegex(ValueError, f'missing catalogues: {file.stem}'):
                    catalogues.generate(self.work)
                file.write_bytes(contents)

    def test_rejects_duplicate_keys_at_every_depth(self):
        for text in ('{"hi":"A", "hi":"B"}', '{"files":{"other":"A", "other":"B"}}'):
            self.spanish.write_text(text, encoding='utf-8')
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'duplicate key'):
                catalogues.generate(self.work)

    def test_rejects_invalid_values_and_placeholders(self):
        for value in [None, False, 2, {}, [], '', ' ', '\ufeff \ufeff', '{name', '{{name}}', '{first-name}', '\ud800', {'other': False},
                      {'other': 'a', '=9007199254740992': 'b'}, {'other': 'a', '=01': 'b'}, {'one': 'one'},
                      {'other': 'Hello, {name}', 'one': 'one'}, {'other': 'a', 'notACategory': 'b'}]:
            self.spanish.write_text(json.dumps({'hi': value}), encoding='utf-8')
            with self.subTest(value=value), self.assertRaises(ValueError):
                catalogues.generate(self.work)
        self.spanish.write_bytes(b'{"hi":"\xff {name}"}')
        with self.assertRaisesRegex(ValueError, 'utf-8'):
            catalogues.generate(self.work)

    def test_rejects_unknown_keys_and_incompatible_contracts(self):
        for value, message in [({'__proto__': 'x'}, 'invalid message key'), ({'unknown': 'x'}, 'unknown message key'),
                               ({'hi': 'Hola, {persona}'}, 'incompatible message'),
                               ({'hi': {'other': 'Hola, {name}'}}, 'incompatible message'),
                               ({'files': '{count} archivos'}, 'incompatible message'),
                               ({'files': {'other': '{count} archivos'}}, 'incompatible message')]:
            self.spanish.write_text(json.dumps(value), encoding='utf-8')
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, message):
                catalogues.generate(self.work)

    def test_allows_missing_messages_and_locale_specific_plural_categories(self):
        self.spanish.write_text('{"files":{"=0":"Ninguno", "many":"{count} archivos", "other":"{count} archivos"}}', encoding='utf-8')
        self.assertIn('Ninguno', catalogues.generate(self.work)['i18n-locales.js'].decode('utf-8'))

    def test_output_is_order_independent_and_writes_literal_data(self):
        value = '¡Está listo! \u2028 <img src=x onerror="bad()"> "); bad(); ({name}'
        messages = {'hi': value, 'files': {'other': '{count} archivos', '=0': 'Ninguno'}}
        self.spanish.write_text(json.dumps(messages, ensure_ascii=False), encoding='utf-8')
        first = catalogues.generate(self.work)
        self.spanish.write_text(json.dumps(dict(reversed(list(messages.items())))), encoding='utf-8')
        self.assertEqual(catalogues.generate(self.work), first)
        js = first['i18n-locales.js'].decode('utf-8')
        self.assertIn('¡Está listo!', js)
        self.assertNotIn('\u2028', js)
        literal = js.split(' = JSON.parse(', 1)[1].removesuffix(');\n')
        self.assertEqual(json.loads(json.loads(literal)), {'es-419': messages})

    def test_source_staging_and_missing_or_stale_assets(self):
        generated = catalogues.generate()
        catalogues.check_assets(ROOT / 'web', generated)
        stage = self.work / 'stage'
        subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'packaging' / 'ship_app_files.py'), str(stage)],
                       check=True, capture_output=True)
        web = stage / 'web'
        catalogues.check_assets(web, generated)
        self.assertFalse((stage / 'translations').exists())
        for name in ('i18n-en.js', 'i18n-locales.js', 'i18n-app.js', 'app.js'):
            with self.subTest(name=name):
                (web / name).unlink()
                with self.assertRaisesRegex(ValueError, 'required localization asset missing'):
                    catalogues.check_assets(web, generated)
                shutil.copyfile(ROOT / 'web' / name, web / name)
        (web / 'setup.html').write_text('<!doctype html><title>Old Setup</title>', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'missing or misordered localization scripts'):
            catalogues.check_assets(web, generated)
        setup = (ROOT / 'web' / 'setup.html').read_text(encoding='utf-8')
        script = next(line for line in setup.splitlines() if 'src="/ui/i18n-app.js' in line)
        for bad in ('<!--' + script + '-->', script.replace('src=', 'data-src='), script.replace('<script ', '<script defer ')):
            with self.subTest(script=bad):
                (web / 'setup.html').write_text(setup.replace(script, bad), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'missing or misordered localization scripts'):
                    catalogues.check_assets(web, generated)
        shutil.copyfile(ROOT / 'web' / 'setup.html', web / 'setup.html')
        (web / 'app.js').write_bytes(b'// old controller\n')
        with self.assertRaisesRegex(ValueError, 'packaged web asset differs from source'):
            catalogues.check_assets(web, generated)
        shutil.copyfile(ROOT / 'web' / 'app.js', web / 'app.js')
        (web / 'i18n-locales.js').write_bytes(b'// stale\n')
        with self.assertRaisesRegex(ValueError, 'stale catalogue'):
            catalogues.check_assets(web, generated)


class FallbackWording(unittest.TestCase):
    """language.unavailable is shown in English when the saved language's catalogue cannot load (web/i18n-app.js), whichever
    language that is. The selector offers more than one translated language, so the message must not name one."""

    def test_english_fallback_names_no_language(self):
        en = json.loads((ROOT / 'translations' / 'desktop' / 'en.json').read_text(encoding='utf-8'))
        text = en['language.unavailable']
        self.assertEqual(text, 'The saved language is unavailable. Lastbook is using English.')
        for name in ('Spanish', 'German', 'Chinese', 'Dutch', 'español', 'Deutsch', '中文', 'Nederlands'):
            self.assertNotIn(name, text)


class SimplifiedChineseWording(unittest.TestCase):
    """The zh-Hans catalogue keeps the conventions in docs/i18n.md#simplified-chinese-zh-hans."""

    @classmethod
    def setUpClass(cls):
        load = lambda name: json.loads((ROOT / 'translations' / 'desktop' / name).read_text(encoding='utf-8'))
        cls.en, cls.zh = load('en.json'), load('zh-Hans.json')

    def test_setup_and_settings_are_different_words(self):
        self.assertEqual(self.zh['nav.settings'], '设置')
        self.assertIn('初始设置', self.zh['setup.title'])
        # "初始设置" contains "设置"; the rest of the heading must not say it again.
        self.assertNotIn('设置', self.zh['setup.title'].replace('初始设置', ''))
        # Where a sentence names both screens, it names both.
        self.assertIn('初始设置', self.zh['language.preview'])
        self.assertIn('设置', self.zh['language.preview'])

    def test_simplified_characters_only(self):
        traditional = '設資庫這個們來時間對話選擇頁題導覽視頻標開關閉啟儲載網路線說檔電腦檢區換'
        everything = ' '.join(self.zh.values())
        self.assertEqual([character for character in traditional if character in everything], [])

    def test_everyday_words_and_formatting(self):
        self.assertIn('这台电脑', self.zh['setup.loading'])
        self.assertIn('州或地区', self.zh['setup.chooseIntro'])
        # A space separates Chinese from Latin words, and names stay as they are.
        self.assertIn('Lastbook 会', self.zh['setup.chooseIntro'])
        self.assertEqual(self.zh['setup.settingsTitle'], '资料库与本地 AI')
        # Full-width punctuation, no space before it, no ideographic space.
        everything = ' '.join(self.zh.values())
        for bad in (' ,', ' 。', ' ，', ' ；', ' …', '\u3000', '..'):
            self.assertNotIn(bad, everything)
        self.assertTrue(self.zh['language.saving'].endswith('…'))

    def test_no_message_is_left_in_english(self):
        same = {key for key in self.zh if self.zh[key] == self.en[key]}
        self.assertEqual(same, set())


class GermanWording(unittest.TestCase):
    """The de catalogue keeps the conventions in docs/i18n.md#german-de: formal "Sie" throughout, and fixed words for the screens."""

    @classmethod
    def setUpClass(cls):
        load = lambda name: json.loads((ROOT / 'translations' / 'desktop' / name).read_text(encoding='utf-8'))
        cls.en, cls.de = load('en.json'), load('de.json')

    def test_formal_address_only(self):
        import re
        everything = ' '.join(self.de.values())
        informal = re.findall(r'\b(du|dich|dir|dein\w*|euch|euer\w*|ihr)\b', everything, flags=re.IGNORECASE)
        self.assertEqual(informal, [])
        self.assertIn('Wählen Sie', self.de['setup.chooseIntro'])

    def test_setup_and_settings_are_different_words(self):
        self.assertEqual(self.de['setup.title'], 'Lastbook einrichten')
        self.assertEqual(self.de['nav.settings'], 'Einstellungen')
        self.assertIn('Einrichtung und Einstellungen', self.de['language.preview'])
        self.assertIn('Region', self.de['setup.chooseIntro'])        # not "Bundesstaat": the prompt is for any region

    def test_no_message_is_left_in_english(self):
        same = {key for key in self.de if self.de[key] == self.en[key]}
        self.assertLessEqual(same, {'nav.chat', 'nav.videos', 'nav.video', 'search.filter'})


class DutchWording(unittest.TestCase):
    """The nl catalogue keeps the conventions in docs/i18n.md#dutch-nl: informal "je" throughout, and different words for
    Setup (inrichten) and Settings (Instellingen), which "instellen" and "Instellingen" would not give."""

    @classmethod
    def setUpClass(cls):
        load = lambda name: json.loads((ROOT / 'translations' / 'desktop' / name).read_text(encoding='utf-8'))
        cls.en, cls.nl = load('en.json'), load('nl.json')
        # Plural messages are objects; every form counts.
        cls.texts = [x for v in cls.nl.values() for x in (v.values() if isinstance(v, dict) else [v])]

    def test_informal_address_only(self):
        import re
        everything = ' '.join(self.texts)
        formal = re.findall(r'\b(u|uw|uzelf)\b', everything, flags=re.IGNORECASE)
        self.assertEqual(formal, [])

    def test_setup_and_settings_are_different_words(self):
        self.assertEqual(self.nl['setup.title'], 'Lastbook inrichten')
        self.assertEqual(self.nl['nav.settings'], 'Instellingen')
        everything = ' '.join(self.texts).lower()
        self.assertNotIn('instellen', everything)        # one letter from "instellingen": the screens would blur
        self.assertIn('Inrichten en Instellingen', self.nl['language.preview'])

    def test_everyday_words_and_formatting(self):
        self.assertIn('deze computer', self.nl['setup.loading'].lower())
        self.assertIn('regio', self.nl['setup.chooseIntro'])           # not "staat" or "provincie": any region
        self.assertIn('zonder internet', self.nl['setup.chooseIntro'])
        everything = ' '.join(self.texts)
        self.assertNotIn(' …', everything)                               # no space before an ellipsis in Dutch
        self.assertNotIn("Video's", everything)                          # the typographic apostrophe, as in English
        self.assertEqual(self.nl['language.unavailable'], 'De opgeslagen taal is niet beschikbaar. Lastbook gebruikt Engels.')

    def test_no_message_is_left_in_english(self):
        same = {key for key in self.nl if self.nl[key] == self.en[key]}
        self.assertLessEqual(same, {'nav.chat', 'nav.video', 'search.filter'})


class SpanishWording(unittest.TestCase):
    """The shipped es-419 catalogue keeps the terms docs/i18n.md#sample-locale-wording-es-419 asks for."""

    @classmethod
    def setUpClass(cls):
        load = lambda name: json.loads((ROOT / 'translations' / 'desktop' / name).read_text(encoding='utf-8'))
        cls.en, cls.es = load('en.json'), load('es-419.json')

    def test_setup_and_settings_are_different_words(self):
        self.assertEqual(self.es['nav.settings'], 'Ajustes')
        self.assertIn('Configuración inicial', self.es['setup.title'])
        self.assertIn('configuración inicial', self.es['setup.error'])
        self.assertNotEqual(self.es['nav.settings'], self.es['setup.title'])
        # Where a sentence names both screens, it names both.
        preview = self.es['language.preview']
        self.assertIn('configuración inicial', preview)
        self.assertIn('ajustes', preview)
        self.assertIn('Setup and Settings', self.en['language.preview'])

    def test_state_prompt_and_everyday_words(self):
        self.assertIn('estado o región', self.es['setup.chooseIntro'])
        self.assertIn('computadora', self.es['setup.loading'])
        everything = ' '.join(self.es.values())
        for avoid in (' equipo', 'Equipo', 'ordenador', 'vídeo', 'Vídeo'):
            self.assertNotIn(avoid, everything)
        self.assertEqual(self.es['language.unavailable'], 'El idioma guardado no está disponible. Lastbook usa inglés.')
        self.assertNotIn('está en inglés', self.es['language.unavailable'])

    def test_no_message_is_left_in_english(self):
        # Words that must differ from English (brand names and loan words such as "Chat" may match).
        same = {key for key in self.es if self.es[key] == self.en[key]}
        self.assertLessEqual(same, {'nav.chat', 'nav.videos', 'nav.video'})
