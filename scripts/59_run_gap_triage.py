#!/usr/bin/env python3
"""T3(b) gap triage on W2 gap-specific scored fills.

Development only; floors stay locked.  This entry point deliberately refuses the
legacy later-year network table because it does not contain one outcome per
planted gap.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.gap_triage import compare_operator_to_length_only

OUTPUT = ROOT / "results/framework/public_rivers"
W2_OUTPUT = OUTPUT / "w2_phase4_gap_specific"
W2_SCORES = W2_OUTPUT / "operator_station_scores.csv"


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _load_scores(path: Path = W2_SCORES) -> pd.DataFrame:
    if not path.is_file():
        raise SystemExit(f"need W2 gap-specific station scores: {path}")
    frame = pd.read_csv(path)
    required = {
        "network_id",
        "gap_length",
        "fill_mae",
        "predicted_conditional_risk",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"gap-specific score table is missing columns: {missing}")
    if frame.empty:
        raise SystemExit("W2 gap-specific station score table is empty")
    if "achieved_skill_mode" not in frame.columns:
        raise SystemExit("refusing unlabeled scores: achieved_skill_mode is required")
    modes = set(frame["achieved_skill_mode"].dropna().astype(str))
    if modes != {"gap_specific"}:
        raise SystemExit(f"refusing non-gap-specific achieved-skill modes: {sorted(modes)}")
    return frame


def main() -> None:
    scores = _load_scores()
    result = compare_operator_to_length_only(scores)
    payload = _jsonable(result)
    W2_OUTPUT.mkdir(parents=True, exist_ok=True)
    (W2_OUTPUT / "gap_triage.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
