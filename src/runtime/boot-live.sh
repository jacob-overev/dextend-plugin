#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Persistent IPC bridge plus independent CCU and phone recovery workers.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
# Persist the default in the package; SSH environment does not survive reboot.
wireless_default=1
[ ! -f /etc/yamaha-sdl/wireless-disabled ] || wireless_default=0
export YAMAHA_WIRELESS=${YAMAHA_WIRELESS:-$wireless_default}
export YAMAHA_IAP2_WIFI_ROUTER_TEST=${YAMAHA_IAP2_WIFI_ROUTER_TEST:-1}
# Confirmed on CCU: prepare the phone before switching and refresh after 500 ms.
export YAMAHA_SMOOTH_TRANSITIONS=${YAMAHA_SMOOTH_TRANSITIONS:-1}
export YAMAHA_FAST_STARTUP_REFRESH=${YAMAHA_FAST_STARTUP_REFRESH:-1}
export YAMAHA_VIDEO_ACK_GUARD=${YAMAHA_VIDEO_ACK_GUARD:-1}
export YAMAHA_STABLE_H264_LEVEL=${YAMAHA_STABLE_H264_LEVEL:-1}
export YAMAHA_WIRELESS_VIDEO_WATCHDOG=${YAMAHA_WIRELESS_VIDEO_WATCHDOG:-1}
export YAMAHA_RUNTIME=/tmp/yamaha-sdl
export YAMAHA_USB_DEBUG_LOGGING=1
case "${YAMAHA_AOA_DRIVER:-vendor}" in
    vendor)
        export YAMAHA_CCU_DEVICE=${YAMAHA_CCU_DEVICE:-/dev/usb_accessory}
        export YAMAHA_CCU_STATE=${YAMAHA_CCU_STATE:-/sys/class/android_usb_accessory/android0/state}
        export YAMAHA_CCU_MODULE=${YAMAHA_CCU_MODULE:-/tmp/g_android_accessory.ko}
        export YAMAHA_CCU_PREPARE=${YAMAHA_CCU_PREPARE:-./prepare-aoa.sh}
        ;;
    independent)
        export YAMAHA_CCU_DEVICE=${YAMAHA_CCU_DEVICE:-/dev/yamaha_aoa}
        export YAMAHA_CCU_STATE=${YAMAHA_CCU_STATE:-/sys/class/misc/yamaha_aoa/state}
        export YAMAHA_CCU_MODULE=${YAMAHA_CCU_MODULE:-/tmp/yamaha-sdl/yamaha_aoa.ko}
        export YAMAHA_CCU_PREPARE=${YAMAHA_CCU_PREPARE:-./prepare-aoa-independent.sh}
        ;;
    *)
        debug 'ERROR: unknown AOA driver selection' >&2
        exit 1
        ;;
esac
phone_supervisor=./supervise-phone.sh
if [ "${YAMAHA_PHONE_AUTO:-0}" = 1 ]; then
    phone_supervisor=./supervise-auto.sh
    export YAMAHA_BT_AUTOCONNECT=0
    export YAMAHA_INPLACE_TRANSITIONS=0
fi
if [ -n "${YAMAHA_AA_MODE:-}" ]; then
    [ "${YAMAHA_AOA_DRIVER:-}" = independent ] && [ "${YAMAHA_CARPLAY_SOCKET:-}" = /var/run/adb-driver ] || exit 2
    phone_supervisor=./supervise-aa.sh
    export YAMAHA_IAP2_WIFI_ROUTER_TEST=0 YAMAHA_WIRELESS_VIDEO_WATCHDOG=0
    export YAMAHA_INPLACE_TRANSITIONS=0 YAMAHA_FAST_STARTUP_REFRESH=0
fi
waiting_default=/tmp/yamaha-sdl/waiting.h264
[ "${YAMAHA_INPLACE_TRANSITIONS:-0}" != 1 ] || waiting_default=/tmp/yamaha-sdl/waiting-inplace.frames
# PID lock survives stale files after a killed supervisor, without duplicate owners.
if [ -f boot.pid ] && kill -0 "$(cat boot.pid)" 2>/dev/null; then exit 0; fi
echo $$ >boot.pid
bridge= ccu_worker= phone_worker=
cleanup() {
    rc=$?
    debug "runtime_exit rc=$rc"
    trap - EXIT INT TERM
    for p in "$ccu_worker" "$phone_worker" "$bridge"; do
        [ -z "$p" ] || kill "$p" 2>/dev/null || true
    done
    killall -KILL AppleCarPlay ARMiPhoneIAP2 ARMAndroidAuto 2>/dev/null || true
    wait 2>/dev/null || true
    if [ -f no_touch.saved ] && [ ! -e /tmp/no_touch ]; then mv no_touch.saved /tmp/no_touch; fi
    rm -f boot.pid
}
trap cleanup EXIT
trap 'exit 0' INT TERM
debug "runtime_start wireless=$YAMAHA_WIRELESS supervisor=${phone_supervisor##*/}"
if [ "${YAMAHA_PHONE_AUTO:-0}" = 1 ]; then
    if sh ./prepare-auto-radio.sh; then
        debug auto_radio_ready
    else
        rc=$?
        debug "auto_radio_failed rc=$rc"
        exit "$rc"
    fi
fi
# Allow factory USB/radio initialization; neither worker waits for the other link.
sleep "${YAMAHA_INIT_DELAY:-20}"
if [ -z "${YAMAHA_WAITING_FRAME:-}" ] && [ "$waiting_default" = "$YAMAHA_RUNTIME/waiting.h264" ] &&
    [ -x ./waiting-frame ]; then
    firmware=
    if [ -r /etc/software_version ]; then
        read -r firmware </etc/software_version || true
    fi
    if [ "$firmware" = 2025.10.15.1127 ] && [ -s waiting-2025.10.15.1127.h264 ]; then
        waiting_default=$YAMAHA_RUNTIME/waiting-2025.10.15.1127.h264
    else
        revision=$(timeout 2 /usr/sbin/riddleBoxCfg -g hardwareVer 2>/dev/null) || revision=
        case "$revision" in *[A-Za-z]*[0-9]*) ;; *) revision= ;; esac
        if ./waiting-frame waiting.h264 waiting-strip.bin waiting-font.bin \
            "${revision:--}" "${firmware:--}" "$(cat waiting-version)" >waiting-live.h264.tmp &&
            mv -f waiting-live.h264.tmp waiting-live.h264; then
            waiting_default=$YAMAHA_RUNTIME/waiting-live.h264
        else
            rm -f waiting-live.h264.tmp
            debug 'WAITING using packaged frame'
        fi
    fi
fi
export YAMAHA_WAITING_FRAME=${YAMAHA_WAITING_FRAME:-$waiting_default}
touch ccu-recover
sh ./supervise-ccu.sh &
ccu_worker=$!
sh "$phone_supervisor" &
phone_worker=$!
while [ -f /etc/yamaha-sdl/enabled ]; do
    rm -f bridge-heartbeat phone-state iap2-wifi-request iap2-wifi-active iap2-wifi-retry iap2-wifi-failures
    rm -f phone-selected
    [ "$phone_supervisor" = ./supervise-phone.sh ] || touch phone-restart
    debug 'bridge_start'
    ./yamaha-sdl-live "$YAMAHA_CCU_DEVICE" --live usb-debug/bridge.log 0 &
    bridge=$!
    [ "$phone_supervisor" != ./supervise-phone.sh ] || touch phone-restart
    read -r uptime rest </proc/uptime
    bridge_started=${uptime%%.*}
    while kill -0 "$bridge" 2>/dev/null && [ -f /etc/yamaha-sdl/enabled ]; do
        sleep 2
        read -r uptime rest </proc/uptime
        now=${uptime%%.*}
        beat=$(cat bridge-heartbeat 2>/dev/null || true)
        case "$beat" in '' | *[!0-9]*) beat=$bridge_started ;; esac
        if [ "$((now - beat))" -gt 10 ]; then
            debug 'RECOVERY bridge watchdog expired'
            kill -KILL "$bridge" 2>/dev/null || true
        fi
        if ! kill -0 "$ccu_worker" 2>/dev/null; then
            debug 'ccu_worker_restart'
            sh ./supervise-ccu.sh &
            ccu_worker=$!
        fi
        if ! kill -0 "$phone_worker" 2>/dev/null; then
            debug 'phone_worker_restart'
            sh "$phone_supervisor" &
            phone_worker=$!
        fi
    done
    kill "$bridge" 2>/dev/null || true
    wait "$bridge" 2>/dev/null || true
    bridge=
    debug 'bridge_stopped; request_ccu_recovery'
    echo closed >ccu-fd
    touch ccu-recover
    sleep 2
done
