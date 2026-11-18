#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Validate delivered notices, independent GPL terms and source-map failures."""

import copy
import hashlib
import io
import json
import lzma
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_licenses import OWN_LICENSE, validate
from package import BINS, COMPACT_WAITING, package
from service_package import render_panel_version


class LicensePackagingTests(unittest.TestCase):
    def test_panel_version_is_release_driven_and_safe(self):
        source = (ROOT / "src/web/index.html").read_bytes()
        for version in ("0.22-alpha", "1.200"):
            rendered = render_panel_version(source, version)
            self.assertEqual(rendered.count(b"data-plugin-version>" + version.encode()), 2)
            self.assertNotIn(b"?v=build", rendered)
            self.assertNotIn(b"2026.10.24-rc1", rendered)
        with self.assertRaisesRegex(ValueError, "Invalid panel version"):
            render_panel_version(source, "<script>")
        with self.assertRaisesRegex(ValueError, "both panel version fields"):
            render_panel_version(b"no version fields", "0.22-alpha")

    def test_all_sources_have_explicit_status(self):
        validate()

    def test_source_provenance_matches_checkout(self):
        data = json.loads((ROOT / "docs/development/source-provenance.json").read_text())
        self.assertTrue((ROOT / data["aoa_source"] / "yamaha_aoa.c").is_file())
        for entry in data["files"]:
            with self.subTest(path=entry["path"]):
                source = ROOT / entry["path"]
                self.assertTrue(source.is_file())
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(), entry["current_sha256"]
                )

    def test_omitted_source_fails_coverage(self):
        data = copy.deepcopy(validate())
        del data["files"]["src/runtime/boot-live.sh"]
        with self.assertRaisesRegex(ValueError, "unmapped="):
            validate(data=data)

    def test_cannot_remove_mit_from_dependency(self):
        data = copy.deepcopy(validate())
        data["files"]["src/native/third-party/jsmn/jsmn.h"]["license"] = OWN_LICENSE
        with self.assertRaisesRegex(ValueError, "MIT boundary changed"):
            validate(data=data)

    def test_own_code_requires_license_and_author_notice(self):
        for notice in ("LICENSE", "NOTICE"):
            with self.subTest(notice=notice):
                data = copy.deepcopy(validate())
                data["files"]["src/native/probe.c"]["notices"].remove(notice)
                with self.assertRaisesRegex(ValueError, "Missing PolyForm"):
                    validate(data=data)

    def test_own_code_cannot_return_to_unassigned_license(self):
        data = copy.deepcopy(validate())
        data["files"]["src/native/probe.c"]["license"] = "NOASSERTION"
        with self.assertRaisesRegex(ValueError, "Unexpected license"):
            validate(data=data)

    def test_packed_notices_match_sources_without_changing_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            userspace = root / "userspace"
            (userspace / "third-party").mkdir(parents=True)
            # No executable is run; fixture bytes exercise packaging only.
            for name in BINS:
                (userspace / name).write_bytes(b"fixture-" + name.encode())
            for name in (
                "musl-COPYRIGHT.txt",
                "GCC-copyright.txt",
                "GPL-3.txt",
                "musl-ARM-memcpy-BSD-2-Clause.txt",
            ):
                (userspace / "third-party" / name).write_bytes(
                    (ROOT / "licenses" / name).read_bytes()
                )
            (userspace / "third-party/build-provenance.txt").write_text("fixture build only\n")
            module, waiting = root / "module.ko", root / "waiting.h264"
            module.write_bytes(b"fixture-module")
            waiting.write_bytes(b"fixture-frame")
            (root / COMPACT_WAITING).write_bytes(b"compact-fixture-frame")
            (root / "waiting-strip.bin").write_bytes(bytes(160 * 96 * 3 // 2))
            (root / "waiting-font.bin").write_bytes(bytes(95 * 7 * 12))
            version_file = root / "waiting-version"
            version_file.write_text("fixture-version\n")
            with self.assertRaisesRegex(ValueError, "does not match"):
                package(userspace, module, waiting, root / "package", "other-version")
            output = root / "package"
            manifest = package(userspace, module, waiting, output, "fixture-version")
            self.assertFalse(manifest["ready_for_installation"])
            self.assertEqual(manifest["own_code_license"], OWN_LICENSE)
            self.assertEqual(manifest["license_scope"]["yamaha_aoa.ko"]["license"], "GPL-2.0-only")
            with tarfile.open(
                fileobj=io.BytesIO(
                    lzma.decompress((output / "native-runtime.tar.lzma").read_bytes())
                )
            ) as archive:
                members = {m.name: archive.extractfile(m).read() for m in archive.getmembers()}
            self.assertEqual(members["waiting-version"], b"fixture-version\n")
            self.assertEqual(members[COMPACT_WAITING], b"compact-fixture-frame")
            self.assertEqual(
                members["web/index.html"].count(b"data-plugin-version>fixture-version"), 2
            )
            self.assertEqual(members["yamaha_aoa.ko"], module.read_bytes())
            self.assertEqual(
                members["licenses/aoa-GPL-2.0-only.txt"], (ROOT / "src/aoa/LICENSE").read_bytes()
            )
            self.assertEqual(
                members["third-party/jsmn-LICENSE.txt"],
                (ROOT / "src/native/third-party/jsmn/LICENSE").read_bytes(),
            )
            self.assertNotIn("licenses/own-terms.txt", members)
            self.assertNotIn("licenses/own-terms.pl.txt", members)
            self.assertEqual(manifest["own_code_license"], "PolyForm-Noncommercial-1.0.0")
            own_scope = manifest["license_scope"]["own_programs_scripts_and_waiting_art"]
            self.assertEqual(members[own_scope["license_text"]], (ROOT / "LICENSE").read_bytes())
            self.assertEqual(members[own_scope["notice"]], (ROOT / "NOTICE").read_bytes())
            self.assertEqual(
                json.loads(members["licenses/source-file-map.json"]),
                json.loads((ROOT / "licenses/file-map.json").read_bytes()),
            )
            for p in (ROOT / "src/runtime").glob("*.sh"):
                self.assertEqual(members[p.name], p.read_bytes())
            for name, digest in manifest["members"].items():
                self.assertEqual(hashlib.sha256(members[name]).hexdigest(), digest)
            self.assertEqual(json.loads(members["manifest.json"]), manifest)


if __name__ == "__main__":
    unittest.main()
