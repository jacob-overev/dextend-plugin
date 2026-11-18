#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Build pinned third-party sources; never access an adapter.
set -eu
src=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
out=${1:?new absolute output directory}
kernel=${2:?prepared AOA kernel directory}
cc=${YAMAHA_MUSL_PREFIX:?}/bin/musl-gcc
cross=${CROSS_COMPILE:?}
case "$out" in /*) ;; *) exit 2 ;; esac
[ ! -e "$out" ] || exit 2
(cd "$src/upstream" && sha256sum -c SHA256SUMS)
mkdir -p "$out/bin" "$out/licenses"
cp "$src/target.symvers" "$kernel/Module.symvers"
make -C "$kernel" -j4 ARCH=arm CROSS_COMPILE="$cross" HOSTCFLAGS=-fcommon \
    KERNELRELEASE=3.14.52+g94d07bb M=drivers/net/wireless/ath modules
cp "$kernel/drivers/net/wireless/ath/ath.ko" "$kernel/drivers/net/wireless/ath/ath9k/ath9k_"*.ko "$out/bin/"
python3 "$src/check.py" "$out/bin"
cp "$src/upstream/htc_9271.fw" "$out/bin/"
cp "$kernel/COPYING" "$out/licenses/Linux-COPYING"
cp "$src/upstream/LICENCE.atheros_firmware" "$out/licenses/"
for archive in libnl-3.11.0.tar.gz wpa_supplicant-2.11.tar.gz dropbear-2025.89.tar.bz2; do
    tar -xf "$src/upstream/$archive" -C "$out"
done
flags='-Os -ffunction-sections -fdata-sections'
ldflags='-Wl,--gc-sections,-z,max-page-size=4096,-z,common-page-size=4096'
(
    cd "$out/libnl-3.11.0"
    CC="$cc" CFLAGS="$flags" ./configure --host=arm-linux-gnueabi --prefix="$out/libnl" --disable-shared --enable-static --disable-cli
    make -j4
    make install
)
cp "$out/libnl-3.11.0/COPYING" "$out/licenses/libnl-COPYING"
cp "$src/wpa.config" "$out/wpa_supplicant-2.11/wpa_supplicant/.config"
printf '\nCFLAGS += %s -I%s/libnl/include/libnl3\nLDFLAGS += -static %s -L%s/libnl/lib\n' "$flags" "$out" "$ldflags" "$out" >>"$out/wpa_supplicant-2.11/wpa_supplicant/.config"
PKG_CONFIG_PATH="$out/libnl/lib/pkgconfig" make -C "$out/wpa_supplicant-2.11/wpa_supplicant" -j4 CC="$cc" wpa_supplicant
cp "$out/wpa_supplicant-2.11/wpa_supplicant/wpa_supplicant" "$out/bin/"
cp "$out/wpa_supplicant-2.11/COPYING" "$out/licenses/wpa-COPYING"
cp "$src/dropbear.options" "$out/dropbear-2025.89/localoptions.h"
(
    cd "$out/dropbear-2025.89"
    CC="$cc" CFLAGS="$flags" LDFLAGS="$ldflags" ./configure --host=arm-linux-gnueabi --enable-static --disable-zlib --disable-syslog --disable-lastlog --disable-utmp --disable-utmpx --disable-wtmp --disable-wtmpx
    make -j4 PROGRAMS='dropbear dropbearkey' MULTI=1
)
cp "$out/dropbear-2025.89/dropbearmulti" "$out/bin/"
cp "$out/dropbear-2025.89/LICENSE" "$out/licenses/Dropbear-LICENSE"
arm-linux-gnueabi-strip "$out/bin/wpa_supplicant" "$out/bin/dropbearmulti"
printf '%s\n' 'Corresponding upstream sources, build configuration and scripts: src/diagnostics/build/ and src/aoa/ at this release tag.' >"$out/licenses/SOURCES.txt"
