# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Real policy/CGI against synthetic bonds; no device or network access."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
A, B, C = "02:00:00:00:00:01", "02:00:00:00:00:02", "02:00:00:00:00:03"


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.binary = str(Path(cls.build.name) / "policy")
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-DDEXTEND_PHONE_TEST",
                str(ROOT / "src/native/phone-policy.c"),
                "-o",
                cls.binary,
            ],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        bt = self.root / "tmp/bluetooth/02:00:00:00:AA:01"
        bt.mkdir(parents=True)
        (bt / "linkkeys").write_text(
            f"{A} SECRET_KEY_ONE 0 4\n{B} SECRET_KEY_TWO 0 4\n{C} SECRET_KEY_THREE 0 4\n"
        )
        (bt / "names").write_text(f'{A} Android <script>\n{B} iPhone "A"\n{C} Android drugi\n')
        (bt.parent / "services").write_text(f"{A} AAP\n{B} IAP2\n{C} AAP\n02:00:00:00:00:99 AAP\n")
        (self.root / "tmp/yamaha-sdl").mkdir()
        (self.root / "etc/yamaha-sdl").mkdir(parents=True)
        self.env = dict(
            os.environ,
            DEXTEND_PHONE_ROOT=str(self.root),
            REQUEST_METHOD="GET",
            HTTP_HOST="192.168.50.2",
        )
        self.run_cli("--init")
        self.token = self.get()["token"]

    def run_cli(self, *args):
        return subprocess.run(
            [self.binary, *args], env=self.env, capture_output=True, check=True, timeout=5
        ).stdout.decode()

    def get(self):
        result = self.run_cli()
        self.assertNotIn("SECRET_KEY", result)
        return json.loads(result.split("\r\n\r\n")[1])

    def post(self, data, **extra):
        body = json.dumps(data).encode()
        env = dict(
            self.env,
            REQUEST_METHOD="POST",
            CONTENT_TYPE="application/json",
            CONTENT_LENGTH=str(len(body)),
            HTTP_ORIGIN="http://192.168.50.2",
            HTTP_X_DEXTEND_TOKEN=self.token,
        )
        env.update(extra)
        return subprocess.run(
            [self.binary], env=env, input=body, capture_output=True, check=True
        ).stdout.decode()

    def test_aa_video_profile_is_persisted_and_validated(self):
        self.env["QUERY_STRING"] = "view=aa-video"
        default = [624, 352, 44, 76, 32, 40]
        custom = [640, 360, 82, 78, 62, 58]
        self.assertEqual(self.get()["geometry"], default)
        self.assertEqual(self.get()["defaultGeometry"], default)
        self.assertIn('"reloadRequested":true', self.post(custom))
        self.assertTrue((self.root / "tmp/yamaha-sdl/aa-video-reload").is_file())
        for invalid in [custom[:-1], [802, 360, 0, 0, 0, 0], [640, 0, 0, 0, 0, 0],
                        [640, 360, 1, 0, 0, 0], [640, 360, -2, 0, 0, 0],
                        [640, 360, 400, 400, 0, 0], [640, 360, 0, 0, 240, 240]]:
            self.assertIn("Status: 400", self.post(invalid))
        self.assertIn("Status: 403", self.post(default, HTTP_X_DEXTEND_TOKEN=""))
        self.assertIn("Status: 403", self.post(default, HTTP_ORIGIN="http://localhost"))
        (self.root / "tmp/dextend-usb-lock").mkdir()
        self.assertIn("Status: 409", self.post(default))
        self.assertEqual(self.get()["geometry"], custom)
        (self.root / "etc/yamaha-sdl/aa-video.conf").write_text("[640")
        self.assertEqual(self.get()["geometry"], default)

    def forget_helper(self, remove=True):
        helper = self.root / "tmp/yamaha-sdl/bluetooth-autoconnect"
        helper.write_text(
            "#!/usr/bin/env python3\nimport pathlib,sys\n"
            "assert sys.argv[1]=='--forget'\n"
            "root=pathlib.Path(__file__).parents[1]\n"
            "(root/'called').write_text(sys.argv[2])\n"
            + (
                "for f in (root/'bluetooth').glob('*/linkkeys'):\n"
                " f.write_text(''.join(line for line in f.read_text().splitlines(True) if not line.startswith(sys.argv[2]+' ')))\n"
                if remove
                else ""
            )
        )
        helper.chmod(0o700)

    def test_forget_uses_daemon_and_checks_bond_disappearance(self):
        self.forget_helper()
        self.assertIn("Status: 200", self.post({"action": "forget", "id": B}))
        self.assertEqual([d["id"] for d in self.get()["devices"]], [A, C])
        self.assertEqual((self.root / "tmp/called").read_text(), B)
        self.assertNotIn(B, self.run_cli("--candidates"))

    def test_forget_acknowledged_but_not_removed_is_failure(self):
        self.forget_helper(remove=False)
        self.assertIn("Status: 503", self.post({"action": "forget", "id": B}))
        self.assertEqual(len(self.get()["devices"]), 3)

    def test_forget_validates_target_origin_token_and_installer_lock(self):
        self.forget_helper()
        for body in [
            {"action": "forget", "id": "02:00:00:00:00:99"},
            {"action": "forget", "id": B, "extra": True},
            {"action": "forget", "id": "$(reboot)"},
        ]:
            self.assertIn("Status: 400", self.post(body))
        for env in [{"HTTP_ORIGIN": "http://evil.invalid"}, {"HTTP_X_DEXTEND_TOKEN": ""}]:
            self.assertIn("Status: 403", self.post({"action": "forget", "id": B}, **env))
        (self.root / "tmp/dextend-usb-lock").mkdir()
        self.assertIn("Status: 409", self.post({"action": "forget", "id": B}))
        self.assertFalse((self.root / "tmp/called").exists())

    def test_forget_does_not_race_autoconnect(self):
        import fcntl

        self.forget_helper()
        with (self.root / "tmp/yamaha-sdl/phone-control.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertIn("Status: 409", self.post({"action": "forget", "id": B}))
        self.assertFalse((self.root / "tmp/called").exists())

    def test_only_bonded_phones_and_safe_json(self):
        devices = self.get()["devices"]
        self.assertEqual([d["id"] for d in devices], [A, B, C])
        self.assertEqual(devices[0]["name"], "Android <script>")
        self.assertEqual(devices[1]["platform"], "carplay")

    def test_bluetooth_names_always_produce_valid_utf8_json(self):
        names = next((self.root / "tmp/bluetooth").glob("*/names"))
        names.write_bytes(
            A.encode()
            + b" "
            + b"a" * 254
            + "🚀".encode()
            + b"\n"
            + B.encode()
            + b" "
            + "Zażółć 🚀".encode()
            + b"\t\x80\n"
            + C.encode()
            + b" bad\xed\xa0\x80\n"
        )
        devices = self.get()["devices"]
        self.assertEqual(devices[0]["name"], "a" * 254 + "\ufffd")
        self.assertEqual(devices[1]["name"], "Zażółć 🚀\t\ufffd")
        self.assertEqual(devices[2]["name"], "bad" + "\ufffd" * 3)

    def test_nonregular_bluetooth_cache_does_not_block_policy(self):
        names = next((self.root / "tmp/bluetooth").glob("*/names"))
        names.unlink()
        os.mkfifo(names)
        self.assertEqual([d["id"] for d in self.get()["devices"]], [A, B, C])

    def test_preferred_platform_then_device_order_survives_new_process(self):
        result = self.post({"schema": 1, "preferred": "carplay", "order": [C, A, B]})
        self.assertIn("Status: 200", result)
        self.assertEqual(
            self.run_cli("--candidates").splitlines(), [f"{B} IAP2", f"{C} AAP", f"{A} AAP"]
        )
        self.assertEqual(self.run_cli("--choose", A, B).strip(), "carplay")
        self.assertEqual([d["id"] for d in self.get()["devices"]], [B, C, A])
        self.assertEqual(
            (self.root / "etc/yamaha-sdl/phone-policy.json").stat().st_mode & 0o777, 0o600
        )
        self.post({"schema": 1, "preferred": "android-auto", "order": [C, A, B]})
        self.assertEqual(self.run_cli("--choose", A, B).strip(), "aa-wireless")

    def test_invalid_unknown_duplicate_and_cross_origin_do_not_write(self):
        good = {"schema": 1, "preferred": "none", "order": [B, A, C]}
        self.post(good)
        before = (self.root / "etc/yamaha-sdl/phone-policy.json").read_bytes()
        bad = [
            dict(good, order=[A, A]),
            dict(good, order=["02:00:00:00:00:99"]),
            dict(good, preferred="shell"),
            dict(good, extra=True),
            dict(good, schema=2),
        ]
        for payload in bad:
            self.assertIn("Status: 400", self.post(payload))
        for changes in [
            {"HTTP_X_DEXTEND_TOKEN": ""},
            {"HTTP_ORIGIN": "https://evil.example"},
            {"HTTP_HOST": "evil.example"},
        ]:
            self.assertIn("Status: 403", self.post(good, **changes))
        self.assertEqual((self.root / "etc/yamaha-sdl/phone-policy.json").read_bytes(), before)

    def test_policy_save_does_not_race_with_install_or_restore(self):
        lock = self.root / "tmp/dextend-usb-lock"
        lock.mkdir()
        payload = {"schema": 1, "preferred": "none", "order": [B]}
        self.assertIn("Status: 409", self.post(payload))
        self.assertFalse((self.root / "etc/yamaha-sdl/phone-policy.json").exists())
        lock.rmdir()
        self.assertIn("Status: 200", self.post(payload))
        self.assertFalse(lock.exists())

    def test_manual_order_with_no_platform_preference(self):
        result = self.post({"schema": 1, "preferred": "none", "order": [C, B]})
        self.assertIn("Status: 200", result)
        self.assertEqual(
            self.run_cli("--candidates").splitlines(), [f"{C} AAP", f"{B} IAP2", f"{A} AAP"]
        )
        self.assertEqual(self.run_cli("--choose", A, B).strip(), "carplay")

    def test_missing_profile_keeps_the_bond_in_the_configured_queue(self):
        (self.root / "tmp/bluetooth/services").write_text(f"{A} AAP\n{B} IAP2\n")
        for preference, expected in [
            ("none", [f"{C} AUTO", f"{A} AAP", f"{B} IAP2"]),
            ("carplay", [f"{B} IAP2", f"{A} AAP", f"{C} AUTO"]),
        ]:
            self.post({"schema": 1, "preferred": preference, "order": [C, A, B]})
            self.assertEqual(self.run_cli("--candidates").splitlines(), expected)

    def test_removed_bond_and_corrupt_config_are_safe(self):
        self.post({"schema": 1, "preferred": "carplay", "order": [B, A, C]})
        bt = next((self.root / "tmp/bluetooth").glob("*/linkkeys"))
        bt.write_text(f"{A} SECRET 0 4\n")
        self.assertEqual(self.run_cli("--candidates").strip(), f"{A} AAP")
        (self.root / "etc/yamaha-sdl/phone-policy.json").write_text("{broken")
        self.assertEqual(self.get()["preferred"], "none")


if __name__ == "__main__":
    unittest.main()
