#!/usr/bin/env python3
"""Analyse one complete, hash-verified frozen result bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.frozen_pipeline import (
    load_frozen_inputs,
    load_frozen_inputs_from_manifest,
    run_frozen_analysis,
)

DEFAULT_PREDICTIONS = PROJECT_ROOT / "results/frozen/predictions.parquet"
DEFAULT_EVENTS = PROJECT_ROOT / "results/frozen/event_metrics.parquet"
DEFAULT_MANIFEST = PROJECT_ROOT / "results/frozen/top_manifest.json"
DEFAULT_DESIGN = PROJECT_ROOT / "configs/design_freeze_v3.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/analysis"
FIXED_TRAINING_SEEDS = frozenset({11, 22, 33, 44, 55})
CANONICAL_TRAINABLE_MODELS = frozenset(
    {
        "brits_lite",
        "saits_lite",
        "brits_ref",
        "saits_ref",
        "csdi",
        "proposed",
        "information_compensation",
    }
)


def _formal_training_seed_coverage(
    events: pd.DataFrame,
    *,
    expected_seeds: set[int] | None = None,
    manifest_complete: bool | None = None,
) -> dict[str, Any]:
    """Compatibility diagnostic; the frozen pipeline trusts no table alone.

    This helper remains importable for focused diagnostics, but the CLI requires
    the stronger top-manifest completion and hash contract before analysis.
    Legacy ambiguous model names (``brits``/``saits``) are intentionally not in
    the canonical registry.
    """

    expected = set(FIXED_TRAINING_SEEDS if expected_seeds is None else expected_seeds)
    if "model" not in events:
        return {
            "complete": manifest_complete is not False,
            "manifest_complete": manifest_complete,
            "expected_training_seeds": sorted(expected),
            "checked_groups": 0,
            "incomplete_group_count": 0,
            "incomplete_groups": [],
        }
    models = events["model"].astype(str).str.lower()
    selected = events.loc[models.isin(CANONICAL_TRAINABLE_MODELS)].copy()
    if selected.empty:
        return {
            "complete": manifest_complete is not False,
            "manifest_complete": manifest_complete,
            "expected_training_seeds": sorted(expected),
            "checked_groups": 0,
            "incomplete_group_count": 0,
            "incomplete_groups": [],
        }
    raw = selected.get("training_seed", pd.Series(np.nan, index=selected.index))
    numeric = pd.to_numeric(raw, errors="coerce")
    selected["_raw_seed"] = raw
    selected["_valid_seed"] = numeric.where(
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
        if column in selected
    ]
    incomplete: list[dict[str, Any]] = []
    grouped = selected.groupby(group_cols, dropna=False, observed=True, sort=True)
    for key, group in grouped:
        key_tuple = key if isinstance(key, tuple) else (key,)
        observed = set(group["_valid_seed"].dropna().astype(int))
        invalid = sorted(
            {
                str(value)
                for value in group.loc[
                    group["_raw_seed"].notna() & group["_valid_seed"].isna(),
                    "_raw_seed",
                ]
            }
        )
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        if missing or unexpected or invalid:
            incomplete.append(
                {
                    **dict(zip(group_cols, key_tuple, strict=True)),
                    "observed_training_seeds": sorted(observed),
                    "missing_training_seeds": missing,
                    "unexpected_training_seeds": unexpected,
                    "invalid_training_seeds": invalid,
                }
            )
    return {
        "complete": not incomplete and manifest_complete is not False,
        "manifest_complete": manifest_complete,
        "expected_training_seeds": sorted(expected),
        "checked_groups": int(grouped.ngroups),
        "incomplete_group_count": len(incomplete),
        "incomplete_groups": incomplete[:20],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--event-metrics", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--top-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--sensitivity-manifest",
        type=Path,
        action="append",
        required=True,
        help=(
            "required exactly three times: one formal_aggregate_manifest_v2 for "
            "each frozen sensitivity data version"
        ),
    )
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if len(args.sensitivity_manifest) != 3:
        parser.error(
            "--sensitivity-manifest must be supplied exactly three times "
            "(no_s2_suspect_v1, b1_no_level_v1, b1_shift_sensitivity_v1)"
        )
    inputs = load_frozen_inputs(
        args.predictions,
        args.event_metrics,
        args.top_manifest,
        args.design,
    )
    sensitivity_inputs = [
        load_frozen_inputs_from_manifest(path, args.design)
        for path in args.sensitivity_manifest
    ]
    manifest = run_frozen_analysis(
        inputs,
        args.output_dir,
        sensitivity_inputs=sensitivity_inputs,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "artifacts": len(manifest["artifacts"]),
                "manifest": str(args.output_dir / "analysis_manifest.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if manifest["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
