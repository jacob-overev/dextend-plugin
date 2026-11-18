#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

set -eu
[ "${1:-}" = --prepared-ram-trial ] || exit 2
cd /tmp/yamaha-sdl
[ ! -f boot.pid ] || exit 2
[ ! -d /sys/module/g_android_accessory ] || exit 2
listeners=$(awk '$8=="/var/run/adb-driver"{n++} END{print n+0}' /proc/net/unix)
[ "$listeners" = 0 ] || exit 2
export YAMAHA_AOA_DRIVER=independent
export YAMAHA_CARPLAY_SOCKET=/var/run/adb-driver
unset LD_PRELOAD
exec sh ./boot-live.sh
