# Licencje składników

Własna, niezależna część dodatku jest udostępniana na **PolyForm Noncommercial
License 1.0.0**, identyfikator SPDX: `PolyForm-Noncommercial-1.0.0`.
Obowiązuje [oryginalny tekst](../../LICENSE), bez dodatkowych ograniczeń.
Autor i zakres są wskazane w [NOTICE](../../NOTICE), a przypisanie poszczególnych
plików w [mapie](../../licenses/file-map.json). Tą samą licencją obejmujemy panel WWW Dextend wraz z logo projektu.

Licencja pozwala korzystać, modyfikować i rozpowszechniać oprogramowanie
do celów dopuszczonych jej warunkami niekomercyjnymi. Wykorzystanie wykraczające
poza te uprawnienia wymaga odrębnego zezwolenia uprawnionego.
To oprogramowanie z dostępnym kodem na licencji niekomercyjnej, nie licencja
open source. Nowe warunki nie obejmują automatycznie innych części prywatnego
repozytorium, oprogramowania OEM, historycznych migawek ani zachowanych paczek.

| Składnik | Licencja i noty |
| --- | --- |
| Własne pliki oznaczone w mapie `PolyForm-Noncommercial-1.0.0` | PolyForm Noncommercial License 1.0.0; `LICENSE`, `NOTICE` |
| `src/aoa/` | GPL-2.0-only; `src/aoa/LICENSE` in the distribution repository |
| `src/native/third-party/jsmn/` | MIT; oryginalna licencja i PROVENANCE.json |
| musl | MIT i noty poszczególnych fragmentów; `licenses/musl-COPYRIGHT.txt` |
| ARM memcpy | BSD-2-Clause; `licenses/musl-ARM-memcpy-BSD-2-Clause.txt` |
| Biblioteki wykonawcze GCC | Noty GCC i Runtime Library Exception; `licenses/GCC-copyright.txt` |
| Lato | SIL OFL 1.1; `licenses/Lato-OFL-1.1.txt` |
| DejaVu Sans Mono Bold | Bitmapy znaków na planszy; licencja w `licenses/DejaVu-Bitstream-Vera.txt` |

Mapa `licenses/file-map.json` używa ścieżek względem głównego katalogu
repozytorium i obejmuje własne programy, skrypty, testy i materiały
towarzyszące oraz odrębnie licencjonowane składniki z tego zakresu. Pakowanie dostarcza oryginalny
tekst PolyForm, notę Overev i mapę źródeł oraz zachowuje noty sterownika,
bibliotek i fontu. Te odrębne licencje nie otrzymują dodatkowych ograniczeń NC.
Mapę sprawdzamy poleceniem `python3 tools/check_licenses.py`.

© 2026 Overev · [overev.com](https://overev.com/)
