#!/usr/bin/env python3
"""Waybar weather module. Reads ~/.config/neuronix/weather.json."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PREFS = Path.home() / ".config" / "neuronix" / "weather.json"
API = "https://api.weatherapi.com/v1/forecast.json"


def emit(text: str, tooltip: str, klass: str = "weather") -> None:
    print(json.dumps({"text": text, "tooltip": tooltip, "class": klass}, ensure_ascii=False))


def _prefs() -> tuple[str, str]:
    try:
        data = json.loads(PREFS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("location") or "").strip(), str(data.get("api_key") or "").strip()


def _glyph(code, is_day: bool = True) -> str:
    """Symbols Nerd Font weather icons (day glyph, night glyph)."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = 0
    icons = {
        1000: ("\ue30d", "\ue32b"),  # clear
        1003: ("\ue302", "\ue32e"),  # partly cloudy
        1006: ("\ue312", "\ue312"),  # cloudy
        1009: ("\ue312", "\ue312"),  # overcast
        1030: ("\ue313", "\ue313"),  # mist
        1063: ("\ue30b", "\ue328"),  # patchy rain
        1066: ("\ue30a", "\ue327"),  # patchy snow
        1069: ("\ue306", "\ue323"),  # patchy sleet
        1072: ("\ue30b", "\ue328"),  # patchy freezing drizzle
        1087: ("\ue305", "\ue322"),  # thundery outbreaks
        1114: ("\ue31a", "\ue31a"),  # blowing snow
        1117: ("\ue31a", "\ue31a"),  # blizzard
        1135: ("\ue313", "\ue313"),  # fog
        1147: ("\ue313", "\ue313"),  # freezing fog
        1150: ("\ue30b", "\ue328"),
        1153: ("\ue30b", "\ue328"),
        1168: ("\ue306", "\ue323"),
        1171: ("\ue306", "\ue323"),
        1180: ("\ue309", "\ue326"),
        1183: ("\ue308", "\ue325"),
        1186: ("\ue308", "\ue325"),
        1189: ("\ue308", "\ue325"),
        1192: ("\ue308", "\ue325"),
        1195: ("\ue308", "\ue325"),
        1198: ("\ue306", "\ue323"),
        1201: ("\ue306", "\ue323"),
        1204: ("\ue306", "\ue323"),
        1207: ("\ue306", "\ue323"),
        1210: ("\ue30a", "\ue327"),
        1213: ("\ue30a", "\ue327"),
        1216: ("\ue31a", "\ue31a"),
        1219: ("\ue31a", "\ue31a"),
        1222: ("\ue31a", "\ue31a"),
        1225: ("\ue31a", "\ue31a"),
        1237: ("\ue314", "\ue314"),  # ice pellets
        1240: ("\ue309", "\ue326"),
        1243: ("\ue309", "\ue326"),
        1246: ("\ue318", "\ue318"),
        1249: ("\ue306", "\ue323"),
        1252: ("\ue306", "\ue323"),
        1255: ("\ue30a", "\ue327"),
        1258: ("\ue31a", "\ue31a"),
        1261: ("\ue314", "\ue314"),
        1264: ("\ue314", "\ue314"),
        1273: ("\ue30f", "\ue32a"),
        1276: ("\ue30f", "\ue32a"),
        1279: ("\ue30e", "\ue329"),
        1282: ("\ue30e", "\ue329"),
    }
    pair = icons.get(code, ("\ue312", "\ue312"))
    return pair[0] if is_day else pair[1]


def _temp(value) -> str:
    try:
        return f"{float(value):.0f}°"
    except (TypeError, ValueError):
        return "—"


def _fetch(location: str, api_key: str) -> dict:
    query = urllib.parse.urlencode(
        {"key": api_key, "q": location, "days": "3", "aqi": "no", "alerts": "no"}
    )
    req = urllib.request.Request(
        f"{API}?{query}",
        headers={"User-Agent": "neuronix-waybar"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError("bad response")
    if isinstance(data.get("error"), dict):
        raise ValueError(str(data["error"].get("message") or "Weather request failed."))
    return data


def _tooltip(data: dict) -> str:
    loc = data.get("location") if isinstance(data.get("location"), dict) else {}
    cur = data.get("current") if isinstance(data.get("current"), dict) else {}
    cond = cur.get("condition") if isinstance(cur.get("condition"), dict) else {}
    place = ", ".join(
        part
        for part in (
            str(loc.get("name") or "").strip(),
            str(loc.get("region") or "").strip(),
        )
        if part
    ) or "Weather"
    raw_day = cur.get("is_day")
    is_day = True if raw_day is None else bool(int(raw_day))
    now_icon = _glyph(cond.get("code"), is_day)
    lines = [
        place,
        f"{now_icon}  {_temp(cur.get('temp_f'))}  {str(cond.get('text') or '').strip()}".strip(),
        f"Feels like {_temp(cur.get('feelslike_f'))}",
    ]
    block = data.get("forecast") if isinstance(data.get("forecast"), dict) else {}
    days = block.get("forecastday") if isinstance(block.get("forecastday"), list) else []
    for day in days[:3]:
        if not isinstance(day, dict):
            continue
        info = day.get("day") if isinstance(day.get("day"), dict) else {}
        day_cond = info.get("condition") if isinstance(info.get("condition"), dict) else {}
        date = str(day.get("date") or "").strip()
        label = date
        try:
            from datetime import datetime

            parsed = datetime.strptime(date, "%Y-%m-%d")
            label = f"{parsed.strftime('%a')} {parsed.day}"
        except ValueError:
            pass
        lines.append(
            f"{_glyph(day_cond.get('code'), True)}  {label}  {_temp(info.get('mintemp_f'))}–{_temp(info.get('maxtemp_f'))}  {str(day_cond.get('text') or '').strip()}"
        )
    return "\n".join(lines)


def main() -> int:
    location, api_key = _prefs()
    if not api_key or not location:
        emit("—", "Set a location and WeatherAPI key in Settings → Weather", "weather-setup")
        return 0
    try:
        data = _fetch(location, api_key)
    except urllib.error.HTTPError as exc:
        message = "Could not load weather."
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace"))
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                message = str(body["error"].get("message") or message)
        except Exception:
            if exc.code in (401, 403):
                message = "WeatherAPI key was rejected."
        emit("—", message, "weather-error")
        return 0
    except Exception:
        emit("—", "Could not reach weatherapi.com.", "weather-error")
        return 0
    cur = data.get("current") if isinstance(data.get("current"), dict) else {}
    cond = cur.get("condition") if isinstance(cur.get("condition"), dict) else {}
    raw_day = cur.get("is_day")
    is_day = True if raw_day is None else bool(int(raw_day))
    emit(f"{_glyph(cond.get('code'), is_day)}  {_temp(cur.get('temp_f'))}", _tooltip(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
