import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from config import CITY, OVERPASS_CACHE_TTL_SECONDS, OVERPASS_URL
from database import Database

logger = logging.getLogger(__name__)


class HotspotServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class HotspotResult:
    areas: list[dict[str, Any]]
    is_stale: bool


def _overpass_query() -> str:
    south, west, north, east = CITY.bbox
    bounds = f"({south},{west},{north},{east})"
    return f"""
    [out:json][timeout:25];
    (
      nwr["railway"~"station|halt"]{bounds};
      nwr["amenity"~"bus_station|marketplace|hospital|university|college"]{bounds};
      nwr["shop"="mall"]{bounds};
      nwr["office"]{bounds};
      nwr["public_transport"="station"]{bounds};
    );
    out center tags;
    """


def _category(tags: dict[str, str]) -> str | None:
    if tags.get("railway") in {"station", "halt"}:
        return "station"
    if tags.get("amenity") == "bus_station" or tags.get("public_transport") == "station":
        return "terminal"
    if tags.get("amenity") == "marketplace":
        return "market"
    if tags.get("shop") == "mall":
        return "mall"
    if tags.get("amenity") == "hospital":
        return "hospital"
    if tags.get("amenity") in {"university", "college"}:
        return "campus"
    if "office" in tags:
        return "office"
    return None


def _parse_areas(payload: dict[str, Any]) -> list[dict[str, Any]]:
    areas: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        category = _category(tags)
        name = tags.get("name")
        if category is None or not name:
            continue
        coordinates = element.get("center", element)
        latitude = coordinates.get("lat")
        longitude = coordinates.get("lon")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        osm_type = element.get("type")
        osm_id = element.get("id")
        if not isinstance(osm_type, str) or not isinstance(osm_id, int):
            continue
        identity = (osm_type, osm_id)
        if identity in seen:
            continue
        seen.add(identity)
        areas.append(
            {
                "osm_type": osm_type,
                "osm_id": osm_id,
                "name": str(name),
                "category": category,
                "latitude": float(latitude),
                "longitude": float(longitude),
            }
        )
    return areas


class HotspotService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_areas(self) -> HotspotResult:
        cached = self.database.get_areas(CITY.name)
        cache_is_fresh = bool(cached) and (
            time.time()
            - _timestamp_seconds(cached[0]["updated_at"])
            < OVERPASS_CACHE_TTL_SECONDS
        )
        if cache_is_fresh:
            return HotspotResult(cached, is_stale=False)

        try:
            response = requests.post(
                OVERPASS_URL,
                data={"data": _overpass_query()},
                timeout=35,
                headers={"User-Agent": "DriverAssistantBot/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
                raise ValueError("Format respons Overpass tidak valid.")
            areas = _parse_areas(payload)
            if not areas:
                raise ValueError("Overpass tidak mengembalikan lokasi yang dapat digunakan.")
            self.database.replace_areas(CITY.name, areas)
            return HotspotResult(areas, is_stale=False)
        except (requests.RequestException, ValueError) as error:
            logger.warning("Gagal memperbarui data hotspot OSM: %s", error)
            if cached:
                return HotspotResult(cached, is_stale=True)
            raise HotspotServiceError(
                "Data lokasi OpenStreetMap belum tersedia. Coba lagi beberapa saat."
            ) from error


def _timestamp_seconds(timestamp: str) -> float:
    return datetime.fromisoformat(timestamp).timestamp()
