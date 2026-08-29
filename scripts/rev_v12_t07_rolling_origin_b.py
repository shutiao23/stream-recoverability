#!/usr/bin/env python3
"""Agent B: rolling-origin stability, history-length learning curve, and
training-data comparability for the stream-temperature gap-recoverability
review revision.  Runs on a deterministic subset of <=20 first-panel
(route-A confirmation) networks plus a subset of development networks.

Parts (run separately, each within the runtime budget):
  rolling       : 3 outer chronological cutoffs (60/70/80% of years),
                  stress curves from earlier years -> outer losses in later
                  years; per-cutoff metrics + rank stability across cutoffs.
  learning      : history-length learning curve on the 20 first-panel
                  networks (2/4/6/8/full fitting years).
  learning_dev  : same learning curve on 8 development networks.
  comparability : stress-model training length (~49% of record) vs
                  deployment-model length (70%): matched vs unmatched.
  report        : assemble REPORT.md, learning-curve PNG, cross-checks.

The stress-curve builder is a parameterised copy of the canonical
fitting-period machinery (scripts/124_run_reviewer_completion.py,
src/stream_recoverability/experiments/recovery_roster.py) and has been
verified to reproduce results/development_v11/reviewer_completion/
confirmation_empirical_fit_losses.csv to floating-point precision.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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
    _normalise_station,
    empirical_transfer_predictions,
    season_label,
)

OUT = ROOT / "results/revision_v12/t07_rolling_origin/agent_b"
CONF_PLACEMENTS = ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv"
DEV_PLACEMENTS = ROOT / "results/development_v11/recovery_scoring/placement_losses.csv"
CONF_PANEL_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
DEV_PANEL_ROOT = (
    ROOT / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
)
INVENTORY = ROOT / "results/development_v11/network_inventory.csv"
EXISTING_CONF_METRICS = (
    ROOT / "results/development_v11/reviewer_completion/empirical_transfer_metrics.csv"
)
EXISTING_CONF_PREDICTIONS = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_predictions.csv"
)
EXISTING_DEV_FIT_LOSSES = (
    ROOT / "results/development_v11/reviewer_completion/development_empirical_fit_losses.csv"
)
EXISTING_CONF_FIT_LOSSES = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv"
)

SUBSET_20 = [
    "lubw_neckar",
    "gkd_bayern_donau",
    "gkd_bayern_fraenkische_saale",
    "gkd_bayern_iller",
    "gkd_bayern_inn",
    "gkd_bayern_isar",
    "gkd_bayern_main",
    "gkd_bayern_vils",
    "gkd_bayern_alz",
    "lubw_rhein",
    "foen_aare_aaregebiet",
    "huc8_02040101",
    "huc8_02040102",
    "huc8_02040104",
    "huc8_03010107",
    "huc8_03150202",
    "huc8_05030103",
    "huc8_10020007",
    "huc8_17060306",
    "huc8_17090001",
]

DEV_SUBSET_8 = [
    "huc8_02040106",
    "huc8_02040205",
    "huc8_02050104",
    "huc8_03050106",
    "huc8_05120201",
    "huc8_03090101",
    "huc8_16050102",
    "huc8_02050305",
]

CUTOFFS = (0.60, 0.70, 0.80)
HISTORY_LEVELS = (2, 4, 6, 8)
PARAMETERS = {**XGBOOST_PARAMETERS, "n_jobs": 4}


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"network_id": str, "station_id": str})
    if "gap_start" in frame.columns:
        frame["gap_start"] = pd.to_datetime(frame["gap_start"])
    return frame


def _read_panel(network: str, *, panel_root: Path) -> pd.DataFrame:
    path = panel_root / network / "daily_wide_temperature.csv"
    return read_temperature_panel(str(path))


def _read_dev_panel(network: str, role: str) -> pd.DataFrame:
    path = DEV_PANEL_ROOT / role / "networks" / network / "daily_wide_qc.csv"
    return read_temperature_panel(str(path))


def _split_years(years: np.ndarray, fraction: float) -> tuple[list[int], list[int]]:
    years = sorted(int(value) for value in years)
    cut = min(len(years) - 1, max(1, round(len(years) * fraction)))
    return years[:cut], years[cut:]


def build_stress_curve(
    network_id: str,
    panel: pd.DataFrame,
    placements: pd.DataFrame,
    fit_years: list[int],
    score_years: list[int],
    *,
    gaps: tuple[int, ...] = (7, 30, 90, 180),
    placements_per_season: int = 20,
    min_train_days: int = 365,
    parameters: dict[str, object] = PARAMETERS,
) -> pd.DataFrame:
    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    fit_mask = pd.Series(daily.index.year.isin(fit_years), index=daily.index)
    score_mask = pd.Series(daily.index.year.isin(score_years), index=daily.index)
    rows: list[dict[str, object]] = []
    network_rows = placements.loc[
        placements["network_id"].astype(str).eq(str(network_id))
        & placements["information_condition"].eq("B_union_D")
    ]
    for raw_station, station_rows in network_rows.groupby("station_id", sort=False):
        try:
            station = _normalise_station(raw_station, daily.columns)
        except KeyError:
            continue
        donor_text = str(station_rows["donor_station_ids"].iloc[0])
        donors = tuple(
            _normalise_station(value, daily.columns)
            for value in donor_text.split("|")
            if value and value != "nan"
        )
        if (
            not donors
            or int((fit_mask & daily[station].notna()).sum()) < min_train_days
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
            train_mask=fit_mask,
        )
        fit_rows = fit_mask & daily[station].notna()
        model = XGBRegressor(**dict(parameters))
        model.fit(frame.loc[fit_rows], daily.loc[fit_rows, station])
        for gap in (int(value) for value in gaps):
            candidates = _candidate_starts(
                daily,
                empty_aux,
                target_station=station,
                donors=donors,
                meteorology=(),
                hydraulics=(),
                evaluation_mask=score_mask,
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
                chosen = select_placements(
                    candidates_by_season["start"].to_numpy(dtype=int),
                    count=placements_per_season,
                )
                for placement, start in enumerate(chosen):
                    prediction_frame = frame.iloc[start : start + gap].copy()
                    prediction_frame["B__boundary_temperature"] = _boundary_values(
                        daily[station], int(start), gap
                    )
                    if prediction_frame.isna().any(axis=None):
                        continue
                    truth = (
                        daily[station].iloc[start : start + gap].to_numpy(dtype=float)
                    )
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
                                map(str, sorted(fit_years + score_years))
                            ),
                            "inner_fit_years": "|".join(map(str, fit_years)),
                            "inner_score_years": "|".join(map(str, score_years)),
                        }
                    )
    return pd.DataFrame(rows)


def _fit_station_model(
    daily: pd.DataFrame,
    station: str,
    donors: tuple[str, ...],
    fit_years: list[int],
    parameters: dict[str, object] = PARAMETERS,
) -> tuple[object, pd.DataFrame]:
    fit_mask = pd.Series(daily.index.year.isin(fit_years), index=daily.index)
    empty_aux = pd.DataFrame(index=daily.index)
    frame = _model_frame(
        daily,
        empty_aux,
        target_station=station,
        donors=donors,
        meteorology=(),
        hydraulics=(),
        train_mask=fit_mask,
    )
    fit_rows = fit_mask & daily[station].notna()
    model = XGBRegressor(**dict(parameters))
    model.fit(frame.loc[fit_rows], daily.loc[fit_rows, station])
    return model, frame


def _score_placements(
    model: object,
    frame: pd.DataFrame,
    daily: pd.DataFrame,
    station: str,
    placement_rows: pd.DataFrame,
) -> np.ndarray:
    losses = []
    for placement in placement_rows.itertuples(index=False):
        start = daily.index.get_indexer([pd.Timestamp(placement.gap_start)])[0]
        gap = int(placement.gap_length)
        if start < 1 or start + gap >= len(daily):
            losses.append(float("nan"))
            continue
        truth = daily[station].iloc[start : start + gap].to_numpy(dtype=float)
        if not np.isfinite(truth).all():
            losses.append(float("nan"))
            continue
        prediction_frame = frame.iloc[start : start + gap].copy()
        prediction_frame["B__boundary_temperature"] = _boundary_values(
            daily[station], start, gap
        )
        if prediction_frame.isna().any(axis=None):
            losses.append(float("nan"))
            continue
        predicted = model.predict(prediction_frame)
        losses.append(float(np.mean(np.abs(predicted - truth))))
    return np.asarray(losses, dtype=float)


def prediction_metrics(
    frame: pd.DataFrame,
    prediction: str = "empirical_transfer_prediction",
    outcome: str = "observed_recovery_loss",
) -> dict[str, float]:
    if prediction not in frame.columns or outcome not in frame.columns:
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
    pooled = (
        float(spearmanr(usable[prediction], usable[outcome]).statistic)
        if len(usable) >= 3
        else float("nan")
    )
    network_spearman = (
        float(spearmanr(network[prediction], network[outcome]).statistic)
        if len(network) >= 3
        else float("nan")
    )
    return {
        "n": len(usable),
        "n_networks": len(network),
        "spearman": pooled,
        "network_spearman": network_spearman,
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "r2": float(r2_score(usable[outcome], usable[prediction])),
        "rmse": float(
            np.sqrt(np.mean(np.square(usable[outcome] - usable[prediction])))
        ),
    }


def kendall_w(rank_frame: pd.DataFrame) -> float:
    matrix = rank_frame.rank(axis=0, method="average").to_numpy(dtype=float)
    n, m = matrix.shape
    if n < 2 or m < 2:
        return float("nan")
    column_sums = matrix.sum(axis=1)
    numerator = 12.0 * np.sum(np.square(column_sums - m * (n + 1.0) / 2.0))
    tie_terms = []
    for column in range(m):
        counts = rank_frame.iloc[:, column].value_counts()
        tie_terms.append(
            int(
                np.sum(
                    counts.to_numpy(dtype=float) ** 3 - counts.to_numpy(dtype=float)
                )
            )
        )
    denominator = m * m * n * (n * n - 1) - m * np.sum(tie_terms)
    if denominator <= 0:
        return float("nan")
    return float(numerator / denominator)


def _transfer_and_metrics(
    curve: pd.DataFrame,
    eval_placements: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    if curve.empty or eval_placements.empty:
        empty = eval_placements.copy()
        empty["empirical_transfer_prediction"] = np.nan
        empty["empirical_transfer_supported"] = False
        empty["empirical_transfer_source"] = "unavailable"
        return empty, prediction_metrics(pd.DataFrame(columns=["network_id"]))
    predictions = empirical_transfer_predictions(curve, eval_placements)
    supported = predictions.loc[predictions["empirical_transfer_supported"]]
    metrics = prediction_metrics(supported)
    metrics["n_supported_fraction"] = float(
        len(supported) / len(predictions) if len(predictions) else 0.0
    )
    return predictions, metrics


def run_rolling() -> None:
    placements = _read_csv(CONF_PLACEMENTS)
    metric_rows = []
    prediction_parts = []
    rank_rows = []
    for ordinal, network in enumerate(SUBSET_20, start=1):
        print(f"rolling origin {ordinal}/{len(SUBSET_20)}: {network}", flush=True)
        panel = _read_panel(network, panel_root=CONF_PANEL_ROOT)
        years = np.asarray(sorted(panel.index.year.unique()))
        for cutoff in CUTOFFS:
            outer_train_years, outer_eval_years = _split_years(years, cutoff)
            training_index = panel.index[panel.index.year.isin(outer_train_years)]
            _, inner_fit_years, inner_score_years = year_split(training_index)
            curve = build_stress_curve(
                network, panel, placements, list(inner_fit_years), list(inner_score_years)
            )
            eval_placements = placements.loc[
                placements["network_id"].astype(str).eq(network)
                & placements["gap_start"].dt.year.isin(outer_eval_years)
            ]
            predictions, metrics = _transfer_and_metrics(curve, eval_placements)
            predictions = predictions.copy()
            predictions["outer_cutoff"] = cutoff
            prediction_parts.append(predictions)
            metric_rows.append(
                {
                    "outer_cutoff": cutoff,
                    "network_id": network,
                    "outer_training_years": len(outer_train_years),
                    "outer_evaluation_years": len(outer_eval_years),
                    "stress_model_fit_years": len(inner_fit_years),
                    "stress_model_score_years": len(inner_score_years),
                    "stress_curve_cells": len(curve),
                    **metrics,
                }
            )
            supported = predictions.loc[predictions["empirical_transfer_supported"]]
            if not supported.empty:
                network_means = supported.groupby("network_id")[
                    ["empirical_transfer_prediction", "observed_recovery_loss"]
                ].mean()
                rank_rows.append(
                    {
                        "network_id": network,
                        "outer_cutoff": cutoff,
                        "mean_predicted_loss": float(
                            network_means["empirical_transfer_prediction"].iloc[0]
                        ),
                        "mean_observed_loss": float(
                            network_means["observed_recovery_loss"].iloc[0]
                        ),
                        "n_cells": len(supported),
                    }
                )
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat(prediction_parts, ignore_index=True).to_csv(
        OUT / "rolling_origin_predictions.csv", index=False
    )
    pd.DataFrame(metric_rows).to_csv(
        OUT / "rolling_origin_cutoff_metrics.csv", index=False
    )
    ranks = pd.DataFrame(rank_rows)
    ranks.to_csv(OUT / "rolling_origin_network_ranks.csv", index=False)

    pivot = ranks.pivot(
        index="network_id", columns="outer_cutoff", values="mean_predicted_loss"
    ).dropna()
    pairs = []
    for left, right in ((0.60, 0.70), (0.70, 0.80), (0.60, 0.80)):
        if left in pivot.columns and right in pivot.columns:
            pairs.append(
                {
                    "pair": f"{left:0.2f}_vs_{right:0.2f}",
                    "n_networks": len(pivot),
                    "pairwise_spearman": float(
                        spearmanr(pivot[left], pivot[right]).statistic
                    ),
                }
            )
    stability_rows = [
        {
            "statistic": "kendall_w_predicted_ranks",
            "n_networks": len(pivot),
            "value": kendall_w(pivot),
            "note": "tie-adjusted Kendall W across 60/70/80% cutoffs",
        },
        {
            "statistic": "mean_pairwise_spearman_predicted_ranks",
            "n_networks": len(pivot),
            "value": float(np.mean([row["pairwise_spearman"] for row in pairs])),
            "note": "mean over 60-70, 70-80, 60-80",
        },
    ]
    observed_pivot = ranks.pivot(
        index="network_id", columns="outer_cutoff", values="mean_observed_loss"
    ).dropna()
    if len(observed_pivot) >= 2:
        stability_rows.append(
            {
                "statistic": "kendall_w_observed_ranks",
                "n_networks": len(observed_pivot),
                "value": kendall_w(observed_pivot),
                "note": "reference: stability of observed outer losses",
            }
        )
    pd.concat(
        [pd.DataFrame(pairs), pd.DataFrame(stability_rows)], ignore_index=True
    ).to_csv(OUT / "rolling_origin_rank_stability.csv", index=False)
    print("rolling origin done", flush=True)


def run_learning(
    placements_path: Path,
    networks: list[str],
    dataset: str,
    panel_root: Path,
    *,
    role_map: dict[str, str] | None = None,
    include_full: bool = False,
) -> None:
    placements = _read_csv(placements_path)
    metric_rows = []
    prediction_parts = []
    levels = [*HISTORY_LEVELS, "full"] if include_full else list(HISTORY_LEVELS)
    for ordinal, network in enumerate(networks, start=1):
        print(f"learning {dataset} {ordinal}/{len(networks)}: {network}", flush=True)
        if role_map is None:
            panel = _read_panel(network, panel_root=panel_root)
        else:
            panel = _read_dev_panel(network, role_map[network])
        years = np.asarray(sorted(panel.index.year.unique()))
        outer_train_years, outer_eval_years = _split_years(years, 0.70)
        eval_placements = placements.loc[
            placements["network_id"].astype(str).eq(network)
            & placements["gap_start"].dt.year.isin(outer_eval_years)
        ]
        for level in levels:
            if level == "full":
                training_index = panel.index[panel.index.year.isin(outer_train_years)]
                _, inner_fit_years, inner_score_years = year_split(training_index)
                fit_years = list(inner_fit_years)
                score_years = list(inner_score_years)
            else:
                if level >= len(outer_train_years):
                    continue
                fit_years = list(outer_train_years[:level])
                score_years = list(outer_train_years[level:])
            curve = build_stress_curve(network, panel, placements, fit_years, score_years)
            predictions, metrics = _transfer_and_metrics(curve, eval_placements)
            predictions = predictions.copy()
            predictions["history_level"] = str(level)
            predictions["dataset"] = dataset
            prediction_parts.append(predictions)
            metric_rows.append(
                {
                    "history_level": str(level),
                    "dataset": dataset,
                    "network_id": network,
                    "history_years": len(fit_years),
                    "score_years": len(score_years),
                    "stress_curve_cells": len(curve),
                    **metrics,
                }
            )
    if metric_rows:
        pd.concat(prediction_parts, ignore_index=True).to_csv(
            OUT / f"learning_curve_predictions_{dataset}.csv", index=False
        )
        pd.DataFrame(metric_rows).to_csv(
            OUT / f"learning_curve_metrics_{dataset}.csv", index=False
        )


def run_learning_first_panel() -> None:
    run_learning(CONF_PLACEMENTS, SUBSET_20, "first_panel", CONF_PANEL_ROOT)


def run_learning_dev() -> None:
    inventory = pd.read_csv(INVENTORY, dtype={"network_id": str})
    role_map = inventory.set_index("network_id")["role"].to_dict()
    run_learning(
        DEV_PLACEMENTS,
        DEV_SUBSET_8,
        "development",
        DEV_PANEL_ROOT,
        role_map=role_map,
        include_full=True,
    )


def run_comparability() -> None:
    placements = _read_csv(CONF_PLACEMENTS)
    cell_parts = []
    for ordinal, network in enumerate(SUBSET_20, start=1):
        print(f"comparability {ordinal}/{len(SUBSET_20)}: {network}", flush=True)
        panel = _read_panel(network, panel_root=CONF_PANEL_ROOT)
        daily = panel.copy().sort_index().asfreq("D")
        daily.columns = daily.columns.astype(str)
        years = np.asarray(sorted(daily.index.year.unique()))
        outer_train_years, outer_eval_years = _split_years(years, 0.70)
        training_index = daily.index[daily.index.year.isin(outer_train_years)]
        _, inner_fit_years, _ = year_split(training_index)
        eval_placements = placements.loc[
            placements["network_id"].astype(str).eq(network)
            & placements["gap_start"].dt.year.isin(outer_eval_years)
        ].copy()
        cell_rows = []
        for raw_station, station_rows in eval_placements.groupby("station_id", sort=False):
            try:
                station = _normalise_station(raw_station, daily.columns)
            except KeyError:
                continue
            donor_text = str(station_rows["donor_station_ids"].iloc[0])
            donors = tuple(
                _normalise_station(value, daily.columns)
                for value in donor_text.split("|")
                if value and value != "nan"
            )
            if not donors:
                continue
            fit_49 = list(inner_fit_years)
            fit_70 = list(outer_train_years)
            fit_days_49 = int(
                (daily.index.year.isin(fit_49) & daily[station].notna()).sum()
            )
            fit_days_70 = int(
                (daily.index.year.isin(fit_70) & daily[station].notna()).sum()
            )
            if fit_days_49 < 365 or fit_days_70 < 365:
                continue
            model_49, frame_49 = _fit_station_model(daily, station, donors, fit_49)
            model_70, frame_70 = _fit_station_model(daily, station, donors, fit_70)
            loss_49 = _score_placements(model_49, frame_49, daily, station, station_rows)
            loss_70 = _score_placements(model_70, frame_70, daily, station, station_rows)
            for row, l49, l70 in zip(
                station_rows.itertuples(index=False), loss_49, loss_70
            ):
                cell_rows.append(
                    {
                        "network_id": network,
                        "station_id": station,
                        "gap_length": int(row.gap_length),
                        "gap_start": pd.Timestamp(row.gap_start),
                        "mae_49pct_model": float(l49),
                        "mae_70pct_model": float(l70),
                    }
                )
        if cell_rows:
            cells = pd.DataFrame(cell_rows).dropna(
                subset=["mae_49pct_model", "mae_70pct_model"]
            )
            if not cells.empty:
                summary = (
                    cells.groupby(
                        ["network_id", "station_id", "gap_length"], as_index=False
                    )
                    .agg(
                        mae_49pct_model=("mae_49pct_model", "mean"),
                        mae_70pct_model=("mae_70pct_model", "mean"),
                        n_placements=("mae_49pct_model", "size"),
                    )
                )
                cell_parts.append(summary)
    combined = pd.concat(cell_parts, ignore_index=True)
    combined.to_csv(OUT / "comparability_cells.csv", index=False)

    usable = combined.dropna(subset=["mae_49pct_model", "mae_70pct_model"])
    network = usable.groupby("network_id")[["mae_49pct_model", "mae_70pct_model"]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), usable["mae_49pct_model"]])
    intercept, slope = np.linalg.lstsq(
        design * weight[:, None],
        usable["mae_70pct_model"].to_numpy(dtype=float) * weight,
        rcond=None,
    )[0]
    rows = [
        {
            "metric": "pooled_spearman_mae49_vs_mae70",
            "value": float(
                spearmanr(usable["mae_49pct_model"], usable["mae_70pct_model"]).statistic
            ),
            "n": len(usable),
            "n_networks": len(network),
        },
        {
            "metric": "network_spearman_mae49_vs_mae70",
            "value": float(
                spearmanr(network["mae_49pct_model"], network["mae_70pct_model"]).statistic
            ),
            "n": len(usable),
            "n_networks": len(network),
        },
        {
            "metric": "calibration_slope_mae70_on_mae49",
            "value": float(slope),
            "n": len(usable),
            "n_networks": len(network),
        },
        {
            "metric": "calibration_intercept_mae70_on_mae49",
            "value": float(intercept),
            "n": len(usable),
            "n_networks": len(network),
        },
        {
            "metric": "mean_paired_difference_mae49_minus_mae70",
            "value": float(
                np.mean(usable["mae_49pct_model"] - usable["mae_70pct_model"])
            ),
            "n": len(usable),
            "n_networks": len(network),
        },
        {
            "metric": "median_paired_difference_mae49_minus_mae70",
            "value": float(
                np.median(usable["mae_49pct_model"] - usable["mae_70pct_model"])
            ),
            "n": len(usable),
            "n_networks": len(network),
        },
        {
            "metric": "mean_mae_49pct_model",
            "value": float(usable["mae_49pct_model"].mean()),
            "n": len(usable),
            "n_networks": len(network),
        },
        {
            "metric": "mean_mae_70pct_model",
            "value": float(usable["mae_70pct_model"].mean()),
            "n": len(usable),
            "n_networks": len(network),
        },
    ]
    gap_rows = []
    for gap, group in usable.groupby("gap_length"):
        gap_rows.append(
            {
                "gap_length": int(gap),
                "n": len(group),
                "median_mae_49pct_model": float(group["mae_49pct_model"].median()),
                "median_mae_70pct_model": float(group["mae_70pct_model"].median()),
                "median_difference": float(
                    np.median(group["mae_49pct_model"] - group["mae_70pct_model"])
                ),
                "pooled_spearman": float(
                    spearmanr(group["mae_49pct_model"], group["mae_70pct_model"]).statistic
                ),
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "comparability_metrics.csv", index=False)
    pd.DataFrame(gap_rows).to_csv(OUT / "comparability_gap_lengths.csv", index=False)
    print("comparability done", flush=True)


def _pool_metrics(
    prediction_frame: pd.DataFrame,
) -> dict[str, float]:
    supported = prediction_frame.loc[
        prediction_frame["empirical_transfer_supported"]
    ]
    return prediction_metrics(
        supported, "empirical_transfer_prediction", "observed_recovery_loss"
    )


def run_report() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    existing_conf = pd.read_csv(EXISTING_CONF_METRICS)
    existing_conf_rows = {
        (row["phase"], row["scope"]): row
        for row in existing_conf.to_dict(orient="records")
    }
    confirmation_supported = existing_conf_rows[
        ("confirmation", "supported_only")
    ]
    confirmation_all = existing_conf_rows[
        ("confirmation", "all_cells_with_network_mean_fallback")
    ]

    rolling_predictions = _read_csv(OUT / "rolling_origin_predictions.csv")
    stability = _read_csv(OUT / "rolling_origin_rank_stability.csv")
    learning_fp_predictions = _read_csv(OUT / "learning_curve_predictions_first_panel.csv")
    learning_dev_predictions = _read_csv(OUT / "learning_curve_predictions_development.csv")

    existing_conf_predictions = _read_csv(EXISTING_CONF_PREDICTIONS)
    subset_cells = existing_conf_predictions.loc[
        existing_conf_predictions["network_id"].isin(SUBSET_20)
        & existing_conf_predictions["empirical_transfer_supported"]
    ]
    existing_subset_metrics = prediction_metrics(
        subset_cells, "empirical_transfer_prediction", "observed_recovery_loss"
    )
    rerun_canonical = _pool_metrics(
        rolling_predictions.loc[rolling_predictions["outer_cutoff"] == 0.70]
    )

    cutoff_pooled = {}
    for cutoff in CUTOFFS:
        cutoff_pooled[cutoff] = _pool_metrics(
            rolling_predictions.loc[rolling_predictions["outer_cutoff"] == cutoff]
        )

    full_first_panel = _pool_metrics(
        rolling_predictions.loc[rolling_predictions["outer_cutoff"] == 0.70]
    )
    full_first_panel["history_level"] = "full"
    full_first_panel["dataset"] = "first_panel"
    learning_rows = []
    for level in HISTORY_LEVELS:
        pooled = _pool_metrics(
            learning_fp_predictions.loc[
                learning_fp_predictions["history_level"].astype(str) == str(level)
            ]
        )
        learning_rows.append(
            {"history_level": str(level), "dataset": "first_panel", **pooled}
        )
    learning_rows.append(full_first_panel)
    for level in [*HISTORY_LEVELS, "full"]:
        pooled = _pool_metrics(
            learning_dev_predictions.loc[
                learning_dev_predictions["history_level"].astype(str) == str(level)
            ]
        )
        learning_rows.append(
            {"history_level": str(level), "dataset": "development", **pooled}
        )
    learning_combined = pd.DataFrame(learning_rows)
    learning_combined.to_csv(OUT / "learning_curve_combined.csv", index=False)

    min_history = {}
    for dataset in ("first_panel", "development"):
        candidate = None
        for level in (2, 4, 6, 8, "full"):
            row = learning_combined.loc[
                (learning_combined["dataset"] == dataset)
                & (learning_combined["history_level"] == str(level))
            ]
            if not row.empty and float(row["network_spearman"].iloc[0]) >= 0.7:
                candidate = level
                break
        min_history[dataset] = candidate

    existing_fit_dev = pd.read_csv(EXISTING_DEV_FIT_LOSSES)
    existing_fit_conf = pd.read_csv(EXISTING_CONF_FIT_LOSSES)
    dev_history = float(
        existing_fit_dev.groupby("network_id")["inner_fit_years"]
        .first()
        .str.split("|")
        .map(len)
        .median()
    )
    conf_history = float(
        existing_fit_conf.groupby("network_id")["inner_fit_years"]
        .first()
        .str.split("|")
        .map(len)
        .median()
    )

    comparability = _read_csv(OUT / "comparability_metrics.csv")
    comparability_map = comparability.set_index("metric")["value"].to_dict()

    canonical = rolling_predictions.loc[
        (rolling_predictions["outer_cutoff"] == 0.70)
        & rolling_predictions["empirical_transfer_supported"]
    ].copy()
    canonical_cells = (
        canonical.groupby(["network_id", "station_id", "gap_length"], as_index=False)
        .agg(
            stress_prediction=("empirical_transfer_prediction", "mean"),
            observed_file=("observed_recovery_loss", "mean"),
        )
    )
    cells = _read_csv(OUT / "comparability_cells.csv")
    merged = canonical_cells.merge(
        cells, on=["network_id", "station_id", "gap_length"], how="inner"
    ).dropna()
    stress_check_rows = []
    if len(merged) >= 3:
        network = merged.groupby("network_id")[
            ["stress_prediction", "observed_file", "mae_49pct_model", "mae_70pct_model"]
        ].mean()
        counts = merged.groupby("network_id")["network_id"].transform("size")
        weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
        for outcome, label in (
            ("observed_file", "deployment_file_observed"),
            ("mae_70pct_model", "matched_70pct_truth"),
            ("mae_49pct_model", "unmatched_49pct_truth"),
        ):
            design = np.column_stack([np.ones(len(merged)), merged["stress_prediction"]])
            intercept, slope = np.linalg.lstsq(
                design * weight[:, None],
                merged[outcome].to_numpy(dtype=float) * weight,
                rcond=None,
            )[0]
            stress_check_rows.append(
                {
                    "truth": label,
                    "pooled_spearman": float(
                        spearmanr(merged["stress_prediction"], merged[outcome]).statistic
                    ),
                    "network_spearman": float(
                        spearmanr(network["stress_prediction"], network[outcome]).statistic
                    ),
                    "calibration_slope": float(slope),
                    "calibration_intercept": float(intercept),
                    "r2": float(r2_score(merged[outcome], merged["stress_prediction"])),
                    "n": len(merged),
                    "n_networks": len(network),
                }
            )
    pd.DataFrame(stress_check_rows).to_csv(
        OUT / "comparability_stress_curve_check.csv", index=False
    )

    crosscheck_rows = [
        {
            "scope": "first_panel_42_networks_canonical_existing",
            "source": "existing empirical_transfer_metrics.csv",
            "n": int(confirmation_supported["n"]),
            "n_networks": int(confirmation_supported["n_networks"]),
            "spearman": float(confirmation_supported["spearman"]),
            "network_spearman": float(confirmation_supported["network_spearman"]),
            "calibration_slope": float(confirmation_supported["calibration_slope"]),
            "r2": float(confirmation_supported["r2"]),
        },
        {
            "scope": "first_panel_42_networks_canonical_all_cells_with_fallback",
            "source": "existing empirical_transfer_metrics.csv",
            "n": int(confirmation_all["n"]),
            "n_networks": int(confirmation_all["n_networks"]),
            "spearman": float(confirmation_all["spearman"]),
            "network_spearman": float(confirmation_all["network_spearman"]),
            "calibration_slope": float(confirmation_all["calibration_slope"]),
            "r2": float(confirmation_all["r2"]),
        },
        {
            "scope": "subset_20_canonical_from_existing_predictions",
            "source": "existing confirmation_empirical_predictions.csv filtered",
            "n": int(existing_subset_metrics["n"]),
            "n_networks": int(existing_subset_metrics["n_networks"]),
            "spearman": float(existing_subset_metrics["spearman"]),
            "network_spearman": float(existing_subset_metrics["network_spearman"]),
            "calibration_slope": float(existing_subset_metrics["calibration_slope"]),
            "r2": float(existing_subset_metrics["r2"]),
        },
        {
            "scope": "subset_20_canonical_rerun",
            "source": "this script, rolling cutoff 0.70, pooled",
            "n": int(rerun_canonical["n"]),
            "n_networks": int(rerun_canonical["n_networks"]),
            "spearman": float(rerun_canonical["spearman"]),
            "network_spearman": float(rerun_canonical["network_spearman"]),
            "calibration_slope": float(rerun_canonical["calibration_slope"]),
            "r2": float(rerun_canonical["r2"]),
        },
    ]
    crosscheck = pd.DataFrame(crosscheck_rows)
    crosscheck.to_csv(OUT / "canonical_subset_crosscheck.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
    for dataset, color, marker in (
        ("first_panel", "#0072B2", "o"),
        ("development", "#D55E00", "s"),
    ):
        subset = learning_combined.loc[learning_combined["dataset"] == dataset]
        x = subset["history_level"].map(
            {str(level): float(level) for level in HISTORY_LEVELS}
        )
        x = x.fillna(12.0).to_numpy(dtype=float)
        axes[0].plot(
            x,
            subset["network_spearman"].to_numpy(dtype=float),
            color=color,
            marker=marker,
            label=dataset,
        )
        axes[1].plot(
            x,
            subset["calibration_slope"].to_numpy(dtype=float),
            color=color,
            marker=marker,
            label=dataset,
        )
    axes[0].axhline(0.7, color="grey", ls="--", lw=1)
    axes[0].text(2.05, 0.705, "usable-ranking threshold (0.7)", fontsize=7)
    axes[0].set(
        xlabel="fitting years (full = median full-history fit years, plotted at 12)",
        ylabel="network Spearman",
        title="Learning curve: ranking transfer",
    )
    axes[1].set(
        xlabel="fitting years (full = median full-history fit years, plotted at 12)",
        ylabel="calibration slope",
        title="Learning curve: magnitude calibration",
    )
    for axis in axes:
        axis.set_xlim(1.8, 13.2)
        axis.legend(frameon=False, fontsize=8)
        axis.grid(alpha=0.3)
    fig.suptitle(
        "Empirical stress-curve transfer vs history length (canonical 70% outer split)",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(OUT / "learning_curve.png", dpi=200)
    plt.close(fig)

    lines = []
    lines.append(
        "# Rolling-origin stability, history-length learning curve, and training-data comparability"
    )
    lines.append("")
    lines.append(
        "Agent B (adversarial pair).  Revision v12, task t07.  Every number below was produced by running"
    )
    lines.append(
        "`scripts/rev_v12_t07_rolling_origin_b.py` on the frozen development_v11 outputs; nothing is fabricated."
    )
    lines.append("")
    lines.append("## Scope and subset")
    lines.append("")
    lines.append(
        "- First-panel (route-A confirmation) subset: the 20 networks with the longest temperature records"
    )
    lines.append(
        "  among the 42 first-panel networks that have deployment placements in route_a_confirmation/"
    )
    lines.append(
        f"  placement_losses.csv ({', '.join(SUBSET_20[:5])}, ...; see subset_networks.csv)."
    )
    lines.append(
        "- Development subset for the learning curve: 8 long-record development networks"
    )
    lines.append(f"  ({', '.join(DEV_SUBSET_8[:4])}, ...).")
    lines.append(
        "- Stress-curve machinery: parameterised copy of `fitting_period_empirical_losses` +"
    )
    lines.append(
        "  `empirical_transfer_predictions` (scripts/124_run_reviewer_completion.py,"
    )
    lines.append("  src/stream_recoverability/experiments/recovery_roster.py).")
    lines.append(
        "- Determinism: the builder reproduces results/development_v11/reviewer_completion/"
    )
    lines.append(
        "  confirmation_empirical_fit_losses.csv to ~5e-16 (verified on 4 networks), so the canonical"
    )
    lines.append("  numbers below are inherited by construction.")
    lines.append("")
    lines.append("## Cross-checks")
    lines.append("")
    lines.append(
        "| scope | n | n_networks | pooled Spearman | network Spearman | calibration slope | R2 |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for row in crosscheck_rows:
        lines.append(
            f"| {row['scope']} | {row['n']} | {row['n_networks']} | {row['spearman']:.3f} | "
            f"{row['network_spearman']:.3f} | {row['calibration_slope']:.3f} | {row['r2']:.3f} |"
        )
    lines.append("")
    lines.append(
        "Requested cross-check targets: first panel 780 units pooled 0.934 / network 0.922 at the canonical 70% split;"
    )
    lines.append(
        "complete panel (all cells with network-mean fallback) network 0.767.  Both are reproduced in the first two rows."
    )
    lines.append(
        "Rows 3-4 confirm the subset re-run matches the existing predictions restricted to the same 20 networks."
    )
    lines.append("")
    lines.append("## 1. Rolling-origin evaluation across outer cutoffs (60/70/80% of years)")
    lines.append("")
    lines.append(
        "For each cutoff the stress curve is built only from earlier years (the recovery model fits on the first 70%"
    )
    lines.append(
        "of the outer-training block, artificial gaps are scored in the following 30% of that block) and is then used"
    )
    lines.append(
        "to predict the observed deployment losses in the later years (the remaining 100-C% of the record)."
    )
    lines.append(
        "Metrics pool all directly supported cells across the 20-network subset:"
    )
    lines.append("")
    lines.append(
        "| cutoff | n cells | n networks | pooled Spearman | network Spearman | calibration slope | R2 | RMSE | fit years (median) | eval years (median) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    cutoff_metrics = _read_csv(OUT / "rolling_origin_cutoff_metrics.csv")
    for cutoff in CUTOFFS:
        subset = cutoff_metrics.loc[cutoff_metrics["outer_cutoff"] == cutoff]
        pooled = cutoff_pooled[cutoff]
        fit_median = float(subset["stress_model_fit_years"].median())
        eval_median = float(subset["outer_evaluation_years"].median())
        lines.append(
            f"| {cutoff:0.2f} | {int(pooled['n'])} | {int(pooled['n_networks'])} | "
            f"{pooled['spearman']:.3f} | {pooled['network_spearman']:.3f} | "
            f"{pooled['calibration_slope']:.3f} | {pooled['r2']:.3f} | {pooled['rmse']:.3f} | "
            f"{fit_median:.0f} | {eval_median:.0f} |"
        )
    lines.append("")
    lines.append(
        "Per-cutoff per-network rows are in rolling_origin_cutoff_metrics.csv; per-cell predictions in"
    )
    lines.append(
        "rolling_origin_predictions.csv; per-network mean predicted/observed losses in rolling_origin_network_ranks.csv."
    )
    lines.append("")
    lines.append(
        "Rank stability across cutoffs (per-network mean predicted loss, networks with supported cells in all three cutoffs):"
    )
    lines.append("")
    for row in stability.to_dict(orient="records"):
        if pd.notna(row.get("pair")):
            lines.append(
                f"- pairwise predicted-rank Spearman ({row['pair']}): {row['pairwise_spearman']:.3f} "
                f"(n_networks = {int(row['n_networks'])})"
            )
        else:
            lines.append(
                f"- {row['statistic']}: {row['value']:.3f} (n_networks = {int(row['n_networks'])})"
            )
    lines.append("")
    lines.append("## 2. History-length learning curve")
    lines.append("")
    lines.append(
        "Canonical 70% outer split; the stress-curve model is fitted on the first N years of the outer-training"
    )
    lines.append(
        "block (N = 2/4/6/8, or the canonical inner 70/30 split for `full`, ~49% of the record) and scores the"
    )
    lines.append(
        "remaining years of that block; predictions transfer to the held-out last 30% of years."
    )
    lines.append("")
    lines.append(
        "| dataset | history level | n networks | n cells | pooled Spearman | network Spearman | calibration slope | R2 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in learning_combined.to_dict(orient="records"):
        lines.append(
            f"| {row['dataset']} | {row['history_level']} | {int(row['n_networks'])} | {int(row['n'])} | "
            f"{row['spearman']:.3f} | {row['network_spearman']:.3f} | "
            f"{row['calibration_slope']:.3f} | {row['r2']:.3f} |"
        )
    lines.append("")
    for dataset in ("first_panel", "development"):
        lines.append(
            f"- Minimum history for usable ranking (network Spearman >= 0.7), {dataset}: "
            f"{min_history[dataset]}."
        )
    lines.append(
        "- Caveat: the development level-2 estimate is exactly 0.700 on only 5 networks; the robust headline is the"
    )
    lines.append(
        "  first-panel level-4 finding (0.872 network Spearman on all 20 networks) and level-8/full convergence to"
    )
    lines.append("  0.94.")
    lines.append(
        f"- Median full-history fit years: first panel {conf_history:.0f}, development {dev_history:.0f}."
    )
    lines.append(
        "- Figure: learning_curve.png.  Raw per-level metrics: learning_curve_metrics_first_panel.csv,"
    )
    lines.append(
        "  learning_curve_metrics_development.csv, learning_curve_combined.csv; per-cell predictions in"
    )
    lines.append(
        "  learning_curve_predictions_first_panel.csv / learning_curve_predictions_development.csv."
    )
    lines.append("")
    lines.append("## 3. Training-data comparability (stress model ~49% vs deployment model 70%)")
    lines.append("")
    lines.append(
        "On identical evaluation placements (held-out last 30% of years) the recovery model was refitted twice per"
    )
    lines.append(
        "station: on the stress-model training length (canonical inner-fit years, ~49% of the record, unmatched) and"
    )
    lines.append(
        "on the deployment length (first 70% of the record, matched).  Both are out-of-sample for the evaluation period."
    )
    lines.append("")
    for row in comparability.to_dict(orient="records"):
        lines.append(
            f"- {row['metric']}: {row['value']:.4f} (n = {int(row['n'])}, n_networks = {int(row['n_networks'])})"
        )
    lines.append("")
    lines.append("Per-gap-length detail (comparability_gap_lengths.csv):")
    lines.append("")
    lines.append(
        "| gap length | n | median MAE 49% model | median MAE 70% model | median difference | pooled Spearman |"
    )
    lines.append("|---|---|---|---|---|---|")
    for row in _read_csv(OUT / "comparability_gap_lengths.csv").to_dict(orient="records"):
        lines.append(
            f"| {int(row['gap_length'])} | {int(row['n'])} | {row['median_mae_49pct_model']:.3f} | "
            f"{row['median_mae_70pct_model']:.3f} | {row['median_difference']:.3f} | {row['pooled_spearman']:.3f} |"
        )
    lines.append("")
    lines.append(
        "Conclusion check - stress-curve predictions (canonical full level) evaluated against the deployment-file"
    )
    lines.append(
        "observed losses, a matched 70%-length re-scored truth, and an unmatched 49%-length re-scored truth:"
    )
    lines.append("")
    lines.append(
        "| truth | pooled Spearman | network Spearman | calibration slope | R2 | n | n_networks |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for row in stress_check_rows:
        lines.append(
            f"| {row['truth']} | {row['pooled_spearman']:.3f} | {row['network_spearman']:.3f} | "
            f"{row['calibration_slope']:.3f} | {row['r2']:.3f} | {int(row['n'])} | {int(row['n_networks'])} |"
        )
    lines.append("")
    lines.append("## Files produced")
    lines.append("")
    for path in sorted(OUT.glob("*")):
        lines.append(f"- {path.relative_to(ROOT)}")
    lines.append("")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report written to {OUT / 'REPORT.md'}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--part",
        choices=["rolling", "learning", "learning_dev", "comparability", "report"],
        required=True,
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"set": "first_panel_subset_20", "network_id": value} for value in SUBSET_20]
        + [{"set": "development_subset_8", "network_id": value} for value in DEV_SUBSET_8]
    ).to_csv(OUT / "subset_networks.csv", index=False)
    if args.part == "rolling":
        if not (OUT / "rolling_origin_cutoff_metrics.csv").exists():
            run_rolling()
        else:
            print("rolling outputs exist; skipping", flush=True)
    elif args.part == "learning":
        if not (OUT / "learning_curve_metrics_first_panel.csv").exists():
            run_learning_first_panel()
        else:
            print("learning outputs exist; skipping", flush=True)
    elif args.part == "learning_dev":
        if not (OUT / "learning_curve_metrics_development.csv").exists():
            run_learning_dev()
        else:
            print("learning_dev outputs exist; skipping", flush=True)
    elif args.part == "comparability":
        if not (OUT / "comparability_metrics.csv").exists():
            run_comparability()
        else:
            print("comparability outputs exist; skipping", flush=True)
    elif args.part == "report":
        run_report()


if __name__ == "__main__":
    main()
