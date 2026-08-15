#!/usr/bin/env python3
"""Run tasks 61-70 on event metrics and daily prediction tables."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.compensation import (
    benjamini_hochberg_fdr,
    build_value_function,
    compensation_gains,
    knn_mutual_information,
    shapley_table,
    transfer_entropy_by_lag,
)
from stream_recoverability.analysis.frontiers import (
    DENSE_FLOW_LEVEL_GAPS,
    DENSE_T_GAPS,
    FRONTIER_GROUP_COLUMNS,
    application_frontier,
    dense_gap_coverage,
    estimate_frontiers,
    frontier_design_subset,
)
from stream_recoverability.analysis.resilience import (
    RESILIENCE_EXPERIMENT,
    complete_resilience_units,
    node_importance,
    resilience_auc,
    resilience_curve,
)
from stream_recoverability.analysis.science_metrics import (
    scientific_metrics_by_event,
)
from stream_recoverability.analysis.statistics import (
    compare_models,
    fit_mixed_effects_by_design,
)
from stream_recoverability.analysis.uncertainty import (
    interval_calibration_by_gap,
    overall_calibration,
    uncertainty_growth,
)

DEFAULT_EVENTS = PROJECT_ROOT / "results/baselines/event_metrics.parquet"
DEFAULT_DAILY = PROJECT_ROOT / "results/baselines/predictions.parquet"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/analysis"
INFORMATION_AGGREGATE_COLUMNS = (
    "experiment",
    "window_length",
    "training_protocol",
    "validation_scope",
    "station_id",
    "target",
    "gap_length",
    "model",
    "source",
)
FIXED_TRAINING_SEEDS = {11, 22, 33, 44, 55}
KNOWN_TRAINABLE_MODELS = {"brits", "saits", "proposed", "information_compensation"}


def _read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported table format: {path}")


def _write_csv(frame: pd.DataFrame, output_dir: Path, name: str) -> str:
    path = output_dir / name
    frame.to_csv(path, index=False)
    return str(path)


def _single_contiguous_information_series(
    daily: pd.DataFrame, source_col: str, target_col: str
) -> pd.DataFrame:
    if "date" not in daily:
        raise ValueError(
            "information theory requires a unique daily date axis; use "
            "scripts/12_run_science_experiments.py information for formal TE"
        )
    unit_columns = [
        column
        for column in (
            "scenario_id",
            "model",
            "training_seed",
            "mask_seed",
            "station_id",
            "target",
            "information_combination",
        )
        if column in daily
    ]
    varying = [
        column for column in unit_columns if daily[column].nunique(dropna=False) > 1
    ]
    if varying:
        raise ValueError(
            "information theory requires one design unit, but these columns vary: "
            f"{varying}; use scripts/12_run_science_experiments.py information "
            "for formal training-only TE"
        )
    selected = daily[["date", source_col, target_col]].copy()
    selected["date"] = pd.to_datetime(selected["date"], errors="coerce")
    selected = selected.sort_values("date")
    if selected["date"].isna().any() or selected["date"].duplicated().any():
        raise ValueError("information theory requires unique finite daily dates")
    if len(selected) > 1 and not selected["date"].diff().dropna().eq(
        pd.Timedelta(days=1)
    ).all():
        raise ValueError("information theory requires an unbroken daily date axis")
    return selected


def _formal_training_seed_coverage(
    events: pd.DataFrame,
    *,
    expected_seeds: set[int] | None = None,
    manifest_complete: bool | None = None,
) -> dict[str, Any]:
    expected = set(FIXED_TRAINING_SEEDS if expected_seeds is None else expected_seeds)
    models = (
        events["model"].astype(str).str.lower()
        if "model" in events
        else pd.Series("", index=events.index, dtype="string")
    )
    if "training_seed" in events:
        raw_seeds = events["training_seed"]
        numeric_seeds = pd.to_numeric(raw_seeds, errors="coerce")
        models_with_seed = set(models.loc[raw_seeds.notna()])
    else:
        raw_seeds = pd.Series(np.nan, index=events.index)
        numeric_seeds = pd.Series(np.nan, index=events.index)
        models_with_seed = set()
    seeded_models = models_with_seed | (set(models) & KNOWN_TRAINABLE_MODELS)
    data = events.loc[models.isin(seeded_models)].copy()
    if data.empty:
        return {
            "complete": manifest_complete is not False,
            "manifest_complete": manifest_complete,
            "expected_training_seeds": sorted(expected),
            "checked_groups": 0,
            "incomplete_group_count": 0,
            "incomplete_groups": [],
            "incomplete_experiments": [],
            "incomplete_models": [],
        }
    data["_raw_training_seed"] = raw_seeds.loc[data.index]
    data["_numeric_training_seed"] = numeric_seeds.loc[data.index]
    numeric = data["_numeric_training_seed"]
    data["_valid_training_seed"] = numeric.where(
        numeric.notna() & np.isfinite(numeric) & np.isclose(numeric, np.round(numeric))
    )
    group_cols = [
        column
        for column in (
            "experiment",
            "condition_id",
            "scenario_id",
            "station_id",
            "target",
            "model",
            "information_combination",
        )
        if column in data
    ]
    incomplete: list[dict[str, Any]] = []
    grouped = data.groupby(group_cols, dropna=False, observed=True)
    checked = 0
    for group_key, group in grouped:
        checked += 1
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        observed = set(group["_valid_training_seed"].dropna().astype(int))
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        invalid = sorted(
            {
                str(value)
                for value in group.loc[
                    group["_raw_training_seed"].notna()
                    & group["_valid_training_seed"].isna(),
                    "_raw_training_seed",
                ]
            }
        )
        if missing or unexpected or invalid:
            incomplete.append(
                {
                    **dict(zip(group_cols, group_key, strict=True)),
                    "observed_training_seeds": sorted(observed),
                    "missing_training_seeds": missing,
                    "unexpected_training_seeds": unexpected,
                    "invalid_training_seeds": invalid,
                }
            )
    manifest_incomplete = manifest_complete is False
    return {
        "complete": not incomplete and not manifest_incomplete,
        "manifest_complete": manifest_complete,
        "expected_training_seeds": sorted(expected),
        "checked_groups": checked,
        "incomplete_group_count": len(incomplete),
        "incomplete_groups": incomplete[:20],
        "incomplete_experiments": sorted(
            {
                str(row["experiment"])
                for row in incomplete
                if row.get("experiment") is not None
                and not pd.isna(row.get("experiment"))
            }
        ),
        "incomplete_models": sorted(
            {str(row["model"]) for row in incomplete if row.get("model") is not None}
        ),
    }


def _analysis_run_manifest(args: argparse.Namespace) -> tuple[Path | None, dict[str, Any]]:
    explicit = getattr(args, "run_manifest", None)
    candidate = explicit or args.event_metrics.parent / "run_manifest.json"
    if not candidate.exists():
        if explicit is not None:
            raise FileNotFoundError(candidate)
        return None, {}
    value = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a mapping in {candidate}")
    return candidate, value


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _status(
    summary: dict[str, Any],
    name: str,
    *,
    status: str,
    reason: str | None = None,
    files: list[str] | None = None,
    rows: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    summary["analyses"][name] = {
        "status": status,
        "reason": reason,
        "files": files or [],
        "rows": rows,
        **(details or {}),
    }


def _application_tables(
    events: pd.DataFrame,
    criteria: dict[str, tuple[str, float]],
) -> pd.DataFrame:
    data = frontier_design_subset(events)
    group_cols = [column for column in FRONTIER_GROUP_COLUMNS if column in data]
    required_metrics = list(criteria)
    for column in ["gap_length", *required_metrics]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    grouped = (
        data.groupby(group_cols, dropna=False, observed=True)
        if group_cols
        else [((), data)]
    )
    rows = []
    for group_key, group in grouped:
        if group_cols and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(group_cols, group_key if group_cols else (), strict=True))
        curve = group.groupby("gap_length", as_index=False)[required_metrics].mean(
            numeric_only=True
        )
        target = str(metadata.get("target", "T"))
        expected_gaps = (
            DENSE_T_GAPS
            if target.upper().split("_")[-1] == "T"
            else DENSE_FLOW_LEVEL_GAPS
        )
        coverage = dense_gap_coverage(curve["gap_length"], target)
        expected_rows = curve.loc[
            curve["gap_length"].map(
                lambda value: any(np.isclose(value, gap) for gap in expected_gaps)
            )
        ].copy()
        missing_metric_gaps = {
            metric: [
                gap
                for gap in expected_gaps
                if not (
                    np.isclose(expected_rows["gap_length"], gap)
                    & np.isfinite(expected_rows[metric])
                ).any()
            ]
            for metric in required_metrics
        }
        missing_metric_gaps = {
            metric: gaps for metric, gaps in missing_metric_gaps.items() if gaps
        }
        inputs_complete = bool(
            coverage["dense_grid_complete"] and not missing_metric_gaps
        )
        estimate = (
            application_frontier(expected_rows, criteria)
            if inputs_complete
            else {
                "application_frontier_days": np.nan,
                "limiting_metric": None,
                "reason": (
                    "incomplete predeclared application grid; "
                    f"missing gaps={coverage['missing_recommended_gap_lengths']}, "
                    f"missing criterion values={missing_metric_gaps}"
                ),
            }
        )
        rows.append(
            {
                **metadata,
                **estimate,
                **coverage,
                "missing_criterion_gap_values": missing_metric_gaps,
                "application_inputs_complete": inputs_complete,
            }
        )
    return pd.DataFrame(rows)


def _aggregate_complete_information_units(
    units: pd.DataFrame,
    value_columns: tuple[str, ...],
) -> pd.DataFrame:
    if units.empty:
        return pd.DataFrame()
    complete = (
        units.loc[units["reason"].isna()].copy() if "reason" in units else units.copy()
    )
    group_cols = [
        column for column in INFORMATION_AGGREGATE_COLUMNS if column in complete
    ]
    metrics = [column for column in value_columns if column in complete]
    if complete.empty or not group_cols or not metrics:
        return pd.DataFrame(columns=[*group_cols, *metrics, "n_units"])
    aggregated = (
        complete.groupby(group_cols, dropna=False, observed=True)[metrics]
        .mean()
        .reset_index()
    )
    counts = (
        complete.groupby(group_cols, dropna=False, observed=True)
        .size()
        .rename("n_units")
        .reset_index()
    )
    return aggregated.merge(counts, on=group_cols, validate="one_to_one")


def _information_exclusions(units: pd.DataFrame) -> pd.DataFrame:
    if units.empty or "reason" not in units:
        return pd.DataFrame()
    excluded = units.loc[units["reason"].notna()].copy()
    if "source" in excluded:
        excluded = excluded.loc[excluded["source"].astype(str).eq("A")]
    unit_cols = [
        column
        for column in (
            "scenario_id",
            "training_seed",
            "mask_seed",
            "experiment",
            "window_length",
            "training_protocol",
            "validation_scope",
            "station_id",
            "target",
            "gap_length",
            "model",
            "missing_combinations",
            "reason",
        )
        if column in excluded
    ]
    return excluded.loc[:, unit_cols].drop_duplicates().reset_index(drop=True)


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    events = _read_table(args.event_metrics)
    daily = (
        _read_table(args.daily_predictions) if args.daily_predictions.exists() else None
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path, run_manifest = _analysis_run_manifest(args)
    training_profile = str(run_manifest.get("training_profile", "formal"))
    manifest_seed_values = run_manifest.get(
        "training_seeds" if training_profile == "smoke" else "expected_training_seeds"
    )
    if manifest_seed_values is None:
        expected_training_seeds = set(FIXED_TRAINING_SEEDS)
    else:
        numeric_manifest_seeds = pd.to_numeric(
            pd.Series(manifest_seed_values), errors="coerce"
        )
        if (
            numeric_manifest_seeds.empty
            or numeric_manifest_seeds.isna().any()
            or not np.isclose(
                numeric_manifest_seeds, np.round(numeric_manifest_seeds)
            ).all()
        ):
            raise ValueError("run manifest training seeds must be finite integers")
        expected_training_seeds = set(numeric_manifest_seeds.astype(int))
    manifest_complete = (
        bool(run_manifest["complete"]) if "complete" in run_manifest else None
    )
    summary: dict[str, Any] = {
        "event_metrics": str(args.event_metrics),
        "daily_predictions": str(args.daily_predictions) if daily is not None else None,
        "run_manifest": str(run_manifest_path) if run_manifest_path else None,
        "training_profile": training_profile,
        "seed": int(args.seed),
        "bootstrap_replicates": int(args.bootstrap),
        "analyses": {},
    }
    training_seed_coverage = _formal_training_seed_coverage(
        events,
        expected_seeds=expected_training_seeds,
        manifest_complete=manifest_complete,
    )
    summary["formal_training_seed_coverage"] = training_seed_coverage

    try:
        comparisons = compare_models(
            events,
            baseline_model=args.baseline_model,
            metric=args.metric,
            n_boot=args.bootstrap,
            seed=args.seed,
        )
        if comparisons.empty:
            _status(
                summary,
                "paired_comparisons",
                status="skipped",
                reason="no paired model comparisons",
            )
        else:
            path = _write_csv(comparisons, args.output_dir, "paired_comparisons.csv")
            _status(
                summary,
                "paired_comparisons",
                status="ok",
                files=[path],
                rows=len(comparisons),
            )
    except ValueError as exc:
        _status(summary, "paired_comparisons", status="skipped", reason=str(exc))

    try:
        coefficients, mixed_diagnostics = fit_mixed_effects_by_design(
            events, outcome=args.metric
        )
        files: list[str] = []
        if not coefficients.empty:
            files.append(
                _write_csv(
                    coefficients, args.output_dir, "mixed_effects_coefficients.csv"
                )
            )
        if not mixed_diagnostics.empty:
            files.append(
                _write_csv(
                    mixed_diagnostics,
                    args.output_dir,
                    "mixed_effects_diagnostics.csv",
                )
            )
        fitted_regimes = (
            int(mixed_diagnostics["reason"].isna().sum())
            if "reason" in mixed_diagnostics
            else 0
        )
        excluded_regimes = int(len(mixed_diagnostics) - fitted_regimes)
        _status(
            summary,
            "mixed_effects",
            status=(
                "skipped"
                if fitted_regimes == 0
                else "partial"
                if excluded_regimes
                else "ok"
            ),
            reason=(
                "no design regime produced an identifiable mixed-effects fit"
                if fitted_regimes == 0
                else f"{excluded_regimes} design regimes were not identifiable"
                if excluded_regimes
                else None
            ),
            files=files,
            rows=len(coefficients),
            details={
                "fitted_design_regimes": fitted_regimes,
                "excluded_design_regimes": excluded_regimes,
            },
        )
    except ValueError as exc:
        _status(summary, "mixed_effects", status="skipped", reason=str(exc))

    combination_col = next(
        (
            column
            for column in (
                "information_combination",
                "available_information",
                "information_sources",
            )
            if column in events
        ),
        None,
    )
    if combination_col is None:
        _status(
            summary,
            "information_compensation",
            status="skipped",
            reason="no information-combination column",
        )
    else:
        try:
            missing_units = sorted(
                {"scenario_id", "training_seed"} - set(events.columns)
            )
            if missing_units:
                raise ValueError(
                    "information compensation requires scenario/training units: "
                    f"{missing_units}"
                )
            values = build_value_function(
                events,
                metric=args.metric,
                combination_col=combination_col,
            )
            shapley_units = shapley_table(values)
            gain_units = compensation_gains(values)
            shapley = _aggregate_complete_information_units(
                shapley_units,
                (
                    "shapley",
                    "baseline_value",
                    "full_value",
                    "total_gain",
                    "efficiency_residual",
                ),
            )
            gains = _aggregate_complete_information_units(
                gain_units,
                (
                    "full_removal_gain",
                    "mean_marginal_gain",
                    "mean_relative_compensation",
                    "n_marginal_pairs",
                ),
            )
            exclusions = _information_exclusions(shapley_units)
            files = [
                _write_csv(values, args.output_dir, "information_value_function.csv"),
                _write_csv(
                    gains, args.output_dir, "information_compensation_gains.csv"
                ),
                _write_csv(shapley, args.output_dir, "information_shapley.csv"),
                _write_csv(
                    gain_units,
                    args.output_dir,
                    "information_compensation_gains_by_unit.csv",
                ),
                _write_csv(
                    shapley_units,
                    args.output_dir,
                    "information_shapley_by_unit.csv",
                ),
                _write_csv(
                    exclusions,
                    args.output_dir,
                    "information_exclusions.csv",
                ),
            ]
            incomplete = len(exclusions)
            complete_units = (
                len(
                    shapley_units.loc[
                        shapley_units["source"].astype(str).eq("A")
                        & shapley_units["reason"].isna()
                    ]
                )
                if not shapley_units.empty
                else 0
            )
            _status(
                summary,
                "information_compensation",
                status="ok" if incomplete == 0 else "partial",
                reason=(
                    None
                    if incomplete == 0
                    else f"{incomplete} scenario/training-seed units were excluded"
                ),
                files=files,
                rows=len(shapley),
                details={"complete_units": complete_units},
            )
        except ValueError as exc:
            _status(
                summary, "information_compensation", status="skipped", reason=str(exc)
            )

    source_col = args.information_source_col
    target_col = args.information_target_col
    if daily is None:
        _status(
            summary,
            "information_theory",
            status="skipped",
            reason="daily prediction table not found",
        )
    elif not source_col or not target_col:
        _status(
            summary,
            "information_theory",
            status="skipped",
            reason="set --information-source-col and --information-target-col",
        )
    elif source_col not in daily or target_col not in daily:
        _status(
            summary,
            "information_theory",
            status="skipped",
            reason=f"missing information columns: {[column for column in (source_col, target_col) if column not in daily]}",
        )
    else:
        try:
            information_series = _single_contiguous_information_series(
                daily, source_col, target_col
            )
            mutual = knn_mutual_information(
                information_series[source_col],
                information_series[target_col],
                seed=args.seed,
            )
            forward = transfer_entropy_by_lag(
                information_series[source_col],
                information_series[target_col],
                args.te_lags,
                n_bins=args.te_bins,
                n_permutations=args.te_permutations,
                seed=args.seed,
            )
            forward["direction"] = f"{source_col}->{target_col}"
            reverse = transfer_entropy_by_lag(
                information_series[target_col],
                information_series[source_col],
                args.te_lags,
                n_bins=args.te_bins,
                n_permutations=args.te_permutations,
                seed=args.seed,
            )
            reverse["direction"] = f"{target_col}->{source_col}"
            information = pd.concat([forward, reverse], ignore_index=True)
            information["p_fdr_bh"] = benjamini_hochberg_fdr(
                information["p_value"]
            )
            information["significant_fdr_05"] = information["p_fdr_bh"].le(0.05)
            information["mutual_information"] = mutual["mutual_information"]
            path = _write_csv(
                information, args.output_dir, "information_metrics.csv"
            )
            _status(
                summary,
                "information_theory",
                status="ok",
                files=[path],
                rows=len(information),
                details={"scope": "single_contiguous_design_unit"},
            )
        except ValueError as exc:
            _status(
                summary,
                "information_theory",
                status="skipped",
                reason=str(exc),
            )

    try:
        curves, frontiers = estimate_frontiers(
            events,
            n_boot=args.bootstrap,
            seed=args.seed,
        )
        files = [
            _write_csv(curves, args.output_dir, "skill_curves.csv"),
            _write_csv(frontiers, args.output_dir, "recoverability_frontiers.csv"),
        ]
        complete_frontiers = (
            int(frontiers["dense_grid_complete"].fillna(False).sum())
            if "dense_grid_complete" in frontiers
            else 0
        )
        incomplete_frontiers = int(len(frontiers) - complete_frontiers)
        _status(
            summary,
            "recoverability_frontiers",
            status=(
                "skipped"
                if complete_frontiers == 0
                else "partial"
                if incomplete_frontiers
                else "ok"
            ),
            reason=(
                "no design group contains the complete predeclared dense gap grid"
                if complete_frontiers == 0
                else f"{incomplete_frontiers} design groups have incomplete dense gap grids"
                if incomplete_frontiers
                else None
            ),
            files=files,
            rows=len(frontiers),
            details={
                "complete_design_groups": complete_frontiers,
                "incomplete_design_groups": incomplete_frontiers,
            },
        )
    except ValueError as exc:
        _status(summary, "recoverability_frontiers", status="skipped", reason=str(exc))

    criteria: dict[str, tuple[str, float]] = {}
    if args.mae_threshold is not None:
        criteria[args.metric] = ("<=", args.mae_threshold)
    if args.extreme_threshold is not None:
        criteria[args.extreme_metric] = ("<=", args.extreme_threshold)
    if args.coverage_threshold is not None:
        criteria[args.coverage_metric] = (">=", args.coverage_threshold)
    if not criteria:
        _status(
            summary,
            "application_frontiers",
            status="skipped",
            reason="no predeclared application thresholds",
        )
    else:
        missing = sorted({"gap_length", *criteria} - set(events.columns))
        if missing:
            _status(
                summary,
                "application_frontiers",
                status="skipped",
                reason=f"missing application columns: {missing}",
            )
        else:
            try:
                applications = _application_tables(events, criteria)
                path = _write_csv(
                    applications, args.output_dir, "application_frontiers.csv"
                )
                complete_applications = int(
                    applications["application_inputs_complete"].fillna(False).sum()
                )
                incomplete_applications = int(
                    len(applications) - complete_applications
                )
                _status(
                    summary,
                    "application_frontiers",
                    status=(
                        "skipped"
                        if complete_applications == 0
                        else "partial"
                        if incomplete_applications
                        else "ok"
                    ),
                    reason=(
                        "no design group contains complete predeclared application inputs"
                        if complete_applications == 0
                        else f"{incomplete_applications} design groups have incomplete application inputs"
                        if incomplete_applications
                        else None
                    ),
                    files=[path],
                    rows=len(applications),
                    details={
                        "complete_design_groups": complete_applications,
                        "incomplete_design_groups": incomplete_applications,
                    },
                )
            except ValueError as exc:
                _status(
                    summary, "application_frontiers", status="skipped", reason=str(exc)
                )

    if "experiment" not in events:
        _status(
            summary,
            "network_resilience",
            status="skipped",
            reason="network resilience requires an explicit experiment column",
        )
    else:
        network_events = events.loc[
            events["experiment"].astype(str).str.upper().eq(RESILIENCE_EXPERIMENT)
        ].copy()
        failed_col = next(
            (
                column
                for column in ("failed_stations", "failed_station_ids")
                if column in network_events and network_events[column].notna().any()
            ),
            None,
        )
        if network_events.empty:
            _status(
                summary,
                "network_resilience",
                status="skipped",
                reason="no experiment='SCI_NET' rows",
            )
        elif failed_col is None:
            _status(
                summary,
                "network_resilience",
                status="skipped",
                reason="SCI_NET rows have no explicit failed-station column",
            )
        else:
            try:
                complete_network, exclusions = complete_resilience_units(
                    network_events,
                    failed_sites_col=failed_col,
                    total_sites=args.total_sites,
                    value_cols=tuple(dict.fromkeys(("skill", args.metric))),
                )
                files = []
                if not exclusions.empty:
                    files.append(
                        _write_csv(
                            exclusions,
                            args.output_dir,
                            "network_resilience_exclusions.csv",
                        )
                    )
                if complete_network.empty:
                    _status(
                        summary,
                        "network_resilience",
                        status="skipped",
                        reason="no complete three-station powerset units",
                        files=files,
                        details={"incomplete_units_excluded": len(exclusions)},
                    )
                else:
                    curve = resilience_curve(
                        complete_network,
                        failed_sites_col=failed_col,
                        total_sites=args.total_sites,
                    )
                    auc = resilience_auc(curve)
                    importance = node_importance(
                        complete_network,
                        value_col=args.metric,
                        failed_sites_col=failed_col,
                        higher_is_better=False,
                    )
                    files.extend(
                        [
                            _write_csv(
                                curve,
                                args.output_dir,
                                "network_resilience_curve.csv",
                            ),
                            _write_csv(
                                auc,
                                args.output_dir,
                                "network_resilience_auc.csv",
                            ),
                            _write_csv(
                                importance,
                                args.output_dir,
                                "node_importance.csv",
                            ),
                        ]
                    )
                    _status(
                        summary,
                        "network_resilience",
                        status="partial" if len(exclusions) else "ok",
                        reason=(
                            f"{len(exclusions)} incomplete replicate units were excluded"
                            if len(exclusions)
                            else None
                        ),
                        files=files,
                        rows=len(curve),
                        details={
                            "incomplete_units_excluded": len(exclusions),
                            "eligible_rows": len(complete_network),
                            "out_of_design_rows_ignored": len(events)
                            - len(network_events),
                        },
                    )
            except ValueError as exc:
                _status(
                    summary, "network_resilience", status="skipped", reason=str(exc)
                )

    if daily is None:
        _status(
            summary,
            "uncertainty_calibration",
            status="skipped",
            reason="daily prediction table not found",
        )
        _status(
            summary,
            "scientific_metrics",
            status="skipped",
            reason="daily prediction table not found",
        )
    else:
        try:
            calibration = interval_calibration_by_gap(daily)
            growth = uncertainty_growth(calibration)
            overall = overall_calibration(calibration)
            files = [
                _write_csv(calibration, args.output_dir, "uncertainty_by_gap.csv"),
                _write_csv(growth, args.output_dir, "uncertainty_growth.csv"),
                _write_csv(overall, args.output_dir, "uncertainty_overall.csv"),
            ]
            _status(
                summary,
                "uncertainty_calibration",
                status="ok",
                files=files,
                rows=len(calibration),
            )
        except ValueError as exc:
            _status(
                summary, "uncertainty_calibration", status="skipped", reason=str(exc)
            )
        try:
            science = scientific_metrics_by_event(daily)
            path = _write_csv(science, args.output_dir, "scientific_metrics.csv")
            long_term = (
                int(science["long_term_trend_available"].sum())
                if "long_term_trend_available" in science
                else 0
            )
            local_only = int(len(science) - long_term)
            _status(
                summary,
                "scientific_metrics",
                status="ok" if local_only == 0 else "partial",
                reason=(
                    None
                    if local_only == 0
                    else f"{local_only} rows report local shape only; complete test-period reconstruction unavailable"
                ),
                files=[path],
                rows=len(science),
                details={
                    "long_term_trend_rows": long_term,
                    "local_shape_only_rows": local_only,
                },
            )
        except ValueError as exc:
            _status(summary, "scientific_metrics", status="skipped", reason=str(exc))

    if not training_seed_coverage["complete"]:
        incomplete_count = training_seed_coverage["incomplete_group_count"]
        expected_seed_label = "/".join(
            str(value)
            for value in training_seed_coverage["expected_training_seeds"]
        )
        seed_reasons = []
        if incomplete_count:
            seed_reasons.append(
                f"{incomplete_count} design units do not contain required training "
                f"seeds {expected_seed_label}"
            )
        if training_seed_coverage["manifest_complete"] is False:
            seed_reasons.append("input run manifest is incomplete")
        seed_reason = "; ".join(seed_reasons)
        incomplete_experiments = set(
            training_seed_coverage["incomplete_experiments"]
        )
        incomplete_models = set(training_seed_coverage["incomplete_models"])
        for name in (
            "paired_comparisons",
            "mixed_effects",
            "information_compensation",
            "recoverability_frontiers",
            "application_frontiers",
            "network_resilience",
            "uncertainty_calibration",
            "scientific_metrics",
        ):
            analysis = summary["analyses"].get(name)
            if analysis is None or analysis["status"] == "skipped":
                continue
            if (
                training_seed_coverage["manifest_complete"] is not False
                and name in {"recoverability_frontiers", "application_frontiers"}
                and "SCI_DENSE" not in incomplete_experiments
            ):
                continue
            if (
                training_seed_coverage["manifest_complete"] is not False
                and name == "network_resilience"
                and "SCI_NET" not in incomplete_experiments
            ):
                continue
            if (
                training_seed_coverage["manifest_complete"] is not False
                and name == "information_compensation"
                and "information_compensation" not in incomplete_models
            ):
                continue
            analysis["status"] = "partial"
            analysis["reason"] = "; ".join(
                value for value in (analysis.get("reason"), seed_reason) if value
            )

    summary_path = args.output_dir / "analysis_summary.json"
    summary_path.write_text(
        json.dumps(
            _json_safe(summary),
            ensure_ascii=False,
            indent=2,
            default=_json_default,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-metrics", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--daily-predictions", type=Path, default=DEFAULT_DAILY)
    parser.add_argument(
        "--run-manifest",
        type=Path,
        help="optional runner manifest used to distinguish smoke and formal seed contracts",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline-model", default="climatology")
    parser.add_argument("--metric", default="MAE")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--information-source-col")
    parser.add_argument("--information-target-col")
    parser.add_argument("--te-lags", type=int, nargs="+", default=[1])
    parser.add_argument("--te-bins", type=int, default=4)
    parser.add_argument("--te-permutations", type=int, default=199)
    parser.add_argument("--total-sites", type=int)
    parser.add_argument("--mae-threshold", type=float)
    parser.add_argument("--extreme-metric", default="high_temp_mae")
    parser.add_argument("--extreme-threshold", type=float)
    parser.add_argument("--coverage-metric", default="coverage_90")
    parser.add_argument("--coverage-threshold", type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_analysis(args)
    statuses = Counter(value["status"] for value in summary["analyses"].values())
    print(
        "analysis complete: "
        + ", ".join(f"{status}={count}" for status, count in sorted(statuses.items()))
    )
    print(f"summary: {args.output_dir / 'analysis_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
