# Dlaczego aktualizacja zaczyna się od stanu fabrycznego

Instalacja może zacząć się na fabrycznym firmware albo na adapterze ze starszym wydaniem Dextend. Przy nadpisywaniu starych plików wynik zależałby od tego, co zostawiła poprzednia wersja. Dlatego obie ścieżki instalacji mają wspólny punkt wyjścia.

Po sprawdzeniu profilu urządzenia i wolnego miejsca instalator tworzy kopię plików, które zmieni. Jeśli rozpoznaje wcześniejszą instalację, przywraca pliki OEM i usuwa stare ustawienia dodatku. Sprawdza stan fabryczny, instaluje nowe oprogramowanie i na końcu zapisuje skrypt startowy. Parowania OEM zostają zachowane. Z tej samej procedury usuwania korzysta opcja przywracania w panelu.

Gdy dodajemy plik zapisywany na stałe, uwzględniamy go w procedurze usuwania i sprawdzamy przywracanie stanu początkowego dla obu ścieżek instalacji. Te próby opisujemy w [dokumencie o budowie i testach wycofania](build.pl.md). Kroki na adapterze opisuje [instrukcja instalacji z USB](../installation.pl.md).

© 2026 Overev · [overev.com](https://overev.com/)
