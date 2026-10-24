"""Fill GitHub metadata using an explicit repository or the existing origin."""

import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit


def parse_repository(value):
    value = value.strip()
    if value.startswith('git@github.com:'):
        value = value[len('git@github.com:'):]
    elif '://' in value:
        url = urlsplit(value)
        if url.hostname != 'github.com':
            raise ValueError('Oczekiwany adres repozytorium GitHub.')
        value = url.path.strip('/')
    if value.endswith('.git'):
        value = value[:-4]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+', value):
        raise ValueError('Podaj repozytorium w formacie LOGIN/tech-controllers-defro.')
    return value


def configure(root, repository, maintainer=None):
    repository = parse_repository(repository)
    maintainer = (maintainer or repository.split('/')[0]).lstrip('@')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', maintainer):
        raise ValueError('Nieprawidłowy login opiekuna repozytorium.')
    manifest = Path(root) / 'custom_components/defro_emodul/manifest.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    base = 'https://github.com/' + repository
    data.update(documentation=base, issue_tracker=base + '/issues', codeowners=['@' + maintainer])
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return repository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', help='LOGIN/tech-controllers-defro albo adres repozytorium GitHub')
    parser.add_argument('--maintainer', help='Login opiekuna, jeśli właścicielem jest organizacja')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    value = args.repository
    if not value:
        try:
            result = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=root, capture_output=True, text=True, timeout=5)
            value = result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            value = None
    if not value:
        parser.error('Podaj --repository LOGIN/tech-controllers-defro.')
    try:
        configured = configure(root, value, args.maintainer)
    except ValueError as exc:
        parser.error(str(exc))
    print('Ustawiono metadane repozytorium: ' + configured)


if __name__ == '__main__':
    main()

