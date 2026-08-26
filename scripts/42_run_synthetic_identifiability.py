#!/usr/bin/env python3
"""Run E0 synthetic identifiability and write framework artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.synthetic_identifiability import run_e0

OUTPUT = ROOT / "results/framework/synthetic_identifiability"


def _write(frame: pd.DataFrame, name: str) -> None:
    path = OUTPUT / name
    frame.to_csv(path, index=False)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = run_e0(include_coverage=False)
    _write(result["identifiability"], "identifiability.csv")
    _write(result["finite_sample"], "finite_sample.csv")
    _write(result["degeneration"]["jensen_ar1"], "jensen_acf_gap.csv")
    _write(result["degeneration"]["donor_count_inflation"], "donor_count_inflation.csv")
    pd.DataFrame([result["degeneration"]["forced_label_theorem"]]).to_csv(
        OUTPUT / "forced_label_theorem.csv", index=False
    )
    pd.DataFrame([result["degeneration"]["mixed_river_donor_r2"]]).to_csv(
        OUTPUT / "mixed_river_donor_r2.csv", index=False
    )
    pd.DataFrame([result["state_shift"]]).to_csv(OUTPUT / "state_shift.csv", index=False)
    pd.DataFrame([result["r2_comparison"]]).to_csv(OUTPUT / "r2_comparison.csv", index=False)
    manifest = {
        "status": "complete",
        "experiment": "E0_synthetic_identifiability",
        "formal_evidence": False,
        "sealed_outcomes_opened": False,
        "pass": result["pass"],
        "forced_label_theorem": result["degeneration"]["forced_label_theorem"],
        "mixed_river_donor_r2": result["degeneration"]["mixed_river_donor_r2"],
    }
    (OUTPUT / "e0_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest["pass"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
