#!/usr/bin/env python3
"""Build reviewer-requested regulation, stationarity, and robustness artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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
from stream_recoverability.analysis.resilience import node_importance

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


def _figure_01(
    annual: pd.DataFrame,
    fingerprints: pd.DataFrame,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.0), constrained_layout=True)
    for station, color in zip(INTERNAL_STATIONS, ("#4c78a8", "#54a24b", "#e45756")):
        selected = annual.loc[annual["station_id"].eq(station)]
        axes[0, 0].plot(
            selected["year"],
            selected["annual_minimum_degC"],
            marker="o",
            label=station,
            color=color,
        )
        axes[0, 1].plot(
            selected["year"],
            selected["annual_amplitude_degC"],
            marker="o",
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
        label="Annual amplitude",
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
        "Reservoir regulation compresses seasonality and lengthens thermal memory",
        fontsize=14,
    )
    figure.savefig(FIGURES / "figure_01.png", dpi=300)
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
            label="Frozen budget",
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
            label="2016--2020 recalibrated budget (post hoc)",
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
        "Frozen prediction and post-hoc state-matched sensitivity", fontsize=14
    )
    figure.savefig(FIGURES / "figure_02.png", dpi=300)
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
    figure.savefig(FIGURES / "figure_03.png", dpi=300)
    plt.close(figure)


def _figure_04(importance: pd.DataFrame) -> None:
    data = importance.copy()
    figure, axes = plt.subplots(
        1, 3, figsize=(11.5, 3.8), sharey=True, constrained_layout=True
    )
    for axis, station in zip(axes, INTERNAL_STATIONS, strict=True):
        selected = data.loc[data["station_id"].eq(station)]
        grouped = (
            selected.groupby("failed_station_id", as_index=False)["impact"]
            .mean()
            .sort_values("impact", ascending=False)
        )
        colors = np.where(grouped["impact"].ge(0), "#e45756", "#54a24b")
        axis.bar(grouped["failed_station_id"], grouped["impact"], color=colors)
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_title(f"Target {station}")
        axis.set_xlabel("Failed station")
        axis.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Best-achievable MAE increase (°C)")
    figure.suptitle(
        "Node importance after best-model reselection and climatology capping",
        fontsize=13,
    )
    figure.savefig(FIGURES / "figure_04.png", dpi=300)
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
    best["prediction_error"] = best["best_skill"] - best["predicted_skill"]
    types = pd.Series(prediction_payload["station_types"], name="recoverability_type")
    rows = []
    for station, group in best.groupby("station_id", observed=True, sort=True):
        curve = group.set_index("gap_length").sort_index()
        station_type = str(types.loc[str(station)])
        decline = float(curve.loc[30.0, "best_skill"] - curve.loc[180.0, "best_skill"])
        long_skill = float(curve.loc[180.0, "best_skill"])
        shape_confirmed = (
            decline > 0.25 and long_skill < 0.25
            if station_type == "memory_dominated"
            else long_skill > 0.40
        )
        rows.append(
            {
                "station_id": station,
                "predicted_type": station_type,
                "observed_best_skill_30d": float(curve.loc[30.0, "best_skill"]),
                "observed_best_skill_90d": float(curve.loc[90.0, "best_skill"]),
                "observed_best_skill_180d": long_skill,
                "observed_30_to_180d_decline": decline,
                "best_model_30d": str(curve.loc[30.0, "best_model"]),
                "best_model_90d": str(curve.loc[90.0, "best_model"]),
                "best_model_180d": str(curve.loc[180.0, "best_model"]),
                "shape_rule": (
                    "decline_gt_0.25_and_180d_skill_lt_0.25"
                    if station_type == "memory_dominated"
                    else "180d_skill_gt_0.40"
                ),
                "shape_confirmed": bool(shape_confirmed),
                "evaluate_once": True,
                "model_selection_on_confirmatory": False,
            }
        )
    return best, pd.DataFrame(rows)


def _figure_05(
    cells: pd.DataFrame,
    summary: pd.DataFrame,
    fingerprints: pd.DataFrame,
) -> None:
    if cells.empty or summary.empty:
        return
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.1), constrained_layout=True)
    for station in EXTERNAL_STATIONS:
        curve = cells.loc[cells["station_id"].astype(str).eq(station)].sort_values(
            "gap_length"
        )
        memory = station == "02334430"
        color = "#e45756" if memory else "#777777"
        alpha = 1.0 if memory else 0.65
        axes[0].plot(
            curve["gap_length"],
            curve["best_skill"],
            color=color,
            alpha=alpha,
            marker="o",
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
        title="(a) Evaluate-once best envelope",
        xlabel="Gap length (days)",
        ylabel="Skill vs external training climatology",
        xticks=[30, 90, 180],
    )
    axes[0].grid(alpha=0.2)
    axes[0].legend(frameon=False, fontsize=7, ncol=2)
    axes[0].text(
        0.02,
        0.02,
        "Solid: observed; dashed: train-only prediction",
        transform=axes[0].transAxes,
        fontsize=7,
    )

    chatt = fingerprints.loc[fingerprints["network"].eq("Upper--Middle Chattahoochee")][
        ["station_id", "acf30", "training_observed_range_degC"]
    ]
    plotted = summary.merge(chatt, on="station_id", validate="one_to_one")
    for row in plotted.itertuples(index=False):
        memory = row.predicted_type == "memory_dominated"
        axes[1].scatter(
            row.acf30,
            row.observed_best_skill_180d,
            marker="s" if memory else "o",
            color="#e45756" if memory else "#4c78a8",
            s=70,
        )
        axes[1].annotate(
            row.station_id,
            (row.acf30, row.observed_best_skill_180d),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=7,
        )
    axes[1].set(
        title="(b) Thermal memory and long-gap recovery",
        xlabel="Training anomaly acf30",
        ylabel="Observed best skill at 180 days",
    )
    axes[1].grid(alpha=0.2)
    figure.suptitle(
        "External Chattahoochee confirmation: type transfers, magnitude does not",
        fontsize=13,
    )
    figure.savefig(FIGURES / "figure_05.png", dpi=300)
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

    dense = _load_dense_predictions()
    original_events = _original_skill_events(dense)
    original_curves = _curve_summary(
        original_events,
        skill_col="skill",
        climatology_mae_col="climatology_MAE",
        analysis="original_training_climatology",
    )
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

    network_events = pd.read_parquet(EVENTS)
    network_events = network_events.loc[
        network_events["experiment"].astype(str).eq("SCI_NET")
    ].copy()
    importance = node_importance(network_events, value_col="MAE")
    external_cells, external_summary = _external_confirmation_tables()

    outputs = {
        "annual_thermal_metrics.csv": annual,
        "period_thermal_metrics.csv": periods,
        "regulation_fingerprint.csv": fingerprints,
        "expanded_covariate_budget.csv": covariates,
        "stationarity_controlled_budgets.csv": budgets,
        "dense_skill_sensitivities.csv": curves,
        "best_envelope_sensitivities.csv": envelopes,
        "budget_evaluation_cells.csv": budget_cells,
        "budget_evaluation_summary.csv": budget_summary,
        "annual_demeaned_skill_events.csv": demeaned_events,
        "frontier_hypothesis_tests_corrected.csv": hypotheses,
        "node_importance_best_available.csv": importance,
        "external_confirmation_cells.csv": external_cells,
        "external_confirmation_summary.csv": external_summary,
    }
    for name, frame in outputs.items():
        frame.to_csv(OUTPUT / name, index=False)

    # Main tables are now mechanism/frontier tables, not validation rankings.
    fingerprints.to_csv(TABLES / "table_01.csv", index=False)
    annual.to_csv(TABLES / "table_02.csv", index=False)
    budget_summary.to_csv(TABLES / "table_03.csv", index=False)
    original_curves.to_csv(TABLES / "table_04.csv", index=False)
    importance.to_csv(TABLES / "table_05.csv", index=False)

    _figure_01(annual, fingerprints)
    _figure_02(budget_cells)
    _figure_03(curves)
    _figure_04(importance)
    _figure_05(external_cells, external_summary, fingerprints)

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
        "figures": [f"figures/main/figure_{index:02d}.png" for index in range(1, 6)],
        "main_tables": [f"paper/tables/table_{index:02d}.csv" for index in range(1, 6)],
        "interpretation_guard": (
            "state-matched and annual-demeaned analyses are reviewer-requested "
            "post-hoc diagnostics, not a replacement for the frozen prediction"
        ),
    }
    (OUTPUT / "revision_analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "complete", "artifacts": len(outputs)}, sort_keys=True))


if __name__ == "__main__":
    main()
