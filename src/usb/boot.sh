#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# USB installer v1 boot controller. No source/eval of persistent state.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset DEXTEND_FIXTURE_ROOT YAMAHA_AA_MODE YAMAHA_AA_PEER LD_PRELOAD
s=/etc/yamaha-sdl/usb-v1
log() { [ ! -f /tmp/dextend-service/diagnostics.sh ] || sh /tmp/dextend-service/diagnostics.sh event boot "$@" || true; }
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
id_ok() { [ "${#1}" = 64 ] && case "$1" in *[!0-9a-f]*) return 1 ;; *) return 0 ;; esac }
digest() { sha256sum "$1" | awk '{print $1}'; }
put() {
    [ ! -L "$s/$1" ] && [ ! -L "$s/$1.new" ] || return 1
    printf '%s\n' "$2" >"$s/$1.new" && sync && mv "$s/$1.new" "$s/$1" && sync
}
get() { regular "$s/$1" && cat "$s/$1"; }
valid_release() {
    id_ok "$1" || return 1
    d=$s/releases/$1
    [ -d "$d" ] && [ ! -L "$d" ] && regular "$d/SHA256SUMS" || return 1
    [ "$(digest "$d/SHA256SUMS")" = "$1" ] || return 1
    count=$(wc -l <"$d/SHA256SUMS")
    [ "$count" = 3 ] || [ "$count" = 4 ] || [ "$count" = 5 ] || return 1
    if [ "$count" -ge 4 ]; then
        regular "$d/service-runtime.tar.lzma" && [ "$(grep -c "  service-runtime.tar.lzma$" "$d/SHA256SUMS")" = 1 ] || return 1
    fi
    for n in native-boot.sh native-runtime.tar.lzma version.txt; do
        regular "$d/$n" || return 1
        [ "$(grep -c "  $n\$" "$d/SHA256SUMS")" = 1 ] || return 1
    done
    (cd "$d" && sha256sum -c SHA256SUMS >/dev/null 2>&1)
}
# The service selection survives a failed native boot. Verify its own files,
# not the native payload, before starting diagnostics in the OEM namespace.
start_service() {
    service_id=$(get service-release || true)
    id_ok "$service_id" || return 0
    service_dir=$s/releases/$service_id
    regular "$service_dir/SHA256SUMS" && [ "$(digest "$service_dir/SHA256SUMS")" = "$service_id" ] || return 1
    for file in service-boot.sh service-runtime.tar.lzma; do
        regular "$service_dir/$file" || return 1
        expected=$(awk -v name="$file" '$2==name {print $1}' "$service_dir/SHA256SUMS")
        [ "${#expected}" = 64 ] && [ "$(digest "$service_dir/$file")" = "$expected" ] || return 1
    done
    DEXTEND_RELEASE_DIR="$service_dir" sh "$service_dir/service-boot.sh"
}
rollback() {
    log rollback_selection "reason=${1:-unknown}"
    old=$(get previous || true)
    if valid_release "$old"; then put active "$old"; else put active none; fi
    put status ROLLED_BACK_RESTART_REQUIRED
    rm -f "$s/pending" "$s/attempted"
    sync
}
[ -d "$s" ] && [ ! -L "$s" ] && [ ! -L /etc/yamaha-sdl ] || exit 1
[ -d "$s/releases" ] && [ ! -L "$s/releases" ] || exit 1
[ ! -L /etc/yamaha-sdl/enabled ] || exit 1
[ -f /etc/yamaha-sdl/enabled ] || exit 0
mkdir /tmp/dextend-usb-started 2>/dev/null || exit 0
start_service || printf 'SERVICE_START_FAILED\n' >/tmp/dextend-service-status
log service_start_complete
current=$(get active || true)
[ "$current" != none ] || {
    log native_skipped active_none
    exit 0
}
if ! valid_release "$current"; then
    rollback invalid_release
    exit 1
fi
pending=$(get pending || true)
if [ "$pending" = "$current" ] && [ "$(get confirmed || true)" != "$current" ]; then
    if [ "$(get attempted || true)" = "$current" ]; then
        rollback previous_attempt_unconfirmed
        current=$(get active)
        [ "$current" != none ] || exit 0
        valid_release "$current" || exit 1
    else
        # A failed durable write aborts BEFORE touching the OEM processes.
        put attempted "$current"
    fi
fi
export DEXTEND_RELEASE_DIR=$s/releases/$current
log native_start
if sh "$DEXTEND_RELEASE_DIR/native-boot.sh" >/dev/null 2>&1; then
    log native_healthy
    put confirmed "$current"
    put status ACTIVE
    rm -f "$s/pending" "$s/attempted"
    sync
else
    # Native coordinator attempts cleanup. Do not start competing processes.
    # Persist selection for the NEXT boot; no automatic reboot loop.
    rc=$?
    log native_exit "rc=$rc"
    rollback native_start_failed
    exit 1
fi
