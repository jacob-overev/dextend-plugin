# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Fault injection through real PTYs/Unix sockets; no dongle or CCU needed."""

import json
import os
import pty
import select
import socket
import struct
import subprocess
import tempfile
import time
import tty
from pathlib import Path
from test_probe import frame, read_frame
from test_live import packet, video

IDR = b"\0\0\0\1\x67sps\0\0\0\1\x68pps\0\0\0\1\x65fresh"
P = b"\0\0\0\1\x41predicted"


def wait_for(predicate, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition timed out")


class Rig:
    def __init__(self, root, markers=False, **overrides):
        self.root = Path(root)
        self.path = self.root / "phone.sock"
        self.device = self.root / "ccu"
        self.log = self.root / "bridge.log"
        self.master = self.slave = None
        self.source = None
        env = dict(
            os.environ,
            YAMAHA_CARPLAY_SOCKET=str(self.path),
            YAMAHA_WAITING_FRAME=os.environ["YAMAHA_WAITING_FRAME"],
        )
        env.pop("YAMAHA_RUNTIME", None)
        if markers:
            env["YAMAHA_RUNTIME"] = str(self.root)
        env.pop("YAMAHA_CCU_STATE", None)
        env.update(overrides)
        self.process = subprocess.Popen(
            [os.environ["YAMAHA_PROBE_CMD"], str(self.device), "--live", str(self.log), "0"],
            env=env,
        )
        wait_for(self.path.exists)

    def phone(self):
        self.source = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.source.settimeout(3)
        self.source.connect(str(self.path))
        self.source.sendall(packet(0xF1, struct.pack("<I", 3)) + packet(5, struct.pack("<I", 3)))
        return self.source

    def ccu(self):
        self.master, self.slave = pty.openpty()
        tty.setraw(self.slave)
        self.device.unlink(missing_ok=True)
        self.device.symlink_to(os.ttyname(self.slave))

    def rpc(self, function, body, kind=2, correlation=0):
        data = json.dumps(body).encode()
        os.write(
            self.master,
            frame(
                4,
                1,
                7,
                0,
                1,
                struct.pack(">III", (kind << 28) | function, correlation, len(data)) + data,
            ),
        )

    def until(self, predicate, timeout=5):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if select.select([self.master], [], [], 0.1)[0]:
                h, p = read_frame(self.master)
                if h[1:3] == bytes([0, 0]):
                    os.write(self.master, frame(4, 0, 0, 255, 1))
                if predicate(h, p):
                    return p
        raise AssertionError("expected CCU frame missing")

    def start(self, accept=True, video_accept=True, timeout=5):
        self.until(lambda h, p: h[:4] == bytes([0x10, 7, 1, 0]), timeout)
        os.write(self.master, frame(4, 0, 7, 2, 1, b"\0\0\0\1"))
        self.until(lambda h, p: h[1] == 7 and len(p) > 12 and struct.unpack_from(">I", p)[0] == 1)
        self.rpc(1, {"success": accept}, kind=1, correlation=1)
        if accept:
            self.rpc(32768, {"hmiLevel": "FULL"})
            if video_accept:
                self.video_start()
            else:
                self.until(lambda h, p: h[1:3] == bytes([11, 1]))

    def video_start(self, timeout=5):
        self.until(lambda h, p: h[1:3] == bytes([11, 1]), timeout)
        os.write(self.master, frame(4, 0, 11, 2, 1))

    def keyframe(self):
        got = b""
        while len(got) < 28:
            got += self.source.recv(28 - len(got))
        assert got == packet(6, struct.pack("<III", 4, 12, 12)), got

    def assert_video(self, payload):
        self.until(lambda h, p: h[1] == 11 and (h[0] & 7) == 1 and p == payload)

    def disconnect_ccu(self):
        os.close(self.master)
        os.close(self.slave)
        self.master = self.slave = None
        self.device.unlink(missing_ok=True)

    def text(self):
        return self.log.read_text()

    def close(self):
        if self.source:
            self.source.close()
        self.process.terminate()
        self.process.wait(timeout=3)
        if self.master is not None:
            os.close(self.master)
        if self.slave is not None:
            os.close(self.slave)


def main():
    waiting = Path(os.environ["YAMAHA_WAITING_FRAME"]).read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        r = Rig(directory)
        try:
            # Phone starts before any CCU; drain substantially more than IPC capacity.
            r.phone()
            for _ in range(250):
                r.source.sendall(video(P + b"x" * 16000))
            assert r.process.poll() is None
            r.ccu()
            r.start()
            r.keyframe()
            assert "WAITING_FOR_CARPLAY_FRAME" not in r.text()
            r.source.sendall(video(P) + video(IDR) + video(P))
            r.assert_video(IDR)
            r.assert_video(P)
            os.write(r.master, frame(4, 0, 11, 254, 1, b"\0\0\0\1"))
            print("OK: CarPlay without CCU, bounded draining, direct fresh IDR for ready phone")

            # HMI close must preserve the same phone socket, reopening needs fresh IDR.
            r.rpc(32768, {"hmiLevel": "NONE"})
            time.sleep(0.1)
            r.source.sendall(video(P))
            r.rpc(32768, {"hmiLevel": "FULL"})
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            print("OK: navigation leave/re-enter keeps phone session and resynchronizes")

            # Physical CCU removal must not close the phone or stop draining video.
            r.disconnect_ccu()
            for _ in range(100):
                r.source.sendall(video(P + b"x" * 16000))
            wait_for(lambda: "CCU reason=" in r.text())
            r.ccu()
            r.start()
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            print("OK: CCU unplug/replug retains original phone socket")

            # Phone disappearance displays a card but preserves SDL registration.
            r.source.close()
            r.source = None
            r.until(lambda h, p: h[1:3] == bytes([11, 4]) and p == b"\0\0\0\1")
            os.write(r.master, frame(4, 0, 11, 5, 1))
            r.video_start()
            r.assert_video(waiting)
            r.phone()
            r.until(lambda h, p: h[1:3] == bytes([11, 4]))
            os.write(r.master, frame(4, 0, 11, 5, 1))
            r.video_start()
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            print("OK: phone disconnect/reconnect preserves CCU and replaces waiting card")

            # EndService and StartService NAK must retry without a manual navigation toggle.
            os.write(r.master, frame(4, 0, 11, 4, 1))
            r.until(lambda h, p: h[1:3] == bytes([11, 1]))
            os.write(r.master, frame(4, 0, 11, 3, 1))
            r.video_start()
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            print("OK: video EndService/NAK automatically recover")

            # Unregistered app and rejected registration recover on the same bridge process.
            r.rpc(32769, {"reason": "PROTOCOL_VIOLATION"})
            r.start(accept=False)
            r.start()
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            print("OK: app unregistration/rejected registration retry independently")

            # A corrupt peer cannot kill the bridge or a healthy phone client.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as bad:
                bad.connect(str(r.path))
                bad.sendall(b"bad header" * 3)
            time.sleep(0.1)
            r.source.sendall(video(P))
            r.assert_video(P)
            print("OK: malformed unrelated IPC client isolated")

            # CCU stops reading while source continues: queue must remain bounded and
            # recover CCU without disconnecting the source. Exceeds kernel + app buffers.
            for _ in range(180):
                r.source.sendall(video(P + b"x" * 64000))
            wait_for(lambda: "CCU_TX_QUEUE_FULL" in r.text() or "CCU_TX_STALLED" in r.text())
            assert r.process.poll() is None
            r.source.sendall(video(P))
            print("OK: blocked CCU cannot block phone ingestion; queue recovery bounded")
        finally:
            r.close()

    # CCU can start with no phone at all, and malformed USB triggers a retry.
    with tempfile.TemporaryDirectory() as directory:
        r = Rig(directory)
        try:
            r.ccu()
            r.start()
            r.assert_video(waiting)
            os.write(r.master, b"\xff" + b"\0" * 11)
            r.start()
            r.assert_video(waiting)
            print("OK: CCU alone serves waiting card and malformed USB recovers")
        finally:
            r.close()

    # Exercise the actual handoff protocol between the bridge and AOA worker.
    with tempfile.TemporaryDirectory() as directory:
        r = Rig(directory, markers=True)
        try:
            r.phone()
            r.ccu()
            (r.root / "ccu-recover").unlink(missing_ok=True)
            r.start()
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            (r.root / "ccu-preparing").touch()
            wait_for(lambda: (r.root / "ccu-fd").read_text().strip() == "closed")
            assert not (r.root / "ccu-recover").exists(), (
                "bridge must not request a second reset during prepare"
            )
            for _ in range(100):
                r.source.sendall(video(P + b"x" * 16000))
            (r.root / "ccu-preparing").unlink()
            r.start()
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            print("OK: AOA worker can reset CCU after fd release without restarting phone")
            r.rpc(32771, {"buttonName": "PRESET_6", "buttonPressMode": "LONG"})
            r.keyframe()
            deadline = time.monotonic() + 12
            while not (r.root / "phone-restart").exists() and time.monotonic() < deadline:
                if select.select([r.master], [], [], 0.1)[0]:
                    h, p = read_frame(r.master)
                    if h[1:3] == bytes([0, 0]):
                        os.write(r.master, frame(4, 0, 0, 255, 1))
            assert (r.root / "phone-restart").read_text() == "keyframe_timeout"
            assert (r.root / "ccu-fd").read_text().strip() == "open"
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            print("OK: Home refresh with missing IDR requests phone recovery, keeps CCU")

        finally:
            r.close()

    with tempfile.TemporaryDirectory() as directory:
        r = Rig(directory)
        try:
            r.phone()
            r.ccu()
            r.until(lambda h, p: h[:4] == bytes([0x10, 7, 1, 0]))
            # Ignore StartService; second handshake must be automatic.
            r.start(video_accept=False, timeout=12)
            # Ignore the first video StartService too; heartbeat replies keep RPC alive.
            r.video_start(timeout=12)
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            assert "response_timeout" in r.text() and "VIDEO_ACK_TIMEOUT" in r.text()
            print("OK: lost RPC StartService ACK and video ACK recover after deadlines")
        finally:
            r.close()


def ipc_recovery():
    with tempfile.TemporaryDirectory() as directory:
        r = Rig(directory, markers=True, YAMAHA_IAP2_WIFI_ROUTER_TEST="1")
        peers = []

        def client(kind):
            peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            peers.append(peer)
            peer.settimeout(4)
            peer.connect(str(r.path))
            peer.sendall(packet(0xF1, struct.pack("<I", kind)))
            return peer

        def receive(peer, size):
            result = bytearray()
            while len(result) < size:
                chunk = peer.recv(size - len(result))
                assert chunk, "IPC peer closed before the message was complete"
                result.extend(chunk)
            return result

        try:
            source = r.phone()
            control = packet(6, struct.pack("<II", 5, 102) + b"hello")
            source.sendall(control)
            time.sleep(0.1)
            assert not (Path(directory) / "phone-restart").exists()
            iap = client(32)
            assert receive(iap, len(control)) == control, (
                "handover must preserve early control bytes"
            )
            iap.sendall(control)
            assert receive(source, len(control)) == control
            # iAP2 phase values must not masquerade as receiver phase changes.
            iap.sendall(packet(5, struct.pack("<I", 1)))
            time.sleep(0.1)
            assert "CARPLAY_PHASE phase=1" not in r.text()
            replacement = client(32)
            assert iap.recv(1) == b"", "new registration must close stale iAP2 owner"
            source.sendall(control)
            assert receive(replacement, len(control)) == control
            (Path(directory) / "iap2-wifi-active").touch()
            replacement.close()
            wait_for(lambda: (Path(directory) / "iap2-wifi-request").exists())
            source.sendall(control)
            wait_for(lambda: (Path(directory) / "phone-restart").exists(), timeout=10)
            assert r.process.poll() is None, "phone recovery must preserve bridge/SDL process"
            assert "peer timeout" in r.text()
            print(
                "OK: exact early handover delivery, bidirectional IPC, sender isolation, client replacement, bounded missing-peer recovery"
            )
        finally:
            for peer in peers:
                peer.close()
            r.close()


def video_ack_guard():
    with tempfile.TemporaryDirectory() as root:
        r = Rig(root, YAMAHA_VIDEO_ACK_GUARD="1")
        try:
            r.ccu()
            r.phone()
            r.start()
            r.keyframe()
            r.source.sendall(video(IDR))
            r.assert_video(IDR)
            for _ in range(3):
                r.source.sendall(video(P))
                r.assert_video(P)
            r.source.sendall(video(P))
            time.sleep(0.2)
            assert "VIDEO_GUARD_PAUSED sent=4 acked=0" in r.text(), r.text()
            # Partial ACKs must not resume video; RPC stays available while paused.
            os.write(r.master, frame(4, 0, 11, 254, 1))
            r.source.sendall(video(P))
            time.sleep(0.2)
            assert "VIDEO_GUARD_RESUME" not in r.text()
            os.write(r.master, frame(4, 0, 0, 0, 1))

            def heartbeat(h, p):
                assert not (h[1] == 11 and (h[0] & 7) == 1), "video resumed before backlog drained"
                return h[1:3] == bytes([0, 255])

            r.until(heartbeat)
            for _ in range(3):
                os.write(r.master, frame(4, 0, 11, 254, 1))
            r.keyframe()
            r.source.sendall(video(P) + video(IDR))
            r.assert_video(IDR)
            assert "VIDEO_GUARD_RESUME" in r.text()
            assert "RECOVERY CCU" not in r.text().split("VIDEO_GUARD_PAUSED", 1)[1]
            assert r.process.poll() is None and r.source.fileno() >= 0
        finally:
            r.close()
    print(
        "OK: four outstanding frames pause video; backlog drains before fresh IDR resume; RPC/phone preserved"
    )


if __name__ == "__main__":
    main()
    ipc_recovery()
    video_ack_guard()
