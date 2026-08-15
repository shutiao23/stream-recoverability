#!/usr/bin/env python3
"""Run tasks 61-70 on event metrics and daily prediction tables."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.compensation import (  # noqa: E402
    build_value_function,
    compensation_gains,
    knn_mutual_information,
    shapley_table,
    transfer_entropy_by_lag,
)
from stream_recoverability.analysis.frontiers import (  # noqa: E402
    application_frontier,
    estimate_frontiers,
)
from stream_recoverability.analysis.resilience import (  # noqa: E402
    node_importance,
    resilience_auc,
    resilience_curve,
)
from stream_recoverability.analysis.science_metrics import (  # noqa: E402
    scientific_metrics_by_event,
)
from stream_recoverability.analysis.statistics import (  # noqa: E402
    compare_models,
    fit_mixed_effects,
)
from stream_recoverability.analysis.uncertainty import (  # noqa: E402
    interval_calibration_by_gap,
    overall_calibration,
    uncertainty_growth,
)


DEFAULT_EVENTS = PROJECT_ROOT / "results/baselines/event_metrics.parquet"
DEFAULT_DAILY = PROJECT_ROOT / "results/baselines/predictions.parquet"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/analysis"


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
    group_cols = [
        column
        for column in ("station_id", "target", "model", "pattern")
        if column in events
    ]
    required_metrics = list(criteria)
    data = events.copy()
    for column in ["gap_length", *required_metrics]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    grouped = data.groupby(group_cols, dropna=False, observed=True) if group_cols else [((), data)]
    rows = []
    for group_key, group in grouped:
        if group_cols and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(group_cols, group_key if group_cols else (), strict=True))
        curve = group.groupby("gap_length", as_index=False)[required_metrics].mean(numeric_only=True)
        rows.append({**metadata, **application_frontier(curve, criteria)})
    return pd.DataFrame(rows)


def run_analysis(args: argparse.Namespace) -> dict[str, Any]:
    events = _read_table(args.event_metrics)
    daily = _read_table(args.daily_predictions) if args.daily_predictions.exists() else None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "event_metrics": str(args.event_metrics),
        "daily_predictions": str(args.daily_predictions) if daily is not None else None,
        "seed": int(args.seed),
        "bootstrap_replicates": int(args.bootstrap),
        "analyses": {},
    }

    try:
        comparisons = compare_models(
            events,
            baseline_model=args.baseline_model,
            metric=args.metric,
            n_boot=args.bootstrap,
            seed=args.seed,
        )
        if comparisons.empty:
            _status(summary, "paired_comparisons", status="skipped", reason="no paired model comparisons")
        else:
            path = _write_csv(comparisons, args.output_dir, "paired_comparisons.csv")
            _status(summary, "paired_comparisons", status="ok", files=[path], rows=len(comparisons))
    except ValueError as exc:
        _status(summary, "paired_comparisons", status="skipped", reason=str(exc))

    try:
        coefficients, mixed_summary = fit_mixed_effects(events, outcome=args.metric)
        files: list[str] = []
        if not coefficients.empty:
            files.append(_write_csv(coefficients, args.output_dir, "mixed_effects_coefficients.csv"))
        _status(
            summary,
            "mixed_effects",
            status="ok" if mixed_summary.get("reason") is None else "skipped",
            reason=mixed_summary.get("reason"),
            files=files,
            rows=len(coefficients),
            details={key: value for key, value in mixed_summary.items() if key != "reason"},
        )
    except ValueError as exc:
        _status(summary, "mixed_effects", status="skipped", reason=str(exc))

    combination_col = next(
        (
            column
            for column in ("information_combination", "available_information", "information_sources")
            if column in events
        ),
        None,
    )
    if combination_col is None:
        _status(summary, "information_compensation", status="skipped", reason="no information-combination column")
    else:
        try:
            values = build_value_function(
                events,
                metric=args.metric,
                combination_col=combination_col,
            )
            shapley = shapley_table(values)
            gains = compensation_gains(values)
            files = [
                _write_csv(values, args.output_dir, "information_value_function.csv"),
                _write_csv(gains, args.output_dir, "information_compensation_gains.csv"),
                _write_csv(shapley, args.output_dir, "information_shapley.csv"),
            ]
            incomplete = int(shapley["reason"].notna().sum()) if "reason" in shapley else 0
            _status(
                summary,
                "information_compensation",
                status="ok" if incomplete == 0 else "partial",
                reason=None if incomplete == 0 else f"{incomplete} Shapley rows could not be estimated",
                files=files,
                rows=len(shapley),
            )
        except ValueError as exc:
            _status(summary, "information_compensation", status="skipped", reason=str(exc))

    source_col = args.information_source_col
    target_col = args.information_target_col
    if daily is None:
        _status(summary, "information_theory", status="skipped", reason="daily prediction table not found")
    elif not source_col or not target_col:
        _status(summary, "information_theory", status="skipped", reason="set --information-source-col and --information-target-col")
    elif source_col not in daily or target_col not in daily:
        _status(
            summary,
            "information_theory",
            status="skipped",
            reason=f"missing information columns: {[column for column in (source_col, target_col) if column not in daily]}",
        )
    else:
        mutual = knn_mutual_information(
            daily[source_col], daily[target_col], seed=args.seed
        )
        forward = transfer_entropy_by_lag(
            daily[source_col],
            daily[target_col],
            args.te_lags,
            n_bins=args.te_bins,
            n_permutations=args.te_permutations,
            seed=args.seed,
        )
        forward["direction"] = f"{source_col}->{target_col}"
        reverse = transfer_entropy_by_lag(
            daily[target_col],
            daily[source_col],
            args.te_lags,
            n_bins=args.te_bins,
            n_permutations=args.te_permutations,
            seed=args.seed,
        )
        reverse["direction"] = f"{target_col}->{source_col}"
        information = pd.concat([forward, reverse], ignore_index=True)
        information["mutual_information"] = mutual["mutual_information"]
        path = _write_csv(information, args.output_dir, "information_metrics.csv")
        _status(summary, "information_theory", status="ok", files=[path], rows=len(information))

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
        _status(summary, "recoverability_frontiers", status="ok", files=files, rows=len(frontiers))
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
        _status(summary, "application_frontiers", status="skipped", reason="no predeclared application thresholds")
    else:
        missing = sorted({"gap_length", *criteria} - set(events.columns))
        if missing:
            _status(summary, "application_frontiers", status="skipped", reason=f"missing application columns: {missing}")
        else:
            applications = _application_tables(events, criteria)
            path = _write_csv(applications, args.output_dir, "application_frontiers.csv")
            _status(summary, "application_frontiers", status="ok", files=[path], rows=len(applications))

    failed_col = next(
        (column for column in ("failed_stations", "failed_station_ids") if column in events),
        None,
    )
    if failed_col is None:
        _status(summary, "network_resilience", status="skipped", reason="no explicit failed-station column")
    else:
        try:
            curve = resilience_curve(
                events,
                failed_sites_col=failed_col,
                total_sites=args.total_sites,
            )
            auc = resilience_auc(curve)
            importance = node_importance(events, failed_sites_col=failed_col)
            files = [
                _write_csv(curve, args.output_dir, "network_resilience_curve.csv"),
                _write_csv(auc, args.output_dir, "network_resilience_auc.csv"),
                _write_csv(importance, args.output_dir, "node_importance.csv"),
            ]
            _status(summary, "network_resilience", status="ok", files=files, rows=len(curve))
        except ValueError as exc:
            _status(summary, "network_resilience", status="skipped", reason=str(exc))

    if daily is None:
        _status(summary, "uncertainty_calibration", status="skipped", reason="daily prediction table not found")
        _status(summary, "scientific_metrics", status="skipped", reason="daily prediction table not found")
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
            _status(summary, "uncertainty_calibration", status="ok", files=files, rows=len(calibration))
        except ValueError as exc:
            _status(summary, "uncertainty_calibration", status="skipped", reason=str(exc))
        try:
            science = scientific_metrics_by_event(daily)
            path = _write_csv(science, args.output_dir, "scientific_metrics.csv")
            _status(summary, "scientific_metrics", status="ok", files=[path], rows=len(science))
        except ValueError as exc:
            _status(summary, "scientific_metrics", status="skipped", reason=str(exc))

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
