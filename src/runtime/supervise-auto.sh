#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# One receiver family owns the phone. Keep the bridge and CCU alive on switches.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
child= mode= selected= retry=0 started=0 listen_at=0 bt_pid= attempt=0 candidate=0 missing=0
stop_receiver() {
    if [ -n "$child" ]; then
        kill -TERM "-$child" 2>/dev/null || true
        sleep 1
        kill -KILL "-$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
        child=
    fi
    killall -KILL AppleCarPlay ARMiPhoneIAP2 ARMAndroidAuto 2>/dev/null || true
}
trap stop_receiver EXIT
trap 'exit 0' INT TERM
rfcomm_peer() {
    link=$(readlink "$1" 2>/dev/null || true)
    case "$link" in /dev/rfcomm[0-9]*) ;; *) return 1 ;; esac
    node=${link#/dev/}
    case "$node" in *[!a-z0-9]*) return 1 ;; esac
    value=$(cat "/sys/class/tty/$node/address" 2>/dev/null || true)
    [ "${#value}" = 17 ] || return 1
    case "$value" in *[!0-9a-fA-F:]*) return 1 ;; esac
    printf '%s\n' "$value"
}
usb_kind() {
    [ "$(cat /sys/class/android_usb/android0/state 2>/dev/null || true)" != CONFIGURED ] || {
        echo carplay
        return
    }
    android=0
    for d in /sys/bus/usb/devices/1-*; do
        [ -f "$d/idVendor" ] || continue
        vendor=$(cat "$d/idVendor")
        product=$(cat "$d/idProduct")
        [ "$vendor" != 05ac ] || {
            echo carplay
            return
        }
        case "$vendor:$product" in 18d1:2d0[0-5]) android=1 ;; esac
        # MTP or ADB identifies a phone interface. Network adapters are ignored.
        for i in "$d"/*/bInterfaceClass; do
            [ -f "$i" ] || continue
            case "$(cat "$i")" in
                06) android=1 ;;
                ff) [ "$(cat "${i%/*}/bInterfaceSubClass" 2>/dev/null || true)" != 42 ] || android=1 ;;
            esac
        done
    done
    [ "$android" = 0 ] || echo aa-usb
}
# Select the active projection path from USB state and saved preferences.
select_mode() {
    stop_receiver
    mode=$1
    selected=$2
    rm -f phone-selected phone-state phone-restart phone-trigger iap2-wifi-request iap2-wifi-active \
        wireless-attempt wireless-retry wireless-acl-at wireless-good-since wireless-backoff
    printf '%s\n' "$mode" >phone-selection.new
    [ "$mode" != aa-wireless ] || printf '%s\n' "$selected" >>phone-selection.new
    mv phone-selection.new phone-selection
    started=$now
    missing=0
    retry=0
    debug "STAGE AUTO_SELECT platform=$mode"
}
while [ -f /etc/yamaha-sdl/enabled ]; do
    exec 8>&-
    sleep 1
    [ -S /var/run/adb-driver ] || continue
    read -r uptime rest </proc/uptime
    now=${uptime%%.*}
    pid=$(pidof bluetoothDaemon 2>/dev/null || true)
    if [ -z "$pid" ]; then
        rm -f /tmp/bluetoothdaemon_running
        bluetoothDaemon -n >/dev/null 2>&1 </dev/null &
        bt_pid=
        listen_at=0
    elif [ "$pid" != "$bt_pid" ]; then
        bt_pid=$pid
        listen_at=0
    fi
    # Serialize Bluetooth control with explicit forgetting in the panel.
    exec 8>phone-control.lock
    flock -n 8 || continue
    # Listen must run after the factory daemon is ready. Success is acceptance,
    # not a connected phone. Retry errors; never disturb an active session.
    if [ "$listen_at" = 0 ] || [ "$((now - listen_at))" -ge 30 ]; then
        if [ "$(cat phone-state 2>/dev/null || true)" != ready ] &&
            [ ! -e /tmp/rfcomm_IAP2 ] && [ ! -e /tmp/rfcomm_AAP ] &&
            [ ! -f iap2-wifi-request ] && [ ! -f iap2-wifi-active ] &&
            ! timeout 3 hcitool con 2>/dev/null | grep -q ACL; then
            debug 'bluetooth_listen_start'
            if timeout 8 ./bluetooth-autoconnect --listen >/dev/null 2>&1; then
                debug 'bluetooth_listen_accepted'
            else
                debug "bluetooth_listen_failed exit=$?"
            fi
            timeout 3 hciconfig hci0 piscan >/dev/null 2>&1 || true
            listen_at=$now
        fi
    fi
    aa_peer=$(rfcomm_peer /tmp/rfcomm_AAP || true)
    cp_peer=$(rfcomm_peer /tmp/rfcomm_IAP2 || true)
    usb=$(usb_kind)
    ready=$(cat phone-state 2>/dev/null || true)
    # A session is sticky. Priorities are for the next connection, not stealing
    # an active map. Bluetooth may vanish normally after Wi-Fi handover.
    if [ -z "$mode" ]; then select_mode carplay ''; fi
    if [ "$mode" = carplay ]; then
        if [ "$ready" != ready ]; then
            if [ "$usb" = aa-usb ]; then
                select_mode aa-usb ''
            elif [ -n "$aa_peer" ] && [ "$usb" != carplay ]; then
                choice=aa-wireless
                [ -z "$cp_peer" ] || choice=$(./phone-policy --choose "$aa_peer" "$cp_peer")
                [ "$choice" != aa-wireless ] || select_mode aa-wireless "$aa_peer"
            fi
        fi
    else
        if [ "$mode" = aa-wireless ] && [ -n "$aa_peer" ]; then
            missing=0
        elif [ "$mode" = aa-usb ] && [ "$usb" = aa-usb ]; then
            missing=0
        else
            [ "$missing" != 0 ] || missing=$now
            if [ "$ready" != ready ] && [ "$((now - missing))" -ge 5 ]; then select_mode carplay ''; fi
        fi
    fi
    if [ -n "$child" ] && ! kill -0 "$child" 2>/dev/null; then
        rc=0
        wait "$child" 2>/dev/null || rc=$?
        debug "auto_receiver_exit platform=$mode exit=$rc"
        child=
        retry=$((now + 3))
        if [ "$mode" != carplay ] && [ -z "$aa_peer" ] && [ "$usb" != aa-usb ]; then select_mode carplay ''; fi
    fi
    if [ "$(cat phone-selected 2>/dev/null || true)" = "$mode" ] && [ -z "$child" ] && [ "$now" -ge "$retry" ]; then
        if [ "$mode" = carplay ]; then
            setsid sh ./supervise-phone.sh 8>&- &
        else
            setsid ./receiver-native --android-auto 8>&- >/dev/null 2>&1 &
        fi
        child=$!
        started=$now
        rm -f phone-restart
        debug "auto_receiver_start platform=$mode"
    fi
    # A panel save requests one new AA negotiation. Ignore it in CarPlay.
    if [ -f aa-video-reload ]; then
        rm -f aa-video-reload
        if [ -n "$child" ] && [ "$mode" != carplay ] &&
            ! cmp -s aa-video-session /etc/yamaha-sdl/aa-video.conf; then
            : >phone-restart
        fi
    fi
    if [ -n "$child" ] && [ "$mode" != carplay ] && [ -f phone-restart ]; then
        debug "auto_receiver_retry platform=$mode"
        stop_receiver
        rm -f phone-restart
        retry=$((now + 2))
    fi
    # No invisible platform change based solely on a paused picture.
    [ "$ready" != ready ] && [ -z "$aa_peer" ] && [ -z "$cp_peer" ] && [ -z "$usb" ] || continue
    [ "$((now - started))" -ge 4 ] || continue
    [ "$((now - attempt))" -ge 10 ] || continue
    links=$(timeout 3 hcitool con 2>/dev/null || true)
    case "$links" in *ACL*) continue ;; *Connections:*) ;; *) continue ;; esac
    ./phone-policy --candidates >phone-candidates.new
    if ! cmp -s phone-candidates.new phone-candidates; then candidate=0; fi
    mv phone-candidates.new phone-candidates
    total=$(wc -l <phone-candidates)
    [ "$total" -gt 0 ] || continue
    candidate=$((candidate % total + 1))
    pair=$(sed -n "${candidate}p" phone-candidates)
    read -r peer service <<PAIR
$pair
PAIR
    attempt=$now
    # Arguments are validated again by the bounded D-Bus helper; never logged.
    debug "bluetooth_connect_attempt candidate=$candidate total=$total"
    if timeout 8 ./bluetooth-autoconnect --connect "$peer" "$service" >/dev/null 2>&1; then
        debug 'bluetooth_connect_accepted'
    else
        debug "bluetooth_connect_failed exit=$?"
    fi
done
