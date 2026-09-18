"""Keyboard / Hyprland kb_* settings for hypr-settings."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from common import make_centered, separator

HYPR_CONF = Path.home() / ".config/hypr/hyprland.conf"

COMMON_LAYOUTS: list[tuple[str, str]] = [
    ("us", "English (US)"),
    ("gb", "English (UK)"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("br", "Portuguese (Brazil)"),
    ("ru", "Russian"),
    ("ua", "Ukrainian"),
    ("pl", "Polish"),
    ("cz", "Czech"),
    ("sk", "Slovak"),
    ("hu", "Hungarian"),
    ("ro", "Romanian"),
    ("nl", "Dutch"),
    ("be", "Belgian"),
    ("ch", "Swiss"),
    ("se", "Swedish"),
    ("no", "Norwegian"),
    ("dk", "Danish"),
    ("fi", "Finnish"),
    ("tr", "Turkish"),
    ("gr", "Greek"),
    ("il", "Hebrew"),
    ("ara", "Arabic"),
    ("jp", "Japanese"),
    ("kr", "Korean"),
    ("cn", "Chinese"),
]

COMMON_VARIANTS: dict[str, list[tuple[str, str]]] = {
    "us": [
        ("", "Default (QWERTY)"),
        ("dvorak", "Dvorak"),
        ("colemak", "Colemak"),
        ("intl", "International"),
        ("altgr-intl", "Intl (AltGr dead keys)"),
        ("euro", "With euro on 5"),
    ],
    "gb": [("", "Default"), ("extd", "Extended"), ("dvorak", "Dvorak")],
    "de": [("", "Default"), ("nodeadkeys", "No dead keys"), ("mac", "Macintosh")],
    "fr": [("", "Default"), ("oss", "Alternative"), ("bepo", "BÉPO"), ("mac", "Macintosh")],
    "es": [("", "Default"), ("nodeadkeys", "No dead keys"), ("dvorak", "Dvorak")],
    "ru": [("", "Default"), ("phonetic", "Phonetic")],
    "br": [("", "Default"), ("abnt2", "ABNT2"), ("dvorak", "Dvorak")],
}

TOGGLE_OPTIONS: list[tuple[str, str]] = [
    ("", "None (no layout switch key)"),
    ("grp:alt_shift_toggle", "Alt+Shift"),
    ("grp:ctrl_shift_toggle", "Ctrl+Shift"),
    ("grp:win_space_toggle", "Super+Space"),
    ("grp:caps_toggle", "Caps Lock"),
    ("grp:alt_caps_toggle", "Alt+Caps Lock"),
    ("grp:shifts_toggle", "Both Shifts together"),
]

CAPS_OPTIONS: list[tuple[str, str]] = [
    ("", "Caps Lock (default)"),
    ("caps:escape", "Caps Lock acts as Escape"),
    ("caps:swapescape", "Swap Caps Lock and Escape"),
    ("ctrl:nocaps", "Caps Lock acts as Ctrl"),
    ("caps:ctrl_modifier", "Caps Lock is Ctrl"),
    ("caps:none", "Disable Caps Lock"),
]


def _read_input_keys(text: str) -> dict[str, str]:
    out = {"kb_layout": "us", "kb_variant": "", "kb_options": "", "kb_model": ""}
    m = re.search(r"(?ms)^\s*input\s*\{(.*?)^\s*\}", text)
    if not m:
        return out
    block = m.group(1)
    for key in out:
        km = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*(.*?)\s*$", block)
        if km:
            out[key] = km.group(1).strip()
    return out


def _write_input_keys(text: str, values: dict[str, str]) -> str:
    m = re.search(r"(?ms)^(\s*input\s*\{)(.*?)(^\s*\})", text)
    if not m:
        lines = ["input {"]
        for k, v in values.items():
            if v:
                lines.append(f"    {k} = {v}")
        lines.append("}")
        return text.rstrip() + "\n\n" + "\n".join(lines) + "\n"

    head, body, tail = m.group(1), m.group(2), m.group(3)
    new_body = body
    for key, val in values.items():
        pat = re.compile(rf"(?m)^(\s*){re.escape(key)}\s*=\s*.*$")
        if pat.search(new_body):
            if val:
                new_body = pat.sub(rf"\1{key} = {val}", new_body, count=1)
            else:
                new_body = pat.sub("", new_body, count=1)
        elif val:
            new_body = new_body.rstrip("\n") + f"\n    {key} = {val}\n"
    new_body = re.sub(r"\n{3,}", "\n\n", new_body)
    return text[: m.start()] + head + new_body + tail + text[m.end() :]


def load_keyboard_config() -> dict[str, str]:
    if not HYPR_CONF.is_file():
        return {"kb_layout": "us", "kb_variant": "", "kb_options": "", "kb_model": ""}
    try:
        return _read_input_keys(HYPR_CONF.read_text(encoding="utf-8"))
    except OSError:
        return {"kb_layout": "us", "kb_variant": "", "kb_options": "", "kb_model": ""}


def save_keyboard_config(values: dict[str, str]) -> tuple[bool, str]:
    if not HYPR_CONF.is_file():
        return False, f"Missing config: {HYPR_CONF}"
    try:
        text = HYPR_CONF.read_text(encoding="utf-8")
    except OSError as exc:
        return False, str(exc)

    cleaned = {
        "kb_layout": (values.get("kb_layout") or "us").strip() or "us",
        "kb_variant": (values.get("kb_variant") or "").strip(),
        "kb_options": (values.get("kb_options") or "").strip(),
        "kb_model": (values.get("kb_model") or "").strip(),
    }
    new_text = _write_input_keys(text, cleaned)
    try:
        HYPR_CONF.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)

    errors: list[str] = []
    for key, val in cleaned.items():
        try:
            r = subprocess.run(
                ["hyprctl", "keyword", f"input:{key}", val],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode != 0:
                errors.append((r.stderr or r.stdout or key).strip())
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        return True, "Saved, but live apply had issues: " + "; ".join(errors[:2])
    return True, "Keyboard settings applied."


def _split_csv(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",")]


def _parse_options(raw: str) -> tuple[str, str, list[str]]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    toggle = ""
    caps = ""
    other: list[str] = []
    toggle_ids = {t[0] for t in TOGGLE_OPTIONS if t[0]}
    caps_ids = {c[0] for c in CAPS_OPTIONS if c[0]}
    for p in parts:
        if p in toggle_ids and not toggle:
            toggle = p
        elif p in caps_ids and not caps:
            caps = p
        else:
            other.append(p)
    return toggle, caps, other


def _fill_combo(combo: QComboBox, items: list[tuple[str, str]], active: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    for code, label in items:
        combo.addItem(label, code)
    idx = combo.findData(active)
    if idx < 0 and active:
        combo.addItem(active, active)
        idx = combo.findData(active)
    combo.setCurrentIndex(max(0, idx))
    combo.blockSignals(False)


def _variant_items(layout: str) -> list[tuple[str, str]]:
    return COMMON_VARIANTS.get(layout, [("", "Default")])


class KeyboardTab(QWidget):
    def __init__(self):
        super().__init__()
        self._other_opts: list[str] = []
        self._kb_model = ""
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(make_centered(self, max_width=720))
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("Keyboard")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        intro = QLabel(
            "Choose layouts for Hyprland. Changes write to hyprland.conf and apply immediately."
        )
        intro.setObjectName("statusLabel")
        intro.setWordWrap(True)
        root.addWidget(intro)
        root.addWidget(separator())

        def labeled(text: str, widget: QWidget):
            lbl = QLabel(text)
            lbl.setObjectName("sectionTitle")
            root.addWidget(lbl)
            root.addWidget(widget)

        self._primary = QComboBox()
        labeled("Primary layout", self._primary)
        self._primary_var = QComboBox()
        labeled("Primary variant", self._primary_var)

        self._secondary = QComboBox()
        labeled("Secondary layout (optional)", self._secondary)
        self._secondary_var = QComboBox()
        labeled("Secondary variant", self._secondary_var)

        self._toggle = QComboBox()
        labeled("Layout switch shortcut", self._toggle)
        self._caps = QComboBox()
        labeled("Caps Lock behavior", self._caps)

        self._primary.currentIndexChanged.connect(self._on_primary_changed)
        self._secondary.currentIndexChanged.connect(self._on_secondary_changed)

        row = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        row.addWidget(apply_btn)
        row.addStretch()
        root.addLayout(row)

        self._status = QLabel("")
        self._status.setObjectName("statusLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._current = QLabel("")
        self._current.setObjectName("statusLabel")
        self._current.setWordWrap(True)
        root.addWidget(self._current)
        root.addStretch()

    def _load(self):
        cfg = load_keyboard_config()
        layouts = _split_csv(cfg.get("kb_layout") or "us")
        variants = _split_csv(cfg.get("kb_variant") or "")
        while len(variants) < len(layouts):
            variants.append("")
        primary = layouts[0] if layouts else "us"
        primary_var = variants[0] if variants else ""
        secondary = layouts[1] if len(layouts) > 1 else ""
        secondary_var = variants[1] if len(variants) > 1 else ""
        toggle, caps, self._other_opts = _parse_options(cfg.get("kb_options") or "")
        self._kb_model = cfg.get("kb_model") or ""

        _fill_combo(self._primary, COMMON_LAYOUTS, primary)
        _fill_combo(self._primary_var, _variant_items(primary), primary_var)

        sec_items = [("", "None")] + list(COMMON_LAYOUTS)
        _fill_combo(self._secondary, sec_items, secondary)
        _fill_combo(
            self._secondary_var, _variant_items(secondary or "us"), secondary_var
        )
        _fill_combo(self._toggle, TOGGLE_OPTIONS, toggle)
        _fill_combo(self._caps, CAPS_OPTIONS, caps)

        self._current.setText(
            f"Current: layout={cfg.get('kb_layout') or 'us'}  "
            f"variant={cfg.get('kb_variant') or '—'}  "
            f"options={cfg.get('kb_options') or '—'}"
        )

    def _on_primary_changed(self):
        code = self._primary.currentData() or "us"
        _fill_combo(self._primary_var, _variant_items(code), "")

    def _on_secondary_changed(self):
        code = self._secondary.currentData() or ""
        _fill_combo(self._secondary_var, _variant_items(code or "us"), "")

    def _collect(self) -> dict[str, str]:
        p = self._primary.currentData() or "us"
        pv = self._primary_var.currentData() or ""
        s = self._secondary.currentData() or ""
        sv = self._secondary_var.currentData() or ""
        if s:
            layout = f"{p},{s}"
            variant = f"{pv},{sv}"
        else:
            layout = p
            variant = pv
        opts = []
        t = self._toggle.currentData() or ""
        c = self._caps.currentData() or ""
        if t:
            opts.append(t)
        if c:
            opts.append(c)
        opts.extend(self._other_opts)
        return {
            "kb_layout": layout,
            "kb_variant": variant,
            "kb_options": ",".join(opts),
            "kb_model": self._kb_model,
        }

    def _apply(self):
        ok, msg = save_keyboard_config(self._collect())
        self._status.setText(msg)
        if ok:
            self._load()
