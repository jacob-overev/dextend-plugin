# Building the plugin

We build locally and use a new output directory outside the repository. The build does not connect to the adapter. Our build environment includes Python 3.11+, OpenSSL, BusyBox, bwrap, host GCC, make, curl, tar, QEMU user (qemu-arm), the OpenSSH client, ARM soft-float binutils, `arm-linux-gnueabi-gcc`, FFmpeg with libx264, fontconfig, Pillow and DejaVu Sans Mono Bold. The kernel module requires ARM GCC **4.9.4**.

<a id="budowa-img-wydania"></a>

## Building a release IMG

We set the release number in the repository's root `VERSION` file. The build uses local sources in `src/aoa/` and `src/diagnostics/build/`. It reads the previous update sequence number from the IMG in `releases/`.

Packaging both runtimes inserts `VERSION` into the web panel header and device information. The number remains visible on every tab even without the debug adapter or an API response. The template and package checks keep it consistent with the IMG. We change the number in the source version file.

```sh
export DEXTEND_UPDATE_SIGNING_KEY=/private/path/updater-ed25519.pem
export CROSS_COMPILE=/absolute/path/to/arm-linux-gnueabi-
export YAMAHA_MUSL_PREFIX=/absolute/path/to/musl-arm
./build-release.sh /absolute/path/to/new-output
```

We copy `distribution/A15W_Update.img` to the USB drive. The same output directory contains `SHA256SUMS` and `VERSION`. Product details, the update sequence number and image inspection results are in `usb/install/MANIFEST.json`. We inspect the finished image with the following command.

```sh
python3 tools/usb_image.py /absolute/path/to/new-output/distribution/A15W_Update.img
```

Each IMG includes the removal procedure used by the panel and subsequent updates. The build checks that the procedure is complete and that its version matches the IMG and waiting screen. The same image installs on OEM software or removes a recognized previous release, verifies the OEM state and installs the new version. The [update procedure](installation.md) describes which files it removes and what happens after an interruption.

When we need a specific sequence number, we pass it as the second argument. It must exceed the previous IMG's sequence number. We build individual components from the repository root.

## Image size and free space on the adapter

After each build, we inspect `size_budget` in `usb/install/MANIFEST.json`. The USB image size is `image_bytes`. The compressed package written to flash is `runtime_compressed_bytes`, and the archive unpacked into RAM is `runtime_unpacked_bytes`. The unpacked main archive is limited to 1 MiB and the service bundle to 4 MiB. First installation needs the combined size of the two compressed archives rounded up to KiB, plus 320 KiB and space for the radio configuration backup. The report includes the measured memory and the total required flash space. Release tests verify rejection 1 KiB below the flash threshold and installation exactly at the threshold.

ARM programs use 4 KiB segment alignment to match the adapter's kernel page size and reduce the unpacked archive size. To measure an individual adapter without writing to flash, we use the `probe` image and read `flash_free_kib` in `DEXTEND-RESULT.txt`.

<a id="kontrola-wycofania-przed-wydaniem"></a>

## Rollback checks before release

For any change that writes a persistent file during installation, startup or normal operation, we verify rollback in the same release. We update `src/usb/transaction.sh.in` to remove new plugin paths and restore modified OEM files. We add a test if the write occurs only after starting a service or using a panel action.

The build runs the installer and removal script extracted from the new IMG in isolation. It exercises panel and USB update modes separately and compares paths, contents, file types, permissions and owners against the recorded OEM state. A synthetic profile and boot confirmation stand in for the physical adapter. A mismatch or skipped test prevents creation of `distribution/`. Results are in `restore-validation.log`.

To recheck a finished image, we use the sources from its release tag and run the following from the repository root:

```sh
python3 tests/test_usb_packages.py --check-release-img /absolute/path/to/A15W_Update.img
```

## Host tests

```sh
sh tools/test.sh
```

Installer tests use `bwrap` and a local copy of the OEM files. Other tests exercise the protocol against a synthetic CCU, stream and session recovery, private audio configuration changes and AOA/ABI logic. Host tests do not validate Yamaha hardware, JFFS2, physical USB, radio operation or recovery after power loss.

## ARM userspace

We start in a fresh working directory. This example puts it outside the repository.

```sh
export DEXTEND_BUILD_ROOT="$PWD/../dextend-build"
mkdir -p "$DEXTEND_BUILD_ROOT"
export YAMAHA_MUSL_BUILD_DIR="$DEXTEND_BUILD_ROOT/toolchain"
sh tools/build-musl.sh
export YAMAHA_MUSL_PREFIX="$YAMAHA_MUSL_BUILD_DIR/musl-arm"
sh tools/build-userspace.sh "$DEXTEND_BUILD_ROOT/userspace"
```

The build downloads musl 1.2.5, checks the pinned SHA-256 and creates a static ARM soft-float toolchain. It builds the bridge with Yamaha's compatible SDL identity (`Motorize`, `7a5f3f258b`, `7a5f3f25-8b82-4e0f-a173-80aefee79897`), along with `receiver-native`, `iphone-usb-role`, `bluetooth-autoconnect` and `phone-policy`. It excludes the preload and the historical OEM module.

## AOA module

```sh
export CROSS_COMPILE=/absolute/path/to/arm-linux-gnueabi-
sh src/aoa/build-module.sh "$DEXTEND_BUILD_ROOT/module"
```

The prefix must point to GCC 4.9.4. We provide compatible host libraries such as libmpfr.so.4 inside the isolated toolchain environment. This keeps the system libraries in place. The build downloads public NXP kernel revision `ad37eebd4b27a81080b655034e45521f064a7a09` and checks SHA-256 `417a92355f11a0c225cd948daa7eb21f42adca8c00c549156a5365474870f7d6`. To reuse an identical, previously downloaded archive, we set `DEXTEND_KERNEL_ARCHIVE`. The checksum check still runs.

The `src/aoa/build-support/` directory contains the reconstructed configuration, observed exports and source overlay from the previously tested build. These are not the manufacturer's original private firmware sources. The build verifies generated configuration definitions and leaves CRCs in the compiled ELF intact. The resulting `yamaha_aoa.ko.EXPERIMENTAL` is specific to this target. A matching 3.14 kernel version alone is insufficient grounds to load it on another receiver.

## Waiting screen and working package

```sh
python3 tools/build-waiting.py "$DEXTEND_BUILD_ROOT/waiting"
python3 tools/package.py \
  --userspace "$DEXTEND_BUILD_ROOT/userspace" \
  --module "$DEXTEND_BUILD_ROOT/module/yamaha_aoa.ko.EXPERIMENTAL" \
  --waiting "$DEXTEND_BUILD_ROOT/waiting/waiting.h264" \
  --output "$DEXTEND_BUILD_ROOT/package"
```

The waiting screen uses the approved `src/assets/waiting.png` and is encoded as one 640×360 H.264 frame. Both it and the IMG take the Dextend release number from the root `VERSION` file. At startup the plugin reads the firmware version from `/etc/software_version`. The optional hardware revision lookup with `riddleBoxCfg -g hardwareVer` needs validation on a physical adapter. A failed lookup or a value that does not fit is displayed as a dash. The fallback screen in the IMG includes the Dextend version even without device readings.

The package contains the LZMA runtime, coordinator and startup hook. Packaging refuses to overwrite the output directory and does not write flash or install the plugin. The [USB installation guide](../installation.md) covers installation on the adapter.

Binary distribution requires the corresponding GPL sources and applicable notices. A local package build neither publishes the package nor fulfils that distribution obligation. The [license map](licenses.md) identifies each component's license.

We describe installation from the panel in [browser updates](network-updates.md). API tests require Python's `cryptography` library.

The TP-Link/SSH bundle is built by `src/diagnostics/build/build.sh`. The same tag includes its full source and configuration. We run the service tests with `DEXTEND_SERVICE_BUILD=/absolute/output/service python3 tests/test_service.py`. The SSH test starts ARM Dropbear under QEMU in host isolation, without connecting to the adapter. In the manifest, `service_compressed_bytes` and `service_unpacked_bytes` give the size of this additional archive.

© 2026 Overev · [overev.com](https://overev.com/)
