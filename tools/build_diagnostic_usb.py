#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# A read-only USB report collector, not a plugin release.
import argparse
from pathlib import Path
import subprocess
from usb_image import encode, sha

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    script = (ROOT / "src/usb/diagnostic.sh").read_bytes()
    subprocess.run(["sh", "-n"], input=script, check=True)
    image = encode({"tmp/once.sh": (script, 0o755)})
    output.mkdir(parents=True, exist_ok=False)
    (output / "A15W_Update.img").write_bytes(image)
    (output / "SHA256SUMS").write_text(f"{sha(image)}  A15W_Update.img\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
