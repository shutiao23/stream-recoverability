"""Stop-loss nested ablation of the Schur operator on downloaded public rivers.

Train-only predictors.  Later-year mode reuses full-window donor-regression
skill across gap lengths (the Phase-4 audit).  Gap-specific mode plants an
observed block of length L and scores fill MAE against hidden truth.  Neither
path is confirmatory evidence.  Clearwater is dropped when donor MAE is
physically impossible.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    empirical_information_set_conditionals,
)
from stream_recoverability.analysis.heuristic_degeneration import (
    in_sample_r2,
    memory_component,
    year_block_cv_r2,
)
from stream_recoverability.analysis.hierarchical_confirmation import (
    evaluate_success,
    network_blocked_spearman,
)
from stream_recoverability.analysis.recoverability_spectrum import recoverability
from stream_recoverability.experiments.real_river_checks import (
    donor_regression_mae,
    year_split,
)
from stream_recoverability.experiments.recoverability_baselines import incremental_fit

GAP_LENGTHS = (30, 90)
INSANE_DONOR_MAE_C = 50.0
MAINSTEM_TOKEN = "willamette_mainstem"
MIN_TRAIN_DAYS = 365
MIN_TEST_DAYS = 180
MIN_CONCURRENT_STATIONS = 2
NESTED_PREDICTORS = (
    "gap_length",
    "acf30",
    "donor_r2",
    "heuristic_explained_variance",
    "recoverability_r",
)
COMPLETE_COLUMNS = ("achieved_skill", *NESTED_PREDICTORS)
ACHIEVED_SKILL_LATER_YEAR = "later_year"
ACHIEVED_SKILL_GAP_SPECIFIC = "gap_specific"
MIN_GAP_DAYS_WITH_DONOR = 5
MIN_DONOR_TRAIN_OVERLAP_DAYS = 365
MIN_TRAIN_COMPLETE_FOR_OPERATOR = 200
W2_PURPOSE = "pipeline_verification_not_evidence"
W2_PRIMARY_NETWORKS = (
    "delaware_river_huc20",
    "willamette_river_huc17",
    "madison_river_huc10",
    "mahoning_river_huc50",
    "roanoke_river_huc30",
    "santa_fe_river_huc31",
)


def load_public_river_panels(
    directory: str | Path | Sequence[str | Path],
    *,
    skip_mainstem: bool = True,
    min_stations_per_day: int = MIN_CONCURRENT_STATIONS,
) -> dict[str, pd.DataFrame]:
    """Load already-downloaded wide CSVs. Does not download or open sealed rivers.

    First directory wins when the same ``network_id`` appears twice.
    """

    roots = (
        [Path(directory)]
        if isinstance(directory, (str, Path))
        else [Path(item) for item in directory]
    )
    panels: dict[str, pd.DataFrame] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*_daily_wide.csv")):
            if skip_mainstem and MAINSTEM_TOKEN in path.stem:
                continue
            network_id = path.name.replace("_daily_wide.csv", "")
            if network_id in panels:
                continue
            wide = pd.read_csv(path, index_col=0, parse_dates=True)
            if not isinstance(wide.index, pd.DatetimeIndex):
                wide.index = pd.to_datetime(wide.index)
            wide = wide.apply(pd.to_numeric, errors="coerce")
            if min_stations_per_day > 0:
                wide = wide.loc[wide.notna().sum(axis=1).ge(int(min_stations_per_day))]
            if wide.empty or wide.shape[1] < 2:
                continue
            panels[network_id] = wide
    return panels


def concurrent_enough_ids(
    directory: str | Path | Sequence[str | Path],
) -> set[str] | None:
    """Return overlap-complete networks if ``overlap.csv`` exists."""

    roots = (
        [Path(directory)]
        if isinstance(directory, (str, Path))
        else [Path(item) for item in directory]
    )
    found = False
    ids: set[str] = set()
    for root in roots:
        path = root / "overlap.csv"
        if not path.is_file():
            continue
        table = pd.read_csv(path)
        if "complete_enough" not in table.columns or "network_id" not in table.columns:
            continue
        found = True
        enough = table["complete_enough"].fillna(False).astype(bool)
        ids.update(table.loc[enough, "network_id"].astype(str))
    return ids if found else None


def _doy_anomalies(
    values: np.ndarray,
    index: pd.DatetimeIndex,
    train: np.ndarray,
) -> np.ndarray:
    """Subtract train-only calendar-day means. Test days use train doy means."""

    doy = pd.Index(index).dayofyear.to_numpy()
    train_mean = float(np.nanmean(values[train])) if int(train.sum()) else float("nan")
    climatology = np.full(len(values), train_mean, dtype=float)
    for day in np.unique(doy[train]):
        on_day = train & (doy == day)
        if np.isfinite(values[on_day]).any():
            climatology[doy == day] = float(np.nanmean(values[on_day]))
    return values - climatology


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


def _rho_at_distance(values: np.ndarray, distance: float) -> float:
    effective = max(1.0, float(distance))
    lower = int(np.floor(effective))
    upper = int(np.ceil(effective))
    lower_rho = _lag_acf(values, lower)
    if lower == upper:
        return lower_rho
    upper_rho = _lag_acf(values, upper)
    if not np.isfinite(lower_rho) or not np.isfinite(upper_rho):
        return float("nan")
    weight = effective - lower
    return float((1.0 - weight) * lower_rho + weight * upper_rho)


def _train_donor_r2(
    target: np.ndarray,
    donors: Sequence[np.ndarray],
    years: np.ndarray,
) -> tuple[float, str]:
    cv = year_block_cv_r2(target, donors, years)
    if np.isfinite(cv):
        return float(cv), "year_block_cv"
    return float(in_sample_r2(target, donors)), "train_in_sample"


def _gap_donor_mae(
    target: np.ndarray,
    donors: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    *,
    min_test: int = MIN_GAP_DAYS_WITH_DONOR,
) -> float:
    """Donor-regression MAE on a planted gap. Allows short planted windows."""

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


def _doy_climatology(
    values: np.ndarray,
    index: pd.DatetimeIndex,
    train: np.ndarray,
) -> np.ndarray:
    """Train-only calendar-day means, broadcast onto the full index."""

    doy = pd.Index(index).dayofyear.to_numpy()
    fallback = float(np.nanmean(values[train])) if int(train.sum()) else float("nan")
    climate = np.full(len(values), fallback, dtype=float)
    for day in np.unique(doy[train]):
        on_day = train & (doy == day)
        if np.isfinite(values[on_day]).any():
            climate[doy == day] = float(np.nanmean(values[on_day]))
    return climate


def _first_365_train_mask(train: np.ndarray) -> np.ndarray:
    """Days that belong to the first 365 train observations."""

    forbidden = np.zeros(train.shape[0], dtype=bool)
    positions = np.flatnonzero(train)
    stop = min(int(MIN_TRAIN_DAYS), int(positions.size))
    if stop:
        forbidden[positions[:stop]] = True
    return forbidden


def first_plant_start(
    target_ok: np.ndarray,
    donor_ok: np.ndarray,
    *,
    length: int,
    test: np.ndarray,
    forbidden: np.ndarray,
    min_donor_days: int = MIN_GAP_DAYS_WITH_DONOR,
) -> int | None:
    """First L-day observed run: test years first, then later non-buffer days."""

    length = int(length)
    n = int(len(target_ok))
    if n < length or length < 1:
        return None
    run = np.convolve(target_ok.astype(int), np.ones(length, dtype=int), mode="valid")
    starts = np.flatnonzero(run == int(length))

    def admissible(start: int, require_test: bool) -> bool:
        stop = int(start) + length
        if forbidden[int(start) : stop].any():
            return False
        if require_test and not bool(np.all(test[int(start) : stop])):
            return False
        if int(donor_ok[int(start) : stop].sum()) < int(min_donor_days):
            return False
        return True

    for start in starts:
        if admissible(int(start), True):
            return int(start)
    for start in starts:
        if admissible(int(start), False):
            return int(start)
    return None


def _usable_donor_indices(
    values: np.ndarray,
    target: int,
    train: np.ndarray,
    *,
    min_overlap: int = MIN_DONOR_TRAIN_OVERLAP_DAYS,
) -> list[int]:
    keep: list[int] = []
    y = values[:, int(target)]
    for donor in range(values.shape[1]):
        if int(donor) == int(target):
            continue
        overlap = int(
            (np.isfinite(y[train]) & np.isfinite(values[train, donor])).sum()
        )
        if overlap >= int(min_overlap):
            keep.append(int(donor))
    return keep


def _prune_donors_for_complete_cases(
    values: np.ndarray,
    mask: np.ndarray,
    target: int,
    donors: Sequence[int],
    *,
    min_complete: int,
) -> list[int]:
    """Drop the sparsest donor until complete-case days meet ``min_complete``."""

    kept = [int(item) for item in donors]
    floor = int(min_complete)
    while kept:
        cols = np.array([int(target), *kept], dtype=int)
        n_complete = int(np.isfinite(values[mask][:, cols]).all(axis=1).sum())
        if n_complete >= floor:
            return kept
        if len(kept) == 1:
            return kept if n_complete >= min(floor, MIN_GAP_DAYS_WITH_DONOR) else []
        sparsest = min(
            kept, key=lambda donor: int(np.isfinite(values[mask, donor]).sum())
        )
        kept.remove(sparsest)
    return []


def _operator_on_subset(
    values: np.ndarray,
    train: np.ndarray,
    target: int,
    donors: Sequence[int],
    gap_length: int,
) -> tuple[float, float, float]:
    if not donors:
        return float("nan"), float("nan"), float("nan")
    columns = [int(target), *[int(item) for item in donors]]
    series = values[train][:, columns]
    try:
        conditionals = empirical_information_set_conditionals(
            series,
            target=0,
            donors=list(range(1, len(columns))),
            gap_length=int(gap_length),
        )
        both = conditionals["B_union_D"]
        return (
            float(both.get("recoverability_r", float("nan"))),
            float(both.get("predicted_skill", float("nan"))),
            float(both.get("expected_mae_conditional", float("nan"))),
        )
    except (np.linalg.LinAlgError, ValueError, KeyError):
        return float("nan"), float("nan"), float("nan")


def _heuristic_explained(
    donor_r2: float,
    anomalies_train: np.ndarray,
    gap_length: int,
) -> float:
    rho = _rho_at_distance(anomalies_train, float(gap_length) / 4.0)
    if np.isfinite(donor_r2) and np.isfinite(rho):
        return float(
            np.clip(
                donor_r2
                + memory_component(float(np.clip(donor_r2, 0.0, 1.0)), rho),
                0.0,
                1.0,
            )
        )
    return float("nan")


def _later_year_station_rows(
    name: str,
    wide: pd.DataFrame,
    values: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    years: np.ndarray,
    gap_lengths: Sequence[int],
) -> list[dict[str, float | str | bool]]:
    rows: list[dict[str, float | str | bool]] = []
    for target in range(values.shape[1]):
        donors = [index for index in range(values.shape[1]) if index != target]
        if not donors:
            continue
        target_values = values[:, target]
        donor_values = values[:, donors]
        train_target = target_values[train]
        test_target = target_values[test]
        if not np.isfinite(train_target).any() or not np.isfinite(test_target).any():
            continue
        climate_mae = float(
            np.nanmean(np.abs(test_target - float(np.nanmean(train_target))))
        )
        donor_mae = donor_regression_mae(target_values, donor_values, train, test)
        if not np.isfinite(climate_mae) or climate_mae == 0 or not np.isfinite(donor_mae):
            continue
        achieved = recoverability(donor_mae, climate_mae)
        anomalies = _doy_anomalies(target_values, wide.index, train)
        donor_anomalies = [
            _doy_anomalies(values[:, donor], wide.index, train) for donor in donors
        ]
        acf30 = _lag_acf(anomalies[train], 30)
        donor_r2, donor_r2_estimator = _train_donor_r2(
            anomalies[train],
            [item[train] for item in donor_anomalies],
            years[train],
        )
        for gap_length in gap_lengths:
            heuristic = _heuristic_explained(donor_r2, anomalies[train], int(gap_length))
            try:
                conditionals = empirical_information_set_conditionals(
                    values[train],
                    target=target,
                    donors=donors,
                    gap_length=int(gap_length),
                )
                both = conditionals["B_union_D"]
                operator_r = float(both.get("recoverability_r", float("nan")))
                predicted_skill = float(both.get("predicted_skill", float("nan")))
                predicted_risk = float(both.get("expected_mae_conditional", float("nan")))
            except (np.linalg.LinAlgError, ValueError, KeyError):
                operator_r = predicted_skill = predicted_risk = float("nan")
            rows.append(
                {
                    "network_id": name,
                    "station_id": str(wide.columns[target]),
                    "gap_length": int(gap_length),
                    "acf30": float(acf30),
                    "donor_r2": float(donor_r2),
                    "donor_r2_estimator": donor_r2_estimator,
                    "heuristic_explained_variance": heuristic,
                    "recoverability_r": operator_r,
                    "predicted_skill": predicted_skill,
                    "predicted_conditional_risk": predicted_risk,
                    "donor_mae": float(donor_mae),
                    "climate_mae": climate_mae,
                    "observed_recovery_loss": float(donor_mae),
                    "achieved_skill": float(achieved),
                    "achieved_skill_mode": ACHIEVED_SKILL_LATER_YEAR,
                    "reason": "",
                }
            )
    return rows


def _gap_specific_station_rows(
    name: str,
    wide: pd.DataFrame,
    values: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
    years: np.ndarray,
    gap_lengths: Sequence[int],
) -> list[dict[str, float | str | bool]]:
    rows: list[dict[str, float | str | bool]] = []
    forbidden = _first_365_train_mask(train)
    for target in range(values.shape[1]):
        target_values = values[:, target]
        if not np.isfinite(target_values[train]).any():
            continue
        usable = _usable_donor_indices(values, target, train)
        usable = _prune_donors_for_complete_cases(
            values,
            train,
            target,
            usable,
            min_complete=MIN_TRAIN_COMPLETE_FOR_OPERATOR,
        )
        if not usable:
            continue
        target_ok = np.isfinite(target_values)
        donor_ok = np.isfinite(values[:, usable]).any(axis=1)
        for gap_length in gap_lengths:
            start = first_plant_start(
                target_ok,
                donor_ok,
                length=int(gap_length),
                test=test,
                forbidden=forbidden,
            )
            if start is None:
                continue
            stop = int(start) + int(gap_length)
            in_gap = np.zeros(len(wide), dtype=bool)
            in_gap[int(start) : stop] = True
            fill_train = train & ~in_gap
            if int(fill_train.sum()) < MIN_TRAIN_DAYS:
                continue
            fill_donors = [
                donor
                for donor in usable
                if int(np.isfinite(values[in_gap, donor]).sum()) >= 1
            ]
            fill_donors = _prune_donors_for_complete_cases(
                values,
                in_gap,
                target,
                fill_donors,
                min_complete=MIN_GAP_DAYS_WITH_DONOR,
            )
            if not fill_donors:
                continue
            fill_mae = _gap_donor_mae(
                target_values,
                values[:, fill_donors],
                fill_train,
                in_gap,
            )
            climate = _doy_climatology(target_values, wide.index, fill_train)
            climate_mae = float(
                np.nanmean(np.abs(target_values[in_gap] - climate[in_gap]))
            )
            if (
                not np.isfinite(fill_mae)
                or not np.isfinite(climate_mae)
                or climate_mae == 0
            ):
                continue
            achieved = recoverability(fill_mae, climate_mae)
            anomalies = _doy_anomalies(target_values, wide.index, fill_train)
            donor_anomalies = [
                _doy_anomalies(values[:, donor], wide.index, fill_train)
                for donor in usable
            ]
            acf30 = _lag_acf(anomalies[fill_train], 30)
            donor_r2, donor_r2_estimator = _train_donor_r2(
                anomalies[fill_train],
                [item[fill_train] for item in donor_anomalies],
                years[fill_train],
            )
            heuristic = _heuristic_explained(
                donor_r2, anomalies[fill_train], int(gap_length)
            )
            operator_r, predicted_skill, predicted_risk = _operator_on_subset(
                values, fill_train, target, usable, int(gap_length)
            )
            n_gap_with_donor = int((in_gap & donor_ok).sum())
            rows.append(
                {
                    "network_id": name,
                    "station_id": str(wide.columns[target]),
                    "gap_length": int(gap_length),
                    "plant_start": pd.Timestamp(wide.index[int(start)]).date().isoformat(),
                    "acf30": float(acf30),
                    "donor_r2": float(donor_r2),
                    "donor_r2_estimator": donor_r2_estimator,
                    "heuristic_explained_variance": heuristic,
                    "recoverability_r": operator_r,
                    "predicted_skill": predicted_skill,
                    "predicted_conditional_risk": predicted_risk,
                    "donor_mae": float(fill_mae),
                    "fill_mae": float(fill_mae),
                    "climate_mae": climate_mae,
                    "observed_recovery_loss": float(fill_mae),
                    "achieved_skill": float(achieved),
                    "achieved_skill_mode": ACHIEVED_SKILL_GAP_SPECIFIC,
                    "n_gap_days_with_donor": n_gap_with_donor,
                    "n_fill_donors": int(len(fill_donors)),
                    "reason": "",
                }
            )
    return rows


def station_operator_rows(
    name: str,
    wide: pd.DataFrame,
    *,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
    achieved_skill_mode: str = ACHIEVED_SKILL_LATER_YEAR,
) -> list[dict[str, float | str | bool]]:
    """Train-only predictors and achieved skill for one river.

    ``later_year`` copies full-window donor-regression skill across gap lengths.
    ``gap_specific`` plants an observed length-L block and scores fill MAE.
    """

    if not isinstance(wide.index, pd.DatetimeIndex):
        raise TypeError("wide frame must be indexed by date")
    mode = str(achieved_skill_mode)
    if mode not in {ACHIEVED_SKILL_LATER_YEAR, ACHIEVED_SKILL_GAP_SPECIFIC}:
        raise ValueError(f"unknown achieved_skill_mode: {achieved_skill_mode!r}")
    values = wide.to_numpy(dtype=float)
    train, test = year_split(wide.index)
    need_test = MIN_TEST_DAYS if mode == ACHIEVED_SKILL_LATER_YEAR else 0
    if int(train.sum()) < MIN_TRAIN_DAYS or int(test.sum()) < need_test:
        return [
            {
                "network_id": name,
                "reason": "not_enough_years_after_split",
                "donor_mae": float("nan"),
                "achieved_skill": float("nan"),
            }
        ]
    years = wide.index.year.to_numpy()
    if mode == ACHIEVED_SKILL_GAP_SPECIFIC:
        rows = _gap_specific_station_rows(
            name, wide, values, train, test, years, gap_lengths
        )
    else:
        rows = _later_year_station_rows(
            name, wide, values, train, test, years, gap_lengths
        )
    if not rows:
        return [
            {
                "network_id": name,
                "reason": "could_not_score_any_station",
                "donor_mae": float("nan"),
                "achieved_skill": float("nan"),
            }
        ]
    return rows


def score_operator_ablation(
    panels: Mapping[str, pd.DataFrame],
    *,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
    achieved_skill_mode: str = ACHIEVED_SKILL_LATER_YEAR,
) -> pd.DataFrame:
    rows: list[dict[str, float | str | bool]] = []
    for name, wide in panels.items():
        rows.extend(
            station_operator_rows(
                name,
                wide,
                gap_lengths=gap_lengths,
                achieved_skill_mode=achieved_skill_mode,
            )
        )
    return pd.DataFrame(rows)


def drop_insane_mae_networks(
    scores: pd.DataFrame,
    *,
    threshold: float = INSANE_DONOR_MAE_C,
) -> tuple[pd.DataFrame, list[str], dict[str, float]]:
    """Drop whole networks whose donor MAE is physically impossible."""

    if scores.empty or "donor_mae" not in scores.columns:
        return scores.copy(), [], {}
    usable = scores.loc[np.isfinite(pd.to_numeric(scores["donor_mae"], errors="coerce"))]
    dropped: list[str] = []
    maxima: dict[str, float] = {}
    for network_id, group in usable.groupby("network_id"):
        maximum = float(pd.to_numeric(group["donor_mae"], errors="coerce").max())
        maxima[str(network_id)] = maximum
        if np.isfinite(maximum) and maximum >= float(threshold):
            dropped.append(str(network_id))
    kept = scores.loc[~scores["network_id"].astype(str).isin(dropped)].copy()
    return kept, dropped, maxima


def complete_predictor_rows(scores: pd.DataFrame) -> pd.DataFrame:
    missing = [name for name in COMPLETE_COLUMNS if name not in scores.columns]
    if missing or scores.empty:
        return pd.DataFrame(columns=list(COMPLETE_COLUMNS) + ["network_id"])
    numeric = scores.copy()
    for name in COMPLETE_COLUMNS:
        numeric[name] = pd.to_numeric(numeric[name], errors="coerce")
    return numeric.loc[np.isfinite(numeric[list(COMPLETE_COLUMNS)]).all(axis=1)].copy()


def nested_ablation_table(
    scores: pd.DataFrame,
    *,
    level: str = "station",
    scope: str = "primary",
) -> pd.DataFrame:
    """Nested OLS of achieved skill. Complete-case so ΔR² steps share rows."""

    frame = complete_predictor_rows(scores)
    if frame.empty:
        return pd.DataFrame(
            columns=["scope", "level", "model", "added", "r2", "delta_r2"]
        )
    if level == "network":
        keys = [name for name in ("network_id", "gap_length") if name in frame.columns]
        value_cols = [name for name in COMPLETE_COLUMNS if name not in keys]
        frame = frame.groupby(keys, sort=False, as_index=False)[value_cols].mean()
    nested = incremental_fit(
        frame,
        outcome="achieved_skill",
        predictors=NESTED_PREDICTORS,
    )
    for column in ("r2", "delta_r2"):
        values = pd.to_numeric(nested[column], errors="coerce")
        nested[column] = values.mask(values.abs().lt(1e-12), 0.0)
    nested.insert(0, "level", level)
    nested.insert(0, "scope", scope)
    return nested


def network_comparison_table(
    scores: pd.DataFrame,
    *,
    operator_spearman: float,
    donor_spearman: float,
) -> pd.DataFrame:
    frame = complete_predictor_rows(scores)
    if frame.empty:
        return pd.DataFrame()
    grouped = (
        frame.groupby("network_id", sort=False)[
            [
                "achieved_skill",
                "recoverability_r",
                "donor_r2",
                "acf30",
                "heuristic_explained_variance",
                "donor_mae",
            ]
        ]
        .mean()
        .reset_index()
    )
    counts = frame.groupby("network_id", sort=False).size().rename("n_station_gap_rows")
    grouped = grouped.merge(counts, on="network_id", how="left")
    grouped["spearman_operator_r_vs_achieved_skill"] = float(operator_spearman)
    grouped["spearman_donor_r2_vs_achieved_skill"] = float(donor_spearman)
    return grouped


def _blocked_spearman(frame: pd.DataFrame, predicted: str, observed: str) -> float:
    if frame.empty or predicted not in frame.columns or observed not in frame.columns:
        return float("nan")
    result = network_blocked_spearman(
        frame,
        predicted=predicted,
        observed=observed,
        network="network_id",
    )
    return float(result.get("spearman", float("nan")))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return value.replace({np.nan: None}).to_dict(orient="records")
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    return value


def _nested_delta(nested: pd.DataFrame, added: str) -> float:
    if nested.empty or "added" not in nested.columns:
        return float("nan")
    match = nested.loc[nested["added"].eq(added), "delta_r2"]
    if match.empty:
        return float("nan")
    return float(match.iloc[0])


def _rows_for_gap(scores: pd.DataFrame, gap_length: int) -> pd.DataFrame:
    if scores.empty or "gap_length" not in scores.columns:
        return scores.copy()
    gaps = pd.to_numeric(scores["gap_length"], errors="coerce")
    return scores.loc[gaps.eq(float(gap_length))].copy()


def _primary_gap(gap_lengths: Sequence[int]) -> int:
    lengths = [int(item) for item in gap_lengths]
    return 30 if 30 in lengths else lengths[0]


def _scored_gap_rows_differ(scores: pd.DataFrame) -> bool:
    """True when achieved skill is not copied across gap lengths."""

    if scores.empty or "gap_length" not in scores.columns:
        return False
    usable = scores.loc[
        np.isfinite(pd.to_numeric(scores["achieved_skill"], errors="coerce"))
    ].copy()
    if usable.empty:
        return False
    usable["gap_length"] = pd.to_numeric(usable["gap_length"], errors="coerce")
    lengths = sorted(usable["gap_length"].dropna().unique().tolist())
    if len(lengths) < 2:
        return False
    keys = [name for name in ("network_id", "station_id") if name in usable.columns]
    if keys:
        pivot = usable.pivot_table(
            index=keys,
            columns="gap_length",
            values="achieved_skill",
            aggfunc="first",
        )
        if pivot.shape[1] >= 2:
            left = pd.to_numeric(pivot.iloc[:, 0], errors="coerce")
            right = pd.to_numeric(pivot.iloc[:, 1], errors="coerce")
            both = np.isfinite(left.to_numpy()) & np.isfinite(right.to_numpy())
            if int(both.sum()) and not np.allclose(
                left.to_numpy()[both], right.to_numpy()[both]
            ):
                return True
    first = []
    for length in lengths[:2]:
        block = usable.loc[usable["gap_length"].eq(length)]
        if block.empty:
            return False
        first.append(float(block["achieved_skill"].iloc[0]))
    return bool(first[0] != first[1])


def _later_year_evaluate_success_summary(complete: pd.DataFrame) -> dict[str, Any]:
    n_complete_networks = (
        int(complete["network_id"].nunique()) if not complete.empty else 0
    )
    if n_complete_networks >= 3:
        confirmation = evaluate_success(
            complete,
            predicted="predicted_conditional_risk",
            observed="observed_recovery_loss",
        )
        return {
            "passed": bool(confirmation.get("passed", False)),
            "passed_numeric_floors": bool(confirmation.get("passed_numeric_floors", False)),
            "confirmatory_eligible": bool(confirmation.get("confirmatory_eligible", False)),
            "n_networks_min": int(confirmation.get("n_networks_min", 100)),
            "thresholds_locked": bool(confirmation.get("thresholds_locked", True)),
        }
    return {
        "passed": False,
        "passed_numeric_floors": False,
        "confirmatory_eligible": False,
        "n_networks_min": 100,
        "thresholds_locked": True,
    }


def _gap_specific_evaluate_success_summary(complete: pd.DataFrame) -> dict[str, Any]:
    """evaluate_success stays failed; network CIs are withheld, not tested."""

    n_complete_networks = (
        int(complete["network_id"].nunique()) if not complete.empty else 0
    )
    status = "withheld_n_lt_100_network_interval"
    if n_complete_networks >= 3:
        confirmation = evaluate_success(
            complete,
            predicted="predicted_conditional_risk",
            observed="observed_recovery_loss",
        )
        spearman = confirmation.get("spearman") or {}
        status = str(
            spearman.get("inference_status") or "withheld_n_lt_100_network_interval"
        )
        floors = bool(confirmation.get("passed_numeric_floors", False))
        locked = bool(confirmation.get("thresholds_locked", True))
        n_min = int(confirmation.get("n_networks_min", 100))
    else:
        floors = False
        locked = True
        n_min = 100
    if status == "tested":
        status = "withheld_n_lt_100_network_interval"
    return {
        "passed": False,
        "passed_numeric_floors": floors,
        "confirmatory_eligible": False,
        "n_networks_min": n_min,
        "thresholds_locked": locked,
        "spearman_inference_status": status,
    }


def run_public_river_operator_ablation(
    panels: Mapping[str, pd.DataFrame],
    *,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
    insane_mae_c: float = INSANE_DONOR_MAE_C,
    primary_networks: Sequence[str] | None = None,
    achieved_skill_mode: str = ACHIEVED_SKILL_LATER_YEAR,
) -> dict[str, Any]:
    """Score downloaded rivers and nest the four baselines plus the operator."""

    mode = str(achieved_skill_mode)
    if mode not in {ACHIEVED_SKILL_LATER_YEAR, ACHIEVED_SKILL_GAP_SPECIFIC}:
        raise ValueError(f"unknown achieved_skill_mode: {achieved_skill_mode!r}")
    gap_specific = mode == ACHIEVED_SKILL_GAP_SPECIFIC
    scores = score_operator_ablation(
        panels, gap_lengths=gap_lengths, achieved_skill_mode=mode
    )
    kept, dropped, mae_maxima = drop_insane_mae_networks(
        scores, threshold=insane_mae_c
    )
    scored = kept.loc[
        np.isfinite(pd.to_numeric(kept.get("achieved_skill", pd.Series(dtype=float)), errors="coerce"))
    ].copy()
    available = set(scored["network_id"].astype(str)) if not scored.empty else set()
    requested = [str(item) for item in primary_networks] if primary_networks is not None else []
    if primary_networks is None:
        primary_ids = available
    else:
        primary_ids = available.intersection(str(item) for item in primary_networks)
    primary = scored.loc[scored["network_id"].astype(str).isin(primary_ids)].copy()
    primary_gap = _primary_gap(gap_lengths)
    nested_parts: list[pd.DataFrame] = []
    spearman_by_gap: dict[str, dict[str, float]] = {}
    for gap in gap_lengths:
        gap_rows = _rows_for_gap(primary, int(gap))
        scope = f"gap_{int(gap)}"
        nested_parts.append(nested_ablation_table(gap_rows, level="station", scope=scope))
        nested_parts.append(nested_ablation_table(gap_rows, level="network", scope=scope))
        gap_complete = complete_predictor_rows(gap_rows)
        spearman_by_gap[scope] = {
            "spearman_operator_r_vs_achieved_skill": _blocked_spearman(
                gap_complete, "recoverability_r", "achieved_skill"
            ),
            "spearman_donor_r2_vs_achieved_skill": _blocked_spearman(
                gap_complete, "donor_r2", "achieved_skill"
            ),
        }
    if gap_specific:
        nested_parts.append(
            nested_ablation_table(primary, level="station", scope="pooled_gaps")
        )
        nested_parts.append(
            nested_ablation_table(primary, level="network", scope="pooled_gaps")
        )
        pooled_complete = complete_predictor_rows(primary)
        spearman_by_gap["pooled_gaps"] = {
            "spearman_operator_r_vs_achieved_skill": _blocked_spearman(
                pooled_complete, "recoverability_r", "achieved_skill"
            ),
            "spearman_donor_r2_vs_achieved_skill": _blocked_spearman(
                pooled_complete, "donor_r2", "achieved_skill"
            ),
        }
    nested = (
        pd.concat(nested_parts, ignore_index=True)
        if nested_parts
        else pd.DataFrame(columns=["scope", "level", "model", "added", "r2", "delta_r2"])
    )
    pipeline_scope = "pooled_gaps" if gap_specific else f"gap_{primary_gap}"
    pipeline_rows = primary if gap_specific else _rows_for_gap(primary, primary_gap)
    complete = complete_predictor_rows(pipeline_rows)
    operator_spearman = float(
        spearman_by_gap.get(pipeline_scope, {}).get(
            "spearman_operator_r_vs_achieved_skill", float("nan")
        )
    )
    donor_spearman = float(
        spearman_by_gap.get(pipeline_scope, {}).get(
            "spearman_donor_r2_vs_achieved_skill", float("nan")
        )
    )
    comparison = network_comparison_table(
        pipeline_rows,
        operator_spearman=operator_spearman,
        donor_spearman=donor_spearman,
    )
    station_nested = nested.loc[
        nested["scope"].eq(pipeline_scope) & nested["level"].eq("station")
    ]
    operator_delta = _nested_delta(station_nested, "recoverability_r")
    gap_length_delta = _nested_delta(station_nested, "gap_length")
    if operator_delta <= 0 or not np.isfinite(operator_delta):
        incremental_note = (
            "operator incremental R2 is <= 0 or undefined; written honestly; not tuned"
        )
    else:
        incremental_note = "operator incremental R2 is positive on this pilot; not confirmatory"
    if gap_specific:
        confirmation_summary = _gap_specific_evaluate_success_summary(complete)
    else:
        confirmation_summary = _later_year_evaluate_success_summary(complete)
    n_networks = int(complete["network_id"].nunique()) if not complete.empty else 0
    missing_requested = sorted(set(requested) - set(primary_ids))
    estimator = (
        str(complete["donor_r2_estimator"].mode().iloc[0])
        if not complete.empty and "donor_r2_estimator" in complete.columns
        else "year_block_cv"
    )
    if gap_specific:
        what = (
            "W2 Phase-4 pipeline verification on already-downloaded public rivers. "
            "Train-only predictors; gap-specific planted-gap donor-fill skill."
        )
        nested_grids = (
            "per-gap diagnostics plus pooled_gaps so gap_length varies "
            "on the pipeline table"
        )
    else:
        what = (
            "Nested ablation on already-downloaded public rivers. "
            "Train-only predictors; later-year donor-regression skill versus train climatology."
        )
        nested_grids = "separate per gap so later-year skill is not duplicated"
    manifest = {
        "what_this_is": what,
        "what_this_is_not": (
            "Not confirmatory. Not formal evidence. Not a headline claim. "
            "Does not replace leave_one_river_out.csv."
        ),
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "thresholds_locked": True,
        "evaluate_success": confirmation_summary,
        "n_networks": n_networks,
        "n_networks_attempted": int(len(panels)),
        "n_station_rows_primary_gap": int(
            len(complete_predictor_rows(_rows_for_gap(primary, primary_gap)))
        ),
        "primary_gap_length": int(primary_gap),
        "primary_networks": sorted(primary_ids),
        "requested_primary_networks": requested,
        "requested_primary_missing": missing_requested,
        "delaware_scored": "delaware_river_huc20" in available,
        "scored_networks": sorted(available),
        "spearman_by_gap": spearman_by_gap,
        "achieved_skill_mode": mode,
        "achieved_skill_is_later_year_not_gap_specific": not gap_specific,
        "achieved_skill_is_gap_specific": gap_specific,
        "nested_grids": nested_grids,
        "clearwater_dropped": "clearwater_river_huc17" in dropped,
        "dropped_insane_mae_networks": dropped,
        "insane_donor_mae_threshold_c": float(insane_mae_c),
        "max_donor_mae_by_network": mae_maxima,
        "gap_lengths": [int(item) for item in gap_lengths],
        "donor_r2_estimator": estimator,
        "donor_r2_estimator_note": (
            "Year-block CV on train years when at least two train years exist; "
            "otherwise train in-sample. Labeled per station."
        ),
        "nested_predictors": list(NESTED_PREDICTORS),
        "spearman_operator_r_vs_achieved_skill": operator_spearman,
        "spearman_donor_r2_vs_achieved_skill": donor_spearman,
        "operator_incremental_r2_station": operator_delta,
        "operator_incremental_r2_le_0": bool(
            np.isfinite(operator_delta) and operator_delta <= 0
        ),
        "incremental_note": incremental_note,
        "sealed_outcomes_opened": False,
        "jinsha_outcomes_used": False,
        "chattahoochee_outcomes_used": False,
        "new_temperatures_downloaded": False,
    }
    if gap_specific:
        manifest.update(
            {
                "passed": False,
                "purpose": W2_PURPOSE,
                "pipeline_gap_length_delta_r2": gap_length_delta,
                "pipeline_gap_length_delta_r2_nonzero": bool(
                    np.isfinite(gap_length_delta) and abs(float(gap_length_delta)) > 0
                ),
                "pipeline_gap_rows_differ": bool(_scored_gap_rows_differ(primary)),
                "n_station_gap_rows_pooled": int(len(complete)),
            }
        )
    return {
        "scores": scores,
        "kept": kept,
        "primary": primary,
        "complete": complete,
        "nested": nested,
        "comparison": comparison,
        "manifest": manifest,
        "operator_spearman": operator_spearman,
        "donor_spearman": donor_spearman,
    }


def write_operator_ablation_artifacts(
    result: Mapping[str, Any],
    output_dir: str | Path,
    *,
    include_station_scores: bool = False,
) -> dict[str, Path]:
    """Write the public-river ablation filenames. Never writes leave_one_river_out.csv."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    nested_path = root / "operator_nested_ablation.csv"
    comparison_path = root / "operator_vs_univariate_network.csv"
    manifest_path = root / "operator_ablation_manifest.json"
    nested = result["nested"]
    comparison = result["comparison"]
    if isinstance(nested, pd.DataFrame) and not nested.empty:
        nested.to_csv(nested_path, index=False)
    else:
        pd.DataFrame(
            columns=["scope", "level", "model", "added", "r2", "delta_r2"]
        ).to_csv(nested_path, index=False)
    if isinstance(comparison, pd.DataFrame) and not comparison.empty:
        comparison.to_csv(comparison_path, index=False)
    else:
        pd.DataFrame().to_csv(comparison_path, index=False)
    manifest_path.write_text(
        json.dumps(_jsonable(result["manifest"]), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths = {
        "nested": nested_path,
        "comparison": comparison_path,
        "manifest": manifest_path,
    }
    if include_station_scores:
        scores_path = root / "operator_station_scores.csv"
        scores = result.get("scores")
        if isinstance(scores, pd.DataFrame) and not scores.empty:
            scores.to_csv(scores_path, index=False)
        else:
            pd.DataFrame().to_csv(scores_path, index=False)
        paths["scores"] = scores_path
    return paths


__all__ = [
    "ACHIEVED_SKILL_GAP_SPECIFIC",
    "ACHIEVED_SKILL_LATER_YEAR",
    "GAP_LENGTHS",
    "INSANE_DONOR_MAE_C",
    "NESTED_PREDICTORS",
    "W2_PRIMARY_NETWORKS",
    "W2_PURPOSE",
    "complete_predictor_rows",
    "concurrent_enough_ids",
    "drop_insane_mae_networks",
    "first_plant_start",
    "load_public_river_panels",
    "nested_ablation_table",
    "run_public_river_operator_ablation",
    "score_operator_ablation",
    "station_operator_rows",
    "write_operator_ablation_artifacts",
]
