#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Local API v1, used by the local panel bridge.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
w=/tmp/dextend-updater
. "$(dirname "$0")/updater-events.sh"
origin=${HTTP_ORIGIN:-}
# The local panel uses the same host as this request, on the OEM HTTP port.
# The browser supplies Host; no adapter address list or public-origin CORS.
panel_host=${HTTP_HOST%:*}
allowed=http://$panel_host
reply() {
    case "$1" in 4* | 5*)
        if [ "${authorized:-0}" = 1 ]; then
            error_code=$(printf '%s' "$2" | sed -n 's/^{"error":"\([A-Za-z0-9_]*\)"}$/\1/p')
            update_event "$error_code"
        fi
        ;;
    esac
    printf 'HTTP/1.1 %s\r\nConnection: close\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n' "$1"
    if [ "$origin" = "$allowed" ]; then
        printf 'Access-Control-Allow-Origin: %s\r\nVary: Origin\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type, X-Dextend-Token\r\n' "$origin"
    fi
    printf '\r\n%s\n' "$2"
    exit 0
}
case "$origin" in '' | "$allowed") ;; *) reply '403 Forbidden' '{"error":"origin"}' ;; esac
uri=${REQUEST_URI:-}
[ "$REQUEST_METHOD" != OPTIONS ] || reply '204 No Content' ''
[ -f "$w/token" ] || reply '503 Service Unavailable' '{"error":"not_ready"}'
token=$(cat "$w/token")
[ "${#token}" = 64 ] || reply '503 Service Unavailable' '{"error":"not_ready"}'
case "$token" in *[!0-9a-f]*) reply '503 Service Unavailable' '{"error":"not_ready"}' ;; esac
state=$(cat "$w/state")
info() {
    version=unknown
    sequence=0
    confirmed=false
    s=/etc/yamaha-sdl/usb-v1
    active=$(cat "$s/active" 2>/dev/null || true)
    [ "$active" != none ] || active=$(cat "$s/service-release" 2>/dev/null || true)
    case "$active" in '' | *[!0-9a-f]*) active=none ;; esac
    if [ "${#active}" = 64 ] && [ -f "$s/releases/$active/version.txt" ]; then
        version=$(sed -n '1p' "$s/releases/$active/version.txt")
        sequence=$(sed -n '2p' "$s/releases/$active/version.txt")
        [ "$(cat "$s/status" 2>/dev/null)" != ACTIVE ] || confirmed=true
    fi
    case "$version" in '' | *[!A-Za-z0-9._-]*) version=unknown ;; esac
    case "$sequence" in '' | *[!0-9]*) sequence=0 ;; esac
    boot=$(cat /proc/sys/kernel/random/boot_id)
    received=0
    [ ! -f "$w/image.img" ] || received=$(wc -c <"$w/image.img" | tr -d ' ')
    detail=$(cat "$w/detail" 2>/dev/null || true)
    case "$detail" in *[!A-Z0-9_]*) detail=UNKNOWN ;; esac
    stage=$(cat "$w/stage" 2>/dev/null || true)
    case "$stage" in idle | receiving | checking | unpacking | installing | ready | restarting) ;; *) stage=unknown ;; esac
    install_detail=$(sed -n 's/^detail=//p' "$w/DEXTEND-RESULT.txt" 2>/dev/null || true)
    case "$install_detail" in *[!A-Z0-9_]*) install_detail=UNKNOWN ;; esac
    compatible=false
    if [ "$(cat /etc/box_product_type 2>/dev/null)" = A15W ] &&
        { [ "$(cat /etc/software_version 2>/dev/null)" = 2026.07.31.1733 ] ||
            [ "$(cat /etc/software_version 2>/dev/null)" = 2025.10.15.1127 ]; } &&
        [ "$(uname -r)" = 3.14.52+g94d07bb ]; then compatible=true; fi
    reply '200 OK' "{\"product\":\"Dextend\",\"protocol\":1,\"diagnostics\":1,\"stage\":\"$stage\",\"install_detail\":\"$install_detail\",\"version\":\"$version\",\"sequence\":\"$sequence\",\"confirmed\":$confirmed,\"compatible\":$compatible,\"boot\":\"$boot\",\"state\":\"$state\",\"detail\":\"$detail\",\"received\":$received,\"token\":\"$token\"}"
}
if [ "$REQUEST_METHOD" = GET ]; then
    case "$uri" in
        /v1/log)
            events=$(if [ -f "$w/events.log" ]; then awk 'BEGIN{printf "["} NF==2 && $1~/^[0-9]+$/ && $2~/^[A-Za-z0-9_]+$/ && length($2)<=48 {printf "%s{\"at\":%s,\"code\":\"%s\"}",n++?",":"",$1,$2} END{printf "]"}' "$w/events.log"; else printf '[]'; fi)
            reply '200 OK' "{\"events\":$events}"
            ;;
        /v1/info | /v1/status) info ;; *) reply '404 Not Found' '{"error":"route"}' ;; esac
fi
[ "$REQUEST_METHOD" = POST ] && [ -n "$origin" ] && [ "${HTTP_X_DEXTEND_TOKEN:-}" = "$token" ] || reply '403 Forbidden' '{"error":"token"}'
authorized=1
mkdir "$w/api-lock" 2>/dev/null || reply '409 Conflict' '{"error":"busy"}'
trap 'rmdir "$w/api-lock"' EXIT
trap 'exit 1' HUP INT TERM ALRM
state=$(cat "$w/state")
case "$uri" in
    /v1/begin)
        case "$state" in idle | receiving | rejected) ;; *) reply '409 Conflict' '{"error":"busy"}' ;; esac
        [ "$CONTENT_LENGTH" -ge 140 ] && [ "$CONTENT_LENGTH" -le 511 ] || reply '400 Bad Request' '{"error":"manifest"}'
        dd bs=1 count="$CONTENT_LENGTH" of="$w/manifest.new" 2>/dev/null
        [ "$(wc -c <"$w/manifest.new")" -eq "$CONTENT_LENGTH" ] || reply '400 Bad Request' '{"error":"truncated"}'
        "$w/updater-http" --verify "$w/manifest.new" || reply '403 Forbidden' '{"error":"signature"}'
        # Signed canonical manifest: product, version, sequence, size, SHA256, signature.
        awk 'NR==1 && $0!="DEXTEND-IMG-1"{exit 1}
      NR==2 && ($0!~/^[A-Za-z0-9._-]+$/ || length($0)>16){exit 1}
      NR==3 && ($0!~/^[0-9]+$/ || length($0)>12){exit 1}
      NR==4 && ($0!~/^[0-9]+$/ || $0<1 || $0>2097152){exit 1}
      NR==5 && ($0!~/^[0-9a-f]+$/ || length($0)!=64){exit 1}
      END{if(NR!=6)exit 1}' "$w/manifest.new" || reply '400 Bad Request' '{"error":"manifest"}'
        memory=$(awk '/^MemFree:|^Buffers:|^Cached:/{sum+=$2} END{print sum+0}' /proc/meminfo)
        [ "$memory" -ge 16384 ] || reply '409 Conflict' '{"error":"memory"}'
        mv "$w/manifest.new" "$w/manifest"
        : >"$w/image.img"
        : >"$w/detail"
        : >"$w/events.log"
        echo receiving >"$w/state"
        update_stage receiving MANIFEST_SIGNATURE_OK
        reply '200 OK' '{"state":"receiving","received":0}'
        ;;
    /v1/chunk?offset=*)
        [ "$state" = receiving ] || reply '409 Conflict' '{"error":"state"}'
        offset=${uri#*=}
        case "$offset" in '' | *[!0-9]*) reply '400 Bad Request' '{"error":"offset"}' ;; esac
        [ "${#offset}" -le 7 ] || reply '400 Bad Request' '{"error":"offset"}'
        actual=$(wc -c <"$w/image.img")
        [ "$offset" -eq "$actual" ] || reply '409 Conflict' '{"error":"offset"}'
        size=$(sed -n '4p' "$w/manifest")
        [ "$CONTENT_LENGTH" -gt 0 ] && [ "$((actual + CONTENT_LENGTH))" -le "$size" ] || reply '400 Bad Request' '{"error":"size"}'
        dd bs=1 count="$CONTENT_LENGTH" of="$w/chunk" 2>/dev/null
        [ "$(wc -c <"$w/chunk")" -eq "$CONTENT_LENGTH" ] || reply '400 Bad Request' '{"error":"truncated"}'
        cat "$w/chunk" >>"$w/image.img"
        rm "$w/chunk"
        reply '200 OK' "{\"received\":$((actual + CONTENT_LENGTH))}"
        ;;
    /v1/install)
        [ "$CONTENT_LENGTH" = 0 ] && [ "$state" = receiving ] || reply '409 Conflict' '{"error":"state"}'
        [ "$(wc -c <"$w/image.img")" -eq "$(sed -n '4p' "$w/manifest")" ] || reply '400 Bad Request' '{"error":"incomplete"}'
        "$w/updater-http" --verify "$w/manifest" || reply '403 Forbidden' '{"error":"signature"}'
        [ "$(sha256sum "$w/image.img" | awk '{print $1}')" = "$(sed -n '5p' "$w/manifest")" ] || reply '400 Bad Request' '{"error":"checksum"}'
        update_stage checking IMAGE_SHA256_OK
        echo checking >"$w/state"
        setsid sh "$w/updater-worker.sh" </dev/null >"$w/worker.log" 2>&1 &
        reply '202 Accepted' '{"state":"checking"}'
        ;;
    /v1/reboot)
        [ "$CONTENT_LENGTH" = 0 ] && [ "$state" = ready ] || reply '409 Conflict' '{"error":"state"}'
        update_stage restarting AUTOMATIC_RESTART
        echo restarting >"$w/state"
        setsid sh -c 'sleep 3; sync; reboot' </dev/null >/dev/null 2>&1 &
        reply '202 Accepted' '{"state":"restarting"}'
        ;;
    /v1/cancel)
        case "$state" in idle | receiving | rejected) ;; *) reply '409 Conflict' '{"error":"busy"}' ;; esac
        rm -f "$w/image.img" "$w/manifest" "$w/chunk"
        echo idle >"$w/state"
        reply '200 OK' '{"state":"idle"}'
        ;;
    *) reply '404 Not Found' '{"error":"route"}' ;;
esac
