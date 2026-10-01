#!/usr/bin/env python3
"""GTK pages for the Waybar settings window. Replaces the Qt hypr-settings tabs."""
from __future__ import annotations

import configparser
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

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


def displays_page() -> Gtk.Widget:
    box = _page()
    status = _note("Reading monitors…")
    box.pack_start(status, False, False, 0)
    rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.pack_start(rows_box, False, False, 0)
    apply_btn = _button("Apply")
    box.pack_start(apply_btn, False, False, 0)
    state: dict = {"mons": []}

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
            mode = Gtk.ComboBoxText()
            current = f"{mon.get('width')}x{mon.get('height')}@{float(mon.get('refreshRate') or 60):.0f}"
            modes = [str(m) for m in (mon.get("availableModes") or [])] or [current]
            if current not in modes:
                modes.insert(0, current)
            for item in modes:
                mode.append_text(item)
            mode.set_active(modes.index(current) if current in modes else 0)
            scale = Gtk.SpinButton.new_with_range(0.5, 3.0, 0.1)
            scale.set_digits(2)
            scale.set_value(float(mon.get("scale") or 1))
            pos = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            x_ent = Gtk.Entry()
            y_ent = Gtk.Entry()
            x_ent.set_text(str(int(mon.get("x") or 0)))
            y_ent.set_text(str(int(mon.get("y") or 0)))
            x_ent.set_width_chars(6)
            y_ent.set_width_chars(6)
            pos.pack_start(Gtk.Label(label="X", xalign=0.0), False, False, 0)
            pos.pack_start(x_ent, False, False, 0)
            pos.pack_start(Gtk.Label(label="Y", xalign=0.0), False, False, 0)
            pos.pack_start(y_ent, False, False, 0)
            card.pack_start(mode, False, False, 0)
            card.pack_start(scale, False, False, 0)
            card.pack_start(pos, False, False, 0)
            rows_box.pack_start(card, False, False, 0)
            editors.append((mon, mode, scale, x_ent, y_ent))
        state["editors"] = editors
        rows_box.show_all()

    def _apply(*_a) -> None:
        written = []
        for mon, mode, scale, x_ent, y_ent in state.get("editors") or []:
            name = str(mon.get("name") or "")
            spec = (mode.get_active_text() or "").strip()
            try:
                x = int(x_ent.get_text().strip() or "0")
                y = int(y_ent.get_text().strip() or "0")
            except ValueError:
                status.set_text(f"{name}: position must be numbers")
                return
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


def themes_page() -> Gtk.Widget:
    box = _page()
    box.pack_start(
        _note("Themes opens the GTK theme editor. The editor applies colors, borders, and window chrome."),
        False,
        False,
        0,
    )
    btn = _button("Open Theme Editor")

    def _open(*_a) -> None:
        exe = quick._which("gtk-theme-editor") or "gtk-theme-editor"
        quick._launch_detached([exe])
        GLib.idle_add(Gtk.main_quit)

    btn.connect("clicked", _open)
    box.pack_start(btn, False, False, 0)
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
