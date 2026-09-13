#!/usr/bin/env python3
"""Shared Neuronix GTK choice dialog — spacious action cards (not a packed zenity table)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell, Pango  # noqa: E402

CSS_TEMPLATE = """
window.neuronix-choice {{
  background-color: {surface};
  border: 1px solid {border};
  border-radius: 12px;
  color: {fg};
}}
box.neuronix-root,
box.neuronix-scroll-wrap,
eventbox.neuronix-scroll-wrap {{
  background-color: {surface};
}}
scrolledwindow.neuronix-scroll,
scrolledwindow.neuronix-scroll > *,
scrolledwindow.neuronix-scroll viewport,
scrolledwindow.neuronix-scroll undershoot,
scrolledwindow.neuronix-scroll overshoot {{
  background-color: {surface};
  border: none;
  box-shadow: none;
  outline: none;
  border-width: 0;
}}
label.neuronix-title {{
  color: {fg};
  font-size: 22px;
  font-weight: 700;
}}
label.neuronix-subtitle {{
  color: {muted};
  font-size: 13px;
}}
scrolledwindow, viewport, box.neuronix-list, frame {{
  background-color: {surface};
  border: none;
  box-shadow: none;
  outline: none;
  border-width: 0;
  border-style: none;
  border-radius: 0;
}}
scrolledwindow > viewport,
scrolledwindow > widget,
scrolledwindow > scrollbar {{
  border: none;
  background-color: {surface};
}}
/* Match edge etch to window bg */
scrolledwindow overshoot.top,
scrolledwindow overshoot.bottom,
scrolledwindow undershoot.top,
scrolledwindow undershoot.bottom,
scrolledwindow overshoot,
scrolledwindow undershoot {{
  background-color: {surface};
  background-image: none;
  border: none;
  box-shadow: none;
  min-height: 0;
  min-width: 0;
  opacity: 0;
  margin: 0;
  padding: 0;
}}
scrollbar {{
  background-color: {surface};
  border: none;
  box-shadow: none;
  min-width: 8px;
  margin: 0;
  padding: 0;
}}
scrollbar trough {{
  background-color: {surface};
  border: none;
}}
scrollbar slider {{
  background-color: {border};
  border-radius: 4px;
  min-width: 6px;
  margin: 2px;
}}
button.neuronix-card {{
  background-color: {card};
  background-image: none;
  border: none;
  border-radius: 10px;
  box-shadow: none;
  outline: none;
  padding: 8px 14px;
  margin: 0;
  min-height: 44px;
}}
button.neuronix-card:hover {{
  background-color: {card_hover};
}}
button.neuronix-card label.neuronix-row-title {{
  color: {fg};
  font-size: 14px;
  font-weight: 600;
}}
button.neuronix-card label.neuronix-row-desc {{
  color: {muted};
  font-size: 11px;
}}
button.neuronix-close {{
  background-color: {card};
  color: {fg};
  border: none;
  border-radius: 8px;
  padding: 10px 20px;
  font-size: 13px;
  min-width: 88px;
}}
button.neuronix-close:hover {{ background-color: {card_hover}; }}
button.neuronix-xclose {{
  background-color: transparent;
  background-image: none;
  color: {fg};
  border: none;
  border-radius: 8px;
  box-shadow: none;
  padding: 0;
  margin: 0;
  min-width: 32px;
  min-height: 32px;
  font-size: 22px;
  font-weight: 700;
}}
button.neuronix-xclose:hover {{
  background-color: #e02020;
  color: #ffffff;
}}
"""


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
    bg, fg = "#2e2e2e", "#f5f5f5"
    try:
        sys.path.insert(0, "/usr/share/neuronix/gtk-theme/python")
        from gtk_theme import load_profile  # type: ignore

        p = load_profile()
        bg, fg = p.background, p.foreground
    except Exception:
        pass
    surface = _mix_hex(bg, fg, 0.10)
    border = _mix_hex(bg, fg, 0.18)
    card = _mix_hex(bg, fg, 0.14)
    card_hover = _mix_hex(bg, fg, 0.22)
    muted = _mix_hex(fg, bg, 0.35)
    return {
        "bg": bg,
        "fg": fg,
        "surface": surface,
        "border": border,
        "card": card,
        "card_hover": card_hover,
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
        pos = subprocess.check_output(["hyprctl", "cursorpos"], text=True, timeout=1).strip()
        parts = [p.strip() for p in pos.split(",")]
        mon = _gdk_monitor_at(display, int(parts[0]), int(parts[1]))
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


def center_layer_window(win: Gtk.Window, width: int, height: int) -> None:
    """Pin a gtk-layer-shell surface to the center of the clicked/focused output."""
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.ON_DEMAND)
    GtkLayerShell.set_exclusive_zone(win, 0)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)

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


def _center_layer(win: Gtk.Window, width: int, height: int) -> None:
    center_layer_window(win, width, height)


def make_close_x_button(on_close) -> Gtk.Button:
    """Compact top-right × used by layer-shell dialogs (no window chrome)."""
    btn = Gtk.Button(label="×")
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_focus_on_click(False)
    btn.set_valign(Gtk.Align.START)
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


def choose(
    title: str,
    subtitle: str,
    items: Sequence[Tuple[str, str, str]],
    *,
    width: int = 520,
    height: int = 560,
    on_pick: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Show a choice dialog.

    items: (id, label, description). Returns selected id, or None if cancelled.
    """
    _apply_css()
    selected: Dict[str, Optional[str]] = {"id": None}

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title(title)
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_default_size(width, height)
    win.set_size_request(width, height)
    win.get_style_context().add_class("neuronix-choice")
    GLib.set_prgname("neuronix-choice")
    try:
        Gdk.set_program_class("neuronix-choice")
    except Exception:
        pass

    _center_layer(win, width, height)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    outer.get_style_context().add_class("neuronix-root")
    outer.set_margin_top(14)
    outer.set_margin_bottom(18)
    outer.set_margin_start(22)
    outer.set_margin_end(14)
    win.add(outer)

    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    pack_title_with_close(outer, title_lbl, lambda: Gtk.main_quit())

    if subtitle:
        sub = Gtk.Label(label=subtitle, xalign=0.0)
        sub.set_line_wrap(True)
        sub.get_style_context().add_class("neuronix-subtitle")
        outer.pack_start(sub, False, False, 0)

    # Avoid Gtk.ScrolledWindow — GTK3 rubber-bands at edges on Wayland.
    # Gtk.Layout gives a hard-clipped fixed viewport with no overshoot.
    scroll_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    scroll_row.set_hexpand(True)
    scroll_row.set_vexpand(True)
    scroll_row.get_style_context().add_class("neuronix-scroll-wrap")

    list_view_h = max(220, int(height) - 170)

    layout = Gtk.Layout()
    layout.set_hexpand(True)
    layout.set_vexpand(True)
    layout.set_size_request(-1, list_view_h)
    layout.get_style_context().add_class("neuronix-scroll")
    try:
        layout.add_events(
            Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
    except Exception:
        pass

    def _paint_layout(widget, cr):
        a = widget.get_allocation()
        cr.set_source_rgb(0x2E / 255.0, 0x2E / 255.0, 0x2E / 255.0)
        cr.rectangle(0, 0, a.width, a.height)
        cr.fill()
        return False

    layout.connect("draw", _paint_layout)

    list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    list_box.get_style_context().add_class("neuronix-list")
    layout.put(list_box, 0, 0)

    vadj = Gtk.Adjustment(
        value=0, lower=0, upper=0, step_increment=40, page_increment=120, page_size=0
    )
    vbar = Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL, adjustment=vadj)
    vbar.set_vexpand(True)

    def _content_height() -> float:
        _min_h, nat_h = list_box.get_preferred_height()
        return float(nat_h or 0)

    def _max_scroll():
        page = float(layout.get_allocated_height() or list_view_h)
        content = _content_height()
        return max(0.0, content - page), page, content

    def _apply_offset() -> None:
        y = -int(round(vadj.get_value()))
        layout.move(list_box, 0, y)

    def _sync_adj(*_a):
        mx, page, content = _max_scroll()
        width = max(layout.get_allocated_width(), 100)
        list_box.set_size_request(width, -1)
        layout.set_size(width, max(int(content), int(page)))
        upper = content if content > 0 else page
        cur = min(max(0.0, vadj.get_value()), mx)
        vadj.configure(cur, 0.0, upper, 40.0, max(page * 0.9, 40.0), page)
        vbar.set_visible(mx > 1.0)
        if mx <= 1.0:
            vadj.set_value(0)
        _apply_offset()
        return False

    def _on_adj(_a):
        mx, _, _ = _max_scroll()
        v = vadj.get_value()
        if v < 0.0:
            vadj.set_value(0.0)
            return
        if v > mx:
            vadj.set_value(mx)
            return
        _apply_offset()

    vadj.connect("value-changed", _on_adj)
    layout.connect("size-allocate", lambda *_: GLib.idle_add(_sync_adj))
    list_box.connect("size-allocate", lambda *_: GLib.idle_add(_sync_adj))

    def _on_scroll_event(_w, event):
        mx, _page, _content = _max_scroll()
        if mx <= 0.0:
            return True  # absorb — no bounce when content fits
        step = vadj.get_step_increment() or 40.0
        direction = event.direction
        if direction == Gdk.ScrollDirection.SMOOTH:
            dy = float(event.delta_y)
            if dy == 0.0:
                return True
            delta = dy * step
        elif direction == Gdk.ScrollDirection.UP:
            delta = -step
        elif direction == Gdk.ScrollDirection.DOWN:
            delta = step
        else:
            return False
        vadj.set_value(max(0.0, min(mx, vadj.get_value() + delta)))
        return True

    layout.connect("scroll-event", _on_scroll_event)
    scroll_row.pack_start(layout, True, True, 0)
    scroll_row.pack_end(vbar, False, False, 0)
    outer.pack_start(scroll_row, True, True, 0)

    def _pick(item_id: str) -> None:
        selected["id"] = item_id
        if on_pick:
            GLib.idle_add(lambda: (on_pick(item_id), False)[1])
        Gtk.main_quit()

    for item_id, label, desc in items:
        btn = Gtk.Button()
        btn.get_style_context().add_class("neuronix-card")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_hexpand(True)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        inner.set_halign(Gtk.Align.START)
        t = Gtk.Label(label=label, xalign=0.0)
        t.get_style_context().add_class("neuronix-row-title")
        d = Gtk.Label(label=desc, xalign=0.0)
        d.set_line_wrap(True)
        d.get_style_context().add_class("neuronix-row-desc")
        inner.pack_start(t, False, False, 0)
        inner.pack_start(d, False, False, 0)
        btn.add(inner)
        btn.connect("clicked", lambda _b, i=item_id: _pick(i))
        list_box.pack_start(btn, False, False, 0)

    foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    foot.set_halign(Gtk.Align.END)
    close_btn = Gtk.Button(label="Close")
    close_btn.get_style_context().add_class("neuronix-close")
    close_btn.connect("clicked", lambda *_: Gtk.main_quit())
    foot.pack_start(close_btn, False, False, 0)
    outer.pack_start(foot, False, False, 0)

    win.connect(
        "key-press-event",
        lambda _w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else False,
    )
    win.connect("destroy", lambda *_: Gtk.main_quit())

    win.show_all()
    GLib.idle_add(_sync_adj)
    win.present()
    Gtk.main()
    return selected["id"]


def main_cli() -> int:
    if len(sys.argv) < 4:
        print(
            "Usage: neuronix_choice_dialog.py TITLE SUBTITLE id|label|desc ...",
            file=sys.stderr,
        )
        return 2
    title, subtitle = sys.argv[1], sys.argv[2]
    items: List[Tuple[str, str, str]] = []
    for raw in sys.argv[3:]:
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
