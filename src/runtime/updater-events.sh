#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# RAM-only, bounded, structured events; no payloads or credentials.
update_event() {
    case "$1" in '' | *[!A-Za-z0-9_]*) return 0 ;; esac
    [ "${#1}" -le 48 ] || return 0
    mkdir "$w/events-lock" 2>/dev/null || return 0
    {
        tail -n 63 "$w/events.log" 2>/dev/null || true
        printf '%s %s\n' "$(date +%s)" "$1"
    } >"$w/events.new"
    mv "$w/events.new" "$w/events.log"
    rmdir "$w/events-lock"
}
update_stage() {
    printf '%s\n' "$1" >"$w/stage.new"
    mv "$w/stage.new" "$w/stage"
    update_event "$2"
}
