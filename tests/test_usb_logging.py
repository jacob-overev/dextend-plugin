# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Opt-in logging lifecycle and privacy checks using a simulated USB volume."""

import os
from pathlib import Path
import pty
import struct
import subprocess
import tempfile
import time
import tty
import unittest

from test_probe import frame, read_frame

ROOT = Path(__file__).resolve().parents[1]


def wait_for(check):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for USB logging state")


class USBLoggingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.device = self.root / "volume"
        self.device.mkdir()
        self.marker = self.device / "dongle-logs"
        self.marker.mkdir()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.spool = self.runtime / "usb-debug"
        self.mounts = self.root / "mountinfo"
        self.mounts.write_text("")
        self.env = dict(
            os.environ,
            YAMAHA_RUNTIME=str(self.runtime),
            YAMAHA_LOG_USB_MOUNT=str(self.device),
            YAMAHA_LOG_MOUNTS=str(self.mounts),
            YAMAHA_LOG_INTERVAL="1",
        )
        self.recorder = subprocess.Popen(
            ["sh", str(ROOT / "src/runtime/usb-log-recorder.sh")], env=self.env
        )
        self.addCleanup(self.stop, self.recorder)

    @staticmethod
    def stop(process):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=4)

    def mount(self, ident=42, mode="rw", fs="vfat"):
        stage = self.mounts.with_suffix(".new")
        stage.write_text(f"{ident} 1 8:1 / {self.device} {mode},nosuid - {fs} /dev/sda1 {mode}\n")
        stage.replace(self.mounts)

    def service_event(self):
        subprocess.run(
            [
                "sh",
                "-c",
                '. "$1"; debug "SESSION_TEST stage=ready"',
                "test",
                str(ROOT / "src/runtime/debug-log.sh"),
            ],
            env=self.env,
            check=True,
        )

    def test_media_and_marker_gate_logging_and_separate_sessions(self):
        self.service_event()
        time.sleep(1.25)
        self.assertFalse(self.spool.exists())
        self.assertEqual(list(self.marker.iterdir()), [])
        for mode, fs in [("ro", "vfat"), ("rw", "ext4")]:
            self.mount(mode=mode, fs=fs)
            time.sleep(1.25)
            self.assertFalse(self.spool.exists())
        image = self.device / "A15W_Update.img"
        image.touch()
        self.mount()
        time.sleep(1.25)
        self.assertFalse(self.spool.exists())
        image.unlink()

        wait_for(self.spool.is_dir)
        self.service_event()
        (first,) = self.marker.iterdir()
        self.assertRegex(first.name, r"^session-[0-9]{8}T[0-9]{6}Z-")
        summary = first / "session.txt"
        self.assertIn("recording_started_utc=", summary.read_text())
        services = first / "services.log"
        wait_for(lambda: services.is_file() and "SESSION_TEST" in services.read_text())
        self.mounts.write_text("")
        wait_for(lambda: not self.spool.exists())
        exported = services.read_bytes()
        self.service_event()
        self.assertEqual(services.read_bytes(), exported)
        self.assertFalse(self.spool.exists())

        self.mount(ident=43)
        wait_for(lambda: self.spool.exists() and len(list(self.marker.iterdir())) == 2)
        for directory in self.marker.iterdir():
            if directory != first:
                data = directory / "services.log"
                wait_for(data.is_file)
                self.assertNotIn("SESSION_TEST", data.read_text())
        self.assertEqual(services.read_bytes(), exported)

    def test_independent_recorder_without_native_runtime(self):
        self.stop(self.recorder)
        self.runtime.rmdir()
        service = self.root / "service"
        service.mkdir()
        version = service / "waiting-version"
        version.write_text("test-release\n")
        self.spool = service / "usb-debug"
        self.recorder = subprocess.Popen(
            ["sh", str(ROOT / "src/runtime/usb-log-recorder.sh")],
            env=dict(
                self.env, YAMAHA_LOG_SPOOL=str(self.spool), YAMAHA_LOG_VERSION_FILE=str(version)
            ),
        )
        self.addCleanup(self.stop, self.recorder)
        self.mount()
        wait_for(self.spool.is_dir)
        (session,) = self.marker.iterdir()
        wait_for(lambda: (session / "services.log").exists())
        self.assertIn("dextend=test-release", (session / "session.txt").read_text())
        self.assertIn("phone-state=unknown", (session / "services.log").read_text())
        self.assertFalse(self.runtime.exists())

    def test_live_bridge_logs_metadata_only_during_recording(self):
        binary = os.getenv("YAMAHA_PROBE_CMD")
        if not binary:
            binary = str(self.root / "probe")
            subprocess.run(
                [
                    "cc",
                    "-O2",
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(ROOT / "src/native/probe.c"),
                    "-o",
                    binary,
                ],
                check=True,
            )
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        tty.setraw(slave)
        log = self.spool / "bridge.log"
        trace = self.root / "trace"
        env = dict(
            self.env,
            YAMAHA_USB_DEBUG_LOGGING="1",
            YAMAHA_CARPLAY_SOCKET=str(self.runtime / "source.sock"),
        )
        bridge = subprocess.Popen(
            [binary, os.ttyname(slave), "--live", str(log), "0", str(trace)], env=env
        )
        self.addCleanup(self.stop, bridge)
        read_frame(master)
        self.assertFalse(self.spool.exists())
        self.assertFalse(trace.exists())

        self.mount()
        wait_for(self.spool.is_dir)
        os.write(master, frame(4, 0, 7, 2, 1, b"\0\0\0\1"))
        read_frame(master)
        secret = b'{"success":true,"secret":"never-record-this"}'
        os.write(
            master, frame(4, 1, 7, 0, 1, struct.pack(">III", 0x10000001, 1, len(secret)) + secret)
        )
        (session,) = self.marker.iterdir()
        exported = session / "bridge.log"
        wait_for(lambda: exported.is_file() and "json_bytes=" in exported.read_text())
        self.assertIn("RPC_SERVICE_ACK", exported.read_text())
        self.assertNotIn("never-record-this", exported.read_text())
        self.assertNotIn("prefix=", exported.read_text())
        self.assertFalse(trace.exists())
        self.mounts.write_text("")
        wait_for(lambda: not self.spool.exists())
        os.write(
            master, frame(4, 1, 7, 0, 1, struct.pack(">III", 0x10000001, 1, len(secret)) + secret)
        )
        time.sleep(0.15)
        self.assertFalse(log.exists())
        self.assertIsNone(bridge.poll())


if __name__ == "__main__":
    unittest.main()
