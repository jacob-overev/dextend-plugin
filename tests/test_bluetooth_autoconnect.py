# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Exercise authentication, framing, asynchronous signals and rejected calls."""

import os
import socket
import struct
import subprocess
import tempfile
import threading
from pathlib import Path


def exact(s, n):
    b = b""
    while len(b) < n:
        r = s.recv(n - len(b))
        assert r
        b += r
    return b


def request(s):
    h = exact(s, 16)
    body, serial, n = struct.unpack_from("<III", h, 4)
    return serial, exact(s, ((n + 7) // 8) * 8 + body)


def response(serial, kind=2):
    fields = b"\x05\x01u\0" + struct.pack("<I", serial)
    return struct.pack("<BBBBIII", 108, kind, 0, 1, 0, 20, len(fields)) + fields


for args, method in [
    ([], b"AutoConnect\0"),
    (["--listen"], b"Listen\0"),
    (["--forget", "02:00:00:00:00:01"], b"ForgetBluetoothAddr\0"),
    (["--connect", "02:00:00:00:00:01", "AAP"], b"Connect\0"),
]:
    for reject in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "bus")
            server = socket.socket(socket.AF_UNIX)
            server.bind(path)
            server.listen()
            errors = []

            def serve():
                try:
                    s, _ = server.accept()
                    with s:
                        line = b""
                        while not line.endswith(b"\r\n"):
                            line += exact(s, 1)
                        assert line.startswith(b"\0AUTH EXTERNAL ")
                        s.sendall(b"OK 1234\r\n")
                        assert exact(s, 7) == b"BEGIN\r\n"
                        serial, payload = request(s)
                        assert serial == 1 and b"Hello\0" in payload
                        s.sendall(response(1))
                        serial, payload = request(s)
                        assert (
                            serial == 2
                            and method in payload
                            and b"org.riddle.BluetoothControl\0" in payload
                        )
                        if args and args[0] == "--connect":
                            assert payload.endswith(struct.pack("<I", 3) + b"AAP\0")
                            assert b"02:00:00:00:00:01\0" in payload
                        if args and args[0] == "--forget":
                            assert payload.endswith(struct.pack("<I", 17) + b"02:00:00:00:00:01\0")
                            assert b"\x08\x01g\0\x01s\0" in payload
                        signal = struct.pack("<BBBBIII", 108, 4, 0, 1, 0, 21, 0)
                        data = signal + response(2, 3 if reject else 2)
                        for i in range(0, len(data), 3):
                            s.sendall(data[i : i + 3])
                except Exception as e:
                    errors.append(e)

            t = threading.Thread(target=serve)
            t.start()
            result = subprocess.run(
                [os.environ["YAMAHA_BT_CONTROL_CMD"]] + args,
                env=dict(os.environ, YAMAHA_DBUS_SOCKET=path),
                capture_output=True,
                timeout=6,
            )
            t.join(2)
            server.close()
            assert not t.is_alive() and not errors, errors
            assert result.returncode == (5 if reject else 0), result
            assert (b"accepted=1" in result.stdout) == (not reject)
print("OK: fragmented D-Bus replies and signals handled; rejected AutoConnect fails")
