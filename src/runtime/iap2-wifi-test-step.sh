#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Serialized Wi-Fi iAP2 handover/recovery; historical filename retained for overlays.
set -eu
unset LD_PRELOAD
cd /tmp/yamaha-sdl
. ./debug-log.sh
[ "${YAMAHA_IAP2_WIFI_ROUTER_TEST:-0}" = 1 ] || exit 0
if [ "$(cat phone-mode 2>/dev/null || true)" != wireless ]; then
    rm -f iap2-wifi-request iap2-wifi-active iap2-wifi-retry iap2-wifi-failures
    exit 0
fi
[ ! -f phone-restart ] || exit 0
pidof AppleCarPlay >/dev/null || exit 0
generation=$(cat phone-generation 2>/dev/null || true)
read -r uptime rest </proc/uptime
now=${uptime%%.*}
# Once selected, Wi-Fi iAP2 is required even when video remains healthy.
if [ -f iap2-wifi-active ] && ! pidof ARMiPhoneIAP2 >/dev/null; then
    touch iap2-wifi-request
fi
if [ ! -f iap2-wifi-request ]; then
    retry=$(cat iap2-wifi-retry 2>/dev/null || echo "$now")
    if [ -f iap2-wifi-active ] && [ "$((now - retry))" -ge 25 ]; then
        rm -f iap2-wifi-failures
    fi
    exit 0
fi
retry=$(cat iap2-wifi-retry 2>/dev/null || echo 0)
[ "$now" -ge "$retry" ] || exit 0
failures=$(cat iap2-wifi-failures 2>/dev/null || echo 0)
if [ "$failures" -ge 3 ]; then
    touch phone-restart
    debug 'RECOVERY IAP2_WIFI repeated failure; receiver retry requested'
    exit 0
fi
echo "$((now + 5))" >iap2-wifi-retry
killall -TERM ARMiPhoneIAP2 2>/dev/null || true
sleep 1
if pidof ARMiPhoneIAP2 >/dev/null; then
    killall -KILL ARMiPhoneIAP2 2>/dev/null || true
    echo "$((failures + 1))" >iap2-wifi-failures
    debug 'RECOVERY IAP2_WIFI previous process did not terminate; retry deferred'
    exit 0
fi
# The receiver or cable mode may change while waiting for TERM.
[ "$(cat phone-generation 2>/dev/null || true)" = "$generation" ] || exit 0
[ "$(cat phone-mode 2>/dev/null || true)" = wireless ] || exit 0
[ ! -f phone-restart ] || exit 0
pidof AppleCarPlay >/dev/null || exit 0
fps=${YAMAHA_WIRELESS_FPS:-20}
case "$fps" in 15 | 20 | 30) ;; *) exit 1 ;; esac
mkdir -p handover-test
(
    /tmp/yamaha-sdl/receiver-native --phone-audio /usr/sbin/ARMiPhoneIAP2 640 360 "$fps" 2 2>&1 |
        debug_receiver iap2
) </dev/null &
echo "$((failures + 1))" >iap2-wifi-failures
touch iap2-wifi-active
rm -f iap2-wifi-request
debug 'STAGE IAP2_WIFI_STARTED medium=2 process_start_requested=1'
# A running process is not an authentication ACK. Reset retry budget only after
# sustained liveness; immediate repeated exits escalate through phone-restart.
