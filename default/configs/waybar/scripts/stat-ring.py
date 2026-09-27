#!/usr/bin/env python3
"""Waybar image-module helper: circular progress ring around a centered icon."""
from __future__ import annotations

import math
import os
import re
import subprocess
import sys
from pathlib import Path

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

PX = 64
RING_WIDTH = 5.0


def _hex_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    raw = value.strip().lstrip("#")
    if len(raw) >= 6 and all(c in "0123456789abcdefABCDEF" for c in raw[:6]):
        r = int(raw[0:2], 16) / 255.0
        g = int(raw[2:4], 16) / 255.0
        b = int(raw[4:6], 16) / 255.0
        return r, g, b, alpha
    return 0.92, 0.86, 0.70, alpha


def _waybar_colors() -> tuple[str, str]:
    fg, dim = "#ebdbb2", "#aea387"
    css = Path.home() / ".config" / "waybar" / "style.css"
    if not css.is_file():
        return fg, dim
    text = css.read_text(encoding="utf-8", errors="replace")

    def grab(name: str, default: str) -> str:
        m = re.search(rf"@define-color\s+{re.escape(name)}\s+([^;]+);", text)
        return m.group(1).strip() if m else default

    return grab("wb_fg", fg), grab("wb_dim", dim)


def _runtime_dir() -> Path:
    path = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "waybar-rings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cpu_percent(state: Path) -> float:
    line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    parts = [int(x) for x in line.split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    total = sum(parts)
    prev_idle = prev_total = None
    if state.is_file():
        try:
            a, b = state.read_text(encoding="utf-8").split()
            prev_idle, prev_total = int(a), int(b)
        except ValueError:
            prev_idle = prev_total = None
    state.write_text(f"{idle} {total}\n", encoding="utf-8")
    if prev_idle is None or prev_total is None:
        return 0.0
    d_idle = idle - prev_idle
    d_total = total - prev_total
    if d_total <= 0:
        return 0.0
    return max(0.0, min(100.0, (1.0 - d_idle / d_total) * 100.0))


def _mem_percent() -> tuple[float, str]:
    info: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        bits = line.split()
        if len(bits) >= 2:
            info[bits[0].rstrip(":")] = int(bits[1])
    total = info.get("MemTotal") or 1
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - avail)
    pct = used / total * 100.0
    used_g = used / (1024 * 1024)
    total_g = total / (1024 * 1024)
    return pct, f"Memory {used_g:.1f}G / {total_g:.1f}G ({pct:.0f}%)"


def _volume() -> tuple[float, bool, str]:
    try:
        out = subprocess.check_output(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            text=True,
            timeout=1,
            stderr=subprocess.DEVNULL,
        )
        muted = "MUTED" in out.upper()
        m = re.search(r"([0-9]*\.?[0-9]+)", out)
        pct = float(m.group(1)) * 100.0 if m else 0.0
        return pct, muted, f"Volume {pct:.0f}%" + (" (muted)" if muted else "")
    except Exception:
        pass
    try:
        mute_out = subprocess.check_output(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
            text=True,
            timeout=1,
            stderr=subprocess.DEVNULL,
        )
        muted = "yes" in mute_out.lower()
        vol_out = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            text=True,
            timeout=1,
            stderr=subprocess.DEVNULL,
        )
        m = re.search(r"(\d+)%", vol_out)
        pct = float(m.group(1)) if m else 0.0
        return pct, muted, f"Volume {pct:.0f}%" + (" (muted)" if muted else "")
    except Exception:
        return 0.0, True, "Volume unavailable"


def _draw_ring(path: Path, percent: float, icon: str, fg: str, dim: str, muted: bool = False) -> None:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, PX, PX)
    cr = cairo.Context(surface)
    cr.set_antialias(cairo.ANTIALIAS_BEST)

    cx = cy = PX / 2.0
    radius = PX / 2.0 - RING_WIDTH - 1.0
    track = _hex_rgba(dim, 0.35 if not muted else 0.22)
    fill = _hex_rgba(dim if muted else fg, 0.95)
    glyph = _hex_rgba(dim if muted else fg, 0.95)

    cr.set_line_width(RING_WIDTH)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_source_rgba(*track)
    cr.arc(cx, cy, radius, 0, 2 * math.pi)
    cr.stroke()

    frac = max(0.0, min(1.0, percent / 100.0))
    if frac > 0.002:
        cr.set_source_rgba(*fill)
        start = -math.pi / 2.0
        cr.arc(cx, cy, radius, start, start + 2 * math.pi * frac)
        cr.stroke()

    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription("FontAwesome, Symbols Nerd Font 18"))
    layout.set_text(icon, -1)
    _ink, logical = layout.get_pixel_extents()
    cr.set_source_rgba(*glyph)
    cr.move_to(cx - logical.width / 2.0, cy - logical.height / 2.0)
    PangoCairo.show_layout(cr, layout)

    tmp = path.with_suffix(".tmp.png")
    surface.write_to_png(str(tmp))
    tmp.replace(path)


def main(argv: list[str]) -> int:
    kind = (argv[1] if len(argv) > 1 else "").strip().lower()
    if kind not in {"cpu", "memory", "volume"}:
        print("usage: stat-ring.py cpu|memory|volume", file=sys.stderr)
        return 2

    fg, dim = _waybar_colors()
    out_dir = _runtime_dir()
    png = out_dir / f"{kind}.png"

    if kind == "cpu":
        pct = _cpu_percent(out_dir / "cpu.state")
        tooltip = f"CPU {pct:.0f}%"
        icon = "\uf2db"
        muted = False
    elif kind == "memory":
        pct, tooltip = _mem_percent()
        icon = "\uf1c0"
        muted = False
    else:
        pct, muted, tooltip = _volume()
        if muted or pct <= 0.5:
            icon = "\uf026"
        elif pct < 40:
            icon = "\uf027"
        else:
            icon = "\uf028"

    _draw_ring(png, 0.0 if muted else pct, icon, fg, dim, muted=muted)
    sys.stdout.write(f"{png}\n{tooltip}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
