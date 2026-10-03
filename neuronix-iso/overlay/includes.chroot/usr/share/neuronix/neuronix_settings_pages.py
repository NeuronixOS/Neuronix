#!/usr/bin/env python3
"""GTK pages for the Waybar settings window. Replaces the Qt hypr-settings tabs."""
from __future__ import annotations

import configparser
import json
import math
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gtk, GLib, Pango, PangoCairo  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (
    "/usr/share/neuronix",
    _HERE,
    os.path.expanduser("~/.local/share/neuronix"),
):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import neuronix_quick_settings as quick  # noqa: E402

_SCREEN_DIR = Path.home() / ".config" / "neuronix-screensaver"
_SCREEN_INI = _SCREEN_DIR / "config.ini"
_SCREEN_UNIT = "neuronix-screensaver-idle.service"
_SCREEN_MODES = (
    ("clock", "Clock"),
    ("stars", "Stars"),
    ("aurora", "Aurora"),
    ("matrix", "Matrix"),
)
_SCREEN_IDLE = (
    (60, "1 minute"),
    (120, "2 minutes"),
    (300, "5 minutes"),
    (600, "10 minutes"),
    (900, "15 minutes"),
    (1800, "30 minutes"),
    (3600, "1 hour"),
)

_APP_CATEGORIES = (
    ("Web Browser", "x-scheme-handler/http"),
    ("Email", "x-scheme-handler/mailto"),
    ("Files", "inode/directory"),
    ("Text Editor", "text/plain"),
    ("Images", "image/png"),
    ("Video", "video/mp4"),
    ("Music", "audio/mpeg"),
    ("PDF", "application/pdf"),
    ("Archives", "application/zip"),
)


def _page() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_margin_top(4)
    box.set_margin_bottom(8)
    box.set_margin_start(2)
    box.set_margin_end(8)
    return box


def _note(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0.0)
    lbl.set_line_wrap(True)
    lbl.set_max_width_chars(52)
    lbl.set_selectable(True)
    lbl.get_style_context().add_class("neuronix-subtitle")
    return lbl


def _section(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0.0)
    lbl.get_style_context().add_class("neuronix-heading")
    return lbl


def _run(argv: list[str], timeout: float = 8.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            argv,
            text=True,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return proc.returncode == 0, (proc.stdout or "").strip()
    except Exception as exc:
        return False, str(exc)


def _button(label: str) -> Gtk.Button:
    btn = Gtk.Button(label=label)
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.get_style_context().add_class("neuronix-secondary")
    return btn


def wifi_page() -> Gtk.Widget:
    box = _page()
    quick.pack_network_controls(box, quit_on_advanced=False, compact=False)
    return box


def ethernet_page() -> Gtk.Widget:
    return quick._ethernet_page()


def bluetooth_page() -> Gtk.Widget:
    box = _page()
    status = _note("Reading Bluetooth…")
    box.pack_start(status, False, False, 0)
    power = _button("Bluetooth")
    box.pack_start(power, False, False, 0)
    scan = _button("Scan")
    box.pack_start(scan, False, False, 0)
    box.pack_start(_section("Available devices"), False, False, 0)
    lst = Gtk.ListBox()
    lst.set_selection_mode(Gtk.SelectionMode.SINGLE)
    lst.get_style_context().add_class("neuronix-list")
    frame = Gtk.ScrolledWindow()
    frame.get_style_context().add_class("neuronix-list-frame")
    frame.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    frame.set_size_request(-1, 220)
    frame.set_vexpand(True)
    frame.add(lst)
    box.pack_start(frame, True, True, 0)

    def _powered() -> bool:
        ok, out = _run(["bluetoothctl", "show"], timeout=4)
        return ok and "Powered: yes" in out

    def _fill(*_a) -> None:
        for child in list(lst.get_children()):
            lst.remove(child)
        on = _powered()
        power.set_label("Bluetooth On" if on else "Bluetooth Off")
        status.set_text("On" if on else "Off")
        ok, out = _run(["bluetoothctl", "devices"], timeout=4)
        if not ok:
            status.set_text(out or "bluetoothctl is not available")
            return
        for line in out.splitlines():
            parts = line.split(None, 2)
            if len(parts) < 3 or parts[0] != "Device":
                continue
            mac, name = parts[1], parts[2]
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("neuronix-list-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            lab = Gtk.Label(label=name, xalign=0.0)
            lab.set_ellipsize(Pango.EllipsizeMode.END)
            lab.get_style_context().add_class("neuronix-row-title")
            detail = Gtk.Label(label=mac, xalign=0.0)
            detail.get_style_context().add_class("neuronix-row-desc")
            inner.pack_start(lab, False, False, 0)
            inner.pack_start(detail, False, False, 0)
            row.add(inner)
            row._mac = mac  # type: ignore[attr-defined]
            lst.add(row)
        lst.show_all()

    def _toggle(*_a) -> None:
        _run(["bluetoothctl", "power", "off" if _powered() else "on"], timeout=6)
        GLib.idle_add(_fill)

    def _connect(_lb, row) -> None:
        mac = getattr(row, "_mac", "")
        if not mac:
            return
        status.set_text(f"Connecting {mac}…")

        def work() -> None:
            ok, out = _run(["bluetoothctl", "connect", mac], timeout=20)
            GLib.idle_add(status.set_text, "Connected" if ok else (out or "Connect failed"))

        import threading

        threading.Thread(target=work, daemon=True).start()

    def _scan(*_a) -> None:
        status.set_text("Scanning…")

        def work() -> None:
            _run(["bluetoothctl", "--timeout", "6", "scan", "on"], timeout=10)
            GLib.idle_add(_fill)

        import threading

        threading.Thread(target=work, daemon=True).start()

    power.connect("clicked", _toggle)
    scan.connect("clicked", _scan)
    lst.connect("row-activated", _connect)
    _fill()
    return box


def _logical_size(mon: dict) -> tuple[int, int]:
    """Size in the layout, after scale and rotation. Hyprland y grows downward."""
    scale = float(mon.get("scale") or 1) or 1.0
    width = max(1, int(round(float(mon.get("width") or 1) / scale)))
    height = max(1, int(round(float(mon.get("height") or 1) / scale)))
    if int(mon.get("transform") or 0) in (1, 3, 5, 7):
        width, height = height, width
    return width, height


def _map_view(mons: list, width: int, height: int, pad: float = 18.0) -> dict:
    if not mons or width < 40 or height < 40:
        return {"ok": False}
    sizes = [_logical_size(m) for m in mons]
    min_x = min(int(m.get("x") or 0) for m in mons)
    min_y = min(int(m.get("y") or 0) for m in mons)
    span_w = max(int(m.get("x") or 0) + sizes[i][0] for i, m in enumerate(mons)) - min_x
    span_h = max(int(m.get("y") or 0) + sizes[i][1] for i, m in enumerate(mons)) - min_y
    span_w = max(span_w, 1)
    span_h = max(span_h, 1)
    scale = min((width - pad * 2) / span_w, (height - pad * 2) / span_h)
    scale = max(scale, 0.0001)
    used_w = span_w * scale
    used_h = span_h * scale
    return {
        "ok": True,
        "min_x": min_x,
        "min_y": min_y,
        "scale": scale,
        "ox": (width - used_w) / 2,
        "oy": (height - used_h) / 2,
    }


def _map_rect(mon: dict, view: dict) -> tuple[float, float, float, float]:
    lw, lh = _logical_size(mon)
    x = view["ox"] + (int(mon.get("x") or 0) - view["min_x"]) * view["scale"]
    y = view["oy"] + (int(mon.get("y") or 0) - view["min_y"]) * view["scale"]
    return x, y, lw * view["scale"], lh * view["scale"]


def _snap_monitor(mons: list, idx: int) -> None:
    """Dock the dragged display against the nearest neighbor edge, keeping the slide axis."""
    if idx < 0 or idx >= len(mons) or len(mons) < 2:
        return
    mon = mons[idx]
    lw, lh = _logical_size(mon)
    best = None
    for other_i, other in enumerate(mons):
        if other_i == idx:
            continue
        ow, oh = _logical_size(other)
        ox, oy = int(other.get("x") or 0), int(other.get("y") or 0)
        limit = max(180, int(min(lw, lh, ow, oh) * 0.4))
        for nx, ny in (
            (ox + ow, int(mon.get("y") or 0)),
            (ox - lw, int(mon.get("y") or 0)),
            (int(mon.get("x") or 0), oy + oh),
            (int(mon.get("x") or 0), oy - lh),
        ):
            dist = abs(nx - int(mon.get("x") or 0)) + abs(ny - int(mon.get("y") or 0))
            if dist > limit:
                continue
            if best is None or dist < best[0]:
                best = (dist, nx, ny)
    if best:
        mon["x"], mon["y"] = best[1], best[2]


def displays_page() -> Gtk.Widget:
    box = _page()
    status = _note("Reading monitors…")
    box.pack_start(status, False, False, 0)
    hint = _note("Drag a display. Edges snap together when you let go.")
    box.pack_start(hint, False, False, 0)

    canvas = Gtk.DrawingArea()
    canvas.set_size_request(-1, 280)
    canvas.set_hexpand(True)
    canvas.add_events(
        Gdk.EventMask.BUTTON_PRESS_MASK
        | Gdk.EventMask.BUTTON_RELEASE_MASK
        | Gdk.EventMask.POINTER_MOTION_MASK
        | Gdk.EventMask.BUTTON1_MOTION_MASK
    )
    box.pack_start(canvas, False, False, 0)

    rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.pack_start(rows_box, False, False, 0)
    apply_btn = _button("Apply")
    box.pack_start(apply_btn, False, False, 0)
    state: dict = {"mons": [], "editors": [], "sel": -1, "drag": -1, "view": None, "paint": {}}

    def _cursor(name: str) -> None:
        window = canvas.get_window()
        if window is None:
            return
        window.set_cursor(Gdk.Cursor.new_from_name(canvas.get_display(), name))

    def _view() -> dict:
        if state["drag"] >= 0 and state.get("view"):
            return state["view"]
        return _map_view(state["mons"], canvas.get_allocated_width(), canvas.get_allocated_height())

    def _sync_pos() -> None:
        for mon, _mode, _scale, pos_lbl in state.get("editors") or []:
            pos_lbl.set_text(f"{int(mon.get('x') or 0)}, {int(mon.get('y') or 0)}")

    def _hit(px: float, py: float) -> int:
        view = _view()
        if not view.get("ok"):
            return -1
        for index in range(len(state["mons"]) - 1, -1, -1):
            x, y, w, h = _map_rect(state["mons"][index], view)
            if x <= px <= x + w and y <= py <= y + h:
                return index
        return -1

    def _draw(_widget, cr: cairo.Context) -> bool:
        width = canvas.get_allocated_width()
        height = canvas.get_allocated_height()
        paint = state.get("paint") or {}
        bg = paint.get("bg", (0.08, 0.08, 0.08))
        fg = paint.get("fg", (0.92, 0.92, 0.9))
        fills = paint.get("fills") or [(0.35, 0.45, 0.7)]
        cr.set_source_rgb(*(c * 0.72 for c in bg))
        cr.paint()
        mons = state["mons"]
        view = _view()
        if not view.get("ok"):
            return False
        for index, mon in enumerate(mons):
            x, y, w, h = _map_rect(mon, view)
            fill = fills[index % len(fills)]
            if mon.get("disabled"):
                fill = _mix(fill, bg, 0.55)
            _rounded(cr, x, y, w, h, 10)
            cr.set_source_rgb(*fill)
            cr.fill()
            selected = index == state["sel"]
            cr.set_source_rgb(*(fg if selected else _mix(fill, fg, 0.35)))
            cr.set_line_width(2.5 if selected else 1.0)
            _rounded(cr, x + 1, y + 1, max(1, w - 2), max(1, h - 2), 9)
            cr.stroke()
            ink = (0.08, 0.08, 0.08) if _luminance(fill) >= 0.45 else fg
            cr.set_source_rgb(*ink)
            name = str(mon.get("name") or "")
            lw, lh = _logical_size(mon)
            if h >= 64 and w >= 72:
                name_layout = _pango_layout(cr, name, 13, True)
                size_layout = _pango_layout(cr, f"{lw}×{lh}", 11, False)
                nw, nh = name_layout.get_pixel_size()
                _sw, sh = size_layout.get_pixel_size()
                block = nh + 4 + sh
                cr.move_to(x + (w - nw) / 2, y + (h - block) / 2)
                PangoCairo.show_layout(cr, name_layout)
                cr.move_to(x + (w - _sw) / 2, y + (h - block) / 2 + nh + 4)
                PangoCairo.show_layout(cr, size_layout)
            else:
                name_layout = _pango_layout(cr, name, 12, True)
                nw, nh = name_layout.get_pixel_size()
                cr.move_to(x + (w - nw) / 2, y + (h - nh) / 2)
                PangoCairo.show_layout(cr, name_layout)
        return False

    def _press(_widget, event) -> bool:
        if event.button != 1:
            return False
        index = _hit(event.x, event.y)
        state["sel"] = index
        if index < 0:
            state["drag"] = -1
            _cursor("default")
            canvas.queue_draw()
            return True
        view = _map_view(state["mons"], canvas.get_allocated_width(), canvas.get_allocated_height())
        state["view"] = view
        state["drag"] = index
        x, y, _w, _h = _map_rect(state["mons"][index], view)
        state["off"] = (event.x - x, event.y - y)
        _cursor("grabbing")
        canvas.queue_draw()
        return True

    def _motion(_widget, event) -> bool:
        if state["drag"] < 0:
            _cursor("grab" if _hit(event.x, event.y) >= 0 else "default")
            return False
        view = state.get("view") or {}
        if not view.get("ok"):
            return True
        mon = state["mons"][state["drag"]]
        offx, offy = state.get("off") or (0, 0)
        left = event.x - offx
        top = event.y - offy
        mon["x"] = int(round(view["min_x"] + (left - view["ox"]) / view["scale"]))
        mon["y"] = int(round(view["min_y"] + (top - view["oy"]) / view["scale"]))
        _sync_pos()
        canvas.queue_draw()
        return True

    def _release(_widget, event) -> bool:
        if event.button != 1 or state["drag"] < 0:
            return False
        index = state["drag"]
        _snap_monitor(state["mons"], index)
        state["drag"] = -1
        state["view"] = None
        _sync_pos()
        name = str(state["mons"][index].get("name") or "")
        status.set_text(f"{name}  ·  {int(state['mons'][index].get('x') or 0)}, {int(state['mons'][index].get('y') or 0)}")
        _cursor("default")
        canvas.queue_draw()
        return True

    canvas.connect("draw", _draw)
    canvas.connect("button-press-event", _press)
    canvas.connect("motion-notify-event", _motion)
    canvas.connect("button-release-event", _release)

    def _load() -> None:
        for child in list(rows_box.get_children()):
            rows_box.remove(child)
        ok, out = _run(["hyprctl", "monitors", "all", "-j"], timeout=4)
        if not ok or not out:
            status.set_text(out or "hyprctl is not available")
            return
        try:
            mons = json.loads(out)
        except json.JSONDecodeError:
            status.set_text("Could not read monitor list")
            return
        state["mons"] = mons
        state["sel"] = 0 if mons else -1
        state["drag"] = -1
        state["view"] = None
        try:
            import neuronix_choice_dialog as choice

            chrome = choice._theme_chrome()
            profile = choice._active_profile() or {}
            palette = [c for c in (profile.get("palette") or []) if isinstance(c, str)]
        except Exception:
            chrome = {"bg": "#1c1c1c", "fg": "#eeeeee", "accent": "#8ab4f8"}
            palette = []
        bg = _rgb(chrome["bg"])
        fg = _rgb(chrome["fg"])
        fills = []
        for hex_color in [chrome.get("accent") or "#8ab4f8", *palette]:
            rgb = _rgb(str(hex_color))
            if abs(_luminance(rgb) - _luminance(bg)) < 0.08:
                continue
            fills.append(rgb)
        if not fills:
            fills = [_rgb("#8ab4f8")]
        state["paint"] = {"bg": bg, "fg": fg, "fills": fills}
        status.set_text(f"{len(mons)} display" + ("s" if len(mons) != 1 else ""))
        editors = []
        for mon in mons:
            name = str(mon.get("name") or "")
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            title = Gtk.Label(label=name, xalign=0.0)
            title.get_style_context().add_class("neuronix-row-title")
            card.pack_start(title, False, False, 0)
            desc = str(mon.get("description") or "")
            if desc:
                card.pack_start(_note(desc), False, False, 0)
            pos_lbl = _note(f"{int(mon.get('x') or 0)}, {int(mon.get('y') or 0)}")
            card.pack_start(pos_lbl, False, False, 0)
            mode = Gtk.ComboBoxText()
            current = f"{mon.get('width')}x{mon.get('height')}@{float(mon.get('refreshRate') or 60):.0f}"
            modes = [str(item) for item in (mon.get("availableModes") or [])] or [current]
            if current not in modes:
                modes.insert(0, current)
            for item in modes:
                mode.append_text(item)
            mode.set_active(modes.index(current) if current in modes else 0)
            scale = Gtk.SpinButton.new_with_range(0.5, 3.0, 0.1)
            scale.set_digits(2)
            scale.set_value(float(mon.get("scale") or 1))

            def _on_mode(widget, target=mon) -> None:
                spec = (widget.get_active_text() or "").strip()
                if "x" in spec and "@" in spec:
                    wh, hz = spec.split("@", 1)
                    w_s, h_s = wh.split("x", 1)
                    try:
                        target["width"] = int(w_s)
                        target["height"] = int(h_s)
                        target["refreshRate"] = float(hz)
                    except ValueError:
                        return
                    canvas.queue_draw()

            def _on_scale(widget, target=mon) -> None:
                target["scale"] = widget.get_value()
                canvas.queue_draw()

            mode.connect("changed", _on_mode)
            scale.connect("value-changed", _on_scale)
            card.pack_start(mode, False, False, 0)
            card.pack_start(scale, False, False, 0)
            rows_box.pack_start(card, False, False, 0)
            editors.append((mon, mode, scale, pos_lbl))
        state["editors"] = editors
        rows_box.show_all()
        canvas.queue_draw()

    def _apply(*_a) -> None:
        written = []
        for mon, mode, scale, _pos in state.get("editors") or []:
            name = str(mon.get("name") or "")
            spec = (mode.get_active_text() or "").strip()
            x = int(mon.get("x") or 0)
            y = int(mon.get("y") or 0)
            sc = f"{scale.get_value():.2g}"
            ok, out = _run(
                ["hyprctl", "keyword", "monitor", f"{name},{spec},{x}x{y},{sc}"],
                timeout=4,
            )
            if not ok:
                status.set_text(out or f"Could not apply {name}")
                return
            mon["x"] = x
            mon["y"] = y
            mon["scale"] = scale.get_value()
            if "x" in spec and "@" in spec:
                wh, hz = spec.split("@", 1)
                w, h = wh.split("x", 1)
                mon["width"] = int(w)
                mon["height"] = int(h)
                mon["refreshRate"] = float(hz)
            written.append(mon)
        try:
            sys.path.insert(0, "/usr/local/lib/neuronix/hypr-settings")
            from monitor_profiles import write_monitors_lua

            write_monitors_lua(written, use_edid=False)
        except Exception:
            pass
        _sync_pos()
        canvas.queue_draw()
        status.set_text("Applied")

    apply_btn.connect("clicked", _apply)
    _load()
    return box


def sound_page() -> Gtk.Widget:
    box = _page()
    quick.pack_sound_controls(box, quit_on_advanced=False, compact=False)
    box.pack_start(_section("Microphone"), False, False, 0)

    def _pct() -> int:
        out = quick._run(["pactl", "get-source-volume", "@DEFAULT_SOURCE@"])
        import re

        m = re.search(r"(\d+)%", out or "")
        return int(m.group(1)) if m else 0

    lbl = Gtk.Label(label=f"{_pct()}%", xalign=1.0)
    lbl.get_style_context().add_class("neuronix-pct")
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
    scale.set_draw_value(False)
    scale.set_hexpand(True)
    scale.get_style_context().add_class("neuronix-scale")
    scale.set_value(_pct())

    def _on_scale(s: Gtk.Scale) -> None:
        pct = int(s.get_value())
        lbl.set_text(f"{pct}%")
        quick._run_ok(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{pct}%"])

    scale.connect("value-changed", _on_scale)
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.pack_start(scale, True, True, 0)
    row.pack_start(lbl, False, False, 0)
    box.pack_start(row, False, False, 0)
    mute = _button("Mute microphone")

    def _mute(*_a) -> None:
        quick._run_ok(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"])

    mute.connect("clicked", _mute)
    box.pack_start(mute, False, False, 0)
    return box


def _pack_battery(box: Gtk.Box) -> None:
    status = _note("")
    box.pack_start(status, False, False, 0)
    supply = Path("/sys/class/power_supply")
    bats = sorted(p for p in supply.glob("BAT*") if p.is_dir()) if supply.is_dir() else []
    if not bats:
        status.set_text("No battery. This machine is on external power.")
        return
    bat = bats[0]

    def _read(name: str) -> str:
        try:
            return (bat / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    cap = _read("capacity") or "—"
    state = _read("status") or "—"
    status.set_text(f"{bat.name}  ·  {cap}%  ·  {state}")
    now = _read("energy_now") or _read("charge_now")
    full = _read("energy_full") or _read("charge_full")
    if now and full:
        box.pack_start(_note(f"Charge {now} / {full}"), False, False, 0)
    ok, profile = _run(["powerprofilesctl", "get"], timeout=3)
    if ok and profile:
        box.pack_start(_note(f"Power profile: {profile}"), False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for name in ("power-saver", "balanced", "performance"):
            btn = _button(name)
            btn.connect(
                "clicked",
                lambda *_a, n=name: _run(["powerprofilesctl", "set", n], timeout=4),
            )
            row.pack_start(btn, False, False, 0)
        box.pack_start(row, False, False, 0)


def _desktop_files() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    roots = []
    for d in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"):
        if d:
            roots.append(Path(d) / "applications")
    roots.append(Path.home() / ".local/share/applications")
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.desktop"):
            if path.name in seen:
                continue
            seen.add(path.name)
            name = path.stem
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("Name="):
                        name = line.split("=", 1)[1].strip() or name
                        break
            except OSError:
                pass
            found.append((path.name, name))
    found.sort(key=lambda item: item[1].lower())
    return found


def apps_page() -> Gtk.Widget:
    box = _page()
    box.pack_start(_section("Default applications"), False, False, 0)
    apps = _desktop_files()
    for label, mime in _APP_CATEGORIES:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cap = Gtk.Label(label=label, xalign=0.0)
        cap.set_width_chars(14)
        combo = Gtk.ComboBoxText()
        combo.set_hexpand(True)
        current = ""
        ok, out = _run(["xdg-mime", "query", "default", mime], timeout=3)
        if ok:
            current = out.strip()
        active = 0
        combo.append_text("")
        for i, (filename, title) in enumerate(apps, start=1):
            combo.append_text(f"{title}  ({filename})")
            if filename == current:
                active = i
        combo.set_active(active)

        def _set(widget: Gtk.ComboBoxText, mime=mime) -> None:
            text = widget.get_active_text() or ""
            if "(" not in text:
                return
            filename = text.rsplit("(", 1)[-1].rstrip(")").strip()
            if filename:
                _run(["xdg-mime", "default", filename, mime], timeout=4)

        combo.connect("changed", _set)
        row.pack_start(cap, False, False, 0)
        row.pack_start(combo, True, True, 0)
        box.pack_start(row, False, False, 0)
    return box


def _gtk_theme():
    for path in (
        "/usr/local/lib/neuronix/gtk-apps/gtk-theme/python",
        "/usr/share/neuronix/gtk-theme/python",
    ):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    import gtk_theme

    return gtk_theme


def _rgb(hex_color: str) -> tuple[float, float, float]:
    raw = (hex_color or "").strip().lstrip("#")
    if len(raw) != 6:
        return (0.2, 0.2, 0.2)
    try:
        return tuple(int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.2, 0.2, 0.2)


def _mix(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _rounded(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    if r < 0.5:
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _pango_layout(cr: cairo.Context, text: str, px: float, bold: bool = False):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription.from_string("DejaVu Sans, sans-serif")
    if bold:
        desc.set_weight(Pango.Weight.BOLD)
    desc.set_absolute_size(px * Pango.SCALE)
    layout.set_font_description(desc)
    layout.set_text(text, -1)
    return layout


def _pango_show(cr: cairo.Context, x: float, y: float, text: str, px: float, bold: bool = False) -> tuple[int, int]:
    layout = _pango_layout(cr, text, px, bold)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)
    return layout.get_pixel_size()


def _bar_colors(chrome, fill, fg, focused: bool) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    src = chrome.bar if focused else (chrome.bar_inactive or chrome.bar)
    if src:
        a = _rgb(src[0])
        b = _rgb(src[1]) if len(src) > 1 else _mix(a, fg, 0.22 if focused else 0.10)
        return a, b
    if focused:
        return _mix(fill, fg, 0.10), _mix(fill, fg, 0.22)
    return _mix(fill, fg, 0.06), _mix(fill, (0.0, 0.0, 0.0), 0.12)


def _paint_fake_window(cr, x, y, fw, fh, chrome, bg, fg, outer, inner, title: str, focused: bool) -> None:
    thickness = float(chrome.border_size)
    radius = float(chrome.rounding)
    highlight = _mix(outer, (1.0, 1.0, 1.0), 0.45)
    shadow = _mix(outer, (0.0, 0.0, 0.0), 0.45)
    fill = bg if focused else _mix(bg, (0.0, 0.0, 0.0), 0.08)

    _rounded(cr, x, y, fw, fh, radius)
    cr.set_source_rgb(*fill)
    cr.fill()

    if chrome.bevel == "inner":
        cr.set_source_rgb(*shadow)
        cr.set_line_width(max(2.0, thickness))
        _rounded(cr, x + thickness / 2, y + thickness / 2, max(1.0, fw - thickness), max(1.0, fh - thickness), radius)
        cr.stroke()
        cr.set_source_rgb(*highlight)
        cr.set_line_width(max(1.0, thickness * 0.35))
        inset = thickness * 0.55
        _rounded(
            cr,
            x + inset,
            y + inset,
            max(1.0, fw - inset * 2),
            max(1.0, fh - inset * 2),
            max(0.0, radius - inset * 0.3),
        )
        cr.stroke()
    elif chrome.bevel == "double":
        cr.set_source_rgb(*outer)
        cr.set_line_width(max(1.0, thickness * 0.4))
        _rounded(
            cr,
            x + thickness * 0.25,
            y + thickness * 0.25,
            max(1.0, fw - thickness * 0.5),
            max(1.0, fh - thickness * 0.5),
            radius,
        )
        cr.stroke()
        cr.set_source_rgb(*inner)
        inset = thickness * 0.75
        cr.set_line_width(max(1.0, thickness * 0.4))
        _rounded(
            cr,
            x + inset,
            y + inset,
            max(1.0, fw - inset * 2),
            max(1.0, fh - inset * 2),
            max(0.0, radius - inset * 0.4),
        )
        cr.stroke()
    else:
        rtl = chrome.gradient == "rtl"
        x0, x1 = (x + fw, x) if rtl else (x, x + fw)
        pat = cairo.LinearGradient(x0, y, x1, y)
        pat.add_color_stop_rgb(0.0, *outer)
        pat.add_color_stop_rgb(1.0, *inner)
        cr.set_source(pat)
        cr.set_line_width(max(1.0, thickness))
        _rounded(
            cr,
            x + thickness / 2,
            y + thickness / 2,
            max(1.0, fw - thickness),
            max(1.0, fh - thickness),
            max(0.0, radius),
        )
        cr.stroke()

    bar_h = 22.0
    bar_inset = max(2.0, thickness)
    inner_x = x + bar_inset
    inner_y = y + bar_inset
    inner_w = max(8.0, fw - bar_inset * 2)
    b0, b1 = _bar_colors(chrome, fill, fg, focused)
    if not focused:
        b0 = _mix(b0, (0.0, 0.0, 0.0), 0.12)
        b1 = _mix(b1, (0.0, 0.0, 0.0), 0.12)
    rtl = chrome.gradient == "rtl"
    gx0, gx1 = (inner_x + inner_w, inner_x) if rtl else (inner_x, inner_x + inner_w)
    bar = cairo.LinearGradient(gx0, inner_y, gx1, inner_y)
    bar.add_color_stop_rgb(0.0, *b0)
    bar.add_color_stop_rgb(1.0, *b1)
    cr.set_source(bar)
    cr.rectangle(inner_x, inner_y, inner_w, bar_h)
    cr.fill()

    cr.set_source_rgb(*fg)
    _pango_show(cr, inner_x + 8, inner_y + 4, title, 11, True)
    glyphs = (chrome.minimize, chrome.maximize, chrome.close)
    glyph_px = float(min(chrome.button_size, 22))
    gx = inner_x + inner_w - 8
    for glyph in reversed(glyphs):
        tw, _th = _pango_layout(cr, glyph, glyph_px, False).get_pixel_size()
        gx -= tw + 10
        _pango_show(cr, gx, inner_y + 2, glyph, glyph_px, False)


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _paint_chip(cr, x, y, w, h, text, fill, ink, border=None) -> None:
    _rounded(cr, x, y, w, h, 8)
    cr.set_source_rgb(*fill)
    cr.fill()
    if border is not None:
        cr.set_source_rgb(*border)
        cr.set_line_width(1)
        _rounded(cr, x + 0.5, y + 0.5, max(1, w - 1), max(1, h - 1), 8)
        cr.stroke()
    tw, th = _pango_layout(cr, text, 13, True).get_pixel_size()
    cr.set_source_rgb(*ink)
    _pango_show(cr, x + (w - tw) / 2, y + (h - th) / 2, text, 13, True)


def _draw_theme_preview(area: Gtk.DrawingArea, cr: cairo.Context, profile) -> bool:
    w = area.get_allocated_width()
    h = area.get_allocated_height()
    if w < 20 or h < 20 or profile is None:
        return False
    bg = _rgb(profile.background)
    fg = _rgb(profile.foreground)
    palette = getattr(profile, "palette", ()) or ()
    accent = _rgb(palette[4]) if len(palette) > 4 else _mix(bg, fg, 0.45)
    selection = _mix(bg, fg, 0.16)
    hint = _mix(fg, bg, 0.38)
    border = _mix(bg, fg, 0.22)
    on_accent = (0.11, 0.12, 0.13) if _luminance(accent) >= 0.45 else fg
    cr.set_source_rgb(*bg)
    cr.paint()

    chrome_h = min(150.0, max(110.0, h * 0.42))
    cr.set_source_rgb(bg[0] * 0.55, bg[1] * 0.55, bg[2] * 0.55)
    cr.rectangle(0, 0, w, chrome_h)
    cr.fill()
    pad = 10.0
    stack = 16.0
    fw = max(48.0, w - pad * 2 - stack)
    fh = max(56.0, chrome_h - pad * 2 - stack)
    chrome = profile.chrome
    i0, i1 = profile.border_inactive_stops()
    a0, a1 = profile.border_active_stops()
    _paint_fake_window(
        cr, pad + stack, pad, fw, fh, chrome, bg, _mix(fg, bg, 0.45), _rgb(i0), _rgb(i1), "Inactive", False
    )
    _paint_fake_window(cr, pad, pad + stack, fw, fh, chrome, bg, fg, _rgb(a0), _rgb(a1), "Window", True)

    y = chrome_h + 12
    cr.set_source_rgb(*hint)
    _pango_show(cr, pad, y, "Settings", 11)
    y += 22
    row_w = max(40.0, w - pad * 2)
    row_h = 34.0
    _rounded(cr, pad, y, row_w, row_h, 6)
    cr.set_source_rgb(*selection)
    cr.fill()
    cr.set_source_rgb(*fg)
    _pango_show(cr, pad + 12, y + 8, "Selected item", 13, True)
    y += row_h + 4
    cr.set_source_rgb(*fg)
    _pango_show(cr, pad + 12, y + 8, "Item", 13)
    cr.set_source_rgb(*hint)
    _pango_show(cr, pad + 118, y + 10, "Detail", 11)
    y += row_h + 12
    gap = 8.0
    bw = max(40.0, (row_w - gap) / 2)
    bh = 34.0
    _paint_chip(cr, pad, y, bw, bh, "Button", _mix(bg, fg, 0.08), fg, border)
    _paint_chip(cr, pad + bw + gap, y, bw, bh, "Accent", accent, on_accent)
    return False


def themes_page() -> Gtk.Widget:
    box = _page()
    try:
        theme = _gtk_theme()
        profiles = theme.all_profiles()
    except Exception as exc:
        box.pack_start(_note(str(exc)), False, False, 0)
        return box
    if not profiles:
        box.pack_start(_note("No themes were found."), False, False, 0)
        return box

    names: dict[str, int] = {}
    for profile in profiles:
        names[profile.name] = names.get(profile.name, 0) + 1
    box.pack_start(_section("Theme"), False, False, 0)
    combo = Gtk.ComboBoxText()
    ids: list[str] = []
    for profile in profiles:
        ids.append(profile.id)
        label = profile.name if names[profile.name] == 1 else f"{profile.name} ({profile.id})"
        combo.append_text(label)
    current = theme.load_theme_id()
    combo.set_active(ids.index(current) if current in ids else 0)
    box.pack_start(combo, False, False, 0)

    chosen = {"profile": profiles[combo.get_active()]}
    area = Gtk.DrawingArea()
    area.set_size_request(-1, 360)
    area.set_hexpand(True)
    frame = Gtk.ScrolledWindow()
    frame.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
    frame.get_style_context().add_class("neuronix-well")
    frame.set_size_request(-1, 384)
    frame.add(area)
    box.pack_start(frame, False, False, 0)
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    apply_btn = _button("Apply")
    edit_btn = _button("Edit")
    apply_btn.get_style_context().remove_class("neuronix-secondary")
    apply_btn.get_style_context().add_class("neuronix-primary")
    apply_btn.set_hexpand(True)
    edit_btn.set_hexpand(True)
    apply_btn.set_size_request(140, 40)
    edit_btn.set_size_request(140, 40)
    actions.pack_start(apply_btn, True, True, 0)
    actions.pack_start(edit_btn, True, True, 0)
    box.pack_start(actions, False, False, 0)
    status = _note(chosen["profile"].name)
    box.pack_start(status, False, False, 0)

    def _draw(widget, cr):
        return _draw_theme_preview(widget, cr, chosen["profile"])

    def _pick() -> object | None:
        index = combo.get_active()
        if index < 0:
            return None
        return next((item for item in profiles if item.id == ids[index]), None)

    def _changed(*_a) -> None:
        profile = _pick()
        if profile is None:
            return
        chosen["profile"] = profile
        area.queue_draw()
        if profile.id == theme.load_theme_id():
            status.set_text(f"{profile.name} is in use")
        else:
            status.set_text(profile.name)

    def _apply(*_a) -> None:
        profile = chosen.get("profile")
        if profile is None:
            return
        try:
            theme.select_theme(profile.id, gtk_version=3)
            status.set_text(f"Applied {profile.name}")
        except Exception as exc:
            status.set_text(str(exc))

    def _edit(*_a) -> None:
        profile = chosen.get("profile")
        if profile is None:
            return
        request = Path.home() / ".config" / "gtk-apps" / "editor-request"
        try:
            request.parent.mkdir(parents=True, exist_ok=True)
            request.write_text(profile.id + "\n", encoding="utf-8")
        except OSError as exc:
            status.set_text(str(exc))
            return
        exe = quick._which("gtk-theme-editor") or "gtk-theme-editor"
        quick._launch_detached([exe])
        GLib.idle_add(Gtk.main_quit)

    area.connect("draw", _draw)
    combo.connect("changed", _changed)
    apply_btn.connect("clicked", _apply)
    edit_btn.connect("clicked", _edit)
    return box


def configs_page() -> Gtk.Widget:
    box = _page()
    root = Path.home() / "configs"
    box.pack_start(_note(str(root)), False, False, 0)
    if not root.is_dir():
        box.pack_start(_note("Configs folder was not found."), False, False, 0)
        return box
    lst = Gtk.ListBox()
    lst.set_selection_mode(Gtk.SelectionMode.SINGLE)
    lst.get_style_context().add_class("neuronix-list")
    files: list[Path] = []
    skip_dirs = {"secrets", ".git", "__pycache__"}
    skip_suf = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".odt", ".pdf"}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in skip_dirs for part in rel.parts):
            continue
        if path.suffix.lower() in skip_suf:
            continue
        try:
            if path.stat().st_size > 256_000:
                continue
        except OSError:
            continue
        files.append(path)
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("neuronix-list-row")
        lab = Gtk.Label(label=str(rel), xalign=0.0)
        lab.set_ellipsize(Pango.EllipsizeMode.END)
        lab.get_style_context().add_class("neuronix-row-title")
        row.add(lab)
        row._path = path  # type: ignore[attr-defined]
        lst.add(row)
    scroll = Gtk.ScrolledWindow()
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_size_request(-1, 160)
    scroll.add(lst)
    box.pack_start(scroll, False, False, 0)
    buf = Gtk.TextBuffer()
    view = Gtk.TextView.new_with_buffer(buf)
    view.set_monospace(True)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_style_context().add_class("neuronix-text")
    text_scroll = Gtk.ScrolledWindow()
    text_scroll.get_style_context().add_class("neuronix-well")
    text_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    text_scroll.set_vexpand(True)
    text_scroll.set_size_request(-1, 240)
    text_scroll.add(view)
    box.pack_start(text_scroll, True, True, 0)
    current: dict = {"path": None}
    buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    save = _button("Save")
    edit = _button("Open in editor")
    buttons.pack_start(save, False, False, 0)
    buttons.pack_start(edit, False, False, 0)
    box.pack_start(buttons, False, False, 0)
    msg = _note("")
    box.pack_start(msg, False, False, 0)

    def _show(_lb, row) -> None:
        path = getattr(row, "_path", None)
        if path is None:
            return
        current["path"] = path
        try:
            buf.set_text(path.read_text(encoding="utf-8", errors="replace"))
            msg.set_text(str(path.relative_to(root)))
        except OSError as exc:
            msg.set_text(str(exc))

    def _save(*_a) -> None:
        path = current.get("path")
        if path is None:
            return
        try:
            path.write_text(buf.get_text(*buf.get_bounds(), True), encoding="utf-8")
            msg.set_text("Saved")
        except OSError as exc:
            msg.set_text(str(exc))

    def _open(*_a) -> None:
        path = current.get("path")
        if path is None:
            return
        exe = quick._which("gtk-edit") or "gtk-edit"
        quick._launch_detached([exe, str(path)])

    lst.connect("row-activated", _show)
    save.connect("clicked", _save)
    edit.connect("clicked", _open)
    return box


def screensaver_page() -> Gtk.Widget:
    box = _page()
    idle = 300
    mode = "clock"
    if _SCREEN_INI.is_file():
        cfg = configparser.ConfigParser()
        try:
            cfg.read(_SCREEN_INI)
            idle = cfg.getint("idle", "seconds", fallback=idle)
            mode = cfg.get("screensaver", "mode", fallback=mode)
        except (configparser.Error, OSError, ValueError):
            pass
    box.pack_start(_section("Idle"), False, False, 0)
    idle_combo = Gtk.ComboBoxText()
    idle_values = [sec for sec, _label in _SCREEN_IDLE]
    for sec, label in _SCREEN_IDLE:
        idle_combo.append_text(label)
    if idle in idle_values:
        idle_combo.set_active(idle_values.index(idle))
    else:
        idle_combo.append_text(f"{idle} seconds")
        idle_combo.set_active(len(idle_values))
        idle_values.append(idle)
    box.pack_start(idle_combo, False, False, 0)
    box.pack_start(_section("Style"), False, False, 0)
    mode_combo = Gtk.ComboBoxText()
    mode_ids = [mid for mid, _label in _SCREEN_MODES]
    for _mid, label in _SCREEN_MODES:
        mode_combo.append_text(label)
    mode_combo.set_active(mode_ids.index(mode) if mode in mode_ids else 0)
    box.pack_start(mode_combo, False, False, 0)
    msg = _note("")
    save = _button("Save")

    def _save(*_a) -> None:
        sec = idle_values[idle_combo.get_active()] if idle_combo.get_active() >= 0 else 300
        mid = mode_ids[mode_combo.get_active()] if mode_combo.get_active() >= 0 else "clock"
        _SCREEN_DIR.mkdir(parents=True, exist_ok=True)
        cfg = configparser.ConfigParser()
        if _SCREEN_INI.is_file():
            cfg.read(_SCREEN_INI)
        if not cfg.has_section("idle"):
            cfg.add_section("idle")
        if not cfg.has_section("screensaver"):
            cfg.add_section("screensaver")
        cfg.set("idle", "seconds", str(sec))
        cfg.set("screensaver", "mode", mid)
        try:
            with _SCREEN_INI.open("w", encoding="utf-8") as fh:
                cfg.write(fh)
            msg.set_text("Saved")
        except OSError as exc:
            msg.set_text(str(exc))

    enabled = _button("Enable idle screensaver")

    def _enable(*_a) -> None:
        ok, out = _run(["systemctl", "--user", "enable", "--now", _SCREEN_UNIT], timeout=15)
        msg.set_text("Enabled" if ok else (out or "Could not enable the idle service"))

    save.connect("clicked", _save)
    enabled.connect("clicked", _enable)
    box.pack_start(save, False, False, 0)
    box.pack_start(enabled, False, False, 0)
    box.pack_start(msg, False, False, 0)
    return box


def system_page() -> Gtk.Widget:
    box = _page()
    os_name = platform.system()
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                os_name = line.split("=", 1)[1].strip().strip('"')
                break
    except OSError:
        pass
    uptime = "—"
    try:
        secs = int(float(Path("/proc/uptime").read_text().split()[0]))
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{rem // 60}m")
        uptime = " ".join(parts)
    except OSError:
        pass
    cpu = platform.processor() or "—"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    ram = "—"
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, val = line.partition(":")
            mem[key.strip()] = int(val.split()[0])
        ram = f"{(mem['MemTotal'] - mem['MemAvailable']) // 1024} / {mem['MemTotal'] // 1024} MB"
    except (OSError, KeyError, ValueError):
        pass
    gpu = "—"
    ok, lspci = _run(["lspci"], timeout=4)
    if ok:
        for line in lspci.splitlines():
            if any(token in line for token in ("VGA compatible", "3D controller", "Display controller")):
                gpu = line.split(":", 2)[-1].strip()
                break
    for label, value in (
        ("Hostname", platform.node() or "—"),
        ("OS", os_name),
        ("Kernel", platform.release()),
        ("Uptime", uptime),
        ("CPU", cpu),
        ("Cores", str(os.cpu_count() or "—")),
        ("Memory", ram),
        ("GPU", gpu),
    ):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        name = Gtk.Label(label=label, xalign=0.0)
        name.set_width_chars(12)
        name.get_style_context().add_class("neuronix-row-title")
        val = _note(value)
        row.pack_start(name, False, False, 0)
        row.pack_start(val, True, True, 0)
        box.pack_start(row, False, False, 0)

    box.pack_start(_section("Battery"), False, False, 0)
    _pack_battery(box)
    box.pack_start(_section("CPU"), False, False, 0)
    quick.pack_cpu_controls(
        box, quit_on_advanced=False, compact=True, include_btop=False, framed=False
    )
    box.pack_start(_section("Memory"), False, False, 0)
    quick.pack_memory_controls(
        box, quit_on_advanced=False, compact=True, include_btop=False, framed=False
    )
    btop = _button("Open btop…")
    btop.connect("clicked", lambda *_a: quick._open_btop_detached(quit_after=True))
    box.pack_start(btop, False, False, 0)
    return box


def keyboard_page() -> Gtk.Widget:
    box = _page()
    box.pack_start(_note("Layout is applied live and saved in the Hyprland input block."), False, False, 0)

    def _opt(key: str) -> str:
        ok, out = _run(["hyprctl", "getoption", f"input:{key}"], timeout=3)
        if not ok:
            return ""
        for line in out.splitlines():
            if "str:" in line:
                return line.split("str:", 1)[1].strip().strip('"')
        return ""

    fields = {}
    for key, label in (
        ("kb_layout", "Layout"),
        ("kb_variant", "Variant"),
        ("kb_options", "Options"),
        ("kb_model", "Model"),
    ):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cap = Gtk.Label(label=label, xalign=0.0)
        cap.set_width_chars(12)
        ent = Gtk.Entry()
        ent.set_hexpand(True)
        ent.set_text(_opt(key))
        row.pack_start(cap, False, False, 0)
        row.pack_start(ent, True, True, 0)
        box.pack_start(row, False, False, 0)
        fields[key] = ent
    msg = _note("")
    apply = _button("Apply")

    def _apply(*_a) -> None:
        values = {key: ent.get_text().strip() for key, ent in fields.items()}
        if not values["kb_layout"]:
            values["kb_layout"] = "us"
        errors = []
        for key, val in values.items():
            ok, out = _run(["hyprctl", "keyword", f"input:{key}", val], timeout=3)
            if not ok:
                errors.append(out or key)
        conf = Path.home() / ".config" / "hypr" / "hyprland.conf"
        if not conf.is_file():
            conf = Path.home() / "configs" / "hypr" / "hyprland.conf"
        if conf.is_file():
            try:
                text = conf.read_text(encoding="utf-8")
                for key, val in values.items():
                    import re

                    pat = re.compile(rf"(?m)^(\s*){re.escape(key)}\s*=.*$")
                    if pat.search(text):
                        text = pat.sub(rf"\1{key} = {val}", text, count=1)
                conf.write_text(text, encoding="utf-8")
            except OSError as exc:
                errors.append(str(exc))
        msg.set_text("Applied" if not errors else "; ".join(errors))

    apply.connect("clicked", _apply)
    box.pack_start(apply, False, False, 0)
    box.pack_start(msg, False, False, 0)
    return box


_UPDATE = {
    "running": False,
    "status": "Installs available package upgrades.",
    "log": "",
    "sink": None,
}


def _update_emit(kind: str, text: str) -> None:
    """Append log text or replace the status line on the open Updates page."""
    sink = _UPDATE.get("sink")

    def _do(current=sink) -> bool:
        if _UPDATE.get("sink") is not current or current is None:
            return False
        if kind == "log":
            buf = current["buf"]
            buf.insert(buf.get_end_iter(), text)
            current["view"].scroll_to_iter(buf.get_end_iter(), 0.0, False, 0.0, 1.0)
        elif kind == "status":
            current["status"].set_text(text)
        elif kind == "idle":
            current["button"].set_sensitive(True)
        return False

    GLib.idle_add(_do)


def _run_apt(password: str, argv: list[str]) -> int:
    cmd = ["sudo", "-k", "-S", "-p", "", "--"]
    stdbuf = "/usr/bin/stdbuf"
    if os.path.isfile(stdbuf):
        cmd.extend([stdbuf, "-oL", "-eL"])
    cmd.extend(argv)
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["APT_LISTCHANGES_FRONTEND"] = "none"
    env["NEEDRESTART_MODE"] = "a"
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
    except OSError as exc:
        _update_emit("log", str(exc) + "\n")
        return 127
    assert proc.stdin is not None and proc.stdout is not None
    try:
        proc.stdin.write(password + "\n")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    for line in proc.stdout:
        _UPDATE["log"] += line
        _update_emit("log", line)
    return proc.wait()


def _update_worker(password: str) -> None:
    steps = (
        ("Running apt update…", ["apt", "update"], "sudo apt update"),
        (
            "Running apt upgrade…",
            [
                "apt",
                "upgrade",
                "-y",
                "-o",
                "Dpkg::Options::=--force-confdef",
                "-o",
                "Dpkg::Options::=--force-confold",
            ],
            "sudo apt upgrade -y",
        ),
    )
    ok = True
    for status, argv, shown in steps:
        _UPDATE["status"] = status
        _update_emit("status", status)
        header = f"$ {shown}\n"
        _UPDATE["log"] += header
        _update_emit("log", header)
        if _run_apt(password, argv) != 0:
            ok = False
            break
        _UPDATE["log"] += "\n"
        _update_emit("log", "\n")
    _UPDATE["running"] = False
    if ok:
        _UPDATE["status"] = "Upgrade finished."
        _update_emit("status", _UPDATE["status"])
        _update_emit("idle", "ok")
    else:
        _UPDATE["status"] = "Update failed. Check the output below."
        _update_emit("status", _UPDATE["status"])
        _update_emit("idle", "fail")


def _ask_sudo_password() -> str | None:
    """Modal password dialog. Uses its own loop so closing it leaves Settings open."""
    import neuronix_choice_dialog as choice

    choice._apply_css()
    result: dict = {"value": None, "done": False}
    loop = GLib.MainLoop()
    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title("Sudo password")
    win.set_decorated(False)
    win.set_resizable(False)
    win.get_style_context().add_class("neuronix-choice")
    choice.center_layer_window(win, 440, 230)
    release_keys = choice.hold_layer_keyboard(win)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.get_style_context().add_class("neuronix-root")
    choice._glass_root(outer)
    win.add(outer)

    def _finish(value: str | None):
        if result["done"]:
            return False
        result["done"] = True
        result["value"] = value
        release_keys()
        loop.quit()
        return False

    title = Gtk.Label(label="Sudo password", xalign=0.0)
    title.get_style_context().add_class("neuronix-title")
    choice.pack_title_with_close(outer, title, lambda: _finish(None))

    prompt = Gtk.Label(label="Enter your sudo password to upgrade.", xalign=0.0)
    prompt.set_line_wrap(True)
    prompt.set_max_width_chars(42)
    prompt.get_style_context().add_class("neuronix-subtitle")
    outer.pack_start(prompt, False, False, 0)

    ent = Gtk.Entry()
    ent.set_visibility(False)
    ent.set_activates_default(True)
    ent.get_style_context().add_class("neuronix-entry")
    try:
        ent.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    except Exception:
        pass
    outer.pack_start(ent, False, False, 0)

    cancel = Gtk.Button(label="Cancel")
    cancel.set_relief(Gtk.ReliefStyle.NONE)
    cancel.set_focus_on_click(False)
    cancel.get_style_context().add_class("neuronix-secondary")
    upgrade = Gtk.Button(label="Upgrade")
    upgrade.set_relief(Gtk.ReliefStyle.NONE)
    upgrade.set_focus_on_click(False)
    upgrade.get_style_context().add_class("neuronix-primary")
    upgrade.set_can_default(True)

    def _ok(*_a) -> None:
        if not ent.get_text():
            ent.grab_focus()
            return
        _finish(ent.get_text())

    cancel.connect("clicked", lambda *_: _finish(None))
    upgrade.connect("clicked", _ok)
    ent.connect("activate", _ok)
    outer.pack_start(choice._action_row(cancel, upgrade), False, False, 0)
    win.set_default(upgrade)
    win.connect(
        "key-press-event",
        lambda _w, event: _finish(None) if event.keyval == Gdk.KEY_Escape else False,
    )
    win.connect("destroy", lambda *_: _finish(None))
    win.show_all()
    win.present()
    ent.grab_focus()
    loop.run()
    if win.get_realized():
        win.hide()
    win.destroy()
    return result["value"]


def updates_page() -> Gtk.Widget:
    box = _page()
    box.pack_start(
        _note("Runs apt update, then installs available upgrades."),
        False,
        False,
        0,
    )
    button = _button("Upgrade")
    box.pack_start(button, False, False, 0)
    status = _note(_UPDATE["status"])
    box.pack_start(status, False, False, 0)

    buf = Gtk.TextBuffer()
    if _UPDATE["log"]:
        buf.set_text(_UPDATE["log"])
    view = Gtk.TextView.new_with_buffer(buf)
    view.set_editable(False)
    view.set_monospace(True)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_style_context().add_class("neuronix-text")
    scroll = Gtk.ScrolledWindow()
    scroll.get_style_context().add_class("neuronix-well")
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)
    scroll.set_size_request(-1, 280)
    scroll.add(view)
    box.pack_start(scroll, True, True, 0)

    sink = {"buf": buf, "view": view, "status": status, "button": button}
    _UPDATE["sink"] = sink

    def _drop(*_a) -> None:
        if _UPDATE.get("sink") is sink:
            _UPDATE["sink"] = None

    box.connect("destroy", _drop)

    if _UPDATE["running"]:
        button.set_sensitive(False)

    def _start(*_a) -> None:
        if _UPDATE["running"]:
            return
        password = _ask_sudo_password()
        if not password:
            return
        _UPDATE["running"] = True
        _UPDATE["log"] = ""
        _UPDATE["status"] = "Running apt update…"
        buf.set_text("")
        status.set_text(_UPDATE["status"])
        button.set_sensitive(False)
        threading.Thread(target=_update_worker, args=(password,), daemon=True).start()

    button.connect("clicked", _start)
    return box


def about_page() -> Gtk.Widget:
    box = _page()
    box.pack_start(
        _note(
            "Settings for this desktop. Wi-Fi, displays, sound, Bluetooth, "
            "themes, and configs open here from the Waybar."
        ),
        False,
        False,
        0,
    )
    author = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    author_name = Gtk.Label(label="Author", xalign=0.0)
    author_name.set_width_chars(12)
    author_name.get_style_context().add_class("neuronix-row-title")
    author.pack_start(author_name, False, False, 0)
    author.pack_start(_note("Kevin Hinds"), True, True, 0)
    box.pack_start(author, False, False, 0)

    repo = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    repo_name = Gtk.Label(label="Repository", xalign=0.0)
    repo_name.set_width_chars(12)
    repo_name.get_style_context().add_class("neuronix-row-title")
    link = Gtk.Label(xalign=0.0)
    link.set_markup(
        '<a href="https://github.com/khinds10-Neuronix/Neuronix">github.com/khinds10-Neuronix/Neuronix</a>'
    )
    link.get_style_context().add_class("neuronix-subtitle")
    repo.pack_start(repo_name, False, False, 0)
    repo.pack_start(link, True, True, 0)
    box.pack_start(repo, False, False, 0)
    return box
