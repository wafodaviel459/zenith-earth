import unittest

import numpy as np
import pandas as pd

from statistics_engine import analyze_series, project_trends


class StatisticsEngineTests(unittest.TestCase):
    def test_annual_trend_is_not_biased_by_monthly_seasonality(self) -> None:
        dates = pd.date_range("2015-01-01", "2025-12-01", freq="MS")
        elapsed_years = (dates - dates[0]).days.to_numpy(dtype=float) / 365.25
        seasonal_cycle = 7 * np.sin(2 * np.pi * (dates.month.to_numpy() - 1) / 12)
        values = 24 + 0.08 * elapsed_years + seasonal_cycle

        stats, curves = analyze_series(
            dates.strftime("%Y-%m-%d").tolist(),
            values.tolist(),
        )

        self.assertAlmostEqual(stats["slope_c_per_year"], 0.08, delta=0.003)
        self.assertLess(stats["p_value"], 0.05)
        self.assertEqual(len(curves["linear"]), len(dates))
        self.assertEqual(set(curves), {"linear"})
        self.assertEqual(
            set(stats),
            {"slope_c_per_year", "intercept_c", "r_squared", "p_value", "mann_kendall"},
        )

    def test_linear_projection_extends_to_2100_and_uses_latest_annual_baseline(self) -> None:
        dates = pd.date_range("2015-01-01", "2025-12-01", freq="MS")
        elapsed_years = (dates - dates[0]).days.to_numpy(dtype=float) / 365.25
        city_values = 25 + 0.05 * elapsed_years
        rural_values = 24 + 0.02 * elapsed_years
        city_stats, _ = analyze_series(dates.strftime("%Y-%m-%d").tolist(), city_values.tolist())
        rural_stats, _ = analyze_series(dates.strftime("%Y-%m-%d").tolist(), rural_values.tolist())

        projection = project_trends(
            dates.strftime("%Y-%m-%d").tolist(),
            city_values.tolist(),
            rural_values.tolist(),
            city_stats,
            rural_stats,
            end_year=2025,
        )

        self.assertEqual(projection["baseline_year"], 2025)
        self.assertEqual(len(projection["points"]), 75)
        self.assertEqual(projection["points"][0]["year"], 2026)
        self.assertEqual(projection["points"][-1]["year"], 2100)
        self.assertAlmostEqual(
            projection["points"][-1]["city_linear_delta_c"],
            projection["points"][-1]["city_linear_c"] - projection["baseline_city_c"],
        )
        self.assertAlmostEqual(
            projection["points"][-1]["urban_rural_linear_difference_c"],
            projection["points"][-1]["city_linear_c"] - projection["points"][-1]["rural_linear_c"],
        )
        self.assertEqual(
            set(projection["points"][-1]),
            {
                "year",
                "city_linear_c",
                "rural_linear_c",
                "city_linear_delta_c",
                "urban_rural_linear_difference_c",
            },
        )

    def test_constant_annual_series_has_finite_trend_statistics(self) -> None:
        dates = pd.date_range("2015-01-01", "2020-12-01", freq="MS")
        values = [18.5] * len(dates)

        stats, curves = analyze_series(dates.strftime("%Y-%m-%d").tolist(), values)

        self.assertEqual(stats["slope_c_per_year"], 0.0)
        self.assertEqual(stats["intercept_c"], 18.5)
        self.assertEqual(stats["r_squared"], 0.0)
        self.assertEqual(stats["p_value"], 1.0)
        self.assertTrue(all(np.isfinite(value) for value in curves["linear"]))


if __name__ == "__main__":
    unittest.main()
