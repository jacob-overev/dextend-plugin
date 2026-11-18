#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Owns ci_hdrc.1 only; never stops the iPhone receiver.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
module=${YAMAHA_CCU_MODULE:-/tmp/g_android_accessory.ko}
state_path=${YAMAHA_CCU_STATE:-/sys/class/android_usb_accessory/android0/state}
prepare=${YAMAHA_CCU_PREPARE:-./prepare-aoa.sh}
attempt= child=
cleanup() {
    [ -z "$child" ] || kill "$child" 2>/dev/null || true
    rm -f ccu-preparing
}
trap cleanup EXIT
trap 'exit 0' INT TERM
[ ! -f ccu-preparing ] || touch ccu-recover
backoff=1
while [ -f /etc/yamaha-sdl/enabled ]; do
    if [ ! -f "$module" ] || [ ! -d /sys/bus/platform/drivers/ci_hdrc ]; then
        sleep 2
        continue
    fi
    state=$(cat "$state_path" 2>/dev/null || true)
    if [ -f ccu-recover ] || [ "$state" != CONFIGURED ]; then
        touch ccu-preparing
        # Wait for the bridge to release its fd before unloading the CCU module.
        count=0
        while [ "$(cat ccu-fd 2>/dev/null || true)" = open ] && [ "$count" -lt 15 ]; do
            sleep 1
            count=$((count + 1))
        done
        if [ "$count" -ge 15 ]; then
            debug 'RECOVERY CCU waiting for bridge to release device'
            sleep 5
            continue
        fi
        reset=0
        [ ! -f ccu-recover ] || reset=1
        # Consume request before work so a new request during work is retained.
        rm -f ccu-recover
        debug "ccu_prepare reset=$reset wait_seconds=$count"
        YAMAHA_AOA_RESET=$reset sh "$prepare" >/dev/null 2>&1 &
        child=$!
        if wait "$child"; then
            debug 'STAGE CCU_TRANSPORT_READY'
            backoff=1
        else
            debug "RECOVERY CCU prepare failed retry_seconds=$backoff"
            touch ccu-recover
        fi
        child=
        rm -f ccu-preparing
        sleep "$backoff"
        [ "$backoff" -ge 32 ] || backoff=$((backoff * 2))
        [ "$backoff" -le 32 ] || backoff=32
    else
        sleep 2
    fi
done
