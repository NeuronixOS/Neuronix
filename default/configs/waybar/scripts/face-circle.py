#!/usr/bin/env python3
"""Clip the waybar launcher face into a circle with a theme-colored ring."""
from __future__ import annotations

import math
import os
import re
import sys
import tempfile
from pathlib import Path

import cairo
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

PX = 128
RING = 6.0
# Trim the gray photo-frame around face.jpg before the circular crop.
INSET = 0.06

FACE_CANDIDATES = (
    Path.home() / "configs" / "user-icon" / "face.jpg",
    Path.home() / ".config" / "user-icon" / "face.jpg",
    Path.home() / ".face",
)


def _hex_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    raw = value.strip().lstrip("#")
    if len(raw) >= 6 and all(c in "0123456789abcdefABCDEF" for c in raw[:6]):
        r = int(raw[0:2], 16) / 255.0
        g = int(raw[2:4], 16) / 255.0
        b = int(raw[4:6], 16) / 255.0
        return r, g, b, alpha
    return 0.92, 0.86, 0.70, alpha


def _ring_color() -> str:
    css = Path.home() / ".config" / "waybar" / "style.css"
    if css.is_file():
        text = css.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"@define-color\s+wb_fg\s+([^;]+);", text)
        if m:
            return m.group(1).strip()
    return "#ebdbb2"


def _face_src() -> Path:
    for path in FACE_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError("face.jpg not found")


def _runtime_dir() -> Path:
    path = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "waybar-rings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _draw(src: Path, dest: Path, ring_hex: str) -> None:
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(src))
    w, h = pixbuf.get_width(), pixbuf.get_height()
    pad = int(min(w, h) * INSET)
    side = min(w, h) - 2 * pad
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    cropped = pixbuf.new_subpixbuf(x0, y0, side, side)
    scaled = cropped.scale_simple(PX, PX, GdkPixbuf.InterpType.BILINEAR)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    scaled.savev(tmp_path, "png", [], [])
    photo = cairo.ImageSurface.create_from_png(tmp_path)
    Path(tmp_path).unlink(missing_ok=True)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, PX, PX)
    cr = cairo.Context(surface)
    cr.set_antialias(cairo.ANTIALIAS_BEST)

    cx = cy = PX / 2.0
    radius = PX / 2.0 - RING / 2.0 - 0.5

    cr.save()
    cr.arc(cx, cy, radius - RING / 2.0, 0, 2 * math.pi)
    cr.clip()
    cr.set_source_surface(photo, 0, 0)
    cr.paint()
    cr.restore()

    cr.arc(cx, cy, radius, 0, 2 * math.pi)
    cr.set_line_width(RING)
    cr.set_source_rgba(*_hex_rgba(ring_hex, 0.95))
    cr.stroke()

    tmp_out = dest.with_suffix(".tmp.png")
    surface.write_to_png(str(tmp_out))
    tmp_out.replace(dest)


def main() -> int:
    try:
        src = _face_src()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    dest = _runtime_dir() / "face-circle.png"
    stamp = dest.with_suffix(".stamp")
    ring = _ring_color()
    token = f"{src}\n{src.stat().st_mtime_ns}\n{ring}\n{PX}\n"
    if dest.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == token:
        sys.stdout.write(f"{dest}\nApplications\n")
        return 0
    _draw(src, dest, ring)
    stamp.write_text(token, encoding="utf-8")
    sys.stdout.write(f"{dest}\nApplications\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
