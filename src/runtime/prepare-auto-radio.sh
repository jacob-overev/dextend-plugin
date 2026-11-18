#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Run inside receiver-native's private mount namespace, once per boot worker.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
[ "${YAMAHA_PHONE_AUTO:-0}" = 1 ] || exit 2
[ -x /usr/sbin/ARMAndroidAuto ] && [ -x ./phone-policy ] || exit 2
# Marker is RAM-only. Preserve it for a graceful return to the factory runtime.
if [ -f /tmp/no_touch ] && [ ! -L /tmp/no_touch ]; then mv /tmp/no_touch no_touch.saved; fi
debug AUTO_RADIO_POLICY_INIT
if ./phone-policy --init; then debug AUTO_RADIO_POLICY_READY; else
    rc=$?
    debug "AUTO_RADIO_POLICY_FAILED rc=$rc"
    exit "$rc"
fi
# Parent OEM daemon was started with HiCar mode. Its replacement inherits
# AndroidWorkMode=1 without rewriting either persistent factory config.
killall -KILL bluetoothDaemon 2>/dev/null || true
rm -f /tmp/bluetoothdaemon_running
bluetoothDaemon -n >/dev/null 2>&1 </dev/null &
debug 'STAGE AUTO_RADIO_STARTED android_mode=1 carplay_available=1'
# The independent service publishes phone-policy when the OEM web server is
# ready. Its later startup must not abort the native receiver.
exit 0
