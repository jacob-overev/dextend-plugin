#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Exercise opaque config preservation and refusal of ambiguous audio edits."""

import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "src/native/receiver-native.c"


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temporary.name) / "config-test"
        cls.settings = Path(cls.temporary.name) / "aa-video.conf"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-DDEXTEND_CONFIG_TEST",
                f'-DAA_SETTINGS="{cls.settings}"',
                str(SOURCE),
                "-o",
                str(cls.binary),
            ],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_config(self, data):
        return subprocess.run([str(self.binary)], input=data, capture_output=True)

    def test_aa_edits_only_top_level_geometry_and_input_profile(self):
        before = b'{"AndroidAutoWidth":800,"KnobMode":1,"ScreenDPI":160,"nested":{"AndroidAutoHeight":12,"KnobMode":1},"BtAudio":0}'
        run = subprocess.run([str(self.binary), "aa"], input=before, capture_output=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(
            json.loads(run.stdout),
            {
                "AndroidAutoWidth": 624,
                "AndroidAutoHeight": 352,
                "KnobMode": 0,
                "ScreenDPI": 120,
                "nested": {"AndroidAutoHeight": 12, "KnobMode": 1},
                "BtAudio": 0,
            },
        )
        again = subprocess.run([str(self.binary), "aa"], input=run.stdout, capture_output=True)
        self.assertEqual(again.returncode, 0)
        self.assertEqual(again.stdout, run.stdout)

    def test_aa_inserts_missing_input_profile(self):
        run = subprocess.run([str(self.binary), "aa"], input=b"{}", capture_output=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout)["KnobMode"], 0)
        self.assertEqual(json.loads(run.stdout)["ScreenDPI"], 120)

    def test_custom_aa_profile_reaches_receiver_config(self):
        self.settings.write_text("[656,368,80,60,48,56]")
        self.addCleanup(self.settings.unlink)
        run = subprocess.run([self.binary, "aa"], input=b"{}", capture_output=True, check=True)
        self.assertEqual(json.loads(run.stdout), {
            "AndroidAutoWidth": 656, "AndroidAutoHeight": 368, "KnobMode": 0, "ScreenDPI": 120
        })
        self.assertEqual(json.loads(self.run_config(b"{}").stdout), {"BtAudio": 1})

    def test_auto_radio_only_changes_android_mode(self):
        before = b'{"AndroidWorkMode":4,"DevList":[],"BtAudio":0,"AndroidAutoWidth":1457}'
        run = subprocess.run([str(self.binary), "auto"], input=before, capture_output=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout, before.replace(b'"AndroidWorkMode":4', b'"AndroidWorkMode":1'))

    def test_preserves_every_other_byte(self):
        before = b' {"nested":{"BtAudio":0}, "BtAudio" : 0, "opaque":"synthetic\\"value"}\n'
        run = self.run_config(before)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout, before.replace(b'"BtAudio" : 0', b'"BtAudio" : 1'))

    def test_insert_and_idempotence(self):
        for data in [b"{}", b'{ "nested":{"BtAudio":0} }\n', b'{"BtAudio":1}']:
            first = self.run_config(data)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(json.loads(first.stdout)["BtAudio"], 1)
            self.assertEqual(self.run_config(first.stdout).stdout, first.stdout)

    def test_refuses_ambiguous_types_duplicates_and_extra_documents(self):
        for data in [
            b'{"BtAudio":0,"BtAudio":1}',
            b'{"BtAudio":"0"}',
            b'{"BtAudio":false}',
            b'{"BtAudio":2}',
            b"[]",
            b"{} {}",
            b'{"\\u0042tAudio":0}',
            b"{",
            b'{"BtAudio":0}\0',
        ]:
            run = self.run_config(data)
            self.assertNotEqual(run.returncode, 0, data)
            self.assertEqual(run.stdout, b"")


class WirelessLifecycleTests(unittest.TestCase):
    def test_old_wifi_iap2_is_replaced_by_bluetooth_after_receiver_exit(self):
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / "bin"
            commands.mkdir()
            runtime = SOURCE.parents[1] / "runtime"
            script = (runtime / "wireless-step.sh").read_text()
            for original in [
                "/tmp/yamaha-sdl",
                "/sys/class/net/wlan0",
                "/sys/class/bluetooth/hci0",
            ]:
                script = script.replace(original, tmp)
            script = script.replace("/tmp/rfcomm_IAP2", str(root / "rfcomm"))
            (root / "step.sh").write_text(script)
            (root / "debug-log.sh").write_text(
                "debug() { :; }; debug_receiver() { cat >/dev/null; }\n"
            )
            (root / "iap2-wifi-test-step.sh").write_text("exit 0\n")
            (root / "old-iap2").touch()
            (root / "rfcomm").touch()
            (root / "iap2-wifi-active").touch()
            (root / "wireless-attempt").write_text("0")
            programs = {
                "pidof": '#!/bin/sh\ncase "$1" in AppleCarPlay) exit 1;; ARMiPhoneIAP2) test -f "$FIXTURE/old-iap2";; *) exit 0;; esac\n',
                "killall": '#!/bin/sh\ncase "$*" in *ARMiPhoneIAP2*) rm -f "$FIXTURE/old-iap2"; echo stopped >> "$FIXTURE/events";; esac\n',
                "ps": "#!/bin/sh\nexit 0\n",
                "receiver-native": '#!/bin/sh\n[ ! -f "$FIXTURE/old-iap2" ] || exit 9\necho "$*" >> "$FIXTURE/events"\n',
            }
            for name, body in programs.items():
                target = (root if name == "receiver-native" else commands) / name
                target.write_text(body)
                target.chmod(0o755)
            env = dict(
                os.environ,
                PATH=str(commands) + ":" + os.environ["PATH"],
                FIXTURE=tmp,
                YAMAHA_BT_AUTOCONNECT="0",
            )
            result = subprocess.run(
                ["sh", str(root / "step.sh")], env=env, capture_output=True, timeout=5
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            events = (root / "events").read_text().splitlines()
            self.assertEqual(events[0], "stopped")
            self.assertTrue(any("AppleCarPlay" in line for line in events), events)
            self.assertTrue(any("ARMiPhoneIAP2 640 360 20 1" in line for line in events), events)
            self.assertFalse((root / "iap2-wifi-active").exists())
            self.assertGreater(int((root / "wireless-attempt").read_text()), 0)


@unittest.skipUnless(shutil.which("bwrap"), "needs user-namespace mount fixtures")
class NamespaceTests(unittest.TestCase):
    def test_child_receiver_can_override_auto_runtime_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "receiver"
            subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-Os",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(SOURCE),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            (root / "etc").mkdir()
            (root / "ram/yamaha-sdl").mkdir(parents=True)
            (root / "etc/riddle.conf").write_text('{"AndroidWorkMode":4,"BtAudio":0}')
            (root / "etc/android_work_mode").write_bytes(bytes([4, 0, 0, 0]))
            (root / "ram/.riddle.conf").write_text('{"AndroidWorkMode":4,"BtAudio":0}')
            probe = root / "riddleBoxCfg"
            probe.write_text(
                "#!/bin/sh\ngrep -q '\"BtAudio\":1' /etc/riddle.conf || exit 2\necho 1\nexit 1\n"
            )
            probe.chmod(0o755)
            boot = root / "ram/yamaha-sdl/boot-live.sh"
            boot.write_text(
                '#!/bin/sh\n[ "$YAMAHA_PHONE_AUTO" = 1 ] || exit 2\n/receiver --probe-phone-audio\n[ "$?" = 1 ]\n'
            )
            run = subprocess.run(
                [
                    "bwrap",
                    "--unshare-user",
                    "--uid",
                    "0",
                    "--gid",
                    "0",
                    "--cap-add",
                    "CAP_SYS_ADMIN",
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
                    "--proc",
                    "/proc",
                    "--dev",
                    "/dev",
                    "--bind",
                    str(root / "etc"),
                    "/etc",
                    "--bind",
                    str(root / "ram"),
                    "/tmp",
                    "--ro-bind",
                    str(binary),
                    "/receiver",
                    "--tmpfs",
                    "/usr/sbin",
                    "--ro-bind",
                    str(probe),
                    "/usr/sbin/riddleBoxCfg",
                    "--chdir",
                    "/tmp/yamaha-sdl",
                    "/bin/sh",
                    "-c",
                    "unshare -m true || exit 77; exec /receiver --auto-runtime",
                ],
                capture_output=True,
            )
            if run.returncode == 77 or b"No permissions to create new namespace" in run.stderr:
                self.skipTest("host disables unprivileged mount namespace")
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            self.assertEqual(
                (root / "etc/riddle.conf").read_text(), '{"AndroidWorkMode":4,"BtAudio":0}'
            )


if __name__ == "__main__":
    unittest.main()
