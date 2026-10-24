"""Check archive layout and all local runtime resources without contacting HA."""

import argparse
import ast
import json
from pathlib import Path


def check(root, require_hacs=False):
    root = Path(root)
    component = root / 'custom_components/defro_emodul'
    for name in ('README.md', 'LICENSE', 'hacs.json', 'requirements-test.txt', 'tests/fixtures/snapshot.json'):
        if not (root / name).is_file():
            raise ValueError('Brak pliku: ' + name)
    domains = [p.name for p in (root / 'custom_components').iterdir() if p.is_dir() and not p.name.startswith(('.', '__'))]
    if domains != ['defro_emodul']:
        raise ValueError('Repozytorium powinno zawierać jedną integrację: defro_emodul.')
    for p in component.rglob('*.py'):
        ast.parse(p.read_text(encoding='utf-8'))
    for p in component.rglob('*.json'):
        json.loads(p.read_text(encoding='utf-8'))
    manifest = json.loads((component / 'manifest.json').read_text(encoding='utf-8'))
    catalogue = json.loads((component / 'catalogue.json').read_text(encoding='utf-8'))
    specs = catalogue['entities']
    if manifest['domain'] != 'defro_emodul' or len(specs) != 317 or len({s['key'] for s in specs}) != 317:
        raise ValueError('Nieprawidłowa domena lub katalog encji.')
    if not (component / 'brand/icon.png').is_file():
        raise ValueError('Brak ikony integracji.')
    for name in ('number.py','select.py','switch.py','services.yaml','www/defro-emodul-card.js','THIRD_PARTY_NOTICES.md'):
        if not (component / name).is_file():
            raise ValueError('Brak zasobu sterowania: ' + name)
    ready = bool(manifest.get('issue_tracker') and manifest.get('codeowners') and manifest.get('documentation', '').startswith('https://github.com/'))
    if require_hacs and not ready:
        raise ValueError('Uzupełnij metadane poleceniem scripts/configure_repository.py --repository LOGIN/tech-controllers-defro.')
    return {'domain': manifest['domain'], 'entities': len(specs), 'hacs_metadata_ready': ready}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-hacs-metadata', action='store_true')
    args = parser.parse_args()
    try:
        result = check(Path(__file__).resolve().parents[1], args.require_hacs_metadata)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

