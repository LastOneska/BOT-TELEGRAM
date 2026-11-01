from datetime import date, datetime
from typing import Any

import holidays

from config import CATEGORIES, CITY

INDONESIAN_HOLIDAYS = holidays.country_holidays("ID")


def is_peak_time(moment: datetime) -> bool:
    local = moment.astimezone(CITY.timezone)
    minute = local.hour * 60 + local.minute
    return any(
        start <= minute < end
        for category in CATEGORIES.values()
        for start, end in category.peak_windows
    )


def score_hotspot(
    area: dict[str, Any],
    moment: datetime,
    is_raining: bool,
) -> float:
    category = CATEGORIES.get(area["category"])
    if category is None:
        return 0.0

    local = moment.astimezone(CITY.timezone)
    minute = local.hour * 60 + local.minute
    active = any(start <= minute < end for start, end in category.peak_windows)
    near_peak = any(
        0 <= start - minute <= 90 or 0 <= minute - end <= 60
        for start, end in category.peak_windows
    )
    time_factor = 1.5 if active else 0.9 if near_peak else 0.45
    if is_raining and area["category"] in {"mall", "hospital"}:
        weather_factor = 1.1
    elif is_raining and area["category"] == "market":
        weather_factor = 0.9
    else:
        weather_factor = 1.0
    holiday_factor = _holiday_factor(area["category"], local.date())
    return category.weight * time_factor * weather_factor * holiday_factor


def _holiday_factor(category: str, day: date) -> float:
    if day not in INDONESIAN_HOLIDAYS:
        return 1.0
    if category in {"mall", "market", "station", "terminal"}:
        return 1.15
    if category in {"office", "campus"}:
        return 0.65
    return 1.0


def next_peak_label(category_key: str, moment: datetime) -> str:
    category = CATEGORIES.get(category_key)
    if category is None:
        return "Jadwal belum tersedia"

    local = moment.astimezone(CITY.timezone)
    minute = local.hour * 60 + local.minute
    for start, end in category.peak_windows:
        if start <= minute < end:
            return f"sedang ramai hingga {_format_minute(end)}"
        if start > minute:
            return f"puncak berikutnya {_format_minute(start)}"
    next_start = category.peak_windows[0][0]
    return f"puncak berikutnya besok {_format_minute(next_start)}"


def format_category_schedule() -> str:
    lines = []
    for category in CATEGORIES.values():
        windows = " dan ".join(
            f"{_format_minute(start)}–{_format_minute(end)}"
            for start, end in category.peak_windows
        )
        lines.append(f"• {category.label}: {windows}")
    return "\n".join(lines)


def _format_minute(value: int) -> str:
    return f"{value // 60:02d}.{value % 60:02d}"
