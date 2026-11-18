# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Exercise live IPC framing, HMI gating and ordered video over a fake CCU."""

import json
import os
import pty
import socket
import struct
import subprocess
import tempfile
import time
import tty
from pathlib import Path
from test_probe import frame, read_frame


def packet(cmd, data):
    return struct.pack("<4I", 0x55AA55AA, len(data), cmd, cmd ^ 0xFFFFFFFF) + data


def video(data):
    return packet(6, struct.pack("<II", len(data), 1) + data)


def main():
    binary = os.environ["YAMAHA_PROBE_CMD"]
    master, slave = pty.openpty()
    tty.setraw(slave)
    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "live.log"
        path = str(Path(directory) / "source.sock")
        env = dict(os.environ, YAMAHA_CARPLAY_SOCKET=path)
        process = subprocess.Popen([binary, os.ttyname(slave), "--live", str(log), "4"], env=env)
        source = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            read_frame(master)
            source.connect(path)
            source.sendall(packet(0xF1, struct.pack("<I", 3)) + packet(5, struct.pack("<I", 3)))
            # These data must be drained without reaching USB before HMI_FULL.
            source.sendall(video(b"\0\0\0\1\x65before-hmi"))
            time.sleep(0.08)
            os.write(master, frame(4, 0, 7, 2, 1, b"\0\0\0\1"))
            head, registration = read_frame(master)
            identity = json.loads(registration[12:])
            assert identity["appName"] == "Motorize"
            assert identity["appID"] == "7a5f3f258b"
            assert identity["fullAppID"] == "7a5f3f25-8b82-4e0f-a173-80aefee79897"
            response = b'{"success": true}'
            os.write(
                master,
                frame(4, 1, 7, 0, 1, struct.pack(">III", 0x10000001, 1, len(response)) + response),
            )
            hmi = b'{"hmiLevel": "FULL"}'
            os.write(
                master, frame(4, 1, 7, 0, 1, struct.pack(">III", 0x20008000, 0, len(hmi)) + hmi)
            )
            subscriptions = []
            while True:
                head, payload = read_frame(master)
                if (
                    head[1] == 7
                    and len(payload) >= 12
                    and struct.unpack_from(">I", payload)[0] == 18
                ):
                    subscriptions.append(payload[12:])
                if (
                    head[1] == 7
                    and len(payload) >= 12
                    and struct.unpack_from(">I", payload)[0] == 13
                ):
                    assert b"NAV_LEAVE_TOP_PAGE" in payload[12:]
                if head[1:3] == bytes([11, 1]):
                    break
            assert len(subscriptions) == 16
            assert all(f"PRESET_{i}".encode() in subscriptions[i] for i in range(7))
            os.write(master, frame(4, 0, 11, 2, 1))
            source.settimeout(2)
            request = b""
            while len(request) < 28:
                request += source.recv(28 - len(request))
            assert request == packet(6, struct.pack("<III", 4, 12, 12))
            idr = b"\0\0\0\1\x67sps\0\0\0\1\x68pps\0\0\0\1\x65idr"
            predicted = b"\0\0\0\1\x41next"
            # P before IDR and timestamp metadata must not become video.
            source.sendall(video(predicted) + video(struct.pack("<III", 0x1A2B3C4D, 1, 2)))
            stream = video(idr) + video(predicted)
            source.sendall(stream[:7])
            time.sleep(0.06)
            source.sendall(stream[7:19])
            time.sleep(0.06)
            source.sendall(stream[19:])
            received = []
            while len(received) < 2:
                head, data = read_frame(master)
                if head[1] == 11 and head[0] == 0x41:
                    received.append(data)
            assert received == [idr, predicted]
            source.settimeout(2)
            for preset, key in enumerate([106, 104, 100, 101, 102, 103]):
                press = ('{"buttonName":"PRESET_%d","buttonPressMode":"SHORT"}' % preset).encode()
                os.write(
                    master,
                    frame(4, 1, 7, 0, 1, struct.pack(">III", 0x20008003, 0, len(press)) + press),
                )
                command = b""
                while len(command) < 56:
                    command += source.recv(56 - len(command))
                assert command == packet(6, struct.pack("<III", 4, 12, key)) + packet(
                    6, struct.pack("<III", 4, 12, 105)
                )
            # Repeated CCU Home notifications must not toggle Show or emit HID.
            home = b'{"buttonName":"PRESET_6","buttonPressMode":"LONG"}'
            for _ in range(3):
                os.write(
                    master,
                    frame(4, 1, 7, 0, 1, struct.pack(">III", 0x20008003, 0, len(home)) + home),
                )
                source.settimeout(2)
                command = b""
                while len(command) < 28:
                    command += source.recv(28 - len(command))
                assert command == packet(6, struct.pack("<III", 4, 12, 12)), (
                    "Home may request an IDR, never HID"
                )
                source.sendall(video(idr))
                while True:
                    head, payload = read_frame(master)
                    if head[1] == 11 and (head[0] & 7) == 1:
                        assert payload == idr
                        break
            # Steering still works after an odd number of Home notifications.
            right = b'{"buttonName":"PRESET_3","buttonPressMode":"SHORT"}'
            os.write(
                master, frame(4, 1, 7, 0, 1, struct.pack(">III", 0x20008003, 0, len(right)) + right)
            )
            source.settimeout(2)
            command = b""
            while len(command) < 56:
                command += source.recv(56 - len(command))
            assert command == packet(6, struct.pack("<III", 4, 12, 101)) + packet(
                6, struct.pack("<III", 4, 12, 105)
            )
            # Event notifications must not duplicate an action emitted by OnButtonPress.
            event = b'{"buttonName":"PRESET_3","buttonEventMode":"BUTTONUP"}'
            os.write(
                master, frame(4, 1, 7, 0, 1, struct.pack(">III", 0x20008002, 0, len(event)) + event)
            )
            source.settimeout(0.1)
            try:
                assert not source.recv(40), "unexpected duplicate action"
            except socket.timeout:
                pass
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
                control.connect(path)
                request = b'{"buttonName":"OK"}'
                control.sendall(
                    packet(0xF1, struct.pack("<I", 0x59414D41))
                    + packet(0x59414D42, struct.pack("<I", 18) + request)
                )
                while True:
                    head, payload = read_frame(master)
                    if (
                        head[1] == 7
                        and len(payload) >= 12
                        and struct.unpack_from(">II", payload) == (18, 1001)
                    ):
                        assert payload[12:] == request
                        break
            os.write(master, frame(4, 0, 11, 4, 1))
            time.sleep(0.08)
            source.sendall(video(idr))
            assert process.wait(timeout=6) == 1
            after = log.read_text().split("VIDEO_SERVICE_ENDED", 1)[1]
            assert "TX    SDL v4 kind=1 service=11" not in after
            assert "LIVE_END frames=5" in after
            assert log.read_text().count("NAVIGATION_STATE") == 2
            assert after.count("requesting video service") == 1
            print(
                "OK: fragmented/coalesced IPC, metadata filtering, IDR gate, live H.264, six CarPlay button mappings/release, Home refresh without HID/page toggling, no duplicate event, SDL EndService"
            )
        finally:
            source.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
    os.close(master)
    os.close(slave)


if __name__ == "__main__":
    main()
