#!/usr/bin/env python3
"""Scratch dry run: exercise the F12 report/contrast path on synthetic data.

Not part of the deliverable. It exists so a shape bug in the reporting code is
caught in seconds rather than after a ten-minute worker pass.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

spec = importlib.util.spec_from_file_location("f12_script", ROOT / "scripts" / "247_wrr_mechanism_equal_k.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

rng = np.random.default_rng(0)
rows = []
for network in ("n1", "n2", "n3", "n4"):
    for station in ("s1", "s2"):
        for year in (2018, 2019):
            for k in (1, 2, 3):
                for overlap in ("none", "partial", "full"):
                    base = float(rng.uniform(0.05, 0.5))
                    rows.append(
                        {
                            "network_id": network,
                            "station_id": station,
                            "year": year,
                            "realization_id": f"s{k}_{overlap}",
                            "arm": "stratified",
                            "overlap_class": overlap,
                            "k_matched": k,
                            "k_orig_diff": int(rng.integers(-1, 2)),
                            "n_visible_strong": k + int(rng.integers(0, 3)),
                            "n_visible_weak": k + int(rng.integers(0, 3)),
                            "k_nominal": 4,
                            "n_strong_orig": k + int(rng.integers(0, 2)),
                            "n_weak_orig": k + int(rng.integers(0, 2)),
                            "corr_strong_mean_orig": 0.9,
                            "corr_weak_mean_orig": 0.7,
                            "corr_strong_mean_top_of_half": 0.9,
                            "corr_weak_mean_top_of_half": 0.7,
                            "abserr_strong_orig": base,
                            "abserr_weak_orig": base + 0.08,
                            "abserr_strong_top_of_half": base,
                            "abserr_weak_top_of_half": base + 0.09,
                            "abserr_strong_gap_minimising": base + 0.01,
                            "abserr_weak_gap_minimising": base + 0.06,
                            "abserr_strong_gap_maximising": base - 0.01,
                            "abserr_weak_gap_maximising": base + 0.10,
                            "abserr_all_donors": base + 0.02,
                            "abserr_anomaly_shuffled": base + 0.25,
                        }
                    )
frame = pd.DataFrame(rows)

contrasts = script.build_contrasts(frame)
arms = script.build_arm_table(frame)
k_table = script.build_k_table(frame)
matched_primary = contrasts.loc[contrasts["spec"] == "matched_exact_k"]
stratified_row = contrasts.loc[contrasts["spec"] == "matched_exact_k_stratified"].iloc[0]
matched_rows = list(matched_primary.itertuples()) + [stratified_row]
verdict = {
    "claim_survives_exact_k": bool(all(float(r.ci_low_c) > 0.0 for r in matched_rows)),
    "min_matched_ci_low_c": float(min(float(r.ci_low_c) for r in matched_rows)),
    "rule": "synthetic",
}
paired_orig = script._paired(frame, "abserr_weak_orig", "abserr_strong_orig")
paired_matched = script._paired(frame, "abserr_weak_top_of_half", "abserr_strong_top_of_half")
retention = {
    "n_paired_original_only": 0,
    "n_paired_matched_only": 3,
    "share_matched_only_where_truncated": 0.9,
    "mean_visible_strong_matched_only": 3.1,
    "mean_k_matched_only": 2.1,
    "n_cases_total": len(frame),
    "n_cases_with_unequal_counts": int((frame["k_orig_diff"] != 0).sum()),
    "share_cases_with_unequal_counts": float((frame["k_orig_diff"] != 0).mean()),
    "max_abs_count_gap": int(frame["k_orig_diff"].abs().max()),
    "n_paired_original": len(paired_orig),
    "n_paired_matched": len(paired_matched),
    "paired_retention": len(paired_matched) / len(paired_orig),
    "n_networks_matched": int(paired_matched["network_id"].nunique()),
    "n_strata": int(paired_matched.groupby(["arm", "overlap_class", "k_matched"]).ngroups),
    "mean_abs_count_gap_paired": float(paired_orig["k_orig_diff"].abs().mean()),
    "max_abs_count_gap_paired": int(paired_orig["k_orig_diff"].abs().max()),
    "share_strong_truncated": 0.5,
    "share_weak_truncated": 0.4,
    "share_positive_matched_cases": float(
        (paired_matched["abserr_weak_top_of_half"] > paired_matched["abserr_strong_top_of_half"]).mean()
    ),
}
reproduction = {
    "reproduces_frozen_generation": True,
    "frozen_n_paired": 5712,
    "recomputed_original_n_paired": 5712,
    "frozen_point_c": 0.08241046300708349,
    "recomputed_original_point_c": 0.08241046300708349,
    "point_abs_diff_c": 0.0,
    "frozen_ci": [0.0605, 0.1121],
    "recomputed_original_ci": [0.0605, 0.1121],
    "frozen_n_cases": 16103,
    "recomputed_n_cases": int(len(frame)),
    "frozen_controls_block": {},
    "frozen_controls_block_empty": True,
    "frozen_distribution": {},
    "case_level": {
        "longest_run_agreement": 0.77,
        "joined_cases": 16080,
        "frozen_cases": 16103,
        "donor_count_agreement": 1.0,
        "strong_max_abs_diff_c": 0.0,
        "weak_max_abs_diff_c": 0.0,
    },
}
hazard = {
    "stale_table_preserved": True,
    "summary_claims_zero_controls": True,
    "mixed_generation_state": True,
    "new_guard_error": "donor control produced no rows",
    "verify_generation_error": "no MANIFEST.json",
}
audit = {"n_rows": int(len(frame))}
provenance = {
    "frozen_mtimes_utc": {
        "donor_control_contrasts.csv": "2026-09-23 12:47:19Z",
        "donor_control_summary.csv": "2026-09-23 12:47:15Z",
        "donor_controls.parquet": "2026-09-23 12:47:06Z",
        "summary.json": "2026-09-23 20:55:41Z",
    }
}
out = Path(__file__).resolve().parent / "f12_dryrun_REPORT.md"
distributions = {
    "matched_exact_k_top_of_half": script.distribution_stats(
        frame.loc[frame["k_matched"] >= 1], "abserr_weak_top_of_half", "abserr_strong_top_of_half"
    ),
    "unmatched_original": script.distribution_stats(frame, "abserr_weak_orig", "abserr_strong_orig"),
    "frozen_original": {},
}
text = script.write_report(
    out,
    distributions=distributions,
    contrasts=contrasts,
    arms=arms,
    k_table=k_table,
    retention=retention,
    reproduction=reproduction,
    hazard=hazard,
    audit=audit,
    provenance=provenance,
    verdict=verdict,
)
print(f"dry run wrote {out} ({len(text)} chars)")
print(contrasts[["spec", "selection_rule", "n_paired", "point_c", "ci_low_c", "ci_high_c"]].to_string(index=False))
print(json.dumps({"headline_rows": int(len(contrasts))}, indent=2))
