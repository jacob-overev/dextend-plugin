#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Merge the public client key without changing existing key lines
set -eu
file=${1:?authorized_keys file}
key=${2:?public key file}
[ -f "$file" ] && [ ! -L "$file" ] && [ -f "$key" ] && [ ! -L "$key" ] || exit 1
[ "$(wc -l <"$key")" -eq 1 ] || exit 1
set -- $(cat "$key")
[ "$#" -eq 3 ] && [ "$1" = ssh-ed25519 ] && [ "$3" = dextend-service ] || exit 1
blob=$2
if awk -v key="$blob" '{for(i=1;i<NF;i++)if($i=="ssh-ed25519" && $(i+1)==key)found=1} END{exit !found}' "$file"; then exit 0; fi
[ "$(wc -c <"$file")" -eq 0 ] || printf '\n' >>"$file"
cat "$key" >>"$file"
