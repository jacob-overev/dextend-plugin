#!/bin/sh
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

set -eu
src=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python3 "$src/tools/check_licenses.py"
python3 "$src/tests/test_package_licenses.py"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
cc -O2 -std=c11 -Wall -Wextra -Werror "$src/src/native/probe.c" -o "$tmp/bridge"
export YAMAHA_PROBE_CMD="$tmp/bridge"
python3 "$src/tools/build-waiting.py" "$tmp/waiting" >/dev/null
export YAMAHA_WAITING_FRAME="$tmp/waiting/waiting.h264"
YAMAHA_PROBE_SAMPLE="$YAMAHA_WAITING_FRAME" python3 "$src/tests/test_probe.py"
python3 "$src/tests/test_live.py"
python3 "$src/tests/test_android_auto.py"
python3 "$src/tests/test_auto_phone.py"
python3 "$src/tests/test_recovery.py"
cc -Os -Wall -Wextra -Werror "$src/src/native/bluetooth-autoconnect.c" -o "$tmp/bluetooth-autoconnect"
YAMAHA_BT_CONTROL_CMD="$tmp/bluetooth-autoconnect" python3 "$src/tests/test_bluetooth_autoconnect.py"
python3 "$src/tests/test_receiver_native.py"
python3 "$src/tests/test_phone_policy.py"
python3 "$src/tests/test_usb_logging.py"
python3 "$src/tests/test_updater.py"
python3 "$src/tests/test_usb_packages.py"
python3 "$src/tests/test_diagnostic_usb.py"
python3 "$src/tests/test_service.py"
python3 "$src/tests/test_service_recovery.py"
python3 "$src/tests/test_diagnostics.py"
sh "$src/src/aoa/test.sh"
for file in "$src"/src/runtime/*.sh "$src"/packaging/*.in "$src"/tools/*.sh "$src"/src/usb/*.sh "$src"/src/diagnostics/runtime/*.sh; do sh -n "$file"; done
