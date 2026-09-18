"""Date & Time settings for hypr-settings."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from common import make_centered, run, separator

WAYBAR_CONF = Path.home() / ".config/waybar/config"
PREF_DIR = Path.home() / ".config/neuronix"
PREF_FILE = PREF_DIR / "clock-format"


def _current_fmt() -> str:
    if PREF_FILE.is_file():
        try:
            return PREF_FILE.read_text(encoding="utf-8").strip() or "12"
        except OSError:
            pass
    return "12"


def _apply_waybar_format(mode: str) -> bool:
    PREF_DIR.mkdir(parents=True, exist_ok=True)
    PREF_FILE.write_text(f"{mode}\n", encoding="utf-8")
    if not WAYBAR_CONF.is_file():
        return True
    fmt = "{:%a %b %d  %H:%M}" if mode == "24" else "{:%a %b %d  %I:%M %p}"
    try:
        cfg = json.loads(WAYBAR_CONF.read_text(encoding="utf-8"))
        cfg.setdefault("clock", {})["format"] = fmt
        WAYBAR_CONF.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    except Exception:
        return False
    # Soft-reload waybar
    try:
        subprocess.run(["pkill", "-USR2", "-x", "waybar"], check=False, timeout=2)
    except Exception:
        pass
    return True


def _list_timezones() -> list[str]:
    out, ok = run(["timedatectl", "list-timezones"], timeout=8)
    if not ok:
        return ["UTC"]
    return [line.strip() for line in out.splitlines() if line.strip()] or ["UTC"]


def _current_timezone() -> str:
    out, ok = run(["timedatectl", "show", "-p", "Timezone", "--value"], timeout=3)
    return out.strip() if ok and out.strip() else "UTC"


class DateTimeTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(make_centered(self, max_width=720))
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("Date & Time")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self._now_lbl = QLabel("")
        self._now_lbl.setObjectName("statusLabel")
        self._now_lbl.setWordWrap(True)
        root.addWidget(self._now_lbl)
        root.addWidget(separator())

        sec = QLabel("Waybar clock")
        sec.setObjectName("sectionTitle")
        root.addWidget(sec)

        row = QHBoxLayout()
        self._fmt_lbl = QLabel("")
        row.addWidget(self._fmt_lbl)
        row.addStretch()
        self._fmt_btn = QPushButton("Toggle 12/24-hour")
        self._fmt_btn.clicked.connect(self._toggle_fmt)
        row.addWidget(self._fmt_btn)
        root.addLayout(row)
        root.addWidget(separator())

        sec2 = QLabel("Set system date & time")
        sec2.setObjectName("sectionTitle")
        root.addWidget(sec2)

        self._cal = QCalendarWidget()
        self._cal.setGridVisible(True)
        root.addWidget(self._cal)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time (24h)"))
        self._time = QTimeEdit()
        self._time.setDisplayFormat("HH:mm")
        self._time.setTime(QTime.currentTime())
        time_row.addWidget(self._time)
        time_row.addStretch()
        apply_dt = QPushButton("Apply date & time")
        apply_dt.clicked.connect(self._apply_datetime)
        time_row.addWidget(apply_dt)
        root.addLayout(time_row)
        root.addWidget(separator())

        sec3 = QLabel("Time zone")
        sec3.setObjectName("sectionTitle")
        root.addWidget(sec3)

        tz_row = QHBoxLayout()
        self._tz = QComboBox()
        self._tz.setEditable(True)
        self._tz.setInsertPolicy(QComboBox.NoInsert)
        tz_row.addWidget(self._tz, stretch=1)
        apply_tz = QPushButton("Apply time zone")
        apply_tz.clicked.connect(self._apply_timezone)
        tz_row.addWidget(apply_tz)
        root.addLayout(tz_row)

        self._status = QLabel("")
        self._status.setObjectName("statusLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch()

    def _load(self):
        now = datetime.now().strftime("%A, %B %d %Y  %I:%M %p")
        tz = _current_timezone()
        self._now_lbl.setText(f"{now}\nTimezone: {tz}")
        mode = _current_fmt()
        self._fmt_lbl.setText(f"Current format: {'24-hour' if mode == '24' else '12-hour'}")
        zones = _list_timezones()
        self._tz.blockSignals(True)
        self._tz.clear()
        self._tz.addItems(zones)
        idx = self._tz.findText(tz)
        if idx >= 0:
            self._tz.setCurrentIndex(idx)
        else:
            self._tz.setEditText(tz)
        self._tz.blockSignals(False)
        self._cal.setSelectedDate(QDate.currentDate())
        self._time.setTime(QTime.currentTime())

    def _toggle_fmt(self):
        mode = "12" if _current_fmt() == "24" else "24"
        if _apply_waybar_format(mode):
            self._status.setText(f"Waybar clock set to {'24-hour' if mode == '24' else '12-hour'}.")
        else:
            self._status.setText("Saved preference, but could not update waybar config.")
        self._load()

    def _apply_datetime(self):
        d = self._cal.selectedDate()
        t = self._time.time()
        iso = f"{d.year():04d}-{d.month():02d}-{d.day():02d} {t.hour():02d}:{t.minute():02d}:00"
        try:
            r = subprocess.run(
                ["pkexec", "timedatectl", "set-time", iso],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Date & Time", f"Failed: {exc}")
            return
        if r.returncode == 0:
            self._status.setText(f"System time set to {iso}")
            self._load()
        else:
            err = (r.stderr or r.stdout or "need admin rights").strip()
            QMessageBox.warning(self, "Date & Time", f"Failed to set system time:\n{err}")

    def _apply_timezone(self):
        tz = self._tz.currentText().strip()
        if not tz:
            return
        try:
            r = subprocess.run(
                ["pkexec", "timedatectl", "set-timezone", tz],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Time zone", f"Failed: {exc}")
            return
        if r.returncode == 0:
            self._status.setText(f"Time zone set to {tz}")
            self._load()
        else:
            err = (r.stderr or r.stdout or "need admin rights").strip()
            QMessageBox.warning(self, "Time zone", f"Failed to set time zone:\n{err}")
