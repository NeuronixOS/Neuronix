#!/usr/bin/env python3
"""GNOME-style Sound & Network panels for Waybar (no pavucontrol/nm fly-in)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

sys.path.insert(0, "/usr/share/neuronix")
sys.path.insert(0, os.path.expanduser("~/.local/share/neuronix"))
from neuronix_choice_dialog import (  # noqa: E402
    _action_row,
    _apply_css,
    _base_panel,
    _make_tile,
    entry as prompt_entry,
    freeze_click_xy,
)


def _run(cmd: list[str], timeout: float = 3.0) -> str:
    try:
        return subprocess.check_output(cmd, text=True, timeout=timeout, stderr=subprocess.DEVNULL)
    except Exception:
        return ""


def _run_ok(cmd: list[str], timeout: float = 8.0) -> bool:
    try:
        subprocess.run(cmd, check=True, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _which(name: str) -> Optional[str]:
    from shutil import which

    local = os.path.expanduser(f"~/.local/bin/{name}")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return which(name)


def _launch_detached(argv: list[str]) -> None:
    """Spawn outside this panel's cgroup so Advanced survives when we quit."""
    if not argv:
        return
    env = os.environ.copy()
    local = os.path.expanduser("~/.local/bin")
    env["PATH"] = f"{local}:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    if not env.get("NEURONIX_CLICK_XY"):
        try:
            env["NEURONIX_CLICK_XY"] = (
                subprocess.check_output(["hyprctl", "cursorpos"], text=True, timeout=1)
                .replace(" ", "")
                .strip()
            )
        except Exception:
            pass
    run = [
        "systemd-run",
        "--user",
        "--collect",
        "--quiet",
        "--property=KillMode=process",
    ]
    for key in (
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "DBUS_SESSION_BUS_ADDRESS",
        "DISPLAY",
        "PATH",
        "HOME",
        "NEURONIX_CLICK_XY",
        "XDG_CURRENT_DESKTOP",
    ):
        val = env.get(key)
        if val:
            run.append(f"--setenv={key}={val}")
    run.extend(["--", *argv])
    try:
        r = subprocess.run(run, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return
    except FileNotFoundError:
        pass
    subprocess.Popen(
        argv,
        start_new_session=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _friendly_sink(name: str) -> str:
    n = name or "Output"
    n = re.sub(r"^alsa_output\.", "", n)
    n = re.sub(r"^bluez_output\.", "Bluetooth ", n)
    n = n.replace(".", " · ").replace("_", " ")
    return n[:64]


# ── Sound ────────────────────────────────────────────────────────────────────


def _default_sink() -> str:
    return (_run(["pactl", "get-default-sink"]) or "").strip()


def _sink_volume_pct(sink: str = "@DEFAULT_SINK@") -> int:
    out = _run(["pactl", "get-sink-volume", sink])
    m = re.search(r"(\d+)%", out)
    return int(m.group(1)) if m else 0


def _sink_muted(sink: str = "@DEFAULT_SINK@") -> bool:
    out = _run(["pactl", "get-sink-mute", sink]).lower()
    return "yes" in out or "muted: yes" in out


def _list_sinks() -> list[tuple[str, str]]:
    """Return [(name, state), ...] from pactl list short sinks."""
    rows: list[tuple[str, str]] = []
    for line in (_run(["pactl", "list", "short", "sinks"]) or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[1], parts[4] if len(parts) > 4 else ""))
    return rows


def _set_volume(pct: int, sink: str = "@DEFAULT_SINK@") -> None:
    pct = max(0, min(150, int(pct)))
    _run_ok(["pactl", "set-sink-volume", sink, f"{pct}%"])


def _toggle_mute(sink: str = "@DEFAULT_SINK@") -> None:
    _run_ok(["pactl", "set-sink-mute", sink, "toggle"])


def _set_default_sink(name: str) -> None:
    _run_ok(["pactl", "set-default-sink", name])


def pack_sound_controls(
    outer: Gtk.Box,
    *,
    quit_on_advanced: bool = True,
    compact: bool = False,
    on_advanced: Optional[Callable[..., None]] = None,
) -> None:
    """Embed Sound controls into an existing container (popover or accordion)."""
    vol_lbl = Gtk.Label(label=f"{_sink_volume_pct()}%", xalign=1.0)
    vol_lbl.get_style_context().add_class("neuronix-pct")

    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
    scale.set_draw_value(False)
    scale.set_hexpand(True)
    scale.get_style_context().add_class("neuronix-scale")
    scale.set_value(_sink_volume_pct())

    mute_btn = Gtk.Button()
    mute_btn.set_relief(Gtk.ReliefStyle.NONE)

    def _refresh_mute_btn() -> None:
        muted = _sink_muted()
        mute_btn.set_label("Unmute" if muted else "Mute")
        mute_btn.get_style_context().remove_class("neuronix-toggle-on")
        mute_btn.get_style_context().remove_class("neuronix-toggle-off")
        mute_btn.get_style_context().add_class(
            "neuronix-toggle-off" if muted else "neuronix-toggle-on"
        )

    _refresh_mute_btn()

    def _on_scale(s: Gtk.Scale) -> None:
        pct = int(s.get_value())
        vol_lbl.set_text(f"{pct}%")
        _set_volume(pct)

    scale.connect("value-changed", _on_scale)

    def _on_mute(*_a) -> None:
        _toggle_mute()
        _refresh_mute_btn()
        if not _sink_muted():
            scale.set_value(_sink_volume_pct())
            vol_lbl.set_text(f"{_sink_volume_pct()}%")

    mute_btn.connect("clicked", _on_mute)

    vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    vol_row.pack_start(scale, True, True, 0)
    vol_row.pack_start(vol_lbl, False, False, 0)
    outer.pack_start(vol_row, False, False, 0)
    outer.pack_start(mute_btn, False, False, 0)

    devices_lbl = Gtk.Label(label="Output device", xalign=0.0)
    devices_lbl.get_style_context().add_class("neuronix-subtitle")
    outer.pack_start(devices_lbl, False, False, 0)

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.get_style_context().add_class("neuronix-list")

    def _rebuild_sinks() -> None:
        for child in list(listbox.get_children()):
            listbox.remove(child)
        cur = _default_sink()
        for name, state in _list_sinks():
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("neuronix-list-row")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            t = Gtk.Label(label=_friendly_sink(name), xalign=0.0)
            t.get_style_context().add_class("neuronix-row-title")
            t.set_ellipsize(Pango.EllipsizeMode.END)
            desc = "Default" if name == cur else (state.title() if state else "Available")
            d = Gtk.Label(label=desc, xalign=0.0)
            d.get_style_context().add_class("neuronix-row-desc")
            box.pack_start(t, False, False, 0)
            box.pack_start(d, False, False, 0)
            row.add(box)
            row._sink_name = name  # type: ignore[attr-defined]
            if name == cur:
                row.get_style_context().add_class("current")
            listbox.add(row)
        listbox.show_all()

    def _pick_sink(_lb, row: Gtk.ListBoxRow) -> None:
        name = getattr(row, "_sink_name", "") or ""
        if not name:
            return
        _set_default_sink(name)
        scale.set_value(_sink_volume_pct())
        vol_lbl.set_text(f"{_sink_volume_pct()}%")
        _refresh_mute_btn()
        _rebuild_sinks()

    listbox.connect("row-activated", _pick_sink)
    _rebuild_sinks()

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_size_request(-1, 140 if compact else 160)
    scroll.set_vexpand(not compact)
    scroll.add(listbox)
    outer.pack_start(scroll, not compact, not compact, 0)


def show_sound_panel() -> None:
    freeze_click_xy()
    _apply_css()
    win, outer, _result = _base_panel("Sound", width=420, height=480, subtitle="Output volume")
    pack_sound_controls(outer, quit_on_advanced=True)
    win.show_all()
    win.present()
    Gtk.main()


# ── Network ──────────────────────────────────────────────────────────────────


def _wifi_radio_on() -> bool:
    out = (_run(["nmcli", "-t", "-f", "WIFI", "radio"]) or "").strip().lower()
    return out in ("enabled", "on")


def _wifi_networks() -> list[dict]:
    """Deduped Wi-Fi scan rows: ssid, signal, security, in_use."""
    raw = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list"])
    best: dict[str, dict] = {}
    for line in raw.splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        ssid, signal, security, in_use = parts[0], parts[1], parts[2], parts[3]
        if not ssid:
            continue
        try:
            sig = int(signal)
        except Exception:
            sig = 0
        prev = best.get(ssid)
        if prev is None or sig > int(prev["signal"]) or in_use == "*":
            best[ssid] = {
                "ssid": ssid,
                "signal": sig,
                "security": security or "Open",
                "in_use": in_use == "*",
            }
    rows = list(best.values())
    rows.sort(key=lambda r: (not r["in_use"], -r["signal"], r["ssid"].lower()))
    return rows


def _active_summary() -> str:
    lines = []
    for line in (_run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"]) or "").splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, typ, dev = parts[0], parts[1], parts[2]
        if typ in ("loopback", "bridge", "tun", "wireguard") and not name.lower().startswith("wg"):
            if typ != "wireguard":
                continue
        if typ == "802-11-wireless":
            lines.append(f"Wi‑Fi · {name} ({dev})")
        elif typ == "802-3-ethernet":
            lines.append(f"Ethernet · {name} ({dev})")
        elif typ == "wireguard":
            lines.append(f"VPN · {name}")
    return "\n".join(lines) if lines else "No active connection"


def _connect_wifi(ssid: str, password: Optional[str] = None) -> bool:
    if password:
        return _run_ok(["nmcli", "device", "wifi", "connect", ssid, "password", password], timeout=30)
    # Try known connection first, then open network
    if _run_ok(["nmcli", "connection", "up", "id", ssid], timeout=20):
        return True
    return _run_ok(["nmcli", "device", "wifi", "connect", ssid], timeout=30)


def pack_network_controls(
    outer: Gtk.Box,
    *,
    quit_on_advanced: bool = True,
    compact: bool = False,
    on_advanced: Optional[Callable[..., None]] = None,
) -> None:
    """Embed Network controls into an existing container (popover or accordion)."""
    summary = Gtk.Label(label=_active_summary(), xalign=0.0)
    summary.get_style_context().add_class("neuronix-subtitle")
    summary.set_line_wrap(True)
    outer.pack_start(summary, False, False, 0)

    wifi_btn = Gtk.Button()
    wifi_btn.set_relief(Gtk.ReliefStyle.NONE)

    def _refresh_wifi_btn() -> None:
        on = _wifi_radio_on()
        wifi_btn.set_label("Wi‑Fi On" if on else "Wi‑Fi Off")
        wifi_btn.get_style_context().remove_class("neuronix-toggle-on")
        wifi_btn.get_style_context().remove_class("neuronix-toggle-off")
        wifi_btn.get_style_context().add_class("neuronix-toggle-on" if on else "neuronix-toggle-off")

    def _toggle_wifi(*_a) -> None:
        _run_ok(["nmcli", "radio", "wifi", "off" if _wifi_radio_on() else "on"])
        _refresh_wifi_btn()
        GLib.timeout_add(600, lambda: (_rebuild_wifi(), False)[1])

    _refresh_wifi_btn()
    wifi_btn.connect("clicked", _toggle_wifi)
    outer.pack_start(wifi_btn, False, False, 0)

    nets_lbl = Gtk.Label(label="Wi‑Fi networks", xalign=0.0)
    nets_lbl.get_style_context().add_class("neuronix-subtitle")
    outer.pack_start(nets_lbl, False, False, 0)

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.get_style_context().add_class("neuronix-list")
    status = Gtk.Label(label="", xalign=0.0)
    status.get_style_context().add_class("neuronix-subtitle")
    status.set_line_wrap(True)

    def _rebuild_wifi() -> None:
        for child in list(listbox.get_children()):
            listbox.remove(child)
        summary.set_text(_active_summary())
        if not _wifi_radio_on():
            status.set_text("Wi‑Fi is turned off.")
            listbox.show_all()
            return
        status.set_text("")
        for net in _wifi_networks():
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("neuronix-list-row")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            title = net["ssid"]
            if net["in_use"]:
                title = f"{title}  ·  connected"
                row.get_style_context().add_class("current")
            t = Gtk.Label(label=title, xalign=0.0)
            t.get_style_context().add_class("neuronix-row-title")
            t.set_ellipsize(Pango.EllipsizeMode.END)
            d = Gtk.Label(
                label=f"{net['signal']}%  ·  {net['security']}",
                xalign=0.0,
            )
            d.get_style_context().add_class("neuronix-row-desc")
            box.pack_start(t, False, False, 0)
            box.pack_start(d, False, False, 0)
            row.add(box)
            row._net = net  # type: ignore[attr-defined]
            listbox.add(row)
        listbox.show_all()

    def _pick_wifi(_lb, row: Gtk.ListBoxRow) -> None:
        net = getattr(row, "_net", None) or {}
        ssid = net.get("ssid") or ""
        if not ssid or net.get("in_use"):
            return
        status.set_text(f"Connecting to {ssid}…")

        def _do() -> bool:
            ok = _connect_wifi(ssid)
            sec = net.get("security") or ""
            needs_pw = any(x in sec for x in ("WPA", "WEP", "802.1X"))
            if not ok and needs_pw:
                pw = prompt_entry("Wi‑Fi password", f"Password for {ssid}", default="")
                if pw:
                    ok = _connect_wifi(ssid, pw)
            if ok:
                status.set_text(f"Connected to {ssid}")
                _rebuild_wifi()
            else:
                status.set_text(f"Could not connect to {ssid}")
            return False

        GLib.idle_add(_do)

    listbox.connect("row-activated", _pick_wifi)
    _rebuild_wifi()

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_size_request(-1, 160 if compact else 180)
    scroll.set_vexpand(not compact)
    scroll.add(listbox)
    outer.pack_start(scroll, not compact, not compact, 0)
    outer.pack_start(status, False, False, 0)

    refresh = Gtk.Button(label="Refresh")
    refresh.get_style_context().add_class("neuronix-secondary")
    refresh.connect(
        "clicked",
        lambda *_: (
            _run_ok(["nmcli", "device", "wifi", "rescan"]),
            GLib.timeout_add(800, lambda: (_rebuild_wifi(), False)[1]),
        ),
    )
    outer.pack_start(_action_row(refresh), False, False, 0)


def show_network_panel() -> None:
    freeze_click_xy()
    _apply_css()
    win, outer, _result = _base_panel("Network", width=440, height=560, subtitle=_active_summary())
    pack_network_controls(outer, quit_on_advanced=True)
    win.show_all()
    win.present()
    Gtk.main()


# ── CPU / Memory ─────────────────────────────────────────────────────────────


def _read_loadavg() -> tuple[float, float, float]:
    try:
        with open("/proc/loadavg", encoding="utf-8") as f:
            a, b, c, *_ = f.read().split()
        return float(a), float(b), float(c)
    except Exception:
        return 0.0, 0.0, 0.0


def _cpu_count() -> int:
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "CPU"


def _cpu_usage_pct() -> float:
    """Approximate overall CPU usage from /proc/stat over a short sample."""
    def _snap() -> tuple[int, int]:
        with open("/proc/stat", encoding="utf-8") as f:
            parts = f.readline().split()
        vals = [int(x) for x in parts[1:]]
        total = sum(vals)
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        return total, idle

    try:
        t0, i0 = _snap()
        import time as _time

        _time.sleep(0.12)
        t1, i1 = _snap()
        dt, di = t1 - t0, i1 - i0
        if dt <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))
    except Exception:
        return 0.0


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                num = v.strip().split()[0]
                out[k] = int(num)  # KiB
    except Exception:
        pass
    return out


def _fmt_gib(kib: float) -> str:
    return f"{kib / (1024 * 1024):.1f} GiB"


def _open_btop_detached(*, quit_after: bool = True) -> None:
    popover = _which("neuronix-waybar-popover")
    term = _which("gtk-term-launch.sh") or "gtk-term-launch.sh"
    btop = _which("btop") or "btop"
    if popover:
        _launch_detached(
            [
                popover,
                "--class",
                "btop",
                "--width",
                "960",
                "--height",
                "640",
                "--",
                term,
                "-e",
                btop,
            ]
        )
    else:
        _launch_detached([term, "-e", btop])
    if quit_after:
        GLib.idle_add(Gtk.main_quit)


def pack_cpu_controls(
    outer: Gtk.Box, *, quit_on_advanced: bool = True, compact: bool = False
) -> None:
    """Embed CPU stats into an existing container."""
    usage = _cpu_usage_pct()
    load1, load5, load15 = _read_loadavg()
    cores = _cpu_count()
    model = _cpu_model()

    model_lbl = Gtk.Label(label=model[:72], xalign=0.0)
    model_lbl.get_style_context().add_class("neuronix-subtitle")
    model_lbl.set_line_wrap(True)
    outer.pack_start(model_lbl, False, False, 0)

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.NONE)
    listbox.get_style_context().add_class("neuronix-list")

    def _add(title: str, value: str) -> None:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        row.get_style_context().add_class("neuronix-list-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        t = Gtk.Label(label=title, xalign=0.0)
        t.get_style_context().add_class("neuronix-row-title")
        t.set_hexpand(True)
        v = Gtk.Label(label=value, xalign=1.0)
        v.get_style_context().add_class("neuronix-row-desc")
        box.pack_start(t, True, True, 0)
        box.pack_end(v, False, False, 0)
        row.add(box)
        listbox.add(row)

    _add("Usage", f"{usage:.0f}%")
    _add("Cores / threads", str(cores))
    _add("Load average", f"{load1:.2f}  ·  {load5:.2f}  ·  {load15:.2f}")
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            secs = float(f.read().split()[0])
        days, rem = divmod(int(secs), 86400)
        hours, rem = divmod(rem, 3600)
        mins, _ = divmod(rem, 60)
        up = f"{days}d {hours}h {mins}m" if days else f"{hours}h {mins}m"
        _add("Uptime", up)
    except Exception:
        pass

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_size_request(-1, 120 if compact else 140)
    scroll.set_vexpand(not compact)
    scroll.add(listbox)
    outer.pack_start(scroll, not compact, not compact, 0)

    btop_btn = Gtk.Button(label="Open btop…")
    btop_btn.get_style_context().add_class("neuronix-secondary")
    btop_btn.connect(
        "clicked", lambda *_: _open_btop_detached(quit_after=quit_on_advanced)
    )
    outer.pack_start(_action_row(btop_btn), False, False, 0)


def show_cpu_panel() -> None:
    freeze_click_xy()
    _apply_css()
    win, outer, _result = _base_panel(
        "CPU",
        width=420,
        height=360,
        subtitle=_cpu_model()[:72],
    )
    pack_cpu_controls(outer, quit_on_advanced=True)
    win.show_all()
    win.present()
    Gtk.main()


def pack_memory_controls(
    outer: Gtk.Box, *, quit_on_advanced: bool = True, compact: bool = False
) -> None:
    """Embed Memory stats into an existing container."""
    info = _meminfo()
    total = float(info.get("MemTotal", 0))
    avail = float(info.get("MemAvailable", info.get("MemFree", 0)))
    used = max(0.0, total - avail)
    pct = (100.0 * used / total) if total else 0.0
    swap_t = float(info.get("SwapTotal", 0))
    swap_f = float(info.get("SwapFree", 0))
    swap_u = max(0.0, swap_t - swap_f)

    summary = Gtk.Label(
        label=f"{_fmt_gib(used)} used of {_fmt_gib(total)}",
        xalign=0.0,
    )
    summary.get_style_context().add_class("neuronix-subtitle")
    outer.pack_start(summary, False, False, 0)

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.NONE)
    listbox.get_style_context().add_class("neuronix-list")

    def _add(title: str, value: str) -> None:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        row.get_style_context().add_class("neuronix-list-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        t = Gtk.Label(label=title, xalign=0.0)
        t.get_style_context().add_class("neuronix-row-title")
        t.set_hexpand(True)
        v = Gtk.Label(label=value, xalign=1.0)
        v.get_style_context().add_class("neuronix-row-desc")
        box.pack_start(t, True, True, 0)
        box.pack_end(v, False, False, 0)
        row.add(box)
        listbox.add(row)

    _add("Used", f"{_fmt_gib(used)}  ({pct:.0f}%)")
    _add("Available", _fmt_gib(avail))
    _add("Total", _fmt_gib(total))
    if swap_t > 0:
        _add("Swap used", f"{_fmt_gib(swap_u)} / {_fmt_gib(swap_t)}")
    else:
        _add("Swap", "None")
    cached = float(info.get("Cached", 0)) + float(info.get("Buffers", 0))
    _add("Buffers / cache", _fmt_gib(cached))

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_size_request(-1, 120 if compact else 140)
    scroll.set_vexpand(not compact)
    scroll.add(listbox)
    outer.pack_start(scroll, not compact, not compact, 0)

    btop_btn = Gtk.Button(label="Open btop…")
    btop_btn.get_style_context().add_class("neuronix-secondary")
    btop_btn.connect(
        "clicked", lambda *_: _open_btop_detached(quit_after=quit_on_advanced)
    )
    outer.pack_start(_action_row(btop_btn), False, False, 0)


def show_memory_panel() -> None:
    freeze_click_xy()
    _apply_css()
    info = _meminfo()
    total = float(info.get("MemTotal", 0))
    avail = float(info.get("MemAvailable", info.get("MemFree", 0)))
    used = max(0.0, total - avail)
    win, outer, _result = _base_panel(
        "Memory",
        width=420,
        height=340,
        subtitle=f"{_fmt_gib(used)} used of {_fmt_gib(total)}",
    )
    pack_memory_controls(outer, quit_on_advanced=True)
    win.show_all()
    win.present()
    Gtk.main()


def show_power_panel() -> None:
    freeze_click_xy()
    _apply_css()
    win, outer, _result = _base_panel("Power", width=340, height=256)

    def _go(action: str) -> None:
        helper = _which("neuronix-session-action") or "neuronix-session-action"
        _launch_detached([helper, action])
        GLib.idle_add(Gtk.main_quit)

    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    col.pack_start(
        _make_tile("logout", "Log Out", "End this session", _go),
        False,
        False,
        0,
    )
    col.pack_start(
        _make_tile("reboot", "Reboot", "Restart this computer", _go),
        False,
        False,
        0,
    )
    col.pack_start(
        _make_tile("shutdown", "Shut Down", "Power off this computer", _go),
        False,
        False,
        0,
    )
    outer.pack_start(col, True, True, 0)
    win.show_all()
    win.present()
    Gtk.main()


def main() -> int:
    if not os.environ.get("NEURONIX_CLICK_XY"):
        try:
            os.environ["NEURONIX_CLICK_XY"] = (
                subprocess.check_output(["hyprctl", "cursorpos"], text=True, timeout=1)
                .replace(" ", "")
                .strip()
            )
        except Exception:
            pass
    os.environ.setdefault("XDG_CURRENT_DESKTOP", "Hyprland")
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode in ("sound", "volume", "audio"):
        show_sound_panel()
        return 0
    if mode in ("network", "wifi", "nm"):
        show_network_panel()
        return 0
    if mode in ("cpu",):
        show_cpu_panel()
        return 0
    if mode in ("memory", "ram", "mem"):
        show_memory_panel()
        return 0
    if mode in ("power", "session"):
        show_power_panel()
        return 0
    print("Usage: neuronix_quick_settings.py sound|network|cpu|memory|power", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
