#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

set -eu
cd /tmp/yamaha-sdl
case "${1:-}" in
    usb) [ "$#" -eq 1 ] || exit 2 ;;
    wireless)
        [ "$#" -eq 2 ] || exit 2
        case "$2" in
            [0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]:[0-9a-fA-F][0-9a-fA-F]) ;;
            *) exit 2 ;;
        esac
        export YAMAHA_AA_PEER="$2"
        ;;
    *)
        echo 'Usage: start-aa-trial.sh usb | wireless PAIRED_PEER'
        exit 2
        ;;
esac
[ -f /etc/yamaha-sdl/enabled ] || exit 2
[ -x /usr/sbin/ARMAndroidAuto ] || exit 2
if [ -e /tmp/no_touch ]; then
    echo 'AA joystick trial requires /tmp/no_touch absent: this OEM otherwise omits DPAD keys' >&2
    exit 2
fi
if pidof AppleCarPlay ARMiPhoneIAP2 ARMAndroidAuto >/dev/null; then
    echo 'AA trial requires exclusive ownership of the phone session' >&2
    exit 2
fi
if [ "$1" = usb ] && [ "$(cat /sys/class/android_usb/android0/state 2>/dev/null || true)" = CONFIGURED ]; then
    echo 'AA USB trial requires the phone port in host mode; start without iPhone' >&2
    exit 2
fi
export YAMAHA_AA_MODE="$1"
exec sh ./start-independent-candidate.sh --prepared-ram-trial
