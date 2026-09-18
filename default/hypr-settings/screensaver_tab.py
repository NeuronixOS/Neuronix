"""Screensaver settings — configures neuronix-screensaver idle service."""
from __future__ import annotations

import configparser
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from common import make_centered, run, separator

CONFIG_DIR = Path.home() / ".config" / "neuronix-screensaver"
CONFIG_PATH = CONFIG_DIR / "config.ini"
UNIT = "neuronix-screensaver-idle.service"

MODES = [
    ("clock", "Clock"),
    ("stars", "Stars (warp field)"),
    ("aurora", "Aurora"),
    ("matrix", "Matrix"),
]

# Preset idle timeouts shown in the combo (seconds → label).
IDLE_PRESETS = [
    (60, "1 minute"),
    (120, "2 minutes"),
    (300, "5 minutes"),
    (600, "10 minutes"),
    (900, "15 minutes"),
    (1800, "30 minutes"),
    (3600, "1 hour"),
]

DEFAULT_IDLE = 300
DEFAULT_MODE = "clock"

_SERVICE_ROOTS = (
    Path("/usr/local/lib/neuronix/services/screensaver"),
    Path(__file__).resolve().parents[1] / "services" / "screensaver",
    Path.home() / "Projects/LinuxOS/Neuronix/default/services/screensaver",
)


def _service_root() -> Path | None:
    for root in _SERVICE_ROOTS:
        if (root / "screensaver.py").is_file() and (root / "idle_daemon.py").is_file():
            return root
    return None


def _example_config() -> Path | None:
    root = _service_root()
    if root and (root / "config.example.ini").is_file():
        return root / "config.example.ini"
    return None


def _load_config() -> tuple[int, str]:
    idle = DEFAULT_IDLE
    mode = DEFAULT_MODE
    if CONFIG_PATH.is_file():
        cfg = configparser.ConfigParser()
        try:
            cfg.read(CONFIG_PATH)
            if cfg.has_section("idle"):
                idle = cfg.getint("idle", "seconds", fallback=idle)
            if cfg.has_section("screensaver"):
                mode = cfg.get("screensaver", "mode", fallback=mode).strip() or mode
        except (configparser.Error, OSError, ValueError):
            pass
    if mode not in {m for m, _ in MODES}:
        mode = DEFAULT_MODE
    return max(1, idle), mode


def _write_config(idle_seconds: int, mode: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    example = _example_config()
    if not CONFIG_PATH.is_file() and example is not None:
        shutil.copy(example, CONFIG_PATH)

    cfg = configparser.ConfigParser()
    if CONFIG_PATH.is_file():
        cfg.read(CONFIG_PATH)
    if not cfg.has_section("idle"):
        cfg.add_section("idle")
    if not cfg.has_section("screensaver"):
        cfg.add_section("screensaver")
    cfg.set("idle", "seconds", str(max(1, int(idle_seconds))))
    cfg.set("screensaver", "mode", mode)
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        cfg.write(fh)


def _unit_state() -> str:
    """active / inactive / failed / not-found / …"""
    out, ok = run(["systemctl", "--user", "is-active", UNIT], timeout=3)
    if ok and out.strip():
        return out.strip()
    out2, _ = run(["systemctl", "--user", "is-enabled", UNIT], timeout=3)
    enabled = out2.strip() if out2 else ""
    if enabled == "not-found" or "could not be found" in (out2 or "").lower():
        return "not-found"
    return out.strip() or "inactive"


def _unit_enabled() -> bool:
    out, ok = run(["systemctl", "--user", "is-enabled", UNIT], timeout=3)
    return ok and out.strip() in ("enabled", "enabled-runtime", "static", "indirect")


def _systemctl_user(*args: str) -> tuple[str, bool]:
    return run(["systemctl", "--user", *args], timeout=15)


class ScreensaverTab(QWidget):
    def __init__(self):
        super().__init__()
        self._loading = False
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(make_centered(self, max_width=720))
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("Screensaver")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        hint = QLabel(
            "Idle watcher covers every monitor after a period without keyboard "
            "or mouse input. Config: ~/.config/neuronix-screensaver/config.ini"
        )
        hint.setObjectName("statusLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addWidget(separator())

        sec = QLabel("Idle service")
        sec.setObjectName("sectionTitle")
        root.addWidget(sec)

        self._status = QLabel("")
        self._status.setObjectName("statusLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._enabled = QCheckBox("Start screensaver automatically when idle")
        self._enabled.toggled.connect(self._on_enabled_toggled)
        root.addWidget(self._enabled)

        svc_row = QHBoxLayout()
        self._restart_btn = QPushButton("Restart service")
        self._restart_btn.clicked.connect(self._restart_service)
        svc_row.addWidget(self._restart_btn)
        self._preview_btn = QPushButton("Preview now")
        self._preview_btn.clicked.connect(self._preview)
        svc_row.addWidget(self._preview_btn)
        svc_row.addStretch()
        root.addLayout(svc_row)
        root.addWidget(separator())

        sec2 = QLabel("Timeouts & appearance")
        sec2.setObjectName("sectionTitle")
        root.addWidget(sec2)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self._idle_preset = QComboBox()
        for secs, label in IDLE_PRESETS:
            self._idle_preset.addItem(label, secs)
        self._idle_preset.addItem("Custom…", -1)
        self._idle_preset.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("Idle after", self._idle_preset)

        self._idle_spin = QSpinBox()
        self._idle_spin.setRange(15, 86400)
        self._idle_spin.setSingleStep(30)
        self._idle_spin.setSuffix(" seconds")
        self._idle_spin.setToolTip("Seconds without keyboard/mouse before the screensaver starts")
        form.addRow("Custom timeout", self._idle_spin)

        self._mode = QComboBox()
        for key, label in MODES:
            self._mode.addItem(label, key)
        form.addRow("Style", self._mode)

        root.addLayout(form)

        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.clicked.connect(self._apply)
        apply_row.addWidget(self._apply_btn)
        root.addLayout(apply_row)

        self._msg = QLabel("")
        self._msg.setObjectName("statusLabel")
        self._msg.setWordWrap(True)
        root.addWidget(self._msg)
        root.addStretch()

    def _load(self):
        self._loading = True
        idle, mode = _load_config()
        preset_idx = -1
        for i in range(self._idle_preset.count()):
            if self._idle_preset.itemData(i) == idle:
                preset_idx = i
                break
        if preset_idx < 0:
            # Custom
            for i in range(self._idle_preset.count()):
                if self._idle_preset.itemData(i) == -1:
                    preset_idx = i
                    break
        self._idle_preset.setCurrentIndex(max(0, preset_idx))
        self._idle_spin.setValue(idle)
        self._on_preset_changed()

        midx = self._mode.findData(mode)
        self._mode.setCurrentIndex(midx if midx >= 0 else 0)

        state = _unit_state()
        enabled = _unit_enabled() and state != "not-found"
        self._enabled.blockSignals(True)
        self._enabled.setChecked(enabled)
        self._enabled.blockSignals(False)

        root = _service_root()
        if state == "not-found" or root is None:
            self._status.setText(
                "Screensaver service not installed. It ships with Neuronix "
                "(default/services/screensaver) and is enabled after install."
            )
            self._enabled.setEnabled(False)
            self._restart_btn.setEnabled(False)
        else:
            self._enabled.setEnabled(True)
            self._restart_btn.setEnabled(True)
            self._status.setText(
                f"Service: {UNIT} — {state}"
                + (" (enabled)" if enabled else " (disabled)")
            )
        self._preview_btn.setEnabled(root is not None)
        self._loading = False

    def _on_preset_changed(self):
        data = self._idle_preset.currentData()
        custom = data == -1
        self._idle_spin.setEnabled(custom)
        if not custom and data is not None and data > 0:
            self._idle_spin.blockSignals(True)
            self._idle_spin.setValue(int(data))
            self._idle_spin.blockSignals(False)

    def _idle_seconds(self) -> int:
        data = self._idle_preset.currentData()
        if data == -1:
            return int(self._idle_spin.value())
        return int(data or DEFAULT_IDLE)

    def _selected_mode(self) -> str:
        return self._mode.currentData() or DEFAULT_MODE

    def _apply(self):
        idle = self._idle_seconds()
        mode = self._selected_mode()
        try:
            _write_config(idle, mode)
        except OSError as exc:
            QMessageBox.warning(self, "Screensaver", f"Could not write config:\n{exc}")
            return

        # Restart idle daemon so it picks up the new timeout/mode.
        state = _unit_state()
        if state != "not-found" and _unit_enabled():
            out, ok = _systemctl_user("restart", UNIT)
            if not ok:
                self._msg.setText(
                    f"Saved {CONFIG_PATH}, but restart failed: {out or 'unknown error'}"
                )
                self._load()
                return
            self._msg.setText(
                f"Saved — idle after {idle}s, style “{mode}”. Service restarted."
            )
        else:
            self._msg.setText(
                f"Saved — idle after {idle}s, style “{mode}”. "
                "Enable the idle service to use it automatically."
            )
        self._load()

    def _on_enabled_toggled(self, checked: bool):
        if self._loading:
            return
        if _unit_state() == "not-found":
            self._msg.setText("Service not installed.")
            self._load()
            return
        if checked:
            # Persist current UI values before enabling.
            try:
                _write_config(self._idle_seconds(), self._selected_mode())
            except OSError:
                pass
            _systemctl_user("daemon-reload")
            out, ok = _systemctl_user("enable", "--now", UNIT)
            self._msg.setText("Idle service enabled." if ok else f"Enable failed: {out}")
        else:
            out, ok = _systemctl_user("disable", "--now", UNIT)
            self._msg.setText("Idle service disabled." if ok else f"Disable failed: {out}")
        self._load()

    def _restart_service(self):
        if _unit_state() == "not-found":
            self._msg.setText("Service not installed.")
            return
        out, ok = _systemctl_user("restart", UNIT)
        self._msg.setText("Service restarted." if ok else f"Restart failed: {out}")
        self._load()

    def _preview(self):
        root = _service_root()
        if root is None:
            QMessageBox.warning(self, "Screensaver", "screensaver.py not found.")
            return
        mode = self._selected_mode()
        script = root / "screensaver.py"
        try:
            subprocess.Popen(
                [sys.executable, str(script), "--mode", mode],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._msg.setText(f"Preview started ({mode}). Move the mouse or press a key to dismiss.")
        except OSError as exc:
            QMessageBox.warning(self, "Screensaver", f"Could not launch preview:\n{exc}")
