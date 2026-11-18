#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Assemble an offline development package from explicit local build outputs.

Assembles artifacts only. Installation and hardware validation are separate.
"""

import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path
import tarfile
from check_licenses import OWN_LICENSE, validate
from service_package import render_panel_version
from build_usb import MAX_RUNTIME, restore_inputs

ROOT = Path(__file__).resolve().parents[1]
BINS = (
    "yamaha-sdl-live",
    "iphone-usb-role",
    "bluetooth-autoconnect",
    "receiver-native",
    "phone-policy",
    "waiting-frame",
    "updater-http",
    "service-key",
)
WAITING_FILES = ("waiting-strip.bin", "waiting-font.bin", "waiting-version")
COMPACT_WAITING = "waiting-2025.10.15.1127.h264"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Expected a regular non-symlink file: {path.name}")
    return path.read_bytes()


def package(userspace, module, waiting, output, version=None):
    validate()
    if version is None:
        version = (ROOT / "VERSION").read_text().strip()
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new directory")
    members = {p.name: regular(p) for p in sorted((ROOT / "src/runtime").glob("*.sh"))}
    members.update({"restore/" + name: data for name, data in restore_inputs(version).items()})
    for p in sorted((ROOT / "src/web").rglob("*")):
        if p.is_file():
            members["web/" + p.relative_to(ROOT / "src/web").as_posix()] = regular(p)
    for name in BINS:
        members[name] = regular(userspace / name)
    members["yamaha_aoa.ko"] = regular(module)
    members["waiting.h264"] = regular(waiting)
    members[COMPACT_WAITING] = regular(waiting.with_name(COMPACT_WAITING))
    if any(not 0 < len(members[name]) <= 131072 for name in ("waiting.h264", COMPACT_WAITING)):
        raise ValueError("Waiting frame must fit the 128 KiB bridge limit")
    for name in WAITING_FILES:
        members[name] = regular(waiting.with_name(name))
    if members["waiting-version"] != (version + "\n").encode():
        raise ValueError("Waiting frame version does not match the package version")
    if (
        len(members["waiting-strip.bin"]) != 160 * 96 * 3 // 2
        or len(members["waiting-font.bin"]) != 95 * 7 * 12
    ):
        raise ValueError("Unexpected waiting frame renderer inputs")
    for name in (
        "musl-COPYRIGHT.txt",
        "GCC-copyright.txt",
        "GPL-3.txt",
        "build-provenance.txt",
        "musl-ARM-memcpy-BSD-2-Clause.txt",
    ):
        members["third-party/" + name] = regular(userspace / "third-party" / name)
    members["third-party/monocypher-LICENSE.txt"] = regular(
        ROOT / "src/native/third-party/monocypher/LICENSE"
    )
    members["third-party/jsmn-LICENSE.txt"] = regular(ROOT / "src/native/third-party/jsmn/LICENSE")
    members["third-party/jsmn-provenance.json"] = regular(
        ROOT / "src/native/third-party/jsmn/PROVENANCE.json"
    )
    members["licenses/aoa-GPL-2.0-only.txt"] = regular(ROOT / "src/aoa/LICENSE")
    members["licenses/PolyForm-Noncommercial-1.0.0.txt"] = regular(ROOT / "LICENSE")
    members["licenses/Dextend-NOTICE.txt"] = regular(ROOT / "NOTICE")
    members["licenses/aoa-source-kit.txt"] = (
        b"GPL sources: src/aoa/ at the matching distribution tag.\n"
    )
    file_map = json.loads(regular(ROOT / "licenses/file-map.json"))
    members["licenses/source-file-map.json"] = json.dumps(file_map, separators=(",", ":")).encode()
    members["licenses/Lato-OFL-1.1.txt"] = regular(ROOT / "licenses/Lato-OFL-1.1.txt")
    members["licenses/DejaVu-Bitstream-Vera.txt"] = regular(
        ROOT / "licenses/DejaVu-Bitstream-Vera.txt"
    )
    members["web/index.html"] = render_panel_version(members["web/index.html"], version)
    members["AOA.sha256"] = (digest(members["yamaha_aoa.ko"]) + "  yamaha_aoa.ko\n").encode()
    manifest = {
        "schema": 1,
        "version": version,
        "based_on": "2026-10-30-native-clean-rc2",
        "ready_for_installation": False,
        "hardware_validation": "not performed for this build",
        "own_code_license": OWN_LICENSE,
        "license_scope": {
            "historical_panel": {
                "license": OWN_LICENSE,
                "license_text": "licenses/PolyForm-Noncommercial-1.0.0.txt",
                "notice": "licenses/Dextend-NOTICE.txt",
                "files": [
                    "web/index.html",
                    "web/console.css",
                    "web/console.js",
                    "web/debug.js",
                    "web/assets/dextend-logo.svg",
                ],
                "origin": "dongle-sdl/web",
            },
            "yamaha_aoa.ko": {"license": "GPL-2.0-only", "notice": "licenses/aoa-GPL-2.0-only.txt"},
            "own_programs_scripts_and_waiting_art": {
                "license": OWN_LICENSE,
                "license_text": "licenses/PolyForm-Noncommercial-1.0.0.txt",
                "notice": "licenses/Dextend-NOTICE.txt",
                "independent_dependencies": "third-party/; those licenses remain separate",
            },
            "source_file_map": "licenses/source-file-map.json",
        },
        "members": {n: digest(v) for n, v in sorted(members.items())},
    }
    members["manifest.json"] = json.dumps(manifest, separators=(",", ":")).encode()
    members["SHA256SUMS"] = "".join(
        digest(v) + "  " + n + "\n" for n, v in sorted(members.items())
    ).encode()
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(members.items()):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o700 if name.endswith(".sh") or name in BINS else 0o600
            tar.addfile(entry, io.BytesIO(data))
    if len(raw.getvalue()) > MAX_RUNTIME:
        raise ValueError("Runtime exceeds the native-boot unpacked limit")
    payload = lzma.compress(
        raw.getvalue(),
        format=lzma.FORMAT_ALONE,
        filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 1024 * 1024}],
    )
    boot = regular(ROOT / "packaging/native-boot.sh.in").replace(
        b"@RUNTIME_SHA256@", digest(payload).encode()
    )
    hook = (
        regular(ROOT / "packaging/custom_init.sh.in")
        .replace(b"@RUNTIME_SHA256@", digest(payload).encode())
        .replace(b"@BOOT_SHA256@", digest(boot).encode())
    )
    output.mkdir(parents=True)
    for name, data in {
        "native-runtime.tar.lzma": payload,
        "native-boot.sh": boot,
        "custom_init.sh": hook,
    }.items():
        (output / name).write_bytes(data)
    (output / "BUILD-STATUS.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--userspace", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--waiting", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version")
    args = parser.parse_args()
    package(args.userspace, args.module, args.waiting, args.output, args.version)
    print("Development package assembled; no installer or hardware approval.")
