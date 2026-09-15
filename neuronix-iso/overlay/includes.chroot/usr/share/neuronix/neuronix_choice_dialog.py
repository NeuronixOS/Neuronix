#!/usr/bin/env python3
"""Shared Neuronix GTK choice dialog — spacious action cards (not a packed zenity table)."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell, Pango  # noqa: E402

_SINGLETON_LOCKS: list[int] = []


def _singleton_key(title: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", (title or "dialog").lower()).strip("-")
    return key or "dialog"


def _lock_pid(fd: int) -> Optional[int]:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 64).decode("utf-8", "replace").strip()
        return int(raw)
    except Exception:
        return None


def _try_exclusive_lock(path: str) -> Tuple[int, bool]:
    import fcntl

    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd, True
    except OSError:
        return fd, False


def _signal_toggle(pid: int) -> bool:
    """Ask the live panel to close. False if that PID is already gone."""
    try:
        os.kill(pid, signal.SIGUSR2)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def _acquire_choice_singleton(title: str) -> bool:
    """One panel of this title. A second Waybar click closes it instead of stacking."""
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    os.makedirs(runtime, exist_ok=True)
    path = os.path.join(runtime, f"neuronix-choice-{_singleton_key(title)}.lock")
    fd, got = _try_exclusive_lock(path)
    if not got:
        pid = _lock_pid(fd)
        try:
            os.close(fd)
        except Exception:
            pass
        if pid and _signal_toggle(pid):
            return False
        fd, got = _try_exclusive_lock(path)
        if not got:
            pid = _lock_pid(fd)
            try:
                os.close(fd)
            except Exception:
                pass
            if pid:
                _signal_toggle(pid)
            return False
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        os.ftruncate(fd, 0)
    except Exception:
        pass
    os.write(fd, str(os.getpid()).encode("utf-8"))
    _SINGLETON_LOCKS.append(fd)
    return True


def begin_waybar_popover(title: str) -> bool:
    """Return True if this process should show the panel.

    A second Waybar click of the same panel closes it (GNOME-style toggle).
    Nested/follow-up dialogs in the same process keep the existing lock.
    """
    def _quit(*_a):
        GLib.idle_add(Gtk.main_quit)
        return True

    try:
        signal.signal(signal.SIGUSR2, _quit)
    except Exception:
        pass
    if _SINGLETON_LOCKS:
        return True
    return _acquire_choice_singleton(title)

CSS_TEMPLATE = """
window.neuronix-choice {{
  background-color: transparent;
  color: {fg};
}}
box.neuronix-root {{
  background-color: {surface};
  border: 3px solid {border};
  border-radius: 16px;
  padding: 14px;
}}
label.neuronix-title {{
  color: {fg};
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.01em;
}}
label.neuronix-subtitle {{
  color: {muted};
  font-size: 11px;
  font-weight: 500;
}}
button.neuronix-tile {{
  background-color: {tile};
  background-image: none;
  color: {fg};
  border: 1px solid {btn_border};
  border-radius: 8px;
  box-shadow: none;
  outline: none;
  padding: 8px 12px;
  margin: 0;
  min-height: 52px;
}}
button.neuronix-tile:hover {{
  background-color: {btn_hover};
  border-color: {btn_border};
}}
button.neuronix-tile label.neuronix-row-title {{
  color: {fg};
  font-size: 13px;
  font-weight: 600;
}}
button.neuronix-tile label.neuronix-row-desc {{
  color: {muted};
  font-size: 10px;
  font-weight: 500;
}}
button.neuronix-tile label.neuronix-chevron {{
  color: {muted};
  font-size: 16px;
  font-weight: 600;
  padding-left: 4px;
}}
button.neuronix-tile:hover label.neuronix-row-title,
button.neuronix-tile:hover label.neuronix-row-desc,
button.neuronix-tile:hover label.neuronix-chevron {{
  color: {fg};
}}
button.neuronix-xclose {{
  background-color: {tile};
  background-image: none;
  color: {fg};
  border: 1px solid {btn_border};
  border-radius: 999px;
  box-shadow: none;
  padding: 0;
  margin: 0;
  min-width: 32px;
  min-height: 32px;
  font-size: 16px;
  font-weight: 700;
}}
button.neuronix-xclose:hover {{
  background-color: {btn_hover};
  color: {fg};
}}
label.neuronix-body {{
  color: {fg};
  font-size: 12px;
  font-weight: 500;
}}
entry.neuronix-entry, entry {{
  background-color: {tile};
  color: {fg};
  border: 1px solid {border};
  border-radius: 10px;
  padding: 8px 10px;
  min-height: 36px;
}}
scrolledwindow.neuronix-scroll {{
  border: none;
  background-color: transparent;
}}
scrolledwindow.neuronix-list-frame {{
  background-color: {tile};
  border: 1px solid {border};
  border-radius: 12px;
}}
scrolledwindow.neuronix-list-frame > viewport,
scrolledwindow.neuronix-list-frame > viewport > list,
scrolledwindow.neuronix-list-frame list {{
  background-color: transparent;
  border: none;
}}
list.neuronix-list, listbox.neuronix-list {{
  background-color: transparent;
  border: none;
}}
row.neuronix-list-row {{
  background-color: transparent;
  border-radius: 0;
  padding: 8px 12px;
  margin: 0;
  min-height: 40px;
  border-bottom: 1px solid {border};
}}
row.neuronix-list-row:last-child {{
  border-bottom: none;
}}
row.neuronix-list-row:hover {{
  background-color: {surface};
}}
row.neuronix-list-row:selected {{
  background-color: {accent};
}}
row.neuronix-list-row.current:not(:selected) {{
  background-color: {surface};
}}
row.neuronix-list-row label {{
  color: {fg};
  font-size: 12px;
}}
row.neuronix-list-row label.neuronix-row-title {{
  color: {fg};
  font-size: 13px;
  font-weight: 600;
}}
row.neuronix-list-row label.neuronix-row-desc {{
  color: {muted};
  font-size: 11px;
  font-weight: 500;
}}
row.neuronix-list-row:selected label,
row.neuronix-list-row:selected label.neuronix-row-title,
row.neuronix-list-row:selected label.neuronix-row-desc {{
  color: {on_accent};
}}
row.neuronix-list-row:hover label,
row.neuronix-list-row:hover label.neuronix-row-title {{
  color: {fg};
}}
row.neuronix-list-row:hover label.neuronix-row-desc {{
  color: {muted};
}}
row.neuronix-list-row:selected:hover label,
row.neuronix-list-row:selected:hover label.neuronix-row-title,
row.neuronix-list-row:selected:hover label.neuronix-row-desc {{
  color: {on_accent};
}}
textview.neuronix-text, textview.neuronix-text text {{
  background-color: {tile};
  color: {fg};
  font-size: 12px;
  border-radius: 12px;
}}
button.neuronix-primary,
button.neuronix-secondary,
button.neuronix-toggle-on,
button.neuronix-toggle-off {{
  background-color: {tile};
  background-image: none;
  color: {fg};
  border: 1px solid {btn_border};
  border-radius: 8px;
  box-shadow: none;
  outline: none;
  padding: 8px 18px;
  font-size: 12px;
  font-weight: 600;
  min-height: 36px;
}}
button.neuronix-primary:hover,
button.neuronix-secondary:hover,
button.neuronix-toggle-on:hover,
button.neuronix-toggle-off:hover {{
  background-color: {btn_hover};
  border-color: {btn_border};
  color: {fg};
  opacity: 1;
}}
button.neuronix-toggle-on {{
  border-color: {accent};
}}
calendar.neuronix-cal {{
  background-color: {tile};
  color: {fg};
  border-radius: 12px;
}}
scale.neuronix-scale {{
  padding: 4px 0;
}}
scale.neuronix-scale trough {{
  background-color: {tile};
  border-radius: 999px;
  min-height: 8px;
}}
scale.neuronix-scale highlight {{
  background-color: {accent};
  border-radius: 999px;
}}
scale.neuronix-scale slider {{
  background-color: {fg};
  border-radius: 999px;
  min-width: 18px;
  min-height: 18px;
}}
label.neuronix-pct {{
  color: {muted};
  font-size: 12px;
  font-weight: 600;
  min-width: 40px;
}}
"""


def _hex_to_rgba(h: str, a: float) -> str:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return f"rgba(46, 46, 46, {a:.2f})"
    return f"rgba({r}, {g}, {b}, {a:.2f})"


def _enable_rgba(win: Gtk.Window) -> None:
    """Let CSS alpha actually punch through to the wallpaper."""
    try:
        screen = win.get_screen()
        visual = screen.get_rgba_visual() if screen is not None else None
        if visual is not None:
            win.set_visual(visual)
        win.set_app_paintable(True)
    except Exception:
        pass


def _mix_hex(a: str, b: str, t: float) -> str:
    def parse(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    try:
        ar, ag, ab = parse(a)
        br, bg, bb = parse(b)
    except Exception:
        return a
    r = int(ar + (br - ar) * t)
    g = int(ag + (bg - ag) * t)
    b_ = int(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{b_:02x}"


def _theme_chrome() -> dict[str, str]:
    """Pull suite profile colors when gtk-theme is available."""
    bg, fg, accent = "#2c2c2e", "#f5f5f5", "#3584e4"
    try:
        sys.path.insert(0, "/usr/share/neuronix/gtk-theme/python")
        from gtk_theme import load_profile  # type: ignore

        p = load_profile()
        bg, fg = p.background, p.foreground
        try:
            accent = p.accent()
        except Exception:
            pass
    except Exception:
        pass
    surface = _mix_hex(bg, fg, 0.08)
    tile = _mix_hex(bg, fg, 0.18)
    border = _mix_hex(bg, fg, 0.22)
    # GTK Theme Editor "Normal" button: darker fill, lighter outline.
    btn_border = _mix_hex(bg, fg, 0.42)
    btn_hover = _mix_hex(bg, fg, 0.26)
    muted = _mix_hex(fg, bg, 0.40)
    on_accent = "#ffffff"
    try:
        ar, ag, ab = int(accent.lstrip("#")[0:2], 16), int(accent.lstrip("#")[2:4], 16), int(accent.lstrip("#")[4:6], 16)
        if (0.2126 * ar + 0.7152 * ag + 0.0722 * ab) / 255.0 > 0.55:
            on_accent = "#1a1a1a"
    except Exception:
        pass
    return {
        "bg": bg,
        "fg": fg,
        "surface": surface,
        "border": border,
        "tile": tile,
        "btn_border": btn_border,
        "btn_hover": btn_hover,
        "accent": accent,
        "on_accent": on_accent,
        "muted": muted,
    }


def _apply_css() -> None:
    chrome = _theme_chrome()
    css = CSS_TEMPLATE.format(**chrome).encode("utf-8")
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    # USER priority so we beat Adwaita's scrolledwindow border/undershoot
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
    )


def _hypr_json(args: list[str]):
    return json.loads(subprocess.check_output(args, text=True, timeout=1))


def _hypr_cursor_xy() -> Optional[Tuple[int, int]]:
    try:
        pos = subprocess.check_output(["hyprctl", "cursorpos"], text=True, timeout=1).strip()
        parts = [p.strip() for p in pos.split(",")]
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def _hypr_monitor_logical_size(mon: dict) -> Tuple[int, int]:
    """Layout width/height for a Hypr monitor (swap for 90°/270° transform).

    hyprctl reports the mode size (e.g. 3840x2160) even when the output is
    rotated; layer-shell / cursor coords use the post-transform layout box.
    """
    w = int(mon.get("width", 0) or 0)
    h = int(mon.get("height", 0) or 0)
    try:
        transform = int(mon.get("transform", 0) or 0) % 4
    except Exception:
        transform = 0
    if transform in (1, 3):
        return h, w
    return w, h


def _hypr_monitor_at_point(x: int, y: int) -> Optional[dict]:
    try:
        for mon in _hypr_json(["hyprctl", "monitors", "-j"]):
            mx, my = int(mon.get("x", 0)), int(mon.get("y", 0))
            mw, mh = _hypr_monitor_logical_size(mon)
            if mw <= 0 or mh <= 0:
                continue
            if mx <= x < mx + mw and my <= y < my + mh:
                return mon
    except Exception:
        pass
    return None


def _waybar_height(mon_name: str, fallback: int = 32) -> int:
    try:
        layers = _hypr_json(["hyprctl", "layers", "-j"])
        info = layers.get(mon_name) or {}
        for level in (info.get("levels") or {}).values():
            for surf in level:
                if surf.get("namespace") == "waybar":
                    return max(int(surf.get("h") or fallback), 1)
    except Exception:
        pass
    return fallback


_frozen_click_xy: Optional[Tuple[int, int]] = None


def freeze_click_xy(xy: Optional[Tuple[int, int]] = None) -> Optional[Tuple[int, int]]:
    """Remember the pointer from the Waybar click for the rest of this process."""
    global _frozen_click_xy
    if xy is not None:
        _frozen_click_xy = (int(xy[0]), int(xy[1]))
        return _frozen_click_xy
    if _frozen_click_xy is not None:
        return _frozen_click_xy
    env = (os.environ.get("NEURONIX_CLICK_XY") or "").replace(" ", "")
    if env and "," in env:
        try:
            a, b = env.split(",", 1)
            _frozen_click_xy = (int(a), int(b))
            return _frozen_click_xy
        except Exception:
            pass
    _frozen_click_xy = _hypr_cursor_xy()
    return _frozen_click_xy


def waybar_popover_geom(
    width: int,
    height: int,
    gap: int = 2,
    cursor: Optional[Tuple[int, int]] = None,
) -> Optional[Tuple[int, int, dict]]:
    """Global top-left for a popover hung under Waybar at the click.

    Returns (x, y, hypr_monitor) or None if this does not look like a bar click.
    """
    cur = cursor if cursor is not None else freeze_click_xy()
    if cur is None:
        return None
    x, y = cur
    mon = _hypr_monitor_at_point(x, y)
    if mon is None:
        return None
    mx, my = int(mon.get("x", 0)), int(mon.get("y", 0))
    mw, mh = _hypr_monitor_logical_size(mon)
    if mw <= 0 or mh <= 0:
        return None
    bar_h = _waybar_height(str(mon.get("name") or ""), 32)
    left = int(x - width / 2)
    left = max(mx + 8, min(left, mx + mw - width - 8))
    top = my + bar_h + gap
    if top + height > my + mh - 8:
        top = max(my + bar_h + gap, my + mh - height - 8)
    return left, top, mon


def _gdk_monitor_at(display, x: int, y: int):
    try:
        mon = display.get_monitor_at_point(int(x), int(y))
        if mon is not None:
            return mon
    except Exception:
        pass
    return None


def _gdk_monitor_at_origin(display, x: int, y: int):
    n = display.get_n_monitors()
    for i in range(n):
        mon = display.get_monitor(i)
        geo = mon.get_geometry()
        if int(geo.x) == int(x) and int(geo.y) == int(y):
            return mon
    return None


def _hypr_cursor_monitor(display):
    """Hyprland cursor/focus — Gdk pointer is stuck at 0,0 on Wayland."""
    try:
        cur = freeze_click_xy()
        if cur is not None:
            mon = _gdk_monitor_at(display, cur[0], cur[1])
            if mon is not None:
                return mon
    except Exception:
        pass
    try:
        monitors = json.loads(
            subprocess.check_output(["hyprctl", "monitors", "-j"], text=True, timeout=1)
        )
        for hm in monitors:
            if not hm.get("focused"):
                continue
            mon = _gdk_monitor_at_origin(display, int(hm.get("x", 0)), int(hm.get("y", 0)))
            if mon is not None:
                return mon
    except Exception:
        pass
    return None


def _pointer_monitor():
    """Monitor under the Waybar click (Hyprland), not Gdk's bogus 0,0 / missing primary."""
    display = Gdk.Display.get_default()
    if display is None:
        return None
    mon = _hypr_cursor_monitor(display)
    if mon is not None:
        return mon
    n = display.get_n_monitors()
    landscape = None
    for i in range(n):
        candidate = display.get_monitor(i)
        geo = candidate.get_geometry()
        if geo.width >= geo.height:
            landscape = candidate
            break
    if landscape is not None:
        return landscape
    primary = display.get_primary_monitor()
    if primary is not None:
        return primary
    if n > 0:
        return display.get_monitor(0)
    return None


def _pin_layer_to_click(win: Gtk.Window, width: int, height: int) -> None:
    """Recompute layer-shell monitor + margins from the frozen Waybar click."""
    freeze_click_xy()
    w, h = int(width), int(height)
    try:
        alloc = win.get_allocation()
        if int(alloc.width) >= 50:
            w = int(alloc.width)
        if int(alloc.height) >= 50:
            h = int(alloc.height)
    except Exception:
        pass
    pop = waybar_popover_geom(w, h)
    if pop is None:
        return
    gx, gy, hmon = pop
    display = Gdk.Display.get_default()
    gdk_mon = None
    if display is not None:
        gdk_mon = _gdk_monitor_at_origin(
            display, int(hmon.get("x", 0)), int(hmon.get("y", 0))
        ) or _gdk_monitor_at(display, gx, gy)
    if gdk_mon is not None:
        try:
            GtkLayerShell.set_monitor(win, gdk_mon)
        except Exception:
            pass
    mx, my = int(hmon.get("x", 0)), int(hmon.get("y", 0))
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, max(8, gx - mx))
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, max(8, gy - my))


def center_layer_window(win: Gtk.Window, width: int, height: int) -> None:
    """Pin a gtk-layer-shell surface under Waybar at the click, else monitor center."""
    _enable_rgba(win)
    try:
        already = False
        try:
            already = bool(GtkLayerShell.is_layer_window(win))
        except Exception:
            already = False
        if not already:
            GtkLayerShell.init_for_window(win)
    except Exception:
        GtkLayerShell.init_for_window(win)
    try:
        GtkLayerShell.set_namespace(win, "neuronix-popover")
    except Exception:
        pass
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.ON_DEMAND)
    GtkLayerShell.set_exclusive_zone(win, 0)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, False)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.BOTTOM, False)
    try:
        win.set_size_request(int(width), int(height))
        win.resize(int(width), int(height))
    except Exception:
        pass

    _pin_layer_to_click(win, width, height)
    if waybar_popover_geom(width, height) is None:
        mon = _pointer_monitor()
        if mon is not None:
            try:
                GtkLayerShell.set_monitor(win, mon)
            except Exception:
                pass
            geo = mon.get_geometry()
            left = max(12, (int(geo.width) - int(width)) // 2)
            top = max(12, (int(geo.height) - int(height)) // 2)
        else:
            left, top = 200, 120
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, left)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, top)

    def _repin(*_a):
        _pin_layer_to_click(win, width, height)
        return False

    GLib.idle_add(_repin)
    try:
        win.connect("map", lambda *_: _repin())
    except Exception:
        pass


def _center_layer(win: Gtk.Window, width: int, height: int) -> None:
    center_layer_window(win, width, height)


def make_close_x_button(on_close) -> Gtk.Button:
    """Circular top-right close, GNOME quick-settings style."""
    btn = Gtk.Button(label="×")
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_focus_on_click(False)
    btn.set_valign(Gtk.Align.CENTER)
    btn.set_halign(Gtk.Align.END)
    btn.set_tooltip_text("Close")
    btn.get_style_context().add_class("neuronix-xclose")
    btn.connect("clicked", lambda *_: on_close())
    return btn


def pack_title_with_close(parent: Gtk.Box, title_widget: Gtk.Widget, on_close) -> Gtk.Box:
    """Title on the left, × close on the top-right."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    title_widget.set_hexpand(True)
    try:
        title_widget.set_ellipsize(Pango.EllipsizeMode.END)
    except Exception:
        pass
    row.pack_start(title_widget, True, True, 0)
    row.pack_end(make_close_x_button(on_close), False, False, 0)
    parent.pack_start(row, False, False, 0)
    return row


def _make_tile(item_id: str, label: str, desc: str, on_pick) -> Gtk.Button:
    btn = Gtk.Button()
    btn.get_style_context().add_class("neuronix-tile")
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_hexpand(True)
    btn.set_halign(Gtk.Align.FILL)

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    text.set_halign(Gtk.Align.START)
    text.set_valign(Gtk.Align.CENTER)
    text.set_hexpand(True)
    t = Gtk.Label(label=label, xalign=0.0)
    t.get_style_context().add_class("neuronix-row-title")
    t.set_ellipsize(Pango.EllipsizeMode.END)
    d = Gtk.Label(label=desc, xalign=0.0)
    d.set_ellipsize(Pango.EllipsizeMode.END)
    d.get_style_context().add_class("neuronix-row-desc")
    text.pack_start(t, False, False, 0)
    if desc:
        text.pack_start(d, False, False, 0)
    chev = Gtk.Label(label="›")
    chev.get_style_context().add_class("neuronix-chevron")
    chev.set_valign(Gtk.Align.CENTER)
    row.pack_start(text, True, True, 0)
    row.pack_end(chev, False, False, 0)
    btn.add(row)
    btn.connect("clicked", lambda _b, i=item_id: on_pick(i))
    return btn


def choose(
    title: str,
    subtitle: str,
    items: Sequence[Tuple[str, str, str]],
    *,
    width: int = 520,
    height: int = 560,
    on_pick: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Show a GNOME-style quick-settings choice panel.

    items: (id, label, description). Returns selected id, or None if cancelled.
    """
    freeze_click_xy()
    if not begin_waybar_popover(title):
        return None
    _apply_css()
    selected: Dict[str, Optional[str]] = {"id": None}

    n = max(1, len(items))
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols
    panel_w = 392
    row_h = 54
    gap = 8
    pad = 14
    header_h = 40 + (28 if subtitle else 0)
    panel_h = pad + header_h + 8 + rows * row_h + max(0, rows - 1) * gap + pad
    panel_h = min(max(panel_h, 120), int(height) if height else 640)

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title(title)
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_default_size(panel_w, panel_h)
    win.set_size_request(panel_w, panel_h)
    win.get_style_context().add_class("neuronix-choice")
    GLib.set_prgname("neuronix-choice")
    try:
        Gdk.set_program_class("neuronix-choice")
    except Exception:
        pass

    _center_layer(win, panel_w, panel_h)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.get_style_context().add_class("neuronix-root")
    outer.set_hexpand(True)
    outer.set_vexpand(True)
    win.add(outer)

    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    pack_title_with_close(outer, title_lbl, lambda: Gtk.main_quit())

    if subtitle:
        sub = Gtk.Label(label=subtitle, xalign=0.0)
        sub.set_line_wrap(True)
        sub.set_max_width_chars(42)
        sub.get_style_context().add_class("neuronix-subtitle")
        outer.pack_start(sub, False, False, 0)

    def _pick(item_id: str) -> None:
        selected["id"] = item_id
        if on_pick:
            GLib.idle_add(lambda: (on_pick(item_id), False)[1])
        Gtk.main_quit()

    grid = Gtk.Grid()
    grid.set_column_homogeneous(True)
    grid.set_column_spacing(gap)
    grid.set_row_spacing(gap)
    grid.set_hexpand(True)

    for i, (item_id, label, desc) in enumerate(items):
        btn = _make_tile(item_id, label, desc, _pick)
        r, c = divmod(i, cols)
        span = 2 if (cols == 2 and i == n - 1 and n % 2 == 1) else 1
        if span == 2:
            c = 0
        grid.attach(btn, c, r, span, 1)

    outer.pack_start(grid, True, True, 0)

    win.connect(
        "key-press-event",
        lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else False,
    )
    win.connect("destroy", lambda *_: Gtk.main_quit())

    win.show_all()
    win.present()
    Gtk.main()
    return selected["id"]


def _base_panel(
    title: str,
    *,
    width: int,
    height: int,
    subtitle: str = "",
) -> Tuple[Gtk.Window, Gtk.Box, Dict[str, Optional[str]]]:
    """Shared chrome for nested popovers (same slot as the choice panel)."""
    freeze_click_xy()
    if not begin_waybar_popover(title):
        raise SystemExit(0)
    _apply_css()
    result: Dict[str, Optional[str]] = {"value": None}

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title(title)
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_default_size(int(width), int(height))
    win.set_size_request(int(width), int(height))
    win.get_style_context().add_class("neuronix-choice")
    GLib.set_prgname("neuronix-choice")
    try:
        Gdk.set_program_class("neuronix-choice")
    except Exception:
        pass
    center_layer_window(win, int(width), int(height))

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.get_style_context().add_class("neuronix-root")
    outer.set_hexpand(True)
    outer.set_vexpand(True)
    win.add(outer)

    def _close(*_a):
        Gtk.main_quit()
        return False

    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    pack_title_with_close(outer, title_lbl, _close)

    if subtitle:
        sub = Gtk.Label(label=subtitle, xalign=0.0)
        sub.set_line_wrap(True)
        sub.set_max_width_chars(48)
        sub.get_style_context().add_class("neuronix-subtitle")
        outer.pack_start(sub, False, False, 0)

    win.connect(
        "key-press-event",
        lambda _w, e: _close() if e.keyval == Gdk.KEY_Escape else False,
    )
    win.connect("destroy", _close)
    return win, outer, result


def _action_row(*buttons: Gtk.Widget) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.set_halign(Gtk.Align.END)
    for b in buttons:
        row.pack_start(b, False, False, 0)
    return row


def message(
    title: str,
    body: str,
    *,
    kind: str = "info",
    width: int = 440,
    height: int = 200,
) -> None:
    """Info / warning / error panel under the Waybar click."""
    _ = kind  # reserved for future accent tinting
    win, outer, _result = _base_panel(title, width=width, height=height)
    body_lbl = Gtk.Label(label=body, xalign=0.0)
    body_lbl.set_line_wrap(True)
    body_lbl.set_max_width_chars(52)
    body_lbl.get_style_context().add_class("neuronix-body")
    outer.pack_start(body_lbl, True, True, 0)

    ok = Gtk.Button(label="OK")
    ok.get_style_context().add_class("neuronix-primary")
    ok.connect("clicked", lambda *_: Gtk.main_quit())
    outer.pack_start(_action_row(ok), False, False, 0)

    win.show_all()
    win.present()
    Gtk.main()


def text_panel(
    title: str,
    body: str,
    *,
    subtitle: str = "",
    width: int = 520,
    height: int = 420,
    monospace: bool = False,
) -> None:
    """Scrollable text panel (status / logs) under the Waybar click."""
    win, outer, _result = _base_panel(
        title, width=width, height=height, subtitle=subtitle
    )

    buf = Gtk.TextBuffer()
    buf.set_text(body or "")
    view = Gtk.TextView.new_with_buffer(buf)
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_style_context().add_class("neuronix-text")
    if monospace:
        try:
            view.override_font(Pango.FontDescription("monospace 11"))
        except Exception:
            pass

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-scroll")
    scroll.set_hexpand(True)
    scroll.set_vexpand(True)
    scroll.add(view)
    outer.pack_start(scroll, True, True, 0)

    ok = Gtk.Button(label="Close")
    ok.get_style_context().add_class("neuronix-primary")
    ok.connect("clicked", lambda *_: Gtk.main_quit())
    outer.pack_start(_action_row(ok), False, False, 0)

    win.show_all()
    win.present()
    Gtk.main()


def entry(
    title: str,
    prompt: str,
    *,
    default: str = "",
    width: int = 440,
    height: int = 220,
) -> Optional[str]:
    """Single-line entry under the Waybar click. Returns text or None."""
    win, outer, result = _base_panel(
        title, width=width, height=height, subtitle=prompt
    )

    ent = Gtk.Entry()
    ent.get_style_context().add_class("neuronix-entry")
    ent.set_text(default or "")
    ent.set_activates_default(True)
    outer.pack_start(ent, False, False, 0)

    cancel = Gtk.Button(label="Cancel")
    cancel.get_style_context().add_class("neuronix-secondary")
    ok = Gtk.Button(label="OK")
    ok.get_style_context().add_class("neuronix-primary")
    ok.set_can_default(True)

    def _ok(*_a):
        result["value"] = ent.get_text()
        Gtk.main_quit()

    cancel.connect("clicked", lambda *_: Gtk.main_quit())
    ok.connect("clicked", _ok)
    ent.connect("activate", _ok)
    outer.pack_start(_action_row(cancel, ok), False, False, 0)

    win.set_default(ok)
    win.show_all()
    win.present()
    ent.grab_focus()
    Gtk.main()
    return result["value"]


def pick_one(
    title: str,
    rows: Sequence[str],
    *,
    subtitle: str = "",
    width: int = 480,
    height: int = 520,
    searchable: bool = True,
    current: str = "",
) -> Optional[str]:
    """Searchable single-select list under the Waybar click."""
    win, outer, result = _base_panel(
        title, width=width, height=height, subtitle=subtitle
    )

    search = Gtk.SearchEntry() if searchable else None
    if search is not None:
        search.set_placeholder_text("Search cities or regions…")
        outer.pack_start(search, False, False, 0)

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.get_style_context().add_class("neuronix-list")
    listbox.set_hexpand(True)
    listbox.set_vexpand(True)

    current_row: Optional[Gtk.ListBoxRow] = None
    for text in rows:
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("neuronix-list-row")
        city, region = _timezone_labels(text)
        if region:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            t = Gtk.Label(label=city, xalign=0.0)
            t.get_style_context().add_class("neuronix-row-title")
            t.set_ellipsize(Pango.EllipsizeMode.END)
            d = Gtk.Label(label=region if text != current else f"{region}  ·  current", xalign=0.0)
            d.get_style_context().add_class("neuronix-row-desc")
            d.set_ellipsize(Pango.EllipsizeMode.END)
            box.pack_start(t, False, False, 0)
            box.pack_start(d, False, False, 0)
            row.add(box)
        else:
            lbl = Gtk.Label(label=city, xalign=0.0)
            lbl.get_style_context().add_class("neuronix-row-title")
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            row.add(lbl)
        row._neuronix_value = text  # type: ignore[attr-defined]
        row._neuronix_search = f"{city} {region} {text}".lower()  # type: ignore[attr-defined]
        if current and text == current:
            row.get_style_context().add_class("current")
            current_row = row
        listbox.add(row)

    def _filter(row: Gtk.ListBoxRow) -> bool:
        if search is None:
            return True
        q = (search.get_text() or "").strip().lower()
        if not q:
            return True
        hay = getattr(row, "_neuronix_search", "") or getattr(row, "_neuronix_value", "") or ""
        return q in str(hay).lower()

    listbox.set_filter_func(_filter)
    if search is not None:
        search.connect("search-changed", lambda *_: listbox.invalidate_filter())

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-scroll")
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_hexpand(True)
    scroll.set_vexpand(True)
    scroll.add(listbox)
    outer.pack_start(scroll, True, True, 0)

    cancel = Gtk.Button(label="Cancel")
    cancel.get_style_context().add_class("neuronix-secondary")
    ok = Gtk.Button(label="Select")
    ok.get_style_context().add_class("neuronix-primary")

    def _accept(row: Optional[Gtk.ListBoxRow] = None) -> None:
        chosen = row or listbox.get_selected_row()
        if chosen is None:
            return
        result["value"] = str(getattr(chosen, "_neuronix_value", "") or "")
        Gtk.main_quit()

    cancel.connect("clicked", lambda *_: Gtk.main_quit())
    ok.connect("clicked", lambda *_: _accept())
    listbox.connect("row-activated", lambda _lb, row: _accept(row))
    outer.pack_start(_action_row(cancel, ok), False, False, 0)

    win.show_all()
    win.present()
    if current_row is not None:
        listbox.select_row(current_row)

        def _scroll_current(*_a):
            try:
                alloc = current_row.get_allocation()
                adj = scroll.get_vadjustment()
                if adj is not None and alloc.height > 0:
                    adj.set_value(max(0, alloc.y - (adj.get_page_size() - alloc.height) / 2))
            except Exception:
                pass
            return False

        GLib.idle_add(_scroll_current)
    if search is not None:
        search.grab_focus()
    Gtk.main()
    return result["value"]


def _timezone_labels(tz: str) -> Tuple[str, str]:
    """America/New_York → ('New York', 'America')."""
    raw = (tz or "").strip()
    if not raw:
        return "", ""
    parts = raw.split("/")
    city = parts[-1].replace("_", " ")
    if len(parts) == 1:
        return city, ""
    region = " / ".join(p.replace("_", " ") for p in parts[:-1])
    return city, region


def pick_timezone(
    zones: Sequence[str],
    *,
    current: str = "",
    width: int = 440,
    height: int = 560,
) -> Optional[str]:
    """GNOME Settings-style timezone picker under the Waybar click."""
    cur = (current or "").strip()
    subtitle = f"Current: {cur}" if cur else "Choose a time zone"
    return pick_one(
        "Time zone",
        list(zones),
        subtitle=subtitle,
        width=width,
        height=height,
        searchable=True,
        current=cur,
    )


def pick_date(
    title: str,
    *,
    subtitle: str = "",
    width: int = 440,
    height: int = 380,
) -> Optional[str]:
    """Calendar date picker under the Waybar click. Returns YYYY-MM-DD or None."""
    import datetime as _dt

    win, outer, result = _base_panel(
        title, width=width, height=height, subtitle=subtitle
    )
    today = _dt.date.today()
    cal = Gtk.Calendar()
    cal.get_style_context().add_class("neuronix-cal")
    cal.set_display_options(
        Gtk.CalendarDisplayOptions.SHOW_HEADING
        | Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
    )
    cal.select_month(today.month - 1, today.year)
    cal.select_day(today.day)
    outer.pack_start(cal, True, True, 0)

    cancel = Gtk.Button(label="Cancel")
    cancel.get_style_context().add_class("neuronix-secondary")
    ok = Gtk.Button(label="OK")
    ok.get_style_context().add_class("neuronix-primary")

    def _ok(*_a):
        y, m, d = cal.get_date()
        result["value"] = f"{int(y):04d}-{int(m) + 1:02d}-{int(d):02d}"
        Gtk.main_quit()

    cancel.connect("clicked", lambda *_: Gtk.main_quit())
    ok.connect("clicked", _ok)
    outer.pack_start(_action_row(cancel, ok), False, False, 0)

    win.show_all()
    win.present()
    Gtk.main()
    return result["value"]


def main_cli() -> int:
    argv = list(sys.argv[1:])
    if not argv:
        print(
            "Usage: neuronix_choice_dialog.py TITLE SUBTITLE id|label|desc ...\n"
            "   or: neuronix_choice_dialog.py message|text|entry|list|timezone|calendar ...",
            file=sys.stderr,
        )
        return 2

    cmd = argv[0]
    if cmd == "message":
        # message [--kind=info] TITLE BODY
        kind = "info"
        rest = argv[1:]
        if rest and rest[0].startswith("--kind="):
            kind = rest[0].split("=", 1)[1] or "info"
            rest = rest[1:]
        if len(rest) < 2:
            print("Usage: message [--kind=info|warning|error] TITLE BODY", file=sys.stderr)
            return 2
        message(rest[0], rest[1], kind=kind)
        return 0

    if cmd == "text":
        # text TITLE [--subtitle=SUB] --body-file PATH
        rest = argv[1:]
        body_file = ""
        subtitle = ""
        title = ""
        while rest:
            arg = rest[0]
            if arg.startswith("--subtitle="):
                subtitle = arg.split("=", 1)[1]
                rest = rest[1:]
                continue
            if arg == "--subtitle" and len(rest) > 1:
                subtitle = rest[1]
                rest = rest[2:]
                continue
            if arg.startswith("--body-file="):
                body_file = arg.split("=", 1)[1]
                rest = rest[1:]
                continue
            if arg == "--body-file" and len(rest) > 1:
                body_file = rest[1]
                rest = rest[2:]
                continue
            if not title:
                title = arg
                rest = rest[1:]
                continue
            break
        if not title or not body_file:
            print(
                "Usage: text TITLE [--subtitle=SUB] --body-file PATH",
                file=sys.stderr,
            )
            return 2
        with open(body_file, encoding="utf-8", errors="replace") as f:
            body = f.read()
        text_panel(title, body, subtitle=subtitle)
        return 0

    if cmd == "entry":
        # entry TITLE PROMPT [--default=VAL]
        rest = argv[1:]
        default = ""
        if rest and rest[-1].startswith("--default="):
            default = rest[-1].split("=", 1)[1]
            rest = rest[:-1]
        if len(rest) < 2:
            print("Usage: entry TITLE PROMPT [--default=VAL]", file=sys.stderr)
            return 2
        val = entry(rest[0], rest[1], default=default)
        if val is None:
            return 1
        print(val)
        return 0

    if cmd == "list":
        # list TITLE SUBTITLE [--current=VAL] [ROW ...]  (or rows on stdin)
        rest = argv[1:]
        current = ""
        filtered: list[str] = []
        for a in rest:
            if a.startswith("--current="):
                current = a.split("=", 1)[1]
            else:
                filtered.append(a)
        if len(filtered) < 2:
            print("Usage: list TITLE SUBTITLE [--current=VAL] [ROW ...]", file=sys.stderr)
            return 2
        title, subtitle = filtered[0], filtered[1]
        rows = list(filtered[2:])
        if not rows:
            rows = [ln.strip() for ln in sys.stdin if ln.strip()]
        val = pick_one(title, rows, subtitle=subtitle, current=current)
        if val is None:
            return 1
        print(val)
        return 0

    if cmd == "timezone":
        # timezone [--current=ZONE]   zones on stdin
        current = ""
        for a in argv[1:]:
            if a.startswith("--current="):
                current = a.split("=", 1)[1]
        rows = [ln.strip() for ln in sys.stdin if ln.strip()]
        if not rows:
            print("Usage: timezone [--current=ZONE]  < zones.txt", file=sys.stderr)
            return 2
        val = pick_timezone(rows, current=current)
        if val is None:
            return 1
        print(val)
        return 0

    if cmd == "calendar":
        # calendar TITLE [SUBTITLE]
        if len(argv) < 2:
            print("Usage: calendar TITLE [SUBTITLE]", file=sys.stderr)
            return 2
        title = argv[1]
        subtitle = argv[2] if len(argv) > 2 else ""
        val = pick_date(title, subtitle=subtitle)
        if val is None:
            return 1
        print(val)
        return 0

    if cmd == "choose":
        argv = argv[1:]

    # Legacy / default: TITLE SUBTITLE id|label|desc ...
    if len(argv) < 3:
        print(
            "Usage: neuronix_choice_dialog.py TITLE SUBTITLE id|label|desc ...",
            file=sys.stderr,
        )
        return 2
    title, subtitle = argv[0], argv[1]
    items: List[Tuple[str, str, str]] = []
    for raw in argv[2:]:
        parts = raw.split("|", 2)
        if len(parts) != 3:
            print(f"bad item: {raw}", file=sys.stderr)
            return 2
        items.append((parts[0], parts[1], parts[2]))
    pick = choose(title, subtitle, items)
    if pick:
        print(pick)
        return 0
    return 1


if __name__ == "__main__":
    os.environ.setdefault("XDG_CURRENT_DESKTOP", "Hyprland")
    raise SystemExit(main_cli())
