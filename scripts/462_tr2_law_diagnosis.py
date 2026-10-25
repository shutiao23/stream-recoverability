#!/usr/bin/env python3
"""TR2-S2: why the recovery law underestimates failure in the hardest cells.

For each cell of gap length x peak overlap x information layer (controlled
gaps), the observed plug-in errors are compared with the law's predictive
distribution: the ratio of observed to predicted error variance, the share of
standardised errors beyond two predicted standard deviations (4.6% if the law's
normal shape held), the excess kurtosis of the errors, and the ratio of the
reconstruction residual's standard deviation inside the training peak windows
to its warm-season value (heteroscedasticity in hot periods). The
peak-conditional version v2p, which uses the peak-window residual moments, is
the simple correction suggested by the review.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis

import wrr_tr_common as T

OUT = T.OUT / "e3_recovery_law"


def main() -> int:
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    law = pd.read_parquet(OUT / "law_predictions.parquet")
    if not (law.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("Law predictions are not aligned with the cases")
    tolerance = T.settings()["tolerance_c"]
    mech = cases.design_family.eq("crossed").to_numpy()
    frame = pd.DataFrame({
        "gap_length": cases.gap_length, "overlap_class": cases.overlap_class, "layer": cases.policy_choice.where(cases.policy_choice.isin(["donor_ridge", "air_ridge"]), "other"),
        "error": cases.h30__policy - cases.eval_truth_h30, "law_bias": law.law_bias, "law_sd": law.law_sd, "law_pfail": law.law_pfail_050,
        "v2p_bias": law.law_v2p_bias, "v2p_sd": law.law_v2p_sd, "v2p_pfail": law.law_v2p_pfail_050,
        "hetero": cases.law_sigma_r_peak / cases.law_sigma_r_warm,
    }).loc[mech]
    frame["fail"] = (frame.error.abs() > tolerance).astype(float)
    frame["z"] = (frame.error - frame.law_bias) / frame.law_sd
    rows = []
    for (length, overlap, layer), block in frame.groupby(["gap_length", "overlap_class", "layer"]):
        if len(block) < 200:
            continue
        rows.append({
            "gap_length": int(length), "overlap_class": overlap, "layer": layer, "n": len(block), "observed_failure": float(block.fail.mean()),
            "law_v2_pfail": float(block.law_pfail.mean()), "law_v2p_pfail": float(block.v2p_pfail.mean()),
            "variance_ratio_observed_to_v2": float(block.error.var() / np.mean(block.law_sd**2 + block.law_bias**2 - block.law_bias.mean() ** 2)),
            "share_beyond_2sd_v2": float((block.z.abs() > 2).mean()), "excess_kurtosis": float(kurtosis(block.error, fisher=True)),
            "median_peak_to_warm_residual_sd": float(block.hetero.median()),
        })
    table = pd.DataFrame(rows).sort_values("observed_failure", ascending=False)
    table.to_csv(OUT / "hard_cell_diagnosis.csv", index=False)
    hardest = table.head(5)
    summary = {
        "hardest5_observed_failure": float(np.average(hardest.observed_failure, weights=hardest.n)),
        "hardest5_v2": float(np.average(hardest.law_v2_pfail, weights=hardest.n)), "hardest5_v2p": float(np.average(hardest.law_v2p_pfail, weights=hardest.n)),
        "hardest5_variance_ratio": float(np.average(hardest.variance_ratio_observed_to_v2, weights=hardest.n)),
        "hardest5_share_beyond_2sd": float(np.average(hardest.share_beyond_2sd_v2, weights=hardest.n)),
        "hardest5_excess_kurtosis": float(np.average(hardest.excess_kurtosis, weights=hardest.n)),
        "all_cells_share_beyond_2sd": float((frame.z.abs() > 2).mean()),
        "median_peak_to_warm_residual_sd_all": float(frame.hetero.median()),
        "median_peak_to_warm_residual_sd_hardest5": float(np.average(hardest.median_peak_to_warm_residual_sd, weights=hardest.n)),
        "role": "post hoc diagnosis requested by the second review (S2)",
    }
    T.write_json(OUT / "hard_cell_diagnosis.json", summary)
    print(table.round(3).to_string(), flush=True)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
