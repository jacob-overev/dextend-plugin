#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# A private RAM spool exists only during a user-selected USB logging session.
set -u
umask 077
runtime=${YAMAHA_RUNTIME:-/tmp/yamaha-sdl}
mountpoint=${YAMAHA_LOG_USB_MOUNT:-/mnt/UPAN}
mountinfo=${YAMAHA_LOG_MOUNTS:-/proc/self/mountinfo}
interval=${YAMAHA_LOG_INTERVAL:-2}
enabled=${YAMAHA_LOG_ENABLED_FILE:-}
spool=${YAMAHA_LOG_SPOOL:-$runtime/usb-debug}
chunk=524288
mount_id=
session=
stop_logging() {
    rm -rf "$spool"
    mount_id=
    session=
}
trap stop_logging EXIT
trap 'exit 0' INT TERM HUP
stop_logging

usb_mount_id() {
    awk -v target="$mountpoint" '
        $5 == target && $6 ~ /^rw(,|$)/ {
            for (i=7; i<=NF; i++)
                if ($i=="-" && $(i+1)=="vfat" && $(i+2) ~ /^\/dev\/sd[a-z][0-9]*$/)
                    print $1
        }
    ' "$mountinfo" 2>/dev/null
}
usable() {
    [ "$(usb_mount_id)" = "$mount_id" ] &&
        [ -d "$mountpoint/dongle-logs" ] && [ ! -L "$mountpoint/dongle-logs" ] &&
        [ ! -e "$mountpoint/A15W_Update.img" ] && [ ! -L "$mountpoint/A15W_Update.img" ]
}
# Open one opt-in diagnostic session on the mounted drive.
open_session() {
    # The subshell holds the mounted directory by reference. If unmounted
    # during I/O, relative paths cannot fall back to the underlying rootfs.
    cd -P "$mountpoint/dongle-logs" && usable || exit 1
    stamp=$(date -u +%Y%m%dT%H%M%SZ) || exit 1
    directory=$(mktemp -d "session-$stamp-XXXXXX") || exit 1
    (
        cd "$directory" || exit 1
        printf 'recording_started_utc=%s\nclock=device_utc_may_be_unsynchronised\n' "$stamp"
        printf 'uptime_seconds='
        cut -d ' ' -f 1 /proc/uptime
        awk '$1 == "btime" { print "boot_epoch_seconds=" $2 }' /proc/stat
        printf 'dextend='
        cat "${YAMAHA_LOG_VERSION_FILE:-$runtime/waiting-version}" 2>/dev/null || echo unknown
        printf 'oem_firmware='
        cat /etc/software_version 2>/dev/null || echo unknown
        printf 'kernel='
        uname -r
    ) >"$directory/session.txt" || exit 1
    printf '%s\n' "$directory"
}
export_logs() (
    cd -P "$mountpoint/dongle-logs/$session" && usable || exit 1
    for name in bridge.log bridge.log.previous services.log services.log.previous; do
        [ -f "$spool/$name" ] || continue
        [ ! -L "$spool/$name" ] && [ ! -L "$name.new" ] || exit 1
        usable || exit 1
        tail -c "$chunk" "$spool/$name" >"$name.new" &&
            mv -f "$name.new" "$name" || exit 1
    done
    sync
)
state_snapshot() {
    (
        printf '%s state' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        for name in phone-state phone-mode ccu-fd; do
            value=$(cat "$runtime/$name" 2>/dev/null || true)
            case "$value" in
                ready | waiting | wired | wireless | open | closed) ;;
                *) value=unknown ;;
            esac
            printf ' %s=%s' "$name" "$value"
        done
        for name in AppleCarPlay ARMiPhoneIAP2 ARMAndroidAuto bluetoothDaemon; do
            if pidof "$name" >/dev/null 2>&1; then value=running; else value=stopped; fi
            printf ' %s=%s' "$name" "$value"
        done
        for name in status ssh-status; do
            value=$(cat "/tmp/dextend-service/$name" 2>/dev/null || true)
            case "$value" in '' | *[!a-z_]*) value=unknown ;; esac
            printf ' service_%s=%s' "$name" "$value"
        done
        printf '\n'
    ) >>"$spool/services.log"
}
trap 'if [ -n "$session" ] && usable; then export_logs || true; fi; exit 0' INT TERM HUP
while [ -z "$enabled" ] || [ -f "$enabled" ]; do
    current=$(usb_mount_id)
    case "$current" in '' | *[!0-9]*)
        stop_logging
        sleep "$interval"
        continue
        ;;
    esac
    if [ "$current" != "$mount_id" ]; then
        stop_logging
        mount_id=$current
    fi
    free=$(df -Pk "$mountpoint" 2>/dev/null | awk 'NR==2 {print $4}')
    case "$free" in '' | *[!0-9]*) free=0 ;; esac
    if ! usable || [ "$free" -lt 8192 ]; then
        stop_logging
        sleep "$interval"
        continue
    fi
    if [ -z "$session" ]; then
        session=$(open_session) && mkdir "$spool" || {
            stop_logging
            sleep "$interval"
            continue
        }
    fi
    if [ -f "$spool/services.log" ] && [ "$(wc -c <"$spool/services.log")" -ge "$chunk" ]; then
        mv -f "$spool/services.log" "$spool/services.log.previous"
    fi
    state_snapshot
    export_logs || stop_logging
    sleep "$interval"
done
