#!/usr/bin/env python3
"""Apply unchanged held-group admission heads to events and donor cofailures."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import wrr_r3_common as C

from stream_recoverability.experiments.v19_revision.learning import predict_score

OUT = C.RUN / "r3_15_held_group_replay"
NAMES = ("generic_target_disagreement", "generic_direct_h30_uncertainty", "uncertain_support", "generic_both_diagnostics", "complete_diagnostic_model", "policy_certificate", "peak_overlap_rule", "length_rule", "direct_h30_uncertainty")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--family", choices=["events", "real_calendars"], default="events")
    parser.add_argument("--cofailure", type=float, choices=[0, 0.5, 1], default=0)
    args = parser.parse_args()
    settings = C.protocol()
    ablation = C.load_script("r3_held_group_ablation", C.ROOT / "scripts/354_wrr_uncertainty_ablation.py")
    report = C.load_script("r3_held_group_report", C.ROOT / "scripts/357_wrr_decision_report.py")
    source = C.RUN / "r3_14_monitoring_replay" / args.protocol / args.family / f"cofailure_{args.cofailure:g}"
    frame = pd.read_parquet(source / "cases.parquet")
    if args.cofailure:
        original = pd.read_parquet(source.parent / "cofailure_0/cases.parquet", columns=["network_id", "station_id", "year", "realization_id", "n_visible_donors"])
        frame = frame.merge(original.rename(columns={"n_visible_donors": "original_visible_donors"}), on=["network_id", "station_id", "year", "realization_id"], validate="one_to_one")
        frame["n_removed_donors"] = frame.original_visible_donors - frame.n_visible_donors
    else:
        frame["n_removed_donors"] = 0
    admission = pd.read_parquet(C.source_cases(args.protocol), columns=["independence_group"])
    output = OUT / args.protocol / args.family / f"cofailure_{args.cofailure:g}"
    output.mkdir(parents=True, exist_ok=True)
    rows, strata, groups = [], [], []
    for scope in ("documented_daily_mean", "all"):
        data = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])].copy() if scope == "documented_daily_mean" else frame.copy()
        data = data.reset_index(drop=True)
        directory = C.RUN / "r3_04_uncertainty_ablation/admission" / args.protocol / scope
        for name in NAMES:
            for seed in settings["fold_seeds"]:
                record = json.loads((directory / f"{name}_{seed}.json").read_text())
                saved = np.load(directory / f"{name}_{seed}.npz")
                assignments = admission.loc[saved["case_row"]].assign(fold=saved["fold"])
                if assignments.groupby("independence_group").fold.nunique().max() != 1:
                    raise RuntimeError("One component appeared in multiple held-out folds")
                fold_of = assignments.groupby("independence_group").fold.first()
                fold = data.independence_group.map(fold_of)
                if fold.isna().any():
                    raise RuntimeError("Replay group has no admission-training exclusion")
                scores = np.full(len(data), np.inf)
                admitted = np.zeros(len(data), dtype=bool)
                for item in record["folds"]:
                    mask = fold.eq(item["fold"]).to_numpy()
                    if not mask.any():
                        continue
                    if name in ablation.RULES:
                        score = ablation.raw_rule(data.loc[mask], name)
                    else:
                        head = joblib.load(directory / "models" / f"{name}_{seed}_{item['fold']}.joblib")
                        score = predict_score(head["model"], data.loc[mask], tuple(head["features"]), head["kind"])
                    scores[mask] = score
                    cutoff = item["empirical_threshold"]
                    admitted[mask] = score <= (cutoff if cutoff is not None else -np.inf)
                identity = {"arm": name, "seed": seed, "scope": scope, "family": args.family, "cofailure": args.cofailure, "protocol": args.protocol}
                rows.append({**identity, **report.pooled_metrics(data, admitted)})
                for dimension in ["event_phase", "warm_anomaly", "provider", "policy_choice", "n_visible_donors", "n_removed_donors"]:
                    if dimension not in data:
                        continue
                    for value, block in data.groupby(dimension):
                        strata.append({**identity, "dimension": dimension, "stratum": value, **report.pooled_metrics(block, admitted[block.index])})
                for group, block in data.groupby("independence_group"):
                    groups.append({**identity, "group": group, "risk_certification": "not_certified_from_single_dependent_component", **report.pooled_metrics(block, admitted[block.index])})
        rows.append({"arm": "reconstruct_all", "seed": 0, "scope": scope, "family": args.family, "cofailure": args.cofailure, "protocol": args.protocol, **report.pooled_metrics(data, np.isfinite(data.policy_metric.to_numpy()))})
    for name, records in [("operating_points", rows), ("stratum_results", strata), ("group_results", groups)]:
        pd.DataFrame(records).to_csv(output / f"{name}.csv", index=False)
    C.write_json(output / "summary.json", {"n_cases": len(frame), "n_components": frame.independence_group.nunique(), "n_with_visible_donors": int((frame.n_visible_donors > 0).sum()), "n_with_removed_donors": int((frame.n_removed_donors > 0).sum()), "new_models_or_thresholds_fitted": False, "independent_confirmation": False, "interpretation": "opened-source component-held-out stress test; thresholds unchanged from admission calibration"})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source / "cases.parquet", "admission_cases": C.source_cases(args.protocol)}))
    print(f"[365] {len(frame)} held-group cases scored without threshold adaptation", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
