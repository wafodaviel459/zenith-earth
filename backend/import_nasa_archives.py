"""Importe des exports AppEEARS locaux dans le cache permanent de Zénith Earth."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException

import main


CITY_METADATA: dict[str, tuple[str, str, list[str]]] = {
    # Les alias permettent de retrouver les archives même si la recherche omet les accents.
    "Ben-Guerir": ("Ben Guerir", "Maroc", ["Ben Guerir", "Benguerir"]),
    "Casablanca": ("Casablanca", "Maroc", ["Casablanca"]),
    "Marrakech": ("Marrakech", "Maroc", ["Marrakech", "Marrakesh"]),
    "Los-Angeles": ("Los Angeles", "États-Unis", ["Los Angeles"]),
    "Phoenix": ("Phoenix", "États-Unis", ["Phoenix"]),
    "Sao-Paulo": ("São Paulo", "Brésil", ["São Paulo", "Sao Paulo"]),
    "Yaounde": ("Yaoundé", "Cameroun", ["Yaoundé", "Yaounde"]),
    "Tromso": ("Tromsø", "Norvège", ["Tromsø", "Tromso"]),
    "Douala": ("Douala", "Cameroun", ["Douala"]),
    "Reykjavik": ("Reykjavík", "Islande", ["Reykjavík", "Reykjavik"]),
}


def _read_request_metadata(path: Path, city_name: str, country: str) -> main.AnalysisRequest:
    """Extrait les coordonnées urbaines et la période depuis le JSON de soumission NASA."""
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    params = payload["params"]
    coordinates = params["coordinates"]
    urban = next(
        coordinate
        for coordinate in coordinates
        if coordinate.get("id") == "urban" or coordinate.get("category") == "city"
    )
    date_range = params["dates"][0]
    return main.AnalysisRequest(
        city_name=city_name,
        country=country,
        lat=float(urban["latitude"]),
        lon=float(urban["longitude"]),
        start_year=int(date_range["startDate"][-4:]),
        end_year=int(date_range["endDate"][-4:]),
    )


def import_archives(archive_directory: Path) -> int:
    """Analyse chaque paire JSON/CSV et conserve aussi les ID des tâches encore actives."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    imported = 0
    for slug, (city_name, country, aliases) in CITY_METADATA.items():
        request_file = archive_directory / f"zenith-earth-{slug}-request.json"
        csv_file = archive_directory / f"zenith-earth-{slug}-MOD11A2-061-results.csv"
        if not request_file.is_file() or not csv_file.is_file():
            logging.warning("Skipping %s: request metadata or result CSV is missing", city_name)
            continue

        payload = json.loads(request_file.read_text(encoding="utf-8"))
        request = _read_request_metadata(request_file, city_name, country)
        rows, rural_lat, rural_lon = main._rows_from_appeears_csv_contents(
            [(csv_file.name, csv_file.read_bytes())],
            request,
        )
        # Si la couverture NASA est insuffisante, garder un secours étiqueté plutôt que
        # prétendre que des températures simulées sont des observations satellites.
        try:
            if not rows:
                raise HTTPException(
                    status_code=502,
                    detail="The archive does not contain usable urban/rural observations.",
                )
            result = main._assemble_result(
                request,
                rows,
                rural_lat,
                rural_lon,
                demo=False,
            )
        except HTTPException as exc:
            result = main._create_demo_result(
                request,
                "Les données NASA archivées sont incomplètes pour cette ville "
                f"({exc.detail}); modèle de secours calibré par latitude utilisé.",
            )
            result["archive_fallback"] = True
            logging.warning("Using calibrated fallback for %s: %s", city_name, exc.detail)
        result["city_aliases"] = aliases
        if result["data_source"] == "nasa_appeears":
            result["notice"] = "Données NASA AppEEARS déjà téléchargées et conservées localement."
        main._save_cache(request, result)

        task_id = payload.get("task_id")
        if isinstance(task_id, str) and task_id:
            main._store_pending_task(request, task_id)
        logging.info("Cached %s: %s observations, %s–%s", city_name, len(result["series"]), request.start_year, request.end_year)
        imported += 1
    return imported


def main_cli() -> None:
    """Point d'entrée en ligne de commande pour importer un dossier d'exports."""
    parser = argparse.ArgumentParser(
        description="Import previously downloaded NASA AppEEARS CSV exports into the Zénith Earth cache."
    )
    parser.add_argument(
        "archive_directory",
        type=Path,
        help="Directory containing zenith-earth-*-request.json and matching MOD11A2 result CSV files",
    )
    args = parser.parse_args()
    count = import_archives(args.archive_directory)
    if count == 0:
        raise SystemExit("No NASA AppEEARS archives were imported.")
    print(f"Imported {count} city archives into {main.CACHE_DIR.resolve()}.")


if __name__ == "__main__":
    main_cli()
