from dataclasses import dataclass
from math import ceil, floor, isfinite

from config import (
    PEAK_PRICE_MULTIPLIER,
    PICKUP_FEE,
    PRICE_PER_KM,
    PRICE_RANGE_MARGIN,
    RAIN_PRICE_MULTIPLIER,
)


@dataclass(frozen=True)
class PriceSuggestion:
    low: int
    high: int
    is_peak: bool
    is_raining: bool


def suggest_price(distance_km: float, is_peak: bool, is_raining: bool) -> PriceSuggestion:
    if not isfinite(distance_km) or not 0 < distance_km <= 300:
        raise ValueError("Jarak harus lebih dari 0 dan maksimal 300 km.")

    base = PRICE_PER_KM * distance_km + PICKUP_FEE
    multiplier = 1.0
    if is_peak:
        multiplier *= PEAK_PRICE_MULTIPLIER
    if is_raining:
        multiplier *= RAIN_PRICE_MULTIPLIER

    estimate = base * multiplier
    low = floor((estimate * (1 - PRICE_RANGE_MARGIN)) / 1_000) * 1_000
    high = ceil((estimate * (1 + PRICE_RANGE_MARGIN)) / 1_000) * 1_000
    return PriceSuggestion(
        low=max(1_000, low),
        high=max(1_000, high),
        is_peak=is_peak,
        is_raining=is_raining,
    )


def format_rupiah(amount: int) -> str:
    return f"Rp{amount:,}".replace(",", ".")
