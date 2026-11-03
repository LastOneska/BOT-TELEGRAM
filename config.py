from dataclasses import dataclass
from zoneinfo import ZoneInfo

TIMEZONE = "Asia/Jakarta"


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float
    bbox: tuple[float, float, float, float]
    timezone: ZoneInfo


@dataclass(frozen=True)
class HotspotCategory:
    label: str
    weight: float
    peak_windows: tuple[tuple[int, int], ...]


CITY = City(
    name="Bandung",
    latitude=-6.9175,
    longitude=107.6191,
    bbox=(-7.05, 107.52, -6.84, 107.75),
    timezone=ZoneInfo(TIMEZONE),
)

CATEGORIES = {
    "station": HotspotCategory("Stasiun", 1.2, ((6 * 60, 8 * 60 + 30), (16 * 60 + 30, 19 * 60))),
    "terminal": HotspotCategory("Terminal", 1.15, ((6 * 60, 9 * 60), (16 * 60, 19 * 60))),
    "campus": HotspotCategory("Kampus", 1.0, ((7 * 60, 9 * 60), (15 * 60, 18 * 60))),
    "mall": HotspotCategory("Mal", 1.0, ((11 * 60, 14 * 60), (17 * 60, 21 * 60))),
    "market": HotspotCategory("Pasar", 1.05, ((5 * 60, 8 * 60), (15 * 60, 18 * 60))),
    "hospital": HotspotCategory("Rumah sakit", 0.9, ((7 * 60, 10 * 60), (15 * 60, 19 * 60))),
    "office": HotspotCategory("Kawasan perkantoran", 0.95, ((7 * 60, 9 * 60), (16 * 60, 19 * 60))),
}

# Each reminder is scheduled 30 minutes before the listed peak window.
ALERT_SCHEDULE = (
    (4, 30, ("market",)),
    (5, 30, ("station", "terminal")),
    (6, 30, ("campus", "office")),
    (10, 30, ("mall",)),
    (14, 30, ("market", "campus", "hospital")),
    (15, 30, ("terminal", "office")),
    (16, 0, ("station",)),
    (16, 30, ("mall",)),
)

PRICE_PER_KM = 2_500
PICKUP_FEE = 5_000
PEAK_PRICE_MULTIPLIER = 1.15
RAIN_PRICE_MULTIPLIER = 1.10
PRICE_RANGE_MARGIN = 0.05
RP_PER_KM_MIN = 1_950
RP_PER_KM_MAX = 2_500
PEMBULATAN = 500

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
DATABASE_PATH = "driver_bot.sqlite3"
