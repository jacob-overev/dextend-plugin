#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Build host artifacts from the checked-out sources and local AOA driver.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
case "$#" in
    1 | 2) ;;
    *)
        echo 'Usage: build-release.sh NEW_ABSOLUTE_OUTPUT [SEQUENCE]' >&2
        exit 2
        ;;
esac
out=$1
shift
if [ "$#" -eq 1 ]; then set -- --sequence "$1"; fi
version=$(cat "$root/VERSION")
case "$out" in /*) ;; *)
    echo 'Absolute output required' >&2
    exit 2
    ;;
esac
mkdir "$out"
aoa=$root/src/aoa
sh "$aoa/build-module.sh" "$out/module"
sh "$root/tools/build-userspace.sh" "$out/userspace"
python3 "$root/tools/build-waiting.py" "$out/waiting" --version "$version"
python3 "$root/tools/package.py" --userspace "$out/userspace" \
    --module "$out/module/yamaha_aoa.ko.EXPERIMENTAL" \
    --waiting "$out/waiting/waiting.h264" --version "$version" --output "$out/package"
sh "$root/src/diagnostics/build/build.sh" "$out/service" "$out/module/kernel"
"$YAMAHA_MUSL_PREFIX/bin/musl-gcc" -static -Os -Wall -Wextra -Werror \
    -Wl,-z,max-page-size=4096,-z,common-page-size=4096 "$root/src/native/debug-api.c" -o "$out/service/bin/debug-api"
arm-linux-gnueabi-strip "$out/service/bin/debug-api"
DEXTEND_SERVICE_BUILD="$out/service" python3 "$root/tests/test_service.py" >"$out/service-validation.log" 2>&1 || {
    cat "$out/service-validation.log" >&2
    exit 1
}
cat "$out/service-validation.log"
python3 "$root/tools/service_package.py" "$out/service" "$out/service/bin/debug-api" "$out/package/service-runtime.tar.lzma" "$out/userspace"
if [ -f "$root/releases/A15W_Update.img" ]; then
    set -- --previous-img "$root/releases/A15W_Update.img" "$@"
fi
python3 "$root/tools/build_usb.py" --package "$out/package" \
    --output "$out/usb" --version "$version" \
    "$@"
validation="$out/restore-validation.log"
if ! python3 "$root/tests/test_usb_packages.py" --check-release-img "$out/usb/install/A15W_Update.img" >"$validation" 2>&1; then
    cat "$validation" >&2
    exit 1
fi
cat "$validation"
mkdir "$out/distribution"
cp "$out/usb/install/A15W_Update.img" "$out/usb/install/SHA256SUMS" "$out/distribution/"
printf '%s\n' "$version" >"$out/distribution/VERSION"
(cd "$out/distribution" && sha256sum -c SHA256SUMS)

python3 "$root/tools/sign_update.py" "$out/distribution" --key "${DEXTEND_UPDATE_SIGNING_KEY:?Set the offline release signing key path}"
cp "$root/RELEASE-NOTES.json" "$out/distribution/NOTES.json"
