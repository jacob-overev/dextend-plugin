#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Phone-side USB and receiver recovery never depend on CCU/HMI readiness.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
backoff=1
retry_at=0
started=0
last_trigger=0
good_since=0
child=
trap '[ -z "$child" ] || kill "$child" 2>/dev/null || true' EXIT
trap 'exit 0' INT TERM
while [ -f /etc/yamaha-sdl/enabled ]; do
    if [ "${YAMAHA_PHONE_AUTO:-0}" != 1 ] || ! ./receiver-native --wait-carplay; then
        sleep 2
    fi
    [ -S "${YAMAHA_CARPLAY_SOCKET:-/tmp/yamaha-sdl/carplay-ipc.sock}" ] || continue
    read -r uptime rest </proc/uptime
    now=${uptime%%.*}
    state=$(cat /sys/class/android_usb/android0/state 2>/dev/null || true)
    phone=0
    for device in /sys/bus/usb/devices/1-*; do
        [ -f "$device/idVendor" ] || continue
        [ "$(cat "$device/idVendor")" != 05ac ] || phone=1
    done
    if [ "$state" != CONFIGURED ] && [ "$phone" = 0 ]; then
        if [ "$started" != 0 ]; then
            killall -KILL AppleCarPlay ARMiPhoneIAP2 2>/dev/null || true
            rm -f phone-state iap2-wifi-request iap2-wifi-active iap2-wifi-retry iap2-wifi-failures
            debug 'STAGE PHONE_ABSENT'
        fi
        started=0
        retry_at=0
        backoff=1
        good_since=0
        if [ "${YAMAHA_WIRELESS:-1}" = 1 ]; then
            echo wireless >phone-mode
            sh ./wireless-step.sh &
            child=$!
            wait "$child" || debug 'RECOVERY WIRELESS tick failed'
            child=
        fi
        continue
    fi
    if [ "$(cat phone-mode 2>/dev/null || true)" = wireless ]; then
        killall -KILL AppleCarPlay ARMiPhoneIAP2 2>/dev/null || true
        rm -f phone-state wireless-attempt wireless-retry wireless-backoff wireless-acl-at wireless-good-since wireless-recovery-count wireless-bt-failures iap2-wifi-request iap2-wifi-active iap2-wifi-retry iap2-wifi-failures
    fi
    echo wired >phone-mode
    ready=$(cat phone-state 2>/dev/null || true)
    restart=0
    pidof AppleCarPlay >/dev/null || restart=1
    pidof ARMiPhoneIAP2 >/dev/null || restart=1
    [ "$phone" = 0 ] || restart=1
    [ ! -f phone-restart ] || restart=1
    if [ "$ready" = ready ] && [ "$restart" = 0 ]; then
        rm -f phone-trigger
        [ "$good_since" != 0 ] || good_since=$now
        [ "$((now - good_since))" -lt 30 ] || backoff=1
        started=$now
        continue
    fi
    good_since=0
    if [ "$started" != 0 ] && [ "$((now - started))" -ge 30 ]; then
        debug 'RECOVERY PHONE session setup timed out'
        restart=1
    fi
    # A navigation-button trigger can shorten backoff for an unhealthy session.
    # Attempts remain serialized, with a five-second guard against repeated input.
    trigger=0
    if [ -f phone-trigger ] && [ "$((now - last_trigger))" -ge 5 ]; then
        trigger=1
        restart=1
    fi
    [ "$restart" = 1 ] || continue
    if [ "$trigger" = 1 ]; then
        last_trigger=$now
        debug 'RECOVERY PHONE navigation trigger'
    else
        [ "$now" -ge "$retry_at" ] || continue
    fi
    rm -f phone-restart phone-trigger phone-state
    killall -KILL AppleCarPlay ARMiPhoneIAP2 2>/dev/null || true
    # Reset phone gadget as well as processes to renegotiate CarPlay cleanly.
    debug "wired_receiver_start trigger=$trigger"
    sh ./restart-live-carplay.sh >/dev/null 2>&1 &
    child=$!
    if wait "$child"; then
        debug 'STAGE PHONE_RECEIVERS_STARTED'
    else
        debug "RECOVERY PHONE start failed retry_seconds=$backoff"
    fi
    child=
    read -r uptime rest </proc/uptime
    started=${uptime%%.*}
    retry_at=$((started + backoff))
    [ "$backoff" -ge 32 ] || backoff=$((backoff * 2))
    [ "$backoff" -le 32 ] || backoff=32
done
