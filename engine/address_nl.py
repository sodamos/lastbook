"""Dutch street addresses, read the way people in the Netherlands write them, from a Dutch province's BAG address index.

The index is addresses/NL-<province>.sqlite, built by tools/build_region_nl.py: one row per BAG address with the house
number as written on a letter ('12', '12A', '12-2'), the street, its normalized form (scheme 'nl-1', in meta), the place
(woonplaats), the postcode ('8911HG') and the municipality. Two ways of writing an address are read:

  Dorpsstraat 12a Leeuwarden        street, house number (letter, addition), optional postcode, optional place
  8911 HG 12                        postcode and house number, the way a parcel label or a form asks for it

Only houses that exist are returned: an exact number first, then, when the number was given without its letter or
addition, the real addresses that share it (12A, 12-1). Nothing is guessed or interpolated."""
import math
import re
import sqlite3
import unicodedata
from pathlib import Path

from engine.paths import ro_uri

NORM = 'nl-1'
SOURCE = 'Kadaster BAG'
POSTCODE = re.compile(r'([1-9][0-9]{3}) ?([A-Za-z]{2})')
# 12, 12a, 12A-2, 12-hs, 12/2: a house number with its letter and addition written onto it.
HOUSE = re.compile(r'([1-9][0-9]{0,4})([A-Za-z])?(?:[-/]([A-Za-z0-9]{1,6}))?')
# Additions people write as a separate word after the number.
ADDITIONS = {'hs', 'huis', 'bis', 'bg', 'i', 'ii', 'iii', 'iv', 'zw', 'rd', 'boven', 'beneden'}
# Places people call by another name than the BAG's woonplaats.
PLACE_NAMES = {'den haag': 's gravenhage', 'the hague': 's gravenhage', 'den bosch': 's hertogenbosch'}
# Titles at the start of a street name, which the BAG writes sometimes in full and sometimes short ("Burgemeester
# Hogguerstraat", "Burg. Breebaartweg"): a search tries the other way too.
TITLES = {'burg': ['burgemeester'], 'dr': ['dokter', 'doctor'], 'mr': ['meester'], 'st': ['sint'], 'prof': ['professor'],
          'pr': ['prins'], 'kon': ['koning', 'koningin'], 'gen': ['generaal'], 'ds': ['dominee'], 'past': ['pastoor'],
          'jhr': ['jonkheer'], 'mgr': ['monseigneur']}
TITLES.update({full: [short] for short, fulls in list(TITLES.items()) for full in fulls})


def normalize(text):
    """Scheme 'nl-1', the same rule as normalize_nl in tools/build_region_nl.py: 'Burg. Jansenstraat' -> 'burg
    jansenstr', 'Ruïnelaan' -> 'ruinelaan', "'s-Gravenhage" -> 's gravenhage'."""
    text = unicodedata.normalize('NFKD', str(text)).lower().replace('’', "'")
    text = ''.join(c for c in text if not unicodedata.combining(c))
    words = re.sub(r'[^a-z0-9 ]+', ' ', text).split()
    return ' '.join(w[:-len('straat')] + 'str' if w.endswith('straat') and len(w) > len('straat') else w for w in words)


def indexes(geo_directory):
    """The Dutch address indexes in this map folder."""
    return sorted(Path(geo_directory).glob('addresses/NL-*.sqlite'))


def has_index(geo_directory):
    return bool(indexes(geo_directory))


def readings(query):
    """The ways to read the query as an address, likeliest first, each (street words, number, letter, addition,
    postcode, place words); [] when it is not an address. A street can hold a number of its own ('Laan 1940-1945 12',
    'Plein 1813 4'), so every number after the first word is a reading, left to right, and find() takes the first that
    names a real house."""
    text = ' '.join(query.replace(',', ' ').split())
    if not text:
        return []
    # Postcode first: '8911 HG 12', '8911HG12', '8911 hg 12a'
    m = re.fullmatch(POSTCODE.pattern + r' ?' + HOUSE.pattern + r'(?: (.+))?', text)
    if m:
        code, number, letter, addition = (m.group(1) + m.group(2)).upper(), m.group(3), m.group(4), m.group(5)
        rest = (m.group(6) or '').split()
        if rest and rest[0].lower() in ADDITIONS and not addition:
            addition, rest = rest[0], rest[1:]
        return [([], number, letter, addition, code, rest)]
    words, out = text.split(), []
    for i, word in enumerate(words):
        house = HOUSE.fullmatch(word)
        if not house or i == 0:
            continue
        if re.fullmatch(r'[0-9]{4}', word) and i + 1 < len(words) and re.fullmatch(r'[A-Za-z]{2}', words[i + 1]):
            continue                                               # the digits of a postcode, not a house number
        street, rest = words[:i], words[i + 1:]
        number, letter, addition = house.group(1), house.group(2), house.group(3)
        if rest and not letter and not addition and re.fullmatch(r'[A-Za-z]', rest[0]):
            letter, rest = rest[0], rest[1:]                       # 'Dorpsstraat 12 a'
        if rest and not addition and rest[0].lower() in ADDITIONS:
            addition, rest = rest[0], rest[1:]                     # 'Dorpsstraat 12 hs'
        code = ''
        joined = ' '.join(rest)
        pc = re.match(POSTCODE.pattern + r'\b', joined)
        if pc:
            code, rest = (pc.group(1) + pc.group(2)).upper(), joined[pc.end():].split()
        out.append((street, number, letter, addition, code, rest))
    return out


def written(number, letter=None, addition=None):
    """As the index writes it: '12', '12A', '12-2', '12A-hs'."""
    out = number + (letter or '').upper()
    return f'{out}-{addition}' if addition else out


def show_postcode(code):
    return f'{code[:4]} {code[4:]}' if code else ''


def find(query, geo_directory, limit=8, near=None):
    """Existing Dutch addresses for the query, best first, as place-finder rows; [] when it is not an address or no such
    house exists."""
    for reading in readings(query):
        found = _find(*reading, geo_directory, limit, near)
        if found:
            return found
    return []


def street_forms(street):
    """The street as typed, then with a title at its start written the other way ('burg x' <-> 'burgemeester x')."""
    words = street.split()
    forms = [street]
    if words and words[0] in TITLES:
        forms += [' '.join([other] + words[1:]) for other in TITLES[words[0]]]
    return forms


def _find(street_words, number, letter, addition, code, place_words, geo_directory, limit, near):
    street = normalize(' '.join(street_words))
    if not street and not code:
        return []
    place = normalize(' '.join(place_words))
    place = PLACE_NAMES.get(place, place)
    exact = written(number, letter, addition).upper()
    wanted = [exact]
    if addition and not letter and re.fullmatch(r'[A-Za-z]', addition):
        wanted.append(written(number, addition))                  # '19-a' is how some write the letter of 19A
    if letter or addition:
        house_sql, house_parameters = f"upper(num) IN ({','.join('?' * len(wanted))})", wanted
    else:   # the number alone: that house, and the real houses that share its number (12A, 12-1)
        house_sql, house_parameters = '(num = ? OR num GLOB ? OR num GLOB ?)', [number, number + '[A-Za-z]*', number + '-*']
    # Ways to find the street, each tried only when the ones before it found nothing: the street as typed (or with a
    # title the other way), a street that starts with it, and last a street that ends in its main word, so that
    # "Dr. Plesmanlaan" finds "Dr. A. Plesmanlaan". That last one reads the whole index, so it comes last.
    forms = street_forms(street) if street else []
    passes = [('norm = ?', [form]) for form in forms] + [('norm > ? AND norm < ?', [form, form + '\uffff']) for form in forms]
    main = max(street.split(), key=len) if street else ''
    if len(main) >= 5:
        passes.append(('norm LIKE ?', ['%' + main + '%']))
    if not street:
        passes = [('1', [])]
    must = [w for w in street.split() if len(w) >= 3 and w not in TITLES]
    rows = []
    for path in indexes(geo_directory):
        try:
            db = sqlite3.connect(ro_uri(path), uri=True)
        except sqlite3.Error:
            continue
        try:
            if dict(db.execute('SELECT key, value FROM meta').fetchall()).get('norm') != NORM:
                continue
            for number_of_pass, (street_sql, street_parameters) in enumerate(passes):
                conditions, parameters = [house_sql, street_sql], house_parameters + street_parameters
                if code:
                    conditions.append('zip = ?')
                    parameters.append(code)
                sql = 'SELECT num, street, norm, city, zip, lat, lon, district FROM addr WHERE ' + ' AND '.join(conditions)
                before = len(rows)
                for row in db.execute(sql + ' LIMIT 5000', parameters):
                    if place and not (normalize(row[3] or '').startswith(place) or normalize(row[7] or '').startswith(place)):
                        continue
                    if street_sql.startswith('norm LIKE') and not all(any(s.startswith(w) for s in row[2].split()) for w in must):
                        continue
                    rows.append(row)
                if len(rows) > before:
                    break
        except sqlite3.Error:
            continue
        finally:
            db.close()
    if not rows:
        return []

    def rank(row):
        km = 0
        if near:
            km = int(111 * math.hypot(row[5] - near[0], (row[6] - near[1]) * math.cos(math.radians(near[0]))))
        base = re.match(r'[0-9]+', row[0])
        # The house asked for first, then the same street name over a longer one, the nearest place (to the kilometre,
        # so one street's houses stay together), and the houses in the order of their numbers: 9, 9A, 9B, 9-1.
        return (row[0].upper() not in wanted, bool(street) and row[2] != street, km, len(row[2]), row[3] or '', row[1],
                int(base.group()) if base else 0, '-' in row[0], row[0])

    out, seen = [], set()
    for num, name, _, city, zip_code, lat, lon, district in sorted(rows, key=rank):
        key = (num, name, city)
        if key in seen:
            continue
        seen.add(key)
        where = ' '.join(part for part in (show_postcode(zip_code), city) if part)
        if district and district != city:
            where += f' ({district})'
        out.append({'name': f'{name} {num}', 'kind': 'Street address', 'detail': where,
                    'lat': lat, 'lon': lon, 'source': SOURCE, 'onMap': True})
        if len(out) == limit:
            break
    return out
