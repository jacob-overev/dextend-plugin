#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Temporary OEM pause only while a failed installation is serviced.
# No flash, radio configuration, module or USB role writes.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
r=/tmp/dextend-service
s=/etc/yamaha-sdl/usb-v1
if [ "${1:-}" = release ]; then
    owner=0
    owner_start=0
else
    owner=${1:?manager PID required}
    owner_start=${2:?manager start time required}
fi
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
stamp() { sed 's/.*) //' "/proc/$1/stat" 2>/dev/null | awk '{print $20}'; }
same() { [ -r "/proc/$1/stat" ] && [ "$(stamp "$1")" = "$2" ]; }
log() { sh "$r/diagnostics.sh" event recovery "$@" 2>/dev/null || true; }
resume() {
    if regular "$r/recovery.paused"; then
        while read -r pid start; do
            case "$pid:$start" in *[!0-9:]* | :*) continue ;; esac
            [ "$pid" -gt 1 ] || continue
            if same "$pid" "$start"; then kill -CONT "$pid" 2>/dev/null || true; fi
        done <"$r/recovery.paused"
        rm -f "$r/recovery.paused"
        log oem_resumed
    fi
    echo idle >"$r/recovery-status"
}
cleanup() {
    trap - EXIT
    resume
}
# Do not install cleanup until all output paths are verified.
[ ! -L "$r/recovery.paused" ] && [ ! -L "$r/recovery-status" ] && [ ! -L "$r/recovery.lock" ] || exit 1
# Serialize cleanup with a previous guard after a manager crash. Kernel releases
# the lock even after SIGKILL; a stale PID file cannot hold it indefinitely.
exec 9>"$r/recovery.lock"
flock 9
trap cleanup EXIT
trap 'exit 0' HUP INT TERM
resume
command -v pidof >/dev/null || exit 1
eligible() {
    regular "$s/active" && [ "$(cat "$s/active")" = none ] &&
        regular "$s/status" && [ "$(cat "$s/status")" = ROLLED_BACK_RESTART_REQUIRED ] &&
        ! pidof receiver-native >/dev/null 2>&1 &&
        "$r/debug-api" --device >/dev/null 2>&1
}
target() {
    exe=$(readlink "/proc/$1/exe" 2>/dev/null) || return 1
    case "$exe" in
        /usr/sbin/ARMadb-driver | /usr/sbin/ARMHiCar) return 0 ;;
        /tmp/bin/ARMadb-driver | /tmp/bin/ARMHiCar)
            # OEM copies HiCar into RAM. Do not trust a name alone.
            cmp -s "$exe" "/usr/sbin/${exe##*/}"
            return $?
            ;;
        /bin/busybox | /usr/bin/busybox)
            tr '\000' '\n' <"/proc/$1/cmdline" | awk '
                NR==1 {shell=($0=="sh" || $0=="ash" || $0=="/bin/sh" || $0=="/bin/ash")}
                NR==2 {script=($0=="/script/phone_link_deamon.sh")}
                NR==3 {kind=($0=="HiCar")}
                NR==4 {start=($0=="start")}
                END {exit !(NR==4 && shell && script && kind && start)}'
            ;;
        *) return 1 ;;
    esac
}
pause() {
    if regular "$r/recovery.paused"; then
        # Bound the journal when OEM children are killed and replaced externally.
        [ ! -L "$r/recovery.live" ] || return 1
        : >"$r/recovery.live"
        while read -r pid start; do
            if same "$pid" "$start"; then printf '%s %s\n' "$pid" "$start" >>"$r/recovery.live"; fi
        done <"$r/recovery.paused"
        mv "$r/recovery.live" "$r/recovery.paused"
    fi
    for proc in /proc/[0-9]*; do
        pid=${proc##*/}
        [ "$pid" -gt 1 ] || continue
        # read is a shell builtin: avoid spawning readlink for every kernel task.
        IFS= read -r name <"$proc/comm" 2>/dev/null || continue
        case "$name" in ARMadb-driver | ARMHiCar | sh | ash | exe | busybox | phone_link_deam*) ;; *) continue ;; esac
        target "$pid" || continue
        start=$(stamp "$pid")
        case "$start" in '' | *[!0-9]*) continue ;; esac
        if regular "$r/recovery.paused" && grep -qx "$pid $start" "$r/recovery.paused"; then continue; fi
        # A process stopped by another owner must never be resumed by us.
        if awk '/^State:/{exit ($2=="T" || $2=="t" ? 0 : 1)}' "$proc/status" 2>/dev/null; then continue; fi
        if regular "$r/recovery.paused" && [ "$(wc -l <"$r/recovery.paused")" -ge 64 ]; then
            log process_limit
            return 1
        fi
        # Journal identity before STOP so a restarted guard can undo its pause.
        printf '%s %s\n' "$pid" "$start" >>"$r/recovery.paused"
        if same "$pid" "$start"; then kill -STOP "$pid" 2>/dev/null || true; fi
    done
    status=oem_not_found
    if regular "$r/recovery.paused" && [ -s "$r/recovery.paused" ]; then status=oem_paused; fi
    if [ "$(cat "$r/recovery-status")" != "$status" ]; then log "$status"; fi
    echo "$status" >"$r/recovery-status"
}
while same "$owner" "$owner_start" && [ ! -e "$r/stopping" ] && regular /etc/yamaha-sdl/enabled; do
    if eligible; then pause; else resume; fi
    sleep 1
done
