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

_CHROME_PREFS = Path.home() / ".config" / "hypr" / "neuronix-window-chrome.json"
_DEFAULT_BAR_IMAGE = Path.home() / ".local/share/neuronix" / "hyprbars" / "tile-grey-round.png"
_PLUGIN_SO_CANDIDATES = {
    "hyprbars": (
        Path.home() / ".local/lib/hyprland/plugins/libhyprbars.so",
        Path("/usr/local/lib/hyprland/plugins/libhyprbars.so"),
        Path("/usr/lib/x86_64-linux-gnu/hyprland/plugins/libhyprbars.so"),
        Path("/usr/lib/x86_64-linux-gnu/hyprland/plugins/hyprbars.so"),
    ),
    "hyprframes": (
        Path.home() / ".local/lib/hyprland/plugins/libhyprframes.so",
        Path("/usr/local/lib/hyprland/plugins/libhyprframes.so"),
        Path("/usr/lib/x86_64-linux-gnu/hyprland/plugins/libhyprframes.so"),
    ),
    "hyprtabs": (
        Path.home() / ".local/lib/hyprland/plugins/libhyprtabs.so",
        Path("/usr/local/lib/hyprland/plugins/libhyprtabs.so"),
        Path("/usr/lib/x86_64-linux-gnu/hyprland/plugins/libhyprtabs.so"),
    ),
}


class _SettingsPage(Gtk.Box):
    """Vertical page whose sections land in GNOME-style cards."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(6)
        self.set_margin_bottom(10)
        self.set_margin_start(4)
        self.set_margin_end(6)
        self._card: Gtk.Box | None = None

    def _open_card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("neuronix-card")
        Gtk.Box.pack_start(self, card, False, False, 0)
        self._card = card
        return card

    def pack_start(self, child, expand=True, fill=True, padding=0):
        try:
            heading = bool(child.get_style_context().has_class("neuronix-heading"))
        except Exception:
            heading = False
        if heading:
            self._card = None
            return Gtk.Box.pack_start(self, child, False, False, 0)
        if self._card is None:
            self._open_card()
        if expand and self._card is not None:
            self._card.set_vexpand(True)
            self.set_child_packing(self._card, True, True, 0, Gtk.PackType.START)
        return Gtk.Box.pack_start(self._card, child, expand, fill, padding)

    def pack_end(self, child, expand=True, fill=True, padding=0):
        return Gtk.Box.pack_end(self, child, expand, fill, padding)


def _page() -> Gtk.Box:
    return _SettingsPage()


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


def _chrome_prefs() -> dict[str, bool]:
    # hyprbars is always on; Themes toggles tiled bar images instead.
    data = {
        "hyprbars": True,
        "hyprbars_images": True,
        "hyprframes": True,
        "hyprtabs": False,
    }
    try:
        raw = json.loads(_CHROME_PREFS.read_text(encoding="utf-8"))
    except Exception:
        return data
    if not isinstance(raw, dict):
        return data
    for key in ("hyprbars", "hyprbars_images", "hyprframes", "hyprtabs"):
        if key in raw:
            data[key] = bool(raw[key])
    # Migrate old "hyprbars off" preference → images off (bars stay loaded).
    if "hyprbars_images" not in raw and "hyprbars" in raw and not bool(raw.get("hyprbars")):
        data["hyprbars_images"] = False
    data["hyprbars"] = True
    return data


def _save_chrome_prefs(prefs: dict[str, bool]) -> None:
    try:
        # Merge so toggling one switch cannot drop the others.
        current = _chrome_prefs()
        current.update({k: bool(v) for k, v in prefs.items()})
        current["hyprbars"] = True
        _CHROME_PREFS.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "hyprbars": True,
            "hyprbars_images": bool(current.get("hyprbars_images", True)),
            "hyprframes": bool(current.get("hyprframes", True)),
            "hyprtabs": bool(current.get("hyprtabs", False)),
        }
        _CHROME_PREFS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _plugin_so(name: str) -> str:
    for path in _PLUGIN_SO_CANDIDATES.get(name, ()):
        if path.is_file():
            return str(path)
    return ""


def _plugin_loaded(name: str) -> bool:
    ok, out = _run(["hyprctl", "-j", "plugin", "list"], timeout=3)
    if not ok:
        ok, out = _run(["hyprctl", "plugin", "list"], timeout=3)
        return ok and name.lower() in out.lower()
    try:
        rows = json.loads(out or "[]")
    except Exception:
        return name.lower() in (out or "").lower()
    if not isinstance(rows, list):
        return False
    needle = name.lower()
    return any(str(row.get("name") or "").lower() == needle for row in rows if isinstance(row, dict))


def _hyprbars_enabled_live() -> bool:
    if not _plugin_loaded("hyprbars"):
        return False
    ok, out = _run(["hyprctl", "getoption", "plugin:hyprbars:enabled"], timeout=3)
    if not ok:
        return True
    for line in (out or "").splitlines():
        if line.strip().startswith("int:"):
            try:
                return int(line.split(":", 1)[1].strip()) != 0
            except ValueError:
                break
    return True


def _ensure_hyprbars_on() -> str:
    """Title bars are always enabled (needed to drag windows)."""
    prefs = _chrome_prefs()
    prefs["hyprbars"] = True
    _save_chrome_prefs(prefs)
    if not _plugin_loaded("hyprbars"):
        so = _plugin_so("hyprbars")
        if not so:
            return "hyprbars plugin was not found"
        ok, out = _run(["hyprctl", "plugin", "load", so], timeout=8)
        if not ok and not _plugin_loaded("hyprbars"):
            return out or "Could not load hyprbars"
    _run(["hyprctl", "keyword", "plugin:hyprbars:enabled", "true"], timeout=4)
    return ""


def _set_hyprbars(on: bool) -> str:
    # Kept for callers; hyprbars cannot be turned off anymore.
    del on
    return _ensure_hyprbars_on()


def _default_bar_image() -> str:
    for path in (
        _DEFAULT_BAR_IMAGE,
        Path("/usr/share/neuronix/hyprbars/tile-grey-round.png"),
        Path("/usr/local/share/neuronix/hyprbars/tile-grey-round.png"),
    ):
        if path.is_file():
            return str(path)
    return str(_DEFAULT_BAR_IMAGE)


def _rewrite_hyprland_bar_image(path: str) -> None:
    conf = Path.home() / ".config" / "hypr" / "hyprland.conf"
    if not conf.is_file():
        return
    try:
        text = conf.read_text(encoding="utf-8")
    except OSError:
        return
    import re

    value = path.strip()
    repl = f"bar_image = {value}" if value else "bar_image ="
    new, n = re.subn(r"(?m)^([ \t]*)bar_image\s*=.*$", rf"\1{repl}", text, count=1)
    if n and new != text:
        try:
            conf.write_text(new, encoding="utf-8")
        except OSError:
            pass


def _hyprbars_images_live() -> bool:
    ok, out = _run(["hyprctl", "getoption", "plugin:hyprbars:bar_image"], timeout=3)
    if not ok:
        return bool(_chrome_prefs().get("hyprbars_images", True))
    for line in (out or "").splitlines():
        if line.strip().startswith("str:"):
            return bool(line.split(":", 1)[1].strip())
    return bool(_chrome_prefs().get("hyprbars_images", True))


def _set_hyprbars_images(on: bool) -> str:
    """Toggle tiled bar_image; when off, bars use solid GTK theme colors."""
    err = _ensure_hyprbars_on()
    if err:
        return err
    prefs = _chrome_prefs()
    prefs["hyprbars_images"] = bool(on)
    prefs["hyprbars"] = True
    _save_chrome_prefs(prefs)
    if on:
        path = _default_bar_image()
        _run(["hyprctl", "keyword", "plugin:hyprbars:bar_image", path], timeout=4)
        _rewrite_hyprland_bar_image(path)
        return ""
    _run(["hyprctl", "keyword", "plugin:hyprbars:bar_image", ""], timeout=4)
    _rewrite_hyprland_bar_image("")
    # Solid fill from the active GTK suite profile.
    try:
        theme = _gtk_theme()
        if theme is not None:
            theme.sync_hyprbars()
    except Exception as exc:
        return str(exc)
    return ""


def _set_hyprframes(on: bool) -> str:
    prefs = _chrome_prefs()
    prefs["hyprframes"] = bool(on)
    _save_chrome_prefs(prefs)
    so = _plugin_so("hyprframes")
    if on:
        if _plugin_loaded("hyprframes"):
            return ""
        if not so:
            return "hyprframes plugin was not found"
        ok, out = _run(["hyprctl", "plugin", "load", so], timeout=8)
        if not ok and not _plugin_loaded("hyprframes"):
            return out or "Could not load hyprframes"
        return ""
    if not _plugin_loaded("hyprframes"):
        return ""
    if not so:
        # Still try unload by common paths.
        for candidate in _PLUGIN_SO_CANDIDATES["hyprframes"]:
            _run(["hyprctl", "plugin", "unload", str(candidate)], timeout=6)
            if not _plugin_loaded("hyprframes"):
                return ""
        return "Could not unload hyprframes"
    ok, out = _run(["hyprctl", "plugin", "unload", so], timeout=6)
    if _plugin_loaded("hyprframes"):
        return out or "Could not unload hyprframes"
    return ""


def _hyprtabs_enabled_live() -> bool:
    if not _plugin_loaded("hyprtabs"):
        return False
    ok, out = _run(["hyprctl", "getoption", "plugin:hyprtabs:enabled"], timeout=3)
    if not ok:
        return True
    for line in (out or "").splitlines():
        if line.strip().startswith("int:"):
            try:
                return int(line.split(":", 1)[1].strip()) != 0
            except ValueError:
                break
    return True


def _window_manager_py() -> str:
    for path in (
        Path.home() / ".config" / "hypr" / "window-manager.py",
        Path("/usr/share/neuronix/hypr/window-manager.py"),
        Path("/usr/local/share/neuronix/hypr/window-manager.py"),
    ):
        if path.is_file():
            return str(path)
    return ""


def _set_hyprtabs(on: bool) -> str:
    prefs = _chrome_prefs()
    prefs["hyprtabs"] = bool(on)
    _save_chrome_prefs(prefs)
    wm = _window_manager_py()
    if on:
        if not _plugin_loaded("hyprtabs"):
            so = _plugin_so("hyprtabs")
            if not so:
                return "hyprtabs plugin was not found"
            ok, out = _run(["hyprctl", "plugin", "load", so], timeout=8)
            if not ok and not _plugin_loaded("hyprtabs"):
                return out or "Could not load hyprtabs"
        _run(["hyprctl", "keyword", "plugin:hyprtabs:enabled", "true"], timeout=4)
        _ensure_hyprbars_on()
        # Switch desktop layout to tabbed (full-width under the strip).
        if wm:
            _run([wm, "layout-set", "tabs"], timeout=12)
        return ""
    if _plugin_loaded("hyprtabs"):
        ok, out = _run(["hyprctl", "keyword", "plugin:hyprtabs:enabled", "false"], timeout=4)
        if not ok:
            return out or "Could not disable hyprtabs"
    _ensure_hyprbars_on()
    if wm:
        _run([wm, "layout-set", "float"], timeout=12)
    return ""


_PLUGIN_DIRS = (
    Path.home() / ".local/lib/hyprland/plugins",
    Path("/usr/local/lib/hyprland/plugins"),
    Path("/usr/lib/x86_64-linux-gnu/hyprland/plugins"),
)
_PLUGIN_COPY = {
    "hyprbars": ("Hyprbars", "Title bars on windows"),
    "hyprframes": ("Hyprframes", "Image borders around windows"),
    "hyprtabs": ("Hyprtabs", "Tabs along the top of windows"),
    "hyprspace": ("Hyprspace", "Workspace overview"),
}


def _plugin_key(path: Path) -> str:
    stem = path.stem
    if stem.lower().startswith("lib"):
        stem = stem[3:]
    return stem.lower()


def _installed_plugins() -> list[dict[str, str]]:
    """Every plugin .so on disk, one row each. Empty when nothing is installed."""
    found: dict[str, dict[str, str]] = {}
    for directory in _PLUGIN_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.so")):
            key = _plugin_key(path)
            if not key or key in found:
                continue
            title, desc = _PLUGIN_COPY.get(key, ("", ""))
            if not title:
                raw = path.stem[3:] if path.stem.lower().startswith("lib") else path.stem
                title = raw[:1].upper() + raw[1:]
                desc = path.name
            found[key] = {"id": key, "path": str(path), "title": title, "desc": desc}
    return [found[key] for key in sorted(found, key=lambda item: found[item]["title"].casefold())]


def _plugin_enabled(plugin_id: str) -> bool:
    prefs = _chrome_prefs()
    if plugin_id == "hyprbars":
        if _plugin_loaded("hyprbars"):
            return _hyprbars_enabled_live()
        return bool(prefs.get("hyprbars", True))
    if plugin_id == "hyprtabs":
        if _plugin_loaded("hyprtabs"):
            return _hyprtabs_enabled_live()
        return bool(prefs.get("hyprtabs", False))
    if plugin_id == "hyprframes":
        return _plugin_loaded("hyprframes")
    return _plugin_loaded(plugin_id)


def _set_plugin(plugin_id: str, path: str, on: bool) -> str:
    if plugin_id == "hyprbars":
        return _set_hyprbars(on)
    if plugin_id == "hyprframes":
        return _set_hyprframes(on)
    if plugin_id == "hyprtabs":
        return _set_hyprtabs(on)
    if on:
        if _plugin_loaded(plugin_id):
            return ""
        if not path:
            return f"{plugin_id} plugin was not found"
        ok, out = _run(["hyprctl", "plugin", "load", path], timeout=8)
        if not ok and not _plugin_loaded(plugin_id):
            return out or f"Could not enable {plugin_id}"
        return ""
    if not _plugin_loaded(plugin_id):
        return ""
    if not path:
        return f"Could not disable {plugin_id}"
    ok, out = _run(["hyprctl", "plugin", "unload", path], timeout=6)
    if _plugin_loaded(plugin_id):
        return out or f"Could not disable {plugin_id}"
    return ""


def plugins_page() -> Gtk.Widget:
    """Installed Hyprland plugins, each with its own on/off switch."""
    box = _page()
    box.pack_start(_section("Installed"), False, False, 0)
    plugins = _installed_plugins()
    if not plugins:
        box.pack_start(_note("No plugins are installed."), False, False, 0)
        return box
    status = _note("")
    status.set_no_show_all(True)
    status.hide()

    def _msg(text: str) -> None:
        if text:
            status.set_text(text)
            status.show()
        else:
            status.hide()

    for plugin in plugins:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.set_hexpand(True)
        title = Gtk.Label(label=plugin["title"], xalign=0.0)
        title.get_style_context().add_class("neuronix-row-title")
        desc = Gtk.Label(label=plugin["desc"], xalign=0.0)
        desc.get_style_context().add_class("neuronix-subtitle")
        text.pack_start(title, False, False, 0)
        text.pack_start(desc, False, False, 0)
        sw = Gtk.Switch()
        sw.set_valign(Gtk.Align.CENTER)
        sw.set_active(_plugin_enabled(plugin["id"]))
        armed = {"ok": False}

        def _notify(widget: Gtk.Switch, *_a, item=plugin, gate=armed) -> None:
            if not gate["ok"]:
                return
            err = _set_plugin(item["id"], item["path"], bool(widget.get_active()))
            if not err:
                _msg("")
                return
            _msg(err)
            gate["ok"] = False
            widget.set_active(not widget.get_active())
            gate["ok"] = True

        sw.connect("notify::active", _notify)

        def _arm(gate=armed) -> bool:
            gate["ok"] = True
            return False

        GLib.idle_add(_arm)
        row.pack_start(text, True, True, 0)
        row.pack_end(sw, False, False, 0)
        box.pack_start(row, False, False, 0)
    box.pack_start(status, False, False, 0)
    return box

def _switch_row(label: str, active: bool, on_change) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.get_style_context().add_class("neuronix-pref-row")
    cap = Gtk.Label(label=label, xalign=0.0)
    cap.set_hexpand(True)
    sw = Gtk.Switch()
    sw.set_valign(Gtk.Align.CENTER)
    sw.set_active(bool(active))
    armed = {"ok": False}

    def _notify(widget: Gtk.Switch, *_a) -> None:
        if not armed["ok"]:
            return
        on_change(bool(widget.get_active()))

    sw.connect("notify::active", _notify)
    row.pack_start(cap, True, True, 0)
    row.pack_end(sw, False, False, 0)

    def _arm() -> bool:
        armed["ok"] = True
        return False

    GLib.idle_add(_arm)
    row._neuronix_switch = sw  # type: ignore[attr-defined]
    return row


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
        # Id = desktop file; label = short title only (long "title (file)"
        # strings were stretching the fixed-width settings hub).
        current = ""
        ok, out = _run(["xdg-mime", "query", "default", mime], timeout=3)
        if ok:
            current = out.strip()
        combo.append("", "")
        active_id = ""
        for filename, title in apps:
            combo.append(filename, title)
            if filename == current:
                active_id = filename
        if active_id:
            combo.set_active_id(active_id)
        else:
            combo.set_active(0)

        def _set(widget: Gtk.ComboBoxText, mime=mime) -> None:
            filename = widget.get_active_id() or ""
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
    combo.set_hexpand(True)
    ids: list[str] = []
    for profile in profiles:
        ids.append(profile.id)
        label = profile.name if names[profile.name] == 1 else f"{profile.name} ({profile.id})"
        combo.append(profile.id, label)
    current = theme.load_theme_id()
    if current in ids:
        combo.set_active_id(current)
    else:
        combo.set_active(0)
    box.pack_start(combo, False, False, 0)

    active_i = max(0, combo.get_active())
    chosen = {"profile": profiles[active_i]}
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
        index = int(combo.get_active())
        if index < 0 or index >= len(profiles):
            active_id = combo.get_active_id() or ""
            return next((item for item in profiles if item.id == active_id), None)
        return profiles[index]

    def _changed(*_a) -> None:
        profile = _pick()
        if profile is None:
            return
        chosen["profile"] = profile
        area.queue_draw()
        try:
            area.queue_draw_area(0, 0, area.get_allocated_width(), area.get_allocated_height())
        except Exception:
            pass
        if profile.id == theme.load_theme_id():
            status.set_text(f"{profile.name} is in use")
        else:
            status.set_text(profile.name)

    def _open_combo(*_a):
        # Exclusive hub grab eats dropdown selection; release while picking.
        try:
            import neuronix_choice_dialog as choice

            choice.release_hub_keyboard_briefly()
        except Exception:
            pass
        return False

    def _apply(*_a) -> None:
        profile = chosen.get("profile") or _pick()
        if profile is None:
            return
        try:
            theme.select_theme(profile.id, gtk_version=3)
        except Exception as exc:
            status.set_text(str(exc))
            return
        # Restart the hub on Themes so glass/CSS pick up the new chrome.
        try:
            import neuronix_choice_dialog as choice

            choice.request_hub_reopen("themes")
        except Exception:
            pass
        GLib.idle_add(Gtk.main_quit)

    def _edit(*_a) -> None:
        profile = chosen.get("profile") or _pick()
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
    combo.connect("button-press-event", _open_combo)
    try:
        combo.connect("notify::popup-shown", lambda *_: _open_combo())
    except TypeError:
        pass
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


_WEATHER_PREFS = Path.home() / ".config" / "neuronix" / "weather.json"
_WEATHER_API = "https://api.weatherapi.com/v1/forecast.json"
_WEATHER_SIGNUP = "https://www.weatherapi.com/signup.aspx"


class _WeatherError(Exception):
    pass


def _weather_read() -> dict:
    if not _WEATHER_PREFS.is_file():
        return {"location": "", "api_key": ""}
    try:
        data = json.loads(_WEATHER_PREFS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"location": "", "api_key": ""}
    if not isinstance(data, dict):
        return {"location": "", "api_key": ""}
    return {
        "location": str(data.get("location") or "").strip(),
        "api_key": str(data.get("api_key") or "").strip(),
    }


def _weather_write(location: str, api_key: str) -> None:
    _WEATHER_PREFS.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"location": location, "api_key": api_key}, indent=2) + "\n"
    tmp = _WEATHER_PREFS.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(_WEATHER_PREFS)
    os.chmod(_WEATHER_PREFS, 0o600)


def _weather_error_message(body: str) -> str:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        return str(data["error"].get("message") or "").strip()
    return ""


def _weather_fetch(location: str, api_key: str) -> dict:
    import urllib.error
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode(
        {"key": api_key, "q": location, "days": "3", "aqi": "no", "alerts": "no"}
    )
    req = urllib.request.Request(
        f"{_WEATHER_API}?{query}",
        headers={"User-Agent": "neuronix-settings"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        message = _weather_error_message(detail)
        if exc.code in (401, 403):
            raise _WeatherError(message or "API key was rejected.") from exc
        raise _WeatherError(message or f"Weather request failed ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise _WeatherError("Could not reach weatherapi.com.") from exc
    except TimeoutError as exc:
        raise _WeatherError("Weather request timed out.") from exc
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _WeatherError("Could not read the weather response.") from exc
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        raise _WeatherError(str(data["error"].get("message") or "Weather request failed."))
    if not isinstance(data, dict):
        raise _WeatherError("Could not read the weather response.")
    return data


def _weather_temp(value) -> str:
    try:
        return f"{float(value):.0f}°"
    except (TypeError, ValueError):
        return "—"



def _weather_glyph(code, is_day: bool = True) -> str:
    """Symbols Nerd Font weather icon for a WeatherAPI condition code."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = 0
    icons = {
        1000: ("", ""),
        1003: ("", ""),
        1006: ("", ""),
        1009: ("", ""),
        1030: ("", ""),
        1063: ("", ""),
        1066: ("", ""),
        1069: ("", ""),
        1072: ("", ""),
        1087: ("", ""),
        1114: ("", ""),
        1117: ("", ""),
        1135: ("", ""),
        1147: ("", ""),
        1150: ("", ""),
        1153: ("", ""),
        1168: ("", ""),
        1171: ("", ""),
        1180: ("", ""),
        1183: ("", ""),
        1186: ("", ""),
        1189: ("", ""),
        1192: ("", ""),
        1195: ("", ""),
        1198: ("", ""),
        1201: ("", ""),
        1204: ("", ""),
        1207: ("", ""),
        1210: ("", ""),
        1213: ("", ""),
        1216: ("", ""),
        1219: ("", ""),
        1222: ("", ""),
        1225: ("", ""),
        1237: ("", ""),
        1240: ("", ""),
        1243: ("", ""),
        1246: ("", ""),
        1249: ("", ""),
        1252: ("", ""),
        1255: ("", ""),
        1258: ("", ""),
        1261: ("", ""),
        1264: ("", ""),
        1273: ("", ""),
        1276: ("", ""),
        1279: ("", ""),
        1282: ("", ""),
    }
    pair = icons.get(code, ("", ""))
    return pair[0] if is_day else pair[1]


def _weather_icon_font(lbl) -> None:
    try:
        lbl.override_font(Pango.FontDescription("Symbols Nerd Font 14"))
    except Exception:
        pass


def weather_page() -> Gtk.Widget:
    box = _page()
    box.set_vexpand(True)
    if not getattr(weather_page, "_css", False):
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"box.neuronix-hour-strip {"
            b" border-radius: 18px;"
            b" padding: 10px 8px;"
            b" background-color: rgba(0, 0, 0, 0.28);"
            b"}"
            b"box.neuronix-hour-strip label { background: none; }"
            b"box.neuronix-weather-page { margin: 8px 8px 12px 8px; padding: 0; }"
            b"box.neuronix-weather-page box.neuronix-card {"
            b" padding: 10px 16px;"
            b" margin-top: 0;"
            b" margin-bottom: 0;"
            b"}"
            b"box.neuronix-weather-page label.neuronix-heading {"
            b" margin-top: 10px;"
            b" margin-bottom: 4px;"
            b"}"
        )
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            weather_page._css = True

    box.get_style_context().add_class("neuronix-weather-page")
    box.set_margin_top(0)
    box.set_margin_bottom(4)
    place = Gtk.Label(label="—", xalign=0.0)
    place.get_style_context().add_class("neuronix-heading")
    box.pack_start(place, False, False, 0)

    current = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    current.set_valign(Gtk.Align.CENTER)
    current.set_hexpand(True)
    now_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    now_row.set_hexpand(True)
    left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    cond_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    cond_icon = Gtk.Label(label="")
    _weather_icon_font(cond_icon)
    cond_text = Gtk.Label(label="", xalign=0.0)
    cond_text.get_style_context().add_class("neuronix-row-title")
    cond_row.pack_start(cond_icon, False, False, 0)
    cond_row.pack_start(cond_text, False, False, 0)
    feels = _note("")
    day_range = _note("")
    left.pack_start(cond_row, False, False, 0)
    left.pack_start(feels, False, False, 0)
    left.pack_start(day_range, False, False, 0)
    big = Gtk.Label(label="—")
    big.set_halign(Gtk.Align.END)
    big.set_valign(Gtk.Align.CENTER)
    try:
        big.override_font(Pango.FontDescription("DejaVu Sans 32"))
    except Exception:
        pass
    now_row.pack_start(left, True, True, 0)
    now_row.pack_start(big, False, False, 0)
    current.pack_start(now_row, False, False, 0)

    strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
    strip.set_homogeneous(True)
    strip.set_hexpand(True)
    strip.get_style_context().add_class("neuronix-hour-strip")
    hours = []
    for _i in range(6):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        temp = Gtk.Label(label="—")
        temp.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Label(label="")
        icon.set_halign(Gtk.Align.CENTER)
        _weather_icon_font(icon)
        when = Gtk.Label(label="")
        when.set_halign(Gtk.Align.CENTER)
        when.get_style_context().add_class("neuronix-subtitle")
        col.pack_start(temp, False, False, 0)
        col.pack_start(icon, False, False, 0)
        col.pack_start(when, False, False, 0)
        strip.pack_start(col, True, True, 0)
        hours.append((temp, icon, when))
    current.pack_start(strip, False, False, 0)
    msg = _note("")
    current.pack_start(msg, False, False, 0)
    box.pack_start(current, False, False, 0)

    box.pack_start(_section("Upcoming"), False, False, 0)
    days_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    days_col.set_valign(Gtk.Align.CENTER)
    days_col.set_hexpand(True)
    days = []
    for _i in range(2):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_hexpand(True)
        row.get_style_context().add_class("neuronix-pref-row")
        name = Gtk.Label(label="—", xalign=0.0)
        name.set_width_chars(4)
        icon = Gtk.Label(label="")
        _weather_icon_font(icon)
        cond = Gtk.Label(label="", xalign=0.0)
        cond.set_hexpand(True)
        cond.get_style_context().add_class("neuronix-subtitle")
        hi = Gtk.Label(label="", xalign=1.0)
        lo = Gtk.Label(label="", xalign=1.0)
        lo.get_style_context().add_class("neuronix-subtitle")
        row.pack_start(name, False, False, 0)
        row.pack_start(icon, False, False, 0)
        row.pack_start(cond, True, True, 0)
        row.pack_start(hi, False, False, 0)
        row.pack_start(lo, False, False, 0)
        days_col.pack_start(row, False, False, 0)
        days.append((name, icon, cond, hi, lo))
    box.pack_start(days_col, False, False, 0)

    drawer_btn = _button("API key  ▸")
    box.pack_end(drawer_btn, False, False, 0)
    reveal = Gtk.Revealer()
    reveal.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
    reveal.set_reveal_child(False)
    form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    form.set_margin_top(8)
    intro = _note("Current conditions and forecast from WeatherAPI.com.")
    link = Gtk.LinkButton.new_with_label(_WEATHER_SIGNUP, "Get a free key at weatherapi.com")
    link.set_halign(Gtk.Align.START)
    intro.set_no_show_all(True)
    link.set_no_show_all(True)
    location = Gtk.Entry()
    location.set_placeholder_text("City, ZIP, or lat,lon")
    key = Gtk.Entry()
    key.set_placeholder_text("WeatherAPI.com key")
    key.set_visibility(False)
    show = Gtk.CheckButton(label="Show key")

    def _toggle_key(btn) -> None:
        key.set_visibility(bool(btn.get_active()))

    show.connect("toggled", _toggle_key)

    def _sync_help(*_a) -> None:
        show_help = not bool(key.get_text().strip())
        intro.set_visible(show_help)
        link.set_visible(show_help)

    key.connect("changed", _sync_help)
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    save = _button("Save")
    refresh = _button("Refresh")
    actions.pack_start(save, False, False, 0)
    actions.pack_start(refresh, False, False, 0)
    form.pack_start(intro, False, False, 0)
    form.pack_start(link, False, False, 0)
    form.pack_start(location, False, False, 0)
    form.pack_start(key, False, False, 0)
    form.pack_start(show, False, False, 0)
    form.pack_start(actions, False, False, 0)
    reveal.add(form)
    box.pack_end(reveal, False, False, 0)

    def _set_drawer(open_: bool) -> None:
        reveal.set_reveal_child(open_)
        drawer_btn.set_label("API key  ▾" if open_ else "API key  ▸")

    drawer_btn.connect("clicked", lambda *_a: _set_drawer(not reveal.get_reveal_child()))

    state = {"gen": 0}

    def _clear() -> None:
        place.set_text("—")
        cond_icon.set_text("")
        cond_text.set_text("")
        feels.set_text("")
        day_range.set_text("")
        big.set_text("—")
        for temp, icon, when in hours:
            temp.set_text("—")
            icon.set_text("")
            when.set_text("")
        for name, icon, cond, hi, lo in days:
            name.set_text("—")
            icon.set_text("")
            cond.set_text("")
            hi.set_text("")
            lo.set_text("")

    def _hour_label(parsed, is_now: bool) -> str:
        if is_now:
            return "Now"
        hour = parsed.hour % 12 or 12
        return f"{hour} {'AM' if parsed.hour < 12 else 'PM'}"

    def _upcoming_hours(data: dict):
        from datetime import datetime

        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        found = []
        block = data.get("forecast") if isinstance(data.get("forecast"), dict) else {}
        for day in block.get("forecastday") or []:
            if not isinstance(day, dict):
                continue
            for hour in day.get("hour") or []:
                if not isinstance(hour, dict):
                    continue
                raw = str(hour.get("time") or "")
                try:
                    parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M")
                except ValueError:
                    continue
                if parsed < now:
                    continue
                found.append((parsed, hour))
                if len(found) >= len(hours):
                    return found
        return found

    def _apply_data(data: dict) -> None:
        from datetime import datetime

        loc = data.get("location") if isinstance(data.get("location"), dict) else {}
        parts = [str(loc.get("name") or "").strip(), str(loc.get("region") or "").strip()]
        parts = [part for part in parts if part]
        place.set_text(", ".join(parts) or "Weather")
        cur = data.get("current") if isinstance(data.get("current"), dict) else {}
        cond = cur.get("condition") if isinstance(cur.get("condition"), dict) else {}
        raw_day = cur.get("is_day")
        is_day = True if raw_day is None else bool(int(raw_day))
        cond_icon.set_text(_weather_glyph(cond.get("code"), is_day))
        cond_text.set_text(str(cond.get("text") or "Unknown").strip())
        feels.set_text(f"Feels like {_weather_temp(cur.get('feelslike_f'))}")
        big.set_text(_weather_temp(cur.get("temp_f")))
        block = data.get("forecast") if isinstance(data.get("forecast"), dict) else {}
        forecast_days = block.get("forecastday") if isinstance(block.get("forecastday"), list) else []
        today_block = forecast_days[0] if forecast_days and isinstance(forecast_days[0], dict) else {}
        info = today_block.get("day") if isinstance(today_block.get("day"), dict) else {}
        day_range.set_text(
            f"{_weather_temp(info.get('maxtemp_f'))}  ·  {_weather_temp(info.get('mintemp_f'))}"
        )
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        slots = _upcoming_hours(data)
        for index, (temp, icon, when) in enumerate(hours):
            if index >= len(slots):
                temp.set_text("")
                icon.set_text("")
                when.set_text("")
                continue
            parsed, hour = slots[index]
            hour_cond = hour.get("condition") if isinstance(hour.get("condition"), dict) else {}
            hour_day = hour.get("is_day")
            hour_is_day = True if hour_day is None else bool(int(hour_day))
            temp.set_text(_weather_temp(hour.get("temp_f")))
            icon.set_text(_weather_glyph(hour_cond.get("code"), hour_is_day))
            when.set_text(_hour_label(parsed, parsed == now))
        from datetime import date

        today = date.today()
        upcoming = []
        for day in forecast_days:
            if not isinstance(day, dict):
                continue
            raw = str(day.get("date") or "").strip()
            try:
                parsed_day = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                continue
            if parsed_day <= today:
                continue
            info = day.get("day") if isinstance(day.get("day"), dict) else {}
            day_cond = info.get("condition") if isinstance(info.get("condition"), dict) else {}
            upcoming.append((parsed_day, info, day_cond))
        for index, (name, icon, cond, hi, lo) in enumerate(days):
            if index >= len(upcoming):
                name.set_text("")
                icon.set_text("")
                cond.set_text("")
                hi.set_text("")
                lo.set_text("")
                continue
            parsed_day, info, day_cond = upcoming[index]
            name.set_text(parsed_day.strftime("%a"))
            icon.set_text(_weather_glyph(day_cond.get("code"), True))
            cond.set_text(str(day_cond.get("text") or "").strip() or "—")
            hi.set_text(_weather_temp(info.get("maxtemp_f")))
            lo.set_text(_weather_temp(info.get("mintemp_f")))

    def _refresh(*_a) -> None:
        loc = location.get_text().strip()
        api_key = key.get_text().strip()
        state["gen"] += 1
        gen = state["gen"]
        if not api_key:
            _clear()
            msg.set_text("Add a WeatherAPI.com key, then save.")
            _set_drawer(True)
            return
        if not loc:
            _clear()
            msg.set_text("Enter a city, ZIP, or lat,lon.")
            _set_drawer(True)
            return
        msg.set_text("Loading weather…")

        def _work() -> None:
            try:
                data = _weather_fetch(loc, api_key)
                err = ""
            except _WeatherError as exc:
                data = None
                err = str(exc)
            except Exception:
                data = None
                err = "Could not read the weather response."

            def _done() -> bool:
                if state["gen"] != gen:
                    return False
                if err or not isinstance(data, dict):
                    _clear()
                    msg.set_text(err or "Could not read the weather response.")
                    return False
                _apply_data(data)
                msg.set_text("")
                return False

            GLib.idle_add(_done)

        threading.Thread(target=_work, daemon=True).start()

    def _save(*_a) -> None:
        loc = location.get_text().strip()
        api_key = key.get_text().strip()
        try:
            _weather_write(loc, api_key)
        except OSError as exc:
            msg.set_text(f"Could not save weather settings: {exc}")
            return
        msg.set_text("Saved.")
        if api_key:
            _set_drawer(False)
        _refresh()

    save.connect("clicked", _save)
    refresh.connect("clicked", _refresh)
    prefs = _weather_read()
    location.set_text(prefs["location"])
    key.set_text(prefs["api_key"])
    _sync_help()
    _set_drawer(not bool(prefs["api_key"]))

    GLib.idle_add(_refresh)
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


def _run_apt(password: str, argv: list[str], on_line=None) -> int:
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
        err = str(exc) + "\n"
        if on_line is not None:
            on_line(err)
        else:
            _update_emit("log", err)
        return 127
    assert proc.stdin is not None and proc.stdout is not None
    try:
        proc.stdin.write(password + "\n")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    for line in proc.stdout:
        if on_line is not None:
            on_line(line)
        else:
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
        _finish_job(
            _UPDATE,
            _update_emit,
            title="Upgrade finished",
            body="All available updates were installed.",
            ok=True,
        )
    else:
        _finish_job(
            _UPDATE,
            _update_emit,
            title="Upgrade failed",
            body="Check the log for details.",
            ok=False,
        )


def _desktop_notify(title: str, body: str, *, ok: bool = True) -> None:
    icon = "dialog-information" if ok else "dialog-error"
    try:
        subprocess.Popen(
            ["notify-send", "-a", "Settings", "-i", icon, title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def _job_done_dialog(title: str, body: str) -> None:
    """Solid Done/Failed dialog. Nested loop so Settings stays open."""
    import neuronix_choice_dialog as choice

    choice._apply_css()
    result = {"done": False}
    loop = GLib.MainLoop()
    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title(title)
    win.set_decorated(False)
    win.set_resizable(False)
    win.get_style_context().add_class("neuronix-choice")
    win.get_style_context().add_class("neuronix-settings")
    choice.center_layer_window(win, 440, 220)
    release_keys = choice.hold_layer_keyboard(win)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.get_style_context().add_class("neuronix-root")
    choice._glass_root(outer, alpha=1.0, radius=16, color="#1e1e1e")
    win.add(outer)

    def _finish(*_a):
        if result["done"]:
            return False
        result["done"] = True
        release_keys()
        loop.quit()
        return False

    head = Gtk.Label(label=title, xalign=0.0)
    head.get_style_context().add_class("neuronix-title")
    choice.pack_title_with_close(outer, head, _finish)

    prompt = Gtk.Label(label=body, xalign=0.0)
    prompt.set_line_wrap(True)
    prompt.set_max_width_chars(42)
    prompt.get_style_context().add_class("neuronix-subtitle")
    outer.pack_start(prompt, False, False, 0)

    ok = Gtk.Button(label="OK")
    ok.set_relief(Gtk.ReliefStyle.NONE)
    ok.set_can_default(True)
    ok.get_style_context().add_class("neuronix-primary")
    ok.connect("clicked", _finish)
    outer.pack_start(choice._action_row(ok), False, False, 0)
    win.set_default(ok)
    win.connect(
        "key-press-event",
        lambda _w, event: _finish() if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_Return) else False,
    )
    win.connect("destroy", _finish)
    win.show_all()
    win.present()
    ok.grab_focus()
    loop.run()
    if win.get_realized():
        win.hide()
    win.destroy()


def _names_line(verb: str, names: list[str]) -> str:
    if not names:
        return f"{verb} nothing."
    if len(names) == 1:
        return f"{verb} {names[0]}."
    if len(names) <= 5:
        return f"{verb} {', '.join(names)}."
    return f"{verb} {len(names)} items ({', '.join(names[:5])}…)."


def _finish_job(store: dict, emit, *, title: str, body: str, ok: bool) -> None:
    """Status, log banner, notification, and a Done dialog when apt/flatpak finishes."""
    banner = f"\n=== {title} ===\n"
    store["log"] = str(store.get("log") or "") + banner
    store["status"] = title if title.endswith(".") else f"{title}."
    emit("log", banner)
    emit("status", store["status"])
    emit("idle", "ok" if ok else "fail")
    _desktop_notify(title, body, ok=ok)
    GLib.idle_add(lambda t=title, b=body: (_job_done_dialog(t, b), False)[1])


def _ask_sudo_password(
    prompt_text: str = "Enter your sudo password to upgrade.",
    confirm: str = "Upgrade",
) -> str | None:
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
    win.get_style_context().add_class("neuronix-settings")
    choice.center_layer_window(win, 440, 230)
    release_keys = choice.hold_layer_keyboard(win)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.get_style_context().add_class("neuronix-root")
    choice._glass_root(outer, alpha=1.0, radius=16, color="#1e1e1e")
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

    prompt = Gtk.Label(label=prompt_text, xalign=0.0)
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
    upgrade = Gtk.Button(label=confirm)
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


_SOFTWARE = {
    "running": False,
    "status": "Search Debian packages with apt, then install the ones you pick.",
    "log": "",
    "sink": None,
    "done_install": [],
    "done_remove": [],
}


def _software_emit(kind: str, text: str) -> None:
    sink = _SOFTWARE.get("sink")

    def _do(current=sink) -> bool:
        if _SOFTWARE.get("sink") is not current or current is None:
            return False
        if kind == "log":
            buf = current["buf"]
            buf.insert(buf.get_end_iter(), text)
            current["view"].scroll_to_iter(buf.get_end_iter(), 0.0, False, 0.0, 1.0)
        elif kind == "status":
            current["status"].set_text(text)
        elif kind == "idle":
            current["install"].set_sensitive(True)
            current["search_btn"].set_sensitive(True)
            sync = current.get("sync_rows")
            if callable(sync):
                sync()
        elif kind == "busy":
            current["install"].set_sensitive(False)
            current["search_btn"].set_sensitive(False)
        return False

    GLib.idle_add(_do)


def _apt_search_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in (query or "").split():
        token = raw.strip().strip("\"\'")
        if not token or token.startswith("-") or len(token) > 40:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(token)
        if len(terms) >= 6:
            break
    return terms


def _apt_parse_search(output: str, limit: int) -> list[dict]:
    import re

    items: list[dict] = []
    pending: dict | None = None
    name_re = re.compile(r"^([A-Za-z0-9][A-Za-z0-9.+-]*)/\S+")

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            items.append(pending)
        pending = None

    for raw in (output or "").splitlines():
        line = raw.rstrip()
        if not line or line.startswith("Sorting") or line.startswith("Full Text"):
            continue
        if line.startswith("  "):
            if pending is not None:
                extra = line.strip()
                if extra:
                    pending["desc"] = extra if not pending["desc"] else pending["desc"]
            continue
        flush()
        match = name_re.match(line)
        if not match:
            continue
        flags = ""
        if "[" in line and line.endswith("]"):
            flags = line.rsplit("[", 1)[1][:-1]
        bits = line.split()
        version = bits[1] if len(bits) > 1 else ""
        pending = {
            "name": match.group(1),
            "version": version,
            "desc": "",
            "installed": "installed" in flags.lower(),
        }
        if len(items) >= limit:
            pending = None
            break
    flush()
    return items[:limit]


def _apt_search_one(term: str, limit: int) -> list[dict]:
    import re

    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    env["NO_COLOR"] = "1"
    pattern = re.escape(term)
    try:
        proc = subprocess.run(
            ["apt", "search", "-o", "APT::Color=never", "--", pattern],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    return _apt_parse_search(proc.stdout or "", limit)


def _apt_search(query: str, limit: int = 80) -> list[dict]:
    query = (query or "").strip()
    if not query or len(query) > 120:
        return []
    terms = _apt_search_terms(query)
    if not terms:
        return []
    merged: dict[str, dict] = {}
    per = max(40, limit)
    for term in terms:
        for item in _apt_search_one(term, per):
            name = str(item.get("name") or "")
            if not name:
                continue
            prev = merged.get(name)
            if prev is None:
                merged[name] = item
            elif item.get("installed"):
                prev["installed"] = True
            if item.get("desc") and not (prev or item).get("desc"):
                merged[name]["desc"] = item.get("desc")
    keys = [term.casefold() for term in terms]
    nterms = len(keys)

    def score(item: dict) -> tuple:
        name = str(item.get("name") or "").casefold()
        blob = f"{name} {item.get('desc') or ''}".casefold()
        hits = sum(1 for key in keys if key in blob)
        name_hits = sum(1 for key in keys if key in name)
        return (hits == nterms, name_hits == nterms, hits, name_hits)

    ranked = sorted(merged.values(), key=score, reverse=True)
    return ranked[:limit]

def _valid_pkg(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", name or ""))


def _software_apply(password: str, install: list[str], remove: list[str]) -> None:
    def _line(text: str) -> None:
        _SOFTWARE["log"] += text
        _software_emit("log", text)

    ok_install: list[str] = []
    ok_remove: list[str] = []
    if install:
        shown = "sudo apt install -y " + " ".join(install)
        header = f"$ {shown}\n"
        _SOFTWARE["log"] += header
        _software_emit("log", header)
        argv = [
            "apt",
            "install",
            "-y",
            "-o",
            "Dpkg::Options::=--force-confdef",
            "-o",
            "Dpkg::Options::=--force-confold",
            "--",
            *install,
        ]
        if _run_apt(password, argv, on_line=_line) == 0:
            ok_install = list(install)
    if remove:
        shown = "sudo apt remove -y " + " ".join(remove)
        header = f"$ {shown}\n"
        _SOFTWARE["log"] += header
        _software_emit("log", header)
        argv = ["apt", "remove", "-y", "--", *remove]
        if _run_apt(password, argv, on_line=_line) == 0:
            ok_remove = list(remove)

    _SOFTWARE["running"] = False
    _SOFTWARE["done_install"] = ok_install
    _SOFTWARE["done_remove"] = ok_remove
    failed = (bool(install) and not ok_install) or (bool(remove) and not ok_remove)
    if not failed:
        if install and remove:
            title = "Finished"
            body = _names_line("Installed", ok_install) + " " + _names_line("Uninstalled", ok_remove)
        elif remove:
            title = "Uninstall finished"
            body = _names_line("Uninstalled", ok_remove)
        else:
            title = "Install finished"
            body = _names_line("Installed", ok_install)
    else:
        title = "Some packages failed"
        body = "Check the log for details."
    _finish_job(_SOFTWARE, _software_emit, title=title, body=body, ok=not failed)


def software_page() -> Gtk.Widget:
    box = _page()
    box.pack_start(
        _note("Tick packages to install. Untick an installed package to uninstall it."),
        False,
        False,
        0,
    )
    query = Gtk.Entry()
    query.set_placeholder_text("steam installer")
    query.get_style_context().add_class("neuronix-entry")
    search_btn = _button("Search")
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    query.set_hexpand(True)
    row.pack_start(query, True, True, 0)
    row.pack_start(search_btn, False, False, 0)
    box.pack_start(row, False, False, 0)

    box.pack_start(_section("Packages"), False, False, 0)
    lst = Gtk.ListBox()
    lst.set_selection_mode(Gtk.SelectionMode.NONE)
    lst.set_activate_on_single_click(True)
    lst.get_style_context().add_class("neuronix-list")
    scroll = Gtk.ScrolledWindow()
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)
    scroll.set_size_request(-1, 220)
    scroll.add(lst)
    box.pack_start(scroll, True, True, 0)

    picked = Gtk.Label(label="No packages selected.", xalign=0.0)
    picked.get_style_context().add_class("neuronix-subtitle")
    install = _button("Install selected")
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.pack_start(install, False, False, 0)
    actions.pack_start(picked, True, True, 0)
    status = _note(_SOFTWARE["status"])
    foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    foot.pack_start(actions, False, False, 0)
    foot.pack_start(status, False, False, 0)
    card = getattr(box, "_card", None)
    if card is not None:
        Gtk.Box.pack_end(card, foot, False, False, 0)
    else:
        box.pack_start(foot, False, False, 0)

    buf = Gtk.TextBuffer()
    if _SOFTWARE["log"]:
        buf.set_text(_SOFTWARE["log"])
    view = Gtk.TextView.new_with_buffer(buf)
    view.set_editable(False)
    view.set_monospace(True)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_style_context().add_class("neuronix-text")
    log_scroll = Gtk.ScrolledWindow()
    log_scroll.get_style_context().add_class("neuronix-well")
    log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    log_scroll.set_size_request(-1, 140)
    log_scroll.add(view)
    log_btn = _button("Log  ▸")
    log_reveal = Gtk.Revealer()
    log_reveal.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
    log_reveal.set_reveal_child(False)
    log_reveal.add(log_scroll)
    box.pack_end(log_btn, False, False, 0)
    box.pack_end(log_reveal, False, False, 0)

    def _set_log(open_: bool) -> None:
        log_reveal.set_reveal_child(open_)
        log_btn.set_label("Log  ▾" if open_ else "Log  ▸")

    log_btn.connect("clicked", lambda *_a: _set_log(not log_reveal.get_reveal_child()))

    state = {"gen": 0, "rows": [], "ignore_toggle": False}
    sink = {
        "buf": buf,
        "view": view,
        "status": status,
        "install": install,
        "search_btn": search_btn,
        "open_log": lambda: _set_log(True),
    }
    _SOFTWARE["sink"] = sink
    if _SOFTWARE["running"]:
        install.set_sensitive(False)
        search_btn.set_sensitive(False)
        _set_log(True)

    def _drop(*_a) -> None:
        if _SOFTWARE.get("sink") is sink:
            _SOFTWARE["sink"] = None

    box.connect("destroy", _drop)

    def _to_install() -> list[str]:
        names = []
        for row in state["rows"]:
            check = getattr(row, "_check", None)
            name = str(getattr(row, "_pkg", "") or "")
            if check is None or getattr(row, "_installed", False):
                continue
            if check.get_active() and _valid_pkg(name):
                names.append(name)
        return names

    def _to_remove() -> list[str]:
        names = []
        for row in state["rows"]:
            check = getattr(row, "_check", None)
            name = str(getattr(row, "_pkg", "") or "")
            if check is None or not getattr(row, "_installed", False):
                continue
            if (not check.get_active()) and _valid_pkg(name):
                names.append(name)
        return names

    def _refresh_picked(*_a) -> None:
        if state.get("ignore_toggle"):
            return
        ins = _to_install()
        rem = _to_remove()
        if not ins and not rem:
            picked.set_text("No packages selected.")
            install.set_label("Install selected")
        elif ins and rem:
            picked.set_text(f"Install {len(ins)}, uninstall {len(rem)}")
            install.set_label("Apply selected")
        elif rem:
            if len(rem) == 1:
                picked.set_text("Uninstall " + rem[0])
            else:
                picked.set_text(
                    f"{len(rem)} packages: " + ", ".join(rem[:8]) + ("…" if len(rem) > 8 else "")
                )
            install.set_label("Uninstall selected")
        elif len(ins) == 1:
            picked.set_text(ins[0])
            install.set_label("Install selected")
        else:
            picked.set_text(
                f"{len(ins)} packages: " + ", ".join(ins[:8]) + ("…" if len(ins) > 8 else "")
            )
            install.set_label("Install selected")

    def _clear_rows() -> None:
        for child in list(lst.get_children()):
            lst.remove(child)
            child.destroy()
        state["rows"] = []
        _refresh_picked()

    def _add_row(item: dict) -> None:
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("neuronix-list-row")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        check = Gtk.CheckButton()
        check.set_valign(Gtk.Align.CENTER)
        installed = bool(item.get("installed"))
        check.set_active(installed)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label=str(item.get("name") or ""), xalign=0.0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.get_style_context().add_class("neuronix-row-title")
        base_desc = str(item.get("desc") or "").strip()
        version = str(item.get("version") or "").strip()
        if installed:
            extra = "Installed" + (f"  ·  {base_desc}" if base_desc else "")
        elif version:
            extra = f"{version}" + (f"  ·  {base_desc}" if base_desc else "")
        else:
            extra = base_desc
        desc = Gtk.Label(label=extra, xalign=0.0)
        desc.set_ellipsize(Pango.EllipsizeMode.END)
        desc.get_style_context().add_class("neuronix-row-desc")
        text.pack_start(title, False, False, 0)
        text.pack_start(desc, False, False, 0)
        inner.pack_start(check, False, False, 0)
        inner.pack_start(text, True, True, 0)
        row.add(inner)
        row._pkg = str(item.get("name") or "")  # type: ignore[attr-defined]
        row._check = check  # type: ignore[attr-defined]
        row._installed = installed  # type: ignore[attr-defined]
        row._base_desc = base_desc  # type: ignore[attr-defined]
        row._version = version  # type: ignore[attr-defined]
        row._desc = desc  # type: ignore[attr-defined]
        check.connect("toggled", _refresh_picked)
        lst.add(row)
        state["rows"].append(row)

    def _fill(items: list[dict], err: str) -> None:
        _clear_rows()
        if err:
            status.set_text(err)
            return
        if not items:
            status.set_text("No packages matched.")
            return
        for item in items:
            _add_row(item)
        lst.show_all()
        status.set_text(f"{len(items)} package{'s' if len(items) != 1 else ''}.")
        _refresh_picked()

    def _search(*_a) -> None:
        if _SOFTWARE["running"]:
            return
        needle = query.get_text().strip()
        if not needle:
            status.set_text("Type a package name, then search.")
            return
        state["gen"] += 1
        gen = state["gen"]
        status.set_text("Searching…")
        search_btn.set_sensitive(False)

        def _work() -> None:
            try:
                items = _apt_search(needle)
                err = ""
            except Exception as exc:
                items = []
                err = str(exc) or "Search failed."

            def _done() -> bool:
                if state["gen"] != gen:
                    return False
                search_btn.set_sensitive(True)
                _fill(items, err)
                return False

            GLib.idle_add(_done)

        threading.Thread(target=_work, daemon=True).start()

    def _set_row_installed(row, installed: bool) -> None:
        row._installed = installed  # type: ignore[attr-defined]
        check = getattr(row, "_check", None)
        desc = getattr(row, "_desc", None)
        base = str(getattr(row, "_base_desc", "") or "")
        version = str(getattr(row, "_version", "") or "")
        state["ignore_toggle"] = True
        if check is not None:
            check.set_active(installed)
        state["ignore_toggle"] = False
        if installed:
            extra = "Installed" + (f"  ·  {base}" if base else "")
        elif version:
            extra = f"{version}" + (f"  ·  {base}" if base else "")
        else:
            extra = base
        if desc is not None:
            desc.set_text(extra)

    def _sync_rows() -> None:
        done_install = set(_SOFTWARE.get("done_install") or [])
        done_remove = set(_SOFTWARE.get("done_remove") or [])
        if not done_install and not done_remove:
            _refresh_picked()
            return
        for row in state["rows"]:
            name = str(getattr(row, "_pkg", "") or "")
            if name in done_install:
                _set_row_installed(row, True)
            elif name in done_remove:
                _set_row_installed(row, False)
        _SOFTWARE["done_install"] = []
        _SOFTWARE["done_remove"] = []
        _refresh_picked()

    sink["sync_rows"] = _sync_rows

    def _toggle(_lb, row) -> None:
        if _SOFTWARE["running"]:
            return
        check = getattr(row, "_check", None)
        if check is not None:
            check.set_active(not check.get_active())

    def _install(*_a) -> None:
        if _SOFTWARE["running"]:
            return
        names = _to_install()
        remove = _to_remove()
        if not names and not remove:
            status.set_text("Tick packages to install, or untick installed ones to uninstall.")
            return
        if names and remove:
            prompt = (
                f"Enter your sudo password to install {len(names)} and "
                f"uninstall {len(remove)} package{'s' if (len(names) + len(remove)) != 1 else ''}."
            )
            confirm = "Apply"
            busy = "Applying…"
        elif remove:
            prompt = (
                f"Enter your sudo password to uninstall {len(remove)} "
                f"package{'s' if len(remove) != 1 else ''}."
            )
            confirm = "Uninstall"
            busy = "Uninstalling…"
        else:
            prompt = (
                f"Enter your sudo password to install {len(names)} "
                f"package{'s' if len(names) != 1 else ''}."
            )
            confirm = "Install"
            busy = "Installing…"
        password = _ask_sudo_password(prompt, confirm)
        if not password:
            return
        _SOFTWARE["running"] = True
        _SOFTWARE["log"] = ""
        _SOFTWARE["status"] = busy
        _SOFTWARE["done_install"] = []
        _SOFTWARE["done_remove"] = []
        buf.set_text("")
        status.set_text(_SOFTWARE["status"])
        search_btn.set_sensitive(False)
        install.set_sensitive(False)
        _set_log(True)
        threading.Thread(
            target=_software_apply, args=(password, names, remove), daemon=True
        ).start()

    lst.connect("row-activated", _toggle)
    search_btn.connect("clicked", _search)
    query.connect("activate", _search)
    install.connect("clicked", _install)
    return box



def _run_logged(argv: list[str], on_line=None, password: str | None = None) -> int:
    """Stream a command's output. Uses sudo -S when password is set."""
    if password:
        return _run_apt(password, argv, on_line=on_line)
    cmd = list(argv)
    stdbuf = "/usr/bin/stdbuf"
    if os.path.isfile(stdbuf):
        cmd = [stdbuf, "-oL", "-eL", *cmd]
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
    except OSError as exc:
        err = str(exc) + "\n"
        if on_line is not None:
            on_line(err)
        return 127
    assert proc.stdout is not None
    for line in proc.stdout:
        if on_line is not None:
            on_line(line)
    return proc.wait()


def _flatpak_bin() -> str:
    for cand in ("/usr/bin/flatpak", "/usr/local/bin/flatpak"):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return "flatpak"


def _valid_flatpak_id(name: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,200}", name or "")) and "." in (name or "")


_FLATPAK = {
    "running": False,
    "status": "Search Flathub, tick apps to install, untick installed ones to uninstall.",
    "log": "",
    "sink": None,
    "done_install": [],
    "done_remove": [],
}


def _flatpak_emit(kind: str, text: str) -> None:
    sink = _FLATPAK.get("sink")

    def _do(current=sink) -> bool:
        if _FLATPAK.get("sink") is not current or current is None:
            return False
        if kind == "log":
            buf = current["buf"]
            buf.insert(buf.get_end_iter(), text)
            current["view"].scroll_to_iter(buf.get_end_iter(), 0.0, False, 0.0, 1.0)
        elif kind == "status":
            current["status"].set_text(text)
        elif kind == "idle":
            current["install"].set_sensitive(True)
            current["search_btn"].set_sensitive(True)
            sync = current.get("sync_rows")
            if callable(sync):
                sync()
        elif kind == "busy":
            current["install"].set_sensitive(False)
            current["search_btn"].set_sensitive(False)
        return False

    GLib.idle_add(_do)


def _flatpak_parse_rows(output: str, *, kind: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for raw in (output or "").splitlines():
        line = raw.rstrip()
        if not line or line.startswith("No matches") or line.startswith("Looking for"):
            continue
        parts = line.split("\t")
        appid = (parts[0] if parts else "").strip()
        if not _valid_flatpak_id(appid) or appid in seen:
            continue
        seen.add(appid)
        name = parts[1].strip() if len(parts) > 1 else appid
        version = parts[2].strip() if len(parts) > 2 else ""
        if kind == "list":
            origin = parts[3].strip() if len(parts) > 3 else "flathub"
            installation = (parts[4].strip() if len(parts) > 4 else "system").casefold()
            desc = parts[5].strip() if len(parts) > 5 else ""
            installed = True
        else:
            desc = parts[3].strip() if len(parts) > 3 else ""
            origin = parts[4].strip() if len(parts) > 4 else "flathub"
            installation = ""
            installed = False
        origin = (origin.split(",")[0].strip() or "flathub")
        if installation not in ("user", "system"):
            installation = "system" if kind == "list" else ""
        items.append(
            {
                "id": appid,
                "name": name or appid,
                "version": version,
                "desc": desc,
                "origin": origin,
                "installation": installation,
                "installed": installed,
            }
        )
    return items


def _flatpak_installed_map() -> dict[str, dict]:
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    try:
        proc = subprocess.run(
            [
                _flatpak_bin(),
                "list",
                "--app",
                "--columns=application,name,version,origin,installation,description",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    items = _flatpak_parse_rows(proc.stdout or "", kind="list")
    return {str(item["id"]): item for item in items}


def _flatpak_search_one(term: str, limit: int) -> list[dict]:
    env = os.environ.copy()
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    try:
        proc = subprocess.run(
            [
                _flatpak_bin(),
                "search",
                "--columns=application,name,version,description,remotes",
                term,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=25,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    return _flatpak_parse_rows(proc.stdout or "", kind="search")[:limit]


def _flatpak_search(query: str, limit: int = 80) -> list[dict]:
    installed = _flatpak_installed_map()
    query = (query or "").strip()
    if not query:
        return sorted(installed.values(), key=lambda item: str(item.get("name") or "").casefold())
    terms = _apt_search_terms(query)
    if not terms:
        return []
    merged: dict[str, dict] = {}
    per = max(40, limit)
    for term in terms:
        for item in _flatpak_search_one(term, per):
            appid = str(item.get("id") or "")
            if not appid:
                continue
            have = installed.get(appid)
            if have is not None:
                item["installed"] = True
                item["installation"] = have.get("installation") or item.get("installation")
                item["origin"] = have.get("origin") or item.get("origin")
            prev = merged.get(appid)
            if prev is None:
                merged[appid] = item
            elif item.get("installed"):
                prev["installed"] = True
    keys = [term.casefold() for term in terms]
    nterms = len(keys)

    def score(item: dict) -> tuple:
        import re

        appid = str(item.get("id") or "").casefold()
        name = str(item.get("name") or "").casefold()
        blob = f"{appid} {name} {item.get('desc') or ''}".casefold()

        def word(hay: str, key: str) -> bool:
            return bool(re.search(rf"(^|[^a-z0-9]){re.escape(key)}([^a-z0-9]|$)", hay))

        exact_name = any(key == name for key in keys)
        exact_id = any(key == appid or appid.endswith("." + key) for key in keys)
        name_words = sum(1 for key in keys if word(name, key))
        id_words = sum(1 for key in keys if word(appid.replace(".", " "), key) or key in appid)
        hits = sum(1 for key in keys if key in blob)
        return (exact_name, exact_id, name_words == nterms, name_words, id_words, hits)

    ranked = sorted(merged.values(), key=score, reverse=True)
    return ranked[:limit]


def _flatpak_apply(
    password: str | None,
    install: list[str],
    remove: list[str],
    origins: dict[str, str],
    installs_where: dict[str, str],
) -> None:
    def _line(text: str) -> None:
        _FLATPAK["log"] += text
        _flatpak_emit("log", text)

    bin_ = _flatpak_bin()
    ok_install: list[str] = []
    ok_remove: list[str] = []
    if install:
        from collections import defaultdict

        groups: dict[str, list[str]] = defaultdict(list)
        for appid in install:
            origin = origins.get(appid) or "flathub"
            groups[origin].append(appid)
        _line("$ flatpak remote-add --if-not-exists flathub …\n")
        _run_logged(
            [
                bin_,
                "remote-add",
                "--if-not-exists",
                "flathub",
                "https://dl.flathub.org/repo/flathub.flatpakrepo",
            ],
            on_line=_line,
            password=password,
        )
        for origin, names in groups.items():
            shown = "sudo flatpak install -y --noninteractive --system " + origin + " " + " ".join(names)
            header = f"$ {shown}\n"
            _FLATPAK["log"] += header
            _flatpak_emit("log", header)
            argv = [
                bin_,
                "install",
                "-y",
                "--noninteractive",
                "--system",
                origin,
                *names,
            ]
            if _run_logged(argv, on_line=_line, password=password) == 0:
                ok_install.extend(names)
    if remove:
        from collections import defaultdict

        groups = defaultdict(list)
        for appid in remove:
            where = (installs_where.get(appid) or "system").casefold()
            groups["user" if where == "user" else "system"].append(appid)
        for where, names in groups.items():
            flag = "--user" if where == "user" else "--system"
            need_pass = password if where == "system" else None
            shown = (
                ("sudo " if need_pass else "")
                + "flatpak uninstall -y --noninteractive "
                + flag
                + " "
                + " ".join(names)
            )
            header = f"$ {shown}\n"
            _FLATPAK["log"] += header
            _flatpak_emit("log", header)
            argv = [bin_, "uninstall", "-y", "--noninteractive", flag, *names]
            if _run_logged(argv, on_line=_line, password=need_pass) == 0:
                ok_remove.extend(names)

    _FLATPAK["running"] = False
    _FLATPAK["done_install"] = ok_install
    _FLATPAK["done_remove"] = ok_remove
    failed = (bool(install) and set(ok_install) != set(install)) or (
        bool(remove) and set(ok_remove) != set(remove)
    )
    if not failed:
        if install and remove:
            title = "Finished"
            body = _names_line("Installed", ok_install) + " " + _names_line("Uninstalled", ok_remove)
        elif remove:
            title = "Uninstall finished"
            body = _names_line("Uninstalled", ok_remove)
        else:
            title = "Install finished"
            body = _names_line("Installed", ok_install)
    else:
        title = "Some Flatpaks failed"
        body = "Check the log for details."
    _finish_job(_FLATPAK, _flatpak_emit, title=title, body=body, ok=not failed)


def flatpak_page() -> Gtk.Widget:
    box = _page()
    box.pack_start(
        _note("Search Flathub. Tick apps to install, untick installed apps to uninstall."),
        False,
        False,
        0,
    )
    query = Gtk.Entry()
    query.set_placeholder_text("steam")
    query.get_style_context().add_class("neuronix-entry")
    search_btn = _button("Search")
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    query.set_hexpand(True)
    row.pack_start(query, True, True, 0)
    row.pack_start(search_btn, False, False, 0)
    box.pack_start(row, False, False, 0)

    box.pack_start(_section("Flatpaks"), False, False, 0)
    lst = Gtk.ListBox()
    lst.set_selection_mode(Gtk.SelectionMode.NONE)
    lst.set_activate_on_single_click(True)
    lst.get_style_context().add_class("neuronix-list")
    scroll = Gtk.ScrolledWindow()
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_vexpand(True)
    scroll.set_size_request(-1, 220)
    scroll.add(lst)
    box.pack_start(scroll, True, True, 0)

    picked = Gtk.Label(label="No apps selected.", xalign=0.0)
    picked.get_style_context().add_class("neuronix-subtitle")
    install = _button("Install selected")
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.pack_start(install, False, False, 0)
    actions.pack_start(picked, True, True, 0)
    status = _note(_FLATPAK["status"])
    foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    foot.pack_start(actions, False, False, 0)
    foot.pack_start(status, False, False, 0)
    card = getattr(box, "_card", None)
    if card is not None:
        Gtk.Box.pack_end(card, foot, False, False, 0)
    else:
        box.pack_start(foot, False, False, 0)

    buf = Gtk.TextBuffer()
    if _FLATPAK["log"]:
        buf.set_text(_FLATPAK["log"])
    view = Gtk.TextView.new_with_buffer(buf)
    view.set_editable(False)
    view.set_monospace(True)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_style_context().add_class("neuronix-text")
    log_scroll = Gtk.ScrolledWindow()
    log_scroll.get_style_context().add_class("neuronix-well")
    log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    log_scroll.set_size_request(-1, 140)
    log_scroll.add(view)
    log_btn = _button("Log  ▸")
    log_reveal = Gtk.Revealer()
    log_reveal.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
    log_reveal.set_reveal_child(False)
    log_reveal.add(log_scroll)
    box.pack_end(log_btn, False, False, 0)
    box.pack_end(log_reveal, False, False, 0)

    def _set_log(open_: bool) -> None:
        log_reveal.set_reveal_child(open_)
        log_btn.set_label("Log  ▾" if open_ else "Log  ▸")

    log_btn.connect("clicked", lambda *_a: _set_log(not log_reveal.get_reveal_child()))

    state = {"gen": 0, "rows": [], "ignore_toggle": False}
    sink = {
        "buf": buf,
        "view": view,
        "status": status,
        "install": install,
        "search_btn": search_btn,
        "open_log": lambda: _set_log(True),
    }
    _FLATPAK["sink"] = sink
    if _FLATPAK["running"]:
        install.set_sensitive(False)
        search_btn.set_sensitive(False)
        _set_log(True)

    def _drop(*_a) -> None:
        if _FLATPAK.get("sink") is sink:
            _FLATPAK["sink"] = None

    box.connect("destroy", _drop)

    def _to_install() -> list[str]:
        names = []
        for item in state["rows"]:
            check = getattr(item, "_check", None)
            name = str(getattr(item, "_pkg", "") or "")
            if check is None or getattr(item, "_installed", False):
                continue
            if check.get_active() and _valid_flatpak_id(name):
                names.append(name)
        return names

    def _to_remove() -> list[str]:
        names = []
        for item in state["rows"]:
            check = getattr(item, "_check", None)
            name = str(getattr(item, "_pkg", "") or "")
            if check is None or not getattr(item, "_installed", False):
                continue
            if (not check.get_active()) and _valid_flatpak_id(name):
                names.append(name)
        return names

    def _refresh_picked(*_a) -> None:
        if state.get("ignore_toggle"):
            return
        ins = _to_install()
        rem = _to_remove()
        if not ins and not rem:
            picked.set_text("No apps selected.")
            install.set_label("Install selected")
        elif ins and rem:
            picked.set_text(f"Install {len(ins)}, uninstall {len(rem)}")
            install.set_label("Apply selected")
        elif rem:
            if len(rem) == 1:
                picked.set_text("Uninstall " + rem[0])
            else:
                picked.set_text(
                    f"{len(rem)} apps: " + ", ".join(rem[:8]) + ("…" if len(rem) > 8 else "")
                )
            install.set_label("Uninstall selected")
        elif len(ins) == 1:
            picked.set_text(ins[0])
            install.set_label("Install selected")
        else:
            picked.set_text(
                f"{len(ins)} apps: " + ", ".join(ins[:8]) + ("…" if len(ins) > 8 else "")
            )
            install.set_label("Install selected")

    def _clear_rows() -> None:
        for child in list(lst.get_children()):
            lst.remove(child)
            child.destroy()
        state["rows"] = []
        _refresh_picked()

    def _add_row(item: dict) -> None:
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("neuronix-list-row")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        check = Gtk.CheckButton()
        check.set_valign(Gtk.Align.CENTER)
        installed = bool(item.get("installed"))
        check.set_active(installed)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label=str(item.get("name") or item.get("id") or ""), xalign=0.0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.get_style_context().add_class("neuronix-row-title")
        appid = str(item.get("id") or "")
        base_desc = str(item.get("desc") or "").strip()
        version = str(item.get("version") or "").strip()
        bits = []
        if installed:
            bits.append("Installed")
        if version:
            bits.append(version)
        if appid:
            bits.append(appid)
        extra = "  ·  ".join(bits)
        if base_desc:
            extra = extra + ("  ·  " if extra else "") + base_desc
        desc = Gtk.Label(label=extra, xalign=0.0)
        desc.set_ellipsize(Pango.EllipsizeMode.END)
        desc.get_style_context().add_class("neuronix-row-desc")
        text.pack_start(title, False, False, 0)
        text.pack_start(desc, False, False, 0)
        inner.pack_start(check, False, False, 0)
        inner.pack_start(text, True, True, 0)
        row.add(inner)
        row._pkg = appid  # type: ignore[attr-defined]
        row._check = check  # type: ignore[attr-defined]
        row._installed = installed  # type: ignore[attr-defined]
        row._origin = str(item.get("origin") or "flathub")  # type: ignore[attr-defined]
        row._installation = str(item.get("installation") or "")  # type: ignore[attr-defined]
        row._base_desc = base_desc  # type: ignore[attr-defined]
        row._version = version  # type: ignore[attr-defined]
        row._pretty = str(item.get("name") or appid)  # type: ignore[attr-defined]
        row._desc = desc  # type: ignore[attr-defined]
        check.connect("toggled", _refresh_picked)
        lst.add(row)
        state["rows"].append(row)

    def _fill(items: list[dict], err: str) -> None:
        _clear_rows()
        if err:
            status.set_text(err)
            return
        if not items:
            status.set_text("No Flatpaks matched.")
            return
        for item in items:
            _add_row(item)
        lst.show_all()
        status.set_text(f"{len(items)} app{'s' if len(items) != 1 else ''}.")
        _refresh_picked()

    def _search(*_a) -> None:
        if _FLATPAK["running"]:
            return
        needle = query.get_text().strip()
        state["gen"] += 1
        gen = state["gen"]
        status.set_text("Searching…" if needle else "Loading installed Flatpaks…")
        search_btn.set_sensitive(False)

        def _work() -> None:
            try:
                items = _flatpak_search(needle)
                err = ""
            except Exception as exc:
                items = []
                err = str(exc) or "Search failed."

            def _done() -> bool:
                if state["gen"] != gen:
                    return False
                search_btn.set_sensitive(True)
                _fill(items, err)
                return False

            GLib.idle_add(_done)

        threading.Thread(target=_work, daemon=True).start()

    def _set_row_installed(row, installed: bool) -> None:
        row._installed = installed  # type: ignore[attr-defined]
        check = getattr(row, "_check", None)
        desc = getattr(row, "_desc", None)
        base = str(getattr(row, "_base_desc", "") or "")
        version = str(getattr(row, "_version", "") or "")
        appid = str(getattr(row, "_pkg", "") or "")
        state["ignore_toggle"] = True
        if check is not None:
            check.set_active(installed)
        state["ignore_toggle"] = False
        bits = []
        if installed:
            bits.append("Installed")
            row._installation = "system"  # type: ignore[attr-defined]
        if version:
            bits.append(version)
        if appid:
            bits.append(appid)
        extra = "  ·  ".join(bits)
        if base:
            extra = extra + ("  ·  " if extra else "") + base
        if desc is not None:
            desc.set_text(extra)

    def _sync_rows() -> None:
        done_install = set(_FLATPAK.get("done_install") or [])
        done_remove = set(_FLATPAK.get("done_remove") or [])
        if not done_install and not done_remove:
            _refresh_picked()
            return
        for item in state["rows"]:
            name = str(getattr(item, "_pkg", "") or "")
            if name in done_install:
                _set_row_installed(item, True)
            elif name in done_remove:
                _set_row_installed(item, False)
        _FLATPAK["done_install"] = []
        _FLATPAK["done_remove"] = []
        _refresh_picked()

    sink["sync_rows"] = _sync_rows

    def _toggle(_lb, row) -> None:
        if _FLATPAK["running"]:
            return
        check = getattr(row, "_check", None)
        if check is not None:
            check.set_active(not check.get_active())

    def _install(*_a) -> None:
        if _FLATPAK["running"]:
            return
        names = _to_install()
        remove = _to_remove()
        if not names and not remove:
            status.set_text("Tick apps to install, or untick installed ones to uninstall.")
            return
        origins = {}
        where = {}
        for item in state["rows"]:
            appid = str(getattr(item, "_pkg", "") or "")
            if appid in names:
                origins[appid] = str(getattr(item, "_origin", "") or "flathub")
            if appid in remove:
                where[appid] = str(getattr(item, "_installation", "") or "system")
        need_sudo = bool(names) or any((where.get(appid) or "system") != "user" for appid in remove)
        if names and remove:
            prompt = (
                f"Enter your sudo password to install {len(names)} and "
                f"uninstall {len(remove)} Flatpak{'s' if (len(names) + len(remove)) != 1 else ''}."
            )
            confirm = "Apply"
            busy = "Applying…"
        elif remove:
            prompt = (
                f"Enter your sudo password to uninstall {len(remove)} "
                f"Flatpak{'s' if len(remove) != 1 else ''}."
            )
            confirm = "Uninstall"
            busy = "Uninstalling…"
        else:
            prompt = (
                f"Enter your sudo password to install {len(names)} "
                f"Flatpak{'s' if len(names) != 1 else ''}."
            )
            confirm = "Install"
            busy = "Installing…"
        password = None
        if need_sudo:
            password = _ask_sudo_password(prompt, confirm)
            if not password:
                return
        _FLATPAK["running"] = True
        _FLATPAK["log"] = ""
        _FLATPAK["status"] = busy
        _FLATPAK["done_install"] = []
        _FLATPAK["done_remove"] = []
        buf.set_text("")
        status.set_text(_FLATPAK["status"])
        search_btn.set_sensitive(False)
        install.set_sensitive(False)
        _set_log(True)
        threading.Thread(
            target=_flatpak_apply,
            args=(password, names, remove, origins, where),
            daemon=True,
        ).start()

    lst.connect("row-activated", _toggle)
    search_btn.connect("clicked", _search)
    query.connect("activate", _search)
    install.connect("clicked", _install)
    GLib.idle_add(lambda: (_search(), False)[1])
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
