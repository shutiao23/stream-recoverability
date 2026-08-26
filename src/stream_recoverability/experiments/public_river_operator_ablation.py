"""Stop-loss nested ablation of the Schur operator on downloaded public rivers.

Train-only predictors; later-year achieved donor-regression skill.  This is a
development stop-loss, not confirmatory evidence.  Clearwater is dropped when
donor MAE is physically impossible.
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


def station_operator_rows(
    name: str,
    wide: pd.DataFrame,
    *,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
) -> list[dict[str, float | str | bool]]:
    """Train-only predictors and later-year achieved skill for one river."""

    if not isinstance(wide.index, pd.DatetimeIndex):
        raise TypeError("wide frame must be indexed by date")
    values = wide.to_numpy(dtype=float)
    train, test = year_split(wide.index)
    if int(train.sum()) < MIN_TRAIN_DAYS or int(test.sum()) < MIN_TEST_DAYS:
        return [
            {
                "network_id": name,
                "reason": "not_enough_years_after_split",
                "donor_mae": float("nan"),
                "achieved_skill": float("nan"),
            }
        ]
    years = wide.index.year.to_numpy()
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
            rho = _rho_at_distance(anomalies[train], float(gap_length) / 4.0)
            if np.isfinite(donor_r2) and np.isfinite(rho):
                heuristic = float(
                    np.clip(donor_r2 + memory_component(float(np.clip(donor_r2, 0.0, 1.0)), rho), 0.0, 1.0)
                )
            else:
                heuristic = float("nan")
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
                    "reason": "",
                }
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
) -> pd.DataFrame:
    rows: list[dict[str, float | str | bool]] = []
    for name, wide in panels.items():
        rows.extend(station_operator_rows(name, wide, gap_lengths=gap_lengths))
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


def run_public_river_operator_ablation(
    panels: Mapping[str, pd.DataFrame],
    *,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
    insane_mae_c: float = INSANE_DONOR_MAE_C,
    primary_networks: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Score downloaded rivers and nest the four baselines plus the operator."""

    scores = score_operator_ablation(panels, gap_lengths=gap_lengths)
    kept, dropped, mae_maxima = drop_insane_mae_networks(
        scores, threshold=insane_mae_c
    )
    scored = kept.loc[
        np.isfinite(pd.to_numeric(kept.get("achieved_skill", pd.Series(dtype=float)), errors="coerce"))
    ].copy()
    available = set(scored["network_id"].astype(str)) if not scored.empty else set()
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
    nested = (
        pd.concat(nested_parts, ignore_index=True)
        if nested_parts
        else pd.DataFrame(columns=["scope", "level", "model", "added", "r2", "delta_r2"])
    )
    primary_scope = f"gap_{primary_gap}"
    primary_rows = _rows_for_gap(primary, primary_gap)
    complete = complete_predictor_rows(primary_rows)
    operator_spearman = float(
        spearman_by_gap.get(primary_scope, {}).get(
            "spearman_operator_r_vs_achieved_skill", float("nan")
        )
    )
    donor_spearman = float(
        spearman_by_gap.get(primary_scope, {}).get(
            "spearman_donor_r2_vs_achieved_skill", float("nan")
        )
    )
    comparison = network_comparison_table(
        primary_rows,
        operator_spearman=operator_spearman,
        donor_spearman=donor_spearman,
    )
    station_nested = nested.loc[
        nested["scope"].eq(primary_scope) & nested["level"].eq("station")
    ]
    operator_delta = _nested_delta(station_nested, "recoverability_r")
    if operator_delta <= 0 or not np.isfinite(operator_delta):
        incremental_note = (
            "operator incremental R2 is <= 0 or undefined; written honestly; not tuned"
        )
    else:
        incremental_note = "operator incremental R2 is positive on this pilot; not confirmatory"
    n_complete_networks = (
        int(complete["network_id"].nunique()) if not complete.empty else 0
    )
    requested = [str(item) for item in primary_networks] if primary_networks is not None else []
    missing_requested = sorted(set(requested) - set(primary_ids))
    if n_complete_networks >= 3:
        confirmation = evaluate_success(
            complete,
            predicted="predicted_conditional_risk",
            observed="observed_recovery_loss",
        )
    else:
        confirmation = {
            "passed": False,
            "passed_numeric_floors": False,
            "confirmatory_eligible": False,
            "n_networks_min": 100,
            "thresholds_locked": True,
            "reason": (
                "no_complete_predictor_rows"
                if complete.empty
                else "fewer_than_three_networks_for_evaluate_success"
            ),
        }
    confirmation_summary = {
        "passed": bool(confirmation.get("passed", False)),
        "passed_numeric_floors": bool(confirmation.get("passed_numeric_floors", False)),
        "confirmatory_eligible": bool(confirmation.get("confirmatory_eligible", False)),
        "n_networks_min": int(confirmation.get("n_networks_min", 100)),
        "thresholds_locked": bool(confirmation.get("thresholds_locked", True)),
    }
    n_networks = int(complete["network_id"].nunique()) if not complete.empty else 0
    estimator = (
        str(complete["donor_r2_estimator"].mode().iloc[0])
        if not complete.empty and "donor_r2_estimator" in complete.columns
        else "year_block_cv"
    )
    manifest = {
        "what_this_is": (
            "Nested ablation on already-downloaded public rivers. "
            "Train-only predictors; later-year donor-regression skill versus train climatology."
        ),
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
        "n_station_rows_primary_gap": int(len(complete)),
        "primary_gap_length": int(primary_gap),
        "primary_networks": sorted(primary_ids),
        "requested_primary_networks": requested,
        "requested_primary_missing": missing_requested,
        "delaware_scored": "delaware_river_huc20" in available,
        "scored_networks": sorted(available),
        "spearman_by_gap": spearman_by_gap,
        "achieved_skill_is_later_year_not_gap_specific": True,
        "nested_grids": "separate per gap so later-year skill is not duplicated",
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
) -> dict[str, Path]:
    """Write only the three new public-river ablation filenames."""

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
    return {
        "nested": nested_path,
        "comparison": comparison_path,
        "manifest": manifest_path,
    }


__all__ = [
    "GAP_LENGTHS",
    "INSANE_DONOR_MAE_C",
    "NESTED_PREDICTORS",
    "complete_predictor_rows",
    "concurrent_enough_ids",
    "drop_insane_mae_networks",
    "load_public_river_panels",
    "nested_ablation_table",
    "run_public_river_operator_ablation",
    "score_operator_ablation",
    "station_operator_rows",
    "write_operator_ablation_artifacts",
]
