#!/usr/bin/env python3
"""Step 7: generative mechanism battery that can refute a universal threshold."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.mechanism import (  # noqa: E402
    SCENARIOS,
    score_scenario,
    scenario_verdict,
)
from stream_recoverability.experiments.wrr_revision.paths import RESULTS_ROOT  # noqa: E402

OUTPUT = RESULTS_ROOT / "step7_mechanism"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frames = [score_scenario(name, seed=1) for name in SCENARIOS]
    scores = pd.concat(frames, ignore_index=True)
    scores.to_csv(OUTPUT / "scenario_scores.csv", index=False)
    verdict = scenario_verdict(scores)
    verdict.to_csv(OUTPUT / "verdict.csv", index=False)
    law_retained = bool(
        verdict.loc[verdict["recoverer"].eq("structurally_correct"), "crossed"].all()
        and verdict.loc[verdict["recoverer"].eq("neighbor_ridge"), "crossed"].all()
    )
    summary = {
        "n_scenarios": int(len(SCENARIOS)),
        "structurally_correct_always_crosses": bool(
            verdict.loc[verdict["recoverer"].eq("structurally_correct"), "crossed"].all()
        ),
        "neighbor_always_crosses": bool(
            verdict.loc[verdict["recoverer"].eq("neighbor_ridge"), "crossed"].all()
        ),
        "retain_universal_law": law_retained,
        "decision": (
            "retain_law_claim"
            if law_retained
            else "drop_law_claim_write_as_prediction_and_decision"
        ),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(verdict.to_string(index=False))


if __name__ == "__main__":
    main()
