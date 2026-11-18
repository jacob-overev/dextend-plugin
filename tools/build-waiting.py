#!/usr/bin/env python3
# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

"""Build the waiting frame and the inputs for adding live adapter details."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ARTWORK = ROOT / "src/assets/waiting.png"
FFMPEG = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory outside the repository")
    parser.add_argument("--version", default=(ROOT / "VERSION").read_text().strip())
    args = parser.parse_args()
    output = args.output.absolute()
    if (
        output.exists()
        or output.resolve().is_relative_to(ROOT)
        or any(p.is_symlink() for p in (output, *output.parents))
    ):
        parser.error("Use a new non-symlink directory outside the repository")
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,16}", args.version):
        parser.error("The waiting screen needs a version of at most 16 ASCII characters")
    font_file = Path(
        subprocess.check_output(
            ["fc-match", "DejaVu Sans Mono:style=Bold", "-f", "%{file}"], text=True
        )
    )
    if font_file.name != "DejaVuSansMono-Bold.ttf":
        parser.error("Expected installed DejaVu Sans Mono Bold")
    output.mkdir(parents=True, mode=0o700)
    glyphs = output / "waiting-font.bin"
    strip = output / "waiting-strip.bin"
    template = output / "template.h264"
    video = output / "waiting.h264"
    png = output / "waiting.png"

    font = ImageFont.truetype(str(font_file), 11)
    with glyphs.open("wb") as stream:
        for code in range(32, 127):
            glyph = Image.new("L", (7, 12))
            ImageDraw.Draw(glyph).text((0, -2), chr(code), font=font, fill=255)
            stream.write(glyph.tobytes())
    subprocess.run(
        FFMPEG
        + [
            "-i",
            str(ARTWORK),
            "-vf",
            "scale=640:360:flags=lanczos:in_range=full:out_range=tv,setsar=1",
            "-frames:v",
            "1",
            "-c:v",
            "libx264",
            "-threads",
            "4",
            "-profile:v",
            "baseline",
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-crf",
            "18",
            "-tune",
            "zerolatency",
            "-x264-params",
            "keyint=1:repeat-headers=1:aud=1:no-deblock=1:slice-max-mbs=10",
            "-f",
            "h264",
            str(template),
        ],
        check=True,
    )
    subprocess.run(
        FFMPEG
        + [
            "-i",
            str(template),
            "-vf",
            "crop=160:96:480:240",
            "-frames:v",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "rawvideo",
            str(strip),
        ],
        check=True,
    )
    renderer = output / "render-host"
    subprocess.run(
        [
            os.environ.get("CC", "cc"),
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "src/native/waiting-frame.c"),
            "-o",
            str(renderer),
        ],
        check=True,
    )
    with video.open("wb") as stream:
        subprocess.run(
            [renderer, template, strip, glyphs, "-", "-", args.version], stdout=stream, check=True
        )

    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(video)]
        )
    )
    (stream,) = probe["streams"]
    if not (
        stream["codec_name"] == "h264"
        and stream["width"] == 640
        and stream["height"] == 360
        and stream["nb_read_frames"] == "1"
        and 0 < video.stat().st_size <= 131072
    ):
        raise ValueError("Unexpected waiting-frame format")
    subprocess.run(
        FFMPEG + ["-xerror", "-i", str(video), "-frames:v", "1", "-update", "1", str(png)],
        check=True,
    )
    # The Yamaha decoder on this OEM profile needs a fully encoded frame.
    # Keep unknown PCB revisions blank and render the reported OEM version.
    firmware = "2025.10.15.1127"
    rendered = output / f"waiting-{firmware}-rendered.h264"
    compact = output / f"waiting-{firmware}.h264"
    with rendered.open("wb") as target:
        subprocess.run(
            [renderer, template, strip, glyphs, "-", firmware, args.version],
            stdout=target,
            check=True,
        )
    subprocess.run(
        FFMPEG
        + [
            "-xerror",
            "-i",
            str(rendered),
            "-frames:v",
            "1",
            "-c:v",
            "libx264",
            "-threads",
            "4",
            "-profile:v",
            "baseline",
            "-level:v",
            "2.2",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "15",
            "-crf",
            "18",
            "-tune",
            "zerolatency",
            "-x264-params",
            "keyint=1:repeat-headers=1:aud=1",
            "-f",
            "h264",
            str(compact),
        ],
        check=True,
    )
    subprocess.run(
        FFMPEG + ["-xerror", "-i", str(compact), "-frames:v", "1", "-f", "null", "-"], check=True
    )
    (output / "waiting-version").write_text(args.version + "\n")
    result = {
        "version": args.version,
        "artwork_sha256": digest(ARTWORK),
        "waiting_sha256": digest(video),
        "waiting_bytes": video.stat().st_size,
        "font": font_file.name,
        "font_sha256": digest(font_file),
    }
    (output / "provenance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
