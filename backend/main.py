"""API de Zénith Earth : analyse de températures MODIS, cache et synchronisation AppEEARS."""

from __future__ import annotations

import io
import json
import logging
import math
import os
import tempfile
import threading
import time
import unicodedata
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, model_validator

from statistics_engine import analyze_series, project_trends

ROOT = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT / ".env")

# Tous les fichiers persistants suivent le même répertoire pour survivre aux redémarrages.
DATA_DIR = Path(os.getenv("ZENITH_DATA_DIR") or ROOT)
if not DATA_DIR.is_absolute():
    DATA_DIR = ROOT / DATA_DIR
DATA_DIR = DATA_DIR.resolve()
CACHE_DIR = DATA_DIR / "cache"
DEMO_DIR = DATA_DIR / "demo_data"
PENDING_TASKS_FILE = DATA_DIR / "pending_tasks.json"
APPEEARS = "https://appeears.earthdatacloud.nasa.gov/api"
PRODUCT = "MOD11A2.061"
LAYER = "LST_Day_1km"
APPEEARS_BACKGROUND_POLL_SECONDS = 30
APPEEARS_BACKGROUND_TIMEOUT_SECONDS = 45 * 60
DEMO_DATA_VERSION = 2
CACHE_VERSION = 6
logger = logging.getLogger(__name__)
_PENDING_TASKS_LOCK = threading.Lock()
_BACKGROUND_TASKS_LOCK = threading.Lock()
_ACTIVE_BACKGROUND_TASKS: set[str] = set()

CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEMO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Zénith Earth API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "ALLOWED_ORIGINS",
            os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    """Paramètres validés d'une analyse pour une ville et son point rural témoin."""

    city_name: str = Field(min_length=1, max_length=120)
    country: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    start_year: int = Field(ge=2000, le=date.today().year - 1)
    end_year: int = Field(ge=2001, le=date.today().year - 1)

    @model_validator(mode="after")
    def valid_years(self) -> "AnalysisRequest":
        if self.end_year - self.start_year < 2:
            raise ValueError("La période doit couvrir au moins trois années pour analyser la tendance.")
        return self


DEMO_CITIES = [
    {
        "city_name": "Ben Guerir",
        "country": "Maroc",
        "lat": 32.23,
        "lon": -7.95,
        "urban_base": 30.0,
        "rural_base": 28.9,
        "urban_trend": 0.045,
        "rural_trend": 0.025,
        "amplitude": 8.0,
        "phase": 0.1,
    },
    {
        "city_name": "Casablanca",
        "country": "Maroc",
        "lat": 33.57,
        "lon": -7.59,
        "urban_base": 23.7,
        "rural_base": 22.8,
        "urban_trend": 0.035,
        "rural_trend": 0.022,
        "amplitude": 5.5,
        "phase": 0.4,
    },
    {
        "city_name": "Phoenix",
        "country": "États-Unis",
        "lat": 33.45,
        "lon": -112.07,
        "urban_base": 34.0,
        "rural_base": 32.5,
        "urban_trend": 0.055,
        "rural_trend": 0.030,
        "amplitude": 10.0,
        "phase": 0.0,
    },
    {
        "city_name": "Paris",
        "country": "France",
        "lat": 48.86,
        "lon": 2.35,
        "urban_base": 17.4,
        "rural_base": 16.9,
        "urban_trend": 0.032,
        "rural_trend": 0.025,
        "amplitude": 6.2,
        "phase": 0.35,
    },
]


def _demo_path(city: dict[str, Any]) -> Path:
    return DEMO_DIR / f"{city['city_name'].lower().replace(' ', '_')}.json"


def ensure_demo_data() -> None:
    """Create reproducible monthly demonstration series when the server starts."""
    for city in DEMO_CITIES:
        path = _demo_path(city)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing.get("data_version") == DEMO_DATA_VERSION:
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        # Le jeu de démonstration est déterministe afin que les essais restent reproductibles.
        months = pd.date_range("2000-01-01", "2025-12-01", freq="MS")
        elapsed = np.arange(len(months), dtype=float) / 12
        seasonal = city["amplitude"] * np.sin(
            2 * np.pi * (months.month.to_numpy() - 1) / 12 + city["phase"]
        )
        # A small deterministic modulation keeps the sample plausible without randomness.
        modulation = 0.10 * np.sin(elapsed * 1.7) + 0.05 * np.cos(elapsed * 0.63)
        urban = city["urban_base"] + city["urban_trend"] * elapsed + seasonal + modulation
        rural = city["rural_base"] + city["rural_trend"] * elapsed + seasonal * 0.94 + modulation * 0.8
        payload = {
            "data_version": DEMO_DATA_VERSION,
            "city": city,
            "series": [
                {
                    "date": month.strftime("%Y-%m-%d"),
                    "urban_c": round(float(u), 3),
                    "rural_c": round(float(r), 3),
                }
                for month, u, r in zip(months, urban, rural)
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


ensure_demo_data()


def _cache_path(request: AnalysisRequest) -> Path:
    """Construit un nom de cache unique pour les coordonnées et la période demandée."""
    return CACHE_DIR / (
        f"{request.lat:.4f}_{request.lon:.4f}_"
        f"{request.start_year}_{request.end_year}.json"
    )


def _normalize_place_name(value: str) -> str:
    """Normalise accents et ponctuation pour comparer les alias d'une ville."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_name = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join("".join(character if character.isalnum() else " " for character in ascii_name).split())


def _cache_matches_named_location(
    result: dict[str, Any],
    request: AnalysisRequest,
    normalized_city: str,
) -> bool:
    """Accepte les libellés de géocodeur proches, sans confondre deux villes homonymes."""
    aliases = result.get("city_aliases", [result.get("city", "")])
    matching_alias = any(
        isinstance(alias, str)
        and (
            normalized_city == normalized_alias
            or normalized_city.startswith(f"{normalized_alias} ")
        )
        for alias in aliases
        if (normalized_alias := _normalize_place_name(alias))
    )
    coordinates = result.get("coordinates")
    if not matching_alias or not isinstance(coordinates, dict):
        return False
    try:
        cached_lat = float(coordinates["lat"])
        cached_lon = float(coordinates["lon"])
    except (KeyError, TypeError, ValueError):
        return False

    # Le géocodeur peut renvoyer un point de centre-ville différent de celui de l'archive.
    lat1, lat2 = math.radians(cached_lat), math.radians(request.lat)
    delta_lat = math.radians(request.lat - cached_lat)
    delta_lon = math.radians(request.lon - cached_lon)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    distance_km = 6371 * 2 * math.asin(math.sqrt(min(1.0, haversine)))
    return distance_km <= 40


def _load_cache(request: AnalysisRequest) -> dict[str, Any] | None:
    """Charge une analyse compatible, ou recalcule une sous-période depuis un cache plus large."""
    expected_period = {
        "start_year": request.start_year,
        "end_year": request.end_year,
    }
    direct_path = _cache_path(request)
    candidate_paths = [direct_path]
    if CACHE_DIR.exists():
        candidate_paths.extend(path for path in CACHE_DIR.glob("*.json") if path != direct_path)

    normalized_city = _normalize_place_name(request.city_name)
    for path in candidate_paths:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cached_period = result.get("period", {})
        # Les simulations ordinaires ne sont pas définitives; seuls les exports archivés
        # explicitement signalés peuvent servir de secours durable.
        if (
            result.get("cache_version") != CACHE_VERSION
            or (
                result.get("data_source") != "nasa_appeears"
                and not (
                    result.get("data_source") == "fallback_model"
                    and result.get("archive_fallback") is True
                )
            )
            or not isinstance(cached_period, dict)
            or cached_period.get("start_year", request.start_year + 1) > request.start_year
            or cached_period.get("end_year", request.end_year - 1) < request.end_year
        ):
            continue
        if path == direct_path or _cache_matches_named_location(
            result,
            request,
            normalized_city,
        ):
            if cached_period != expected_period:
                cached_result = result
                cached_rows = [
                    {
                        "date": point["date"],
                        "urban_c": point["city_c"],
                        "rural_c": point["rural_c"],
                    }
                    for point in result.get("series", [])
                    if request.start_year <= int(point["date"][:4]) <= request.end_year
                ]
                try:
                    result = _assemble_result(
                        request,
                        cached_rows,
                        float(cached_result["rural_coordinates"]["lat"]),
                        float(cached_result["rural_coordinates"]["lon"]),
                        demo=cached_result["data_source"] == "fallback_model",
                        notice=cached_result.get("notice"),
                    )
                except (HTTPException, KeyError, TypeError, ValueError):
                    continue
                result["city_aliases"] = cached_result.get("city_aliases", [])
                result["notice"] = cached_result.get("notice")
                if cached_result.get("archive_fallback"):
                    result["archive_fallback"] = True
                _save_cache(request, result)
            result["city"] = request.city_name
            result["country"] = request.country
            result["cache_hit"] = True
            return result
    return None


def _save_cache(request: AnalysisRequest, result: dict[str, Any]) -> None:
    """Persiste le résultat JSON sous la clé déterminée par les coordonnées et les années."""
    _cache_path(request).write_text(
        json.dumps(result, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


def _pending_task_key(request: AnalysisRequest) -> str:
    """Identifie une tâche NASA indépendamment du nom de ville ou de sa langue."""
    return json.dumps(
        [request.lat, request.lon, request.start_year, request.end_year],
        separators=(",", ":"),
    )


def _load_pending_tasks() -> dict[str, Any]:
    """Lit et valide l'index des tâches à reprendre après un redémarrage du backend."""
    if not PENDING_TASKS_FILE.exists():
        return {}
    try:
        pending_tasks = json.loads(PENDING_TASKS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Impossible de lire l’index des tâches AppEEARS : {exc}") from exc
    if not isinstance(pending_tasks, dict) or not all(
        isinstance(key, str)
        and (
            (isinstance(task, str) and task)
            or (
                isinstance(task, dict)
                and isinstance(task.get("task_id"), str)
                and task["task_id"]
            )
        )
        for key, task in pending_tasks.items()
    ):
        raise RuntimeError("L’index des tâches AppEEARS est invalide.")
    return pending_tasks


def _save_pending_tasks(pending_tasks: dict[str, Any]) -> None:
    """Écrit l'index par remplacement atomique pour éviter un JSON partiellement écrit."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=PENDING_TASKS_FILE.parent,
            prefix="pending_tasks.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(pending_tasks, temporary_file, ensure_ascii=False)
        os.replace(temporary_path, PENDING_TASKS_FILE)
    except OSError as exc:
        raise RuntimeError(f"Impossible d’enregistrer l’index des tâches AppEEARS : {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _remove_pending_task(
    request: AnalysisRequest,
    expected_task_id: str | None = None,
) -> None:
    """Retire une tâche terminée sans effacer une tâche plus récente pour la même requête."""
    with _PENDING_TASKS_LOCK:
        pending_tasks = _load_pending_tasks()
        pending_key = _pending_task_key(request)
        pending_task = pending_tasks.get(pending_key)
        if pending_task is None or (
            expected_task_id is not None
            and _get_pending_task_id(pending_task) != expected_task_id
        ):
            return
        pending_tasks.pop(pending_key)
        if pending_tasks:
            _save_pending_tasks(pending_tasks)
        else:
            try:
                PENDING_TASKS_FILE.unlink()
            except FileNotFoundError:
                pass


def _get_pending_task_id(pending_task: Any) -> str:
    """Accepte les anciens index (ID brut) comme le format actuel contenant une fiche."""
    if isinstance(pending_task, str):
        return pending_task
    return pending_task["task_id"]


def _get_pending_request(pending_task: Any) -> AnalysisRequest | None:
    """Reconstruit la requête enregistrée avec l'ID NASA, si elle est encore valide."""
    if not isinstance(pending_task, dict):
        return None
    request_data = pending_task.get("request")
    if not isinstance(request_data, dict):
        return None
    try:
        return AnalysisRequest.model_validate(request_data)
    except ValidationError as exc:
        logger.warning("Ignoring invalid request metadata in AppEEARS task index: %s", exc)
        return None


def _store_pending_task(request: AnalysisRequest, task_id: str) -> None:
    """Enregistre immédiatement l'ID fourni par AppEEARS pour pouvoir reprendre le travail."""
    with _PENDING_TASKS_LOCK:
        pending_tasks = _load_pending_tasks()
        pending_tasks[_pending_task_key(request)] = {
            "task_id": task_id,
            "request": request.model_dump(),
        }
        _save_pending_tasks(pending_tasks)


def _rural_coordinates(lat: float, lon: float) -> tuple[float, float]:
    # 0.40° latitude is approximately 44.5 km; clamp at the poles.
    return max(-90.0, min(90.0, lat + 0.40)), lon


def _create_demo_result(request: AnalysisRequest, reason: str) -> dict[str, Any]:
    """Produit une série pédagogique clairement étiquetée lorsque les données NASA manquent."""
    latitude = abs(request.lat)
    annual_mean = 27.5 - 0.52 * latitude
    seasonal_amplitude = min(20.0, 5.0 + 0.22 * latitude)
    hemisphere = -1.0 if request.lat < 0 else 1.0
    urban_heat_effect = max(0.3, 1.4 - 0.012 * latitude)
    dates = pd.date_range(
        f"{request.start_year}-01-01",
        f"{request.end_year}-12-01",
        freq="MS",
    )
    winter_months = (
        {11, 12, 1, 2, 3}
        if request.lat >= 0
        else {5, 6, 7, 8, 9}
    )
    series = []
    for timestamp in dates:
        seasonal = seasonal_amplitude * math.sin(
            2 * math.pi * (timestamp.month - 4) / 12
        ) * hemisphere
        urban_c = annual_mean + seasonal + urban_heat_effect
        rural_c = annual_mean + seasonal * 0.95
        if latitude >= 65 and timestamp.month in winter_months:
            urban_c = min(5.0, max(-25.0, urban_c))
            rural_c = min(5.0, max(-25.0, rural_c))
        series.append({
            "date": timestamp.strftime("%Y-%m-%d"),
            "urban_c": round(urban_c, 3),
            "rural_c": round(rural_c, 3),
        })

    return _assemble_result(
        request=request,
        rows=series,
        rural_lat=_rural_coordinates(request.lat, request.lon)[0],
        rural_lon=request.lon,
        demo=True,
        notice=(
            f"{reason} Les valeurs sont simulées par un modèle pédagogique "
            "calibré selon la latitude et l’hémisphère."
        ),
    )


def _assemble_result(
    request: AnalysisRequest,
    rows: list[dict[str, Any]],
    rural_lat: float,
    rural_lon: float,
    demo: bool,
    notice: str | None = None,
) -> dict[str, Any]:
    """Filtre les mesures, vérifie la couverture puis calcule statistiques et projections."""
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "urban_c", "rural_c"]).sort_values("date")
    frame = frame[
        np.isfinite(frame["urban_c"].astype(float))
        & np.isfinite(frame["rural_c"].astype(float))
    ].copy()
    frame = frame[
        (frame["date"].dt.year >= request.start_year)
        & (frame["date"].dt.year <= request.end_year)
    ]
    frame["year"] = frame["date"].dt.year
    months_per_year = frame.groupby("year")["date"].apply(
        lambda dates: dates.dt.month.nunique()
    )
    # Une année est conservée seulement si au moins six mois ont des observations appariées.
    valid_years = months_per_year[months_per_year >= 6].index
    frame = frame[frame["year"].isin(valid_years)]
    if frame["year"].nunique() < 3:
        raise HTTPException(
            status_code=502,
            detail=(
                "Données insuffisantes : des mesures valides pendant au moins 6 mois par an "
                "sur 3 années sont requis pour chaque paire de points."
            ),
        )

    city_values = frame["urban_c"].astype(float).tolist()
    rural_values = frame["rural_c"].astype(float).tolist()
    dates = frame["date"].dt.strftime("%Y-%m-%d").tolist()
    city_stats, city_curves = analyze_series(dates, city_values)
    rural_stats, rural_curves = analyze_series(dates, rural_values)
    projection = project_trends(
        dates,
        city_values,
        rural_values,
        city_stats,
        rural_stats,
        request.end_year,
    )
    series = []
    for index, timestamp in enumerate(dates):
        series.append(
            {
                "date": timestamp,
                "city_c": city_values[index],
                "rural_c": rural_values[index],
                "city_linear": city_curves["linear"][index],
                "rural_linear": rural_curves["linear"][index],
            }
        )
    return {
        "city": request.city_name,
        "country": request.country,
        "coordinates": {"lat": request.lat, "lon": request.lon},
        "rural_coordinates": {"lat": rural_lat, "lon": rural_lon},
        "period": {"start_year": request.start_year, "end_year": request.end_year},
        "source": (
            f"Simulation pédagogique — profil MODIS {PRODUCT} / {LAYER}"
            if demo
            else f"NASA MODIS {PRODUCT} — {LAYER}"
        ),
        "cache_version": CACHE_VERSION,
        "mode": "demo" if demo else "live",
        "data_source": "fallback_model" if demo else "nasa_appeears",
        "fallback_reason": notice if demo else None,
        "notice": notice,
        "cache_hit": False,
        "series": series,
        "projection": projection,
        "statistics": {
            "city": city_stats,
            "rural": rural_stats,
            "mean_urban_rural_difference_c": float(np.mean(np.array(city_values) - np.array(rural_values))),
        },
    }


def _earthdata_token() -> str:
    """Authentifie le compte Earthdata et renvoie le jeton nécessaire aux appels AppEEARS."""
    username = os.getenv("NASA_EARTHDATA_USER", "").strip()
    password = os.getenv("NASA_EARTHDATA_PASS", "").strip()
    if not username or not password:
        raise RuntimeError("Les identifiants NASA Earthdata ne sont pas configurés.")
    response = requests.post(
        f"{APPEEARS}/login",
        auth=(username, password),
        timeout=12,
    )
    response.raise_for_status()
    token = response.json().get("token")
    if not token:
        raise RuntimeError("La réponse d’authentification NASA ne contient pas de jeton.")
    return token


def _appeears_request_error(exc: requests.RequestException) -> str:
    """Formate une erreur HTTP sans exposer les identifiants Earthdata dans les journaux."""
    response = exc.response
    if response is None:
        detail = str(exc) or exc.__class__.__name__
    else:
        detail = f"HTTP {response.status_code} {response.reason}"
        body = response.text.strip()
        if body:
            detail = f"{detail}: {body[:500]}"
    for secret_name in ("NASA_EARTHDATA_USER", "NASA_EARTHDATA_PASS"):
        secret = os.getenv(secret_name, "").strip()
        if secret:
            detail = detail.replace(secret, "[redacted]")
    return detail


def _create_or_resume_appeears_task(token: str, request: AnalysisRequest) -> str:
    """Réutilise l'ID en attente, ou soumet et persiste une seule nouvelle tâche NASA."""
    headers = {"Authorization": f"Bearer {token}"}
    rural_lat, rural_lon = _rural_coordinates(request.lat, request.lon)
    task = {
        "task_type": "point",
        "task_name": f"zenith-earth-{request.city_name[:40]}",
        "params": {
            "dates": [
                {
                    "startDate": f"01-01-{request.start_year}",
                    "endDate": f"12-31-{request.end_year}",
                }
            ],
            "layers": [{"product": PRODUCT, "layer": LAYER}],
            "coordinates": [
                {"latitude": request.lat, "longitude": request.lon, "id": "urban", "category": "city"},
                {"latitude": rural_lat, "longitude": rural_lon, "id": "rural", "category": "rural"},
            ],
        },
    }
    pending_key = _pending_task_key(request)
    with _PENDING_TASKS_LOCK:
        pending_tasks = _load_pending_tasks()
        pending_task = pending_tasks.get(pending_key)
        if pending_task is not None:
            return _get_pending_task_id(pending_task)
        else:
            created = requests.post(f"{APPEEARS}/task", headers=headers, json=task, timeout=15)
            created.raise_for_status()
            response_task_id = created.json().get("task_id")
            if not response_task_id:
                raise RuntimeError("AppEEARS n’a pas fourni d’identifiant de tâche.")
            task_id = str(response_task_id)
            pending_tasks[pending_key] = {
                "task_id": task_id,
                "request": request.model_dump(),
            }
            _save_pending_tasks(pending_tasks)
            return task_id

def _download_appeears_rows(
    token: str,
    request: AnalysisRequest,
    task_id: str,
) -> tuple[list[dict[str, Any]], float, float]:
    """Télécharge les fichiers du bundle AppEEARS et délègue le parsing des CSV."""
    headers = {"Authorization": f"******"}
    bundle_response = requests.get(f"{APPEEARS}/bundle/{task_id}", headers=headers, timeout=15)
    bundle_response.raise_for_status()
    files = bundle_response.json().get("files", [])
    csv_contents: list[tuple[str, bytes]] = []
    for item in files:
        file_id = item.get("file_id")
        if not file_id:
            continue
        download = requests.get(
            f"{APPEEARS}/bundle/{task_id}/{file_id}",
            headers=headers,
            timeout=20,
        )
        download.raise_for_status()
        content = download.content
        if zipfile.is_zipfile(io.BytesIO(content)):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                csv_name = next((name for name in archive.namelist() if name.lower().endswith(".csv")), None)
                if not csv_name:
                    continue
                content = archive.read(csv_name)
        csv_contents.append((str(item.get("file_name", "")), content))
    return _rows_from_appeears_csv_contents(csv_contents, request)


def _rows_from_appeears_csv_contents(
    csv_contents: list[tuple[str, bytes]],
    request: AnalysisRequest,
) -> tuple[list[dict[str, Any]], float, float]:
    """Associe les points urbain/rural, convertit les LST en °C et écarte les valeurs invalides."""
    rural_lat, rural_lon = _rural_coordinates(request.lat, request.lon)
    rows_by_date: dict[str, dict[str, float | None]] = {}
    for file_name, content in csv_contents:
        try:
            data = pd.read_csv(io.BytesIO(content))
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        if data.empty:
            continue
        columns = {str(column).lower(): column for column in data.columns}
        date_column = next((columns[key] for key in columns if "date" in key or "time" in key), None)
        value_column = next(
            (
                columns[key]
                for key in columns
                if "value" in key or "lst_day" in key or "pixel" in key
            ),
            None,
        )
        point_column = next(
            (columns[key] for key in columns if "id" in key or "category" in key or "coordinate" in key),
            None,
        )
        latitude_column = next((columns[key] for key in columns if key in {"latitude", "lat"}), None)
        longitude_column = next((columns[key] for key in columns if key in {"longitude", "lon", "lng"}), None)
        if date_column is None or value_column is None:
            continue
        fallback_point = "rural" if "rural" in file_name.lower() else "urban"
        for _, record in data.iterrows():
            timestamp = pd.to_datetime(record[date_column], errors="coerce")
            raw_value = pd.to_numeric(record[value_column], errors="coerce")
            if pd.isna(timestamp) or pd.isna(raw_value) or not math.isfinite(float(raw_value)):
                continue
            point_name = str(record[point_column]).lower() if point_column else ""
            if "rural" in point_name or "urban" in point_name:
                site = "rural" if "rural" in point_name else "urban"
            elif latitude_column and longitude_column:
                point_lat = pd.to_numeric(record[latitude_column], errors="coerce")
                point_lon = pd.to_numeric(record[longitude_column], errors="coerce")
                if pd.isna(point_lat) or pd.isna(point_lon):
                    continue
                city_distance = (float(point_lat) - request.lat) ** 2 + (float(point_lon) - request.lon) ** 2
                rural_distance = (float(point_lat) - rural_lat) ** 2 + (float(point_lon) - rural_lon) ** 2
                site = "urban" if city_distance <= rural_distance else "rural"
            else:
                site = fallback_point
            observed_value = float(raw_value)
            # Les exports fournis peuvent contenir des Kelvin directs ou les pixels MODIS bruts.
            kelvin = observed_value if 150 <= observed_value <= 400 else observed_value * 0.02
            if kelvin <= 200:
                continue
            celsius = kelvin - 273.15
            if celsius > 80:
                continue
            rows_by_date.setdefault(timestamp.strftime("%Y-%m-%d"), {})[site] = celsius

    rows = [
        {"date": timestamp, "urban_c": values.get("urban"), "rural_c": values.get("rural")}
        for timestamp, values in sorted(rows_by_date.items())
        if values.get("urban") is not None and values.get("rural") is not None
    ]
    return rows, rural_lat, rural_lon


def _cache_appeears_task(token: str, request: AnalysisRequest, task_id: str) -> None:
    """Transforme une tâche terminée en résultat NASA en cache puis nettoie l'index."""
    rows, rural_lat, rural_lon = _download_appeears_rows(token, request, task_id)
    if not rows:
        raise RuntimeError(f"La tâche AppEEARS {task_id} ne contient aucune observation exploitable.")
    result = _assemble_result(request, rows, rural_lat, rural_lon, demo=False)
    _save_cache(request, result)
    _remove_pending_task(request, expected_task_id=task_id)


def _poll_and_cache_appeears_task(
    token: str | None,
    request: AnalysisRequest,
    task_id: str,
) -> None:
    """Surveille AppEEARS en arrière-plan et conserve le résultat dès que la tâche est finie."""
    try:
        token = token or _earthdata_token()
        headers = {"Authorization": f"******"}
        deadline = time.monotonic() + APPEEARS_BACKGROUND_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            status_response = requests.get(
                f"{APPEEARS}/status/{task_id}",
                headers=headers,
                timeout=25,
            )
            status_response.raise_for_status()
            state = str(status_response.json().get("status", "")).lower()
            if state == "done":
                _cache_appeears_task(token, request, task_id)
                logger.info("Cached completed AppEEARS task %s", task_id)
                return
            if state in {"error", "failed", "cancelled"}:
                _remove_pending_task(request, expected_task_id=task_id)
                logger.error("NASA AppEEARS task %s ended with status %s", task_id, state)
                return
            time.sleep(min(APPEEARS_BACKGROUND_POLL_SECONDS, max(0, deadline - time.monotonic())))
        logger.warning("NASA AppEEARS task %s was not complete after 45 minutes", task_id)
    except (requests.RequestException, RuntimeError, OSError, HTTPException) as exc:
        logger.error("NASA AppEEARS background sync failed for task %s: %s", task_id, exc)
    finally:
        with _BACKGROUND_TASKS_LOCK:
            _ACTIVE_BACKGROUND_TASKS.discard(task_id)


def _schedule_appeears_task(
    background_tasks: BackgroundTasks,
    token: str | None,
    request: AnalysisRequest,
    task_id: str,
) -> bool:
    """Évite de lancer deux pollers locaux simultanés pour le même ID AppEEARS."""
    with _BACKGROUND_TASKS_LOCK:
        if task_id in _ACTIVE_BACKGROUND_TASKS:
            return False
        _ACTIVE_BACKGROUND_TASKS.add(task_id)
    background_tasks.add_task(_poll_and_cache_appeears_task, token, request, task_id)
    return True


def _appeears_task_records(payload: Any) -> list[dict[str, Any]]:
    """Normalise les différentes formes de réponse de l'endpoint de tâches NASA."""
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, dict)]
    if not isinstance(payload, dict):
        raise RuntimeError("La liste des tâches AppEEARS a un format inattendu.")
    for collection_key in ("tasks", "results"):
        records = payload.get(collection_key)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    if "task_id" in payload or "id" in payload:
        return [payload]
    records: list[dict[str, Any]] = []
    for task_id, record in payload.items():
        if isinstance(record, dict):
            records.append({"task_id": task_id, **record})
        elif isinstance(record, str):
            records.append({"task_id": task_id, "status": record})
    return records


def _request_from_appeears_task(
    task: dict[str, Any],
    pending_key: str | None = None,
    pending_task: Any = None,
) -> AnalysisRequest | None:
    """Reconstruit la requête d'origine depuis l'index local ou les paramètres NASA."""
    stored_request = _get_pending_request(pending_task)
    if stored_request is not None:
        return stored_request

    params = task.get("params")
    coordinates = params.get("coordinates", []) if isinstance(params, dict) else []
    dates = params.get("dates", []) if isinstance(params, dict) else []
    urban = next(
        (
            coordinate
            for coordinate in coordinates
            if isinstance(coordinate, dict)
            and (
                str(coordinate.get("id", "")).lower() == "urban"
                or str(coordinate.get("category", "")).lower() == "city"
            )
        ),
        None,
    )
    date_range = dates[0] if dates and isinstance(dates[0], dict) else None
    if urban is not None and date_range is not None:
        try:
            start_year = int(str(date_range["startDate"])[-4:])
            end_year = int(str(date_range["endDate"])[-4:])
            lat, lon = float(urban["latitude"]), float(urban["longitude"])
        except (KeyError, TypeError, ValueError):
            return None
    elif pending_key is not None:
        try:
            lat, lon, start_year, end_year = json.loads(pending_key)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    else:
        return None

    task_name = str(task.get("task_name") or "")
    city_name = task_name.removeprefix("zenith-earth-").strip() or "NASA location"
    country = str(task.get("country") or "NASA")
    try:
        return AnalysisRequest(
            city_name=city_name,
            country=country,
            lat=lat,
            lon=lon,
            start_year=start_year,
            end_year=end_year,
        )
    except ValidationError:
        return None


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Expose l'état de l'API et indique si les identifiants NASA sont configurés."""
    configured = bool(os.getenv("NASA_EARTHDATA_USER") and os.getenv("NASA_EARTHDATA_PASS"))
    return {"status": "ok", "mode": "live" if configured else "demo"}


@app.post("/api/analyze")
async def analyze(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Répond depuis le cache, sinon renvoie un modèle provisoire et démarre la tâche NASA."""
    cached = _load_cache(request)
    if cached:
        # Un résultat en cache répond immédiatement sans solliciter à nouveau AppEEARS.
        return cached
    if not os.getenv("NASA_EARTHDATA_USER") or not os.getenv("NASA_EARTHDATA_PASS"):
        result = _create_demo_result(request, "Identifiants NASA absents : données de démonstration utilisées.")
        _save_cache(request, result)
        return result

    try:
        token = _earthdata_token()
        task_id = _create_or_resume_appeears_task(token, request)
        _schedule_appeears_task(background_tasks, token, request, task_id)
        queue_notice = "Synchronisation satellite NASA en cours — rechargez dans quelques minutes"
        result = _create_demo_result(
            request,
            queue_notice,
        )
        result["status"] = "queued_nasa"
        result["notice"] = queue_notice
    except requests.RequestException as exc:
        reason = _appeears_request_error(exc)
        logger.error("NASA AppEEARS request failed: %s", reason)
        result = _create_demo_result(request, f"Échec AppEEARS : {reason}.")
    except RuntimeError as exc:
        logger.error("NASA AppEEARS processing failed: %s", exc)
        result = _create_demo_result(request, f"Échec AppEEARS : {exc}.")
    return result


@app.get("/api/nasa/sync")
async def sync_nasa_tasks(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Retrouve les tâches AppEEARS existantes et planifie le téléchargement des résultats."""
    if not os.getenv("NASA_EARTHDATA_USER") or not os.getenv("NASA_EARTHDATA_PASS"):
        raise HTTPException(status_code=503, detail="Les identifiants NASA Earthdata ne sont pas configurés.")

    token = _earthdata_token()
    headers = {"Authorization": f"******"}
    response = requests.get(f"{APPEEARS}/task", headers=headers, timeout=30)
    response.raise_for_status()
    task_records = _appeears_task_records(response.json())
    pending_tasks = _load_pending_tasks()
    pending_by_id = {
        _get_pending_task_id(pending_task): (pending_key, pending_task)
        for pending_key, pending_task in pending_tasks.items()
    }
    seen_task_ids: set[str] = set()
    scheduled = 0
    already_cached = 0
    unmatched = 0

    for task in task_records:
        task_id_value = task.get("task_id") or task.get("id")
        if not task_id_value:
            continue
        task_id = str(task_id_value)
        seen_task_ids.add(task_id)
        pending_entry = pending_by_id.get(task_id)
        pending_key, pending_task = pending_entry if pending_entry else (None, None)
        state = str(task.get("status", "")).lower()
        if state not in {"done", "error", "failed", "cancelled", "processing", "pending"}:
            status_response = requests.get(
                f"{APPEEARS}/status/{task_id}",
                headers=headers,
                timeout=20,
            )
            status_response.raise_for_status()
            state = str(status_response.json().get("status", "")).lower()

        if state in {"error", "failed", "cancelled"}:
            request_for_task = _request_from_appeears_task(task, pending_key, pending_task)
            if request_for_task is not None:
                _remove_pending_task(request_for_task, expected_task_id=task_id)
            continue

        if state != "done" and pending_entry is None:
            continue

        task_details = task
        request_for_task = _request_from_appeears_task(task_details, pending_key, pending_task)
        if request_for_task is None:
            detail_response = requests.get(
                f"{APPEEARS}/task/{task_id}",
                headers=headers,
                timeout=20,
            )
            detail_response.raise_for_status()
            task_details = detail_response.json()
            request_for_task = _request_from_appeears_task(task_details, pending_key, pending_task)
        if request_for_task is None:
            unmatched += 1
            logger.warning("Cannot map AppEEARS task %s to a location and date range", task_id)
            continue

        if state == "done" and _load_cache(request_for_task) is not None:
            _remove_pending_task(request_for_task, expected_task_id=task_id)
            already_cached += 1
            continue
        if _schedule_appeears_task(background_tasks, token, request_for_task, task_id):
            scheduled += 1

    for pending_key, pending_task in pending_tasks.items():
        task_id = _get_pending_task_id(pending_task)
        if task_id in seen_task_ids:
            continue
        request_for_task = _request_from_appeears_task({}, pending_key, pending_task)
        if request_for_task is None:
            unmatched += 1
            continue
        if _schedule_appeears_task(background_tasks, token, request_for_task, task_id):
            scheduled += 1

    return {
        "status": "syncing" if scheduled else "complete",
        "scheduled_downloads": scheduled,
        "already_cached": already_cached,
        "unmatched_tasks": unmatched,
    }


@app.get("/api/demo-cities")
async def demo_cities() -> list[dict[str, Any]]:
    """Fournit au frontend les villes préchargées utilisables pour la démonstration."""
    return [
        {key: city[key] for key in ("city_name", "country", "lat", "lon")}
        for city in DEMO_CITIES
    ]
