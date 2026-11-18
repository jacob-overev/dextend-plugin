#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Reconstruct the tested source build. Never loads a module or edits ELF CRCs.
set -eu
src=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
out=${1:?Usage: build-module.sh NEW_ABSOLUTE_OUTPUT}
cross=${CROSS_COMPILE:?Set the ARM GCC 4.9.4 executable prefix}
case "$out" in /*) ;; *)
    echo 'Absolute output required' >&2
    exit 2
    ;;
esac
[ ! -e "$out" ] || {
    echo 'Output already exists' >&2
    exit 2
}
[ "$("${cross}gcc" -dumpversion)" = 4.9.4 ] || {
    echo 'This recipe requires GCC 4.9.4' >&2
    exit 2
}
revision=ad37eebd4b27a81080b655034e45521f064a7a09
digest=417a92355f11a0c225cd948daa7eb21f42adca8c00c549156a5365474870f7d6
# SHA-256 of the sorted CONFIG_ defines from the reference build.
config_digest=ed7ba38a2f1a9b5f0bbcbf94b9e22d7525239b3f048f65b626457825aaf012a1
mkdir -p "$out/kernel" "$out/module"
archive=${DEXTEND_KERNEL_ARCHIVE:-$out/linux-imx.tar.gz}
if [ ! -f "$archive" ]; then
    curl -fL --max-time 180 "https://codeload.github.com/nxp-imx/linux-imx/tar.gz/$revision" -o "$archive.download"
    mv "$archive.download" "$archive"
fi
printf '%s  %s\n' "$digest" "$archive" | sha256sum -c -
kernel=$out/kernel
tar -xzf "$archive" --strip-components=1 -C "$kernel"
# Match the reference configuration by dropping these two ATH9K selects.
sed -i '/^[[:blank:]]*select MAC80211_LEDS$/d' "$kernel/drivers/net/wireless/ath/ath9k/Kconfig"
cp "$src/build-support/kernel.config" "$kernel/.config"
make -C "$kernel" ARCH=arm CROSS_COMPILE="$cross" HOSTCFLAGS=-fcommon olddefconfig
make -C "$kernel" -j"${DEXTEND_BUILD_JOBS:-4}" ARCH=arm CROSS_COMPILE="$cross" HOSTCFLAGS=-fcommon \
    KERNELRELEASE=3.14.52+g94d07bb modules_prepare
sed -n '/^#define CONFIG_/p' "$kernel/include/generated/autoconf.h" | LC_ALL=C sort >"$out/autoconf-defines.txt"
printf '%s  %s\n' "$config_digest" "$out/autoconf-defines.txt" | sha256sum -c -
cp "$src/build-support/target.symvers" "$kernel/Module.symvers"
cp "$src/yamaha_aoa.c" "$src/aoa_protocol.h" "$out/module/"
cat >"$out/module/Makefile" <<'KBUILD'
# SPDX-License-Identifier: GPL-2.0-only
obj-m := yamaha_aoa.o
ccflags-y += -Wall
KBUILD
make -C "$kernel" ARCH=arm CROSS_COMPILE="$cross" HOSTCFLAGS=-fcommon \
    KERNELRELEASE=3.14.52+g94d07bb M="$out/module" modules
cp "$out/module/yamaha_aoa.ko" "$out/yamaha_aoa.ko.EXPERIMENTAL"
sha256sum "$out/yamaha_aoa.ko.EXPERIMENTAL"
echo 'Experimental reconstructed ABI; compilation is not compatibility approval.'
