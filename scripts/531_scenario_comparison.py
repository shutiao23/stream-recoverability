#!/usr/bin/env python3
"""Compare small whole-archive stress studies on matched site repetitions."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "results/wrr_review_response_20261027"
BASE = ROOT / "whole_archive"
OUT = ROOT / "scenarios"
STUDIES = {"synchronized_donors": ROOT / "scenario_donors/pilot_7",
           "heat_associated": ROOT / "scenario_heat/pilot_7"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(BASE / "trends.csv")
    keys = ["family", "mode", "station_key", "replicate", "estimator", "retention", "dependence"]
    summaries, audit, matched = [], [], []
    for name, root in STUDIES.items():
        current = pd.read_csv(root / "trends.csv")
        design = json.loads((root / "design.json").read_text())
        baseline = old.loc[old.station_key.isin(design["station_keys"])
                           & old.replicate.lt(design["replicates"])].copy()
        pairs = baseline.merge(current, on=keys, how="left",
                               suffixes=("_baseline", "_stress"), validate="one_to_one")
        pairs["available_stress"] = pairs.available_stress.fillna(False).astype(bool)
        pairs["both_available"] = pairs.available_stress & pairs.available_baseline
        matched.append(pairs.assign(scenario=name))
        for values, block in pairs.groupby(["family", "mode", "estimator", "retention", "dependence"]):
            valid = block.loc[block.both_available]
            row = dict(zip(["family", "mode", "estimator", "retention", "dependence"], values))
            row.update(scenario=name, paired_rows=len(block), both_available=len(valid),
                       baseline_availability=float(block.available_baseline.mean()),
                       stress_availability=float(block.available_stress.mean()),
                       n_stations=block.station_key.nunique(),
                       n_groups=block.independence_group_baseline.nunique(),
                       baseline_incomplete_years=float(valid.n_incomplete_baseline.mean()) if len(valid) else np.nan,
                       stress_incomplete_years=float(valid.n_incomplete_stress.mean()) if len(valid) else np.nan)
            if len(valid):
                row.update(baseline_rmse=float(np.sqrt(valid.squared_error_baseline.mean())),
                           stress_rmse=float(np.sqrt(valid.squared_error_stress.mean())))
                if "missing_coverage95_stress" in valid:
                    row.update(baseline_coverage95=float(valid.missing_coverage95_baseline.mean()),
                               stress_coverage95=float(valid.missing_coverage95_stress.mean()),
                               baseline_width95=float(valid.width95_baseline.mean()),
                               stress_width95=float(valid.width95_stress.mean()),
                               baseline_interval_score95=float(valid.interval_score95_baseline.mean()),
                               stress_interval_score95=float(valid.interval_score95_stress.mean()))
            summaries.append(row)
        for path in root.glob("*/*/replicate_*/*/design.json"):
            relative = path.relative_to(root)
            baseline_path = BASE / relative
            if not baseline_path.exists():
                continue
            scenario_design, baseline_design = json.loads(path.read_text()), json.loads(baseline_path.read_text())
            audit.append(dict(scenario=name, family=relative.parts[0], mode=relative.parts[1],
                              replicate=relative.parts[2], station=relative.parts[3],
                              identical_target_masks=scenario_design.get("masks") == baseline_design.get("masks"),
                              hidden_target_values_present=scenario_design.get("hidden_values_present_in_visible_archive"),
                              hidden_donor_values_present=scenario_design.get("hidden_donor_values_present")))
    pd.DataFrame(summaries).to_csv(OUT / "paired_summary.csv", index=False)
    pd.DataFrame(audit).to_csv(OUT / "mask_audit.csv", index=False)
    pd.concat(matched, ignore_index=True).to_csv(OUT / "matched_trends.csv", index=False)
    counts = pd.DataFrame(audit)
    if not counts.loc[counts.scenario.eq("synchronized_donors"), "identical_target_masks"].all():
        raise RuntimeError("Donor comparison did not preserve the baseline target masks")
    if counts.loc[counts.scenario.eq("synchronized_donors"), "hidden_donor_values_present"].fillna(-1).ne(0).any():
        raise RuntimeError("Some synchronized donor gaps contain visible observations")
    (OUT / "design.json").write_text(json.dumps({
        "stations": "seven stations chosen by region round-robin, five masks, not independent climates",
        "synchronized_donors": "same target-year masks are hidden from every donor in the same panel; paired with identical target masks",
        "heat_associated": "year-specific missing probabilities 0.9 or 0.18 according to air H30 relative to the first-seven-year 80th percentile; different masks and potentially different missing rates",
        "interpretation": "finite-record slopes; small, exploratory scenario sensitivity; no universal safety or causal separation of changed missingness rates"}, indent=2) + "\n")
    print(pd.DataFrame(summaries).query("estimator == 'D2' and retention == 'all' and dependence == 'independent'").to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
