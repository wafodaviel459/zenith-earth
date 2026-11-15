import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from main import AnalysisRequest, _create_demo_result, _load_cache


class NasaArchiveCacheTests(unittest.TestCase):
    def test_temporary_fallback_does_not_become_a_permanent_cache_hit(self):
        request = AnalysisRequest(
            city_name="Unknown city",
            country="Test",
            lat=10,
            lon=20,
            start_year=2015,
            end_year=2025,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("main.CACHE_DIR", Path(temp_dir)):
                main._save_cache(request, _create_demo_result(request, "Temporary fallback."))

                result = _load_cache(request)

        self.assertIsNone(result)

    def test_archived_city_cache_matches_accent_and_coordinate_variants(self):
        archived_request = AnalysisRequest(
            city_name="Yaoundé",
            country="Cameroun",
            lat=3.72256,
            lon=11.55327,
            start_year=2015,
            end_year=2025,
        )
        searched_request = AnalysisRequest(
            city_name="Yaounde",
            country="Cameroon",
            lat=3.8667,
            lon=11.5167,
            start_year=2015,
            end_year=2025,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("main.CACHE_DIR", Path(temp_dir)):
                cached_result = _create_demo_result(
                    archived_request,
                    "Cached fallback for archive coverage test.",
                )
                cached_result["city_aliases"] = ["Yaoundé", "Yaounde"]
                cached_result["archive_fallback"] = True
                main._save_cache(archived_request, cached_result)

                result = _load_cache(searched_request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["city"], "Yaounde")
        self.assertEqual(result["country"], "Cameroon")

    def test_archived_city_cache_matches_geocoder_name_and_nearby_coordinates(self):
        archived_request = AnalysisRequest(
            city_name="Marrakech",
            country="Maroc",
            lat=31.63416,
            lon=-7.99994,
            start_year=2015,
            end_year=2025,
        )
        searched_request = AnalysisRequest(
            city_name="Marrakech, Marrakech-Safi, Morocco",
            country="Morocco",
            lat=31.6295,
            lon=-7.9811,
            start_year=2015,
            end_year=2025,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("main.CACHE_DIR", Path(temp_dir)):
                cached_result = _create_demo_result(archived_request, "Archived cache test.")
                cached_result["data_source"] = "nasa_appeears"
                cached_result["city_aliases"] = ["Marrakech", "Marrakesh"]
                main._save_cache(archived_request, cached_result)

                result = _load_cache(searched_request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["city"], searched_request.city_name)

    def test_archived_city_cache_serves_requested_subperiod_without_nasa_call(self):
        archived_request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2015,
            end_year=2025,
        )
        subperiod_request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2018,
            end_year=2020,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("main.CACHE_DIR", Path(temp_dir)):
                cached_result = _create_demo_result(archived_request, "Archived model cache test.")
                cached_result["city_aliases"] = ["Ben Guerir"]
                cached_result["archive_fallback"] = True
                main._save_cache(archived_request, cached_result)

                result = _load_cache(subperiod_request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["period"], {"start_year": 2018, "end_year": 2020})
        self.assertEqual({point["date"][:4] for point in result["series"]}, {"2018", "2019", "2020"})


if __name__ == "__main__":
    unittest.main()
