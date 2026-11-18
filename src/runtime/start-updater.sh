#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Separate process in the OEM namespace; survives runtime stop.
set -eu
umask 077
cd "$(dirname "$0")"
w=/tmp/dextend-updater
[ ! -L "$w" ] || exit 1
mkdir -p "$w"
mkdir "$w/start.lock" 2>/dev/null || exit 0
trap 'rmdir "$w/start.lock"' EXIT
for name in updater-http updater-api.sh updater-worker.sh updater-events.sh token state stage events.log http.log http.pid http.start; do
    [ ! -L "$w/$name" ] && { [ ! -e "$w/$name" ] || [ -f "$w/$name" ]; } || exit 1
done
pid=$(cat "$w/http.pid" 2>/dev/null || true)
case "$pid" in '' | *[!0-9]* | 0 | 1) pid= ;; esac
if [ -n "$pid" ] && [ -r "/proc/$pid/stat" ] &&
    [ "$(readlink "/proc/$pid/exe")" = "$w/updater-http" ] &&
    [ "$(awk '{print $22}' "/proc/$pid/stat")" = "$(cat "$w/http.start" 2>/dev/null)" ]; then
    exit 0
fi
cp ./updater-http ./updater-api.sh ./updater-worker.sh ./updater-events.sh "$w/"
token=$(cat "$w/token" 2>/dev/null || true)
valid=1
[ "${#token}" = 64 ] || valid=0
case "$token" in *[!0-9a-f]*) valid=0 ;; esac
if [ "$valid" = 0 ]; then
    # Retry an incomplete initialization without publishing a partial token.
    stage=$(mktemp "$w/.token.XXXXXX")
    trap 'rm -f "$stage"; rmdir "$w/start.lock"' EXIT
    dd if=/dev/urandom bs=32 count=1 2>/dev/null | hexdump -v -e '1/1 "%02x"' >"$stage"
    [ "$(wc -c <"$stage")" = 64 ]
    mv "$stage" "$w/token"
fi
[ -f "$w/state" ] || echo idle >"$w/state"
[ -f "$w/stage" ] || echo idle >"$w/stage"
[ -f "$w/events.log" ] || : >"$w/events.log"
setsid "$w/updater-http" 8765 "$w/updater-api.sh" </dev/null >"$w/http.log" 2>&1 &
pid=$!
printf '%s\n' "$pid" >"$w/http.pid"
awk '{print $22}' "/proc/$pid/stat" >"$w/http.start"
