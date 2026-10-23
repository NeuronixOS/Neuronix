"""Weather settings for hypr-settings (WeatherAPI.com)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from common import make_centered, separator

PREF_DIR = Path.home() / ".config" / "neuronix"
PREF_FILE = PREF_DIR / "weather.json"
SIGNUP_URL = "https://www.weatherapi.com/signup.aspx"
API_URL = "https://api.weatherapi.com/v1/forecast.json"


class _WeatherError(Exception):
    pass


def _read_prefs() -> dict[str, str]:
    if not PREF_FILE.is_file():
        return {"location": "", "api_key": ""}
    try:
        data = json.loads(PREF_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"location": "", "api_key": ""}
    if not isinstance(data, dict):
        return {"location": "", "api_key": ""}
    return {
        "location": str(data.get("location") or "").strip(),
        "api_key": str(data.get("api_key") or "").strip(),
    }


def _write_prefs(location: str, api_key: str) -> None:
    PREF_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"location": location, "api_key": api_key},
        indent=2,
    ) + "\n"
    tmp = PREF_FILE.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(PREF_FILE)
    os.chmod(PREF_FILE, 0o600)


def _error_message(body: str) -> str:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    err = data.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or "").strip()
    return ""


def _fetch(location: str, api_key: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "key": api_key,
            "q": location,
            "days": "3",
            "aqi": "no",
            "alerts": "no",
        }
    )
    req = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "neuronix-hypr-settings"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        message = _error_message(detail)
        if exc.code in (401, 403):
            raise _WeatherError(message or "API key was rejected.") from exc
        raise _WeatherError(message or f"Weather request failed ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise _WeatherError("Could not reach weatherapi.com.") from exc
    except TimeoutError as exc:
        raise _WeatherError("Weather request timed out.") from exc
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _WeatherError("Could not read the weather response.") from exc
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        raise _WeatherError(str(data["error"].get("message") or "Weather request failed."))
    if not isinstance(data, dict):
        raise _WeatherError("Could not read the weather response.")
    return data


class _FetchThread(QThread):
    done = Signal(object, str)

    def __init__(self, location: str, api_key: str, parent=None):
        super().__init__(parent)
        self._location = location
        self._api_key = api_key

    def run(self) -> None:
        try:
            data = _fetch(self._location, self._api_key)
        except _WeatherError as exc:
            self.done.emit(None, str(exc))
            return
        except Exception:
            self.done.emit(None, "Could not read the weather response.")
            return
        self.done.emit(data, "")


def _temp(value) -> str:
    try:
        return f"{float(value):.0f}°F"
    except (TypeError, ValueError):
        return "—"


def _place(data: dict) -> str:
    loc = data.get("location") if isinstance(data.get("location"), dict) else {}
    parts = [str(loc.get("name") or "").strip(), str(loc.get("region") or "").strip()]
    parts = [p for p in parts if p]
    country = str(loc.get("country") or "").strip()
    if country and country not in parts:
        parts.append(country)
    return ", ".join(parts) or "Current conditions"


def _current_lines(data: dict) -> tuple[str, str]:
    cur = data.get("current") if isinstance(data.get("current"), dict) else {}
    cond = cur.get("condition") if isinstance(cur.get("condition"), dict) else {}
    text = str(cond.get("text") or "Unknown").strip()
    headline = f"{_temp(cur.get('temp_f'))}  {text}"
    wind = cur.get("wind_mph")
    try:
        wind_s = f"{float(wind):.0f} mph"
    except (TypeError, ValueError):
        wind_s = "—"
    direction = str(cur.get("wind_dir") or "").strip()
    if direction:
        wind_s = f"{wind_s} {direction}"
    humidity = cur.get("humidity")
    try:
        humidity_s = f"{int(humidity)}%"
    except (TypeError, ValueError):
        humidity_s = "—"
    detail = (
        f"Feels like {_temp(cur.get('feelslike_f'))}"
        f"  ·  Humidity {humidity_s}"
        f"  ·  Wind {wind_s}"
    )
    return headline, detail


def _forecast_lines(data: dict) -> list[str]:
    block = data.get("forecast") if isinstance(data.get("forecast"), dict) else {}
    days = block.get("forecastday") if isinstance(block.get("forecastday"), list) else []
    lines: list[str] = []
    for day in days[:3]:
        if not isinstance(day, dict):
            continue
        info = day.get("day") if isinstance(day.get("day"), dict) else {}
        cond = info.get("condition") if isinstance(info.get("condition"), dict) else {}
        date = str(day.get("date") or "").strip()
        label = date or "—"
        try:
            from datetime import datetime

            parsed = datetime.strptime(date, "%Y-%m-%d")
            label = f"{parsed.strftime('%a %b')} {parsed.day}"
        except (TypeError, ValueError):
            pass
        text = str(cond.get("text") or "").strip() or "—"
        lines.append(
            f"{label}    {_temp(info.get('mintemp_f'))} – {_temp(info.get('maxtemp_f'))}    {text}"
        )
    return lines


class WeatherTab(QWidget):
    def __init__(self):
        super().__init__()
        self._thread: _FetchThread | None = None
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(make_centered(self, max_width=720))
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("Weather")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self._intro = QLabel(
            "Current conditions and a 3-day forecast from WeatherAPI.com. "
            "The key stays in ~/.config/neuronix/weather.json on this machine."
        )
        self._intro.setObjectName("statusLabel")
        self._intro.setWordWrap(True)
        root.addWidget(self._intro)

        self._signup = QLabel(
            f'<a href="{SIGNUP_URL}">Get a free key at weatherapi.com</a>'
        )
        self._signup.setObjectName("statusLabel")
        self._signup.setOpenExternalLinks(True)
        root.addWidget(self._signup)
        root.addWidget(separator())

        sec = QLabel("Location and key")
        sec.setObjectName("sectionTitle")
        root.addWidget(sec)

        self._location = QLineEdit()
        self._location.setPlaceholderText("City, ZIP, or lat,lon")
        root.addWidget(self._location)

        self._key = QLineEdit()
        self._key.setPlaceholderText("WeatherAPI.com key")
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.textChanged.connect(self._sync_help)
        root.addWidget(self._key)

        show_row = QHBoxLayout()
        self._show_key = QCheckBox("Show key")
        self._show_key.toggled.connect(
            lambda on: self._key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        show_row.addWidget(self._show_key)
        show_row.addStretch()
        save = QPushButton("Save")
        save.clicked.connect(self._save)
        show_row.addWidget(save)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        show_row.addWidget(refresh)
        root.addLayout(show_row)
        root.addWidget(separator())

        now = QLabel("Now")
        now.setObjectName("sectionTitle")
        root.addWidget(now)

        self._place = QLabel("—")
        self._place.setObjectName("statusLabel")
        self._place.setWordWrap(True)
        root.addWidget(self._place)

        self._headline = QLabel("")
        self._headline.setWordWrap(True)
        root.addWidget(self._headline)

        self._detail = QLabel("")
        self._detail.setObjectName("statusLabel")
        self._detail.setWordWrap(True)
        root.addWidget(self._detail)
        root.addWidget(separator())

        forecast = QLabel("Forecast")
        forecast.setObjectName("sectionTitle")
        root.addWidget(forecast)

        self._days: list[QLabel] = []
        for _ in range(3):
            lbl = QLabel("—")
            lbl.setWordWrap(True)
            root.addWidget(lbl)
            self._days.append(lbl)

        self._status = QLabel("")
        self._status.setObjectName("statusLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch()

    def _sync_help(self, *_args) -> None:
        show = not bool(self._key.text().strip())
        self._intro.setVisible(show)
        self._signup.setVisible(show)

    def _load(self):
        prefs = _read_prefs()
        self._location.setText(prefs["location"])
        self._key.setText(prefs["api_key"])
        self._sync_help()
        self._refresh()

    def _save(self):
        location = self._location.text().strip()
        api_key = self._key.text().strip()
        try:
            _write_prefs(location, api_key)
        except OSError as exc:
            self._status.setText(f"Could not save weather settings: {exc}")
            return
        self._status.setText("Saved.")
        self._refresh()

    def _refresh(self):
        location = self._location.text().strip()
        api_key = self._key.text().strip()
        if not api_key:
            self._clear_report()
            self._status.setText("Add a WeatherAPI.com key, then save.")
            return
        if not location:
            self._clear_report()
            self._status.setText("Enter a city, ZIP, or lat,lon.")
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self._status.setText("Loading weather…")
        self._thread = _FetchThread(location, api_key, self)
        self._thread.done.connect(self._on_fetch)
        self._thread.start()

    def _clear_report(self):
        self._place.setText("—")
        self._headline.setText("")
        self._detail.setText("")
        for lbl in self._days:
            lbl.setText("—")

    def _on_fetch(self, data, error: str):
        if error or not isinstance(data, dict):
            self._clear_report()
            self._status.setText(error or "Could not read the weather response.")
            return
        headline, detail = _current_lines(data)
        self._place.setText(_place(data))
        self._headline.setText(headline)
        self._detail.setText(detail)
        lines = _forecast_lines(data)
        for i, lbl in enumerate(self._days):
            lbl.setText(lines[i] if i < len(lines) else "—")
        self._status.setText("Updated.")
