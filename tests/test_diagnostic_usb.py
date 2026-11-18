#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# The diagnostic image must abort OEM copying and preserve flash.
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import os
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_diagnostic_usb import build
from usb_image import decode


@unittest.skipUnless(shutil.which("bwrap"), "requires bwrap isolation")
class DiagnosticUsbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for n in (
            "etc/alternatives",
            "etc/yamaha-sdl/usb-v1/radio",
            "tmp/dextend-updater",
            "script",
            "mnt/UPAN",
            "proc/self",
            "proc/sys/kernel/random",
        ):
            (self.root / n).mkdir(parents=True)
        self.write("etc/riddle.conf", b'{"password":"DO_NOT_EXPORT"}')
        self.write("etc/yamaha-sdl/usb-v1/status", b"PREPARED_FOR_BOOT")
        self.write("tmp/dextend-updater/state", b"error")
        self.write("tmp/dextend-updater/detail", b"RADIO_NAMES_FAILED")
        self.write(
            "tmp/dextend-updater/worker.log",
            b"mv: cannot move radio-output to /etc/riddle.conf: Device or resource busy\n"
            b'password=DO_NOT_EXPORT\n+ candidate={"secret":"DO_NOT_EXPORT"}\n'
            b"awk: invalid DO_NOT_EXPORT\nDEXTEND: RADIO_NAMES_FAILED\n",
        )
        self.write("proc/mounts", b"/dev/sda1 /mnt/UPAN vfat rw,relatime 0 0\n")
        self.write("proc/self/mountinfo", b"12 1 0:1 / /etc/riddle.conf rw - tmpfs tmpfs rw\n")
        self.write("proc/sys/kernel/random/boot_id", b"test-boot\n")
        build(self.root / "image")
        self.image = decode((self.root / "image/A15W_Update.img").read_bytes())
        self.write("collector.sh", self.image["tmp/once.sh"][0])

    def write(self, path, data):
        (self.root / path).write_bytes(data)

    def run_collector(self, oem=None, controller=False):
        before = {
            str(p.relative_to(self.root / "etc")): p.read_bytes()
            for p in (self.root / "etc").rglob("*")
            if p.is_file()
        }
        cmd = [
            "bwrap",
            "--tmpfs",
            "/",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--dev",
            "/dev",
            "--unshare-net",
            "--die-with-parent",
        ]
        for n in ("etc", "proc", "script"):
            cmd += ["--ro-bind", str(self.root / n), "/" + n]
        cmd += ["--bind" if controller else "--ro-bind", str(self.root / "tmp"), "/tmp"]
        cmd += ["--ro-bind", "/etc/alternatives", "/etc/alternatives"]
        cmd += [
            "--bind",
            str(self.root / "mnt"),
            "/mnt",
            "--ro-bind",
            str(self.root / "collector.sh"),
            "/collector.sh",
        ]
        if oem:
            applets = self.root / "applets"
            applets.mkdir()
            for name in (
                "awk",
                "head",
                "tr",
                "wc",
                "find",
                "sha256sum",
                "cmp",
                "mktemp",
                "df",
                "sync",
                "mv",
            ):
                file = applets / name
                file.write_text(
                    "#!/bin/sh\nexec /usr/bin/qemu-arm -L /arm-root /oem/bin/busybox "
                    + name
                    + ' "$@"\n'
                )
                file.chmod(0o755)
            self.write(
                "collector.sh",
                self.image["tmp/once.sh"][0].replace(
                    b"PATH=/usr/sbin:/usr/bin:/sbin:/bin", b"PATH=/applets:/usr/bin"
                ),
            )
            cmd += [
                "--ro-bind",
                str(applets),
                "/applets",
                "--ro-bind",
                str(oem),
                "/oem",
                "--ro-bind",
                str(oem / "lib"),
                "/arm-root/lib",
                "/usr/bin/qemu-arm",
                "-L",
                "/arm-root",
                "/oem/bin/busybox",
                "ash",
                "/collector.sh",
            ]
        else:
            cmd += ["/bin/sh", "/collector.sh"]
        result = subprocess.run(cmd, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 1, result.stderr)
        after = {
            str(p.relative_to(self.root / "etc")): p.read_bytes()
            for p in (self.root / "etc").rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)
        return list((self.root / "mnt/UPAN").glob("dextend-diagnostics.*/REPORT.txt"))

    def test_image_has_only_ram_launcher_and_reports_without_secrets(self):
        self.assertEqual(set(self.image), {"tmp/once.sh"})
        reports = self.run_collector()
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text()
        self.assertIn("tool=mv reason=busy_mount target=riddle.conf", text)
        self.assertIn("RADIO_NAMES_FAILED", text)
        self.assertIn("mount=/etc/riddle.conf", text)
        self.assertNotIn("DO_NOT_EXPORT", text)
        self.assertTrue(text.endswith("END OF REPORT\n"))

    def test_no_usb_mount_refuses_without_writing(self):
        self.write("proc/mounts", b"")
        self.assertEqual(self.run_collector(), [])

    def test_missing_updater_logs_still_reports_state(self):
        shutil.rmtree(self.root / "tmp/dextend-updater")
        text = self.run_collector()[0].read_text()
        self.assertIn("updater_state=absent", text)
        self.assertIn("END OF REPORT", text)

    def test_repeated_collection_keeps_previous_report(self):
        first = self.run_collector()[0]
        before = first.read_bytes()
        self.assertEqual(len(self.run_collector()), 2)
        self.assertEqual(first.read_bytes(), before)

    def test_original_oem_busybox_reads_and_finishes_report(self):
        oem = Path(os.environ.get("DEXTEND_OEM_TEST_ROOT") or "/nonexistent/dextend-oem-fixture")
        if not shutil.which("qemu-arm") or not (oem / "bin/busybox").exists():
            self.skipTest("requires OEM fixture and qemu-arm")
        reports = self.run_collector(oem=oem)
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text()
        self.assertIn("reason=busy_mount", text)
        self.assertNotIn("DO_NOT_EXPORT", text)
        self.assertTrue(text.endswith("END OF REPORT\n"))

    def test_oem_controller_aborts_before_copy_or_metadata_deletion(self):
        oem = Path(os.environ.get("DEXTEND_OEM_TEST_ROOT") or "/nonexistent/dextend-oem-fixture")
        path = oem / "script/update_box.sh"
        if not path.exists():
            self.skipTest("requires OEM fixture")
        (self.root / "tmp/update/tmp").mkdir(parents=True)
        self.write("tmp/update/tmp/once.sh", self.image["tmp/once.sh"][0])
        (self.root / "tmp/update/tmp/once.sh").chmod(0o755)
        (self.root / "etc/module_version").mkdir()
        self.write("etc/module_version/sentinel", b"preserve")
        self.write("script/quickly_update.sh", b"#!/bin/sh\necho called > /tmp/copy-called\n")
        (self.root / "script/quickly_update.sh").chmod(0o755)
        functions = path.read_bytes().split(b"\nif [ -e /etc/box_product_type ]; then\n")[0]
        self.write("collector.sh", functions + b"\nupdatepath=/tmp/update\ndoUpdate img\n")
        reports = self.run_collector(controller=True)
        self.assertEqual(len(reports), 1)
        self.assertEqual((self.root / "tmp/update_status").read_text().strip(), "3")
        self.assertFalse((self.root / "tmp/copy-called").exists())
        self.assertEqual((self.root / "etc/module_version/sentinel").read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
