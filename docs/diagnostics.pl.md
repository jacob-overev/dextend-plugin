# Zbierz logi z adaptera

Po wystąpieniu problemu otwórz zakładkę Diagnostyka w panelu. Przed restartem adaptera skopiuj lub pobierz raport. Jeśli potrzebujesz dłuższego zapisu, przygotuj pendrive.

## Przygotuj pendrive

1. Użyj pendrive’a FAT32 z co najmniej 8 MiB wolnego miejsca. Jeśli musisz go sformatować, najpierw skopiuj z niego pliki.
2. Utwórz pusty folder dongle-logs bezpośrednio na pendrivie. Plik aktualizacji A15W_Update.img przechowuj na osobnym nośniku.
3. Wysuń pendrive z komputera.

## Odtwórz problem

1. Włóż pendrive do pośrednika. Jeśli problem pojawia się podczas uruchamiania, włóż go przed włączeniem zasilania.
2. Powtórz czynności, po których pojawia się problem. Jeśli możesz, zapisz godzinę i opisz, co stało się na ekranie motocykla lub telefonu.
3. Odczekaj kilka sekund i wyjmij pendrive. Ponowne włożenie rozpocznie osobną sesję.

## Prześlij sesję

1. Podłącz pendrive do komputera i otwórz dongle-logs. Wybierz folder session-… z danej próby. Zegar pośrednika może pokazywać inną godzinę, więc w razie wątpliwości porównaj kolejność utworzenia folderów.
2. Spakuj cały folder sesji do ZIP i prześlij go autorowi prywatnie wraz z opisem kroków i godziną wystąpienia problemu.

## Opcjonalna sesja SSH

Podłącz obsługiwaną kartę Wi-Fi USB, połącz telefon z siecią Wi-Fi dongla i otwórz zakładkę **Debug**. W sekcji **Dostęp serwisowy SSH** pozostaw klucz publiczny autora lub wpisz własny klucz publiczny Ed25519. Włącz przełącznik, gdy chcesz pozwolić posiadaczowi tego klucza na logowanie jako root. Serwer SSH nasłuchuje na porcie 2223 na interfejsie diagnostycznym. Po zakończeniu sesji wyłącz dostęp. Restart dongla również go wyłącza.

© 2026 Overev · [overev.com](https://overev.com/)
