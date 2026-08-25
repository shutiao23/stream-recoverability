#!/usr/bin/env python3
"""Post-hoc diagnosis of frozen regulation-panel leave-one-ecoregion-out AUC."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.regulation_panel_auc_diagnosis import (
    assert_matches_frozen_primary_pooled_auc,
    diagnose_loeo_auc,
    fold_auc_table,
    json_safe,
)

DEFAULT_PREDICTIONS = (
    PROJECT_ROOT
    / "results/regulation_panel_v1_legacy_transport"
    / "leave_ecoregion_out_predictions.csv"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "results/revision"
FROZEN_PANEL_DIR = PROJECT_ROOT / "results/regulation_panel_v1_legacy_transport"
FOLD_CSV = "loeo_within_fold_auc.csv"
DIAGNOSIS_JSON = "loeo_auc_metric_diagnosis.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def reject_frozen_output(output_dir: Path) -> None:
    frozen = FROZEN_PANEL_DIR.resolve()
    target = output_dir.resolve()
    if target == frozen or frozen in target.parents:
        raise ValueError(
            "refusing to write into the frozen regulation-panel directory"
        )


def relative_to_project(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def write_diagnosis(predictions_path: Path, output_dir: Path) -> dict[str, object]:
    reject_frozen_output(output_dir)
    predictions = pd.read_csv(predictions_path)
    folds = fold_auc_table(predictions)
    diagnosis = diagnose_loeo_auc(predictions, require_frozen_primary=True)
    pooled = diagnosis["summary"]["pooled_oof_auc"]
    assert_matches_frozen_primary_pooled_auc(float(pooled))
    payload = json_safe(
        {
            **diagnosis,
            "source_predictions": relative_to_project(predictions_path),
        }
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    folds.to_csv(output_dir / FOLD_CSV, index=False)
    (output_dir / DIAGNOSIS_JSON).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    args = parse_args()
    payload = write_diagnosis(args.predictions, args.output_dir)
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
