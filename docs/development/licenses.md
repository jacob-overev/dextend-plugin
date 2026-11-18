# Component licenses

The independently developed parts of Dextend use the **PolyForm Noncommercial License 1.0.0**, SPDX identifier `PolyForm-Noncommercial-1.0.0`. The [original license text](../../LICENSE) applies without additional restrictions. [NOTICE](../../NOTICE) identifies the author and scope. The [file map](../../licenses/file-map.json) records the license for each covered file. The Dextend web panel, including its project logo, uses the same license.

The license permits use, modification and redistribution for the noncommercial purposes covered by its terms. Uses outside those terms require separate permission from the rights holder. The source is available under a noncommercial license. It does not meet the definition of an open-source license. These terms do not automatically cover other parts of the private repository, OEM software, historical snapshots or archived packages.

| Component | License and notices |
| --- | --- |
| Project files marked `PolyForm-Noncommercial-1.0.0` in the map | PolyForm Noncommercial License 1.0.0; `LICENSE`, `NOTICE` |
| `src/aoa/` | GPL-2.0-only; `src/aoa/LICENSE` in the distribution repository |
| `src/native/third-party/jsmn/` | MIT; original license and PROVENANCE.json |
| musl | MIT and individual component notices; `licenses/musl-COPYRIGHT.txt` |
| ARM memcpy | BSD-2-Clause; `licenses/musl-ARM-memcpy-BSD-2-Clause.txt` |
| GCC runtime libraries | GCC notices and Runtime Library Exception; `licenses/GCC-copyright.txt` |
| Lato | SIL OFL 1.1; `licenses/Lato-OFL-1.1.txt` |
| DejaVu Sans Mono Bold | Glyph bitmaps on the waiting screen; license in `licenses/DejaVu-Bitstream-Vera.txt` |

Paths in `licenses/file-map.json` are relative to the repository root. The map covers the project's programs, scripts, tests and accompanying materials, along with separately licensed components in that scope. The package includes the original PolyForm text, the Overev notice and the source map. It preserves driver, library and font notices. No additional noncommercial restriction applies to those separate licenses. We check the map with `python3 tools/check_licenses.py`.

© 2026 Overev · [overev.com](https://overev.com/)
