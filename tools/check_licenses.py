#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Check explicit file coverage and separation of independent licenses offline."""

import json
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OWN_LICENSE = "PolyForm-Noncommercial-1.0.0"
LICENSE_MAP = "licenses/file-map.json"
MAPPED_PATHS = (
    ".gitattributes",
    "LICENSE",
    "NOTICE",
    "docs/development",
    "licenses",
    "packaging",
    "tests",
    "tools",
    "src/assets",
    "src/diagnostics/runtime",
    "src/native",
    "src/runtime",
    "src/usb",
    "src/web",
)


def source_files(root):
    if (root / ".git").exists():
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                *MAPPED_PATHS,
            ],
            check=True,
            capture_output=True,
        )
        return {
            name.decode()
            for name in result.stdout.split(b"\0")
            if name and (root / name.decode()).is_file()
        }
    ignored = {".git", ".venv", "__pycache__", "build", "dist"}
    files = set()
    for name in MAPPED_PATHS:
        path = root / name
        candidates = (path,) if path.is_file() else path.rglob("*")
        files.update(
            p.relative_to(root).as_posix()
            for p in candidates
            if p.is_file() and ignored.isdisjoint(p.relative_to(root).parts)
        )
    return files


def validate(root=ROOT, data=None):
    data = data if data is not None else json.loads((root / LICENSE_MAP).read_text())
    if data.get("schema") != 1 or data.get("own_license") != OWN_LICENSE:
        raise ValueError("Unsupported license map")
    mapped = data["files"]
    actual = source_files(root)
    if set(mapped) != actual:
        raise ValueError(
            f"License coverage mismatch: unmapped={sorted(actual - set(mapped))}, "
            f"missing={sorted(set(mapped) - actual)}"
        )
    for name, record in mapped.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or (root / path).is_symlink():
            raise ValueError(f"Invalid mapped path: {name}")
        license_id = record["license"]
        if name.startswith("src/native/third-party/jsmn/"):
            expected = "license-text" if name.endswith("/LICENSE") else "MIT"
            if license_id != expected:
                raise ValueError(f"MIT boundary changed: {name}")
        elif name.startswith("src/native/third-party/monocypher/"):
            expected = "license-text" if name.endswith("/LICENSE") else "BSD-2-Clause"
            if license_id != expected:
                raise ValueError(f"Monocypher boundary changed: {name}")
        elif name in (
            "src/web/index.html",
            "src/web/console.css",
            "src/web/console.js",
            "src/web/debug.js",
            "src/web/assets/dextend-logo.svg",
        ):
            if license_id != OWN_LICENSE or not record.get("origin", "").startswith(
                "dongle-sdl/web/"
            ):
                raise ValueError(f"Historical panel scope changed: {name}")
        elif license_id not in (OWN_LICENSE, "license-text"):
            raise ValueError(f"Unexpected license for independent file: {name}")
        if name in ("LICENSE", "NOTICE") and license_id != "license-text":
            raise ValueError(f"License or notice text must remain separate: {name}")
        if license_id == OWN_LICENSE:
            if not {"LICENSE", "NOTICE"}.issubset(record["notices"]):
                raise ValueError(f"Missing PolyForm license or author notice for {name}")
            text = (root / path).read_bytes()
            if re.search(
                rb"^\s*(?:#|/\*|\*)?\s*SPDX-License-Identifier:\s*(?:GPL-|MIT\b)", text, re.M
            ):
                raise ValueError(f"Independent source missing its license: {name}")
        for notice in record["notices"]:
            if notice not in mapped or not (root / notice).is_file():
                raise ValueError(f"Missing notice for {name}: {notice}")
    return data


if __name__ == "__main__":
    result = validate()
    print(f"License map valid: {len(result['files'])} files; GPL/MIT boundaries preserved.")
