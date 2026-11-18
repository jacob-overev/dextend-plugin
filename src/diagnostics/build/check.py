#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Metadata comparison is not a hardware test.
import importlib.util
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("aoa_abi", root.parents[1] / "aoa/check-abi.py")
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)
for name, reference in json.loads((root / "abi-reference.json").read_text()).items():
    result = abi.inspect(Path(sys.argv[1]) / (name + ".ko"))
    if result != reference:
        raise SystemExit("Driver ABI metadata differs: " + name)
print(
    "All four radio modules match the recorded ABI metadata; hardware validation remains separate."
)
