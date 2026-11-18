#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Per-device radio names, with a durable baseline and selective undo.
set -eu
umask 077
LC_ALL=C
export LC_ALL
base=/etc/yamaha-sdl/usb-v1
saved=$base/radio
here=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
names='riddle.conf hostapd.conf wifi_name bluetooth_name .custom_wifi_name .custom_bluetooth_name'
regular() { [ -f "$1" ] && [ ! -L "$1" ] && [ "$(wc -c <"$1")" -le 65536 ]; }
exists() { [ -e "$1" ] || [ -L "$1" ]; }
private_radio_bus() {
    bus=$1
    case "$bus" in '' | *[!0-9]* | 0 | 1) return 1 ;; esac
    case "$(readlink "/proc/$bus/exe" 2>/dev/null)" in
        /usr/sbin/dbus-daemon) ;;
        /tmp/bin/dbus-daemon) cmp -s /tmp/bin/dbus-daemon /usr/sbin/dbus-daemon || return 1 ;;
        *) return 1 ;;
    esac
    [ "$(tr '\000' ' ' <"/proc/$bus/cmdline")" = 'dbus-daemon --system --print-pid --print-address ' ] || return 1
    bus_ns=$(readlink "/proc/$bus/ns/mnt") || return 1
    init_ns=$(readlink /proc/1/ns/mnt) || return 1
    [ "$bus_ns" != "$init_ns" ] || return 1
    # OEM bluetoothDaemon starts a detached system bus. Accept only a bus
    # retaining all three mounts created by receiver-native --auto-runtime.
    awk '
      $4 ~ /^\/yamaha-sdl\/bt-audio-[A-Za-z0-9]+$/ && $5=="/etc/riddle.conf" {a=1}
      $4 ~ /^\/yamaha-sdl\/bt-audio-[A-Za-z0-9]+$/ && $5=="/tmp/.riddle.conf" {b=1}
      $4 ~ /^\/yamaha-sdl\/android-mode-[A-Za-z0-9]+(\/\/deleted)?$/ && $5=="/etc/android_work_mode" {c=1}
      END {exit !(a&&b&&c)}' "/proc/$bus/mountinfo" || return 1
    awk '{sub(/^[0-9]+ \(.*\) /, ""); print $20}' "/proc/$bus/stat"
}
quiesce_private_bus() {
    for info in /proc/[0-9]*/mountinfo; do
        bus=${info#/proc/}
        bus=${bus%/mountinfo}
        stamp=$(private_radio_bus "$bus" 2>/dev/null) || continue
        [ -n "$stamp" ] || continue
        kill -TERM "$bus" 2>/dev/null || true
        i=0
        while [ "$(private_radio_bus "$bus" 2>/dev/null || true)" = "$stamp" ] && [ "$i" -lt 3 ]; do
            sleep 1
            i=$((i + 1))
        done
        # Revalidate identity after waiting; never signal a reused PID.
        if [ "$(private_radio_bus "$bus" 2>/dev/null || true)" = "$stamp" ]; then
            kill -KILL "$bus" 2>/dev/null || true
        fi
    done
}
quiesce() {
    # Linux 3.14 rejects rename over a dentry mounted in ANY namespace.
    # receiver-native binds riddle.conf privately; stop its verified process
    # group before restoring or replacing the persistent configuration.
    if regular /tmp/yamaha-sdl/boot.pid; then
        pid=$(cat /tmp/yamaha-sdl/boot.pid)
        case "$pid" in '' | *[!0-9]* | 0 | 1) return 1 ;; esac
        if [ -d "/proc/$pid" ]; then
            [ "$(readlink "/proc/$pid/cwd")" = /tmp/yamaha-sdl ] || return 1
            tr '\000' '\n' <"/proc/$pid/cmdline" | grep -Fxq './boot-live.sh' || return 1
            group=$(awk '{sub(/^[0-9]+ \(.*\) /, ""); print $3}' "/proc/$pid/stat")
            [ "$group" = "$pid" ] || return 1
            kill -TERM "-$pid" 2>/dev/null || true
            i=0
            while kill -0 "-$pid" 2>/dev/null && [ "$i" -lt 3 ]; do
                sleep 1
                i=$((i + 1))
            done
            if kill -0 "-$pid" 2>/dev/null; then kill -KILL "-$pid" 2>/dev/null || true; fi
        fi
    fi
    quiesce_private_bus
    # Refuse unknown users of these files; never unmount another process's data.
    i=0
    while :; do
        busy=0
        for info in /proc/[0-9]*/mountinfo; do
            [ -r "$info" ] || continue
            if awk '$5=="/etc/riddle.conf" || $5=="/etc/hostapd.conf" || $5=="/etc/wifi_name" || $5=="/etc/bluetooth_name" || $5=="/etc/.custom_wifi_name" || $5=="/etc/.custom_bluetooth_name" {found=1} END{exit !found}' "$info" 2>/dev/null; then
                busy=1
                break
            fi
        done
        [ "$busy" != 0 ] || return 0
        [ "$i" -lt 3 ] || return 1
        sleep 1
        i=$((i + 1))
    done
}
render_ssid() {
    awk '/^ssid=/{if(!done++)print "ssid=Dextend";next} {print} END{if(!done)print "ssid=Dextend"}' /etc/hostapd.conf
}
check_current() {
    for n in $names; do ! exists "/etc/$n" || regular "/etc/$n"; done
    regular /etc/riddle.conf
    regular /etc/hostapd.conf
    candidate=$(awk -v action=apply -f "$here/radio-config.awk" /etc/riddle.conf)
    [ "${#candidate}" -lt 65536 ]
    candidate=$(render_ssid)
    [ "${#candidate}" -lt 65536 ]
    unset candidate
    [ "$(grep -c '^ssid=' /etc/hostapd.conf)" -le 1 ]
}
check_saved() {
    [ -d "$saved" ] && [ ! -L "$saved" ]
    for n in $names presence SHA256SUMS; do regular "$saved/$n"; done
    [ "$(find "$saved" -mindepth 1 | wc -l)" = 8 ]
    [ "$(wc -l <"$saved/presence")" = 6 ]
    [ "$(wc -l <"$saved/SHA256SUMS")" = 7 ]
    for n in $names; do
        [ "$(awk -v n="$n" '$2==n && $1 ~ /^[01]$/ && NF==2 {c++} END {print c+0}' "$saved/presence")" = 1 ]
        [ "$(awk -v n="$n" '$2==n {c++} END {print c+0}' "$saved/SHA256SUMS")" = 1 ]
    done
    [ "$(awk '$2=="presence" {c++} END {print c+0}' "$saved/SHA256SUMS")" = 1 ]
    (cd "$saved" && sha256sum -c SHA256SUMS >/dev/null)
}
write_file() {
    regular "$1"
    # Stage on the same filesystem, within the installation's owned directory.
    ! exists "$base/radio-output" || regular "$base/radio-output"
    case "$2" in
        riddle.conf) label=RIDDLE ;; hostapd.conf) label=HOSTAPD ;;
        wifi_name) label=WIFI ;; bluetooth_name) label=BT ;;
        .custom_wifi_name) label=CUSTOM_WIFI ;; .custom_bluetooth_name) label=CUSTOM_BT ;;
        *) return 1 ;;
    esac
    step=RADIO_${label}_STAGE_FAILED
    cp -p "$1" "$base/radio-output"
    sync
    step=RADIO_${label}_RENAME_FAILED
    mv -f "$base/radio-output" "/etc/$2"
    sync
    step=RADIO_${label}_VERIFY_FAILED
    cmp -s "$1" "/etc/$2"
}
tmp=
step=RADIO_VALIDATION_FAILED
finish() {
    rc=$?
    trap - EXIT HUP INT TERM
    if [ "$rc" != 0 ]; then
        printf '%s\n' "$step" >/tmp/dextend-radio-error
        printf 'DEXTEND: %s\n' "$step" >&2
    fi
    [ -z "$tmp" ] || rm -f "$tmp"
    exit "$rc"
}
rm -f /tmp/dextend-radio-error
trap finish EXIT
trap 'exit 1' HUP INT TERM
case "${1:-}" in
    quiesce)
        step=RADIO_CONFIG_IN_USE
        quiesce
        ;;
    preflight)
        check_current
        if exists "$saved"; then check_saved; fi
        ;;
    budget)
        total=0
        for n in $names; do
            a=0
            b=0
            if regular "/etc/$n"; then a=$(wc -c <"/etc/$n"); fi
            if regular "$saved/$n"; then b=$(wc -c <"$saved/$n"); fi
            [ "$a" -ge "$b" ] || a=$b
            total=$((total + a))
        done
        echo $(((3 * total + 1023) / 1024 + 32))
        ;;
    apply)
        check_current
        if ! exists "$saved"; then
            ! exists "$base/radio.new"
            mkdir "$base/radio.new"
            for n in $names; do
                if exists "/etc/$n"; then
                    cp -p "/etc/$n" "$base/radio.new/$n"
                    printf '1 %s\n' "$n"
                else
                    : >"$base/radio.new/$n"
                    printf '0 %s\n' "$n"
                fi
            done >"$base/radio.new/presence"
            (cd "$base/radio.new" && sha256sum $names presence >SHA256SUMS && sync)
            mv "$base/radio.new" "$saved"
            sync
        fi
        check_saved
        tmp=$(mktemp /tmp/dextend-radio.XXXXXX)
        for n in $names; do
            if exists "/etc/$n"; then cp -p "/etc/$n" "$tmp"; else chmod 644 "$tmp"; fi
            case "$n" in
                riddle.conf) awk -v action=apply -f "$here/radio-config.awk" /etc/riddle.conf >"$tmp" ;;
                hostapd.conf) render_ssid >"$tmp" ;;
                *) printf 'Dextend\n' >"$tmp" ;;
            esac
            write_file "$tmp" "$n"
        done
        ;;
    restore)
        if exists "$saved"; then
            check_saved
            tmp=$(mktemp /tmp/dextend-radio.XXXXXX)
            for n in $names; do
                ! exists "/etc/$n" || regular "/etc/$n"
                if grep -Fxq "0 $n" "$saved/presence"; then
                    rm -f "/etc/$n"
                    continue
                fi
                cp -p "$saved/$n" "$tmp"
                if [ "$n" = riddle.conf ] && exists /etc/riddle.conf; then
                    awk -v action=restore -f "$here/radio-config.awk" /etc/riddle.conf "$saved/riddle.conf" >"$tmp"
                elif [ "$n" = hostapd.conf ] && exists /etc/hostapd.conf; then
                    awk 'FILENAME==ARGV[1]{if(/^ssid=/){old=$0;found=1};next} /^ssid=/{if(found && !done++)print old;next} {print} END{if(found && !done)print old}' "$saved/hostapd.conf" /etc/hostapd.conf >"$tmp"
                fi
                if [ "$(cat "$tmp")" = "$(cat "$saved/$n")" ]; then cp -p "$saved/$n" "$tmp"; fi
                write_file "$tmp" "$n"
            done
            sync
        fi
        ;;
    *) exit 2 ;;
esac
