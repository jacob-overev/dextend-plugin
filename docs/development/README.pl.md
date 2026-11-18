# Oprogramowanie dongla

Angielski oryginał zapisujemy jako `name.md`, a polskie tłumaczenie jako `name.pl.md`. [English](README.md)

Źródła mostu SDL, obsługi Bluetooth i konfiguracji odbiornika oraz skryptów
startowych native. Sterownik AOA jest w katalogu `src/aoa/` repozytorium. iPhone łączy się
z odbiornikiem przez Bluetooth/Wi-Fi, a odbiornik z CCU motocykla przez USB. Bieżący wariant testowy
obejmuje również Android Auto i automatyczny wybór odbiornika telefonu.

Pierwsze próby CarPlay na Yamasze obejmowały obraz, joystick i dźwięk z iPhone’a po kablu. Później dodaliśmy połączenie bezprzewodowe. Obsługa Android Auto wymagała dopasowania układu telefonu do licznika. Instalator USB, a następnie aktualizacje z panelu, pozwoliły dostarczać te zmiany w jednym obrazie.

| Katalog | Zawartość |
| --- | --- |
| `src/native/` | Programy C oraz parser jsmn |
| [`../../src/aoa/`](../../src/aoa/) | Sterownik AOA, konfiguracja budowania i testy ABI |
| `src/runtime/` | Start i nadzór procesów oraz połączeń |
| `packaging/`, `tools/` | Budowanie, pakowanie i testowanie |
| `tests/` | Testy protokołu, odzyskiwania sesji, polityki telefonów i instalatora |
| `src/usb/` | Profil i skrypty instalatora USB |
| `src/assets/` | Plansza używana przez runtime |
| `src/web/` | Panel konfiguracji, lista sparowanych telefonów i priorytety |
| `src/diagnostics/` | Zestaw diagnostyczny TP-Link/SSH i jego budowa |

Testy hosta uruchamiamy z głównego katalogu repozytorium:

```sh
sh tools/test.sh
```

- [Budowa](build.pl.md)
- [Proces instalacji, aktualizacji i powrotu do OEM](installation.pl.md)
- [Konfiguracje i testy sprzętowe](compatibility.pl.md)
- [Jak sprawdzić zmianę](validation.pl.md)
- [Dopasowanie obrazu Android Auto](android-auto.pl.md)
- [Licencje składników](licenses.pl.md)
- [Aktualizacje przez przeglądarkę](network-updates.pl.md)

© 2026 Overev · [overev.com](https://overev.com/)
