#!/usr/bin/env python3
"""P0-05 / F04: paired position–length controls on a common feasible region.

For each (station, year, estimator, donor set) with multiple designed
realizations, compare:
  - fixed length, varying overlap class
  - fixed overlap class, varying length
Only cells with ≥2 overlap classes at the same length enter the position test;
only cells with ≥2 lengths at the same overlap class enter the length test.

Writes amendments/position_length_paired/. Title-grade "governs" language remains
withdrawn unless both contrasts are stable with intervals excluding zero.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = ROOT / "results" / "wrr_submission_ready" / "amendments" / "position_length_paired"
LENGTHS = (30, 60, 90)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet")
    cases = cases.loc[cases["longest_run"].isin(LENGTHS)].copy()
    cases["abserr"] = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    cases["hidden"] = pd.to_numeric(cases["true_peak_hidden_fraction"], errors="coerce")

    # Feasible region inventory (audit claim: most length×station-year have one overlap).
    key = ["network_id", "station_id", "year", "longest_run"]
    n_overlap = cases.groupby(key)["overlap_class"].nunique().rename("n_overlap_class")
    inventory = n_overlap.reset_index()
    inventory.to_csv(OUT / "feasibility_inventory.csv", index=False)

    multi = inventory.loc[inventory["n_overlap_class"] >= 2]
    paired_pos = cases.merge(multi[key], on=key, how="inner")
    # Position effect: within (station,year,length), range of mean abserr across overlap classes
    pos = (
        paired_pos.groupby(key + ["overlap_class"], as_index=False)["abserr"]
        .mean()
        .groupby(key)["abserr"]
        .agg(position_range=lambda s: float(s.max() - s.min()), n_classes="count")
        .reset_index()
    )
    pos.to_csv(OUT / "position_effect_within_length.csv", index=False)

    key_len = ["network_id", "station_id", "year", "overlap_class"]
    n_len = cases.groupby(key_len)["longest_run"].nunique().rename("n_lengths")
    multi_len = n_len.reset_index().loc[lambda d: d["n_lengths"] >= 2]
    paired_len = cases.merge(multi_len[key_len], on=key_len, how="inner")
    length_eff = (
        paired_len.groupby(key_len + ["longest_run"], as_index=False)["abserr"]
        .mean()
        .groupby(key_len)["abserr"]
        .agg(length_range=lambda s: float(s.max() - s.min()), n_lengths="count")
        .reset_index()
    )
    length_eff.to_csv(OUT / "length_effect_within_overlap.csv", index=False)

    # Counterexample: true peak not hidden but error > 0.5 C
    counter = cases.loc[(cases["hidden"].fillna(1) <= 0) & (cases["abserr"] > 0.5)]
    counter_path = OUT / "false_peak_counterexamples.csv"
    counter.head(500).to_csv(counter_path, index=False)

    summary = {
        "n_cases_in_length_subset": int(len(cases)),
        "n_station_year_length_with_ge2_overlap": int(len(multi)),
        "share_with_ge2_overlap": float(len(multi) / max(1, len(inventory))),
        "n_station_year_overlap_with_ge2_lengths": int(len(multi_len)),
        "mean_position_range_abserr_C": float(pos["position_range"].mean()) if len(pos) else None,
        "mean_length_range_abserr_C": float(length_eff["length_range"].mean()) if len(length_eff) else None,
        "n_false_peak_counterexamples_dev": int(len(counter)),
        "title_claim": "withdraw_governs_until_paired_region_rebuilt",
        "note": (
            "Current design draws one overlap class per station-year-length, so the "
            "paired position cell is nearly empty by construction. A new case build "
            "must cross length × overlap on a common feasible region before any "
            "dominance claim."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
