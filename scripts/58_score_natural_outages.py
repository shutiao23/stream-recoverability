#!/usr/bin/env python3
"""Score empirically weighted natural outages on already-downloaded rivers.

Does not download last-check temperatures. Does not claim T4 passed.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.gap_triage import compare_operator_to_length_only
from stream_recoverability.experiments.natural_outage_scoring import (
    load_real_missing_blocks,
    natural_outage_summary,
    score_natural_outages,
    write_natural_outage_artifacts,
)
from stream_recoverability.experiments.public_river_operator_ablation import (
    load_public_river_panels,
)

PANEL_DIR = ROOT / "results/framework/public_rivers"
BLOCKS = ROOT / "results/framework/public_rivers/real_missing_blocks.csv"
MAINSTEM_BLOCKS = (
    ROOT / "results/framework/public_rivers/willamette_mainstem_real_missing_blocks.csv"
)
OUTPUT = ROOT / "results/framework/public_rivers"


def _load_blocks():
    frames = [load_real_missing_blocks(BLOCKS)]
    if MAINSTEM_BLOCKS.is_file():
        extra = load_real_missing_blocks(MAINSTEM_BLOCKS)
        if "network_id" not in extra.columns:
            extra["network_id"] = "willamette_mainstem"
        frames.append(extra)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    panels = load_public_river_panels(PANEL_DIR)
    blocks = _load_blocks()
    scores = score_natural_outages(panels, blocks)
    manifest = natural_outage_summary(scores)
    manifest["willamette_mainstem_blocks_in_geometry"] = bool(MAINSTEM_BLOCKS.is_file())
    manifest["willamette_mainstem_panel_scored"] = False
    if scores is not None and not scores.empty:
        triage = compare_operator_to_length_only(scores)
        triage_path = OUTPUT / "gap_triage_natural_outage.json"
        triage_path.write_text(
            json.dumps(triage, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        manifest["gap_triage"] = {
            "n_fills": triage["n_fills"],
            "n_networks": triage["n_networks"],
            "relative_improvement": triage["relative_improvement"],
            "absolute_improvement_pp": triage["absolute_improvement_pp"],
            "passed_numeric_floors": triage["passed_numeric_floors"],
            "passed": False,
            "headline_claim_licensed": False,
        }
    write_natural_outage_artifacts(scores, manifest, OUTPUT)
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
