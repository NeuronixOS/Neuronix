#!/usr/bin/env python3
"""Shared Neuronix GTK choice dialog — spacious action cards (not a packed zenity table)."""
from __future__ import annotations

import os
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell  # noqa: E402

CSS = b"""
window.neuronix-choice {
  background-color: #2e2e2e;
  border: 1px solid #505050;
  border-radius: 12px;
  color: #f5f5f5;
}
box.neuronix-root,
box.neuronix-scroll-wrap,
eventbox.neuronix-scroll-wrap {
  background-color: #2e2e2e;
}
scrolledwindow.neuronix-scroll,
scrolledwindow.neuronix-scroll > *,
scrolledwindow.neuronix-scroll viewport,
scrolledwindow.neuronix-scroll undershoot,
scrolledwindow.neuronix-scroll overshoot {
  background-color: #2e2e2e;
  border: none;
  box-shadow: none;
  outline: none;
  border-width: 0;
}
label.neuronix-title {
  color: #f5f5f5;
  font-size: 22px;
  font-weight: 700;
}
label.neuronix-subtitle {
  color: #b0b0b0;
  font-size: 13px;
}
scrolledwindow, viewport, box.neuronix-list, frame {
  background-color: #2e2e2e;
  border: none;
  box-shadow: none;
  outline: none;
  border-width: 0;
  border-style: none;
  border-radius: 0;
}
scrolledwindow > viewport,
scrolledwindow > widget,
scrolledwindow > scrollbar {
  border: none;
  background-color: #2e2e2e;
}
/* Match edge etch to window bg */
scrolledwindow overshoot.top,
scrolledwindow overshoot.bottom,
scrolledwindow undershoot.top,
scrolledwindow undershoot.bottom,
scrolledwindow overshoot,
scrolledwindow undershoot {
  background-color: #2e2e2e;
  background-image: none;
  border: none;
  box-shadow: none;
  min-height: 0;
  min-width: 0;
  opacity: 0;
  margin: 0;
  padding: 0;
}
scrollbar {
  background-color: #2e2e2e;
  border: none;
  box-shadow: none;
  min-width: 8px;
  margin: 0;
  padding: 0;
}
scrollbar trough {
  background-color: #2e2e2e;
  border: none;
}
scrollbar slider {
  background-color: #555555;
  border-radius: 4px;
  min-width: 6px;
  margin: 2px;
}
button.neuronix-card {
  background-color: #3a3a3a;
  background-image: none;
  border: none;
  border-radius: 10px;
  box-shadow: none;
  outline: none;
  padding: 8px 14px;
  margin: 0;
  min-height: 44px;
}
button.neuronix-card:hover {
  background-color: #4a4a4a;
}
button.neuronix-card label.neuronix-row-title {
  color: #f5f5f5;
  font-size: 14px;
  font-weight: 600;
}
button.neuronix-card label.neuronix-row-desc {
  color: #a8a8a8;
  font-size: 11px;
}
button.neuronix-close {
  background-color: #3a3a3a;
  color: #f5f5f5;
  border: none;
  border-radius: 8px;
  padding: 10px 20px;
  font-size: 13px;
  min-width: 88px;
}
button.neuronix-close:hover { background-color: #4a4a4a; }
"""


def _apply_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    # USER priority so we beat Adwaita's scrolledwindow border/undershoot
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
    )


def _monitor_geom():
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() if display else None
    if monitor is None and display is not None:
        monitor = display.get_monitor(0)
    if monitor is not None:
        return monitor.get_geometry()
    return None


def _center_layer(win: Gtk.Window, width: int, height: int) -> None:
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.TOP)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.ON_DEMAND)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.LEFT, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)

    geo = _monitor_geom()
    if geo is not None:
        left = max(12, (geo.width - width) // 2)
        top = max(40, (geo.height - height) // 2)
    else:
        left, top = 200, 120
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.LEFT, left)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, top)


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
    outer.set_margin_top(22)
    outer.set_margin_bottom(18)
    outer.set_margin_start(22)
    outer.set_margin_end(22)
    win.add(outer)

    title_lbl = Gtk.Label(label=title, xalign=0.0)
    title_lbl.get_style_context().add_class("neuronix-title")
    outer.pack_start(title_lbl, False, False, 0)

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
