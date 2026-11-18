#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Sign a verified distribution IMG. The private key never enters build artifacts."""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
from usb_image import decode


def sign(directory, key):
    image = (directory / "A15W_Update.img").read_bytes()
    if not 0 < len(image) <= 2097152:
        raise ValueError("IMG exceeds the network updater budget")
    members = decode(image)
    version, sequence = members["tmp/dextend/release/version.txt"][0].decode().splitlines()
    if (directory / "VERSION").read_text().strip() != version:
        raise ValueError("Version mismatch")
    message = f"DEXTEND-IMG-1\n{version}\n{sequence}\n{len(image)}\n{hashlib.sha256(image).hexdigest()}\n".encode()
    # OpenSSL needs a seekable input for Ed25519; use only public message data.
    temporary = directory / ".update-message"
    temporary.write_bytes(message)
    try:
        signature = subprocess.check_output(
            ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key), "-in", str(temporary)]
        )
    finally:
        temporary.unlink()
    if len(signature) != 64:
        raise ValueError("Expected an Ed25519 signature")
    public = subprocess.check_output(
        ["openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"]
    )[-32:]
    header = (Path(__file__).resolve().parents[1] / "src/native/update-key.h").read_text()
    expected = bytes(map(int, re.search(r"\{([^}]+)\}", header)[1].split(",")))
    if public != expected:
        raise ValueError("Signing key does not match the key embedded in the receiver")
    (directory / "UPDATE.manifest").write_bytes(message + signature.hex().encode() + b"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    sign(args.directory, args.key)
