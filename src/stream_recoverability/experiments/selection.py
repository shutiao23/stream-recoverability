"""Frozen validation-only finalist selection and proposed-model go/no-go rules."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .validation import (
    DEEP_CANDIDATES,
    TRADITIONAL_CANDIDATES,
    VALIDATION_DEEP_SEEDS,
    rank_validation_models,
    validation_condition_stratum,
)


def _strict_boolean(value: Any, *, field: str, model: str) -> bool:
    """Parse persisted diagnostic booleans without treating ``"False"`` as true."""

    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and int(value) in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    raise ValueError(
        f"stage-2 diagnostic {field!r} for {model!r} must be a strict boolean"
    )


@dataclass(frozen=True)
class ProposedGoNoGoDecision:
    """Auditable all-criteria decision for formal proposed-model inclusion."""

    passed: bool
    criteria: pd.DataFrame
    best_traditional_model: str
    evidence: dict[str, Any]


def select_stage2_finalists(
    ranking: pd.DataFrame,
    *,
    diagnostics: pd.DataFrame | None = None,
    tolerance_from_best: float = 0.05,
    mandatory_diagnostic_candidates: Sequence[str] = ("csdi", "proposed"),
) -> pd.DataFrame:
    """Apply the frozen single-seed deep finalist rule.

    A model must first pass finite/convergence diagnostics. Eligible models are
    retained when their equal-stratum mean skill is within ``tolerance_from_best``
    of the best eligible model. CSDI and proposed remain diagnostic candidates
    even outside that tolerance, but never bypass a failed diagnostic contract.
    """

    required = {"model", "validation_stage", "mean_skill_across_strata"}
    missing = sorted(required.difference(ranking.columns))
    if missing:
        raise ValueError(f"stage-2 ranking is missing columns: {missing}")
    data = ranking.loc[
        ranking["model"].astype(str).isin(DEEP_CANDIDATES)
        & ranking["validation_stage"].astype(str).eq("deep_single_seed")
    ].copy()
    if set(data["model"].astype(str)) != set(DEEP_CANDIDATES):
        raise ValueError("stage-2 ranking must contain all frozen deep candidates")
    data["mean_skill_across_strata"] = pd.to_numeric(
        data["mean_skill_across_strata"], errors="coerce"
    )
    if not np.isfinite(data["mean_skill_across_strata"]).all():
        raise ValueError("stage-2 mean skills must be finite")

    diagnostic_pass = {model: True for model in DEEP_CANDIDATES}
    diagnostic_reason = {
        model: "all required diagnostics passed" for model in DEEP_CANDIDATES
    }
    if diagnostics is not None:
        diagnostic_required = {
            "model",
            "finite_predictions",
            "finite_validation_score",
            "best_epoch",
            "epochs_run",
        }
        absent = sorted(diagnostic_required.difference(diagnostics.columns))
        if absent:
            raise ValueError(f"stage-2 diagnostics are missing columns: {absent}")
        if diagnostics["model"].astype(str).duplicated().any():
            raise ValueError("stage-2 diagnostics require one row per model")
        indexed = diagnostics.assign(model=diagnostics["model"].astype(str)).set_index(
            "model"
        )
        if not set(DEEP_CANDIDATES).issubset(indexed.index):
            raise ValueError("stage-2 diagnostics omit a frozen deep candidate")
        for model in DEEP_CANDIDATES:
            row = indexed.loc[model]
            epoch = pd.to_numeric(pd.Series([row["best_epoch"]]), errors="coerce").iloc[
                0
            ]
            epochs_run = pd.to_numeric(
                pd.Series([row["epochs_run"]]), errors="coerce"
            ).iloc[0]
            checks = {
                "finite_predictions": _strict_boolean(
                    row["finite_predictions"],
                    field="finite_predictions",
                    model=model,
                ),
                "finite_validation_score": _strict_boolean(
                    row["finite_validation_score"],
                    field="finite_validation_score",
                    model=model,
                ),
                "finite_best_epoch": bool(
                    np.isfinite(epoch)
                    and np.isfinite(epochs_run)
                    and 1 <= epoch <= epochs_run
                ),
            }
            if "hit_epoch_limit" in indexed.columns:
                hit_limit = _strict_boolean(
                    row["hit_epoch_limit"],
                    field="hit_epoch_limit",
                    model=model,
                )
                checks["budget_stable"] = not hit_limit
            diagnostic_pass[model] = all(checks.values())
            failed = [name for name, passed in checks.items() if not passed]
            diagnostic_reason[model] = (
                "all required diagnostics passed"
                if not failed
                else "failed diagnostics: " + ", ".join(failed)
            )

    eligible = data.loc[data["model"].map(diagnostic_pass)]
    if eligible.empty:
        raise ValueError("no stage-2 deep candidate passed diagnostics")
    if not np.isfinite(float(tolerance_from_best)) or tolerance_from_best < 0:
        raise ValueError("tolerance_from_best must be finite and non-negative")
    best = float(eligible["mean_skill_across_strata"].max())
    mandatory = {str(model) for model in mandatory_diagnostic_candidates}
    unknown_mandatory = sorted(mandatory.difference(DEEP_CANDIDATES))
    if unknown_mandatory:
        raise ValueError(
            f"unknown mandatory diagnostic candidates: {unknown_mandatory}"
        )

    data["diagnostic_pass"] = data["model"].map(diagnostic_pass).astype(bool)
    data["distance_from_best_skill"] = best - data["mean_skill_across_strata"]
    data["within_best_tolerance"] = data["distance_from_best_skill"].le(
        float(tolerance_from_best) + 1e-12
    )
    data["mandatory_diagnostic_candidate"] = data["model"].isin(mandatory)
    data["selected_for_stability"] = data["diagnostic_pass"] & (
        data["within_best_tolerance"] | data["mandatory_diagnostic_candidate"]
    )
    data["selection_reason"] = [
        diagnostic_reason[str(model)]
        if not passed
        else "mandatory diagnostic candidate"
        if mandatory_candidate and not within
        else "within frozen tolerance of best eligible mean skill"
        for model, passed, mandatory_candidate, within in data[
            [
                "model",
                "diagnostic_pass",
                "mandatory_diagnostic_candidate",
                "within_best_tolerance",
            ]
        ].itertuples(index=False, name=None)
    ]
    data["selection_split"] = "validation"
    data["formal_evidence"] = False
    return data.sort_values(
        ["selected_for_stability", "mean_skill_across_strata", "model"],
        ascending=[False, False, True],
        kind="mergesort",
        ignore_index=True,
    )


def _paired_skill_units(
    event_metrics: pd.DataFrame,
    best_traditional_model: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = event_metrics.copy()
    data["condition_stratum"] = data["condition_id"].map(validation_condition_stratum)
    data["skill"] = pd.to_numeric(data["skill"], errors="coerce")
    data["coverage_90"] = pd.to_numeric(
        data.get("coverage_90", np.nan), errors="coerce"
    )
    keys = ["condition_id", "condition_stratum", "station_id", "mask_seed"]
    traditional = (
        data.loc[data["model"].astype(str).eq(best_traditional_model)]
        .groupby(keys, as_index=False, dropna=False, sort=True)
        .agg(traditional_skill=("skill", "mean"))
    )
    proposed = data.loc[data["model"].astype(str).eq("proposed")].copy()
    proposed["training_seed"] = pd.to_numeric(
        proposed["training_seed"], errors="coerce"
    )
    if proposed["training_seed"].isna().any():
        raise ValueError("proposed stability rows require explicit training seeds")
    proposed["training_seed"] = proposed["training_seed"].astype(int)
    proposed_units = proposed.groupby(
        [*keys, "training_seed"], as_index=False, dropna=False, sort=True
    ).agg(proposed_skill=("skill", "mean"), coverage_90=("coverage_90", "mean"))
    paired = proposed_units.merge(
        traditional, on=keys, how="inner", validate="many_to_one"
    )
    if len(paired) != len(proposed_units):
        raise ValueError(
            "proposed and best-traditional validation units are not paired"
        )
    paired["skill_gain"] = paired["proposed_skill"] - paired["traditional_skill"]
    return paired, proposed_units


def _branch_ablation_checks(
    ablations: pd.DataFrame,
    *,
    tolerance: float,
) -> tuple[bool, bool, dict[str, float]]:
    required = {
        "training_seed",
        "station_id",
        "mask_seed",
        "gap_length",
        "information_combination",
        "MAE",
        "attribution_estimand",
    }
    missing = sorted(required.difference(ablations.columns))
    if missing:
        raise ValueError(f"branch ablations are missing columns: {missing}")
    data = ablations.copy()
    if not data["attribution_estimand"].astype(str).eq("operational_dropout").all():
        raise ValueError(
            "go/no-go branch ablations must use one-checkpoint operational dropout"
        )
    data["MAE"] = pd.to_numeric(data["MAE"], errors="coerce")
    data["gap_length"] = pd.to_numeric(data["gap_length"], errors="coerce")
    if not np.isfinite(data[["MAE", "gap_length"]]).all().all():
        raise ValueError("branch ablation MAE and gap lengths must be finite")
    keys = ["training_seed", "station_id", "mask_seed", "gap_length"]
    values = data.pivot_table(
        index=keys,
        columns="information_combination",
        values="MAE",
        aggfunc="mean",
    )
    full = "S0+A+B+C+D"
    required_combinations = {full, "S0+B+C+D", "S0+A+C+D", "S0+A+B+D", "S0+A+B+C"}
    missing_combinations = sorted(required_combinations.difference(values.columns))
    if missing_combinations:
        raise ValueError(f"branch ablations omit combinations: {missing_combinations}")
    short = values.loc[
        np.isclose(values.index.get_level_values("gap_length").astype(float), 10.0)
    ]
    long = values.loc[
        values.index.get_level_values("gap_length").astype(float).isin([90.0, 180.0])
    ]
    if short.empty or long.empty:
        raise ValueError("branch ablations require 10-day and 90/180-day units")
    short_a_delta = float((short["S0+B+C+D"] - short[full]).mean())
    long_deltas = {
        source: float((long[label] - long[full]).mean())
        for source, label in {
            "B": "S0+A+C+D",
            "C": "S0+A+B+D",
            "D": "S0+A+B+C",
        }.items()
    }
    return (
        short_a_delta > tolerance,
        any(value > tolerance for value in long_deltas.values()),
        {
            "short_A_removal_MAE_delta": short_a_delta,
            **{f"long_{k}_removal_MAE_delta": v for k, v in long_deltas.items()},
        },
    )


def assess_proposed_go_no_go(
    event_metrics: pd.DataFrame,
    branch_ablations: pd.DataFrame,
    *,
    best_traditional_model: str | None = None,
    skill_gain_minimum: float = 0.02,
    coverage_bounds: tuple[float, float] = (0.85, 0.95),
    minimum_positive_stations: int = 2,
    maximum_station_share: float = 0.60,
    ablation_tolerance_mae: float = 1e-6,
) -> ProposedGoNoGoDecision:
    """Evaluate every predeclared proposed-model continuation criterion."""

    ranking = rank_validation_models(event_metrics)
    traditional = ranking.loc[ranking["model"].astype(str).isin(TRADITIONAL_CANDIDATES)]
    if traditional.empty:
        raise ValueError("go/no-go requires at least one complete traditional model")
    derived_best = str(traditional.iloc[0]["model"])
    if best_traditional_model is None:
        best_traditional_model = derived_best
    elif str(best_traditional_model) != derived_best:
        raise ValueError(
            "declared best traditional model disagrees with frozen validation ranking"
        )
    paired, proposed_units = _paired_skill_units(event_metrics, best_traditional_model)
    seeds = tuple(sorted(paired["training_seed"].unique()))
    if seeds != VALIDATION_DEEP_SEEDS:
        raise ValueError(
            f"go/no-go requires proposed seeds {VALIDATION_DEEP_SEEDS}, found {seeds}"
        )

    block_90 = paired.loc[paired["condition_stratum"].eq("t_block_90d")]
    block_180 = paired.loc[paired["condition_stratum"].eq("t_block_180d")]
    outage_90 = paired.loc[paired["condition_stratum"].eq("hydro_station_outage_90d")]
    if min(len(block_90), len(block_180), len(outage_90)) == 0:
        raise ValueError("go/no-go requires complete 90/180/outage validation strata")
    mean_90 = float(block_90["skill_gain"].mean())
    seed_90 = block_90.groupby("training_seed", sort=True)["skill_gain"].mean()
    gain_180 = float(block_180["skill_gain"].mean())
    gain_outage = float(outage_90["skill_gain"].mean())

    long_labels = {
        "t_block_90d",
        "t_block_180d",
        "tfl_block_90d",
        "hydro_station_outage_90d",
    }
    coverage = proposed_units.loc[
        proposed_units["condition_stratum"].isin(long_labels), "coverage_90"
    ].dropna()
    mean_coverage = float(coverage.mean()) if len(coverage) else float("nan")
    station_gain = block_90.groupby("station_id", sort=True)["skill_gain"].mean()
    positive_station_gain = station_gain.clip(lower=0.0)
    positive_station_count = int((station_gain > 0).sum())
    positive_total = float(positive_station_gain.sum())
    station_share = (
        float(positive_station_gain.max() / positive_total)
        if positive_total > 0
        else float("inf")
    )
    short_ablation, long_ablation, ablation_evidence = _branch_ablation_checks(
        branch_ablations, tolerance=ablation_tolerance_mae
    )
    low_coverage, high_coverage = map(float, coverage_bounds)

    criteria_rows = [
        {
            "criterion": "stable_90_day_gain",
            "observed": mean_90,
            "threshold": f">={skill_gain_minimum} and every seed >0",
            "passed": bool(mean_90 >= skill_gain_minimum and (seed_90 > 0).all()),
        },
        {
            "criterion": "difficult_case_gain",
            "observed": max(gain_180, gain_outage),
            "threshold": f"180-day or outage gain >={skill_gain_minimum}",
            "passed": bool(max(gain_180, gain_outage) >= skill_gain_minimum),
        },
        {
            "criterion": "seed_direction",
            "observed": int((seed_90 > 0).sum()),
            "threshold": f"{len(VALIDATION_DEEP_SEEDS)} of {len(VALIDATION_DEEP_SEEDS)} positive",
            "passed": bool((seed_90 > 0).all()),
        },
        {
            "criterion": "interval_calibration",
            "observed": mean_coverage,
            "threshold": f"{low_coverage} <= mean coverage <= {high_coverage}",
            "passed": bool(
                np.isfinite(mean_coverage)
                and low_coverage <= mean_coverage <= high_coverage
            ),
        },
        {
            "criterion": "station_robustness",
            "observed": station_share,
            "threshold": f">={minimum_positive_stations} positive stations and max share <={maximum_station_share}",
            "passed": bool(
                positive_station_count >= minimum_positive_stations
                and station_share <= maximum_station_share
            ),
        },
        {
            "criterion": "short_gap_A_ablation",
            "observed": ablation_evidence["short_A_removal_MAE_delta"],
            "threshold": f">{ablation_tolerance_mae}",
            "passed": bool(short_ablation),
        },
        {
            "criterion": "long_gap_nonlocal_ablation",
            "observed": max(
                ablation_evidence["long_B_removal_MAE_delta"],
                ablation_evidence["long_C_removal_MAE_delta"],
                ablation_evidence["long_D_removal_MAE_delta"],
            ),
            "threshold": f"at least one B/C/D removal delta >{ablation_tolerance_mae}",
            "passed": bool(long_ablation),
        },
    ]
    criteria = pd.DataFrame(criteria_rows)
    criteria["evaluation_split"] = "validation"
    criteria["formal_evidence"] = False
    evidence = {
        "best_traditional_model": best_traditional_model,
        "mean_90_day_skill_gain": mean_90,
        "seed_90_day_skill_gains": {str(int(k)): float(v) for k, v in seed_90.items()},
        "mean_180_day_skill_gain": gain_180,
        "mean_outage_90_day_skill_gain": gain_outage,
        "mean_long_case_coverage_90": mean_coverage,
        "station_90_day_skill_gains": {
            str(k): float(v) for k, v in station_gain.items()
        },
        "positive_station_count": positive_station_count,
        "maximum_positive_station_gain_share": station_share,
        "branch_ablation": ablation_evidence,
        "criterion_passes": json.loads(
            criteria.set_index("criterion")["passed"].to_json()
        ),
    }
    return ProposedGoNoGoDecision(
        passed=bool(criteria["passed"].all()),
        criteria=criteria,
        best_traditional_model=best_traditional_model,
        evidence=evidence,
    )


__all__ = [
    "ProposedGoNoGoDecision",
    "assess_proposed_go_no_go",
    "select_stage2_finalists",
]
