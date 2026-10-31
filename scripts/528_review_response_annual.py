#!/usr/bin/env python3
"""Re-score the 20 historical source fits after equal support projection.

The original held-region model weights and independent quantile offsets are
retained, because only seed-zero fitted model weights were archived. Both
annual methods receive the same projection after their original calibration.
Normal-spacing tails are a stated approximation, not a new fit or guarantee.
"""
from __future__ import annotations
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

import argparse
from pathlib import Path
import json
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import norm
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.archive import LEVELS, apply_observed_lower_bound
from stream_recoverability.experiments.tr_revision.statistics import ensemble_crps, interval_score

OUT = T.ROOT / "results/wrr_review_response_20261027/annual"


def quantile_samples(q, bounds, draws=128):
    """Vectorized version of the same fixed-support normal-spacing approximation."""
    q = apply_observed_lower_bound(q, bounds)
    u = (np.arange(draws) + .5) / draws
    j = np.clip(np.searchsorted(LEVELS, u) - 1, 0, len(LEVELS) - 2)
    w = np.clip((u - LEVELS[j]) / (LEVELS[j + 1] - LEVELS[j]), 0, 1)
    values = q[:, j] * (1 - w) + q[:, j + 1] * w
    z = norm.ppf(LEVELS)
    low, high = u < LEVELS[0], u > LEVELS[-1]
    low_scale = (q[:, 1] - q[:, 0]) / (z[1] - z[0])
    high_scale = (q[:, -1] - q[:, -2]) / (z[-1] - z[-2])
    values[:, low] = q[:, [0]] + low_scale[:, None] * (norm.ppf(u[low]) - z[0])
    values[:, high] = q[:, [-1]] + high_scale[:, None] * (norm.ppf(u[high]) - z[-1])
    return np.where(np.isfinite(bounds[:, None]), np.maximum(values, bounds[:, None]), values)


def one(seed, output, resume):
    path = output / f"seed_{seed:02d}.csv"
    pair_path = output / f"seed_{seed:02d}_paired.csv"
    if resume and path.exists() and pair_path.exists():
        return seed
    analysis = T.load_script(f"response_annual_{seed}", T.ROOT / "scripts/467_review_completion_analysis.py")
    c = analysis.load(seed, "leave_one_year_out")
    c = analysis.calibrate_classical(c, seed, "leave_one_year_out")
    truth = c.eval_truth_h30.to_numpy(float)
    lower = c.observed_lower_bound__observed_days.to_numpy(float)
    if np.any(np.isfinite(truth) & np.isfinite(lower) & (truth < lower - 1e-8)):
        raise RuntimeError("A source evaluation target contradicts its observed-window bound")
    rows, pairs = [], []
    methods = {"plug_in": "h30__policy", "functional_debias": "P2",
               "distribution_regression": "D2", "stochastic_regression_calibrated": "stochastic_cal_q50"}
    for family in ["calendar", "crossed"]:
        for stratum in ["all", "danger"]:
            chosen = c.design_family.eq(family).to_numpy()
            if stratum == "danger":
                chosen &= c.peak_overlap.ge(.5).to_numpy()
            block = c.loc[chosen]
            y, l = truth[chosen], lower[chosen]
            predictions = {}
            for method, column in methods.items():
                original = block[column].to_numpy(float)
                value = np.where(np.isfinite(l), np.maximum(original, l), original)
                if np.any(np.isfinite(value) & np.isfinite(l) & (value < l - 1e-8)):
                    raise RuntimeError("Projected annual point is below its observed bound")
                valid = np.isfinite(value) & np.isfinite(y)
                error = value[valid] - y[valid]
                row = dict(seed=seed, family=family, stratum=stratum, estimator=method,
                           n=int(valid.sum()), eligible=int(len(block)), availability=float(valid.mean()),
                           mae=float(np.mean(abs(error))), bias=float(np.mean(error)),
                           failure_rate=float(np.mean(abs(error) > .5)))
                prefix = {"distribution_regression": "D2", "stochastic_regression_calibrated": "stochastic_cal"}.get(method)
                if prefix:
                    q = block[[f"{prefix}_q{int(100 * level):02d}" for level in LEVELS]].to_numpy(float)
                    good = valid & np.isfinite(q).all(axis=1)
                    samples = quantile_samples(q[good], l[good])
                    if np.any(np.isfinite(l[good, None]) & (samples < l[good, None] - 1e-8)):
                        raise RuntimeError("Annual sample is below its observed bound")
                    observed = y[good]
                    crps = ensemble_crps(samples, observed)
                    twcrps = ensemble_crps(samples, observed, block.train_h30_q90.to_numpy(float)[good])
                    clipped_q = apply_observed_lower_bound(q[good], l[good])
                    low, high = clipped_q[:, 0], clipped_q[:, -1]
                    row.update(crps=float(np.mean(crps)), twcrps=float(np.mean(twcrps)),
                               coverage90=float(np.mean((observed >= low - 1e-8) & (observed <= high + 1e-8))),
                               width90=float(np.mean(high - low)),
                               interval_score90=float(np.mean(interval_score(low, high, observed))))
                    predictions[method] = (value, good, crps, twcrps)
                rows.append(row)
            a, b = predictions["distribution_regression"], predictions["stochastic_regression_calibrated"]
            common = a[1] & b[1]
            # Score only the common subset; partial availability cannot create a win.
            qa = block[[f"D2_q{int(100 * level):02d}" for level in LEVELS]].to_numpy(float)[common]
            qb = block[[f"stochastic_cal_q{int(100 * level):02d}" for level in LEVELS]].to_numpy(float)[common]
            sa, sb = quantile_samples(qa, l[common]), quantile_samples(qb, l[common])
            threshold = block.train_h30_q90.to_numpy(float)[common]
            ca, cb = ensemble_crps(sa, y[common]), ensemble_crps(sb, y[common])
            ta, tb = ensemble_crps(sa, y[common], threshold), ensemble_crps(sb, y[common], threshold)
            pairs.append(dict(seed=seed, family=family, stratum=stratum, n_common=int(common.sum()),
                              D2_mae=float(np.mean(abs(a[0][common]-y[common]))),
                              stochastic_mae=float(np.mean(abs(b[0][common]-y[common]))),
                              D2_crps=float(np.mean(ca)), stochastic_crps=float(np.mean(cb)),
                              D2_twcrps=float(np.mean(ta)), stochastic_twcrps=float(np.mean(tb))))
    pd.DataFrame(rows).to_csv(path, index=False)
    pd.DataFrame(pairs).to_csv(pair_path, index=False)
    print(f"Completed support-aware source seed {seed}", flush=True)
    return seed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(20)))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    done = Parallel(n_jobs=args.workers, verbose=10)(delayed(one)(seed, args.output, args.resume) for seed in args.seeds)
    records = pd.concat([pd.read_csv(args.output / f"seed_{seed:02d}.csv") for seed in sorted(done)])
    paired = pd.concat([pd.read_csv(args.output / f"seed_{seed:02d}_paired.csv") for seed in sorted(done)])
    records.to_csv(args.output / "source_scorecard.csv", index=False)
    paired.to_csv(args.output / "source_paired.csv", index=False)
    summaries = []
    for (family, stratum, method), g in records.groupby(["family", "stratum", "estimator"]):
        row = dict(family=family, stratum=stratum, estimator=method, n_seeds=g.seed.nunique())
        for col in ["mae", "bias", "failure_rate", "coverage90", "width90", "interval_score90", "crps", "twcrps", "availability"]:
            if col in g:
                values = g[col].dropna()
                if len(values):
                    row.update({col+"_median":float(values.median()), col+"_lower":float(values.quantile(.025)), col+"_upper":float(values.quantile(.975))})
        summaries.append(row)
    pd.DataFrame(summaries).to_csv(args.output / "source_scorecard_summary.csv", index=False)
    (args.output / "design.json").write_text(json.dumps({"seeds":sorted(done),
        "calibration":"historical held-region quantile offsets for each seed, then identical observed-bound projection",
        "tails":"same adjacent-normal-quantile extension and support projection for both annual methods",
        "limitation":"post-calibration projection is not projection-aware offset refitting; seed-zero whole-archive analysis separately refits offsets on calibration groups",
        "repetitions":"20 source masks/role compositions on the same archive; not independent climates"},indent=2)+"\n")


if __name__ == "__main__":
    main()
