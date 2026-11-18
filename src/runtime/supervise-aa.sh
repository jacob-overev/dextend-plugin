#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Explicit RAM trial. OEM handles USB AOAP or the paired Bluetooth/Wi-Fi peer.
set -eu
cd /tmp/yamaha-sdl
. ./debug-log.sh
delay=1
child=
trap '[ -z "$child" ] || kill "$child" 2>/dev/null || true' EXIT
trap 'exit 0' INT TERM
while [ -f /etc/yamaha-sdl/enabled ]; do
    if [ ! -S /var/run/adb-driver ]; then
        sleep 1
        continue
    fi
    rm -f phone-restart aa-video-reload
    ./receiver-native --android-auto >/dev/null 2>&1 &
    child=$!
    debug 'AA_RECEIVER_STARTED'
    while kill -0 "$child" 2>/dev/null && [ -f /etc/yamaha-sdl/enabled ] &&
        [ ! -f phone-restart ] && [ ! -f aa-video-reload ]; do sleep 1; done
    [ ! -f aa-video-reload ] || delay=1
    kill "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
    child=
    sleep "$delay"
    [ "$delay" -ge 32 ] || delay=$((delay * 2))
done
