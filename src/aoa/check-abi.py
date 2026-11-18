#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Read ELF32 ARM module metadata; never edit CRCs, vermagic or load a module.

An exit code of zero means only that the available symbol checks agree.
It is not proof of structure layout, target configuration, or hardware behavior.
"""

import argparse
import json
from pathlib import Path
import struct
import sys


def inspect(path):
    data = Path(path).read_bytes()
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        raise ValueError(f"{path}: expected little-endian ELF32")
    if struct.unpack_from("<H", data, 18)[0] != 40:
        raise ValueError(f"{path}: expected ARM machine")
    offset = struct.unpack_from("<I", data, 32)[0]
    size, count, strings = struct.unpack_from("<HHH", data, 46)
    if size != 40 or strings >= count or offset + size * count > len(data):
        raise ValueError(f"{path}: invalid section table")
    headers = [struct.unpack_from("<10I", data, offset + i * size) for i in range(count)]

    def content(h):
        if h[1] == 8:  # NOBITS has no bytes in the ELF file.
            return b""
        if h[4] + h[5] > len(data):
            raise ValueError(f"{path}: section exceeds file")
        return data[h[4] : h[4] + h[5]]

    def string(table, start):
        if start >= len(table):
            raise ValueError(f"{path}: invalid string offset")
        end = table.find(b"\0", start)
        if end < 0:
            raise ValueError(f"{path}: unterminated string")
        return table[start:end].decode("ascii")

    names = content(headers[strings])
    sections = {string(names, h[0]): h for h in headers}
    info = content(sections[".modinfo"]).split(b"\0")
    magic = [x.decode().split("=", 1)[1] for x in info if x.startswith(b"vermagic=")]
    if len(magic) != 1:
        raise ValueError(f"{path}: expected one vermagic")
    versions = {}
    raw = content(sections["__versions"]) if "__versions" in sections else b""
    if len(raw) % 64:
        raise ValueError(f"{path}: invalid ARM modversion entry size")
    for i in range(0, len(raw), 64):
        name = string(raw[i + 4 : i + 64], 0)
        if name in versions:
            raise ValueError(f"{path}: duplicate modversion symbol")
        versions[name] = struct.unpack_from("<I", raw, i)[0]
    imports = set()
    for h in headers:
        if h[1] != 2:
            continue
        if h[9] != 16 or h[6] >= count or h[5] % 16:
            raise ValueError(f"{path}: invalid symbol table")
        table = content(headers[h[6]])
        symbols = content(h)
        for i in range(0, len(symbols), 16):
            name, _, _, flags, _, section = struct.unpack_from("<IIIBBH", symbols, i)
            if section == 0 and flags >> 4 == 1 and name:
                imports.add(string(table, name))
    module = sections.get(".gnu.linkonce.this_module")
    return {
        "vermagic": magic[0],
        "versions": versions,
        "imports": sorted(imports),
        "module_struct_size": module[5] if module else None,
    }


def compare(candidate, references):
    issues = []
    known = {}
    for reference in references:
        if candidate["vermagic"] != reference["vermagic"]:
            issues.append("vermagic differs from reference")
        if candidate["module_struct_size"] != reference["module_struct_size"]:
            issues.append("struct module section size differs from reference")
        for name, crc in reference["versions"].items():
            if name in known and known[name] != crc:
                issues.append(f"references disagree on CRC: {name}")
            known[name] = crc
    required = set(candidate["imports"]) | {"module_layout"}
    missing_candidate = sorted(required - candidate["versions"].keys())
    missing_reference = sorted(required - known.keys())
    mismatch = sorted(
        name for name, crc in candidate["versions"].items() if name in known and known[name] != crc
    )
    if missing_candidate:
        issues.append("candidate lacks required symbol CRCs")
    if missing_reference:
        issues.append("reference evidence does not cover all imported symbols")
    if mismatch:
        issues.append("symbol CRC mismatch")
    return {
        "status": "NEEDS_TARGET_BUILD_OR_EVIDENCE"
        if issues
        else "SYMBOL_CHECKS_PASS_NOT_LOAD_APPROVAL",
        "issues": sorted(set(issues)),
        "missing_candidate_crcs": missing_candidate,
        "missing_reference_crcs": missing_reference,
        "mismatched_crcs": mismatch,
        "candidate_vermagic": candidate["vermagic"],
        "limitations": [
            "No structure-layout or hardware verification",
            "Never force-load or transplant reference CRCs into a candidate",
        ],
    }


def self_test():
    import tempfile
    import unittest

    class Checks(unittest.TestCase):
        def setUp(self):
            self.reference = dict(
                vermagic="target SMP modversions",
                versions={"module_layout": 123, "usb_test": 456},
                imports=["usb_test"],
                module_struct_size=128,
            )

        def test_consistent(self):
            self.assertFalse(compare(self.reference, [self.reference])["issues"])

        def test_missing_crcs(self):
            candidate = dict(self.reference, versions={})
            result = compare(candidate, [self.reference])
            self.assertEqual(result["missing_candidate_crcs"], ["module_layout", "usb_test"])
            self.assertTrue(result["issues"])

        def test_crc_mismatch(self):
            candidate = dict(self.reference, versions={"module_layout": 123, "usb_test": 999})
            self.assertEqual(compare(candidate, [self.reference])["mismatched_crcs"], ["usb_test"])

        def test_version_and_structure(self):
            candidate = dict(self.reference, vermagic="different", module_struct_size=144)
            self.assertEqual(len(compare(candidate, [self.reference])["issues"]), 2)

        def test_unknown_import(self):
            candidate = dict(self.reference, imports=["usb_test", "unknown"])
            result = compare(candidate, [self.reference])
            self.assertIn("unknown", result["missing_reference_crcs"])
            self.assertTrue(result["issues"])

        def test_reference_conflict(self):
            other = dict(self.reference, versions={"module_layout": 123, "usb_test": 999})
            self.assertTrue(compare(self.reference, [self.reference, other])["issues"])

        def test_not_an_elf(self):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "bad.ko"
                path.write_bytes(b"invalid")
                with self.assertRaises(ValueError):
                    inspect(path)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    result = unittest.TextTestRunner().run(suite)
    return 0 if result.wasSuccessful() else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        raise SystemExit(self_test())
    parser = argparse.ArgumentParser(
        description=__doc__, epilog="Run --self-test to verify the checker itself."
    )
    parser.add_argument("candidate")
    parser.add_argument("reference", nargs="+")
    args = parser.parse_args()
    try:
        result = compare(inspect(args.candidate), [inspect(p) for p in args.reference])
    except (ValueError, KeyError, UnicodeError, OSError, struct.error) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(2 if result["issues"] else 0)


if __name__ == "__main__":
    main()
