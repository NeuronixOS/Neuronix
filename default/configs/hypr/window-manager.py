#!/usr/bin/env python3
"""Park HDMI windows as floats; tile onto the DP portraits.

New windows land in the HDMI bottom-center slot. Ctrl+Super+Alt parks a 3×3
HDMI grid, fills HDMI, or tiles onto DP-3 / DP-4. A second (or third) window
in the same slot cascades slightly so title bars of the ones behind stay
visible. gtk-photos viewers pack bottom-left across, then up, on HDMI;
gtk-meld diffs fill HDMI.
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

HDMI = "HDMI-A-1"
DP_LEFT = "DP-3"
DP_RIGHT = "DP-4"
GAP = 18
CASCADE_STEP = 40
CASCADE_MAX = 6
CASCADE_SIZE_SLOP = 96
CASCADE_POS_SLOP = 24

SKIP_CLASS_SUBSTR = (
    "zenity",
    "polkit",
    "neuronix-choice",
    "xdg-desktop-portal",
    "pavucontrol",
    "nm-connection-editor",
    "blueman",
    "galculator",
    "gtkcalc",
    "xfce4-power",
    "nwg-bar",
    "fuzzel",
    "windowswitch",
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
    "about ",
    "authenticate",
    "destination",
    "moving files",
)

PHOTOS_CLASS = "org.neuronix.gtkphotos"
PHOTOS_MEDIA_CLASS = "gtk-photos-media"
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


def monitor_by_name(name: str, monitors: list[dict] | None = None) -> dict:
    monitors = monitors if monitors is not None else hypr_json("monitors")
    for mon in monitors:
        if mon.get("name") == name:
            return mon
    raise RuntimeError(f"monitor {name} not found")


def hdmi_monitor(monitors: list[dict] | None = None) -> dict:
    return monitor_by_name(HDMI, monitors)


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
    x = mx + left + GAP
    y = strip_top + GAP
    w = mw - left - right - 2 * GAP
    h = strip_bottom - y - GAP
    if w < 200 or h < 200:
        raise RuntimeError(f"{name} is too small to place a window")
    return x, y, w, h


def hdmi_slot_rect(mon: dict, layers: dict, align: str, row: str) -> tuple[int, int, int, int]:
    """Float slot on HDMI: ~5/12 × 1/2 of the screen."""
    mx, my = int(mon["x"]), int(mon["y"])
    mw, mh = int(mon["width"]), int(mon["height"])
    left, top_res, right, _bottom = [int(v) for v in mon["reserved"]]
    full_top = my + max(int(top_res), 0)
    full_bottom = my + mh
    full_top, full_bottom = waybar_cut(layers, HDMI, full_top, full_bottom)
    usable_w = mw - left - right
    usable_h = full_bottom - full_top
    w = usable_w * 5 // 12
    h = usable_h // 2
    if w < 200 or h < 200:
        raise RuntimeError("HDMI is too small to place a 1/3 × 1/2 float")
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


def _nine_slot_rects(mon: dict, layers: dict) -> list[tuple[int, int, int, int]]:
    return [
        hdmi_slot_rect(mon, layers, align, row)
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
    slot: tuple[int, int, int, int], mon: dict, layers: dict
) -> tuple[str, str] | None:
    sx, sy = slot[0], slot[1]
    for row in ("top", "middle", "bottom"):
        for align in ("left", "center", "right"):
            rect = hdmi_slot_rect(mon, layers, align, row)
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
) -> list[dict]:
    except_addr = except_addr if except_addr.startswith("0x") else f"0x{except_addr}"
    hdmi_id = mon.get("id")
    all_slots = _nine_slot_rects(mon, layers)
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
    compact = (w <= 720 and h <= 640) or (w * h <= 280_000)
    floating = bool(win.get("floating"))
    if _class_is_chromium(cls) and floating and compact:
        return True
    if floating and compact:
        return True
    if compact and w <= 480 and h <= 480:
        return True
    return False


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


def skip_new_window(win: dict) -> bool:
    cls = (win.get("class") or "").lower()
    ws = str((win.get("workspace") or {}).get("name") or "")
    if ws.startswith("special"):
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


def is_photos_media(win: dict) -> bool:
    """True only for image/video viewer windows, not the organizer or dialogs."""
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
    if _title_is_photos_media(title) or _title_is_photos_media(initial):
        return True
    pid = int(win.get("pid") or 0)
    if pid and any(marker in _pid_cmdlines(pid) for marker in PHOTOS_CMDLINE_MARKERS):
        return True
    if _class_is_chromium(cls) or _class_is_chromium(initial_cls):
        if pid and pid in _photos_chromium_tree_pids():
            return True
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
    target, raw = address_target(addr)
    win = client_by_address(raw)
    if not win:
        return
    dispatch("focuswindow", target)
    ensure_floating(target, win)
    dispatch("centerwindow")


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
    dispatch("movewindow", f"mon:{HDMI}")
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
    place_at(addr, x, y, w, h, HDMI, focus)


def window_monitor_name(win: dict, monitors: list[dict] | None = None) -> str:
    mid = win.get("monitor")
    for mon in monitors if monitors is not None else hypr_json("monitors"):
        if mon.get("id") == mid:
            return str(mon.get("name") or "")
    return ""


def on_dp(win: dict, monitors: list[dict] | None = None) -> bool:
    return window_monitor_name(win, monitors) in (DP_LEFT, DP_RIGHT)


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
) -> tuple[int, int, int, int]:
    target, raw = address_target(addr)
    win = client_by_address(raw)
    if not win:
        return 0, 0, 0, 0
    mon = hdmi_monitor()
    layers = hypr_json("layers")
    slot = hdmi_slot_rect(mon, layers, align, row)
    usable = usable_rect(mon, layers)
    sx, sy, w, h = slot
    others = _slot_pile_windows(raw, slot, win, mon, layers)
    ordered = others + [win]
    positions = _cascade_positions(len(ordered), slot, usable)
    x, y = positions[-1]
    move_mon = HDMI if win.get("monitor") != mon.get("id") else None
    if move_mon:
        if focus:
            dispatch("focuswindow", target)
        dispatch("movewindow", f"mon:{move_mon}")
        time.sleep(0.04)
    _apply_card_stack(ordered, positions, w, h, raw)
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
    """
    if n < 1:
        return 1, 1, max(200, aw // 2), max(120, ah // 3), ox, oy

    # Prefer ~16:9 landscape cards.
    aspect = 16.0 / 9.0
    best: tuple[float, int, int, int, int] | None = None
    # Try column counts that keep a reasonable grid.
    for cols in range(1, n + 1):
        rows = max(1, math.ceil(n / cols))
        # Max cell that fits this grid in the usable area.
        max_w = (aw - GAP * max(0, cols - 1)) // cols
        max_h = (ah - GAP * max(0, rows - 1)) // rows
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
        cell_h = max(100, min(ah // max(1, rows) - GAP, 400))
        cell_w = min(aw // max(1, cols) - GAP, int(cell_h * aspect))
        if cell_w <= cell_h:
            cell_w = cell_h + 40
    else:
        _score, cols, rows, cell_w, cell_h = best

    grid_w = cols * cell_w + GAP * max(0, cols - 1)
    grid_h = rows * cell_h + GAP * max(0, rows - 1)
    origin_x = ox + max(0, (aw - grid_w) // 2)
    origin_y = oy + max(0, (ah - grid_h) // 2)
    return cols, rows, cell_w, cell_h, origin_x, origin_y


def _overview_place_grid(clients: list[dict]) -> int:
    """Shrink clients into centered landscape overview cells. Returns column count."""
    if not clients:
        return 1
    mon = hdmi_monitor()
    ox, oy, aw, ah = usable_rect(mon, hypr_json("layers"))
    n = len(clients)
    cols, _rows, cell_w, cell_h, grid_ox, grid_oy = overview_landscape_cells(
        n, ox, oy, aw, ah
    )
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
    return cols


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
            dispatch("movewindow", f"mon:{HDMI}")
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
    """
    if enter_overview and overview_state():
        # Super again: leave overview, restore previous layouts.
        overview_cancel()
        return

    mon = hdmi_monitor()
    mid = int(mon["id"])
    active_ws = hypr_json("activeworkspace") or {}
    if active_ws.get("monitor") != HDMI:
        aws = mon.get("activeWorkspace") or {}
        ws_id = int(aws.get("id") or 1)
        dispatch("focusmonitor", HDMI)
        dispatch("workspace", str(ws_id))
        active_ws = hypr_json("activeworkspace") or {}
    ws_id = int(active_ws.get("id") or 1)

    clients = []
    for win in hypr_json("clients"):
        if int(win.get("monitor") if win.get("monitor") is not None else -1) != mid:
            continue
        wsid = int((win.get("workspace") or {}).get("id") or -1)
        if wsid != ws_id:
            continue
        if not win.get("mapped") or win.get("hidden"):
            continue
        if skip_new_window(win) or is_dialog_like(win) or is_photos_dialog(win):
            continue
        if not win.get("address"):
            continue
        clients.append(win)
    if not clients:
        return

    clients.sort(
        key=lambda w: (
            int((w.get("at") or [0, 0])[1]),
            int((w.get("at") or [0, 0])[0]),
            w.get("address") or "",
        )
    )
    dispatch("focusmonitor", HDMI)
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
                }
            )
        write_overview_state(
            {
                "active": True,
                "workspace": ws_id,
                "windows": snaps,
                "cols": 1,
                "armed_at": time.time() + 0.35,
            }
        )
        cols = _overview_place_grid(clients)
        st = overview_state() or {}
        st["cols"] = cols
        write_overview_state(st)
        overview_raise(clients[0]["address"])
        try:
            dispatch("submap", "hdmi-overview")
        except Exception:
            pass
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


def restore_overview_windows(snaps: list[dict], focus_addr: str | None = None) -> None:
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


def overview_cancel() -> None:
    st = overview_state()
    write_overview_state(None)
    try:
        dispatch("submap", "reset")
    except Exception:
        pass
    if st and st.get("windows"):
        restore_overview_windows(list(st["windows"]))


def _fuzzel_running() -> bool:
    try:
        subprocess.run(
            ["pgrep", "-x", "fuzzel"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


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
    """True when the cursor is on the fuzzel overlay (do not treat as a window pick)."""
    if not _fuzzel_running():
        return False
    try:
        pos = hypr_json("cursorpos")
        cx, cy = int(pos.get("x") or 0), int(pos.get("y") or 0)
    except Exception:
        return True
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
                    if "fuzzel" not in ns:
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


def overview_fuzzel(query: str = "") -> None:
    """Open fuzzel over the zoomed-out grid. Overview stays until Enter or a click."""
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
        dispatch("submap", "reset")
    except Exception:
        pass

    exe = shutil.which("neuronix-fuzzel") or shutil.which("fuzzel") or "fuzzel"
    cmd = [
        exe,
        f"--output={HDMI}",
        "--layer=overlay",
        "--keyboard-focus=exclusive",
        "--no-exit-on-keyboard-focus-loss",
    ]
    if text:
        cmd.append(f"--search={text}")

    # Must wait here: a daemon thread is killed when this keybind process exits,
    # which aborted fuzzel before it could map.
    try:
        subprocess.run(
            cmd,
            check=False,
            start_new_session=True,
        )
    finally:
        cur = overview_state()
        if not cur:
            return
        cur.pop("launcher", None)
        write_overview_state(cur)
        try:
            dispatch("submap", "hdmi-overview")
        except Exception:
            pass


def window_at_cursor() -> dict | None:
    """Window under the pointer on the overview HDMI workspace only."""
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
        if active.get("monitor") == HDMI:
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
        if x <= cx < x + w and y <= cy < y + h:
            hits.append((w * h, win))
    if not hits:
        return None
    hits.sort(key=lambda t: (t[0], int(t[1].get("focusHistoryID") or 9999)))
    return hits[0][1]


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
    write_overview_state(None)
    try:
        dispatch("submap", "reset")
    except Exception:
        pass
    if ws_id is not None:
        dispatch("workspace", str(int(ws_id)))
    restore_overview_windows(snaps, focus_addr=addr)


def overview_pick() -> None:
    """Click a grid cell: restore everyone, raise the clicked window."""
    st = overview_state()
    if not st:
        return
    if time.time() < float(st.get("armed_at") or 0):
        return
    win = window_at_cursor()
    if not win or not win.get("address"):
        return
    ws_id = st.get("workspace")
    if ws_id is not None:
        if int((win.get("workspace") or {}).get("id") or -1) != int(ws_id):
            return
    overview_confirm(win["address"])


def float_hdmi_clients() -> None:
    """Float leftover tiled windows on HDMI (popups left alone)."""
    try:
        mid = int(hdmi_monitor()["id"])
    except RuntimeError:
        return
    for win in hypr_json("clients"):
        if int(win.get("monitor") if win.get("monitor") is not None else -1) != mid:
            continue
        if not win.get("mapped") or win.get("hidden") or skip_new_window(win):
            continue
        addr = win.get("address")
        if not addr or win.get("floating"):
            continue
        try:
            dispatch("setfloating", f"address:{addr}")
        except Exception:
            pass


def skip_dp_tile(win: dict) -> bool:
    """Don't force-tile popups, dialogs, or specials on the DP portraits."""
    cls = (win.get("class") or "").lower()
    ws = str((win.get("workspace") or {}).get("name") or "")
    if ws.startswith("special"):
        return True
    if any(s in cls for s in SKIP_CLASS_SUBSTR):
        return True
    xdg = str(win.get("xdgTag") or win.get("xdg_tag") or "").lower()
    if any(s in xdg for s in ("popup", "menu", "dropdown", "tooltip")):
        return True
    if is_dialog_like(win) or is_photos_dialog(win):
        return True
    return False


def tile_dp_clients() -> None:
    """Keep DP-3 / DP-4 tiled (popups and dialogs left alone)."""
    monitors = hypr_json("monitors")
    for win in hypr_json("clients"):
        if not on_dp(win, monitors):
            continue
        if not win.get("mapped") or win.get("hidden") or skip_dp_tile(win):
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
    if is_gtk_meld_diff(win):
        place_hdmi_full(addr, focus=focus)
        return True
    return False


def place_new_window(addr: str) -> None:
    addr = addr if addr.startswith("0x") else f"0x{addr}"
    if overview_state():
        overview_adopt_window(addr)
        return
    win = None
    for _ in range(20):
        win = client_by_address(addr)
        if win and win.get("mapped"):
            break
        time.sleep(0.02)
    if not win:
        return
    if on_dp(win):
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
    x, y, w, h = place_float(addr, align, focus=True, row=row)
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
            return
        x, y, w, h = place_float(addr, align, focus=False, row=row)


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
    float_hdmi_clients()
    tile_dp_clients()
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
                addr = payload.split(",", 1)[0].strip()
                if not addr:
                    continue

                def _run(a: str = addr) -> None:
                    try:
                        place_new_window(a)
                    except Exception:
                        pass

                threading.Thread(target=_run, daemon=True).start()
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
                        if not win or skip_new_window(win) or on_dp(win):
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
    if action in ("overview-cancel", "overview-escape"):
        overview_cancel()
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
    slot = slots.get(action)
    if slot is None:
        sys.exit(
            f"usage: {sys.argv[0]} [bottom|left|right|middle|middle-left|middle-right|"
            f"top|top-left|top-right|hdmi-full|grid|overview|overview-pick|overview-cancel|"
            f"overview-fuzzel|"
            f"dp-left|dp-right|watch]"
        )
    row, align = slot
    place_float(addr, align, row=row)


if __name__ == "__main__":
    main()
