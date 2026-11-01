from dataclasses import dataclass

import requests

from config import CITY


class WeatherUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Weather:
    is_raining: bool
    precipitation_mm: float


def get_current_weather() -> Weather:
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": CITY.latitude,
                "longitude": CITY.longitude,
                "current": "precipitation,weather_code",
                "timezone": "Asia/Jakarta",
            },
            timeout=10,
            headers={"User-Agent": "DriverAssistantBot/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        current = payload.get("current", {})
        precipitation = current.get("precipitation")
        weather_code = current.get("weather_code")
        if not isinstance(precipitation, (int, float)) or not isinstance(weather_code, int):
            raise ValueError("Format data cuaca tidak valid.")
    except (requests.RequestException, ValueError, AttributeError) as error:
        raise WeatherUnavailable("Data cuaca sementara tidak tersedia.") from error

    rainy_codes = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
    return Weather(
        is_raining=precipitation > 0 or weather_code in rainy_codes,
        precipitation_mm=float(precipitation),
    )
