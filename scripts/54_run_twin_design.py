#!/usr/bin/env python3
"""Run the Phase 2 synthetic twin design and write synthetic_v2 artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.twin_design import run_twin_design

OUTPUT = ROOT / "results/framework/synthetic_v2"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = run_twin_design()
    nodes = result["node_scores"]
    aucs = result["aucs"]
    gate = result["gate"]
    nodes.to_csv(OUTPUT / "twin_node_scores.csv", index=False)
    aucs.to_csv(OUTPUT / "twin_auc.csv", index=False)
    manifest = {
        "status": "complete",
        "experiment": "E5_twin_design",
        "formal_evidence": False,
        "sealed_outcomes_opened": False,
        "headline_claim_licensed": False,
        "gap_length": 90,
        "n_graphs": result["n_graphs"],
        "topologies": result["topologies"],
        "cells": result.get("cells"),
        "predictors": {
            "operator": "recoverability_r / operator_risk=1-R at gap 90 from known Sigma",
            "univariate": [
                "contemporaneous donor R2",
                "lag-30 ACF",
                "legacy additive d/4 memory component and hard label",
                "mean hop distance to other stations",
            ],
        },
        "gate": gate,
        "identifiability_status": gate["identifiability_status"],
        "note": (
            "Known-dynamics twin design. Not confirmation. Not formal evidence. "
            "If the operator cannot separate dam-like vs not, status is inseparable "
            "and the generator is not retuned to save the gate. "
            "The 2x2 cells are dam×interior, ordinary×endpoint, dam×endpoint, "
            "and ordinary×interior. Hard-negative AUC uses only interior dams "
            "versus ordinary endpoints."
        ),
    }
    (OUTPUT / "twin_design_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(gate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
