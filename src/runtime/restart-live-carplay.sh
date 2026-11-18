#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Reconnect only phone-side USB, preserving CCU/SDL and joystick state.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
[ -S "${YAMAHA_CARPLAY_SOCKET:-/tmp/yamaha-sdl/carplay-ipc.sock}" ] || {
    debug 'ERROR: SDL bridge is not running'
    exit 1
}
[ "$(cat /sys/class/android_usb/android0/functions)" = 'iap2,ncm' ] || {
    debug 'ERROR: unexpected phone-side gadget'
    exit 1
}
killall -KILL AppleCarPlay ARMiPhoneIAP2 2>/dev/null || true
echo 0 >/sys/class/android_usb/android0/enable
sleep 1
echo 1 >/sys/class/android_usb/android0/enable
count=0
while [ "$count" -lt 30 ]; do
    if [ "$(cat /sys/class/android_usb/android0/state)" = CONFIGURED ]; then
        exec sh ./start-live-carplay.sh
    fi
    for device in /sys/bus/usb/devices/1-*; do
        [ -f "$device/idVendor" ] || continue
        if [ "$(cat "$device/idVendor")" = 05ac ]; then
            exec sh ./start-live-carplay.sh
        fi
    done
    count=$((count + 1))
    sleep 1
done
debug 'ERROR: reconnect iPhone cable, then run start-live-carplay.sh'
exit 1
