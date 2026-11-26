#!/usr/bin/env python3
"""content/emergency/<CC>.json: every number names its source and the day it was checked (format: content/emergency/SCHEMA.md).

  python3 -B -m unittest app.tests.test_emergency_numbers

Two parts: the real files are checked, and the checker itself is shown to fail on a row with no source, no date or a
number that is not a number, so a passing run means something.
"""
import copy, json, os, re, sys, unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
DIR = Path(__file__).resolve().parents[2] / 'content' / 'emergency'

KINDS = {'general', 'ambulance', 'fire', 'police', 'poison', 'crisis', 'other'}
HOW = {'call', 'sms', 'chat', 'app'}
WORKS_FROM = {'mobile', 'landline', 'voip'}
VERIFIED = {'official', 'found_online'}
COUNTRY_KEYS = {'country', 'code', 'calling_code', 'languages', 'general', 'services'}
SERVICE_KEYS = {'kind', 'name', 'number', 'how', 'works_from', 'works_from_source', 'free', 'free_source', 'keywords',
                'when', 'source', 'url', 'area_whole_country', 'area', 'checked_on', 'verified'}
LANG = re.compile(r'[a-z]{2}')   # ISO 639-1: two letters, as in es, en, qu, ay, gn (no region such as es-cl, no 3-letter code)
MAX_LANGUAGES = 4   # up to 4 main languages per country. In a dataset of 237 countries and territories, 99.6% name 4 or fewer
#                     official languages; the cap says "main", not "official" (Bolivia, South Africa and India list many more).
NUMBER = re.compile(r'^[+*]?[0-9][0-9 ]*$')
CALLING_CODE = re.compile(r'^\+[0-9]{1,3}$')   # ITU country calling codes have one to three digits
SOURCE = re.compile(r'^https?://[^\s/]+\.[^\s/]+\S*$')


# The last day a number in content/emergency/ may be dated. The real files are checked against this day, not against the
# computer's clock, so the result is the same on every machine and every day, even where the clock or the time zone is
# off. Whoever adds or re-checks a number sets it to that day, in the same change. A row dated after it fails.
REFERENCE_DATE = date(2026, 11, 25)


def latest_checked_date(now=None):
    """The latest day a number can honestly say it was checked on: today's date in the earliest time zone on Earth
    (UTC+14), from the clock in UTC. A person in Chile or Europe may check a number after their midnight while a machine
    behind them is still on the day before, so the machine's own date would call that "the future" and fail. A day more
    than that is the future everywhere."""
    now = now or datetime.now(timezone.utc)
    return (now.astimezone(timezone.utc) + timedelta(hours=14)).date()


def source(x):
    return isinstance(x, str) and bool(SOURCE.match(x))


def one_of(x, allowed):
    """A string that is one of `allowed`. Tested by type first: a list or a number must fail, not crash the check."""
    return isinstance(x, str) and x in allowed


def choices(x, allowed):
    """A list whose every item is a string from `allowed` (it may be empty: the callers decide)."""
    return isinstance(x, list) and all(one_of(i, allowed) for i in x)


def words(x):
    return isinstance(x, list) and bool(x) and all(isinstance(w, str) and w.strip() and w == w.lower() for w in x)


def problems(data, name, latest=None):
    """What is wrong with one country's table, as a list of plain lines. Empty when it is sound. `latest` is the last
    day a check may be dated (default: latest_checked_date()); the tests below give it a fixed day."""
    latest = latest or latest_checked_date()
    if not isinstance(data, dict):
        return [f'{name}: the file must hold one object']
    out = []
    code = name[:-5] if name.endswith('.json') else name
    if not re.fullmatch(r'[A-Z]{2}', code):
        out.append(f'{name}: the file name must be the two-letter country code in capitals, such as CL.json')
    for key in sorted(set(data) - COUNTRY_KEYS):
        out.append(f'{name}: unknown key {key!r} (a typo? the allowed keys are in SCHEMA.md)')
    if data.get('code') != code:
        out.append(f'{name}: "code" is {data.get("code")!r}, but the file name says {code!r}')
    if not isinstance(data.get('country'), str) or not data['country'].strip():
        out.append(f'{name}: "country" is missing')
    if not isinstance(data.get('calling_code'), str) or not CALLING_CODE.match(data['calling_code']):
        out.append(f'{name}: "calling_code" must be + and digits, such as +56')
    langs = data.get('languages')
    langs_ok = (isinstance(langs, list) and bool(langs) and all(isinstance(c, str) and LANG.fullmatch(c) for c in langs)
                and len(set(langs)) == len(langs) and len(langs) <= MAX_LANGUAGES)
    if not langs_ok:
        out.append(f'{name}: "languages" is required: the country\'s main languages as codes without a region, '
                   f'such as ["es"], each listed once, at most {MAX_LANGUAGES}')
    services = data.get('services')
    if not isinstance(services, list) or not services:
        return out + [f'{name}: "services" must list at least one number']
    numbers = set()
    for i, s in enumerate(services):
        who = f'{name} services[{i}] ({s.get("name", "?") if isinstance(s, dict) else "?"})'
        if not isinstance(s, dict):
            out.append(f'{who}: not an object')
            continue
        if not one_of(s.get('kind'), KINDS):
            out.append(f'{who}: "kind" {s.get("kind")!r} is not one of {sorted(KINDS)}')
        if not isinstance(s.get('name'), str) or not s['name'].strip():
            out.append(f'{who}: "name" is missing')
        n = s.get('number')
        if not isinstance(n, str) or not NUMBER.match(n):
            out.append(f'{who}: "number" must be digits and spaces only (a leading + or * is allowed): {n!r}')
        elif n in numbers:
            out.append(f'{who}: "number" {n} is listed twice in this file')
        else:
            numbers.add(n)
        v = s.get('how')
        if not choices(v, HOW) or not v:
            out.append(f'{who}: "how" must be a non-empty list from {sorted(HOW)}')
        v = s.get('works_from')   # empty: the source does not say
        if not choices(v, WORKS_FROM):
            out.append(f'{who}: "works_from" must be a list from {sorted(WORKS_FROM)}, empty if the source does not say')
        k = s.get('keywords')
        if not isinstance(k, dict) or not all(isinstance(c, str) and words(w) for c, w in k.items()) or not k:
            out.append(f'{who}: "keywords" must map language codes to non-empty lower-case word lists')
        elif langs_ok and set(k) != set(langs) | {'en'}:
            want = sorted(set(langs) | {'en'})
            out.append(f'{who}: "keywords" must have exactly the country\'s languages plus "en" {want}, found {sorted(k)}')
        for key in sorted(set(s) - SERVICE_KEYS):
            out.append(f'{who}: unknown key {key!r} (a typo? the allowed keys are in SCHEMA.md)')
        if 'area_whole_country' in s and not isinstance(s['area_whole_country'], bool):
            out.append(f'{who}: "area_whole_country" is optional, but when present it must be true or false')
        if 'area' in s and (not isinstance(s['area'], str) or not s['area'].strip()):
            out.append(f'{who}: "area" is optional, but when present it must be the specific place the number covers')
        elif 'area' in s and s.get('area_whole_country') is True:
            out.append(f'{who}: "area_whole_country" is true, so there is no specific "area"; leave "area" out')
        if 'url' in s and not source(s['url']):
            out.append(f'{who}: "url" is optional, but when present it must be the web address of the service\'s own page')
        # Each claim about how the number can be reached has its own source, so an editor can check it alone.
        if s.get('works_from') and not source(s.get('works_from_source')):
            out.append(f'{who}: "works_from" is listed, so "works_from_source" must be the address of the page that says so')
        if not s.get('works_from') and s.get('works_from_source') is not None:
            out.append(f'{who}: "works_from" is empty (unknown), so leave "works_from_source" out')
        if 'free' not in s or not (s['free'] is None or isinstance(s['free'], bool)):   # 0 and 1 are not booleans
            out.append(f'{who}: "free" must be true, false or null (null: the sources do not say)')
        elif s['free'] is not None and not source(s.get('free_source')):
            out.append(f'{who}: "free" is {str(s["free"]).lower()}, so "free_source" must be the address of the page that says so')
        elif s['free'] is None and s.get('free_source') is not None:
            out.append(f'{who}: "free" is null (unknown), so leave "free_source" out')
        if not isinstance(s.get('when'), str):
            out.append(f'{who}: "when" must be a string (empty if there is nothing to add)')
        src = s.get('source')
        if not (source(src) or (isinstance(src, list) and src and all(source(x) for x in src))):
            out.append(f'{who}: "source" must be the web address of the page the number was read from')
        c = s.get('checked_on')
        try:
            d = date.fromisoformat(c)
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', c):
                raise ValueError
            if d > latest:
                out.append(f'{who}: "checked_on" {c} is after the last allowed day, {latest}')
        except (TypeError, ValueError):
            out.append(f'{who}: "checked_on" must be a date as YYYY-MM-DD')
        if not one_of(s.get('verified'), VERIFIED):
            out.append(f'{who}: "verified" must be one of {sorted(VERIFIED)}')
    g = data.get('general')
    if g is not None and (not isinstance(g, str) or g not in numbers):
        out.append(f'{name}: "general" is {g!r}, which is not the number of any service')
    return out


class Files(unittest.TestCase):
    def check_all(self, latest):
        files = sorted(DIR.glob('*.json'))
        self.assertTrue(files, 'no country files in content/emergency/')
        for f in files:
            with self.subTest(f.name):
                data = json.loads(f.read_text(encoding='utf-8'))
                self.assertEqual(problems(data, f.name, latest=latest), [])

    def test_every_file_is_sound(self):
        """Against the fixed REFERENCE_DATE: needs no right clock."""
        self.check_all(REFERENCE_DATE)

    @unittest.skipUnless(os.environ.get('LASTBOOK_CHECK_CLOCK') == '1',
                         "off by default: it trusts the clock of this computer; set LASTBOOK_CHECK_CLOCK=1 to run it")
    def test_no_file_is_dated_in_the_future_by_the_clock(self):
        """Against the computer's own clock (UTC+14 rule): catches a date later than the day it really is, which the
        fixed REFERENCE_DATE cannot. Only as right as the clock of the computer that runs it."""
        self.check_all(latest_checked_date())

    def test_the_reference_date_is_not_older_than_the_data(self):
        """Raising a row's date past REFERENCE_DATE fails the test above; this says why, in plain words."""
        newest = max(date.fromisoformat(s['checked_on']) for f in DIR.glob('*.json')
                     for s in json.loads(f.read_text(encoding='utf-8'))['services'])
        self.assertLessEqual(newest, REFERENCE_DATE, 'a number is dated after REFERENCE_DATE: set REFERENCE_DATE to that day')


class Checker(unittest.TestCase):
    GOOD = {
        'country': 'Springfield', 'code': 'ZZ', 'calling_code': '+99', 'languages': ['es'], 'general': '911',
        'services': [{
            'kind': 'general', 'name': 'Emergency', 'number': '911', 'how': ['call'],
            'works_from': ['mobile', 'landline'], 'keywords': {'es': ['emergencia'], 'en': ['emergency']},
            'works_from_source': 'https://example.org/dialling', 'free': True, 'free_source': 'https://example.org/costs',
            'when': '', 'source': 'https://example.org/numbers', 'checked_on': '2026-11-01', 'verified': 'official'}],
    }

    def bad(self, **change):
        d = copy.deepcopy(self.GOOD)
        for k, v in change.items():
            if k.startswith('s_'):
                d['services'][0][k[2:]] = v
            else:
                d[k] = v
        return problems(d, 'ZZ.json', latest=date(2026, 11, 22))

    def test_a_sound_table_passes(self):
        self.assertEqual(problems(self.GOOD, 'ZZ.json', latest=date(2026, 11, 22)), [])

    def test_no_source_fails(self):
        self.assertTrue(self.bad(s_source=''))
        self.assertTrue(self.bad(s_source='not an address'))
        d = copy.deepcopy(self.GOOD)
        del d['services'][0]['source']
        self.assertTrue(problems(d, 'ZZ.json'))

    def test_no_date_fails(self):
        d = copy.deepcopy(self.GOOD)
        del d['services'][0]['checked_on']
        self.assertTrue(problems(d, 'ZZ.json'))
        self.assertTrue(self.bad(s_checked_on='yesterday'))
        self.assertTrue(self.bad(s_checked_on='2026-13-01'))
        self.assertTrue(self.bad(s_checked_on='20261101'))

    def test_a_date_in_the_future_fails(self):
        self.assertFalse(self.bad(s_checked_on='2026-11-22'))   # the last day allowed
        self.assertTrue(self.bad(s_checked_on='2026-11-23'))    # one day past it
        self.assertTrue(self.bad(s_checked_on='2026-12-01'))

    def test_the_last_day_allowed_is_the_same_whatever_the_machine_clock_says(self):
        """Fixed moments, not the real clock. 10:00 UTC is midnight in UTC+14: from then on, that next day has begun
        somewhere, so a number checked there may carry it; one minute earlier it has not."""
        utc = timezone.utc
        for now, day in ((datetime(2026, 11, 21, 9, 59, tzinfo=utc), date(2026, 11, 21)),
                         (datetime(2026, 11, 21, 10, 0, tzinfo=utc), date(2026, 11, 22)),
                         (datetime(2026, 11, 21, 23, 59, tzinfo=utc), date(2026, 11, 22)),
                         (datetime(2026, 11, 22, 0, 0, tzinfo=utc), date(2026, 11, 22)),
                         (datetime(2026, 11, 22, 9, 59, tzinfo=timezone(timedelta(hours=-11))), date(2026, 11, 23))):
            with self.subTest(now=now.isoformat()):
                self.assertEqual(latest_checked_date(now), day)

    def test_a_number_that_is_not_a_number_fails(self):
        for n in ('', 'call 911', '9-1-1', '911.', None, 911):
            with self.subTest(n):
                self.assertTrue(self.bad(s_number=n))
        self.assertFalse(self.bad(s_number='+56 2 2635 3800', general=None))
        self.assertFalse(self.bad(s_number='*4141', general=None))

    def test_a_claim_without_its_own_source_fails(self):
        self.assertTrue(self.bad(s_works_from_source=''))
        self.assertTrue(self.bad(s_free_source=None))
        self.assertTrue(self.bad(s_free='yes'))
        d = copy.deepcopy(self.GOOD)
        del d['services'][0]['free']
        self.assertTrue(problems(d, 'ZZ.json'))

    def test_a_claim_left_unknown_must_not_keep_its_source(self):
        # Clearing the claim but leaving the address behind: the source would now back nothing.
        self.assertTrue(self.bad(s_works_from=[]))
        self.assertTrue(self.bad(s_free=None))

    def test_a_claim_left_unknown_needs_no_source(self):
        self.assertFalse(self.bad(s_works_from=[], s_works_from_source=None, s_free=None, s_free_source=None))
        self.assertFalse(self.bad(s_free=False))

    def test_unknown_words_fail(self):
        self.assertTrue(self.bad(s_kind='hospital'))
        self.assertTrue(self.bad(s_verified='probably'))
        self.assertTrue(self.bad(s_how=['pigeon']))
        self.assertTrue(self.bad(s_works_from=['telepathy']))
        self.assertTrue(self.bad(s_how=[]))
        self.assertFalse(self.bad(s_works_from=[], s_works_from_source=None))

    def test_the_file_name_must_match_the_code(self):
        self.assertTrue(problems(self.GOOD, 'zz.json', latest=date(2026, 11, 22)))
        self.assertTrue(problems(self.GOOD, 'YY.json', latest=date(2026, 11, 22)))

    def test_general_must_be_a_listed_number(self):
        self.assertTrue(self.bad(general='112'))

    def test_keywords_are_tagged_by_language_and_lower_case(self):
        self.assertFalse(self.bad(languages=['es', 'qu'], s_keywords={'es': ['emergencia'], 'qu': ['ratu'], 'en': ['emergency']}))
        self.assertTrue(self.bad(s_keywords={'es': ['Emergencia'], 'en': ['emergency']}))   # upper case
        self.assertTrue(self.bad(s_keywords={'local': ['emergencia'], 'en': ['emergency']}))  # "local" is not a language
        self.assertTrue(self.bad(s_keywords={'es': [], 'en': ['emergency']}))                # empty list
        self.assertTrue(self.bad(s_keywords={}))

    def test_languages_are_required_and_are_codes_without_a_region(self):
        d = copy.deepcopy(self.GOOD)
        del d['languages']
        self.assertTrue(problems(d, 'ZZ.json', latest=date(2026, 11, 22)))                  # missing
        for v in ([], 'es', ['es', 'es'], ['es-cl'], ['ES'], ['e'], [''], [5], None):
            self.assertTrue(self.bad(languages=v), repr(v))
        self.assertFalse(self.bad(languages=['es', 'en'], s_keywords={'es': ['emergencia'], 'en': ['emergency']}))

    def test_keywords_cover_exactly_the_country_languages_plus_english(self):
        multi = {'languages': ['es', 'qu', 'ay']}
        full = {'es': ['emergencia'], 'qu': ['ratu'], 'ay': ['jan walt'], 'en': ['emergency']}
        self.assertFalse(self.bad(s_keywords=full, **multi))
        for drop in ('es', 'qu', 'ay', 'en'):                    # a language of the country, or English, left out
            self.assertTrue(self.bad(s_keywords={c: w for c, w in full.items() if c != drop}, **multi), drop)
        self.assertTrue(self.bad(s_keywords={**full, 'gn': ['mba']}, **multi))                 # a language the country did not list
        self.assertTrue(self.bad(s_keywords={**full, 'qu': []}, **multi))                      # listed but empty
        self.assertTrue(self.bad(s_keywords={'es': ['emergencia'], 'en': ['emergency']}, **multi))   # one language of three

    def test_a_keyword_language_with_a_region_fails(self):
        # The language only: "es", never "es-cl" (one list of Spanish words serves every Spanish-speaking country).
        for code in ('es-cl', 'es-CL', 'es_cl', 'es-419', 'ES', 'e', 'espa', "es\n", ''):
            self.assertTrue(self.bad(s_keywords={code: ['emergencia'], 'en': ['emergency']}), repr(code))
            self.assertTrue(self.bad(languages=[code], s_keywords={code: ['emergencia'], 'en': ['emergency']}), repr(code))
        self.assertFalse(self.bad(s_keywords={'es': ['emergencia'], 'en': ['emergency']}))

    def test_languages_are_two_letter_iso_639_1_codes(self):
        for code in ('esp', 'spa', 'es1', '1a', 'é', 'e s', 'ES'):
            self.assertTrue(self.bad(languages=[code], s_keywords={code: ['x'], 'en': ['y']}), repr(code))
        self.assertFalse(self.bad(languages=['qu'], s_keywords={'qu': ['ratu'], 'en': ['emergency']}))

    def test_a_country_lists_at_most_four_main_languages(self):
        four = ['es', 'qu', 'ay', 'gn']
        self.assertFalse(self.bad(languages=four, s_keywords={**{c: ['x'] for c in four}, 'en': ['y']}))
        five = four + ['fr']
        self.assertTrue(self.bad(languages=five, s_keywords={**{c: ['x'] for c in five}, 'en': ['y']}))

    def test_calling_code_is_plus_and_one_to_three_digits(self):
        for ok in ('+1', '+56', '+591'):
            self.assertFalse(self.bad(calling_code=ok), ok)
        for no in ('+1234', '+123123123', '+', '56', '+5a', '++56', '+ 56', '+-5', ''):
            self.assertTrue(self.bad(calling_code=no), repr(no))

    def test_a_typo_in_a_key_fails(self):
        self.assertTrue(self.bad(s_works_form=['mobile']))
        self.assertTrue(self.bad(countri='Chile'))

    def test_a_number_listed_twice_fails(self):
        d = copy.deepcopy(self.GOOD)
        d['services'].append(copy.deepcopy(d['services'][0]))
        self.assertTrue(problems(d, 'ZZ.json', latest=date(2026, 11, 22)))

    def test_source_may_be_one_address_or_a_list_of_addresses(self):
        self.assertFalse(self.bad(s_source=['https://example.org/a', 'https://example.org/b']))
        for v in ([], ['not an address'], ['https://example.org/a', ''], None):
            self.assertTrue(self.bad(s_source=v), v)

    def test_area_whole_country_is_yes_or_no_and_area_is_a_specific_place(self):
        self.assertFalse(self.bad(s_area_whole_country=True))
        self.assertFalse(self.bad(s_area_whole_country=False, s_area='Comuna de San Miguel'))
        self.assertFalse(self.bad(s_area='Comuna de San Miguel'))
        for v in ('yes', 1, None):
            self.assertTrue(self.bad(s_area_whole_country=v), v)
        for v in ('', '  ', None, 5):
            self.assertTrue(self.bad(s_area=v), v)
        self.assertTrue(self.bad(s_area_whole_country=True, s_area='Comuna de San Miguel'))   # contradiction

    def test_url_is_optional_but_must_be_an_address(self):
        self.assertFalse(self.bad())
        self.assertFalse(self.bad(s_url='https://example.org/service'))
        for v in ('', None, 'not an address', 5):
            self.assertTrue(self.bad(s_url=v), v)


# The JSON type each field must hold, written once and apart from problems(), so the two can disagree and a test fail.
# 'text' = a string, 'bool' = true/false only (never 0 or 1), 'bool?' = true/false/null, 'list' = a list of strings,
# 'map' = an object of language code to list of strings. 'text?' fields are optional: they may be missing.
SERVICE_TYPES = {
    'kind': 'text', 'name': 'text', 'number': 'text', 'how': 'list', 'works_from': 'list', 'works_from_source': 'text?',
    'free': 'bool?', 'free_source': 'text?', 'keywords': 'map', 'when': 'text', 'source': 'text|list',
    'url': 'text', 'area_whole_country': 'bool', 'area': 'text', 'checked_on': 'text', 'verified': 'text',
}
COUNTRY_TYPES = {'country': 'text', 'code': 'text', 'calling_code': 'text', 'languages': 'list', 'general': 'text?',
                 'services': 'list of rows'}
OPTIONAL = {'works_from_source', 'free_source', 'url', 'area_whole_country', 'area'}   # may be missing; `free` may not


def has_type(v, kind):
    """Strictly the JSON type: bool is not a number here and a number is not a bool."""
    for k in kind.rstrip('?').split('|'):
        if k == 'text' and isinstance(v, str):
            return True
        if k in ('bool',) and isinstance(v, bool):
            return True
        if k == 'list' and isinstance(v, list) and all(isinstance(i, str) for i in v):
            return True
        if k == 'map' and isinstance(v, dict) and all(isinstance(c, str) and isinstance(w, list)
                                                      and all(isinstance(i, str) for i in w) for c, w in v.items()):
            return True
        if k == 'list of rows' and isinstance(v, list) and all(isinstance(i, dict) for i in v):
            return True
    return kind.endswith('?') and v is None


class Types(unittest.TestCase):
    """Every value of every row is the kind of value its field holds, and a wrong kind fails without crashing."""
    JUNK = [0, 1, -1, 1.5, True, False, None, '', ' ', 'x', 'true', [], [0], [1], [None], [[]], [{}], {}, {'a': 1}, {'es': 'x'}]

    def test_every_value_of_every_real_row_has_its_field_type(self):
        for f in sorted(DIR.glob('*.json')):
            data = json.loads(f.read_text(encoding='utf-8'))
            for key, kind in COUNTRY_TYPES.items():
                with self.subTest(file=f.name, field=key):
                    self.assertTrue(has_type(data.get(key), kind), f'{key} must be {kind}: {data.get(key)!r}')
            for i, s in enumerate(data['services']):
                for key, value in s.items():
                    with self.subTest(file=f.name, row=f'{i} {s["number"]}', field=key):
                        self.assertIn(key, SERVICE_TYPES)
                        self.assertTrue(has_type(value, SERVICE_TYPES[key]), f'{key} must be {SERVICE_TYPES[key]}: {value!r}')
                for key in set(SERVICE_TYPES) - OPTIONAL:
                    self.assertIn(key, s, f'{f.name} row {i} ({s["number"]}) lacks "{key}"')

    def test_a_value_of_the_wrong_type_fails_and_never_crashes(self):
        good = Checker.GOOD
        for key, kind in SERVICE_TYPES.items():
            for junk in self.JUNK:
                if has_type(junk, kind):
                    continue
                d = copy.deepcopy(good)
                d['services'][0][key] = junk
                with self.subTest(field=key, value=junk):
                    self.assertTrue(problems(d, 'ZZ.json', latest=date(2026, 11, 22)), f'{key}={junk!r} passed')
        for key, kind in COUNTRY_TYPES.items():
            for junk in self.JUNK:
                if has_type(junk, kind) and key != 'services':
                    continue
                d = copy.deepcopy(good)
                d[key] = junk
                with self.subTest(field=key, value=junk):
                    self.assertTrue(problems(d, 'ZZ.json', latest=date(2026, 11, 22)), f'{key}={junk!r} passed')

    def test_free_is_a_json_boolean_or_null_never_a_number(self):
        for ok in (True, False):
            self.assertFalse(Checker().bad(s_free=ok))
        self.assertFalse(Checker().bad(s_free=None, s_free_source=None))
        for n in (0, 1, 0.0, 1.0):
            self.assertTrue(Checker().bad(s_free=n), n)
        self.assertTrue(Checker().bad(s_free=0, s_free_source=None))
        self.assertTrue(Checker().bad(s_area_whole_country=0))
        self.assertTrue(Checker().bad(s_area_whole_country=1))

    def test_a_file_that_is_not_an_object_fails(self):
        for v in ([], 'x', 5, None):
            self.assertTrue(problems(v, 'ZZ.json'))


if __name__ == '__main__':
    unittest.main()
