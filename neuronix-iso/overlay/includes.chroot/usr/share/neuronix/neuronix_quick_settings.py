#!/usr/bin/env python3
"""GNOME-style Sound & Network panels for Waybar (no pavucontrol/nm fly-in)."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import sys
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, GLib, Pango  # noqa: E402

sys.path.insert(0, "/usr/share/neuronix")
sys.path.insert(0, os.path.expanduser("~/.local/share/neuronix"))
from neuronix_choice_dialog import (  # noqa: E402
    DrillItem,
    _action_row,
    entry as prompt_entry,
    show_drilldown,
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
    devices_lbl.get_style_context().add_class("neuronix-heading")
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


def _sound_volume_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
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

    def _on_scale(s: Gtk.Scale) -> None:
        pct = int(s.get_value())
        vol_lbl.set_text(f"{pct}%")
        _set_volume(pct)

    def _on_mute(*_a) -> None:
        _toggle_mute()
        _refresh_mute_btn()
        if not _sink_muted():
            scale.set_value(_sink_volume_pct())
            vol_lbl.set_text(f"{_sink_volume_pct()}%")

    _refresh_mute_btn()
    scale.connect("value-changed", _on_scale)
    mute_btn.connect("clicked", _on_mute)
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.pack_start(scale, True, True, 0)
    row.pack_start(vol_lbl, False, False, 0)
    box.pack_start(row, False, False, 0)
    box.pack_start(mute_btn, False, False, 0)
    return box


def _sound_output_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.get_style_context().add_class("neuronix-list")

    def _rebuild() -> None:
        for child in list(listbox.get_children()):
            listbox.remove(child)
        cur = _default_sink()
        for name, state in _list_sinks():
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("neuronix-list-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            t = Gtk.Label(label=_friendly_sink(name), xalign=0.0)
            t.get_style_context().add_class("neuronix-row-title")
            t.set_ellipsize(Pango.EllipsizeMode.END)
            desc = "Default" if name == cur else (state.title() if state else "Available")
            d = Gtk.Label(label=desc, xalign=0.0)
            d.get_style_context().add_class("neuronix-row-desc")
            inner.pack_start(t, False, False, 0)
            inner.pack_start(d, False, False, 0)
            row.add(inner)
            row._sink_name = name  # type: ignore[attr-defined]
            if name == cur:
                row.get_style_context().add_class("current")
            listbox.add(row)
        listbox.show_all()

    def _pick(_lb, row: Gtk.ListBoxRow) -> None:
        name = getattr(row, "_sink_name", "") or ""
        if not name:
            return
        _set_default_sink(name)
        _rebuild()

    listbox.connect("row-activated", _pick)
    _rebuild()
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_size_request(360, 240)
    scroll.set_vexpand(True)
    scroll.add(listbox)
    box.pack_start(scroll, True, True, 0)
    return box


def sound_items() -> list:
    return [
        DrillItem("volume", "Volume", "Output level and mute", panel=_sound_volume_page),
        DrillItem("output", "Output", "Choose a device", panel=_sound_output_page),
    ]


def show_sound_panel() -> None:
    show_drilldown("Sound", sound_items())


# ── Network ──────────────────────────────────────────────────────────────────


def _wifi_radio_on() -> bool:
    out = (_run(["nmcli", "-t", "-f", "WIFI", "radio"]) or "").strip().lower()
    return out in ("enabled", "on")


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
            lines.append(f"Wi-Fi · {name} ({dev})")
        elif typ == "802-3-ethernet":
            lines.append(f"Ethernet · {name} ({dev})")
        elif typ == "wireguard":
            lines.append(f"VPN · {name}")
    return "\n".join(lines) if lines else "No active connection"


def _nm_unescape(text: str) -> str:
    return text.replace("\\:", ":").replace("\\\\", "\\").strip()


def _nm(cmd: list[str], timeout: float = 20.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return proc.returncode == 0, (proc.stdout or "").strip()
    except Exception as exc:
        return False, str(exc)


def _nm_error(detail: str, fallback: str) -> str:
    lines = [line.strip() for line in (detail or "").splitlines() if line.strip()]
    if not lines:
        return fallback
    last = lines[-1]
    if last.lower().startswith("error:"):
        last = last.split(":", 1)[1].strip()
    return last or fallback


def _saved_wifi(ssid: str) -> bool:
    _ok, out = _nm(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"], timeout=8)
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line, maxsplit=1)
        if len(parts) != 2 or parts[1].strip() != "802-11-wireless":
            continue
        if _nm_unescape(parts[0]) == ssid:
            return True
    return False


def _parse_wifi_rows(raw: str) -> list[dict]:
    best: dict[str, dict] = {}
    for line in raw.splitlines():
        parts = re.split(r"(?<!\\):", line, maxsplit=3)
        if len(parts) < 4:
            continue
        ssid = _nm_unescape(parts[0])
        if not ssid:
            continue
        try:
            signal = int(parts[1].strip())
        except ValueError:
            signal = 0
        security = _nm_unescape(parts[2]) or "Open"
        active = parts[3].strip().lower() in ("yes", "*")
        row = best.get(ssid)
        if row is None:
            best[ssid] = {
                "ssid": ssid,
                "signal": signal,
                "security": security,
                "in_use": active,
            }
            continue
        if active:
            row["in_use"] = True
        if signal > int(row["signal"]):
            row["signal"] = signal
            row["security"] = security
    rows = list(best.values())
    rows.sort(key=lambda item: (not item["in_use"], -int(item["signal"]), item["ssid"].lower()))
    return rows


def _scan_wifi(rescan: bool) -> tuple[list[dict], str]:
    ok, out = _nm(
        [
            "nmcli",
            "-t",
            "-f",
            "SSID,SIGNAL,SECURITY,ACTIVE",
            "device",
            "wifi",
            "list",
            "--rescan",
            "yes" if rescan else "no",
        ],
        timeout=30 if rescan else 10,
    )
    rows = _parse_wifi_rows(out)
    if rows or ok:
        return rows, ""
    return [], _nm_error(out, "Could not list networks")


def _needs_password(security: str) -> bool:
    sec = (security or "").strip().lower()
    return bool(sec) and sec not in ("open", "--", "none", "owe")


def _is_enterprise(security: str) -> bool:
    return "802.1X" in (security or "")


def _connect_open(ssid: str) -> tuple[bool, str]:
    return _nm(["nmcli", "device", "wifi", "connect", ssid], timeout=30)


def _connect_with_password(ssid: str, password: str) -> tuple[bool, str]:
    """Same first step as Settings: nmcli device wifi connect … password.

    A password is collected before that command. Connecting once without a
    secret leaves a profile that then rejects the real password.
    """
    cmd = ["nmcli", "device", "wifi", "connect", ssid, "password", password]
    ok, out = _nm(cmd, timeout=30)
    if ok or not _saved_wifi(ssid):
        return ok, out
    mok, mout = _nm(
        [
            "nmcli",
            "connection",
            "modify",
            "id",
            ssid,
            "802-11-wireless-security.psk",
            password,
        ],
        timeout=10,
    )
    if mok:
        uok, uout = _nm(["nmcli", "connection", "up", "id", ssid], timeout=30)
        if uok:
            return True, uout
        return False, uout or mout or out
    _nm(["nmcli", "connection", "delete", "id", ssid], timeout=10)
    return _nm(cmd, timeout=30)


def _forget_wifi(ssid: str) -> tuple[bool, str]:
    """Disconnect and delete every saved profile for this network."""
    ok, out = _nm(["nmcli", "-t", "-f", "NAME,UUID,TYPE", "connection", "show"], timeout=8)
    if not ok and not out:
        return False, "Could not list saved networks"
    uuids: list[str] = []
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3:
            continue
        name = _nm_unescape(parts[0])
        uuid = parts[1].strip()
        typ = parts[2].strip()
        if typ == "802-11-wireless" and name == ssid and uuid:
            uuids.append(uuid)
    if not uuids:
        return False, f"No saved network named {ssid}"
    errors: list[str] = []
    for uuid in uuids:
        deleted, detail = _nm(["nmcli", "connection", "delete", "uuid", uuid], timeout=15)
        if not deleted:
            errors.append(detail)
    if errors and len(errors) == len(uuids):
        return False, errors[-1]
    return True, ""


def _ask_forget(ssid: str) -> bool:
    """Confirm forgetting a connected network. Does not close Settings."""
    from neuronix_choice_dialog import (  # noqa: WPS433
        _apply_css,
        _glass_root,
        center_layer_window,
        hold_layer_keyboard,
        pack_title_with_close,
    )

    _apply_css()
    result: dict[str, Optional[str]] = {"value": None}
    done = {"on": False}
    loop = GLib.MainLoop()
    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title("Forget Wi-Fi")
    win.set_decorated(False)
    win.set_resizable(False)
    win.get_style_context().add_class("neuronix-choice")
    center_layer_window(win, 440, 220)
    release_keys = hold_layer_keyboard(win)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    outer.get_style_context().add_class("neuronix-root")
    _glass_root(outer)
    win.add(outer)

    def _finish(value: Optional[str]) -> bool:
        if done["on"]:
            return False
        done["on"] = True
        result["value"] = value
        release_keys()
        loop.quit()
        return False

    title = Gtk.Label(label="Forget Wi-Fi", xalign=0.0)
    title.get_style_context().add_class("neuronix-title")
    pack_title_with_close(outer, title, lambda: _finish(None))

    prompt = Gtk.Label(
        label=f"Forget {ssid}? This disconnects and removes the saved password.",
        xalign=0.0,
    )
    prompt.set_line_wrap(True)
    prompt.set_max_width_chars(42)
    prompt.get_style_context().add_class("neuronix-subtitle")
    outer.pack_start(prompt, False, False, 0)

    cancel = Gtk.Button(label="Cancel")
    cancel.set_relief(Gtk.ReliefStyle.NONE)
    cancel.set_focus_on_click(False)
    cancel.get_style_context().add_class("neuronix-secondary")
    forget = Gtk.Button(label="Forget")
    forget.set_relief(Gtk.ReliefStyle.NONE)
    forget.set_focus_on_click(False)
    forget.get_style_context().add_class("neuronix-primary")
    cancel.connect("clicked", lambda *_a: _finish(None))
    forget.connect("clicked", lambda *_a: _finish("forget"))
    outer.pack_start(_action_row(cancel, forget), False, False, 0)
    win.connect(
        "key-press-event",
        lambda _w, event: _finish(None) if event.keyval == Gdk.KEY_Escape else False,
    )
    win.connect("destroy", lambda *_a: _finish(None))
    win.show_all()
    win.present()
    loop.run()
    if win.get_realized():
        win.hide()
    win.destroy()
    return result["value"] == "forget"


def _activate_wifi(ssid: str, security: str) -> tuple[bool, str, str]:
    """Return ok, detail, and 'password' when a secret is still required."""
    if _saved_wifi(ssid):
        ok, out = _nm(["nmcli", "connection", "up", "id", ssid], timeout=25)
        if ok:
            return True, out, ""
        if _needs_password(security):
            return False, out, "password"
        return False, out, ""
    if _needs_password(security):
        return False, "", "password"
    ok, out = _connect_open(ssid)
    return ok, out, ""


def _attach_wifi_list(
    listbox: Gtk.ListBox,
    status: Gtk.Label,
    on_changed: Optional[Callable[[], None]] = None,
) -> Callable[[bool], None]:
    """Fill listbox off the UI thread. Returns start(rescan)."""
    token = {"n": 0}
    alive = {"ok": True}
    busy = {"on": False}
    asking = {"on": False}
    listbox.set_activate_on_single_click(True)
    listbox.connect("destroy", lambda *_a: alive.__setitem__("ok", False))
    status.set_no_show_all(True)

    def _set_status(text: str) -> None:
        status.set_text(text)
        if text:
            status.show()
        else:
            status.hide()

    def _add_rows(rows: list) -> None:
        for child in list(listbox.get_children()):
            listbox.remove(child)
        for net in rows:
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("neuronix-list-row")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            title = net["ssid"]
            if net["in_use"]:
                title = f"{title}  ·  connected"
                row.get_style_context().add_class("current")
            heading = Gtk.Label(label=title, xalign=0.0)
            heading.get_style_context().add_class("neuronix-row-title")
            heading.set_ellipsize(Pango.EllipsizeMode.END)
            detail = Gtk.Label(
                label=f"{net['signal']}%  ·  {net['security']}",
                xalign=0.0,
            )
            detail.get_style_context().add_class("neuronix-row-desc")
            inner.pack_start(heading, False, False, 0)
            inner.pack_start(detail, False, False, 0)
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            line.pack_start(inner, True, True, 0)
            if net["in_use"]:
                forget = Gtk.Button(label="Forget")
                forget.set_relief(Gtk.ReliefStyle.NONE)
                forget.set_focus_on_click(False)
                forget.set_valign(Gtk.Align.CENTER)
                forget.get_style_context().add_class("neuronix-secondary")
                forget.connect("clicked", lambda *_a, name=net["ssid"]: _begin_forget(name))
                line.pack_start(forget, False, False, 0)
            row.add(line)
            row._net = net  # type: ignore[attr-defined]
            listbox.add(row)
        listbox.show_all()

    def _apply(gen: int, rows: list, err: str, off_msg: str) -> bool:
        if not alive["ok"] or gen != token["n"]:
            return False
        _add_rows([] if off_msg else rows)
        if off_msg:
            _set_status(off_msg)
        elif err and not rows:
            _set_status(err)
        elif not rows:
            _set_status("No networks found.")
        else:
            _set_status("")
        return False

    def start(rescan: bool) -> None:
        token["n"] += 1
        gen = token["n"]
        _add_rows([])
        _set_status("Scanning…" if rescan else "Loading networks…")

        def _mark_scanning() -> bool:
            if alive["ok"] and gen == token["n"]:
                _set_status("Scanning…")
            return False

        def work() -> None:
            if not _wifi_radio_on():
                GLib.idle_add(_apply, gen, [], "", "Wi-Fi is turned off.")
                return
            rows, err = _scan_wifi(rescan)
            if not rows and not err and not rescan:
                GLib.idle_add(_mark_scanning)
                rows, err = _scan_wifi(True)
            GLib.idle_add(_apply, gen, rows, err, "")

        threading.Thread(target=work, daemon=True).start()

    def _finish(gen: int, ssid: str, ok: bool, detail: str, fail: str = "") -> bool:
        busy["on"] = False
        if not alive["ok"] or gen != token["n"]:
            return False
        if ok:
            if on_changed:
                on_changed()
            start(False)
            return False
        _set_status(_nm_error(detail, fail or f"Could not connect to {ssid}"))
        return False

    def _begin_forget(ssid: str) -> None:
        if busy["on"] or asking["on"] or not alive["ok"] or not ssid:
            return
        asking["on"] = True
        try:
            yes = _ask_forget(ssid)
        finally:
            asking["on"] = False
        if not yes or busy["on"] or not alive["ok"]:
            return
        busy["on"] = True
        gen = token["n"]
        _set_status(f"Forgetting {ssid}…")

        def work() -> None:
            try:
                ok, detail = _forget_wifi(ssid)
                GLib.idle_add(_finish, gen, ssid, ok, detail, f"Could not forget {ssid}")
            except Exception as exc:
                GLib.idle_add(_finish, gen, ssid, False, str(exc), f"Could not forget {ssid}")

        threading.Thread(target=work, daemon=True).start()

    def _pick(_lb: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if busy["on"] or asking["on"] or not alive["ok"]:
            return
        net = getattr(row, "_net", None) or {}
        ssid = net.get("ssid") or ""
        if not ssid:
            return
        if net.get("in_use"):
            _begin_forget(ssid)
            return
        security = net.get("security") or ""
        busy["on"] = True
        gen = token["n"]
        _set_status(f"Connecting to {ssid}…")

        def work() -> None:
            try:
                if _is_enterprise(security):
                    if _saved_wifi(ssid):
                        ok, detail = _nm(["nmcli", "connection", "up", "id", ssid], timeout=30)
                        if ok:
                            GLib.idle_add(_finish, gen, ssid, True, "")
                            return
                    GLib.idle_add(
                        _finish,
                        gen,
                        ssid,
                        False,
                        "Enterprise networks are set up in the Settings app.",
                    )
                    return
                ok, detail, nxt = _activate_wifi(ssid, security)
                if nxt == "password":
                    holder: dict[str, Optional[str]] = {"pw": None}
                    done = threading.Event()

                    def ask() -> bool:
                        try:
                            holder["pw"] = prompt_entry(
                                "Wi-Fi password",
                                f"Password for {ssid}",
                                default="",
                                secret=True,
                            )
                            if (holder.get("pw") or "").strip() and alive["ok"] and gen == token["n"]:
                                _set_status(f"Connecting to {ssid}…")
                        finally:
                            done.set()
                        return False

                    GLib.idle_add(ask)
                    if not done.wait(180):
                        GLib.idle_add(_finish, gen, ssid, False, "Timed out waiting for a password")
                        return
                    password = (holder.get("pw") or "").strip()
                    if not password:
                        def _clear() -> bool:
                            busy["on"] = False
                            if alive["ok"] and gen == token["n"]:
                                _set_status("")
                            return False

                        GLib.idle_add(_clear)
                        return

                    def _connecting() -> bool:
                        if alive["ok"] and gen == token["n"]:
                            _set_status(f"Connecting to {ssid}…")
                        return False

                    GLib.idle_add(_connecting)
                    ok, detail = _connect_with_password(ssid, password)
                GLib.idle_add(_finish, gen, ssid, ok, detail)
            except Exception as exc:
                GLib.idle_add(_finish, gen, ssid, False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    listbox.connect("row-activated", _pick)
    start(False)
    return start


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
        wifi_btn.set_label("Wi-Fi On" if on else "Wi-Fi Off")
        wifi_btn.get_style_context().remove_class("neuronix-toggle-on")
        wifi_btn.get_style_context().remove_class("neuronix-toggle-off")
        wifi_btn.get_style_context().add_class("neuronix-toggle-on" if on else "neuronix-toggle-off")

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.get_style_context().add_class("neuronix-list")
    status = Gtk.Label(label="Loading networks…", xalign=0.0)
    status.get_style_context().add_class("neuronix-body")
    status.set_line_wrap(True)
    status.set_max_width_chars(42)

    def _changed() -> None:
        summary.set_text(_active_summary())
        _refresh_wifi_btn()

    reload_list = _attach_wifi_list(listbox, status, on_changed=_changed)

    def _toggle_wifi(*_a) -> None:
        _run_ok(["nmcli", "radio", "wifi", "off" if _wifi_radio_on() else "on"])
        _refresh_wifi_btn()
        reload_list(False)

    _refresh_wifi_btn()
    wifi_btn.connect("clicked", _toggle_wifi)
    outer.pack_start(wifi_btn, False, False, 0)

    nets_lbl = Gtk.Label(label="Available networks", xalign=0.0)
    nets_lbl.get_style_context().add_class("neuronix-heading")
    outer.pack_start(nets_lbl, False, False, 0)

    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    inner.pack_start(status, False, False, 0)
    inner.pack_start(listbox, True, True, 0)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_size_request(-1, 160 if compact else 180)
    scroll.set_vexpand(not compact)
    scroll.add(inner)
    outer.pack_start(scroll, not compact, not compact, 0)

    refresh = Gtk.Button(label="Refresh")
    refresh.get_style_context().add_class("neuronix-secondary")
    refresh.connect("clicked", lambda *_a: reload_list(True))
    outer.pack_start(_action_row(refresh), False, False, 0)


def _network_radio_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    summary = Gtk.Label(label=_active_summary(), xalign=0.0)
    summary.get_style_context().add_class("neuronix-body")
    summary.set_line_wrap(True)
    summary.set_max_width_chars(42)
    wifi_btn = Gtk.Button()
    wifi_btn.set_relief(Gtk.ReliefStyle.NONE)

    def _refresh() -> None:
        on = _wifi_radio_on()
        wifi_btn.set_label("Wi-Fi On" if on else "Wi-Fi Off")
        wifi_btn.get_style_context().remove_class("neuronix-toggle-on")
        wifi_btn.get_style_context().remove_class("neuronix-toggle-off")
        wifi_btn.get_style_context().add_class("neuronix-toggle-on" if on else "neuronix-toggle-off")
        summary.set_text(_active_summary())

    def _toggle(*_a) -> None:
        _run_ok(["nmcli", "radio", "wifi", "off" if _wifi_radio_on() else "on"])
        _refresh()

    _refresh()
    wifi_btn.connect("clicked", _toggle)
    box.pack_start(summary, False, False, 0)
    box.pack_start(wifi_btn, False, False, 0)
    return box


def _network_list_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.get_style_context().add_class("neuronix-list")
    status = Gtk.Label(label="Loading networks…", xalign=0.0)
    status.get_style_context().add_class("neuronix-body")
    status.set_line_wrap(True)
    status.set_max_width_chars(42)
    reload_list = _attach_wifi_list(listbox, status)
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    inner.pack_start(status, False, False, 0)
    inner.pack_start(listbox, True, True, 0)
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.get_style_context().add_class("neuronix-list-frame")
    scroll.set_size_request(360, 240)
    scroll.set_vexpand(True)
    scroll.add(inner)
    refresh = Gtk.Button(label="Refresh")
    refresh.get_style_context().add_class("neuronix-secondary")
    refresh.connect("clicked", lambda *_a: reload_list(True))
    box.pack_start(scroll, True, True, 0)
    box.pack_start(_action_row(refresh), False, False, 0)
    return box


_ETH_SKIP = ("veth", "docker", "br-", "virbr", "vmnet", "tap", "tun")


def _link_up(state: str) -> bool:
    text = (state or "").lower()
    if any(word in text for word in ("disconnected", "unavailable", "unmanaged", "failed")):
        return False
    return "connected" in text and "externally" not in text


def _ethernet_devices() -> list[dict]:
    ok, out = _nm(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"], timeout=8)
    if not ok and not out:
        return []
    devices: list[dict] = []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        dev, typ, state = parts[0], parts[1], ":".join(parts[2:])
        if typ != "ethernet":
            continue
        if state.strip().lower().startswith("unmanaged"):
            continue
        if any(dev.startswith(prefix) for prefix in _ETH_SKIP):
            continue
        devices.append({"device": dev, "state": state.strip()})
    return devices


def _ethernet_details(device: str) -> dict:
    _ok, out = _nm(
        [
            "nmcli",
            "-t",
            "-f",
            "GENERAL.STATE,GENERAL.CONNECTION,GENERAL.HWADDR,"
            "WIRED-PROPERTIES.CARRIER,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
            "device",
            "show",
            device,
        ],
        timeout=8,
    )
    info: dict = {"device": device, "dns": []}
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = _nm_unescape(val)
        if not val or val == "--":
            continue
        if key == "GENERAL.STATE":
            info["state"] = val
        elif key == "GENERAL.CONNECTION":
            info["connection"] = val
        elif key == "GENERAL.HWADDR":
            info["mac"] = val
        elif key == "WIRED-PROPERTIES.CARRIER":
            info["carrier"] = val
        elif re.match(r"IP4\.ADDRESS", key):
            info.setdefault("addresses", []).append(val)
            if "ip" not in info:
                pieces = val.split("/")
                info["ip"] = pieces[0]
                if len(pieces) == 2:
                    try:
                        info["prefix"] = int(pieces[1])
                    except ValueError:
                        pass
        elif key == "IP4.GATEWAY":
            info["gateway"] = val
        elif re.match(r"IP4\.DNS", key):
            info["dns"].append(val)
    return info


def _ethernet_profile(device: str, details: Optional[dict] = None) -> Optional[str]:
    info = details if details is not None else _ethernet_details(device)
    conn = info.get("connection")
    if conn:
        return str(conn)
    _ok, out = _nm(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"], timeout=8)
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3:
            continue
        name, typ, dev = _nm_unescape(parts[0]), parts[1].strip(), parts[2].strip()
        if typ in ("802-3-ethernet", "ethernet") and (dev == device or not dev):
            return name
    return None


def _ensure_ethernet(device: str) -> tuple[Optional[str], str]:
    name = _ethernet_profile(device)
    if name:
        return name, ""
    con_name = f"Wired connection {device}"
    ok, out = _nm(
        [
            "nmcli",
            "connection",
            "add",
            "type",
            "ethernet",
            "ifname",
            device,
            "con-name",
            con_name,
        ],
        timeout=15,
    )
    if ok:
        return con_name, ""
    return None, _nm_error(out, "Could not create a connection profile.")


def _ipv4_settings(conn: str) -> dict:
    cfg = {
        "method": "auto",
        "addresses": "",
        "gateway": "",
        "dns": "",
        "autoconnect": True,
    }
    _ok, out = _nm(
        [
            "nmcli",
            "-t",
            "-f",
            "ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,connection.autoconnect",
            "connection",
            "show",
            "id",
            conn,
        ],
        timeout=8,
    )
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if key == "ipv4.method":
            cfg["method"] = val or "auto"
        elif key == "ipv4.addresses":
            cfg["addresses"] = val
        elif key == "ipv4.gateway":
            cfg["gateway"] = val
        elif key == "ipv4.dns":
            cfg["dns"] = val.replace("|", " ").replace(",", " ")
        elif key == "connection.autoconnect":
            cfg["autoconnect"] = val.lower() == "yes"
    return cfg


def _ethernet_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    alive = {"ok": True}
    box.connect("destroy", lambda *_a: alive.__setitem__("ok", False))
    token = {"n": 0}

    status = Gtk.Label(label="Loading ethernet…", xalign=0.0)
    status.get_style_context().add_class("neuronix-body")
    status.set_line_wrap(True)
    status.set_max_width_chars(42)
    status.set_xalign(0.0)
    box.pack_start(status, False, False, 0)

    info = Gtk.Label(label="", xalign=0.0)
    info.get_style_context().add_class("neuronix-subtitle")
    info.set_line_wrap(True)
    info.set_max_width_chars(42)
    info.set_selectable(True)

    dev_combo = Gtk.ComboBoxText()
    dev_combo.set_hexpand(True)

    connect_btn = Gtk.Button(label="Connect")
    connect_btn.get_style_context().add_class("neuronix-secondary")
    disconnect_btn = Gtk.Button(label="Disconnect")
    disconnect_btn.get_style_context().add_class("neuronix-secondary")
    apply_btn = Gtk.Button(label="Apply")
    apply_btn.get_style_context().add_class("neuronix-primary")

    auto_btn = Gtk.RadioButton.new_with_label_from_widget(None, "Automatic (DHCP)")
    manual_btn = Gtk.RadioButton.new_with_label_from_widget(auto_btn, "Manual")
    for choice in (auto_btn, manual_btn):
        child = choice.get_child()
        if isinstance(child, Gtk.Label):
            child.get_style_context().add_class("neuronix-body")

    addr = Gtk.Entry()
    gateway = Gtk.Entry()
    dns = Gtk.Entry()
    for ent, hint in (
        (addr, "192.168.1.10/24"),
        (gateway, "192.168.1.1"),
        (dns, "1.1.1.1"),
    ):
        ent.get_style_context().add_class("neuronix-entry")
        ent.set_placeholder_text(hint)
        ent.set_hexpand(True)

    auto_cb = Gtk.CheckButton(label="Connect automatically")
    auto_cb.set_active(True)
    check_lbl = auto_cb.get_child()
    if isinstance(check_lbl, Gtk.Label):
        check_lbl.get_style_context().add_class("neuronix-body")

    def _labeled(caption: str, widget: Gtk.Widget) -> Gtk.Box:
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lab = Gtk.Label(label=caption, xalign=0.0)
        lab.get_style_context().add_class("neuronix-subtitle")
        col.pack_start(lab, False, False, 0)
        col.pack_start(widget, False, False, 0)
        return col

    def _manual_on(*_a) -> None:
        manual = manual_btn.get_active()
        for widget in (addr, gateway, dns):
            widget.set_sensitive(manual)

    auto_btn.connect("toggled", _manual_on)
    manual_btn.connect("toggled", _manual_on)

    form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    form.pack_start(info, False, False, 0)
    form.pack_start(_labeled("Interface", dev_combo), False, False, 0)
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.pack_start(connect_btn, False, False, 0)
    actions.pack_start(disconnect_btn, False, False, 0)
    actions.pack_end(apply_btn, False, False, 0)
    form.pack_start(actions, False, False, 0)
    form.pack_start(auto_btn, False, False, 0)
    form.pack_start(manual_btn, False, False, 0)
    form.pack_start(_labeled("Address", addr), False, False, 0)
    form.pack_start(_labeled("Gateway", gateway), False, False, 0)
    form.pack_start(_labeled("DNS", dns), False, False, 0)
    form.pack_start(auto_cb, False, False, 0)
    form.set_no_show_all(True)
    form.hide()
    box.pack_start(form, False, False, 0)

    def _set_busy(on: bool) -> None:
        for widget in (connect_btn, disconnect_btn, apply_btn, dev_combo, auto_btn, manual_btn, auto_cb):
            widget.set_sensitive(not on)
        if not on:
            _manual_on()

    def _show_link(device: str, details: dict, conn: Optional[str], cfg: Optional[dict]) -> None:
        if not alive["ok"]:
            return
        state = str(details.get("state") or "unknown")
        lines = [state]
        if details.get("carrier"):
            lines.append(f"Cable: {details['carrier']}")
        if details.get("mac"):
            lines.append(f"MAC: {details['mac']}")
        if details.get("ip"):
            ip = str(details["ip"])
            if details.get("prefix"):
                ip = f"{ip}/{details['prefix']}"
            lines.append(f"IP: {ip}")
        if details.get("gateway"):
            lines.append(f"Gateway: {details['gateway']}")
        if details.get("dns"):
            lines.append("DNS: " + ", ".join(details["dns"]))
        if conn:
            lines.append(f"Profile: {conn}")
        info.set_text("\n".join(lines))
        up = _link_up(state)
        _set_busy(False)
        connect_btn.set_sensitive(not up)
        disconnect_btn.set_sensitive(bool(conn) and up)
        if cfg and conn:
            if cfg.get("method") == "manual":
                manual_btn.set_active(True)
            else:
                auto_btn.set_active(True)
            address = str(cfg.get("addresses") or "")
            if not address and details.get("ip") and details.get("prefix"):
                address = f"{details['ip']}/{details['prefix']}"
            addr.set_text(address)
            gateway.set_text(str(cfg.get("gateway") or details.get("gateway") or ""))
            dns_text = str(cfg.get("dns") or "")
            if not dns_text and details.get("dns"):
                dns_text = " ".join(details["dns"])
            dns.set_text(dns_text)
            auto_cb.set_active(bool(cfg.get("autoconnect", True)))
        else:
            auto_btn.set_active(True)
            addr.set_text("")
            gateway.set_text("")
            dns.set_text("")
            auto_cb.set_active(True)
        _manual_on()
        form.set_no_show_all(False)
        form.show_all()
        status.set_text("")

    def _load_device(device: str) -> None:
        token["n"] += 1
        gen = token["n"]
        status.set_text("Loading ethernet…")

        def work() -> None:
            details = _ethernet_details(device)
            conn = _ethernet_profile(device, details)
            cfg = _ipv4_settings(conn) if conn else None

            def apply() -> bool:
                if not alive["ok"] or gen != token["n"]:
                    return False
                _show_link(device, details, conn, cfg)
                return False

            GLib.idle_add(apply)

        threading.Thread(target=work, daemon=True).start()

    def _on_device_changed(*_a) -> None:
        device = dev_combo.get_active_id() or ""
        if device:
            _load_device(device)

    dev_combo.connect("changed", _on_device_changed)

    def _reload_devices() -> None:
        status.set_text("Loading ethernet…")

        def work() -> None:
            devices = _ethernet_devices()

            def apply() -> bool:
                if not alive["ok"]:
                    return False
                dev_combo.remove_all()
                if not devices:
                    form.hide()
                    status.set_text("No ethernet interfaces found.")
                    return False
                for item in devices:
                    dev_combo.append(item["device"], f"{item['device']}  ·  {item['state']}")
                dev_combo.set_active(0)
                return False

            GLib.idle_add(apply)

        threading.Thread(target=work, daemon=True).start()

    def _after(device: str, ok: bool, detail: str, busy_ok: str) -> bool:
        if not alive["ok"]:
            return False
        if not ok:
            _set_busy(False)
            status.set_text(_nm_error(detail, "Could not change ethernet"))
            return False
        status.set_text(busy_ok)
        _load_device(device)
        return False

    def _on_connect(*_a) -> None:
        device = dev_combo.get_active_id() or ""
        if not device:
            return
        status.set_text(f"Connecting {device}…")

        def work() -> None:
            conn, err = _ensure_ethernet(device)
            if not conn:
                GLib.idle_add(_after, device, False, err, "")
                return
            ok, out = _nm(["nmcli", "connection", "up", "id", conn], timeout=30)
            GLib.idle_add(_after, device, ok, out, f"Connected {device}")

        _set_busy(True)
        threading.Thread(target=work, daemon=True).start()

    def _on_disconnect(*_a) -> None:
        device = dev_combo.get_active_id() or ""
        if not device:
            return
        status.set_text(f"Disconnecting {device}…")

        def work() -> None:
            conn = _ethernet_profile(device)
            if not conn:
                GLib.idle_add(_after, device, False, "No active connection.", "")
                return
            ok, out = _nm(["nmcli", "connection", "down", "id", conn], timeout=20)
            GLib.idle_add(_after, device, ok, out, f"Disconnected {device}")

        _set_busy(True)
        threading.Thread(target=work, daemon=True).start()

    def _on_apply(*_a) -> None:
        device = dev_combo.get_active_id() or ""
        if not device:
            return
        manual = manual_btn.get_active()
        address = addr.get_text().strip()
        gate = gateway.get_text().strip()
        dns_text = dns.get_text().strip()
        autoconnect = "yes" if auto_cb.get_active() else "no"
        if manual and (not address or "/" not in address):
            status.set_text("Address needs a prefix, for example 192.168.1.10/24")
            return
        status.set_text("Applying…")
        _set_busy(True)

        def work() -> None:
            conn, err = _ensure_ethernet(device)
            if not conn:
                GLib.idle_add(_after, device, False, err, "")
                return
            cmds = [
                ["nmcli", "connection", "modify", "id", conn, "connection.autoconnect", autoconnect]
            ]
            if not manual:
                cmds.append(
                    [
                        "nmcli",
                        "connection",
                        "modify",
                        "id",
                        conn,
                        "ipv4.method",
                        "auto",
                        "ipv4.addresses",
                        "",
                        "ipv4.gateway",
                        "",
                        "ipv4.dns",
                        "",
                    ]
                )
            else:
                modify = [
                    "nmcli",
                    "connection",
                    "modify",
                    "id",
                    conn,
                    "ipv4.method",
                    "manual",
                    "ipv4.addresses",
                    address,
                    "ipv4.gateway",
                    gate,
                    "ipv4.dns",
                    dns_text,
                ]
                cmds.append(modify)
            cmds.append(["nmcli", "connection", "up", "id", conn])
            last = ""
            ok = True
            for cmd in cmds:
                ok, last = _nm(cmd, timeout=45)
                if not ok:
                    break
            GLib.idle_add(_after, device, ok, last, "Ethernet settings applied.")

        threading.Thread(target=work, daemon=True).start()

    connect_btn.connect("clicked", _on_connect)
    disconnect_btn.connect("clicked", _on_disconnect)
    apply_btn.connect("clicked", _on_apply)
    _manual_on()
    _reload_devices()
    return box


def network_items() -> list:
    return [
        DrillItem("wifi", "Wi-Fi", "Radio and current connection", panel=_network_radio_page),
        DrillItem("networks", "Networks", "Choose a wireless network", panel=_network_list_page),
        DrillItem("ethernet", "Ethernet", "Wired address and connection", panel=_ethernet_page),
    ]


def show_network_panel() -> None:
    show_drilldown("Network", network_items())


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
    term = _which("gtk-term-launch.sh") or _which("gtk-term") or "gtk-term"
    btop = _which("btop") or "btop"
    _launch_detached(
        [
            term,
            "--class",
            "org.neuronix.btop",
            "--title",
            "btop",
            "-e",
            btop,
        ]
    )
    if quit_after:
        GLib.idle_add(Gtk.main_quit)


def pack_cpu_controls(
    outer: Gtk.Box,
    *,
    quit_on_advanced: bool = True,
    compact: bool = False,
    include_btop: bool = True,
    framed: bool = True,
) -> None:
    """Embed CPU stats into an existing container."""
    usage = _cpu_usage_pct()
    load1, load5, load15 = _read_loadavg()
    cores = _cpu_count()
    model = _cpu_model()

    if framed:
        model_lbl = Gtk.Label(label=model[:72], xalign=0.0)
        model_lbl.get_style_context().add_class("neuronix-subtitle")
        model_lbl.set_line_wrap(True)
        outer.pack_start(model_lbl, False, False, 0)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.get_style_context().add_class("neuronix-list")
    else:
        listbox = None

    def _add(title: str, value: str) -> None:
        if not framed:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            name = Gtk.Label(label=title, xalign=0.0)
            name.set_width_chars(16)
            name.get_style_context().add_class("neuronix-row-title")
            val = Gtk.Label(label=value, xalign=0.0)
            val.set_line_wrap(True)
            val.get_style_context().add_class("neuronix-subtitle")
            row.pack_start(name, False, False, 0)
            row.pack_start(val, True, True, 0)
            outer.pack_start(row, False, False, 0)
            return
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

    if framed:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class("neuronix-list-frame")
        scroll.set_size_request(-1, 120 if compact else 140)
        scroll.set_vexpand(not compact)
        scroll.add(listbox)
        outer.pack_start(scroll, not compact, not compact, 0)

    if include_btop:
        btop_btn = Gtk.Button(label="Open btop…")
        btop_btn.get_style_context().add_class("neuronix-secondary")
        btop_btn.connect(
            "clicked", lambda *_: _open_btop_detached(quit_after=quit_on_advanced)
        )
        outer.pack_start(_action_row(btop_btn), False, False, 0)


def _cpu_usage_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pack_cpu_controls(box, include_btop=False)
    return box


def cpu_items() -> list:
    return [
        DrillItem("usage", "Usage", _cpu_model()[:64], panel=_cpu_usage_page, icon="cpu"),
        DrillItem(
            "btop",
            "Open btop",
            "Full process view",
            action=lambda _i: _open_btop_detached(),
        ),
    ]


def show_cpu_panel() -> None:
    show_drilldown("CPU", cpu_items())


def pack_memory_controls(
    outer: Gtk.Box,
    *,
    quit_on_advanced: bool = True,
    compact: bool = False,
    include_btop: bool = True,
    framed: bool = True,
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

    if framed:
        summary = Gtk.Label(
            label=f"{_fmt_gib(used)} used of {_fmt_gib(total)}",
            xalign=0.0,
        )
        summary.get_style_context().add_class("neuronix-subtitle")
        outer.pack_start(summary, False, False, 0)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.get_style_context().add_class("neuronix-list")
    else:
        listbox = None

    def _add(title: str, value: str) -> None:
        if not framed:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            name = Gtk.Label(label=title, xalign=0.0)
            name.set_width_chars(16)
            name.get_style_context().add_class("neuronix-row-title")
            val = Gtk.Label(label=value, xalign=0.0)
            val.set_line_wrap(True)
            val.get_style_context().add_class("neuronix-subtitle")
            row.pack_start(name, False, False, 0)
            row.pack_start(val, True, True, 0)
            outer.pack_start(row, False, False, 0)
            return
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

    if framed:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.get_style_context().add_class("neuronix-list-frame")
        scroll.set_size_request(-1, 120 if compact else 140)
        scroll.set_vexpand(not compact)
        scroll.add(listbox)
        outer.pack_start(scroll, not compact, not compact, 0)

    if include_btop:
        btop_btn = Gtk.Button(label="Open btop…")
        btop_btn.get_style_context().add_class("neuronix-secondary")
        btop_btn.connect(
            "clicked", lambda *_: _open_btop_detached(quit_after=quit_on_advanced)
        )
        outer.pack_start(_action_row(btop_btn), False, False, 0)


def _memory_usage_page() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pack_memory_controls(box, include_btop=False)
    return box


def _memory_subtitle() -> str:
    info = _meminfo()
    total = float(info.get("MemTotal", 0))
    avail = float(info.get("MemAvailable", info.get("MemFree", 0)))
    used = max(0.0, total - avail)
    return f"{_fmt_gib(used)} used of {_fmt_gib(total)}"


def memory_items() -> list:
    return [
        DrillItem("usage", "Usage", _memory_subtitle(), panel=_memory_usage_page, icon="dialog-memory"),
        DrillItem(
            "btop",
            "Open btop",
            "Full process view",
            action=lambda _i: _open_btop_detached(),
        ),
    ]


def show_memory_panel() -> None:
    show_drilldown("Memory", memory_items())


def power_items() -> list:
    def _go(action: str) -> None:
        helper = _which("neuronix-session-action") or "neuronix-session-action"
        _launch_detached([helper, action])
        GLib.idle_add(Gtk.main_quit)

    return [
        DrillItem("logout", "Log Out", "End this session", action=_go),
        DrillItem("reboot", "Reboot", "Restart this computer", action=_go),
        DrillItem("shutdown", "Shut Down", "Power off this computer", action=_go),
    ]


def show_power_panel() -> None:
    show_drilldown("Power", power_items())


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
