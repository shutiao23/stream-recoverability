#!/usr/bin/env python3
"""Stop-loss nested ablation on already-downloaded public rivers.

Does not download temperatures. Does not open sealed catalog rivers.
Does not rewrite leave_one_river_out.csv. n<<100 is not confirmatory.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.public_river_operator_ablation import (
    concurrent_enough_ids,
    load_public_river_panels,
    run_public_river_operator_ablation,
    write_operator_ablation_artifacts,
)

OUTPUT = ROOT / "results/framework/public_rivers"


def main() -> None:
    panels = load_public_river_panels(OUTPUT)
    primary = concurrent_enough_ids(OUTPUT)
    result = run_public_river_operator_ablation(
        panels,
        primary_networks=sorted(primary) if primary is not None else None,
    )
    write_operator_ablation_artifacts(result, OUTPUT)
    manifest = result["manifest"]
    nested = result["nested"]
    print(nested.to_string(index=False))
    print(
        json.dumps(
            {
                "formal_evidence": manifest["formal_evidence"],
                "headline_claim_licensed": manifest["headline_claim_licensed"],
                "confirmatory_eligible": manifest["confirmatory_eligible"],
                "n_networks": manifest["n_networks"],
                "clearwater_dropped": manifest["clearwater_dropped"],
                "dropped_insane_mae_networks": manifest["dropped_insane_mae_networks"],
                "donor_r2_estimator": manifest["donor_r2_estimator"],
                "spearman_operator_r_vs_achieved_skill": manifest[
                    "spearman_operator_r_vs_achieved_skill"
                ],
                "spearman_donor_r2_vs_achieved_skill": manifest[
                    "spearman_donor_r2_vs_achieved_skill"
                ],
                "operator_incremental_r2_station": manifest[
                    "operator_incremental_r2_station"
                ],
                "operator_incremental_r2_le_0": manifest["operator_incremental_r2_le_0"],
                "incremental_note": manifest["incremental_note"],
                "primary_networks": manifest["primary_networks"],
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
