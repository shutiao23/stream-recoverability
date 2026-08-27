"""W2 Phase-4 y: planted 30/90 gaps, not copied later-year donor skill.

Train-only predictors. Fill MAE versus train-only day-of-year climatology on
held-out observed blocks of length L. This module lives in scratch; it must
not overwrite ``results/framework/public_rivers/operator_ablation_manifest.json``.
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
from stream_recoverability.analysis.recoverability_spectrum import recoverability
from stream_recoverability.experiments.natural_outage_scoring import (
    MIN_GAP_DAYS_WITH_DONOR,
    _doy_climatology,
    _gap_donor_mae,
    observed_gap_starts,
)
from stream_recoverability.experiments.public_river_operator_ablation import (
    GAP_LENGTHS,
    INSANE_DONOR_MAE_C,
    MIN_TEST_DAYS,
    MIN_TRAIN_DAYS,
    NESTED_PREDICTORS,
    _doy_anomalies,
    _jsonable,
    _lag_acf,
    _rho_at_distance,
    complete_predictor_rows,
    nested_ablation_table,
    station_operator_rows,
)
from stream_recoverability.experiments.real_river_checks import year_split

REQUIRED_SIX = (
    "delaware_river_huc20",
    "willamette_river_huc17",
    "madison_river_huc10",
    "mahoning_river_huc50",
    "roanoke_river_huc30",
    "santa_fe_river_huc31",
)
SUWANNEE_ID = "suwannee_river_huc31"
MIN_DONOR_TRAIN_DAYS = 365
W2_PURPOSE = "pipeline_verification_not_evidence"
W2_INFERENCE_STATUS = "withheld_n_lt_100_network_interval"


def concurrent_enough_roster(overlap: pd.DataFrame) -> tuple[str, ...]:
    """Return overlap-complete network ids. Suwannee is not a Delaware substitute."""

    if "complete_enough" not in overlap.columns or "network_id" not in overlap.columns:
        raise ValueError("overlap.csv must have network_id and complete_enough")
    enough = overlap["complete_enough"].map(_explicit_true)
    ids = tuple(overlap.loc[enough, "network_id"].astype(str).tolist())
    return ids


def _explicit_true(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"true", "1", "yes"}


def usable_donor_indices(
    target: np.ndarray,
    donors: np.ndarray,
    train: np.ndarray,
    gap: np.ndarray | None = None,
    *,
    min_train_days: int = MIN_DONOR_TRAIN_DAYS,
    min_gap_days: int = MIN_GAP_DAYS_WITH_DONOR,
) -> list[int]:
    """Keep donors with train overlap. Do not require every catalog column on the same day."""

    keep: list[int] = []
    if donors.size == 0:
        return keep
    for column in range(donors.shape[1]):
        train_ok = int(
            (train & np.isfinite(target) & np.isfinite(donors[:, column])).sum()
        )
        if train_ok < int(min_train_days):
            continue
        if gap is not None:
            gap_ok = int((gap & np.isfinite(donors[:, column])).sum())
            if gap_ok < int(min_gap_days):
                continue
        keep.append(int(column))
    return keep


def planted_starts_in_test(
    index: pd.DatetimeIndex,
    target_ok: np.ndarray,
    donor_ok: np.ndarray,
    test: np.ndarray,
    *,
    length: int,
) -> np.ndarray:
    """Starts of length-L observed blocks that sit entirely in later years."""

    starts = observed_gap_starts(
        index,
        target_ok,
        donor_ok,
        length=int(length),
        season="",
        later_half=False,
    )
    if starts.size == 0:
        return starts
    length = int(length)
    keep = [
        int(start)
        for start in starts
        if bool(test[int(start)]) and bool(test[int(start) + length - 1])
    ]
    return np.asarray(keep, dtype=int)


def shared_plant_start(
    index: pd.DatetimeIndex,
    target_ok: np.ndarray,
    donor_ok: np.ndarray,
    test: np.ndarray,
    gap_lengths: Sequence[int],
) -> int | None:
    """One later-year start that can host every requested L (prefix nesting)."""

    longest = max(int(item) for item in gap_lengths)
    starts = planted_starts_in_test(
        index, target_ok, donor_ok, test, length=longest
    )
    if starts.size == 0:
        return None
    return int(starts[0])


def score_planted_block(
    target: np.ndarray,
    donors: np.ndarray,
    index: pd.DatetimeIndex,
    train: np.ndarray,
    in_gap: np.ndarray,
    *,
    min_gap_days: int = MIN_GAP_DAYS_WITH_DONOR,
) -> tuple[float, float, float, list[int]]:
    """Donor-fill MAE versus train-only DOY climatology on the planted block."""

    keep = usable_donor_indices(target, donors, train, in_gap, min_gap_days=min_gap_days)
    if not keep:
        return float("nan"), float("nan"), float("nan"), []
    selected = donors[:, keep]
    fill_mae = _gap_donor_mae(
        target, selected, train, in_gap, min_test=min_gap_days
    )
    climate = _doy_climatology(target, index, train)
    climate_mae = float(np.nanmean(np.abs(target[in_gap] - climate[in_gap])))
    skill = recoverability(fill_mae, climate_mae)
    return float(fill_mae), float(climate_mae), float(skill), keep


def _train_donor_r2(
    target: np.ndarray,
    donors: Sequence[np.ndarray],
    years: np.ndarray,
) -> tuple[float, str]:
    cv = year_block_cv_r2(target, donors, years)
    if np.isfinite(cv):
        return float(cv), "year_block_cv"
    return float(in_sample_r2(target, donors)), "train_in_sample"


def planted_station_rows(
    name: str,
    wide: pd.DataFrame,
    *,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
    max_gaps_per_length: int = 1,
    insane_mae_c: float = INSANE_DONOR_MAE_C,
) -> list[dict[str, float | str | bool | int]]:
    """Score planted L=30/90 gaps. Predictors use fitting years only."""

    if not isinstance(wide.index, pd.DatetimeIndex):
        raise TypeError("wide frame must be indexed by date")
    values = wide.to_numpy(dtype=float)
    train, test = year_split(wide.index)
    if int(train.sum()) < MIN_TRAIN_DAYS or int(test.sum()) < MIN_TEST_DAYS:
        return [
            {
                "network_id": name,
                "reason": "not_enough_years_after_split",
                "achieved_skill": float("nan"),
                "y_kind": "planted_gap",
            }
        ]
    years = wide.index.year.to_numpy()
    rows: list[dict[str, float | str | bool | int]] = []
    lengths = [int(item) for item in gap_lengths]
    for target in range(values.shape[1]):
        donor_idx = [index for index in range(values.shape[1]) if index != target]
        if not donor_idx:
            continue
        target_values = values[:, target]
        donor_values = values[:, donor_idx]
        if not np.isfinite(target_values[train]).any():
            continue
        target_ok = np.isfinite(target_values)
        donor_ok = np.isfinite(donor_values).any(axis=1)
        anomalies = _doy_anomalies(target_values, wide.index, train)
        donor_anomalies = [
            _doy_anomalies(values[:, donor], wide.index, train) for donor in donor_idx
        ]
        train_keep = usable_donor_indices(target_values, donor_values, train)
        if not train_keep:
            continue
        acf30 = _lag_acf(anomalies[train], 30)
        donor_r2, donor_r2_estimator = _train_donor_r2(
            anomalies[train],
            [donor_anomalies[item][train] for item in train_keep],
            years[train],
        )
        shared = shared_plant_start(
            wide.index, target_ok, donor_ok, test, lengths
        )
        for gap_length in lengths:
            starts = planted_starts_in_test(
                wide.index, target_ok, donor_ok, test, length=gap_length
            )
            if starts.size == 0:
                continue
            chosen: list[int]
            if shared is not None:
                chosen = [int(shared)]
            else:
                chosen = [int(starts[0])]
            chosen = chosen[: int(max_gaps_per_length)]
            rho = _rho_at_distance(anomalies[train], float(gap_length) / 4.0)
            if np.isfinite(donor_r2) and np.isfinite(rho):
                heuristic = float(
                    np.clip(
                        donor_r2
                        + memory_component(float(np.clip(donor_r2, 0.0, 1.0)), rho),
                        0.0,
                        1.0,
                    )
                )
            else:
                heuristic = float("nan")
            compact = np.column_stack(
                [target_values, donor_values[:, train_keep]]
            )
            compact_donors = list(range(1, compact.shape[1]))
            try:
                conditionals = empirical_information_set_conditionals(
                    compact[train],
                    target=0,
                    donors=compact_donors,
                    gap_length=int(gap_length),
                )
                both = conditionals["B_union_D"]
                operator_r = float(both.get("recoverability_r", float("nan")))
                predicted_skill = float(both.get("predicted_skill", float("nan")))
                predicted_risk = float(both.get("expected_mae_conditional", float("nan")))
            except (np.linalg.LinAlgError, ValueError, KeyError):
                operator_r = predicted_skill = predicted_risk = float("nan")
            for start in chosen:
                in_gap = np.zeros(len(wide), dtype=bool)
                in_gap[int(start) : int(start) + int(gap_length)] = True
                fill_mae, climate_mae, skill, keep = score_planted_block(
                    target_values,
                    donor_values,
                    wide.index,
                    train,
                    in_gap,
                )
                if (
                    not np.isfinite(skill)
                    or not np.isfinite(fill_mae)
                    or not np.isfinite(climate_mae)
                    or climate_mae == 0
                    or fill_mae >= float(insane_mae_c)
                ):
                    continue
                rows.append(
                    {
                        "network_id": name,
                        "station_id": str(wide.columns[target]),
                        "gap_length": int(gap_length),
                        "start_date": pd.Timestamp(wide.index[int(start)]).date().isoformat(),
                        "n_usable_donors": int(len(keep)),
                        "acf30": float(acf30),
                        "donor_r2": float(donor_r2),
                        "donor_r2_estimator": donor_r2_estimator,
                        "heuristic_explained_variance": heuristic,
                        "recoverability_r": operator_r,
                        "predicted_skill": predicted_skill,
                        "predicted_conditional_risk": predicted_risk,
                        "fill_mae": float(fill_mae),
                        "donor_mae": float(fill_mae),
                        "climate_mae": float(climate_mae),
                        "observed_recovery_loss": float(fill_mae),
                        "achieved_skill": float(skill),
                        "y_kind": "planted_gap",
                        "reason": "",
                    }
                )
    if not rows:
        return [
            {
                "network_id": name,
                "reason": "could_not_score_any_station",
                "achieved_skill": float("nan"),
                "y_kind": "planted_gap",
            }
        ]
    return rows


def later_year_station_rows(
    name: str,
    wide: pd.DataFrame,
    *,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
) -> list[dict[str, float | str | bool | int]]:
    """Production hole, labeled. Same later-year skill copied across L."""

    rows = station_operator_rows(name, wide, gap_lengths=gap_lengths)
    labeled: list[dict[str, float | str | bool | int]] = []
    for row in rows:
        item = dict(row)
        item["y_kind"] = "later_year_copied"
        labeled.append(item)
    return labeled


def score_panels(
    panels: Mapping[str, pd.DataFrame],
    *,
    kind: str = "planted_gap",
    gap_lengths: Sequence[int] = GAP_LENGTHS,
) -> pd.DataFrame:
    rows: list[dict[str, float | str | bool | int]] = []
    for name, wide in panels.items():
        if kind == "later_year":
            rows.extend(later_year_station_rows(name, wide, gap_lengths=gap_lengths))
        else:
            rows.extend(planted_station_rows(name, wide, gap_lengths=gap_lengths))
    return pd.DataFrame(rows)


def skill_copied_across_gap_lengths(scores: pd.DataFrame) -> bool:
    """True when each station's achieved_skill is identical at every L."""

    needed = {"station_id", "gap_length", "achieved_skill"}
    if scores.empty or not needed.issubset(scores.columns):
        return False
    usable = scores.loc[
        np.isfinite(pd.to_numeric(scores["achieved_skill"], errors="coerce"))
        & scores.get("reason", pd.Series("", index=scores.index)).fillna("").eq("")
    ]
    if usable.empty:
        return False
    keys = [name for name in ("network_id", "station_id") if name in usable.columns]
    for _, group in usable.groupby(keys, sort=False):
        if group["gap_length"].nunique() < 2:
            continue
        skills = pd.to_numeric(group["achieved_skill"], errors="coerce")
        if skills.nunique(dropna=True) != 1:
            return False
    return True


def gap_length_delta_r2(scores: pd.DataFrame, *, pooled: bool) -> float:
    """First nested step. Per-gap tables make this vacuous; pooling is the check."""

    if pooled:
        nested = nested_ablation_table(scores, level="station", scope="pooled")
        match = nested.loc[nested["added"].eq("gap_length"), "delta_r2"]
        if match.empty:
            return float("nan")
        return float(match.iloc[0])
    deltas: list[float] = []
    if "gap_length" not in scores.columns:
        return float("nan")
    for gap, group in scores.groupby("gap_length", sort=False):
        nested = nested_ablation_table(
            group, level="station", scope=f"gap_{int(gap)}"
        )
        match = nested.loc[nested["added"].eq("gap_length"), "delta_r2"]
        if match.empty:
            deltas.append(float("nan"))
        else:
            deltas.append(float(match.iloc[0]))
    finite = [item for item in deltas if np.isfinite(item)]
    if not finite:
        return float("nan")
    return float(max(abs(item) for item in finite))


def w2_manifest(
    scores: pd.DataFrame,
    *,
    roster: Sequence[str] = REQUIRED_SIX,
) -> dict[str, Any]:
    """Pipeline-verification contract. Never a T2 pass. Never a tested network CI."""

    usable = scores.loc[
        np.isfinite(pd.to_numeric(scores.get("achieved_skill"), errors="coerce"))
    ] if scores is not None and not scores.empty else pd.DataFrame()
    scored = (
        sorted(usable["network_id"].astype(str).unique())
        if not usable.empty and "network_id" in usable.columns
        else []
    )
    missing = [item for item in roster if item not in scored]
    leaked = [item for item in scored if item == SUWANNEE_ID]
    nested_pooled = (
        nested_ablation_table(usable, level="station", scope="pooled")
        if not usable.empty
        else pd.DataFrame()
    )
    gap_delta = gap_length_delta_r2(usable, pooled=True) if not usable.empty else float("nan")
    copied = skill_copied_across_gap_lengths(usable) if not usable.empty else True
    return {
        "what_this_is": (
            "W2 six-river pipeline verification: planted 30/90 gap skill "
            "versus train-only predictors."
        ),
        "what_this_is_not": (
            "Not T2. Not formal evidence. Not a headline. Not the later-year "
            "audit in results/framework/public_rivers/operator_ablation_manifest.json."
        ),
        "n_networks": 6,
        "passed": False,
        "purpose": W2_PURPOSE,
        "achieved_skill_is_later_year_not_gap_specific": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "thresholds_locked": True,
        "primary_networks": list(roster),
        "scored_networks": scored,
        "requested_primary_missing": missing,
        "delaware_required": "delaware_river_huc20" in roster,
        "delaware_scored": "delaware_river_huc20" in scored,
        "suwannee_must_not_replace_delaware": SUWANNEE_ID not in roster,
        "suwannee_leaked_into_scored": leaked,
        "y_kind": "planted_gap",
        "gap_lengths": [30, 90],
        "nested_grids": "pooled across gap lengths; per-gap tables are not the pipeline check",
        "gap_length_delta_r2_pooled": gap_delta,
        "gap_length_delta_r2_is_pipeline_check": True,
        "later_year_skill_copied_across_L": copied,
        "operator_incremental_r2_le_0_does_not_license_retuning": True,
        "network_interval": {
            "inference_status": W2_INFERENCE_STATUS,
            "ci_lower": None,
            "ci_upper": None,
            "n_networks": 6,
            "note": "W2 n=6 cannot report a cluster-bootstrap network CI.",
        },
        "evaluate_success": {
            "passed": False,
            "passed_numeric_floors": False,
            "confirmatory_eligible": False,
            "n_networks_min": 100,
            "thresholds_locked": True,
            "inference_status": W2_INFERENCE_STATUS,
        },
        "sealed_outcomes_opened": False,
        "jinsha_outcomes_used": False,
        "chattahoochee_outcomes_used": False,
        "new_temperatures_downloaded": False,
        "natural_outage_fill_mae_used_as_phase4_y": False,
        "overwrites_later_year_audit_manifest": False,
        "nested_predictors": list(NESTED_PREDICTORS),
        "n_station_gap_rows": int(len(complete_predictor_rows(usable))) if not usable.empty else 0,
        "pooled_nested": _jsonable(nested_pooled),
    }


def write_w2_artifacts(
    scores: pd.DataFrame,
    manifest: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    scores_path = root / "w2_planted_gap_scores.csv"
    nested_path = root / "w2_pooled_nested_ablation.csv"
    manifest_path = root / "w2_pipeline_manifest.json"
    scores.to_csv(scores_path, index=False)
    nested = nested_ablation_table(scores, level="station", scope="pooled")
    nested.to_csv(nested_path, index=False)
    manifest_path.write_text(
        json.dumps(_jsonable(dict(manifest)), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"scores": scores_path, "nested": nested_path, "manifest": manifest_path}


def shock_toy_wide(
    *,
    n_years: int = 8,
    n_stations: int = 4,
    seed: int = 1,
    shock: float = 18.0,
) -> pd.DataFrame:
    """Later years: days 30–90 of the first test window carry a unique target shock.

    Same-day donor fill is easy on a 30-day prefix and hard on the 90-day window
    that includes the shock. Later-year y still copies one MAE across L.
    """

    dates = pd.date_range("2000-01-01", periods=365 * n_years, freq="D")
    rng = np.random.default_rng(seed)
    seasonal = 8.0 * np.sin(2.0 * np.pi * dates.dayofyear.to_numpy() / 365.25)
    factor = rng.normal(0.0, 1.1, len(dates))
    data = {}
    for index in range(n_stations):
        data[f"s{index}"] = (
            seasonal
            + factor
            + (0.2 * index)
            + rng.normal(0.0, 0.25, len(dates))
        )
    frame = pd.DataFrame(data, index=dates)
    train, test = year_split(frame.index)
    test_indices = np.flatnonzero(test)
    if test_indices.size < 90:
        raise ValueError("toy series needs >=90 later-year days")
    start = int(test_indices[0])
    frame.iloc[start + 30 : start + 90, 0] = (
        frame.iloc[start + 30 : start + 90, 0].to_numpy(dtype=float) + float(shock)
    )
    return frame


__all__ = [
    "REQUIRED_SIX",
    "SUWANNEE_ID",
    "W2_INFERENCE_STATUS",
    "W2_PURPOSE",
    "concurrent_enough_roster",
    "gap_length_delta_r2",
    "later_year_station_rows",
    "planted_station_rows",
    "score_panels",
    "shock_toy_wide",
    "skill_copied_across_gap_lengths",
    "usable_donor_indices",
    "w2_manifest",
    "write_w2_artifacts",
]
