#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Unpack only the checked release's bounded service archive into RAM.
set -eu
umask 077
release=${DEXTEND_RELEASE_DIR:?}
s=/etc/yamaha-sdl/service
r=/tmp/dextend-service
[ -f "$release/service-runtime.tar.lzma" ] && [ ! -L "$release/service-runtime.tar.lzma" ] || exit 0
if [ -d "$r" ] && [ ! -L "$r" ]; then
    sh "$r/service.sh" watch >/dev/null 2>&1 </dev/null &
    sh "$r/start-updater.sh" >/dev/null 2>&1 || true
    exit 0
fi
[ ! -e "$r" ] || exit 1
work=$(mktemp -d /tmp/dextend-service-stage.XXXXXX)
trap 'rm -rf "$work"' EXIT
lzma -dc "$release/service-runtime.tar.lzma" | head -c 4194305 >"$work/service.tar"
[ "$(wc -c <"$work/service.tar")" -le 4194304 ] || exit 1
mkdir "$work/unpacked"
tar -xf "$work/service.tar" -C "$work/unpacked"
(cd "$work/unpacked" && sha256sum -c SHA256SUMS >/dev/null)
[ ! -L "$s" ] && [ -f "$s/format" ] && [ ! -L "$s/format" ] && [ "$(cat "$s/format")" = dextend-service-v1 ] || exit 1
chmod 700 "$work/unpacked"/*.sh "$work/unpacked/debug-api" "$work/unpacked/dropbearmulti" "$work/unpacked/wpa_supplicant" "$work/unpacked/service-key" "$work/unpacked/updater-http"
mv "$work/unpacked" "$r"
sh "$r/diagnostics.sh" event service unpacked || true
sh "$r/service.sh" watch >/dev/null 2>&1 </dev/null &
sh "$r/start-updater.sh" >/dev/null 2>&1 || true
# Readiness means a live supervisor, not a promise of a Wi-Fi lease without setup.
i=0
while [ "$i" -lt 5 ]; do
    [ ! -f "$r/heartbeat" ] || exit 0
    sleep 1
    i=$((i + 1))
done
exit 1
