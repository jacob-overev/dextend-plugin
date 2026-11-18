#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Reversible key addition for an already interface-bound SSH server.
set -eu
umask 077
s=/etc/yamaha-sdl/service
key=/tmp/dextend-service/authorized_keys
file=/root/.ssh/authorized_keys
helper=/tmp/dextend-service/service-key
[ -x "$helper" ] || helper=/tmp/yamaha-sdl/service-key
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
[ -d /root ] && [ ! -L /root ] && [ -d /root/.ssh ] && [ ! -L /root/.ssh ] || exit 1
[ ! -L "$file" ] && [ ! -L /root/.ssh/authorized_keys.dextend-new ] || exit 1
case "${1:-}" in
    add)
        [ ! -e "$s/borrowed.before" ] || exit 0
        regular "$key" || exit 1
        if regular "$file"; then
            [ "$(wc -c <"$file")" -le 60000 ] || exit 1
            blob=$(awk '{print $2}' "$key")
            if awk -v k="$blob" '{for(i=1;i<NF;i++)if($i=="ssh-ed25519" && $(i+1)==k)found=1} END{exit !found}' "$file"; then exit 0; fi
            cp -p "$file" "$s/borrowed.before"
            printf 'existing\n' >"$s/borrowed.kind"
        elif [ ! -e "$file" ]; then
            : >"$s/borrowed.before"
            printf 'absent\n' >"$s/borrowed.kind"
        else exit 1; fi
        cp "$key" "$s/borrowed.key"
        cp -p "$s/borrowed.before" "$s/borrowed.after"
        sh /tmp/dextend-service/keys.sh "$s/borrowed.after" "$s/borrowed.key"
        sync
        cp -p "$s/borrowed.after" /root/.ssh/authorized_keys.dextend-new
        mv /root/.ssh/authorized_keys.dextend-new "$file"
        sync
        ;;
    restore)
        [ -e "$s/borrowed.before" ] || exit 0
        # Restore identical files byte-for-byte; reconcile later edits by removing only
        # the exact inserted bytes. Ambiguous or edited entries keep their journal.
        regular "$s/borrowed.after" && regular "$s/borrowed.kind" || exit 1
        if regular "$file" && cmp -s "$file" "$s/borrowed.after"; then
            if [ "$(cat "$s/borrowed.kind")" = absent ]; then
                rm "$file"
            else
                cp -p "$s/borrowed.before" /root/.ssh/authorized_keys.dextend-new
                mv /root/.ssh/authorized_keys.dextend-new "$file"
            fi
        elif regular "$file" && cmp -s "$file" "$s/borrowed.before"; then
            :
        elif [ ! -e "$file" ] && [ "$(cat "$s/borrowed.kind")" = absent ]; then
            :
        elif regular "$file" && [ -x "$helper" ]; then
            cp -p "$file" /root/.ssh/authorized_keys.dextend-new
            if ! "$helper" "$s/borrowed.before" "$s/borrowed.after" "$file" >/root/.ssh/authorized_keys.dextend-new; then
                rm -f /root/.ssh/authorized_keys.dextend-new
                exit 1
            fi
            mv /root/.ssh/authorized_keys.dextend-new "$file"
        else exit 1; fi
        rm -f "$s/borrowed.before" "$s/borrowed.after" "$s/borrowed.kind" "$s/borrowed.key"
        sync
        ;;
    *) exit 2 ;;
esac
