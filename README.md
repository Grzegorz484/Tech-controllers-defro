# tech-controllers-defro

Integracja odczytu danych DEFRO APC Slim / ST-9730 z eModułu do Home Assistant.
Tworzy **317 encji**: **261 sensor** i **56 binary_sensor**.

## Funkcje

- Odczyt temperatur CO, spalin, zewnętrznej, pokoju, zaworu i powrotu.
- Stany pomp, podajnika, grzałki, wentylatora i zaworu.
- Odczyt nastaw z menu użytkownika, instalatora i serwisowego.
- Punkty krzywych grzewczych oraz surowe dane harmonogramów.
- Formularz logowania, znane kody menu i ponowne logowanie po wygaśnięciu sesji.
- Diagnostyka pomijająca tokeny, hasła, kody i identyfikator modułu.

Kafelki są odświeżane co 60 sekund, a menu co 300 sekund. Wskazania pochodzą
z API eModułu. Katalog zawiera definicje pól i etykiety, a wartości pobierane są
na bieżąco. Nieaktywne lub niedostępne pozycje mają stan `unavailable`.
Komunikacja obejmuje logowanie i odczyt danych.

## Instalacja ręczna

1. Skopiuj `custom_components/defro_emodul` do `/config/custom_components/` w HA.
2. Uruchom ponownie Home Assistant.
3. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację**.
4. Wybierz **DEFRO eModuł — odczyt**.
5. Zaloguj się do `emodul.pl` albo `emodul.eu`, wybierz sterownik i podaj znane
   kody menu, jeśli są wymagane.

W instalacji Docker folder konfiguracji jest katalogiem hosta zamontowanym
jako `/config`. Opcjonalny `install.py` kopiuje pliki do wskazanego folderu HA
z `configuration.yaml` i zachowuje poprzednią wersję. W Windows można użyć
`ZAINSTALUJ_WINDOWS.cmd`. Szczegóły: [INSTALACJA.txt](INSTALACJA.txt).

## Repozytorium GitHub i HACS

Repozytorium: **Grzegorz484/Tech-controllers-defro**. W katalogu głównym
znajdują się `README.md`, `hacs.json` i `custom_components/`.

Aby zainstalować przez HACS, repozytorium musi być publiczne. W HACS otwórz
menu **Repozytoria niestandardowe**, dodaj
`https://github.com/Grzegorz484/Tech-controllers-defro` jako typ **Integration**,
pobierz integrację, zrestartuj HA i przejdź przez formularz logowania.

W przypadku własnej kopii repozytorium uzupełnij jej właściciela i linki:

```bash
python scripts/configure_repository.py --repository TWOJ_LOGIN/tech-controllers-defro
```

`TWOJ_LOGIN` zastąp loginem właściciela repozytorium. W repozytorium Git z
ustawionym zdalnym adresem GitHub wystarczy uruchomić skrypt bez argumentów.
Skrypt ustawia `documentation`, `issue_tracker` i `codeowners` w manifeście.
Dla organizacji można dodatkowo podać `--maintainer LOGIN_OPIEKUNA`.

Metadane do publikacji można sprawdzić poleceniem:

```bash
python scripts/check_repository.py --require-hacs-metadata
```

## Układ plików

| Ścieżka | Zawartość |
|---|---|
| `custom_components/defro_emodul/` | Integracja instalowana w HA |
| `custom_components/defro_emodul/catalogue.json` | 317 definicji encji |
| `custom_components/defro_emodul/translations/` | Polski i angielski formularz |
| `custom_components/defro_emodul/brand/` | Ikona integracji |
| `tests/` | Samodzielne testy i syntetyczne dane testowe |
| `scripts/` | Konfiguracja metadanych GitHub i kontrola paczki |
| `.github/workflows/` | Testy GitHub Actions |

## Rozwój i testy

Środowisko testowe: Python 3.14 oraz Home Assistant Core 2026.10.3.

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q --tb=short
python -m ruff check --select E9,F custom_components install.py scripts
python scripts/check_repository.py
```

Testy używają danych syntetycznych zapisanych w `tests/fixtures/snapshot.json`.
Nie wymagają konta eModułu ani prywatnego eksportu użytkownika.

## Dostępność danych

317 oznacza liczbę zarejestrowanych encji, a nie aktywnych urządzeń fizycznych.
Brak uprawnień, odłączony sterownik, nieaktywna gałąź albo brak pola w API
powoduje stan `unavailable`. Po wygaśnięciu sesji HA uruchamia ponowne logowanie,
zachowując istniejące identyfikatory encji.

Katalog jest przeznaczony dla DEFRO ST-9730. Nie obejmuje bieżącej temperatury
CWU, której nie było w odczytanym zestawie pól; nastawa CWU jest osobnym odczytem.
Niepotwierdzone jednostki pozostają surowe. Kolejność bitów harmonogramów oraz
wielokrotnych wyborów nie jest interpretowana. Przy harmonogramach korekt
stanem jest liczba punktów, a lista znajduje się w atrybucie `values`.

Hasło konta służy do logowania i nie jest zapisywane przez integrację.
Token sesji i podane kody menu są przechowywane lokalnie w konfiguracji HA.

## Źródła protokołu

- [Dokumentacja API eModułu](https://api-documentation.emodul.eu/)
- [TECH Controllers dla Home Assistant](https://github.com/mariusz-ostoja-swierczynski/tech-controllers)
- [Dokumentacja integracji Home Assistant](https://contributors.home-assistant.io/core/integrations/)

Integracja społecznościowa. Licencja [MIT](LICENSE).

