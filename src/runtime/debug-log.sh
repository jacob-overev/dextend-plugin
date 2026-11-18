#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Call with fixed event names and bounded state or numeric values.
debug() {
    [ ! -f /tmp/dextend-service/diagnostics.sh ] || sh /tmp/dextend-service/diagnostics.sh event runtime "$@" || true
    debug_dir=${YAMAHA_RUNTIME:-/tmp/yamaha-sdl}/usb-debug
    [ -d "$debug_dir" ] || return 0
    {
        printf '%s %-26s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${0##*/}" "$*" >>"$debug_dir/services.log"
    } 2>/dev/null || true
}

# Classify factory receiver messages; the original lines never leave the pipe.
debug_receiver() {
    receiver=$1
    awk '
        /^AirPlay session started$/ { event = "session-started" }
        /Screen stream started/ { event = "screen-started" }
        /Exit Carplay code|main quit/ { event = "receiver-exit" }
        /CarPlay iAP2 main start/ { event = "iap2-started" }
        /IAP2 SchedulDone stat: AuthSuccess/ { event = "iap2-authenticated" }
        /WriteOne fail|ReadOne fail/ { event = "transport-error" }
        {
            if (event != "" && event != previous) { print event; fflush(); previous = event }
            event = ""
        }
    ' | while IFS= read -r record; do debug "receiver=$receiver event=$record"; done
}
