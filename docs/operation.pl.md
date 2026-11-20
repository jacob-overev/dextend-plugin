# Połącz telefon i motocykl

Pierwszą konfigurację wykonaj na postoju.

## Podłącz pośrednik

1. Wyjmij pendrive. Podłącz pośrednik do portu USB systemu multimedialnego motocykla i włącz jego ekran.
2. Poczekaj, aż pośrednik się uruchomi. W telefonie włącz Bluetooth i Wi-Fi.

## Sparuj przez Bluetooth

1. Na iPhonie otwórz Ustawienia → Bluetooth. Na Androidzie otwórz Ustawienia → Połączone urządzenia → Sparuj nowe urządzenie. Nazwy opcji mogą się różnić zależnie od telefonu.
2. Wybierz nazwę Bluetooth swojego pośrednika. Potwierdź parowanie. Jeśli pojawi się prośba o zgodę na CarPlay lub Android Auto, zaakceptuj ją. Zostaw włączone Wi-Fi.
3. Na ekranie motocykla otwórz funkcję projekcji, jeśli jest dostępna. Sprawdź, czy pojawia się obraz, czy działa sterowanie i czy słychać dźwięk.

## Otwórz panel Dextend

1. Na telefonie lub komputerze wejdź w Ustawienia → Wi-Fi i wybierz sieć pośrednika, jeśli ją udostępnia. W razie pytania użyj hasła tej sieci. Jeśli telefon lub komputer wyświetli komunikat o braku internetu, zostań w tej sieci.
2. Wpisz w pasku adresu przeglądarki http://192.168.43.1/dextend/. To adres dla fabrycznej sieci tego pośrednika. Jeśli używasz skonfigurowanej sieci serwisowej, zastąp adres IP adresem pośrednika w tej sieci i zostaw ścieżkę /dextend/.
3. Jeżeli panel się nie otwiera, sprawdź, czy urządzenie wciąż jest w sieci pośrednika i czy adres rozpoczyna się od http://. Panel otworzy się po udanym starcie dodatku, gdy sieć pośrednika jest dostępna.

## Ustaw priorytet i sieć

### Parowanie → Sparowane telefony i priorytety

1. Po sparowaniu telefonu w jego ustawieniach Bluetooth otwórz zakładkę Parowanie i wybierz Odśwież listę.
2. W polu Preferowana platforma wybierz Według listy, CarPlay albo Android Auto. Pośrednik najpierw spróbuje połączyć się z telefonami z wybranej grupy.
3. Użyj ↑ Wyżej i ↓ Niżej, żeby zmienić kolejność w grupie. Wybierz Zapisz na donglu. Zmiana zacznie działać przy następnym łączeniu bez przerywania bieżącej sesji.

Po włączeniu zasilania i uruchomieniu Bluetooth dongiel sam próbuje połączyć się z pierwszym telefonem z listy. Przy pustej liście czeka na połączenie rozpoczęte z telefonu. Gdy telefon jest poza zasięgiem lub nie ukończy negocjacji, kolej przechodzi na następny. Po ostatnim dongiel wraca do pierwszego. Po zakończeniu działającej sesji zaczyna od początku listy.

Po kolejnych niepowodzeniach dongiel czeka co najmniej 5, 10, 15, 20, 20, a następnie 30 sekund przed ponowną próbą z tym samym telefonem. W tym czasie może próbować połączyć się z innymi telefonami z listy. Udane połączenie zeruje licznik danego telefonu. W trakcie przerwy możesz rozpocząć połączenie ze smartfona. Dongiel może je przyjąć, gdy telefon otworzy kanał Bluetooth i odbiornik będzie wolny.

### Debug → Debug / Wi-Fi USB

Zakładka pojawia się, gdy działa usługa sieci serwisowej i jest podłączona osobna karta Wi-Fi USB. Do zwykłego parowania i projekcji wystarczy wbudowane Wi-Fi pośrednika.

1. Otwórz Debug i wybierz Skanuj ponownie. Przy swojej sieci naciśnij Wybierz albo wpisz jej nazwę w polu SSID.
2. Wpisz hasło sieci WPA2 Personal i wybierz Zapamiętaj i połącz. Sprawdź stan w sekcji Połączenie.
3. W Zapamiętane sieci użyj Połącz, aby wybrać sieć, lub Zapomnij, aby ją usunąć. Ponów połączenie uruchomi kolejną próbę.

W zakładce Parowanie przycisk Zapisz na donglu zmienia priorytety pośrednika. Przycisk Zapisz lokalnie w pozostałej konfiguracji zapisuje ustawienia w przeglądarce.

## Aktualizacja lub usunięcie Dextend

Otwórz updater w panelu Dextend. Pozostań w sieci Wi-Fi adaptera. Telefon potrzebuje też dostępu do internetu, żeby pobrać wydanie. Wybierz wersję, potwierdź instalację i pozostaw adapter podłączony do zasilania.

Aby usunąć Dextend, otwórz sekcję przywracania ustawień fabrycznych i wykonaj kroki potwierdzenia. Jeśli chcesz też wyczyścić ustawienia i parowania, po ponownym uruchomieniu adaptera otwórz panel producenta.

© 2026 Overev · [overev.com](https://overev.com/)
