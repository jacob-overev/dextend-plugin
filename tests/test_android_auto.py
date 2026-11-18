# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""AA startup dialects and byte-preserving SPS crop, without hardware."""

import os
import select
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path

from test_recovery import Rig, wait_for
from test_probe import frame
from test_live import packet


def read_exact(sock, size):
    data = b""
    while len(data) < size:
        part = sock.recv(size - len(data))
        assert part
        data += part
    return data


ENCODED_AA = subprocess.check_output(
    [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=624x352:r=30,pad=800:480:88:64",
        "-frames:v",
        "3",
        "-c:v",
        "libx264",
        "-profile:v",
        "baseline",
        "-level",
        "3.1",
        "-f",
        "h264",
        "-",
    ]
)

for mode, reserved in [("usb", False), ("wireless", True)]:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(YAMAHA_AA_MODE=mode, YAMAHA_AA_PEER="02:00:00:00:00:01")
        rfcomm = Path(tmp) / "rfcomm-ready"
        os.environ["YAMAHA_AA_RFCOMM_PATH"] = str(rfcomm)
        view = (656, 368) if reserved else (624, 352)
        if reserved:
            (Path(tmp) / "aa-video-session").write_text("[656,368,84,72,58,56]")
        rig = Rig(tmp, markers=reserved)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                peer.settimeout(4)
                peer.connect(str(rig.path))
                registration = packet(0xF1, struct.pack("<I", 5))
                if reserved:
                    registration = registration[:12] + bytes(4) + registration[16:]
                peer.sendall(registration[:7])
                peer.sendall(registration[7:])
                if mode == "wireless":
                    peer.settimeout(0.3)
                    try:
                        assert not peer.recv(1), "LinkParam sent before RFCOMM readiness"
                        raise AssertionError("AA socket closed while waiting")
                    except socket.timeout:
                        pass
                    rfcomm.touch()
                    peer.settimeout(4)
                response = read_exact(peer, 60)
                assert response[40:] == (b"02:00:00:00:00:01" + bytes(3) if reserved else bytes(20))
                assert struct.unpack("<15I", response)[:10] == (
                    0x55AA55AA,
                    44,
                    9,
                    0 if reserved else 0xFFFFFFF6,
                    36,
                    200,
                    1 if mode == "usb" else 2,
                    *view,
                    30,
                )
                rig.ccu()
                (Path(tmp) / "ccu-recover").unlink(missing_ok=True)
                rig.start()

                def press(preset, key):
                    rig.rpc(32771, {"buttonName": f"PRESET_{preset}", "buttonPressMode": "SHORT"})
                    while True:
                        header = read_exact(peer, 16)
                        magic, size, command, check = struct.unpack("<4I", header)
                        body = read_exact(peer, size)
                        assert magic == 0x55AA55AA and command == 9
                        assert check == (0 if reserved else 0xFFFFFFF6)
                        if key != 12 and body == struct.pack("<3I", 4, 12, 12):
                            continue  # Independent video refresh.
                        assert body == struct.pack("<3I", 4, 12, key)
                        break

                for preset, key in enumerate((106, 104, 100, 101, 102, 103)):
                    press(preset, key)
                press(0, 106)
                press(0, 200)  # Explicit double Back -> AA Home.
                press(0, 106)  # A completed pair does not latch Home.
                time.sleep(0.65)
                press(0, 106)  # Separate Back actions stay Back.
                press(3, 101)
                press(0, 106)  # Another button cancels the gesture.

                def control(value):
                    peer.sendall(packet(9, struct.pack("<3I", 4, 12, value)))

                def picture(data):
                    peer.sendall(packet(9, struct.pack("<II", len(data), 1) + data))

                def quiet():
                    peer.settimeout(0.15)
                    try:
                        assert not peer.recv(1), "Unexpected automatic input/focus request"
                    except socket.timeout:
                        pass
                    finally:
                        peer.settimeout(4)

                control(3)  # Phone yields video focus, not an IPC disconnection.
                wait_for(lambda: "AA_VIDEO_BACKGROUND control=3" in rig.log.read_text())
                picture(ENCODED_AA)  # A queued old IDR cannot undo the exit.
                quiet()  # No automatic reclaim while the user stays idle.
                press(1, 12)  # Select resumes instead of activating an invisible item.
                control(501)  # A late stop must not cancel an explicit resume.
                rig.rpc(32771, {"buttonName": "PRESET_1", "buttonPressMode": "SHORT"})
                quiet()  # Do not flood focus requests or replay blind selections.
                control(500)
                picture(ENCODED_AA)
                wait_for(lambda: "AA_VIDEO_ACTIVE fresh_idr=1" in rig.log.read_text())
                press(1, 104)  # Normal navigation only after a new resume IDR.
                control(501)  # A standalone video-stop also suspends controls.
                wait_for(lambda: "AA_VIDEO_BACKGROUND control=501" in rig.log.read_text())
                press(3, 12)
                picture(ENCODED_AA)
                wait_for(lambda: rig.log.read_text().count("AA_VIDEO_ACTIVE fresh_idr=1") == 2)
                press(3, 101)
                peer.settimeout(0.2)
                try:
                    extra = peer.recv(28)
                    assert not extra or extra[24:] != struct.pack("<I", 105), (
                        "CarPlay release leaked to AA"
                    )
                except socket.timeout:
                    pass
        finally:
            rig.close()
os.environ.pop("YAMAHA_AA_MODE")
os.environ.pop("YAMAHA_AA_PEER")
os.environ.pop("YAMAHA_AA_RFCOMM_PATH")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = Path(__file__).resolve().parents[1] / "src/native"
    fixture = root / "crop.c"
    fixture.write_text("""
#include <stdio.h>
#include <string.h>
#include "aa-sps.h"
int main(int argc, char **argv) {
    struct aa_geometry geometry = AA_YAMAHA_GEOMETRY;
    if (argc == 2 && aa_parse_geometry(argv[1], &geometry)) return 2;
    unsigned char input[512],output[816];
    size_t n=fread(input,1,sizeof(input),stdin);
    int m=aa_crop_sps(input,n,output,&geometry);
    return m>0 && fwrite(output,1,(size_t)m,stdout)==(size_t)m ? 0:2;
}
""")
    subprocess.run(["cc", "-I", str(source), str(fixture), "-o", str(root / "crop")], check=True)
    cmd = ["ffmpeg", "-v", "error"]
    encoded = ENCODED_AA
    import re

    def rewrite_sps(stream, *args):
        result = bytearray()
        for nal in re.split(rb"\x00\x00(?:\x00)?\x01", stream)[1:]:
            if nal[0] & 31 == 7:
                nal = subprocess.check_output([root / "crop", *args], input=nal)
                # Reapplying a crop to an already modified SPS is rejected.
                if args != ("[800,480,0,0,0,0]",):
                    assert subprocess.run([root / "crop"], input=nal,
                                          capture_output=True).returncode != 0
            result.extend(b"\x00\x00\x00\x01" + nal)
        return result

    def decode(data, crop=None):
        return subprocess.check_output(
            cmd
            + ["-flags", "+unaligned", "-f", "h264", "-i", "-"]
            + (["-vf", f"crop={crop}"] if crop else [])
            + ["-pix_fmt", "yuv420p", "-f", "rawvideo", "-"],
            input=data,
        )

    expected = decode(encoded, "680:408:44:32")
    assert len(expected) == 3 * 680 * 408 * 3 // 2
    assert decode(rewrite_sps(encoded)) == expected

    for geometry, crop in [
        ("[640,360,80,80,60,60]", "640:360:80:60"),
        ("[640,360,82,78,62,58]", "640:360:82:62"),
        ("[800,480,0,0,0,0]", "800:480:0:0"),
    ]:
        assert decode(rewrite_sps(encoded, geometry)) == decode(encoded, crop)

    # SPS metadata must not change the pixels for different encoder profiles.
    # Several GOPs also exercise repeated SPS updates inside a session.
    for profile in ("baseline", "main", "high"):
        for fps in (15, 30):
            source_video = subprocess.check_output(cmd + [
                "-f", "lavfi", "-i", f"testsrc2=s=624x352:r={fps},pad=800:480:88:64",
                "-frames:v", "12", "-c:v", "libx264", "-threads", "1",
                "-profile:v", profile, "-level", "3.1", "-g", "5", "-f", "h264", "-",
            ])
            assert decode(rewrite_sps(source_video)) == decode(source_video, "680:408:44:32"), (profile, fps)
print("OK: AA USB/wireless LinkParam and pixel-exact native SPS crop")

# Diagnostic clips must retain P frames after a blank startup IDR, then stop.
# Capture is before CCU forwarding, so it also works while the display is idle.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    snapshot = root / "source.h264"
    os.environ.update(YAMAHA_AA_MODE="usb", YAMAHA_SOURCE_SNAPSHOT=str(snapshot))
    rig = Rig(tmp, markers=True)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(4)
            peer.connect(str(rig.path))
            peer.sendall(packet(0xF1, struct.pack("<I", 5)))
            read_exact(peer, 60)
            (root / "capture-source").touch()
            (root / "capture-sequence").touch()

            def send_video(data):
                peer.sendall(packet(9, struct.pack("<II", len(data), 1) + data))

            send_video(encoded)
            wait_for(lambda: snapshot.exists() and snapshot.stat().st_size > 0)
            initial = snapshot.read_bytes()
            predicted = b"\0\0\0\1\x41predicted"
            for _ in range(100):
                send_video(predicted)
            wait_for(lambda: "SOURCE_SEQUENCE stopped" in rig.log.read_text())
            assert snapshot.read_bytes() == initial + predicted * 89
            assert not (root / "capture-source").exists()
            assert not (root / "capture-sequence").exists()
    finally:
        rig.close()
        os.environ.pop("YAMAHA_AA_MODE")
        os.environ.pop("YAMAHA_SOURCE_SNAPSHOT")
print("OK: bounded AA diagnostic clip retains predictive frames and stops")

# Four frames may be on the wire. A short ACK delay must preserve the next
# predictive frame without asking the Android receiver to change video focus.
with tempfile.TemporaryDirectory() as tmp:
    rig = Rig(tmp, YAMAHA_AA_MODE="usb", YAMAHA_VIDEO_ACK_GUARD="1")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(4)
            peer.connect(str(rig.path))
            peer.sendall(packet(0xF1, struct.pack("<I", 5)))
            read_exact(peer, 60)

            def send_picture(data):
                peer.sendall(packet(9, struct.pack("<II", len(data), 1) + data))

            send_picture(ENCODED_AA)
            rig.ccu()
            rig.start()
            read_exact(peer, 28)  # The active CCU has requested an initial IDR.
            send_picture(ENCODED_AA)
            rig.until(lambda h, p: h[1] == 11 and (h[0] & 7) == 1 and b"\x00\x00\x00\x01\x67" in p)
            for number in range(4):
                data = b"\x00\x00\x00\x01\x41predicted" + bytes([number])
                send_picture(data)
                if number < 3:
                    rig.assert_video(data)
            assert not select.select([rig.master], [], [], 0.12)[0], "fifth frame escaped ACK window"
            os.write(rig.master, frame(4, 0, 11, 254, 1))
            rig.assert_video(data)
            assert "VIDEO_GUARD_PAUSED" not in rig.text()
    finally:
        rig.close()
print("OK: AA buffers a fifth frame and delivers it after one ACK")
