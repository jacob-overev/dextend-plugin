# External USB diagnostic radio and SSH

This source kit builds the AR9271 service payload. It includes the upstream
source archives, firmware license, build configuration and ABI observations
used for the image. Own integration scripts are by overev.com; upstream
copyrights and licenses remain unchanged.

The TP-Link USB radio is independent of the built-in Wi-Fi and Bluetooth used
by CarPlay and Android Auto. The Debug tab appears when the qualified USB
adapter is connected. Its saved networks can be configured in that tab.
SSH uses public-key authentication on the external interface only. The image
contains a public client key, never its private counterpart. Host keys are
created on each adapter. No default Wi-Fi credentials are shipped.

## Rebuild

Prepare the kernel with `../../aoa/build-module.sh`. Set `CROSS_COMPILE` to the
ARM GCC 4.9.4 prefix and `YAMAHA_MUSL_PREFIX` to the ARM musl toolchain prefix.
Run `sh build.sh /absolute/new-output /absolute/aoa-output/kernel`.
The build verifies `upstream/SHA256SUMS`. The two kernel archive parts join
into the same pinned archive used by the AOA recipe:

```sh
cat upstream/linux-imx.tar.gz.part1 upstream/linux-imx.tar.gz.part2 > /tmp/linux-imx.tar.gz
export DEXTEND_KERNEL_ARCHIVE=/tmp/linux-imx.tar.gz
```

The reconstructed kernel configuration is in `../../aoa/build-support/`.
`target.symvers` extends those observations to the radio modules. `check.py`
checks all imports, symbol CRCs, vermagic and module structure size against
`abi-reference.json`. These checks do not establish physical radio operation
or compatibility with another kernel.

## Upstream inputs and licenses

- Linux/NXP `ad37eebd4b27a81080b655034e45521f064a7a09`, GPL-2.0, from
  https://github.com/nxp-imx/linux-imx/tree/ad37eebd4b27a81080b655034e45521f064a7a09.
  Sources are included as two archive parts because of Git's file size limit.
- libnl 3.11.0, LGPL-2.1, from https://github.com/thom311/libnl/releases/tag/libnl3_11_0.
- wpa_supplicant 2.11, BSD, from https://w1.fi/releases/wpa_supplicant-2.11.tar.gz.
- Dropbear 2025.89, licenses in its `LICENSE`, from
  https://matt.ucc.asn.au/dropbear/releases/dropbear-2025.89.tar.bz2.
- `htc_9271.fw`, redistribution terms in `LICENCE.atheros_firmware`, matches
  https://github.com/wkennington/linux-firmware/blob/711d3297bac870af42088a467459a0634c1970ca/htc_9271.fw.

The image carries these notices. The bundled archives include the full
sources for the linked libraries and SSH server, not just the radio driver.
