"""Calcul des tendances annuelles, tests statistiques et extrapolations linéaires."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy.stats import linregress


def analyze_series(dates: list[str], values: list[float]) -> tuple[dict[str, Any], dict[str, list[float | None]]]:
    """Calcule les tendances sur les moyennes annuelles et renvoie la courbe au pas d'origine."""
    frame = pd.DataFrame({"date": pd.to_datetime(dates), "value": values}).dropna()
    frame = frame.sort_values("date").reset_index(drop=True)
    if len(frame) < 2:
        raise ValueError("Au moins deux mesures valides sont nécessaires pour calculer une tendance.")
    monthly_years = (frame["date"] - frame["date"].iloc[0]).dt.days.to_numpy(dtype=float) / 365.25
    annual = frame.set_index("date")["value"].resample("YS").mean().dropna()
    annual_years = (annual.index - frame["date"].iloc[0]).days.to_numpy(dtype=float) / 365.25
    annual_temperatures = annual.to_numpy(dtype=float)
    if len(annual) < 3:
        raise ValueError("Au moins trois années de données sont nécessaires pour l’analyse de tendance.")

    # Annual averages prevent the repeating seasonal cycle from biasing the trend and p-value.
    if np.allclose(annual_temperatures, annual_temperatures[0], rtol=0, atol=1e-10):
        linear_slope = 0.0
        linear_intercept = float(annual_temperatures[0])
        linear_r_squared = 0.0
        linear_p_value = 1.0
    else:
        linear = linregress(annual_years, annual_temperatures)
        linear_slope = float(linear.slope)
        linear_intercept = float(linear.intercept)
        linear_r_squared = float(linear.rvalue**2)
        linear_p_value = float(linear.pvalue)
    linear_values = linear_intercept + linear_slope * monthly_years
    mann = mk.original_test(annual_temperatures)

    curves = {
        "linear": [float(value) for value in linear_values],
    }
    stats = {
        "slope_c_per_year": linear_slope,
        "intercept_c": linear_intercept,
        "r_squared": linear_r_squared,
        "p_value": linear_p_value,
        "mann_kendall": {
            "trend": str(mann.trend),
            "p_value": float(mann.p),
            "tau": float(mann.Tau),
            "slope_per_month": float(mann.slope),
        },
    }
    return stats, curves


def project_trends(
    dates: list[str],
    city_values: list[float],
    rural_values: list[float],
    city_stats: dict[str, Any],
    rural_stats: dict[str, Any],
    end_year: int,
    horizon_year: int = 2100,
) -> dict[str, Any]:
    """Extrapole les droites ajustées et leurs écarts à la dernière moyenne observée."""
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "city": city_values,
            "rural": rural_values,
        }
    ).dropna().sort_values("date")
    annual = frame.set_index("date")[["city", "rural"]].resample("YS").mean().dropna()
    if annual.empty:
        raise ValueError("Aucune moyenne annuelle valide n’est disponible pour la projection.")
    if horizon_year <= end_year:
        raise ValueError("L’horizon de projection doit être postérieur à la période observée.")

    reference_date = frame["date"].iloc[0]
    baseline_year = int(annual.index[-1].year)
    baseline_city = float(annual.iloc[-1]["city"])
    baseline_rural = float(annual.iloc[-1]["rural"])
    points = []
    for year in range(end_year + 1, horizon_year + 1):
        elapsed_years = (pd.Timestamp(year=year, month=1, day=1) - reference_date).days / 365.25
        city_linear = city_stats["intercept_c"] + city_stats["slope_c_per_year"] * elapsed_years
        rural_linear = rural_stats["intercept_c"] + rural_stats["slope_c_per_year"] * elapsed_years
        points.append(
            {
                "year": year,
                "city_linear_c": float(city_linear),
                "rural_linear_c": float(rural_linear),
                "city_linear_delta_c": float(city_linear - baseline_city),
                "urban_rural_linear_difference_c": float(city_linear - rural_linear),
            }
        )

    return {
        "baseline_year": baseline_year,
        "baseline_city_c": baseline_city,
        "baseline_rural_c": baseline_rural,
        "points": points,
    }
