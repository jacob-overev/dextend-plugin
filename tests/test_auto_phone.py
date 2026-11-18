# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Switch phone families without restarting CCU or replaying stale input."""

import os
from pathlib import Path
import socket
import struct
import tempfile
from test_recovery import Rig, wait_for
from test_live import packet


def exact(s, n):
    data = b""
    while len(data) < n:
        chunk = s.recv(n - len(data))
        assert chunk
        data += chunk
    return data


def command(s, outer, key):
    for _ in range(10):
        h = exact(s, 16)
        _, n, kind, _ = struct.unpack("<4I", h)
        b = exact(s, n)
        if b == struct.pack("<3I", 4, 12, 12):
            continue
        assert kind == outer and b == struct.pack("<3I", 4, 12, key), (kind, b)
        return
    raise AssertionError("no input command")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    rig = Rig(tmp, markers=True, YAMAHA_PHONE_AUTO="1")
    try:

        def select(value, ack):
            p = root / "phone-selection.new"
            p.write_text(value)
            p.replace(root / "phone-selection")
            wait_for(
                lambda: (
                    (root / "phone-selected").exists()
                    and (root / "phone-selected").read_text() == ack + "\n"
                )
            )

        select("carplay\n", "carplay")
        cp = rig.phone()
        rig.ccu()
        (root / "ccu-recover").unlink(missing_ok=True)
        rig.start()
        pid = rig.process.pid
        # Switch to USB AA without changing the CCU session/process.
        select("aa-usb\n", "aa-usb")
        cp.close()
        aa = socket.socket(socket.AF_UNIX)
        aa.settimeout(4)
        aa.connect(str(rig.path))
        reg = packet(0xF1, struct.pack("<I", 5))
        aa.sendall(reg[:12] + bytes(4) + reg[16:])
        response = exact(aa, 60)
        assert struct.unpack_from("<4I", response, 24) == (1, 624, 352, 30)
        rig.rpc(32771, {"buttonName": "PRESET_4", "buttonPressMode": "SHORT"})
        command(aa, 9, 102)
        select("carplay\n", "carplay")
        aa.close()
        phase = "CARPLAY_PHASE phase=3"
        previous_ready = rig.text().count(phase)
        cp = rig.phone()
        wait_for(lambda: rig.text().count(phase) > previous_ready)
        rig.rpc(32771, {"buttonName": "PRESET_4", "buttonPressMode": "SHORT"})
        command(cp, 6, 102)
        command(cp, 6, 105)
        # Invalid selections do not cancel the working family or invoke code.
        (root / "phone-selection").write_text("aa-wireless\n$(reboot)\n")
        import time

        time.sleep(0.35)
        assert (root / "phone-selected").read_text() == "carplay\n"
        rig.rpc(32771, {"buttonName": "PRESET_1", "buttonPressMode": "SHORT"})
        command(cp, 6, 104)
        command(cp, 6, 105)
        assert rig.process.pid == pid and rig.process.poll() is None
        cp.close()
    finally:
        rig.close()
print("OK: CP -> AA -> CP keeps CCU session, isolates input and rejects invalid selection")
