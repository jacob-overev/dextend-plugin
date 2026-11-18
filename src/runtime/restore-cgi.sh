#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Factory restoration from the Dextend panel
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
work=/tmp/boa/dextend-restore
reply() {
    printf 'Status: %s\r\nContent-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n%s\n' "$1" "$2"
    exit 0
}

# Boa serves the local panel over HTTP. Check the same host forms as
# the paired-phone API before issuing a token or accepting a POST.
host=${HTTP_HOST:-}
name=${host%%:*}
if [ "$name" != "$host" ]; then
    case "${host#*:}" in '' | *[!0-9]*) reply '403 Forbidden' '{"error":"Nieprawidłowy adres panelu."}' ;; esac
fi
case "$name" in
    localhost | autobox.com | www.autobox.com) ;;
    *)
        printf '%s\n' "$name" | awk -F. '
            NF == 4 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ &&
            $3 ~ /^[0-9]+$/ && $4 ~ /^[0-9]+$/ &&
            $1 < 256 && $2 < 256 && $3 < 256 && $4 < 256 { valid = 1 }
            END { exit(!valid || NR != 1) }
        ' || reply '403 Forbidden' '{"error":"Nieprawidłowy adres panelu."}'
        ;;
esac

[ -d "$work" ] && [ ! -L "$work" ] && [ -f "$work/token" ] ||
    reply '503 Service Unavailable' '{"error":"Usługa przywracania nie jest gotowa."}'
token=$(cat "$work/token")
[ "${#token}" -eq 64 ] || reply '503 Service Unavailable' '{"error":"Brak klucza sesji."}'
case "$token" in '' | *[!0-9a-f]*) reply '503 Service Unavailable' '{"error":"Brak klucza sesji."}' ;; esac
state() {
    if [ ! -d "$work/claimed" ]; then
        echo idle
        return
    fi
    if [ ! -f "$work/result" ]; then
        echo checking
        return
    fi
    case "$(sed -n 's/^result=//p' "$work/result")" in
        CHECKING) echo checking ;;
        WRITING) echo writing ;;
        REJECTED) echo rejected ;;
        OEM_RESTORED_RESTART_REQUIRED) echo restored ;;
        *) echo error ;;
    esac
}
case "${REQUEST_METHOD:-}" in
    GET)
        if [ "$(state)" = idle ]; then
            reply '200 OK' "{\"state\":\"idle\",\"token\":\"$token\"}"
        fi
        reply '200 OK' "{\"state\":\"$(state)\"}"
        ;;
    POST) ;;
    *) reply '405 Method Not Allowed' '{"error":"Niedozwolona metoda."}' ;;
esac

[ "${HTTP_ORIGIN:-}" = "http://$host" ] && [ "${HTTP_X_DEXTEND_TOKEN:-}" = "$token" ] ||
    reply '403 Forbidden' '{"error":"Nieprawidłowe żądanie przywrócenia."}'
phrase=PRZYWRÓĆ
[ "${CONTENT_TYPE:-}" = 'text/plain;charset=UTF-8' ] && [ "${CONTENT_LENGTH:-}" = 10 ] &&
    [ "$(dd bs=1 count=10 2>/dev/null)" = "$phrase" ] ||
    reply '400 Bad Request' '{"error":"Wpisz PRZYWRÓĆ, aby potwierdzić."}'
command -v setsid >/dev/null && [ -f "$work/transaction.sh" ] ||
    reply '503 Service Unavailable' '{"error":"Nie można uruchomić usługi przywracania."}'
mkdir "$work/claimed" 2>/dev/null ||
    reply '409 Conflict' '{"error":"Żądanie przywrócenia już istnieje. Sprawdź jego wynik."}'

# Keep the worker and report outside the Dextend install tree. Boa can finish
# the response without waiting for the restore process or holding its stdin.
setsid sh "$work/transaction.sh" web </dev/null >/dev/null 2>&1 &
reply '202 Accepted' '{"state":"checking"}'
