// Dextend | Developed by Overev
// Copyright (c) 2026 Overev | https://overev.com/

'use strict';

const i18n = (() => {
  const english = {
    'Połącz się z Wi-Fi adaptera, aby włączyć SSH.': 'Connect to the adapter’s Wi-Fi to enable SSH.',
    'Dostęp serwisowy SSH': 'SSH service access',
    'Włączenie pozwala właścicielowi wybranego klucza zalogować się jako root. Dostęp wygasa po restarcie adaptera.': 'Enabling SSH lets the holder of the selected key sign in as root. Access ends when the adapter restarts.',
    'Klucz publiczny Ed25519 (domyślnie klucz autora)': 'Ed25519 public key (developer key by default)',
    'Zapisano ustawienie SSH.': 'SSH setting saved.',
    'Wyłącz SSH przed zmianą klucza.': 'Turn off SSH before changing the key.',
    'Wprowadź klucz publiczny Ed25519.': 'Enter an Ed25519 public key.',
    'SSH: zapis nie powiódł się.': 'Could not save the SSH setting.',
    'Zapisz i zastosuj': 'Save and apply',
    'Zapisano profil. Uruchom ponownie dongiel, aby go zastosować.':
      'Profile saved. Restart the adapter to apply it.',
    'Dolny margines (px)': 'Bottom margin (px)',
    'Górny margines (px)': 'Top margin (px)',
    'Prawy margines (px)': 'Right margin (px)',
    'Lewy margines (px)': 'Left margin (px)',
    'Wysokość AA (px)': 'AA height (px)',
    'Szerokość AA (px)': 'AA width (px)',
    'Wczytano profil z dongla.': 'Display profile loaded from the adapter.',
    'Zapisano profil na donglu.': 'Display profile saved on the adapter.',
    'Niezapisane zmiany profilu.': 'Unsaved profile changes.',
    'Podaj wartości parzyste. Marginesy muszą pozostawić widoczny kadr.':
      'Enter even values within the field limits. The margins must leave a visible frame.',
    'Widoczny kadr: {w} × {h} px': 'Visible frame: {w} × {h} px',
    'Ustawienia lokalne odbiornika': 'Local receiver settings',
    'Wczytaj z dongla': 'Load from adapter',
    'Każdy ruch przesuwa obraz o 2 px. Zapis ponownie uruchomi aktywne połączenie Android Auto.':
      'Each move shifts the picture by 2 px. Saving restarts an active Android Auto connection.',
    '↓ W dół': '↓ Down',
    '↑ W górę': '↑ Up',
    'W prawo →': 'Right →',
    '← W lewo': '← Left',
    'Przesuń obraz o 2 px': 'Move picture by 2 px',
    'Rozdzielczość określa obszar rysowany przez telefon. Marginesy wycinają krawędzie klatki 800 × 480 px.':
      'Resolution sets the area drawn by the phone. The margins crop the edges of the 800 × 480 px frame.',
    Własny: 'Custom',
    'Centralny 640 × 360': 'Centered 640 × 360',
    'Profil obrazu': 'Display profile',
    'Android Auto · ustawienia obrazu na donglu.': 'Android Auto display settings on the adapter.',
    Usuń: 'Remove',
    'Usuń sparowanie': 'Forget pairing',
    'Usuń sparowanie: {name}': 'Forget pairing: {name}',
    'Usunąć sparowanie z {name}? Może to zakończyć aktywne połączenie z tym telefonem.':
      'Forget pairing with {name}? This may end the active connection to this phone.',
    'Usunięto sparowanie. Usuń adapter także w ustawieniach Bluetooth telefonu przed ponownym parowaniem.':
      'Pairing removed. Also forget the adapter in your phone’s Bluetooth settings before pairing again.',
    'Bluetooth jest zajęty. Spróbuj ponownie.': 'Bluetooth is busy. Please try again.',
    'Nie udało się potwierdzić usunięcia telefonu. Odśwież listę.':
      'Could not confirm that the phone was removed. Refresh the list.',
    Aktualizacja: 'Update',
    'Aktualizacja Dextend': 'Update Dextend',
    'Sprawdź najnowszą wersję i zainstaluj ją przez Wi-Fi.':
      'Check the latest version and install it over Wi-Fi.',
    'Pozostań w sieci Wi-Fi adaptera. Telefon potrzebuje też dostępu do Internetu, aby pobrać wydanie.':
      'Stay on the adapter’s Wi-Fi. Your phone also needs Internet access to download the release.',
    'Na stronie aktualizacji wybierzesz wersję i potwierdzisz instalację. Podczas aktualizacji pozostaw adapter podłączony do zasilania.':
      'On the update page, select the version and confirm installation. Keep the adapter powered throughout the update.',
    'Otwórz updater': 'Open updater',
    Diagnostyka: 'Diagnostics',
    'Skopiuj raport po wystąpieniu problemu i dołącz go do zgłoszenia.':
      'Copy the report after the problem occurs and include it in your issue report.',
    'Raport obejmuje bieżący stan instalacji, start dodatku oraz połączenie serwisowe. Logi są przechowywane wyłącznie w ograniczonym buforze RAM i znikają po restarcie. Hasła i klucze nie są zbierane.':
      'The report covers the current installation state, plugin startup and the service connection. Logs are kept only in a bounded RAM buffer and are cleared on restart. Passwords and keys are not collected.',
    'Odśwież raport': 'Refresh report',
    'Kopiuj wszystko': 'Copy all',
    'Pobierz raport': 'Download report',
    'Raport diagnostyczny': 'Diagnostic report',
    'Pobieranie raportu…': 'Loading report\u2026',
    'Raport odświeżony.': 'Report refreshed.',
    'Skopiowano raport.': 'Report copied.',
    'Nie udało się skopiować. Zaznaczony tekst możesz skopiować ręcznie.':
      'Could not copy. You can copy the selected text manually.',
    'Nie udało się pobrać raportu. Sprawdź połączenie z panelem i spróbuj ponownie.':
      'Could not load the report. Check your connection to the panel and try again.',
    'Brak odpowiedzi usługi Wi-Fi': 'Wi-Fi service not responding',

    'Język panelu': 'Panel language',
    'Kategorie konfiguracji': 'Configuration categories',
    '↓ Eksport JSON': '↓ Export JSON',
    'Brak niezapisanych zmian': 'No unsaved changes',
    'Niezapisane zmiany: {count}': 'Unsaved changes: {count}',
    'Urządzenie i utrzymanie': 'Device and maintenance',
    'Informacje, urządzenia sparowane i operacje serwisowe.':
      'Device details, paired phones and maintenance tools.',
    'Informacje o donglu': 'Adapter information',
    'Wersja Dextend': 'Dextend version',
    'Wersja dodatku': 'Plugin version',
    'Numer seryjny': 'Serial number',
    'Adres IP / czas pracy': 'IP address / uptime',
    'Sparowane telefony': 'Paired phones',
    'CarPlay i Android Auto: wybierz preferowaną platformę i kolejność łączenia telefonów.':
      'Choose a preferred platform and connection order for CarPlay and Android Auto.',
    'Lista i priorytety są dostępne w zakładce Parowanie.':
      'Open the Pairing tab to view the list and set priorities.',
    'Firmware i diagnostyka': 'Firmware and diagnostics',
    'Sprawdź aktualizację': 'Check for updates',
    'Wgraj firmware': 'Install firmware',
    'Przywróć poprzednią wersję': 'Restore previous version',
    'Pobierz logi': 'Download logs',
    'Zgłoś problem / załącz plik': 'Report an issue / attach a file',
    'Restart dongla': 'Restart adapter',
    'Reset ustawień aplikacji': 'Reset app settings',
    'Sparowane telefony i priorytety': 'Paired phones and priorities',
    'Automatyczne połączenie z CarPlay i Android Auto.':
      'Automatic connection to CarPlay and Android Auto.',
    'Priorytet połączenia': 'Connection priority',
    'Preferowana platforma': 'Preferred platform',
    'Najpierw telefony wybranej platformy, następnie pozostałe.':
      'Try phones on the preferred platform first.',
    'Według listy': 'List order',
    'W obrębie platformy decyduje kolejność na liście. Jeśli telefon jest niedostępny, dongiel próbuje połączyć kolejny.':
      'Within each platform, the adapter tries phones in list order. If a phone is unavailable, it tries the next one.',
    'Zmiana nie przerywa działającego połączenia. Obowiązuje przy następnym łączeniu i pozostaje zapisana po restarcie dongla.':
      'Changes take effect the next time the adapter connects and are kept after a restart. The current connection stays active.',
    'Odśwież listę': 'Refresh list',
    'Kolejność łączenia telefonów': 'Phone connection order',
    'Pobieranie telefonów…': 'Loading phones…',
    'Pierwszy na liście ma najwyższy priorytet. Nowy telefon sparuj przez Bluetooth z donglem, a następnie odśwież listę.':
      'The first phone in the list has the highest priority. To add a phone, pair it with the adapter over Bluetooth and refresh the list.',
    'Łączenie z donglem…': 'Connecting to the adapter…',
    'Zapisz na donglu': 'Save to adapter',
    'Debug / Wi-Fi USB': 'Debug / USB Wi-Fi',
    'Oddzielna sieć serwisowa. Wbudowane Wi-Fi CarPlay pracuje niezależnie.':
      'A separate service network. Built-in CarPlay Wi-Fi works independently.',
    POŁĄCZENIE: 'CONNECTION',
    'Oczekiwanie na kartę': 'Waiting for USB Wi-Fi',
    'Dongiel automatycznie szuka dowolnej zapamiętanej sieci i ponawia połączenie po utracie zasięgu. Obsługa działa wyłącznie z podłączoną kartą USB.':
      'With a USB Wi-Fi adapter connected, Dextend looks for saved networks and retries when the connection drops.',
    'Dostępne sieci': 'Available networks',
    'Skanuj ponownie': 'Scan again',
    'Brak wyników skanowania.': 'No scan results.',
    'Dodaj sieć WPA2 Personal': 'Add a WPA2 Personal network',
    Hasło: 'Password',
    'Wybierz sieć lub wpisz nazwę': 'Select a network or enter its name',
    'Hasło trafia wyłącznie do dongla. Nie jest częścią eksportu ani zapisu przeglądarki.':
      'The password is sent only to the adapter. The browser and the JSON export do not store it.',
    'Zapamiętaj i połącz': 'Save and connect',
    'Zapamiętane sieci': 'Saved networks',
    'Ponów połączenie': 'Retry connection',
    'Zdarzenia połączenia': 'Connection events',
    'Zmiany stanu obserwowane od otwarcia panelu.':
      'Connection changes since you opened the panel.',
    'Przywracanie ustawień fabrycznych': 'Factory reset',
    'Usuń Dextend, a po ponownym uruchomieniu zresetuj ustawienia i parowania w panelu producenta.':
      "Remove Dextend, then restart the adapter and reset its settings and pairings in the manufacturer's panel.",
    'Zostaw adapter podłączony do zasilania podczas każdej operacji. W trakcie resetu połączenie Wi-Fi może się rozłączyć.':
      'Keep the adapter powered throughout. Wi-Fi may disconnect during the reset.',
    'Rozpocznij przywracanie': 'Start restore',
    'Otwórz panel producenta': "Open the manufacturer's panel",
    'Potwierdź przywracanie': 'Confirm restore',
    'Usunięcie Dextend przygotuje adapter do resetu fabrycznego. Zostaw go podłączony do zasilania, aż panel pozwoli uruchomić go ponownie.':
      'Removing Dextend prepares the adapter for a factory reset. Keep it powered until the panel says you can restart it.',
    'Wpisz PRZYWRÓĆ, aby kontynuować.': 'Enter RESTORE to continue.',
    Anuluj: 'Cancel',
    'Usuń Dextend': 'Remove Dextend',
    'Dextend · Auto · zmodyfikowany dongiel CPC200-CCPA':
      'Dextend · Auto · modified CPC200-CCPA adapter',
    'sprawdzanie Wi-Fi USB…': 'checking USB Wi-Fi…',
    'Konfiguracja lokalna': 'Local configuration',
    'Zapis nie zmienia ustawień dongla.': 'These settings are saved in this browser only.',
    'Cofnij zmiany': 'Discard changes',
    'Zapisz lokalnie': 'Save locally',
    'Profil mostu do CCU. Wartości referencyjne recovery32-rc1; edycja jest lokalna.':
      'CCU bridge profile. The reference values come from recovery32-rc1. Edits are saved in this browser.',
    'FPS bezprzewodowego CarPlay': 'Wireless CarPlay frame rate',
    'Profil bezprzewodowy: 20 FPS. Liczba określa cel, nie bieżący pomiar.':
      'The wireless profile targets 20 FPS. This setting shows the target frame rate.',
    'Połączenie telefonu': 'Phone connection',
    'USB + wireless': 'USB and wireless',
    'USB ma pierwszeństwo. Wireless potwierdzono na motocyklu.':
      'USB takes priority. Wireless was verified on a motorcycle.',
    'Dźwięk i mikrofon': 'Audio and microphone',
    'Telefon — potwierdzony profil': 'Phone (verified profile)',
    'Dźwięk i mikrofon obsługuje telefon. Zmiana wymaga innego pakietu firmware.':
      'The phone handles audio and the microphone. Changing this requires a different firmware package.',
    'Opóźnienie startu mostu': 'Bridge startup delay',
    'Czas na inicjalizację fabrycznych usług.': 'Time for the original firmware services to start.',
    'Autostart mostu': 'Start bridge automatically',
    'Start dodatku po włączeniu dongla.': 'Start Dextend when the adapter powers on.',
    'Odzyskiwanie połączeń': 'Connection recovery',
    'Niezależny nadzór CCU i telefonu. Obecnie wbudowany.':
      'Built-in monitoring for the CCU and phone connections.',
    'Plansza oczekiwania': 'Waiting screen',
    'Dextend — motocykl + QR': 'Dextend with motorcycle and QR code',
    Statyczna: 'Static',
    'Animowana (test)': 'Animated (test)',
    'Projekt pakietu 2026-10-24; nie jest odczytem aktywnej planszy.':
      'Reference from the 2026-10-24 package. The active waiting screen may differ.',
    'AutoConnect Bluetooth': 'Bluetooth auto-connect',
    'Automatycznie próbuje połączyć wcześniej sparowany telefon.':
      'Automatically tries to connect a previously paired phone.',
    'Ponowienie Bluetooth': 'Bluetooth retry interval',
    'Odstęp prób w sekundach. Oczekiwanie po błędach narasta do 32 s.':
      'Time between attempts, in seconds. After failures, the delay increases up to 32 seconds.',
    'Ograniczanie zaległych ACK': 'Limit pending ACKs',
    'Ogranicza zaległe klatki i narastanie opóźnienia obrazu.':
      'Limits queued frames and keeps video delay from building up.',
    'Nadzór obrazu wireless': 'Wireless video monitoring',
    'Po 2 s ciszy sprawdza źródło; po kolejnych 2 s próbuje odzyskać obraz.':
      'Checks the source after 2 seconds without video and tries to recover it after another 2 seconds.',
    'Płynne przejścia obrazu': 'Smooth video transitions',
    'Przygotowuje obraz telefonu przed przejściem z planszy oczekiwania.':
      'Prepares the phone video before switching away from the waiting screen.',
    'Szybkie odświeżenie IDR': 'Early IDR refresh',
    'Odświeża klatkę kluczową po 500 ms od startu obrazu.':
      'Refreshes the keyframe 500 ms after video starts.',
    'Diagnostyka IPC': 'IPC diagnostics',
    'Zapisuje ograniczone metadane komunikacji, bez treści pakietów.':
      'Records a limited set of communication metadata. Packet contents are excluded.',
    'Android Auto i CarPlay': 'Android Auto and CarPlay',
    'Automatyczny wybór': 'Automatic selection',
    'Rzeczywiste priorytety połączeń ustawisz w zakładce Parowanie.':
      'Use the Pairing tab to change the active connection priorities.',
    'Logi na pamięci USB': 'USB diagnostic logs',
    'Katalog dongle-logs na pendrivie': 'dongle-logs folder on USB drive',
    'Podłączenie nośnika z tym katalogiem włącza diagnostykę; minimum 8 MiB wolnego.':
      'Plug in a USB drive with this folder and at least 8 MiB free to start recording.',
    'Poziom logów': 'Log level',
    Zdarzenia: 'Events',
    Diagnostyczny: 'Diagnostic',
    'Szczegółowe logi są aktywne podczas sesji USB.':
      'Detailed logs are recorded during a USB logging session.',
    'Profil joysticka': 'Joystick profile',
    'Yamaha — potwierdzone mapowanie': 'Yamaha (verified mapping)',
    'Lewo/prawo: pokrętło; długi powrót obsługuje CCU.':
      'Left and right inputs use the rotary control. The CCU handles a long press of Back.',
    Obraz: 'Video',
    'Ustawienia fabrycznego odbiornika. Profil CCU ma stałe 640 × 360.':
      'Settings for the original receiver. The CCU profile uses a fixed resolution of 640 × 360.',
    'FPS odbiornika': 'Receiver frame rate',
    'W profilu Yamaha docelowe FPS określa sekcja SDL.':
      'For the Yamaha profile, the SDL settings specify the target frame rate.',
    Rozdzielczość: 'Resolution',
    Automatyczna: 'Automatic',
    Automatyczny: 'Automatic',
    Automatyczne: 'Automatic',
    Własna: 'Custom',
    Własne: 'Custom',
    'Szerokość własna': 'Custom width',
    'Wysokość własna': 'Custom height',
    'Wartości fabryczne trzeba odczytać z API; 0 = auto.':
      'The API supplies the factory values. Set to 0 for automatic selection.',
    '0 = automatycznie.': 'Set to 0 for automatic selection.',
    'Rozmiar interfejsu': 'Interface size',
    Mały: 'Small',
    Duży: 'Large',
    'Tryb obrazu': 'Video mode',
    Domyślny: 'Default',
    Domyślna: 'Default',
    Domyślne: 'Default',
    Płynność: 'Smooth playback',
    'Oryginalna rozdzielczość': 'Native resolution',
    'Automatyczne odświeżanie': 'Automatic refresh',
    'Praca w tle': 'Run in background',
    'Wysyłanie pustej klatki': 'Send a blank frame',
    'Opcje fabryczne. W profilu Yamaha audio pozostaje po stronie telefonu.':
      'Settings for the original firmware. In the Yamaha profile, the phone handles audio.',
    'Opóźnienie mediów': 'Media delay',
    'Opóźnienie echa': 'Echo delay',
    'Wzmocnienie mikrofonu': 'Microphone gain',
    'Źródło mikrofonu': 'Microphone source',
    Telefon: 'Phone',
    Dongiel: 'Adapter',
    Pojazd: 'Vehicle',
    'Tryb mikrofonu': 'Microphone mode',
    'Tryb 1': 'Mode 1',
    'Tryb 2': 'Mode 2',
    'Tryb 3': 'Mode 3',
    'Tryb 4': 'Mode 4',
    'Kategoria mediów': 'Media category',
    'Jakość rozmów': 'Call quality',
    'Kanał nawigacji': 'Navigation channel',
    Nawigacja: 'Navigation',
    Głos: 'Voice',
    'Rozmowy przez Bluetooth': 'Bluetooth calls',
    'Audio Bluetooth': 'Bluetooth audio',
    'Automatyczne odtwarzanie': 'Autoplay',
    'Nagrywanie w tle': 'Background recording',
    'Bufor mediów': 'Media buffer',
    'Bufor nawigacji': 'Navigation buffer',
    'Bufor rozmów': 'Call buffer',
    'Wzmocnienie nawigacji': 'Navigation gain',
    'Wzmocnienie rozmów': 'Call gain',
    'Nawigacja podczas rozmowy': 'Navigation volume during calls',
    Połączenia: 'Connections',
    'Wi-Fi, Bluetooth i zachowanie po uruchomieniu.': 'Wi-Fi, Bluetooth and startup behaviour.',
    'Nazwa Wi-Fi': 'Wi-Fi name',
    'Odczyt z dongla po podłączeniu API.': 'Read from the adapter once the API is connected.',
    'Nazwa Bluetooth': 'Bluetooth name',
    'Pasmo Wi-Fi': 'Wi-Fi band',
    'Automatyczne połączenie': 'Connect automatically',
    'Szybkie połączenie': 'Quick connect',
    'Fabryczne opóźnienie startu': 'Factory startup delay',
    'Tryb połączenia': 'Connection mode',
    'Tryb transmisji': 'Transfer mode',
    Zgodność: 'Compatibility',
    'Sterowanie i zachowanie': 'Controls and behaviour',
    'Opcje fabrycznego interfejsu i zgodności z pojazdem.':
      'Original receiver controls and vehicle compatibility settings.',
    'Tryb pokrętła': 'Rotary control mode',
    'Tryb kursora': 'Cursor mode',
    'Automatyczne wyświetlanie': 'Show automatically',
    Wymuszone: 'Forced',
    'Powrót do interfejsu': 'Return to interface',
    'Synchronizacja licznika': 'Instrument cluster sync',
    'Synchronizacja GPS': 'GPS sync',
    'Typ HULink': 'HULink type',
    Personalizacja: 'Personalisation',
    'Dane pojazdu, język i ekran połączenia.': 'Vehicle details, language and connection screen.',
    Marka: 'Make',
    Rok: 'Year',
    'Język ekranu dongla': 'Adapter display language',
    'Logo startowe': 'Startup logo',
    'Plik logo': 'Logo file',
    'Propozycja lokalna: PNG/JPEG do 100 kB. Plik nie jest zapisywany na donglu.':
      'Local preview. Use a PNG or JPEG up to 100 kB. The adapter does not store the file.',
    'Automatyczne sprawdzanie aktualizacji': 'Check for updates automatically',
    Parowanie: 'Pairing',
    Przywracanie: 'Restore',
    Urządzenie: 'Device',
    'Pamięć lokalna niedostępna lub uszkodzona.':
      'Local storage is unavailable or could not be read.',
    'Logo przekracza limit 100 kB.': 'The logo exceeds the 100 kB limit.',
    'Zapisano ustawienia lokalnie. Przesyłanie logo wymaga API.':
      'Settings saved locally. Uploading the logo requires the adapter API.',
    'Zapisano w przeglądarce. Dongiel pozostaje bez zmian.': 'Settings saved in this browser only.',
    'Nie udało się zapisać. Możesz wyeksportować konfigurację.':
      'Could not save. You can still export the configuration.',
    'Wyeksportowano projekt konfiguracji.': 'Configuration draft exported.',
    'Platforma jeszcze nierozpoznana': 'Platform not detected yet',
    'Nie ma jeszcze sparowanych telefonów.': 'No paired phones yet.',
    '↑ Wyżej': '↑ Move up',
    '↓ Niżej': '↓ Move down',
    'Wyżej: {name}': 'Move {name} up',
    'Niżej: {name}': 'Move {name} down',
    'Kolejność zmieniona. Zapisz ją na donglu.': 'Order changed. Save it to the adapter.',
    'Dongiel nie przyjął żądania.': 'The adapter rejected the request.',
    'Pobieranie telefonów z dongla…': 'Loading phones from the adapter…',
    'Nieprawidłowa odpowiedź dongla.': 'The adapter returned an unexpected response.',
    'Ustawienia odczytane z dongla.': 'Settings loaded from the adapter.',
    'Nie udało się odczytać ustawień. {detail}': 'Could not load settings. {detail}',
    'Lista telefonów jest niedostępna. Spróbuj odświeżyć.':
      'The phone list is unavailable. Try refreshing it.',
    'Priorytet zmieniony. Zapisz go na donglu.': 'Priority changed. Save it to the adapter.',
    'Zapisywanie na donglu…': 'Saving to the adapter…',
    'Zapisano na donglu. Kolejność obowiązuje przy następnym łączeniu.':
      'Saved to the adapter. The new order takes effect the next time it connects.',
    Połączono: 'Connected',
    'Szukanie zapamiętanych sieci': 'Looking for saved networks',
    'Łączenie z siecią': 'Connecting to the network',
    Uwierzytelnianie: 'Authenticating',
    'Weryfikacja hasła': 'Checking the password',
    'Weryfikacja połączenia': 'Checking the connection',
    'Rozłączono · ponawianie': 'Disconnected · retrying',
    'Oczekiwanie na zapamiętaną sieć': 'Waiting for a saved network',
    'Karta nieaktywna': 'USB Wi-Fi inactive',
    'API debug jest niedostępne.': 'The debug API is unavailable.',
    'Operacja nie powiodła się.': 'The operation failed.',
    'Test w RAM: sieci i hasła znikną po ponownym uruchomieniu dongla.':
      'RAM-only test. Networks and passwords are cleared when the adapter restarts.',
    'Zapamiętane sieci są zapisywane na donglu wyłącznie przy zmianie konfiguracji.':
      'The adapter saves networks when you change the configuration.',
    'karta USB podłączona': 'USB Wi-Fi connected',
    'inicjalizacja karty USB': 'starting USB Wi-Fi',
    'brak karty USB': 'no USB Wi-Fi adapter',
    'Inicjalizacja karty': 'Starting USB Wi-Fi',
    'Karta odłączona': 'USB Wi-Fi disconnected',
    'Brak aktywnego adresu IP': 'No active IP address',
    'Wykryto kartę USB': 'USB Wi-Fi detected',
    'Karta USB odłączona': 'USB Wi-Fi disconnected',
    Wybierz: 'Select',
    'Nieobsługiwane zabezpieczenia': 'Unsupported security',
    'Brak sieci w wynikach. Uruchom skanowanie lub wpisz SSID.':
      'No networks found. Scan again or enter an SSID.',
    Połącz: 'Connect',
    'Wybrano sieć. Inne zapamiętane sieci pozostają dostępne.':
      'Network selected. Your other saved networks are still available.',
    Zapomnij: 'Forget',
    'Usunięto zapamiętaną sieć.': 'Saved network removed.',
    'Bieżąca sieć': 'Current network',
    'Nie zapisano jeszcze żadnej sieci.': 'No saved networks yet.',
    'API debug niedostępne': 'debug API unavailable',
    'Wykonywanie operacji…': 'Working…',
    'SSID może mieć maksymalnie 32 bajty.': 'The SSID can be up to 32 bytes long.',
    'Sieć zapisana w RAM na czas testu. Rozpoczęto próbę połączenia.':
      'Network saved in RAM for this test. Connecting now.',
    'Sieć zapisana na donglu. Rozpoczęto próbę połączenia.':
      'Network saved to the adapter. Connecting now.',
    'Skanowanie rozpoczęte; wyniki odświeżą się automatycznie.':
      'Scan started. Results will update automatically.',
    'Ponowiono wyszukiwanie zapamiętanych sieci.': 'Looking for saved networks again.',
    'Usługa przywracania jest niedostępna.': 'The restore service is unavailable.',
    'Adapter odrzucił żądanie.': 'The adapter rejected the request.',
    'Sprawdzanie instalacji i tworzenie kopii. Nie odłączaj zasilania.':
      'Checking the installation and creating a backup. Keep the adapter powered.',
    'Usuwanie Dextend i sprawdzanie plików. Nie odłączaj zasilania.':
      'Removing Dextend and checking files. Keep the adapter powered.',
    'Dextend usunięty. Uruchom adapter ponownie, połącz się z jego Wi-Fi i w panelu producenta wybierz przywrócenie ustawień fabrycznych. Zostaw zasilanie podłączone, aż adapter ponownie się uruchomi.':
      "Dextend has been removed. Restart the adapter, reconnect to its Wi-Fi and select the factory reset option in the manufacturer's panel. Keep it powered until it restarts.",
    'Adapter odrzucił operację przed zapisem. Dextend pozostaje zainstalowany.':
      'The adapter rejected the operation before writing any files. Dextend is still installed.',
    'Nie udało się potwierdzić usunięcia Dextend. Zostaw zasilanie podłączone i sprawdź stan przed ponowieniem.':
      'Dextend removal could not be confirmed. Keep the adapter powered and check its status before trying again.',
    'Nie otrzymano potwierdzenia uruchomienia.':
      'The adapter did not confirm that the restore had started.',
    'Brak potwierdzenia z adaptera. Nie odłączaj zasilania. Panel spróbuje ponownie sprawdzić stan.':
      "The adapter hasn't confirmed its status. Keep it powered while the panel checks again.",
    'Nie potwierdzono przyjęcia żądania. Nie odłączaj zasilania podczas sprawdzania stanu.':
      "The adapter hasn't confirmed the request. Keep it powered while the panel checks its status.",
    'Nieprawidłowy adres panelu.': 'Invalid panel address.',
    'Panel nie jest jeszcze gotowy.': 'The panel is still starting.',
    'Odśwież panel i spróbuj ponownie.': 'Refresh the panel and try again.',
    'Nieprawidłowe ustawienia.': 'Invalid settings.',
    'Nieprawidłowa kolejność telefonów.': 'Invalid phone order.',
    'Trwa operacja na oprogramowaniu adaptera.':
      'The adapter is already performing a firmware operation.',
    'Nie udało się zapisać ustawień. Odśwież panel.': 'Could not save settings. Refresh the panel.',
    'Niedozwolona metoda.': 'Request method is not allowed.',
    'Usługa przywracania nie jest gotowa.': 'The restore service is not ready.',
    'Brak klucza sesji.': 'The session key is missing.',
    'Nieprawidłowe żądanie przywrócenia.': 'Invalid restore request.',
    'Wpisz PRZYWRÓĆ, aby potwierdzić.': 'Enter RESTORE to confirm.',
    'Nie można uruchomić usługi przywracania.': 'Could not start the restore service.',
    'Żądanie przywrócenia już istnieje. Sprawdź jego wynik.':
      'A restore has already been requested. Check its status.',
    'Nie udało się połączyć z adapterem.': 'Could not connect to the adapter.',
  };

  const select = document.getElementById('panel-language');
  const storageKey = 'dextend-panel-language';
  const bindings = new WeakMap();
  const hasTranslation = (key) => Object.hasOwn(english, key);
  let language = /^pl(?:-|$)/i.test(navigator.language) ? 'pl' : 'en';
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved === 'pl' || saved === 'en') language = saved;
  } catch {
    // A blocked storage backend still allows changing language for this visit.
  }

  function t(key, values = {}) {
    const message = language === 'en' && hasTranslation(key) ? english[key] : key;
    return message.replace(/\{(\w+)\}/g, (placeholder, name) => {
      const value = values[name];
      return typeof value === 'function' ? value() : (value ?? placeholder);
    });
  }

  function render(element) {
    for (const [attribute, { key, values }] of bindings.get(element)) {
      const value = t(key, values);
      if (attribute === 'text') {
        if (element.textContent !== value) element.textContent = value;
      } else if (element.getAttribute(attribute) !== value) {
        element.setAttribute(attribute, value);
      }
    }
  }

  function set(element, key, values, attribute = 'text') {
    if (!bindings.has(element)) {
      bindings.set(element, new Map());
      element.setAttribute('data-i18n', '');
    }
    bindings.get(element).set(attribute, { key, values });
    render(element);
  }

  // Translate the active panel without rebuilding form controls.
  function apply() {
    document.documentElement.lang = language;
    select.value = language;
    document.querySelectorAll('[data-i18n]').forEach(render);
  }

  document
    .querySelectorAll('[data-i18n]')
    .forEach((element) => set(element, element.textContent.trim().replace(/\s+/g, ' ')));
  document
    .querySelectorAll('[data-i18n-label]')
    .forEach((element) =>
      set(element, element.getAttribute('aria-label'), undefined, 'aria-label'),
    );
  document
    .querySelectorAll('[data-i18n-placeholder]')
    .forEach((element) =>
      set(element, element.getAttribute('placeholder'), undefined, 'placeholder'),
    );
  apply();
  select.addEventListener('change', () => {
    language = select.value;
    try {
      localStorage.setItem(storageKey, language);
    } catch {}
    apply();
    document.dispatchEvent(new Event('dextend-languagechange'));
  });

  function error(message, fallback) {
    return new Error(hasTranslation(message) ? message : fallback);
  }

  function errorKey(error) {
    return hasTranslation(error.message) ? error.message : 'Nie udało się połączyć z adapterem.';
  }

  return {
    t,
    set,
    error,
    errorKey,
    get language() {
      return language;
    },
  };
})();
