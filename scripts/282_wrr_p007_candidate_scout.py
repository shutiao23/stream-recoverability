#!/usr/bin/env python3
"""P0-07: scout never-used networks for a new confirmation panel.

Does not score. Writes a recruitment worksheet under
amendments/p0_07_new_confirmation_scout/ from existing catalogs and prior-access
ledgers. Human/provider download steps remain.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "p0_07_new_confirmation_scout"


def main() -> int:
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    used = set()
    for path in [
        READY / "confirmation_inputs_manifest.csv",
        READY / "multi_agency_inputs_manifest.csv",
        ROOT / "results/v17_fitness/step1_panel/network_split.csv",
    ]:
        if path.is_file():
            frame = pd.read_csv(path)
            col = "network_id" if "network_id" in frame.columns else None
            if col:
                used.update(frame[col].astype(str))

    # Existing recruitment leftovers
    candidates = []
    for path in [
        READY / "confirmation_recruitment_pool.csv",
        READY / "nve_confirmation_candidates.csv",
        READY / "confirmation_external_worksheet.csv",
    ]:
        if not path.is_file():
            continue
        frame = pd.read_csv(path)
        frame["source_file"] = str(path.relative_to(ROOT))
        candidates.append(frame)

    if not candidates:
        summary = {
            "status": "no_local_candidate_tables",
            "n_used_networks_seen": len(used),
            "next_steps": [
                "Query USGS NWIS for HUC4 clusters outside used set with ≥2 stations ≥4 complete years",
                "Add non-development agencies (e.g. additional Hub'Eau basins, EA, SMHI catchments not in transport)",
                "Run scripts/245-style prior-access audit before sealing",
                "Seal under P0_07_NEW_CONFIRMATION_PROTOCOL_DRAFT.md then score once",
            ],
        }
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        return 0

    pool = pd.concat(candidates, ignore_index=True, sort=False)
    if "network_id" in pool.columns:
        pool["already_used"] = pool["network_id"].astype(str).isin(used)
    else:
        pool["already_used"] = False
    pool.to_csv(OUT / "candidate_union.csv", index=False)
    free = pool.loc[~pool["already_used"]] if "already_used" in pool.columns else pool
    summary = {
        "status": "worksheet_written",
        "n_used_networks_seen": len(used),
        "n_candidate_rows": int(len(pool)),
        "n_not_already_used": int(len(free)),
        "protocol": str(
            (READY / "P0_07_NEW_CONFIRMATION_PROTOCOL_DRAFT.md").relative_to(ROOT)
        ),
        "floors": {
            "min_networks": 30,
            "min_providers": 3,
            "min_contexts": 3,
            "min_stations_per_network": 2,
            "min_complete_years": 4,
        },
        "note": (
            "Opened USGS/transport panels are exhausted for first confirmation. "
            "New downloads required; do not unseal-score until QA+prior-access freeze."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
