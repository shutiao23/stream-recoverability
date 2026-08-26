"""T4 natural-outage scoring with empirical gap geometry.

True missing days have no labels, so they cannot be scored. This module takes
length and season from ``real_missing_blocks.csv`` and plants the same geometry
into later observed days, where donor-fill error is defined. Last-check
temperatures are not opened. Results are not confirmatory.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    empirical_information_set_conditionals,
)
from stream_recoverability.analysis.heuristic_degeneration import memory_component
from stream_recoverability.analysis.natural_outage import (
    TASK_OFFLINE,
    task_contract,
    weight_natural_suite,
)
from stream_recoverability.analysis.recoverability_spectrum import recoverability
from stream_recoverability.experiments.public_river_operator_ablation import (
    load_public_river_panels,
)
MIN_TRAIN_DAYS = 365
MIN_GAP_DAYS_WITH_DONOR = 5
MIN_LENGTH = 3
MIN_EVAL_LENGTH = 7
MAX_LENGTH = 180
MAX_OPERATOR_GAP = 90
INSANE_MAE_C = 50.0
SEASON_MONTHS = {
    "DJF": {12, 1, 2},
    "MAM": {3, 4, 5},
    "JJA": {6, 7, 8},
    "SON": {9, 10, 11},
}


def _lag_acf(values: np.ndarray, lag: int) -> float:
    if lag < 1 or len(values) <= lag:
        return float("nan")
    left = values[:-lag]
    right = values[lag:]
    valid = np.isfinite(left) & np.isfinite(right)
    if int(valid.sum()) < 3:
        return float("nan")
    if float(np.nanstd(left[valid])) == 0 or float(np.nanstd(right[valid])) == 0:
        return float("nan")
    return float(np.corrcoef(left[valid], right[valid])[0, 1])


def _gap_donor_mae(
    target: np.ndarray,
    donors: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    *,
    min_test: int = MIN_GAP_DAYS_WITH_DONOR,
) -> float:
    """Donor-regression MAE on a planted gap. Allows short natural outages."""

    if donors.size == 0 or int(train.sum()) < donors.shape[1] + 2:
        return float("nan")
    y_train = target[train]
    x_train = np.column_stack([np.ones(int(train.sum())), donors[train]])
    valid = np.isfinite(y_train) & np.isfinite(x_train).all(axis=1)
    if int(valid.sum()) < x_train.shape[1] + 1:
        return float("nan")
    coef = np.linalg.lstsq(x_train[valid], y_train[valid], rcond=None)[0]
    y_test = target[test]
    x_test = np.column_stack([np.ones(int(test.sum())), donors[test]])
    ok = np.isfinite(y_test) & np.isfinite(x_test).all(axis=1)
    if int(ok.sum()) < int(min_test):
        return float("nan")
    pred = x_test[ok] @ coef
    return float(np.mean(np.abs(pred - y_test[ok])))


def _doy_climatology(values: np.ndarray, index: pd.DatetimeIndex, train: np.ndarray) -> np.ndarray:
    doy = pd.Index(index).dayofyear.to_numpy()
    fallback = float(np.nanmean(values[train])) if int(train.sum()) else float("nan")
    climate = np.full(len(values), fallback, dtype=float)
    for day in np.unique(doy[train]):
        on_day = train & (doy == day)
        if np.isfinite(values[on_day]).any():
            climate[doy == day] = float(np.nanmean(values[on_day]))
    return climate


def load_real_missing_blocks(path: str | Path) -> pd.DataFrame:
    table = pd.read_csv(path, dtype={"site_id": str, "network_id": str})
    table["start_date"] = pd.to_datetime(table["start_date"])
    table["length_days"] = pd.to_numeric(table["length_days"], errors="coerce")
    return table


def empirical_gap_catalog(blocks: pd.DataFrame) -> pd.DataFrame:
    """Length-by-season frequencies from real missing blocks. Not scores."""

    usable = blocks.loc[
        blocks["length_days"].ge(MIN_LENGTH) & blocks["length_days"].le(MAX_LENGTH)
    ].copy()
    if usable.empty:
        return usable
    catalog = usable[["length_days", "season"]].copy()
    if "station_id" not in catalog.columns:
        catalog["station_id"] = "*"
    catalog["start_date"] = None
    catalog["suite"] = "natural_outage"
    return weight_natural_suite(catalog)


def _season_of(stamp: pd.Timestamp) -> str:
    return ("DJF", "MAM", "JJA", "SON")[(int(stamp.month) % 12) // 3]


def observed_gap_starts(
    index: pd.DatetimeIndex,
    target_ok: np.ndarray,
    donor_ok: np.ndarray,
    *,
    length: int,
    season: str,
    later_half: bool = True,
) -> np.ndarray:
    """Start indices where ``length`` consecutive days have labels and a donor."""

    n = int(len(index))
    if n < length:
        return np.array([], dtype=int)
    ok = target_ok & donor_ok
    run = np.convolve(ok.astype(int), np.ones(int(length), dtype=int), mode="valid")
    starts = np.flatnonzero(run == int(length))
    if later_half and n > 0:
        cut = index[min(n // 2, n - 1)]
        starts = np.array([item for item in starts if index[item] >= cut], dtype=int)
    months = SEASON_MONTHS.get(str(season).upper())
    if months:
        starts = np.array(
            [item for item in starts if int(index[item].month) in months],
            dtype=int,
        )
    return starts


def score_planted_gap(
    wide: pd.DataFrame,
    *,
    network_id: str,
    site_id: str,
    start_index: int,
    length: int,
    season: str,
    task: str = TASK_OFFLINE,
) -> dict[str, Any] | None:
    """Hide an observed block, fill from donors, score against the hidden truth."""

    if site_id not in wide.columns:
        return None
    values = wide.to_numpy(dtype=float)
    columns = [str(item) for item in wide.columns]
    target = columns.index(str(site_id))
    donors = [index for index in range(values.shape[1]) if index != target]
    if not donors:
        return None
    stop = int(start_index) + int(length)
    if stop > len(wide):
        return None
    in_gap = np.zeros(len(wide), dtype=bool)
    in_gap[int(start_index) : stop] = True
    target_values = values[:, target]
    donor_values = values[:, donors]
    observed = np.isfinite(target_values)
    if not bool(np.all(observed[in_gap])):
        return None
    train = observed & ~in_gap
    if int(train.sum()) < MIN_TRAIN_DAYS:
        return None
    gap_with_donor = in_gap & np.isfinite(donor_values).any(axis=1)
    if int(gap_with_donor.sum()) < MIN_GAP_DAYS_WITH_DONOR:
        return None
    contract = task_contract(task)
    include_right = bool(contract["right_boundary_allowed"])
    climate = _doy_climatology(target_values, wide.index, train)
    climate_mae = float(np.nanmean(np.abs(target_values[in_gap] - climate[in_gap])))
    fill_mae = _gap_donor_mae(target_values, donor_values, train, in_gap)
    if not np.isfinite(fill_mae) or not np.isfinite(climate_mae) or climate_mae == 0:
        return None
    if fill_mae >= INSANE_MAE_C:
        return None
    achieved = recoverability(fill_mae, climate_mae)
    acf30 = _lag_acf(target_values[train], 30)
    operator_gap = min(int(length), MAX_OPERATOR_GAP)
    try:
        conditionals = empirical_information_set_conditionals(
            values[train],
            target=target,
            donors=donors,
            gap_length=operator_gap,
            include_left_boundary=True,
            include_right_boundary=include_right,
        )
        both = conditionals["B_union_D"]
        operator_r = float(both.get("recoverability_r", float("nan")))
        predicted_skill = float(both.get("predicted_skill", float("nan")))
        predicted_risk = float(both.get("expected_mae_conditional", float("nan")))
        withheld = bool(both.get("withheld", False))
    except (np.linalg.LinAlgError, ValueError, KeyError):
        operator_r = predicted_skill = predicted_risk = float("nan")
        withheld = True
    rho = _lag_acf(target_values[train], max(1, int(round(float(length) / 4.0))))
    heuristic = float("nan")
    if np.isfinite(rho):
        heuristic = float(np.clip(memory_component(0.0, rho), 0.0, 1.0))
    start_ts = pd.Timestamp(wide.index[int(start_index)])
    return {
        "network_id": network_id,
        "station_id": str(site_id),
        "start_date": start_ts.date().isoformat(),
        "gap_length": int(length),
        "season": season or _season_of(start_ts),
        "task": task,
        "n_train_days": int(train.sum()),
        "n_gap_days_with_donor": int(gap_with_donor.sum()),
        "fill_mae": float(fill_mae),
        "climate_mae": float(climate_mae),
        "achieved_skill": float(achieved),
        "acf30": float(acf30),
        "heuristic_explained_variance": heuristic,
        "recoverability_r": operator_r,
        "predicted_skill": predicted_skill,
        "predicted_conditional_risk": predicted_risk,
        "operator_withheld": withheld,
        "right_boundary_allowed": include_right,
        "truth_source": "held_out_observed_days",
        "geometry_source": "real_missing_blocks_length_season",
        "formal_evidence": False,
    }


def evaluable_length_season_pairs(catalog: pd.DataFrame) -> pd.DataFrame:
    """Keep lengths that can be scored. Short 1–6 day holes dominate the raw catalog."""

    if catalog.empty:
        return catalog
    pairs = (
        catalog.groupby(["length_days", "season"], dropna=False)["weight"]
        .sum()
        .reset_index()
    )
    pairs = pairs.loc[pairs["length_days"].ge(MIN_EVAL_LENGTH)]
    if pairs.empty:
        return pairs
    pairs = pairs.sort_values("weight", ascending=False)
    length = pairs["length_days"].to_numpy(dtype=float)
    strata = [
        pairs.loc[(length >= 7) & (length <= 21)].head(6),
        pairs.loc[(length >= 22) & (length <= 60)].head(4),
        pairs.loc[(length >= 61) & (length <= 180)].head(4),
    ]
    stacked = [frame for frame in strata if not frame.empty]
    if not stacked:
        return pairs.head(12)
    return pd.concat(stacked, ignore_index=True).drop_duplicates(
        ["length_days", "season"]
    )


def score_natural_outages(
    panels: Mapping[str, pd.DataFrame],
    blocks: pd.DataFrame,
    *,
    task: str = TASK_OFFLINE,
    max_gaps_per_station: int = 8,
    seed: int = 0,
) -> pd.DataFrame:
    """Plant empirically weighted gaps into labeled days."""

    catalog = empirical_gap_catalog(blocks)
    if catalog.empty:
        return pd.DataFrame()
    top = evaluable_length_season_pairs(catalog)
    if top.empty:
        return pd.DataFrame()
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for network_id, wide in panels.items():
        values = wide.to_numpy(dtype=float)
        for column_i, site_id in enumerate(wide.columns):
            target_ok = np.isfinite(values[:, column_i])
            donor_ok = (
                np.isfinite(np.delete(values, column_i, axis=1)).any(axis=1)
                if values.shape[1] > 1
                else np.zeros(len(wide), dtype=bool)
            )
            n_kept = 0
            for pair in top.itertuples(index=False):
                if n_kept >= int(max_gaps_per_station):
                    break
                length = int(pair.length_days)
                season = str(pair.season)
                starts = observed_gap_starts(
                    wide.index, target_ok, donor_ok, length=length, season=season
                )
                if starts.size == 0:
                    starts = observed_gap_starts(
                        wide.index,
                        target_ok,
                        donor_ok,
                        length=length,
                        season="",
                    )
                if starts.size == 0:
                    continue
                chosen = int(rng.choice(starts))
                scored = score_planted_gap(
                    wide,
                    network_id=str(network_id),
                    site_id=str(site_id),
                    start_index=chosen,
                    length=length,
                    season=season,
                    task=task,
                )
                if scored is not None:
                    rows.append(scored)
                    n_kept += 1
    return pd.DataFrame(rows)


def natural_outage_summary(scores: pd.DataFrame) -> dict[str, Any]:
    usable = (
        scores.loc[
            np.isfinite(pd.to_numeric(scores.get("achieved_skill"), errors="coerce"))
            & np.isfinite(pd.to_numeric(scores.get("recoverability_r"), errors="coerce"))
        ]
        if scores is not None and not scores.empty
        else pd.DataFrame()
    )
    spearman = float("nan")
    if not usable.empty and int(usable["network_id"].nunique()) >= 2:
        network = usable.groupby("network_id", as_index=False)[
            ["recoverability_r", "achieved_skill"]
        ].mean(numeric_only=True)
        if len(network) >= 2:
            spearman = float(
                pd.Series(network["recoverability_r"]).corr(
                    pd.Series(network["achieved_skill"]), method="spearman"
                )
            )
    n_networks = int(usable["network_id"].nunique()) if not usable.empty else 0
    return {
        "what_this_is": (
            "Donor fills on held-out observed days whose gap length and season "
            "follow real_missing_blocks.csv."
        ),
        "what_this_is_not": (
            "Not confirmatory. Not scoring unlabeled missing days. Not a last-"
            "check opening. Not a T2 result. T4 is not passed."
        ),
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "passed": False,
        "n_gaps_scored": int(len(scores)) if scores is not None and not scores.empty else 0,
        "n_gaps_with_operator": int(len(usable)),
        "n_networks": n_networks,
        "network_spearman_r_vs_achieved_skill": spearman,
        "n_networks_min_for_confirmation": 100,
        "task": TASK_OFFLINE,
        "truth_source": "held_out_observed_days",
        "geometry_source": "real_missing_blocks_length_season",
        "unlabeled_missing_days_scored": False,
        "min_eval_length_days": MIN_EVAL_LENGTH,
        "short_holes_excluded_reason": (
            "1-6 day holes dominate real_missing_blocks but cannot support a "
            "stable donor-fill MAE; evaluable geometry starts at 7 days."
        ),
        "last_check_temperatures_used": False,
        "sealed_outcomes_opened": False,
    }


def write_natural_outage_artifacts(
    scores: pd.DataFrame,
    summary: Mapping[str, Any],
    directory: str | Path,
) -> None:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    scores.to_csv(root / "natural_outage_scores.csv", index=False)
    (root / "natural_outage_manifest.json").write_text(
        json.dumps(dict(summary), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def run_natural_outage_scoring(
    panel_dir: str | Path,
    blocks_path: str | Path,
    *,
    task: str = TASK_OFFLINE,
) -> dict[str, Any]:
    panels = load_public_river_panels(panel_dir)
    blocks = load_real_missing_blocks(blocks_path)
    scores = score_natural_outages(panels, blocks, task=task)
    summary = natural_outage_summary(scores)
    return {"scores": scores, "manifest": summary}


__all__ = [
    "empirical_gap_catalog",
    "evaluable_length_season_pairs",
    "load_real_missing_blocks",
    "natural_outage_summary",
    "observed_gap_starts",
    "run_natural_outage_scoring",
    "score_natural_outages",
    "score_planted_gap",
    "write_natural_outage_artifacts",
]
