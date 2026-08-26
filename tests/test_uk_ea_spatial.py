from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.data.hubeau_temperature import HUBEAU_CORRECT_QUALIFICATION
from stream_recoverability.data.public_river_inventory import haversine_km
from stream_recoverability.data.uk_ea_spatial import (
    cluster_uk_ea_spatial,
    hydrometric_stations,
    is_hydrometric_site_id,
    omit_groups_exceeding_cap,
    score_spatial_cluster_overlap,
    select_download_site_ids,
    uk_ea_complete_enough,
    w6_europe_spatial_manifest,
)


def test_event_monitor_ids_are_not_hydrometric() -> None:
    assert is_hydrometric_site_id("370cba4c-c28e-4063-aaea-a99575c408b6") is True
    assert is_hydrometric_site_id("SALMON") is True
    assert is_hydrometric_site_id("ANGEL1") is True
    assert is_hydrometric_site_id("E00491A") is False
    assert is_hydrometric_site_id("EN0091A") is False
    assert is_hydrometric_site_id("EP0128A") is False
    assert is_hydrometric_site_id("GPRSD8A") is False
    mixed = pd.DataFrame(
        {
            "site_id": [
                "370cba4c-c28e-4063-aaea-a99575c408b6",
                "E00491A",
                "SALMON",
                "ANGEL1",
                "EP0128A",
            ],
            "latitude": [52.88, 52.89, 52.90, 52.91, 52.92],
            "longitude": [-1.35, -1.36, -1.37, -1.38, -1.39],
        }
    )
    hydro = hydrometric_stations(mixed)
    assert set(hydro["site_id"]) == {
        "370cba4c-c28e-4063-aaea-a99575c408b6",
        "SALMON",
        "ANGEL1",
    }
    clusters = cluster_uk_ea_spatial(hydro, cap_km=50)
    assert len(clusters) == 1
    members = str(clusters.iloc[0]["site_ids"])
    assert "E00491A" not in members
    assert "EP0128A" not in members
    assert int(clusters.iloc[0]["n_stations"]) == 3

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results/framework/public_catalog/w6_europe_source_audit_manifest.json"


def _triangle(side_km: float) -> pd.DataFrame:
    """Approximate equilateral triangle around (51.5, -1.0)."""

    origin_lat, origin_lon = 51.5, -1.0
    dlat = side_km / 111.32
    dlon = side_km / (111.32 * np.cos(np.radians(origin_lat)))
    return pd.DataFrame(
        {
            "site_id": ["a", "b", "c"],
            "latitude": [origin_lat, origin_lat, origin_lat + dlat * np.sqrt(3) / 2],
            "longitude": [origin_lon, origin_lon + dlon, origin_lon + dlon / 2],
        }
    )


def test_spatial_clustering_does_not_require_river_names() -> None:
    stations = pd.DataFrame(
        {
            "site_id": ["x", "y", "z"],
            "latitude": [52.88, 52.93, 52.90],
            "longitude": [-1.35, -1.47, -1.41],
            "date_opened": ["1935-01-01", "2019-01-01", "2022-01-01"],
        }
    )
    clusters = cluster_uk_ea_spatial(stations, cap_km=50)
    assert "river" not in stations.columns
    assert len(clusters) == 1
    assert int(clusters.iloc[0]["n_stations"]) == 3
    assert bool(clusters.iloc[0]["countable_public_daily"]) is False
    assert float(clusters.iloc[0]["max_pairwise_km"]) <= 50.0
    assert float(clusters.iloc[0]["cap_km"]) == 50.0


def test_50km_cap_omits_far_groups() -> None:
    far = pd.DataFrame(
        {
            "site_id": ["london", "manchester", "edinburgh"],
            "river": ["", "", ""],
            "latitude": [51.5074, 53.4808, 55.9533],
            "longitude": [-0.1278, -2.2426, -3.1883],
        }
    )
    assert cluster_uk_ea_spatial(far, cap_km=50).empty
    handmade = pd.DataFrame(
        {
            "cluster_id": ["too_wide"],
            "n_stations": [3],
            "max_pairwise_km": [80.0],
            "site_ids": ["a,b,c"],
            "cap_km": [50.0],
            "countable_public_daily": [False],
        }
    )
    assert omit_groups_exceeding_cap(handmade, cap_km=50).empty
    close = _triangle(20.0)
    kept = cluster_uk_ea_spatial(close, cap_km=50)
    assert len(kept) == 1
    assert float(kept.iloc[0]["max_pairwise_km"]) <= 50.0
    wide = _triangle(80.0)
    ab = haversine_km(
        float(wide.latitude.iloc[0]),
        float(wide.longitude.iloc[0]),
        float(wide.latitude.iloc[1]),
        float(wide.longitude.iloc[1]),
    )
    assert ab > 50.0
    assert cluster_uk_ea_spatial(wide, cap_km=50).empty
    sensitivity = cluster_uk_ea_spatial(wide, cap_km=100)
    assert len(sensitivity) == 1


def test_complete_enough_false_when_overlap_years_below_8() -> None:
    dates = pd.date_range("2010-01-01", periods=7 * 365, freq="D")
    wide = pd.DataFrame(
        {"s1": 10.0, "s2": 11.0, "s3": 12.0},
        index=dates,
    )
    stations = pd.DataFrame(
        {
            "site_id": ["s1", "s2", "s3"],
            "latitude": [52.0, 52.01, 52.02],
            "longitude": [-1.0, -1.01, -1.02],
        }
    )
    report = score_spatial_cluster_overlap(wide, stations, cap_km=50)
    assert float(report["overlap_years"]) < 8.0
    assert report["complete_enough"] is False
    assert report["countable_toward_t8"] is False
    assert uk_ea_complete_enough(
        {"n_stations": 3, "overlap_years": 7.9, "days_with_min_stations": 4000}
    ) is False
    assert uk_ea_complete_enough(
        {"n_stations": 3, "overlap_years": 8.0, "days_with_min_stations": 5 * 365}
    ) is True


def test_overlap_subset_over_50km_is_omitted_not_t8() -> None:
    dates = pd.date_range("2000-01-01", periods=10 * 365, freq="D")
    wide = pd.DataFrame(
        {"london": 10.0, "manchester": 11.0, "edinburgh": 12.0},
        index=dates,
    )
    stations = pd.DataFrame(
        {
            "site_id": ["london", "manchester", "edinburgh"],
            "latitude": [51.5074, 53.4808, 55.9533],
            "longitude": [-0.1278, -2.2426, -3.1883],
        }
    )
    report = score_spatial_cluster_overlap(wide, stations, cap_km=50)
    assert float(report["overlap_years"]) >= 8.0
    assert int(report["days_with_min_stations"]) >= 5 * 365
    assert report["omitted_spatial_cap"] is True
    assert report["complete_enough"] is False
    assert report["countable_toward_t8"] is False


def test_download_subset_does_not_require_river_names() -> None:
    stations = pd.DataFrame(
        {
            "site_id": [
                "E01000A",
                "370cba4c-c28e-4063-aaea-a99575c408b6",
                "E01001A",
                "ANGEL1",
            ],
            "latitude": [51.5, 51.51, 51.52, 51.53],
            "longitude": [-0.1, -0.11, -0.12, -0.13],
            "date_opened": ["2018-01-01", "1973-05-01", "2019-01-01", "2001-01-01"],
        }
    )
    chosen = select_download_site_ids(list(stations["site_id"]), stations, max_stations=2)
    assert "river" not in stations.columns
    assert chosen == [
        "370cba4c-c28e-4063-aaea-a99575c408b6",
        "ANGEL1",
    ]


def test_hubeau_correcte_path_reports_zero_and_is_not_t8() -> None:
    assert HUBEAU_CORRECT_QUALIFICATION == "1"
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["hubeau_n_sites_with_sandre_correcte_observations"] == 0
    assert audit["hubeau_bulk_daily_downloads_started"] == 0
    assert audit.get("hubeau_unqualified_code_4_accepted") is False
    manifest = w6_europe_spatial_manifest(
        n_stations_catalog=1964,
        n_with_river_name=16,
        n_spatial_clusters_3plus_50km=1,
        n_spatial_clusters_3plus_100km=1,
        n_clusters_downloaded=0,
        n_complete_enough=0,
    )
    assert manifest["hubeau_correcte_t8_usable"] is False
    assert manifest["hubeau_code4_not_relabeled_as_correcte"] is True
    assert manifest["hubeau_n_sites_with_sandre_correcte_observations"] == 0
    assert manifest["countable_toward_t8"] is False
    assert manifest["passed"] is False
    assert "never as T8 Correcte" in manifest["hubeau_sandre_correcte_note"]


def test_on_disk_50km_cluster_table_is_catalog_not_t8() -> None:
    path = ROOT / "results/framework/public_catalog/uk_ea_spatial_clusters.csv"
    if not path.is_file():
        return
    frame = pd.read_csv(path)
    assert not frame.empty
    assert frame["countable_public_daily"].astype(str).str.lower().isin({"false", "0"}).all()
    assert pd.to_numeric(frame["cap_km"], errors="coerce").le(50.0).all()
    assert pd.to_numeric(frame["n_stations"], errors="coerce").ge(3).all()
    assert pd.to_numeric(frame["max_pairwise_km"], errors="coerce").le(50.0 + 1e-6).all()
