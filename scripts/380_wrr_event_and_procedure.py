#!/usr/bin/env python3
"""Regional forward-event holdouts and full four-cell procedure resampling."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, DIRECT_UNCERTAINTY, WINDOW_INFORMATION, group_roles, empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, bounded_mean_upper

OUT = C.READY / "followup_20261021/robustness"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def read_cases(protocol):
    frame = pd.read_parquet(C.source_cases(protocol))
    frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy()
    groups = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    frame["independence_group"] = frame.network_id.map(groups)
    return frame.reset_index(drop=True)


def cells(train, calibration, test, seed, cal_draws=1000):
    output = []
    for objective in ("quantile", "probability"):
        for window in (False, True):
            features = GENERIC + DIRECT_UNCERTAINTY + (WINDOW_INFORMATION if window else ())
            model = D.fit_matched(train, features, train.abserr_policy if objective == "quantile" else train.policy_bad.astype(int), objective=objective, seed=seed)
            train_score, cal_score, score = [D.predict_matched(model, block, features, objective=objective) for block in (train, calibration, test)]
            cutoff = empirical_threshold(cal_score, calibration.policy_bad.to_numpy(), calibration.independence_group.to_numpy(), fixed_training_candidates(train_score), seed=seed, draws=cal_draws)["threshold"]
            admitted = score <= cutoff
            failures = admitted & test.policy_bad.to_numpy()
            bygroup = pd.DataFrame({"group": test.independence_group.to_numpy(), "admitted": admitted, "failed": failures}).groupby("group").mean()
            x = (bygroup.failed + 0.05 * (1 - bygroup.admitted)).mean()
            output.append({"objective": objective, "window": window, "n_candidates": len(test), "n_groups": test.independence_group.nunique(),
                           "retention": admitted.mean(), "risk": test.policy_bad.to_numpy()[admitted].mean() if admitted.any() else np.nan,
                           "accepted": int(admitted.sum()), "failures": int(failures.sum()),
                           "test_bounded_loss_mean": float(x), "test_bounded_loss_upper": bounded_mean_upper(float(np.clip(x, 0, 1)), len(bygroup), alpha=0.025)})
    return output


def resample(frame, rng):
    mapping = {str(group): block for group, block in frame.groupby("independence_group")}
    chosen = rng.choice(sorted(mapping), len(mapping), replace=True)
    pieces = []
    for copy, group in enumerate(chosen):
        piece = mapping[group].copy()
        piece["independence_group"] = f"copy_{copy}"
        pieces.append(piece)
    return pd.concat(pieces, ignore_index=True)


def repetition(protocol, parts, rep):
    destination = OUT / protocol / "refits" / f"{rep:04d}.json"
    if destination.exists():
        return json.loads(destination.read_text())["rows"]
    rng = np.random.default_rng(20261021 + rep)
    sampled = [resample(part, rng) for part in parts]
    rows = [{"repetition": rep, **row} for row in cells(*sampled, seed=20261021 + rep)]
    for row in rows:
        if not np.isfinite(row["risk"]):
            row["risk"] = None
    C.write_json(destination, {"rows": rows})
    return rows


def event_holdouts():
    frame = read_cases("strictly_prior_years")
    if (frame.maximum_training_calendar_year >= frame.year).any():
        raise RuntimeError("Future observations in regional event test")
    rows = []
    for provider in sorted(frame.provider.unique()):
        test_units = set(frame.loc[frame.provider.eq(provider), "independence_group"])
        source = frame.loc[~frame.independence_group.isin(test_units) & (frame.year <= 2014)]
        units = np.array(sorted(source.independence_group.unique()))
        calibration_units = set(np.random.default_rng(20261021).permutation(units)[::4])
        train, calibration = source.loc[~source.independence_group.isin(calibration_units)], source.loc[source.independence_group.isin(calibration_units)]
        test = frame.loc[frame.provider.eq(provider) & frame.year.isin([2015, 2018, 2022])]
        if train.empty or calibration.empty or test.empty:
            continue
        result = cells(train, calibration, test, seed=20261021)
        for row in result:
            rows.append({"held_region_proxy": provider, "training_latest_target_year": 2014, "test_event_years": "2015;2018;2022",
                         "n_train_groups": train.independence_group.nunique(), "n_cal_groups": calibration.independence_group.nunique(),
                         "interpretation": "provider is a declared regional proxy; not a verified hydrological process class", **row})
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "regional_forward_events.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--refits", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--events-only", action="store_true")
    args = parser.parse_args()
    if args.events_only:
        event_holdouts()
        return 0
    frame = read_cases(args.protocol)
    roles = group_roles(frame.independence_group.to_numpy(), 20261021, 0)
    parts = [frame.loc[frame.independence_group.map(roles).eq(role)] for role in ("train", "calibration", "test")]
    if args.protocol == "strictly_prior_years":
        parts = [part.loc[part.year <= 2018] if i < 2 else part.loc[part.year.between(2019, 2022)] for i, part in enumerate(parts)]
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(repetition)(args.protocol, parts, rep) for rep in range(args.refits))
    output = OUT / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    data = pd.DataFrame([row for result in results for row in result])
    data.to_csv(output / "whole_procedure.csv", index=False)
    contrasts = []
    wide = data.pivot(index="repetition", columns=["objective", "window"], values="retention")
    for left, right in [(("quantile", True), ("quantile", False)), (("probability", True), ("probability", False)), (("probability", False), ("quantile", False)), (("probability", True), ("quantile", True))]:
        values = wide[left] - wide[right]
        lo, hi = values.quantile([0.025, 0.975])
        risk_supported = data.loc[data.objective.eq(left[0]) & data.window.eq(left[1])].set_index("repetition").test_bounded_loss_upper <= 0.05
        contrasts.append({"left": str(left), "right": str(right), "n_refits": len(values), "mean_retention_difference": values.mean(), "ci_low": lo, "ci_high": hi,
                          "joint_five_point_and_test_risk_evidence_fraction": float(((values > 0.05) & risk_supported).mean()),
                          "interpretation": "source-like component bootstrap; not a new independent confirmation"})
    pd.DataFrame(contrasts).to_csv(output / "whole_procedure_contrasts.csv", index=False)
    C.write_json(output / "run_record.json", run_record({"cases": C.source_cases(args.protocol), "learner": Path(D.__file__)}, refits=args.refits, train_calibration_test_resampled=True, risk_cap_evidence_and_practical_gain_joint=True))
    print(f"[380] {args.protocol}: {args.refits} full four-cell refits", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
