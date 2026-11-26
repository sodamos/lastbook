"""The web/ and content/ an app build packages, written to a folder of their own. The builds package that folder, never the source folders.

  python -I -B ship_app_files.py OUT

web/ and content/ stay as this household's own library on 8890 reads them. The difference is in ship_edits.json, applied here to a copy:
general wording for the home area, no working names, guide items for things no pack holds taken out. Stops with an error if a listed word is left, or a web address in our own pages.
"""
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))  # also when the build invokes this script with -I
import i18n_catalogs  # noqa: E402

EDITS = json.loads((HERE / 'ship_edits.json').read_text(encoding='utf-8'))
LEFT = re.compile('|'.join(EDITS['forbidden']), re.I)
WEB_ADDRESS = re.compile(r'https?://(?!www\.w3\.org/)', re.I)    # our own pages link nowhere on the web (an SVG or XML name space is not a link)
PREFIXES = EDITS['id_prefixes']
TEXT, DROP_TEXTS = EDITS['text'], set(EDITS['drop_texts'])
used = set()


def new_id(doc):
    for old, new in PREFIXES.items():
        if doc.startswith(old):
            return new + doc[len(old):]
    return doc


def dropped(item):
    if not isinstance(item, dict):
        return item in DROP_TEXTS or item in EDITS['drop_keywords']
    drop = EDITS['drop_items']
    doc, zim = item.get('doc') or '', item.get('zim') or ''
    return doc.startswith(tuple(drop['doc_prefixes'])) or any(z in zim for z in drop['zim_contains'])


def clean(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[k] = new_id(v) if k == 'doc' else clean(v)
        if isinstance(value.get('read'), list) and value['read'] and not out['read']:
            return None    # a step or choice whose only cards were dropped
        return out
    if isinstance(value, list):
        kept = [clean(v) for v in value if not dropped(v)]
        return [v for v in kept if v is not None]
    if isinstance(value, str) and value in TEXT:
        used.add(value)
        return TEXT[value]
    return value


def main():
    out = Path(sys.argv[1])
    try:
        generated = i18n_catalogs.generate()
        i18n_catalogs.check_assets(ROOT / 'web', generated)
    except (OSError, ValueError) as error:
        sys.exit(f'Not shipping. Localization: {error}')
    (out / 'web').mkdir(parents=True, exist_ok=True)
    (out / 'content' / 'topics').mkdir(parents=True, exist_ok=True)
    written = []
    for p in sorted((ROOT / 'web').iterdir()):
        if p.is_file() and p.name not in EDITS['never_ship'] and p.name != '.DS_Store':
            shutil.copyfile(p, out / 'web' / p.name)
            written.append(out / 'web' / p.name)
    for rel in ['gaps.json'] + [f'topics/{p.name}' for p in sorted((ROOT / 'content' / 'topics').glob('*.json'))]:
        data = clean(json.loads((ROOT / 'content' / rel).read_text(encoding='utf-8')))
        if rel == 'gaps.json':
            data.pop('_about', None)
        (out / 'content' / rel).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        written.append(out / 'content' / rel)
    # Translated guide words (content/topics-i18n/<lang>/<id>.json): strings only, no readings, so nothing to clean.
    for src in sorted((ROOT / 'content' / 'topics-i18n').glob('*/*.json')):
        rel = src.relative_to(ROOT / 'content')
        (out / 'content' / rel).parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(src.read_text(encoding='utf-8'))
        (out / 'content' / rel).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        written.append(out / 'content' / rel)
    bad = [str(EDITS['text'].keys() - used)] if EDITS['text'].keys() - used else []    # an edit that matched nothing: the guide changed, so look again
    for p in written:
        m = LEFT.search(p.read_text(encoding='utf-8', errors='replace'))
        if not m and p.parent.name == 'web' and p.suffix in ('.js', '.html', '.css'):
            m = WEB_ADDRESS.search(p.read_text(encoding='utf-8', errors='replace'))
        if m:
            bad.append(f'{p.relative_to(out)}: {p.read_text(encoding="utf-8", errors="replace")[max(0, m.start() - 40):m.end() + 40]!r}')
    if bad:
        sys.exit('Not shipping. Left in place:\n' + '\n'.join(bad))
    try:
        i18n_catalogs.check_assets(out / 'web', generated)
    except (OSError, ValueError) as error:
        sys.exit(f'Not shipping. Localization: {error}')
    print(f'{len(written)} files in {out}')


if __name__ == '__main__':
    main()
