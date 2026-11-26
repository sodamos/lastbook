"""Dutch searches on an English library: everyday Dutch words to the English words the manuals use.

The library's manuals, transcripts and encyclopedias are English, so "brandwond hand" finds nothing there. to_english()
turns a Dutch search into an English one ("burn hand") before the keyword and meaning-based search run. It is a word
list, not a translator: words it does not know stay as they were, so an English search, a product name or a place name
passes through unchanged.

When is a search Dutch? When the person chose Dutch in Settings (the app sends lang=nl), or when it holds a word that
is only Dutch ("brandwond", "het", "mijn"). Words that are also English ("brand", "been", "kind", "door") are only read
as Dutch in a search that is Dutch for one of those reasons, and never in one that holds English-only words ("the",
"how", "my"), so "brand of bleach" and "door is stuck" stay English.

No network, no dependency; engine/ and server.py share it. app/tests/test_dutch_query.py checks it.
"""
import re
import unicodedata

# Dutch phrase or word -> English words the manuals use. Phrases (with a space) are replaced first, longest first.
PHRASES = {
    'eerste hulp': 'first aid', 'pijn op de borst': 'chest pain', 'kan niet ademen': 'not breathing',
    'ademt niet': 'not breathing', 'geen ademhaling': 'not breathing', 'geen stroom': 'power outage',
    'stroom is uitgevallen': 'power outage', 'stroom uitgevallen': 'power outage', 'stroom valt uit': 'power outage',
    'stroom is uit': 'power outage', 'geen water': 'no water', 'geen gas': 'gas outage', 'ik ruik gas': 'gas leak',
    'ruik gas': 'gas leak', 'water koken': 'boil water', 'water zuiveren': 'purify water', 'water bewaren': 'water storage',
    'eten bewaren': 'food storage', 'voedsel bewaren': 'food storage', 'koken zonder stroom': 'cooking without power',
    'gebroken been': 'broken leg', 'gebroken arm': 'broken arm', 'gebroken enkel': 'broken ankle',
    'wc trekt niet door': 'toilet flush', 'wc doortrekken': 'toilet flush', 'handen wassen': 'handwashing',
    'warm blijven': 'stay warm', 'koel blijven': 'stay cool', 'open haard': 'fireplace', 'open vuur': 'open fire',
    'telefoon leeg': 'phone battery dead', 'telefoon opladen': 'charge phone', 'kaart lezen': 'map reading',
    'water halen': 'find water', 'binnen blijven': 'shelter in place', 'ramen en deuren dicht': 'shelter in place',
    'verdacht pakket': 'unattended package', 'te heet': 'heat', 'te koud': 'cold',
}
WORDS = {
    # water
    'drinkwater': 'drinking water', 'kraanwater': 'tap water', 'regenwater': 'rainwater', 'bleekwater': 'bleach',
    'chloor': 'chlorine', 'zuiveren': 'purify', 'zuivering': 'purification', 'ontsmetten': 'disinfect',
    'ontsmetting': 'disinfection', 'gefilterd': 'filtered', 'filteren': 'filter', 'kookadvies': 'boil water notice',
    'koken': 'boil cooking', 'kook': 'boil', 'dorst': 'thirsty', 'put': 'well', 'bron': 'spring', 'beek': 'stream',
    'rivier': 'river', 'sloot': 'ditch', 'gracht': 'canal', 'zeewater': 'seawater', 'zout': 'salt', 'vervuild': 'contaminated',
    'jerrycan': 'water container', 'tabletten': 'tablets', 'boiler': 'water heater',
    # food
    'eten': 'food', 'voedsel': 'food', 'koelkast': 'refrigerator', 'vriezer': 'freezer', 'diepvries': 'freezer',
    'ontdooid': 'thawed', 'bedorven': 'spoiled', 'blik': 'canned', 'blikken': 'cans', 'conserven': 'canned food',
    'houdbaar': 'shelf life', 'voorraad': 'storage', 'noodvoorraad': 'emergency food supply', 'rijst': 'rice',
    'inmaken': 'canning', 'wecken': 'canning', 'weckpot': 'canning jar', 'drogen': 'drying', 'invriezen': 'freezing',
    'inleggen': 'pickling', 'fermenteren': 'fermenting', 'botulisme': 'botulism', 'babyvoeding': 'infant formula',
    'flesvoeding': 'infant formula', 'kampeerbrander': 'camp stove', 'gasstel': 'camp stove', 'barbecue': 'grill',
    # injury and illness
    'ehbo': 'first aid', 'gewond': 'injured', 'letsel': 'injury', 'wond': 'wound', 'wonden': 'wounds',
    'snijwond': 'cut wound', 'schaafwond': 'scrape wound', 'bloeden': 'bleeding', 'bloeding': 'bleeding',
    'bloedt': 'bleeding', 'bloed': 'blood', 'verband': 'bandage', 'pleister': 'bandage', 'drukverband': 'pressure bandage',
    'hechten': 'stitches', 'hechting': 'stitches', 'infectie': 'infection', 'ontstoken': 'infected', 'ontsteking': 'infection',
    'koorts': 'fever', 'griep': 'flu', 'hoesten': 'cough', 'hoest': 'cough', 'diarree': 'diarrhea', 'overgeven': 'vomiting',
    'braken': 'vomiting', 'kotsen': 'vomiting', 'misselijk': 'nausea', 'uitgedroogd': 'dehydration', 'uitdroging': 'dehydration',
    'buikpijn': 'abdominal pain', 'hoofdpijn': 'headache', 'pijn': 'pain', 'pijnstiller': 'painkiller', 'paracetamol': 'paracetamol',
    'medicijn': 'medicine', 'medicijnen': 'medicines', 'medicatie': 'medication', 'geneesmiddel': 'medicine',
    'antibiotica': 'antibiotics', 'insuline': 'insulin', 'suikerziekte': 'diabetes', 'bloeddruk': 'blood pressure',
    'hartaanval': 'heart attack', 'hartstilstand': 'cardiac arrest', 'beroerte': 'stroke', 'herseninfarct': 'stroke',
    'epilepsie': 'seizure', 'stuipen': 'convulsions', 'flauwgevallen': 'fainted', 'flauwvallen': 'fainting',
    'bewusteloos': 'unconscious', 'reanimeren': 'cpr', 'reanimatie': 'cpr', 'beademen': 'rescue breathing',
    'verslikken': 'choking', 'verslikt': 'choking', 'stikken': 'choking', 'ademhaling': 'breathing', 'ademen': 'breathing',
    'verdrinking': 'drowning', 'verdronken': 'drowning', 'botbreuk': 'fracture', 'breuk': 'fracture', 'gebroken': 'broken',
    'verstuikt': 'sprain', 'verstuiking': 'sprain', 'verzwikt': 'sprain', 'ontwricht': 'dislocation', 'ontwrichting': 'dislocation',
    'mitella': 'sling', 'spalk': 'splint', 'knie': 'knee', 'pols': 'wrist', 'nek': 'neck', 'hoofd': 'head',
    'hoofdletsel': 'head injury', 'hersenschudding': 'concussion', 'wervelkolom': 'spine', 'oog': 'eye', 'ogen': 'eyes',
    'tand': 'tooth', 'tanden': 'teeth', 'kies': 'tooth', 'kiespijn': 'toothache', 'tandpijn': 'toothache',
    'brandwond': 'burn', 'brandwonden': 'burns', 'verbrand': 'burn', 'verbranding': 'burn', 'onderkoeling': 'hypothermia',
    'onderkoeld': 'hypothermia', 'bevriezing': 'frostbite', 'hitteberoerte': 'heat stroke', 'zonnesteek': 'heat stroke',
    'oververhit': 'heat exhaustion', 'oververhitting': 'heat exhaustion', 'allergie': 'allergy', 'allergisch': 'allergic',
    'anafylaxie': 'anaphylaxis', 'adrenaline': 'epinephrine', 'epipen': 'epinephrine', 'slangenbeet': 'snakebite',
    'adder': 'snakebite', 'beet': 'bite', 'gebeten': 'bitten', 'hondenbeet': 'dog bite', 'hondsdolheid': 'rabies',
    'steek': 'sting', 'gestoken': 'sting', 'wesp': 'wasp', 'wespensteek': 'wasp sting', 'bijensteek': 'bee sting',
    'teek': 'tick', 'kwal': 'jellyfish', 'vergiftiging': 'poisoning', 'vergiftigd': 'poisoned', 'giftig': 'poisonous',
    'overdosis': 'overdose', 'zwanger': 'pregnant', 'zwangerschap': 'pregnancy', 'bevalling': 'childbirth',
    'bevallen': 'childbirth', 'weeën': 'labor', 'kinderen': 'children', 'ouderen': 'elderly', 'bejaarde': 'elderly',
    'zuigeling': 'infant', 'brancard': 'stretcher', 'ambulance': 'ambulance', 'ziek': 'sick', 'ziekte': 'illness',
    # mind
    'angst': 'anxiety', 'bang': 'fear', 'paniek': 'panic', 'rouw': 'grief', 'depressie': 'depression', 'somber': 'depression',
    'zelfmoord': 'suicide', 'zelfdoding': 'suicide', 'suicide': 'suicide', 'slapeloos': 'insomnia', 'slaap': 'sleep',
    'dementie': 'dementia', 'mantelzorg': 'caregiver', 'beperking': 'disability', 'rolstoel': 'wheelchair',
    # power and heat
    'stroom': 'electricity power', 'stroomstoring': 'power outage', 'stroomuitval': 'power outage', 'elektriciteit': 'electricity',
    'aggregaat': 'generator', 'accu': 'battery', 'batterij': 'battery', 'batterijen': 'batteries', 'accu’s': 'batteries',
    'zonnepaneel': 'solar panel', 'zonnepanelen': 'solar panels', 'omvormer': 'inverter', 'laadregelaar': 'charge controller',
    'zekering': 'fuse', 'opladen': 'charging', 'oplader': 'charger', 'zaklamp': 'flashlight', 'kaars': 'candle',
    'kaarsen': 'candles', 'lamp': 'lamp', 'spanning': 'voltage', 'benzine': 'gasoline', 'brandstof': 'fuel',
    'propaan': 'propane', 'butaan': 'butane', 'gaslucht': 'gas leak', 'gaslek': 'gas leak', 'gasstoring': 'gas outage',
    'koolmonoxide': 'carbon monoxide', 'koolmonoxidevergiftiging': 'carbon monoxide poisoning', 'lift': 'elevator',
    'flat': 'apartment', 'hitte': 'heat', 'heet': 'hot', 'hittegolf': 'heat wave', 'warmte': 'heat', 'kou': 'cold',
    'koud': 'cold', 'vriest': 'freezing', 'vorst': 'freezing', 'verwarming': 'heating', 'kachel': 'heater',
    'houtkachel': 'wood stove', 'petroleumkachel': 'kerosene heater', 'isolatie': 'insulation', 'isoleren': 'insulation',
    'slaapzak': 'sleeping bag', 'deken': 'blanket', 'dekens': 'blankets', 'zeil': 'tarp', 'onderdak': 'shelter',
    'schuilplaats': 'shelter', 'schuilen': 'shelter', 'ventilator': 'fan', 'airco': 'air conditioning',
    # disasters
    'vuur': 'fire', 'brandblusser': 'fire extinguisher', 'rookmelder': 'smoke alarm', 'natuurbrand': 'wildfire',
    'bosbrand': 'wildfire', 'duinbrand': 'wildfire', 'heidebrand': 'wildfire', 'huisbrand': 'house fire', 'aardbeving': 'earthquake',
    'naschok': 'aftershock', 'overstroming': 'flood', 'overstromingen': 'floods', 'hoogwater': 'flood', 'wateroverlast': 'flooding',
    'dijkdoorbraak': 'flood', 'onweer': 'thunderstorm', 'bliksem': 'lightning', 'hagel': 'hail', 'windhoos': 'tornado',
    'orkaan': 'hurricane', 'lawine': 'avalanche', 'aardverschuiving': 'landslide', 'vulkaan': 'volcano', 'evacuatie': 'evacuation',
    'evacueren': 'evacuate', 'vluchten': 'evacuate', 'explosie': 'explosion', 'ontploffing': 'explosion', 'aanslag': 'attack',
    'bom': 'bomb', 'kernexplosie': 'nuclear explosion', 'kernwapen': 'nuclear weapon', 'atoombom': 'nuclear bomb',
    'kerncentrale': 'nuclear power plant', 'straling': 'radiation', 'radioactief': 'radioactive', 'radioactieve': 'radioactive',
    'neerslag': 'fallout', 'jodiumtabletten': 'potassium iodide', 'binnenblijven': 'shelter in place', 'noodpakket': 'emergency kit',
    'noodtas': 'go bag', 'vluchttas': 'go bag', 'noodkoffer': 'emergency kit', 'sirene': 'siren', 'ramp': 'disaster',
    'noodgeval': 'emergency', 'nood': 'emergency', 'gevaar': 'danger', 'gevaarlijk': 'dangerous', 'veilig': 'safe',
    # toilets and hygiene
    'wc': 'toilet', 'noodtoilet': 'emergency toilet', 'riool': 'sewer', 'rioolwater': 'sewage', 'poep': 'feces',
    'ontlasting': 'feces', 'plassen': 'urine', 'zeep': 'soap', 'handgel': 'hand sanitizer', 'afval': 'garbage',
    'vuilnis': 'garbage', 'ratten': 'rats', 'muizen': 'mice', 'muggen': 'mosquitoes', 'hygiene': 'hygiene', 'schimmel': 'mold',
    # repair, growing, finding the way
    'repareren': 'repair', 'reparatie': 'repair', 'gereedschap': 'tools', 'slijpen': 'sharpening', 'mes': 'knife',
    'messen': 'knives', 'bijl': 'axe', 'zaag': 'saw', 'hamer': 'hammer', 'lassen': 'welding', 'motor': 'engine',
    'lekkage': 'leak', 'lek': 'leak', 'kraan': 'faucet', 'leiding': 'pipe', 'leidingen': 'pipes', 'loodgieter': 'plumbing',
    'hout': 'wood', 'touw': 'rope', 'knopen': 'knots', 'spijker': 'nail', 'moestuin': 'vegetable garden', 'zaaien': 'sowing',
    'zaad': 'seed', 'zaden': 'seeds', 'aardappel': 'potato', 'aardappelen': 'potatoes', 'bonen': 'beans', 'groente': 'vegetables',
    'groenten': 'vegetables', 'mest': 'manure', 'grond': 'soil', 'kippen': 'chickens', 'geiten': 'goats', 'bijen': 'bees',
    'ongedierte': 'pests', 'paddenstoelen': 'mushrooms', 'bessen': 'berries', 'wilde': 'wild', 'kaart': 'map',
    'kompas': 'compass', 'verdwaald': 'lost', 'zendamateur': 'amateur radio', 'portofoon': 'two-way radio',
    'walkietalkie': 'two-way radio', 'noodradio': 'emergency radio', 'fluitje': 'whistle', 'telefoon': 'phone',
    'mobiel': 'cell phone', 'bereik': 'signal', 'hond': 'dog', 'kat': 'cat', 'huisdier': 'pet', 'huisdieren': 'pets',
    'fiets': 'bicycle', 'auto': 'car',
    # everyday verbs and adjectives
    'zuiver': 'purify', 'zuiveren': 'purify', 'drinkbaar': 'potable', 'drinken': 'drinking', 'onveilig': 'unsafe',
    'kapot': 'broken', 'lekt': 'leaking', 'bewaren': 'storage', 'opslaan': 'storage', 'schoonmaken': 'cleaning',
    'schoon': 'clean', 'verwarmen': 'heating', 'ruik': 'smell', 'stinkt': 'smell', 'bewegen': 'moving',
    'keuken': 'kitchen', 'huis': 'house', 'kelder': 'basement', 'zolder': 'attic', 'buiten': 'outdoors', 'binnen': 'indoors',
}
# Words that are Dutch here but also everyday English. They are read as Dutch only in a search that is Dutch already.
SHARED = {
    'brand': 'fire', 'been': 'leg', 'benen': 'legs', 'kind': 'child', 'rook': 'smoke', 'rug': 'back', 'enkel': 'ankle',
    'slang': 'snake', 'arm': 'arm', 'hand': 'hand', 'gas': 'gas', 'water': 'water', 'storm': 'storm', 'baby': 'baby',
    'radio': 'radio', 'tent': 'tent', 'filter': 'filter', 'compost': 'compost', 'stress': 'stress', 'toilet': 'toilet',
    'spin': 'spider', 'bij': 'bee', 'vliegen': 'flies', 'gif': 'poison', 'planten': 'planting', 'aarde': 'soil',
    'teken': 'ticks', 'aanval': 'seizure', 'maken': 'repair',
}
# Dutch function words: dropped from a Dutch search. Those marked as only Dutch also say that a search is Dutch.
STOP = set('ik je jij jou jouw u uw hij zij ze we wij mijn ons onze het de een en of in op aan bij van voor met naar om '
           'uit tot door over als dan dat die dit deze er wat wie waar hoe welke waarom wanneer is zijn was wordt worden '
           'heb hebt heeft hebben had kan kun kunt kunnen moet moeten mag mogen wil wilt ga gaat doe doet doen niet geen '
           'wel ook nog maar al zo nu heel erg veel weinig iets iemand mij me zich mezelf hoelang hoeveel snel nodig '
           'help helpen hulp'.split())
DUTCH_ONLY = set('ik jij jou jouw uw zij wij mijn onze het de een aan voor naar uit dat dit deze wat wie waar welke waarom '
                 'wanneer zijn wordt worden heb hebt heeft hebben kan kun kunt kunnen moet moeten mag mogen wil wilt ga '
                 'gaat doe doet doen niet geen wel ook nog maar heel erg veel weinig iets iemand mij mezelf hoelang '
                 'hoeveel nodig helpen hulp'.split())
# English-only words: a search that holds one is English, whatever else it holds.
ENGLISH_ONLY = set('the and how what my with to for from have has are can should does it this that when where which who '
                   'why your you i of after before without there their our'.split())

def fold(text):
    """Lower case, accent marks off (weeën -> weeen, hygiëne -> hygiene) and a curly apostrophe made straight, for
    both the lists below and the search, so "Weeën" and "weeen" are the same word."""
    text = unicodedata.normalize('NFKD', str(text).lower().replace('\u2019', "'"))
    return ''.join(c for c in text if not unicodedata.combining(c))


def _words(text):
    return re.findall(r"[\w']+", fold(text))


_PHRASES = sorted(((tuple(_words(k)), v) for k, v in PHRASES.items()), key=lambda kv: -len(kv[0]))
_WORDS = {fold(k): v for k, v in WORDS.items()}
_SHARED = {fold(k): v for k, v in SHARED.items()}
ENDINGS = ('tjes', 'jes', 'tje', 'je', 'en', 's')


def _lookup(word, shared_too):
    """The English for one Dutch word, also with a Dutch ending taken off (plural -en, -s; diminutive -je, -tje)."""
    for form in (word, *(word[:-len(e)] for e in ENDINGS if word.endswith(e) and len(word) - len(e) >= 4)):
        if form in _WORDS:
            return _WORDS[form]
        if shared_too and form in _SHARED:
            return _SHARED[form]
    return None


def _phrase_at(words, i):
    for key, english in _PHRASES:
        if tuple(words[i:i + len(key)]) == key:
            return key, english
    return None


def is_dutch(q, lang=None):
    """Is this search Dutch? Never when it holds an English-only word; yes when the person chose Dutch, or when it holds
    a phrase or word that is only Dutch."""
    words = _words(q)
    if any(w in ENGLISH_ONLY for w in words):
        return False
    if lang == 'nl':
        return True
    return any(w in DUTCH_ONLY or _lookup(w, False) or _phrase_at(words, i) for i, w in enumerate(words))


def to_english(q, lang=None):
    """(the search in English, [(Dutch, English), ...]) for a Dutch search; (q, []) for any other.

    Phrases are read first ("geen stroom" is a power outage, not "no" and "electricity"), then single words; Dutch
    function words go, and a word the lists do not know stays as it was."""
    if not q or not is_dutch(q, lang):
        return q, []
    words, out, found, i = _words(q), [], [], 0
    while i < len(words):
        hit = _phrase_at(words, i)
        if hit:
            out.append(hit[1])
            found.append((' '.join(hit[0]), hit[1]))
            i += len(hit[0])
            continue
        w = words[i]
        english = _lookup(w, True)
        if english:
            out.append(english)
            if english != w:
                found.append((w, english))
        elif w not in STOP:
            out.append(w)
        i += 1
    return (' '.join(out) or q), found
