# Dopasowanie Android Auto do ekranu Yamahy

Zaczęliśmy od wyśrodkowanego obszaru 640×360 w strumieniu H.264 o wymiarach 800×480. Telefon dobiera układ interfejsu do zadanych wymiarów treści. Licznik Yamahy wyświetla okno określone przez parametry kadrowania SPS w strumieniu. Zmiana tylko jednego z tych ustawień mogła zostawić uciętą mapę albo przenieść pasek nawigacji na bok.

Na liczniku LYWW20 przy obszarze 624×332 pasek znalazł się po lewej stronie. Przy 624×352 i 120 DPI telefon zostawił go na dole. Po przycięciu 44 pikseli z lewej, 76 z prawej, 32 z góry i 40 z dołu widoczne okno miało 680×408. Podczas próby z bezprzewodowym Android Auto użytkownik potwierdził na rzeczywistym LYWW20 widoczność krawędzi mapy i działanie joysticka.

Most zmienia parametry kadrowania H.264, dzięki czemu adapter przekazuje zakodowane klatki bez dekodowania i ponownego kodowania. W porównaniu strumieni syntetycznych i nagrania z telefonu wszystkie 306 klatek odpowiadało oczekiwanemu wycinkowi piksel w piksel. W zakładce Obraz wracamy do profilu LYWW20 lub dobieramy marginesy do innego ekranu. Przewodowe Android Auto i inne liczniki wymagają osobnych prób sprzętowych.

© 2026 Overev · [overev.com](https://overev.com/)
