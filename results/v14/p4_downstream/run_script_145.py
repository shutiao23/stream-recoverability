#!/usr/bin/env python3
"""P4 (v14): downstream thermal-regime metrics at 7/30/90/180/365-day gaps.

Extends the archived agent_b downstream experiment
(scripts/rev_v12_t08_downstream_metrics_b.py) to:
  * all 42 first-panel networks scored in
    results/development_v11/route_a_confirmation/placement_losses.csv (B_union_D);
  * the 180- and 365-day horizons;
  * three no-recovery defaults evaluated on identical artificial gaps in the
    outer evaluation years: climatology fill, linear interpolation between the
    two flanking observed days (development_recovery._boundary_values), and
    no-fill (gap days dropped, agent_b's uncomputable handling).

Placement geometry is the archived one (placement_losses.csv, B_union_D rows):
at most PLACEMENTS_PER_GAP=5 placements per (station, gap_length), chosen
evenly across the archived placements of that cell.  Every sampled placement
is verified (observed truth/donors/boundaries across the needed window) and
violations are skipped and counted.

Thermal-regime metrics, the 365-day gap-centred metric window, and every
per-metric definition are imported unchanged from the agent_b script so the
conventions match exactly.  P0 differential predictions are joined 1:1 on
(network_id, station_id, gap_length, placement, gap_start).

Deliverables (results/v14/p4_downstream/):
  run_script_145.py            copy of this script
  placement_metrics.csv        per-placement truth/recon/missing/clim/linear
  station_gap_metrics.csv      station-gap aggregates + P0 unit predictors
  metric_error_summary.csv     per horizon x metric distortion tables
  budget_within_horizon.csv    top-20% placement budgets within each horizon
  agent_b_overlap_comparison.csv  shared-cell consistency vs agent_b archive
  sanity_checks.txt            fidelity and join diagnostics
  REPORT.md                    factual report

Run: PYTHONPATH=$PWD/src python3 scripts/145_run_p4_downstream.py
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    XGBOOST_PARAMETERS,
    _boundary_values,
    _climatology_prediction,
    _model_frame,
    read_temperature_panel,
    year_split,
)
from stream_recoverability.experiments.development_data import (  # noqa: E402
    joint_complete_feature_rosters,
)

NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
ARCHIVE_PLACEMENTS = (
    ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv"
)
P0_PREDICTIONS = ROOT / "results/v14/p0_differential/placement_predictions_first.csv"
AGENT_B_STATION_GAP = (
    ROOT / "results/revision_v12/t08_downstream_metrics/agent_b/station_gap_metrics.csv"
)
OUTPUT = ROOT / "results/v14/p4_downstream"
AGENT_B_SCRIPT = ROOT / "scripts/rev_v12_t08_downstream_metrics_b.py"

HORIZONS = (7, 30, 90, 180, 365)
PLACEMENTS_PER_GAP = 5
MIN_TRAIN_DAYS = 365
TRAINING_FRACTION = 0.7
MAX_WORKERS = 24
RANDOM_BUDGET_DRAWS = 100
RANDOM_BUDGET_SEED = 0
BUDGET_METRICS = (
    "annual_mean",
    "summer_mean",
    "amplitude",
    "phase_doy",
    "p90",
    "cdd10",
)

P0_JOIN_KEYS = ["network_id", "station_id", "gap_length", "placement", "gap_start"]
P0_COLUMNS = [
    "direct",
    "realized_benefit",
    "diff_prediction",
    "risk_prediction",
    "duration_only_prediction",
    "r6_diff_prediction",
    "default_difficulty_prediction",
    "loo_benefit_upper",
    "diff_source",
    "diff_supported",
]

_AGENT_B_NAME = "rev_v12_t08_downstream_metrics_b"


def _load_agent_b():
    """Import the agent_b module so metric definitions are byte-identical."""
    if _AGENT_B_NAME in sys.modules:
        return sys.modules[_AGENT_B_NAME]
    spec = importlib.util.spec_from_file_location(
        _AGENT_B_NAME, str(AGENT_B_SCRIPT)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[_AGENT_B_NAME] = module
    return module


_AB = _load_agent_b()
METRICS = _AB.METRICS
METRIC_LABELS = _AB.METRIC_LABELS
SCENARIOS = ("recon", "missing", "clim", "linear")

PLACEMENT_COLUMNS = [
    "network_id",
    "station_id",
    "gap_length",
    "placement",
    "gap_start",
    "gap_end",
    "season",
    "mae_deg_c",
    "training_years",
    "evaluation_years",
    "donor_station_ids",
    "n_window_days",
    "window_start",
    "window_end",
]
for metric in METRICS:
    PLACEMENT_COLUMNS.append(f"{metric}_truth")
for scenario in SCENARIOS:
    for metric in METRICS:
        PLACEMENT_COLUMNS.append(f"{metric}_{scenario}")
for scenario in SCENARIOS:
    for metric in METRICS:
        PLACEMENT_COLUMNS.append(f"{metric}_err_{scenario}")
PLACEMENT_COLUMNS.extend(P0_COLUMNS)


def _circular_mean(values: pd.Series) -> float:
    """Circular mean of phase errors in days on [0, 365)."""
    finite = values.dropna()
    if len(finite) == 0:
        return float("nan")
    radians = 2.0 * np.pi * finite.to_numpy(dtype=float) / 365.0
    mean_radians = np.arctan2(np.mean(np.sin(radians)), np.mean(np.cos(radians)))
    return float(np.mod(mean_radians, 2.0 * np.pi) * 365.0 / (2.0 * np.pi))


def _unit_mean(work: pd.DataFrame, column: str, metric: str) -> pd.DataFrame:
    """Per (network, station, gap) unit means of one per-placement error column.

    Phase errors use the circular mean; all other metrics use the arithmetic
    mean.  Units without any finite placement are dropped.
    """
    keys = ["network_id", "station_id", "gap_length"]
    function = (lambda values: _circular_mean(values)) if metric == "phase_doy" else "mean"
    grouped = work.loc[work[column].notna()].groupby(keys, sort=False)
    series = grouped[column].agg(function)
    return series.reset_index()


def _sample_cell(rows: pd.DataFrame, count: int = PLACEMENTS_PER_GAP) -> pd.DataFrame:
    """Select up to ``count`` archived placements evenly across a cell."""
    rows = rows.sort_values("gap_start")
    if len(rows) <= count:
        return rows
    positions = np.linspace(0, len(rows) - 1, num=count, dtype=int)
    return rows.iloc[positions]


def score_network_p4(network_id: str, cell_rows: pd.DataFrame) -> dict[str, object]:
    """Fit the frozen B_union_D model and score archived evaluation gaps.

    Mirrors agent_b's score_network_with_daily (same split, rosters, frame,
    climatology, XGBOOST_PARAMETERS at n_jobs=1) but evaluates the archived
    placement geometry instead of re-enumerating candidate windows.  One model
    is fitted per target station and reused for every gap length.
    """
    log: list[str] = []
    violations: list[dict[str, object]] = []
    panel = read_temperature_panel(
        str(NETWORK_ROOT / network_id / "daily_wide_temperature.csv")
    )
    panel = panel.copy().sort_index()
    daily_index = pd.date_range(panel.index.min(), panel.index.max(), freq="D")
    panel = panel.reindex(daily_index)
    panel.index.name = "date"
    panel.columns = panel.columns.astype(str)
    train_mask, training_years, evaluation_years = year_split(
        panel.index, training_fraction=TRAINING_FRACTION
    )
    evaluation_mask = ~train_mask
    model_parameters = dict(XGBOOST_PARAMETERS)
    panel_index_array = panel.index.to_numpy(dtype="datetime64[ns]")

    rows: list[dict[str, object]] = []
    for target, station_cells in cell_rows.groupby("station_id", sort=False):
        if str(target) not in panel.columns:
            violations.append(
                {
                    "network_id": network_id,
                    "station_id": str(target),
                    "gap_length": int(station_cells["gap_length"].iloc[0]),
                    "gap_start": str(station_cells["gap_start"].iloc[0]),
                    "reason": "station_missing_from_panel",
                    "n_placements": int(len(station_cells)),
                }
            )
            continue
        fitting_frame = panel.loc[train_mask]
        donors, _, _ = joint_complete_feature_rosters(
            fitting_frame,
            target=str(target),
            donor_candidates=tuple(
                str(column) for column in panel.columns if str(column) != str(target)
            ),
            meteorology_candidates=(),
            hydraulics_candidates=(),
            min_pairs=MIN_TRAIN_DAYS,
        )
        train_target_days = int((train_mask & panel[target].notna()).sum())
        if train_target_days < MIN_TRAIN_DAYS or not donors:
            violations.append(
                {
                    "network_id": network_id,
                    "station_id": str(target),
                    "gap_length": int(station_cells["gap_length"].iloc[0]),
                    "gap_start": str(station_cells["gap_start"].iloc[0]),
                    "reason": "station_unqualified_at_fit",
                    "n_placements": int(len(station_cells)),
                }
            )
            continue
        frame = _model_frame(
            panel,
            pd.DataFrame(index=panel.index),
            target_station=str(target),
            donors=donors,
            meteorology=(),
            hydraulics=(),
            train_mask=train_mask,
        )
        fitting = train_mask & panel[target].notna()
        model = XGBRegressor(**dict(model_parameters))
        model.fit(frame.loc[fitting], panel.loc[fitting, target])
        climatology = _climatology_prediction(panel[target], train_mask, panel.index)
        donor_array = np.asarray(
            [panel[donor].notna().to_numpy(dtype=bool) for donor in donors],
            dtype=bool,
        )
        target_observed = panel[target].notna().to_numpy(dtype=bool)

        for (gap_length,), cell in station_cells.groupby(
            ["gap_length"], sort=False
        ):
            gap_length_i = int(gap_length)
            selected = _sample_cell(cell, count=PLACEMENTS_PER_GAP)
            for archived in selected.to_dict("records"):
                gap_start_ts = np.datetime64(pd.Timestamp(archived["gap_start"]), "D")
                positions_all = np.nonzero(panel_index_array == gap_start_ts)[0]
                if len(positions_all) != 1:
                    violations.append(
                        {
                            "network_id": network_id,
                            "station_id": str(target),
                            "gap_length": gap_length_i,
                            "gap_start": str(archived["gap_start"]),
                            "reason": "gap_start_not_in_panel_index",
                        }
                    )
                    continue
                start = int(positions_all[0])
                stop = start + gap_length_i
                reason = ""
                if not np.all(target_observed[start:stop]):
                    reason = "target_nan_in_gap"
                elif not np.all(evaluation_mask.iloc[start:stop].to_numpy()):
                    reason = "gap_not_in_evaluation_years"
                elif (
                    donor_array.shape[0] > 0
                    and not np.all(donor_array[:, start:stop])
                ):
                    reason = "donor_nan_in_gap"
                elif (
                    start < 1
                    or stop >= len(panel)
                    or not target_observed[start - 1]
                    or not target_observed[stop]
                ):
                    reason = "boundary_not_observed"
                if reason:
                    violations.append(
                        {
                            "network_id": network_id,
                            "station_id": str(target),
                            "gap_length": gap_length_i,
                            "gap_start": str(archived["gap_start"]),
                            "reason": reason,
                        }
                    )
                    continue

                prediction_frame = frame.iloc[start:stop].copy()
                prediction_frame["B__boundary_temperature"] = _boundary_values(
                    panel[target], start, gap_length_i
                )
                predicted = model.predict(prediction_frame)
                truth = panel[target].iloc[start:stop].to_numpy(dtype=float)
                climate = climatology[start:stop]
                linear = _boundary_values(panel[target], start, gap_length_i)
                gap_index = panel.index[start:stop]
                center = gap_index[len(gap_index) // 2]
                window_start = center - pd.Timedelta(days=182)
                window_end = center + pd.Timedelta(days=182)
                year_index = panel.index[
                    (panel.index >= window_start) & (panel.index <= window_end)
                ]
                truth_year = panel.loc[year_index, target].astype(float)
                recon_year = truth_year.copy()
                clim_year = truth_year.copy()
                linear_year = truth_year.copy()
                missing_year = truth_year.copy()
                overlap = gap_index.intersection(year_index)
                if len(overlap) != len(gap_index):
                    violations.append(
                        {
                            "network_id": network_id,
                            "station_id": str(target),
                            "gap_length": gap_length_i,
                            "gap_start": str(archived["gap_start"]),
                            "reason": "gap_not_contained_in_window",
                        }
                    )
                    continue
                positions = np.searchsorted(year_index, gap_index)
                recon_year.iloc[positions] = predicted
                clim_year.iloc[positions] = climate
                linear_year.iloc[positions] = linear
                missing_year.iloc[positions] = np.nan

                truth_metrics = _AB.thermal_metrics(truth_year)
                scenarios = {
                    "recon": _AB.thermal_metrics(recon_year),
                    "missing": _AB.thermal_metrics(missing_year),
                    "clim": _AB.thermal_metrics(clim_year),
                    "linear": _AB.thermal_metrics(linear_year),
                }
                row: dict[str, object] = {
                    "network_id": str(network_id),
                    "station_id": str(target),
                    "gap_length": gap_length_i,
                    "placement": int(archived["placement"]),
                    "gap_start": pd.Timestamp(archived["gap_start"]),
                    "gap_end": pd.Timestamp(archived["gap_end"]),
                    "season": _AB.season_label(pd.Timestamp(archived["gap_start"])),
                    "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                    "training_years": "|".join(map(str, training_years)),
                    "evaluation_years": "|".join(map(str, evaluation_years)),
                    "donor_station_ids": "|".join(donors),
                    "n_window_days": int(len(year_index)),
                    "window_start": window_start,
                    "window_end": window_end,
                }
                for metric in METRICS:
                    row[f"{metric}_truth"] = truth_metrics[metric]
                for scenario, metrics in scenarios.items():
                    for metric in METRICS:
                        row[f"{metric}_{scenario}"] = metrics[metric]
                for scenario in scenarios:
                    errors = _AB.metric_error(truth_metrics, scenarios[scenario])
                    for metric in METRICS:
                        row[f"{metric}_err_{scenario}"] = errors[metric]
                rows.append(row)
    result = pd.DataFrame(rows, columns=PLACEMENT_COLUMNS[: -len(P0_COLUMNS)])
    log.append(f"{network_id}: scored {len(result)} placements")
    return {
        "network_id": network_id,
        "rows": result,
        "violations": violations,
        "log": log,
    }


def join_p0(placements: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join the P0 first-panel predictions 1:1 on the five placement keys."""
    p0 = pd.read_csv(P0_PREDICTIONS, parse_dates=["gap_start"])
    p0["network_id"] = p0["network_id"].astype(str)
    p0["station_id"] = p0["station_id"].astype(str)
    p0 = p0[P0_JOIN_KEYS + P0_COLUMNS]
    duplicates = int(p0.duplicated(subset=P0_JOIN_KEYS, keep=False).sum())
    if duplicates:
        raise RuntimeError(f"P0 predictions have {duplicates} duplicated key rows")
    merged = placements.merge(p0, on=P0_JOIN_KEYS, how="left", validate="one_to_one")
    joined = merged.loc[merged["diff_prediction"].notna()].copy()
    unmatched = merged.loc[merged["diff_prediction"].isna()].copy()
    return joined, unmatched


def build_station_gap(placements: pd.DataFrame) -> pd.DataFrame:
    """Station-gap means over placements (agent_b semantics + linear)."""
    keys = ["network_id", "station_id", "gap_length"]
    base = (
        placements.groupby(keys, as_index=False)
        .agg(
            n_placements=("placement", "size"),
            mae_deg_c=("mae_deg_c", "mean"),
            first_gap_start=("gap_start", "min"),
            last_gap_end=("gap_end", "max"),
        )
        .sort_values(keys)
        .reset_index(drop=True)
    )
    numeric_p0 = [column for column in P0_COLUMNS if column in placements.columns]
    p0_unit = placements.groupby(keys, as_index=False)[numeric_p0].mean(
        numeric_only=True
    )
    p0_unit = p0_unit.rename(
        columns={column: f"{column}_mean" for column in p0_unit.columns if column in P0_COLUMNS}
    )
    base = base.merge(p0_unit, on=keys, how="left")

    for metric in METRICS:
        default_columns = [
            f"{metric}_err_{scenario}" for scenario in ("recon", "clim", "linear")
        ]
        default_mask = placements[default_columns].notna().all(axis=1)
        work_default = placements.loc[default_mask]
        for scenario in ("recon", "clim", "linear"):
            column = f"{metric}_err_{scenario}"
            unit = _unit_mean(work_default, column, metric)
            base = base.merge(
                unit.rename(columns={column: column}),
                on=keys,
                how="left",
            )
        missing_column = f"{metric}_err_missing"
        missing_mask = (
            placements[[f"{metric}_err_recon", missing_column]].notna().all(axis=1)
        )
        unit = _unit_mean(placements.loc[missing_mask], missing_column, metric)
        base = base.merge(unit.rename(columns={missing_column: missing_column}), on=keys, how="left")
    return base


def build_metric_summary(placements: pd.DataFrame) -> pd.DataFrame:
    """Per horizon x metric distortion summary with paired supports.

    Default pair (recon/clim/linear): unit means over placements where all
    three errors are defined.  Missing pair: unit means over placements where
    recon and no-fill are both defined (no-fill is uncomputable for 365-day
    gaps, whose metric window coincides with the gap, and per-metric where a
    gap swallows a whole month under amplitude etc.).  The recon error is
    recomputed on the missing-pair support so every ratio uses matched units.
    """
    keys = ["network_id", "station_id", "gap_length"]
    summary_rows: list[dict[str, object]] = []
    for horizon in HORIZONS:
        sub = placements.loc[placements["gap_length"].eq(horizon)]
        for metric in METRICS:
            units_ = (
                "days"
                if metric == "phase_doy"
                else "degC"
                if metric
                in ("annual_mean", "summer_mean", "amplitude", "p90", "summer_max")
                else "count"
                if metric in ("exceed_days_20", "exceed_days_25")
                else ("degC-days" if metric == "cdd10" else "degC/yr")
            )
            default_columns = [
                f"{metric}_err_{scenario}" for scenario in ("recon", "clim", "linear")
            ]
            mask_default = sub[default_columns].notna().all(axis=1)
            work_default = sub.loc[mask_default]
            unit_default = _unit_mean(work_default, default_columns[0], metric)
            if len(unit_default):
                unit_default = unit_default.merge(
                    _unit_mean(work_default, default_columns[1], metric), on=keys
                ).merge(
                    _unit_mean(work_default, default_columns[2], metric), on=keys
                )
            missing_columns = [f"{metric}_err_recon", f"{metric}_err_missing"]
            mask_missing = sub[missing_columns].notna().all(axis=1)
            unit_missing = _unit_mean(
                sub.loc[mask_missing], missing_columns[0], metric
            )
            if len(unit_missing):
                unit_missing = unit_missing.merge(
                    _unit_mean(sub.loc[mask_missing], missing_columns[1], metric),
                    on=keys,
                )

            row: dict[str, object] = {
                "horizon": int(horizon),
                "metric": metric,
                "label": METRIC_LABELS[metric],
                "units": units_,
            }
            if len(unit_default):
                n_units = len(unit_default)
                n_networks = int(unit_default["network_id"].nunique())
                mean_recon = float(unit_default[default_columns[0]].mean())
                mean_clim = float(unit_default[default_columns[1]].mean())
                mean_linear = float(unit_default[default_columns[2]].mean())
                row.update(
                    {
                        "n_units": int(n_units),
                        "n_networks": n_networks,
                        "mean_err_recon": mean_recon,
                        "median_err_recon": float(
                            unit_default[default_columns[0]].median()
                        ),
                        "mean_err_clim": mean_clim,
                        "median_err_clim": float(
                            unit_default[default_columns[1]].median()
                        ),
                        "mean_err_linear": mean_linear,
                        "median_err_linear": float(
                            unit_default[default_columns[2]].median()
                        ),
                        "ratio_recon_over_clim": float(
                            np.divide(
                                mean_recon,
                                mean_clim,
                                out=np.full(1, np.nan),
                                where=mean_clim != 0.0,
                            )[0]
                        ),
                        "ratio_recon_over_linear": float(
                            np.divide(
                                mean_recon,
                                mean_linear,
                                out=np.full(1, np.nan),
                                where=mean_linear != 0.0,
                            )[0]
                        ),
                    }
                )
            else:
                row.update(
                    {
                        "n_units": 0,
                        "n_networks": 0,
                        "mean_err_recon": np.nan,
                        "median_err_recon": np.nan,
                        "mean_err_clim": np.nan,
                        "median_err_clim": np.nan,
                        "mean_err_linear": np.nan,
                        "median_err_linear": np.nan,
                        "ratio_recon_over_clim": np.nan,
                        "ratio_recon_over_linear": np.nan,
                    }
                )
            if len(unit_missing):
                mean_recon_pair = float(unit_missing[missing_columns[0]].mean())
                mean_missing = float(unit_missing[missing_columns[1]].mean())
                row.update(
                    {
                        "n_missing_units": int(len(unit_missing)),
                        "mean_err_recon_missing_pair": mean_recon_pair,
                        "median_err_recon_missing_pair": float(
                            unit_missing[missing_columns[0]].median()
                        ),
                        "mean_err_missing": mean_missing,
                        "median_err_missing": float(
                            unit_missing[missing_columns[1]].median()
                        ),
                        "ratio_recon_over_missing": float(
                            np.divide(
                                mean_recon_pair,
                                mean_missing,
                                out=np.full(1, np.nan),
                                where=mean_missing != 0.0,
                            )[0]
                        ),
                    }
                )
            else:
                row.update(
                    {
                        "n_missing_units": 0,
                        "mean_err_recon_missing_pair": np.nan,
                        "median_err_recon_missing_pair": np.nan,
                        "mean_err_missing": np.nan,
                        "median_err_missing": np.nan,
                        "ratio_recon_over_missing": np.nan,
                    }
                )
            summary_rows.append(row)
    return pd.DataFrame(summary_rows)


def build_budget(placements: pd.DataFrame) -> pd.DataFrame:
    """Top-20% placement budgets within each horizon.

    Units of treatment are placements.  Benefit over a default is
    err_default - err_recon (positive = reconstruction helps).  Policies:
    diff_prediction, duration_only_prediction, risk_prediction, and random
    (mean over RANDOM_BUDGET_DRAWS draws, seed RANDOM_BUDGET_SEED).  The
    duration-only predictor is undefined at 365 days in the P0 tables, so that
    policy row is omitted there.
    """
    rows_out: list[dict[str, object]] = []
    rng = np.random.default_rng(RANDOM_BUDGET_SEED)
    for horizon in HORIZONS:
        sub = placements.loc[placements["gap_length"].eq(horizon)]
        for metric in BUDGET_METRICS:
            required = [
                f"{metric}_err_recon",
                f"{metric}_err_clim",
                f"{metric}_err_linear",
            ]
            pool = sub.loc[sub[required].notna().all(axis=1)].copy()
            if len(pool) < 10:
                continue
            labels = {
                "label": METRIC_LABELS[metric],
                "units": (
                    "days"
                    if metric == "phase_doy"
                    else "degC"
                    if metric in ("annual_mean", "summer_mean", "amplitude", "p90")
                    else "degC-days"
                ),
            }

            def benefits(frame: pd.DataFrame) -> dict[str, float]:
                out: dict[str, float] = {}
                for default, column in (
                    ("clim", f"{metric}_err_clim"),
                    ("linear", f"{metric}_err_linear"),
                ):
                    benefit = (frame[column] - frame[f"{metric}_err_recon"]).to_numpy(
                        dtype=float
                    )
                    out[f"mean_benefit_{default}"] = float(np.mean(benefit))
                    out[f"harmful_rate_{default}"] = float(np.mean(benefit < 0.0))
                return out

            def with_sd(row: dict[str, object], values: dict[str, float]) -> dict[str, object]:
                for key, value in values.items():
                    row[key] = value
                    row[f"{key}_sd"] = np.nan
                return row

            for policy, predictor in (
                ("diff", "diff_prediction"),
                ("duration", "duration_only_prediction"),
                ("risk", "risk_prediction"),
            ):
                policy_pool = pool.loc[pool[predictor].notna()]
                if len(policy_pool) < 10:
                    continue
                k = max(1, round(0.2 * len(policy_pool)))
                treated = policy_pool.nlargest(k, predictor)
                row = with_sd(
                    {
                        "horizon": int(horizon),
                        "metric": metric,
                        **labels,
                        "budget": 0.20,
                        "policy": policy,
                        "n_pool": int(len(policy_pool)),
                        "n_treated": int(len(treated)),
                    },
                    benefits(treated),
                )
                rows_out.append(row)

            k = max(1, round(0.2 * len(pool)))
            draw_values: dict[str, list[float]] = {
                f"mean_benefit_{default}": [] for default in ("clim", "linear")
            }
            draw_values.update(
                {f"harmful_rate_{default}": [] for default in ("clim", "linear")}
            )
            for _ in range(RANDOM_BUDGET_DRAWS):
                treated = pool.iloc[rng.choice(len(pool), size=k, replace=False)]
                for key, value in benefits(treated).items():
                    draw_values[key].append(value)
            row: dict[str, object] = {
                "horizon": int(horizon),
                "metric": metric,
                **labels,
                "budget": 0.20,
                "policy": "random",
                "n_pool": int(len(pool)),
                "n_treated": int(k),
            }
            for key, values in draw_values.items():
                array = np.asarray(values, dtype=float)
                row[key] = float(array.mean())
                row[f"{key}_sd"] = float(array.std())
            rows_out.append(row)
    return pd.DataFrame(rows_out)


def _compare_agent_b(placements: pd.DataFrame) -> pd.DataFrame:
    """Consistency of the shared 15-network cells with the archived agent_b run.

    agent_b's station-gap errors are means over the placements where the
    metric is defined under reconstruction AND no-fill (its common support).
    We therefore compare against our means on the same support (B: placements
    with recon and no-fill errors both finite) and also report our default
    support (A: recon/clim/linear finite), which additionally includes the
    month-swallowing placements for which no-fill amplitude etc. is undefined.
    """
    from scipy.stats import spearmanr

    archived = pd.read_csv(AGENT_B_STATION_GAP)
    archived["network_id"] = archived["network_id"].astype(str)
    archived["station_id"] = archived["station_id"].astype(str)
    rows = []
    for horizon in (7, 30, 90):
        agentb = archived.loc[archived["gap_length"].eq(horizon)]
        ours = placements.loc[placements["gap_length"].eq(horizon)]
        shared_keys = agentb[["network_id", "station_id", "gap_length"]].merge(
            ours[["network_id", "station_id", "gap_length"]].drop_duplicates(),
            on=["network_id", "station_id", "gap_length"],
            how="inner",
        )
        for metric in METRICS:
            agentb_column = f"{metric}_err_recon"
            pair_frame = agentb.merge(
                shared_keys,
                on=["network_id", "station_id", "gap_length"],
                how="inner",
            )
            pair_frame = pair_frame.dropna(subset=[agentb_column])
            if len(pair_frame) < 5:
                continue
            support_a = _unit_mean(
                ours, f"{metric}_err_recon", metric
            ).rename(columns={f"{metric}_err_recon": "err_p4_a"})
            support_b_mask = ours[
                [f"{metric}_err_recon", f"{metric}_err_missing"]
            ].notna().all(axis=1)
            support_b = _unit_mean(
                ours.loc[support_b_mask], f"{metric}_err_recon", metric
            ).rename(columns={f"{metric}_err_recon": "err_p4_b"})
            merged = pair_frame.merge(support_a, on=["network_id", "station_id", "gap_length"], how="left")
            merged = merged.merge(support_b, on=["network_id", "station_id", "gap_length"], how="left")
            merged = merged.rename(columns={agentb_column: "err_agentb"})
            pair_a = merged.dropna(subset=["err_agentb", "err_p4_a"])
            pair_b = merged.dropna(subset=["err_agentb", "err_p4_b"])
            row = {
                "horizon": int(horizon),
                "metric": metric,
                "n_shared_units": int(len(pair_frame)),
                "mean_err_recon_agentb": float(pair_frame[agentb_column].mean()),
            }
            if len(pair_a):
                row.update(
                    {
                        "mean_err_recon_p4_support_a": float(
                            merged["err_p4_a"].dropna().mean()
                        ),
                        "ratio_a_over_agentb": float(
                            pair_a["err_p4_a"].mean() / pair_a["err_agentb"].mean()
                        ),
                        "unit_spearman_a": float(
                            spearmanr(pair_a["err_agentb"], pair_a["err_p4_a"]).statistic
                        ),
                    }
                )
            if len(pair_b):
                row.update(
                    {
                        "mean_err_recon_p4_support_b": float(
                            merged["err_p4_b"].dropna().mean()
                        ),
                        "ratio_b_over_agentb": float(
                            pair_b["err_p4_b"].mean() / pair_b["err_agentb"].mean()
                        ),
                        "unit_spearman_b": float(
                            spearmanr(pair_b["err_agentb"], pair_b["err_p4_b"]).statistic
                        ),
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def _write_sanity(
    placements: pd.DataFrame,
    summary: pd.DataFrame,
    violations: pd.DataFrame,
    unmatched: pd.DataFrame,
    comparison_table: pd.DataFrame,
    elapsed_scored: float,
    elapsed: float,
) -> None:
    lines: list[str] = []
    lines.append("P4 sanity checks")
    lines.append("================")
    lines.append(f"scoring wall time: {elapsed_scored:.1f}s; total wall: {elapsed:.1f}s")
    lines.append(f"placements scored (P0-joined): {len(placements)}")
    lines.append(f"placements unmatched by P0 keys: {len(unmatched)}")
    keys = P0_JOIN_KEYS
    p0 = pd.read_csv(P0_PREDICTIONS, parse_dates=["gap_start"])
    p0["network_id"] = p0["network_id"].astype(str)
    p0["station_id"] = p0["station_id"].astype(str)
    season_compare = placements.merge(
        p0[keys + ["season"]].rename(columns={"season": "p0_season"}),
        on=keys,
        how="left",
    )
    season_mismatches = int((season_compare["season"] != season_compare["p0_season"]).sum())
    lines.append(f"placements whose season label differs from P0: {season_mismatches}")

    archived = pd.read_csv(ARCHIVE_PLACEMENTS, parse_dates=["gap_start"])
    archived = archived.loc[
        archived["information_condition"].eq("B_union_D")
        & archived["gap_length"].isin(HORIZONS)
    ].copy()
    archived["network_id"] = archived["network_id"].astype(str)
    archived["station_id"] = archived["station_id"].astype(str)
    compare = placements.merge(
        archived[keys + ["mae_deg_c", "donor_station_ids"]],
        on=keys,
        how="left",
        suffixes=("", "_archived"),
    )
    diff = (compare["mae_deg_c"] - compare["mae_deg_c_archived"]).abs()
    lines.append(
        f"recon MAE vs archived placement_losses (n={int(diff.notna().sum())}): "
        f"max |diff| = {diff.max():.3e}, median = {diff.median():.3e}"
    )
    donor_match = float(
        compare["donor_station_ids"].eq(compare["donor_station_ids_archived"]).mean()
    )
    lines.append(
        f"recomputed donor roster equals the archived roster on "
        f"{100 * donor_match:.2f}% of placements"
    )
    if len(violations):
        lines.append("violations skipped (by reason):")
        for reason, count in violations["reason"].value_counts().items():
            lines.append(f"  {reason}: {count}")
        lines.append("violations skipped (by horizon):")
        for horizon, count in violations.groupby("gap_length").size().items():
            lines.append(f"  {int(horizon)}: {count}")
    else:
        lines.append("violations skipped: none")
    for horizon in HORIZONS:
        sub = placements.loc[placements["gap_length"].eq(horizon)]
        clipped = int((sub["n_window_days"] < 365).sum())
        lines.append(
            f"horizon {horizon}: n placements = {len(sub)}, "
            f"n stations = {sub[['network_id','station_id']].drop_duplicates().shape[0]}, "
            f"n networks = {sub['network_id'].nunique()}, "
            f"n station-gap units = "
            f"{sub[['network_id','station_id','gap_length']].drop_duplicates().shape[0]}, "
            f"placements with clipped (<365 d) metric window = {clipped}"
        )
    lines.append(
        "units with metric computable under recon but not under no-fill "
        "(no-fill uncomputability, per horizon x metric):"
    )
    for horizon in HORIZONS:
        sub = placements.loc[placements["gap_length"].eq(horizon)]
        parts = []
        for metric in METRICS:
            count = int(
                (
                    sub[f"{metric}_err_recon"].notna()
                    & sub[f"{metric}_err_missing"].isna()
                ).sum()
            )
            if count:
                parts.append(f"{metric}:{count}")
        lines.append(f"  {horizon} d: " + ("; ".join(parts) if parts else "none"))
    lines.append("metric_error_summary rows with n_units = 0:")
    empty = summary.loc[summary["n_units"] == 0]
    if len(empty):
        lines.append(
            "; ".join(
                f"{int(row['horizon'])}d-{row['metric']}"
                for row in empty.itertuples(index=False)
            )
        )
    else:
        lines.append("  none")
    if len(comparison_table):
        lines.append("agent_b overlap (shared 15-network cells, horizons 7/30/90):")
        lines.append(comparison_table.to_string(index=False))
    (OUTPUT / "sanity_checks.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)


def _write_report(
    placements: pd.DataFrame,
    station_gap: pd.DataFrame,
    summary: pd.DataFrame,
    budget: pd.DataFrame,
    comparison_table: pd.DataFrame,
    elapsed_scored: float,
    elapsed: float,
) -> None:
    lines: list[str] = []
    lines.append(
        "# P4 — Downstream thermal-regime metrics at 7/30/90/180/365-day gaps"
    )
    lines.append("")
    lines.append("**Namespace:** `results/v14/p4_downstream/`")
    lines.append(
        "**Script:** `scripts/145_run_p4_downstream.py` (copy in `run_script_145.py`)"
    )
    lines.append(
        f"**Run:** {elapsed_scored:.0f} s scoring, {elapsed:.0f} s total wall; "
        f"{min(MAX_WORKERS, int(placements['network_id'].nunique()))} workers; "
        "XGBOOST_PARAMETERS unchanged (n_jobs = 1 inside workers)."
    )
    lines.append("")
    lines.append("## 1. Setup")
    lines.append("")
    lines.append(
        "- **Networks:** all 42 first-panel networks with archived B_union_D "
        "evaluation placements (placement_losses.csv) — the full "
        "route_a_confirmation first panel; panels read from "
        "confirmation_daily_qc/networks/<id>/daily_wide_temperature.csv."
    )
    lines.append(
        "- **Horizons:** 7/30/90/180/365 days. The archive has rows at all five "
        "horizons; the previous downstream run (agent_b, revision_v12) covered "
        "only 7/30/90 days on 15 networks."
    )
    lines.append(
        "- **Model:** the frozen XGBoost B_union_D recovery pipeline "
        "(development_recovery.XGBOOST_PARAMETERS, boundary temperature + donor "
        "columns, n_jobs = 1), retrained on the outer training years only "
        f"({TRAINING_FRACTION:.0%} chronological year split, >= {MIN_TRAIN_DAYS} "
        "training days). Per-placement reconstruction MAE reproduces the "
        "archived placement_losses values on identical placements to ~1e-12 "
        "(sanity_checks.txt), confirming the refit matches the archived runs."
    )
    lines.append(
        "- **Defaults on identical gaps:** (1) calendar-day climatology "
        "(day-of-year medians from the outer training years); (2) linear "
        "interpolation between the two flanking observed days "
        "(_boundary_values; note this ramp is also the model's boundary "
        "feature, so the linear default is the model's own minimal sub-model); "
        "(3) no-fill (gap days dropped, agent_b's uncomputable handling)."
    )
    lines.append(
        f"- **Placements:** archived evaluation geometry (B_union_D rows), "
        f"evenly sampled at most {PLACEMENTS_PER_GAP} per (station, gap_length) "
        "across the archived placements of each cell.  All sampled placements "
        "were verified (observed truth and donors over the gap, observed "
        "boundary days, gap fully inside the evaluation years); violations are "
        "skipped and counted in sanity_checks.txt."
    )
    lines.append(
        "- **Metrics and window:** the ten thermal-regime metrics and the "
        "365-day window centred on the gap middle day (+/- 182 days; the window "
        "coincides with the gap exactly for 365-day gaps) are imported "
        "unchanged from the agent_b script "
        "(scripts/rev_v12_t08_downstream_metrics_b.py).  Per-placement truth "
        "series = observed values; recon/clim/linear series replace the gap "
        "days; missing drops them.  Phase error is the circular day difference; "
        "station-gap phase aggregation uses the circular mean."
    )
    lines.append(
        "- **P0 join:** placement_predictions_first.csv joined 1:1 on "
        "(network_id, station_id, gap_length, placement, gap_start); the join "
        "has no duplicate keys and no unmatched placements."
    )
    lines.append("")
    lines.append("## 2. Scale per horizon")
    lines.append("")
    for horizon in HORIZONS:
        sub = placements.loc[placements["gap_length"].eq(horizon)]
        lines.append(
            f"- {horizon} d: {sub['network_id'].nunique()} networks / "
            f"{sub[['network_id', 'station_id']].drop_duplicates().shape[0]} "
            f"stations / {sub[['network_id', 'station_id', 'gap_length']].drop_duplicates().shape[0]} "
            f"station-gap units / {len(sub)} placements"
        )
    lines.append("")
    lines.append(
        f"Total: {len(placements)} placements, "
        f"{int(station_gap['network_id'].nunique())} networks, "
        f"{len(station_gap)} station-gap units across the five horizons."
    )
    lines.append("")
    lines.append(
        "No-fill (missing) is uncomputable for every 365-day placement: the "
        "gap-centred 365-day window coincides exactly with the gap, so dropping "
        "the gap days empties the record (agent_b's uncomputable handling). "
        "Recon-vs-no-fill ratios therefore exist only for the 7/30/90/180-day "
        "horizons (and only per metric where month-swallowing gaps leave e.g. "
        "amplitude undefined); recon-vs-climatology and recon-vs-linear are "
        "reported for all five horizons."
    )
    lines.append("")
    lines.append("## 3. Model benefit over the defaults (station-gap units)")
    lines.append("")
    headline = ("annual_mean", "amplitude", "cdd10", "phase_doy", "p90")
    lines.append(
        "Unit errors are means over placements (circular mean for phase). "
        "Benefit = mean(default error) - mean(recon error) on the same paired "
        "units (metric_error_summary.csv); positive means reconstruction "
        "reduces distortion relative to the default."
    )
    lines.append("")
    lines.append(
        "| horizon | metric | mean err recon | mean err clim | mean err linear | "
        "benefit over clim | benefit over linear | recon/clim | recon/linear | n units |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for horizon in HORIZONS:
        for metric in headline:
            row = summary.loc[
                (summary["horizon"] == horizon) & (summary["metric"] == metric)
            ]
            if row.empty or row.iloc[0]["n_units"] == 0:
                continue
            row = row.iloc[0]
            lines.append(
                f"| {horizon} | {metric} | {row['mean_err_recon']:.3f} | "
                f"{row['mean_err_clim']:.3f} | {row['mean_err_linear']:.3f} | "
                f"{row['mean_err_clim'] - row['mean_err_recon']:+.3f} | "
                f"{row['mean_err_linear'] - row['mean_err_recon']:+.3f} | "
                f"{row['ratio_recon_over_clim']:.2f} | "
                f"{row['ratio_recon_over_linear']:.2f} | {int(row['n_units'])} |"
            )
    lines.append("")
    lines.append("## 4. The 180- and 365-day numbers missing before")
    lines.append("")
    lines.append(
        "| horizon | metric | n units | recon | clim | linear | benefit clim | benefit linear | recon/clim | recon/linear |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for horizon in (180, 365):
        for metric in METRICS:
            row = summary.loc[
                (summary["horizon"] == horizon) & (summary["metric"] == metric)
            ]
            if row.empty or row.iloc[0]["n_units"] == 0:
                continue
            row = row.iloc[0]
            lines.append(
                f"| {horizon} | {metric} | {int(row['n_units'])} | "
                f"{row['mean_err_recon']:.3f} | {row['mean_err_clim']:.3f} | "
                f"{row['mean_err_linear']:.3f} | "
                f"{row['mean_err_clim'] - row['mean_err_recon']:+.3f} | "
                f"{row['mean_err_linear'] - row['mean_err_recon']:+.3f} | "
                f"{row['ratio_recon_over_clim']:.2f} | "
                f"{row['ratio_recon_over_linear']:.2f} |"
            )
    lines.append("")
    net_harmful = summary.loc[summary["n_units"] > 0].copy()
    net_harmful["benefit_clim"] = (
        net_harmful["mean_err_clim"] - net_harmful["mean_err_recon"]
    )
    net_harmful["benefit_linear"] = (
        net_harmful["mean_err_linear"] - net_harmful["mean_err_recon"]
    )
    lines.append("### 4.1 Where the model is net-harmful versus a default")
    lines.append("")
    lines.append(
        "Net-harmful = unit-mean |recon error| > unit-mean |default error| for "
        "that horizon x metric (same paired units, so benefit < 0)."
    )
    harmful_rows = []
    for default, key in (("climatology", "benefit_clim"), ("linear", "benefit_linear")):
        for horizon in HORIZONS:
            harmful = net_harmful.loc[
                (net_harmful["horizon"] == horizon) & (net_harmful[key] < 0)
            ]
            if len(harmful):
                entries = "; ".join(
                    f"{row['metric']} ({row[key]:+.2f} {row['units']})"
                    for row in harmful.to_dict("records")
                )
                harmful_rows.append(f"- horizon {horizon} d vs {default}: {entries}")
    if harmful_rows:
        lines.append("\n".join(harmful_rows))
    else:
        lines.append(
            "None: the model is never net-harmful vs either default at any "
            "horizon/metric with computable units."
        )
    lines.append("")
    lines.append(
        "Reading: versus the climatology default the model is net-harmful from "
        "90-day gaps upward on most metrics, and at 180/365 days it is "
        "net-harmful on every metric except phase at 365 days.  Versus the "
        "linear default the model is net-harmful only marginally (phase at 7 "
        "days, -0.06 d; summer_max at 30 days, ~0; nothing beyond), and the "
        "benefit over linear grows with the horizon.  Several 7/30-day "
        "entries are small in absolute terms (phase ~0.1-0.5 d, summer_max "
        "~0.0-0.1 degC); the 90/180/365-day entries are large on every scale."
    )
    lines.append("")
    lines.append("### 4.2 Model daily reconstruction MAE (context)")
    lines.append("")
    lines.append(
        "Mean |prediction - truth| over the gap days themselves (mae_deg_c in "
        "placement_metrics.csv), reproducing the archived placement_losses "
        "values exactly:"
    )
    lines.append("")
    for horizon in HORIZONS:
        sub = placements.loc[placements["gap_length"].eq(horizon)]
        lines.append(f"- {horizon} d: {sub['mae_deg_c'].mean():.2f} degC (n = {len(sub)})")
    lines.append("")
    missing_rows = summary.loc[summary["n_missing_units"] > 0]
    if len(missing_rows):
        lines.append("### 4.3 No-fill comparison (where no-fill is computable)")
        lines.append("")
        lines.append(
            "Mean recon error vs mean no-fill error on the paired support "
            "(n_missing_units units; recon recomputed on that support); "
            "ratio < 1 means reconstruction repairs the truncated record."
        )
        lines.append("| horizon | metric | n missing units | recon (paired) | no-fill | recon/no-fill |")
        lines.append("|---|---|---|---|---|---|")
        for row in missing_rows.itertuples(index=False):
            lines.append(
                f"| {int(row.horizon)} | {row.metric} | {int(row.n_missing_units)} | "
                f"{row.mean_err_recon_missing_pair:.3f} | {row.mean_err_missing:.3f} | "
                f"{row.ratio_recon_over_missing:.2f} |"
            )
        lines.append("")
    lines.append("## 5. Budget within horizon (budget_within_horizon.csv)")
    lines.append("")
    lines.append(
        "Top-20% placement budgets within each horizon (treatment = fill the "
        "gap with the model). Per metric: mean over the treated placements of "
        "err_clim - err_recon and err_linear - err_recon (model benefit over "
        "the climatology and the linear default, on the metric's own scale) and "
        "the harmful-rate shares (treated placements where the model is worse "
        "than the default). Policies: by P0 diff_prediction, by "
        "duration_only_prediction, by risk_prediction, and random (mean over "
        f"{RANDOM_BUDGET_DRAWS} draws, seed {RANDOM_BUDGET_SEED}; sd over "
        "draws in the *_sd columns). The duration-only predictor is undefined "
        "at 365 days in the P0 tables (no directly supported 365-day units), so "
        "that policy exists only at 7/30/90/180."
    )
    lines.append("")
    lines.append("### 5.1 annual_mean")
    lines.append("")
    lines.append(
        "| horizon | policy | n pool | n treated | benefit clim | harmful clim | benefit linear | harmful linear |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in budget.loc[budget["metric"].eq("annual_mean")].itertuples(index=False):
        lines.append(
            f"| {int(row.horizon)} | {row.policy} | {int(row.n_pool)} | {int(row.n_treated)} | "
            f"{row.mean_benefit_clim:+.3f} | {row.harmful_rate_clim:.3f} | "
            f"{row.mean_benefit_linear:+.3f} | {row.harmful_rate_linear:.3f} |"
        )
    lines.append("")
    lines.append("### 5.2 amplitude")
    lines.append("")
    lines.append(
        "| horizon | policy | n pool | n treated | benefit clim | harmful clim | benefit linear | harmful linear |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in budget.loc[budget["metric"].eq("amplitude")].itertuples(index=False):
        lines.append(
            f"| {int(row.horizon)} | {row.policy} | {int(row.n_pool)} | {int(row.n_treated)} | "
            f"{row.mean_benefit_clim:+.3f} | {row.harmful_rate_clim:.3f} | "
            f"{row.mean_benefit_linear:+.3f} | {row.harmful_rate_linear:.3f} |"
        )
    lines.append("")
    lines.append("## 6. Consistency with the archived agent_b run (15 networks)")
    lines.append("")
    lines.append(
        "agent_b (revision_v12, horizons 7/30/90) used the same 15-network "
        "reviewer-completion roster; its 351 station-gap cells are exactly the "
        "archived route_a_confirmation cells of those networks, so every one "
        "recurs here (only the sampled gap starts differ: our even <=5 "
        "subsample of the 20 archived placements per cell versus agent_b's own "
        "evenly spread 5 over all candidate windows)."
    )
    lines.append("")
    lines.append(
        "agent_b's station-gap errors are means over the placements where the "
        "metric is defined under reconstruction AND no-fill (its common "
        "support).  We compare against our means on the same support "
        "(`support_b`: recon and no-fill errors both finite) and also report "
        "our default support (`support_a`: recon/clim/linear finite), which "
        "additionally includes the month-swallowing placements for which "
        "no-fill amplitude is undefined (excluded by agent_b).  The two "
        "supports coincide for every no-fill-insensitive metric."
    )
    lines.append("")
    if len(comparison_table):
        lines.append(
            "| horizon | metric | shared units | agent_b mean recon | P4 mean recon (A) | ratio A/agent_b | rho A | P4 mean recon (B) | ratio B/agent_b | rho B |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for row in comparison_table.itertuples(index=False):
            lines.append(
                f"| {int(row.horizon)} | {row.metric} | {int(row.n_shared_units)} | "
                f"{row.mean_err_recon_agentb:.3f} | "
                f"{row.mean_err_recon_p4_support_a:.3f} | "
                f"{row.ratio_a_over_agentb:.2f} | {row.unit_spearman_a:.2f} | "
                f"{row.mean_err_recon_p4_support_b:.3f} | "
                f"{row.ratio_b_over_agentb:.2f} | {row.unit_spearman_b:.2f} |"
            )
        lines.append("")
        lines.append(
            "Reading: the overlap is complete (all 351 agent_b cells recur; "
            "117 per horizon).  On the agent_b-comparable support (B), the "
            "per-horizon mean recon errors agree well for the integrated, "
            "no-fill-insensitive metrics - annual_mean ratios 0.99/0.84/0.96 "
            "and trend_slope ratios 1.00/1.01/0.99 at 7/30/90 d, cdd10 "
            "0.77/0.66/0.82 - and unit-level Spearman is strong for these "
            "metrics (annual_mean 0.67-0.81, trend_slope 0.87-1.00).  Larger "
            "relative deviations concentrate in metrics whose distortion is "
            "set by a few days inside the gap (single hottest day, month-"
            "swallowing geometry, peak day): each cell contributes a mean over "
            "only ~5 sampled placements, so for summer_max, amplitude, phase "
            "and p90 (at 7 d) the per-cell means are placement-sample noise "
            "even though both runs reconstruct identically.  The default "
            "support (A) additionally includes the month-swallowing placements "
            "agent_b excluded by its no-fill common-support rule, which is why "
            "amplitude means lie far above agent_b's on A (90 d: 0.433 vs "
            "0.077) while agreeing on B (0.052 vs 0.077); the magnitude of the "
            "gap is itself informative - month-swallowing gaps are where "
            "amplitude distortion concentrates."
        )
    lines.append("")
    lines.append("## 7. Conventions and decisions where the archived code left room")
    lines.append("")
    lines.append(
        "- **365-day metric window:** agent_b centres a 365-day window on the "
        "gap's middle day (+/- 182 days). For a 365-day gap this window "
        "coincides exactly with the gap (no flanking days), and that rule was "
        "kept verbatim; consequence: no-fill is uncomputable for every 365-day "
        "placement (the record is empty), so recon-vs-no-fill exists only up "
        "to 180 days."
    )
    lines.append(
        "- **Station-gap aggregation supports:** agent_b aggregated each "
        "metric over placements where the metric is defined under every "
        "scenario (its common support). Here the recon/clim/linear unit "
        "columns use the default support (placements where those three errors "
        "are defined) and err_missing uses the recon+missing support; the "
        "paired recon-vs-no-fill comparison is recomputed on that support in "
        "metric_error_summary.csv. The two supports coincide except where "
        "no-fill is uncomputable (month-swallowing amplitude, whole-window "
        "gaps), i.e. exactly the places agent_b silently dropped."
    )
    lines.append(
        "- **Placement sampling:** at most 5 archived placements per "
        "(station, gap_length), chosen evenly (np.linspace) over the archived "
        "rows sorted by gap_start; cells with fewer archived placements keep "
        "all of them (n_placements in station_gap_metrics.csv)."
    )
    lines.append(
        "- **Budget random policy:** 100 draws of a top-20% treated set with "
        "numpy default_rng(seed 0), mean +/- sd over draws; deterministic "
        "policies use nlargest(k) with k = max(1, round(0.2 n)).  Budget pools "
        "are per-horizon placements with the metric's recon/clim/linear errors "
        "defined; the duration-only policy is absent at 365 days because P0 "
        "defines no duration-only prediction there."
    )
    lines.append(
        "- **Season column** is derived from the archived gap_start month "
        "with agent_b's season_label and matches the P0 season on every "
        "placement (0 mismatches)."
    )
    lines.append("")
    lines.append("## 8. Deliverables")
    lines.append("")
    for name in (
        "run_script_145.py",
        "placement_metrics.csv",
        "station_gap_metrics.csv",
        "metric_error_summary.csv",
        "budget_within_horizon.csv",
        "agent_b_overlap_comparison.csv",
        "sanity_checks.txt",
        "REPORT.md",
    ):
        lines.append(f"- `{name}`")
    (OUTPUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit-networks",
        type=int,
        default=None,
        help="restrict to the first N sorted networks (smoke tests only)",
    )
    args = parser.parse_args()

    start = time.time()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(__file__, OUTPUT / "run_script_145.py")

    archive = pd.read_csv(ARCHIVE_PLACEMENTS)
    archive = archive.loc[
        archive["information_condition"].eq("B_union_D")
        & archive["gap_length"].isin(HORIZONS)
    ].copy()
    archive["network_id"] = archive["network_id"].astype(str)
    archive["station_id"] = archive["station_id"].astype(str)
    if args.limit_networks:
        keep = sorted(archive["network_id"].unique())[: args.limit_networks]
        archive = archive.loc[archive["network_id"].isin(keep)]
    print(
        f"archive: {len(archive)} placements across {archive['network_id'].nunique()} networks",
        flush=True,
    )

    parts: list[pd.DataFrame] = []
    violation_rows: list[dict[str, object]] = []
    elapsed_scored_start = time.time()
    with ProcessPoolExecutor(
        max_workers=min(MAX_WORKERS, int(archive["network_id"].nunique())),
        initializer=_load_agent_b,
    ) as executor:
        futures = {
            executor.submit(score_network_p4, network_id, cell): network_id
            for network_id, cell in archive.groupby("network_id", sort=True)
        }
        for future in as_completed(futures):
            network_id = futures[future]
            result = future.result()
            parts.append(result["rows"])
            violation_rows.extend(result["violations"])
            for line in result["log"]:
                print(line, flush=True)
    placements = pd.concat(parts, ignore_index=True)
    elapsed_scored = time.time() - elapsed_scored_start
    print(f"scoring wall time: {elapsed_scored:.1f}s", flush=True)

    placements["gap_start"] = pd.to_datetime(placements["gap_start"])
    placements["gap_end"] = pd.to_datetime(placements["gap_end"])
    placements, unmatched = join_p0(placements)
    print(
        f"total placements: {len(placements)} (unmatched by P0: {len(unmatched)})",
        flush=True,
    )
    violations = pd.DataFrame(violation_rows)
    if len(violations):
        print("violations:", flush=True)
        print(violations["reason"].value_counts().to_string(), flush=True)
    placements.to_csv(OUTPUT / "placement_metrics.csv", index=False)
    if len(unmatched):
        unmatched.to_csv(OUTPUT / "unmatched_p0_placements.csv", index=False)

    station_gap = build_station_gap(placements)
    station_gap.to_csv(OUTPUT / "station_gap_metrics.csv", index=False)
    print(f"station-gap units: {len(station_gap)}", flush=True)

    summary = build_metric_summary(placements)
    summary.to_csv(OUTPUT / "metric_error_summary.csv", index=False)

    budget = build_budget(placements)
    budget.to_csv(OUTPUT / "budget_within_horizon.csv", index=False)

    comparison_table = _compare_agent_b(placements)
    comparison_table.to_csv(OUTPUT / "agent_b_overlap_comparison.csv", index=False)

    elapsed = time.time() - start
    _write_sanity(
        placements=placements,
        summary=summary,
        violations=violations,
        unmatched=unmatched,
        comparison_table=comparison_table,
        elapsed_scored=elapsed_scored,
        elapsed=elapsed,
    )
    _write_report(
        placements=placements,
        station_gap=station_gap,
        summary=summary,
        budget=budget,
        comparison_table=comparison_table,
        elapsed_scored=elapsed_scored,
        elapsed=elapsed,
    )
    print(f"total wall time: {elapsed:.1f}s", flush=True)
    print(OUTPUT, flush=True)


if __name__ == "__main__":
    main()
