#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Only a fully authenticated IMG reaches the OEM decoder.
set -eu
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
w=/tmp/dextend-updater
owned=0
. "$(dirname "$0")/updater-events.sh"
fail() {
    update_event "$1"
    echo "$1" >"$w/detail"
    echo "$2" >"$w/state"
    exit 1
}
finish() {
    code=$?
    if [ "$code" != 0 ] && [ "$(cat "$w/state")" = checking ]; then
        update_event WORKER_FAILED
        echo WORKER_FAILED >"$w/detail"
        echo rejected >"$w/state"
    fi
    if [ "$code" != 0 ] && [ "$(cat "$w/state")" = installing ]; then
        update_event WORKER_INTERRUPTED
        echo WORKER_INTERRUPTED >"$w/detail"
        echo error >"$w/state"
    fi
    # Retain transaction evidence after writes; no blind retry or cleanup.
    if [ "$owned" = 1 ] && [ "$(cat "$w/state")" = rejected ]; then rm -rf "$w/extracted"; fi
}
trap finish EXIT
trap 'exit 1' HUP INT TERM
"$w/updater-http" --verify "$w/manifest" || fail SIGNATURE rejected
[ "$(sha256sum "$w/image.img" | awk '{print $1}')" = "$(sed -n '5p' "$w/manifest")" ] || fail CHECKSUM rejected
[ ! -d /tmp/dextend-usb-lock ] || fail ANOTHER_INSTALLER rejected
mkdir "$w/extracted" || fail STAGING_EXISTS rejected
owned=1
cd "$w"
update_stage unpacking SIGNATURE_AND_SHA256_OK
ARMimg_maker ./image.img || fail DECODE_FAILED rejected
[ -f update.tar.gz ] || fail DECODE_FAILED rejected
# The build strictly validates archive paths/types before signing the IMG.
tar -xzf update.tar.gz -C "$w/extracted" || fail UNPACK_FAILED rejected
p=$w/extracted/tmp/dextend
[ -f "$p/transaction.sh" ] || fail INVALID_IMG rejected
(cd "$p" && sha256sum -c BUNDLE.sha256 >/dev/null) || fail BUNDLE_CHECKSUM rejected
[ "$(sed -n '1p' "$p/release/version.txt")" = "$(sed -n '2p' "$w/manifest")" ] &&
    [ "$(sed -n '2p' "$p/release/version.txt")" = "$(sed -n '3p' "$w/manifest")" ] || fail VERSION_MISMATCH rejected
# Use our own transaction, not OEM OTA copying/deletion/reboot side effects.
update_stage installing INSTALL_PREFLIGHT
echo installing >"$w/state"
if ! sh "$p/transaction.sh" ota; then
    result=$(sed -n 's/^result=//p' "$w/DEXTEND-RESULT.txt" 2>/dev/null || true)
    detail=$(sed -n 's/^detail=//p' "$w/DEXTEND-RESULT.txt" 2>/dev/null || true)
    case "$detail" in '' | *[!A-Z0-9_]*) detail=INSTALL_FAILED ;; esac
    if [ "$result" = REJECTED ]; then fail "$detail" rejected; fi
    fail "$detail" error
fi
grep -qx result=FILES_COMMITTED "$w/DEXTEND-RESULT.txt" || fail INSTALL_UNCONFIRMED error
sync
echo READY_TO_RESTART >"$w/detail"
update_stage ready FILES_COMMITTED
echo ready >"$w/state"
