#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# One serialized wireless recovery tick, called only when wired USB is absent.
# Factory pairing/profile protocol is reused; retry policy is owned here.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
unset LD_PRELOAD
fps=${YAMAHA_WIRELESS_FPS:-20}
case "$fps" in
    15 | 20 | 30) ;;
    *)
        debug 'ERROR WIRELESS invalid YAMAHA_WIRELESS_FPS (expected 15, 20 or 30)'
        exit 1
        ;;
esac
bt_retry=${YAMAHA_BT_RETRY_SECONDS:-5}
case "$bt_retry" in
    5 | 10 | 30) ;;
    *)
        debug 'ERROR WIRELESS invalid YAMAHA_BT_RETRY_SECONDS (expected 5, 10 or 30)'
        exit 1
        ;;
esac
bt_control_failed() {
    failures=$(cat wireless-bt-failures 2>/dev/null || echo 0)
    failures=$((failures + 1))
    echo "$failures" >wireless-bt-failures
    if [ "$failures" -ge 3 ]; then
        killall -KILL bluetoothDaemon 2>/dev/null || true
        rm -f wireless-bt-failures
        debug 'RECOVERY BLUETOOTH repeated control failures; daemon restart requested'
    fi
}
set --
case "${YAMAHA_CARPLAY_SCREEN_MODE:-}" in
    '') ;;
    userInitiated,anytime) set -- --modes screen=userInitiated,anytime ;;
    *)
        debug 'ERROR WIRELESS invalid YAMAHA_CARPLAY_SCREEN_MODE'
        exit 1
        ;;
esac
read -r uptime rest </proc/uptime
now=${uptime%%.*}
sh ./iap2-wifi-test-step.sh
ready=$(cat phone-state 2>/dev/null || true)
# Bluetooth/iAP2 may disappear normally after the Wi-Fi handover.
if pidof AppleCarPlay >/dev/null && [ "$ready" = ready ] && [ ! -f phone-restart ]; then
    good_since=$(cat wireless-good-since 2>/dev/null || echo "$now")
    echo "$good_since" >wireless-good-since
    if [ "$((now - good_since))" -ge 30 ]; then
        rm -f wireless-backoff wireless-recovery-count
    fi
    rm -f phone-trigger wireless-attempt wireless-retry wireless-acl-at wireless-bt-failures
    exit 0
fi
rm -f wireless-good-since
forced=0
retry=$(cat wireless-retry 2>/dev/null || echo 0)
last=$(cat wireless-trigger-at 2>/dev/null || echo 0)
if [ -f phone-trigger ] && [ "$((now - last))" -ge 5 ]; then
    echo "$now" >wireless-trigger-at
    retry=0
    forced=1
fi
[ "$now" -ge "$retry" ] || exit 0
rm -f phone-trigger

# Repair missing services only. Never cycle a healthy AP: SSH can use it too.
[ -e /sys/class/net/wlan0 ] || {
    debug 'RECOVERY WIRELESS wlan0 unavailable'
    echo "$((now + 5))" >wireless-retry
    exit 0
}
[ -e /sys/class/bluetooth/hci0 ] || {
    debug 'RECOVERY WIRELESS hci0 unavailable'
    echo "$((now + 5))" >wireless-retry
    exit 0
}
if ! pidof hostapd >/dev/null; then
    timeout 10 hostapd /etc/hostapd.conf -B >/dev/null 2>&1 || true
    debug 'RECOVERY WIRELESS restarted missing AP service'
fi
pidof udhcpd >/dev/null || udhcpd >/dev/null 2>&1 || true
pidof mdnsd >/dev/null || mdnsd >/dev/null 2>&1 || true
if ! pidof bluetoothDaemon >/dev/null; then
    rm -f /tmp/bluetoothdaemon_running
    bluetoothDaemon -n >/dev/null 2>&1 </dev/null &
    debug 'RECOVERY WIRELESS restarted missing Bluetooth service'
fi
exposure=$(cat wireless-exposure-at 2>/dev/null || echo 0)
if [ "$((now - exposure))" -ge 15 ] && [ ! -e /tmp/rfcomm_IAP2 ] &&
    [ ! -f iap2-wifi-request ] && [ ! -f iap2-wifi-active ] &&
    ! pidof ARMiPhoneIAP2 >/dev/null; then
    if timeout 3 hciconfig hci0 up >/dev/null 2>&1 && timeout 3 hciconfig hci0 piscan >/dev/null 2>&1; then
        debug 'STAGE WIRELESS_DISCOVERABLE'
    else
        debug 'RECOVERY WIRELESS Bluetooth discovery refresh failed'
    fi
    echo "$now" >wireless-exposure-at
fi
attempt=$(cat wireless-attempt 2>/dev/null || echo 0)
restart=$forced
[ ! -f phone-restart ] || restart=1
if [ "$attempt" != 0 ] && [ "$((now - attempt))" -ge 45 ]; then
    debug 'RECOVERY WIRELESS negotiation timed out'
    restart=1
fi
if [ "$restart" = 1 ]; then
    if [ "${YAMAHA_PHONE_AUTO:-0}" != 1 ] && links=$(timeout 3 hcitool con 2>/dev/null); then
        printf '%s\n' "$links" | awk '/ACL/ {print $3}' | while IFS= read -r peer; do
            case "$peer" in *[!0-9A-Fa-f:]* | '') continue ;; esac
            [ "${#peer}" = 17 ] || continue
            timeout 3 hcitool dc "$peer" >/dev/null 2>&1 || true
        done
    fi
    debug 'RECOVERY BLUETOOTH stale transport release attempted'
    recoveries=$(cat wireless-recovery-count 2>/dev/null || echo 0)
    recoveries=$((recoveries + 1))
    # Repeated receiver retries can leave a stale Bluetooth transport behind.
    # This is an escalation step, not a total retry limit. Keep bonds and AP.
    if [ "$recoveries" -ge 3 ] && [ "${YAMAHA_PHONE_AUTO:-0}" != 1 ]; then
        killall -KILL bluetoothDaemon 2>/dev/null || true
        recoveries=0
        debug 'RECOVERY WIRELESS escalation=bluetooth_daemon; pairing history preserved'
    fi
    echo "$recoveries" >wireless-recovery-count
    killall -KILL AppleCarPlay ARMiPhoneIAP2 2>/dev/null || true
    rm -f phone-state phone-restart wireless-attempt wireless-acl-at iap2-wifi-request iap2-wifi-active iap2-wifi-retry iap2-wifi-failures
    backoff=$(cat wireless-backoff 2>/dev/null || echo 1)
    delay=$backoff
    [ "$forced" = 0 ] || delay=1
    echo "$((now + delay))" >wireless-retry
    [ "$backoff" -ge 32 ] || backoff=$((backoff * 2))
    [ "$backoff" -le 32 ] || backoff=32
    echo "$backoff" >wireless-backoff
    debug 'RECOVERY WIRELESS receiver reset; SDL preserved'
    exit 0
fi
# In automatic mode only the scheduled phone may open Bluetooth iAP2.
# Wi-Fi handover and the active AirPlay session continue independently.
priority_iap2_allowed() {
    [ "${YAMAHA_PHONE_AUTO:-0}" = 1 ] || return 0
    allowed=$(cat priority-carplay 2>/dev/null || echo pending)
    # A grant is the permitted address plus a unique attempt ID. Outside a
    # granted turn the supervisor can still discover a new phone via RFCOMM.
    [ "$allowed" != any ] || return 1
    node=$(readlink /tmp/rfcomm_IAP2 2>/dev/null) || return 1
    case "$node" in /dev/rfcomm[0-9]*) ;; *) return 1 ;; esac
    [ "$(tr a-f A-F <"/sys/class/tty/${node##*/}/address" 2>/dev/null)" = "${allowed%% *}" ]
}
# Record the actual child status before the log filter consumes the pipeline.
run_receiver() {
    family=$1
    shift
    rc=0
    /tmp/yamaha-sdl/receiver-native --phone-audio "$@" || rc=$?
    if [ "$family" = iap2 ] && [ "${YAMAHA_PHONE_AUTO:-0}" = 1 ] &&
        { [ "$rc" = 0 ] || [ "$rc" = 141 ]; } && [ -n "${allowed:-}" ] &&
        [ "$(cat priority-carplay 2>/dev/null || true)" = "$allowed" ]; then
        printf '%s\n' "$allowed" >priority-iap2-ended.new
        mv -f priority-iap2-ended.new priority-iap2-ended
    fi
    debug "wireless_process_exit receiver=$family exit=$rc"
}
if ! pidof AppleCarPlay >/dev/null; then
    # Same competing receiver guard as the wired launcher.
    for p in $(ps | awk '/phone_link_deamon.sh HiCar start/ && !/awk/ {print $1}'); do
        kill -STOP "$p"
    done
    killall ARMHiCar 2>/dev/null || true
    # A local receiver replacement also removes its iAP2 helper. Give the
    # same open BT channel one continuation within its original turn.
    if [ "${YAMAHA_PHONE_AUTO:-0}" = 1 ] && [ "$ready" != ready ] &&
        [ "$attempt" != 0 ] && [ ! -f iap2-wifi-request ] && [ ! -f iap2-wifi-active ] &&
        priority_iap2_allowed && [ "$(cat priority-iap2-started 2>/dev/null || true)" = "$allowed" ] &&
        [ "$(cat priority-iap2-failed 2>/dev/null || true)" != "$allowed" ] &&
        [ "$(cat priority-iap2-rearmed 2>/dev/null || true)" != "$allowed" ]; then
        printf '%s\n' "$allowed" >priority-iap2-rearmed
        rm -f priority-iap2-started priority-iap2-ended
        debug 'priority_iap2_resume reason=receiver_replaced'
    fi
    # A Wi-Fi iAP2 process belongs to the old receiver. Leaving it alive
    # suppresses the Bluetooth iAP2 start below after a disconnected session.
    killall -KILL ARMiPhoneIAP2 2>/dev/null || true
    rm -f phone-state wireless-attempt iap2-wifi-request iap2-wifi-active iap2-wifi-retry iap2-wifi-failures
    attempt=0
    (
        run_receiver carplay /usr/sbin/AppleCarPlay --width 640 --height 360 --fps "$fps" --wireless "$@" 2>&1 |
            debug_receiver carplay
    ) </dev/null &
    echo "$now" >wireless-receiver-at
    debug "STAGE WIRELESS_RECEIVER_STARTED fps=$fps"
fi
# Transport 1 is the firmware Bluetooth iAP2 medium (/tmp/rfcomm_IAP2).
# A Wi-Fi station alone is not evidence of a phone; it may be the SSH host.
if [ ! -f iap2-wifi-active ] && [ ! -f iap2-wifi-request ] && [ -e /tmp/rfcomm_IAP2 ] && ! pidof ARMiPhoneIAP2 >/dev/null && priority_iap2_allowed; then
    if [ "${YAMAHA_PHONE_AUTO:-0}" = 1 ]; then
        if [ "$(cat priority-iap2-started 2>/dev/null || true)" = "$allowed" ]; then
            # The child exited before handover with the same BT link still
            # present. Let the supervisor schedule the next attempt.
            printf '%s\n' "$allowed" >priority-iap2-failed.new
            mv -f priority-iap2-failed.new priority-iap2-failed
            exit 0
        fi
        if [ "$(cat priority-iap2-rearmed 2>/dev/null || true)" = "$allowed" ] &&
            ! pidof AppleCarPlay >/dev/null; then
            exit 0
        fi
        printf '%s\n' "$allowed" >priority-iap2-started
    fi
    if [ "$attempt" = 0 ]; then echo "$now" >wireless-attempt; fi
    (
        run_receiver iap2 /usr/sbin/ARMiPhoneIAP2 640 360 "$fps" 1 2>&1 |
            debug_receiver iap2
    ) </dev/null &
    debug "STAGE WIRELESS_IAP2_STARTED fps=$fps"
fi

# Replace the stopped vendor controller's verified no-argument AutoConnect call.
# Start the receiver first; do not initiate pairing before its startup settles.
receiver_at=$(cat wireless-receiver-at 2>/dev/null || echo 0)
if [ ! -f manual-pairing ] && [ "${YAMAHA_BT_AUTOCONNECT:-1}" = 1 ] && [ ! -e /tmp/rfcomm_IAP2 ] &&
    [ "$receiver_at" != 0 ] && [ "$((now - receiver_at))" -ge 4 ]; then
    bt_at=$(cat bluetooth-autoconnect-at 2>/dev/null || echo 0)
    if [ "$bt_at" = 0 ] || [ "$((now - bt_at))" -ge "$bt_retry" ]; then
        echo "$now" >bluetooth-autoconnect-at
        # RFCOMM appears after pairing. Do not race an existing ACL/SSP
        # connection by initiating another automatic attempt in that gap.
        if links=$(timeout 3 hcitool con 2>/dev/null); then
            case "$links" in
                *Connections:*) ;;
                *)
                    bt_control_failed
                    debug 'RECOVERY BLUETOOTH link status unavailable; AutoConnect deferred'
                    exit 0
                    ;;
            esac
            if printf '%s\n' "$links" | awk '/ACL/ {found=1} END {exit !found}'; then
                acl_at=$(cat wireless-acl-at 2>/dev/null || echo "$now")
                echo "$acl_at" >wireless-acl-at
                if [ "$((now - acl_at))" -ge 45 ]; then
                    # Target only this phone's stale ACL. Do not cycle the AP.
                    # Addresses are passed as arguments and never logged.
                    printf '%s\n' "$links" | awk '/ACL/ {print $3}' | while IFS= read -r peer; do
                        case "$peer" in *[!0-9A-Fa-f:]* | '') continue ;; esac
                        [ "${#peer}" = 17 ] || continue
                        timeout 3 hcitool dc "$peer" >/dev/null 2>&1 || true
                    done
                    touch phone-restart
                    rm -f wireless-acl-at
                    debug 'RECOVERY BLUETOOTH stalled ACL negotiation; receiver retry requested'
                else
                    debug 'STAGE BLUETOOTH_AUTOCONNECT_DEFERRED active_acl=1'
                fi
                exit 0
            fi
        else
            bt_control_failed
            debug 'RECOVERY BLUETOOTH link status unavailable; AutoConnect deferred'
            exit 0
        fi
        rm -f wireless-acl-at
        debug "STAGE BLUETOOTH_AUTOCONNECT_ATTEMPT uptime=$now retry_seconds=$bt_retry"
        if [ -x ./bluetooth-autoconnect ] && timeout 10 ./bluetooth-autoconnect; then
            rm -f wireless-bt-failures
        else
            bt_control_failed
            debug 'RECOVERY BLUETOOTH AutoConnect request failed'
        fi
    fi
fi
