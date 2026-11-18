# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Strict A15W update envelope codec. Never executes or extracts an image.

The fixed OEM-format cipher value is a public format constant, not a device
credential or an authenticity mechanism. SHA256 identifies artifacts only.
"""

import gzip
import hashlib
import io
from pathlib import PurePosixPath
import re
import subprocess
import tarfile

MAX_IMAGE = 8 * 1024 * 1024
MAX_TAR = 16 * 1024 * 1024
KEY = b"AutoPlay9uPT4n17".hex()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def crypt(data, decrypt=False):
    if not 0 < len(data) <= MAX_IMAGE:
        raise ValueError("Invalid image size")
    cut = len(data) // 16 * 16
    result = subprocess.run(
        [
            "openssl",
            "enc",
            "-d" if decrypt else "-e",
            "-aes-128-cbc",
            "-nopad",
            "-K",
            KEY,
            "-iv",
            KEY,
        ],
        input=data[:cut],
        capture_output=True,
        check=True,
    )
    return result.stdout + data[cut:]


def valid_name(name):
    return (name in ("tmp/once.sh", "tmp/finish.sh") or name.startswith("tmp/dextend/")) and (
        str(PurePosixPath(name)) == name
        and not PurePosixPath(name).is_absolute()
        and ".." not in PurePosixPath(name).parts
        and re.fullmatch(r"[A-Za-z0-9_./-]+", name) is not None
    )


def encode(files):
    """files is {safe_relative_name: (bytes, mode)}; only regular files."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, (data, mode) in sorted(files.items()):
            if not valid_name(name) or mode not in (0o600, 0o700, 0o755, 0o644):
                raise ValueError("Unsafe image member")
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(data), mode
            item.uid = item.gid = item.mtime = 0
            archive.addfile(item, io.BytesIO(data))
    if len(raw.getvalue()) > MAX_TAR:
        raise ValueError("Archive too large")
    image = crypt(gzip.compress(raw.getvalue(), mtime=0))
    if decode(image) != files:
        raise ValueError("Image round-trip failed")
    return image


def decode(image):
    # Bounded decompression, including a read past EOF to validate the gzip CRC.
    with gzip.GzipFile(fileobj=io.BytesIO(crypt(image, decrypt=True))) as stream:
        raw = stream.read(MAX_TAR + 1)
    if len(raw) > MAX_TAR:
        raise ValueError("Expanded archive too large")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            if (
                not member.isfile()
                or not valid_name(member.name)
                or member.name in files
                or member.mode not in (0o600, 0o700, 0o755, 0o644)
                or member.uid != 0
                or member.gid != 0
            ):
                raise ValueError("Unsafe or duplicate image member")
            files[member.name] = (archive.extractfile(member).read(), member.mode)
    if not files or "tmp/once.sh" not in files:
        raise ValueError("Missing update entry point")
    return files


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Inspect an A15W image without extracting or executing it"
    )
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    if args.image.stat().st_size > MAX_IMAGE:
        parser.error("Image too large")
    data = args.image.read_bytes()
    entries = decode(data)
    print(
        json.dumps(
            {
                "image_sha256": sha(data),
                "bytes": len(data),
                "members": {
                    n: {"sha256": sha(v), "bytes": len(v), "mode": oct(m)}
                    for n, (v, m) in entries.items()
                },
            },
            indent=2,
        )
    )
