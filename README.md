<p align="center">
<img src="./assets/dextend-logo.svg" alt="Dextend" width="480">
</p>

<p align="center">
<a href="https://overev.com"><img src="assets/author-en.svg" alt="Author: Overev" width="100" height="20"></a> <img src="./assets/carplay.svg" alt="Apple CarPlay" width="105" height="20"> <img src="./assets/android.svg" alt="Android Auto" width="99" height="20"> <a href="https://polyformproject.org/licenses/noncommercial/1.0.0"><img src="assets/license.svg" alt="License: PolyForm Noncommercial 1.0.0" width="113" height="20"></a> <a href="https://discord.gg/ErW7BdZzJ"><img src="assets/discord.svg" alt="Discord - Dextend community" width="82" height="20"></a> <a href="https://suppi.pl/overev"><img src="assets/suppi-en.svg" alt="Support via Suppi" width="118" height="20"></a> <a href="https://ko-fi.com/overev"><img src="assets/kofi-en.svg" alt="Buy me a coffee via Ko-fi" width="158" height="20"></a>
</p>

**Apple CarPlay and Android Auto on your motorcycle display** - with the Dextend plugin installed on an external adapter.

Dextend is a single plugin designed for different motorcycles and adapters. Check the list for your motorcycle’s make, model, model year and compatibility status.

[Project status](#stan-projektu) · [Motorcycle compatibility](#wybierz-motocykl) · [Adapters](#posredniki) · [How it works](#jak-to-dziala) · [Before installation](#przed-instalacja) · [License and project independence](#warunki-wykorzystania) · [Support the project](#wsparcie)

<a id="stan-projektu"></a>

## 📦 Project status

[Current version](VERSION)

- Apple CarPlay and Android Auto integration with the motorcycle display.
- Verified support for the 2023-2024 Yamaha TRACER 9 GT+.
- Plugin installation and operation on the Carlinkit CPC200-CCPA / A15W adapter.

<a id="wybierz-motocykl"></a>

## 🏍️ Motorcycle compatibility

| Make | Model | Model years | Compatibility&nbsp;status | Adapter |
| --- | --- | --- | --- | --- |
| Yamaha | TRACER 9 GT+ | 2023-2024 | <img src="./assets/compat-verified-en.svg" alt="Verified" width="56" height="20"> | [CPC200-CCPA / A15W](#posrednik-ccpa) |
| Yamaha | NIKEN GT | 2023 | <img src="./assets/compat-candidate-en.svg" alt="To verify" width="61" height="20"> | [CPC200-CCPA / A15W](#posrednik-ccpa)¹ |
| Yamaha | TMAX / TMAX Tech MAX | 2022-2024 | <img src="./assets/compat-candidate-en.svg" alt="To verify" width="61" height="20"> | [CPC200-CCPA / A15W](#posrednik-ccpa)¹ |
| Yamaha | TMAX / TMAX Tech MAX | 2025 | <img src="./assets/compat-candidate-en.svg" alt="To verify" width="61" height="20"> | [CPC200-CCPA / A15W](#posrednik-ccpa)¹ |
| Yamaha | TRACER 9 GT | 2025+ | <img src="./assets/compat-candidate-en.svg" alt="To verify" width="61" height="20"> | [CPC200-CCPA / A15W](#posrednik-ccpa)¹ |
| Yamaha | TRACER 9 GT+ | 2025+ | <img src="./assets/compat-candidate-en.svg" alt="To verify" width="61" height="20"> | [CPC200-CCPA / A15W](#posrednik-ccpa)¹ |
| Yamaha | MT-09 | 2025+ | <img src="./assets/compat-planned-en.svg" alt="Planned port" width="85" height="20"> | Undetermined |

| Compatibility&nbsp;status | Meaning |
| --- | --- |
| <img src="./assets/compat-verified-en.svg" alt="Verified" width="56" height="20"> | Dextend has been verified on the motorcycle. |
| <img src="./assets/compat-candidate-en.svg" alt="To verify" width="61" height="20"> | Dextend is likely to be compatible. Motorcycle testing is still pending. |
| <img src="./assets/compat-planned-en.svg" alt="Planned port" width="85" height="20"> | Support for this model is planned. Compatibility testing and adapter selection are still pending. |

¹ This adapter still needs to be tested with the listed motorcycle model. The label `2025+` refers to the generation introduced for model year 2025. Later model years still need their own compatibility checks.

We tested Apple CarPlay and Android Auto on our 2024 Yamaha TRACER 9 GT+. Both worked on that motorcycle. The beta may still have bugs.

<a id="posredniki"></a>

## 🔌 Adapters for installing the plugin

The compatibility table lists the adapter for your motorcycle and its support status.

| Manufacturer | Model | Revision | Firmware |
| --- | --- | --- | --- |
| Carlinkit | <a id="posrednik-ccpa"></a>CPC200-CCPA / A15W | `YMA0-WN16-0003` | `2026.07.31.1733` |
| Carlinkit | CPC200-CCPA / A15W | `YMA0-WN16-0003` | `2025.10.15.1127` |
| Carlinkit | CPC200-CCPA / A15W | `YMA0-WN16-0003` | `2025.02.25.1521` (USB installation verified with Dextend 1.2-beta) |

CPC200-CCPA / A15W is the name of a device family. On the adapter’s **Box Info** screen, check **Hardware Version** for the hardware revision and **Version** for the firmware. The table lists the manufacturer’s firmware versions on which we tested Dextend.

Dextend is designed for the adapters listed in the table. Installation and updates may vary by hardware revision and firmware version, even within the same model.

Unlisted revisions or firmware versions may still work with Dextend. We have yet to confirm how installation works on those device variants.

<a id="jak-to-dziala"></a>

## 🔗 How it works

An adapter running Dextend connects Apple CarPlay or Android Auto on your phone to the motorcycle’s infotainment system.

<p align="center">
<img src="assets/how-it-works-en.svg" alt="Smartphone with Apple CarPlay or Android Auto ↔ adapter running Dextend ↔ motorcycle infotainment system" width="560">
</p>

<a id="przed-instalacja"></a>

## 🔧 Before installation

1. Find your motorcycle’s make, model and model year in the list. Check the compatibility status and any exclusions.
2. Click the adapter listed for your motorcycle. Compare its manufacturer, model, hardware revision and firmware with the table.

Download the [A15W_Update.img installation image](https://github.com/jacob-overev/dextend-plugin/releases/latest/download/A15W_Update.img) and its [SHA256SUMS checksum file](https://github.com/jacob-overev/dextend-plugin/releases/latest/download/SHA256SUMS).

[USB installation (PDF)](docs/installation-en.pdf) · [Connection and operation (PDF)](docs/operation-en.pdf) · [Collect diagnostic logs (PDF)](docs/diagnostics-en.pdf)

Markdown: [Installation](docs/installation.md) · [Operation](docs/operation.md) · [Diagnostics](docs/diagnostics.md)

<a id="warunki-wykorzystania"></a>

## 📜 License and project independence

I release the independently developed part of the plugin under the **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)**. The original license terms apply, with no added restrictions.

Dextend is an independent project by Overev. It has no affiliation with, endorsement from, or support from the companies behind the listed devices and integrations. Product names and trademarks belong to their respective owners and are used to describe compatibility.

<a id="wsparcie"></a>

## ☕ Support the author

Dextend is a hobby project I work on in my spare time.

If you use the plugin or just like what I’m doing, you can support my work. Contributions help cover the cost of developing Dextend. Thanks for your support!

Support is voluntary. The plugin is available free of charge under its license. Contributions do not pay for installation or technical support.

<a href="https://suppi.pl/overev"><img src="assets/suppi-en.svg" alt="Support via Suppi" width="118" height="20"></a> <a href="https://ko-fi.com/overev"><img src="assets/kofi-en.svg" alt="Buy me a coffee via Ko-fi" width="158" height="20"></a>

## Development

[Build instructions and host tests](docs/development/README.md)
