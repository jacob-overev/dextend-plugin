# Budowanie dodatku

Dodatek budujemy lokalnie, bez połączenia z adapterem. Wyniki zapisujemy w nowym
katalogu poza repozytorium.
Wymagane: Python 3.11+, OpenSSL, BusyBox, bwrap, GCC dla hosta, make, curl,
tar, QEMU user (qemu-arm), OpenSSH client, binutils ARM soft-float,
`arm-linux-gnueabi-gcc`, FFmpeg z libx264, fontconfig, Pillow i DejaVu Sans Mono Bold.
Moduł wymaga ARM GCC **4.9.4**.

## Budowa IMG wydania

W głównym katalogu repozytorium ustawiamy numer nowego wydania w `VERSION`.
Budowa korzysta z lokalnych źródeł `src/aoa/` i `src/diagnostics/build/`. Numer
kolejności aktualizatora odczytuje z poprzedniego IMG w `releases/`.

Pakowanie obu runtime wpisuje wartość `VERSION` do nagłówka panelu WWW
i informacji o urządzeniu. Numer pozostaje widoczny na każdej zakładce,
także bez karty debugowania lub odpowiedzi API. Numer zmieniamy w pliku źródłowym. Szablon i kontrola paczki pilnują zgodności z IMG.

```sh
export DEXTEND_UPDATE_SIGNING_KEY=/private/path/updater-ed25519.pem
export CROSS_COMPILE=/absolute/path/to/arm-linux-gnueabi-
export YAMAHA_MUSL_PREFIX=/absolute/path/to/musl-arm
./build-release.sh /absolute/path/to/new-output
```

Na pendrive kopiujemy `distribution/A15W_Update.img`. W tym samym katalogu leżą
`SHA256SUMS` i `VERSION`. Szczegóły produktu, użyty numer kolejności i wyniki
inspekcji obrazu są w `usb/install/MANIFEST.json`. Zawartość gotowego IMG
sprawdzamy poleceniem:

```sh
python3 tools/usb_image.py /absolute/path/to/new-output/distribution/A15W_Update.img
```

Każdy IMG zawiera własną procedurę wycofania, wykorzystywaną przez panel
i kolejne aktualizacje. Budowa sprawdza jej kompletność i zgodność wersji
z IMG i planszą. Ten sam obraz instaluje na OEM lub najpierw wycofuje
rozpoznane wydanie, sprawdza stan OEM i instaluje nową wersję. Zakres
usuwanych plików i zachowanie po przerwaniu opisuje
[procedura aktualizacji](installation.pl.md).

Jeśli potrzebujemy konkretnego numeru kolejności, podajemy go jako drugi
argument. Musi być wyższy od numeru w poprzednim IMG. Poszczególne części budujemy z głównego katalogu repozytorium.

## Rozmiar obrazu i miejsce na adapterze

Sprawdzamy pole `size_budget` w `usb/install/MANIFEST.json` po każdej budowie.
`image_bytes` dotyczy pliku na pendrivie, `runtime_compressed_bytes` pakietu
zapisywanego do flash, a `runtime_unpacked_bytes` archiwum rozpakowywanego do RAM.
Rozpakowane archiwum główne ma limit 1 MiB, a zestaw serwisowy 4 MiB.
Pierwsza instalacja wymaga wolnego miejsca równego sumie rozmiarów obu
skompresowanych archiwów zaokrąglonej w górę do KiB plus 320 KiB,
oraz co najmniej 16 MiB RAM według własnego odczytu. Test wydania sprawdza
odmowę 1 KiB poniżej progu flash oraz instalację dokładnie przy progu.

Programy ARM linkujemy z wyrównaniem segmentów do 4 KiB, zgodnym z rozmiarem
strony kernela adaptera. Zmiana zmniejsza archiwum po rozpakowaniu. Ilość
wolnego miejsca na konkretnym egzemplarzu pokazuje `flash_free_kib` w
`DEXTEND-RESULT.txt` z obrazu diagnostycznego `probe`, bez zapisu flash.

## Kontrola wycofania przed wydaniem

Każda zmiana, która zapisuje plik na stałe podczas instalacji, uruchomienia
lub pracy dodatku, wymaga sprawdzenia wycofania w tym samym wydaniu.
Aktualizujemy `src/usb/transaction.sh.in` tak, żeby usuwał nowe ścieżki
dodatku i przywracał zmienione pliki OEM. Dodajemy przypadek do testów, jeśli
dany zapis powstaje dopiero po uruchomieniu usługi albo wykonaniu akcji
w panelu.

Budowa uruchamia instalator i skrypt wycofania wyjęte z nowego IMG w
izolacji, osobno w trybie panelu i aktualizacji USB. Test porównuje ścieżki,
zawartość, typy, prawa i właścicieli z zapisanym stanem OEM. Sztuczny profil
i potwierdzenie startu zastępują fizyczny adapter. Rozbieżność albo
pominięcie testu zatrzymuje przygotowanie katalogu `distribution/`.
Wynik jest w `restore-validation.log`.

Aby sprawdzić gotowy obraz ponownie, korzystamy ze źródeł z jego tagu wydania
i uruchamiamy test w głównym katalogu repozytorium:

```sh
python3 tests/test_usb_packages.py --check-release-img /absolute/path/to/A15W_Update.img
```

## Testy na hoście

```sh
sh tools/test.sh
```

Testy instalatora używają `bwrap` i lokalnej kopii plików OEM.
Testowany jest także protokół na sztucznym CCU, odzyskiwanie strumienia/sesji,
prywatna zmiana konfiguracji audio i logika AOA/ABI. Nie jest to test Yamaha,
JFFS2, fizycznego USB, radia ani odtwarzania po utracie zasilania.

## Userspace ARM

Zaczynamy w nowym katalogu roboczym. W tym przykładzie tworzymy go poza repozytorium.

```sh
export DEXTEND_BUILD_ROOT="$PWD/../dextend-build"
mkdir -p "$DEXTEND_BUILD_ROOT"
export YAMAHA_MUSL_BUILD_DIR="$DEXTEND_BUILD_ROOT/toolchain"
sh tools/build-musl.sh
export YAMAHA_MUSL_PREFIX="$YAMAHA_MUSL_BUILD_DIR/musl-arm"
sh tools/build-userspace.sh "$DEXTEND_BUILD_ROOT/userspace"
```

Receptura pobiera musl 1.2.5 z przypiętą sumą SHA-256 i tworzy statyczny
ARM soft-float toolchain. Buduje most z tożsamością SDL zgodności Yamaha
(`Motorize`, `7a5f3f258b`, `7a5f3f25-8b82-4e0f-a173-80aefee79897`) oraz
`receiver-native`, `iphone-usb-role`, `bluetooth-autoconnect` i `phone-policy`.
Nie buduje preloadu ani historycznego modułu OEM.

## Moduł AOA

```sh
export CROSS_COMPILE=/absolute/path/to/arm-linux-gnueabi-
sh src/aoa/build-module.sh "$DEXTEND_BUILD_ROOT/module"
```

Prefiks wskazuje GCC 4.9.4. Stary toolchain wymaga zgodnych bibliotek hosta
(np. libmpfr.so.4); zapewniamy je w jego izolowanym środowisku, bez podmieniania
bibliotek systemowych. Receptura pobiera publiczny kernel NXP revision
`ad37eebd4b27a81080b655034e45521f064a7a09` i sprawdza SHA-256
`417a92355f11a0c225cd948daa7eb21f42adca8c00c549156a5365474870f7d6`.
Jeśli mamy już identyczne archiwum, wskazujemy je przez
`DEXTEND_KERNEL_ARCHIVE`; suma nadal jest sprawdzana.

`src/aoa/build-support/` zawiera dokładną odtworzoną konfigurację, listę
obserwowanych eksportów i nakładkę źródłową wcześniejszego sprawdzonego builda.
Nie są to oryginalne źródła prywatnego firmware producenta. Receptura sprawdza
wygenerowane definicje konfiguracji; nie patchuje CRC w skompilowanym ELF.
Wynik `yamaha_aoa.ko.EXPERIMENTAL` nie jest zgodny z dowolnym kernelem 3.14.
Nie ładujemy go na innym odbiorniku na podstawie samego numeru wersji.

## Plansza i paczka robocza

```sh
python3 tools/build-waiting.py "$DEXTEND_BUILD_ROOT/waiting"
python3 tools/package.py \
  --userspace "$DEXTEND_BUILD_ROOT/userspace" \
  --module "$DEXTEND_BUILD_ROOT/module/yamaha_aoa.ko.EXPERIMENTAL" \
  --waiting "$DEXTEND_BUILD_ROOT/waiting/waiting.h264" \
  --output "$DEXTEND_BUILD_ROOT/package"
```

Plansza korzysta z zaakceptowanego pliku `src/assets/waiting.png` i jest kodowana jako
jedna klatka H.264 640×360. Numer Dextend pochodzi z głównego `VERSION`, tak
samo jak numer IMG. Podczas startu dodatku firmware jest odczytywany z
`/etc/software_version`, a odczyt rewizji przez `riddleBoxCfg -g hardwareVer`
jest opcjonalny i wymaga sprawdzenia na fizycznym adapterze. Jeśli odczyt się
nie powiedzie albo wartość nie pasuje do pola, na planszy pojawi się kreska.
Plansza zapasowa w IMG zawiera numer Dextend także bez odczytów z urządzenia.

Paczka zawiera runtime LZMA, koordynator i hook startowy. Pakowanie nie
nadpisuje katalogu wynikowego i nie wykonuje zapisu flash ani instalacji.
Przebieg instalacji opisuje [instrukcja USB](../installation.pl.md).

Przy dystrybucji binarnej dostarczamy odpowiadające źródła GPL i
właściwe noty; samo lokalne zbudowanie paczki nie zamyka tego obowiązku ani
nie stanowi publikacji. Licencje składników są jawnie przypisane w
[mapie](licenses.pl.md).

Przebieg aktualizacji z panelu opisuje [aktualizacja przez przeglądarkę](network-updates.pl.md).
Testy API wymagają biblioteki Python `cryptography`.

Zestaw TP-Link/SSH buduje `src/diagnostics/build/build.sh`. Pełne źródła
i konfiguracje są dołączone do tego samego tagu. Testy serwisu uruchamiamy poleceniem:
`DEXTEND_SERVICE_BUILD=/absolute/output/service python3 tests/test_service.py`.
Test SSH uruchamia ARM Dropbear przez QEMU w izolacji na hoście; nie łączy
się z adapterem. `service_compressed_bytes` i `service_unpacked_bytes`
w manifeście określają koszt dodatkowego archiwum.

© 2026 Overev · [overev.com](https://overev.com/)
