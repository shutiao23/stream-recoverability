#!/usr/bin/env python3
"""Build reviewer-requested regulation, stationarity, and robustness artifacts."""

from __future__ import annotations

import hashlib
import io
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from scipy.stats import wilcoxon

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.inference_safeguards import (
    benjamini_hochberg_by_family,
)
from stream_recoverability.analysis.recoverability_budget import (
    budget_decomposition,
)
from stream_recoverability.analysis.regulation import (
    annual_demeaned_skill_events,
    annual_thermal_metrics,
    expanded_covariate_r2,
    network_regulation_fingerprint,
    period_thermal_metrics,
    rescore_with_state_climatology,
)
from stream_recoverability.analysis.resilience import (
    cross_fitted_node_importance,
    node_importance,
)

INTERNAL_WIDE = PROJECT_ROOT / "data_versions/published_v2/daily_wide.parquet"
EXTERNAL_ROOT = PROJECT_ROOT / "data_versions/external_upper_middle_chattahoochee_v1"
EXTERNAL_WIDE = EXTERNAL_ROOT / "daily_wide.parquet"
EXTERNAL_METADATA = EXTERNAL_ROOT / "metadata/site_metadata.parquet"
EXTERNAL_RESULTS = (
    PROJECT_ROOT
    / "results/confirmatory/external_upper_middle_chattahoochee_v1/external_confirmation"
)
PREDICTIONS = PROJECT_ROOT / "results/frozen/published_v2/predictions.parquet"
EVENTS = PROJECT_ROOT / "results/frozen/published_v2/event_metrics.parquet"
FROZEN_PREDICTION = (
    PROJECT_ROOT / "results/predictions/recoverability_prediction_v1.json"
)
OUTPUT = PROJECT_ROOT / "results/revision"
FIGURES = PROJECT_ROOT / "figures/main"
TABLES = PROJECT_ROOT / "paper/tables"
GAPS = (1, 3, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180, 240, 365)
INTERNAL_STATIONS = ("B1", "S2", "P3")
EXTERNAL_STATIONS = (
    "02334430",
    "02335000",
    "02335450",
    "02336000",
    "02337170",
)
MODEL_ORDER = (
    "climatology",
    "linear",
    "pchip",
    "kalman",
    "air_only",
    "air_hydro",
    "donor_regression",
    "random_forest",
    "xgboost",
)
MODEL_COLORS = {
    "climatology": "#777777",
    "linear": "#4c78a8",
    "pchip": "#72b7b2",
    "kalman": "#54a24b",
    "air_only": "#eeca3b",
    "air_hydro": "#f58518",
    "donor_regression": "#b279a2",
    "random_forest": "#e45756",
    "xgboost": "#9d755d",
}


def _write_loeo_auc_diagnosis() -> pd.DataFrame:
    """Recompute the post-hoc LOEO diagnosis without touching the frozen panel."""

    from stream_recoverability.analysis.regulation_panel_auc_diagnosis import (
        diagnose_loeo_auc,
        fold_auc_table,
        json_safe,
    )

    predictions = pd.read_csv(
        PROJECT_ROOT
        / "results/regulation_panel_v1_legacy_transport"
        / "leave_ecoregion_out_predictions.csv"
    )
    folds = fold_auc_table(predictions)
    diagnosis = diagnose_loeo_auc(predictions, require_frozen_primary=True)
    folds.to_csv(OUTPUT / "loeo_within_fold_auc.csv", index=False)
    payload = json_safe(
        {
            **diagnosis,
            "source_predictions": (
                "results/regulation_panel_v1_legacy_transport/"
                "leave_ecoregion_out_predictions.csv"
            ),
        }
    )
    (OUTPUT / "loeo_auc_metric_diagnosis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return folds


def _file_identity(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _load_dense_predictions() -> pd.DataFrame:
    columns = [
        "date",
        "scenario_id",
        "station_id",
        "target",
        "model",
        "training_seed",
        "mask_seed",
        "gap_length",
        "y_true",
        "y_pred",
        "climatology_pred",
        "anchor_id",
        "anchor_year",
        "experiment",
        "quality_approved",
        "artificial_mask",
    ]
    table = ds.dataset(PREDICTIONS, format="parquet").to_table(
        columns=columns,
        filter=(ds.field("experiment") == "SCI_DENSE") & (ds.field("target") == "T"),
    )
    frame = table.to_pandas()
    frame["date"] = pd.to_datetime(frame["date"])
    valid = (
        frame["quality_approved"].fillna(False).astype(bool)
        & frame["artificial_mask"].fillna(False).astype(bool)
        & np.isfinite(frame[["y_true", "y_pred", "climatology_pred"]]).all(axis=1)
    )
    return frame.loc[valid].copy()


def _original_skill_events(dense: pd.DataFrame) -> pd.DataFrame:
    data = dense.copy()
    data["model_absolute_error"] = (data["y_true"] - data["y_pred"]).abs()
    data["climatology_absolute_error"] = (
        data["y_true"] - data["climatology_pred"]
    ).abs()
    keys = [
        "scenario_id",
        "station_id",
        "model",
        "training_seed",
        "mask_seed",
        "gap_length",
        "anchor_id",
        "anchor_year",
    ]
    result = (
        data.groupby(keys, dropna=False, observed=True)
        .agg(
            MAE=("model_absolute_error", "mean"),
            climatology_MAE=("climatology_absolute_error", "mean"),
            n_evaluated=("model_absolute_error", "size"),
        )
        .reset_index()
    )
    result["skill"] = np.where(
        result["climatology_MAE"].gt(0.05),
        1.0 - result["MAE"] / result["climatology_MAE"],
        np.nan,
    )
    return result


def _stratified_anchor_ci(
    group: pd.DataFrame,
    value_col: str,
    *,
    n_boot: int = 2000,
    seed: int,
) -> tuple[float, float]:
    finite = group.loc[np.isfinite(group[value_col])].copy()
    if len(finite) < 2:
        return np.nan, np.nan
    strata = [
        values[value_col].to_numpy(float)
        for _, values in finite.groupby(
            "anchor_year", dropna=False, observed=True, sort=True
        )
    ]
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot, dtype=float)
    for index in range(n_boot):
        sampled = [
            values[rng.integers(0, len(values), size=len(values))] for values in strata
        ]
        draws[index] = float(np.mean(np.concatenate(sampled)))
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def _curve_summary(
    events: pd.DataFrame,
    *,
    skill_col: str,
    climatology_mae_col: str,
    analysis: str,
) -> pd.DataFrame:
    data = events.copy()
    # Training seeds are optimisation replicates, not independent anchors.
    anchor = (
        data.groupby(
            [
                "station_id",
                "model",
                "gap_length",
                "anchor_id",
                "anchor_year",
            ],
            dropna=False,
            observed=True,
        )
        .agg(
            skill=(skill_col, "mean"),
            MAE=("MAE" if "MAE" in data else "annual_demeaned_MAE", "mean"),
            climatology_MAE=(climatology_mae_col, "mean"),
        )
        .reset_index()
    )
    rows: list[dict[str, Any]] = []
    for offset, (key, group) in enumerate(
        anchor.groupby(
            ["station_id", "model", "gap_length"],
            observed=True,
            sort=True,
        )
    ):
        station, model, gap = key
        lower, upper = _stratified_anchor_ci(group, "skill", seed=20260824 + offset)
        rows.append(
            {
                "analysis": analysis,
                "station_id": station,
                "model": model,
                "gap_length": float(gap),
                "mean_skill": float(group["skill"].mean()),
                "skill_ci_lower": lower,
                "skill_ci_upper": upper,
                "mean_MAE_degC": float(group["MAE"].mean()),
                "mean_climatology_MAE_degC": float(group["climatology_MAE"].mean()),
                "n_anchors": int(group["anchor_id"].nunique()),
                "n_anchor_year_units": len(group),
            }
        )
    return pd.DataFrame(rows)


def _best_envelope(curves: pd.DataFrame) -> pd.DataFrame:
    finite = curves.loc[np.isfinite(curves["mean_skill"])].copy()
    return (
        finite.sort_values(
            ["analysis", "station_id", "gap_length", "mean_skill", "model"],
            ascending=[True, True, True, False, True],
            kind="mergesort",
        )
        .groupby(
            ["analysis", "station_id", "gap_length"],
            as_index=False,
            observed=True,
        )
        .first()
        .rename(columns={"model": "best_model"})
    )


def _main_recoverability_table(curves: pd.DataFrame) -> pd.DataFrame:
    lookup = pd.read_csv(
        PROJECT_ROOT
        / "results/validation_funnel/published_v2/best_simple_baseline_lookup.csv"
    )
    lookup = lookup.loc[
        lookup["target"].eq("T") & lookup["mask_geometry"].eq("block"),
        ["station_id", "best_simple_baseline", "validation_mean_MAE"],
    ].rename(columns={"best_simple_baseline": "validation_selected_model"})
    selected = curves.merge(
        lookup, on="station_id", how="inner", validate="many_to_one"
    )
    selected = selected.loc[
        selected["model"].eq(selected["validation_selected_model"])
        & selected["gap_length"].isin((30, 90, 180))
    ].copy()
    frontiers = pd.read_csv(PROJECT_ROOT / "results/analysis/statistical_frontiers.csv")
    frontiers = frontiers.loc[
        frontiers["target"].eq("T"),
        [
            "station_id",
            "model",
            "statistical_frontier_days",
            "statistical_frontier_censoring",
        ],
    ]
    selected = selected.merge(
        frontiers,
        on=["station_id", "model"],
        how="left",
        validate="many_to_one",
    )
    columns = [
        "station_id",
        "gap_length",
        "validation_selected_model",
        "validation_mean_MAE",
        "mean_skill",
        "skill_ci_lower",
        "skill_ci_upper",
        "mean_MAE_degC",
        "mean_climatology_MAE_degC",
        "statistical_frontier_days",
        "statistical_frontier_censoring",
        "n_anchors",
        "n_anchor_year_units",
    ]
    if len(selected) != len(INTERNAL_STATIONS) * 3:
        raise ValueError("main recoverability table is incomplete")
    return (
        selected[columns]
        .sort_values(["station_id", "gap_length"], kind="mergesort")
        .reset_index(drop=True)
    )


def _budget_table(wide: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(wide["date"])
    periods = {
        "frozen_2006_2015": dates.between("2006-01-01", "2015-12-31"),
        "bridge_2016_2017": dates.between("2016-01-01", "2017-12-31"),
        "state_matched_2016_2020": dates.between("2016-01-01", "2020-12-31"),
    }
    parts = []
    for label, selected in periods.items():
        fit = wide.loc[selected]
        for station in INTERNAL_STATIONS:
            table = budget_decomposition(
                fit,
                station,
                tuple(value for value in INTERNAL_STATIONS if value != station),
                GAPS,
            )
            table["calibration"] = label
            table["post_hoc_state_control"] = label != "frozen_2006_2015"
            parts.append(table)
    return pd.concat(parts, ignore_index=True).rename(
        columns={"station": "station_id", "gap_length_days": "gap_length"}
    )


def _budget_evaluation(
    budgets: pd.DataFrame,
    envelopes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping = {
        "original_training_climatology": "frozen_2006_2015",
        "bridge_2016_2017_climatology": "bridge_2016_2017",
        "state_matched_2016_2020_climatology": "state_matched_2016_2020",
    }
    pieces = []
    for analysis, calibration in mapping.items():
        observed = envelopes.loc[envelopes["analysis"].eq(analysis)]
        predicted = budgets.loc[budgets["calibration"].eq(calibration)]
        merged = observed.merge(
            predicted[
                [
                    "station_id",
                    "gap_length",
                    "R2_donor",
                    "rho",
                    "predicted_skill",
                    "calibration",
                ]
            ],
            on=["station_id", "gap_length"],
            validate="one_to_one",
        )
        merged["best_exceeds_budget"] = merged["mean_skill"] > merged["predicted_skill"]
        merged["best_lower_ci_exceeds_budget"] = (
            merged["skill_ci_lower"] > merged["predicted_skill"]
        )
        merged["prediction_error"] = merged["mean_skill"] - merged["predicted_skill"]
        pieces.append(merged)
    cells = pd.concat(pieces, ignore_index=True)
    rows = []
    for (analysis, station), group in cells.groupby(
        ["analysis", "station_id"], observed=True, sort=True
    ):
        rows.append(
            {
                "analysis": analysis,
                "station_id": station,
                "correlation": float(
                    group["mean_skill"].corr(group["predicted_skill"])
                ),
                "mean_absolute_skill_error": float(
                    group["prediction_error"].abs().mean()
                ),
                "best_exceeds_budget_count": int(group["best_exceeds_budget"].sum()),
                "best_lower_ci_exceeds_budget_count": int(
                    group["best_lower_ci_exceeds_budget"].sum()
                ),
                "comparison_cells": len(group),
            }
        )
    return cells, pd.DataFrame(rows)


def _corrected_frontier_hypotheses(
    original_events: pd.DataFrame,
) -> pd.DataFrame:
    anchor = (
        original_events.groupby(
            ["station_id", "model", "anchor_id", "anchor_year"],
            dropna=False,
            observed=True,
        )["skill"]
        .mean()
        .reset_index()
    )
    rows = []
    for (station, model), group in anchor.groupby(
        ["station_id", "model"], observed=True, sort=True
    ):
        if model == "climatology":
            continue
        values = group["skill"].dropna().to_numpy(float)
        p_value = (
            np.nan
            if not len(values)
            else 1.0
            if np.allclose(values, 0.0)
            else float(wilcoxon(values, alternative="two-sided", method="auto").pvalue)
        )
        rows.append(
            {
                "station_id": station,
                "model": model,
                "estimate": float(np.mean(values)) if len(values) else np.nan,
                "n_anchor_year_units": len(values),
                "p_value": p_value,
                "hypothesis_family": "frontier_model_vs_climatology",
                "alternative": "two_sided_frozen_rule",
                "bug_fixed": (
                    "former_test_collapsed_each_station_to_one_overlap_component"
                ),
            }
        )
    return benjamini_hochberg_by_family(pd.DataFrame(rows))


def _haversine_km(
    latitude: pd.Series,
    longitude: pd.Series,
    reference_latitude: float,
    reference_longitude: float,
) -> np.ndarray:
    radius = 6371.0088
    lat1 = np.deg2rad(latitude.to_numpy(float))
    lon1 = np.deg2rad(longitude.to_numpy(float))
    lat2 = np.deg2rad(reference_latitude)
    lon2 = np.deg2rad(reference_longitude)
    dlat, dlon = lat1 - lat2, lon1 - lon2
    value = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * radius * np.arcsin(np.sqrt(value))


def _fingerprint_table(
    internal_train: pd.DataFrame,
    external_train: pd.DataFrame,
) -> pd.DataFrame:
    jinsha = network_regulation_fingerprint(internal_train, INTERNAL_STATIONS)
    jinsha["network"] = "Upper Jinsha"
    jinsha["network_order"] = [1, 2, 3]
    jinsha["station_name"] = ["Batang", "Shigu", "Panzhihua"]
    jinsha["regulation_context"] = [
        "upstream of Guanyinyan",
        "upstream of Guanyinyan",
        "27 km downstream of Guanyinyan",
    ]
    jinsha["dam_distance_km"] = [np.nan, np.nan, 27.0]
    jinsha["dam_distance_basis"] = [
        "upstream; not used as a downstream distance",
        "upstream; not used as a downstream distance",
        "MEE project description",
    ]

    chatt = network_regulation_fingerprint(external_train, EXTERNAL_STATIONS)
    metadata = pd.read_parquet(EXTERNAL_METADATA)
    metadata["station_id"] = metadata["site_id"].astype(str)
    metadata = metadata.set_index("station_id").reindex(EXTERNAL_STATIONS)
    # The first gauge is 366 m below Buford Dam (USGS station description).
    straight = _haversine_km(
        metadata["latitude"],
        metadata["longitude"],
        float(metadata.iloc[0]["latitude"]),
        float(metadata.iloc[0]["longitude"]),
    )
    chatt["network"] = "Upper--Middle Chattahoochee"
    chatt["network_order"] = np.arange(1, len(chatt) + 1)
    chatt["station_name"] = metadata["monitoring_location_name"].to_numpy()
    chatt["regulation_context"] = [
        "0.366 km below Buford Dam",
        "downstream re-equilibration reach",
        "downstream re-equilibration reach",
        "downstream re-equilibration reach",
        "downstream re-equilibration reach",
    ]
    chatt["dam_distance_km"] = straight + 0.366
    chatt.loc[chatt["station_id"].eq("02334430"), "dam_distance_km"] = 0.366
    chatt["dam_distance_basis"] = (
        "USGS 0.366 km for 02334430; otherwise straight-line proxy from that gauge"
    )
    return pd.concat([jinsha, chatt], ignore_index=True, sort=False)


def _type_horizon_sensitivity(budgets: pd.DataFrame) -> pd.DataFrame:
    horizons = (14, 30, 60, 90)
    internal = budgets.loc[
        budgets["calibration"].eq("frozen_2006_2015")
        & budgets["gap_length"].isin(horizons),
        [
            "station_id",
            "gap_length",
            "donor_component",
            "memory_component",
        ],
    ].copy()
    internal["network"] = "Upper Jinsha"
    payload = json.loads(
        (
            PROJECT_ROOT
            / "results/predictions/chattahoochee_recoverability_prediction_v1.json"
        ).read_text(encoding="utf-8")
    )
    external = pd.DataFrame(payload["predictions"]).rename(
        columns={"station": "station_id", "gap_length_days": "gap_length"}
    )
    external = external.loc[
        external["gap_length"].isin(horizons),
        [
            "station_id",
            "gap_length",
            "donor_component",
            "memory_component",
        ],
    ].copy()
    external["network"] = "Upper--Middle Chattahoochee"
    result = pd.concat([internal, external], ignore_index=True)
    result["recoverability_type"] = np.where(
        result["memory_component"].gt(result["donor_component"]),
        "memory_dominated",
        "donor_dominated",
    )
    result["classification_rule"] = (
        "memory_component_gt_donor_component_at_named_gap_horizon"
    )
    expected = (len(INTERNAL_STATIONS) + len(EXTERNAL_STATIONS)) * len(horizons)
    if len(result) != expected:
        raise ValueError("type-horizon sensitivity inventory is incomplete")
    return result.sort_values(
        ["network", "station_id", "gap_length"], kind="mergesort"
    ).reset_index(drop=True)


def _tile_coordinates(
    longitude: float, latitude: float, zoom: int
) -> tuple[float, float]:
    latitude = float(np.clip(latitude, -85.0511, 85.0511))
    scale = 2**zoom
    x = (longitude + 180.0) / 360.0 * scale
    radians = math.radians(latitude)
    y = (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * scale
    return x, y


def _tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    scale = 2**zoom
    left = x / scale * 360.0 - 180.0
    right = (x + 1) / scale * 360.0 - 180.0

    def latitude(tile_y: int) -> float:
        value = math.pi * (1.0 - 2.0 * tile_y / scale)
        return math.degrees(math.atan(math.sinh(value)))

    top = latitude(y)
    bottom = latitude(y + 1)
    return left, right, bottom, top


def _add_openstreetmap_background(
    axis: plt.Axes,
    bounds: tuple[float, float, float, float],
    *,
    zoom: int,
) -> None:
    """Add a small reproducible map-tile mosaic with an offline fallback."""

    lon_min, lon_max, lat_min, lat_max = bounds
    x0, y1 = _tile_coordinates(lon_min, lat_min, zoom)
    x1, y0 = _tile_coordinates(lon_max, lat_max, zoom)
    try:
        for tile_x in range(math.floor(x0), math.floor(x1) + 1):
            for tile_y in range(math.floor(y0), math.floor(y1) + 1):
                request = Request(
                    f"https://tile.openstreetmap.org/{zoom}/{tile_x}/{tile_y}.png",
                    headers={
                        "User-Agent": "stream-recoverability-paper-map/1.0 "
                        "(research figure; contact repository maintainer)"
                    },
                )
                with urlopen(request, timeout=20) as response:
                    image = plt.imread(io.BytesIO(response.read()), format="png")
                axis.imshow(
                    image,
                    extent=_tile_bounds(tile_x, tile_y, zoom),
                    origin="upper",
                    interpolation="bilinear",
                    zorder=0,
                )
    except (OSError, TimeoutError, URLError, ValueError):
        axis.set_facecolor("#eef3f5")
        axis.text(
            0.02,
            0.02,
            "Basemap unavailable; coordinates remain WGS84",
            transform=axis.transAxes,
            fontsize=6,
            color="#555555",
        )
    axis.set_xlim(lon_min, lon_max)
    axis.set_ylim(lat_min, lat_max)
    axis.set_aspect("equal", adjustable="box")


def _figure_study_networks() -> None:
    internal = pd.read_csv(PROJECT_ROOT / "metadata/station_metadata.csv")
    external = pd.read_parquet(EXTERNAL_METADATA)
    external["station_id"] = external["site_id"].astype(str).str.zfill(8)
    external = external.set_index("station_id").reindex(EXTERNAL_STATIONS).reset_index()
    dams = pd.read_csv(PROJECT_ROOT / "metadata/dam_metadata.csv")

    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.7), constrained_layout=True)
    panels = (
        (
            axes[0],
            internal,
            dams.loc[dams["dam_id"].eq("guanyinyan")].iloc[0],
            (98.5, 102.15, 26.2, 30.2),
            7,
            "(a) Jinsha River case-study stations",
        ),
        (
            axes[1],
            external,
            dams.loc[dams["dam_id"].eq("buford")].iloc[0],
            (-84.82, -83.92, 33.52, 34.28),
            9,
            "(b) Upper-to-Middle Chattahoochee panel",
        ),
    )
    for axis, stations, dam, bounds, zoom, title in panels:
        _add_openstreetmap_background(axis, bounds, zoom=zoom)
        longitude = stations["longitude"].to_numpy(float)
        latitude = stations["latitude"].to_numpy(float)
        axis.plot(
            longitude,
            latitude,
            color="#1f77b4",
            linewidth=1.5,
            alpha=0.75,
            zorder=3,
        )
        axis.scatter(
            longitude,
            latitude,
            s=52,
            facecolor="white",
            edgecolor="#1f4e79",
            linewidth=1.5,
            zorder=4,
            label="Temperature station",
        )
        axis.scatter(
            [dam.longitude],
            [dam.latitude],
            marker="D",
            s=62,
            color="#b23a48",
            edgecolor="white",
            linewidth=0.8,
            zorder=5,
            label="Dam",
        )
        for row in stations.itertuples(index=False):
            station_id = row.station_id
            axis.annotate(
                str(station_id),
                (row.longitude, row.latitude),
                xytext=(4, 5),
                textcoords="offset points",
                fontsize=7,
                fontweight="bold",
                zorder=6,
            )
        axis.annotate(
            dam.dam_name,
            (dam.longitude, dam.latitude),
            xytext=(5, -12),
            textcoords="offset points",
            fontsize=7,
            color="#8c1d2c",
            fontweight="bold",
            zorder=6,
        )
        axis.set(title=title, xlabel="Longitude", ylabel="Latitude")
        axis.grid(color="white", linewidth=0.5, alpha=0.65)
    axes[0].legend(frameon=True, fontsize=7, loc="upper right")
    axes[1].text(
        0.99,
        0.01,
        "© OpenStreetMap contributors | WGS84 coordinates",
        transform=axes[1].transAxes,
        ha="right",
        va="bottom",
        fontsize=6,
        color="#444444",
    )
    figure.suptitle(
        "Study networks, monitoring stations, and regulating dams",
        fontsize=14,
    )
    figure.savefig(FIGURES / "figure_01.png", dpi=300)
    plt.close(figure)


def _figure_01(
    annual: pd.DataFrame,
    fingerprints: pd.DataFrame,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), constrained_layout=True)
    style = {
        "B1": ("#4c78a8", "o", "-"),
        "S2": ("#2a9d8f", "^", "--"),
        "P3": ("#d1495b", "s", "-."),
    }
    for station in INTERNAL_STATIONS:
        color, marker, linestyle = style[station]
        selected = annual.loc[annual["station_id"].eq(station)]
        axes[0, 0].plot(
            selected["year"],
            selected["annual_minimum_degC"],
            marker=marker,
            linestyle=linestyle,
            label=station,
            color=color,
        )
        axes[0, 1].plot(
            selected["year"],
            selected["annual_amplitude_degC"],
            marker=marker,
            linestyle=linestyle,
            label=station,
            color=color,
        )
    for axis in axes[0]:
        axis.axvspan(2014.8, 2016.0, color="#e45756", alpha=0.10)
        axis.axvline(2014.97, color="#8c2d2d", linestyle="--", linewidth=1)
        axis.grid(alpha=0.2)
        axis.set_xlabel("Year")
    axes[0, 0].set(title="(a) Annual minimum temperature", ylabel="Temperature (°C)")
    axes[0, 1].set(title="(b) Annual thermal amplitude", ylabel="Amplitude (°C)")
    axes[0, 0].legend(frameon=False, ncol=3)
    axes[0, 1].text(
        2015.05,
        axes[0, 1].get_ylim()[1],
        "Guanyinyan first unit\n20 Dec 2014",
        va="top",
        fontsize=8,
    )

    markers = {"donor_dominated": "o", "memory_dominated": "s"}
    colors = {"Upper Jinsha": "#4c78a8", "Upper--Middle Chattahoochee": "#f58518"}
    for row in fingerprints.itertuples(index=False):
        axes[1, 0].scatter(
            row.training_observed_range_degC,
            row.acf30,
            color=colors[row.network],
            marker=markers[row.recoverability_type],
            s=70,
        )
        axes[1, 0].annotate(
            str(row.station_id),
            (row.training_observed_range_degC, row.acf30),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=7,
        )
    axes[1, 0].set(
        title="(c) Regulation fingerprint and covariance type",
        xlabel="Training-period observed temperature range (°C)",
        ylabel="30-day anomaly autocorrelation",
    )
    axes[1, 0].grid(alpha=0.2)

    chatt = fingerprints.loc[
        fingerprints["network"].eq("Upper--Middle Chattahoochee")
    ].sort_values("network_order")
    axes[1, 1].plot(
        chatt["network_order"],
        chatt["training_observed_range_degC"],
        marker="o",
        color="#4c78a8",
        label="Observed range",
    )
    memory_axis = axes[1, 1].twinx()
    memory_axis.plot(
        chatt["network_order"],
        chatt["acf30"],
        marker="s",
        color="#e45756",
        label="acf30",
    )
    axes[1, 1].axvspan(0.8, 1.2, color="#e45756", alpha=0.10)
    axes[1, 1].set_xticks(chatt["network_order"])
    axes[1, 1].set_xticklabels(chatt["station_id"], rotation=35, ha="right", fontsize=7)
    axes[1, 1].set(
        title="(d) Thermal re-equilibration below Buford Dam",
        xlabel="Downstream station order",
        ylabel="Training-period observed range (°C)",
    )
    memory_axis.set_ylabel("30-day anomaly autocorrelation")
    axes[1, 1].grid(alpha=0.2)
    handles1, labels1 = axes[1, 1].get_legend_handles_labels()
    handles2, labels2 = memory_axis.get_legend_handles_labels()
    axes[1, 1].legend(handles1 + handles2, labels1 + labels2, frameon=False, fontsize=8)
    figure.suptitle(
        "Reservoir-associated thermal structure across two river networks",
        fontsize=14,
    )
    figure.savefig(FIGURES / "figure_02.png", dpi=300)
    plt.close(figure)


def _figure_02(cells: pd.DataFrame) -> None:
    figure, axes = plt.subplots(
        1, 3, figsize=(12.2, 3.9), sharey=True, constrained_layout=True
    )
    for axis, station in zip(axes, INTERNAL_STATIONS, strict=True):
        original = cells.loc[
            cells["analysis"].eq("original_training_climatology")
            & cells["station_id"].eq(station)
        ].sort_values("gap_length")
        controlled = cells.loc[
            cells["analysis"].eq("state_matched_2016_2020_climatology")
            & cells["station_id"].eq(station)
        ].sort_values("gap_length")
        axis.plot(
            original["gap_length"],
            original["predicted_skill"],
            color="black",
            linewidth=2,
            label="Frozen covariance heuristic",
        )
        axis.plot(
            original["gap_length"],
            original["mean_skill"],
            color="#e45756",
            marker="o",
            markersize=3,
            label="Original best envelope",
        )
        axis.fill_between(
            original["gap_length"],
            original["skill_ci_lower"],
            original["skill_ci_upper"],
            color="#e45756",
            alpha=0.12,
        )
        axis.plot(
            controlled["gap_length"],
            controlled["predicted_skill"],
            color="#4c78a8",
            linestyle="--",
            label="2016--2020 recalibrated heuristic (post hoc)",
        )
        axis.plot(
            controlled["gap_length"],
            controlled["mean_skill"],
            color="#4c78a8",
            marker="s",
            markersize=3,
            label="2016--2020 state-climatology envelope",
        )
        axis.axhline(0, color="#777777", linewidth=0.8)
        axis.set_xscale("log")
        axis.set_title(station)
        axis.set_xlabel("Gap length (days, log scale)")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Climatology-relative skill")
    axes[-1].legend(frameon=False, fontsize=7, loc="best")
    figure.suptitle(
        "Frozen covariance heuristic and post-hoc state-matched sensitivity",
        fontsize=14,
    )
    figure.savefig(FIGURES / "figure_03.png", dpi=300)
    plt.close(figure)


def _figure_03(curves: pd.DataFrame) -> None:
    selected_models = (
        "linear",
        "kalman",
        "donor_regression",
        "random_forest",
        "xgboost",
    )
    data = curves.loc[
        curves["analysis"].eq("original_training_climatology")
        & curves["model"].isin(selected_models)
    ]
    figure, axes = plt.subplots(
        2, 3, figsize=(12.2, 7.0), sharex=True, constrained_layout=True
    )
    for column, station in enumerate(INTERNAL_STATIONS):
        selected = data.loc[data["station_id"].eq(station)]
        for model in selected_models:
            line = selected.loc[selected["model"].eq(model)].sort_values("gap_length")
            axes[0, column].plot(
                line["gap_length"],
                line["mean_skill"],
                label=model,
                color=MODEL_COLORS[model],
            )
            axes[1, column].plot(
                line["gap_length"],
                line["mean_MAE_degC"],
                label=model,
                color=MODEL_COLORS[model],
            )
        baseline = selected.groupby("gap_length", as_index=False)[
            "mean_climatology_MAE_degC"
        ].mean()
        axes[1, column].plot(
            baseline["gap_length"],
            baseline["mean_climatology_MAE_degC"],
            color="black",
            linestyle="--",
            linewidth=1.5,
            label="climatology MAE",
        )
        axes[0, column].axhline(0, color="#777777", linewidth=0.8)
        axes[0, column].set_ylim(-0.5, 1.05)
        axes[0, column].set_title(station)
        axes[1, column].set_xlabel("Gap length (days, log scale)")
        for row in range(2):
            axes[row, column].set_xscale("log")
            axes[row, column].grid(alpha=0.2)
    axes[0, 0].set_ylabel("Skill vs training climatology")
    axes[0, 0].text(
        0.02,
        0.03,
        "Values below -0.5 clipped; absolute errors shown below",
        transform=axes[0, 0].transAxes,
        fontsize=7,
    )
    axes[1, 0].set_ylabel("MAE (°C)")
    axes[1, -1].legend(frameon=False, fontsize=7, ncol=2)
    figure.suptitle(
        "Recoverability frontier in relative and absolute units", fontsize=14
    )
    figure.savefig(FIGURES / "figure_04.png", dpi=300)
    plt.close(figure)


def _figure_04(importance: pd.DataFrame) -> None:
    data = importance.copy()
    figure, axes = plt.subplots(
        1, 3, figsize=(11.5, 3.8), sharey=True, constrained_layout=True
    )
    for axis, station in zip(axes, INTERNAL_STATIONS, strict=True):
        selected = data.loc[data["station_id"].eq(station)]
        grouped = selected.sort_values("impact", ascending=False).reset_index(drop=True)
        colors = np.where(grouped["impact"].ge(0), "#4c78a8", "#9d755d")
        bar_kwargs = {
            "color": colors,
            "edgecolor": "black",
            "linewidth": 0.5,
        }
        if (
            "impact_ci_lower" in grouped
            and grouped["impact_ci_lower"].notna().all()
            and grouped["impact_ci_upper"].notna().all()
        ):
            lower = grouped["impact"] - grouped["impact_ci_lower"]
            upper = grouped["impact_ci_upper"] - grouped["impact"]
            bar_kwargs["yerr"] = np.vstack([lower.clip(lower=0), upper.clip(lower=0)])
            bar_kwargs["capsize"] = 3
        axis.bar(grouped["failed_station_id"], grouped["impact"], **bar_kwargs)
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_title(f"Target {station}")
        axis.set_xlabel("Failed station")
        axis.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Cross-fitted MAE difference (°C)")
    figure.suptitle(
        "Node importance from leave-one-year-out model selection",
        fontsize=13,
    )
    figure.savefig(FIGURES / "figure_05.png", dpi=300)
    plt.close(figure)


def _external_confirmation_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    event_path = EXTERNAL_RESULTS / "event_metrics.parquet"
    completion_path = EXTERNAL_RESULTS / "completion_manifest.json"
    if not event_path.is_file() or not completion_path.is_file():
        return pd.DataFrame(), pd.DataFrame()
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if (
        completion.get("complete") is not True
        or completion.get("formal_evidence") is not True
    ):
        raise ValueError(
            "external confirmation manifest is not complete formal evidence"
        )
    columns = [
        "station_id",
        "model",
        "gap_length",
        "pattern",
        "mask_type",
        "information_condition",
        "MAE",
        "skill",
        "n_evaluated",
    ]
    events = pd.read_parquet(event_path, columns=columns)
    eligible = events.loc[
        events["mask_type"].astype(str).eq("block")
        & events["pattern"].astype(str).eq("T")
        & events["information_condition"].astype(str).eq("full_information")
    ].copy()
    if len(eligible) != len(EXTERNAL_STATIONS) * 3 * len(MODEL_ORDER):
        raise ValueError("external full-information block inventory is incomplete")
    eligible["station_id"] = eligible["station_id"].astype(str).str.zfill(8)
    best = (
        eligible.sort_values(
            ["station_id", "gap_length", "skill", "model"],
            ascending=[True, True, False, True],
            kind="mergesort",
        )
        .groupby(["station_id", "gap_length"], as_index=False, observed=True)
        .first()
        .rename(
            columns={
                "model": "best_model",
                "MAE": "best_MAE_degC",
                "skill": "best_skill",
            }
        )
    )

    validation_path = (
        OUTPUT
        / "external_validation_uncertainty"
        / "external_validation_uncertainty_seed_cells.csv"
    )
    if not validation_path.is_file():
        raise FileNotFoundError(
            "run scripts/36_run_external_validation_uncertainty.py before "
            "building the fixed-model external sensitivity"
        )
    validation = pd.read_csv(validation_path, dtype={"station_id": str})
    validation["station_id"] = validation["station_id"].str.zfill(8)
    validation = validation.loc[
        validation["gap_length"].isin((30, 90, 180))
        & validation["model"].isin(MODEL_ORDER)
        & np.isfinite(validation["skill"])
    ].copy()
    expected_validation = len(EXTERNAL_STATIONS) * 3 * len(MODEL_ORDER) * 20
    if len(validation) != expected_validation:
        raise ValueError("external validation model-selection inventory is incomplete")
    tie_order = {model: index for index, model in enumerate(MODEL_ORDER)}
    validation_ranking = (
        validation.groupby(["station_id", "model"], as_index=False, observed=True)
        .agg(
            validation_mean_skill=("skill", "mean"),
            validation_mean_MAE_degC=("MAE", "mean"),
            validation_cells=("skill", "size"),
        )
        .assign(model_tie_order=lambda frame: frame["model"].map(tie_order))
        .sort_values(
            ["station_id", "validation_mean_skill", "model_tie_order", "model"],
            ascending=[True, False, True, True],
            kind="mergesort",
        )
        .groupby("station_id", as_index=False, observed=True)
        .first()
        .rename(columns={"model": "validation_selected_model"})
    )
    selected = eligible.merge(
        validation_ranking,
        on="station_id",
        how="inner",
        validate="many_to_one",
    )
    selected = selected.loc[
        selected["model"].eq(selected["validation_selected_model"])
    ].rename(columns={"MAE": "selected_MAE_degC", "skill": "selected_skill"})
    if len(selected) != len(EXTERNAL_STATIONS) * 3:
        raise ValueError("validation-selected external cells are incomplete")
    best = best.merge(
        selected[
            [
                "station_id",
                "gap_length",
                "validation_selected_model",
                "validation_mean_skill",
                "validation_mean_MAE_degC",
                "validation_cells",
                "selected_MAE_degC",
                "selected_skill",
            ]
        ],
        on=["station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    prediction_payload = json.loads(
        (
            PROJECT_ROOT
            / "results/predictions/chattahoochee_recoverability_prediction_v1.json"
        ).read_text(encoding="utf-8")
    )
    predictions = pd.DataFrame(prediction_payload["predictions"]).rename(
        columns={"station": "station_id", "gap_length_days": "gap_length"}
    )
    best = best.merge(
        predictions[["station_id", "gap_length", "predicted_skill", "R2_donor", "rho"]],
        on=["station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    best["selected_prediction_error"] = best["selected_skill"] - best["predicted_skill"]
    best["best_envelope_prediction_error"] = (
        best["best_skill"] - best["predicted_skill"]
    )
    types = pd.Series(prediction_payload["station_types"], name="recoverability_type")
    rows = []
    for station, group in best.groupby("station_id", observed=True, sort=True):
        curve = group.set_index("gap_length").sort_index()
        station_type = str(types.loc[str(station)])
        decline = float(curve.loc[30.0, "best_skill"] - curve.loc[180.0, "best_skill"])
        long_skill = float(curve.loc[180.0, "best_skill"])
        rows.append(
            {
                "station_id": station,
                "predicted_type": station_type,
                "validation_selected_model": str(
                    curve.loc[30.0, "validation_selected_model"]
                ),
                "observed_selected_skill_30d": float(curve.loc[30.0, "selected_skill"]),
                "observed_selected_skill_90d": float(curve.loc[90.0, "selected_skill"]),
                "observed_selected_skill_180d": float(
                    curve.loc[180.0, "selected_skill"]
                ),
                "observed_best_skill_30d": float(curve.loc[30.0, "best_skill"]),
                "observed_best_skill_90d": float(curve.loc[90.0, "best_skill"]),
                "observed_best_skill_180d": long_skill,
                "observed_30_to_180d_decline": decline,
                "best_model_30d": str(curve.loc[30.0, "best_model"]),
                "best_model_90d": str(curve.loc[90.0, "best_model"]),
                "best_model_180d": str(curve.loc[180.0, "best_model"]),
                "evaluate_once": True,
                "model_selection_on_confirmatory": False,
                "selection_source": (
                    "post_frozen_2021_2022_validation_placement_diagnostic"
                ),
                "primary_external_estimand": "validation_selected_fixed_model",
                "best_envelope_role": "descriptive_only",
            }
        )
    summary = pd.DataFrame(rows)
    memory = summary.loc[summary["predicted_type"].eq("memory_dominated")]
    donors = summary.loc[summary["predicted_type"].eq("donor_dominated")]
    if len(memory) != 1 or donors.empty:
        raise ValueError("external prediction requires one memory and surviving donors")
    memory_decline = float(memory.iloc[0]["observed_30_to_180d_decline"])
    memory_long_skill = float(memory.iloc[0]["observed_best_skill_180d"])
    summary["frozen_best_envelope_consistent"] = np.where(
        summary["predicted_type"].eq("memory_dominated"),
        (memory_decline > donors["observed_30_to_180d_decline"].max())
        & (memory_long_skill < donors["observed_best_skill_180d"].min()),
        summary["observed_best_skill_180d"].gt(memory_long_skill),
    )
    memory_selected_90 = float(memory.iloc[0]["observed_selected_skill_90d"])
    memory_selected_180 = float(memory.iloc[0]["observed_selected_skill_180d"])
    summary["qualitative_prediction_consistent"] = np.where(
        summary["predicted_type"].eq("memory_dominated"),
        (memory_selected_90 < donors["observed_selected_skill_90d"].min())
        & (memory_selected_180 < donors["observed_selected_skill_180d"].min()),
        summary["observed_selected_skill_90d"].gt(memory_selected_90)
        & summary["observed_selected_skill_180d"].gt(memory_selected_180),
    )
    summary["consistency_rule"] = (
        "validation-selected fixed model: memory site is weakest at 90 and 180 days"
    )
    return best, summary


def _figure_05(
    cells: pd.DataFrame,
    summary: pd.DataFrame,
    fingerprints: pd.DataFrame,
    placement: pd.DataFrame,
) -> None:
    if cells.empty or summary.empty or placement.empty:
        return
    placement = placement.copy()
    placement["station_id"] = placement["station_id"].astype(str).str.zfill(8)
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), constrained_layout=True)
    for station in EXTERNAL_STATIONS:
        curve = cells.loc[cells["station_id"].astype(str).eq(station)].sort_values(
            "gap_length"
        )
        uncertainty = placement.loc[
            placement["station_id"].eq(station)
            & placement["gap_length"].isin(curve["gap_length"])
            & placement["model"].eq(curve["validation_selected_model"].iloc[0])
        ].sort_values("gap_length")
        if len(uncertainty) != len(curve):
            raise ValueError(f"validation placement SD is incomplete for {station}")
        memory = station == "02334430"
        color = "#e45756" if memory else "#777777"
        alpha = 1.0 if memory else 0.65
        axes[0].errorbar(
            curve["gap_length"],
            curve["selected_skill"],
            yerr=uncertainty["skill_sd"],
            color=color,
            alpha=alpha,
            marker="o",
            capsize=2,
            linewidth=1.2,
            label=station,
        )
        axes[0].plot(
            curve["gap_length"],
            curve["predicted_skill"],
            color=color,
            alpha=alpha,
            linestyle="--",
        )
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set(
        title="(a) Validation-selected fixed model",
        xlabel="Gap length (days)",
        ylabel="Skill vs external training climatology",
        xticks=[30, 90, 180],
    )
    axes[0].grid(alpha=0.2)
    axes[0].legend(
        frameon=False,
        fontsize=7,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
    )

    chatt = fingerprints.loc[fingerprints["network"].eq("Upper--Middle Chattahoochee")][
        ["station_id", "acf30", "training_observed_range_degC"]
    ]
    plotted = summary.merge(chatt, on="station_id", validate="one_to_one")
    label_offsets = {
        "02334430": (5, 4),
        "02335000": (5, 8),
        "02335450": (5, -13),
        "02336000": (5, 10),
        "02337170": (5, -12),
    }
    for row in plotted.itertuples(index=False):
        memory = row.predicted_type == "memory_dominated"
        placement_sd = float(
            placement.loc[
                placement["station_id"].eq(str(row.station_id))
                & placement["gap_length"].eq(180)
                & placement["model"].eq(row.validation_selected_model),
                "skill_sd",
            ].iloc[0]
        )
        axes[1].errorbar(
            [row.acf30],
            [row.observed_selected_skill_180d],
            yerr=[placement_sd],
            marker="s" if memory else "o",
            color="#e45756" if memory else "#4c78a8",
            markersize=7,
            capsize=3,
            linestyle="none",
        )
        axes[1].annotate(
            row.station_id,
            (row.acf30, row.observed_selected_skill_180d),
            xytext=label_offsets[str(row.station_id)],
            textcoords="offset points",
            fontsize=7,
        )
    axes[1].set(
        title="(b) Thermal memory and long-gap recovery",
        xlabel="Training anomaly acf30",
        ylabel="Fixed-model skill at 180 days",
    )
    axes[1].grid(alpha=0.2)
    figure.suptitle(
        "Held-out Chattahoochee post-hoc fixed-model sensitivity",
        fontsize=13,
    )
    figure.savefig(FIGURES / "figure_06.png", dpi=300)
    plt.close(figure)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)

    internal = pd.read_parquet(INTERNAL_WIDE)
    internal["date"] = pd.to_datetime(internal["date"])
    internal_train = internal.loc[internal["split"].eq("train")].copy()
    external = pd.read_parquet(EXTERNAL_WIDE)
    external["date"] = pd.to_datetime(external["date"])
    external_train = external.loc[external["split"].eq("train")].copy()

    annual = annual_thermal_metrics(internal, INTERNAL_STATIONS)
    periods = period_thermal_metrics(
        internal,
        INTERNAL_STATIONS,
        {
            "pre_impoundment_2006_2014": ("2006-01-01", "2014-12-31"),
            "post_impoundment_2015_2020": ("2015-01-01", "2020-12-31"),
            "frozen_training_2006_2015": ("2006-01-01", "2015-12-31"),
            "validation_2016_2017": ("2016-01-01", "2017-12-31"),
            "evaluation_2018_2020": ("2018-01-01", "2020-12-31"),
        },
        climatology_fit_frame=internal_train,
    )
    fingerprints = _fingerprint_table(internal_train, external_train)
    covariates = expanded_covariate_r2(internal_train, INTERNAL_STATIONS)
    budgets = _budget_table(internal)
    type_sensitivity = _type_horizon_sensitivity(budgets)

    dense = _load_dense_predictions()
    original_events = _original_skill_events(dense)
    original_curves = _curve_summary(
        original_events,
        skill_col="skill",
        climatology_mae_col="climatology_MAE",
        analysis="original_training_climatology",
    )
    canonical = pd.read_csv(
        PROJECT_ROOT / "results/analysis/frontier_climatology_curves.csv"
    )
    canonical = canonical.loc[canonical["target"].astype(str).eq("T")].rename(
        columns={
            "mean_skill": "canonical_mean_skill",
            "ci_lower": "canonical_skill_ci_lower",
            "ci_upper": "canonical_skill_ci_upper",
        }
    )
    original_curves = original_curves.merge(
        canonical[
            [
                "station_id",
                "model",
                "gap_length",
                "canonical_mean_skill",
                "canonical_skill_ci_lower",
                "canonical_skill_ci_upper",
            ]
        ],
        on=["station_id", "model", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    if original_curves["canonical_mean_skill"].isna().any():
        raise ValueError("canonical formal curve does not cover revision MAE rows")
    original_curves["mean_skill"] = original_curves.pop("canonical_mean_skill")
    original_curves["skill_ci_lower"] = original_curves.pop("canonical_skill_ci_lower")
    original_curves["skill_ci_upper"] = original_curves.pop("canonical_skill_ci_upper")
    bridge_events = rescore_with_state_climatology(
        dense,
        internal,
        INTERNAL_STATIONS,
        fit_start="2016-01-01",
        fit_end="2017-12-31",
    )
    bridge_curves = _curve_summary(
        bridge_events,
        skill_col="state_climatology_skill",
        climatology_mae_col="state_climatology_MAE",
        analysis="bridge_2016_2017_climatology",
    )
    state_events = rescore_with_state_climatology(
        dense,
        internal,
        INTERNAL_STATIONS,
        fit_start="2016-01-01",
        fit_end="2020-12-31",
    )
    state_curves = _curve_summary(
        state_events,
        skill_col="state_climatology_skill",
        climatology_mae_col="state_climatology_MAE",
        analysis="state_matched_2016_2020_climatology",
    )
    demeaned_events = annual_demeaned_skill_events(dense)
    demeaned_curves = _curve_summary(
        demeaned_events,
        skill_col="annual_demeaned_skill",
        climatology_mae_col="annual_demeaned_climatology_MAE",
        analysis="annual_mean_removed",
    )
    curves = pd.concat(
        [original_curves, bridge_curves, state_curves, demeaned_curves],
        ignore_index=True,
    )
    envelopes = _best_envelope(curves)
    budget_cells, budget_summary = _budget_evaluation(budgets, envelopes)
    hypotheses = _corrected_frontier_hypotheses(original_events)
    main_recoverability = _main_recoverability_table(original_curves)

    network_events = pd.read_parquet(EVENTS)
    network_events = network_events.loc[
        network_events["experiment"].astype(str).eq("SCI_NET")
    ].copy()
    oracle_importance = node_importance(network_events, value_col="MAE")
    importance = cross_fitted_node_importance(network_events, value_col="MAE")
    external_cells, external_summary = _external_confirmation_tables()
    placement_path = (
        OUTPUT
        / "external_validation_uncertainty/external_validation_uncertainty_cells.csv"
    )
    if not placement_path.is_file():
        raise FileNotFoundError(
            "run scripts/36_run_external_validation_uncertainty.py before revision figures"
        )
    external_placement = pd.read_csv(placement_path, dtype={"station_id": str})

    outputs = {
        "annual_thermal_metrics.csv": annual,
        "period_thermal_metrics.csv": periods,
        "regulation_fingerprint.csv": fingerprints,
        "recoverability_type_horizon_sensitivity.csv": type_sensitivity,
        "expanded_covariate_budget.csv": covariates,
        "stationarity_controlled_budgets.csv": budgets,
        "dense_skill_sensitivities.csv": curves,
        "best_envelope_sensitivities.csv": envelopes,
        "budget_evaluation_cells.csv": budget_cells,
        "budget_evaluation_summary.csv": budget_summary,
        "annual_demeaned_skill_events.csv": demeaned_events,
        "frontier_hypothesis_tests_corrected.csv": hypotheses,
        "node_importance_best_available.csv": oracle_importance,
        "node_importance_cross_fitted.csv": importance,
        "external_confirmation_cells.csv": external_cells,
        "external_confirmation_summary.csv": external_summary,
        "loeo_within_fold_auc.csv": _write_loeo_auc_diagnosis(),
    }
    for name, frame in outputs.items():
        frame.to_csv(OUTPUT / name, index=False)

    # Main tables are now mechanism/frontier tables, not validation rankings.
    fingerprints.to_csv(TABLES / "table_01.csv", index=False)
    annual.to_csv(TABLES / "table_02.csv", index=False)
    budget_summary.to_csv(TABLES / "table_03.csv", index=False)
    main_recoverability.to_csv(TABLES / "table_04.csv", index=False)
    importance.to_csv(TABLES / "table_05.csv", index=False)

    _figure_study_networks()
    _figure_01(annual, fingerprints)
    _figure_02(budget_cells)
    _figure_03(curves)
    _figure_04(importance)
    _figure_05(
        external_cells,
        external_summary,
        fingerprints,
        external_placement,
    )
    regulation_panel_figure = (
        PROJECT_ROOT
        / "results/regulation_panel_v1_legacy_transport/figure_06_regulation_panel.png"
    )
    if not regulation_panel_figure.is_file():
        raise FileNotFoundError(
            "run scripts/38_run_regulation_panel.py before revision figures"
        )
    shutil.copyfile(regulation_panel_figure, FIGURES / "figure_07.png")

    figure_titles = {
        1: "Study networks, monitoring stations, and regulating dams",
        2: "Reservoir-associated thermal structure across two networks",
        3: "Frozen covariance heuristic and post-hoc thermal-state control",
        4: "Recoverability in relative and absolute units",
        5: "Cross-fitted node importance",
        6: "Held-out Chattahoochee fixed-model evaluation",
        7: "Nationwide regulation-panel generalization test",
    }
    figure_manifest = {
        "schema_version": "major_revision_figure_manifest_v1",
        "status": "complete",
        "figures": {
            f"figure_{index:02d}": {
                **_file_identity(FIGURES / f"figure_{index:02d}.png"),
                "title": title,
            }
            for index, title in figure_titles.items()
        },
    }
    (FIGURES / "figure_manifest.json").write_text(
        json.dumps(figure_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    table_titles = {
        1: "Eight-station regulation fingerprint",
        2: "Annual Upper Jinsha thermal statistics",
        3: "Frozen and stationarity-controlled covariance-heuristic evaluation",
        4: "Dense recoverability in relative and absolute units",
        5: "Leave-one-year-out cross-fitted node importance",
    }
    table_manifest = {
        "schema_version": "major_revision_table_manifest_v1",
        "status": "complete",
        "tables": {
            f"table_{index:02d}": {
                **_file_identity(TABLES / f"table_{index:02d}.csv"),
                "title": title,
                "rows": len(pd.read_csv(TABLES / f"table_{index:02d}.csv")),
            }
            for index, title in table_titles.items()
        },
    }
    (TABLES / "table_manifest.json").write_text(
        json.dumps(table_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "major_revision_analysis_v1",
        "status": "complete",
        "review_triggered_post_hoc": True,
        "frozen_prediction_unchanged": True,
        "frozen_prediction_path": str(FROZEN_PREDICTION.relative_to(PROJECT_ROOT)),
        "artifacts": {
            name: {"rows": len(frame), "columns": list(frame.columns)}
            for name, frame in outputs.items()
        },
        "figures": [f"figures/main/figure_{index:02d}.png" for index in range(1, 8)],
        "main_tables": [f"paper/tables/table_{index:02d}.csv" for index in range(1, 6)],
        "interpretation_guard": (
            "state-matched and annual-demeaned analyses are reviewer-requested "
            "post-hoc diagnostics, not a replacement for the frozen prediction"
        ),
        "regulation_panel_auc_diagnosis_note": (
            "LOEO AUC diagnosis is post-hoc and does not replace the frozen "
            "panel report"
        ),
    }
    diagnosis_payload = json.loads(
        (OUTPUT / "loeo_auc_metric_diagnosis.json").read_text(encoding="utf-8")
    )
    manifest["artifacts"]["loeo_auc_metric_diagnosis.json"] = {
        "rows": 1,
        "columns": list(diagnosis_payload),
    }
    (OUTPUT / "revision_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    final_manifest = {
        "schema_version": "major_revision_publication_manifest_v1",
        "status": "complete",
        "analysis_manifest": _file_identity(OUTPUT / "revision_analysis_manifest.json"),
        "formal_internal_manifest": _file_identity(
            PROJECT_ROOT / "results/analysis/analysis_manifest.json"
        ),
        "external_completion_manifest": _file_identity(
            EXTERNAL_RESULTS / "completion_manifest.json"
        ),
        "external_validation_uncertainty_manifest": _file_identity(
            OUTPUT
            / "external_validation_uncertainty/external_validation_uncertainty_manifest.json"
        ),
        "p3_change_point_manifest": _file_identity(
            OUTPUT / "p3_change_point_manifest.json"
        ),
        "regulation_panel_manifest": _file_identity(
            PROJECT_ROOT
            / "results/regulation_panel_v1_legacy_transport/artifact_manifest.json"
        ),
        "figure_manifest": _file_identity(FIGURES / "figure_manifest.json"),
        "table_manifest": _file_identity(TABLES / "table_manifest.json"),
    }
    (PROJECT_ROOT / "results/final_results_manifest.json").write_text(
        json.dumps(final_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "complete", "artifacts": len(outputs)}, sort_keys=True))


if __name__ == "__main__":
    main()
