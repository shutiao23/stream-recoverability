#!/usr/bin/env python3
"""Revision v12 task 07 (agent a): rolling-origin stability, history-length
learning curve, and training-data comparability for the empirical-transfer
stress-curve evaluation of the stream-temperature gap-recoverability project.

Reuses the frozen v11 machinery (``fitting_period_empirical_losses`` /
``empirical_transfer_predictions`` in
``stream_recoverability.experiments.recovery_roster``) and the frozen
fit-losses tables under ``results/development_v11/reviewer_completion``.

Design
------
Stage A (rolling origin, first confirmation panel, <= 20 networks):
  outer chronological cutoffs at 60 / 70 / 80 % of panel years.  For each
  cutoff the stress curve is built from earlier years only (inner 70/30
  split inside the outer training block, as in the canonical machinery),
  transferred to placements whose gap starts fall in the later years, and
  scored against realized placement loss.  Network-level Spearman and
  weighted calibration slope per cutoff; rank stability across cutoffs via
  Kendall's W and mean pairwise Spearman of per-network predicted ranks.

Stage B (training-data comparability, canonical 70 % split, same subset):
  the canonical stress curve trains on ~49 % of the record (70 % of the
  70 % training block) while the deployment model trains on 70 %.  A
  matched-length stress curve is built with the full 70 % training block
  (artificial gaps scored in the outer evaluation window on starts that are
  disjoint from the actual placements) and compared with the unmatched
  curve on the same outer placements.

Stage C (history-length learning curve, 20 first-panel + 20 development
networks):  stress curves are rebuilt with fitting windows of 2 / 4 / 6 / 8
years (score window fixed to the canonical inner score years); the frozen
canonical fit-losses tables serve as the "full" point.  Predictive
performance (network Spearman, calibration slope, R2) is reported against
history length; the minimum history with network Spearman >= 0.7 is the
headline.

Outputs go exclusively under results/revision_v12/t07_rolling_origin/agent_a/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stream_recoverability.experiments.development_recovery import (
    XGBOOST_PARAMETERS,
    _boundary_values,
    _candidate_starts,
    _model_frame,
    read_temperature_panel,
    select_placements,
    year_split,
)
from stream_recoverability.experiments.recovery_roster import (
    empirical_transfer_predictions,
    season_label,
)

OUTPUT = ROOT / "results/revision_v12/t07_rolling_origin/agent_a"
REVIEWER = ROOT / "results/development_v11/reviewer_completion"
CONFIRMATION_PANELS = ROOT / "results/development_v11/confirmation_daily_qc/networks"
DEV_PANELS = ROOT / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
CONFIRMATION_PLACEMENTS = ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv"
DEVELOPMENT_PLACEMENTS = ROOT / "results/development_v11/recovery_scoring/placement_losses.csv"
INVENTORY = ROOT / "results/development_v11/network_inventory.csv"
FIT_LOSSES_CONFIRM = REVIEWER / "confirmation_empirical_fit_losses.csv"
FIT_LOSSES_DEV = REVIEWER / "development_empirical_fit_losses.csv"
CROSSCHECK_PREDICTIONS = REVIEWER / "confirmation_empirical_predictions.csv"

GAPS = (7, 30, 90, 180)
# New stress-curve builds score 10 artificial gaps per season-gap cell (the
# frozen canonical tables used 20).  The curve is a mean over placements from
# the same candidate pool, so this halves compute; the frozen-vs-rebuild
# agreement is quantified in the comparability stage.
PLACEMENTS_PER_SEASON = 10
MIN_TRAIN_DAYS = 365
XGB_PARAMS = {**XGBOOST_PARAMETERS, "n_jobs": 4}

CONFIRM_SUBSET = [
    "gkd_bayern_main", "huc8_17090004", "gkd_bayern_donau", "lubw_neckar",
    "huc8_10020007", "arso_sava", "huc8_05030103", "foen_aare_aaregebiet",
    "huc8_17090001", "arso_savinja", "huc8_02040101", "lubw_rhein",
    "gkd_bayern_vils", "arso_vipava", "arso_bistrica", "arso_krka",
    "arso_dravinja", "huc8_02040104", "gkd_bayern_alz", "huc8_17060306",
]
DEV_SUBSET = [
    "huc8_01090001", "huc8_01090004", "huc8_02040106", "huc8_02040205",
    "huc8_02060003", "huc8_02070010", "huc8_04060102", "huc8_04060103",
    "huc8_04070007", "huc8_05010005", "huc8_05010006", "huc8_05010007",
    "huc8_05020005", "huc8_05020006", "huc8_05030102", "huc8_05040001",
    "huc8_05120201", "huc8_05140101", "huc8_05140102", "huc8_07040006",
]
# Longest-record networks so every 2/4/6/8 history length is feasible.
LEARNING_CONFIRM = [
    "gkd_bayern_main", "gkd_bayern_donau", "lubw_neckar", "gkd_bayern_vils",
    "gkd_bayern_alz", "huc8_17090004", "lubw_rhein", "huc8_10020007",
    "huc8_05030103", "foen_aare_aaregebiet", "huc8_17090001", "huc8_02040101",
]
LEARNING_DEV = [
    "huc8_02040106", "huc8_02040205", "huc8_05120201", "huc8_05140102",
    "huc8_05140101", "huc8_04060102", "huc8_04060103", "huc8_04070007",
    "huc8_02070010", "huc8_05010007", "huc8_05020006", "huc8_05030102",
]


def _json_safe(value: object) -> object:
    """Convert numpy scalars and non-finite floats to strict JSON values."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if np.isfinite(numeric) else None
    if value is pd.NA:
        return None
    return value


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"network_id": str, "station_id": str})


def _normalise_station(value: object, columns: pd.Index) -> str:
    station = str(value)
    if station in columns:
        return station
    if station.replace(".0", "").isdigit():
        numeric = station.replace(".0", "")
        widths = sorted({len(str(column)) for column in columns}, reverse=True)
        for width in widths:
            candidate = numeric.zfill(width)
            if candidate in columns:
                return candidate
    raise KeyError(f"station {value!r} is absent from the temperature panel")


def prediction_metrics(
    frame: pd.DataFrame, prediction: str, outcome: str
) -> dict[str, float]:
    """Pooled + network Spearman, weighted calibration, R2, RMSE (mirrors
    scripts/124_run_reviewer_completion.py::_prediction_metrics)."""
    from sklearn.metrics import r2_score

    usable = frame[["network_id", prediction, outcome]].dropna()
    if usable.empty:
        return {
            "n": 0,
            "n_networks": 0,
            "spearman": float("nan"),
            "network_spearman": float("nan"),
            "calibration_intercept": float("nan"),
            "calibration_slope": float("nan"),
            "r2": float("nan"),
            "rmse": float("nan"),
        }
    network = usable.groupby("network_id")[[prediction, outcome]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), usable[prediction]])
    intercept, slope = np.linalg.lstsq(
        design * weight[:, None],
        usable[outcome].to_numpy(dtype=float) * weight,
        rcond=None,
    )[0]
    return {
        "n": int(len(usable)),
        "n_networks": int(len(network)),
        "spearman": float(spearmanr(usable[prediction], usable[outcome]).statistic),
        "network_spearman": float(
            spearmanr(network[prediction], network[outcome]).statistic
        ),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "r2": float(r2_score(usable[outcome], usable[prediction])),
        "rmse": float(
            np.sqrt(np.mean(np.square(usable[outcome] - usable[prediction])))
        ),
    }


def _placement_exclusion_starts(
    network_id: str, placements: pd.DataFrame, daily: pd.DataFrame
) -> dict[tuple[str, int, str], set[int]]:
    """Map (station, gap, season) -> set of panel start indices occupied by the
    actual scored placements (used to keep matched stress curves honest)."""
    rows = placements.loc[
        placements["network_id"].astype(str).eq(str(network_id))
        & placements["information_condition"].eq("B_union_D")
    ].copy()
    rows["gap_start"] = pd.to_datetime(rows["gap_start"])
    rows["season"] = season_label(rows["gap_start"])
    exclusion: dict[tuple[str, int, str], set[int]] = {}
    for row in rows.itertuples(index=False):
        station = _normalise_station(row.station_id, daily.columns)
        start = daily.index.get_indexer([pd.Timestamp(row.gap_start)])[0]
        if start < 0:
            continue
        key = (station, int(row.gap_length), str(row.season))
        exclusion.setdefault(key, set()).add(start)
    return exclusion


def build_fit_losses(
    network_id: str,
    panel: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    outer_fraction: float = 0.7,
    fit_years: tuple[int, ...] | None = None,
    score_years: tuple[int, ...] | None = None,
    score_in_outer_eval: bool = False,
    exclude_placement_starts: bool = False,
    gaps: tuple[int, ...] = GAPS,
    placements_per_season: int = PLACEMENTS_PER_SEASON,
    min_train_days: int = MIN_TRAIN_DAYS,
    xgboost_parameters: dict = XGB_PARAMS,
) -> pd.DataFrame:
    """Generalized fitting-period empirical loss builder.

    Outer split at ``outer_fraction`` (first years train).  The inner split is
    either the canonical 70/30 within the training block (default), an explicit
    (``fit_years``, ``score_years``) pair for the learning curve, or the outer
    evaluation window when ``score_in_outer_eval`` (matched-length design).
    """
    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    outer_train, outer_training_years, outer_eval_years = year_split(
        daily.index, training_fraction=outer_fraction
    )
    training_index = daily.index[outer_train]
    if fit_years is not None and score_years is not None:
        fit_years = tuple(int(value) for value in fit_years)
        score_years = tuple(int(value) for value in score_years)
        if not set(fit_years).isdisjoint(set(score_years)):
            raise ValueError("fit and score years must be disjoint")
        inner_fit_years, inner_score_years = fit_years, score_years
        inner_fit = pd.Series(daily.index.year.isin(fit_years), index=daily.index)
        inner_score = pd.Series(daily.index.year.isin(score_years), index=daily.index)
    elif score_in_outer_eval:
        inner_fit_years, inner_score_years = outer_training_years, outer_eval_years
        inner_fit = outer_train
        inner_score = ~outer_train
    else:
        inner_relative, inner_fit_years, inner_score_years = year_split(
            training_index, training_fraction=0.7
        )
        inner_fit = pd.Series(False, index=daily.index)
        inner_fit.loc[training_index] = inner_relative.to_numpy(dtype=bool)
        inner_score = outer_train & ~inner_fit

    exclusion: dict[tuple[str, int, str], set[int]] = {}
    if exclude_placement_starts:
        exclusion = _placement_exclusion_starts(network_id, placements, daily)

    rows: list[dict[str, object]] = []
    network_rows = placements.loc[
        placements["network_id"].astype(str).eq(str(network_id))
        & placements["information_condition"].eq("B_union_D")
    ]
    for raw_station, station_rows in network_rows.groupby("station_id", sort=False):
        station = _normalise_station(raw_station, daily.columns)
        donor_text = str(station_rows["donor_station_ids"].iloc[0])
        donors = tuple(
            _normalise_station(value, daily.columns)
            for value in donor_text.split("|")
            if value and value != "nan"
        )
        if (
            not donors
            or int((inner_fit & daily[station].notna()).sum()) < min_train_days
        ):
            continue
        empty_aux = pd.DataFrame(index=daily.index)
        frame = _model_frame(
            daily,
            empty_aux,
            target_station=station,
            donors=donors,
            meteorology=(),
            hydraulics=(),
            train_mask=inner_fit,
        )
        fit_rows = inner_fit & daily[station].notna()
        model = XGBRegressor(**dict(xgboost_parameters))
        model.fit(frame.loc[fit_rows], daily.loc[fit_rows, station])
        for gap in (int(value) for value in gaps):
            candidates = _candidate_starts(
                daily,
                empty_aux,
                target_station=station,
                donors=donors,
                meteorology=(),
                hydraulics=(),
                evaluation_mask=inner_score,
                gap_length=gap,
            )
            if not len(candidates):
                continue
            starts_frame = pd.DataFrame(
                {
                    "start": candidates,
                    "date": daily.index[candidates],
                    "season": season_label(daily.index[candidates]),
                }
            )
            for season, candidates_by_season in starts_frame.groupby("season"):
                candidate_starts = candidates_by_season["start"].to_numpy(dtype=int)
                if exclusion:
                    excluded = exclusion.get((station, gap, str(season)), set())
                    if excluded:
                        candidate_starts = np.asarray(
                            [
                                value
                                for value in candidate_starts
                                if value not in excluded
                            ],
                            dtype=int,
                        )
                        if not len(candidate_starts):
                            continue
                chosen = select_placements(
                    candidate_starts, count=placements_per_season
                )
                for placement, start in enumerate(chosen):
                    prediction_frame = frame.iloc[start : start + gap].copy()
                    prediction_frame["B__boundary_temperature"] = _boundary_values(
                        daily[station], int(start), gap
                    )
                    if prediction_frame.isna().any(axis=None):
                        continue
                    truth = daily[station].iloc[start : start + gap].to_numpy(dtype=float)
                    predicted = model.predict(prediction_frame)
                    rows.append(
                        {
                            "network_id": str(network_id),
                            "station_id": station,
                            "gap_length": gap,
                            "season": str(season),
                            "placement": placement,
                            "gap_start": daily.index[start],
                            "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                            "model_family": "xgboost_b_d",
                            "outer_training_years": "|".join(
                                map(str, outer_training_years)
                            ),
                            "inner_fit_years": "|".join(map(str, inner_fit_years)),
                            "inner_score_years": "|".join(map(str, inner_score_years)),
                        }
                    )
    columns = [
        "network_id",
        "station_id",
        "gap_length",
        "season",
        "placement",
        "gap_start",
        "mae_deg_c",
        "model_family",
        "outer_training_years",
        "inner_fit_years",
        "inner_score_years",
    ]
    return pd.DataFrame(rows, columns=columns)


def confirmation_panel(network: str) -> pd.DataFrame:
    return read_temperature_panel(
        str(CONFIRMATION_PANELS / network / "daily_wide_temperature.csv")
    )


def development_panel(network: str, role: str) -> pd.DataFrame:
    return read_temperature_panel(
        str(DEV_PANELS / role / "networks" / network / "daily_wide_qc.csv")
    )


def filter_placements_to_eval(
    placements: pd.DataFrame, panel_years: dict[str, list[int]], fraction: float
) -> pd.DataFrame:
    filtered = []
    for network, group in placements.groupby("network_id", sort=False):
        years = panel_years[str(network)]
        cut = min(len(years) - 1, max(1, round(len(years) * fraction)))
        eval_years = set(years[cut:])
        subset = group.loc[group["gap_year"].isin(eval_years)]
        filtered.append(subset)
    return pd.concat(filtered, ignore_index=True)


def station_gap_summary(predictions: pd.DataFrame) -> pd.DataFrame:
    summary = predictions.groupby(
        ["network_id", "station_id", "gap_length"], as_index=False
    ).agg(
        empirical_transfer_prediction=("empirical_transfer_prediction", "mean"),
        observed_recovery_loss=("mae_deg_c", "mean"),
        n_placements=("placement", "size"),
        empirical_transfer_supported=("empirical_transfer_supported", "all"),
    )
    return summary


def evaluate_cutoff(
    fit_losses: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    cutoff: float,
    network_subset: list[str] | None,
    curve_source: str = "frozen_20_per_season",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = empirical_transfer_predictions(fit_losses, placements)
    predictions["cutoff_fraction"] = cutoff
    summary = station_gap_summary(predictions)
    supported = summary.loc[summary["empirical_transfer_supported"]]
    scopes = {
        "supported_only": supported,
        "all_cells": summary,
    }
    rows = []
    for scope, frame in scopes.items():
        metric = prediction_metrics(
            frame, "empirical_transfer_prediction", "observed_recovery_loss"
        )
        rows.append(
            {
                "cutoff_fraction": cutoff,
                "scope": scope,
                "network_subset": "20" if network_subset else "42",
                "curve_source": curve_source,
                **metric,
            }
        )
    return pd.DataFrame(rows), predictions


def kendall_w(ranks: pd.DataFrame, columns: list[str]) -> float:
    """Kendall's coefficient of concordance across raters (columns)."""
    m = len(columns)
    n = len(ranks)
    totals = ranks[columns].sum(axis=1).to_numpy(dtype=float)
    mean_total = totals.mean()
    numerator = 12.0 * float(np.sum(np.square(totals - mean_total)))
    denominator = (m**2) * (n**3 - n)
    return numerator / denominator if denominator else float("nan")


def network_mean_predictions(summary: pd.DataFrame) -> pd.DataFrame:
    return (
        summary.loc[summary["empirical_transfer_supported"]]
        .groupby("network_id")["empirical_transfer_prediction"]
        .mean()
        .rename("network_predicted_loss")
        .reset_index()
    )


def rank_stability(
    summaries: dict[float, pd.DataFrame], network_subset: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    ranks_by_cutoff: dict[str, pd.Series] = {}
    for cutoff, summary in sorted(summaries.items()):
        network = network_mean_predictions(summary)
        network = network.loc[network["network_id"].isin(network_subset)].set_index(
            "network_id"
        )
        ranks = network["network_predicted_loss"].rank(method="average")
        ranks_by_cutoff[f"cutoff_{int(cutoff * 100)}"] = ranks
    rank_frame = pd.DataFrame(ranks_by_cutoff)
    rank_frame["network_id"] = rank_frame.index
    rank_frame = rank_frame[["network_id", *rank_frame.columns[:-1]]].reset_index(
        drop=True
    )
    columns = [f"cutoff_{int(cutoff * 100)}" for cutoff in sorted(summaries)]
    complete = rank_frame.dropna(subset=columns).copy()
    for column in columns:
        complete[column] = complete[column].rank(method="average")
    dropped = rank_frame.loc[~rank_frame["network_id"].isin(complete["network_id"])]
    w = kendall_w(complete, columns)
    pairs = [(a, b) for i, a in enumerate(columns) for b in columns[i + 1 :]]
    pairwise = {
        f"{a}_vs_{b}": float(spearmanr(complete[a], complete[b]).statistic)
        for a, b in pairs
    }
    pairwise_tau = {
        f"{a}_vs_{b}_kendall_tau": float(kendalltau(complete[a], complete[b]).statistic)
        for a, b in pairs
    }
    stats = {
        "n_networks": int(len(complete)),
        "n_networks_attrited": int(len(dropped)),
        "attrited_network_ids": sorted(dropped["network_id"].astype(str).tolist()),
        "kendall_w": float(w),
        "mean_pairwise_spearman": float(np.mean(list(pairwise.values()))),
        "min_pairwise_spearman": float(np.min(list(pairwise.values()))),
        "mean_pairwise_kendall_tau": float(np.mean(list(pairwise_tau.values()))),
        **pairwise,
        **pairwise_tau,
    }
    return complete, pairwise_tau, stats


def compare_lengths(
    unmatched_summary: pd.DataFrame, matched_summary: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["network_id", "station_id", "gap_length"]
    unmatched = station_gap_summary(unmatched_summary).copy()
    matched = station_gap_summary(matched_summary).copy()
    joined = unmatched.merge(
        matched,
        on=keys,
        suffixes=("_unmatched", "_matched"),
        how="inner",
    )
    both_supported = joined.loc[
        joined["empirical_transfer_supported_unmatched"]
        & joined["empirical_transfer_supported_matched"]
    ].copy()
    both_supported["obs_loss"] = both_supported[
        ["observed_recovery_loss_unmatched", "observed_recovery_loss_matched"]
    ].mean(axis=1)
    pool = both_supported[
        ["network_id", "empirical_transfer_prediction_unmatched",
         "empirical_transfer_prediction_matched", "obs_loss"]
    ]
    network = pool.groupby("network_id")[
        ["empirical_transfer_prediction_unmatched",
         "empirical_transfer_prediction_matched", "obs_loss"]
    ].mean()
    network_metrics = {
        "unmatched": prediction_metrics(
            both_supported, "empirical_transfer_prediction_unmatched", "obs_loss"
        ),
        "matched": prediction_metrics(
            both_supported, "empirical_transfer_prediction_matched", "obs_loss"
        ),
        "prediction_correlation": {
            "network_spearman": float(
                spearmanr(
                    network["empirical_transfer_prediction_unmatched"],
                    network["empirical_transfer_prediction_matched"],
                ).statistic
            ),
            "network_pearson": float(
                np.corrcoef(
                    network["empirical_transfer_prediction_unmatched"],
                    network["empirical_transfer_prediction_matched"],
                )[0, 1]
            ),
            "pooled_spearman": float(
                spearmanr(
                    pool["empirical_transfer_prediction_unmatched"],
                    pool["empirical_transfer_prediction_matched"],
                ).statistic
            ),
        },
        "mean_abs_network_prediction_diff": float(
            np.mean(
                np.abs(
                    network["empirical_transfer_prediction_matched"]
                    - network["empirical_transfer_prediction_unmatched"]
                )
            )
        ),
        "max_abs_network_prediction_diff": float(
            np.max(
                np.abs(
                    network["empirical_transfer_prediction_matched"]
                    - network["empirical_transfer_prediction_unmatched"]
                )
            )
        ),
        "n_units": int(len(both_supported)),
        "n_networks": int(len(network)),
    }
    network["unmatched_rank"] = network[
        "empirical_transfer_prediction_unmatched"
    ].rank(method="average")
    network["matched_rank"] = network[
        "empirical_transfer_prediction_matched"
    ].rank(method="average")
    network["rank_change"] = (
        network["unmatched_rank"] - network["matched_rank"]
    ).abs()
    network["observed_rank"] = network["obs_loss"].rank(method="average")
    network = network.reset_index()
    summary_row = {
        "n_networks": int(len(network)),
        "network_rank_spearman": float(
            spearmanr(network["unmatched_rank"], network["matched_rank"]).statistic
        ),
        "fraction_rank_change_gt_3": float(
            np.mean(network["rank_change"].gt(3))
        ),
        "max_rank_change": float(network["rank_change"].max()),
    }
    return network, pd.DataFrame(
        [
            {
                "comparison": "matched_vs_unmatched",
                **{"unmatched_" + key: value for key, value in network_metrics["unmatched"].items()},
                **{"matched_" + key: value for key, value in network_metrics["matched"].items()},
                **network_metrics["prediction_correlation"],
                **summary_row,
                "mean_abs_network_prediction_diff": network_metrics["mean_abs_network_prediction_diff"],
                "max_abs_network_prediction_diff": network_metrics["max_abs_network_prediction_diff"],
            }
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stages",
        nargs="+",
        default=["rolling", "comparability", "learning"],
        choices=["rolling", "comparability", "learning"],
    )
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    confirmation_placements = _read_csv(CONFIRMATION_PLACEMENTS)
    development_placements = _read_csv(DEVELOPMENT_PLACEMENTS)
    confirmation_placements["gap_year"] = pd.to_datetime(
        confirmation_placements["gap_start"]
    ).dt.year
    development_placements["gap_year"] = pd.to_datetime(
        development_placements["gap_start"]
    ).dt.year
    fit_confirm = _read_csv(FIT_LOSSES_CONFIRM)
    fit_dev = _read_csv(FIT_LOSSES_DEV)
    inventory = _read_csv(INVENTORY)
    roles = inventory.set_index("network_id")["role"].to_dict()

    confirm_years: dict[str, list[int]] = {}
    for network in sorted(confirmation_placements["network_id"].unique()):
        panel = confirmation_panel(network)
        confirm_years[network] = sorted(int(value) for value in panel.index.year.unique())
    dev_years: dict[str, list[int]] = {}
    for network in sorted(development_placements["network_id"].unique()):
        panel = development_panel(network, str(roles[network]))
        dev_years[network] = sorted(int(value) for value in panel.index.year.unique())

    cross_checks: dict[str, object] = {}
    manifest: dict[str, object] = {}

    # ---------------------------------------------------------------- stage A
    if "rolling" in args.stages:
        print("=== Stage A: rolling-origin cutoffs 60/70/80 ===", flush=True)
        cutoff_metrics = []
        cutoff_predictions = []
        summaries: dict[float, pd.DataFrame] = {}

        def build_for_cutoff(cutoff: float, cache_name: str) -> pd.DataFrame:
            path = OUTPUT / f"{cache_name}.csv"
            if path.is_file() and path.stat().st_size > 0:
                return _read_csv(path)
            parts = []
            for ordinal, network in enumerate(CONFIRM_SUBSET, start=1):
                print(
                    f"  cutoff {int(cutoff * 100)}% build {ordinal}/{len(CONFIRM_SUBSET)}: {network}",
                    flush=True,
                )
                panel = confirmation_panel(network)
                built = build_fit_losses(
                    network,
                    panel,
                    confirmation_placements,
                    outer_fraction=cutoff,
                    placements_per_season=PLACEMENTS_PER_SEASON,
                )
                parts.append(built)
            frame = pd.concat(parts, ignore_index=True)
            frame.to_csv(path, index=False)
            return frame

        fit_70_subset = build_for_cutoff(0.7, "fit_losses_cutoff_70_subset")
        for cutoff in (0.6, 0.7, 0.8):
            if cutoff == 0.7:
                fit_losses = fit_70_subset
                curve_source = "rebuild_10_per_season"
            else:
                fit_losses = build_for_cutoff(cutoff, f"fit_losses_cutoff_{int(cutoff * 100)}")
                curve_source = "rebuild_10_per_season"
            placements = filter_placements_to_eval(
                confirmation_placements, confirm_years, cutoff
            )
            subset_placements = placements.loc[
                placements["network_id"].isin(CONFIRM_SUBSET)
            ]
            subset_metrics, subset_predictions = evaluate_cutoff(
                fit_losses,
                subset_placements,
                cutoff=cutoff,
                network_subset=CONFIRM_SUBSET,
                curve_source=curve_source,
            )
            subset_metrics.to_csv(
                OUTPUT / f"rolling_metrics_subset_cutoff_{int(cutoff * 100)}.csv",
                index=False,
            )
            subset_predictions.to_csv(
                OUTPUT / f"rolling_predictions_cutoff_{int(cutoff * 100)}.csv",
                index=False,
            )
            cutoff_metrics.append(subset_metrics)
            cutoff_predictions.append(subset_predictions)
            summary = station_gap_summary(subset_predictions)
            summaries[cutoff] = summary
            print(
                f"  cutoff {int(cutoff * 100)}% subset20: {subset_metrics.to_dict(orient='records')}",
                flush=True,
            )

        # canonical frozen rows: all 42 networks at 70% (cross-check) and the
        # 20-network restriction of the same frozen table
        placements70 = filter_placements_to_eval(
            confirmation_placements, confirm_years, 0.7
        )
        frozen_all, frozen_all_pred = evaluate_cutoff(
            fit_confirm, placements70, cutoff=0.7, network_subset=None
        )
        frozen_all_pred.to_csv(
            OUTPUT / "rolling_predictions_cutoff_70_frozen_all42.csv", index=False
        )
        cutoff_predictions.append(frozen_all_pred)
        cutoff_metrics.append(frozen_all)
        frozen_subset, frozen_subset_pred = evaluate_cutoff(
            fit_confirm,
            placements70.loc[placements70["network_id"].isin(CONFIRM_SUBSET)],
            cutoff=0.7,
            network_subset=CONFIRM_SUBSET,
        )
        cutoff_metrics.append(frozen_subset)
        cutoff_predictions.append(frozen_subset_pred)
        print(
            f"  cutoff 70% frozen all42: {frozen_all.to_dict(orient='records')}",
            flush=True,
        )
        print(
            f"  cutoff 70% frozen subset20: {frozen_subset.to_dict(orient='records')}",
            flush=True,
        )
        metrics_all = pd.concat(cutoff_metrics, ignore_index=True)
        metrics_all.to_csv(OUTPUT / "rolling_origin_metrics.csv", index=False)
        pd.concat(cutoff_predictions, ignore_index=True).to_csv(
            OUTPUT / "rolling_origin_predictions.csv", index=False
        )

        rank_frame, pairwise_tau, stability = rank_stability(summaries, CONFIRM_SUBSET)
        rank_frame.to_csv(OUTPUT / "rolling_origin_network_ranks.csv", index=False)
        pd.DataFrame([stability]).to_csv(
            OUTPUT / "rolling_origin_rank_stability.csv", index=False
        )
        print(f"  rank stability: {stability}", flush=True)

        canonical = metrics_all.loc[
            (metrics_all["cutoff_fraction"].eq(0.7))
            & (metrics_all["scope"].eq("supported_only"))
            & (metrics_all["network_subset"].eq("42"))
        ].iloc[0]
        cross_checks["canonical_70_supported_only"] = {
            "expected_n_units": 780,
            "n_units": int(canonical["n"]),
            "expected_pooled_spearman": 0.9341048983106937,
            "pooled_spearman": canonical["spearman"],
            "expected_network_spearman": 0.9218863949436837,
            "network_spearman": canonical["network_spearman"],
            "expected_calibration_slope": 0.8635904833613768,
            "calibration_slope": canonical["calibration_slope"],
            "match": bool(
                abs(canonical["spearman"] - 0.9341048983106937) < 1e-9
                and abs(canonical["network_spearman"] - 0.9218863949436837) < 1e-9
                and int(canonical["n"]) == 780
            ),
        }
        complete = metrics_all.loc[
            (metrics_all["cutoff_fraction"].eq(0.7))
            & (metrics_all["scope"].eq("all_cells"))
            & (metrics_all["network_subset"].eq("42"))
        ].iloc[0]
        cross_checks["canonical_70_all_cells_network_spearman"] = {
            "expected": 0.766631553358723,
            "value": complete["network_spearman"],
            "match": bool(abs(complete["network_spearman"] - 0.766631553358723) < 1e-9),
        }
        manifest["rolling_origin"] = {
            "design": (
                "outer chronological cutoff of panel years; stress curve built "
                "inside the training block (inner 70/30) and transferred to "
                "placements in the later years; canonical 70% row reproduces the "
                "frozen reviewer-completion evaluation"
            ),
            "first_panel_networks": len(CONFIRM_SUBSET),
            "cutoffs": [0.6, 0.7, 0.8],
            "rank_stability": stability,
        }

    # ------------------------------------------------------------- stage B
    if "comparability" in args.stages:
        print("=== Stage B: matched vs unmatched training length ===", flush=True)
        matched_path = OUTPUT / "fit_losses_matched_70.csv"
        if matched_path.is_file():
            matched_fit = _read_csv(matched_path)
        else:
            parts = []
            for ordinal, network in enumerate(CONFIRM_SUBSET, start=1):
                print(
                    f"  matched build {ordinal}/{len(CONFIRM_SUBSET)}: {network}",
                    flush=True,
                )
                panel = confirmation_panel(network)
                built = build_fit_losses(
                    network,
                    panel,
                    confirmation_placements,
                    outer_fraction=0.7,
                    score_in_outer_eval=True,
                    exclude_placement_starts=True,
                )
                parts.append(built)
            matched_fit = pd.concat(parts, ignore_index=True)
            matched_fit.to_csv(matched_path, index=False)
        placements70 = filter_placements_to_eval(
            confirmation_placements, confirm_years, 0.7
        )
        subset70 = placements70.loc[placements70["network_id"].isin(CONFIRM_SUBSET)]
        matched_pred = empirical_transfer_predictions(matched_fit, subset70)
        matched_pred.to_csv(OUTPUT / "comparability_matched_predictions.csv", index=False)
        unmatched_pred = empirical_transfer_predictions(fit_70_subset, subset70)
        unmatched_pred.to_csv(
            OUTPUT / "comparability_unmatched_predictions.csv", index=False
        )
        network_cmp, summary_cmp = compare_lengths(unmatched_pred, matched_pred)
        network_cmp.to_csv(OUTPUT / "comparability_network_level.csv", index=False)
        summary_cmp.to_csv(OUTPUT / "comparability_summary.csv", index=False)
        print(f"  comparability: {summary_cmp.to_dict(orient='records')}", flush=True)
        matched_metrics = evaluate_cutoff(
            matched_fit, subset70, cutoff=0.7, network_subset=CONFIRM_SUBSET,
            curve_source="matched_70_per_season_10",
        )[0]
        unmatched_metrics = evaluate_cutoff(
            fit_70_subset, subset70, cutoff=0.7, network_subset=CONFIRM_SUBSET,
            curve_source="unmatched_49_per_season_10",
        )[0]
        frozen_subset_metrics = evaluate_cutoff(
            fit_confirm.loc[fit_confirm["network_id"].isin(CONFIRM_SUBSET)],
            subset70,
            cutoff=0.7,
            network_subset=CONFIRM_SUBSET,
            curve_source="unmatched_49_frozen_20_per_season",
        )[0]
        pd.concat(
            [unmatched_metrics, matched_metrics, frozen_subset_metrics],
            ignore_index=True,
        ).to_csv(OUTPUT / "comparability_cutoff_metrics.csv", index=False)
        manifest["comparability"] = {
            "design": (
                "unmatched: stress model trained on inner 70% of the training "
                "block (~49% of record), curve scored in the inner 30%; matched: "
                "stress model trained on the full 70% training block, curve scored "
                "on artificial gaps in the outer evaluation window on starts "
                "disjoint from the actual placements"
            ),
            "summary": summary_cmp.to_dict(orient="records")[0],
        }

    # ------------------------------------------------------------- stage C
    if "learning" in args.stages:
        print("=== Stage C: history-length learning curve ===", flush=True)
        learning_parts = []
        learning_metrics = []
        canonical_score_years: dict[str, list[int]] = {}
        canonical_fit_years: dict[str, list[int]] = {}
        for frame in (fit_confirm, fit_dev):
            for network, group in frame.groupby("network_id"):
                first = group.iloc[0]
                canonical_score_years[str(network)] = [
                    int(value) for value in str(first["inner_score_years"]).split("|")
                ]
                canonical_fit_years[str(network)] = [
                    int(value) for value in str(first["inner_fit_years"]).split("|")
                ]

        networks = []
        for network in LEARNING_CONFIRM:
            networks.append(("first_panel", network, confirmation_placements))
        for network in LEARNING_DEV:
            networks.append(("development", network, development_placements))

        eval_placements = {
            "first_panel": filter_placements_to_eval(
                confirmation_placements, confirm_years, 0.7
            ),
            "development": filter_placements_to_eval(
                development_placements, dev_years, 0.7
            ),
        }
        accumulated: dict[tuple[str, object, str], list[pd.DataFrame]] = {}
        for panel_name, network, all_placements in networks:
            fit_length = len(canonical_fit_years[network])
            score_years = tuple(canonical_score_years[network])
            for history in (2, 4, 6, 8):
                if history > fit_length:
                    continue
                path = OUTPUT / f"learning_fit_losses_{panel_name}_{network}_{history}y.csv"
                if path.is_file():
                    try:
                        built = _read_csv(path)
                        if built.empty:
                            built = pd.DataFrame()
                    except pd.errors.EmptyDataError:
                        built = pd.DataFrame()
                else:
                    panel = (
                        confirmation_panel(network)
                        if panel_name == "first_panel"
                        else development_panel(network, str(roles[network]))
                    )
                    years = sorted(panel.index.year.unique())
                    fit_years = tuple(years[:history])
                    print(
                        f"  learning {panel_name} {network} history={history}: fit {fit_years} score {score_years}",
                        flush=True,
                    )
                    built = build_fit_losses(
                        network,
                        panel,
                        all_placements,
                        outer_fraction=0.7,
                        fit_years=fit_years,
                        score_years=score_years,
                    )
                    built.to_csv(path, index=False)
                if built.empty:
                    print(
                        f"  learning {panel_name} {network} history={history}: EMPTY (no station passes fit-window coverage)",
                        flush=True,
                    )
                    continue
                predictions = empirical_transfer_predictions(
                    built,
                    eval_placements[panel_name].loc[
                        eval_placements[panel_name]["network_id"].eq(network)
                    ],
                )
                predictions["history_years"] = history
                predictions["panel"] = panel_name
                predictions["network_scope"] = "learning_subset"
                learning_parts.append(predictions)
                accumulated.setdefault(
                    (panel_name, history, "learning_subset"), []
                ).append(predictions)

        for panel_name, frame, marker in (
            ("first_panel", fit_confirm, "full"),
            ("development", fit_dev, "full"),
        ):
            for network_scope, scope_placements in (
                ("all", eval_placements[panel_name]),
                (
                    "learning_subset",
                    eval_placements[panel_name].loc[
                        eval_placements[panel_name]["network_id"].isin(
                            LEARNING_CONFIRM if panel_name == "first_panel" else LEARNING_DEV
                        )
                    ],
                ),
            ):
                predictions = empirical_transfer_predictions(
                    frame, scope_placements
                )
                predictions["history_years"] = marker
                predictions["panel"] = panel_name
                predictions["network_scope"] = network_scope
                learning_parts.append(predictions)
                accumulated.setdefault(
                    (panel_name, marker, network_scope), []
                ).append(predictions)

        learning_metrics = []
        for (panel_name, history, network_scope), parts in accumulated.items():
            combined = pd.concat(parts, ignore_index=True)
            summary = station_gap_summary(combined)
            supported = summary.loc[summary["empirical_transfer_supported"]]
            for scope, frame in (("supported_only", supported), ("all_cells", summary)):
                learning_metrics.append(
                    {
                        "panel": panel_name,
                        "history_years": history,
                        "network_scope": network_scope,
                        "scope": scope,
                        **prediction_metrics(
                            frame,
                            "empirical_transfer_prediction",
                            "observed_recovery_loss",
                        ),
                    }
                )
        learning_metrics = pd.DataFrame(learning_metrics)
        learning_metrics.to_csv(OUTPUT / "learning_curve_metrics.csv", index=False)
        pd.concat(learning_parts, ignore_index=True).to_csv(
            OUTPUT / "learning_curve_predictions.csv", index=False
        )
        print(learning_metrics.to_string(index=False), flush=True)

        # headline: minimum history with network Spearman >= 0.7
        supported_curve = learning_metrics.loc[
            learning_metrics["scope"].eq("supported_only")
            & learning_metrics["network_scope"].eq("learning_subset")
        ].copy()
        supported_curve["_history_order"] = np.where(
            supported_curve["history_years"].astype(str).eq("full"),
            99,
            pd.to_numeric(supported_curve["history_years"], errors="coerce"),
        )
        headline = {}
        for panel_name, values in supported_curve.groupby("panel"):
            ordered = values.sort_values("_history_order")
            usable = ordered.loc[~ordered["history_years"].astype(str).eq("full")]
            first_above = usable.loc[usable["network_spearman"].ge(0.7)]
            min_history = (
                float(first_above["_history_order"].min()) if len(first_above) else None
            )
            full_row = ordered.loc[ordered["history_years"].astype(str).eq("full")]
            headline[panel_name] = {
                "min_history_network_spearman_ge_07": min_history,
                "network_spearman_8y": float(
                    usable.loc[usable["_history_order"].eq(8), "network_spearman"].iloc[0]
                    if (usable["_history_order"].eq(8)).any()
                    else np.nan
                ),
                "n_networks_by_history": {
                    str(history): int(count)
                    for history, count in zip(
                        usable["history_years"], usable["n_networks"]
                    )
                },
                "full_network_spearman": float(full_row["network_spearman"].iloc[0]),
            }
        manifest["learning_curve"] = {
            "design": (
                "stress curves fit on the first 2/4/6/8 years of each panel "
                "record, artificial gaps scored in the canonical inner score "
                "years, transferred to the canonical outer placements; 'full' is "
                "the frozen canonical fit-losses table (inner 70% of the training "
                "block).  New builds score 10 placements per season-gap cell "
                "(frozen tables: 20); the agreement of the two conventions is "
                "quantified in the comparability stage."
            ),
            "headline": headline,
        }
        print(f"  learning-curve headline: {headline}", flush=True)

        # figure
        colors = {"first_panel": "#0072B2", "development": "#D55E00"}
        figure, axes = plt.subplots(1, 2, figsize=(11, 4.2))
        for panel_name, values in supported_curve.groupby("panel"):
            ordered = values.sort_values("_history_order")
            numeric = ordered.loc[~ordered["history_years"].astype(str).eq("full")]
            full = ordered.loc[ordered["history_years"].astype(str).eq("full")]
            axes[0].plot(
                numeric["_history_order"].astype(int),
                numeric["network_spearman"],
                marker="o",
                color=colors[panel_name],
                label=f"{panel_name.replace('_', ' ')} (n={int(values['n_networks'].iloc[0])})",
            )
            axes[0].axhline(
                full["network_spearman"].iloc[0],
                color=colors[panel_name],
                ls="--",
                lw=1,
            )
            axes[1].plot(
                numeric["_history_order"].astype(int),
                numeric["calibration_slope"],
                marker="o",
                color=colors[panel_name],
            )
            axes[1].axhline(
                full["calibration_slope"].iloc[0],
                color=colors[panel_name],
                ls="--",
                lw=1,
            )
        axes[0].axhline(0.7, color="black", lw=0.8, ls=":")
        axes[0].annotate("network Spearman = 0.7", (2.1, 0.71), fontsize=8)
        axes[0].set(
            xlabel="Stress-model fitting history (years)",
            ylabel="Network-level Spearman",
            title="Ranking skill vs fitting history",
            ylim=(0.4, 1.0),
        )
        axes[0].legend(frameon=False, fontsize=8)
        axes[1].set(
            xlabel="Stress-model fitting history (years)",
            ylabel="Calibration slope",
            title="Calibration vs fitting history",
            ylim=(0.3, 1.2),
        )
        figure.tight_layout()
        figure.savefig(OUTPUT / "learning_curve.png", dpi=300)
        plt.close(figure)

    manifest["subsets"] = {
        "first_panel_20": CONFIRM_SUBSET,
        "development_20": DEV_SUBSET,
        "learning_first_panel_12": LEARNING_CONFIRM,
        "learning_development_12": LEARNING_DEV,
    }
    manifest["cross_checks"] = cross_checks
    (OUTPUT / "manifest.json").write_text(
        json.dumps(_json_safe(manifest), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print("manifest written:", OUTPUT / "manifest.json", flush=True)


if __name__ == "__main__":
    main()
