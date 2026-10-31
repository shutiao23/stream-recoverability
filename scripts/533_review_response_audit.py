#!/usr/bin/env python3
"""Audit the revised on-disk predictions and calibration support."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1] / "results/wrr_review_response_20261027"
ARCHIVE = ROOT / "whole_archive"
OUT = ROOT / "audit"
LEVELS = (5, 10, 25, 50, 75, 90, 95)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for family in ["calendar", "crossed"]:
        for mode in ["offline", "forward"]:
            paths = sorted((ARCHIVE / family / mode).glob("replicate_*/*/annual_predictions.parquet"))
            counters = {prefix: {"n_comparable":0, "n_below_1e8":0, "max_violation":0.0}
                        for prefix in ["D2", "stochastic_cal", "state_cal"]}
            hidden_target = 0
            for path in paths:
                design = json.loads((path.parent / "design.json").read_text())
                hidden_target += design.get("hidden_values_present_in_visible_archive", 0)
                if pq.ParquetFile(path).metadata.num_rows == 0:
                    continue
                columns = ["observed_lower_bound__observed_days"] + [
                    f"{prefix}_q{level:02d}"
                    for prefix in counters for level in LEVELS
                ]
                frame = pd.read_parquet(path, columns=columns)
                lower = frame.observed_lower_bound__observed_days.to_numpy(float)
                for prefix, counts in counters.items():
                    for level in LEVELS:
                        value = frame[f"{prefix}_q{level:02d}"].to_numpy(float)
                        good = np.isfinite(lower) & np.isfinite(value)
                        gap = lower[good] - value[good]
                        counts["n_comparable"] += int(good.sum())
                        counts["n_below_1e8"] += int((gap > 1e-8).sum())
                        if len(gap):
                            counts["max_violation"] = max(counts["max_violation"], float(gap.max()))
            for method, counts in counters.items():
                rows.append(dict(family=family, mode=mode, estimator=method,
                                 n_archive_files=len(paths), hidden_target_values=hidden_target, **counts))
    audit = pd.DataFrame(rows)
    audit.to_csv(OUT / "annual_support_audit.csv", index=False)
    task = pd.read_csv(ARCHIVE / "task_calibrated_trends.csv")
    zero = task.loc[task.width95.le(1e-8) & task.n_incomplete.gt(0)]
    sources = pd.read_csv(ARCHIVE / "task_calibration_sources.csv")
    unsupported = sources.loc[sources.status.eq("supported") & sources.n_source_groups.lt(3)]
    masks = pd.read_csv(ROOT / "scenarios/mask_audit.csv")
    donor = masks.loc[masks.scenario.eq("synchronized_donors")]
    integrated = pd.read_csv(ROOT / "integrated_release_trend/station_repetitions.csv")
    partition_bad = integrated.n_estimates + integrated.n_bounds + integrated.n_unknown != integrated.n_masked
    decisions_path = ROOT / "integrated_release_trend/annual_decisions.parquet"
    if not decisions_path.exists():
        raise RuntimeError("Integrated annual release decisions have not yet been recorded")
    decisions = pd.read_parquet(decisions_path)
    evaluated = decisions.output_state.eq("estimate") & decisions.observed_lower_bound.notna()
    released_below = (decisions.loc[evaluated, "released_estimate"] <
                      decisions.loc[evaluated, "observed_lower_bound"] - 1e-8).sum()
    status = dict(
        n_annual_quantiles_below_observed_bound=int(audit.n_below_1e8.sum()),
        n_hidden_target_values_present=int(audit.groupby(["family", "mode"]).hidden_target_values.first().sum()),
        n_zero_width_task_intervals_on_incomplete_archives=len(zero),
        n_supported_task_models_below_three_source_groups=len(unsupported),
        n_synchronized_donor_cases_with_different_masks=int((~donor.identical_target_masks).sum()),
        n_synchronized_donor_cases_with_visible_hidden_donors=int(donor.hidden_donor_values_present.fillna(-1).ne(0).sum()),
        n_integrated_release_denominator_errors=int(partition_bad.sum()),
        n_integrated_estimates_below_observed_bound=int(released_below),
        independent_climate_coverage_guarantee=False,
    )
    (OUT / "scientific_checks.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2), flush=True)
    if any(status[k] for k in status if k.startswith("n_")):
        raise RuntimeError("A revised scientific support invariant did not hold")


if __name__ == "__main__":
    main()
