#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Host sandbox tests: no device, network, host root writes or OEM daemons.

Uses synthetic firmware fingerprints and native runtime stubs to exercise
transactions. Envelope tests inspect the real codec independently.
"""

import gzip
import io
import json
import lzma
import os
import stat
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OEM_ROOT = Path(os.environ.get("DEXTEND_OEM_TEST_ROOT") or "/nonexistent/dextend-oem-fixture")
sys.path.insert(0, str(ROOT / "tools"))
from usb_image import crypt, decode, encode, sha
from build_usb import (
    installer_inputs,
    MAX_RUNTIME,
    release_sequence,
    render,
    sequence_from_image,
    verify_runtime,
)


class ReleaseSequenceTests(unittest.TestCase):
    def test_pinned_release_boot_controller_is_accepted_for_upgrade(self):
        members = decode((ROOT / "releases/A15W_Update.img").read_bytes())
        constants = dict(
            line.split("=", 1) for line in installer_inputs()["profile.sh"].decode().splitlines()
        )
        hook = sha(members["tmp/dextend/hook.sh"][0])
        boot = sha(members["tmp/dextend/boot.sh"][0])
        if hook == constants["hook_sha"]:
            self.assertEqual(boot, constants["boot_sha"])
        else:
            self.assertIn(
                (hook, boot),
                [
                    (constants[key + "_hook_sha"], constants[key + "_boot_sha"])
                    for key in ("beta1", "v033", "recent", "previous", "older")
                ],
            )

    def test_lab_version_derives_sequence(self):
        self.assertEqual(release_sequence("2026.11.14-usb-lab12", None), 202611140012)

    def test_release_versions_keep_explicit_sequence(self):
        for version in ("0.3-alpha", "1.0-beta", "1.200"):
            with self.subTest(version=version):
                self.assertEqual(release_sequence(version, 202611150004), 202611150004)

    def test_release_requires_sequence_in_range(self):
        for sequence in (None, 202611140004, 1000000000000):
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                release_sequence("0.3-alpha", sequence)
        self.assertEqual(release_sequence("0.3-alpha", 202611140005), 202611140005)
        self.assertEqual(release_sequence("0.3-alpha", 999999999999), 999999999999)

    def test_release_sequence_advances_from_previous_image(self):
        entry = "tmp/dextend/release/version.txt"
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "A15W_Update.img"
            image.write_bytes(
                encode(
                    {
                        "tmp/once.sh": (b"exit 0", 0o755),
                        entry: (b"0.6-alpha\n202611160006\n", 0o600),
                    }
                )
            )
            previous = sequence_from_image(image)
            self.assertEqual(release_sequence("0.7-alpha", None, previous), 202611160007)
            self.assertEqual(release_sequence("0.7-alpha", 202611160009, previous), 202611160009)
            with self.assertRaisesRegex(ValueError, "higher"):
                release_sequence("0.7-alpha", previous, previous)

    def test_previous_image_needs_sequence_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "A15W_Update.img"
            image.write_bytes(encode({"tmp/once.sh": (b"exit 0", 0o755)}))
            with self.assertRaisesRegex(ValueError, "Previous IMG"):
                sequence_from_image(image)

    def test_version_must_match_release_tag_format(self):
        for version in ("v0.3-alpha", "0.03-alpha", "0.3.0", "0.3-preview"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                release_sequence(version, 202611150004)


class EnvelopeTests(unittest.TestCase):
    def test_partial_blocks_roundtrip(self):
        for length in range(1, 65):
            data = bytes(range(length))
            self.assertEqual(crypt(crypt(data), True), data)
            if length % 16:
                self.assertEqual(crypt(data)[-(length % 16) :], data[-(length % 16) :])

    def test_deterministic_valid_archive(self):
        files = {"tmp/once.sh": (b"#!/bin/sh\nexit 1\n", 0o755), "tmp/dextend/x": (b"abc", 0o600)}
        image = encode(files)
        self.assertEqual(encode(files), image)
        self.assertEqual(decode(image), files)
        with self.assertRaises(Exception):
            decode(image[:-9])

    def test_reject_path_escape(self):
        for name in ("/etc/rcS", "tmp/dextend/../../etc/rcS", "tmp//once.sh", "etc/rcS"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                encode({name: (b"x", 0o600)})

    def test_reject_links_duplicates_and_special_files(self):
        for kind in ("symlink", "duplicate", "device"):
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w") as t:
                a = tarfile.TarInfo("tmp/once.sh")
                a.mode = 0o755
                t.addfile(a, io.BytesIO(b""))
                b = tarfile.TarInfo("tmp/once.sh" if kind == "duplicate" else "tmp/dextend/x")
                b.mode = 0o600
                if kind == "symlink":
                    b.type = tarfile.SYMTYPE
                    b.linkname = "/etc"
                if kind == "device":
                    b.type = tarfile.CHRTYPE
                t.addfile(b)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                decode(crypt(gzip.compress(raw.getvalue(), mtime=0)))


class RuntimeBudgetTests(unittest.TestCase):
    @staticmethod
    def compress(raw):
        return lzma.compress(
            raw,
            format=lzma.FORMAT_ALONE,
            filters=[{"id": lzma.FILTER_LZMA1, "dict_size": 1024 * 1024}],
        )

    def test_reject_unpack_limit_plus_one(self):
        payload = self.compress(bytes(MAX_RUNTIME + 1))
        with self.assertRaisesRegex(ValueError, "LZMA bounds"):
            verify_runtime(payload, "0.1-alpha")

    def test_reject_incomplete_duplicate_or_incorrect_checksum_list(self):
        version = "0.1-alpha"
        waiting = (version + "\n").encode()
        manifest = json.dumps(
            {"version": version, "members": {"waiting-version": sha(waiting)}}
        ).encode()
        entry = f"{sha(waiting)}  waiting-version\n".encode()
        cases = (b"", entry, entry * 2, f"{'0' * 64}  waiting-version\n".encode())
        for checks in cases:
            with self.subTest(checks=checks):
                raw = io.BytesIO()
                with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                    for name, data in {
                        "manifest.json": manifest,
                        "waiting-version": waiting,
                        "SHA256SUMS": checks,
                    }.items():
                        member = tarfile.TarInfo(name)
                        member.size = len(data)
                        archive.addfile(member, io.BytesIO(data))
                payload = self.compress(raw.getvalue())
                with self.assertRaisesRegex(ValueError, "Runtime checksum list"):
                    verify_runtime(payload, version)


class RadioConfigTests(unittest.TestCase):
    def runners(self):
        yield ["awk"]
        if shutil.which("qemu-arm") and (OEM_ROOT / "bin/busybox").is_file():
            yield ["qemu-arm", "-L", str(OEM_ROOT), str(OEM_ROOT / "bin/busybox"), "awk"]

    def patch(self, runner, current, original=None):
        with tempfile.TemporaryDirectory() as temp:
            current_path = Path(temp) / "current"
            current_path.write_bytes(current)
            command = runner + [
                "-v",
                "action=" + ("restore" if original is not None else "apply"),
                "-f",
                str(ROOT / "src/usb/radio-config.awk"),
                str(current_path),
            ]
            if original is not None:
                original_path = Path(temp) / "original"
                original_path.write_bytes(original)
                command += [str(original_path)]
            return subprocess.run(command, capture_output=True, timeout=5)

    def test_json_roundtrip_on_host_and_oem_awk(self):
        for runner in self.runners():
            for original in (
                {},
                {"CustomWifiName": "Prior SSID", "CustomBluetoothName": "Prior BT"},
                {"n": -1.2e-7, "s": '"\\\nZażółć', "a": [True, None, {"nested": [False, 7]}]},
            ):
                with self.subTest(runner=runner, original=original):
                    # JSON is passed as data, including shell metacharacters.
                    raw = json.dumps(original).encode() + bytes([10])
                    run = self.patch(runner, raw)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(
                        json.loads(run.stdout),
                        dict(original, CustomWifiName="Dextend", CustomBluetoothName="Dextend"),
                    )
                    restored = self.patch(runner, run.stdout, raw)
                    self.assertEqual(restored.returncode, 0, restored.stderr)
                    self.assertEqual(restored.stdout, raw)

    def test_malformed_json_refused_without_output(self):
        cases = [
            b"",
            b"[]",
            b"{",
            b'{"a":01}',
            b'{"a":true garbage}',
            b'{"a":1,}',
            b'{"a":1,"a":2}',
            b'{"CustomWifiN\\u0061me":"hidden"}',
            b'{"a":"\x01"}',
            b'{"a":NaN}',
            b'{"a":[' + b"[" * 40 + b"0" + b"]" * 41 + b"}",
            b"{} trailing",
        ]
        for runner in self.runners():
            for raw in cases:
                with self.subTest(runner=runner, raw=raw):
                    run = self.patch(runner, raw)
                    self.assertNotEqual(run.returncode, 0, run.stdout)
                    self.assertEqual(run.stdout, b"")


@unittest.skipUnless(shutil.which("bwrap") and shutil.which("busybox"), "needs bwrap and BusyBox")
class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dextend-usb-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in (
            "etc/init.d",
            "etc/alternatives",
            "script",
            "tmp",
            "mnt/UPAN",
            "proc/sys/vm",
            "sys/class/mtd/mtd2",
        ):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.write("etc/riddle.conf", b'{"OtherSetting": 7}\n')
        self.write(
            "etc/hostapd.conf",
            b"interface=wlan0\nssid=AutoLink-Fixture\nwpa_passphrase=fixture-only\nchannel=6\n",
            0o644,
        )
        self.write("etc/wifi_name", b"AutoLink-Fixture\n", 0o644)
        self.write("etc/bluetooth_name", b"AutoLink-BT-Fixture\n", 0o644)
        self.write("etc/box_product_type", b"A15W\n")
        self.write("etc/box_version", b"\x02\x00\x00\x00")
        self.write("etc/software_version", b"2026.07.31.1733\n")
        self.stock = b"#!/bin/sh\nifconfig lo up\n/script/start_main_service.sh &\n"
        self.ssh = self.stock.replace(
            b"ifconfig lo up\n", b"ifconfig lo up\n/usr/sbin/dropbear -B -p 22\n"
        )
        self.write("etc/init.d/rcS", self.stock)
        self.write("sys/class/mtd/mtd2/size", b"13107200\n")
        self.write("sys/class/mtd/mtd2/erasesize", b"65536\n")
        self.write(
            "proc/mounts",
            b"/dev/root / jffs2 rw,relatime 0 0\n/dev/sda1 /mnt/UPAN vfat rw,relatime 0 0\n",
        )
        self.write("proc/meminfo", b"MemFree: 65536 kB\nBuffers: 0 kB\nCached: 0 kB\n")
        self.write(
            "fake-uname",
            b'#!/bin/sh\ncase "$1" in -r) echo 3.14.52+g94d07bb;; -m) echo armv7l;; esac\n',
            0o755,
        )
        self.flash_space(4096)
        self.boot = (ROOT / "src/usb/boot.sh").read_bytes()
        self.hook = b"#!/bin/sh\n# fixture stable hook\nexit 0\n"
        self.legacy_hook = b"#!/bin/sh\n# fixture legacy hook\nexit 0\n"
        self.legacy = {
            "etc/yamaha-sdl/enabled": b"",
            "etc/yamaha-sdl/native-boot.sh": b"legacy boot",
            "etc/yamaha-sdl/native-runtime.tar.lzma": b"legacy runtime",
            "etc/wifi-usb/enabled": b"",
            "etc/wifi-usb/boot.sh": b"legacy wifi",
        }
        # Run exact OEM doUpdate(), but replace disk-copy work with an observable
        # stub. The OEM extractor and ARM decoder are NOT executed by this test.
        oem_updater = OEM_ROOT / "script/update_box.sh"
        if getattr(self, "release_image", None) is not None:
            oem = "#!/bin/sh\n# Synthetic OEM updater for the release image check.\n"
        elif oem_updater.is_file():
            oem = oem_updater.read_text()
        else:
            self.skipTest("set DEXTEND_OEM_TEST_ROOT to the OEM fixture tree")
        self.oem_functions = oem.split("\nif [ -e /etc/box_product_type ]; then\n")[0]
        self.write("script/update_box.sh", oem.encode())
        self.write(
            "script/quickly_update.sh", b"#!/bin/sh\ntouch /tmp/oem-copy-ran\nexit 0\n", 0o755
        )
        self.write("script/start_main_service.sh", b"fixture OEM service\n")

    def write(self, name, data, mode=0o600):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        p.chmod(mode)

    def flash_space(self, kib):
        self.write(
            "fake-df",
            f'#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted"\necho "/dev/root 12800 0 {kib} 0% /"\n'.encode(),
            0o755,
        )

    def snapshot(self, trees=("etc", "script")):
        state = {}
        for tree in trees:
            base = self.root / tree
            for path in (base, *base.rglob("*")):
                metadata = path.lstat()
                mode = metadata.st_mode
                if stat.S_ISREG(mode):
                    data = sha(path.read_bytes())
                elif stat.S_ISLNK(mode):
                    data = os.readlink(path)
                else:
                    data = None
                state[str(path.relative_to(self.root))] = (
                    mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    data,
                )
        return state

    def package(
        self,
        mode,
        version="test-1",
        native=b"#!/bin/sh\nexit 0\n",
        installed_restore=False,
        service=False,
    ):
        sequence = 1 if version == "test-1" else 2
        constants = {
            "restore_0_22_sidecar_sha": json.loads((ROOT / "src/usb/profile.json").read_text())[
                "restore_0_22_sidecar_sha256"
            ],
            "stock_rcs": sha(self.stock),
            "ssh_rcs": sha(self.ssh),
            "legacy_hook": sha(self.legacy_hook),
            "hook_sha": sha(self.hook),
            "boot_sha": sha(self.boot),
            "format_sha": sha(b"dextend-usb-v1\n"),
            "empty_sha": sha(b""),
        }
        if hasattr(self, "additional_oem_profiles"):
            constants["additional_oem_profiles"] = self.additional_oem_profiles
        if hasattr(self, "previous_boot"):
            constants["previous_boot_sha"] = sha(self.previous_boot)
            constants["previous_hook_sha"] = sha(self.previous_hook)
        if hasattr(self, "older_boot"):
            constants["older_boot_sha"] = sha(self.older_boot)
            constants["older_hook_sha"] = sha(self.older_hook)
        self.write(
            "tmp/update/tmp/dextend/profile.sh",
            "".join(f"{k}={v}\n" for k, v in constants.items()).encode(),
        )
        self.write(
            "tmp/update/tmp/dextend/OEM.sha256",
            "".join(
                f"{sha((self.root / n).read_bytes())}  {n}\n"
                for n in ("script/update_box.sh", "script/start_main_service.sh")
            ).encode(),
        )
        self.write(
            "tmp/update/tmp/dextend/LEGACY.sha256",
            "".join(f"{sha(v)}  {n}\n" for n, v in self.legacy.items()).encode(),
        )
        for name, data in {
            "boot.sh": self.boot,
            "hook.sh": self.hook,
            "empty": b"",
            "format": b"dextend-usb-v1\n",
        }.items():
            self.write("tmp/update/tmp/dextend/" + name, data)
        for name in ("radio-names.sh", "radio-config.awk"):
            self.write("tmp/update/tmp/dextend/" + name, (ROOT / "src/usb" / name).read_bytes())
        template = (ROOT / "src/usb/transaction.sh.in").read_bytes()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            if installed_restore:
                files = {
                    name: (self.root / "tmp/update/tmp/dextend" / name).read_bytes()
                    for name in (
                        "profile.sh",
                        "OEM.sha256",
                        "LEGACY.sha256",
                        "format",
                        "radio-names.sh",
                        "radio-config.awk",
                    )
                }
                files["update-protocol"] = b"1\n" if installed_restore == "v1" else b"2\n"
                files["transaction.sh"] = render(
                    template,
                    {
                        "MODE": "restore-oem",
                        "RELEASE": "",
                        "VERSION": version,
                        "SEQUENCE": 0,
                    },
                ).replace(
                    b"\nwrite_started=1\n", b"\nwrite_started=1\n: > /tmp/installed-restore-ran\n", 1
                )
                if hasattr(self, "restore_worker"):
                    files["transaction.sh"] = self.restore_worker
                for name, data in files.items():
                    entry = tarfile.TarInfo("restore/" + name)
                    entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
        payload = {
            "native-boot.sh": native,
            "native-runtime.tar.lzma": lzma.compress(buffer.getvalue(), format=lzma.FORMAT_ALONE),
            "version.txt": (version + "\n" + str(sequence) + "\n").encode(),
        }
        if service:
            payload["service-boot.sh"] = getattr(
                self, "service_launcher", b"#!/bin/sh\necho started >> /tmp/service-starts\n"
            )
            payload["service-runtime.tar.lzma"] = getattr(
                self, "service_payload", b"fixture service payload"
            )
        sums = "".join(f"{sha(v)}  {n}\n" for n, v in sorted(payload.items())).encode()
        ident = sha(sums)
        payload["SHA256SUMS"] = sums
        for name, data in payload.items():
            self.write("tmp/update/tmp/dextend/release/" + name, data)
        self.write(
            "tmp/update/tmp/dextend/transaction.sh",
            render(
                (ROOT / "src/usb/transaction.sh.in").read_bytes(),
                {"MODE": mode, "RELEASE": ident, "VERSION": version, "SEQUENCE": sequence},
            ),
        )
        files = {
            str(p.relative_to(self.root / "tmp/update/tmp/dextend")): p.read_bytes()
            for p in (self.root / "tmp/update/tmp/dextend").rglob("*")
            if p.is_file() and p.name != "BUNDLE.sha256"
        }
        checks = "".join(f"{sha(v)}  {n}\n" for n, v in sorted(files.items())).encode()
        self.write("tmp/update/tmp/dextend/BUNDLE.sha256", checks)
        from build_usb import installer_entry

        self.write("tmp/update/tmp/once.sh", installer_entry(checks, mode, version), 0o755)
        self.write(
            "tmp/update/tmp/finish.sh",
            b'#!/bin/sh\nexec sh /tmp/update/tmp/dextend/transaction.sh finish "${1:-1}"\n',
            0o755,
        )
        return ident

    def test_radio_names_install_update_restore_original_inventory(self):
        self.write("etc/.custom_wifi_name", b"My original WiFi\n", 0o640)
        self.write("etc/.custom_bluetooth_name", b"My original Bluetooth\n", 0o600)
        original = {
            "OtherSetting": 7,
            "CustomWifiName": "My original WiFi",
            "CustomBluetoothName": "My original Bluetooth",
        }
        self.write("etc/riddle.conf", json.dumps(original).encode())
        before = self.snapshot()
        _, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        for n in ("wifi_name", "bluetooth_name", ".custom_wifi_name", ".custom_bluetooth_name"):
            self.assertEqual((self.root / "etc" / n).read_text(), "Dextend\n")
        self.assertEqual(
            json.loads((self.root / "etc/riddle.conf").read_text()),
            dict(original, CustomWifiName="Dextend", CustomBluetoothName="Dextend"),
        )
        self.assertIn("ssid=Dextend\n", (self.root / "etc/hostapd.conf").read_text())
        self.assertIn("wpa_passphrase=fixture-only\n", (self.root / "etc/hostapd.conf").read_text())
        with tarfile.open(
            next((self.root / "mnt/UPAN").glob("dextend-backup.*/before.tar"))
        ) as backup:
            self.assertEqual(
                backup.extractfile("etc/riddle.conf").read(), json.dumps(original).encode()
            )
        self.assertEqual(self.boot_once().returncode, 0)
        _, run = self.apply("install", "test-2", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_radio_upgrade_from_published_0_26_preserves_original_names(self):
        archive = os.environ.get("DEXTEND_LEGACY_IMG_DIR")
        if not archive or not (Path(archive) / "0.26-alpha.img").is_file():
            self.skipTest("optional legacy upgrade fixture unavailable")
        old_img = (Path(archive) / "0.26-alpha.img").read_bytes()
        old = decode(old_img)
        with tarfile.open(
            fileobj=io.BytesIO(
                lzma.decompress(old["tmp/dextend/release/native-runtime.tar.lzma"][0])
            )
        ) as archive:
            self.restore_worker = archive.extractfile("restore/transaction.sh").read()
        before = self.snapshot()
        _, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        # The published release predates branding and never had this state.
        run = self.run_sandbox("sh /tmp/update/tmp/dextend/radio-names.sh restore")
        self.assertEqual(run.returncode, 0, run.stderr)
        shutil.rmtree(self.root / "etc/yamaha-sdl/usb-v1/radio")
        self.assertEqual(self.boot_once().returncode, 0)
        del self.restore_worker
        _, run = self.apply("install", "test-2", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((self.root / "etc/wifi_name").read_text(), "Dextend\n")
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_radio_restore_preserves_later_password_channel_and_settings(self):
        _, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        config = json.loads((self.root / "etc/riddle.conf").read_text())
        config["OtherSetting"] = {"enabled": True, "values": [1, 'quoted " value']}
        self.write("etc/riddle.conf", json.dumps(config).encode())
        self.write(
            "etc/hostapd.conf",
            b"interface=wlan0\nssid=Dextend\nwpa_passphrase=new-fixture-only\nchannel=11\n",
        )
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(
            json.loads((self.root / "etc/riddle.conf").read_text()),
            {"OtherSetting": config["OtherSetting"]},
        )
        self.assertEqual(
            (self.root / "etc/hostapd.conf").read_text(),
            "interface=wlan0\nssid=AutoLink-Fixture\nwpa_passphrase=new-fixture-only\nchannel=11\n",
        )
        self.assertFalse((self.root / "etc/.custom_wifi_name").exists())
        self.assertFalse((self.root / "etc/.custom_bluetooth_name").exists())

    def test_radio_corrupt_baseline_rejects_without_writes(self):
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.write("etc/yamaha-sdl/usb-v1/radio/wifi_name", b"corrupt baseline")
        self.assert_rejected_unchanged("INVALID_RADIO_NAMES", mode="restore-oem")

    def test_radio_symlink_rejected_without_writes(self):
        (self.root / "etc/.custom_wifi_name").symlink_to("wifi_name")
        self.assert_rejected_unchanged("INVALID_RADIO_NAMES")

    def test_radio_restore_reserves_space_for_original_settings(self):
        self.write("etc/riddle.conf", json.dumps({"payload": "x" * 5000}).encode())
        before = self.snapshot()
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        budget = self.run_sandbox("sh /tmp/update/tmp/dextend/radio-names.sh budget")
        self.assertEqual(budget.returncode, 0, budget.stderr)
        minimum = 64 + int(budget.stdout)
        self.flash_space(minimum - 1)
        self.assert_rejected_unchanged("INSUFFICIENT_FLASH_FOR_RESTORE", mode="restore-oem")
        self.flash_space(minimum)
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_radio_expanded_json_limit_rejects_before_flash_writes(self):
        self.write("etc/riddle.conf", json.dumps({"payload": "x" * 65500}).encode())
        self.assert_rejected_unchanged("INVALID_RADIO_NAMES")

    def test_radio_invalid_json_rejected_without_writes(self):
        self.write("etc/riddle.conf", b'{"CustomWifiName":"a","CustomWifiName":"b"}')
        self.assert_rejected_unchanged("INVALID_RADIO_NAMES")

    def test_radio_interrupted_write_keeps_baseline_for_restore(self):
        before = self.snapshot()
        self.package("install")
        self.write(
            "fail-radio-mv",
            b'#!/bin/sh\ncase "$*" in */etc/bluetooth_name) exit 1;; esac\nexec /usr/bin/busybox mv "$@"\n',
            0o755,
        )
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-radio-mv", "/usr/bin/mv")]
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("RADIO_BT_RENAME_FAILED", self.result())
        self.assertTrue((self.root / "etc/yamaha-sdl/usb-v1/radio/SHA256SUMS").exists())
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.snapshot(), before)

    def private_bus_fixture(
        self, executable="/usr/sbin/dbus-daemon", namespace="mnt:[private]", complete=True
    ):
        self.package("install")
        self.write("proc/77/cmdline", b"dbus-daemon\0--system\0--print-pid\0--print-address\0")
        self.write(
            "proc/77/stat", b"77 (dbus-daemon) S 1 77 77 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1234 0\n"
        )
        self.write(
            "proc/77/mountinfo",
            (
                "30 22 0:13 /yamaha-sdl/bt-audio-abcdef /etc/riddle.conf rw - tmpfs tmpfs rw\n"
                "31 26 0:13 /yamaha-sdl/bt-audio-ghijkl /tmp/.riddle.conf rw - tmpfs tmpfs rw\n"
                + (
                    "32 22 0:13 /yamaha-sdl/android-mode-mnopqr//deleted /etc/android_work_mode rw - tmpfs tmpfs rw\n"
                    if complete
                    else ""
                )
            ).encode(),
        )
        for pid in ("1", "77"):
            (self.root / f"proc/{pid}/ns").mkdir(parents=True)
        (self.root / "proc/77/exe").symlink_to(executable)
        (self.root / "proc/77/ns/mnt").symlink_to(namespace)
        (self.root / "proc/1/ns/mnt").symlink_to("mnt:[init]")

    def test_quiesce_releases_verified_detached_bus(self):
        self.private_bus_fixture()
        run = self.run_sandbox(
            'kill() { echo "$*" >> /tmp/signals; rm -rf /proc/77; }; set -- quiesce; . /tmp/update/tmp/dextend/radio-names.sh'
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((self.root / "tmp/signals").read_text().strip(), "-TERM 77")

    def test_quiesce_rechecks_pid_before_escalation(self):
        self.private_bus_fixture()
        run = self.run_sandbox(
            "kill() { echo \"$*\" >> /tmp/signals; sed -i 's/1234/5678/' /proc/77/stat; }; set -- quiesce; . /tmp/update/tmp/dextend/radio-names.sh"
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual((self.root / "tmp/signals").read_text().strip(), "-TERM 77")

    def test_quiesce_escalates_only_same_private_bus(self):
        self.private_bus_fixture()
        run = self.run_sandbox(
            'kill() { echo "$*" >> /tmp/signals; [ "$1" != -KILL ] || rm -rf /proc/77; }; set -- quiesce; . /tmp/update/tmp/dextend/radio-names.sh'
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(
            (self.root / "tmp/signals").read_text().splitlines(), ["-TERM 77", "-KILL 77"]
        )

    def test_quiesce_keeps_foreign_bus_and_mount(self):
        self.private_bus_fixture(executable="/usr/bin/unrelated")
        run = self.run_sandbox(
            "kill() { echo called > /tmp/signals; }; set -- quiesce; . /tmp/update/tmp/dextend/radio-names.sh"
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.root / "tmp/signals").exists())

    def test_quiesce_keeps_system_namespace_bus(self):
        self.private_bus_fixture(namespace="mnt:[init]")
        run = self.run_sandbox(
            "kill() { echo called > /tmp/signals; }; set -- quiesce; . /tmp/update/tmp/dextend/radio-names.sh"
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.root / "tmp/signals").exists())

    def test_quiesce_keeps_bus_with_incomplete_mount_identity(self):
        self.private_bus_fixture(complete=False)
        run = self.run_sandbox(
            "kill() { echo called > /tmp/signals; }; set -- quiesce; . /tmp/update/tmp/dextend/radio-names.sh"
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.root / "tmp/signals").exists())

    def test_radio_foreign_mount_rejects_before_flash_writes(self):
        self.write("proc/77/mountinfo", b"8 1 0:1 / /etc/riddle.conf rw - tmpfs tmpfs rw\n")
        self.assert_rejected_unchanged("RADIO_CONFIG_IN_USE")

    def test_interrupted_radio_install_reclaims_checked_release_before_space_check(self):
        before = self.snapshot()
        first = self.package("install", service=True)
        self.write(
            "fail-radio-mv",
            b'#!/bin/sh\ncase "$*" in */etc/riddle.conf) exit 1;; esac\nexec /usr/bin/busybox mv "$@"\n',
            0o755,
        )
        failed = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-radio-mv", "/usr/bin/mv")]
        )
        self.assertNotEqual(failed.returncode, 0)
        state = self.root / "etc/yamaha-sdl/usb-v1"
        self.assertEqual((state / "transaction").read_text().strip(), first)
        self.assertFalse((state / "active").exists())
        self.assertEqual(
            (self.root / "etc/riddle.conf").read_bytes(), (state / "radio/riddle.conf").read_bytes()
        )
        self.write(
            "fake-df",
            b'#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted on"\nif [ -e /etc/yamaha-sdl/usb-v1/transaction ]; then echo "fixture 12800 12672 128 99% /"; else echo "fixture 12800 8704 4096 68% /"; fi\n',
            0o755,
        )
        second = self.package("install", "test-2", service=True)
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh")
        self.assertEqual(run.returncode, 0, run.stderr + self.result())
        self.assertEqual((state / "active").read_text().strip(), second)
        self.assertFalse((state / "releases" / first).exists())
        self.assertEqual(self.boot_once().returncode, 0)
        _, restored = self.apply("restore-oem")
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_interrupted_install_with_damaged_release_is_preserved(self):
        ident = self.package("install", service=True)
        self.write(
            "fail-radio-mv",
            b'#!/bin/sh\ncase "$*" in */etc/riddle.conf) exit 1;; esac\nexec /usr/bin/busybox mv "$@"\n',
            0o755,
        )
        self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-radio-mv", "/usr/bin/mv")]
        )
        self.write(
            "etc/yamaha-sdl/usb-v1/releases/" + ident + "/native-runtime.tar.lzma", b"broken"
        )
        self.assert_rejected_unchanged("DAMAGED_INTERRUPTED_RELEASE")

    def test_usb_journal_records_success_and_preserves_it_on_retry(self):
        self.package("install")
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh && sh /tmp/update/tmp/finish.sh 0")
        self.assertEqual(run.returncode, 0, run.stderr)
        completed = self.result()
        steps = [line.split()[:2] for line in completed.splitlines() if line.startswith("step=")]
        self.assertGreater(len(steps), 20)
        self.assertEqual(len(steps) % 2, 0)
        for start, end in zip(steps[::2], steps[1::2]):
            self.assertEqual(start, [end[0], "status=started"])
            self.assertEqual(end[1], "status=ok")
        self.assertEqual(steps[-1][0], "step=oem_finish")
        _, retry = self.apply("install")
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn("result=ALREADY_INSTALLED", self.result())
        archives = list((self.root / "mnt/UPAN").glob("dextend-log.*/DEXTEND-RESULT.txt"))
        self.assertEqual([p.read_text() for p in archives], [completed])

    def test_failed_history_copy_keeps_previous_usb_report(self):
        self.package("install")
        previous = b"DEXTEND USB lab v1\nresult=PREPARED_FOR_BOOT\n"
        self.write("mnt/UPAN/DEXTEND-RESULT.txt", previous)
        before = self.snapshot()
        self.write("fail-archive-copy", b"#!/bin/sh\nexit 1\n", 0o755)
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-archive-copy", "/usr/bin/cp")]
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(self.result().encode(), previous)
        self.assertEqual(self.snapshot(), before)

    def test_usb_journal_survives_worker_killed_during_copy(self):
        self.package("install")
        self.write(
            "interrupt-copy",
            b"""#!/bin/sh
case "$1" in */dextend/release/*) kill -KILL "$PPID"; exit 1 ;; esac
exec /usr/bin/busybox cp "$@"
""",
            0o755,
        )
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "interrupt-copy", "/usr/bin/cp")]
        )
        self.assertNotEqual(run.returncode, 0)
        report = self.result()
        self.assertIn("result=WRITING", report)
        self.assertIn("write_started=1", report)
        self.assertEqual(report.splitlines()[-1], "step=copy_release_files status=started")

    def test_competing_installer_cannot_steal_report_or_lock(self):
        ident = self.package("install")
        self.write(
            "fake-sync",
            b"""#!/bin/sh
if mkdir /tmp/first-sync 2>/dev/null; then
 : > /tmp/first-report-waiting
 while [ ! -e /tmp/release-first ]; do sleep 0.02; done
fi
exit 0
""",
            0o755,
        )
        run = self.run_sandbox(
            """sh /tmp/update/tmp/once.sh > /tmp/first.log 2>&1 &
first=$!
while [ ! -e /tmp/first-report-waiting ]; do sleep 0.02; done
sh /tmp/update/tmp/once.sh > /tmp/second.log 2>&1
second_rc=$?
test -d /tmp/dextend-usb-lock || exit 9
: > /tmp/release-first
wait "$first"
first_rc=$?
printf 'first_rc=%s second_rc=%s\\n' "$first_rc" "$second_rc"
cat /tmp/first.log /tmp/second.log
""",
            [(self.root / "fake-sync", "/usr/bin/sync")],
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("first_rc=0 second_rc=1", run.stdout)
        self.assertIn("ANOTHER_INSTALLER", run.stdout)
        self.assertIn("result=FILES_COMMITTED", self.result())
        self.assertNotIn("USB_REPORT_FAILED", self.result())
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), ident)
        self.assertFalse((self.root / "tmp/dextend-usb-lock").exists())
        self.assertEqual(list((self.root / "mnt/UPAN").glob(".dextend-result.*")), [])

    def test_busy_installer_preserves_existing_report_and_stage(self):
        self.package("install")
        self.write("mnt/UPAN/DEXTEND-RESULT.txt", b"owner result")
        self.write("mnt/UPAN/DEXTEND-RESULT.txt.new", b"foreign staging file")
        (self.root / "tmp/dextend-usb-lock").mkdir()
        before = self.snapshot(("etc", "script", "mnt"))
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("ANOTHER_INSTALLER", run.stderr)
        self.assertEqual(before, self.snapshot(("etc", "script", "mnt")))
        self.assertTrue((self.root / "tmp/dextend-usb-lock").is_dir())

    def test_report_io_failure_records_phase_without_flash_writes(self):
        for phase in ("create", "sync_before_rename", "rename", "sync_after_rename"):
            with self.subTest(phase=phase):
                # Inject failure into publication of this report, not archival of the prior attempt.
                (self.root / "mnt/UPAN/DEXTEND-RESULT.txt").unlink(missing_ok=True)
                marker = self.root / "tmp/failure-count"
                if marker.exists():
                    marker.unlink()
                self.package("install")
                before = self.snapshot()
                command = "mktemp" if phase == "create" else ("mv" if phase == "rename" else "sync")
                fail_at = 2 if phase == "sync_after_rename" else 1
                self.write(
                    "fail-report",
                    f"""#!/bin/sh
n=$(cat /tmp/failure-count 2>/dev/null || echo 0)
n=$((n+1)); echo "$n" > /tmp/failure-count
[ "$n" != {fail_at} ] || exit 1
exec /usr/bin/busybox {command} "$@"
""".encode(),
                    0o755,
                )
                run = self.run_sandbox(
                    "sh /tmp/update/tmp/once.sh",
                    [(self.root / "fail-report", "/usr/bin/" + command)],
                )
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("detail=USB_REPORT_FAILED", self.result())
                self.assertIn("report_error=" + phase, self.result())
                self.assertEqual(before, self.snapshot())
                self.assertEqual(list((self.root / "mnt/UPAN").glob(".dextend-result.*")), [])

    def test_report_short_write_is_not_treated_as_success(self):
        self.package("install")
        before = self.snapshot()
        run = self.run_sandbox("""printf() {
 case "$1" in 'DEXTEND USB lab v1'*)
  if [ ! -e /tmp/short-write ]; then
   : > /tmp/short-write
   command printf partial
   return 1
  fi;;
 esac
 command printf "$@"
}
. /tmp/update/tmp/dextend/transaction.sh
""")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("detail=USB_REPORT_FAILED", self.result())
        self.assertIn("report_error=write", self.result())
        self.assertEqual(before, self.snapshot())
        self.assertEqual(list((self.root / "mnt/UPAN").glob(".dextend-result.*")), [])

    @unittest.skipUnless(shutil.which("qemu-arm"), "needs qemu-arm")
    def test_report_with_actual_oem_busybox_utilities(self):
        self.package("probe")
        wrappers = []
        for name in ("mktemp", "mv", "sync"):
            path = self.root / ("arm-" + name)
            self.write(
                path.name,
                (
                    "#!/bin/sh\nexec /usr/bin/qemu-arm -L /oem /oem/bin/busybox " + name + ' "$@"\n'
                ).encode(),
                0o755,
            )
            wrappers.append((path, "/usr/bin/" + name))
        before = self.snapshot()
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh", [(OEM_ROOT, "/oem"), *wrappers])
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn("result=PROBE_OK", self.result())
        self.assertNotIn("report_error=", self.result())
        self.assertEqual(before, self.snapshot())

    def test_binary_oem_variant_matches_device_fixture(self):
        original = OEM_ROOT / "etc/box_version"
        if not original.is_file():
            self.skipTest("OEM fixture required")
        self.assertEqual(original.read_bytes(), b"\x02\x00\x00\x00")
        self.write("etc/box_version", original.read_bytes())
        _, run = self.apply("probe")
        self.assertNotEqual(run.returncode, 0)  # Intentional OEM copy abort.
        self.assertIn("result=PROBE_OK", self.result())
        self.assertIn("profile_matches=1", self.result())
        self.assertNotIn("mismatch=/etc/box_version", self.result())

    def test_install_on_custom_a15w(self):
        self.write("etc/box_version", b"another variant")
        self.write("etc/software_version", b"2024.01.01.1234")
        self.write("etc/init.d/rcS", b"# local services")
        self.write("fake-uname", b"#!/bin/sh\necho different\n", 0o755)
        self.write("sys/class/mtd/mtd2/size", b"other")
        self.write("proc/meminfo", b"MemFree: 128 kB\n")
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("actual_kernel=different", self.result())
        self.assertEqual((self.root / "etc/init.d/rcS").read_bytes(), b"# local services")

    def test_service_survives_native_failure_and_next_boot(self):
        ident = self.package("install", native=b"exit 1\n", installed_restore=True, service=True)
        self.assertEqual(self.run_sandbox("sh /tmp/update/tmp/once.sh").returncode, 0)
        self.assertNotEqual(self.boot_once().returncode, 0)
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), "none")
        self.assertEqual(self.boot_once().returncode, 0)
        self.assertEqual((self.root / "tmp/service-starts").read_text(), "started\nstarted\n")
        self.assertEqual(
            (self.root / "etc/yamaha-sdl/usb-v1/service-release").read_text().strip(), ident
        )
        # Its own checked remover can still remove the failed release.
        self.package("install", version="test-2", installed_restore=True, service=True)
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh")
        self.assertEqual(run.returncode, 0, run.stderr + self.result())
        self.assertTrue((self.root / "tmp/installed-restore-ran").exists())

    def test_native_damage_does_not_block_service_but_service_damage_does(self):
        ident = self.package("install", service=True)
        self.assertEqual(self.run_sandbox("sh /tmp/update/tmp/once.sh").returncode, 0)
        release = self.root / "etc/yamaha-sdl/usb-v1/releases" / ident
        (release / "native-runtime.tar.lzma").write_bytes(b"damaged")
        self.assertNotEqual(self.boot_once().returncode, 0)
        self.assertEqual((self.root / "tmp/service-starts").read_text(), "started\n")
        (release / "service-boot.sh").write_bytes(b"echo unsafe >> /tmp/service-starts\n")
        self.boot_once()
        self.assertEqual((self.root / "tmp/service-starts").read_text(), "started\n")
        self.assertEqual(
            (self.root / "tmp/dextend-service-status").read_text().strip(), "SERVICE_START_FAILED"
        )

    def test_service_launcher_unpacks_on_both_cold_boots_after_native_failure(self):
        # Use the real installer, controller and unpacker. The manager and ARM
        # binaries are stubs here; their lifecycle/authentication have separate tests.
        files = {
            n: b"#!/bin/sh\nexit 0\n"
            for n in ("debug-api", "dropbearmulti", "wpa_supplicant", "service-key", "updater-http")
        }
        files["service.sh"] = (
            b"#!/bin/sh\necho tick > /tmp/dextend-service/heartbeat\necho manager >> /tmp/service-starts\n"
        )
        files["start-updater.sh"] = b"#!/bin/sh\necho updater >> /tmp/updater-starts\n"
        files["SHA256SUMS"] = "".join(
            f"{sha(data)}  {name}\n" for name, data in sorted(files.items())
        ).encode()
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as archive:
            for name, data in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        self.service_payload = lzma.compress(raw.getvalue(), format=lzma.FORMAT_ALONE)
        self.service_launcher = (ROOT / "src/runtime/start-service.sh").read_bytes()
        self.package("install", native=b"exit 1\n", service=True)
        self.assertEqual(self.run_sandbox("sh /tmp/update/tmp/once.sh").returncode, 0)
        self.assertNotEqual(self.boot_once().returncode, 0)
        self.assertTrue((self.root / "tmp/dextend-service/heartbeat").is_file())
        shutil.rmtree(self.root / "tmp/dextend-service")  # RAM is empty after reboot.
        self.assertEqual(self.boot_once().returncode, 0)
        self.assertEqual((self.root / "tmp/service-starts").read_text(), "manager\nmanager\n")
        self.assertEqual((self.root / "tmp/updater-starts").read_text(), "updater\nupdater\n")

    def run_sandbox(self, script, overrides=(), persistent=()):
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
            "usr/sbin",
            "/sbin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--dev",
            "/dev",
            "--unshare-net",
            "--unshare-pid",
            "--die-with-parent",
        ]
        for name in ("etc", "script", "tmp", "mnt", "proc", "sys", *persistent):
            cmd += ["--bind", str(self.root / name), "/" + name]
        cmd += ["--ro-bind", "/etc/alternatives", "/etc/alternatives"]
        cmd += [
            "--ro-bind",
            str(self.root / "fake-uname"),
            "/usr/bin/uname",
            "--ro-bind",
            str(self.root / "fake-df"),
            "/usr/bin/df",
        ]
        for src, dst in overrides:
            cmd += ["--ro-bind", str(src), dst]
        if persistent:
            cmd += ["--remount-ro", "/"]
        cmd += ["/usr/bin/busybox", "ash", "-c", script]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20)

    def apply(self, mode, version="test-1", native=b"#!/bin/sh\nexit 0\n", installed_restore=False):
        ident = self.package(mode, version, native, installed_restore)
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh")
        return ident, run

    def result(self):
        return (self.root / "mnt/UPAN/DEXTEND-RESULT.txt").read_text()

    def assert_rejected_unchanged(self, code, mode="install"):
        before = self.snapshot()
        _, run = self.apply(mode)
        self.assertNotEqual(run.returncode, 0, run.stderr)
        self.assertIn("detail=" + code, self.result())
        self.assertEqual(self.snapshot(), before)

    def test_network_update_without_usb_preserves_oem(self):
        first, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.run_sandbox("sh /etc/yamaha-sdl/usb-v1/boot.sh").returncode, 0)
        self.write("etc/riddle.conf", b'{"fixture": "OEM settings"}')
        self.write("proc/mounts", b"/dev/root / jffs2 rw,relatime 0 0\n")
        (self.root / "tmp/dextend-updater").mkdir()
        second = self.package("install", "test-2", installed_restore=True)
        run = self.run_sandbox(
            "mkdir -p /tmp/dextend-updater/extracted/tmp; cp -R /tmp/update/tmp/dextend /tmp/dextend-updater/extracted/tmp/; sh /tmp/dextend-updater/extracted/tmp/dextend/transaction.sh ota"
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(
            "result=FILES_COMMITTED",
            (self.root / "tmp/dextend-updater/DEXTEND-RESULT.txt").read_text(),
        )
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), second)
        self.assertFalse((self.root / "etc/yamaha-sdl/usb-v1/releases" / first).exists())
        self.assertTrue((self.root / "tmp/installed-restore-ran").exists())
        self.assertEqual(
            json.loads((self.root / "etc/riddle.conf").read_text())["fixture"], "OEM settings"
        )

    def test_network_rejects_old_restore_contract_before_write(self):
        _, run = self.apply("install", installed_restore="v1")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.run_sandbox("sh /etc/yamaha-sdl/usb-v1/boot.sh").returncode, 0)
        (self.root / "tmp/dextend-updater").mkdir()
        self.package("install", "test-2")
        before = self.snapshot()
        run = self.run_sandbox(
            "mkdir -p /tmp/dextend-updater/extracted/tmp; cp -R /tmp/update/tmp/dextend /tmp/dextend-updater/extracted/tmp/; sh /tmp/dextend-updater/extracted/tmp/dextend/transaction.sh ota"
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertIn(
            "NETWORK_RESTORE_UNSUPPORTED",
            (self.root / "tmp/dextend-updater/DEXTEND-RESULT.txt").read_text(),
        )
        # USB must continue to support that previous contract.
        _, run = self.apply("install", "test-2")
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_network_preflight_rejects_without_writes(self):
        self.package("install")
        (self.root / "tmp/dextend-updater").mkdir()
        self.write("etc/box_product_type", b"WRONG\n")
        before = self.snapshot()
        run = self.run_sandbox(
            "mkdir -p /tmp/dextend-updater/extracted/tmp; cp -R /tmp/update/tmp/dextend /tmp/dextend-updater/extracted/tmp/; sh /tmp/dextend-updater/extracted/tmp/dextend/transaction.sh ota"
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertIn(
            "result=REJECTED", (self.root / "tmp/dextend-updater/DEXTEND-RESULT.txt").read_text()
        )

    def test_probe_reports_unknown_firmware_without_persistent_writes(self):
        self.package("probe")
        self.write("etc/software_version", b"2026.10.01.1234\n")
        self.write("etc/module_version", b"synthetic-private-module-metadata")
        before = self.snapshot()
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh")
        self.assertEqual(run.returncode, 1, run.stderr)
        report = self.result()
        self.assertIn("result=PROBE_OK", report)
        self.assertIn("profile_matches=0", report)
        self.assertIn("probe_revision=2", report)
        self.assertIn("actual_software_version=2026.10.01.1234", report)
        self.assertIn("observed_sha256=/etc/module_version ", report)
        self.assertNotIn("synthetic-private-module-metadata", report)
        self.assertEqual(self.snapshot(), before)

    def test_probe_has_no_persistent_writes_and_stops_oem(self):
        self.package("probe")
        before = self.snapshot()
        self.write("tmp/oem-functions", self.oem_functions.encode())
        run = self.run_sandbox(". /tmp/oem-functions; export updatepath=/tmp/update; doUpdate img")
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertIn("result=PROBE_OK", self.result())
        self.assertFalse((self.root / "tmp/oem-copy-ran").exists())
        self.assertEqual(self.snapshot(), before)

    def test_oem_end_to_end_install_control_flow(self):
        ident = self.package("install")
        self.write("tmp/oem-functions", self.oem_functions.encode())
        run = self.run_sandbox(". /tmp/oem-functions; export updatepath=/tmp/update; doUpdate img")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((self.root / "tmp/update_status").read_text().strip(), "2")
        self.assertIn("result=PREPARED_FOR_BOOT", self.result())
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), ident)

    def test_real_oem_copy_does_not_double_count_consumed_payload(self):
        self.service_payload = b"x" * 900000
        ident = self.package("install", service=True)
        for name in ("quickly_update.sh", "check_update.sh", "smart_copy.sh"):
            # Keep the actual OEM body; Bash supplies its shell extensions on host.
            self.write(
                "script/" + name,
                b"#!/bin/bash\n" + (OEM_ROOT / "script" / name).read_bytes(),
                0o755,
            )
        self.write("tmp/oem-functions", self.oem_functions.encode())
        self.write(
            "fake-df",
            b"""#!/bin/sh
free=1408
[ ! -f /etc/yamaha-sdl/usb-v1/active ] || free=448
[ "$1" != -B ] || free=$((free*1024))
echo 'Filesystem blocks Used Available Capacity Mounted'
echo "/dev/root 13107200 0 $free 0% /"
""",
            0o755,
        )
        run = self.run_sandbox(
            "touch /dev/console; . /tmp/oem-functions; export updatepath=/tmp/update; doUpdate img; cat /dev/console"
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("result=PREPARED_FOR_BOOT", self.result())
        self.assertEqual((self.root / "tmp/update_status").read_text().strip(), "2")
        self.assertEqual(
            (
                self.root / "etc/yamaha-sdl/usb-v1/releases" / ident / "service-runtime.tar.lzma"
            ).read_bytes(),
            self.service_payload,
        )
        self.assertFalse((self.root / "tmp/dextend/release").exists())

    def test_oem_copy_failure_is_still_reported_after_commit(self):
        self.package("install")
        self.write("script/quickly_update.sh", b"#!/bin/sh\nexit 7\n", 0o755)
        self.write("tmp/oem-functions", self.oem_functions.encode())
        self.run_sandbox(
            "touch /dev/console; . /tmp/oem-functions; export updatepath=/tmp/update; doUpdate img"
        )
        self.assertIn("result=UPDATER_ERROR_AFTER_COMMIT", self.result())
        self.assertEqual((self.root / "tmp/update_status").read_text().strip(), "3")

    def test_reject_wrong_product(self):
        self.write("etc/box_product_type", b"U2W\n")
        self.assert_rejected_unchanged("UNSUPPORTED_PRODUCT")

    def test_metadata_preserved_through_oem_install_and_restore(self):
        self.write("etc/module_version/foo", b"original\n")
        before = self.snapshot()
        for mode in ("install", "restore-oem"):
            self.package(mode)
            self.write("tmp/oem-functions", self.oem_functions.encode())
            run = self.run_sandbox(
                ". /tmp/oem-functions; export updatepath=/tmp/update; doUpdate img"
            )
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertIn("detail=EXPECTED_OEM_ERROR_METADATA_PRESERVED_POWER_CYCLE", self.result())
            self.assertIn(
                "result="
                + ("PREPARED_FOR_BOOT" if mode == "install" else "OEM_RESTORED_RESTART_REQUIRED"),
                self.result(),
            )
            self.assertEqual((self.root / "etc/module_version/foo").read_bytes(), b"original\n")
            self.assertFalse((self.root / "tmp/oem-copy-ran").exists())
        self.assertEqual(self.snapshot(), before)

    def test_metadata_symlink_rejected(self):
        (self.root / "etc/module_version").symlink_to("riddle.conf")
        self.assert_rejected_unchanged("OEM_MODULE_METADATA_UNSAFE")

    def test_new_profile_install_update_restore_preserves_metadata(self):
        self.write("etc/software_version", b"2025.10.15.1127\n")
        self.write("etc/module_version/firmware", b"factory metadata\n")
        self.additional_oem_profiles = (
            "'2025.10.15.1127@"
            + ";".join(
                f"{sha((self.root / n).read_bytes())}  {n}"
                for n in ("script/update_box.sh", "script/start_main_service.sh")
            )
            + "'"
        )
        before = self.snapshot()
        self.apply("install", installed_restore=True)
        self.apply("install", version="test-2", installed_restore=True)
        self.apply("restore-oem", version="test-2")
        self.assertEqual(self.snapshot(), before)

    def test_generated_hook_runs_without_oem_profile(self):
        from unittest.mock import patch
        import build_usb

        boot = b"#!/bin/sh\ntouch /tmp/hook-started\n"
        original_read = build_usb.read

        def fixture_read(path):
            return boot if path == ROOT / "src/usb/boot.sh" else original_read(path)

        with patch.object(build_usb, "read", fixture_read):
            generated = installer_inputs()
        self.write("etc/yamaha-sdl/enabled", b"")
        self.write("etc/yamaha-sdl/usb-v1/boot.sh", boot)
        self.write("tmp/test-hook.sh", generated["hook.sh"])
        self.write("etc/software_version", b"2024.01.01.1234")
        run = self.run_sandbox("sh /tmp/test-hook.sh && sleep 0.1 && test -e /tmp/hook-started")
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_reject_low_flash(self):
        self.flash_space(64)
        self.assert_rejected_unchanged("INSUFFICIENT_FLASH")

    def test_reject_malformed_flash_report(self):
        for available in ("", "-1", "4096:0"):
            with self.subTest(available=available):
                self.flash_space(available)
                self.assert_rejected_unchanged("INVALID_MEMORY_REPORT")

    def test_install_reports_measured_memory(self):
        self.write("proc/meminfo", b"MemFree: 8192 kB\nBuffers: 4096 kB\nCached: 4096 kB\n")
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("ram_reclaimable_estimate_kib=16384", self.result())

    def test_reject_readonly_usb(self):
        self.write("proc/mounts", b"/dev/root / jffs2 rw 0 0\n/dev/sda1 /mnt/UPAN vfat ro 0 0\n")
        self.assert_rejected_unchanged("USB_NOT_WRITABLE_VFAT")

    def test_reject_foreign_hook(self):
        self.write("script/custom_init.sh", b"foreign\n")
        self.assert_rejected_unchanged("UNKNOWN_BOOT_HOOK")

    def test_report_symlink_is_not_followed(self):
        target = self.root / "etc/untouched"
        target.write_text("private")
        (self.root / "mnt/UPAN/DEXTEND-RESULT.txt").symlink_to("/etc/untouched")
        before = self.snapshot()
        _, run = self.apply("install")
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_bundle_damage_stops_before_transaction(self):
        self.package("install")
        before = self.snapshot()
        self.write("tmp/update/tmp/dextend/release/native-runtime.tar.lzma", b"damaged")
        run = self.run_sandbox("sh /tmp/update/tmp/once.sh")
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("detail=DAMAGED_BUNDLE", self.result())
        self.assertIn("mismatch=release/native-runtime.tar.lzma expected=", self.result())
        self.assertFalse((self.root / "etc/yamaha-sdl").exists())

    def test_repeat_same_image_does_not_rewrite_flash(self):
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        before = self.snapshot()
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 1)
        self.assertIn("ALREADY_INSTALLED", self.result())
        self.assertEqual(before, self.snapshot())

    def test_update_requires_confirmed_boot(self):
        self.apply("install")
        before = self.snapshot()
        _, run = self.apply("install", "test-2")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("CURRENT_NOT_BOOT_CONFIRMED", self.result())
        self.assertEqual(before, self.snapshot())

    def boot_once(self):
        shutil.rmtree(self.root / "tmp/dextend-usb-started", ignore_errors=True)
        return self.run_sandbox("sh /etc/yamaha-sdl/usb-v1/boot.sh")

    def test_install_boot_update_and_remove(self):
        first, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        s = self.root / "etc/yamaha-sdl/usb-v1"
        self.assertEqual((s / "confirmed").read_text().strip(), first)
        second, run = self.apply("install", "test-2")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((s / "previous").read_text().strip(), "none")
        self.assertFalse((s / "releases" / first).exists())
        self.assertEqual(self.boot_once().returncode, 0)
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse((self.root / "script/custom_init.sh").exists())
        self.assertFalse((self.root / "etc/yamaha-sdl").exists())
        self.assertEqual((self.root / "etc/init.d/rcS").read_bytes(), self.stock)
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_update_rechecks_flash_after_own_restore(self):
        before = self.snapshot()
        _, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        self.flash_space(128)
        _, run = self.apply("install", "test-2")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("detail=OEM_RESTORED_INSUFFICIENT_FLASH", self.result())
        self.assertTrue((self.root / "tmp/installed-restore-ran").is_file())
        self.assertEqual(self.snapshot(), before)

    def test_update_does_not_remove_old_release_below_restore_reserve(self):
        _, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        before = self.snapshot()
        self.flash_space(63)
        _, run = self.apply("install", "test-2")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("detail=INSUFFICIENT_FLASH_FOR_RESTORE", self.result())
        self.assertEqual(self.snapshot(), before)

    def test_fresh_update_removes_plugin_preferences_and_preserves_oem_settings(self):
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        state = self.root / "etc/yamaha-sdl"
        policy = b'{"schema":1,"preferred":"android-auto","order":[]}\n'
        video = b"[640,360,82,78,60,60]"
        (state / "aa-video.conf").write_bytes(video)
        (state / "phone-policy.json").write_bytes(policy)
        (state / "phone-policy.lock").touch()
        self.write("etc/riddle.conf", b'{"fixture": "unchanged OEM settings"}')
        _, run = self.apply("install", "test-2")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse((state / "phone-policy.json").exists())
        self.assertFalse((state / "phone-policy.lock").exists())
        self.assertFalse((state / "aa-video.conf").exists())
        self.assertEqual(
            json.loads((self.root / "etc/riddle.conf").read_text())["fixture"],
            "unchanged OEM settings",
        )
        backups = list((self.root / "mnt/UPAN").glob("dextend-backup.*/before.tar"))
        with tarfile.open(
            next(
                p
                for p in backups
                if "etc/yamaha-sdl/phone-policy.json" in (p.parent / "paths.txt").read_text()
            )
        ) as archive:
            self.assertEqual(archive.extractfile("etc/yamaha-sdl/phone-policy.json").read(), policy)
            self.assertEqual(archive.extractfile("etc/yamaha-sdl/aa-video.conf").read(), video)
        self.assertEqual(self.boot_once().returncode, 0)
        (state / "aa-video.conf").write_bytes(video)
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(state.exists())

    def test_failed_boot_after_fresh_update_falls_back_to_oem(self):
        first, _ = self.apply("install")
        self.boot_once()
        self.apply("install", "test-bad", b"#!/bin/sh\nexit 1\n")
        self.assertNotEqual(self.boot_once().returncode, 0)
        s = self.root / "etc/yamaha-sdl/usb-v1"
        self.assertEqual((s / "active").read_text().strip(), "none")
        self.assertFalse((s / "releases" / first).exists())
        self.assertEqual(self.boot_once().returncode, 0)

    def test_boot_report_keeps_failure_code_and_selected_fallback_reason(self):
        self.apply("install", native=b"#!/bin/sh\nexit 23\n")
        self.write(
            "tmp/dextend-service/diagnostics.sh", (ROOT / "src/runtime/diagnostics.sh").read_bytes()
        )
        self.assertNotEqual(self.boot_once().returncode, 0)
        events = (self.root / "tmp/dextend-diagnostics/boot-events").read_text()
        self.assertIn("native_exit rc=23", events)
        self.assertIn("rollback_selection reason=native_start_failed", events)

    def test_first_boot_failure_falls_back_to_oem(self):
        self.apply("install", native=b"#!/bin/sh\nexit 1\n")
        self.assertNotEqual(self.boot_once().returncode, 0)
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), "none")
        self.assertEqual(self.boot_once().returncode, 0)

    def test_interrupted_attempt_rolls_back_without_running_candidate(self):
        first, _ = self.apply("install")
        self.boot_once()
        second, _ = self.apply(
            "install", "test-2", b"#!/bin/sh\ntouch /tmp/should-not-run\nexit 0\n"
        )
        self.write("etc/yamaha-sdl/usb-v1/attempted", (second + "\n").encode())
        self.assertEqual(self.boot_once().returncode, 0)
        self.assertFalse((self.root / "tmp/should-not-run").exists())
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), "none")
        self.assertFalse((self.root / "etc/yamaha-sdl/usb-v1/releases" / first).exists())

    def test_restore_known_legacy_preserves_rcs_and_identity(self):
        for n, data in self.legacy.items():
            self.write(n, data)
        self.write("script/custom_init.sh", self.legacy_hook)
        self.write("etc/init.d/rcS", self.ssh)
        self.write("etc/private-device-data", b"fixture identity - must remain")
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((self.root / "etc/init.d/rcS").read_bytes(), self.ssh)
        self.assertEqual(
            (self.root / "etc/private-device-data").read_bytes(), b"fixture identity - must remain"
        )
        self.assertFalse((self.root / "etc/wifi-usb").exists())
        backups = list((self.root / "mnt/UPAN").glob("dextend-backup.*/before.tar"))
        self.assertEqual(len(backups), 1)
        with tarfile.open(backups[0]) as t:
            self.assertNotIn("etc/init.d/rcS", t.getnames())

    def prepare_web_restore(self):
        state = self.root / "etc/yamaha-sdl/usb-v1"
        active = (state / "active").read_text().strip()
        runtime = (state / "releases" / active / "native-runtime.tar.lzma").read_bytes()
        work = self.root / "tmp/boa/dextend-restore"
        work.mkdir(parents=True)
        # The panel copies these files from the running release after extraction.
        with tarfile.open(
            fileobj=io.BytesIO(lzma.decompress(runtime, format=lzma.FORMAT_ALONE))
        ) as archive:
            for name in (
                "profile.sh",
                "OEM.sha256",
                "LEGACY.sha256",
                "format",
                "transaction.sh",
                "update-protocol",
                "radio-names.sh",
                "radio-config.awk",
            ):
                self.write(
                    "tmp/boa/dextend-restore/" + name, archive.extractfile("restore/" + name).read()
                )
        self.write("tmp/boa/dextend-restore/token", b"a" * 64)
        shutil.copy(ROOT / "src/runtime/restore-cgi.sh", self.root / "tmp/restore-cgi.sh")
        return work

    def test_web_restore_requires_local_host_origin_token_and_typed_confirmation(self):
        self.apply("install", installed_restore=True)
        self.prepare_web_restore()
        before = self.snapshot()
        run = self.run_sandbox("""
            unset REMOTE_USER AUTH_TYPE
            REQUEST_METHOD=GET HTTP_HOST=untrusted.example sh /tmp/restore-cgi.sh
            export REQUEST_METHOD=POST
            export HTTP_HOST=localhost HTTP_ORIGIN=http://wrong.test
            sh /tmp/restore-cgi.sh
            export HTTP_ORIGIN=http://localhost HTTP_X_DEXTEND_TOKEN=wrong
            sh /tmp/restore-cgi.sh
            export HTTP_X_DEXTEND_TOKEN=$(cat /tmp/boa/dextend-restore/token)
            export CONTENT_TYPE='text/plain;charset=UTF-8' CONTENT_LENGTH=10
            printf 'WRONGTEXT!' | sh /tmp/restore-cgi.sh
        """)
        self.assertEqual(run.stdout.count("403 Forbidden"), 3, run.stdout)
        self.assertIn("400 Bad Request", run.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_web_restore_keeps_oem_settings_and_reports_after_request(self):
        _, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        self.write("etc/riddle.conf", b'{"fixture": "fixture OEM settings"}')
        work = self.prepare_web_restore()
        self.write("proc/mounts", b"/dev/root / jffs2 rw,relatime 0 0\n")
        shutil.rmtree(self.root / "mnt/UPAN")
        run = self.run_sandbox(r"""
            unset REMOTE_USER AUTH_TYPE
            export HTTP_HOST=192.168.50.2 HTTP_ORIGIN=http://192.168.50.2
            info=$(REQUEST_METHOD=GET sh /tmp/restore-cgi.sh)
            token=$(printf '%s\n' "$info" | sed -n 's/.*"token":"\([0-9a-f]*\)".*/\1/p')
            [ "${#token}" = 64 ] || exit 2
            export REQUEST_METHOD=POST HTTP_X_DEXTEND_TOKEN=$token
            export CONTENT_TYPE='text/plain;charset=UTF-8' CONTENT_LENGTH=10
            printf 'PRZYWRÓĆ' | sh /tmp/restore-cgi.sh
            printf 'PRZYWRÓĆ' | sh /tmp/restore-cgi.sh
            i=0
            while [ "$i" -lt 50 ]; do
                REQUEST_METHOD=GET sh /tmp/restore-cgi.sh | grep '"state":"restored"' && exit 0
                sleep .1
                i=$((i+1))
            done
            cat /tmp/boa/dextend-restore/result >&2
            exit 1
        """)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("202 Accepted", run.stdout)
        self.assertIn("409 Conflict", run.stdout)
        self.assertTrue((self.root / "tmp/installed-restore-ran").is_file())
        self.assertFalse((self.root / "script/custom_init.sh").exists())
        self.assertFalse((self.root / "etc/yamaha-sdl").exists())
        self.assertEqual(
            json.loads((self.root / "etc/riddle.conf").read_text()),
            {"fixture": "fixture OEM settings"},
        )
        self.assertEqual(len(list(work.glob("dextend-backup.*/before.tar"))), 1)

    def test_restore_preserves_unrelated_file(self):
        self.write("etc/yamaha-sdl/unrecognised", b"user data")
        before = self.snapshot()
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(before, self.snapshot())

    def test_restore_refuses_unknown_managed_file(self):
        self.apply("install")
        self.write("etc/yamaha-sdl/usb-v1/foreign", b"user data")
        self.assert_rejected_unchanged("UNKNOWN_STATE_FILE", "restore-oem")

    def test_unknown_rcs_is_never_replaced(self):
        self.write("etc/init.d/rcS", b"foreign init")
        before = self.snapshot()
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_release_image_real_oem_finish(self):
        image = getattr(self, "release_image", None)
        if image is None:
            self.skipTest("requires final release IMG")
        members = decode(image.read_bytes())
        for name, (data, mode) in members.items():
            self.write("tmp/update/" + name, data, mode)
        names = (
            "update_box.sh",
            "quickly_update.sh",
            "check_update.sh",
            "smart_copy.sh",
            "start_main_service.sh",
        )
        for n in names:
            self.write(
                "script/" + n, b"#!/bin/bash\n" + (OEM_ROOT / "script" / n).read_bytes(), 0o755
            )
        folder = self.root / "tmp/update/tmp/dextend"
        profile = folder / "profile.sh"
        profile.write_text(
            "\n".join(
                "stock_rcs=" + sha(self.stock) if line.startswith("stock_rcs=") else line
                for line in profile.read_text().splitlines()
            )
            + "\n"
        )
        (folder / "OEM.sha256").write_text(
            "".join(f"{sha((self.root / 'script' / n).read_bytes())}  script/{n}\n" for n in names)
        )
        old = sha((folder / "BUNDLE.sha256").read_bytes())
        checks = "".join(
            f"{sha(f.read_bytes())}  {f.relative_to(folder)}\n"
            for f in sorted(folder.rglob("*"))
            if f.is_file() and f.name != "BUNDLE.sha256"
        ).encode()
        (folder / "BUNDLE.sha256").write_bytes(checks)
        once = self.root / "tmp/update/tmp/once.sh"
        once.write_bytes(once.read_bytes().replace(old.encode(), sha(checks).encode()))
        self.write(
            "fake-df",
            b"""#!/bin/sh
free=1408
[ ! -f /etc/yamaha-sdl/usb-v1/active ] || free=320
[ "$1" != -B ] || free=$((free*1024))
echo 'Filesystem blocks Used Available Capacity Mounted'
echo "/dev/root 13107200 0 $free 0% /"
""",
            0o755,
        )
        functions = (
            (OEM_ROOT / "script/update_box.sh")
            .read_text()
            .split("\nif [ -e /etc/box_product_type ]; then\n")[0]
        )
        self.write("tmp/oem-functions", functions.encode())
        run = self.run_sandbox(
            "touch /dev/console; . /tmp/oem-functions; export updatepath=/tmp/update; doUpdate img"
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("result=PREPARED_FOR_BOOT", self.result())
        state = self.root / "etc/yamaha-sdl/usb-v1"
        for name in ("install-result", "install-detail", "install-version"):
            self.assertFalse((state / name).exists(), name)
        self.assertEqual((self.root / "tmp/update_status").read_text().strip(), "2")
        self.assertFalse((self.root / "tmp/dextend/release").exists())

    def check_release_image_restore(self, transport, fallback=False, interrupted=False):
        image = getattr(self, "release_image", None)
        if image is None:
            self.skipTest("run with --check-release-img to validate a built image")
        members = decode(image.read_bytes())
        prefix = "tmp/dextend/"
        runtime_name = "release/native-runtime.tar.lzma"
        version = members[prefix + "release/version.txt"][0].decode().splitlines()[0]
        # Validate the exact artifact before adapting its OEM fingerprints.
        verify_runtime(members[prefix + runtime_name][0], version)
        for name, (data, mode) in members.items():
            if name.startswith(prefix):
                self.write("tmp/update/" + name, data, mode)
        install = self.root / "tmp/update/tmp/dextend"
        profile = install / "profile.sh"
        lines = profile.read_text().splitlines()
        profile.write_text(
            "\n".join(
                "stock_rcs=" + sha(self.stock) if line.startswith("stock_rcs=") else line
                for line in lines
            )
            + "\n"
        )
        oem = install / "OEM.sha256"
        oem.write_text(
            "".join(
                f"{sha((self.root / name).read_bytes())}  {name}\n"
                for name in ("script/update_box.sh", "script/start_main_service.sh")
            )
        )
        self.write("etc/riddle.conf", b'{"fixture": "fixture OEM settings"}')
        self.write("etc/bluetooth/pairings", b"fixture OEM pairings")
        (self.root / "etc/empty-oem-directory").mkdir()
        (self.root / "etc/oem-settings-link").symlink_to("riddle.conf")
        persistent = ("var", "root", "opt", "www")
        for name in persistent:
            self.write(name + "/oem-file", b"fixture for " + name.encode())
        trees = ("etc", "script", *persistent)
        before = self.snapshot(trees)

        command = "sh /tmp/update/tmp/dextend/transaction.sh"
        # Check the real artifact at exactly 1 KiB below and then at the flash threshold.
        minimum = (
            len(members[prefix + runtime_name][0])
            + len(members.get(prefix + "release/service-runtime.tar.lzma", (b"", 0))[0])
            + 1023
        ) // 1024 + 320
        radio_bytes = sum(
            (self.root / "etc" / n).stat().st_size
            for n in ("riddle.conf", "hostapd.conf", "wifi_name", "bluetooth_name")
        )
        minimum += (3 * radio_bytes + 1023) // 1024 + 32
        self.flash_space(minimum - 1)
        rejected = self.run_sandbox(command, persistent=persistent)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("detail=INSUFFICIENT_FLASH", self.result())
        self.assertEqual(self.snapshot(trees), before)
        self.flash_space(minimum)
        if interrupted:
            self.write(
                "fail-radio-mv",
                b'#!/bin/sh\ncase "$*" in */etc/riddle.conf) exit 1;; esac\nexec /usr/bin/busybox mv "$@"\n',
                0o755,
            )
            failed = self.run_sandbox(
                command, [(self.root / "fail-radio-mv", "/usr/bin/mv")], persistent=persistent
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("RADIO_RIDDLE_RENAME_FAILED", self.result())
            self.assertFalse((self.root / "etc/yamaha-sdl/usb-v1/active").exists())
            # Space reported by the user's incomplete 0.27 installation; full
            # OEM space becomes available only after removing the checked tree.
            self.write(
                "fake-df",
                b'#!/bin/sh\necho "Filesystem 1024-blocks Used Available Capacity Mounted on"\nif [ -e /etc/yamaha-sdl/usb-v1/transaction ]; then echo "fixture 12800 12340 460 96% /"; else echo "fixture 12800 11384 1416 89% /"; fi\n',
                0o755,
            )
        run = self.run_sandbox(command, persistent=persistent)
        self.assertEqual(run.returncode, 0, self.result() + run.stderr)
        self.assertNotEqual(self.snapshot(trees), before, "IMG never exercised a persistent write")
        state = self.root / "etc/yamaha-sdl/usb-v1"
        active = (state / "active").read_bytes()
        # Mark the installed build as booted; this test does not start ARM services.
        self.write("etc/yamaha-sdl/usb-v1/confirmed", active)
        for name in ("pending", "attempted"):
            (state / name).unlink(missing_ok=True)
        if fallback:
            (state / "active").write_text("none\n")
            (state / "confirmed").unlink()
            (state / "status").write_text("ROLLED_BACK_RESTART_REQUIRED\n")
        self.write(
            "etc/yamaha-sdl/phone-policy.json", b'{"schema":1,"preferred":"none","order":[]}\n'
        )
        self.write("etc/yamaha-sdl/phone-policy.lock", b"")
        self.write("etc/yamaha-sdl/aa-video.conf", b"[640,360,82,78,60,60]")
        if prefix + "release/service-runtime.tar.lzma" in members:
            from service_package import verify_service

            verify_service(members[prefix + "release/service-runtime.tar.lzma"][0])
            self.write("etc/yamaha-sdl/service/hostkey.new.pub", b"fixture public sidecar")
            self.write("etc/yamaha-sdl/service/hostkey", b"fixture private host key")
            self.write("etc/yamaha-sdl/service/network.conf", b"fixture network credentials")
            self.write("etc/yamaha-sdl/service/authorized_keys", b"fixture public key")

        work = (
            "/tmp/boa/dextend-restore" if transport == "web" else "/tmp/dextend-update-restore.test"
        )
        archive_path = (
            state
            / "releases"
            / active.decode().strip()
            / ("service-runtime.tar.lzma" if fallback else "native-runtime.tar.lzma")
        )
        with tarfile.open(
            fileobj=io.BytesIO(lzma.decompress(archive_path.read_bytes()))
        ) as archive:
            for entry in archive:
                if entry.name.startswith("restore/"):
                    name = entry.name.removeprefix("restore/")
                    self.write(work.lstrip("/") + "/" + name, archive.extractfile(entry).read())
        # Keep the shipped script byte-for-byte; only the modeled OEM differs.
        for name in ("profile.sh", "OEM.sha256"):
            shutil.copyfile(install / name, self.root / work.lstrip("/") / name)
        args = "web"
        if transport in ("replace", "replace-ota"):
            (self.root / "tmp/dextend-usb-lock").mkdir()
            args = f"{transport} {work}"
            if transport == "replace-ota":
                (self.root / "tmp/dextend-updater").mkdir()
                self.write("proc/mounts", b"/dev/root / jffs2 rw,relatime 0 0\n")
        run = self.run_sandbox(f"sh {work}/transaction.sh {args}", persistent=persistent)
        result = (self.root / work.lstrip("/") / "result").read_text()
        self.assertEqual(run.returncode, 0, result + run.stderr)
        expected_status = (
            "OEM_RESTORED_RESTART_REQUIRED" if transport == "web" else "FILES_COMMITTED"
        )
        self.assertIn(f"result={expected_status}\n", result)
        after = self.snapshot(trees)
        self.assertEqual(
            [
                path
                for path in sorted(before.keys() | after.keys())
                if before.get(path) != after.get(path)
            ],
            [],
            "Persistent paths that differ from OEM after restore",
        )

    def test_release_image_web_restores_oem_inventory(self):
        self.check_release_image_restore("web")

    def test_release_image_web_fallback_restores_oem_inventory(self):
        self.check_release_image_restore("web", fallback=True)

    def test_release_image_usb_fallback_restores_oem_inventory(self):
        self.check_release_image_restore("replace", fallback=True)

    def test_release_image_network_fallback_restores_oem_inventory(self):
        self.check_release_image_restore("replace-ota", fallback=True)

    def test_release_image_usb_restores_oem_inventory(self):
        self.check_release_image_restore("replace")

    def test_release_image_network_restores_oem_inventory(self):
        self.check_release_image_restore("replace-ota")

    def test_release_image_interrupted_radio_recovers_and_restores_oem(self):
        self.check_release_image_restore("replace", interrupted=True)

    def test_reject_downgrade_after_confirmation(self):
        self.apply("install", "test-2")
        self.boot_once()
        before = self.snapshot()
        _, run = self.apply("install", "test-1")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("DOWNGRADE_OR_REUSED_VERSION", self.result())
        self.assertEqual(before, self.snapshot())

    def test_failed_copy_leaves_oem_boot_and_can_resume(self):
        first, _ = self.apply("install")
        self.boot_once()
        second = self.package("install", "test-2")
        self.write(
            "fail-copy",
            b'#!/bin/bash\ncase "$*" in *release/native-boot.sh*) exit 1;; esac\nexec /usr/bin/busybox cp "$@"\n',
            0o755,
        )
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-copy", "/usr/bin/cp")]
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("result=ERROR_AFTER_WRITE", self.result())
        self.assertFalse((self.root / "script/custom_init.sh").exists())
        self.assertFalse((self.root / "etc/yamaha-sdl/usb-v1/releases" / first).exists())
        _, run = self.apply("install", "test-2")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), second)

    def test_update_uses_installed_versions_own_remover(self):
        first, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        second, run = self.apply("install", "test-2")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue((self.root / "tmp/installed-restore-ran").is_file())
        releases = self.root / "etc/yamaha-sdl/usb-v1/releases"
        self.assertEqual({d.name for d in releases.iterdir()}, {second})
        self.assertNotEqual(first, second)

    def test_install_removes_known_legacy_files_and_preserves_rcs(self):
        for name, data in self.legacy.items():
            self.write(name, data)
        self.write("script/custom_init.sh", self.legacy_hook)
        self.write("etc/init.d/rcS", self.ssh)
        self.write("etc/init.d/rcS.dextend-new", self.stock)
        ident, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((self.root / "etc/init.d/rcS").read_bytes(), self.ssh)
        self.assertEqual((self.root / "etc/init.d/rcS.dextend-new").read_bytes(), self.stock)
        self.assertFalse((self.root / "etc/wifi-usb").exists())
        self.assertTrue((self.root / "etc/yamaha-sdl/usb-v1/releases" / ident).exists())

    def test_update_can_run_remover_from_older_boot_contract(self):
        self.test_update_can_run_remover_from_previous_boot_contract(older=True)

    def test_update_can_run_remover_from_previous_boot_contract(self, older=False):
        first, run = self.apply("install", installed_restore=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.boot_once().returncode, 0)
        if older:
            self.older_boot, self.older_hook = self.boot, self.hook
        else:
            self.previous_boot, self.previous_hook = self.boot, self.hook
        self.boot += b"\n# new boot digest\n"
        self.hook += b"\n# new hook digest\n"
        second, run = self.apply("install", "test-2")
        self.assertEqual(run.returncode, 0, self.result())
        self.assertTrue((self.root / "tmp/installed-restore-ran").exists())
        releases = self.root / "etc/yamaha-sdl/usb-v1/releases"
        self.assertFalse((releases / first).exists())
        self.assertTrue((releases / second).exists())
        self.assertEqual((self.root / "script/custom_init.sh").read_bytes(), self.hook)

    def test_unknown_restore_worker_is_not_patched(self):
        self.test_upgrade_0_22_failed_boot_with_public_hostkey_sidecar(unknown=True)

    def test_upgrade_0_22_failed_boot_with_public_hostkey_sidecar(self, unknown=False):
        # Exact published 0.22 restore worker; only OEM profile data is modeled.
        archive = os.environ.get("DEXTEND_LEGACY_IMG_DIR")
        if not archive or not (Path(archive) / "0.22-alpha.img").is_file():
            self.skipTest("optional legacy upgrade fixture unavailable")
        old_img = (Path(archive) / "0.22-alpha.img").read_bytes()
        old = decode(old_img)
        with tarfile.open(
            fileobj=io.BytesIO(
                lzma.decompress(old["tmp/dextend/release/native-runtime.tar.lzma"][0])
            )
        ) as archive:
            self.restore_worker = archive.extractfile("restore/transaction.sh").read()
        self.assertEqual(
            sha(self.restore_worker),
            json.loads((ROOT / "src/usb/profile.json").read_text())["restore_0_22_sidecar_sha256"],
        )
        if unknown:
            self.restore_worker += b"\n# unknown worker revision\n"
        self.write("etc/riddle.conf", b'{"fixture": "preserved OEM settings"}')
        before = (self.root / "etc/riddle.conf").read_bytes()
        first = self.package("install", installed_restore=True, service=True)
        run = self.run_sandbox("sh /tmp/update/tmp/dextend/transaction.sh")
        self.assertEqual(run.returncode, 0, self.result() + run.stderr)
        state = self.root / "etc/yamaha-sdl/usb-v1"
        # 0.22 did not own radio names; model its original state accurately.
        radio_restore = self.run_sandbox("sh /tmp/update/tmp/dextend/radio-names.sh restore")
        self.assertEqual(radio_restore.returncode, 0, radio_restore.stderr)
        shutil.rmtree(state / "radio")
        (state / "active").write_text("none\n")
        (state / "pending").unlink()
        (state / "status").write_text("ROLLED_BACK_RESTART_REQUIRED\n")
        self.write("etc/yamaha-sdl/service/hostkey.new.pub", b"fixture public sidecar")
        del self.restore_worker
        image = getattr(self, "release_image", None)
        if image:
            members = decode(image.read_bytes())
            for name, (data, mode) in members.items():
                self.write("tmp/update/" + name, data, mode)
            install = self.root / "tmp/update/tmp/dextend"
            profile = install / "profile.sh"
            profile.write_text(
                profile.read_text().replace(
                    "stock_rcs="
                    + json.loads((ROOT / "src/usb/profile.json").read_text())["stock_rcs_sha256"],
                    "stock_rcs=" + sha(self.stock),
                )
            )
            with profile.open("a") as f:
                f.write(
                    "previous_hook_sha="
                    + sha(self.hook)
                    + "\nprevious_boot_sha="
                    + sha(self.boot)
                    + "\n"
                )
            (install / "OEM.sha256").write_text(
                "".join(
                    f"{sha((self.root / n).read_bytes())}  {n}\n"
                    for n in ("script/update_box.sh", "script/start_main_service.sh")
                )
            )
            second = sha((install / "release/SHA256SUMS").read_bytes())
        else:
            second = self.package("install", "test-2", installed_restore=True, service=True)
        snapshot = self.snapshot()
        run = self.run_sandbox("sh /tmp/update/tmp/dextend/transaction.sh")
        if unknown:
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("INSTALLED_RESTORE_FAILED", self.result())
            self.assertEqual(self.snapshot(), snapshot)
            return
        self.assertEqual(run.returncode, 0, self.result() + run.stderr)
        self.assertEqual((state / "active").read_text().strip(), second)
        self.assertFalse((state / "releases" / first).exists())
        self.assertFalse((self.root / "etc/yamaha-sdl/service/hostkey.new.pub").exists())
        self.assertEqual(
            json.loads((self.root / "etc/riddle.conf").read_text())["fixture"],
            json.loads(before)["fixture"],
        )
        backups = list((self.root / "mnt/UPAN").glob("dextend-backup.*/before.tar"))
        names = []
        for path in backups:
            with tarfile.open(path) as archive:
                names.extend(archive.getnames())
        self.assertIn("etc/yamaha-sdl/service/hostkey.new.pub", names)

    def test_failed_removal_never_writes_new_release(self):
        first, _ = self.apply("install", installed_restore=True)
        self.assertEqual(self.boot_once().returncode, 0)
        second = self.package("install", "test-2")
        self.write(
            "fail-remove",
            b'#!/bin/bash\ncase "$*" in */usb-v1/releases*) exit 1;; esac\nexec /usr/bin/busybox rm "$@"\n',
            0o755,
        )
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-remove", "/usr/bin/rm")]
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("INSTALLED_RESTORE_FAILED", self.result())
        self.assertFalse((self.root / "script/custom_init.sh").exists())
        releases = self.root / "etc/yamaha-sdl/usb-v1/releases"
        self.assertTrue((releases / first).exists())
        self.assertFalse((releases / second).exists())
        _, run = self.apply("install", "test-2")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual({d.name for d in releases.iterdir()}, {second})

    def test_interrupted_first_hook_commit_can_resume(self):
        ident = self.package("install")
        self.write(
            "fail-move",
            b'#!/bin/bash\ncase "$*" in *custom_init.sh*) exit 1;; esac\nexec /usr/bin/busybox mv "$@"\n',
            0o755,
        )
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-move", "/usr/bin/mv")]
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.root / "script/custom_init.sh").exists())
        _, run = self.apply("install")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue((self.root / "script/custom_init.sh").exists())
        self.assertEqual((self.root / "etc/yamaha-sdl/usb-v1/active").read_text().strip(), ident)

    def test_interrupted_remove_can_resume(self):
        self.apply("install")
        self.package("restore-oem")
        self.write(
            "fail-remove",
            b'#!/bin/bash\ncase "$*" in */usb-v1/releases*) exit 1;; esac\nexec /usr/bin/busybox rm "$@"\n',
            0o755,
        )
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(self.root / "fail-remove", "/usr/bin/rm")]
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.root / "script/custom_init.sh").exists())
        self.assertTrue((self.root / "etc/yamaha-sdl/usb-v1/format").exists())
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse((self.root / "etc/yamaha-sdl").exists())

    def test_wifi_usb_owner_marker_survives_install_and_restore(self):
        self.write("etc/wifi-usb/enabled", b"")
        self.write("etc/wifi-usb/boot.sh", b"owner service")
        before = self.snapshot()
        for mode in ("install", "restore-oem"):
            _, run = self.apply(mode)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue((self.root / "etc/wifi-usb/enabled").exists())
        self.assertEqual(self.snapshot(), before)

    def test_restore_preserves_unrelated_directory(self):
        (self.root / "etc/wifi-usb/foreign").mkdir(parents=True)
        before = self.snapshot()
        _, run = self.apply("restore-oem")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(before, self.snapshot())

    @unittest.skipUnless(shutil.which("qemu-arm"), "needs qemu-arm")
    def test_backup_with_actual_target_busybox_tar(self):
        oem = OEM_ROOT
        self.write(
            "arm-tar",
            b'#!/bin/bash\nexec /usr/bin/qemu-arm -L /oem /oem/bin/busybox tar "$@"\n',
            0o755,
        )
        self.package("install")
        run = self.run_sandbox(
            "sh /tmp/update/tmp/once.sh", [(oem, "/oem"), (self.root / "arm-tar", "/usr/bin/tar")]
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        backups = list((self.root / "mnt/UPAN").glob("dextend-backup.*/before.tar"))
        self.assertEqual(len(backups), 1)
        with tarfile.open(backups[0]) as t:
            self.assertEqual(
                t.extractfile("tmp/update/tmp/dextend/format").read(), b"dextend-usb-v1\n"
            )


@unittest.skipUnless(shutil.which("bwrap") and shutil.which("unshare"), "needs namespaces")
class RadioLifecycleTests(unittest.TestCase):
    def run_lifecycle(self, script):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "etc/alternatives").mkdir(parents=True)
            (root / "etc/riddle.conf").write_text('{"fixture":1}')
            (root / "tmp/yamaha-sdl").mkdir(parents=True)
            (root / "tmp/receiver-config").write_text('{"fixture":2}')
            (root / "tmp/yamaha-sdl/boot-live.sh").write_text(
                '#!/bin/sh\necho $$ > boot.pid\ntrap "exit 0" TERM\nwhile :; do sleep 1; done\n'
            )
            cmd = [
                "bwrap",
                "--unshare-user",
                "--uid",
                "0",
                "--gid",
                "0",
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
                "--bind",
                str(root / "etc"),
                "/etc",
                "--ro-bind",
                "/etc/alternatives",
                "/etc/alternatives",
                "--bind",
                str(root / "tmp"),
                "/tmp",
                "--dev",
                "/dev",
                "--unshare-pid",
                "--proc",
                "/proc",
                "--unshare-net",
                "--die-with-parent",
                "--cap-add",
                "CAP_SYS_ADMIN",
                "--ro-bind",
                str(ROOT / "src/usb"),
                "/work",
                "/bin/sh",
                "-c",
                script,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode == 77:
                self.skipTest("nested mount namespaces unavailable")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_stops_receiver_group_releases_private_mount_and_preserves_other_process(self):
        self.run_lifecycle("""
unshare -m true || exit 77
sleep 100 & unrelated=$!
setsid unshare -m sh -c 'mount --bind /tmp/receiver-config /etc/riddle.conf; cd /tmp/yamaha-sdl; exec sh ./boot-live.sh' & receiver=$!
i=0
while [ ! -f /tmp/yamaha-sdl/boot.pid ]; do i=$((i+1)); [ "$i" -lt 50 ] || exit 2; sleep 0.1; done
sh /work/radio-names.sh quiesce || exit 3
wait "$receiver" 2>/dev/null || true
kill -0 "$unrelated" || exit 4
test ! -d /proc/"$receiver" || exit 5
test "$(cat /etc/riddle.conf)" = '{"fixture":1}' || exit 6
kill "$unrelated"
""")

    def test_stops_verified_receiver_group_without_signalling_other_process(self):
        self.run_lifecycle("""
sleep 100 & unrelated=$!
setsid sh -c 'cd /tmp/yamaha-sdl; exec sh ./boot-live.sh' & receiver=$!
i=0
while [ ! -f /tmp/yamaha-sdl/boot.pid ]; do i=$((i+1)); [ "$i" -lt 50 ] || exit 2; sleep 0.1; done
sh /work/radio-names.sh quiesce || exit 3
wait "$receiver" 2>/dev/null || true
kill -0 "$unrelated" || exit 4
test ! -d /proc/"$receiver" || exit 5
kill "$unrelated"
""")

    def test_unrelated_pid_is_not_signalled(self):
        self.run_lifecycle("""
sleep 100 & unrelated=$!
echo "$unrelated" > /tmp/yamaha-sdl/boot.pid
if sh /work/radio-names.sh quiesce; then exit 2; fi
kill -0 "$unrelated" || exit 3
kill "$unrelated"
""")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check-release-img":
        suite = unittest.TestSuite()
        for transport in (
            "web",
            "usb",
            "network",
            "web_fallback",
            "usb_fallback",
            "network_fallback",
        ):
            case = TransactionTests(f"test_release_image_{transport}_restores_oem_inventory")
            case.release_image = Path(sys.argv[2])
            suite.addTest(case)
        case = TransactionTests("test_upgrade_0_22_failed_boot_with_public_hostkey_sidecar")
        case.release_image = Path(sys.argv[2])
        suite.addTest(case)
        case = TransactionTests("test_release_image_real_oem_finish")
        case.release_image = Path(sys.argv[2])
        suite.addTest(case)
        case = TransactionTests("test_release_image_interrupted_radio_recovers_and_restores_oem")
        case.release_image = Path(sys.argv[2])
        suite.addTest(case)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
    unittest.main()
