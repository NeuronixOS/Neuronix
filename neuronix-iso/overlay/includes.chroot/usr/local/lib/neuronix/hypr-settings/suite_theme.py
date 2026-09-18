"""Map Neuronix gtk-theme suite profile → Qt stylesheet colors for hypr-settings."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional


def _ensure_gtk_theme_path() -> None:
    candidates = (
        Path("/usr/share/neuronix/gtk-theme/python"),
        Path("/usr/local/lib/neuronix/gtk-apps/gtk-theme/python"),
        Path.home() / ".local/share/neuronix/gtk-theme/python",
    )
    for cand in candidates:
        if (cand / "gtk_theme.py").is_file():
            p = str(cand)
            if p not in sys.path:
                sys.path.insert(0, p)
            return


def _mix(a: str, b: str, t: float) -> str:
    def parse(c: str) -> tuple[int, int, int]:
        c = c.lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    ar, ag, ab = parse(a)
    br, bg, bb = parse(b)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    b_ = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{b_:02x}"


def _luminance(color: str) -> float:
    r, g, b = (_c / 255.0 for _c in (
        int(color.lstrip("#")[0:2], 16),
        int(color.lstrip("#")[2:4], 16),
        int(color.lstrip("#")[4:6], 16),
    ))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def load_suite_profile() -> Optional[Any]:
    """Return gtk_theme.Profile or None if the suite module is unavailable."""
    _ensure_gtk_theme_path()
    try:
        import gtk_theme  # type: ignore
    except Exception:
        return None
    try:
        return gtk_theme.load_profile()
    except Exception:
        return None


def theme_toml_path() -> Path:
    return Path.home() / ".config" / "gtk-apps" / "theme.toml"


def colors_from_profile(profile: Any) -> dict[str, str]:
    bg = str(profile.background)
    fg = str(profile.foreground)
    surface = str(profile.surface_hex())
    surface_alt = str(profile.surface_alt_hex())
    accent = str(profile.accent())
    border = str(profile.border_hex())
    on_accent = "#fbf1c7" if _luminance(accent) < 0.55 else "#1d2021"
    return {
        "BG": bg,
        "BG_SIDEBAR": surface,
        "BG_RAISED": surface_alt,
        "BG_HOVER": _mix(bg, fg, 0.10),
        "BG_PRESS": _mix(bg, fg, 0.16),
        "TEXT": fg,
        "TEXT_BRIGHT": fg,
        "TEXT_DIM": _mix(fg, bg, 0.25),
        "TEXT_MUTED": _mix(fg, bg, 0.45),
        "BORDER": border,
        "BORDER_HOVER": _mix(border, fg, 0.35),
        "BORDER_FOCUS": accent,
        "BORDER_SUBTLE": _mix(bg, fg, 0.08),
        "SEP": _mix(bg, fg, 0.12),
        "INPUT_TEXT": fg,
        "LIST_ITEM": fg,
        "ACCENT": accent,
        "ACCENT_TEXT": on_accent,
    }


def suite_colors() -> Optional[dict[str, str]]:
    profile = load_suite_profile()
    if profile is None:
        return None
    return colors_from_profile(profile)


def suite_is_dark() -> Optional[bool]:
    profile = load_suite_profile()
    if profile is None:
        return None
    try:
        return bool(profile.is_dark())
    except Exception:
        return None
