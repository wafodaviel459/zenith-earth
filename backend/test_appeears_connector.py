import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks

import main
from main import AnalysisRequest


class MockResponse:
    def __init__(self, payload=None, content=b""):
        self.payload = payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class AppeearsConnectorTests(unittest.TestCase):
    @patch("main.requests.post")
    @patch("main.requests.get")
    @patch("main._earthdata_token")
    @patch("main._create_or_resume_appeears_task")
    @patch("main._load_cache")
    def test_analyze_returns_cached_result_without_nasa_requests(
        self,
        mock_load_cache,
        mock_create_or_resume,
        mock_token,
        mock_get,
        mock_post,
    ):
        request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2020,
            end_year=2022,
        )
        cached_result = {"status": "complete", "cache_hit": True}
        mock_load_cache.return_value = cached_result

        with patch.dict(os.environ, {
            "NASA_EARTHDATA_USER": "test-user",
            "NASA_EARTHDATA_PASS": "test-password",
        }):
            result = asyncio.run(main.analyze(request, BackgroundTasks()))

        self.assertIs(result, cached_result)
        mock_load_cache.assert_called_once_with(request)
        mock_create_or_resume.assert_not_called()
        mock_token.assert_not_called()
        mock_get.assert_not_called()
        mock_post.assert_not_called()

    @patch("main.requests.post")
    def test_submits_task_and_persists_its_id_before_background_polling(self, mock_post):
        mock_post.return_value = MockResponse({"task_id": "task-123"})
        request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2020,
            end_year=2022,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            pending_tasks_file = Path(temp_dir) / "pending_tasks.json"
            with patch("main.PENDING_TASKS_FILE", pending_tasks_file):
                task_id = main._create_or_resume_appeears_task("token-test", request)
                indexed_task = json.loads(pending_tasks_file.read_text(encoding="utf-8"))[
                    main._pending_task_key(request)
                ]
                self.assertEqual(indexed_task["task_id"], "task-123")
                self.assertEqual(indexed_task["request"]["city_name"], request.city_name)

        self.assertEqual(task_id, "task-123")
        task = mock_post.call_args.kwargs["json"]
        self.assertEqual(mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer token-test")
        self.assertEqual(task["task_type"], "point")
        self.assertEqual(
            task["params"]["layers"],
            [{"product": "MOD11A2.061", "layer": "LST_Day_1km"}],
        )
        self.assertEqual(
            task["params"]["dates"],
            [{"startDate": "01-01-2020", "endDate": "12-31-2022"}],
        )
        mock_post.assert_called_once()

    @patch("main.requests.post")
    @patch("main._earthdata_token", return_value="token-test")
    @patch("main._schedule_appeears_task")
    @patch("main._load_cache", return_value=None)
    def test_analyze_resumes_completed_task_and_caches_without_new_submission(
        self,
        _mock_load_cache,
        mock_schedule,
        _mock_token,
        mock_post,
    ):
        request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2020,
            end_year=2022,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            pending_tasks_file = Path(temp_dir) / "pending_tasks.json"
            pending_tasks_file.write_text(
                json.dumps({main._pending_task_key(request): "task-existing"}),
                encoding="utf-8",
            )
            with (
                patch("main.PENDING_TASKS_FILE", pending_tasks_file),
                patch.dict(os.environ, {
                    "NASA_EARTHDATA_USER": "test-user",
                    "NASA_EARTHDATA_PASS": "test-password",
                }),
            ):
                result = asyncio.run(main.analyze(request, BackgroundTasks()))

            self.assertEqual(result["status"], "queued_nasa")
            _mock_load_cache.assert_called_once_with(request)
            _mock_token.assert_called_once()
            mock_post.assert_not_called()
            mock_schedule.assert_called_once_with(
                unittest.mock.ANY,
                "token-test",
                request,
                "task-existing",
            )
            self.assertTrue(pending_tasks_file.exists())

    def test_imported_kelvin_csv_values_are_parsed_as_kelvin(self):
        request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2020,
            end_year=2022,
        )
        content = (
            "Category,ID,Latitude,Longitude,Date,MOD11A2_061_LST_Day_1km\n"
            "city,urban,32.23,-7.95,2020-01-01,290.96\n"
            "rural,rural,32.63,-7.95,2020-01-01,280.96\n"
        ).encode()

        rows, _, _ = main._rows_from_appeears_csv_contents(
            [("results.csv", content)],
            request,
        )

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["urban_c"], 17.81)
        self.assertAlmostEqual(rows[0]["rural_c"], 7.81)

    @patch("main.requests.get")
    def test_background_sync_downloads_completed_task_and_removes_pending_entry(self, mock_get):
        request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2015,
            end_year=2020,
        )
        csv_lines = ["Category,ID,Latitude,Longitude,Date,MOD11A2_061_LST_Day_1km"]
        for year in range(2015, 2021):
            for month in range(1, 7):
                date = f"{year}-{month:02d}-15"
                csv_lines.extend([
                    f"city,urban,32.23,-7.95,{date},300",
                    f"rural,rural,32.63,-7.95,{date},295",
                ])
        mock_get.side_effect = [
            MockResponse({"status": "done"}),
            MockResponse({"files": [{"file_id": "file-1", "file_name": "points.csv"}]}),
            MockResponse(content=("\n".join(csv_lines) + "\n").encode()),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / "cache"
            cache_dir.mkdir()
            pending_file = Path(temp_dir) / "pending_tasks.json"
            pending_file.write_text(
                json.dumps({
                    main._pending_task_key(request): {
                        "task_id": "task-done",
                        "request": request.model_dump(),
                    }
                }),
                encoding="utf-8",
            )
            with (
                patch("main.CACHE_DIR", cache_dir),
                patch("main.PENDING_TASKS_FILE", pending_file),
            ):
                main._poll_and_cache_appeears_task("token-test", request, "task-done")
                result = main._load_cache(request)
                self.assertFalse(pending_file.exists())

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["data_source"], "nasa_appeears")
        self.assertEqual(len(result["series"]), 36)

    @patch("main.requests.get")
    @patch("main._earthdata_token", return_value="token-test")
    @patch("main._load_cache", return_value=None)
    @patch("main._schedule_appeears_task", return_value=True)
    def test_sync_endpoint_schedules_download_for_known_completed_task(
        self,
        mock_schedule,
        _mock_load_cache,
        _mock_token,
        mock_get,
    ):
        request = AnalysisRequest(
            city_name="Ben Guerir",
            country="Maroc",
            lat=32.23,
            lon=-7.95,
            start_year=2020,
            end_year=2022,
        )
        mock_get.return_value = MockResponse([
            {"task_id": "task-existing", "status": "done"},
        ])

        with tempfile.TemporaryDirectory() as temp_dir:
            pending_file = Path(temp_dir) / "pending_tasks.json"
            pending_file.write_text(
                json.dumps({
                    main._pending_task_key(request): {
                        "task_id": "task-existing",
                        "request": request.model_dump(),
                    }
                }),
                encoding="utf-8",
            )
            with patch("main.PENDING_TASKS_FILE", pending_file):
                result = asyncio.run(main.sync_nasa_tasks(BackgroundTasks()))

        self.assertEqual(result["scheduled_downloads"], 1)
        self.assertEqual(result["status"], "syncing")
        _mock_load_cache.assert_called_once_with(request)
        _mock_token.assert_called_once()
        mock_schedule.assert_called_once_with(
            unittest.mock.ANY,
            "token-test",
            request,
            "task-existing",
        )


if __name__ == "__main__":
    unittest.main()
