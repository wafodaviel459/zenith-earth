import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi import BackgroundTasks
import requests

import main
from main import AnalysisRequest, _assemble_result, _create_demo_result


class FallbackAndDataQualityTests(unittest.TestCase):
    def request(self, latitude: float) -> AnalysisRequest:
        return AnalysisRequest(
            city_name="Test location",
            country="Test",
            lat=latitude,
            lon=-40,
            start_year=2020,
            end_year=2022,
        )

    def test_polar_fallback_is_latitude_calibrated_and_reports_its_source(self) -> None:
        result = _create_demo_result(self.request(72), "AppEEARS unavailable.")
        january = next(point for point in result["series"] if point["date"] == "2020-01-01")
        july = next(point for point in result["series"] if point["date"] == "2020-07-01")

        self.assertEqual(result["data_source"], "fallback_model")
        self.assertIn("AppEEARS unavailable.", result["fallback_reason"])
        self.assertGreaterEqual(january["city_c"], -25)
        self.assertLess(january["city_c"], 0)
        self.assertGreater(july["city_c"], january["city_c"])

    def test_fallback_seasons_are_reversed_in_southern_hemisphere(self) -> None:
        result = _create_demo_result(self.request(-35), "offline")
        january = next(point for point in result["series"] if point["date"] == "2020-01-01")
        july = next(point for point in result["series"] if point["date"] == "2020-07-01")

        self.assertGreater(january["city_c"], july["city_c"])

    def test_background_sync_polls_every_30_seconds_for_45_minutes(self) -> None:
        self.assertEqual(main.APPEEARS_BACKGROUND_POLL_SECONDS, 30)
        self.assertEqual(main.APPEEARS_BACKGROUND_TIMEOUT_SECONDS, 45 * 60)

    @patch("main._save_cache")
    @patch("main._load_cache", return_value=None)
    @patch("main._earthdata_token")
    def test_auth_http_error_is_logged_and_exposed_as_fallback_reason(
        self,
        mock_token,
        _mock_load_cache,
        mock_save_cache,
    ) -> None:
        response = requests.Response()
        response.status_code = 401
        response.reason = "Unauthorized"
        response._content = b"Invalid Earthdata credentials"
        mock_token.side_effect = requests.HTTPError(response=response)

        with patch.dict(os.environ, {
            "NASA_EARTHDATA_USER": "test-earthdata-user",
            "NASA_EARTHDATA_PASS": "test-earthdata-password",
        }):
            with self.assertLogs("main", level="ERROR") as captured:
                result = asyncio.run(main.analyze(self.request(72), BackgroundTasks()))

        self.assertEqual(result["data_source"], "fallback_model")
        self.assertIn("HTTP 401 Unauthorized", result["fallback_reason"])
        self.assertIn("HTTP 401 Unauthorized", captured.output[0])
        mock_save_cache.assert_not_called()

    def test_annual_analysis_requires_six_valid_months_for_three_years(self) -> None:
        rows = [
            {"date": f"{year}-{month:02d}-01", "urban_c": 10, "rural_c": 9}
            for year, month_count in ((2020, 5), (2021, 12), (2022, 12))
            for month in range(1, month_count + 1)
        ]

        with self.assertRaises(HTTPException) as raised:
            _assemble_result(
                self.request(72),
                rows,
                rural_lat=72.4,
                rural_lon=-40,
                demo=False,
            )
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("6 mois par an", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
