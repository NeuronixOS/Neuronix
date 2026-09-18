#!/usr/bin/env python3
"""
Fullscreen screensaver for Wayland / X11 (GTK4).

Covers every connected monitor with a quiet animated scene.
A keypress exits; mouse motion and clicks are ignored (Active-User /
ydotoold jiggles the pointer and would otherwise dismiss immediately).

Usage:
  ./screensaver.py
  ./screensaver.py --mode clock|stars|aurora|matrix
  ./screensaver.py --delay 5          # wait N seconds before blanking
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import time
from dataclasses import dataclass

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

# DrawingArea passes a cairo.Context into draw_func — needs python3-gi-cairo.
try:
    gi.require_foreign("cairo")
except (ImportError, ValueError) as exc:
    print(
        "screensaver: missing cairo GI support (apt install python3-gi-cairo)\n"
        f"  ({exc})",
        file=sys.stderr,
    )
    sys.exit(1)

from gi.repository import Gdk, GLib, Gtk

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell

    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

APP_ID = "org.neuronix.Screensaver"
FPS = 30
LAYER_NS = "neuronix-screensaver"


def using_layer_shell() -> bool:
    return bool(HAS_LAYER_SHELL and LayerShell.is_supported())


def hypr_raise_screensaver() -> bool:
    """HDMI floats stay above a normal fullscreen window; restack the saver."""
    try:
        clients = json.loads(
            subprocess.check_output(["hyprctl", "-j", "clients"], text=True, timeout=2)
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ):
        return True
    batch: list[str] = []
    for win in clients:
        cls = str(win.get("class") or "")
        title = str(win.get("title") or "")
        if cls != APP_ID and "screensaver" not in cls.lower() and title != "Screensaver":
            continue
        addr = win.get("address")
        if not addr:
            continue
        target = str(addr) if str(addr).startswith("address:") else f"address:{addr}"
        batch.append(f"dispatch alterzorder top,{target}")
    if batch:
        try:
            subprocess.run(
                ["hyprctl", "--batch", "; ".join(batch)],
                timeout=2,
                check=False,
                capture_output=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return True


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------


@dataclass
class Star:
    x: float
    y: float
    z: float
    speed: float
    bright: float


@dataclass
class Drop:
    x: float
    y: float
    speed: float
    length: int
    glyph: str


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class Scene:
    """Animated drawing surface for one monitor."""

    def __init__(self, mode: str, width: int, height: int):
        self.mode = mode
        self.width = max(width, 1)
        self.height = max(height, 1)
        self.t0 = time.monotonic()
        self.stars: list[Star] = []
        self.drops: list[Drop] = []
        self._seed()

    def resize(self, width: int, height: int) -> None:
        self.width = max(width, 1)
        self.height = max(height, 1)
        self._seed()

    def _seed(self) -> None:
        # Warp field (stars mode) — denser + faster
        n_warp = max(160, (self.width * self.height) // 9000)
        self.stars = [
            Star(
                x=random.uniform(-1, 1),
                y=random.uniform(-1, 1),
                z=random.uniform(0.12, 1.0),
                speed=random.uniform(0.22, 0.75),
                bright=random.uniform(0.4, 1.0),
            )
            for _ in range(n_warp)
        ]
        # Static twinkles (clock mode)
        n_twinkle = max(40, (self.width * self.height) // 40000)
        self.twinkles = [
            (
                random.uniform(0, 1),
                random.uniform(0, 1),
                random.uniform(0.5, 2.2),
                random.uniform(0, math.tau),
                random.uniform(0.4, 1.2),
            )
            for _ in range(n_twinkle)
        ]
        # Matrix rain — dense columns
        cols = max(24, self.width // 18)
        glyphs = "01アイウエオカキクケコサシスセソタチツテトナニヌネノﾊﾋﾌﾍﾎ"
        self.drops = [
            Drop(
                x=i * (self.width / cols) + random.uniform(0, 4),
                y=random.uniform(-self.height, self.height),
                speed=random.uniform(120, 340),
                length=random.randint(12, 36),
                glyph=random.choice(glyphs),
            )
            for i in range(cols)
        ]

    def tick(self, dt: float) -> None:
        if self.mode == "stars":
            for s in self.stars:
                s.z -= s.speed * dt
                if s.z <= 0.05:
                    s.x = random.uniform(-1, 1)
                    s.y = random.uniform(-1, 1)
                    s.z = 1.0
                    s.bright = random.uniform(0.4, 1.0)
                    s.speed = random.uniform(0.22, 0.75)
        elif self.mode == "matrix":
            for d in self.drops:
                d.y += d.speed * dt
                if d.y - d.length * 16 > self.height:
                    d.y = random.uniform(-self.height * 0.5, 0)
                    d.speed = random.uniform(120, 340)
                    d.length = random.randint(12, 36)

    def draw(self, cr, width: int, height: int) -> None:
        self.width = max(width, 1)
        self.height = max(height, 1)
        t = time.monotonic() - self.t0

        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()

        if self.mode == "clock":
            self._draw_twinkles(cr, t)
            self._draw_clock(cr, t)
        elif self.mode == "stars":
            self._draw_warp(cr, t)
        elif self.mode == "aurora":
            self._draw_aurora(cr, t)
        elif self.mode == "matrix":
            self._draw_matrix(cr, t)
        else:
            self._draw_clock(cr, t)

        self._draw_hint(cr)

    def _draw_twinkles(self, cr, t: float) -> None:
        """Sparse blinking dots behind the clock — not a starfield."""
        for x_n, y_n, size, phase, rate in self.twinkles:
            pulse = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * rate + phase))
            cr.set_source_rgba(1.0, 1.0, 1.0, pulse * 0.55)
            cr.arc(x_n * self.width, y_n * self.height, size, 0, math.tau)
            cr.fill()

    def _draw_warp(self, cr, _t: float) -> None:
        """Hyperspace starfield — streaks flying toward the viewer."""
        cx, cy = self.width / 2, self.height / 2
        for s in self.stars:
            px = cx + (s.x / s.z) * (self.width * 0.6)
            py = cy + (s.y / s.z) * (self.height * 0.6)
            if px < -40 or py < -40 or px > self.width + 40 or py > self.height + 40:
                continue
            # Trail from previous z toward camera
            z2 = min(1.0, s.z + 0.08)
            px2 = cx + (s.x / z2) * (self.width * 0.6)
            py2 = cy + (s.y / z2) * (self.height * 0.6)
            a = _clamp(s.bright * (1.2 - s.z))
            cr.set_source_rgba(1.0, 1.0, 1.0, a)
            cr.set_line_width(max(1.0, (1.0 - s.z) * 2.8))
            cr.move_to(px2, py2)
            cr.line_to(px, py)
            cr.stroke()
            cr.arc(px, py, max(0.8, (1.0 - s.z) * 2.5), 0, math.tau)
            cr.fill()

    def _draw_aurora(self, cr, t: float) -> None:
        """Full-screen rolling greyscale ribbons — no clock, no starfield."""
        # Soft mid-grey wash so it never looks like a black clock face
        pat = cairo_radial(
            self.width * 0.5,
            self.height * 0.55,
            0,
            max(self.width, self.height) * 0.7,
        )
        pat.add_color_stop_rgba(0.0, 0.22, 0.22, 0.22, 0.9)
        pat.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 1.0)
        cr.set_source(pat)
        cr.paint()

        bands = (
            (0.85, 0.55, 0.18, 0.22),
            (0.65, 0.38, 0.32, 0.18),
            (0.95, 0.48, 0.48, 0.14),
            (0.45, 0.62, 0.62, 0.12),
            (0.75, 0.72, 0.28, 0.10),
        )
        for bi, (grey, y_frac, amp_frac, a) in enumerate(bands):
            cr.save()
            cr.new_path()
            y0 = self.height * y_frac
            amp = self.height * amp_frac
            cr.move_to(0, self.height)
            cr.line_to(0, y0)
            steps = 64
            for i in range(steps + 1):
                x = self.width * (i / steps)
                wave = (
                    math.sin(t * 0.45 + i * 0.14 + bi * 1.3) * amp
                    + math.sin(t * 0.22 + i * 0.05 + bi) * amp * 0.45
                )
                cr.line_to(x, y0 + wave)
            cr.line_to(self.width, self.height)
            cr.close_path()
            pat = cairo_linear(0, y0 - amp, 0, self.height)
            pat.add_color_stop_rgba(0.0, grey, grey, grey, a)
            pat.add_color_stop_rgba(0.55, grey * 0.4, grey * 0.4, grey * 0.4, a * 0.4)
            pat.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.0)
            cr.set_source(pat)
            cr.fill()
            cr.restore()

        # Bright crest lines so motion reads clearly
        for bi in range(3):
            cr.set_line_width(1.5)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.18 - bi * 0.04)
            cr.new_path()
            y0 = self.height * (0.28 + bi * 0.14)
            amp = self.height * 0.08
            for i in range(65):
                x = self.width * (i / 64)
                y = y0 + math.sin(t * 0.5 + i * 0.12 + bi) * amp
                if i == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.stroke()

    def _draw_matrix(self, cr, _t: float) -> None:
        """Dense falling code — greyscale only."""
        cr.select_font_face("DejaVu Sans Mono", 0, 0)
        font_size = max(14, min(22, self.width // 90))
        cr.set_font_size(font_size)
        step = font_size + 2
        for d in self.drops:
            for i in range(d.length):
                yy = d.y - i * step
                if yy < -step or yy > self.height + step:
                    continue
                fade = 1.0 - (i / max(1, d.length))
                if i == 0:
                    cr.set_source_rgba(1.0, 1.0, 1.0, 0.98)
                elif i < 3:
                    cr.set_source_rgba(0.85, 0.85, 0.85, fade)
                else:
                    g = 0.35 + 0.35 * fade
                    cr.set_source_rgba(g, g, g, fade * 0.8)
                cr.move_to(d.x, yy)
                cr.show_text(d.glyph)

    def _draw_clock(self, cr, t: float) -> None:
        now = time.localtime()
        clock = time.strftime("%I:%M", now)
        date = time.strftime("%A · %B %-d", now)

        breath = 0.82 + 0.12 * math.sin(t * 0.6)

        cr.select_font_face("Serif", 0, 0)
        cr.set_font_size(min(self.width, self.height) * 0.14)
        te = cr.text_extents(clock)
        x = (self.width - te.width) / 2 - te.x_bearing
        y = self.height * 0.48
        cr.set_source_rgba(1.0, 1.0, 1.0, breath)
        cr.move_to(x, y)
        cr.show_text(clock)

        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(min(self.width, self.height) * 0.028)
        te2 = cr.text_extents(date)
        x2 = (self.width - te2.width) / 2 - te2.x_bearing
        cr.set_source_rgba(0.72, 0.72, 0.72, breath * 0.85)
        cr.move_to(x2, y + te.height * 0.55)
        cr.show_text(date)

    def _draw_hint(self, cr) -> None:
        msg = "press any key to exit"
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(13)
        te = cr.text_extents(msg)
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.move_to((self.width - te.width) / 2 - te.x_bearing, self.height - 28)
        cr.show_text(msg)


def cairo_radial(cx, cy, r0, r1):
    import cairo

    return cairo.RadialGradient(cx, cy, r0, cx, cy, r1)


def cairo_linear(x0, y0, x1, y1):
    import cairo

    return cairo.LinearGradient(x0, y0, x1, y1)


# ---------------------------------------------------------------------------
# Per-monitor window
# ---------------------------------------------------------------------------


class SaverWindow(Gtk.Window):
    def __init__(self, app: "ScreensaverApp", monitor: Gdk.Monitor, mode: str):
        super().__init__(application=app)
        self.app = app
        self.monitor = monitor
        self.mode = mode
        self._armed = False  # ignore keys until delay elapses / first paint

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_title("Screensaver")

        geo = monitor.get_geometry()
        self.scene = Scene(mode, geo.width, geo.height)

        self.area = Gtk.DrawingArea()
        self.area.set_content_width(geo.width)
        self.area.set_content_height(geo.height)
        self.area.set_draw_func(self._on_draw)
        self.set_child(self.area)

        # Keypress quits; mouse is ignored (Active-User jiggles the pointer).
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self._place_on_monitor(monitor)
        self.connect("map", self._on_map)

    def _place_on_monitor(self, monitor: Gdk.Monitor) -> None:
        geo = monitor.get_geometry()
        self.set_default_size(geo.width, geo.height)
        if using_layer_shell():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_monitor(self, monitor)
            if hasattr(LayerShell, "set_namespace"):
                LayerShell.set_namespace(self, LAYER_NS)
            for edge in (
                LayerShell.Edge.TOP,
                LayerShell.Edge.BOTTOM,
                LayerShell.Edge.LEFT,
                LayerShell.Edge.RIGHT,
            ):
                LayerShell.set_anchor(self, edge, True)
            LayerShell.set_exclusive_zone(self, -1)
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)

    def _on_map(self, *_args) -> None:
        if not using_layer_shell():
            # One fullscreen surface per monitor (GTK4 Wayland).
            self.fullscreen_on_monitor(self.monitor)
            GLib.idle_add(hypr_raise_screensaver)
        blank = Gdk.Cursor.new_from_name("none")
        self.set_cursor(blank)
        GLib.timeout_add(500, self._arm)

    def _arm(self) -> bool:
        self._armed = True
        return GLib.SOURCE_REMOVE

    def tick(self, dt: float) -> None:
        self.scene.tick(dt)
        self.area.queue_draw()

    def _on_draw(self, _area, cr, width: int, height: int) -> None:
        if width != self.scene.width or height != self.scene.height:
            self.scene.resize(width, height)
        self.scene.draw(cr, width, height)

    def _quit(self) -> None:
        if self._armed:
            self.app.quit()

    def _on_key(self, *_args) -> bool:
        self._quit()
        return True


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class ScreensaverApp(Gtk.Application):
    def __init__(self, mode: str, delay: float):
        super().__init__(application_id=APP_ID)
        self.mode = mode
        self.delay = delay
        self.windows: list[SaverWindow] = []
        self._last_tick = 0.0
        self.connect("activate", self._on_activate)

    def _on_activate(self, *_args) -> None:
        if self.delay > 0:
            # Invisible hold, then start — keeps the process alive
            GLib.timeout_add(int(self.delay * 1000), self._start)
        else:
            self._start()

    def _start(self) -> bool:
        display = Gdk.Display.get_default()
        if display is None:
            print("screensaver: no display", file=sys.stderr)
            self.quit()
            return GLib.SOURCE_REMOVE

        monitors = list_monitors(display)
        if not monitors:
            print("screensaver: no monitors found", file=sys.stderr)
            self.quit()
            return GLib.SOURCE_REMOVE

        for mon in monitors:
            win = SaverWindow(self, mon, self.mode)
            self.windows.append(win)
            win.present()

        self._last_tick = time.monotonic()
        GLib.timeout_add(int(1000 / FPS), self._frame)
        if not using_layer_shell():
            GLib.timeout_add(400, hypr_raise_screensaver)
        return GLib.SOURCE_REMOVE

    def _frame(self) -> bool:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        for win in self.windows:
            win.tick(dt)
        return GLib.SOURCE_CONTINUE


def list_monitors(display: Gdk.Display) -> list[Gdk.Monitor]:
    """Return every connected monitor (GTK4 ListModel API)."""
    out: list[Gdk.Monitor] = []
    model = display.get_monitors()
    for i in range(model.get_n_items()):
        item = model.get_item(i)
        if item is not None:
            out.append(item)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fullscreen GTK4 screensaver")
    parser.add_argument(
        "--mode",
        choices=("clock", "stars", "aurora", "matrix"),
        default="clock",
        help="Visual style (default: clock)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        metavar="SEC",
        help="Wait this many seconds before covering the screen",
    )
    args = parser.parse_args(argv)

    # Prefer cairo from PyGObject; ensure available early
    try:
        import cairo  # noqa: F401
    except ImportError:
        print(
            "screensaver: needs python3-cairo (apt install python3-cairo)",
            file=sys.stderr,
        )
        return 1

    app = ScreensaverApp(mode=args.mode, delay=args.delay)
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())
