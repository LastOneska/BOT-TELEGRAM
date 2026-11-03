from dataclasses import dataclass
from math import ceil, floor, isfinite

from config import (
    PEMBULATAN,
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


@dataclass(frozen=True)
class OfferAssessment:
    price_per_km: float
    minimum_price: int
    maximum_price: int
    status: str


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


def validate_price_rates(min_per_km: int, max_per_km: int) -> None:
    if min_per_km <= 0 or max_per_km <= 0:
        raise ValueError("Tarif per kilometer harus lebih dari 0.")
    if min_per_km > max_per_km:
        raise ValueError("Tarif minimum tidak boleh melebihi tarif maksimum.")


def _round_price_up(amount: float) -> int:
    return ceil(amount / PEMBULATAN) * PEMBULATAN


def price_range_for_distance(
    distance_km: float, min_per_km: int, max_per_km: int
) -> tuple[int, int]:
    validate_price_rates(min_per_km, max_per_km)
    if not isfinite(distance_km) or distance_km <= 0:
        raise ValueError("Jarak harus lebih dari 0 km.")
    return (
        _round_price_up(distance_km * min_per_km),
        _round_price_up(distance_km * max_per_km),
    )


def assess_offer(
    distance_km: float,
    offered_price: int,
    min_per_km: int,
    max_per_km: int,
) -> OfferAssessment:
    if not isfinite(distance_km) or not 0 < distance_km <= 300:
        raise ValueError("Jarak total harus lebih dari 0 dan maksimal 300 km.")
    if offered_price <= 0:
        raise ValueError("Tawaran harus lebih dari Rp0.")
    minimum_price, maximum_price = price_range_for_distance(
        distance_km, min_per_km, max_per_km
    )
    price_per_km = offered_price / distance_km
    if price_per_km < min_per_km:
        status = "di bawah patokan minimum"
    elif price_per_km > max_per_km:
        status = "di atas patokan maksimum"
    else:
        status = "dalam rentang patokan"
    return OfferAssessment(
        price_per_km=price_per_km,
        minimum_price=minimum_price,
        maximum_price=maximum_price,
        status=status,
    )


def format_price_table(min_per_km: int, max_per_km: int) -> str:
    validate_price_rates(min_per_km, max_per_km)
    lines = [
        "Saran harga — total jarak jemput + antar",
        "Jarak       Minimal       Maksimal",
    ]
    for lower_bound, upper_bound in ((0, 5), (5, 10), (10, 15), (15, 20)):
        minimum, maximum = price_range_for_distance(
            upper_bound, min_per_km, max_per_km
        )
        lines.append(
            f"{lower_bound}–{upper_bound} km    {format_rupiah(minimum)}    "
            f"{format_rupiah(maximum)}"
        )
    lines.extend(
        [
            f">20 km       {format_rupiah(min_per_km)} × jarak    "
            f"{format_rupiah(max_per_km)} × jarak",
            "Harga dibulatkan ke atas ke kelipatan Rp500.",
        ]
    )
    return "\n".join(lines)
