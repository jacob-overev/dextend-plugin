# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""A fake byte-stream CCU: verifies the probe's stage progression without hardware."""

import os
import pty
import select
import shlex
import struct
import subprocess
import tempfile
import termios
import time
import tty
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_exact(fd: int, count: int) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + 5
    while len(data) < count:
        if time.monotonic() > deadline:
            raise TimeoutError(f"received {len(data)}/{count} bytes")
        if select.select([fd], [], [], 0.1)[0]:
            data.extend(os.read(fd, count - len(data)))
    return bytes(data)


def read_frame(fd: int):
    head = read_exact(fd, 8)
    version = head[0] >> 4
    if version != 1:
        head += read_exact(fd, 4)
    payload = read_exact(fd, struct.unpack(">I", head[4:8])[0])
    return head, payload


def frame(version: int, kind: int, service: int, info: int, session: int, payload=b""):
    head = bytes([(version << 4) | kind, service, info, session])
    head += struct.pack(">I", len(payload))
    if version != 1:
        head += struct.pack(">I", 2)
    return head + payload


def main():
    master, slave = pty.openpty()
    tty.setraw(slave, termios.TCSANOW)
    device = os.ttyname(slave)
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "probe.log")
        trace = str(Path(tmp) / "frames.bin")
        command = shlex.split(os.environ.get("YAMAHA_PROBE_CMD", str(ROOT / "yamaha-sdl-probe")))
        sample = Path(os.environ.get("YAMAHA_PROBE_SAMPLE", str(ROOT / "dist/frame.h264")))
        recorded = sample.read_bytes().startswith(b"YCPAU001")
        proc = subprocess.Popen(command + [device, str(sample), log, "3", trace])
        try:
            head, data = read_frame(master)
            assert head[:4] == bytes([0x10, 7, 1, 0]) and data == b""
            os.write(master, frame(4, 0, 7, 2, 1, b"\0\0\0\1"))
            head, data = read_frame(master)
            assert head[0] == 0x41 and head[1] == 7
            assert data[:4] == b"\0\0\0\1" and b"Motorize" in data
            response = b'{\n   "resultCode" : "SUCCESS",\n   "success" : true\n}'
            rpc = struct.pack(">III", 0x10000001, 1, len(response)) + response
            os.write(master, frame(4, 1, 7, 0, 1, rpc))
            hmi = b'{\n   "audioStreamingState" : "NOT_AUDIBLE",\n   "hmiLevel" : "FULL"\n}'
            rpc_hmi = struct.pack(">III", 0x20008000, 0, len(hmi)) + hmi
            os.write(master, frame(4, 1, 7, 0, 1, rpc_hmi))
            while True:
                head, _ = read_frame(master)
                if head[1] == 11 and head[2] == 1:
                    break
            os.write(master, frame(4, 0, 11, 2, 1))
            while True:
                head, data = read_frame(master)
                if head[1] == 11 and head[0] == 0x41:
                    assert data.startswith(b"\0\0\0\x01")
                    break
            if recorded:
                first_video = data
                while True:
                    head, data = read_frame(master)
                    if head[1] == 11 and head[0] == 0x41:
                        assert data.startswith(b"\0\0\0\x01")
                        assert data != first_video, "Clip repeated its first frame"
                        break
            # CCU can end video while the RPC session remains alive.
            os.write(master, frame(4, 0, 11, 4, 1))
            deadline = time.monotonic() + 7
            while proc.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    os.read(master, 65536)
            assert proc.wait(timeout=1) == 1  # no active video at exit
            logged = Path(log).read_text()
            assert "VIDEO_SERVICE_ACK" in logged
            after_end = logged.split("VIDEO_SERVICE_ENDED", 1)[1]
            assert "TX    SDL v4 kind=1 service=11" not in after_end
            captured = Path(trace).read_bytes()
            assert captured[:5] == b"\x01\x00\x00\x00\x08"
            assert b"YAMAHA SDL TEST" not in captured  # encoded as H.264
            print(
                "OK: RPC, Yamaha JSON/FULL, H.264, stop after CCU EndService; recorded="
                + str(recorded)
            )
        finally:
            proc.terminate()
            proc.wait(timeout=3)
    os.close(master)
    os.close(slave)


if __name__ == "__main__":
    main()
