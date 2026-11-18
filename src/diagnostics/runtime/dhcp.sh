#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# A diagnostic lease never replaces OEM routes or DNS.
set -eu
r=/tmp/dextend-service
actual=$("$r/debug-api" --iface) || exit 1
[ -n "$actual" ] && [ "${interface:-}" = "$actual" ] || exit 1
[ ! -f "$r/diagnostics.sh" ] || sh "$r/diagnostics.sh" event dhcp "event=${1:-unknown}" || true
case "${1:-}" in
    bound | renew)
        # Reject malformed DHCP values before passing them as ifconfig arguments.
        for value in "${ip:-}" "${subnet:-255.255.255.0}"; do
            printf '%s\n' "$value" | awk -F. 'NF!=4{exit 1}{for(i=1;i<=4;i++)if($i!~/^[0-9]+$/ || $i>255)exit 1}' || exit 1
        done
        ifconfig "$actual" "$ip" netmask "${subnet:-255.255.255.0}" up
        ;;
    deconfig) ifconfig "$actual" 0.0.0.0 up ;;
esac
