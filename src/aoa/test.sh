#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

set -eu
src=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
cc -std=gnu11 -O1 -g -Wall -Wextra -Werror -Wno-unused-parameter \
    -iquote "$src" -iquote "$src/tests" \
    -fsanitize=address,undefined "$src/tests/test_driver.c" -o "$tmp/test-driver"
"$tmp/test-driver"
python3 "$src/check-abi.py" --self-test
