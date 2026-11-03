#!/usr/bin/env python3
"""Descriptive reviewer diagnostics on fixed saved predictions.

No source model, manuscript, production result or release receipt is changed.
The seed list is 0..19 plus the published extension seed, fixed before running.
These diagnostics are exploratory and are not independent validation.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/wrr_comprehensive_review_20261102"
DATA = ROOT / "results/wrr_final_revision_20261031"
KEY = ["station_key", "replicate", "independence_group"]
SEEDS = [*range(20), 20261031]
SCHEMES = ["cdf_all_years", "sxx_all_years", "all"]
DRAWS = 10000


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_csv(DATA / "retention_geometry_cases.csv")
    account = pd.read_csv(DATA / "retention_choice_counts.csv")
    comparisons, intervals, composition = [], [], []
    for family, block in cases.groupby("family"):
        wide = block.pivot(index=KEY, columns="scheme", values="estimate_mse")
        years = block.pivot(index=KEY, columns="scheme", values="retained_years")
        labels = wide.index.get_level_values("independence_group")
        groups = sorted(set(labels))
        group_counts = np.array([(labels == group).sum() for group in groups])
        sums = {scheme: np.array([wide.loc[labels == group, scheme].sum() for group in groups])
                for scheme in ["warm90", *SCHEMES]}
        for scheme in SCHEMES:
            difference = np.sqrt(wide[scheme]) - np.sqrt(wide["warm90"])
            different_set = years[scheme].ne(years["warm90"])
            for subset, keep in [("all_archives", np.ones(len(wide), dtype=bool)),
                                 ("changed_year_set", different_set.to_numpy())]:
                diff = difference.iloc[np.flatnonzero(keep)]
                comparisons.append({"family": family, "scheme": scheme, "subset": subset,
                                    "n": len(diff), "smaller_absolute_error": int((diff < -1e-12).sum()),
                                    "larger_absolute_error": int((diff > 1e-12).sum()),
                                    "numerically_equal": int((diff.abs() <= 1e-12).sum()),
                                    "median_absolute_error_change": float(diff.median())})
        for seed in SEEDS:
            rng = np.random.default_rng(seed)
            multiplicity = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)), size=DRAWS)
            denominator = multiplicity @ group_counts
            reference = np.sqrt((multiplicity @ sums["warm90"]) / denominator)
            for scheme in SCHEMES:
                change = np.sqrt((multiplicity @ sums[scheme]) / denominator) - reference
                low, high = np.quantile(change, [0.025, 0.975])
                intervals.append({"family": family, "scheme": scheme, "seed": seed,
                                  "draws": DRAWS, "groups": len(groups), "n": len(wide),
                                  "ci_low": float(low), "ci_high": float(high),
                                  "contains_zero": bool(low <= 0 <= high)})
        distinct = block[["station_key", "independence_group", "region"]].drop_duplicates()
        family_account = account.loc[account.family.eq(family)]
        composition.append({"family": family, "archives": len(wide), "stations": distinct.station_key.nunique(),
                            "groups": len(groups), "station_counts_by_region": distinct.groupby("region").station_key.nunique().to_dict(),
                            "largest_group_archive_share": float(group_counts.max() / group_counts.sum()),
                            "nontrivial_choice_archives": int(family_account.choice.sum()),
                            "all_incomplete_already_kept": int(family_account.all_incomplete_kept.sum())})
    pairs = pd.DataFrame(comparisons)
    bootstrap = pd.DataFrame(intervals)
    pairs.to_csv(OUT / "archive_level_comparisons.csv", index=False)
    bootstrap.to_csv(OUT / "bootstrap_seed_sensitivity.csv", index=False)
    summary = []
    for (family, scheme), block in bootstrap.groupby(["family", "scheme"]):
        summary.append({"family": family, "scheme": scheme, "seed_count": len(block),
                        "intervals_containing_zero": int(block.contains_zero.sum()),
                        "lower_endpoint_min": float(block.ci_low.min()), "lower_endpoint_max": float(block.ci_low.max()),
                        "upper_endpoint_min": float(block.ci_high.min()), "upper_endpoint_max": float(block.ci_high.max())})
    report = {"scope": "Post-hoc reviewer diagnostics on the same saved predictions and same cohorts; no model refit, no new independent evidence.",
              "absolute_error_tie_tolerance": 1e-12,
              "tie_tolerance_unit": "degrees C per decade; numerical equality only, not practical equivalence",
              "bootstrap_seeds": SEEDS, "draws_per_seed": DRAWS,
              "archive_comparisons": comparisons, "bootstrap_sensitivity": summary, "composition": composition}
    (OUT / "scope_diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"all_retained_comparisons": pairs.loc[pairs.scheme.eq("all")].to_dict("records"),
                      "bootstrap": summary, "composition": composition}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
