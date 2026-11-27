# Lastbook voor Nederland

Deze versie van Lastbook voegt Nederland toe aan de bestaande app, volgens de structuur die het project zelf gebruikt
voor andere landen (zoals Duitsland/Berlijn). De rest van Lastbook werkt zoals altijd; zie [README.md](README.md).

## Wat er nieuw is

| Onderdeel | Wat | Waar |
|---|---|---|
| Nederlandse interface | Kies **Nederlands** bij Inrichten of in Instellingen. Navigatie, zoekvelden, de gidsen-pagina’s en delen van Inrichten/Instellingen zijn Nederlands. Aanspreekvorm: "je". | `translations/desktop/nl.json`, `docs/i18n.md` |
| Nederlandse gidsen | Alle 14 gidsen (titels, situaties, waarschuwingen, leerroutes) vertaald. De bronpagina’s zelf blijven Engels. Amerikaanse nummers en eenheden staan erbij met de Nederlandse tegenhanger (112, °C, meters). | `content/topics-i18n/nl/` |
| Nederlands zoeken | Zoeken in het Nederlands vindt de juiste gids ("brandwond", "geen stroom", "dijkdoorbraak", "wc werkt niet"). In de (Engelse) handleidingen wordt een Nederlandse zoekvraag vertaald naar de Engelse woorden die erin staan ("brandwond op mijn hand" → "burn hand"). Dat geldt ook voor de chat en de encyclopedieën. | `engine/dutch_query.py`, `web/app.js` |
| Noodnummers | 112, politie geen spoed (0900 8844), 113 Zelfmoordpreventie en het Nationaal Storingsnummer Gas en Stroom (0800 9009), elk met de officiële bron en de datum van controle. | `content/emergency/NL.json` |
| Kaart per provincie | Offline kaart voor elk van de twaalf provincies (of alle in één keer): straten, water, gebouwen en hulppunten uit OpenStreetMap, alle adressen uit de BAG (Kadaster). De Waddeneilanden zitten in hun provincie (Texel in Noord-Holland, de andere vier in Fryslân), met veerhavens als hulppunt en een eigen controle per eiland. | `tools/build_region_nl.py`, `docs/MAP-NL.md` |
| Adres zoeken | Het zoekveld van de kaart vindt Nederlandse adressen zoals je ze schrijft: "Dorpsstraat 12a Leeuwarden", "8911 HG 12", met de plaats of de gemeente erbij of niet, ook "Burg." voor "Burgemeester" en andersom. Alleen huizen die in de BAG staan, nooit een gok; bestaat het huis niet, dan zoekt de plaatszoeker verder (straat, plaats, postcode). | `engine/address_nl.py` |

## Starten zonder installatie

```sh
python3 server.py --data /pad/naar/je/lastbook-data
```

In een gewone browser start de app in het Engels; de taalkeuze zit in de desktop-app (Instellingen → Bibliotheek en
lokale AI → Taal van de app).

## Een provinciekaart bouwen

```sh
python3 tools/build_region_nl.py fetch --province ZH   # downloadt OSM (een paar honderd MB) en de BAG-adressen; hervat waar hij stopte
python3 tools/build_region_nl.py build --province ZH   # bouwt en controleert; de vorige bouw blijft staan tot de nieuwe klopt
python3 tools/build_region_nl.py demo  --province ZH
python3 server.py --data derived/regions/NL-ZH/demo --no-index
```

Een provinciekaart naast je eigen bibliotheek, zonder iets in die bibliotheek te veranderen: geef met `--map` (of
`LASTBOOK_MAP`) de map `derived/geo` van de provincie mee. Voor de desktop-app:

```sh
LASTBOOK_MAP="$PWD/derived/regions/NL-ZH/data/derived/geo" .venv/bin/python app/main.py
python3 server.py --data /pad/naar/LastbookData --map derived/regions/NL-ZH/data/derived/geo   # of de serverversie
```

Provincies: GR, FR, DR, OV, FL, GE, UT, NH, ZH, ZE, NB, LI, of `--province all` voor alle twaalf. Adressen worden één
keer per gebied opgehaald en gedeeld tussen buurprovincies (`derived/regions/NL-shared/`); voor heel Nederland zijn dat
miljoenen adressen, dus reken op een flinke downloadtijd en een paar GB. Een provincie die faalt houdt de rest niet tegen.

Heel Nederland in één kaart, uit de provincies die al gebouwd zijn (niets wordt opnieuw gedownload; een paar minuten,
ongeveer 3,5 GB extra voor de kaart, de adressen worden gelinkt en niet gekopieerd):

```sh
python3 tools/build_region_nl.py merge --province all        # of een paar: --province FR,GR,DR
LASTBOOK_MAP="$PWD/derived/regions/NL/data/derived/geo" .venv/bin/python app/main.py
```

Bouw je een provincie opnieuw, draai `merge` daarna ook opnieuw.

Waddeneilanden: Texel zit in `NL-NH`; Vlieland, Terschelling, Ameland en Schiermonnikoog in `NL-FR`. De controle eist
per eiland straten, adressen, de gemeente in de plaatszoeker en een voorbeeldadres; anders faalt de bouw.

De eerste volledige bouw (26 november 2026): alle twaalf provincies geslaagd, samen 10.798.639 adressen en ongeveer
4,5 GB; per provincie de cijfers in [docs/MAP-NL.md](docs/MAP-NL.md). Ophalen duurde het grootste deel van een
dag (PDOK geeft in drukke gebieden HTTP 500, de bouwer deelt die blokken dan op); bouwen ongeveer acht minuten.

## Tests

```sh
python3 -B -m unittest app.tests.test_i18n_catalogs app.tests.test_bridge app.tests.test_topic_translations \
  app.tests.test_dutch_query app.tests.test_emergency_numbers app.tests.test_build_region_nl app.tests.test_address_nl \
  app.tests.test_topic_search
```

## Nog niet gedaan

- De app laat nog geen provinciekaart kiezen bij Inrichten; dat is hetzelfde open punt als bij Berlijn (de
  "runtime"-kant). Tot dan: `--map` of `LASTBOOK_MAP` (zie hierboven).
- Officiële hulppunten (ziekenhuizen, huisartsenposten, AED’s) komen nu alleen uit OpenStreetMap.
- Nederlandstalige bronnen in de bibliotheek zelf (bijvoorbeeld Denk Vooruit, Rode Kruis) vragen eerst toestemming of
  een licentiecheck per bron, en een nieuw bibliotheekpakket.
- De noodnummers staan als data klaar, maar de app toont ze nog niet (ook upstream nog niet).
