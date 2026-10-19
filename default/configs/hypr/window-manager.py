#!/usr/bin/env python3
"""Park the main screen as floats, or tile it, and tile the DP portraits.

The main screen is HDMI-A-1 when it is connected, otherwise the only screen.
Layout mode (`float` or `tile`) lives in $XDG_STATE_HOME/kvnix/layout-mode.
Missing file: float when HDMI is present, tile when it is not. The Waybar
module and `layout-toggle` flip it. DP-3 / DP-4 stay tiled either way.

In float mode, new windows land in the main-screen bottom-center slot.
Ctrl+Super+Alt parks a 3×3 grid. On HDMI each plain slot is a quarter wider
than a third (and taller by that bump plus 10%); Shift uses two-thirds.
Without HDMI (laptop float desk) every numpad / number-row slot is
two-thirds plus 30% (13/15 of the usable area).
The same keys fill the main screen or tile onto DP-3 / DP-4. A second (or
third) window in the same slot cascades slightly so title bars of the ones
behind stay visible. gtk-photos viewers pack bottom-left across, then up;
gtk-meld diffs fill the main screen. Super in float mode shows the overview
preview grid; Super in tile mode on a laptop opens fuzzel only.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator

HDMI = "HDMI-A-1"
DP_LEFT = "DP-3"
DP_RIGHT = "DP-4"
# Laptop float desk (no HDMI): numpad / number-row slots — 2/3 + 30%.
LAPTOP_FLOAT_FRAC = (13, 15)
GAP = 18
# hyprbars sits above client `at`. A full-bleed window clips the − □ × bar
# off the top of the monitor (behind/above Waybar). Matches plugin { hyprbars }.
HYPRBAR_H = 36
HYPRBAR_BTN = 18
HYPRBAR_BTN_PAD = 10
HYPRBAR_PAD = 12
# Screen-top hyprtabs strip (below Waybar; matches hyprbars when match_hyprbars).
# Bottom tab capsule: height + margin (matches Waybar 42 + margin-top 12).
# HYPRTABS_GAP = air between the window bottom edge and the capsule top.
HYPRTABS_H = 42
HYPRTABS_MARGIN = 12
HYPRTABS_GAP = 14
# Overview previews are small — enlarge the × hit target past the glyph.
OVERVIEW_CLOSE_HIT = 48
HYPRBAR_CLOSE_BTN = 22
CASCADE_STEP = 40
CASCADE_MAX = 6
CASCADE_SIZE_SLOP = 96
CASCADE_POS_SLOP = 24
MINIMIZED_SPECIAL = "special:minimized"
CHROME_PREFS = os.path.join(
    os.path.expanduser("~"), ".config", "hypr", "neuronix-window-chrome.json"
)
HYPRTABS_SO_CANDIDATES = (
    os.path.join(os.path.expanduser("~"), ".local/lib/hyprland/plugins/libhyprtabs.so"),
    "/usr/local/lib/hyprland/plugins/libhyprtabs.so",
    "/usr/lib/x86_64-linux-gnu/hyprland/plugins/libhyprtabs.so",
)
HYPRBARS_SO_CANDIDATES = (
    os.path.join(os.path.expanduser("~"), ".local/lib/hyprland/plugins/libhyprbars.so"),
    "/usr/local/lib/hyprland/plugins/libhyprbars.so",
    "/usr/lib/x86_64-linux-gnu/hyprland/plugins/libhyprbars.so",
    "/usr/lib/x86_64-linux-gnu/hyprland/plugins/hyprbars.so",
)

SKIP_CLASS_SUBSTR = (
    "zenity",
    "polkit",
    "neuronix-choice",
    "neuronix-calendar",
    "xdg-desktop-portal",
    "galculator",
    "gtkcalc",
    "xfce4-power",
    "hypr-settings",
    "gtkthemeeditor",
    "nwg-bar",
    "system-config-printer",
    "gparted",
    "dconf-editor",
    "fuzzel",
    "windowswitch",
    "screensaver",
    "org.neuronix.cava",
    "org.neuronix.btop",
    "org.neuronix.popover",
)

DIALOG_TITLE_SUBSTR = (
    "delete",
    "trash",
    "confirm",
    "warning",
    "error",
    "rename",
    "preferences",
    "properties",
    "empty trash",
    "overwrite",
    "replace",
    "save as",
    "are you sure",
    "permanently",
    "new folder",
    "new document",
    "create link",
    "open with",
    "keyboard shortcuts",
    "about",
    "authenticate",
    "destination",
    "moving files",
)

PHOTOS_CLASS = "org.neuronix.gtkphotos"
PHOTOS_MEDIA_CLASS = "gtk-photos-media"
GTK_IMAGE_CLASS = "org.neuronix.gtkimage"
PHOTOS_MAIN_TITLE = "photo organizer"
MELD_CLASS_SUBSTR = ("gtkmeld", "org.gnome.meld")
MELD_HOME_TITLES = ("meld", "gtk meld", "new comparison")
PHOTOS_CMDLINE_MARKERS = (
    "chromium-image-",
    "chromium-video-",
    "chromium-html-",
    "gtk-photos-player",
    "--class=gtk-photos-media",
)
CHROMIUM_CLASS_SUBSTR = ("chromium", "google-chrome", "chrome")
MAIN_BROWSER_CLASSES = (
    "google-chrome",
    "google-chrome-unstable",
    "google-chrome-beta",
    "chromium",
    "chromium-browser",
)
MEDIA_TITLE_RE = re.compile(
    r"\.(jpe?g|png|gif|webp|bmp|svg|ico|tiff?|heic|heif|"
    r"mp4|avi|webm|mov|m4v|flv|wmv|mpg|mpeg|3gp|ogv|mts|m2ts)$",
    re.I,
)


def hyprctl(*args: str) -> str:
    return subprocess.check_output(["hyprctl", *args], text=True)


def hypr_json(request: str):
    return json.loads(hyprctl("-j", request))


def dispatch(name: str, arg: str = "") -> str:
    cmd = ["hyprctl", "dispatch", name]
    if arg:
        cmd.append(arg)
    return subprocess.check_output(cmd, text=True).strip()


def dispatch_batch(parts: list[str]) -> str:
    return subprocess.check_output(["hyprctl", "--batch", "; ".join(parts)], text=True).strip()


def monitor_by_id(mid: int | str | None, monitors: list[dict] | None = None) -> dict:
    """Resolve a hyprctl monitor id to its monitor dict (falls back to focused)."""
    monitors = monitors if monitors is not None else hypr_json("monitors")
    try:
        want = int(mid) if mid is not None else -1
    except (TypeError, ValueError):
        want = -1
    for item in monitors:
        try:
            if int(item.get("id")) == want:
                return item
        except (TypeError, ValueError):
            continue
    for item in monitors:
        if item.get("focused"):
            return item
    if not monitors:
        raise RuntimeError("no monitors")
    return monitors[0]


def monitor_by_name(name: str, monitors: list[dict] | None = None) -> dict:
    monitors = monitors if monitors is not None else hypr_json("monitors")
    for mon in monitors:
        if mon.get("name") == name:
            return mon
    raise RuntimeError(f"monitor {name} not found")


def has_hdmi(monitors: list[dict] | None = None) -> bool:
    """True when the workstation HDMI-A-1 landscape screen is connected."""
    monitors = monitors if monitors is not None else hypr_json("monitors")
    return any(mon.get("name") == HDMI for mon in monitors)


def hdmi_monitor(monitors: list[dict] | None = None) -> dict:
    """HDMI-A-1 when present; otherwise the focused (or only) screen.

    Parking and the Super zoom grid prefer HDMI-A-1; without HDMI they use the
    focused / only screen (laptop eDP). Super in float mode shows the same
    overview grid; Super in tile mode on a laptop opens fuzzel only.
    """
    monitors = monitors if monitors is not None else hypr_json("monitors")
    for mon in monitors:
        if mon.get("name") == HDMI:
            return mon
    for mon in monitors:
        if mon.get("focused"):
            return mon
    if monitors:
        return monitors[0]
    raise RuntimeError("no monitors")


def hdmi_name(monitors: list[dict] | None = None) -> str:
    return str(hdmi_monitor(monitors).get("name") or HDMI)


def is_minimized_win(win: dict) -> bool:
    """True when the window lives on the hyprbars − / Super+H minimize special."""
    name = str((win.get("workspace") or {}).get("name") or "")
    return name == MINIMIZED_SPECIAL or name.endswith(":minimized")


def waybar_cut(layers: dict, mon_name: str, strip_top: int, strip_bottom: int) -> tuple[int, int]:
    info = layers.get(mon_name) or {}
    for level in (info.get("levels") or {}).values():
        for surf in level:
            if surf.get("namespace") != "waybar":
                continue
            y, h = int(surf["y"]), int(surf["h"])
            if y + h <= strip_top or y >= strip_bottom:
                continue
            mid = (strip_top + strip_bottom) / 2
            if y + h / 2 < mid:
                strip_top = y + h
            else:
                strip_bottom = y
    return strip_top, strip_bottom


def usable_rect(mon: dict, layers: dict) -> tuple[int, int, int, int]:
    name = str(mon.get("name") or "")
    mx, my = int(mon["x"]), int(mon["y"])
    mw, mh = int(mon["width"]), int(mon["height"])
    left, top_res, right, _bottom = [int(v) for v in mon["reserved"]]
    strip_top = my + max(int(top_res), 0)
    strip_bottom = my + mh
    strip_top, strip_bottom = waybar_cut(layers, name, strip_top, strip_bottom)
    strip_top += HYPRBAR_H
    # Bottom tab capsule — keep floated windows above it whenever the strip is on.
    if hyprtabs_strip_visible():
        strip_bottom -= _hyprtabs_bottom_reserve()
    # Tabs mode: flush full-bleed between Waybar and hyprtabs (no side/extra gaps).
    if wants_tabs() or hyprtabs_strip_visible():
        x = mx + left
        y = strip_top
        w = mw - left - right
        h = strip_bottom - y
    else:
        x = mx + left + GAP
        y = strip_top + GAP
        w = mw - left - right - 2 * GAP
        h = strip_bottom - y - GAP
    if w < 200 or h < 200:
        raise RuntimeError(f"{name} is too small to place a window")
    return x, y, w, h


def _fuzzel_ini_text() -> str:
    for path in (
        os.path.expanduser("~/.config/fuzzel/fuzzel.ini"),
        os.path.expanduser("~/configs/fuzzel/fuzzel.ini"),
        "/etc/xdg/fuzzel/fuzzel.ini",
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            continue
    return ""


def estimate_fuzzel_bar_height(layers: dict | None = None, mon_name: str = "") -> int:
    """Bottom fuzzel / chrome-panel height: live layer if mapped, else fuzzel.ini."""
    best = 0
    for name, info in (layers or {}).items():
        if mon_name and name != mon_name:
            continue
        for level in (info.get("levels") or {}).values():
            for surf in level or []:
                ns = str(surf.get("namespace") or "").lower()
                if (
                    ns not in ("launcher", "neuronix-fuzzel-panel")
                    and "fuzzel" not in ns
                ):
                    continue
                h = int(surf.get("h") or 0)
                if h > best:
                    best = h
    if best >= 80:
        return best

    text = _fuzzel_ini_text()

    def _ival(key: str, default: int) -> int:
        m = re.search(rf"(?m)^{re.escape(key)}=([0-9]+)\s*$", text)
        return int(m.group(1)) if m else default

    lines = _ival("lines", 12)
    vpad = _ival("vertical-pad", 20)
    ipad = _ival("inner-pad", 16)
    font = "Sans:size=24"
    fm = re.search(r"(?m)^font=.+$", text)
    if fm:
        font = fm.group(0)
    sm = re.search(r"size=(\d+)", font)
    font_px = int(sm.group(1)) if sm else 24
    bw = 10
    section = re.search(r"(?ms)^\[border\]\s*(.*?)^\[", text + "\n[")
    if section:
        mw = re.search(r"(?m)^width=(\d+)\s*$", section.group(1))
        if mw:
            bw = int(mw.group(1))
    rm = re.search(r"(?m)^image-size-ratio=([0-9.]+)\s*$", text)
    ratio = float(rm.group(1)) if rm else 0.28
    line_h = max(28, int(font_px * 1.35))
    rows = max(1, lines) + 1  # prompt + match rows
    icon_extra = int(line_h * 8 * max(0.0, ratio))
    return 2 * vpad + 2 * bw + ipad + rows * line_h + icon_extra


def overview_usable_rect(mon: dict, layers: dict) -> tuple[int, int, int, int]:
    """Rect for Super overview: below Waybar, above the bottom fuzzel strip.

    Overview always launches fuzzel with ``--anchor=bottom`` so the search
    column does not cover the zoomed-out window previews (clicks must hit them).
    """
    x, y, w, h = usable_rect(mon, layers)
    name = str(mon.get("name") or "")
    bar = estimate_fuzzel_bar_height(layers, name)
    bar = min(max(bar, 280), max(0, h - 220))
    return x, y, w, max(200, h - bar)


def hdmi_slot_rect(
    mon: dict,
    layers: dict,
    align: str,
    row: str,
    width_frac: tuple[int, int] = (1, 3),
) -> tuple[int, int, int, int]:
    """Float slot on HDMI, anchored on the 3×3 grid.

    ``width_frac`` is 1/3 for Ctrl+Super+Alt+number and 2/3 with Shift.
    The plain keys are a quarter wider than a third, and the height is that
    same bump plus another 10%. Shift stays two-thirds in both directions.
    """
    mx, my = int(mon["x"]), int(mon["y"])
    mw, mh = int(mon["width"]), int(mon["height"])
    left, top_res, right, _bottom = [int(v) for v in mon["reserved"]]
    full_top = my + max(int(top_res), 0)
    full_bottom = my + mh
    full_top, full_bottom = waybar_cut(
        layers, str(mon.get("name") or HDMI), full_top, full_bottom
    )
    full_top += HYPRBAR_H
    usable_w = mw - left - right
    usable_h = full_bottom - full_top
    num, den = width_frac
    w = usable_w * num // den
    h = usable_h * num // den
    if width_frac == (1, 3):
        w = w * 5 // 4
        h = h * 5 // 4
        h = h * 11 // 10
    if w < 200 or h < 200:
        raise RuntimeError("HDMI is too small to place that float")
    if align == "left":
        x = mx + left
    elif align == "right":
        x = mx + left + usable_w - w
    else:
        x = mx + left + (usable_w - w) // 2
    if row == "top":
        y = full_top
    elif row == "middle":
        y = full_top + (usable_h - h) // 2
    else:
        y = full_bottom - h
    return x, y, w, h


def _client_rect(win: dict) -> tuple[int, int, int, int]:
    at = win.get("at") or [0, 0]
    size = win.get("size") or [0, 0]
    return int(at[0]), int(at[1]), max(1, int(size[0] or 0)), max(1, int(size[1] or 0))


def _same_workspace(a: dict, b: dict) -> bool:
    return str((a.get("workspace") or {}).get("id", "")) == str(
        (b.get("workspace") or {}).get("id", "")
    )


def _nine_slot_rects(
    mon: dict, layers: dict, width_frac: tuple[int, int] = (1, 3)
) -> list[tuple[int, int, int, int]]:
    return [
        hdmi_slot_rect(mon, layers, align, row, width_frac)
        for row in ("top", "middle", "bottom")
        for align in ("left", "center", "right")
    ]


def _nearest_slot_rect(
    x: int, y: int, slots: list[tuple[int, int, int, int]]
) -> tuple[int, int, int, int]:
    best = slots[0]
    best_d = None
    for rect in slots:
        d = (x - rect[0]) ** 2 + (y - rect[1]) ** 2
        if best_d is None or d < best_d:
            best_d = d
            best = rect
    return best


def _align_row_for_slot(
    slot: tuple[int, int, int, int],
    mon: dict,
    layers: dict,
    width_frac: tuple[int, int] = (1, 3),
) -> tuple[str, str] | None:
    sx, sy = slot[0], slot[1]
    for row in ("top", "middle", "bottom"):
        for align in ("left", "center", "right"):
            rect = hdmi_slot_rect(mon, layers, align, row, width_frac)
            if abs(rect[0] - sx) <= 2 and abs(rect[1] - sy) <= 2:
                return align, row
    return None


def _window_in_slot(
    win: dict,
    slot: tuple[int, int, int, int],
    hdmi_id,
    all_slots: list[tuple[int, int, int, int]],
) -> bool:
    """True when a floating HDMI window belongs to this 3×3 slot's cascade pile."""
    if not win.get("mapped") or win.get("hidden") or not win.get("floating"):
        return False
    if win.get("monitor") != hdmi_id:
        return False
    if skip_new_window(win):
        return False
    sx, sy, sw, sh = slot
    wx, wy, ww, wh = _client_rect(win)
    if abs(ww - sw) > CASCADE_SIZE_SLOP or abs(wh - sh) > CASCADE_SIZE_SLOP:
        return False
    nearest = _nearest_slot_rect(wx, wy, all_slots)
    return abs(nearest[0] - sx) <= 2 and abs(nearest[1] - sy) <= 2


def _slot_pile_windows(
    except_addr: str,
    slot: tuple[int, int, int, int],
    current: dict,
    mon: dict,
    layers: dict,
    clients: list[dict] | None = None,
    width_frac: tuple[int, int] = (1, 3),
) -> list[dict]:
    except_addr = except_addr if except_addr.startswith("0x") else f"0x{except_addr}"
    hdmi_id = mon.get("id")
    all_slots = _nine_slot_rects(mon, layers, width_frac)
    pile: list[dict] = []
    for win in clients if clients is not None else hypr_json("clients"):
        if win.get("address") == except_addr:
            continue
        if not _same_workspace(win, current):
            continue
        if _window_in_slot(win, slot, hdmi_id, all_slots):
            pile.append(win)
    pile.sort(
        key=lambda w: (
            _client_rect(w)[0] + _client_rect(w)[1],
            w.get("address") or "",
        )
    )
    return pile


def _cascade_fits(
    pts: list[tuple[int, int]],
    sw: int,
    sh: int,
    usable: tuple[int, int, int, int],
) -> bool:
    ux, uy, uw, uh = usable
    for x, y in pts:
        if x < ux or y < uy or x + sw > ux + uw or y + sh > uy + uh:
            return False
    return True


def _nudge_pile(
    pts: list[tuple[int, int]],
    sw: int,
    sh: int,
    usable: tuple[int, int, int, int],
) -> list[tuple[int, int]]:
    """Slide the whole pile by one vector so corners stay colinear."""
    ux, uy, uw, uh = usable
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs) + sw
    miny, maxy = min(ys), max(ys) + sh
    dx = dy = 0
    if minx < ux:
        dx += ux - minx
    if maxx > ux + uw:
        dx -= maxx - (ux + uw)
    if miny < uy:
        dy += uy - miny
    if maxy > uy + uh:
        dy -= maxy - (uy + uh)
    return [(x + dx, y + dy) for x, y in pts]


def _cascade_positions(
    n: int,
    slot: tuple[int, int, int, int],
    usable: tuple[int, int, int, int],
) -> list[tuple[int, int]]:
    """45° staircase. Last card is always the bottom-right (front) of the pile."""
    sx, sy, sw, sh = slot
    step = CASCADE_STEP
    if n <= 1:
        return [(sx, sy)]
    k = n - 1
    grow = [(sx + i * step, sy + i * step) for i in range(n)]
    if _cascade_fits(grow, sw, sh, usable):
        return grow
    park = [(sx - (k - i) * step, sy - (k - i) * step) for i in range(n)]
    if _cascade_fits(park, sw, sh, usable):
        return park
    return _nudge_pile(park, sw, sh, usable)


def _apply_card_stack(
    ordered: list[dict],
    positions: list[tuple[int, int]],
    w: int,
    h: int,
    front_addr: str,
    focus: bool = True,
) -> None:
    geo: list[str] = []
    for item, (px, py) in zip(ordered, positions):
        item_addr = item.get("address")
        if not item_addr:
            continue
        item_target, _raw = address_target(item_addr)
        if not item.get("floating"):
            geo.append(f"dispatch setfloating {item_target}")
        geo.append(f"dispatch resizewindowpixel exact {w} {h},{item_target}")
        geo.append(f"dispatch movewindowpixel exact {px} {py},{item_target}")
    if geo:
        dispatch_batch(geo)
    if not focus:
        return
    front_target, _raw = address_target(front_addr)
    zparts: list[str] = []
    for item in ordered:
        item_addr = item.get("address")
        if not item_addr:
            continue
        item_target, _raw = address_target(item_addr)
        zparts.append(f"dispatch alterzorder top,{item_target}")
    zparts.append(f"dispatch alterzorder top,{front_target}")
    zparts.append(f"dispatch focuswindow {front_target}")
    try:
        dispatch_batch(zparts)
    except Exception:
        try:
            dispatch("focuswindow", front_target)
        except Exception:
            pass


def client_by_address(addr: str) -> dict | None:
    addr = addr if addr.startswith("0x") else f"0x{addr}"
    for win in hypr_json("clients"):
        if win.get("address") == addr:
            return win
    return None


def address_target(addr: str) -> tuple[str, str]:
    target = addr if addr.startswith("address:") else f"address:{addr}"
    raw = target.split(":", 1)[1]
    raw = raw if raw.startswith("0x") else f"0x{raw}"
    return target, raw


def ensure_floating(target: str, win: dict | None = None) -> None:
    if win is None or not win.get("floating"):
        dispatch("setfloating", target)


def is_popup_or_menu(win: dict) -> bool:
    if is_photos_media(win) or is_photos_dialog(win):
        return False
    xdg = str(win.get("xdgTag") or win.get("xdg_tag") or "").lower()
    if any(s in xdg for s in ("popup", "menu", "dropdown", "tooltip")):
        return True
    size = win.get("size") or [0, 0]
    w, h = int(size[0] or 0), int(size[1] or 0)
    if w <= 0 or h <= 0:
        return False
    title = (win.get("title") or "").strip().lower()
    if any(s in title for s in DIALOG_TITLE_SUBSTR):
        return False
    cls = (win.get("class") or "").lower()
    if _class_is_main_browser(cls):
        return False
    compact = (w <= 720 and h <= 640) or (w * h <= 280_000)
    floating = bool(win.get("floating"))
    if _class_is_chromium(cls) and floating and compact:
        return True
    if floating and compact:
        return True
    if compact and w <= 480 and h <= 480:
        return True
    return False


def class_is_meld(cls: str) -> bool:
    cls = (cls or "").lower().replace("_", ".")
    return "gtkmeld" in cls or "org.gnome.meld" in cls


def force_meld_fullscreen(addr: str) -> None:
    """Float over the whole monitor. Usable-area placement stops short of the edges."""
    target, raw = address_target(addr)
    try:
        dispatch("focuswindow", target)
        dispatch("setfloating", target)
    except Exception:
        return
    win = client_by_address(raw)
    mon = None
    monitors = hypr_json("monitors")
    if win is not None:
        for item in monitors:
            if item.get("id") == win.get("monitor"):
                mon = item
                break
    if mon is None:
        for item in monitors:
            if item.get("focused"):
                mon = item
                break
    if mon is not None:
        x, y = int(mon["x"]), int(mon["y"])
        w, h = int(mon["width"]), int(mon["height"])
        try:
            dispatch("movewindowpixel", f"exact {x} {y},{target}")
            dispatch("resizewindowpixel", f"exact {w} {h},{target}")
        except Exception:
            pass
    # internal 2 + client 2: real fullscreen, and tell GTK the window is that tall.
    try:
        subprocess.check_call(
            ["hyprctl", "dispatch", "fullscreenstate", "2", "2"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def is_gtk_meld(win: dict) -> bool:
    cls = (win.get("class") or "").lower().replace("_", ".")
    if any(s in cls for s in MELD_CLASS_SUBSTR):
        return True
    pid = int(win.get("pid") or 0)
    if pid:
        cmd = _pid_cmdlines(pid)
        if "gtk-meld" in cmd or "org.neuronix.GtkMeld" in cmd:
            return True
    return False


def is_gtk_meld_diff(win: dict) -> bool:
    if not is_gtk_meld(win):
        return False
    title = (win.get("title") or "").strip().lower()
    initial = (win.get("initialTitle") or "").strip().lower()
    for text in (title, initial):
        if not text or text in MELD_HOME_TITLES or text.startswith("new comparison"):
            continue
        return True
    return False


def _window_tags(win: dict) -> list[str]:
    tags = win.get("tags")
    if isinstance(tags, str):
        return tags.split()
    if isinstance(tags, (list, tuple, set)):
        return [str(t) for t in tags]
    return []


def skip_new_window(win: dict) -> bool:
    cls = (win.get("class") or "").lower()
    ws = str((win.get("workspace") or {}).get("name") or "")
    if ws.startswith("special"):
        return True
    tags = _window_tags(win)
    if "waybar-popover" in tags or "sidepanel" in tags or "settings-host" in tags:
        return True
    if any(s in cls for s in SKIP_CLASS_SUBSTR):
        return True
    if is_popup_or_menu(win):
        return True
    return False


def is_dialog_like(win: dict) -> bool:
    if win.get("modal"):
        return True
    titles = " ".join(
        t.lower()
        for t in ((win.get("title") or ""), (win.get("initialTitle") or ""))
        if t
    )
    return any(s in titles for s in DIALOG_TITLE_SUBSTR)


def _pid_cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _pid_parent(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            text = fh.read()
        close = text.rfind(")")
        if close == -1:
            return 0
        fields = text[close + 1 :].split()
        return int(fields[1])
    except (OSError, IndexError, ValueError):
        return 0


def _pid_cmdlines(pid: int, depth: int = 8) -> str:
    chunks: list[str] = []
    seen: set[int] = set()
    for _ in range(depth):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        chunks.append(_pid_cmdline(pid))
        pid = _pid_parent(pid)
    return " ".join(chunks)


def _window_tags(win: dict) -> list[str]:
    tags = win.get("tags") or []
    if isinstance(tags, str):
        return [tags]
    return [str(t) for t in tags]


def _class_is_chromium(cls: str) -> bool:
    c = (cls or "").lower()
    return any(part in c for part in CHROMIUM_CLASS_SUBSTR)


def _class_is_main_browser(cls: str) -> bool:
    """True for the browser window, not chrome-<id>-Default PWAs."""
    return (cls or "").lower() in MAIN_BROWSER_CLASSES


def _title_is_photos_media(title: str) -> bool:
    text = title or ""
    if MEDIA_TITLE_RE.search(text):
        return True
    lower = text.lower()
    return "image_viewer.html" in lower or "gtk-photos-player" in lower


def _photos_chromium_tree_pids() -> set[int]:
    ppid_of: dict[int, int] = {}
    marker_roots: set[int] = set()
    try:
        names = os.listdir("/proc")
    except OSError:
        return set()
    for name in names:
        if not name.isdigit():
            continue
        pid = int(name)
        ppid_of[pid] = _pid_parent(pid)
        cmd = _pid_cmdline(pid)
        if any(marker in cmd for marker in PHOTOS_CMDLINE_MARKERS):
            marker_roots.add(pid)
    children: dict[int, list[int]] = {}
    for pid, ppid in ppid_of.items():
        children.setdefault(ppid, []).append(pid)
    out: set[int] = set()
    stack = list(marker_roots)
    while stack:
        pid = stack.pop()
        if pid in out:
            continue
        out.add(pid)
        stack.extend(children.get(pid, []))
    for root in marker_roots:
        pid = root
        for _ in range(8):
            pid = ppid_of.get(pid, 0)
            if pid <= 1:
                break
            out.add(pid)
    return out


def _photos_app_pids() -> set[int]:
    pids: set[int] = set()
    for other in hypr_json("clients"):
        cls = (other.get("class") or "").lower().replace("_", ".")
        title = (other.get("title") or "").strip().lower()
        initial = (other.get("initialTitle") or "").strip().lower()
        pid = int(other.get("pid") or 0)
        if not pid:
            continue
        if PHOTOS_CLASS in cls or title == PHOTOS_MAIN_TITLE or initial == PHOTOS_MAIN_TITLE:
            pids.add(pid)
            continue
        cmd = _pid_cmdlines(pid)
        if "gtk-photos" in cmd or "org.neuronix.GtkPhotos" in cmd:
            pids.add(pid)
    return pids


def _photos_dialog_title(title: str) -> bool:
    text = (title or "").lower()
    if any(s in text for s in DIALOG_TITLE_SUBSTR):
        return True
    return any(
        s in text
        for s in (
            "choose",
            "select thumbnail",
            "select folder",
            "select destination",
            "parent location",
            "photos folder not found",
            "pick thumbnail",
        )
    )


def is_photos_organizer(win: dict) -> bool:
    combined = f"{win.get('title') or ''} {win.get('initialTitle') or ''}".strip().lower()
    return combined == PHOTOS_MAIN_TITLE or combined.startswith("photo organizer")


def _photos_class(win: dict) -> bool:
    cls = (win.get("class") or "").lower().replace("_", ".")
    initial = (win.get("initialClass") or "").lower().replace("_", ".")
    return PHOTOS_CLASS in cls or PHOTOS_CLASS in initial


def is_gtk_image(win: dict) -> bool:
    cls = (win.get("class") or "").lower().replace("_", ".")
    initial = (win.get("initialClass") or "").lower().replace("_", ".")
    return GTK_IMAGE_CLASS in cls or GTK_IMAGE_CLASS in initial or "gtkimage" in cls or "gtkimage" in initial


def _spawned_by_photos(win: dict) -> bool:
    """True when this process is gtk-photos or a child of it."""
    pid = int(win.get("pid") or 0)
    if not pid:
        return False
    cmd = _pid_cmdlines(pid)
    if "gtk-photos" in cmd or "org.neuronix.GtkPhotos" in cmd:
        return True
    photos = _photos_app_pids()
    cur = pid
    for _ in range(8):
        if cur in photos:
            return True
        cur = _pid_parent(cur)
        if cur <= 1:
            break
    return False


def is_photos_media(win: dict) -> bool:
    """Image/video viewers opened from gtk-photos — not standalone gtk-image."""
    if is_photos_organizer(win):
        return False
    cls = (win.get("class") or "").lower()
    initial_cls = (win.get("initialClass") or "").lower()
    title = win.get("title") or ""
    initial = win.get("initialTitle") or ""
    if _photos_dialog_title(title) or _photos_dialog_title(initial):
        return False
    if any(t.rstrip("*") == PHOTOS_MEDIA_CLASS for t in _window_tags(win)):
        return True
    if PHOTOS_MEDIA_CLASS in cls or PHOTOS_MEDIA_CLASS in initial_cls:
        return True
    if _photos_class(win) and (
        _title_is_photos_media(title) or _title_is_photos_media(initial)
    ):
        return True
    pid = int(win.get("pid") or 0)
    if pid and any(marker in _pid_cmdlines(pid) for marker in PHOTOS_CMDLINE_MARKERS):
        return True
    if _class_is_chromium(cls) or _class_is_chromium(initial_cls):
        if pid and pid in _photos_chromium_tree_pids():
            return True
    if is_gtk_image(win):
        return _spawned_by_photos(win)
    return False


def is_photos_dialog(win: dict) -> bool:
    """gtk-photos windows that are not the organizer and not an image/video."""
    if is_photos_organizer(win) or is_photos_media(win):
        return False
    cls = (win.get("class") or "").lower().replace("_", ".")
    initial_cls = (win.get("initialClass") or "").lower().replace("_", ".")
    if _class_is_chromium(cls) or _class_is_chromium(initial_cls):
        return False
    if PHOTOS_CLASS in cls or PHOTOS_CLASS in initial_cls:
        return True
    pid = int(win.get("pid") or 0)
    if pid and pid in _photos_app_pids():
        return True
    return False


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int], gap: int) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + gap <= bx
        or bx + bw + gap <= ax
        or ay + ah + gap <= by
        or by + bh + gap <= ay
    )


def next_grid_xy(
    win_w: int,
    win_h: int,
    occupied: list[tuple[int, int, int, int]],
    origin_x: int,
    origin_y: int,
    area_w: int,
    area_h: int,
) -> tuple[int, int]:
    """Next gtk-photos slot: bottom-left, left→right, then the row above."""
    win_w = max(1, win_w)
    win_h = max(1, win_h)
    left, top = origin_x, origin_y
    right, bottom = origin_x + area_w, origin_y + area_h
    floor_y = bottom - win_h

    def _clamp(x: int, y: int) -> tuple[int, int]:
        max_x = left + max(0, area_w - win_w)
        max_y = bottom - win_h
        return max(left, min(x, max_x)), max(top, min(y, max_y))

    y_candidates = {floor_y}
    x_base = {left}
    for ox, oy, ow, oh in occupied:
        x_base.add(ox + ow + GAP)
        y_candidates.add(oy - GAP - win_h)
    for y in sorted(y_candidates, reverse=True):
        if y + win_h > bottom + GAP or y + win_h < top:
            continue
        for x in sorted(x_base):
            if x + win_w > right + GAP:
                continue
            candidate = (x, y, win_w, win_h)
            if any(_rects_overlap(candidate, rect, GAP) for rect in occupied):
                continue
            return _clamp(x, y)
    n_at_origin = sum(
        1 for ox, oy, _ow, _oh in occupied if ox == left and abs(oy - floor_y) <= 8
    )
    bump = (n_at_origin * 32) % 192
    return _clamp(left + bump, floor_y - bump)


def occupied_media_rects(except_addr: str) -> list[tuple[int, int, int, int]]:
    except_addr = except_addr if except_addr.startswith("0x") else f"0x{except_addr}"
    rects: list[tuple[int, int, int, int]] = []
    for win in hypr_json("clients"):
        if win.get("address") == except_addr:
            continue
        if not is_photos_media(win):
            continue
        at = win.get("at") or [0, 0]
        size = win.get("size") or [800, 600]
        rects.append((int(at[0]), int(at[1]), max(1, int(size[0])), max(1, int(size[1]))))
    return rects


def center_dialog(addr: str) -> None:
    """Float and center a dialog on its monitor's usable area (Waybar→hyprtabs).

    Avoids hyprctl ``centerwindow``, which can fling suite About/Preferences
    dialogs into huge off-screen coordinates under tabs mode.
    """
    target, raw = address_target(addr)
    win = client_by_address(raw)
    if not win:
        return
    ensure_floating(target, win)
    try:
        mon = monitor_by_id(win.get("monitor"))
    except Exception:
        try:
            mon = hdmi_monitor()
        except RuntimeError:
            return
    try:
        ux, uy, uw, uh = usable_rect(mon, hypr_json("layers"))
    except Exception:
        ux, uy = int(mon.get("x") or 0), int(mon.get("y") or 0)
        uw, uh = int(mon.get("width") or 1920), int(mon.get("height") or 1080)
    size = win.get("size") or [0, 0]
    sw, sh = int(size[0] or 0), int(size[1] or 0)
    # Reasonable dialog size — never the full tab slot.
    if sw <= 0 or sh <= 0 or sw >= int(uw * 0.85) or sh >= int(uh * 0.85):
        sw = max(420, min(720, int(uw * 0.45)))
        sh = max(320, min(560, int(uh * 0.55)))
    else:
        sw = max(280, min(sw, int(uw * 0.9)))
        sh = max(200, min(sh, int(uh * 0.9)))
    x = int(ux + max(0, (uw - sw) // 2))
    y = int(uy + max(0, (uh - sh) // 2))
    # Clamp so the whole dialog stays on the usable rect.
    x = max(ux, min(x, ux + max(0, uw - sw)))
    y = max(uy, min(y, uy + max(0, uh - sh)))
    try:
        dispatch("focuswindow", target)
    except Exception:
        pass
    dispatch_batch(
        [
            f"dispatch resizewindowpixel exact {sw} {sh},{target}",
            f"dispatch movewindowpixel exact {x} {y},{target}",
        ]
    )
    # Apps sometimes re-assert a wild position once — pin again shortly after.
    def _reclamp(a: str = raw, px: int = x, py: int = y, pw: int = sw, ph: int = sh) -> None:
        time.sleep(0.08)
        again = client_by_address(a)
        if not again:
            return
        at = again.get("at") or [0, 0]
        if abs(int(at[0]) - px) > 64 or abs(int(at[1]) - py) > 64:
            try:
                _pin_geometry(a, px, py, pw, ph)
            except Exception:
                pass

    threading.Thread(target=_reclamp, daemon=True).start()


def place_at(addr: str, x: int, y: int, w: int, h: int, monitor: str | None, focus: bool) -> None:
    target, raw = address_target(addr)
    win = client_by_address(raw)
    if not win:
        return
    if focus:
        dispatch("focuswindow", target)
    if monitor:
        mon = monitor_by_name(monitor)
        if win.get("monitor") != mon.get("id"):
            dispatch("movewindow", f"mon:{monitor}")
    ensure_floating(target, win)
    dispatch_batch(
        [
            f"dispatch resizewindowpixel exact {w} {h},{target}",
            f"dispatch movewindowpixel exact {x} {y},{target}",
        ]
    )


def place_photos_grid(addr: str, focus: bool = True) -> None:
    target, raw = address_target(addr)
    win = client_by_address(raw)
    if not win:
        return
    if focus:
        dispatch("focuswindow", target)
    dispatch("movewindow", f"mon:{hdmi_name()}")
    ensure_floating(target, win)
    win = client_by_address(raw) or win
    size = win.get("size") or [800, 600]
    ww, wh = max(1, int(size[0])), max(1, int(size[1]))
    mon = hdmi_monitor()
    ox, oy, aw, ah = usable_rect(mon, hypr_json("layers"))
    x, y = next_grid_xy(ww, wh, occupied_media_rects(raw), ox, oy, aw, ah)
    place_at(addr, x, y, ww, wh, None, focus=False)


def place_hdmi_full(addr: str, focus: bool = True) -> None:
    mon = hdmi_monitor()
    x, y, w, h = usable_rect(mon, hypr_json("layers"))
    place_at(addr, x, y, w, h, hdmi_name(), focus)


def window_monitor_name(win: dict, monitors: list[dict] | None = None) -> str:
    mid = win.get("monitor")
    for mon in monitors if monitors is not None else hypr_json("monitors"):
        if mon.get("id") == mid:
            return str(mon.get("name") or "")
    return ""


def on_dp(win: dict, monitors: list[dict] | None = None) -> bool:
    return window_monitor_name(win, monitors) in (DP_LEFT, DP_RIGHT)


def layout_mode_path() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return os.path.join(base, "kvnix", "layout-mode")


def layout_mode() -> str:
    """float, tile, or tabs. Unset file follows the screen: HDMI floats, otherwise tiles."""
    try:
        raw = open(layout_mode_path(), encoding="utf-8").read().strip().lower()
    except OSError:
        raw = ""
    if raw in ("float", "tile", "tabs"):
        return raw
    return "float" if has_hdmi() else "tile"


def set_layout_mode(mode: str) -> None:
    if mode not in ("float", "tile", "tabs"):
        raise ValueError(f"bad layout mode: {mode}")
    path = layout_mode_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(mode + "\n")
    os.replace(tmp, path)


def wants_tile_default() -> bool:
    return layout_mode() == "tile"


def wants_tabs() -> bool:
    return layout_mode() == "tabs"


def hyprtabs_strip_visible() -> bool:
    """True when the bottom tab capsule is (or should be) on screen."""
    if layout_mode() == "tabs":
        return True
    try:
        if os.path.isfile(CHROME_PREFS):
            with open(CHROME_PREFS, encoding="utf-8") as fh:
                raw = json.load(fh) or {}
            if isinstance(raw, dict) and raw.get("hyprtabs"):
                return True
    except Exception:
        pass
    if not _hyprtabs_loaded():
        return False
    try:
        out = hyprctl("getoption", "plugin:hyprtabs:enabled")
    except Exception:
        return False
    for line in (out or "").splitlines():
        if line.strip().startswith("int:"):
            try:
                return int(line.split(":", 1)[1].strip()) != 0
            except ValueError:
                break
    return False


def _hyprtabs_bottom_reserve() -> int:
    return int(HYPRTABS_H) + int(HYPRTABS_MARGIN) + int(HYPRTABS_GAP)


def _read_gaps_out() -> tuple[int, int, int, int] | None:
    try:
        raw = hyprctl("-j", "getoption", "general:gaps_out")
        data = json.loads(raw)
        custom = str(data.get("custom") or "").strip()
        parts = [int(x) for x in custom.replace(",", " ").split()]
        if len(parts) == 1:
            return parts[0], parts[0], parts[0], parts[0]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except Exception:
        return None
    return None


def sync_hyprtabs_bottom_gaps() -> None:
    """Bump gaps_out bottom so tiled windows clear the capsule (hyprctl from WM only)."""
    gaps = _read_gaps_out()
    if gaps is None:
        return
    t, r, b, l = gaps
    need = _hyprtabs_bottom_reserve()
    state_path = os.path.join(
        os.environ.get("XDG_STATE_HOME")
        or os.path.join(os.path.expanduser("~"), ".local", "state"),
        "kvnix",
        "hyprtabs-gaps-base",
    )
    if hyprtabs_strip_visible():
        if not os.path.isfile(state_path):
            try:
                os.makedirs(os.path.dirname(state_path), exist_ok=True)
                with open(state_path, "w", encoding="utf-8") as fh:
                    fh.write(f"{t} {r} {b} {l}\n")
            except OSError:
                pass
            base_b = b
        else:
            try:
                base = open(state_path, encoding="utf-8").read().split()
                base_b = int(base[2]) if len(base) >= 3 else b
                t, r, _, l = (int(base[0]), int(base[1]), int(base[2]), int(base[3])) if len(base) >= 4 else (t, r, b, l)
            except Exception:
                base_b = b
        new_b = base_b + need
        if new_b == b:
            return
        try:
            hyprctl("keyword", "general:gaps_out", f"{t},{r},{new_b},{l}")
        except Exception:
            pass
        return
    # Strip off — restore base gaps if we saved them.
    if os.path.isfile(state_path):
        try:
            base = open(state_path, encoding="utf-8").read().split()
            if len(base) >= 4:
                hyprctl(
                    "keyword",
                    "general:gaps_out",
                    f"{int(base[0])},{int(base[1])},{int(base[2])},{int(base[3])}",
                )
            os.remove(state_path)
        except Exception:
            pass


def _chrome_prefs_update(**kwargs) -> None:
    """Merge keys into neuronix-window-chrome.json (preserve siblings)."""
    try:
        raw: dict = {}
        if os.path.isfile(CHROME_PREFS):
            with open(CHROME_PREFS, encoding="utf-8") as fh:
                loaded = json.load(fh) or {}
            if isinstance(loaded, dict):
                raw = loaded
        for key, value in kwargs.items():
            raw[key] = bool(value)
        # hyprbars is always on; Themes toggles hyprbars_images instead.
        raw["hyprbars"] = True
        raw.setdefault("hyprbars_images", True)
        raw.setdefault("hyprframes", True)
        raw.setdefault("hyprtabs", False)
        os.makedirs(os.path.dirname(CHROME_PREFS), exist_ok=True)
        with open(CHROME_PREFS, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "hyprbars": True,
                    "hyprbars_images": bool(raw.get("hyprbars_images", True)),
                    "hyprframes": bool(raw.get("hyprframes", True)),
                    "hyprtabs": bool(raw.get("hyprtabs", False)),
                },
                fh,
                indent=2,
            )
            fh.write("\n")
    except OSError:
        pass


def _hyprtabs_so() -> str:
    for path in HYPRTABS_SO_CANDIDATES:
        if os.path.isfile(path):
            return path
    return ""


def _hyprbars_so() -> str:
    for path in HYPRBARS_SO_CANDIDATES:
        if os.path.isfile(path):
            return path
    return ""


def _hyprtabs_loaded() -> bool:
    try:
        out = hyprctl("plugin", "list")
    except Exception:
        return False
    return "plugin hyprtabs" in out.lower() or "\nhyprtabs" in out.lower() or "hyprtabs by" in out.lower()


def _hyprbars_loaded() -> bool:
    try:
        out = hyprctl("plugin", "list")
    except Exception:
        return False
    return "plugin hyprbars" in out.lower() or "hyprbars by" in out.lower()


def set_hyprbars_plugin(on: bool = True) -> None:
    """Hyprbars title bars are always enabled (needed to drag windows)."""
    del on  # API compat — cannot disable.
    _chrome_prefs_update(hyprbars=True)
    if not _hyprbars_loaded():
        so = _hyprbars_so()
        if so:
            try:
                hyprctl("plugin", "load", so)
            except Exception:
                pass
    try:
        hyprctl("keyword", "plugin:hyprbars:enabled", "true")
    except Exception:
        pass


def set_hyprtabs_plugin(on: bool) -> None:
    """Load/enable or hide the hyprtabs strip (does not spawn hyprctl from a plugin)."""
    prefs_on = bool(on)
    _chrome_prefs_update(hyprtabs=prefs_on)
    so = _hyprtabs_so()
    if on:
        if not _hyprtabs_loaded():
            if not so:
                return
            try:
                hyprctl("plugin", "load", so)
            except Exception:
                return
        try:
            hyprctl("keyword", "plugin:hyprtabs:enabled", "true")
        except Exception:
            pass
        set_hyprbars_plugin(True)
        sync_hyprtabs_bottom_gaps()
        return
    if _hyprtabs_loaded():
        try:
            hyprctl("keyword", "plugin:hyprtabs:enabled", "false")
        except Exception:
            pass
    sync_hyprtabs_bottom_gaps()
    set_hyprbars_plugin(True)


def _is_xdg_popup(win: dict) -> bool:
    xdg = str(win.get("xdgTag") or win.get("xdg_tag") or "").lower()
    return any(s in xdg for s in ("popup", "menu", "dropdown", "tooltip"))


def tile_address(addr: str, *, focus: bool = True) -> None:
    target = addr if str(addr).startswith("address:") else f"address:{addr}"
    if focus:
        dispatch("focuswindow", target)
    dispatch("settiled")


def tile_main_clients(*, focus: bool = True) -> None:
    """Tile the main screen. DP portraits are handled by tile_dp_clients."""
    monitors = hypr_json("monitors")
    for win in hypr_json("clients"):
        if on_dp(win, monitors):
            continue
        if is_minimized_win(win):
            continue
        if is_utility_float(win) or is_gtk_meld(win):
            continue
        if not win.get("mapped") or win.get("hidden") or _is_xdg_popup(win):
            continue
        addr = win.get("address")
        if not addr or not win.get("floating"):
            continue
        try:
            tile_address(addr, focus=focus)
        except Exception:
            pass


def restore_minimized_main_clients() -> None:
    """Rescue windows stranded on the legacy special:minimized workspace."""
    try:
        mon = hdmi_monitor()
        mid = int(mon["id"])
        mon_name = str(mon.get("name") or hdmi_name())
    except RuntimeError:
        return
    try:
        aw = hypr_json("activeworkspace")
        ws_dest = str(int(aw["id"])) if aw and aw.get("id") is not None else "e+0"
        # If focus is on a special workspace, prefer the monitor's active workspace.
        if str((aw or {}).get("name") or "").startswith("special"):
            for m in hypr_json("monitors"):
                if int(m.get("id") if m.get("id") is not None else -1) == mid:
                    aw2 = m.get("activeWorkspace") or {}
                    if aw2.get("id") is not None:
                        ws_dest = str(int(aw2["id"]))
                    break
    except Exception:
        ws_dest = "e+0"
    restored = 0
    for win in hypr_json("clients"):
        if not is_minimized_win(win):
            continue
        if not win.get("mapped"):
            continue
        # Do not call skip_new_window here — it treats every special:* as skip.
        if is_utility_float(win) or is_gtk_meld(win) or _is_xdg_popup(win):
            continue
        if on_dp(win):
            continue
        addr = win.get("address")
        if not addr:
            continue
        target = f"address:{addr}"
        try:
            dispatch("movetoworkspacesilent", f"{ws_dest},{target}")
        except Exception:
            try:
                dispatch("movetoworkspacesilent", f"e+0,{target}")
            except Exception:
                continue
        restored += 1
        try:
            wmon = int(win.get("monitor") if win.get("monitor") is not None else -1)
            if wmon != mid:
                dispatch("movewindow", f"mon:{mon_name}")
        except Exception:
            pass
    if restored:
        time.sleep(0.06)


def _cursor_xy() -> tuple[int, int] | None:
    try:
        pos = hypr_json("cursorpos")
        return int(pos.get("x") or 0), int(pos.get("y") or 0)
    except Exception:
        return None


def _movecursor(x: int, y: int) -> None:
    try:
        subprocess.check_output(
            ["hyprctl", "dispatch", "movecursor", str(int(x)), str(int(y))],
            text=True,
        )
    except Exception:
        pass


def _cursor_no_warps() -> bool:
    try:
        out = hyprctl("getoption", "cursor:no_warps")
        for line in out.splitlines():
            if line.strip().startswith("int:"):
                return int(line.split(":", 1)[1].strip()) != 0
    except Exception:
        pass
    return False


@contextmanager
def preserve_cursor() -> Iterator[None]:
    """Keep the pointer where it is across focus/layout churn (Waybar toggle)."""
    pos = _cursor_xy()
    was_no_warps = _cursor_no_warps()
    try:
        hyprctl("keyword", "cursor:no_warps", "true")
    except Exception:
        pass
    try:
        yield
    finally:
        # Re-pin several times: late focuswindow events can still fire after we
        # flip no_warps back off (follow_mouse / plugin adopt / settle sleeps).
        if pos is not None:
            _movecursor(pos[0], pos[1])
        try:
            hyprctl("keyword", "cursor:no_warps", "true" if was_no_warps else "false")
        except Exception:
            pass
        if pos is not None:
            for _ in range(4):
                time.sleep(0.04)
                _movecursor(pos[0], pos[1])


def apply_layout_mode() -> None:
    mode = layout_mode()
    try:
        with preserve_cursor():
            if mode == "tabs":
                apply_tabs_layout()
            elif mode == "tile":
                set_hyprtabs_plugin(False)
                restore_minimized_main_clients()
                # focus=True is OK here: preserve_cursor sets cursor:no_warps.
                tile_main_clients(focus=True)
            else:
                set_hyprtabs_plugin(False)
                restore_minimized_main_clients()
                float_hdmi_clients(reflow_floating=True, focus=False)
            sync_hyprtabs_bottom_gaps()
            tile_dp_clients()
    except Exception:
        # Hyprland may be restarting; layout file still records the intent.
        pass


def refresh_waybar_layout() -> None:
    subprocess.run(
        ["pkill", "-RTMIN+8", "waybar"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def layout_status() -> None:
    mode = layout_mode()
    # Icons: FontAwesome 4 for tile/cascade; Symbols Nerd Font md-tabs for tabs.
    # Label sits beside the icon (Cascade / Grid / Tab).
    if mode == "tile":
        icon = "\uf009"  # th-large
        label = "Grid"
        tip = "Windows are tiled in a grid. Click to cascade."
    elif mode == "tabs":
        icon = "\U000f0e4e"  # nf-md-tabs
        label = "Tab"
        tip = "Windows are tabbed full-width. Click to tile."
    else:
        icon = "\uf2d2"  # window-restore
        label = "Cascade"
        tip = "Windows cascade over each other. Click for tabs."
    text = f"{icon}  {label}"
    print(json.dumps({"text": text, "tooltip": tip, "class": mode}, ensure_ascii=False))


def layout_toggle() -> None:
    # Cycle: float (cascade) → tabs → tile → float …
    cur = layout_mode()
    if cur == "float":
        nxt = "tabs"
    elif cur == "tabs":
        nxt = "tile"
    else:
        nxt = "float"
    set_layout_mode(nxt)
    apply_layout_mode()
    refresh_waybar_layout()


def layout_set(mode: str) -> None:
    """Force a layout mode (used by Themes → Hyprtabs and layout-set CLI)."""
    set_layout_mode(mode)
    apply_layout_mode()
    refresh_waybar_layout()


def place_tab_window(addr: str, focus: bool = True, raise_over_siblings: bool = True) -> None:
    """Full-bleed float: Waybar bottom → hyprtabs top; raise above siblings (no minimize)."""
    addr = addr if str(addr).startswith("0x") or str(addr).startswith("address:") else f"0x{addr}"
    target = addr if str(addr).startswith("address:") else f"address:{addr}"
    raw = target.split(":", 1)[-1]
    win = client_by_address(raw)
    if not win or is_utility_float(win) or is_gtk_meld(win) or _is_xdg_popup(win):
        return
    # Real dialogs only — size-based overlays must still be expandable into tabs.
    if is_tabs_dialog(win):
        return
    if is_minimized_win(win):
        # Legacy rescue: anything still on special:minimized comes back.
        try:
            dispatch("movetoworkspacesilent", f"e+0,{target}")
            time.sleep(0.04)
            win = client_by_address(raw) or win
        except Exception:
            pass
    try:
        mon = hdmi_monitor()
        layers = hypr_json("layers")
        x, y, w, h = usable_rect(mon, layers)
    except Exception:
        return
    ensure_floating(target, win)
    try:
        fs = win.get("fullscreen")
        if fs not in (None, False, 0, "0"):
            dispatch("focuswindow", target)
            dispatch("fullscreen", "0")
    except Exception:
        pass
    if win.get("monitor") != mon.get("id"):
        try:
            dispatch("movewindow", f"mon:{hdmi_name()}")
            time.sleep(0.04)
            win = client_by_address(raw) or win
        except Exception:
            pass
    # Apps often remap size after first float — keep forcing the tab slot.
    for _ in range(10):
        _pin_geometry(raw, x, y, w, h)
        time.sleep(0.05)
        again = client_by_address(raw)
        if not again:
            break
        ensure_floating(target, again)
        try:
            layers = hypr_json("layers")
            x, y, w, h = usable_rect(mon, layers)
        except Exception:
            pass
        at = again.get("at") or [0, 0]
        size = again.get("size") or [0, 0]
        if (
            abs(int(at[0]) - x) <= 8
            and abs(int(at[1]) - y) <= 8
            and abs(int(size[0] or 0) - w) <= 16
            and abs(int(size[1] or 0) - h) <= 16
        ):
            break
    if raise_over_siblings:
        mid = mon.get("id")
        for other in hypr_json("clients"):
            oaddr = other.get("address")
            if not oaddr or oaddr == raw:
                continue
            if int(other.get("monitor") if other.get("monitor") is not None else -1) != mid:
                continue
            if on_dp(other) or is_utility_float(other) or is_gtk_meld(other) or _is_xdg_popup(other):
                continue
            if is_tabs_overlay(other, (x, y, w, h)):
                continue
            if not other.get("mapped") or other.get("hidden") or is_minimized_win(other):
                continue
            # Keep siblings on the workspace — pin to the same slot underneath.
            try:
                _pin_geometry(oaddr, x, y, w, h)
            except Exception:
                pass
    if focus:
        try:
            dispatch("focuswindow", target)
            dispatch("bringactivetotop")
        except Exception:
            pass
    _pin_geometry(raw, x, y, w, h)
    raise_tabs_overlays(int(mon.get("id")), (x, y, w, h))


def is_tabs_dialog(win: dict) -> bool:
    """True dialogs/pickers — center these; never expand them into a tab slot.

    Intentionally does NOT use a size heuristic: new apps often map small
    first, then get place_tab_window'd to full-bleed.
    """
    if not win:
        return True
    if is_dialog_like(win) or is_photos_dialog(win) or is_popup_or_menu(win):
        return True
    if _is_xdg_popup(win) or is_utility_float(win):
        return True
    # Suite apps open About/Preferences as a second window of the same class.
    title = f"{win.get('title') or ''} {win.get('initialTitle') or ''}".lower()
    return any(
        s in title
        for s in (
            "about",
            "preferences",
            "properties",
            "keyboard shortcuts",
            "open file",
            "save as",
            "open folder",
            "open with",
            "authenticate",
        )
    )


def is_tabs_overlay(win: dict, usable: tuple[int, int, int, int] | None = None) -> bool:
    """Windows that must stay above the tab stack and must not be re-pinned.

    Includes real dialogs plus already-mapped compact floats. Do not use this
    alone to decide openwindow placement — use is_tabs_dialog for that.
    """
    if is_tabs_dialog(win):
        return True
    if not win.get("floating"):
        return False
    size = win.get("size") or [0, 0]
    w, h = int(size[0] or 0), int(size[1] or 0)
    if w <= 0 or h <= 0:
        return False
    if usable is None:
        try:
            mon = hdmi_monitor()
            usable = usable_rect(mon, hypr_json("layers"))
        except Exception:
            return False
    _ux, _uy, uw, uh = usable
    if uw <= 0 or uh <= 0:
        return False
    # Already-compact float (dialog that escaped title heuristics).
    return w < int(uw * 0.85) or h < int(uh * 0.85)


def raise_tabs_overlays(mid: int, usable: tuple[int, int, int, int] | None = None) -> None:
    """Put dialogs/pickers back above the full-bleed tab window after a raise."""
    for win in hypr_json("clients"):
        if int(win.get("monitor") if win.get("monitor") is not None else -1) != mid:
            continue
        if not win.get("mapped") or win.get("hidden") or is_minimized_win(win):
            continue
        if not is_tabs_overlay(win, usable):
            continue
        addr = win.get("address")
        if not addr:
            continue
        try:
            dispatch("alterzorder", f"top,address:{addr}")
        except Exception:
            pass


def _tabs_main_clients(mid: int, usable: tuple[int, int, int, int] | None = None) -> list[dict]:
    clients: list[dict] = []
    for win in hypr_json("clients"):
        if on_dp(win):
            continue
        if is_minimized_win(win):
            continue
        on_main = int(win.get("monitor") if win.get("monitor") is not None else -1) == mid
        if not on_main:
            continue
        if not win.get("mapped") or win.get("hidden") or skip_new_window(win) or is_gtk_meld(win):
            continue
        # Skip real dialogs only — undersized new apps must stay in the list so
        # apply_tabs_layout / pin_tabs can expand them to the full slot.
        if is_utility_float(win) or _is_xdg_popup(win) or is_tabs_dialog(win):
            continue
        if not win.get("address"):
            continue
        clients.append(win)
    return clients


def pin_tabs_after_click(focus_addr: str) -> None:
    """Fast pin after a hyprtabs capsule click.

    The plugin already focused the chosen window and kept the pointer on the
    capsule. Only resize/raise here — never focuswindow or movecursor (those
    yank the pointer to the previous/next window center).
    """
    want = focus_addr if str(focus_addr).startswith("0x") else f"0x{focus_addr}"
    was_no_warps = _cursor_no_warps()
    try:
        hyprctl("keyword", "cursor:no_warps", "true")
    except Exception:
        pass
    try:
        try:
            mon = hdmi_monitor()
            mid = int(mon["id"])
            x, y, w, h = usable_rect(mon, hypr_json("layers"))
        except Exception:
            return
        usable = (x, y, w, h)
        clients = _tabs_main_clients(mid, usable)
        if not clients:
            return
        for win in clients:
            addr = str(win.get("address") or "")
            if not addr:
                continue
            target = f"address:{addr}"
            try:
                ensure_floating(target, win)
            except Exception:
                pass
            # Avoid focuswindow just to leave fullscreen — keyword the window.
            try:
                fs = win.get("fullscreen")
                if fs not in (None, False, 0, "0"):
                    dispatch("fullscreenstate", f"0 0 {target}")
            except Exception:
                pass
            _pin_geometry(addr, x, y, w, h)
        if any(str(w.get("address")) == want for w in clients):
            try:
                dispatch("alterzorder", f"top,address:{want}")
            except Exception:
                pass
            # Do NOT focuswindow here — the plugin already focused the tab and
            # parked the cursor on the capsule; focuswindow warps to center.
        # Keep open dialogs/pickers above the raised tab window.
        raise_tabs_overlays(mid, usable)
    finally:
        try:
            hyprctl("keyword", "cursor:no_warps", "true" if was_no_warps else "false")
        except Exception:
            pass


def apply_tabs_layout(focus_addr: str | None = None, *, do_focus: bool = True) -> None:
    """Enable hyprtabs and pin every main-screen window as a full-width tab.

    When focus_addr is set (e.g. Super overview pick), that window is raised on
    top after every sibling is pinned to the Waybar→hyprtabs slot.
    """
    set_hyprtabs_plugin(True)
    # Rescue anything left on the old minimize special before tabbing.
    restore_minimized_main_clients()
    try:
        mon = hdmi_monitor()
        mid = int(mon["id"])
    except RuntimeError:
        return
    try:
        usable = usable_rect(mon, hypr_json("layers"))
    except Exception:
        usable = None
    clients = _tabs_main_clients(mid, usable)
    if not clients:
        return

    def _history(win: dict) -> int:
        try:
            return int(win.get("focusHistoryID"))
        except (TypeError, ValueError):
            return 10_000

    want = None
    if focus_addr:
        want = focus_addr if str(focus_addr).startswith("0x") else f"0x{focus_addr}"

    # Most recent focusHistoryID is lowest — front of the pile (unless overridden).
    ordered = sorted(clients, key=_history)
    front = str(ordered[0].get("address") or "")
    if want and any(str(w.get("address")) == want for w in clients):
        front = want
    for win in ordered:
        addr = str(win.get("address") or "")
        if not addr:
            continue
        # Never focus during layout apply — focuswindow warps the pointer.
        place_tab_window(addr, focus=False, raise_over_siblings=False)
    if front:
        place_tab_window(front, focus=False, raise_over_siblings=True)
        try:
            dispatch("alterzorder", f"top,address:{front}")
        except Exception:
            pass
        if do_focus:
            try:
                dispatch("focuswindow", f"address:{front}")
            except Exception:
                pass
    raise_tabs_overlays(mid, usable)


def tile_to(monitor: str, addr: str) -> None:
    """Move the window onto a DP portrait and tile it into dwindle."""
    target, raw = address_target(addr)
    win = client_by_address(raw)
    if not win:
        return
    dispatch("focuswindow", target)
    fs = win.get("fullscreen")
    if fs not in (None, False, 0, "0"):
        dispatch("fullscreen", "0")
    dest = monitor_by_name(monitor)
    if win.get("monitor") != dest.get("id"):
        dispatch("movewindow", f"mon:{monitor}")
        time.sleep(0.04)
    dispatch("settiled")


def place_float(
    addr: str,
    align: str = "center",
    focus: bool = True,
    row: str = "bottom",
    pin: bool = True,
    width_frac: tuple[int, int] = (1, 3),
) -> tuple[int, int, int, int]:
    target, raw = address_target(addr)
    win = client_by_address(raw)
    if not win:
        return 0, 0, 0, 0
    if is_utility_float(win):
        at = win.get("at") or [0, 0]
        size = win.get("size") or [0, 0]
        return int(at[0]), int(at[1]), int(size[0] or 0), int(size[1] or 0)
    mon = hdmi_monitor()
    layers = hypr_json("layers")
    slot = hdmi_slot_rect(mon, layers, align, row, width_frac)
    usable = usable_rect(mon, layers)
    sx, sy, w, h = slot
    others = _slot_pile_windows(raw, slot, win, mon, layers, width_frac=width_frac)
    ordered = others + [win]
    positions = _cascade_positions(len(ordered), slot, usable)
    x, y = positions[-1]
    move_mon = hdmi_name() if win.get("monitor") != mon.get("id") else None
    if move_mon:
        if focus:
            dispatch("focuswindow", target)
        dispatch("movewindow", f"mon:{move_mon}")
        time.sleep(0.04)
    _apply_card_stack(ordered, positions, w, h, raw, focus=focus)
    if not pin:
        return x, y, w, h
    # Chrome restores last-session size after map — pin the slot.
    for _ in range(3):
        again = client_by_address(raw)
        if not again:
            break
        size = again.get("size") or [0, 0]
        at = again.get("at") or [0, 0]
        if (
            abs(int(size[0]) - w) <= 24
            and abs(int(size[1]) - h) <= 24
            and abs(int(at[0]) - x) <= 24
            and abs(int(at[1]) - y) <= 24
        ):
            break
        dispatch_batch(
            [
                f"dispatch resizewindowpixel exact {w} {h},{target}",
                f"dispatch movewindowpixel exact {x} {y},{target}",
            ]
        )
        time.sleep(0.04)
    return x, y, w, h


def _pin_geometry(addr: str, x: int, y: int, w: int, h: int) -> None:
    """Resize/move only — never focus, so the pointer can leave the window."""
    target, _raw = address_target(addr)
    # Immediate geometry (no windowsMove slide) when pinning tab slots.
    batch = [
        f"dispatch resizewindowpixel exact {w} {h},{target}",
        f"dispatch movewindowpixel exact {x} {y},{target}",
    ]
    if wants_tabs() or hyprtabs_strip_visible():
        try:
            hyprctl("keyword", "animation", "windowsMove,0,1,default")
            hyprctl("keyword", "animation", "windowsIn,0,1,default")
            hyprctl("keyword", "animation", "fadeIn,0,1,default")
        except Exception:
            pass
        try:
            dispatch_batch(batch)
        finally:
            try:
                # Restore Neuronix defaults (see hyprland.conf animations block).
                hyprctl("keyword", "animation", "windowsMove,1,3.5,emphasizedDecel,slide")
                hyprctl("keyword", "animation", "windowsIn,1,3.5,emphasizedDecel,popin 80%")
                hyprctl("keyword", "animation", "fadeIn,1,3,emphasizedDecel")
            except Exception:
                pass
        return
    dispatch_batch(batch)


def _slot_for_new_window(new_addr: str) -> tuple[str, str]:
    """Join the previously focused HDMI pile when possible; else bottom-center."""
    new_addr = new_addr if new_addr.startswith("0x") else f"0x{new_addr}"
    try:
        monitors = hypr_json("monitors")
        mon = hdmi_monitor(monitors)
    except RuntimeError:
        return "center", "bottom"
    layers = hypr_json("layers")
    clients = hypr_json("clients")
    all_slots = _nine_slot_rects(mon, layers)
    prev = None
    best_hist = None
    for cand in clients:
        if cand.get("address") == new_addr:
            continue
        if not cand.get("mapped") or cand.get("hidden") or not cand.get("floating"):
            continue
        if cand.get("monitor") != mon.get("id"):
            continue
        if skip_new_window(cand):
            continue
        hid = cand.get("focusHistoryID")
        if hid is None:
            continue
        hid = int(hid)
        if best_hist is None or hid < best_hist:
            best_hist = hid
            prev = cand
    if prev is None:
        return "center", "bottom"
    wx, wy, _ww, _wh = _client_rect(prev)
    slot = _nearest_slot_rect(wx, wy, all_slots)
    if _window_in_slot(prev, slot, mon.get("id"), all_slots):
        key = _align_row_for_slot(slot, mon, layers)
        if key:
            return key
    return "center", "bottom"


def overview_landscape_cells(
    n: int, ox: int, oy: int, aw: int, ah: int
) -> tuple[int, int, int, int, int, int]:
    """Equal landscape (w>h) cells; grid is centered — does not stretch to fill.

    Returns (cols, rows, cell_w, cell_h, origin_x, origin_y).

    Sparse grids (especially a single window) are capped so cards stay pickable
    tiles rather than expanding to the full usable monitor.
    """
    if n < 1:
        return 1, 1, max(200, aw // 2), max(120, ah // 3), ox, oy

    # Prefer ~16:9 landscape cards. Cap so 1 window is a centered tile, not
    # full-bleed (one cell would otherwise claim the whole usable rect).
    aspect = 16.0 / 9.0
    max_cell_w = max(200, int(aw * 0.5))
    max_cell_h = max(120, int(ah * 0.5))
    best: tuple[float, int, int, int, int] | None = None
    # Try column counts that keep a reasonable grid.
    for cols in range(1, n + 1):
        rows = max(1, math.ceil(n / cols))
        # Max cell that fits this grid in the usable area.
        max_w = min(max_cell_w, (aw - GAP * max(0, cols - 1)) // cols)
        max_h = min(max_cell_h, (ah - GAP * max(0, rows - 1)) // rows)
        if max_w < 160 or max_h < 100:
            continue
        # Fit landscape rectangle inside the max cell.
        cell_w = max_w
        cell_h = int(cell_w / aspect)
        if cell_h > max_h:
            cell_h = max_h
            cell_w = int(cell_h * aspect)
        if cell_w <= cell_h:
            # Enforce width > height even on short monitors.
            cell_w = min(max_w, cell_h + max(40, cell_h // 5))
            if cell_w <= cell_h:
                continue
        if cell_w < 160 or cell_h < 100:
            continue
        area = cell_w * cell_h
        # Prefer larger cards; slight bias toward fewer rows.
        score = area - rows * 50
        if best is None or score > best[0]:
            best = (float(score), cols, rows, cell_w, cell_h)

    if best is None:
        cols = max(1, math.ceil(math.sqrt(n)))
        rows = max(1, math.ceil(n / cols))
        cell_h = max(100, min(ah // max(1, rows) - GAP, max_cell_h, 400))
        cell_w = min(aw // max(1, cols) - GAP, max_cell_w, int(cell_h * aspect))
        if cell_w <= cell_h:
            cell_w = cell_h + 40
    else:
        _score, cols, rows, cell_w, cell_h = best

    grid_w = cols * cell_w + GAP * max(0, cols - 1)
    grid_h = rows * cell_h + GAP * max(0, rows - 1)
    if grid_w > aw or grid_h > ah:
        scale = min(aw / max(1, grid_w), ah / max(1, grid_h), 1.0)
        cell_w = max(80, int(cell_w * scale))
        cell_h = max(60, int(cell_h * scale))
        if cell_w <= cell_h:
            cell_w = min(max(81, cell_h + 20), max(80, aw // max(1, cols) - GAP))
        grid_w = cols * cell_w + GAP * max(0, cols - 1)
        grid_h = rows * cell_h + GAP * max(0, rows - 1)
    origin_x = ox + max(0, (aw - grid_w) // 2)
    origin_y = oy + max(0, (ah - grid_h) // 2)
    return cols, rows, cell_w, cell_h, origin_x, origin_y


def _overview_place_grid(clients: list[dict]) -> int:
    """Shrink clients into centered landscape overview cells. Returns column count.

    Each cell keeps a top strip for hyprbars (``bar_part_of_window = false``),
    so the − □ × chrome sits inside the card instead of overlapping the
    preview above (GAP is smaller than the bar height).
    """
    if not clients:
        return 1
    mon = hdmi_monitor()
    ox, oy, aw, ah = overview_usable_rect(mon, hypr_json("layers"))
    n = len(clients)
    cols, _rows, cell_w, cell_h, grid_ox, grid_oy = overview_landscape_cells(
        n, ox, oy, aw, ah
    )
    body_h = max(80, cell_h - HYPRBAR_H)
    for i, win in enumerate(clients):
        addr = win["address"]
        target = f"address:{addr}"
        row, col = divmod(i, cols)
        cell_x = grid_ox + col * (cell_w + GAP)
        cell_y = grid_oy + row * (cell_h + GAP)
        # Client below its title bar; bar renders in [cell_y, cell_y + HYPRBAR_H).
        x, y = cell_x, cell_y + HYPRBAR_H
        w, h = cell_w, body_h
        fs = win.get("fullscreen")
        if fs not in (None, False, 0, "0"):
            dispatch("focuswindow", target)
            dispatch("fullscreen", "0")
        place_at(addr, x, y, w, h, None, focus=False)
        time.sleep(0.02)
        dispatch_batch(
            [
                f"dispatch resizewindowpixel exact {w} {h},{target}",
                f"dispatch movewindowpixel exact {x} {y},{target}",
            ]
        )
    return cols


def _pull_to_overview_workspace(addr: str, ws_id: int) -> None:
    """Move a window (often special:minimized) onto the overview HDMI workspace."""
    target = f"address:{addr}"
    try:
        dispatch("movetoworkspacesilent", f"{int(ws_id)},{target}")
    except Exception:
        pass
    time.sleep(0.03)
    try:
        dispatch("focuswindow", target)
        dispatch("movewindow", f"mon:{hdmi_name()}")
    except Exception:
        pass
    time.sleep(0.02)


def restore_overview_windows(
    snaps: list[dict],
    focus_addr: str | None = None,
    workspace: int | None = None,
) -> None:
    """Put every snapshotted window back, then raise focus_addr if given."""
    for s in snaps:
        addr = s.get("address")
        if not addr:
            continue
        target = f"address:{addr}"
        win = client_by_address(addr)
        if not win:
            continue
        fs = win.get("fullscreen")
        if fs not in (None, False, 0, "0"):
            dispatch("focuswindow", target)
            dispatch("fullscreen", "0")
        # Legacy: windows pulled out of special:minimized stay on this workspace.
        if s.get("minimized") and workspace is not None:
            try:
                dispatch("movetoworkspacesilent", f"{int(workspace)},{target}")
            except Exception:
                pass
        if s.get("floating"):
            ensure_floating(target, win)
            w, h = int(s.get("w") or 0), int(s.get("h") or 0)
            x, y = int(s.get("x") or 0), int(s.get("y") or 0)
            if w > 0 and h > 0:
                dispatch_batch(
                    [
                        f"dispatch resizewindowpixel exact {w} {h},{target}",
                        f"dispatch movewindowpixel exact {x} {y},{target}",
                    ]
                )
        else:
            dispatch("focuswindow", target)
            dispatch("settiled")

    if focus_addr:
        target = f"address:{focus_addr}"
        dispatch("focuswindow", target)
        for cmd, arg in (("bringactivetotop", ""), ("alterzorder", "top")):
            try:
                if arg:
                    dispatch(cmd, arg)
                else:
                    dispatch(cmd)
                break
            except Exception:
                continue


def overview_adopt_window(addr: str) -> bool:
    """Put a newly mapped window into the live Super overview grid."""
    st = overview_state()
    if not st:
        return False
    addr = addr if addr.startswith("0x") else f"0x{addr}"
    win = None
    for _ in range(40):
        win = client_by_address(addr)
        if win and win.get("mapped"):
            break
        time.sleep(0.03)
    if not win or not win.get("mapped"):
        return True
    if skip_new_window(win) or is_dialog_like(win) or is_photos_dialog(win):
        return True
    try:
        mon = hdmi_monitor()
    except RuntimeError:
        return True
    mid = int(mon["id"])
    ws_id = int(st.get("workspace") or 0)
    wsid = int((win.get("workspace") or {}).get("id") or -1)
    if ws_id and wsid != ws_id:
        try:
            dispatch("movetoworkspacesilent", f"{ws_id},address:{addr}")
        except Exception:
            pass
        time.sleep(0.05)
        win = client_by_address(addr) or win
    if int(win.get("monitor") if win.get("monitor") is not None else -1) != mid:
        try:
            dispatch("movewindow", f"mon:{hdmi_name()}")
        except Exception:
            pass
        time.sleep(0.05)
        win = client_by_address(addr) or win

    snaps = list(st.get("windows") or [])
    if addr not in {str(s.get("address")) for s in snaps}:
        at = win.get("at") or [0, 0]
        size = win.get("size") or [0, 0]
        cw, ch = int(size[0] or 0), int(size[1] or 0)
        if cw >= 400 and ch >= 300:
            rx, ry, rw, rh = int(at[0]), int(at[1]), cw, ch
        else:
            layers = hypr_json("layers")
            rx, ry, rw, rh = hdmi_slot_rect(mon, layers, "center", "bottom")
        snaps.append(
            {
                "address": addr,
                "floating": True,
                "x": rx,
                "y": ry,
                "w": rw,
                "h": rh,
            }
        )
        st["windows"] = snaps
        write_overview_state(st)

    by_addr = {c.get("address"): c for c in hypr_json("clients")}
    clients: list[dict] = []
    seen: set[str] = set()
    for s in snaps:
        a = str(s.get("address") or "")
        c = by_addr.get(a)
        if not c or a in seen:
            continue
        if not c.get("mapped") or c.get("hidden"):
            continue
        clients.append(c)
        seen.add(a)
    if addr in by_addr and addr not in seen:
        clients.append(by_addr[addr])
    if not clients:
        return True
    st["cols"] = _overview_place_grid(clients)
    write_overview_state(st)
    overview_raise(addr)
    return True


def grid_hdmi(*, enter_overview: bool = False) -> None:
    """Equal floating cells on the current HDMI workspace.

    When enter_overview=True, snapshot layouts first; a later click restores
    every window and raises the picked one. Overview cells are landscape
    rectangles (width > height), centered — not stretched to fill the screen.
    Minimized windows (special:minimized) are pulled into the grid too.
    """
    if enter_overview and overview_state():
        # Super again: leave overview, restore previous layouts.
        overview_cancel()
        return

    if enter_overview and (wants_tabs() or (not has_hdmi() and wants_tile_default())):
        # Tabs (and laptop tiled): leave windows as they are — just fuzzel.
        # Float mode falls through and shows the same preview grid as HDMI.
        if _fuzzel_running():
            _dismiss_fuzzel()
            return
        overview_fuzzel("")
        return

    mon = hdmi_monitor()
    mid = int(mon["id"])
    active_ws = hypr_json("activeworkspace") or {}
    out = str(mon.get("name") or HDMI)
    if active_ws.get("monitor") != out:
        aws = mon.get("activeWorkspace") or {}
        ws_id = int(aws.get("id") or 1)
        dispatch("focusmonitor", out)
        dispatch("workspace", str(ws_id))
        active_ws = hypr_json("activeworkspace") or {}
    ws_id = int(active_ws.get("id") or 1)

    clients: list[dict] = []
    minimized: list[dict] = []
    for win in hypr_json("clients"):
        if not win.get("address"):
            continue
        if not win.get("mapped") or win.get("hidden"):
            continue
        if is_dialog_like(win) or is_photos_dialog(win):
            continue
        cls = (win.get("class") or "").lower()
        tags = _window_tags(win)
        if "waybar-popover" in tags or "sidepanel" in tags or "settings-host" in tags:
            continue
        if any(s in cls for s in SKIP_CLASS_SUBSTR):
            continue
        if is_popup_or_menu(win):
            continue
        # special:minimized must be collected before skip_new_window (that
        # helper skips every special:* workspace, including minimize).
        if is_minimized_win(win):
            minimized.append(win)
            continue
        if skip_new_window(win):
            continue
        if int(win.get("monitor") if win.get("monitor") is not None else -1) != mid:
            continue
        wsid = int((win.get("workspace") or {}).get("id") or -1)
        if wsid != ws_id:
            continue
        clients.append(win)

    if enter_overview and minimized:
        # One-shot rescue of anything still on the legacy minimize special.
        clients.extend(minimized)

    if not clients:
        if enter_overview:
            overview_fuzzel("")
        return

    clients.sort(
        key=lambda w: (
            int((w.get("at") or [0, 0])[1]),
            int((w.get("at") or [0, 0])[0]),
            w.get("address") or "",
        )
    )
    dispatch("focusmonitor", str(mon.get("name") or HDMI))
    dispatch("workspace", str(ws_id))

    if enter_overview:
        snaps = []
        for win in clients:
            at = win.get("at") or [0, 0]
            size = win.get("size") or [0, 0]
            snaps.append(
                {
                    "address": win["address"],
                    "floating": bool(win.get("floating")),
                    "x": int(at[0]),
                    "y": int(at[1]),
                    "w": max(0, int(size[0] or 0)),
                    "h": max(0, int(size[1] or 0)),
                    "minimized": False,
                }
            )
        for win in clients:
            if is_minimized_win(win):
                _pull_to_overview_workspace(win["address"], ws_id)
        # Refresh client dicts after moves (addresses stable).
        by_addr = {c.get("address"): c for c in hypr_json("clients")}
        placed = [by_addr[w["address"]] for w in clients if w["address"] in by_addr]
        if not placed:
            placed = clients

        write_overview_state(
            {
                "active": True,
                "workspace": ws_id,
                "windows": snaps,
                "cols": 1,
                "armed_at": time.time() + 0.35,
            }
        )
        cols = _overview_place_grid(placed)
        st = overview_state() or {}
        st["cols"] = cols
        write_overview_state(st)
        _set_overview_close_highlight(True)
        overview_raise(placed[0]["address"])
        try:
            dispatch("submap", "hdmi-overview")
        except Exception:
            pass
        # Super: zoomed grid plus fuzzel. Blocks until fuzzel exits (click /
        # Super / Escape kill it from another bind).
        overview_fuzzel("")
        return

    n = len(clients)
    ox, oy, aw, ah = usable_rect(mon, hypr_json("layers"))
    cols = max(1, math.ceil(math.sqrt(n)))
    _rows = max(1, math.ceil(n / cols))
    cell_w = max(200, (aw - GAP * max(0, cols - 1)) // cols)
    cell_h = max(160, (ah - GAP * max(0, _rows - 1)) // _rows)
    grid_ox, grid_oy = ox, oy

    for i, win in enumerate(clients):
        addr = win["address"]
        target = f"address:{addr}"
        row, col = divmod(i, cols)
        x = grid_ox + col * (cell_w + GAP)
        y = grid_oy + row * (cell_h + GAP)
        fs = win.get("fullscreen")
        if fs not in (None, False, 0, "0"):
            dispatch("focuswindow", target)
            dispatch("fullscreen", "0")
        place_at(addr, x, y, cell_w, cell_h, None, focus=False)
        time.sleep(0.02)
        dispatch_batch(
            [
                f"dispatch resizewindowpixel exact {cell_w} {cell_h},{target}",
                f"dispatch movewindowpixel exact {x} {y},{target}",
            ]
        )

    dispatch("focuswindow", f"address:{clients[0]['address']}")


def overview_state_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(runtime, "hdmi-overview.json")


def overview_state() -> dict | None:
    path = overview_state_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("active"):
        return None
    return data


def write_overview_state(data: dict | None) -> None:
    path = overview_state_path()
    if data is None:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def overview_dismiss_launcher() -> bool:
    """Close fuzzel over the overview grid; leave the preview windows up.

    Returns True when a launcher was dismissed (caller should not exit overview).
    """
    st = overview_state()
    if not st:
        return False
    if not (st.get("launcher") or _fuzzel_running()):
        return False
    _dismiss_fuzzel()
    cur = overview_state()
    if cur:
        cur.pop("launcher", None)
        write_overview_state(cur)
    try:
        dispatch("submap", "hdmi-overview")
    except Exception:
        pass
    return True


def overview_escape() -> None:
    """First Escape closes fuzzel; second Escape closes the window previews."""
    if overview_dismiss_launcher():
        return
    overview_cancel()


def _hyprbars_close_button_value(*, highlight: bool) -> str:
    """hyprbars-button value for the × control (Neuronix replace-in-place by glyph)."""
    action = "hyprctl dispatch closewindow activewindow"
    glyph = "rgb(eeffff)"
    if highlight:
        return f"rgb(c43e1c), 22, ×, {action}, {glyph}"
    # Match the bar fill so × is quiet outside overview; gtk-theme may retint later.
    bar = "rgb(363737)"
    for path in (
        os.path.expanduser("~/.config/hypr/hyprland.conf"),
        os.path.expanduser("~/configs/hypr/hyprland.conf"),
    ):
        try:
            with open(path, encoding="utf-8") as fh:
                conf = fh.read()
        except OSError:
            continue
        for line in conf.splitlines():
            trimmed = line.lstrip()
            if not trimmed.startswith("hyprbars-button") or "×" not in trimmed:
                continue
            if "=" not in trimmed:
                continue
            value = trimmed.split("=", 1)[1].strip()
            # Prefer conf when it is not the overview highlight (avoid sticky red).
            if value.startswith("rgb(c43e1c)"):
                break
            return value
        m = re.search(
            r"(?m)^\s*bar_color\s*=\s*rgba\(([0-9a-fA-F]{6})",
            conf,
        )
        if m:
            bar = f"rgb({m.group(1)})"
        break
    return f"{bar}, 18, ×, {action}, {glyph}"


def _set_overview_close_highlight(enabled: bool) -> None:
    """Red × only while Super overview is up; quiet bar-matching × otherwise."""
    value = _hyprbars_close_button_value(highlight=bool(enabled))
    try:
        subprocess.run(
            ["hyprctl", "keyword", "plugin:hyprbars:hyprbars-button", value],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except Exception:
        pass


def overview_cancel() -> None:
    st = overview_state()
    _set_overview_close_highlight(False)
    write_overview_state(None)
    try:
        dispatch("submap", "reset")
    except Exception:
        pass
    _dismiss_fuzzel()
    if not st or not st.get("windows"):
        return
    if wants_tabs() or hyprtabs_strip_visible():
        apply_tabs_layout()
        return
    ws = st.get("workspace")
    restore_overview_windows(
        list(st["windows"]),
        workspace=int(ws) if ws is not None else None,
    )


def _fuzzel_pids() -> set[int]:
    try:
        out = subprocess.check_output(["pgrep", "-x", "fuzzel"], text=True, timeout=1)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    pids: set[int] = set()
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(int(line))
    return pids


def _dismiss_fuzzel() -> None:
    """Drop the Super-overview launcher so a window click can finish the pick."""
    subprocess.run(
        ["pkill", "-x", "fuzzel"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["pkill", "-f", "neuronix_fuzzel_panel.py"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _fuzzel_running() -> bool:
    return bool(_fuzzel_pids())


def _sanitize_query(query: str) -> str:
    return "".join(ch for ch in (query or "") if ch.isalpha() or ch.isdigit())[:16]


def _send_to_fuzzel(text: str) -> None:
    if not text:
        return
    for ch in text.lower():
        try:
            dispatch("sendshortcut", f",{ch},class:fuzzel")
            continue
        except Exception:
            pass
        subprocess.run(
            ["ydotool", "type", "--", ch],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _pointer_on_fuzzel() -> bool:
    """True when the cursor is on fuzzel or its full-width chrome panel."""
    pids = _fuzzel_pids()
    try:
        pos = hypr_json("cursorpos")
        cx, cy = int(pos.get("x") or 0), int(pos.get("y") or 0)
    except Exception:
        return bool(pids)
    try:
        layers = hypr_json("layers")
    except Exception:
        layers = {}
    if isinstance(layers, dict):
        for info in layers.values():
            if not isinstance(info, dict):
                continue
            for level in (info.get("levels") or {}).values():
                for surf in level or []:
                    ns = str(surf.get("namespace") or "").lower()
                    try:
                        pid = int(surf.get("pid") or 0)
                    except Exception:
                        pid = 0
                    # fuzzel namespace is "launcher"; chrome is "neuronix-fuzzel-panel".
                    on_chrome = (
                        pid in pids
                        or "fuzzel" in ns
                        or ns in ("launcher", "neuronix-fuzzel-panel")
                    )
                    if not on_chrome:
                        continue
                    x, y = int(surf.get("x") or 0), int(surf.get("y") or 0)
                    w, h = int(surf.get("w") or 0), int(surf.get("h") or 0)
                    if w > 0 and h > 0 and x <= cx < x + w and y <= cy < y + h:
                        return True
    try:
        clients = hypr_json("clients")
    except Exception:
        clients = []
    for win in clients:
        if "fuzzel" not in str(win.get("class") or "").lower():
            continue
        at = win.get("at") or [0, 0]
        size = win.get("size") or [0, 0]
        x, y = int(at[0]), int(at[1])
        w, h = int(size[0] or 0), int(size[1] or 0)
        if w > 0 and h > 0 and x <= cx < x + w and y <= cy < y + h:
            return True
    return False


def _passthrough_click_to_fuzzel() -> None:
    """Hypr mouse binds eat the event — hop to a pass submap and redeliver via ydotool."""
    try:
        dispatch("submap", "hdmi-overview-pass")
    except Exception:
        return
    time.sleep(0.03)
    try:
        subprocess.run(
            ["ydotool", "click", "0xC0"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
    except Exception:
        pass
    time.sleep(0.05)
    st = overview_state()
    if st and st.get("launcher") and _fuzzel_running():
        try:
            dispatch("submap", "hdmi-overview-launcher")
        except Exception:
            pass


def overview_finish_from_launcher(known_addrs: set[str]) -> None:
    """After fuzzel launches an app: leave overview and focus the new window."""
    st = overview_state()
    if not st:
        return
    snaps = list(st.get("windows") or [])
    ws_id = st.get("workspace")
    tabs = wants_tabs() or hyprtabs_strip_visible()
    _set_overview_close_highlight(False)
    write_overview_state(None)
    try:
        dispatch("submap", "reset")
    except Exception:
        pass
    if ws_id is not None:
        try:
            dispatch("workspace", str(int(ws_id)))
        except Exception:
            pass
    if snaps and not tabs:
        restore_overview_windows(
            snaps,
            focus_addr=None,
            workspace=int(ws_id) if ws_id is not None else None,
        )

    focus: str | None = None
    for _ in range(50):
        time.sleep(0.04)
        try:
            clients = hypr_json("clients")
        except Exception:
            clients = []
        newest: list[tuple[int, str]] = []
        for win in clients:
            addr = win.get("address")
            if not addr or addr in known_addrs:
                continue
            if not win.get("mapped") or win.get("hidden"):
                continue
            if skip_new_window(win):
                continue
            newest.append((int(win.get("focusHistoryID") or 9999), addr))
        if newest:
            newest.sort(key=lambda t: t[0])
            focus = newest[0][1]
            break
    if tabs:
        apply_tabs_layout(focus_addr=focus)
        return
    if not focus:
        return
    time.sleep(0.12)
    target = f"address:{focus}"
    try:
        dispatch("focuswindow", target)
    except Exception:
        return
    for cmd, arg in (("bringactivetotop", ""), ("alterzorder", "top")):
        try:
            if arg:
                dispatch(cmd, arg)
            else:
                dispatch(cmd)
            break
        except Exception:
            continue


def overview_fuzzel(query: str = "") -> None:
    """Open fuzzel over the zoomed-out grid. Overview stays until Enter or a click.

    While fuzzel is up, Hyprland uses submap ``hdmi-overview-launcher`` so a
    left-click on a grid cell can pick that window and kill fuzzel. Clicks on
    fuzzel itself are redelivered (namespace ``launcher``). Unbound keys go to
    fuzzel. A successful launch closes the overview and focuses the new app.
    """
    text = _sanitize_query(query)
    st = overview_state()
    if not st:
        exe = shutil.which("neuronix-fuzzel") or shutil.which("fuzzel") or "fuzzel"
        cmd = [exe]
        if text:
            cmd.append(f"--search={text}")
        subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if st.get("launcher") or _fuzzel_running():
        for _ in range(30):
            if _fuzzel_running():
                _send_to_fuzzel(text)
                return
            time.sleep(0.04)
        return

    st["launcher"] = True
    write_overview_state(st)
    try:
        dispatch("submap", "hdmi-overview-launcher")
    except Exception:
        try:
            dispatch("submap", "reset")
        except Exception:
            pass

    exe = shutil.which("neuronix-fuzzel") or shutil.which("fuzzel") or "fuzzel"
    # Bottom anchor keeps the launcher off the preview grid so left-click can
    # pick a zoomed-out window (center anchor covered the cards).
    cmd = [
        exe,
        f"--output={hdmi_name()}",
        "--layer=overlay",
        "--anchor=bottom",
        "--keyboard-focus=exclusive",
        "--no-exit-on-keyboard-focus-loss",
    ]
    if text:
        cmd.append(f"--search={text}")

    known_addrs = {
        str(w.get("address"))
        for w in (hypr_json("clients") or [])
        if w.get("address")
    }

    # Must wait here: a daemon thread is killed when this keybind process exits,
    # which aborted fuzzel before it could map.
    rc = 1
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            start_new_session=True,
        )
        rc = int(completed.returncode)
    finally:
        cur = overview_state()
        if not cur:
            return
        cur.pop("launcher", None)
        write_overview_state(cur)
        if rc == 0:
            overview_finish_from_launcher(known_addrs)
        else:
            try:
                dispatch("submap", "hdmi-overview")
            except Exception:
                pass


def window_at_cursor(*, include_hyprbar: bool = True) -> dict | None:
    """Window under the pointer on the overview HDMI workspace only.

    When ``include_hyprbar`` is True (default), the title-bar strip above the
    client rect counts too — needed so × clicks are attributed to that preview.
    """
    try:
        pos = hypr_json("cursorpos")
    except Exception:
        return None
    cx, cy = int(pos.get("x") or 0), int(pos.get("y") or 0)
    mid = int(hdmi_monitor()["id"])
    st = overview_state() or {}
    ws_id = st.get("workspace")
    if ws_id is None:
        active = hypr_json("activeworkspace") or {}
        if active.get("monitor") == hdmi_name():
            ws_id = active.get("id")
    if ws_id is not None:
        ws_id = int(ws_id)

    hits: list[tuple[int, dict]] = []
    for win in hypr_json("clients"):
        if int(win.get("monitor") if win.get("monitor") is not None else -1) != mid:
            continue
        if ws_id is not None:
            if int((win.get("workspace") or {}).get("id") or -1) != ws_id:
                continue
        if not win.get("mapped") or win.get("hidden"):
            continue
        if skip_new_window(win) or is_dialog_like(win) or is_photos_dialog(win):
            continue
        at = win.get("at") or [0, 0]
        size = win.get("size") or [0, 0]
        x, y = int(at[0]), int(at[1])
        w, h = int(size[0] or 0), int(size[1] or 0)
        if w <= 0 or h <= 0:
            continue
        top = y - HYPRBAR_H if include_hyprbar else y
        if x <= cx < x + w and top <= cy < y + h:
            hits.append((w * h, win))
    if not hits:
        return None
    # Prefer the topmost card (lowest focusHistoryID), then the smallest cell
    # so a nested/overlapping pick still lands on the intended preview.
    hits.sort(key=lambda t: (int(t[1].get("focusHistoryID") or 9999), t[0]))
    return hits[0][1]


def _pointer_on_overview_close(win: dict, cx: int | None = None, cy: int | None = None) -> bool:
    """True when the cursor is on the hyprbars × (rightmost title-bar button)."""
    if cx is None or cy is None:
        try:
            pos = hypr_json("cursorpos")
            cx, cy = int(pos.get("x") or 0), int(pos.get("y") or 0)
        except Exception:
            return False
    at = win.get("at") or [0, 0]
    size = win.get("size") or [0, 0]
    x, y = int(at[0]), int(at[1])
    w = int(size[0] or 0)
    if w <= 0:
        return False
    # bar_part_of_window=false → bar sits just above client `at`.
    bar_top = y - HYPRBAR_H
    bar_bot = y + 8  # slight slop into the client under the glyph
    hit_w = max(OVERVIEW_CLOSE_HIT, HYPRBAR_CLOSE_BTN + HYPRBAR_PAD + 12)
    return (x + w - hit_w) <= cx < (x + w + 4) and bar_top - 2 <= cy < bar_bot


def overview_relayout() -> None:
    """Re-pack remaining overview previews after a close/minimize."""
    st = overview_state()
    if not st:
        return
    snaps = list(st.get("windows") or [])
    by_addr = {c.get("address"): c for c in hypr_json("clients")}
    clients: list[dict] = []
    seen: set[str] = set()
    for s in snaps:
        if s.get("minimized"):
            continue
        addr = str(s.get("address") or "")
        if not addr or addr in seen:
            continue
        win = by_addr.get(addr)
        if not win or not win.get("mapped") or win.get("hidden"):
            continue
        clients.append(win)
        seen.add(addr)
    if not clients:
        overview_cancel()
        return
    st["cols"] = _overview_place_grid(clients)
    write_overview_state(st)
    overview_raise(clients[0]["address"])


def overview_close_window(addr: str) -> None:
    """Close one preview from Super overview and reflow the grid (stay in overview).

    Uses ``closewindow`` (xdg soft-close) on that address only. ``killwindow`` /
    ``killactive`` can tear down the whole Wayland client and every other window
    from the same app (e.g. all GtkTerm instances sharing one process).
    """
    st = overview_state()
    if not st:
        return
    target = addr if str(addr).startswith("address:") else f"address:{addr}"
    raw = addr[len("address:") :] if str(addr).startswith("address:") else str(addr)
    before = {c.get("address") for c in hypr_json("clients") if c.get("address")}
    try:
        dispatch("closewindow", target)
    except Exception:
        try:
            # Fallback still targets this window only — never killactive.
            dispatch("closewindow", f"address:{raw}")
        except Exception:
            return
    for _ in range(40):
        if not client_by_address(raw):
            break
        time.sleep(0.03)
    # Only drop this address; leave every other overview card alone.
    snaps = [s for s in (st.get("windows") or []) if str(s.get("address")) != raw]
    # If the app still mapped sibling windows, keep whatever is still alive.
    alive = {c.get("address") for c in hypr_json("clients") if c.get("address")}
    gone = before - alive
    if gone:
        snaps = [s for s in snaps if str(s.get("address")) not in gone]
    st["windows"] = snaps
    write_overview_state(st)
    overview_relayout()


def overview_addrs(st: dict | None = None) -> list[str]:
    st = st if st is not None else overview_state()
    if not st:
        return []
    return [str(w["address"]) for w in (st.get("windows") or []) if w.get("address")]


def overview_raise(addr: str) -> None:
    """Focus + raise within the overview grid (does not restore layouts)."""
    target = f"address:{addr}"
    dispatch("focuswindow", target)
    for cmd, arg in (("bringactivetotop", ""), ("alterzorder", "top")):
        try:
            if arg:
                dispatch(cmd, arg)
            else:
                dispatch(cmd)
            break
        except Exception:
            continue


def overview_cycle(delta: int = 1) -> None:
    """Alt+Tab / Alt+Shift+Tab through overview windows."""
    st = overview_state()
    if not st:
        return
    addrs = overview_addrs(st)
    if not addrs:
        return
    active = hypr_json("activewindow") or {}
    cur = active.get("address")
    try:
        idx = addrs.index(cur) if cur else -1
    except ValueError:
        idx = -1
    idx = (idx + int(delta)) % len(addrs)
    overview_raise(addrs[idx])


def overview_move(dx: int = 0, dy: int = 0) -> None:
    """Arrow-key selection across the overview grid (row-major)."""
    st = overview_state()
    if not st:
        return
    addrs = overview_addrs(st)
    if not addrs:
        return
    cols = max(1, int(st.get("cols") or 1))
    n = len(addrs)
    rows = max(1, math.ceil(n / cols))
    active = hypr_json("activewindow") or {}
    cur = active.get("address")
    try:
        idx = addrs.index(cur) if cur else 0
    except ValueError:
        idx = 0
    row, col = divmod(idx, cols)
    col = max(0, min(cols - 1, col + int(dx)))
    row = max(0, min(rows - 1, row + int(dy)))
    nxt = row * cols + col
    if nxt >= n:
        # Last row may be short — clamp to last cell in that row.
        nxt = n - 1
    overview_raise(addrs[nxt])


def overview_confirm(addr: str | None = None) -> None:
    """Restore layouts and raise the chosen window (click / Enter)."""
    st = overview_state()
    if not st:
        return
    if time.time() < float(st.get("armed_at") or 0):
        return
    addrs = set(overview_addrs(st))
    if not addr:
        active = hypr_json("activewindow") or {}
        addr = active.get("address")
    if not addr or addr not in addrs:
        return
    snaps = list(st.get("windows") or [])
    ws_id = st.get("workspace")
    _set_overview_close_highlight(False)
    write_overview_state(None)
    try:
        dispatch("submap", "reset")
    except Exception:
        pass
    _dismiss_fuzzel()
    if ws_id is not None:
        dispatch("workspace", str(int(ws_id)))
    # Tabs mode: always re-pin every window to the Waybar→hyprtabs slot (same
    # geometry as openwindow) and raise the clicked one — don't restore the
    # pre-overview snapshot, which can leave siblings at zoomed-out sizes.
    if wants_tabs() or hyprtabs_strip_visible():
        apply_tabs_layout(focus_addr=addr)
        return
    restore_overview_windows(
        snaps,
        focus_addr=addr,
        workspace=int(ws_id) if ws_id is not None else None,
    )


def overview_pick() -> None:
    """Click a preview: × closes it in-place; otherwise restore and focus it."""
    st = overview_state()
    if not st:
        return
    if time.time() < float(st.get("armed_at") or 0):
        return
    if _pointer_on_fuzzel():
        # Mouse bind already consumed the event — redeliver to fuzzel.
        _passthrough_click_to_fuzzel()
        return
    addrs = set(overview_addrs(st))
    try:
        pos = hypr_json("cursorpos")
        cx, cy = int(pos.get("x") or 0), int(pos.get("y") or 0)
    except Exception:
        cx = cy = 0
    win = window_at_cursor(include_hyprbar=True)
    addr = win.get("address") if win else None
    if not addr or addr not in addrs:
        # Click may have focused the preview before the bind ran.
        active = hypr_json("activewindow") or {}
        addr = active.get("address")
        win = client_by_address(addr) if addr else None
    if not addr or addr not in addrs:
        return
    if win and _pointer_on_overview_close(win, cx, cy):
        overview_close_window(addr)
        return
    overview_confirm(addr)


def float_hdmi_clients(*, reflow_floating: bool = False, focus: bool = True) -> None:
    """Float leftover tiled windows on the main screen (popups left alone).

    The main screen is HDMI-A-1 when it is connected, otherwise the laptop panel.
    Every tiled window becomes the float-slot size (2/3 on HDMI, 13/15 on
    laptop), centered, and cascaded.
    A lone window sits in the middle. Several windows step down from that center.

    When reflow_floating is True (leaving tabs), already-floating main windows
    are included so full-bleed tab slots cascade instead of staying stacked.
    """
    try:
        mon = hdmi_monitor()
        mid = int(mon["id"])
    except RuntimeError:
        return
    pending: list[dict] = []
    for win in hypr_json("clients"):
        if is_minimized_win(win):
            continue
        if int(win.get("monitor") if win.get("monitor") is not None else -1) != mid:
            continue
        if not win.get("mapped") or win.get("hidden") or skip_new_window(win) or is_gtk_meld(win):
            continue
        if is_utility_float(win) or _is_xdg_popup(win):
            continue
        addr = win.get("address")
        if not addr:
            continue
        if win.get("floating") and not reflow_floating:
            continue
        pending.append(win)
    if not pending:
        return
    for win in pending:
        target = f"address:{win['address']}"
        try:
            fs = win.get("fullscreen")
            if fs not in (None, False, 0, "0"):
                if focus:
                    dispatch("focuswindow", target)
                dispatch("fullscreen", "0")
        except Exception:
            pass

    def _history(win: dict) -> int:
        try:
            return int(win.get("focusHistoryID"))
        except (TypeError, ValueError):
            return 10_000

    # Lower focusHistoryID is more recent. The last card is the front of the pile.
    ordered = sorted(pending, key=_history, reverse=True)
    try:
        layers = hypr_json("layers")
        usable = usable_rect(mon, layers)
    except Exception:
        return
    ux, uy, uw, uh = usable
    if has_hdmi():
        num, den = 2, 3
    else:
        num, den = LAPTOP_FLOAT_FRAC
    sw = max(200, uw * num // den)
    sh = max(200, uh * num // den)
    slot = (ux + (uw - sw) // 2, uy + (uh - sh) // 2, sw, sh)
    positions = _cascade_positions(len(ordered), slot, usable)
    front = str(ordered[-1].get("address") or "")
    for _ in range(3):
        _apply_card_stack(ordered, positions, sw, sh, front, focus=focus)
        time.sleep(0.06)
        drifted = False
        for item, (px, py) in zip(ordered, positions):
            again = client_by_address(str(item.get("address") or ""))
            if not again:
                continue
            size = again.get("size") or [0, 0]
            at = again.get("at") or [0, 0]
            if (
                abs(int(size[0] or 0) - sw) > 24
                or abs(int(size[1] or 0) - sh) > 24
                or abs(int(at[0]) - px) > 24
                or abs(int(at[1]) - py) > 24
            ):
                drifted = True
                break
        if not drifted:
            break


def skip_dp_tile(win: dict) -> bool:
    """Don't force-tile popups, dialogs, or specials on the DP portraits."""
    cls = (win.get("class") or "").lower()
    ws = str((win.get("workspace") or {}).get("name") or "")
    if ws.startswith("special"):
        return True
    tags = _window_tags(win)
    if "waybar-popover" in tags or "sidepanel" in tags or "settings-host" in tags:
        return True
    if any(s in cls for s in SKIP_CLASS_SUBSTR):
        return True
    if _class_is_main_browser(cls):
        return True
    xdg = str(win.get("xdgTag") or win.get("xdg_tag") or "").lower()
    if any(s in xdg for s in ("popup", "menu", "dropdown", "tooltip")):
        return True
    if is_dialog_like(win) or is_photos_dialog(win):
        return True
    return False


def on_laptop_panel(win: dict, monitors: list[dict] | None = None) -> bool:
    """Built-in panel: tiled dwindle only, never the HDMI float grid."""
    monitors = monitors if monitors is not None else hypr_json("monitors")
    if window_monitor_name(win, monitors) == "eDP-1":
        return True
    mid = win.get("monitor")
    for mon in monitors:
        if mon.get("id") == mid and "LG Display 0x07C0" in str(mon.get("description") or ""):
            return True
    return False


def tile_laptop_clients() -> None:
    """eDP-1 stays in the Hyprland tile grid (menus/popups left alone)."""
    monitors = hypr_json("monitors")
    for win in hypr_json("clients"):
        if not on_laptop_panel(win, monitors):
            continue
        if not win.get("mapped") or win.get("hidden") or _is_xdg_popup(win) or is_gtk_meld(win):
            continue
        addr = win.get("address")
        if not addr or not win.get("floating"):
            continue
        try:
            tile_address(addr)
        except Exception:
            pass


def tile_dp_clients() -> None:
    """Keep DP-3 / DP-4 tiled (popups and dialogs left alone)."""
    monitors = hypr_json("monitors")
    for win in hypr_json("clients"):
        if not on_dp(win, monitors):
            continue
        if not win.get("mapped") or win.get("hidden") or skip_dp_tile(win) or is_gtk_meld(win):
            continue
        addr = win.get("address")
        if not addr or not win.get("floating"):
            continue
        try:
            dispatch("focuswindow", f"address:{addr}")
            dispatch("settiled")
        except Exception:
            pass


def _apply_special_or_bottom(addr: str, win: dict, focus: bool) -> bool:
    if is_photos_dialog(win) or is_dialog_like(win):
        center_dialog(addr)
        return True
    if is_photos_media(win):
        place_photos_grid(addr, focus=focus)
        return True
    if is_gtk_meld(win):
        force_meld_fullscreen(addr)
        return True
    return False



def _is_utility_hint(cls: str, title: str = "") -> bool:
    """Settings, Theme Editor, Power Manager, and btop. Never tiled or slotted."""
    cls = (cls or "").lower()
    title = (title or "").strip().lower()
    if any(
        s in cls
        for s in (
            "xfce4-power",
            "hypr-settings",
            "gtkthemeeditor",
            "gtk-theme",
            "gtkcalc",
            "galculator",
            "org.neuronix.btop",
        )
    ):
        return True
    return title in ("settings", "power manager", "theme editor", "calculator", "btop")


def is_utility_float(win: dict) -> bool:
    return _is_utility_hint(str(win.get("class") or ""), str(win.get("title") or "")) or _is_utility_hint(
        "", str(win.get("initialTitle") or "")
    )


def settle_utility(addr: str) -> None:
    """Float and center a utility window. The theme editor is five-sixths of the screen."""
    target, raw = address_target(addr)
    deadline = time.time() + 1.5
    prev: tuple[int, int] | None = None
    win = None
    while time.time() < deadline:
        win = client_by_address(raw)
        if not win or not win.get("mapped"):
            time.sleep(0.05)
            continue
        size = win.get("size") or [0, 0]
        cur = (int(size[0] or 0), int(size[1] or 0))
        if cur[0] >= 80 and cur[1] >= 80 and cur == prev:
            break
        prev = cur
        time.sleep(0.12)
    if not win or not win.get("mapped"):
        return
    try:
        if not win.get("floating"):
            dispatch("setfloating", target)
            time.sleep(0.05)
            win = client_by_address(raw) or win
    except Exception:
        return
    size = win.get("size") or [0, 0]
    w, h = int(size[0] or 0), int(size[1] or 0)
    if w < 80 or h < 80:
        return
    cls = (win.get("class") or "").lower()
    monitors = hypr_json("monitors")
    mon = None
    for item in monitors:
        if item.get("id") == win.get("monitor"):
            mon = item
            break
    if mon is None:
        try:
            mon = hdmi_monitor(monitors)
        except RuntimeError:
            return
    if any(s in cls for s in ("gtkthemeeditor", "gtk-theme")):
        mw, mh = int(mon["width"]), int(mon["height"])
        tw, th = mw * 5 // 6, mh * 5 // 6
        if tw >= 200 and th >= 200:
            x = int(mon["x"]) + (mw - tw) // 2
            y = int(mon["y"]) + (mh - th) // 2
            try:
                dispatch("resizewindowpixel", f"exact {tw} {th},{target}")
                dispatch("movewindowpixel", f"exact {x} {y},{target}")
            except Exception:
                return
        return
    if any(s in cls for s in ("gtkcalc", "galculator")) and (w > 520 or h > 680):
        w, h = 360, 520
        try:
            dispatch("resizewindowpixel", f"exact {w} {h},{target}")
            time.sleep(0.05)
        except Exception:
            return
    if "org.neuronix.btop" in cls and (w > 1100 or h > 800):
        w, h = 960, 640
        try:
            dispatch("resizewindowpixel", f"exact {w} {h},{target}")
            time.sleep(0.05)
        except Exception:
            return
    monitors = hypr_json("monitors")
    mon = None
    for item in monitors:
        if item.get("id") == win.get("monitor"):
            mon = item
            break
    if mon is None:
        try:
            mon = hdmi_monitor(monitors)
        except RuntimeError:
            return
    try:
        ux, uy, uw, uh = usable_rect(mon, hypr_json("layers"))
    except Exception:
        ux, uy = int(mon["x"]), int(mon["y"])
        uw, uh = int(mon["width"]), int(mon["height"])
    x = ux + max(0, (uw - w) // 2)
    y = uy + max(0, (uh - h) // 2)
    try:
        dispatch("movewindowpixel", f"exact {x} {y},{target}")
    except Exception:
        return


def place_new_window(addr: str, hint_class: str = "", hint_title: str = "") -> None:
    addr = addr if addr.startswith("0x") else f"0x{addr}"
    if class_is_meld(hint_class):
        force_meld_fullscreen(addr)
        return
    if _is_utility_hint(hint_class, hint_title):
        settle_utility(addr)
        return
    if overview_state():
        overview_adopt_window(addr)
        return
    win = None
    for _ in range(30):
        win = client_by_address(addr)
        if win and win.get("mapped") and (win.get("class") or hint_class):
            break
        time.sleep(0.02)
    if not win:
        return
    if is_utility_float(win) or _is_utility_hint(hint_class, hint_title):
        settle_utility(addr)
        return
    if is_gtk_meld(win):
        force_meld_fullscreen(addr)
        return
    if wants_tabs() or hyprtabs_strip_visible():
        if on_dp(win) and not _class_is_main_browser(win.get("class") or ""):
            if skip_dp_tile(win):
                return
            if win.get("floating"):
                try:
                    dispatch("focuswindow", f"address:{addr}")
                    dispatch("settiled")
                except Exception:
                    pass
            return
        if skip_new_window(win):
            return
        # Only true dialogs/pickers center. New apps often map small first —
        # those must still become full-bleed tabs (not center_dialog).
        if is_dialog_like(win) or is_photos_dialog(win) or is_tabs_dialog(win):
            center_dialog(addr)
            try:
                dispatch("alterzorder", f"top,address:{addr}")
            except Exception:
                pass
            return
        place_tab_window(addr, focus=True, raise_over_siblings=True)
        return
    # Laptop panel: only force-tile when layout-mode is tile. In float mode the
    # built-in screen is the "main" float desk (hdmi_monitor falls back to eDP),
    # so new windows must join the cascade — otherwise they map as a full-bleed
    # tiled client *under* the float pile and cannot be clicked to focus.
    if wants_tile_default() and (on_laptop_panel(win) or not on_dp(win)):
        if not _is_xdg_popup(win) and win.get("floating"):
            try:
                tile_address(addr)
            except Exception:
                pass
        return
    if on_dp(win) and not _class_is_main_browser(win.get("class") or ""):
        if skip_dp_tile(win):
            return
        if win.get("floating"):
            try:
                dispatch("focuswindow", f"address:{addr}")
                dispatch("settiled")
            except Exception:
                pass
        return
    if skip_new_window(win):
        return
    if _apply_special_or_bottom(addr, win, focus=True):
        return
    align, row = _slot_for_new_window(addr)
    frac = LAPTOP_FLOAT_FRAC if not has_hdmi() else (1, 3)
    x, y, w, h = place_float(addr, align, focus=True, row=row, width_frac=frac)
    passes = 10 if _class_is_chromium((win.get("class") or "")) else 4
    for _ in range(passes):
        time.sleep(0.12)
        again = client_by_address(addr)
        if not again or skip_new_window(again):
            return
        ensure_floating(f"address:{addr}", again)
        if _apply_special_or_bottom(addr, again, focus=False):
            return
        at = again.get("at") or [0, 0]
        size = again.get("size") or [0, 0]
        if (
            abs(int(at[0]) - x) <= 32
            and abs(int(at[1]) - y) <= 32
            and abs(int(size[0] or 0) - w) <= 48
            and abs(int(size[1] or 0) - h) <= 48
        ):
            break
        _pin_geometry(addr, x, y, w, h)
    # Chrome restores last-session size after map (often full HDMI), which
    # clips hyprbars off the top of the monitor. Quiet-pin only while it is
    # still focused and still full-bleed — never steal the pointer back.
    if _class_is_chromium(win.get("class") or ""):

        def _keep_chrome_slot(
            a: str = addr, x0: int = x, y0: int = y, w0: int = w, h0: int = h
        ) -> None:
            try:
                mon_h = int(hdmi_monitor()["height"])
            except RuntimeError:
                mon_h = 2160
            end = time.time() + 4.0
            while time.time() < end:
                time.sleep(0.4)
                again = client_by_address(a)
                if not again or not again.get("floating"):
                    return
                active = hypr_json("activewindow") or {}
                if (active.get("address") or "") != (again.get("address") or ""):
                    return
                size = again.get("size") or [0, 0]
                at = again.get("at") or [0, 0]
                sh = int(size[1] or 0)
                if sh < mon_h - 80:
                    if abs(int(at[0]) - x0) > 96 or abs(int(at[1]) - y0) > 96:
                        return
                    continue
                try:
                    _pin_geometry(a, x0, y0, w0, h0)
                except Exception:
                    return

        threading.Thread(target=_keep_chrome_slot, daemon=True).start()


def socket2_path() -> str:
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    path = os.path.join(runtime, "hypr", sig, ".socket2.sock")
    if os.path.exists(path):
        return path
    base = os.path.join(runtime, "hypr")
    if os.path.isdir(base):
        for root, _dirs, files in os.walk(base):
            if ".socket2.sock" in files:
                return os.path.join(root, ".socket2.sock")
    raise RuntimeError(f"hypr socket2 not found ({path})")


def watch() -> None:
    # One-shot: bring back anything left on special:minimized (feature removed).
    restore_minimized_main_clients()
    apply_layout_mode()
    # Only re-tile the built-in panel when layout-mode is tile. Float mode on a
    # laptop without HDMI uses eDP as the main float desk — do not yank those.
    if wants_tile_default():
        tile_laptop_clients()
    path = socket2_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    buf = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode("utf-8", "replace")
            if text.startswith("openwindow>>"):
                payload = text.split(">>", 1)[1]
                fields = payload.split(",")
                addr = fields[0].strip() if fields else ""
                hint_class = fields[2].strip() if len(fields) > 2 else ""
                hint_title = ",".join(fields[3:]).strip() if len(fields) > 3 else ""
                if not addr:
                    continue

                def _run(a: str = addr, c: str = hint_class, t: str = hint_title) -> None:
                    place_new_window(a, c, t)

                threading.Thread(target=_run, daemon=True).start()
                continue

            if text.startswith("changefloatingmode>>"):
                payload = text.split(">>", 1)[1]
                parts = payload.split(",")
                addr = parts[0].strip()
                floating = parts[1].strip() if len(parts) > 1 else "1"
                if addr and floating in ("1", "true") and wants_tile_default():

                    def _retile(a: str = addr) -> None:
                        try:
                            time.sleep(0.02)
                            a = a if a.startswith("0x") else f"0x{a}"
                            win = client_by_address(a)
                            if (
                                not win
                                or _is_xdg_popup(win)
                                or is_utility_float(win)
                                or is_gtk_meld(win)
                                or not (
                                    on_laptop_panel(win)
                                    or (wants_tile_default() and not on_dp(win))
                                )
                            ):
                                return
                            if win.get("floating"):
                                tile_address(a)
                        except Exception:
                            pass

                    threading.Thread(target=_retile, daemon=True).start()
                continue

            if text.startswith("windowtitle>>"):
                payload = text.split(">>", 1)[1]
                addr = payload.split(",", 1)[0].strip()
                if not addr:
                    continue

                def _title(a: str = addr) -> None:
                    try:
                        time.sleep(0.02)
                        a = a if a.startswith("0x") else f"0x{a}"
                        win = client_by_address(a)
                        if not win or skip_new_window(win):
                            return
                        if is_gtk_meld(win):
                            force_meld_fullscreen(a)
                            return
                        # Tabs: rescue About/Preferences that got full-bleed pinned
                        # before the real title arrived (title-only — not size).
                        if wants_tabs() or hyprtabs_strip_visible():
                            if is_dialog_like(win) or is_tabs_dialog(win):
                                center_dialog(a)
                                try:
                                    dispatch("alterzorder", f"top,address:{a}")
                                except Exception:
                                    pass
                            return
                        # Tile-mode laptop/DP: leave alone. Float-mode laptop
                        # must still allow special/media placement below.
                        if wants_tile_default() and (
                            on_dp(win) or on_laptop_panel(win)
                        ):
                            return
                        if on_dp(win):
                            return
                        _apply_special_or_bottom(a, win, focus=False)
                    except Exception:
                        pass

                threading.Thread(target=_title, daemon=True).start()


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "bottom"
    if action == "watch":
        watch()
        return
    if action == "layout-status":
        layout_status()
        return
    if action == "layout-toggle":
        layout_toggle()
        return
    if action == "layout-set":
        if len(sys.argv) < 3 or sys.argv[2] not in ("float", "tile", "tabs"):
            sys.exit("usage: layout-set float|tile|tabs")
        layout_set(sys.argv[2])
        return
    if action == "layout-apply":
        apply_layout_mode()
        return
    if action in ("tab-select", "tabs-focus"):
        # hyprtabs plugin calls this after a capsule click so every sibling is
        # pinned with hyprctl resize/move. Must not steal the pointer — the
        # plugin already focused the tab and left the cursor on the capsule.
        if len(sys.argv) < 3:
            sys.exit("usage: tab-select ADDRESS")
        if wants_tabs() or hyprtabs_strip_visible():
            pin_tabs_after_click(sys.argv[2])
        return
    if action == "on-open":
        if len(sys.argv) < 3:
            sys.exit("usage: on-open ADDRESS")
        place_new_window(sys.argv[2])
        return
    if action in ("tile-all", "tile-hdmi-all", "grid"):
        grid_hdmi(enter_overview=False)
        return
    if action in ("overview", "overview-enter", "super-overview"):
        grid_hdmi(enter_overview=True)
        return
    if action in ("overview-pick", "overview-click"):
        overview_pick()
        return
    if action in ("overview-confirm", "overview-enter-key"):
        overview_confirm()
        return
    if action in ("overview-next", "overview-tab"):
        overview_cycle(+1)
        return
    if action in ("overview-prev", "overview-tab-back"):
        overview_cycle(-1)
        return
    if action in ("overview-left",):
        overview_move(-1, 0)
        return
    if action in ("overview-right",):
        overview_move(+1, 0)
        return
    if action in ("overview-up",):
        overview_move(0, -1)
        return
    if action in ("overview-down",):
        overview_move(0, +1)
        return
    # Escape binds use overview-cancel / overview-escape: first closes fuzzel,
    # second closes the grid. Super-again / pick / confirm call overview_cancel()
    # directly in-process (full exit).
    if action in ("overview-escape", "overview-cancel"):
        overview_escape()
        return
    if action in ("overview-fuzzel", "overview-type", "overview-search"):
        overview_fuzzel(sys.argv[2] if len(sys.argv) > 2 else "")
        return

    win = hypr_json("activewindow")
    if not win or not win.get("address"):
        sys.exit(0)
    addr = win["address"]

    if action in ("dp-left", "mon-left"):
        tile_to(DP_LEFT, addr)
        return
    if action in ("dp-right", "mon-right"):
        tile_to(DP_RIGHT, addr)
        return
    if action in ("tile", "mon-center", "mon-hdmi", "hdmi-full"):
        place_hdmi_full(addr)
        return

    slots = {
        "bottom": ("bottom", "center"),
        "float": ("bottom", "center"),
        "center": ("bottom", "center"),
        "left": ("bottom", "left"),
        "right": ("bottom", "right"),
        "middle": ("middle", "center"),
        "middle-center": ("middle", "center"),
        "middle-left": ("middle", "left"),
        "middle-right": ("middle", "right"),
        "top": ("top", "center"),
        "top-center": ("top", "center"),
        "top-left": ("top", "left"),
        "top-right": ("top", "right"),
    }
    wide = action.startswith("wide-")
    if wide:
        action = action[len("wide-") :]
    slot = slots.get(action)
    if slot is None:
        sys.exit(
            f"usage: {sys.argv[0]} [bottom|left|right|middle|middle-left|middle-right|"
            f"top|top-left|top-right|wide-left|wide-bottom|wide-right|"
            f"hdmi-full|grid|overview|overview-pick|overview-cancel|"
            f"overview-fuzzel|"
            f"dp-left|dp-right|watch]"
        )
    row, align = slot
    # Laptop float desk: number-row / numpad slots are 2/3 + 30% (13/15).
    # On HDMI, plain keys stay ~1/3 (with bump); Shift / wide-* stay 2/3.
    if not has_hdmi():
        frac = LAPTOP_FLOAT_FRAC
    elif wide:
        frac = (2, 3)
    else:
        frac = (1, 3)
    place_float(addr, align, row=row, width_frac=frac)


if __name__ == "__main__":
    main()
