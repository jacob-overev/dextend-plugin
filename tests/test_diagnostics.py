#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Bounded RAM diagnostics, privacy and native boot failure checkpoints."""

import io
import lzma
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from usb_image import decode, sha


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.logs = self.base / "logs"
        self.script = self.base / "diagnostics.sh"
        self.script.write_text(
            (ROOT / "src/runtime/diagnostics.sh")
            .read_text()
            .replace("/tmp/dextend-diagnostics", str(self.logs))
        )

    def run_log(self, *args, data=None):
        return subprocess.run(
            ["sh", str(self.script), *args], input=data, capture_output=True, text=True, timeout=10
        )

    def test_rotates_and_limits_memory(self):
        self.logs.mkdir()
        (self.logs / "events").write_text("old event\n" * 3300)
        self.assertEqual(self.run_log("event", "boot", "native_start").returncode, 0)
        self.assertIn("native_start", (self.logs / "events").read_text())
        self.assertEqual((self.logs / "previous").stat().st_size, 33000)
        self.run_log("event", "x" * 500)
        self.assertLess((self.logs / "events").stat().st_size, 500)

    def test_boot_evidence_survives_wifi_rotation_and_is_bounded(self):
        self.run_log("event", "native", "failed", "stage=verify_archive", "rc=1")
        for i in range(3):
            (self.logs / "events").write_text("wifi reconnect\n" * 2500)
            self.run_log("event", "wifi", "CTRL_EVENT_CONNECTED")
        report = self.run_log("report").stdout
        self.assertIn("BOOT EVENTS (CURRENT BOOT ONLY)", report)
        self.assertIn("native failed stage=verify_archive rc=1", report)
        (self.logs / "boot-events").write_text("x" * 8192)
        self.run_log("event", "native", "stage", "healthy")
        self.assertEqual((self.logs / "boot-events").stat().st_size, 8192)

    def test_no_symlink_writes(self):
        target = self.base / "untouched"
        target.write_text("keep")
        self.logs.mkdir()
        (self.logs / "events").symlink_to(target)
        self.run_log("event", "test")
        self.assertEqual(target.read_text(), "keep")

    def test_wifi_stream_keeps_reason_without_identity_or_password(self):
        data = (
            "wlan1: CTRL-EVENT-DISCONNECTED bssid=aa:bb:cc:dd:ee:ff reason=3\n"
            'ssid="private network" password="never log this"\n'
            "wlan1: CTRL-EVENT-CONNECTED aa:bb:cc:dd:ee:ff\n"
        )
        self.assertEqual(self.run_log("stream", "wifi", data=data).returncode, 0)
        logs = (self.logs / "events").read_text()
        self.assertIn("CTRL_EVENT_DISCONNECTED reason=3", logs)
        self.assertIn("CTRL_EVENT_CONNECTED", logs)
        for secret in ["aa:bb", "private network", "never log this", "password"]:
            self.assertNotIn(secret, logs)

    def test_native_failure_preserves_stage_and_errno(self):
        self.run_log(
            "stream", "native", data="DEXTEND_NATIVE_RECEIVER refused stage=namespace errno=1\n"
        )
        self.assertIn("stage=namespace errno=1", (self.logs / "events").read_text())

    def test_report_includes_events_but_not_configuration_files(self):
        self.run_log("event", "native", "failed", "stage=probe_auto_runtime", "rc=2")
        report = self.run_log("report")
        self.assertEqual(report.returncode, 0)
        self.assertTrue(report.stdout.startswith("DEXTEND DIAGNOSTICS"))
        self.assertIn("stage=probe_auto_runtime", report.stdout)
        self.assertLess(len(report.stdout), 100000)

    def test_oem_usb_report_distinguishes_no_mount_and_started_update(self):
        import os

        fake = self.base / "bin"
        fake.mkdir()
        kernel = fake / "dmesg"
        kernel.write_text(
            '#!/bin/sh\nprintf "%s\\n" "[ 12.500] [otg_set_state] Set state: a_wait_bcon" "[ 12.600] usb 1-1: USB disconnect, device number 4" "private network identity"\n'
        )
        kernel.chmod(0o700)
        status = self.base / "update_status"
        progress = self.base / "update_progress"
        mounts = self.base / "mounts"
        mounts.write_text("tmpfs /tmp tmpfs rw 0 0\n")
        script = (
            self.script.read_text()
            .replace('"/tmp/$n"', '"' + str(self.base) + '/$n"')
            .replace("/proc/mounts", str(mounts))
        )
        self.script.write_text(script)

        def report():
            return subprocess.run(
                ["sh", str(self.script), "report"],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "PATH": str(fake) + ":" + os.environ["PATH"]},
            ).stdout

        first = report()
        self.assertIn("update_status=absent", first)
        self.assertIn("usb_mount=absent", first)
        self.assertIn("OTG a_wait_bcon", first)
        self.assertIn("USB_DISCONNECT", first)
        self.assertNotIn("private network identity", first)
        status.write_text("5\n")
        progress.write_text("100\n")
        mounts.write_text("/dev/sda1 /mnt/UPAN vfat rw,relatime 0 0\n")
        second = report()
        self.assertIn("update_status=5", second)
        self.assertIn("update_progress=100", second)
        self.assertIn("usb_mount=writable_vfat", second)
        status.write_text("sensitive-unexpected-data\n")
        third = report()
        self.assertIn("update_status=invalid", third)
        self.assertNotIn("sensitive-unexpected-data", third)


class NativeBootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for n in ["tmp", "etc/yamaha-sdl", "var/run"]:
            (self.root / n).mkdir(parents=True)
        (self.root / ".fixture").touch()
        (self.root / "etc/riddle.conf").write_text("{}")
        (self.root / "tmp/.riddle.conf").write_text("{}")
        image = decode((ROOT / "releases/A15W_Update.img").read_bytes())
        data = image["tmp/dextend/release/native-runtime.tar.lzma"][0]
        (self.root / "etc/yamaha-sdl/native-runtime.tar.lzma").write_bytes(data)
        self.script = self.root / "boot.sh"
        self.script.write_text(
            (ROOT / "packaging/native-boot.sh.in")
            .read_text()
            .replace("@RUNTIME_SHA256@", sha(data))
        )
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.bind(str(self.root / "var/run/adb-driver"))
        self.addCleanup(self.socket.close)

    def run_boot(self, failed):
        (self.root / "actions.sh").write_text(
            '''#!/bin/sh
echo "$1" >> "$(dirname "$0")/actions"
case "$1" in
kernel) echo 3.14.52+g94d07bb;;
probe) echo 1;;
listeners) echo 0;;
start) echo 12345;;
esac
[ "$1" != "'''
            + failed
            + '" ]\n'
        )
        import os

        return subprocess.run(
            ["sh", str(self.script)],
            env={**os.environ, "DEXTEND_FIXTURE_ROOT": str(self.root)},
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_auto_radio_does_not_require_oem_web_directory(self):
        import os

        runtime = self.root / "runtime"
        runtime.mkdir()
        fake = self.root / "bin"
        fake.mkdir()
        for name in ("bluetoothDaemon", "killall", "phone-policy", "ARMAndroidAuto"):
            path = (runtime if name == "phone-policy" else fake) / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o700)
        (runtime / "debug-log.sh").write_text('debug() { printf "%s\\n" "$*"; }\n')
        source = (ROOT / "src/runtime/prepare-auto-radio.sh").read_text()
        source = source.replace("/tmp/yamaha-sdl", str(runtime)).replace(
            "/usr/sbin/ARMAndroidAuto", str(fake / "ARMAndroidAuto")
        )
        source = (
            source.replace("/tmp/no_touch", str(self.root / "no_touch"))
            .replace("/tmp/bluetoothdaemon_running", str(self.root / "bluetoothdaemon_running"))
            .replace("/tmp/boa", str(self.root / "absent-boa"))
        )
        run = subprocess.run(
            ["sh", "-c", source],
            env={
                **os.environ,
                "YAMAHA_PHONE_AUTO": "1",
                "PATH": str(fake) + ":" + os.environ["PATH"],
            },
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("AUTO_RADIO_STARTED", run.stdout)
        self.assertFalse((self.root / "absent-boa").exists())

    def test_healthy_native_keeps_factory_paused(self):
        result = self.run_boot("never")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("healthy", result.stdout)
        self.assertNotIn("resume-factory", (self.root / "actions").read_text())

    def test_probe_failure_does_not_pause_factory(self):
        # Probe exit=1 is deliberately accepted by OEM; use the factory barrier.
        result = self.run_boot("factory-ready")
        self.assertNotEqual(result.returncode, 0)
        actions = (self.root / "actions").read_text().splitlines()
        self.assertNotIn("pause-factory", actions)
        self.assertNotIn("start", actions)

    def test_health_failure_stops_receiver_and_restores_socket(self):
        result = self.run_boot("health")
        self.assertNotEqual(result.returncode, 0)
        actions = (self.root / "actions").read_text().splitlines()
        self.assertIn("stop", actions)
        self.assertIn("resume-factory", actions)
        self.assertTrue((self.root / "var/run/adb-driver").is_socket())

    @unittest.skipUnless(shutil.which("bwrap"), "requires isolated process namespace")
    def test_factory_hicar_cannot_keep_inherited_listener(self):
        # HiCar inherits the OEM IPC listener on the real device. Killing only
        # ARMadb does not release it; exercise the actual production action.
        source = (ROOT / "packaging/native-boot.sh.in").read_text()
        action = "action() {" + source.split("action() {", 1)[1].split("\nfallback()", 1)[0]
        (self.root / "action.sh").write_text(
            "root=\nwork=/work\nruntime=/tmp/yamaha-sdl\n" + action + '\naction "$1"\n'
        )
        harness = (
            r"""
import pathlib, socket, subprocess, sys, time
pathlib.Path('/var/run').mkdir(parents=True, exist_ok=True)
s=socket.socket(socket.AF_UNIX)
s.bind('/var/run/adb-driver'); s.listen()
child=subprocess.Popen([sys.executable, '-c', """
            + repr("""
import ctypes, pathlib, signal, socket, sys
ctypes.CDLL(None).prctl(15, b'ARMHiCar', 0, 0, 0)
s=socket.socket(fileno=int(sys.argv[1]))
pathlib.Path('/work/ready').touch()
signal.pause()
""")
            + r""", str(s.fileno())], pass_fds=(s.fileno(),))
s.close()
try:
    for _ in range(100):
        if pathlib.Path('/work/ready').exists(): break
        time.sleep(.01)
    else: raise AssertionError('fixture did not start')
    count=lambda: subprocess.check_output(['sh','/work/action.sh','listeners'],text=True).strip()
    assert count()=='1', 'inherited listener absent before pause'
    subprocess.run(['sh','/work/action.sh','pause-factory'],check=True)
    child.wait(timeout=3)
    assert child.returncode==-9, child.returncode
    assert count()=='0', 'OEM listener remains after pause'
finally:
    if child.poll() is None: child.kill(); child.wait()
"""
        )
        (self.root / "listener-test.py").write_text(harness)
        result = subprocess.run(
            [
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
                "--ro-bind",
                "/etc/alternatives",
                "/etc/alternatives",
                "--symlink",
                "usr/lib64",
                "/lib64",
                "--dev",
                "/dev",
                "--unshare-pid",
                "--proc",
                "/proc",
                "--unshare-net",
                "--die-with-parent",
                "--dir",
                "/tmp",
                "--dir",
                "/var",
                "--bind",
                str(self.root),
                "/work",
                sys.executable,
                "/work/listener-test.py",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
