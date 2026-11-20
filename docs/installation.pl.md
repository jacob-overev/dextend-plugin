# Instalacja Dextend z pendrive’a

## Sprawdź adapter

Znajdź model i rocznik motocykla w tabeli zgodności w README. Na adapterze Carlinkit CPC200-CCPA / A15W otwórz **Box Info**. Przetestowaliśmy rewizję sprzętową (**Hardware Version**) `YMA0-WN16-0003` z dwiema wersjami firmware (**Version**): `2025.10.15.1127` i `2026.07.31.1733`. Do obu służy ten sam obraz instalacyjny. Na A15W instalator zapisuje numer firmware w raporcie. Obsługa innych wersji wymaga sprawdzenia po uruchomieniu. Skrypt startowy właściciela w `/etc/init.d/rcS` i ustawienia SSH oraz Telnet pozostają na miejscu.

Utrata zasilania podczas instalacji może unieruchomić adapter. Jeśli zależy Ci na odzyskaniu fabrycznego oprogramowania, zachowaj sprawdzoną kopię zapasową. Przywrócenie urządzenia nie zawsze jest możliwe.

## Przygotuj pendrive

1. Pobierz [obraz instalacyjny A15W_Update.img](https://github.com/jacob-overev/dextend-plugin/releases/latest/download/A15W_Update.img). Do opcjonalnej weryfikacji na komputerze pobierz [plik kontrolny SHA256SUMS](https://github.com/jacob-overev/dextend-plugin/releases/latest/download/SHA256SUMS).
2. Opcjonalnie sprawdź sumę obrazu przed skopiowaniem. W katalogu z pobranymi plikami oblicz sumę obrazu. W PowerShellu na Windowsie wpisz `Get-FileHash .\A15W_Update.img -Algorithm SHA256`, na macOS `shasum -a 256 A15W_Update.img`, a na Linuksie `sha256sum A15W_Update.img`. Porównaj wynik z wpisem w `SHA256SUMS`. Jeśli się różnią, przerwij instalację.
3. Skopiuj potrzebne dane z pendrive’a, a następnie sformatuj go jako FAT32. Umieść sam obraz w katalogu głównym, zachowaj nazwę pliku i wysuń pendrive z komputera.

## Zainstaluj dodatek i sprawdź wynik

1. Poza motocyklem podłącz adapter do stabilnej ładowarki USB. Gdy się uruchomi, włóż pendrive do portu USB-A adaptera.
2. Przez cały czas aktualizacji zostaw podłączone zasilanie i pendrive. Gdy skończy się sygnalizacja aktualizacji producenta, odczekaj jeszcze cztery minuty. Odłącz zasilanie, wyjmij pendrive i otwórz na komputerze plik `DEXTEND-RESULT.txt`. Zachowaj raport i katalog `dextend-backup.*`.
3. Sprawdź, czy raport zawiera `operation=install` i wybraną przez Ciebie wersję. Wynik `result=PREPARED_FOR_BOOT` oznacza, że instalator sprawdził zapisane pliki. Uruchom adapter bez pendrive’a. Zgodnie z instrukcją połączenia sprawdź obraz, sterowanie i dźwięk. Wynik `ALREADY_INSTALLED` oznacza, że ta wersja była już zainstalowana.
4. Przy wyniku `REJECTED` powód odmowy znajdziesz w polu `detail`. Jeśli raportu brakuje, zawiera błąd lub kończy się na `FILES_COMMITTED`, zachowaj kopię zapasową i sprawdź stan adaptera przed następną próbą. Sam kolor diody nie potwierdza instalacji.

© 2026 Overev · [overev.com](https://overev.com/)
