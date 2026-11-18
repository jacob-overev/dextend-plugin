#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Host-only USB identity, CGI, key ownership and service lifecycle tests."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.sys = self.base / "sys"
        self.run = self.base / "run"
        self.store = self.base / "store"
        for p in (self.sys, self.run, self.store):
            p.mkdir()
        self.api = self.base / "api"
        subprocess.run(
            [
                "cc",
                "-Os",
                "-Wall",
                "-Wextra",
                "-Werror",
                '-DMANAGEMENT_IFACE="lo"',
                f'-DROOT="{self.run}"',
                f'-DSTORE="{self.store}"',
                f'-DSYS="{self.sys}"',
                str(ROOT / "src/native/debug-api.c"),
                "-o",
                str(self.api),
            ],
            check=True,
            capture_output=True,
        )

    def device(self, iface="wlx-test", product="1006", driver="ath9k_htc"):
        dev = self.sys / "devices/usb/1-2"
        dev.mkdir(parents=True, exist_ok=True)
        (dev / "idVendor").write_text("0cf3\n")
        (dev / "idProduct").write_text(product + "\n")
        bus = self.sys / "bus/usb/devices"
        bus.mkdir(parents=True, exist_ok=True)
        (bus / "1-2").symlink_to(dev)
        usbif = dev / "1-2:1.0"
        usbif.mkdir()
        drv = self.sys / "bus/usb/drivers" / driver
        drv.mkdir(parents=True)
        (usbif / "driver").symlink_to(drv)
        net = self.sys / "class/net" / iface
        net.mkdir(parents=True)
        (net / "device").symlink_to(usbif)
        return dev

    def call(self, *args, **env):
        return subprocess.run(
            [str(self.api), *args],
            input=env.pop("body", None),
            capture_output=True,
            text=True,
            env={**os.environ, **env},
            timeout=20,
        )

    @unittest.skipUnless(shutil.which("qemu-arm"), "requires ARM emulator")
    def test_session_token_encoding_with_oem_busybox(self):
        oem = Path(os.environ.get("DEXTEND_OEM_TEST_ROOT") or "/nonexistent/dextend-oem-fixture")
        if not (oem / "bin/busybox").is_file():
            self.skipTest("OEM fixture unavailable")
        for data in (bytes(32), bytes(range(32))):
            result = subprocess.run(
                [
                    "qemu-arm",
                    "-L",
                    str(oem),
                    str(oem / "bin/busybox"),
                    "hexdump",
                    "-v",
                    "-e",
                    '1/1 "%02x"',
                ],
                input=data,
                capture_output=True,
                check=True,
            )
            self.assertEqual(result.stdout.decode(), data.hex())
            self.assertEqual(len(result.stdout), 64)

    def test_diagnostics_without_card_and_with_origin_guard(self):
        (self.run / "diagnostics.sh").write_text(
            '#!/bin/sh\nprintf "DEXTEND DIAGNOSTICS\\nfixture\\n"\n'
        )
        r = self.call(
            REQUEST_METHOD="GET",
            QUERY_STRING="diagnostics=1",
            HTTP_HOST="127.0.0.1",
            SERVER_ADDR="127.0.0.1",
            HTTP_X_DEXTEND_REQUEST="1",
        )
        self.assertIn("text/plain", r.stdout)
        self.assertIn("DEXTEND DIAGNOSTICS", r.stdout)
        r = self.call(
            REQUEST_METHOD="GET",
            QUERY_STRING="diagnostics=1",
            HTTP_HOST="evil.example",
            HTTP_X_DEXTEND_REQUEST="1",
        )
        self.assertIn("403", r.stdout)
        self.assertNotIn("fixture", r.stdout)

    def test_no_card(self):
        self.assertEqual(self.call("--device").returncode, 1)
        r = self.call(
            REQUEST_METHOD="GET",
            HTTP_HOST="127.0.0.1",
            SERVER_ADDR="127.0.0.1",
            HTTP_X_DEXTEND_REQUEST="1",
        )
        self.assertFalse(json.loads(r.stdout.split("\n\n")[1])["present"])

    def test_external_identity_and_replug_ignore_interface_name(self):
        d = self.device()
        self.assertEqual(self.call("--iface").stdout, "wlx-test\n")
        (d / "idProduct").write_text("ffff\n")
        self.assertNotEqual(self.call("--iface").returncode, 0)
        (d / "idProduct").write_text("1006\n")
        self.assertEqual(self.call("--iface").stdout, "wlx-test\n")

    def test_internal_radio_never_selected(self):
        self.device(driver="mwifiex")
        self.assertNotEqual(self.call("--iface").returncode, 0)

    def test_oem_barrier_requires_sdio_not_usb_wlan0(self):
        self.device(iface="wlan0")
        dev = self.sys / "devices/usb/1-2/1-2:1.0"
        usb = self.sys / "bus/usb"
        (dev / "subsystem").symlink_to(usb)
        self.assertNotEqual(self.call("--oem-ready").returncode, 0)
        (dev / "subsystem").unlink()
        sdio = self.sys / "bus/sdio"
        sdio.mkdir()
        (dev / "subsystem").symlink_to(sdio)
        self.assertEqual(self.call("--oem-ready").returncode, 0)

    def test_absent_card_rejects_network_writes(self):
        r = self.call(
            CONTENT_TYPE="application/x-www-form-urlencoded",
            CONTENT_LENGTH="11", body="action=scan",
            REQUEST_METHOD="POST",
            HTTP_HOST="127.0.0.1",
            SERVER_ADDR="127.0.0.1",
            HTTP_X_DEXTEND_REQUEST="1",
        )
        self.assertIn("409", r.stdout)
        self.assertEqual(list(self.store.iterdir()), [])

    def test_ssh_requires_opt_in_and_valid_local_key(self):
        from urllib.parse import urlencode
        self.device()
        (self.run / "ctrl").mkdir()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(sock.close)
        sock.bind(str(self.run / "ctrl/wlx-test"))
        key = (ROOT / "src/diagnostics/runtime/authorized_keys").read_text().strip()
        def post(action, key, peer="127.0.0.1"):
            body = urlencode({"action": action, "key": key})
            return self.call(REQUEST_METHOD="POST", HTTP_HOST="127.0.0.1",
                             SERVER_ADDR="127.0.0.1", REMOTE_ADDR=peer, HTTP_X_DEXTEND_REQUEST="1",
                             CONTENT_TYPE="application/x-www-form-urlencoded",
                             CONTENT_LENGTH=str(len(body)), body=body).stdout
        active = self.run / "session-key"
        self.assertFalse(active.exists())
        self.assertIn("403", post("ssh-on", key, "192.0.2.1"))
        self.assertIn("400", post("ssh-on", "invalid"))
        self.assertFalse(active.exists())
        self.assertIn("200 OK", post("ssh-on", key))
        self.assertEqual(active.read_text().split(), key.split()[:2])
        self.assertIn("409", post("ssh-on", key))
        self.assertIn("200 OK", post("ssh-off", ""))
        self.assertFalse(active.exists())

    def test_csrf_rejected(self):
        r = self.call(REQUEST_METHOD="POST", HTTP_HOST="evil.example", HTTP_X_DEXTEND_REQUEST="1")
        self.assertIn("403", r.stdout)

    def test_keys_preserve_existing_and_do_not_duplicate_restricted_key(self):
        key = ROOT / "src/diagnostics/runtime/authorized_keys"
        existing = self.base / "authorized_keys"
        old = b'command="my-command" ssh-ed25519 AAAAother user\n'
        existing.write_bytes(old)
        command = ["sh", str(ROOT / "src/diagnostics/runtime/keys.sh"), str(existing), str(key)]
        subprocess.run(command, check=True)
        added = existing.read_bytes()
        self.assertTrue(added.startswith(old))
        self.assertIn(key.read_bytes(), added)
        subprocess.run(command, check=True)
        self.assertEqual(existing.read_bytes(), added)
        restricted = b"no-port-forwarding " + key.read_bytes()
        existing.write_bytes(restricted)
        subprocess.run(command, check=True)
        self.assertEqual(existing.read_bytes(), restricted)

    def test_keys_reject_symlink_and_private_key(self):
        target = self.base / "target"
        target.write_bytes(b"unchanged")
        dest = self.base / "link"
        dest.symlink_to(target)
        self.assertNotEqual(
            subprocess.run(
                [
                    "sh",
                    str(ROOT / "src/diagnostics/runtime/keys.sh"),
                    str(dest),
                    str(ROOT / "src/diagnostics/runtime/authorized_keys"),
                ],
                capture_output=True,
            ).returncode,
            0,
        )
        self.assertEqual(target.read_bytes(), b"unchanged")
        private = self.base / "private"
        private.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
        self.assertNotEqual(
            subprocess.run(
                ["sh", str(ROOT / "src/diagnostics/runtime/keys.sh"), str(target), str(private)],
                capture_output=True,
            ).returncode,
            0,
        )

    def test_cgi_uses_detected_interface_socket(self):
        self.device()
        ctrl = self.run / "ctrl"
        ctrl.mkdir()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(str(ctrl / "wlx-test"))
        sock.settimeout(3)
        self.addCleanup(sock.close)
        requests = []

        def answer():
            for _ in range(3):
                message, addr = sock.recvfrom(4096)
                requests.append(message)
                sock.sendto(
                    b"wpa_state=COMPLETED\nssid=lab\n" if message == b"STATUS" else b"header\n",
                    addr,
                )

        worker = threading.Thread(target=answer)
        worker.start()
        r = self.call(
            REQUEST_METHOD="GET",
            HTTP_HOST="127.0.0.1",
            SERVER_ADDR="127.0.0.1",
            HTTP_X_DEXTEND_REQUEST="1",
        )
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(requests, [b"STATUS", b"LIST_NETWORKS", b"SCAN_RESULTS"])
        self.assertTrue(json.loads(r.stdout.split("\n\n")[1])["ready"])


class KeyRollbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in [
            "root/.ssh",
            "etc/yamaha-sdl/service",
            "tmp/dextend-service",
            "tmp/yamaha-sdl",
        ]:
            (self.root / name).mkdir(parents=True)
        for name in ["keys.sh", "borrow-key.sh", "authorized_keys"]:
            shutil.copyfile(
                ROOT / "src/diagnostics/runtime" / name, self.root / "tmp/dextend-service" / name
            )
        self.keyfile = self.root / "root/.ssh/authorized_keys"
        subprocess.run(
            [
                "cc",
                "-Os",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(ROOT / "src/native/service-key.c"),
                "-o",
                str(self.root / "tmp/yamaha-sdl/service-key"),
            ],
            check=True,
        )

    def call(self, operation):
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
        for n in ["root", "etc", "tmp"]:
            cmd += ["--bind", str(self.root / n), "/" + n]
        cmd += ["--ro-bind", "/etc/alternatives", "/etc/alternatives"]
        return subprocess.run(
            cmd + ["/bin/sh", "/tmp/dextend-service/borrow-key.sh", operation],
            capture_output=True,
            text=True,
        )

    def test_restore_exact_original_and_modes(self):
        old = b"ssh-ed25519 AAAAold owner"
        self.keyfile.write_bytes(old)
        self.keyfile.chmod(0o640)
        self.assertEqual(self.call("add").returncode, 0)
        self.assertIn(
            (ROOT / "src/diagnostics/runtime/authorized_keys").read_bytes(),
            self.keyfile.read_bytes(),
        )
        self.assertEqual(self.call("restore").returncode, 0)
        self.assertEqual(self.keyfile.read_bytes(), old)
        self.assertEqual(self.keyfile.stat().st_mode & 0o777, 0o640)

    def test_restore_absent_file(self):
        self.assertEqual(self.call("add").returncode, 0)
        self.assertTrue(self.keyfile.exists())
        self.assertEqual(self.call("restore").returncode, 0)
        self.assertFalse(self.keyfile.exists())

    def test_repeated_add_and_restore(self):
        self.keyfile.write_bytes(b"old\n")
        self.assertEqual(self.call("add").returncode, 0)
        a = self.keyfile.read_bytes()
        self.assertEqual(self.call("add").returncode, 0)
        self.assertEqual(a, self.keyfile.read_bytes())
        self.assertEqual(self.call("restore").returncode, 0)
        self.assertEqual(self.call("restore").returncode, 0)

    def test_user_edits_preserved_on_conflict(self):
        self.keyfile.write_bytes(b"old\n")
        self.assertEqual(self.call("add").returncode, 0)
        self.keyfile.write_bytes(self.keyfile.read_bytes() + b"user-added-key\n")
        changed = self.keyfile.read_bytes()
        self.assertEqual(self.call("restore").returncode, 0)
        self.assertEqual(self.keyfile.read_bytes(), b"old\nuser-added-key\n")
        self.assertFalse((self.root / "etc/yamaha-sdl/service/borrowed.before").exists())

    def test_edited_service_key_aborts_without_losing_other_keys(self):
        self.keyfile.write_bytes(b"owner-key\n")
        self.assertEqual(self.call("add").returncode, 0)
        changed = self.keyfile.read_bytes().replace(b"dextend-service", b"owner-edited-comment")
        self.keyfile.write_bytes(changed)
        self.assertNotEqual(self.call("restore").returncode, 0)
        self.assertEqual(self.keyfile.read_bytes(), changed)
        self.assertTrue((self.root / "etc/yamaha-sdl/service/borrowed.before").exists())


class ArmSshTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("DEXTEND_SERVICE_BUILD"), "set DEXTEND_SERVICE_BUILD for ARM integration"
    )
    def test_key_login_rejects_other_key_and_password(self):
        binary = Path(os.environ["DEXTEND_SERVICE_BUILD"]) / "bin/dropbearmulti"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ["keys", "etc", "root"]:
                (base / name).mkdir(mode=0o700)
            # Unprivileged namespaces prohibit setgroups. Use a mapped test user
            # for the real ARM authentication + command round trip.
            (base / "etc/passwd").write_text("root:x:1000:1000:root:/root:/bin/sh\n")
            (base / "etc/shadow").write_text("root::0:0:99999:7:::\n")
            (base / "etc/group").write_text("root:x:1000:\n")
            (base / "etc").chmod(0o777)
            (base / "etc/shells").write_text("/bin/sh\n")
            for name in ["client", "rejected"]:
                subprocess.run(
                    [
                        "ssh-keygen",
                        "-q",
                        "-t",
                        "ed25519",
                        "-N",
                        "",
                        "-f",
                        str(base / "keys" / name),
                    ],
                    check=True,
                    capture_output=True,
                )
            shutil.copyfile(base / "keys/client.pub", base / "keys/authorized_keys")
            (base / "keys/authorized_keys").chmod(0o600)
            subprocess.run(
                [
                    "qemu-arm",
                    str(binary),
                    "dropbearkey",
                    "-t",
                    "ed25519",
                    "-f",
                    str(base / "keys/hostkey"),
                ],
                check=True,
                capture_output=True,
            )
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
                "--proc",
                "/proc",
                "--dir",
                "/tmp",
                "--unshare-user",
                "--uid",
                "1000",
                "--gid",
                "1000",
                "--unshare-net",
                "--cap-add",
                "CAP_NET_ADMIN",
                "--cap-add",
                "CAP_NET_RAW",
                "--cap-add",
                "CAP_SETUID",
                "--cap-add",
                "CAP_SETGID",
                "--die-with-parent",
            ]
            for name in ["keys", "etc", "root"]:
                cmd += ["--bind", str(base / name), "/" + name]
            cmd += [
                "--ro-bind",
                str(binary),
                "/server",
                "--ro-bind",
                "/etc/alternatives",
                "/etc/alternatives",
            ]
            script = """
set -eu
mkdir -m 700 /dev/dextend-service-keys
cp /keys/authorized_keys /dev/dextend-service-keys/authorized_keys
chmod 600 /dev/dextend-service-keys/authorized_keys
qemu-arm /server dropbear -F -l lo -p 127.0.0.1:2223 -D /dev/dextend-service-keys -r /keys/hostkey -P /tmp/ssh.pid > /tmp/ssh.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true; cat /tmp/ssh.log >&2' EXIT
sleep 1
opts='-p 2223 -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=3'
ssh $opts -i /keys/client root@127.0.0.1 'printf DEXTEND_SSH_OK'
if ssh $opts -i /keys/rejected root@127.0.0.1 true; then exit 1; fi
if ssh $opts -o PubkeyAuthentication=no -o PreferredAuthentications=password root@127.0.0.1 true; then exit 1; fi
"""
            # Dropbear may signal its process group during shutdown. Isolate the
            # ARM integration test so cleanup cannot terminate the build runner.
            r = subprocess.run(
                cmd + ["/bin/sh", "-c", script],
                capture_output=True,
                text=True,
                timeout=20,
                start_new_session=True,
            )
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("DEXTEND_SSH_OK", r.stdout)

    @unittest.skipUnless(
        os.environ.get("DEXTEND_SERVICE_BUILD"), "set DEXTEND_SERVICE_BUILD for ARM integration"
    )
    def test_actual_arm_staged_hostkey_recovers(self):
        binary = Path(os.environ["DEXTEND_SERVICE_BUILD"]) / "bin/dropbearmulti"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = base / "store"
            store.mkdir()
            runtime = base / "runtime"
            runtime.mkdir()
            wrapper = runtime / "dropbearmulti"
            wrapper.write_text('#!/bin/sh\nexec qemu-arm "' + str(binary) + '" "$@"\n')
            wrapper.chmod(0o700)
            function = (
                (ROOT / "src/diagnostics/runtime/service.sh")
                .read_text()
                .split("ensure_hostkey() {", 1)[1]
                .split("\npublish_panel()", 1)[0]
            )
            command = (
                'set -eu\ns="$1"; r="$2"\nregular() { [ -f "$1" ] && [ ! -L "$1" ]; }\nensure_hostkey() {'
                + function
                + "\nensure_hostkey\n"
            )
            subprocess.run(
                [
                    "qemu-arm",
                    str(binary),
                    "dropbearkey",
                    "-t",
                    "ed25519",
                    "-f",
                    str(store / "hostkey.new"),
                ],
                check=True,
                capture_output=True,
            )
            expected = (store / "hostkey.new").read_bytes()
            result = subprocess.run(
                ["sh", "-c", command, "test", str(store), str(runtime)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((store / "hostkey").read_bytes(), expected)
            self.assertFalse((store / "hostkey.new").exists())
            (store / "hostkey.new.pub").unlink()
            (store / "hostkey").unlink()
            (store / "hostkey.new").write_bytes(b"interrupted")
            result = subprocess.run(
                ["sh", "-c", command, "test", str(store), str(runtime)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual((store / "hostkey").read_bytes(), b"interrupted")
            self.assertFalse((store / "hostkey.new.pub").exists())
            self.assertEqual(list(runtime.glob("hostkey.*")), [])


class VolatileSshKeysTests(unittest.TestCase):
    def test_foreign_directory_and_symlink_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = base / "store"
            store.mkdir()
            (store / "session-key").write_text("owner-key\n")
            volatile = base / "volatile"
            functions = (
                (ROOT / "src/diagnostics/runtime/service.sh")
                .read_text()
                .split("prepare_ssh_keys() {", 1)[1]
                .split("\nstop_radio()", 1)[0]
            )
            script = (
                'set -eu\ns="$1"; r="$1"; a="$2"\nregular() { [ -f "$1" ] && [ ! -L "$1" ]; }\nprepare_ssh_keys() {'
                + functions
                + "\nprepare_ssh_keys\n"
            )

            def call():
                return subprocess.run(
                    ["sh", "-c", script, "test", str(store), str(volatile)], capture_output=True
                )

            volatile.symlink_to(store, target_is_directory=True)
            self.assertNotEqual(call().returncode, 0)
            self.assertEqual((store / "session-key").read_text(), "owner-key\n")
            volatile.unlink()
            volatile.mkdir()
            (volatile / "foreign").write_text("keep")
            self.assertNotEqual(call().returncode, 0)
            self.assertEqual((volatile / "foreign").read_text(), "keep")
            (volatile / "foreign").unlink()
            volatile.rmdir()
            self.assertEqual(call().returncode, 0)
            self.assertEqual((volatile / "authorized_keys").read_text(), "owner-key\n")
            self.assertEqual((volatile.stat().st_mode & 0o777), 0o700)
            self.assertEqual(((volatile / "authorized_keys").stat().st_mode & 0o777), 0o600)
            (store / "session-key").write_text("updated-key\n")
            self.assertEqual(call().returncode, 0)
            self.assertEqual((volatile / "authorized_keys").read_text(), "updated-key\n")
            clean = script.rsplit("prepare_ssh_keys\n", 1)[0] + "clear_ssh_keys\n"
            self.assertEqual(
                subprocess.run(
                    ["sh", "-c", clean, "test", str(store), str(volatile)], capture_output=True
                ).returncode,
                0,
            )
            self.assertFalse(volatile.exists())


class HotplugTests(unittest.TestCase):
    def test_unplug_replug_stops_owned_processes_and_keeps_oem_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Path(tmp)
            r = b / "run"
            store = b / "addon/service"
            fake = b / "bin"
            boa = b / "boa"
            sys = b / "sys"
            for p in [
                r,
                store,
                fake,
                boa / "cgi-bin",
                boa / "www",
                r / "web",
                r / "restore",
                sys / "module/firmware_class/parameters",
            ]:
                p.mkdir(parents=True)
            (store / "format").write_text("dextend-service-v1\n".replace("\\n", "\n"))
            (r / "web/index.html").write_text("existing panel")
            (r / "restore/transaction.sh").write_text("restore")
            (r / "restore-cgi.sh").write_text("restore CGI")
            (b / "addon/enabled").touch()
            (sys / "module/firmware_class/parameters/path").write_text("/oem/firmware")
            (b / "oem-wifi").write_text("unchanged")
            (b / "oem-bluetooth").write_text("unchanged")

            def script(p, text):
                p.write_text("#!/bin/sh\n".replace("\\n", "\n") + text)
                p.chmod(0o700)

            for name in ["authorized_keys", "keys.sh", "borrow-key.sh"]:
                shutil.copyfile(ROOT / "src/diagnostics/runtime" / name, r / name)
            text = (ROOT / "src/diagnostics/runtime/service.sh").read_text()
            text = (
                text.replace("/dev/dextend-service-keys", str(b / "volatile-keys"))
                .replace("/tmp/dextend-service", str(r))
                .replace("/etc/yamaha-sdl", str(b / "addon"))
                .replace("/tmp/boa", str(boa))
                .replace("/sys/module", str(sys / "module"))
                .replace("/root/.ssh", str(b / "home/.ssh"))
            )
            text = text.replace(
                "PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={fake}:/usr/sbin:/usr/bin:/sbin:/bin"
            ).replace("sleep 3", "sleep 0.05")
            manager = b / "manager"
            manager.write_text(text)
            script(
                r / "debug-api",
                f'[ -f "{b}/connected" ] || exit 1\ncase "$1" in --device) echo USB;; --iface) echo wlx-diagnostic;; --ip) echo 10.99.0.2;; esac\n',
            )
            script(fake / "insmod", f'mkdir -p "{sys}/module/$(basename "$1" .ko)"\n')
            script(fake / "rmmod", f'rmdir "{sys}/module/$1"\n')
            script(fake / "pidof", "exit 1\n")
            for name in ["wpa_supplicant", "udhcpc"]:
                script(
                    (r if name == "wpa_supplicant" else fake) / name,
                    f'echo "{name} $*" >> "{b}/events"\nexec sleep 60\n',
                )
            script(
                r / "dropbearmulti",
                f'if [ "$1" = dropbearkey ]; then [ "$2" != -y ] || exit 0; while [ "$1" != -f ]; do shift; done; printf test-key > "$2"; exit 0; fi\necho "SSH $*" >> "{b}/events"\nexec sleep 60\n',
            )
            process = subprocess.Popen(
                ["sh", str(manager), "run"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )

            def wait_for(condition):
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if condition():
                        return
                    if process.poll() is not None:
                        self.fail("manager exited: " + process.stderr.read())
                    time.sleep(0.05)
                self.fail("hotplug condition timed out")

            try:
                time.sleep(0.15)
                self.assertFalse((b / "events").exists())
                (b / "connected").touch()
                wait_for(lambda: (r / "address").exists())
                self.assertFalse((r / "ssh.pid").exists())
                (r / "session-key").write_bytes((r / "authorized_keys").read_bytes())
                wait_for(lambda: (r / "ssh.pid").exists())
                first = (r / "ssh.pid").read_text()
                wait_for(lambda: (b / "events").exists() and "SSH" in (b / "events").read_text())
                (b / "connected").unlink()
                wait_for(lambda: not (r / "ssh.pid").exists())
                (b / "connected").touch()
                wait_for(lambda: (r / "ssh.pid").exists())
                self.assertNotEqual(first, (r / "ssh.pid").read_text())
                (r / "session-key").unlink()
                wait_for(lambda: not (r / "ssh.pid").exists())
                self.assertFalse((b / "volatile-keys/authorized_keys").exists())
                (b / "addon/enabled").unlink()
                process.wait(timeout=10)
                self.assertEqual(process.returncode, 0, process.stderr.read())
                events = (b / "events").read_text()
                self.assertIn("-l wlx-diagnostic", events)
                self.assertIn("-p 10.99.0.2:2223", events)
                self.assertNotIn("wlan0", events)
                self.assertIn("-D " + str(b / "volatile-keys"), events)
                self.assertFalse((b / "volatile-keys").exists())
                self.assertEqual(
                    (sys / "module/firmware_class/parameters/path").read_text(), "/oem/firmware"
                )
                self.assertEqual((boa / "www/dextend/index.html").read_text(), "existing panel")
                self.assertEqual(len((boa / "dextend-restore/token").read_text()), 64)
                self.assertEqual((b / "oem-wifi").read_text(), "unchanged")
                self.assertEqual((b / "oem-bluetooth").read_text(), "unchanged")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)
                process.stderr.close()


class IndependentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.b = Path(self.temp.name)
        self.r = self.b / "run"
        self.store = self.b / "addon/service"
        self.fake = self.b / "bin"
        self.boa = self.b / "boa"
        self.sys = self.b / "sys"
        for p in (
            self.r,
            self.store,
            self.fake,
            self.boa / "www",
            self.boa / "cgi-bin",
            self.r / "web",
            self.r / "restore",
            self.sys / "module/firmware_class/parameters",
        ):
            p.mkdir(parents=True)
        (self.store / "format").write_text("dextend-service-v1\n")
        (self.b / "addon/enabled").touch()
        (self.sys / "module/firmware_class/parameters/path").write_text("/oem/firmware")
        (self.r / "web/index.html").write_text("approved panel")
        (self.r / "web/update").mkdir()
        (self.r / "web/update/index.html").write_text("local updater bridge")
        (self.r / "restore/transaction.sh").write_text("restore")
        (self.r / "restore-cgi.sh").write_text("restore CGI")
        (self.r / "phone-policy").write_text("phone CGI")
        for n in ("authorized_keys", "keys.sh", "borrow-key.sh"):
            shutil.copyfile(ROOT / "src/diagnostics/runtime" / n, self.r / n)
        script = (ROOT / "src/diagnostics/runtime/service.sh").read_text()
        for old, new in (
            ("/dev/dextend-service-keys", self.b / "volatile-keys"),
            ("/tmp/dextend-service", self.r),
            ("/etc/yamaha-sdl", self.b / "addon"),
            ("/tmp/boa", self.boa),
            ("/sys/module", self.sys / "module"),
            ("/root/.ssh", self.b / "home/.ssh"),
        ):
            script = script.replace(old, str(new))
        script = script.replace(
            "PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={self.fake}:/usr/sbin:/usr/bin:/sbin:/bin"
        ).replace("sleep 3", "sleep 0.05")
        (self.r / "service.sh").write_text(script)
        (self.r / "diagnostics.sh").write_text(
            (ROOT / "src/runtime/diagnostics.sh")
            .read_text()
            .replace("/tmp/dextend-diagnostics", str(self.b / "diagnostics"))
        )
        self.script(
            self.r / "debug-api",
            f'''case "$1" in
--device) [ -f "{self.b}/card" ];;
--oem-ready) [ -f "{self.b}/oem-ready" ];;
--iface) echo wlx-diagnostic;;
--ip) echo 10.99.0.2;;
esac
''',
        )
        self.script(
            self.fake / "insmod",
            f'echo module >> "{self.b}/events"; mkdir -p "{self.sys}/module/$(basename "$1" .ko)"\n',
        )
        self.script(self.fake / "rmmod", f'rmdir "{self.sys}/module/$1"\n')
        self.script(self.fake / "pidof", "exit 1\n")
        for n in ("wpa_supplicant", "usb-log-recorder.sh"):
            self.script(self.r / n, "exec sleep 60\n")
        self.script(self.fake / "udhcpc", "exec sleep 60\n")
        self.script(
            self.r / "dropbearmulti",
            f'''
if [ "$1" = dropbearkey ]; then
  op=$2; while [ "$1" != -f ]; do shift; done
  if [ "$op" = -y ]; then [ "$(cat "$2" 2>/dev/null)" = valid ]; exit $?; fi
  echo keygen >> "{self.b}/events"
  [ ! -f "{self.b}/key-fails" ] || exit 1
  [ ! -e "$2" ] || exit 1
  echo valid > "$2"; exit 0
fi
echo ssh >> "{self.b}/events"
exec sleep 60
''',
        )
        self.process = subprocess.Popen(
            ["sh", str(self.r / "service.sh"), "watch"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop)

    def script(self, p, text):
        p.write_text("#!/bin/sh\n" + text)
        p.chmod(0o700)

    def wait_for(self, condition):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if condition():
                return
            if self.process.poll() is not None:
                self.fail("watcher exited: " + self.process.stderr.read())
            time.sleep(0.05)
        self.fail("service state timed out")

    def stop(self):
        subprocess.run(
            ["sh", str(self.r / "service.sh"), "stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
        )
        self.process.wait(timeout=5)
        self.process.stderr.close()
        self.assertFalse((self.b / "volatile-keys").exists())
        for name in ("watcher", "manager", "recorder", "ssh", "wpa", "dhcp"):
            self.assertFalse((self.r / (name + ".pid")).exists(), name + " left after stop")

    def test_panel_survives_key_failure_and_waits_for_oem_radio(self):
        (self.b / "key-fails").touch()
        (self.b / "card").touch()
        self.wait_for(lambda: (self.r / "panel-ready").exists())
        self.wait_for(lambda: (self.r / "heartbeat").exists())
        self.assertFalse((self.sys / "module/ath9k_htc").exists())
        self.assertFalse((self.r / "ssh.pid").exists())
        self.assertEqual(len((self.boa / "dextend-restore/token").read_text()), 64)
        (self.b / "oem-ready").touch()
        self.wait_for(lambda: (self.sys / "module/ath9k_htc").exists())
        self.wait_for(lambda: (self.r / "ssh-status").exists())
        self.assertFalse((self.r / "ssh.pid").exists())
        (self.r / "session-key").write_bytes((self.r / "authorized_keys").read_bytes())
        (self.b / "key-fails").unlink()
        self.wait_for(lambda: (self.r / "ssh.pid").exists())
        self.assertEqual((self.store / "hostkey").read_text(), "valid\n")
        self.assertFalse((self.store / "hostkey.new").exists())
        dhcp = (self.r / "dhcp.pid").read_text()
        ssh = (self.r / "ssh.pid").read_text()
        os.kill(int(dhcp), 15)
        self.wait_for(
            lambda: (self.r / "dhcp.pid").exists() and (self.r / "dhcp.pid").read_text() != dhcp
        )
        self.assertEqual((self.r / "ssh.pid").read_text(), ssh)

    def test_phone_endpoint_is_published_after_late_oem_web_start(self):
        self.wait_for(lambda: (self.r / "panel-ready").exists())
        shutil.rmtree(self.boa)
        manager = (self.r / "manager.pid").read_text()
        time.sleep(0.15)
        (self.boa / "www").mkdir(parents=True)
        (self.boa / "cgi-bin").mkdir()
        # Publication copies first, then sets executable permissions.
        self.wait_for(
            lambda: (
                (self.boa / "cgi-bin/dextend-phones").exists()
                and bool((self.boa / "cgi-bin/dextend-phones").stat().st_mode & 0o100)
            )
        )
        self.assertEqual((self.boa / "cgi-bin/dextend-phones").read_text(), "phone CGI")
        self.assertEqual(
            (self.boa / "www/dextend/update/index.html").read_text(), "local updater bridge"
        )
        self.assertEqual((self.r / "manager.pid").read_text(), manager)
        self.assertTrue((self.boa / "cgi-bin/dextend-phones").stat().st_mode & 0o100)

    def test_wifi_worker_restart_keeps_manager_and_records_evidence(self):
        (self.b / "card").touch()
        (self.b / "oem-ready").touch()
        self.wait_for(lambda: (self.r / "wpa.pid").exists() and (self.r / "wpa.start").exists())
        manager = (self.r / "manager.pid").read_text()
        worker = (self.r / "wpa.pid").read_text()
        os.kill(int(worker), 15)
        self.wait_for(
            lambda: (self.r / "wpa.pid").exists() and (self.r / "wpa.pid").read_text() != worker
        )
        self.assertEqual((self.r / "manager.pid").read_text(), manager)
        events = (self.b / "diagnostics/events").read_text()
        self.assertGreaterEqual(events.count("process_start wpa pid="), 2)
        self.assertTrue((self.r / "wpa.events").is_fifo())

    def test_watchdog_restarts_manager_and_republishes_panel(self):
        self.wait_for(lambda: (self.r / "panel-ready").exists())
        first = (self.r / "manager.pid").read_text()
        os.kill(int(first), 15)
        self.wait_for(
            lambda: (
                (self.r / "manager.pid").exists() and (self.r / "manager.pid").read_text() != first
            )
        )
        self.wait_for(lambda: (self.boa / "cgi-bin/dextend-debug").exists())
        self.assertEqual((self.boa / "www/dextend/index.html").read_text(), "approved panel")
        self.assertIsNone(self.process.poll())

    def test_staged_key_is_recovered_without_regeneration(self):
        # Start absent card, then simulate a complete key left by interrupted rename.
        self.wait_for(lambda: (self.store / "hostkey").exists())
        original = (self.store / "hostkey").read_bytes()
        (self.store / "hostkey").rename(self.store / "hostkey.new")
        previous = (self.b / "events").read_text()
        self.wait_for(lambda: (self.store / "hostkey").exists())
        self.assertEqual((self.store / "hostkey").read_bytes(), original)
        self.assertEqual((self.b / "events").read_text(), previous)
        (self.store / "hostkey").unlink()
        (self.store / "hostkey.new").write_text("partial")
        self.wait_for(lambda: (self.store / "hostkey").exists())
        self.assertEqual((self.store / "hostkey").read_text(), "valid\n")


if __name__ == "__main__":
    unittest.main()
