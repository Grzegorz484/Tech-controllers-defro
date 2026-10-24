#!/usr/bin/env python3
"""Copy only this component into a user-selected HA configuration folder."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import shutil
import sys
import uuid


def install(config_folder, source_folder=None):
    config = Path(config_folder).expanduser().resolve()
    source = Path(source_folder) if source_folder else Path(__file__).resolve().parent / 'custom_components' / 'defro_emodul'
    if not config.is_dir() or not (config / 'configuration.yaml').is_file():
        raise ValueError('Wybierz folder konfiguracji Home Assistant zawierający plik configuration.yaml.')
    if not (source / 'manifest.json').is_file() or not (source / 'catalogue.json').is_file():
        raise ValueError('Brak kompletu plików integracji. Najpierw rozpakuj cały pobrany ZIP.')
    components = config / 'custom_components'
    destination = components / 'defro_emodul'
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError('Ścieżka docelowa nie jest zwykłym folderem. Użyj instalacji ręcznej.')
    components.mkdir(exist_ok=True)
    staging = config / ('.defro_install_' + uuid.uuid4().hex)
    backup = None
    try:
        shutil.copytree(source, staging, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        if destination.exists():
            stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            backup = config / 'defro_emodul_backups' / stamp
            backup.parent.mkdir(exist_ok=True)
            destination.rename(backup)
        staging.rename(destination)
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            backup.rename(destination)
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return destination, backup


def main():
    parser = argparse.ArgumentParser(description='Instalacja DEFRO eModuł w folderze konfiguracji HA.')
    parser.add_argument('--config', help='Folder HA z configuration.yaml; bez argumentu otwiera wybór folderu.')
    args = parser.parse_args()
    selected = args.config
    root = None
    if not selected:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            selected = filedialog.askdirectory(title='Wybierz folder konfiguracji Home Assistant z configuration.yaml')
            root.destroy()
        except Exception:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass
            selected = input('Folder konfiguracji Home Assistant: ').strip().strip('"')
    if not selected:
        print('Nie wybrano folderu. Instalacja nie została rozpoczęta.')
        return 0
    try:
        target, backup = install(selected)
    except (ValueError, OSError, shutil.Error) as exc:
        print('BŁĄD: ' + str(exc), file=sys.stderr)
        return 1
    print('Wgrano integrację: ' + str(target))
    if backup:
        print('Kopia poprzedniej wersji: ' + str(backup))
    print('\nTeraz w Home Assistant:')
    print('1. Uruchom ponownie Home Assistant.')
    print('2. Ustawienia > Urządzenia i usługi > Dodaj integrację > DEFRO eModuł — odczyt.')
    print('3. Zaloguj się do eModułu i wybierz swój sterownik. Encje powstaną automatycznie.')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())

