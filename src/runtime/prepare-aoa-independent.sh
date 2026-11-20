#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Experimental source-built AOA transport, selected explicitly by boot-live.sh.
# Owns only ci_hdrc.1. All module and node changes are RAM-only.
set -eu
cd /tmp/yamaha-sdl
diag() { [ ! -f /tmp/dextend-service/diagnostics.sh ] || sh /tmp/dextend-service/diagnostics.sh event aoa "$@" || true; }
diag prepare_start
trap 'rc=$?; diag "prepare_exit rc=$rc"' EXIT
fail() {
    diag "$*"
    echo "AOA_INDEPENDENT ERROR: $*" >&2
    exit 1
}
[ -f AOA.sha256 ] || fail MISSING_MODULE_MANIFEST
sha256sum -c AOA.sha256 >/dev/null || fail MODULE_HASH_MISMATCH
driver=/sys/bus/platform/drivers/ci_hdrc
if [ -d /sys/module/yamaha_aoa ] && [ "${YAMAHA_AOA_RESET:-0}" = 1 ]; then
    rmmod yamaha_aoa
    [ ! -d /sys/module/yamaha_aoa ] || fail MODULE_IN_USE
fi
if [ ! -d /sys/module/yamaha_aoa ]; then
    # An incompatible module cannot become loadable by retrying this boot.
    [ ! -f aoa-load-error ] || fail AOA_MODULE_LOAD_FAILED
    # Same vendor worker stop used by the accepted transport; the iPhone
    # controller, network interfaces and pairing stores remain untouched.
    killall -STOP ARMadb-driver 2>/dev/null || true
    for pid in $(pidof ARMadb-driver 2>/dev/null || true); do
        parent=$(awk '/^PPid:/ {print $2}' "/proc/$pid/status")
        [ "$parent" = 1 ] || kill -KILL "$pid" 2>/dev/null || true
    done
    usb=/sys/class/android_usb_accessory/android0
    previous_enable=$(cat "$usb/enable" 2>/dev/null || true)
    restore_vendor=0
    [ ! -d /sys/module/g_android_accessory ] || restore_vendor=1
    [ ! -e "$usb/enable" ] || echo 0 >"$usb/enable"
    [ ! -e "$driver/ci_hdrc.1" ] || echo ci_hdrc.1 >"$driver/unbind"
    if [ -d /sys/module/g_android_accessory ]; then rmmod g_android_accessory; fi
    [ ! -d /sys/module/g_android_accessory ] || fail VENDOR_MODULE_IN_USE
    [ -e "$driver/ci_hdrc.1" ] || echo ci_hdrc.1 >"$driver/bind"
    diag loading_module
    if ! insmod ./yamaha_aoa.ko experimental=1 2>aoa-insmod.log; then
        diag "module load: $(head -c 256 aoa-insmod.log)"
        # Reuse the OEM module staged by the factory startup.
        if [ "$restore_vendor" = 1 ]; then
            if ! insmod /tmp/g_android_accessory.ko; then
                echo OEM_MODULE_RESTORE_FAILED >aoa-load-error
                fail OEM_MODULE_RESTORE_FAILED
            fi
            case "$previous_enable" in 0 | 1)
                [ ! -e "$usb/enable" ] || echo "$previous_enable" >"$usb/enable" ;;
            esac
        fi
        echo AOA_MODULE_LOAD_FAILED >aoa-load-error
        fail AOA_MODULE_LOAD_FAILED
    fi
    diag module_loaded
    [ -d /sys/module/yamaha_aoa ] || fail MODULE_NOT_LOADED
fi
if [ ! -e /dev/yamaha_aoa ]; then
    dev=$(cat /sys/class/misc/yamaha_aoa/dev)
    mknod /dev/yamaha_aoa c "${dev%:*}" "${dev#*:}"
    chmod 600 /dev/yamaha_aoa
fi
# An unplugged CCU needs only to reconnect; do not churn the module while idle.
count=0
while [ "$count" -lt 45 ]; do
    state=$(cat /sys/class/misc/yamaha_aoa/state)
    if [ "$state" = CONFIGURED ]; then
        echo 'AOA_INDEPENDENT READY'
        exit 0
    fi
    sleep 1
    count=$((count + 1))
done
fail NO_CCU_CONFIGURATION_WITHIN_45_SECONDS
