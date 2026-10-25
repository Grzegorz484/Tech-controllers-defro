# tech-controllers-defro

Integracja **DEFRO APC Slim / ST-9730** z Home Assistant przez eModuł.
Wersja **1.1.1** otwiera z kafelków standardowe okno Home Assistant z historią encji.
Integracja zawiera sterowanie i panel menu z ikonami funkcji kotła.
Zachowuje identyfikatory **317 encji odczytu**: 261 `sensor` i 56 `binary_sensor`.

## Sterowanie

- Encje `number`: temperatury, moce, czasy, opóźnienia i punkty krzywych.
- Encje `select`: tryby pracy i pozostałe pojedyncze wybory z menu.
- Encje `switch`: ustawienia włącz/wyłącz i poszczególne opcje wielokrotnego wyboru.
- Panel **DEFRO eModuł**: menu użytkownika MU, instalatora MI, serwisu MS
  oraz producenta MP, o ile API je udostępnia; wyszukiwanie i widoczność pozycji niedostępnych.
- Harmonogramy korekt temperatury: 24 wartości godzinowe w rzeczywistych °C korekty.
- Harmonogramy włącz/wyłącz: 24 lub 48 przedziałów, zgodnie z danymi sterownika.
- Krzywe grzewcze: wszystkie punkty dla temperatur zewnętrznych podanych przez API.
- Wielokrotne zaznaczenia, czynności z osobnym potwierdzeniem i znane kody podmenu.
- Ikony funkcji kotła: płomień, pompy, wentylator, podajnik, zawory, CO, CWU,
  termometry i harmonogramy. Są to odpowiedniki MDI z Home Assistant.

Obsługiwane są wszystkie edytowalne typy obecne w dostarczonym menu ST-9730:
1, 2, 3, 4, 10, 11, 12, 13, 15, 20 i 30; typ 35 służy do odblokowania podmenu.
Grupy są prezentowane jako ścieżki ustawień. Nieznany typ pozostaje widoczny
jako niedostępny. Typ 4 jest edytowany w minutach, również dla czasów dłuższych niż doba.
Liczba encji sterowania zależy od menu zwróconego przez konkretny sterownik.

Przed zapisem integracja pobiera świeże menu i sprawdza dostęp, stan sterownika,
zakres, krok oraz dozwolone opcje. Wysyła jedno polecenie, bez automatycznego
powtarzania zapisu. Przyjęcie polecenia przez API nie zastępuje potwierdzenia
odczytem: ustawienie oczekuje na aktualizację; brak potwierdzenia powoduje ostrzeżenie.
Czynności takie jak rozpalanie, wygaszanie lub przywrócenie ustawień są dostępne
w panelu, jeśli udostępnia je sterownik, i wymagają dodatkowego potwierdzenia.

## Aktualizacja z 1.0.0 lub 1.1.0

1. W HACS otwórz **Tech-controllers-defro → menu ⋮ → Pobierz ponownie**
   (lub Aktualizuj, jeśli HACS wyświetla aktualizację).
2. Uruchom ponownie Home Assistant. Zachowaj dotychczasowy wpis integracji.
3. Odśwież stronę HA. Encje sterowania znajdziesz przy urządzeniu DEFRO
   w części konfiguracji; mogą mieć osobne nazwy obok sensorów odczytu.
4. Dodaj kartę menu do pulpitu zgodnie z następną sekcją.
   Jeżeli karta jest już dodana, kliknij kafelek temperatury, aby otworzyć historię HA.

## Panel menu z ikonami

W standardowym trybie pulpitu integracja automatycznie rejestruje zasób karty.
Otwórz **Edytuj pulpit → Dodaj kartę → Ręcznie** i wklej:

```yaml
type: custom:defro-emodul-card
title: DEFRO eModuł
```

Panel wymaga konta administratora Home Assistant. Obsługuje także wybór
sterownika, jeżeli skonfigurowano kilka wpisów integracji. Formularze zapisują
ustawienia dopiero po użyciu przycisku **Zapisz**. Wartości niezapisane pozostają
w formularzu podczas odświeżania odczytów.

Jeżeli HA pokazuje „Custom element doesn't exist”, odśwież stronę i sprawdź
**Ustawienia → Pulpity → menu ⋮ → Zasoby**. Dodaj zasób typu **Moduł JavaScript**:

```text
/defro_emodul_static/defro-emodul-card.js?v=1.1.1
```

W trybie zasobów YAML wpisz go ręcznie w konfiguracji Lovelace:

```yaml
lovelace:
  resources:
    - url: /defro_emodul_static/defro-emodul-card.js?v=1.1.1
      type: module
```

### Historia po kliknięciu kafelka

Kliknięcie kafelka w zakładce **Podgląd** otwiera standardowe okno szczegółów
tej samej encji Home Assistant, które jest dostępne na stronie urządzenia.
Temperatury pokazują wykres, a stany pomp i pozostałe encje swoją historię
zgodnie z danymi zapisanymi przez HA. Kafelki obsługują również klawisze Enter i spację.

Powiązanie korzysta z rejestru encji, więc uwzględnia zmienione przez użytkownika
identyfikatory i właściwy sterownik. Historia pochodzi z `recorder` Home Assistant;
integracja zachowuje istniejące encje i ich wcześniejsze dane. Nawet gdy bieżący
odczyt jest niedostępny, kafelek nadal otwiera szczegóły zarejestrowanej encji.

## Pierwsza instalacja

W HACS dodaj repozytorium niestandardowe
`https://github.com/Grzegorz484/Tech-controllers-defro` jako **Integration**,
pobierz pliki i uruchom ponownie HA. Następnie otwórz
**Ustawienia → Urządzenia i usługi → Dodaj integrację → DEFRO eModuł**.
Zaloguj się do swojej domeny `emodul.pl` lub `emodul.eu`, wybierz sterownik
oraz podaj znane kody menu, jeżeli są wymagane.

Przy instalacji ręcznej skopiuj `custom_components/defro_emodul` do
`/config/custom_components/`. W Docker użyj folderu hosta zamontowanego
jako `/config`. Opcjonalny `install.py` i `ZAINSTALUJ_WINDOWS.cmd` kopiują
integrację do wskazanego folderu HA z `configuration.yaml` i zachowują kopię
poprzedniej wersji. Szczegóły: [INSTALACJA.txt](INSTALACJA.txt).

## Dostęp i kody

Integracja respektuje uprawnienia konta eModuł i flagi dostępu API. Nieaktywne
gałęzie, brak uprawnień, menu zablokowane kodem i sterownik offline oznaczają
niedostępność. Samo dodanie panelu nie nadaje uprawnień serwisowych.
Kody głównych menu można zmieniać przez **menu integracji → Zmień konfigurację**.
Znany kod podmenu można podać przy chronionej pozycji w karcie. Kod jest sprawdzany
raz i zapisywany lokalnie po przyjęciu; integracja nie zgaduje kodów.
Aby usunąć zapamiętane kody podmenu, zaznacz **Usuń zapisane kody podmenu**
w formularzu **Zmień konfigurację**. Przydaje się to także po zmianie kodu w eModuł.

Kafelki są odświeżane co 60 sekund, menu co 300 sekund. Po zapisie integracja
sprawdza menu wcześniej. Odświeżanie samej karty korzysta z danych już pobranych
przez integrację. Bieżącej temperatury CWU nie było w dostarczonym katalogu:
nastawa CWU pozostaje osobnym parametrem. Niepotwierdzone jednostki pozostają surowe.

Hasło konta jest używane tylko do utworzenia sesji. Token sesji i podane kody
menu są przechowywane lokalnie w konfiguracji HA. Panel nie otrzymuje tokenu,
hasła, kodów ani identyfikatora modułu. Diagnostyka pomija te dane.
Ponowne logowanie po wygaśnięciu sesji zachowuje encje i historię.

Administratorzy mogą też użyć akcji `defro_emodul.get_controls`,
`defro_emodul.set_parameter` i `defro_emodul.unlock_menu`.
`get_controls` zwraca klucze, typy i dostępne zakresy. Dla `set_parameter`
wartość wyboru jest etykietą opcji, harmonogramy i krzywe są listami,
a czynności wymagają `value: true` oraz `confirm: true`.

## Rozwój i weryfikacja

Testy używają syntetycznych danych i rzeczywistego frameworka Home Assistant
Core 2026.10.3 na Pythonie 3.14. Testy nie wysyłają poleceń do fizycznego kotła.
Działanie zapisu na Twoim urządzeniu wymaga sprawdzenia po aktualizacji HA.

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q --tb=short
python -m ruff check --select E9,F custom_components install.py scripts
python scripts/check_repository.py --require-hacs-metadata
node --check custom_components/defro_emodul/www/defro-emodul-card.js
node --test tests/frontend.test.cjs
```

Własną kopię repozytorium skonfiguruj poleceniem
`python scripts/configure_repository.py --repository LOGIN/tech-controllers-defro`.
Repozytorium zawiera syntetyczne fixture i katalog definicji, bez danych logowania
oraz bez prywatnego eksportu użytkownika.

## Źródła

- [Oficjalna dokumentacja API eModułu](https://api-documentation.emodul.eu/)
- [Schemat zapisu ustawień menu](https://api-documentation.emodul.eu/tags/menu/users_user_id_modules_module_udid_menu_menu_type_ido.yaml)
- [Schemat odczytu i kodów podmenu](https://api-documentation.emodul.eu/tags/menu/users_user_id_modules_module_udid_menu_menu_type_pin.yaml)
- [TECH Controllers dla Home Assistant](https://github.com/mariusz-ostoja-swierczynski/tech-controllers)

Integracja społecznościowa na licencji [MIT](LICENSE).
Informacje o projekcie referencyjnym i jego licencji:
[THIRD_PARTY_NOTICES.md](custom_components/defro_emodul/THIRD_PARTY_NOTICES.md).
