#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# TP-Link diagnostic lifecycle. Never configures the OEM radios.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
r=/tmp/dextend-service
s=/etc/yamaha-sdl/service
a=/dev/dextend-service-keys
log() { [ ! -f "$r/diagnostics.sh" ] || sh "$r/diagnostics.sh" event service "$@" || true; }
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
running() {
    regular "$r/$1.pid" && regular "$r/$1.start" || return 1
    pid=$(cat "$r/$1.pid")
    case "$pid" in '' | *[!0-9]* | 0 | 1) return 1 ;; esac
    [ -r "/proc/$pid/stat" ] && [ "$(awk '{print $22}' "/proc/$pid/stat")" = "$(cat "$r/$1.start")" ]
}
track() {
    log process_start "$1" "pid=$2"
    printf '%s\n' "$2" >"$r/$1.pid"
    # A failed child can exit before /proc is read. Retry it on the next tick.
    if ! awk '{print $22}' "/proc/$2/stat" >"$r/$1.start" 2>/dev/null; then
        rm -f "$r/$1.pid" "$r/$1.start"
    fi
}
stop_one() {
    log process_stop "$1"
    if running "$1"; then
        kill -TERM "$(cat "$r/$1.pid")" 2>/dev/null || true
        n=0
        while running "$1" && [ "$n" -lt 3 ]; do
            sleep 1
            n=$((n + 1))
        done
        if running "$1"; then kill -KILL "$(cat "$r/$1.pid")" 2>/dev/null || true; fi
    fi
    rm -f "$r/$1.pid" "$r/$1.start"
}
# OEM /etc may be group/world-writable. Dropbear checks every parent of -D.
# Publish the key list under root-owned devtmpfs without changing OEM modes.
prepare_ssh_keys() {
    [ ! -L "$a" ] || return 1
    if [ -e "$a" ]; then
        [ -d "$a" ] && regular "$a/format" &&
            [ "$(cat "$a/format")" = dextend-service-keys-v1 ] || return 1
    else
        mkdir -m 700 "$a" || return 1
        printf 'dextend-service-keys-v1\n' >"$a/format" || return 1
    fi
    for name in authorized_keys authorized_keys.new; do
        [ ! -L "$a/$name" ] && { [ ! -e "$a/$name" ] || regular "$a/$name"; } || return 1
    done
    chmod 700 "$a" || return 1
    cp "$r/session-key" "$a/authorized_keys.new" || return 1
    chmod 600 "$a/authorized_keys.new" || return 1
    mv "$a/authorized_keys.new" "$a/authorized_keys"
}
clear_ssh_keys() {
    [ ! -L "$a" ] && [ -d "$a" ] && regular "$a/format" &&
        [ "$(cat "$a/format")" = dextend-service-keys-v1 ] || return 0
    rm -f "$a/authorized_keys" "$a/authorized_keys.new" "$a/format"
    rmdir "$a" 2>/dev/null || true
}
stop_service_ssh() {
    clear_ssh_keys
    stop_one ssh
    # Dropbear forks a separate session for every authenticated connection.
    for exe in /proc/[0-9]*/exe; do
        [ "$(readlink "$exe" 2>/dev/null)" = "$r/dropbearmulti" ] || continue
        pid=${exe%/exe}
        kill -TERM "${pid##*/}" 2>/dev/null || true
    done
}
stop_radio() {
    stop_service_ssh
    stop_one dhcp
    stop_one wpa
    stop_one wpa-log
    rm -f "$r/wpa.events"
    rm -f "$r/interface" "$r/address"
    [ ! -e "$s/borrowed.before" ] || sh "$r/borrow-key.sh" restore
}
cleanup() {
    log manager_exit
    trap - EXIT HUP INT TERM
    rm -f "$r/session-key"
    stop_one recovery
    # Finish recovery even if stop_one had to kill a slow guard during cleanup.
    if regular "$r/recovery.sh"; then sh "$r/recovery.sh" release >/dev/null 2>&1 || true; fi
    stop_one recorder
    stop_radio || true
    # Restore only the firmware lookup override this worker installed.
    if regular "$r/firmware.previous" && [ "$(cat /sys/module/firmware_class/parameters/path)" = "$r" ]; then
        cat "$r/firmware.previous" >/sys/module/firmware_class/parameters/path || true
    fi
    if regular /tmp/boa/cgi-bin/dextend-debug && cmp -s "$r/debug-api" /tmp/boa/cgi-bin/dextend-debug; then
        rm /tmp/boa/cgi-bin/dextend-debug
    fi
    if regular "$r/modules.owned"; then
        for module in ath9k_htc ath9k_common ath9k_hw ath; do
            grep -Fxq "$module" "$r/modules.owned" && rmmod "$module" 2>/dev/null || true
        done
    fi
    rm -f "$r/manager.pid" "$r/manager.start" "$r/panel-ready"
}
case "${1:-}" in
    stop)
        : >"$r/stopping"
        if running manager; then kill -TERM "$(cat "$r/manager.pid")"; fi
        n=0
        while running manager && [ "$n" -lt 20 ]; do
            sleep 1
            n=$((n + 1))
        done
        stop_one watcher
        ! running manager
        exit $?
        ;;
    watch)
        running watcher && exit 0
        rmdir "$r/watch.lock" 2>/dev/null || true
        mkdir "$r/watch.lock" 2>/dev/null || exit 0
        track watcher $$
        trap 'rm -f "$r/watcher.pid" "$r/watcher.start"; rmdir "$r/watch.lock"' EXIT
        trap 'exit 0' HUP INT TERM
        while [ ! -e "$r/stopping" ] && regular /etc/yamaha-sdl/enabled && regular "$s/format"; do
            if ! running manager; then
                rmdir "$r/lock" 2>/dev/null || true
                sh "$r/service.sh" run || echo retrying >"$r/status"
            fi
            sleep 3
        done
        exit 0
        ;;
    run) ;;
    *) exit 2 ;;
esac
[ -d "$s" ] && [ ! -L "$s" ] && regular "$s/format" && [ "$(cat "$s/format")" = dextend-service-v1 ] || exit 1
mkdir "$r/lock" 2>/dev/null || exit 0
track manager $$
log manager_started
trap 'cleanup; rmdir "$r/lock"' EXIT
trap 'exit 0' HUP INT TERM
for name in network.conf hostkey authorized_keys; do [ ! -L "$s/$name" ] && [ ! -L "$s/$name.new" ] || exit 1; done
if ! regular "$s/network.conf"; then
    printf 'ctrl_interface=%s/ctrl\nupdate_config=1\n' "$r" >"$s/network.conf.new"
    mv "$s/network.conf.new" "$s/network.conf"
fi
cp "$s/network.conf" "$r/network.conf"
# Legacy releases could lend a key to an OEM listener. Reconcile that journal first.
if [ -e "$s/borrowed.before" ]; then sh "$r/borrow-key.sh" restore || exit 1; fi
ensure_hostkey() {
    if regular "$s/hostkey" && "$r/dropbearmulti" dropbearkey -y -f "$s/hostkey" >/dev/null 2>&1; then return 0; fi
    # A power loss can leave a complete staging key. Validate and finish it.
    if regular "$s/hostkey.new" && ! "$r/dropbearmulti" dropbearkey -y -f "$s/hostkey.new" >/dev/null 2>&1; then rm "$s/hostkey.new"; fi
    if ! regular "$s/hostkey.new"; then
        # Dropbear also creates a .pub sidecar. Generate both files in RAM;
        # persist only the private host key through the existing staging path.
        key_work=$(mktemp -d "$r/hostkey.XXXXXX") || return 1
        if ! "$r/dropbearmulti" dropbearkey -t ed25519 -f "$key_work/key" >/dev/null 2>&1; then
            rm -rf "$key_work"
            return 1
        fi
        if ! cp "$key_work/key" "$s/hostkey.new"; then
            rm -rf "$key_work"
            return 1
        fi
        rm -rf "$key_work"
    fi
    "$r/dropbearmulti" dropbearkey -y -f "$s/hostkey.new" >/dev/null 2>&1 || return 1
    chmod 600 "$s/hostkey.new"
    sync
    mv "$s/hostkey.new" "$s/hostkey" && sync
}
publish_panel() {
    [ -d /tmp/boa/www ] && [ -d /tmp/boa/cgi-bin ] && [ ! -L /tmp/boa ] && [ ! -L /tmp/boa/cgi-bin ] && [ ! -L /tmp/boa/www ] && [ ! -L /tmp/boa/www/dextend ] || return 0
    if [ ! -e "$r/panel-ready" ] || [ ! -f /tmp/boa/cgi-bin/dextend-debug ] || [ ! -f /tmp/boa/www/dextend/index.html ]; then
        mkdir -p /tmp/boa/www/dextend
        cp -R "$r/web/." /tmp/boa/www/dextend/
        cp "$r/debug-api" /tmp/boa/cgi-bin/dextend-debug
        chmod 700 /tmp/boa/cgi-bin/dextend-debug
        if regular "$r/phone-policy"; then
            cp "$r/phone-policy" /tmp/boa/cgi-bin/dextend-phones
            chmod 700 /tmp/boa/cgi-bin/dextend-phones
        fi
        # Restore remains usable when the native receiver never started.
        w=/tmp/boa/dextend-restore
        [ ! -e "$w" ] || [ -d "$w" ] && [ ! -L "$w" ] || return 1
        mkdir -p "$w"
        cp "$r/restore/"* "$w/"
        if ! regular "$w/token" || [ "$(wc -c <"$w/token")" != 64 ]; then
            dd if=/dev/urandom bs=32 count=1 2>/dev/null | hexdump -v -e '1/1 "%02x"' >"$w/token"
        fi
        [ "$(wc -c <"$w/token")" = 64 ] || return 1
        cp "$r/restore-cgi.sh" /tmp/boa/cgi-bin/dextend-restore
        chmod 700 /tmp/boa/cgi-bin/dextend-restore
        : >"$r/panel-ready"
    fi
}
while regular /etc/yamaha-sdl/enabled && regular "$s/format"; do
    if ! running recovery && regular "$r/recovery.sh"; then
        sh "$r/recovery.sh" "$$" "$(cat "$r/manager.start")" >/dev/null 2>&1 &
        track recovery $!
    fi
    printf '%s\n' "$(date +%s)" >"$r/heartbeat"
    echo running >"$r/status"
    publish_panel || echo panel_unavailable >"$r/status"
    # Retry partial initialization or a stopped listener without changing its token.
    if [ -f "$r/start-updater.sh" ]; then
        sh "$r/start-updater.sh" >/dev/null 2>&1 || echo updater_unavailable >"$r/status"
    fi
    if ! running recorder; then
        YAMAHA_LOG_SPOOL="$r/usb-debug" YAMAHA_LOG_VERSION_FILE="$r/waiting-version" \
            YAMAHA_LOG_ENABLED_FILE=/etc/yamaha-sdl/enabled \
            sh "$r/usb-log-recorder.sh" >/dev/null 2>&1 &
        track recorder $!
    fi
    if running ssh && ! cmp -s "$a/authorized_keys" "$r/session-key"; then stop_service_ssh; fi
    if ! regular "$r/session-key"; then
        if running ssh || [ -e "$a/format" ]; then stop_service_ssh; fi
        echo disabled >"$r/ssh-status"
    fi
    key_ready=0
    if ensure_hostkey; then key_ready=1; else echo hostkey_retry >"$r/ssh-status"; fi
    if "$r/debug-api" --device >/dev/null && "$r/debug-api" --oem-ready >/dev/null; then
        if [ ! -d /sys/module/ath9k_htc ]; then
            if [ ! -e "$r/firmware.previous" ]; then cat /sys/module/firmware_class/parameters/path >"$r/firmware.previous"; fi
            printf '%s' "$r" >/sys/module/firmware_class/parameters/path
            for module in ath ath9k_hw ath9k_common ath9k_htc; do
                if [ ! -d "/sys/module/$module" ]; then
                    insmod "$r/$module.ko" || break
                    printf '%s\n' "$module" >>"$r/modules.owned"
                fi
            done
        fi
        iface=$("$r/debug-api" --iface || true)
    else iface=; fi
    old=$(cat "$r/interface" 2>/dev/null || true)
    if [ "$iface" != "$old" ]; then
        log interface_changed "interface=${iface:-absent}"
        stop_radio
    fi
    if [ -n "$iface" ]; then
        printf '%s\n' "$iface" >"$r/interface"
        if ! running wpa; then
            stop_one wpa-log
            rm -f "$r/wpa.events"
            if [ -f "$r/diagnostics.sh" ] && mkfifo -m 600 "$r/wpa.events"; then
                sh "$r/diagnostics.sh" stream wifi <"$r/wpa.events" &
                track wpa-log $!
                "$r/wpa_supplicant" -D nl80211 -i "$iface" -c "$r/network.conf" >"$r/wpa.events" 2>&1 &
            else
                "$r/wpa_supplicant" -D nl80211 -i "$iface" -c "$r/network.conf" >/dev/null 2>&1 &
            fi
            track wpa $!
        fi
        if ! running dhcp; then
            udhcpc -f -i "$iface" -s "$r/dhcp.sh" >/dev/null 2>&1 &
            track dhcp $!
        fi
        ip=$("$r/debug-api" --ip || true)
        oldip=$(cat "$r/address" 2>/dev/null || true)
        if [ "$ip" != "$oldip" ]; then
            log address_changed "ip=${ip:-absent}"
            stop_one ssh
        fi
        if regular "$r/session-key" && [ "$key_ready" = 1 ] && [ -n "$ip" ] && [ "$ip" != 0.0.0.0 ] && ! running ssh; then
            # Never create a second SSH server beside an existing one.
            if pidof dropbear dropbearmulti sshd >/dev/null 2>&1; then
                echo existing_server_preserved >"$r/ssh-status"
            elif prepare_ssh_keys; then
                "$r/dropbearmulti" dropbear -F -l "$iface" -p "$ip:2223" -D "$a" -r "$s/hostkey" -P "$r/dropbear.pid" >/dev/null 2>&1 &
                track ssh $!
                echo key_only_external_interface >"$r/ssh-status"
            else
                echo authorized_keys_retry >"$r/ssh-status"
            fi
        fi
        printf '%s\n' "$ip" >"$r/address"
    fi
    summary=$("$r/debug-api" --state 2>/dev/null || echo UNAVAILABLE)
    summary="$iface $summary $(cat "$r/status") $(cat "$r/ssh-status" 2>/dev/null || true)"
    if [ "$summary" != "${last_summary:-}" ]; then
        log state "$summary"
        last_summary=$summary
    fi
    sleep 3
done
