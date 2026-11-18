# Adapter software

We keep the English original in `name.md` and its Polish translation in `name.pl.md`. [Polski](README.pl.md)

The adapter connects to the motorcycle CCU over USB and to the iPhone over Bluetooth and Wi-Fi. This tree contains the SDL bridge, Bluetooth and receiver configuration, native startup scripts and the AOA driver in `src/aoa/`. The test build also supports Android Auto and automatic selection of the phone receiver.

Early CarPlay tests on the Yamaha covered video, joystick control and audio from a wired iPhone. We then added wireless CarPlay. Adding Android Auto meant fitting the phone layout to the motorcycle display. The USB installer and later the browser updater let both connection modes ship in one image.

| Directory | Contents |
| --- | --- |
| `src/native/` | C programs and the jsmn parser |
| [`../../src/aoa/`](../../src/aoa/) | AOA driver, build configuration and ABI tests |
| `src/runtime/` | Process startup, connection management and supervision |
| `packaging/`, `tools/` | Build, packaging and test tools |
| `tests/` | Protocol, session recovery, phone policy and installer tests |
| `src/usb/` | USB installer profile and scripts |
| `src/assets/` | Waiting screen used at runtime |
| `src/web/` | Configuration panel, paired phones and connection priorities |
| `src/diagnostics/` | TP-Link/SSH diagnostic service and its build tools |

We run the host tests from the repository root:

```sh
sh tools/test.sh
```

- [Build instructions](build.md)
- [Installation, updates and OEM restoration](installation.md)
- [Hardware configurations and compatibility tests](compatibility.md)
- [Testing a change](validation.md)
- [Android Auto display geometry](android-auto.md)
- [Component licenses](licenses.md)
- [Browser updates](network-updates.md)

© 2026 Overev · [overev.com](https://overev.com/)
