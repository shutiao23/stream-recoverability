#!/usr/bin/env python3
"""Nested operator ablation on burned public rivers plus v2 concurrent downloads.

Does not open last-check temperatures. Does not overwrite the 5-river stop-loss
CSVs in public_rivers/. n<100 is not confirmatory. Catalog 98 / target 150.
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

from stream_recoverability.experiments.public_river_operator_ablation import (
    concurrent_enough_ids,
    load_public_river_panels,
    run_public_river_operator_ablation,
    write_operator_ablation_artifacts,
)

V1 = ROOT / "results/framework/public_rivers"
V2 = ROOT / "results/framework/public_rivers_v2"
OUTPUT = V2


def six_year_relaxation(overlap_path: Path) -> dict[str, object]:
    """Documented hatch: 3 stations / 6 years. Not the honest T2 count."""

    if not overlap_path.is_file():
        return {"n_complete_enough_6yr": 0, "used_as_t2": False}
    table = pd.read_csv(overlap_path)
    years = pd.to_numeric(table.get("overlap_years"), errors="coerce")
    days = pd.to_numeric(table.get("days_with_min_stations"), errors="coerce")
    stations = pd.to_numeric(table.get("n_stations"), errors="coerce")
    ok = stations.ge(3) & years.ge(6.0) & days.ge(4 * 365)
    return {
        "n_complete_enough_6yr": int(ok.sum()),
        "ids": sorted(table.loc[ok, "network_id"].astype(str)),
        "used_as_t2": False,
        "note": "Failure-hatch count. Honest T2 remains 3 stations / 8 years / 150 networks.",
    }


def main() -> None:
    panels = load_public_river_panels([V1, V2])
    primary = concurrent_enough_ids([V1, V2]) or set()
    result = run_public_river_operator_ablation(
        panels,
        primary_networks=sorted(primary) if primary else None,
    )
    write_operator_ablation_artifacts(result, OUTPUT)
    manifest = dict(result["manifest"])
    hatch = six_year_relaxation(V2 / "overlap.csv")
    manifest.update(
        {
            "corpus": "burned_public_rivers_plus_v2_downloads",
            "n_panels_loaded": int(len(panels)),
            "n_primary_concurrent_8yr": int(len(primary)),
            "n_complete_enough_6yr_v2_only": hatch["n_complete_enough_6yr"],
            "six_year_relaxation_used_as_t2": False,
            "best_honest_catalog_count": 98,
            "target_independent_networks": 150,
            "continents": ["north_america"],
            "last_check_temperatures_opened": False,
            "network_catalog_v1_rewritten": False,
        }
    )
    (OUTPUT / "operator_ablation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    nested = result["nested"]
    print(nested.to_string(index=False))
    print(
        json.dumps(
            {
                "formal_evidence": manifest["formal_evidence"],
                "confirmatory_eligible": manifest["confirmatory_eligible"],
                "n_networks": manifest["n_networks"],
                "n_primary_concurrent_8yr": manifest["n_primary_concurrent_8yr"],
                "n_complete_enough_6yr_v2_only": manifest["n_complete_enough_6yr_v2_only"],
                "spearman_operator_r_vs_achieved_skill": manifest[
                    "spearman_operator_r_vs_achieved_skill"
                ],
                "spearman_donor_r2_vs_achieved_skill": manifest[
                    "spearman_donor_r2_vs_achieved_skill"
                ],
                "operator_incremental_r2_station": manifest[
                    "operator_incremental_r2_station"
                ],
                "evaluate_success": manifest["evaluate_success"],
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
