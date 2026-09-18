"""Sidebar schema: sections and typed fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FieldKind = Literal[
    "string",
    "int",
    "float",
    "bool",
    "color",
    "font",
    "choice",
    "raw_link",
]


@dataclass
class FieldDef:
    id: str
    label: str
    kind: FieldKind
    # Where the value lives
    file: str
    # Backend: hypr|ini|flat|xsettings|toml|css_prop
    backend: str
    # Backend-specific locator
    block: list[str] = field(default_factory=list)  # hypr
    section: str | None = None  # ini
    key: str = ""
    color_kind: str = "auto"  # for color fields
    choices: list[str] = field(default_factory=list)
    min_v: float | None = None
    max_v: float | None = None
    step: float | None = None
    search_tags: str = ""


@dataclass
class SectionDef:
    id: str
    title: str
    blurb: str
    fields: list[FieldDef] = field(default_factory=list)
    raw_files: list[str] = field(default_factory=list)  # shown as Raw open buttons


def build_schema() -> list[SectionDef]:
    hypr = "hypr/hyprland.conf"
    # Color swatches live in GTK Theme Editor (Settings → Themes), not here.
    return [
        SectionDef(
            id="files",
            title="Files",
            blurb="Open any text config under the root in the Raw editor. Secrets are listed but not loaded for editing.",
            fields=[],
            raw_files=[],  # filled dynamically
        ),
        SectionDef(
            id="hyprland",
            title="Hyprland",
            blurb="Gaps, decoration, and plugin layout. Binds, monitors, and windowrules → Raw. Colors → Themes.",
            fields=[
                FieldDef("gaps_in", "Gaps in", "int", hypr, "hypr", block=["general"], key="gaps_in", min_v=0, max_v=64),
                FieldDef("gaps_out", "Gaps out", "int", hypr, "hypr", block=["general"], key="gaps_out", min_v=0, max_v=128),
                FieldDef("border_size", "Border size", "int", hypr, "hypr", block=["general"], key="border_size", min_v=0, max_v=16),
                FieldDef("rounding", "Rounding", "int", hypr, "hypr", block=["decoration"], key="rounding", min_v=0, max_v=32),
                FieldDef("active_opacity", "Active opacity", "float", hypr, "hypr", block=["decoration"], key="active_opacity", min_v=0.5, max_v=1.0, step=0.01),
                FieldDef("inactive_opacity", "Inactive opacity", "float", hypr, "hypr", block=["decoration"], key="inactive_opacity", min_v=0.5, max_v=1.0, step=0.01),
                FieldDef("panel_height", "Panel height", "int", hypr, "hypr", block=["plugin", "overview"], key="panelHeight", min_v=40, max_v=400),
            ],
            raw_files=[
                "hypr/hyprland.conf",
                "hypr/binds-personal.conf",
                "hypr/hyprpaper.conf",
                "hypr/monitors.conf",
                "hypr/workspaces.conf",
            ],
        ),
        SectionDef(
            id="waybar",
            title="Waybar",
            blurb="Module JSON and style.css. Chrome colors → Themes (GTK Theme Editor).",
            fields=[],
            raw_files=["waybar/style.css", "waybar/config"],
        ),
        SectionDef(
            id="fuzzel",
            title="Fuzzel",
            blurb="Launcher layout. Colors → Themes (GTK Theme Editor).",
            fields=[
                FieldDef("fz_font", "Font", "font", "fuzzel/fuzzel.ini", "ini", section="main", key="font"),
                FieldDef("fz_terminal", "Terminal", "string", "fuzzel/fuzzel.ini", "ini", section="main", key="terminal"),
                FieldDef("fz_lines", "Lines", "int", "fuzzel/fuzzel.ini", "ini", section="main", key="lines", min_v=4, max_v=40),
                FieldDef("fz_width", "Width", "int", "fuzzel/fuzzel.ini", "ini", section="main", key="width", min_v=20, max_v=120),
                FieldDef("fz_icons", "Icon theme", "string", "fuzzel/fuzzel.ini", "ini", section="main", key="icon-theme"),
            ],
            raw_files=["fuzzel/fuzzel.ini"],
        ),
        SectionDef(
            id="mako",
            title="Mako",
            blurb="Notification daemon layout. Colors → Themes (GTK Theme Editor).",
            fields=[
                FieldDef("mk_font", "Font", "font", "mako/config", "flat", key="font"),
                FieldDef("mk_bs", "Border size", "int", "mako/config", "flat", key="border-size", min_v=0, max_v=20),
                FieldDef("mk_br", "Border radius", "int", "mako/config", "flat", key="border-radius", min_v=0, max_v=40),
                FieldDef("mk_timeout", "Default timeout (ms)", "int", "mako/config", "flat", key="default-timeout", min_v=0, max_v=60000),
                FieldDef(
                    "mk_anchor",
                    "Anchor",
                    "choice",
                    "mako/config",
                    "flat",
                    key="anchor",
                    choices=[
                        "top-right",
                        "top-center",
                        "top-left",
                        "bottom-right",
                        "bottom-center",
                        "bottom-left",
                        "center",
                    ],
                ),
                FieldDef("mk_margin", "Margin", "int", "mako/config", "flat", key="margin", min_v=0, max_v=64),
            ],
            raw_files=["mako/config"],
        ),
        SectionDef(
            id="gtk",
            title="GTK / cursors",
            blurb="Theme and icon names (not hex). Palette colors → Themes (GTK Theme Editor).",
            fields=[
                FieldDef("gtk3_theme", "GTK3 theme", "string", "gtk-3.0/settings.ini", "ini", section="Settings", key="gtk-theme-name"),
                FieldDef("gtk3_icons", "GTK3 icons", "string", "gtk-3.0/settings.ini", "ini", section="Settings", key="gtk-icon-theme-name"),
                FieldDef("gtk3_font", "GTK3 font", "font", "gtk-3.0/settings.ini", "ini", section="Settings", key="gtk-font-name"),
                FieldDef("gtk4_theme", "GTK4 theme", "string", "gtk-4.0/settings.ini", "ini", section="Settings", key="gtk-theme-name"),
                FieldDef("gtk4_icons", "GTK4 icons", "string", "gtk-4.0/settings.ini", "ini", section="Settings", key="gtk-icon-theme-name"),
                FieldDef("gtk4_scheme", "Adw color-scheme", "choice", "gtk-4.0/settings.ini", "ini", section="AdwStyleManager", key="color-scheme", choices=["prefer-dark", "prefer-light", "default"]),
                FieldDef("xs_theme", "Xsettings theme", "string", "xsettingsd/xsettingsd.conf", "xsettings", key="Net/ThemeName"),
                FieldDef("xs_icons", "Xsettings icons", "string", "xsettingsd/xsettingsd.conf", "xsettings", key="Net/IconThemeName"),
                FieldDef("xs_cursor", "Xsettings cursor", "string", "xsettingsd/xsettingsd.conf", "xsettings", key="Gtk/CursorThemeName"),
                FieldDef("xs_font", "Xsettings font", "font", "xsettingsd/xsettingsd.conf", "xsettings", key="Gtk/FontName"),
            ],
            raw_files=[
                "gtk-3.0/settings.ini",
                "gtk-3.0/gtk.css",
                "gtk-4.0/settings.ini",
                "gtk-4.0/gtk.css",
                "gtkrc-2.0",
                "xsettingsd/xsettingsd.conf",
                "icons/default/index.theme",
            ],
        ),
        SectionDef(
            id="terminal",
            title="Terminal / gtk-apps",
            blurb="Active profile id and raw profile JSON / app state.",
            fields=[
                FieldDef("theme_profile", "theme.toml profile", "string", "gtk-apps/theme.toml", "toml", key="profile"),
                FieldDef("term_profile", "gtk-term profile", "string", "gtk-apps/gtk-term/state.toml", "toml", key="profile"),
                FieldDef("edit_scheme", "gtk-edit scheme", "string", "gtk-apps/gtk-edit/config.toml", "ini", section="editor", key="scheme"),
            ],
            raw_files=[
                "gtk-apps/theme.toml",
                "gtk-apps/custom-profiles.json",
                "gtk-apps/gtk-term/state.toml",
                "gtk-apps/gtk-edit/config.toml",
                "gtk-apps/gtk-files/config.toml",
                "gtk-apps/gtk-files/places.toml",
            ],
        ),
        SectionDef(
            id="mime",
            title="MIME / terminals",
            blurb="Default applications and terminal desktop ids.",
            fields=[],
            raw_files=[
                "mimeapps.list",
                "xdg-terminals.list",
                "gnome-xdg-terminals.list",
            ],
        ),
    ]


def _strip_quotes(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def get_field_value(store: Any, field: FieldDef) -> str | None:
    from . import css_edit

    b = field.backend
    if b == "hypr":
        return store.get_hypr(field.file, field.block, field.key)
    if b == "ini":
        return _strip_quotes(store.get_ini(field.file, field.section, field.key))
    if b == "flat":
        return store.get_flat(field.file, field.key)
    if b == "xsettings":
        return store.get_xsettings(field.file, field.key)
    if b == "toml":
        return _strip_quotes(store.get_toml_simple(field.file, field.key))
    if b in ("css_first", "css_border"):
        return css_edit.get_prop(store.get_text(field.file), field.key, border=(b == "css_border"))
    return None


def set_field_value(store: Any, field: FieldDef, value: str) -> None:
    from . import css_edit
    from . import colors_fmt

    b = field.backend
    if field.kind == "color" and b in ("hypr", "ini", "flat"):
        rgba = colors_fmt.parse_color(
            value, field.color_kind if field.color_kind != "auto" else "auto"
        )  # type: ignore[arg-type]
        if rgba is None:
            rgba = colors_fmt.parse_color(value, "auto")
        if rgba is not None:
            kind = field.color_kind if field.color_kind != "auto" else "hex"
            if kind == "auto":
                kind = "hex"
            old = get_field_value(store, field)
            if old:
                value = colors_fmt.rewrite_token(old.strip(), rgba)
            else:
                value = colors_fmt.format_color(rgba, kind)  # type: ignore[arg-type]

    if b == "hypr":
        store.set_hypr(field.file, field.block, field.key, value)
    elif b == "ini":
        # Preserve TOML-style quoting when the on-disk value was quoted
        raw = store.get_ini(field.file, field.section, field.key)
        if raw and len(raw.strip()) >= 2 and raw.strip()[0] == '"':
            value = f'"{_strip_quotes(value)}"'
        store.set_ini(field.file, field.section, field.key, value)
    elif b == "flat":
        store.set_flat(field.file, field.key, value)
    elif b == "xsettings":
        store.set_xsettings(field.file, field.key, value)
    elif b == "toml":
        store.set_toml_simple(field.file, field.key, value)
    elif b in ("css_first", "css_border"):
        text = store.get_text(field.file)
        store.set_text(
            field.file,
            css_edit.set_prop(text, field.key, value, border=(b == "css_border")),
        )
