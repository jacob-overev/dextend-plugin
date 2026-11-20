#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Build only; never accesses a receiver.
set -eu
src=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
out=${1:?Usage: build-userspace.sh NEW_ABSOLUTE_OUTPUT}
case "$out" in /*) ;; *)
    echo 'Absolute output required' >&2
    exit 2
    ;;
esac
[ ! -e "$out" ] || {
    echo 'Output already exists' >&2
    exit 2
}
cc=${YAMAHA_MUSL_PREFIX:?Build the pinned musl toolchain first}/bin/musl-gcc
mkdir -p "$out/third-party"
# ARM Linux on the adapter uses 4 KiB pages. Avoid 64 KiB ELF segment gaps.
page_size=-Wl,-z,max-page-size=4096,-z,common-page-size=4096
# Thumb-2 keeps the projection bridge within the one-MiB runtime archive.
"$cc" -static "$page_size" -ffunction-sections -fdata-sections -Wl,--gc-sections -O2 -std=c11 -Wall -Wextra -Werror -march=armv7-a -mthumb \
    -Wl,-Map,"$out/yamaha-sdl-live.map" -o "$out/yamaha-sdl-live" "$src/src/native/probe.c"
"$cc" -static "$page_size" -O2 -Wall -Wextra -Werror -o "$out/iphone-usb-role" "$src/src/native/iphone-usb-role.c"
"$cc" -static "$page_size" -Os -Wall -Wextra -Werror -o "$out/bluetooth-autoconnect" "$src/src/native/bluetooth-autoconnect.c"
# These configuration helpers run on the same ARMv7-A target as the bridge.
# Thumb-2 keeps both copies of the panel and their binaries within the RAM budget.
for name in receiver-native phone-policy; do
    "$cc" -static "$page_size" -Os -march=armv7-a -mthumb -ffunction-sections -fdata-sections \
        -Wl,--gc-sections -std=c11 -Wall -Wextra -Werror -o "$out/$name" "$src/src/native/$name.c"
done
"$cc" -static "$page_size" -Os -std=c11 -Wall -Wextra -Werror -o "$out/waiting-frame" "$src/src/native/waiting-frame.c"
# Use the same ARMv7-A Thumb-2 target for the update verifier.
"$cc" -static "$page_size" -Os -march=armv7-a -mthumb -std=c11 -ffunction-sections -fdata-sections -Wl,--gc-sections -Wall -Wextra -Werror \
    -I"$src/src/native/third-party/monocypher" -o "$out/updater-http" "$src/src/native/updater-http.c" \
    "$src/src/native/third-party/monocypher/monocypher.c" "$src/src/native/third-party/monocypher/monocypher-ed25519.c"
"$cc" -static "$page_size" -Os -Wall -Wextra -Werror -o "$out/service-key" "$src/src/native/service-key.c"
for name in service-key yamaha-sdl-live iphone-usb-role bluetooth-autoconnect receiver-native phone-policy waiting-frame updater-http; do
    arm-linux-gnueabi-strip "$out/$name"
done
cp "$YAMAHA_MUSL_PREFIX/third-party/musl-COPYRIGHT.txt" "$YAMAHA_MUSL_PREFIX/third-party/GCC-copyright.txt" \
    "$YAMAHA_MUSL_PREFIX/third-party/GPL-3.txt" "$YAMAHA_MUSL_PREFIX/third-party/build-provenance.txt" "$out/third-party/"
cp "$src/licenses/musl-ARM-memcpy-BSD-2-Clause.txt" "$out/third-party/"
(cd "$out" && sha256sum service-key yamaha-sdl-live iphone-usb-role bluetooth-autoconnect receiver-native phone-policy waiting-frame updater-http >SHA256SUMS)
echo "Built ARM userspace in $out; this is not an installer."
