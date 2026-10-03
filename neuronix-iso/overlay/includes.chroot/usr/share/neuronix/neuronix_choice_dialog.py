#!/usr/bin/env python3
"""Shared Neuronix GTK choice dialog — spacious action cards (not a packed zenity table)."""
from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import sys

import cairo
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GObject, GtkLayerShell, Pango  # noqa: E402

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


_HUB_CONTROL: Dict[str, object] = {"active": False, "section": "", "switch": None}


def _settings_request_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    os.makedirs(runtime, exist_ok=True)
    return os.path.join(runtime, "neuronix-settings.request")


def _write_settings_request(section: str, drill: str) -> None:
    with open(_settings_request_path(), "w", encoding="utf-8") as handle:
        handle.write((section or "") + "\n" + (drill or "") + "\n")


def _read_settings_request() -> Tuple[str, str]:
    try:
        lines = open(_settings_request_path(), encoding="utf-8").read().splitlines()
    except Exception:
        return "", ""
    section = lines[0].strip() if lines else ""
    drill = lines[1].strip() if len(lines) > 1 else ""
    return section, drill


def _hub_signal(*_args):
    def _go() -> bool:
        section, drill = _read_settings_request()
        current = str(_HUB_CONTROL.get("section") or "")
        switch = _HUB_CONTROL.get("switch")
        if section and section != current and callable(switch):
            switch(section, drill)
        else:
            Gtk.main_quit()
        return False

    GLib.idle_add(_go)
    return True


def begin_settings_hub(section: str, drill: str = "") -> bool:
    """One combined settings window.

    A second click of the section already on screen closes it.
    A click of a different section switches the open window.
    """
    _HUB_CONTROL["active"] = True
    try:
        signal.signal(signal.SIGUSR2, _hub_signal)
    except Exception:
        pass
    if _SINGLETON_LOCKS:
        return True
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    os.makedirs(runtime, exist_ok=True)
    path = os.path.join(runtime, "neuronix-choice-neuronix-settings.lock")
    fd, got = _try_exclusive_lock(path)
    if not got:
        pid = _lock_pid(fd)
        try:
            os.close(fd)
        except Exception:
            pass
        _write_settings_request(section, drill)
        if pid and _signal_toggle(pid):
            return False
        fd, got = _try_exclusive_lock(path)
        if not got:
            try:
                os.close(fd)
            except Exception:
                pass
            return False
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        os.ftruncate(fd, 0)
    except Exception:
        pass
    os.write(fd, str(os.getpid()).encode("utf-8"))
    _SINGLETON_LOCKS.append(fd)
    _HUB_CONTROL["section"] = section
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
        if not _HUB_CONTROL.get("active"):
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
  background-color: transparent;
  background-image: none;
  border: 3px solid {border};
  border-radius: 8px;
  padding: 14px 16px;
  font-family: Sans;
}}
box.neuronix-sep {{
  background-color: {well_border};
  min-width: 1px;
}}
label.neuronix-title {{
  color: {fg};
  font-family: Sans;
  font-size: 22px;
  font-weight: 600;
}}
label.neuronix-heading {{
  color: {hint};
  font-family: Sans;
  font-size: 12px;
  font-weight: 600;
  margin-top: 12px;
  margin-bottom: 2px;
}}
label.neuronix-subtitle {{
  color: {hint};
  font-family: Sans;
  font-size: 13px;
  font-weight: 400;
}}
label a {{
  color: {accent};
}}
label a:hover {{
  color: {fg};
}}
button.neuronix-tile {{
  background-color: transparent;
  background-image: none;
  color: {fg};
  border: none;
  border-radius: 8px;
  box-shadow: none;
  outline: none;
  padding: 8px 10px;
  margin: 0;
  min-height: 0;
}}
button.neuronix-tile:hover,
button.neuronix-tile.selected {{
  background-color: {selection};
  border: none;
}}
button.neuronix-tile.selected label.neuronix-row-title,
button.neuronix-tile.selected label.neuronix-chevron,
button.neuronix-tile:hover label.neuronix-row-title,
button.neuronix-tile:hover label.neuronix-chevron {{
  color: {fg};
}}
button.neuronix-tile label.neuronix-row-title {{
  color: {fg};
  font-family: Sans;
  font-size: 15px;
  font-weight: 500;
}}
button.neuronix-tile label.neuronix-row-desc {{
  color: {hint};
  font-family: Sans;
  font-size: 11px;
  font-weight: 400;
}}
button.neuronix-tile label.neuronix-chevron {{
  color: {accent};
  font-family: Sans;
  font-size: 16px;
  font-weight: 400;
  padding-left: 8px;
}}
button.neuronix-tile:hover label.neuronix-row-title,
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
  font-weight: 400;
}}
button.neuronix-xclose:hover {{
  background-color: {btn_hover};
  color: {fg};
}}
label.neuronix-body {{
  color: {fg};
  font-family: Sans;
  font-size: 13px;
  font-weight: 400;
}}
entry.neuronix-entry, entry {{
  background-color: {tile};
  color: {fg};
  font-family: Sans;
  font-size: 11px;
  border: 1px solid {border};
  border-radius: 0;
  padding: 4px 8px;
  min-height: 0;
}}
window.neuronix-choice combobox button,
window.neuronix-choice combobox button.combo {{
  background-color: {tile};
  background-image: none;
  color: {fg};
  border: 1px solid {border};
  border-radius: 0;
  box-shadow: none;
  padding: 4px 8px;
  min-height: 0;
  font-family: Sans;
  font-size: 11px;
}}
window.neuronix-choice combobox button:hover {{
  background-color: {selection};
  color: {fg};
}}
window.neuronix-choice combobox button label,
window.neuronix-choice combobox button cellview {{
  color: {fg};
  background-color: transparent;
  background-image: none;
}}
window.neuronix-choice combobox arrow {{
  color: {fg};
  -gtk-icon-source: -gtk-icontheme("pan-down-symbolic");
  min-width: 16px;
  min-height: 16px;
}}
window.neuronix-choice combobox window.popup,
window.neuronix-choice combobox window.popup menu,
window.neuronix-choice combobox window.popup treeview,
window.neuronix-choice combobox window.popup treeview.view {{
  background-color: {tile};
  background-image: none;
  color: {fg};
  border: 1px solid {border};
}}
window.neuronix-choice combobox menuitem,
window.neuronix-choice combobox menuitem cellview {{
  color: {fg};
  background-color: transparent;
  background-image: none;
}}
window.neuronix-choice combobox menuitem:hover,
window.neuronix-choice combobox menuitem:selected,
window.neuronix-choice combobox window.popup treeview:selected,
window.neuronix-choice combobox window.popup treeview:selected:focus {{
  background-color: {selection};
  color: {fg};
}}
scrolledwindow.neuronix-scroll,
scrolledwindow.neuronix-list-frame,
scrolledwindow.neuronix-well {{
  background-color: transparent;
  background-image: none;
  border: 1px solid {well_border};
  border-radius: 8px;
  padding: 12px 14px;
}}
scrolledwindow.neuronix-scroll > viewport,
scrolledwindow.neuronix-list-frame > viewport,
scrolledwindow.neuronix-well > viewport,
scrolledwindow.neuronix-clear,
scrolledwindow.neuronix-clear > viewport,
scrolledwindow.neuronix-list-frame > viewport > list,
scrolledwindow.neuronix-list-frame list,
textview.neuronix-text,
textview.neuronix-text text {{
  background-color: transparent;
  background-image: none;
  border: none;
}}
list.neuronix-list, listbox.neuronix-list {{
  background-color: transparent;
  border: none;
}}
row.neuronix-list-row {{
  background-color: transparent;
  border-radius: 6px;
  padding: 6px 10px;
  margin: 1px 0;
  min-height: 0;
  border: none;
}}
row.neuronix-list-row:last-child {{
  border-bottom: none;
}}
row.neuronix-list-row:hover {{
  background-color: {selection};
}}
row.neuronix-list-row:selected {{
  background-color: {selection};
}}
row.neuronix-list-row.current:not(:selected) {{
  background-color: {surface};
}}
row.neuronix-list-row label {{
  color: {fg};
  font-family: Sans;
  font-size: 13px;
  font-weight: 500;
}}
row.neuronix-list-row label.neuronix-row-title {{
  color: {fg};
  font-family: Sans;
  font-size: 13px;
  font-weight: 500;
}}
row.neuronix-list-row label.neuronix-row-desc {{
  color: {hint};
  font-family: Sans;
  font-size: 11px;
  font-weight: 400;
}}
row.neuronix-list-row:selected label,
row.neuronix-list-row:selected label.neuronix-row-title {{
  color: {fg};
}}
row.neuronix-list-row:selected label.neuronix-row-desc {{
  color: {hint};
}}
row.neuronix-list-row:hover label,
row.neuronix-list-row:hover label.neuronix-row-title {{
  color: {fg};
}}
row.neuronix-list-row:hover label.neuronix-row-desc {{
  color: {hint};
}}
row.neuronix-list-row:selected:hover label,
row.neuronix-list-row:selected:hover label.neuronix-row-title {{
  color: {fg};
}}
row.neuronix-list-row:selected:hover label.neuronix-row-desc {{
  color: {hint};
}}
scrolledwindow.neuronix-list-frame label,
scrolledwindow.neuronix-list-frame row.neuronix-list-row label,
scrolledwindow.neuronix-list-frame row.neuronix-list-row label.neuronix-row-title,
scrolledwindow.neuronix-well label,
scrolledwindow.neuronix-well row.neuronix-list-row label,
scrolledwindow.neuronix-well row.neuronix-list-row label.neuronix-row-title,
scrolledwindow.neuronix-scroll label {{
  color: {fg};
  font-family: Sans;
  font-size: 11px;
  font-weight: 400;
}}
scrolledwindow.neuronix-list-frame label.neuronix-row-desc,
scrolledwindow.neuronix-list-frame row.neuronix-list-row label.neuronix-row-desc,
scrolledwindow.neuronix-well label.neuronix-row-desc,
scrolledwindow.neuronix-well row.neuronix-list-row label.neuronix-row-desc,
scrolledwindow.neuronix-scroll label.neuronix-row-desc {{
  color: {hint};
  font-family: Sans;
  font-size: 10px;
  font-weight: 400;
}}
textview.neuronix-text, textview.neuronix-text text {{
  background-color: transparent;
  background-image: none;
  color: {fg};
  font-family: Sans;
  font-size: 11px;
  border-radius: 0;
  padding: 4px 2px;
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
  padding: 6px 12px;
  font-family: Sans;
  font-size: 13px;
  font-weight: 500;
  min-height: 0;
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
button.neuronix-day {{
  background-color: transparent;
  background-image: none;
  color: {fg};
  font-family: Sans;
  font-size: 20px;
  font-weight: 500;
  border: none;
  border-radius: 8px;
  box-shadow: none;
  outline: none;
  padding: 0;
  min-width: 40px;
  min-height: 36px;
}}
button.neuronix-day:hover {{
  background-color: {selection};
  color: {fg};
}}
button.neuronix-day.neuronix-picked:not(.neuronix-today) {{
  background-color: {selection};
  color: {fg};
}}
button.neuronix-day.neuronix-today,
button.neuronix-day.neuronix-today:hover {{
  background-color: {accent};
  color: {on_accent};
}}
button.neuronix-day.neuronix-other,
button.neuronix-day.neuronix-other:hover {{
  background-color: transparent;
  color: {hint};
}}
calendar.neuronix-cal {{
  background-color: transparent;
  background-image: none;
  color: {fg};
  font-family: Sans;
  font-size: 30px;
  padding: 4px;
}}
calendar.neuronix-cal.header,
calendar.neuronix-cal.button,
calendar.neuronix-cal.day-name,
calendar.neuronix-cal.week-number {{
  background-color: transparent;
  background-image: none;
  color: {fg};
  font-family: Sans;
  font-size: 16px;
}}
calendar.neuronix-cal:selected {{
  background-color: {selection};
  color: {fg};
  border-radius: 8px;
}}
calendar.neuronix-cal.highlight,
calendar.neuronix-cal.highlight:selected {{
  background-color: {accent};
  color: {on_accent};
  border-radius: 8px;
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
  color: {fg};
  font-family: Sans;
  font-size: 14px;
  font-weight: 500;
  min-width: 40px;
}}
"""


def _force_background(widget: Gtk.Widget, red: float, green: float, blue: float, alpha: float) -> None:
    """GTK's theme paints text views and viewports with an opaque base color.
    override_background_color sits above that stylesheet, so a clear viewport
    lets the 40% well show the wallpaper through the glass dialog."""
    color = Gdk.RGBA()
    color.red = red
    color.green = green
    color.blue = blue
    color.alpha = alpha
    states = (
        Gtk.StateFlags.NORMAL,
        Gtk.StateFlags.ACTIVE,
        Gtk.StateFlags.PRELIGHT,
        Gtk.StateFlags.SELECTED,
        Gtk.StateFlags.INSENSITIVE,
        Gtk.StateFlags.BACKDROP,
    )
    for state in states:
        try:
            widget.override_background_color(state, color)
        except Exception:
            return


def _clear_widget_bg(widget: Gtk.Widget) -> None:
    _force_background(widget, 0.0, 0.0, 0.0, 0.0)
    child = None
    try:
        child = widget.get_child()
    except Exception:
        child = None
    if child is not None and child is not widget:
        _force_background(child, 0.0, 0.0, 0.0, 0.0)


def _style_text_well(scroll: Gtk.ScrolledWindow, view: Gtk.TextView) -> None:
    """Keep the text area clear so only the dialog's one glass layer shows."""

    def _on_map(*_args) -> bool:
        _force_background(scroll, 0.0, 0.0, 0.0, 0.0)
        child = None
        try:
            child = scroll.get_child()
        except Exception:
            child = None
        if child is not None:
            _force_background(child, 0.0, 0.0, 0.0, 0.0)
        _force_background(view, 0.0, 0.0, 0.0, 0.0)
        return False

    _on_map()
    scroll.connect("map", _on_map)
    view.connect("map", _on_map)


def _rounded_rect(cr, x: float, y: float, w: float, h: float, radius: float) -> None:
    r = max(0.0, min(radius, w / 2.0, h / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _glass_root(box: Gtk.Box) -> None:
    """One 50% glass fill for the whole dialog, including subpages."""

    def _draw(_widget, cr) -> bool:
        width = box.get_allocated_width()
        height = box.get_allocated_height()
        if width <= 1 or height <= 1:
            return False
        cr.save()
        _rounded_rect(cr, 0, 0, width, height, 8)
        rgb = _hex_rgb(_theme_chrome()["bg"]) or (46, 52, 64)
        cr.set_source_rgba(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 0.5)
        cr.fill()
        cr.restore()
        return False

    box.connect("draw", _draw)


def _hex_rgb(h: str) -> Optional[Tuple[int, int, int]]:
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _hex_to_rgba(h: str, a: float) -> str:
    rgb = _hex_rgb(h)
    if rgb is None:
        return f"rgba(46, 46, 46, {a:.2f})"
    r, g, b = rgb
    return f"rgba({r}, {g}, {b}, {a:.2f})"


def _relative_luminance(h: str) -> float:
    rgb = _hex_rgb(h)
    if rgb is None:
        return 0.0

    def channel(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _profile_catalog_paths() -> list[str]:
    home = os.path.expanduser("~")
    return [
        os.path.join(home, ".config/gtk-apps/custom-profiles.json"),
        os.path.join(home, ".local/share/neuronix/gtk-theme/profiles.json"),
        "/usr/local/lib/neuronix/gtk-apps/gtk-theme/profiles.json",
        "/usr/share/neuronix/gtk-theme/profiles.json",
        "/usr/local/lib/neuronix/gtk-apps/profiles.json",
    ]


def _active_profile() -> dict:
    """The profile named in ~/.config/gtk-apps/theme.toml."""
    profile_id = ""
    theme_path = os.path.expanduser("~/.config/gtk-apps/theme.toml")
    try:
        text = open(theme_path, encoding="utf-8").read()
    except OSError:
        text = ""
    match = re.search(r'(?m)^\s*profile\s*=\s*"([^"]+)"', text)
    if match:
        profile_id = match.group(1).strip()
    if not profile_id:
        return {}
    for path in _profile_catalog_paths():
        try:
            data = json.loads(open(path, encoding="utf-8").read())
        except (OSError, json.JSONDecodeError):
            continue
        items = data.get("profiles") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("id") == profile_id:
                return item
    return {}


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
    """Colors from the active gtk-theme profile, not a fixed Nord palette."""
    profile = _active_profile()
    bg = str(profile.get("background") or "#2e3440")
    fg = str(profile.get("foreground") or "#d8dee9")
    palette = profile.get("palette") if isinstance(profile.get("palette"), list) else []
    accent = palette[4] if len(palette) > 4 and isinstance(palette[4], str) else _mix_hex(bg, fg, 0.45)
    border = str(profile.get("border") or _mix_hex(bg, fg, 0.22))
    if _hex_rgb(bg) is None:
        bg = "#2e3440"
    if _hex_rgb(fg) is None:
        fg = "#d8dee9"
    if _hex_rgb(accent) is None:
        accent = _mix_hex(bg, fg, 0.45)
    if _hex_rgb(border) is None:
        border = _mix_hex(bg, fg, 0.22)
    selection = _mix_hex(bg, fg, 0.16)
    hint = _mix_hex(fg, bg, 0.38)
    well_border = _mix_hex(border, fg, 0.28)
    on_accent = "#1d2021" if _relative_luminance(accent) >= 0.45 else fg
    return {
        "bg": bg,
        "fg": fg,
        "surface": _hex_to_rgba(bg, 0.5),
        "border": border,
        "selection": selection,
        "tile": bg,
        "btn_border": border,
        "btn_hover": selection,
        "accent": accent,
        "on_accent": on_accent,
        "muted": hint,
        "hint": hint,
        "well": _hex_to_rgba(bg, 0.4),
        "well_border": well_border,
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


def _ensure_layer(win: Gtk.Window) -> None:
    try:
        already = bool(GtkLayerShell.is_layer_window(win))
    except Exception:
        already = False
    if not already:
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


def _waybar_reserved(mon_name: str) -> int:
    """Pixels from the top of the monitor through the bottom of Waybar.

    Layer-shell top margins start below that reserved strip, so centering has
    to subtract it or the window sits low by exactly the bar's bottom edge.
    """
    try:
        layers = _hypr_json(["hyprctl", "layers", "-j"])
        info = layers.get(mon_name) or {}
        for level in (info.get("levels") or {}).values():
            for surf in level:
                if surf.get("namespace") == "waybar":
                    return max(0, int(surf.get("y") or 0) + int(surf.get("h") or 0))
    except Exception:
        pass
    return 0


def _set_centered_margins(win: Gtk.Window, width: int, height: int) -> None:
    """Place the overlay in the middle of the monitor under the pointer."""
    w, h = max(1, int(width)), max(1, int(height))
    gdk = _pointer_monitor()
    hypr = None
    cur = freeze_click_xy()
    if cur is not None:
        hypr = _hypr_monitor_at_point(cur[0], cur[1])
    if hypr is None:
        try:
            for mon in _hypr_json(["hyprctl", "monitors", "-j"]):
                if mon.get("focused"):
                    hypr = mon
                    break
        except Exception:
            hypr = None
    if gdk is not None:
        try:
            GtkLayerShell.set_monitor(win, gdk)
        except Exception:
            pass
    if hypr is not None:
        mw, mh = _hypr_monitor_logical_size(hypr)
        reserved = _waybar_reserved(str(hypr.get("name") or ""))
    elif gdk is not None:
        geo = gdk.get_geometry()
        mw, mh = int(geo.width), int(geo.height)
        reserved = 0
    else:
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, 200)
        GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, 120)
        return
    left = max(0, (mw - w) // 2)
    top = max(0, (mh - h) // 2 - reserved)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, left)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, top)


def hold_layer_keyboard(win: Gtk.Window):
    """Keep keystrokes on this layer until the returned function is called.

    Settings takes an exclusive keyboard grab. A password dialog on top never
    sees keys while that grab is held, and a button click hands the keyboard
    back to Settings. Park every other layer and keep this one exclusive.
    """
    state: Dict[str, object] = {"on": True, "saved": []}

    def _apply() -> bool:
        if not state["on"]:
            return False
        saved: list = state["saved"]  # type: ignore[assignment]
        known = {id(top) for top, _prev in saved}
        try:
            tops = list(Gtk.Window.list_toplevels())
        except Exception:
            tops = []
        for top in tops:
            if top is win:
                continue
            try:
                if not GtkLayerShell.is_layer_window(top):
                    continue
                if id(top) in known:
                    GtkLayerShell.set_keyboard_mode(top, GtkLayerShell.KeyboardMode.NONE)
                    continue
                prev = GtkLayerShell.get_keyboard_mode(top)
                GtkLayerShell.set_keyboard_mode(top, GtkLayerShell.KeyboardMode.NONE)
                saved.append((top, prev))
            except Exception:
                pass
        try:
            GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        except Exception:
            pass
        return True

    def stop() -> None:
        if not state["on"]:
            return
        state["on"] = False
        for top, prev in list(state["saved"]):  # type: ignore[arg-type]
            try:
                GtkLayerShell.set_keyboard_mode(top, prev)
            except Exception:
                pass
        state["saved"] = []

    _apply()
    GLib.timeout_add(150, _apply)
    return stop


def center_layer_window(win: Gtk.Window, width: int, height: int) -> None:
    """Center a gtk-layer-shell surface. Safe to call again when the window grows."""
    _enable_rgba(win)
    _ensure_layer(win)
    w, h = int(width), int(height)
    try:
        win.set_size_request(w, h)
        win.resize(w, h)
    except Exception:
        pass
    _set_centered_margins(win, w, h)

    def _again(*_a, fallback_w=w, fallback_h=h):
        aw, ah = fallback_w, fallback_h
        try:
            alloc = win.get_allocation()
            if int(alloc.width) > 50:
                aw = int(alloc.width)
            if int(alloc.height) > 50:
                ah = int(alloc.height)
        except Exception:
            pass
        _set_centered_margins(win, aw, ah)
        return False

    GLib.idle_add(_again)
    if not getattr(win, "_neuronix_center_hook", False):
        try:
            win._neuronix_center_hook = True  # type: ignore[attr-defined]
            win.connect("map", lambda *_: GLib.idle_add(_again))
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


def pack_back_button(parent: Gtk.Box, on_back) -> Gtk.Button:
    """Back control pinned to the bottom-left of a dialog."""
    btn = Gtk.Button(label="Back")
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_halign(Gtk.Align.START)
    btn.set_valign(Gtk.Align.END)
    btn.get_style_context().add_class("neuronix-secondary")
    btn.connect("clicked", lambda *_: on_back())
    parent.pack_end(btn, False, False, 0)
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


def _menu_icon(item_id: str, icon: str = "") -> str:
    if icon:
        return icon
    return {
        "open": "folder-open",
        "status": "dialog-information",
        "start": "media-playback-start",
        "stop": "media-playback-stop",
        "restart": "view-refresh",
        "activity": "document-open-recent",
        "server": "network-server",
        "calendar": "x-office-calendar",
        "fmt12": "preferences-system-time",
        "fmt24": "preferences-system-time",
        "setclock": "document-edit",
        "timezone": "mark-location",
        "volume": "audio-volume-high",
        "output": "audio-card",
        "wifi": "network-wireless",
        "networks": "network-wireless",
        "ethernet": "network-wired",
        "usage": "utilities-system-monitor",
        "btop": "utilities-terminal",
        "logout": "system-log-out",
        "reboot": "system-reboot",
        "shutdown": "system-shutdown",
    }.get(item_id, "")


def _make_tile(
    item_id: str,
    label: str,
    desc: str,
    on_pick,
    *,
    show_chevron: bool = True,
    icon: str = "",
) -> Gtk.Button:
    btn = Gtk.Button()
    btn.get_style_context().add_class("neuronix-tile")
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_hexpand(True)
    btn.set_halign(Gtk.Align.FILL)

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    icon_name = _menu_icon(item_id, icon)
    if icon_name:
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DND)
        try:
            img.set_pixel_size(24)
        except Exception:
            pass
        img.set_valign(Gtk.Align.CENTER)
        img.get_style_context().add_class("neuronix-item-icon")
        row.pack_start(img, False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
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
    row.pack_start(text, True, True, 0)
    if show_chevron:
        chev = Gtk.Label(label="›")
        chev.get_style_context().add_class("neuronix-chevron")
        chev.set_valign(Gtk.Align.CENTER)
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
    panel_w = 480
    row_h = 72
    gap = 12
    header_h = 52 + (32 if subtitle else 0)
    panel_h = header_h + n * row_h + max(0, n - 1) * gap + 72
    panel_h = min(max(panel_h, 180), 520)

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
    _glass_root(outer)
    outer.set_hexpand(True)
    outer.set_vexpand(True)
    win.add(outer)

    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    pack_title_with_close(outer, title_lbl, lambda: Gtk.main_quit())
    pack_back_button(outer, Gtk.main_quit)

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

    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=gap)
    col.set_hexpand(True)
    for item_id, label, desc in items:
        col.pack_start(
            _make_tile(item_id, label, desc, _pick, show_chevron=False),
            False,
            False,
            0,
        )
    outer.pack_start(col, True, True, 0)

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
    _glass_root(outer)
    outer.set_hexpand(True)
    outer.set_vexpand(True)
    win.add(outer)

    def _close(*_a):
        try:
            win.hide()
        except Exception:
            pass
        Gtk.main_quit()
        return False

    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    pack_title_with_close(outer, title_lbl, _close)
    pack_back_button(outer, _close)

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
    win._neuronix_destroy_id = win.connect("destroy", _close)  # type: ignore[attr-defined]
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
    try:
        view.set_left_margin(6)
        view.set_right_margin(6)
        view.set_top_margin(4)
        view.set_bottom_margin(4)
    except Exception:
        pass
    if monospace:
        try:
            view.override_font(Pango.FontDescription("monospace 11"))
        except Exception:
            pass

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-scroll")
    scroll.get_style_context().add_class("neuronix-well")
    scroll.set_hexpand(True)
    scroll.set_vexpand(True)
    scroll.add(view)
    _style_text_well(scroll, view)
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
    secret: bool = False,
    width: int = 440,
    height: int = 320,
) -> Optional[str]:
    """Single-line entry under the Waybar click. Returns text or None."""
    win, outer, result = _base_panel(
        title, width=width, height=height, subtitle=prompt
    )

    ent = Gtk.Entry()
    ent.get_style_context().add_class("neuronix-entry")
    ent.set_text(default or "")
    ent.set_activates_default(True)
    if secret:
        ent.set_visibility(False)
        try:
            ent.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        except Exception:
            pass
    outer.pack_start(ent, False, False, 0)

    cancel = Gtk.Button(label="Cancel")
    cancel.get_style_context().add_class("neuronix-secondary")
    ok = Gtk.Button(label="OK")
    ok.get_style_context().add_class("neuronix-primary")
    ok.set_can_default(True)

    def _leave(value: Optional[str]) -> None:
        result["value"] = value
        try:
            win.hide()
        except Exception:
            pass
        Gtk.main_quit()

    def _ok(*_a):
        _leave(ent.get_text())

    cancel.set_label("Close")
    cancel.connect("clicked", lambda *_: _leave(None))
    ok.connect("clicked", _ok)
    ent.connect("activate", _ok)
    outer.pack_start(_action_row(cancel, ok), False, False, 0)

    win.set_default(ok)
    win.show_all()
    win.present()
    release_keys = hold_layer_keyboard(win)
    ent.grab_focus()
    try:
        Gtk.main()
    finally:
        release_keys()
        try:
            win.hide()
        except Exception:
            pass
        try:
            win.disconnect(win._neuronix_destroy_id)  # type: ignore[attr-defined]
        except Exception:
            pass
        win.destroy()
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
    scroll.get_style_context().add_class("neuronix-well")
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


class MonthCalendar(Gtk.Box):
    """Month grid with large day numbers. Today is accent-filled with black text."""

    __gtype_name__ = "NeuronixMonthCalendar"
    __gsignals__ = {
        "day-selected": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        import datetime as _dt

        today = _dt.date.today()
        self._today = today
        self._year = today.year
        self._month = today.month
        self._day = today.day

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        prev_btn = Gtk.Button(label="‹")
        prev_btn.get_style_context().add_class("neuronix-secondary")
        prev_btn.set_relief(Gtk.ReliefStyle.NONE)
        prev_btn.connect("clicked", lambda *_a: self._shift(-1))
        next_btn = Gtk.Button(label="›")
        next_btn.get_style_context().add_class("neuronix-secondary")
        next_btn.set_relief(Gtk.ReliefStyle.NONE)
        next_btn.connect("clicked", lambda *_a: self._shift(1))
        self._title = Gtk.Label(xalign=0.5)
        self._title.set_hexpand(True)
        self._title.get_style_context().add_class("neuronix-title")
        header.pack_start(prev_btn, False, False, 0)
        header.pack_start(self._title, True, True, 0)
        header.pack_end(next_btn, False, False, 0)
        self.pack_start(header, False, False, 0)

        self._grid = Gtk.Grid()
        self._grid.set_row_homogeneous(True)
        self._grid.set_column_homogeneous(True)
        self._grid.set_row_spacing(4)
        self._grid.set_column_spacing(4)
        self._grid.set_hexpand(True)
        self._grid.set_vexpand(True)
        self.pack_start(self._grid, True, True, 0)
        self._rebuild()

    def get_date(self) -> Tuple[int, int, int]:
        """Year, month (0-11), day. Same order as Gtk.Calendar."""
        return self._year, self._month - 1, self._day

    def _shift(self, delta: int) -> None:
        import calendar as _cal
        import datetime as _dt

        month = self._month + delta
        year = self._year
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        self._year = year
        self._month = month
        last = _cal.monthrange(year, month)[1]
        self._day = min(self._day, last)
        if year == self._today.year and month == self._today.month:
            self._day = self._today.day
        self._rebuild()
        self.emit("day-selected")

    def _pick(self, day: int) -> None:
        self._day = day
        self._rebuild()
        self.emit("day-selected")

    def _rebuild(self) -> None:
        import calendar as _cal
        import datetime as _dt

        for child in list(self._grid.get_children()):
            self._grid.remove(child)
        self._title.set_text(_dt.date(self._year, self._month, 1).strftime("%B %Y"))
        names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        for col, name in enumerate(names):
            label = Gtk.Label(label=name)
            label.get_style_context().add_class("neuronix-subtitle")
            self._grid.attach(label, col, 0, 1, 1)
        weeks = _cal.Calendar(firstweekday=6).monthdayscalendar(self._year, self._month)
        for row, week in enumerate(weeks, start=1):
            for col, day in enumerate(week):
                if day == 0:
                    self._grid.attach(Gtk.Label(label=""), col, row, 1, 1)
                    continue
                btn = Gtk.Button(label=str(day))
                btn.set_relief(Gtk.ReliefStyle.NONE)
                ctx = btn.get_style_context()
                ctx.add_class("neuronix-day")
                is_today = (
                    self._year == self._today.year
                    and self._month == self._today.month
                    and day == self._today.day
                )
                if is_today:
                    ctx.add_class("neuronix-today")
                elif day == self._day:
                    ctx.add_class("neuronix-picked")
                btn.connect("clicked", lambda *_a, d=day: self._pick(d))
                self._grid.attach(btn, col, row, 1, 1)
        self._grid.show_all()


def style_calendar(cal: Gtk.Calendar) -> None:
    """Large day numbers, with today filled in and drawn in black."""
    import datetime as _dt

    cal.get_style_context().add_class("neuronix-cal")
    cal.set_display_options(
        Gtk.CalendarDisplayOptions.SHOW_HEADING
        | Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
    )
    today = _dt.date.today()
    cal.select_month(today.month - 1, today.year)
    cal.select_day(today.day)

    def _mark(*_args) -> None:
        cal.clear_marks()
        year, month, _day = cal.get_date()
        if int(year) == today.year and int(month) == today.month - 1:
            cal.mark_day(today.day)

    _mark()
    cal.connect("month-changed", _mark)


def pick_date(
    title: str,
    *,
    subtitle: str = "",
    width: int = 440,
    height: int = 380,
) -> Optional[str]:
    """Calendar date picker under the Waybar click. Returns YYYY-MM-DD or None."""
    win, outer, result = _base_panel(
        title, width=width, height=height, subtitle=subtitle
    )
    cal = MonthCalendar()
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


class DrillItem:
    """One row in a centered menu. A panel or children opens on the right."""

    def __init__(
        self,
        item_id: str,
        label: str,
        desc: str = "",
        *,
        children: Optional[Sequence["DrillItem"]] = None,
        panel: Optional[Callable[[], Gtk.Widget]] = None,
        action: Optional[Callable[[str], None]] = None,
        icon: str = "",
    ) -> None:
        self.id = item_id
        self.label = label
        self.desc = desc or ""
        self.children = list(children or [])
        self.panel = panel
        self.action = action
        self.icon = icon or ""

    def opens_submenu(self) -> bool:
        return self.panel is not None or bool(self.children)


def make_text_page(body: str, *, monospace: bool = False) -> Gtk.Widget:
    """Scrollable text block for a drill-down submenu."""
    buf = Gtk.TextBuffer()
    buf.set_text(body or "")
    view = Gtk.TextView.new_with_buffer(buf)
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_style_context().add_class("neuronix-text")
    try:
        view.set_left_margin(6)
        view.set_right_margin(6)
        view.set_top_margin(4)
        view.set_bottom_margin(4)
    except Exception:
        pass
    if monospace:
        try:
            view.override_font(Pango.FontDescription("monospace 11"))
        except Exception:
            pass
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-scroll")
    scroll.get_style_context().add_class("neuronix-well")
    scroll.set_hexpand(True)
    scroll.set_vexpand(True)
    scroll.add(view)
    _style_text_well(scroll, view)
    return scroll


def _section_window_height(count: int, subtitle: str) -> int:
    extra = 48 if subtitle and "\n" in subtitle else (32 if subtitle else 0)
    return max(500, min(760, 140 + extra + max(1, count) * 72))


def attach_drill(
    parent: Gtk.Box,
    title: str,
    items: Sequence[DrillItem],
    *,
    subtitle: str = "",
    initial: Optional[str] = None,
    on_quit: Callable[[], None],
    on_change: Optional[Callable[[], None]] = None,
) -> Dict[str, object]:
    """Pack a drill menu into parent. Submenus replace the list in that column."""
    rows = list(items)
    selected: Dict[str, Optional[str]] = {"id": None, "open": None}

    def _changed() -> None:
        if on_change is not None:
            on_change()

    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    pack_title_with_close(parent, title_lbl, on_quit)

    if subtitle:
        sub = Gtk.Label(label=subtitle, xalign=0.0)
        sub.set_line_wrap(True)
        sub.set_max_width_chars(42)
        sub.get_style_context().add_class("neuronix-subtitle")
        parent.pack_start(sub, False, False, 0)

    stack = Gtk.Stack()
    stack.set_hexpand(True)
    stack.set_vexpand(True)
    try:
        stack.set_transition_type(Gtk.StackTransitionType.NONE)
    except Exception:
        pass
    parent.pack_start(stack, True, True, 0)

    main_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    main_page.set_hexpand(True)
    main_page.set_vexpand(True)
    sub_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    sub_page.set_hexpand(True)
    sub_page.set_vexpand(True)
    stack.add_named(main_page, "main")
    stack.add_named(sub_page, "sub")

    def _clear_sub() -> None:
        for child in list(sub_page.get_children()):
            sub_page.remove(child)

    back_btn: Dict[str, Optional[Gtk.Widget]] = {"w": None}

    def _show_back(visible: bool) -> None:
        widget = back_btn["w"]
        if widget is None:
            return
        if visible:
            widget.show()
        else:
            widget.hide()

    def collapse() -> None:
        selected["open"] = None
        stack.set_visible_child_name("main")
        _clear_sub()
        _show_back(False)
        _changed()

    def _run_leaf(item: DrillItem) -> None:
        selected["id"] = item.id
        if item.action:
            item.action(item.id)
            return
        on_quit()

    def open_item(item: DrillItem) -> None:
        if not item.opens_submenu():
            _run_leaf(item)
            return
        selected["open"] = item.id
        if item.panel is not None:
            widget = item.panel()
        else:
            widget = _child_column(item.children)
        _clear_sub()
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        heading = Gtk.Label(label=item.label, xalign=0.0)
        heading.get_style_context().add_class("neuronix-title")
        heading.set_hexpand(True)
        head.pack_start(heading, True, True, 0)
        sub_page.pack_start(head, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class("neuronix-clear")
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.connect("map", lambda *_a: _clear_widget_bg(scroll) or False)
        try:
            scroll.set_propagate_natural_width(False)
            scroll.set_propagate_natural_height(False)
            scroll.set_min_content_width(1)
            scroll.set_min_content_height(1)
        except Exception:
            pass
        scroll.add(widget)
        sub_page.pack_start(scroll, True, True, 0)
        stack.set_visible_child_name("sub")
        sub_page.show_all()
        _show_back(True)
        _changed()

    def _child_column(children: Sequence[DrillItem]) -> Gtk.Widget:
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for child in children:
            col.pack_start(
                _make_tile(
                    child.id,
                    child.label,
                    child.desc,
                    lambda i, c=child: open_item(c),
                    show_chevron=child.opens_submenu(),
                    icon=child.icon,
                ),
                False,
                False,
                0,
            )
        return col

    for item in rows:
        main_page.pack_start(
            _make_tile(
                item.id,
                item.label,
                item.desc,
                lambda i, it=item: open_item(it),
                show_chevron=item.opens_submenu(),
                icon=item.icon,
            ),
            False,
            False,
            0,
        )

    def _on_back() -> None:
        if selected["open"]:
            collapse()

    back = pack_back_button(parent, _on_back)
    back.set_no_show_all(True)
    back.hide()
    back_btn["w"] = back

    def _on_key(_w, event):
        if event.keyval != Gdk.KEY_Escape:
            return False
        if selected["open"]:
            collapse()
            return True
        on_quit()
        return True

    stack.set_visible_child_name("main")
    if initial:
        for item in rows:
            if item.id == initial and item.opens_submenu():
                GLib.idle_add(lambda it=item: (open_item(it), False)[1])
                break
    return {"on_key": _on_key, "selected": selected}


def attach_page(
    parent: Gtk.Box,
    title: str,
    widget: Gtk.Widget,
    *,
    on_quit: Callable[[], None],
) -> Dict[str, object]:
    """Fill the right column with one settings page."""
    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    pack_title_with_close(parent, title_lbl, on_quit)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-clear")
    scroll.set_hexpand(True)
    scroll.set_vexpand(True)
    scroll.add(widget)
    parent.pack_start(scroll, True, True, 0)

    def _on_key(_w, event):
        if event.keyval != Gdk.KEY_Escape:
            return False
        on_quit()
        return True

    return {"on_key": _on_key}


class HubSection:
    """One entry in the combined settings window."""

    def __init__(
        self,
        section_id: str,
        label: str,
        icon: str,
        build: Optional[Callable[[], Tuple[str, Sequence[DrillItem], Optional[str]]]] = None,
        page: Optional[Callable[[], Gtk.Widget]] = None,
    ) -> None:
        if build is None and page is None:
            raise ValueError(f"section {section_id} needs a menu or a page")
        self.id = section_id
        self.label = label
        self.icon = icon
        self.build = build
        self.page = page


class HubAction:
    """A bottom row that launches another app instead of changing the page."""

    def __init__(self, action_id: str, label: str, icon: str, run: Callable[[], None]) -> None:
        self.id = action_id
        self.label = label
        self.icon = icon
        self.run = run


def show_drilldown(
    title: str,
    items: Sequence[DrillItem],
    *,
    subtitle: str = "",
    width: int = 480,
    height: int = 0,
    split_width: int = 920,
    split_height: int = 520,
    initial: Optional[str] = None,
) -> Optional[str]:
    """Centered Fuzzel-style menu.

    A row with a panel or children replaces this list in the same window.
    A row with only an action runs it. Escape returns to the parent list first.
    """
    _ = split_width, split_height
    freeze_click_xy()
    if not begin_waybar_popover(title):
        return None
    _apply_css()
    rows = list(items)
    n = max(1, len(rows))
    panel_w = int(width)
    if int(height) > 0:
        panel_h = int(height)
    else:
        extra = 48 if subtitle and "\n" in subtitle else (32 if subtitle else 0)
        panel_h = min(760, 140 + extra + n * 72)
    selected: Dict[str, Optional[str]] = {"id": None}

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title(title)
    win.set_decorated(False)
    win.set_resizable(False)
    win.get_style_context().add_class("neuronix-choice")
    GLib.set_prgname("neuronix-choice")
    try:
        Gdk.set_program_class("neuronix-choice")
    except Exception:
        pass

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.get_style_context().add_class("neuronix-root")
    _glass_root(outer)
    win.add(outer)

    def _quit() -> None:
        Gtk.main_quit()

    def _lock_size() -> None:
        center_layer_window(win, panel_w, panel_h)
        geom = Gdk.Geometry()
        geom.min_width = panel_w
        geom.max_width = panel_w
        geom.min_height = panel_h
        geom.max_height = panel_h
        try:
            win.set_geometry_hints(
                win,
                geom,
                Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE,
            )
        except Exception:
            pass

    state = attach_drill(
        outer,
        title,
        rows,
        subtitle=subtitle,
        initial=initial,
        on_quit=_quit,
        on_change=_lock_size,
    )
    picked = state.get("selected")
    if isinstance(picked, dict):
        selected = picked

    win.connect("key-press-event", state["on_key"])
    win.connect("destroy", lambda *_: _quit())
    _lock_size()
    win.show_all()
    win.present()
    Gtk.main()
    return selected.get("id")


def show_hub(
    sections: Sequence[HubSection],
    initial_id: str,
    drill: str = "",
    actions: Sequence[HubAction] = (),
) -> None:
    """One centered window: section list on the left, that menu on the right."""
    freeze_click_xy()
    if not begin_settings_hub(initial_id, drill):
        return
    _apply_css()
    catalog = list(sections)
    by_id = {section.id: section for section in catalog}
    if initial_id not in by_id and catalog:
        initial_id = catalog[0].id

    nav_w = 220
    content_w = 720
    panel_w = nav_w + content_w + 72

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title("Settings")
    win.set_decorated(False)
    win.set_resizable(False)
    win.get_style_context().add_class("neuronix-choice")
    GLib.set_prgname("neuronix-choice")
    try:
        Gdk.set_program_class("neuronix-choice")
    except Exception:
        pass

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    outer.get_style_context().add_class("neuronix-root")
    _glass_root(outer)
    win.add(outer)

    body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    body.set_hexpand(True)
    body.set_vexpand(True)
    outer.pack_start(body, True, True, 0)

    nav_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    nav_col.set_size_request(nav_w, -1)
    nav_col.set_vexpand(True)
    body.pack_start(nav_col, False, False, 0)

    nav_scroll = Gtk.ScrolledWindow()
    nav_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    nav_scroll.set_vexpand(True)
    nav_scroll.get_style_context().add_class("neuronix-clear")
    nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    nav.set_size_request(nav_w, -1)
    nav_scroll.add(nav)
    nav_col.pack_start(nav_scroll, True, True, 0)

    sep = Gtk.Box()
    sep.set_size_request(1, -1)
    sep.set_vexpand(True)
    sep.get_style_context().add_class("neuronix-sep")
    body.pack_start(sep, False, False, 0)

    right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    right.set_size_request(content_w, -1)
    right.set_hexpand(True)
    right.set_vexpand(True)
    body.pack_start(right, True, True, 0)

    panel_h = 700
    size = {"h": panel_h}
    buttons: Dict[str, Gtk.Button] = {}

    def _quit() -> None:
        Gtk.main_quit()

    def _lock_size() -> None:
        panel_h = int(size["h"])
        center_layer_window(win, panel_w, panel_h)
        try:
            GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        except Exception:
            pass
        geom = Gdk.Geometry()
        geom.min_width = panel_w
        geom.max_width = panel_w
        geom.min_height = panel_h
        geom.max_height = panel_h
        try:
            win.set_geometry_hints(
                win,
                geom,
                Gdk.WindowHints.MIN_SIZE | Gdk.WindowHints.MAX_SIZE,
            )
        except Exception:
            pass

    def _show(section_id: str, drill_id: str) -> None:
        section = by_id.get(section_id)
        if section is None:
            return
        _HUB_CONTROL["section"] = section_id
        for sid, btn in buttons.items():
            ctx = btn.get_style_context()
            if sid == section_id:
                ctx.add_class("selected")
            else:
                ctx.remove_class("selected")
        for child in list(right.get_children()):
            right.remove(child)
            child.destroy()
        win.set_title(section.label)
        if section.page is not None:
            state = attach_page(right, section.label, section.page(), on_quit=_quit)
        else:
            subtitle, items, preset = section.build()
            if drill_id:
                preset = drill_id
            state = attach_drill(
                right,
                section.label,
                list(items),
                subtitle=subtitle or "",
                initial=preset,
                on_quit=_quit,
                on_change=_lock_size,
            )
        win._neuronix_key = state["on_key"]  # type: ignore[attr-defined]
        _lock_size()
        right.show_all()

    def _on_key(widget, event):
        handler = getattr(win, "_neuronix_key", None)
        if callable(handler):
            return handler(widget, event)
        return False

    nav_sections = sorted(
        (section for section in catalog if section.id != "about"),
        key=lambda section: section.label.casefold(),
    )
    nav_sections.extend(section for section in catalog if section.id == "about")
    for section in nav_sections:
        btn = _make_tile(
            section.id,
            section.label,
            "",
            lambda i, sid=section.id: _show(sid, ""),
            show_chevron=False,
            icon=section.icon,
        )
        if section.id == "about":
            btn.set_margin_top(28)
        buttons[section.id] = btn
        nav.pack_start(btn, False, False, 0)

    if actions:
        for action in actions:
            def _run(item_id: str, act: HubAction = action) -> None:
                _ = item_id
                act.run()
                _quit()

            nav_col.pack_start(
                _make_tile(action.id, action.label, "", _run, show_chevron=False, icon=action.icon),
                False,
                False,
                0,
            )

    _HUB_CONTROL["switch"] = lambda section, drill_id: _show(section, drill_id)
    win.connect("key-press-event", _on_key)
    win.connect("destroy", lambda *_: _quit())
    _show(initial_id, drill)
    win.show_all()
    win.present()
    Gtk.main()


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
