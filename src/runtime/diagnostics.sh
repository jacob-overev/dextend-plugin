#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Bounded, secret-free operational evidence in RAM.
set -u
umask 077
d=/tmp/dextend-diagnostics
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
event() (
    [ ! -L "$d" ] || exit 0
    mkdir -p "$d" || exit 0
    attempts=0
    while ! mkdir "$d/lock" 2>/dev/null; do
        case "${1:-}" in boot | native) ;; *) exit 0 ;; esac
        attempts=$((attempts + 1))
        [ "$attempts" -lt 10 ] || exit 0
        sleep 0.1
    done
    trap 'rmdir "$d/lock"' EXIT
    trap 'exit 0' TERM INT HUP
    for f in events previous boot-events; do
        [ ! -e "$d/$f" ] || regular "$d/$f" || exit 0
        [ ! -L "$d/$f" ] || exit 0
    done
    # Callers pass fixed event names and bounded numeric/enumerated fields.
    case "$*" in *[!a-zA-Z0-9_./:=\ -]*) exit 0 ;; esac
    [ "${#*}" -le 400 ] || exit 0
    if regular "$d/events" && [ "$(wc -c <"$d/events")" -ge 32768 ]; then
        mv -f "$d/events" "$d/previous" || exit 0
    fi
    read -r uptime rest </proc/uptime || uptime=unknown
    printf '%s %s\n' "$uptime" "$*" >>"$d/events"
    # Boot evidence must not disappear under a Wi-Fi reconnect storm. This
    # separate bounded trail contains fixed tokens only and stays in RAM.
    case "${1:-}" in
        boot | native)
            if [ ! -f "$d/boot-events" ] || [ "$(wc -c <"$d/boot-events")" -lt 8192 ]; then
                printf '%s %s\n' "$uptime" "$*" >>"$d/boot-events"
            fi
            ;;
    esac
)
case "${1:-}" in
    event)
        shift
        event "$@"
        ;;
    stream)
        component=${2:-unknown}
        # Do not forward raw daemon output: it can contain SSIDs, MACs or credentials.
        trap 'exit 0' TERM INT HUP
        while IFS= read -r raw; do
            line=$(printf '%s\n' "$raw" | awk '
          /CTRL-EVENT-/ {
            if (match($0,/CTRL-EVENT-[A-Z-]+/)) {
              event=substr($0,RSTART,RLENGTH); gsub(/-/,"_",event)
              detail=""; if(match($0,/reason=[A-Z0-9_]+/))detail=" " substr($0,RSTART,RLENGTH)
              print event detail
            }
            next
          }
          /^DEXTEND_NATIVE_RECEIVER refused stage=[a-z_]+ errno=[0-9]+$/ {print; next}
          /Failed to initialize|Failed to open|Operation not permitted|Permission denied/ {print "INITIALIZATION_ERROR";next}
          /Network is down|No such device/ {print "INTERFACE_UNAVAILABLE"}
        ')
            [ -z "$line" ] || event "$component $line"
        done
        ;;
    report)
        printf 'DEXTEND DIAGNOSTICS\nTime: seconds since boot; RAM events are cleared on restart.\n'
        printf 'boot_id='
        cat /proc/sys/kernel/random/boot_id
        printf 'uptime='
        cat /proc/uptime
        printf 'version='
        head -c 80 /tmp/dextend-service/waiting-version 2>/dev/null || true
        printf '\nINSTALL AND START\n'
        for n in status active pending attempted confirmed service-release; do
            printf '%s=' "$n"
            if regular "/etc/yamaha-sdl/usb-v1/$n"; then
                head -c 128 "/etc/yamaha-sdl/usb-v1/$n" | tr -cd 'A-Za-z0-9_.=:/ \n-'
            else printf 'absent\n'; fi
            printf '\n'
        done
        printf '\nSERVICE\n'
        for n in status ssh-status heartbeat interface address recovery-status; do
            printf '%s=' "$n"
            if regular "/tmp/dextend-service/$n"; then head -c 128 "/tmp/dextend-service/$n" | tr -cd 'A-Za-z0-9_.=:/ \n-'; else printf 'absent\n'; fi
            printf '\n'
        done
        printf '\nUPDATER\n'
        for n in state stage detail; do
            printf '%s=' "$n"
            if regular "/tmp/dextend-updater/$n"; then head -c 128 "/tmp/dextend-updater/$n" | tr -cd 'A-Za-z0-9_.=:/ \n-'; else printf 'absent\n'; fi
            printf '\n'
        done
        printf '\nPROCESSES\n'
        for n in wpa_supplicant dropbearmulti udhcpc receiver-native yamaha-sdl-live ARMadb-driver ARMHiCar; do
            printf '%s=' "$n"
            pidof "$n" 2>/dev/null || printf 'stopped\n'
        done
        printf '\nOEM USB UPDATER\n'
        for n in update_status update_progress; do
            printf '%s=' "$n"
            if regular "/tmp/$n"; then
                # Never copy an unexpected file's contents into the report.
                head -c 32 "/tmp/$n" | awk 'NR==1 && /^[0-9]+$/ && length($0)<=3 {print; ok=1} END{if(!ok)print "invalid"}'
            else printf 'absent\n'; fi
        done
        printf 'installer_lock='
        if [ -d /tmp/dextend-usb-lock ]; then printf 'present\n'; else printf 'absent\n'; fi
        printf 'usb_mount='
        awk '$2=="/mnt/UPAN" {found=1; if($3=="vfat" && $4~/(^|,)rw(,|$)/)print "writable_vfat"; else print "unsupported_or_readonly"} END{if(!found)print "absent"}' /proc/mounts
        printf '\nSPACE\n'
        df -k / /tmp 2>/dev/null
        printf '\nMEMORY\n'
        awk '/^(MemFree|MemAvailable|Buffers|Cached):/' /proc/meminfo
        printf '\nBOOT EVENTS (CURRENT BOOT ONLY)\n'
        if regular "$d/boot-events"; then head -c 8600 "$d/boot-events"; else printf 'unavailable\n'; fi
        printf '\nEVENTS\n'
        for f in previous events; do regular "$d/$f" && tail -c 33500 "$d/$f"; done
        printf '\nPROJECTION EVENTS (seconds since boot)\n'
        projection=/tmp/yamaha-sdl/projection-events
        if regular "$projection"; then
            tail -c 8400 "$projection" | awk 'NF == 3 && $1 ~ /^[0-9]+[.][0-9]+$/ && $2 ~ /^(CP|AA)$/ && $3 ~ /^[A-Z_]+$/'
        fi
        printf '\nUSB AND DRIVER EVENTS\n'
        # Only fixed kernel event categories, not arbitrary kernel messages/identities.
        dmesg 2>/dev/null | awk '
      {
        stamp="kernel"; bus=""; code=""
        if(match($0,/^\[[ 0-9.]+\]/))stamp=substr($0,RSTART,RLENGTH)
        if(match($0,/usb [0-9]+-[0-9.]+/))bus=" " substr($0,RSTART,RLENGTH)
        if(match($0,/error -?[0-9]+/))code=" " substr($0,RSTART,RLENGTH)
      }
      /usb .*USB disconnect/ {print stamp bus code,"USB_DISCONNECT"}
      /usb .*reset .*USB device/ {print stamp bus code,"USB_RESET"}
      /usb .*new .*USB device/ {print stamp bus code,"USB_ATTACH"}
      /ath9k_htc.*Firmware/ {print stamp bus code,"ATH9K_FIRMWARE"}
      /ath9k_htc.*[Tt]imeout|ath9k_htc.*[Ff]ail|ath9k_htc.*[Ee]rror/ {print stamp bus code,"ATH9K_ERROR"}
      /device descriptor read.*error|unable to enumerate USB/ {print stamp bus code,"USB_ENUMERATION_ERROR"}
      /\[otg_set_state\].*Set state:/ {
        if(match($0,/Set state: [a-z_]+/))print stamp,"OTG",substr($0,RSTART+11,RLENGTH-11)
      }
      /Out of memory|Killed process/ {print stamp bus code,"OUT_OF_MEMORY"}
    ' | tail -n 80
        exit 0
        ;;
    *) exit 2 ;;
esac
