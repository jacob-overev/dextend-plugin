#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Bounded, independently checksummed diagnostic payload. No device access."""

import argparse
import hashlib
import io
import lzma
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 4 * 1024 * 1024
BINS = (
    "ath.ko",
    "ath9k_hw.ko",
    "ath9k_common.ko",
    "ath9k_htc.ko",
    "htc_9271.fw",
    "wpa_supplicant",
    "dropbearmulti",
)
REQUIRED = set(BINS) | {
    "debug-api",
    "authorized_keys",
    "service.sh",
    "dhcp.sh",
    "keys.sh",
    "borrow-key.sh",
    "service-key",
    "restore-cgi.sh",
    "start-updater.sh",
    "updater-http",
    "updater-api.sh",
    "updater-worker.sh",
    "updater-events.sh",
    "usb-log-recorder.sh",
    "diagnostics.sh",
    "waiting-version",
    "web/index.html",
    "web/update/index.html",
    "restore/transaction.sh",
    "restore/profile.sh",
    "restore/OEM.sha256",
    "restore/LEGACY.sha256",
    "restore/format",
    "restore/update-protocol",
    "restore/service-key-restore.sh",
    "SHA256SUMS",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def render_panel_version(html, version):
    """Stamp both panel copies from the release parameter, without an API dependency."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError("Invalid panel version")
    placeholder = "data-plugin-version>—".encode()
    if html.count(placeholder) != 2:
        raise ValueError("Expected both panel version fields")
    return html.replace(placeholder, b"data-plugin-version>" + version.encode()).replace(
        b"?v=build", b"?v=" + version.encode()
    )


def verify_service(payload, version=None):
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=8 * 1024 * 1024)
    raw = dec.decompress(payload, max_length=LIMIT + 1)
    if len(raw) > LIMIT or not dec.eof or dec.unused_data:
        raise ValueError("Service archive bounds/trailing data")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        for entry in t:
            if (
                not entry.isfile()
                or entry.name in files
                or entry.name.startswith("/")
                or ".." in Path(entry.name).parts
                or not re.fullmatch(r"[A-Za-z0-9_.\-/]+", entry.name)
            ):
                raise ValueError("Unsafe service member")
            files[entry.name] = t.extractfile(entry).read()
    if not REQUIRED <= files.keys() or any(
        n not in REQUIRED | {"phone-policy", "recovery.sh"}
        and not n.startswith(("licenses/", "web/", "restore/"))
        for n in files
    ):
        raise ValueError("Service inventory mismatch")
    checks = "".join(
        f"{sha(v)}  {n}\n" for n, v in sorted(files.items()) if n != "SHA256SUMS"
    ).encode()
    if files["SHA256SUMS"] != checks:
        raise ValueError("Service checksums incomplete or damaged")
    if not re.fullmatch(
        rb"ssh-ed25519 [A-Za-z0-9+/]{68} dextend-service\n", files["authorized_keys"]
    ):
        raise ValueError("Expected only one public Ed25519 client key")
    for n in (
        "debug-api",
        "wpa_supplicant",
        "dropbearmulti",
        "service-key",
        "updater-http",
        "ath.ko",
        "ath9k_hw.ko",
        "ath9k_common.ko",
        "ath9k_htc.ko",
    ):
        data = files[n]
        if data[:6] != b"\x7fELF\x01\x01" or data[18:20] != b"\x28\x00":
            raise ValueError("Service executable must be ARM little-endian")
    if "phone-policy" in files:
        data = files["phone-policy"]
        if data[:6] != b"\x7fELF\x01\x01" or data[18:20] != b"\x28\x00":
            raise ValueError("Phone policy must be ARM little-endian")
    if version is not None:
        if "recovery.sh" not in files:
            raise ValueError("New service package must include the recovery guard")
        if "phone-policy" not in files:
            raise ValueError("Service must publish phone policy independently of native startup")
        from build_usb import restore_inputs

        if (
            re.findall(rb"data-plugin-version>([^<]+)<", files["web/index.html"])
            != [version.encode()] * 2
        ):
            raise ValueError("Panel version differs from the IMG")
        if files["waiting-version"] != (version + "\n").encode():
            raise ValueError("Service version differs from the IMG")
        if {n: v for n, v in files.items() if n.startswith("restore/")} != {
            "restore/" + n: v for n, v in restore_inputs(version).items()
        }:
            raise ValueError("Service restore procedure differs from this release")
    return len(raw)


def package(dependencies, api, output, userspace):
    files = {n: (dependencies / "bin" / n).read_bytes() for n in BINS}
    files.update(
        {
            "licenses/" + p.name: p.read_bytes()
            for p in (dependencies / "licenses").iterdir()
            if p.is_file()
        }
    )
    files.update(
        {
            p.name: p.read_bytes()
            for p in (ROOT / "src/diagnostics/runtime").iterdir()
            if p.is_file()
        }
    )
    files["debug-api"] = api.read_bytes()
    files["service-key"] = (userspace / "service-key").read_bytes()
    files["phone-policy"] = (userspace / "phone-policy").read_bytes()
    files["restore-cgi.sh"] = (ROOT / "src/runtime/restore-cgi.sh").read_bytes()
    files["updater-http"] = (userspace / "updater-http").read_bytes()
    for n in (
        "start-updater.sh",
        "updater-api.sh",
        "updater-worker.sh",
        "updater-events.sh",
        "usb-log-recorder.sh",
        "diagnostics.sh",
    ):
        files[n] = (ROOT / "src/runtime" / n).read_bytes()
    files.update(
        {
            "web/" + p.relative_to(ROOT / "src/web").as_posix(): p.read_bytes()
            for p in (ROOT / "src/web").rglob("*")
            if p.is_file()
        }
    )
    from build_usb import restore_inputs

    version = (ROOT / "VERSION").read_text().strip()
    files["waiting-version"] = (version + "\n").encode()
    files["web/index.html"] = render_panel_version(files["web/index.html"], version)
    files.update({"restore/" + n: data for n, data in restore_inputs(version).items()})
    for n in (
        "musl-COPYRIGHT.txt",
        "GCC-copyright.txt",
        "GPL-3.txt",
        "build-provenance.txt",
        "musl-ARM-memcpy-BSD-2-Clause.txt",
    ):
        files["licenses/" + n] = (userspace / "third-party" / n).read_bytes()
    files["licenses/monocypher-LICENSE.txt"] = (
        ROOT / "src/native/third-party/monocypher/LICENSE"
    ).read_bytes()
    files["licenses/Dextend-LICENSE"] = (ROOT / "LICENSE").read_bytes()
    files["licenses/Dextend-NOTICE"] = (ROOT / "NOTICE").read_bytes()
    files["SHA256SUMS"] = "".join(f"{sha(v)}  {n}\n" for n, v in sorted(files.items())).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for n, v in sorted(files.items()):
            e = tarfile.TarInfo(n)
            e.size = len(v)
            e.mode = (
                0o700
                if n.endswith(".sh")
                or n
                in (
                    "debug-api",
                    "wpa_supplicant",
                    "dropbearmulti",
                    "service-key",
                    "updater-http",
                    "phone-policy",
                )
                else 0o600
            )
            t.addfile(e, io.BytesIO(v))
    payload = lzma.compress(
        buf.getvalue(),
        format=lzma.FORMAT_ALONE,
        filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 1024 * 1024}],
    )
    verify_service(payload, version)
    with output.open("xb") as f:
        f.write(payload)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("dependencies", type=Path)
    p.add_argument("api", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("userspace", type=Path)
    a = p.parse_args()
    package(a.dependencies, a.api, a.output, a.userspace)
