# Translated guides (`content/topics-i18n/<lang>/<topic id>.json`)

The guides in `content/topics/` are written in English. A translation for one interface language sits beside them,
one file per guide, named after the guide's `id`. The app asks for the guides in the language the person chose in
Settings (`/api/topics?lang=nl`) and `server.py` (`translate_topic`) puts the translated words in place. A language
without a folder here, and English, get the guides as they are.

```json
{
  "id": "water",
  "tile": "Drinkwater",
  "keywords": ["drinkwater", "kraanwater"],
  "text": {
    "Get safe drinking water": "Veilig drinkwater",
    "Boiling or chlorination kills most germs but does not remove heavy metals, salts, or most other chemicals.": "Koken of chloor doodt de meeste ziektekiemen, maar haalt zware metalen, zouten en de meeste andere chemicaliën er niet uit."
  }
}
```

| Field | Meaning |
| --- | --- |
| `id` | The guide's `id`; must match the file name. |
| `tile` | The guide's short name on tiles and in breadcrumbs (English has these in `SHORT` in `web/app.js`). |
| `keywords` | Words people type in this language. They are added to the guide's English keywords, so search finds the guide in both. Lower case. |
| `text` | English string → translated string, for the guide's own words: `title`, `short`, `intro`, each choice's `label` and `hint`, each limit's `text`, and each route step's `title` and `goal`. |

Rules

- A translation is keyed by the exact English text. When the English changes, the old key no longer matches and that
  string shows in English until someone translates the new text. `app/tests/test_topic_translations.py` fails on a key
  that matches nothing, so a stale translation is noticed, and on a guide string that has no translation.
- Translate; do not add. A limit is a faithful paraphrase of its cited page, so its translation says the same and no
  more. Where the English names a US number, unit or agency, the translation may give the local equivalent beside it
  ("bel het alarmnummer (911 in de VS, 112 in Nederland)", "4 °C (40 °F)"), never instead of the source's own meaning.
- Readings (`read`, `prepare`, `learn`) are not translated: their labels and notes describe English pages.
- Keep the words of the interface catalogue (`translations/desktop/<lang>.json`, `docs/i18n.md`) so the guides and the
  app say the same thing the same way. Dutch uses "je", never "u".
