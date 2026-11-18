# Jak sprawdzić zmianę

W głównym katalogu repozytorium uruchamiamy `sh tools/test.sh`. Zestaw sprawdza most protokołu, wybór telefonu, odzyskiwanie połączenia, transakcje instalatora i ABI sterownika. Część testów instalatora wymaga zewnętrznych plików OEM (`DEXTEND_OEM_TEST_ROOT`). W wynikach uwzględniamy pominięte testy. Po zmianach pakowania lub wycofania [sprawdzamy też gotowy IMG](build.pl.md).

Na motocyklu osobno sprawdzamy obraz, sterowanie i dźwięk. Przy próbie restartu porównujemy identyfikator rozruchu przed i po. Po zmianie geometrii Android Auto sprawdzamy krawędzie mapy, pasek nawigacji i joystick na docelowym liczniku. W [dokumencie zgodności](compatibility.pl.md) zapisujemy sprzęt i wersję dodatku razem z wynikiem.

© 2026 Overev · [overev.com](https://overev.com/)
