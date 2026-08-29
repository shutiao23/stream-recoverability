#!/usr/bin/env python3
"""Support-hierarchy ablation for the empirical-transfer predictor (agent b).

Tiers (most specific -> least):
  station_gap_season  : exact station x gap-length x season fitting-period curve
  station_gap         : station x gap-length curve (season collapsed)
  network_gap         : network x gap-length curve (station collapsed)
  network_mean_fallback: network-wide mean across all fitting losses
  unavailable         : no fitting-period support at all

First-panel / development sources come from the per-placement
empirical_transfer_source column already stored in
reviewer_completion/*_empirical_predictions.csv.  Second-panel sources are
NOT stored: the second-confirmation pipeline (131_run_second_confirmation.py)
dropped the source columns in _empirical_summary.  We re-run the exact
builder (fitting_period_empirical_losses + empirical_transfer_predictions)
on the frozen second-panel daily QC panels with the stored second-panel
placement roster, and verify the reconstructed predictions reproduce the
frozen second-confirmation scoring/empirical_predictions.csv.

Unit-level tier assignment: a station-gap unit contains ~20 placements whose
individual sources may differ; we assign the MOST SPECIFIC available source
across the unit's placements and report mixing diagnostics.

Every number written to REPORT.md comes from this script.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    XGBOOST_PARAMETERS,
    read_temperature_panel,
)
from stream_recoverability.experiments.recovery_roster import (
    empirical_transfer_predictions,
    fitting_period_empirical_losses,
)

OUT = ROOT / "results/revision_v12/t02_support_hierarchy/agent_b"
SECOND = ROOT / "results/development_v11/second_confirmation"
REVIEWER = ROOT / "results/development_v11/reviewer_completion"
TIER_ORDER = (
    "station_gap_season",
    "station_gap",
    "network_gap",
    "network_mean_fallback",
    "unavailable",
)
RENAMED = {
    "station_gap_season": "exact local support",
    "station_gap": "station-duration support",
    "network_gap": "network-duration support",
    "network_mean_fallback": "cross-duration fallback",
    "unavailable": "unavailable",
}
DIRECT_HORIZONS = (7, 30, 90, 180)


# ---------------------------------------------------------------------------
# second-panel source reconstruction (exact builder rerun)
# ---------------------------------------------------------------------------

def _panel_path(network_id: str) -> Path:
    second = SECOND / "daily_qc/networks" / network_id / "daily_wide_temperature.csv"
    if second.is_file():
        return second
    first = (
        ROOT
        / "results/development_v11/confirmation_daily_qc/networks"
        / network_id
        / "daily_wide_temperature.csv"
    )
    if first.is_file():
        return first
    raise FileNotFoundError(f"qualified network panel absent: {network_id}")


def _fit_losses_network(args: tuple) -> pd.DataFrame:
    network_id, panel_file, placements = args
    panel = read_temperature_panel(str(panel_file))
    return fitting_period_empirical_losses(
        network_id, panel, placements, xgboost_parameters=XGBOOST_PARAMETERS
    )


def regenerate_second_fit_losses(placements: pd.DataFrame) -> pd.DataFrame:
    cache = OUT / "second_fit_losses.csv"
    if cache.is_file():
        print(f"[phase1] reuse cached fit losses: {cache}", flush=True)
        return pd.read_csv(cache, dtype={"network_id": str, "station_id": str})
    networks = sorted(placements["network_id"].unique())
    tasks = [
        (net, str(_panel_path(net)), placements.loc[placements["network_id"].eq(net)])
        for net in networks
    ]
    started = time.time()
    with ProcessPoolExecutor(max_workers=8) as pool:
        parts = list(pool.map(_fit_losses_network, tasks, chunksize=1))
    losses = pd.concat(parts, ignore_index=True)
    losses.to_csv(cache, index=False)
    print(
        f"[phase1] regenerated fit losses: {len(losses)} rows, "
        f"{time.time() - started:.0f}s -> {cache}",
        flush=True,
    )
    return losses


def reconstruct_second_sources(
    placements: pd.DataFrame, losses: pd.DataFrame, frozen: pd.DataFrame
) -> pd.DataFrame:
    per_placement = empirical_transfer_predictions(losses, placements)
    units = unit_level(
        per_placement,
        prediction_column="empirical_transfer_prediction",
        observed_column="mae_deg_c",
    )
    frozen = frozen.copy()
    merged = units.merge(
        frozen,
        on=["network_id", "station_id", "gap_length"],
        suffixes=("_reconstructed", "_frozen"),
    )
    diff = (merged["prediction"] - merged["empirical_transfer_prediction"]).abs()
    verification = {
        "n_units_reconstructed": int(len(units)),
        "n_units_matched_to_frozen": int(len(merged)),
        "max_abs_prediction_diff": float(diff.max()),
        "frac_within_1e-6": float((diff <= 1e-6).mean()),
        "reconstruction_verified": bool(
            len(merged) == len(frozen) and (diff <= 1e-6).all()
        ),
    }
    print("[phase1] verification:", json.dumps(verification), flush=True)
    return per_placement, units, verification


# ---------------------------------------------------------------------------
# unit-level aggregation
# ---------------------------------------------------------------------------

def unit_level(
    per_placement: pd.DataFrame,
    prediction_column: str,
    observed_column: str,
) -> pd.DataFrame:
    """Aggregate per-placement rows to station-gap units.

    Tier rule: most-specific available source across the unit's placements.
    """
    units = (
        per_placement.groupby(["network_id", "station_id", "gap_length"], as_index=False)
        .agg(
            prediction=(prediction_column, "mean"),
            observed=(observed_column, "mean"),
            n_placements=("placement", "size"),
            sources=("empirical_transfer_source", lambda s: "|".join(sorted(set(s)))),
        )
    )
    units["tier"] = units["sources"].map(_most_specific_source)
    units["all_placements_same_tier"] = units["sources"].map(
        lambda s: "|" not in s
    )
    return units


def _most_specific_source(sources: str) -> str:
    for tier in TIER_ORDER:
        if tier in sources.split("|"):
            return tier
    return "unavailable"


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _network_weighted_calibration(frame: pd.DataFrame) -> tuple[float, float]:
    counts = frame.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(frame)), frame["prediction"].to_numpy(float)])
    intercept, slope = np.linalg.lstsq(
        design * weight[:, None], frame["observed"].to_numpy(float) * weight, rcond=None
    )[0]
    return float(intercept), float(slope)


def _r2(observed: np.ndarray, predicted: np.ndarray) -> float:
    return float(1.0 - np.sum(np.square(observed - predicted)) / np.sum(np.square(observed - observed.mean())))


def tier_metrics(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    rows = []
    for tier in TIER_ORDER:
        subset = frame.loc[frame["tier"].eq(tier)]
        rows.append(_metric_row(subset, tier))
    rows.append(_metric_row(frame, "all"))
    return pd.DataFrame(rows)


def _metric_row(frame: pd.DataFrame, tier: str) -> dict:
    n = len(frame)
    base = {
        "panel": None,
        "tier": tier,
        "n_station_gaps": n,
        "n_networks": int(frame["network_id"].nunique()) if n else 0,
    }
    if n < 2:
        return base
    observed = frame["observed"].to_numpy(float)
    predicted = frame["prediction"].to_numpy(float)
    base["pooled_spearman"] = float(spearmanr(predicted, observed).statistic)
    network = frame.groupby("network_id")[["prediction", "observed"]].mean()
    base["network_spearman"] = float(
        spearmanr(network["prediction"], network["observed"]).statistic
    )
    base["network_r2"] = _r2(
        network["observed"].to_numpy(float), network["prediction"].to_numpy(float)
    )
    per_network = []
    for _, values in frame.groupby("network_id"):
        if len(values) >= 3:
            rho = spearmanr(
                values["prediction"].to_numpy(float),
                values["observed"].to_numpy(float),
            ).statistic
            if np.isfinite(rho):
                per_network.append(rho)
    base["within_network_spearman_mean"] = (
        float(np.mean(per_network)) if per_network else np.nan
    )
    base["within_network_spearman_n_networks_ge3units"] = len(per_network)
    intercept, slope = _network_weighted_calibration(frame)
    base["calibration_intercept"] = intercept
    base["calibration_slope"] = slope
    base["pooled_r2"] = _r2(observed, predicted)
    return base


# ---------------------------------------------------------------------------
# support quality
# ---------------------------------------------------------------------------

def support_quality(
    units: pd.DataFrame,
    fit_losses: pd.DataFrame,
    placements: pd.DataFrame,
) -> pd.DataFrame:
    """Effective support (fit placements in the curve cell used) and distance
    to the nearest supported exact (station, gap, season) cell.

    distance = min over supported cells of |gap - gap'| + 10*(season mismatch)
               + 100*(station mismatch).
    Placements are scored individually; the unit value is the mean.
    """
    fit = fit_losses.copy()
    fit["network_id"] = fit["network_id"].astype(str)
    fit["station_id"] = fit["station_id"].astype(str)
    cell_counts = (
        fit.groupby(["network_id", "station_id", "gap_length", "season"])
        .size()
        .reset_index(name="n_fit_placements")
    )
    station_gap_counts = (
        fit.groupby(["network_id", "station_id", "gap_length"])
        .size()
        .reset_index(name="n_fit_placements")
    )
    network_gap_counts = (
        fit.groupby(["network_id", "gap_length"])
        .size()
        .reset_index(name="n_fit_placements")
    )
    network_counts = (
        fit.groupby("network_id")
        .size()
        .reset_index(name="n_fit_placements")
    )
    cell_lookup = {
        (str(row.network_id), str(row.station_id), int(row.gap_length), str(row.season)): int(
            row.n_fit_placements
        )
        for row in cell_counts.itertuples(index=False)
    }
    station_gap_lookup = {
        (str(row.network_id), str(row.station_id), int(row.gap_length)): int(
            row.n_fit_placements
        )
        for row in station_gap_counts.itertuples(index=False)
    }
    network_gap_lookup = {
        (str(row.network_id), int(row.gap_length)): int(row.n_fit_placements)
        for row in network_gap_counts.itertuples(index=False)
    }
    network_lookup = {
        str(row.network_id): int(row.n_fit_placements)
        for row in network_counts.itertuples(index=False)
    }
    supported_by_network: dict[str, np.ndarray] = {}
    supported_station_by_network: dict[str, np.ndarray] = {}
    for network, values in cell_counts.groupby("network_id"):
        supported_by_network[network] = np.column_stack(
            [
                values["gap_length"].to_numpy(int),
                values["season"].map(_SEASON_INDEX).to_numpy(int),
            ]
        )
        supported_station_by_network[network] = values["station_id"].to_numpy(
            dtype=object
        )
    rows = []
    for placement in placements.itertuples(index=False):
        network = str(placement.network_id)
        station = str(placement.station_id)
        gap = int(placement.gap_length)
        season = (
            str(placement.season)
            if hasattr(placement, "season") and pd.notna(placement.season)
            else _season_of(placement.gap_start)
        )
        curve_n = cell_lookup.get((network, station, gap, season), 0)
        if curve_n:
            effective = curve_n
        else:
            effective = (
                station_gap_lookup.get((network, station, gap), 0)
                or network_gap_lookup.get((network, gap), 0)
                or network_lookup.get(network, 0)
            )
        supported = supported_by_network.get(network)
        if supported is not None and len(supported):
            gap_d = np.abs(gap - supported[:, 0])
            season_d = np.where(supported[:, 1] == _SEASON_INDEX[season], 0.0, 10.0)
            station_d = np.where(
                supported_station_by_network[network] == station, 0.0, 100.0
            )
            distance = float(np.min(gap_d + season_d + station_d))
        else:
            distance = np.nan
        rows.append(
            {
                "network_id": network,
                "station_id": station,
                "gap_length": gap,
                "placement": int(placement.placement),
                "effective_support": effective,
                "distance_to_nearest_supported_cell": distance,
            }
        )
    quality = pd.DataFrame(rows)
    unit_quality = (
        quality.groupby(["network_id", "station_id", "gap_length"], as_index=False)
        .agg(
            effective_support=("effective_support", "mean"),
            distance_to_nearest_supported_cell=(
                "distance_to_nearest_supported_cell", "mean"
            ),
        )
    )
    return units.merge(unit_quality, on=["network_id", "station_id", "gap_length"])


def _season_of(gap_start: object) -> str:
    month = pd.Timestamp(gap_start).month
    if month in (12, 1, 2):
        return "DJF"
    if month in (3, 4, 5):
        return "MAM"
    if month in (6, 7, 8):
        return "JJA"
    return "SON"


_SEASON_INDEX = {"DJF": 0, "MAM": 1, "JJA": 2, "SON": 3}


def tercile_metrics(frame: pd.DataFrame, by_column: str, label: str) -> pd.DataFrame:
    """Rank-based thirds, ties broken by row order (documented); each group
    is contiguous in the sorted value.  Also adds semantic support-quality
    groups: for distance, d==0 exact local, 0<d<100 station-level proximity,
    d>=100 network-level only; for effective support, <20 partial cell,
    ==20 full cell, >20 pooled cell.
    """
    usable = frame.loc[frame[by_column].notna()].copy().sort_values(by_column)
    usable = usable.reset_index(drop=True)
    n = len(usable)
    thirds = np.zeros(n, dtype=int)
    first_edge = int(np.ceil(n / 3.0))
    second_edge = int(np.ceil(2 * n / 3.0))
    thirds[first_edge:] = 1
    thirds[second_edge:] = 2
    usable["quality_group"] = pd.Series(thirds).map(
        {0: "t1", 1: "t2", 2: "t3"}
    )
    rows = []
    for group, values in usable.groupby("quality_group", observed=True):
        row = _metric_row(values, str(group))
        row["panel"] = label
        row[by_column + "_min"] = float(values[by_column].min())
        row[by_column + "_max"] = float(values[by_column].max())
        rows.append(row)
    if by_column == "distance_to_nearest_supported_cell":
        semantic = usable.assign(
            quality_group=np.select(
                [
                    usable[by_column] == 0.0,
                    usable[by_column] < 100.0,
                ],
                ["exact_local", "station_level"],
                default="network_level",
            )
        )
    else:
        semantic = usable.assign(
            quality_group=np.select(
                [
                    usable[by_column] < 20.0,
                    usable[by_column] == 20.0,
                ],
                ["partial_cell", "full_cell"],
                default="pooled_cell",
            )
        )
    for group, values in semantic.groupby("quality_group", observed=True):
        row = _metric_row(values, f"semantic_{group}")
        row["panel"] = label
        row[by_column + "_min"] = float(values[by_column].min())
        row[by_column + "_max"] = float(values[by_column].max())
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {}

    # ---- second panel ----------------------------------------------------
    second_placements = pd.read_csv(
        SECOND / "scoring/placement_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    second_frozen = pd.read_csv(
        SECOND / "scoring/empirical_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    second_fit_losses = regenerate_second_fit_losses(second_placements)
    second_placement_rows, second_units, verification = reconstruct_second_sources(
        second_placements, second_fit_losses, second_frozen
    )
    second_placement_rows.to_csv(OUT / "second_placement_sources.csv", index=False)
    second_units = second_units.rename(
        columns={"prediction": "prediction", "observed": "observed"}
    )
    second_units["panel"] = "second"
    second_units = second_units.merge(
        second_frozen[["network_id", "station_id", "gap_length", "observed_recovery_loss"]],
        on=["network_id", "station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    second_units["observed"] = second_units["observed"].fillna(
        second_units["observed_recovery_loss"]
    )
    second_units["panel"] = "second"
    second_units = support_quality(second_units, second_fit_losses, second_placement_rows)
    second_units.to_csv(OUT / "second_unit_tiers.csv", index=False)
    results["second_reconstruction_verification"] = verification

    # ---- first panel (confirmation) --------------------------------------
    first_placements = pd.read_csv(
        REVIEWER / "confirmation_empirical_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    first_units = unit_level(
        first_placements,
        prediction_column="empirical_transfer_prediction",
        observed_column="mae_deg_c",
    )
    first_units["panel"] = "first"
    first_fit_losses = pd.read_csv(
        REVIEWER / "confirmation_empirical_fit_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    first_units = support_quality(first_units, first_fit_losses, first_placements)
    first_units.to_csv(OUT / "first_unit_tiers.csv", index=False)

    # ---- development ------------------------------------------------------
    dev_placements = pd.read_csv(
        REVIEWER / "development_empirical_predictions.csv",
        dtype={"network_id": str, "station_id": str},
    )
    dev_units = unit_level(
        dev_placements,
        prediction_column="empirical_transfer_prediction",
        observed_column="mae_deg_c",
    )
    dev_units["panel"] = "development"
    dev_units = dev_units.loc[dev_units["prediction"].notna()]
    dev_fit_losses = pd.read_csv(
        REVIEWER / "development_empirical_fit_losses.csv",
        dtype={"network_id": str, "station_id": str},
    )
    dev_units = support_quality(dev_units, dev_fit_losses, dev_placements)
    dev_units.to_csv(OUT / "development_unit_tiers.csv", index=False)

    # ---- per-tier metrics --------------------------------------------------
    for label, frame in (
        ("second", second_units),
        ("first", first_units),
        ("development", dev_units),
    ):
        metrics = tier_metrics(frame, label)
        metrics["panel"] = label
        metrics.to_csv(OUT / f"tier_metrics_{label}.csv", index=False)
        results[f"tier_metrics_{label}"] = metrics.to_dict(orient="records")
        composition = (
            frame.groupby(["tier", "gap_length"])
            .size()
            .reset_index(name="n_units")
        )
        composition["panel"] = label
        composition.to_csv(OUT / f"tier_gap_composition_{label}.csv", index=False)
        results[f"tier_gap_composition_{label}"] = composition.to_dict(
            orient="records"
        )

    # ---- key decomposition: second panel direct horizons ------------------
    direct = second_units.loc[second_units["gap_length"].isin(DIRECT_HORIZONS)]
    direct_net = direct.groupby("network_id")[["prediction", "observed"]].mean()
    exact = direct.loc[direct["tier"].eq("station_gap_season")]
    station_fallback = direct.loc[direct["tier"].eq("station_gap")]
    network_fallback = direct.loc[direct["tier"].eq("network_mean_fallback")]
    fallback_tiers = pd.concat([station_fallback, network_fallback], ignore_index=True)


    def _network_spearman(frame: pd.DataFrame) -> float:
        means = frame.groupby("network_id")[["prediction", "observed"]].mean()
        return float(spearmanr(means["prediction"], means["observed"]).statistic)


    decomposition = {
        "n_direct_horizon_units": int(len(direct)),
        "n_direct_horizon_networks": int(direct["network_id"].nunique()),
        "direct_network_spearman": float(
            spearmanr(direct_net["prediction"], direct_net["observed"]).statistic
        ),
        "direct_pooled_spearman": float(
            spearmanr(direct["prediction"], direct["observed"]).statistic
        ),
        "exact_tier_units": int(len(exact)),
        "exact_tier_networks": int(exact["network_id"].nunique()),
        "exact_tier_network_spearman": _network_spearman(exact),
        "exact_tier_pooled_spearman": float(
            spearmanr(exact["prediction"], exact["observed"]).statistic
        ),
        "station_gap_fallback_tier_units": int(len(station_fallback)),
        "station_gap_fallback_tier_network_spearman": (
            _network_spearman(station_fallback)
            if len(station_fallback) >= 3
            else np.nan
        ),
        "network_mean_fallback_direct_units": int(len(network_fallback)),
        "network_mean_fallback_direct_network_spearman": (
            _network_spearman(network_fallback)
            if len(network_fallback) >= 3
            else np.nan
        ),
        "all_fallback_tier_units": int(len(fallback_tiers)),
        "all_fallback_tier_network_spearman": (
            _network_spearman(fallback_tiers)
            if len(fallback_tiers) >= 3
            else np.nan
        ),
        "all_fallback_tier_pooled_spearman": float(
            spearmanr(fallback_tiers["prediction"], fallback_tiers["observed"]).statistic
        ),
        "exact_tier_share_of_direct_units": float(len(exact) / len(direct)),
    }
    results["key_decomposition"] = decomposition
    (OUT / "key_decomposition.json").write_text(
        json.dumps(decomposition, indent=2) + "\n", encoding="utf-8"
    )

    # ---- cross-checks -----------------------------------------------------
    all_second = second_units
    second_all_net = all_second.groupby("network_id")[["prediction", "observed"]].mean()
    first_fallback_all = first_units["tier"].eq("network_mean_fallback").sum()
    first_fallback_any = (
        first_units["sources"].str.split("|").map(lambda s: "network_mean_fallback" in s).sum()
    )
    crosschecks = {
        "second_panel_n_units": int(len(all_second)),
        "second_panel_network_spearman_all": float(
            spearmanr(second_all_net["prediction"], second_all_net["observed"]).statistic
        ),
        "second_panel_n_direct_units": int(len(direct)),
        "second_panel_n_fallback_units": int(len(all_second) - len(direct)),
        "first_panel_n_units": int(len(first_units)),
        "first_panel_n_fallback_units_all_placements_fallback": int(first_fallback_all),
        "first_panel_n_fallback_units_any_placement_fallback": int(first_fallback_any),
        "development_n_units_with_prediction": int(len(dev_units)),
    }
    results["crosschecks"] = crosschecks
    (OUT / "crosschecks.json").write_text(
        json.dumps(crosschecks, indent=2) + "\n", encoding="utf-8"
    )

    # ---- support-quality terciles ------------------------------------------
    second_distance = tercile_metrics(
        second_units, "distance_to_nearest_supported_cell", "second_all_units"
    )
    second_support = tercile_metrics(direct, "effective_support", "second_direct_horizons")
    first_distance = tercile_metrics(
        first_units, "distance_to_nearest_supported_cell", "first_all_units"
    )
    first_support = tercile_metrics(
        first_units.loc[first_units["gap_length"].isin(DIRECT_HORIZONS)],
        "effective_support",
        "first_direct_horizons",
    )
    terciles = pd.concat(
        [second_distance, second_support, first_distance, first_support],
        ignore_index=True,
    )
    terciles.to_csv(OUT / "support_quality_terciles.csv", index=False)
    results["support_quality_terciles"] = terciles.to_dict(orient="records")

    # ---- renamed hierarchy (manuscript-ready) -------------------------------
    hierarchy = []
    for panel in ("second", "first", "development"):
        frame = {
            "second": second_units,
            "first": first_units,
            "development": dev_units,
        }[panel]
        for tier in TIER_ORDER:
            subset = frame.loc[frame["tier"].eq(tier)]
            row = _metric_row(subset, tier)
            row["panel"] = panel
            row["tier_code"] = tier
            row["tier_name"] = RENAMED[tier]
            hierarchy.append(row)
    hierarchy_df = pd.DataFrame(hierarchy)
    hierarchy_df.to_csv(OUT / "renamed_hierarchy.csv", index=False)
    results["renamed_hierarchy"] = hierarchy_df.to_dict(orient="records")

    # ---- tier mixing diagnostics -------------------------------------------
    mixing = {
        "second_units_with_mixed_placement_sources": int(
            (~second_units["all_placements_same_tier"]).sum()
        ),
        "first_units_with_mixed_placement_sources": int(
            (~first_units["all_placements_same_tier"]).sum()
        ),
        "development_units_with_mixed_placement_sources": int(
            (~dev_units["all_placements_same_tier"]).sum()
        ),
    }
    results["unit_tier_assignment_mixing"] = mixing
    (OUT / "mixing_diagnostics.json").write_text(
        json.dumps(mixing, indent=2) + "\n", encoding="utf-8"
    )

    (OUT / "analysis_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
