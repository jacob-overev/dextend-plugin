#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Experimental RAM-only wired receiver, using the SDL process's IPC listener.
set -eu
unset LD_PRELOAD
cd /tmp/yamaha-sdl
. ./debug-log.sh
[ -S "${YAMAHA_CARPLAY_SOCKET:-/tmp/yamaha-sdl/carplay-ipc.sock}" ] || {
    debug 'ERROR: start yamaha-sdl-live --live first'
    exit 1
}
[ -z "$(pidof AppleCarPlay 2>/dev/null || true)" ] || {
    debug 'ERROR: receiver already running'
    exit 1
}
[ -z "$(pidof ARMiPhoneIAP2 2>/dev/null || true)" ] || {
    debug 'ERROR: iAP2 already running'
    exit 1
}
[ "$(cat /sys/class/android_usb/android0/functions)" = 'iap2,ncm' ] || {
    debug 'ERROR: unexpected phone-side gadget'
    exit 1
}

# HiCar otherwise restarts continuously after the factory IPC server is stopped.
for p in $(ps | awk '/phone_link_deamon.sh HiCar start/ && !/awk/ {print $1}'); do
    kill -STOP "$p"
done
killall ARMHiCar 2>/dev/null || true

if [ "$(cat /sys/class/android_usb/android0/state)" != CONFIGURED ]; then
    node=
    for device in /sys/bus/usb/devices/1-*; do
        [ -f "$device/idVendor" ] || continue
        [ "$(cat "$device/idVendor")" = 05ac ] || continue
        node=$(printf '/dev/bus/usb/%03d/%03d' "$(cat "$device/busnum")" "$(cat "$device/devnum")")
        break
    done
    [ -n "$node" ] || {
        debug 'ERROR: no iPhone on phone-side USB bus'
        exit 1
    }
    ./iphone-usb-role "$node" --switch
fi
count=0
while [ "$(cat /sys/class/android_usb/android0/state)" != CONFIGURED ]; do
    count=$((count + 1))
    [ "$count" -lt 30 ] || {
        debug 'ERROR: phone USB did not configure'
        exit 1
    }
    sleep 1
done
# Link-local address only on the phone interface; no default route is added.
ifconfig ncm0 169.254.24.1 netmask 255.255.0.0 up
debug 'STAGE PHONE_USB_CONFIGURED'

(
    /tmp/yamaha-sdl/receiver-native --phone-audio /usr/sbin/AppleCarPlay --width 640 --height 360 --fps 30 2>&1 |
        debug_receiver carplay
) </dev/null &
(
    /tmp/yamaha-sdl/receiver-native --phone-audio /usr/sbin/ARMiPhoneIAP2 640 360 30 2>&1 |
        debug_receiver iap2
) </dev/null &
debug 'STAGE WIRED_CARPLAY_STARTED'
