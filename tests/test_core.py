import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot import _build_recap_message, _parse_accepted_at
from database import Database, DuplicateOrderError
from pricing import (
    format_price_table,
    format_rupiah,
    price_range_for_distance,
    suggest_price,
    validate_price_rates,
)
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

    def test_distance_price_ranges_use_upper_bound_and_round_up(self) -> None:
        self.assertEqual(price_range_for_distance(5, 1_950, 2_500), (10_000, 12_500))
        self.assertEqual(price_range_for_distance(15, 1_950, 2_500), (29_500, 37_500))
        self.assertEqual(
            price_range_for_distance(5, 2_000, 2_600),
            (10_000, 13_000),
        )

    def test_price_table_and_rate_validation(self) -> None:
        table = format_price_table(1_950, 2_500)
        self.assertIn("0–5 km    Rp10.000    Rp12.500", table)
        self.assertIn("5–10 km    Rp19.500    Rp25.000", table)
        self.assertIn(">20 km       Rp1.950 × jarak    Rp2.500 × jarak", table)
        with self.assertRaises(ValueError):
            validate_price_rates(2_600, 2_000)


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

    def test_order_id_prevents_duplicate_and_price_settings_persist_per_user(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            database.ensure_user(123, "driver")
            database.ensure_user(456, "another-driver")
            accepted_at = datetime(2026, 11, 2, 14, 13, tzinfo=CITY.timezone)
            database.add_order(123, 4.5, 20_000, accepted_at, "ORDER-123")
            with self.assertRaises(DuplicateOrderError):
                database.add_order(123, 4.5, 20_000, accepted_at, "ORDER-123")
            database.add_order(456, 4.5, 20_000, accepted_at, "ORDER-123")

            database.set_price_range(123, 2_000, 2_600)
            self.assertEqual(database.get_price_range(123, 1_950, 2_500), (2_000, 2_600))
            self.assertEqual(database.get_price_range(456, 1_950, 2_500), (1_950, 2_500))
            database.reset_price_range(123)
            self.assertEqual(database.get_price_range(123, 1_950, 2_500), (1_950, 2_500))

    def test_migrates_existing_order_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    city TEXT NOT NULL DEFAULT 'Bandung',
                    alerts_enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(user_id),
                    distance_km REAL NOT NULL,
                    price INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO users (user_id, username, created_at)
                VALUES (123, 'driver', '2026-11-02T00:00:00+00:00');
                INSERT INTO orders (user_id, distance_km, price, created_at)
                VALUES (123, 4.5, 20000, '2026-11-02T14:13:00+00:00');
                """
            )
            connection.close()

            database = Database(path)
            orders = database.get_orders(
                123,
                datetime(2026, 11, 2, tzinfo=timezone.utc),
                datetime(2026, 11, 3, tzinfo=timezone.utc),
            )
            self.assertEqual(orders[0]["completed_at"], "2026-11-02T14:13:00+00:00")
            self.assertIsNone(orders[0]["accepted_at"])
            self.assertTrue(orders[0]["order_id"].startswith("legacy-"))

    def test_wib_midnight_boundary_uses_local_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "test.sqlite3")
            database.ensure_user(123, "driver")
            completed_at = "2026-11-02T17:30:00+00:00"
            with database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO orders
                        (order_id, user_id, distance_km, price, accepted_at,
                         completed_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "MIDNIGHT-1",
                        123,
                        5,
                        15_000,
                        "2026-11-02T16:30:00+00:00",
                        completed_at,
                        completed_at,
                    ),
                )
            previous_day = database.get_orders(
                123,
                datetime(2026, 11, 2, tzinfo=CITY.timezone),
                datetime(2026, 11, 3, tzinfo=CITY.timezone),
            )
            following_day = database.get_orders(
                123,
                datetime(2026, 11, 3, tzinfo=CITY.timezone),
                datetime(2026, 11, 4, tzinfo=CITY.timezone),
            )
            self.assertEqual(previous_day, [])
            self.assertEqual(len(following_day), 1)


class RecapTests(unittest.TestCase):
    @staticmethod
    def _order(
        completed_local: datetime,
        accepted_local: datetime | None,
        price: int,
        distance: float = 10,
    ) -> dict[str, object]:
        return {
            "completed_at": completed_local.astimezone(timezone.utc).isoformat(),
            "accepted_at": (
                accepted_local.astimezone(timezone.utc).isoformat()
                if accepted_local is not None
                else None
            ),
            "price": price,
            "distance_km": distance,
        }

    def test_accepted_time_parser_supports_wib_times_and_rejects_future(self) -> None:
        now = datetime(2026, 11, 2, 15, 0, tzinfo=CITY.timezone)
        self.assertEqual(
            _parse_accepted_at("14:13", now),
            datetime(2026, 11, 2, 14, 13, tzinfo=CITY.timezone),
        )
        self.assertEqual(
            _parse_accepted_at("2026-11-01T23:30", now),
            datetime(2026, 11, 1, 23, 30, tzinfo=CITY.timezone),
        )
        with self.assertRaises(ValueError):
            _parse_accepted_at("15:01", now)

    def test_best_hour_uses_completion_time_not_report_time(self) -> None:
        orders = [
            self._order(
                datetime(2026, 11, 2, 14, 13, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 14, 0, tzinfo=CITY.timezone),
                30_000,
            ),
            self._order(
                datetime(2026, 11, 2, 20, 26, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 18, 50, tzinfo=CITY.timezone),
                26_000,
            ),
        ]
        message = _build_recap_message(
            orders,
            datetime(2026, 11, 2, 21, 14, tzinfo=CITY.timezone),
            1_950,
            2_500,
        )
        self.assertIn("Jam terbaik: 14.00–15.00 (Rp30.000)", message)
        self.assertNotIn("21.00–22.00", message)
        self.assertIn("Durasi narik: 6 j 26 m", message)

    def test_eight_order_example_is_stable_across_report_times(self) -> None:
        orders = [
            self._order(
                datetime(2026, 11, 2, 14, 30, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 14, 13, tzinfo=CITY.timezone),
                15_000,
                5,
            ),
            self._order(
                datetime(2026, 11, 2, 15, 20, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 14, 40, tzinfo=CITY.timezone),
                12_000,
                6,
            ),
            self._order(
                datetime(2026, 11, 2, 16, 15, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 15, 30, tzinfo=CITY.timezone),
                18_000,
                7,
            ),
            self._order(
                datetime(2026, 11, 2, 17, 20, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 16, 50, tzinfo=CITY.timezone),
                17_000,
                8,
            ),
            self._order(
                datetime(2026, 11, 2, 18, 10, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 17, 35, tzinfo=CITY.timezone),
                16_000,
                7,
            ),
            self._order(
                datetime(2026, 11, 2, 19, 10, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 18, 30, tzinfo=CITY.timezone),
                21_000,
                9,
            ),
            self._order(
                datetime(2026, 11, 2, 19, 45, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 18, 45, tzinfo=CITY.timezone),
                26_000,
                8,
            ),
            self._order(
                datetime(2026, 11, 2, 20, 26, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 19, 45, tzinfo=CITY.timezone),
                10_100,
                8.1,
            ),
        ]
        early_report = _build_recap_message(
            orders,
            datetime(2026, 11, 2, 21, 14, tzinfo=CITY.timezone),
            1_950,
            2_500,
        )
        late_report = _build_recap_message(
            orders,
            datetime(2026, 11, 2, 23, 0, tzinfo=CITY.timezone),
            1_950,
            2_500,
        )
        expected_best_hour = "Jam terbaik: 19.00–20.00 (Rp47.000)"
        self.assertIn(expected_best_hour, early_report)
        self.assertIn(expected_best_hour, late_report)
        self.assertNotIn("21.00–22.00", early_report)
        self.assertIn("Pendapatan: Rp135.100", early_report)
        self.assertIn("Jarak tercatat: 58.1 km", early_report)
        self.assertIn("Durasi narik: 6 j 13 m", early_report)
        self.assertIn("Pendapatan/jam: Rp21.700", early_report)
        self.assertIn("Pendapatan/km: Rp2.325", early_report)

    def test_tied_best_hour_prefers_more_orders_and_empty_day_shows_dash(self) -> None:
        orders = [
            self._order(
                datetime(2026, 11, 2, 14, 20, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 13, 30, tzinfo=CITY.timezone),
                10_000,
            ),
            self._order(
                datetime(2026, 11, 2, 15, 10, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 14, 30, tzinfo=CITY.timezone),
                5_000,
            ),
            self._order(
                datetime(2026, 11, 2, 15, 40, tzinfo=CITY.timezone),
                datetime(2026, 11, 2, 15, 0, tzinfo=CITY.timezone),
                5_000,
            ),
        ]
        message = _build_recap_message(
            orders,
            datetime(2026, 11, 2, 21, 14, tzinfo=CITY.timezone),
            1_950,
            2_500,
        )
        self.assertIn("Jam terbaik: 15.00–16.00 (Rp10.000)", message)

        empty_message = _build_recap_message(
            [],
            datetime(2026, 11, 2, 21, 14, tzinfo=CITY.timezone),
            1_950,
            2_500,
        )
        self.assertIn("Jam terbaik: -", empty_message)

    def test_recap_flags_missing_accepted_time_and_compares_income_per_km(self) -> None:
        orders = [
            self._order(
                datetime(2026, 11, 2, 20, 26, tzinfo=CITY.timezone),
                None,
                135_100,
                58.1,
            )
        ]
        message = _build_recap_message(
            orders,
            datetime(2026, 11, 2, 21, 14, tzinfo=CITY.timezone),
            1_950,
            2_500,
        )
        self.assertIn("Durasi narik: tidak tersedia", message)
        self.assertIn("Pendapatan/jam: -", message)
        self.assertIn("Rp2.325 (patokan Rp1.950–Rp2.500, dalam rentang)", message)


if __name__ == "__main__":
    unittest.main()
