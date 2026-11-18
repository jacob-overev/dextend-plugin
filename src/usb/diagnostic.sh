#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Read installation evidence; write only a report on removable USB.
# Exit 1 intentionally: the OEM updater must not reach its firmware-copy phase.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
usb=/mnt/UPAN
w=/tmp/dextend-updater
s=/etc/yamaha-sdl/usb-v1
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
state() {
    printf '%s=' "$1"
    if regular "$2"; then
        # Only bounded status tokens, never arbitrary configuration or credentials.
        head -c 160 "$2" | tr -cd 'A-Za-z0-9_.= -\n' | head -n 2
        printf '\n'
    else printf 'absent\n'; fi
}
metadata() {
    printf '%s ' "$1"
    if [ -L "$1" ]; then
        printf 'symlink\n'
    elif regular "$1"; then
        printf 'bytes='
        wc -c <"$1"
    elif [ -d "$1" ]; then
        printf 'directory\n'
    else printf 'absent\n'; fi
}
[ -d "$usb" ] && [ ! -L "$usb" ] || exit 1
awk '$2=="/mnt/UPAN" && $3=="vfat" && $4~/(^|,)rw(,|$)/{ok=1} END{exit !ok}' /proc/mounts || exit 1
out=$(mktemp -d "$usb/dextend-diagnostics.XXXXXX") || exit 1
{
    printf 'DEXTEND INSTALL DIAGNOSTICS 1\nmode=read_only\n'
    state boot_id /proc/sys/kernel/random/boot_id
    state updater_state "$w/state"
    state updater_detail "$w/detail"
    state updater_stage "$w/stage"
    for n in format status active previous pending confirmed transaction service-release; do state "$n" "$s/$n"; done
    printf '\nINSTALL RESULT\n'
    if regular "$w/DEXTEND-RESULT.txt"; then
        head -c 8192 "$w/DEXTEND-RESULT.txt" | awk '/^(operation|version|result|detail|profile_matches|rcs|flash_free_kib|module_version|hook)=[A-Za-z0-9_. -]+$/{print}'
    fi
    printf '\nWORKER ERRORS\n'
    if regular "$w/worker.log"; then
        # Never include shell tracing, JSON, SSIDs, passwords, keys or log payloads.
        # Classify errors without copying their arbitrary message text.
        head -c 65536 "$w/worker.log" | awk '
          /^(cp|mv|cmp|awk|sh|sha256sum|find|wc|mkdir|chmod|sync|rm|tar|lzma):/ || /radio-names.sh: (line )?[0-9]+:/ {
            tool=$1; sub(/:$/, "", tool); reason="other"
            if($0~/radio-names.sh:/)tool="radio-script"
            if($0~/[Nn]o space left/)reason="no_space"
            else if($0~/[Dd]evice or resource busy/)reason="busy_mount"
            else if($0~/[Pp]ermission denied/)reason="permission"
            else if($0~/[Rr]ead-only file system/)reason="read_only"
            else if($0~/[Nn]o such file/)reason="missing_file"
            else if($0~/not found/)reason="missing_command"
            else if($0~/[Ii]nvalid/)reason="invalid"
            target="unknown"
            if(index($0,"riddle.conf"))target="riddle.conf"
            else if(index($0,"hostapd.conf"))target="hostapd.conf"
            else if(index($0,"bluetooth_name"))target="bluetooth_name"
            else if(index($0,"wifi_name"))target="wifi_name"
            else if(index($0,"radio-output"))target="radio-output"
            else if(index($0,"radio.new"))target="radio.new"
            printf "line=%d tool=%s reason=%s target=%s\n",NR,tool,reason,target
          }
          /^DEXTEND: [A-Z0-9_]+$/{print}
        '
    fi
    printf '\nRADIO FILE STATE\n'
    for n in riddle.conf hostapd.conf wifi_name bluetooth_name .custom_wifi_name .custom_bluetooth_name; do
        metadata "/etc/$n"
        metadata "$s/radio/$n"
        metadata "$s/radio.new/$n"
        if regular "/etc/$n" && regular "$s/radio/$n"; then
            if cmp -s "/etc/$n" "$s/radio/$n"; then
                printf '%s=original_bytes\n' "$n"
            else printf '%s=different_bytes\n' "$n"; fi
        fi
    done
    metadata "$s/radio-output"
    for n in presence SHA256SUMS; do metadata "$s/radio/$n"; done
    if regular "$s/radio/presence"; then
        printf 'presence_lines='
        wc -l <"$s/radio/presence"
    fi
    if regular "$s/radio/SHA256SUMS"; then
        printf 'checksum_lines='
        wc -l <"$s/radio/SHA256SUMS"
        for n in riddle.conf hostapd.conf wifi_name bluetooth_name .custom_wifi_name .custom_bluetooth_name presence; do
            expected=$(awk -v n="$n" '$2==n && NF==2 {print $1}' "$s/radio/SHA256SUMS")
            actual=
            if regular "$s/radio/$n"; then actual=$(sha256sum "$s/radio/$n" | awk '{print $1}'); fi
            if [ -n "$actual" ] && [ "$actual" = "$expected" ]; then
                printf 'checksum_%s=ok\n' "$n"
            else printf 'checksum_%s=mismatch\n' "$n"; fi
        done
    fi
    if [ -d "$s/radio" ] && [ ! -L "$s/radio" ]; then
        printf 'baseline_entry_count='
        find "$s/radio" -mindepth 1 | wc -l
    fi
    printf '\nMOUNT TARGETS\n'
    awk '$5=="/etc" || $5=="/etc/riddle.conf" || $5=="/etc/hostapd.conf" || $5=="/etc/wifi_name" || $5=="/etc/bluetooth_name" {print "mount=" $5 " options=" $6}' /proc/self/mountinfo
    printf '\nSPACE\n'
    df -Pk /etc /tmp
    printf '\nTOOLS\n'
    for n in awk cmp find wc sha256sum cp mv; do command -v "$n" || true; done
    printf '\nEND OF REPORT\n'
} >"$out/REPORT.txt.new"
sync
mv "$out/REPORT.txt.new" "$out/REPORT.txt"
sync
exit 1
