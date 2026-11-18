#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Real HTTP/parser/signature tests, no hardware writes.
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import tempfile
import time
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://127.0.0.1"


class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.key = Ed25519PrivateKey.generate()
        pub = cls.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        header = cls.root / "key.h"
        header.write_text(
            "static const unsigned char update_key[32]={" + ",".join(map(str, pub)) + "};"
        )
        cls.binary = cls.root / "updater-http"
        third = ROOT / "src/native/third-party/monocypher"
        subprocess.run(
            [
                "cc",
                "-Os",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I" + str(third),
                '-DUPDATE_KEY_HEADER="' + str(header) + '"',
                str(ROOT / "src/native/updater-http.c"),
                str(third / "monocypher.c"),
                str(third / "monocypher-ed25519.c"),
                "-o",
                str(cls.binary),
            ],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.w = Path(self.work.name)
        (self.w / "updater-http").symlink_to(self.binary)
        (self.w / "token").write_text("a" * 64)
        (self.w / "state").write_text("idle\n")
        api = (
            (ROOT / "src/runtime/updater-api.sh")
            .read_text()
            .replace("w=/tmp/dextend-updater", "w=" + str(self.w))
        )
        api = api.replace("s=/etc/yamaha-sdl/usb-v1", "s=" + str(self.w / "installed"))
        self.script = self.w / "api.sh"
        self.script.write_text(api)
        (self.w / "updater-events.sh").write_bytes(
            (ROOT / "src/runtime/updater-events.sh").read_bytes()
        )
        (self.w / "events.log").write_text("")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [str(self.binary), str(self.port), str(self.script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.02)

    def tearDown(self):
        import signal

        os.killpg(self.proc.pid, signal.SIGTERM)
        self.proc.wait()
        self.work.cleanup()

    def request(self, path, method="GET", body=None, origin=ORIGIN, token="a" * 64, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Origin": origin, "X-Dextend-Token": token}
        if host:
            headers["Host"] = host
        c.request(method, path, body=body, headers=headers)
        r = c.getresponse()
        data = r.read()
        status = r.status
        headers = dict(r.getheaders())
        c.close()
        return status, headers, json.loads(data) if data else None

    def test_empty_or_malformed_session_token_rejects_requests(self):
        for token in ("", "x" * 64, "a" * 63):
            with self.subTest(token_length=len(token)):
                (self.w / "token").write_text(token)
                self.assertEqual(self.request("/v1/info")[0], 503)
                self.assertEqual(self.request("/v1/begin", "POST", b"", token=token)[0], 503)

    def test_startup_recovers_partial_directory_and_restarts_listener(self):
        source = self.w / "source"
        source.mkdir()
        (source / "web/update").mkdir(parents=True)
        shutil.copy2(self.binary, source / "updater-http")
        for name in ("updater-api.sh", "updater-worker.sh", "updater-events.sh"):
            shutil.copy2(ROOT / "src/runtime" / name, source / name)
        (source / "web/update/index.html").write_text("bridge")
        run = self.w / "retry"
        run.mkdir()
        (run / "token").write_text("")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        launcher = source / "start.sh"
        launcher.write_text(
            (ROOT / "src/runtime/start-updater.sh")
            .read_text()
            .replace("w=/tmp/dextend-updater", "w=" + str(run))
            .replace(" 8765 ", " " + str(port) + " ")
        )

        def launch():
            subprocess.run(["sh", str(launcher)], check=True, capture_output=True)
            pid = int((run / "http.pid").read_text())
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        return pid
                except OSError:
                    time.sleep(0.02)
            self.fail("listener never became ready")

        pid = None
        try:
            fake = self.w / "bin"
            fake.mkdir()
            encoder = fake / "hexdump"
            encoder.write_text("#!/bin/sh\nprintf short\n")
            encoder.chmod(0o700)
            failed = subprocess.run(
                ["sh", str(launcher)],
                env={**os.environ, "PATH": str(fake) + ":" + os.environ["PATH"]},
                capture_output=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse((run / "http.pid").exists())
            self.assertEqual((run / "token").read_text(), "")
            self.assertEqual(list(run.glob(".token.*")), [])
            self.assertFalse((run / "start.lock").exists())
            pid = launch()
            token = (run / "token").read_text()
            self.assertRegex(token, r"^[0-9a-f]{64}$")
            self.assertEqual((run / "token").stat().st_mode & 0o777, 0o600)
            self.assertEqual(launch(), pid)
            (run / "events.log").write_text("100 PRESERVE\n")
            (run / "state").write_text("failed\n")
            os.kill(pid, 15)
            for _ in range(100):
                try:
                    if Path("/proc/" + str(pid) + "/stat").read_text().split()[2] == "Z":
                        break
                except FileNotFoundError:
                    break
                time.sleep(0.02)
            pid = launch()
            self.assertEqual((run / "token").read_text(), token)
            self.assertEqual((run / "state").read_text(), "failed\n")
            self.assertEqual((run / "events.log").read_text(), "100 PRESERVE\n")
        finally:
            if pid:
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass

    def manifest(self, image=b"fixture IMG"):
        m = f"DEXTEND-IMG-1\n0.13-alpha\n202611140099\n{len(image)}\n{hashlib.sha256(image).hexdigest()}\n".encode()
        return m + self.key.sign(m).hex().encode() + b"\n"

    def test_diagnostics_exclude_tokens_and_payloads(self):
        self.request("/v1/begin", "POST", self.manifest(b"private-payload"))
        self.request("/v1/install", "POST", b"")
        status, _, data = self.request("/v1/log")
        self.assertEqual(status, 200)
        codes = [x["code"] for x in data["events"]]
        self.assertIn("MANIFEST_SIGNATURE_OK", codes)
        self.assertIn("incomplete", codes)
        self.assertNotIn("a" * 64, json.dumps(data))
        self.assertNotIn("private-payload", json.dumps(data))
        self.assertEqual(self.request("/v1/info")[2]["diagnostics"], 1)

    def test_failed_native_start_keeps_installed_version_visible(self):
        state = self.w / "installed"
        release = state / "releases" / ("b" * 64)
        release.mkdir(parents=True)
        (state / "active").write_text("none\n")
        (state / "service-release").write_text("b" * 64 + "\n")
        (state / "status").write_text("ROLLED_BACK_RESTART_REQUIRED\n")
        (release / "version.txt").write_text("0.15-alpha\n202611140101\n")
        status, _, info = self.request("/v1/info")
        self.assertEqual(status, 200)
        self.assertEqual(info["version"], "0.15-alpha")
        self.assertFalse(info["confirmed"])

    def test_log_is_bounded_and_filters_malformed_records(self):
        (self.w / "events.log").write_text("100 BAD_TOKEN/secret\n101 GOOD_CODE\n")
        self.assertEqual(self.request("/v1/log")[2]["events"], [{"at": 101, "code": "GOOD_CODE"}])
        (self.w / "events.log").unlink()
        self.assertEqual(self.request("/v1/log")[2]["events"], [])
        for i in range(70):
            subprocess.run(
                [
                    "sh",
                    "-c",
                    'w="$1"; . "$2"; update_event EVENT',
                    "sh",
                    str(self.w),
                    str(self.w / "updater-events.sh"),
                ],
                check=True,
            )
        self.assertLessEqual(len(self.request("/v1/log")[2]["events"]), 64)

    def test_discovery_and_cors(self):
        status, h, data = self.request("/v1/info")
        self.assertEqual(status, 200)
        self.assertEqual(data["product"], "Dextend")
        self.assertEqual(h["Access-Control-Allow-Origin"], ORIGIN)

    def test_options(self):
        self.assertEqual(self.request("/v1/begin", "OPTIONS")[0], 204)

    def test_foreign_origin(self):
        self.assertEqual(self.request("/v1/info", origin="https://evil.test")[0], 403)

    def test_panel_bridge_origins_and_token_checks(self):
        for host in ("10.42.17.8", "172.20.10.9", "autobox.com"):
            origin = "http://" + host
            with self.subTest(host=host):
                opts = {"origin": origin, "host": host + ":8765"}
                status, headers, _ = self.request("/v1/info", **opts)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Access-Control-Allow-Origin"], origin)
                self.assertEqual(self.request("/v1/begin", "OPTIONS", **opts)[0], 204)
                self.assertEqual(
                    self.request("/v1/begin", "POST", self.manifest(), token="wrong", **opts)[0],
                    403,
                )
                self.assertEqual(self.request("/v1/begin", "POST", self.manifest(), **opts)[0], 200)
        for origin in (
            "http://127.0.0.1.evil.test",
            "http://127.0.0.1:9999",
            "null",
            "https://updater.getdextend.com",
            "http://10.42.17.9",
        ):
            status, headers, _ = self.request("/v1/info", origin=origin)
            self.assertEqual(status, 403)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.request("/bridge")[0], 404)

    def test_bad_token(self):
        self.assertEqual(self.request("/v1/begin", "POST", self.manifest(), token="bad")[0], 403)

    def test_signature_rejection(self):
        manifest = self.manifest().replace(b"0.13-alpha", b"0.14-alpha")
        self.assertEqual(self.request("/v1/begin", "POST", manifest)[0], 403)
        self.assertFalse((self.w / "image.img").exists())

    def test_wrong_key(self):
        m = self.manifest()
        other = Ed25519PrivateKey.generate()
        body = m[:-129] + other.sign(m[:-129]).hex().encode() + b"\n"
        self.assertEqual(self.request("/v1/begin", "POST", body)[0], 403)

    def test_chunked_transfer_and_offset(self):
        image = b"x" * 100000
        self.assertEqual(self.request("/v1/begin", "POST", self.manifest(image))[0], 200)
        self.assertEqual(self.request("/v1/chunk?offset=1", "POST", b"a")[0], 409)
        self.assertEqual(self.request("/v1/chunk?offset=0", "POST", image[:65536])[0], 200)
        self.assertEqual(self.request("/v1/chunk?offset=65536", "POST", image[65536:])[0], 200)
        self.assertEqual((self.w / "image.img").read_bytes(), image)
        self.assertEqual(self.request("/v1/status")[2]["received"], 100000)

    def test_corrupt_image_never_starts_worker(self):
        self.request("/v1/begin", "POST", self.manifest(b"good"))
        self.request("/v1/chunk?offset=0", "POST", b"evil")
        self.assertEqual(self.request("/v1/install", "POST", b"")[2]["error"], "checksum")
        self.assertEqual((self.w / "state").read_text().strip(), "receiving")

    def test_incomplete_image(self):
        self.request("/v1/begin", "POST", self.manifest())
        self.assertEqual(self.request("/v1/install", "POST", b"")[2]["error"], "incomplete")

    def test_cancel(self):
        self.request("/v1/begin", "POST", self.manifest())
        self.assertEqual(self.request("/v1/cancel", "POST", b"")[0], 200)
        self.assertFalse((self.w / "image.img").exists())

    def test_install_state_prevents_reset(self):
        (self.w / "state").write_text("installing\n")
        for route in ("begin", "cancel", "reboot"):
            self.assertEqual(self.request("/v1/" + route, "POST", self.manifest())[0], 409)

    def test_unknown_route(self):
        self.assertEqual(self.request("/v1/nope")[0], 404)

    def test_signed_oversize_manifest(self):
        m = b"DEXTEND-IMG-1\n0.13-alpha\n202611140099\n2097153\n" + b"a" * 64 + b"\n"
        m += self.key.sign(m).hex().encode() + b"\n"
        self.assertEqual(self.request("/v1/begin", "POST", m)[0], 400)

    def test_oversize_http_body(self):
        self.assertEqual(self.request("/v1/begin", "POST", b"x" * 65537)[0], 400)

    def test_duplicate_length_and_transfer_encoding(self):
        for header in ("Content-Length: 0\r\nContent-Length: 1", "Transfer-Encoding: chunked"):
            with socket.create_connection(("127.0.0.1", self.port)) as s:
                s.sendall(
                    (
                        "POST /v1/begin HTTP/1.1\r\nHost: 127.0.0.1\r\n" + header + "\r\n\r\n"
                    ).encode()
                )
                self.assertIn(b"400 Bad Request", s.recv(1024))

    def test_valid_signature_worker_detached(self):
        # Substitute an inert worker. Never execute real installer/reboot on host.
        (self.w / "updater-worker.sh").write_text(
            "sleep 0.2\necho ready > " + str(self.w / "state") + "\n"
        )
        image = b"test"
        self.request("/v1/begin", "POST", self.manifest(image))
        self.request("/v1/chunk?offset=0", "POST", image)
        self.assertEqual(self.request("/v1/install", "POST", b"")[0], 202)
        time.sleep(0.4)
        self.assertEqual(self.request("/v1/status")[2]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
