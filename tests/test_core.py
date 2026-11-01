import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from database import Database
from pricing import format_rupiah, suggest_price
from prediction import next_peak_label, score_hotspot
from config import CITY
from services.hotspots import _parse_areas


class PricingTests(unittest.TestCase):
    def test_suggestion_includes_expected_range(self) -> None:
        suggestion = suggest_price(4.5, is_peak=False, is_raining=False)
        self.assertEqual((suggestion.low, suggestion.high), (15_000, 18_000))

    def test_busy_rain_period_increases_suggestion(self) -> None:
        ordinary = suggest_price(4.5, is_peak=False, is_raining=False)
        busy_rain = suggest_price(4.5, is_peak=True, is_raining=True)
        self.assertGreater(busy_rain.low, ordinary.low)

    def test_rejects_invalid_distance(self) -> None:
        for distance in (0, -1, float("inf")):
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                suggest_price(distance, is_peak=False, is_raining=False)

    def test_rupiah_format(self) -> None:
        self.assertEqual(format_rupiah(125_000), "Rp125.000")


class PredictionTests(unittest.TestCase):
    def test_active_peak_is_labeled(self) -> None:
        moment = datetime(2026, 11, 1, 6, 30, tzinfo=CITY.timezone)
        self.assertEqual(
            next_peak_label("station", moment),
            "sedang ramai hingga 08.30",
        )

    def test_active_area_scores_above_inactive_area(self) -> None:
        moment = datetime(2026, 11, 1, 7, 0, tzinfo=CITY.timezone)
        station = {"category": "station"}
        mall = {"category": "mall"}
        self.assertGreater(
            score_hotspot(station, moment, is_raining=False),
            score_hotspot(mall, moment, is_raining=False),
        )

    def test_rain_adjusts_indoor_and_market_scores_differently(self) -> None:
        moment = datetime(2026, 11, 1, 12, 0, tzinfo=CITY.timezone)
        mall = {"category": "mall"}
        market = {"category": "market"}
        self.assertGreater(
            score_hotspot(mall, moment, is_raining=True),
            score_hotspot(mall, moment, is_raining=False),
        )
        self.assertLess(
            score_hotspot(market, moment, is_raining=True),
            score_hotspot(market, moment, is_raining=False),
        )


class HotspotTests(unittest.TestCase):
    def test_parses_named_osm_locations_and_skips_unknowns(self) -> None:
        areas = _parse_areas(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 10,
                        "center": {"lat": -6.9, "lon": 107.6},
                        "tags": {"name": "Stasiun Contoh", "railway": "station"},
                    },
                    {
                        "type": "node",
                        "id": 11,
                        "lat": -6.91,
                        "lon": 107.61,
                        "tags": {"amenity": "cafe"},
                    },
                ]
            }
        )
        self.assertEqual(len(areas), 1)
        self.assertEqual(areas[0]["category"], "station")
        self.assertEqual(areas[0]["name"], "Stasiun Contoh")


class DatabaseTests(unittest.TestCase):
    def test_order_and_feedback_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            database.ensure_user(123, "driver")
            database.add_order(123, 4.5, 20_000)
            orders = database.get_orders(
                123,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2027, 1, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]["price"], 20_000)
            self.assertTrue(database.save_feedback(123, 456, "up"))
            self.assertFalse(database.save_feedback(123, 456, "up"))


if __name__ == "__main__":
    unittest.main()
