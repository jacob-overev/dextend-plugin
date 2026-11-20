#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Switch phone receivers while keeping the CCU bridge alive.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
child= mode= selected= retry=0 next_listen=0 bt_pid=
candidate=0 last_peer= peer= service= deadline=0 negotiating=0 was_ready=0 next_slot=0
last_cp= last_aa= incoming_cp= incoming_aa= grant= generation=0
handover_due=0 last_woken=
acl_before=skip android_grace=0
mkdir -p carplay-wakeup || true
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
    printf '%s\n' "$value" | tr a-f A-F
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
    retry=0
    debug "STAGE AUTO_SELECT platform=$mode"
}
# The CarPlay worker also listens for incoming iAP2. Publish its permitted
# peer before starting a slot so a stale link cannot steal another turn.
allow_carplay() {
    printf '%s\n' "$1" >priority-carplay.new
    mv -f priority-carplay.new priority-carplay
}
clear_slot() {
    peer= service= negotiating=0 deadline=0 grant= android_grace=0
    allow_carplay pending
}
start_slot() {
    ./phone-policy --candidates >phone-candidates.new || return 0
    # Append live peers missing from the OEM service cache.
    for entry in "$cp_peer IAP2" "$aa_peer AAP"; do
        case "$entry" in ' '*) continue ;; esac
        # One turn per handset, even if it exposes both profiles.
        grep -q "^${entry% *} " phone-candidates.new || printf '%s\n' "$entry" >>phone-candidates.new
    done
    total=$(wc -l <phone-candidates.new)
    if ! cmp -s phone-candidates.new phone-candidates; then
        mv -f phone-candidates.new phone-candidates
        # Keep our place if a later candidate appeared or disappeared.
        candidate=$(awk -v addr="$last_peer" '$1==addr {print NR; exit}' phone-candidates)
        candidate=${candidate:-0}
    fi
    [ "$total" -gt 0 ] && [ ! -f manual-pairing ] || { allow_carplay any; return 0; }
    checked=0
    index=$candidate
    while [ "$checked" -lt "$total" ]; do
        index=$((index % total + 1))
        checked=$((checked + 1))
        pair=$(sed -n "${index}p" phone-candidates)
        address=${pair% *}
        if [ -f "priority-retry-$address" ] &&
            read -r failures until_time <"priority-retry-$address" && [ "$now" -lt "$until_time" ]; then
            [ "$until_time" -ge "$next_slot" ] || next_slot=$until_time
            continue
        fi
        candidate=$index
        last_peer=$address
        profile=${pair##* }
        if [ "$profile" = AUTO ]; then
            if [ "$address" = "$cp_peer" ]; then profile=IAP2
            elif [ "$address" = "$aa_peer" ]; then profile=AAP; fi
        fi
        begin_slot "$address" "$profile" "$candidate"
        debug "priority_attempt candidate=$candidate total=$total service=$service"
        break
    done
    [ -n "$peer" ] || return 0
    if { [ "$service" = IAP2 ] && [ "$peer" = "$cp_peer" ]; } ||
        { [ "$service" = AAP ] && [ "$peer" = "$aa_peer" ]; }; then
        return 0
    fi
    # Keep the destination fixed. Let the OEM worker discover the iPhone
    # service as it does when resuming a saved phone. AAP has a known profile.
    profile=AUTO
    if [ "$service" = AAP ]; then
        profile=AAP
        acl_before=$(peer_acl_handle) || acl_before=skip
    fi
    if timeout 8 ./bluetooth-autoconnect --connect "$peer" "$profile" >/dev/null 2>&1; then
        debug "bluetooth_connect_accepted service=$service"
    else
        rc=$?
        debug "bluetooth_connect_failed service=$service exit=$rc"
        # If the method was sent but its reply was lost, keep listening
        # for this phone until the original deadline.
        case "$rc" in 2|3|4|5) finish_slot request_failed ;; esac
    fi
}
begin_slot() {
    peer=$1 service=$2 slot_label=$3 negotiating=0 handover_due=0
    acl_before=skip android_grace=0
    generation=$((generation + 1))
    grant="$peer $$-$generation"
    if [ "$service" = IAP2 ]; then allow_carplay "$grant"; else allow_carplay pending; fi
    deadline=$((now + 10))
    next_slot=$deadline
}
peer_acl_handle() {
    links=$(timeout 3 hcitool con 2>/dev/null) || return 1
    printf '%s\n' "$links" | awk -v peer="$peer" '$2=="ACL" && toupper($3)==peer {
        print ($4=="handle" && $5 ~ /^[0-9]+$/) ? $5 : "present"; exit
    }'
}
extend_android_slot() {
    [ "$service" = AAP ] && [ "$negotiating" = 0 ] && [ "$android_grace" = 0 ] &&
        [ "$acl_before" != skip ] && [ "$now" -lt "$((deadline + 5))" ] || return 1
    acl_now=$(peer_acl_handle) || return 1
    [ -n "$acl_now" ] && [ "$acl_now" != "$acl_before" ] || return 1
    # A fresh Bluetooth link to this phone can precede its AAP channel.
    android_grace=1
    deadline=$((deadline + 5))
    debug "priority_waiting_for_android_profile candidate=$slot_label seconds=5"
}
slot_link_present() {
    case "$service" in
        AAP) [ "$peer" = "$aa_peer" ] ;;
        IAP2) [ "$peer" = "$cp_peer" ] || [ -f iap2-wifi-request ] || [ -f iap2-wifi-active ] ;;
        *) return 1 ;;
    esac
}
retry_delay() {
    case "$1" in
        1) echo 5 ;; 2) echo 10 ;; 3) echo 15 ;; 4|5) echo 20 ;; *) echo 30 ;;
    esac
}
delay_retry() {
    failures=0
    if [ -f "priority-retry-$peer" ]; then read -r failures unused <"priority-retry-$peer" || failures=0; fi
    [ "$failures" -ge 6 ] || failures=$((failures + 1))
    delay=$(retry_delay "$failures")
    printf '%s %s\n' "$failures" "$((now + delay))" >priority-retry.new
    mv -f priority-retry.new "priority-retry-$peer"
    debug "priority_backoff service=$service failures=$failures seconds=$delay"
}
finish_slot() {
    if [ "$(cat phone-state 2>/dev/null || true)" = ready ] && [ -n "$child" ]; then
        rm -f "priority-retry-$peer"
        was_ready=1
        return 0
    fi
    delay_retry
    next_slot=$now
    debug "priority_finished candidate=$slot_label service=$service reason=$1"
    allow_carplay pending
    # Release only the failed peer so the next phone can connect.
    if [ "$1" != request_failed ] && acl_now=$(peer_acl_handle) && [ -n "$acl_now" ]; then
        timeout 3 hcitool dc "$peer" >/dev/null 2>&1 || true
    fi
    if [ "$mode" = aa-wireless ] || [ "$negotiating" = 1 ]; then select_mode carplay ''; fi
    clear_slot
}
allow_carplay pending
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
        next_listen=0
    elif [ "$pid" != "$bt_pid" ]; then
        bt_pid=$pid
        next_listen=0
    fi
    # Serialize Bluetooth control with explicit forgetting in the panel.
    exec 8>phone-control.lock
    flock -n 8 || continue
    # Listen must run after the factory daemon is ready. Success is acceptance,
    # not a connected phone. Retry errors; never disturb an active session.
    if [ "$was_ready" = 0 ] && [ -n "$pid" ] && [ "$now" -ge "$next_listen" ]; then
        if [ "$(cat phone-state 2>/dev/null || true)" != ready ] &&
            [ ! -e /tmp/rfcomm_IAP2 ] && [ ! -e /tmp/rfcomm_AAP ] &&
            [ ! -f iap2-wifi-request ] && [ ! -f iap2-wifi-active ] &&
            ! timeout 3 hcitool con 2>/dev/null | grep -q ACL; then
            debug 'bluetooth_listen_start'
            if timeout 8 ./bluetooth-autoconnect --listen >/dev/null 2>&1; then
                next_listen=$((now + 30))
                debug 'bluetooth_listen_accepted'
            else
                debug "bluetooth_listen_failed exit=$?"
                next_listen=$((now + 5))
            fi
            timeout 3 hciconfig hci0 piscan >/dev/null 2>&1 || true
        fi
    fi
    aa_peer=$(rfcomm_peer /tmp/rfcomm_AAP || true)
    cp_peer=$(rfcomm_peer /tmp/rfcomm_IAP2 || true)
    usb=$(usb_kind)
    ready=$(cat phone-state 2>/dev/null || true)
    # A fresh profile link is observable even while directed calls are on hold.
    # A link already present at startup, or still present after failure, is not
    # another incoming request. Keep a new edge only while its link survives.
    if [ "$cp_peer" != "$last_cp" ] && [ -n "$mode" ]; then incoming_cp=$cp_peer; fi
    if [ "$aa_peer" != "$last_aa" ] && [ -n "$mode" ]; then incoming_aa=$aa_peer; fi
    last_cp=$cp_peer last_aa=$aa_peer
    if [ -z "$mode" ]; then
        select_mode carplay ''
        next_slot=$((now + 4))
    fi
    exited=0
    if [ -n "$child" ] && ! kill -0 "$child" 2>/dev/null; then
        rc=0
        wait "$child" 2>/dev/null || rc=$?
        debug "auto_receiver_exit platform=$mode exit=$rc"
        child=
        exited=1
        retry=$((now + 3))
    fi
    if [ "$ready" = ready ] && [ "$exited" = 0 ]; then
        if [ "$was_ready" = 0 ] && [ -n "$peer" ]; then rm -f "priority-retry-$peer"; fi
        was_ready=1
        incoming_cp= incoming_aa=
    elif [ -z "$ready" ] && [ "$was_ready" = 1 ] && [ "$exited" = 0 ]; then
        : # The bridge refreshes this marker. Wait for an explicit state.
    else
        if [ "$was_ready" = 1 ]; then
            clear_slot
            candidate=0 last_peer=
            next_slot=$now
            select_mode carplay ''
            was_ready=0
            debug 'priority_restart reason=session_ended'
        fi
        # Prefer the phone already answering our current attempt. Otherwise a
        # fresh incoming link may take an idle receiver or interrupt a dial
        # that has not begun negotiation. Never displace wired/active work.
        if [ "$service" = AUTO ]; then
            if [ "$peer" = "$cp_peer" ]; then
                service=IAP2
                allow_carplay "$grant"
            elif [ "$peer" = "$aa_peer" ]; then
                service=AAP
            fi
        fi
        if [ "$now" -ge "$deadline" ] && [ -z "$usb" ] && [ "$exited" = 0 ] && ! slot_link_present; then
            extend_android_slot || :
        fi
        if [ -z "$usb" ] && [ "$mode" = carplay ] && [ "$negotiating" = 0 ] &&
            [ "$android_grace" = 0 ] && [ -n "$incoming_cp$incoming_aa" ] &&
            ! slot_link_present; then
            choice=carplay
            if [ -z "$incoming_cp" ]; then choice=aa-wireless
            elif [ -n "$incoming_aa" ]; then choice=$(./phone-policy --choose "$incoming_aa" "$incoming_cp"); fi
            if [ "$choice" = aa-wireless ]; then
                begin_slot "$incoming_aa" AAP incoming
            else
                rm -f wireless-retry wireless-attempt
                begin_slot "$incoming_cp" IAP2 incoming
            fi
            debug "priority_incoming service=$service"
            exited=0
        fi
        if [ "$service" = IAP2 ] && [ "$peer" = "$incoming_cp" ]; then incoming_cp=; fi
        if [ "$service" = AAP ] && [ "$peer" = "$incoming_aa" ]; then incoming_aa=; fi
        if [ -n "$peer" ]; then
            if [ "$exited" = 1 ]; then
                finish_slot receiver_exit
            elif [ "$service" = IAP2 ] && [ "$(cat priority-iap2-ended 2>/dev/null || true)" = "$grant" ] &&
                [ ! -f iap2-wifi-request ] && [ ! -f iap2-wifi-active ]; then
                # Bluetooth can finish between two ticks, before Wi-Fi starts.
                if [ "$handover_due" = 0 ]; then
                    handover_due=$((now + 15))
                    if [ "$negotiating" = 0 ]; then negotiating=1; deadline=$((now + 45)); fi
                    debug 'priority_waiting_for_wifi'
                fi
                if [ "$now" -ge "$handover_due" ] || [ "$now" -ge "$deadline" ]; then finish_slot iap2_exit; fi
            elif [ "$service" = IAP2 ] && [ "$(cat priority-iap2-failed 2>/dev/null || true)" = "$grant" ] &&
                [ ! -f iap2-wifi-request ] && [ ! -f iap2-wifi-active ]; then
                finish_slot iap2_exit
            elif [ "$negotiating" = 0 ] && slot_link_present; then
                if [ "$service" = AAP ]; then select_mode aa-wireless "$peer"; fi
                negotiating=1
                deadline=$((now + 45))
                debug "priority_negotiating candidate=$slot_label service=$service"
            elif [ "$now" -ge "$deadline" ]; then
                finish_slot timeout
            fi
        fi
        if [ -n "$usb" ] && [ "$negotiating" = 0 ]; then
            if [ -n "$peer" ]; then clear_slot; fi
            candidate=0 last_peer=
            if [ "$mode" != "$usb" ]; then select_mode "$usb" ''; fi
        elif [ -z "$usb" ] && [ -z "$peer" ]; then
            if [ "$mode" = aa-usb ]; then select_mode carplay ''; fi
            if [ -n "$pid" ] && [ -n "$child" ] && [ -z "$incoming_cp$incoming_aa" ] && [ "$now" -ge "$next_slot" ]; then
                next_slot=$((now + 3))
                start_slot
            fi
        fi
    fi
    if [ "$(cat phone-selected 2>/dev/null || true)" = "$mode" ] && [ -z "$child" ] &&
        [ "$now" -ge "$retry" ] && { [ "$mode" != aa-wireless ] || [ "$aa_peer" = "$selected" ]; }; then
        if [ "$mode" = carplay ]; then
            setsid sh ./supervise-phone.sh 8>&- &
        else
            setsid ./receiver-native --android-auto 8>&- >/dev/null 2>&1 &
        fi
        child=$!
        rm -f phone-restart
        debug "auto_receiver_start platform=$mode"
    fi
    # Wake the serialized worker once both the grant and its matching channel
    # exist. It still checks the grant and USB state before launching iAP2.
    if [ "$mode" = carplay ] && [ -z "$usb" ] && [ "$was_ready" = 0 ] &&
        [ "$service" = IAP2 ] && [ "$peer" = "$cp_peer" ] && [ "$grant" != "$last_woken" ] &&
        touch carplay-wakeup/pending; then
        last_woken=$grant
    fi
    # A panel save explicitly requests another negotiation with this phone.
    reconfigure=0
    if [ -f aa-video-reload ]; then
        rm -f aa-video-reload
        if [ -n "$child" ] && [ "$mode" != carplay ] &&
            ! cmp -s aa-video-session /etc/yamaha-sdl/aa-video.conf; then
            reconfigure=1
            : >phone-restart
        fi
    fi
    if [ -n "$child" ] && [ "$mode" != carplay ] && [ -f phone-restart ]; then
        if [ "$reconfigure" = 0 ] && [ "$mode" = aa-wireless ] &&
            [ "$was_ready" = 0 ] && [ -n "$peer" ]; then
            finish_slot receiver_failed
        else
            debug "auto_receiver_retry platform=$mode"
            stop_receiver
            rm -f phone-restart
            retry=$((now + 2))
        fi
    fi
    # Release the shared open-file lock explicitly, including when an ash
    # applet keeps a duplicate descriptor while launching the receiver.
    flock -u 8
done
