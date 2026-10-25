#!/usr/bin/env python3
"""TR-E7c (post hoc): why the frozen thresholds failed in Australia.

Written after the sealed evaluation; nothing here changes or re-scores the
sealed result. It compares recoverability parameters, real gap calendars,
score distributions and P(failure | score) between the source and Australia,
and checks the hemisphere hypothesis (peak month, year boundary).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e7_sealed"
SEALED = T.load_script("tr_sealed_for_diag", T.ROOT / "scripts/439_tr_e7_sealed.py")
E5 = T.load_script("tr_e5_for_diag", T.ROOT / "scripts/436_tr_e5_rules.py")


def prepare(path: Path, pipeline: dict) -> pd.DataFrame:
    cases = pd.read_parquet(path)
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof, _ = SEALED.predict(cases, pipeline)
    levels = tuple(pipeline["levels"])
    q = oof[[f"h30__{pipeline['d2']}_q{int(level * 100):02d}" for level in levels]].to_numpy()
    cases["d2_point"] = q[:, levels.index(0.5)]
    cases["score"] = E5.predictive_pfail(q, levels, cases.d2_point.to_numpy(), pipeline["tolerance_c"])
    cases["covered90"] = (cases.eval_truth_h30 >= q[:, 0]) & (cases.eval_truth_h30 <= q[:, -1])
    cases["fail_D2"] = (cases.d2_point - cases.eval_truth_h30).abs() > pipeline["tolerance_c"]
    cases["fail_P0"] = (cases.h30__policy - cases.eval_truth_h30).abs() > pipeline["tolerance_c"]
    cases["r2"] = 1 - cases.law_sigma_r_warm**2 / cases.law_sigma_a**2
    return cases


def main() -> int:
    pipeline = json.loads(SEALED.PIPELINE.read_text())
    # The frozen models were fitted on all source cases, so source scores here are in-sample; they are used
    # only for distributions, not for performance claims.
    source = prepare(T.OUT / "e2_cases/cases.parquet", pipeline)
    au = prepare(OUT / "cases.parquet", pipeline)
    rows = []
    for name, frame in (("source", source), ("australia", au)):
        for family in ("calendar", "crossed"):
            block = frame.loc[frame.design_family.eq(family)]
            rows.append({
                "domain": name, "family": family, "n": len(block), "air_layer_share": float(block.policy_choice.eq("air_ridge").mean()),
                "median_sigma_a": float(block.law_sigma_a.median()), "median_sigma_r": float(block.law_sigma_r_warm.median()), "median_r2": float(block.r2.median()),
                "median_phi_r": float(block.law_phi_r.median()), "median_missing_fraction": float(block.missing_fraction.median()),
                "share_peak_overlap_half": float(block.peak_overlap.ge(0.5).mean()), "failure_P0": float(block.fail_P0.mean()), "failure_D2": float(block.fail_D2.mean()),
                "mean_error_P0": float((block.h30__policy - block.eval_truth_h30).mean()), "coverage90_D2": float(block.covered90.mean()),
                "median_score": float(block.score.median()),
            })
    contrast = pd.DataFrame(rows)
    contrast.to_csv(OUT / "posthoc_domain_contrast.csv", index=False)
    bins = [-0.01, 0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    calibration = []
    for name, frame in (("source", source), ("australia", au)):
        block = frame.loc[frame.design_family.eq("calendar")]
        grouped = block.groupby(pd.cut(block.score, bins), observed=True).agg(n=("fail_D2", "size"), failure=("fail_D2", "mean"), mean_score=("score", "mean"))
        grouped.insert(0, "domain", name)
        calibration.append(grouped.reset_index().astype({"score": str}))
    pd.concat(calibration).to_csv(OUT / "posthoc_conditional_shift.csv", index=False)
    au["peak_month"] = ((au.eval_truth_peak_doy - 1) // 30.5 + 1).clip(1, 12).astype(int)
    au.groupby("peak_month").agg(n=("fail_P0", "size"), failure_P0=("fail_P0", "mean"), mean_error_P0=("eval_truth_h30", lambda s: float((au.loc[s.index, "h30__policy"] - s).mean()))).reset_index().to_csv(OUT / "posthoc_peak_month.csv", index=False)
    print(contrast.round(3).to_string(), flush=True)
    print(pd.concat(calibration).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
