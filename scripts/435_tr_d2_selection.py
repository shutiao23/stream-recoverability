#!/usr/bin/env python3
"""TR-E4b: select D2* by the preregistered rule and evaluate primary endpoint P1.

D2* is the candidate (P3, P3raw, P5a, P5b) with the lowest mean quantile CRPS
of H30 over all source leave-one-region-out predictions. P1 is the reduction
of the absolute mean signed error relative to P0 in the mechanism population,
air-temperature layer, true peak window at least half hidden, with D2*'s 90%
interval coverage in the same stratum. Intervals resample independence groups.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse

import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_features as F

OUT = T.OUT / "e4_estimators"
LEVELS = F.QUANTILES


def quantile_crps(q: np.ndarray, truth: np.ndarray) -> np.ndarray:
    loss = [np.maximum(level * (truth - values), (level - 1) * (truth - values)) for level, values in zip(LEVELS, q.T)]
    return 2 * np.mean(loss, axis=0)


def candidates(cases: pd.DataFrame, oof: pd.DataFrame) -> dict[str, np.ndarray]:
    names = [f"q{int(level * 100):02d}" for level in LEVELS]
    return {
        "P3": cases[[f"state_h30_{n}" for n in names]].to_numpy(),
        "P3raw": cases[[f"raw_h30_{n}" for n in names]].to_numpy(),
        "P5a": oof[[f"h30__P5a_{n}" for n in names]].to_numpy(),
        "P5b": oof[[f"h30__P5b_{n}" for n in names]].to_numpy(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draws", type=int, default=2000)
    args = parser.parse_args()
    settings = T.settings()
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof = pd.read_parquet(OUT / "oof_predictions.parquet")
    if len(oof) != len(cases) or not (oof.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("Out-of-fold predictions are not aligned")
    truth = cases.eval_truth_h30.to_numpy()
    table = candidates(cases, oof)
    crps = {name: float(quantile_crps(q, truth).mean()) for name, q in table.items()}
    d2 = min(crps, key=crps.get)
    T.write_json(OUT / "d2_selection.json", {"d2": d2, "levels": list(LEVELS), "mean_quantile_crps": crps, "rule": "lowest mean quantile CRPS over all source LORO predictions"})
    print(f"[435] D2* = {d2}; CRPS {crps}", flush=True)

    hidden = cases.eval_true_peak_hidden_fraction.ge(0.5)
    stratum = cases.design_family.eq("crossed") & cases.policy_choice.eq("air_ridge") & hidden
    frame = cases.loc[stratum, ["independence_group"]].copy()
    frame["e0"] = (cases.h30__policy - cases.eval_truth_h30)[stratum]
    rows = []
    for name, q in table.items():
        frame[f"e_{name}"] = q[stratum.to_numpy(), 3] - truth[stratum.to_numpy()]
        lower = np.array([np.interp(0.05, LEVELS, row) for row in q[stratum.to_numpy()]])
        upper = np.array([np.interp(0.95, LEVELS, row) for row in q[stratum.to_numpy()]])
        frame[f"c_{name}"] = ((truth[stratum.to_numpy()] >= lower) & (truth[stratum.to_numpy()] <= upper)).astype(float)
    frame["e_P2"] = (oof.loc[stratum, "h30__P2"] - cases.loc[stratum, "eval_truth_h30"]).to_numpy()
    for name in list(table) + ["P2"]:
        reduction = lambda f, n=name: float(1 - abs(f[f"e_{n}"].mean()) / abs(f.e0.mean()))
        boot = T.group_bootstrap(frame, "independence_group", reduction, args.draws, settings["seed"])
        row = {"estimator": name, "n": len(frame), "n_groups": int(frame.independence_group.nunique()), "bias_P0": float(frame.e0.mean()), "bias": float(frame[f"e_{name}"].mean()), "reduction": reduction(frame), "reduction_lower95": float(np.quantile(boot, 0.025)), "reduction_upper95": float(np.quantile(boot, 0.975)), "mae_P0": float(frame.e0.abs().mean()), "mae": float(frame[f"e_{name}"].abs().mean())}
        if f"c_{name}" in frame:
            cover = T.group_bootstrap(frame, "independence_group", lambda f, n=name: float(f[f"c_{n}"].mean()), args.draws, settings["seed"] + 1)
            row.update({"coverage90": float(frame[f"c_{name}"].mean()), "coverage90_lower95": float(np.quantile(cover, 0.025)), "coverage90_upper95": float(np.quantile(cover, 0.975))})
        rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "endpoint_P1.csv", index=False)
    chosen = result.set_index("estimator").loc[d2]
    summary = {"d2": d2, **{f"P1_{k}": (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in chosen.items()}, "P1_success": bool(chosen.reduction >= 0.5 and 0.85 <= chosen.coverage90 <= 0.95), "success_rule": "reduction >= 0.50 and coverage90 in [0.85, 0.95]"}
    T.write_json(OUT / "endpoint_P1.json", summary)
    print(result.to_string(), flush=True)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
