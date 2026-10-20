#!/usr/bin/env python3
"""Correct a percent-unit descriptive label without changing any frozen decision."""

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
from wrr_r3_hydrology import hydrological_strata

from stream_recoverability.experiments.v19_revision.learning import certificate_delivery, predict_score

OUT = C.RUN / "r3_19_hydrological_correction"
NAMES = {"generic_target_disagreement", "generic_direct_h30_uncertainty", "uncertain_support", "complete_diagnostic_model", "certificate_joint"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--family", choices=["admission", "crossed", "events", "real_calendars"], default="admission")
    args = parser.parse_args()
    settings = C.protocol()
    gate = C.load_script("r3_corrected_hydrology_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access("test")
    evaluator = C.load_script("r3_corrected_hydrology_evaluation", C.ROOT / "scripts/360_wrr_external_decisions.py")
    source = C.RUN / "r3_10_external_decisions/test" / args.protocol / args.family / "cofailure_0/case_information.parquet"
    frame = pd.read_parquet(source)
    frame["hydrological_stratum_corrected"] = hydrological_strata(frame)
    transfer = C.RUN / "r3_09_frozen_transfer"
    bank = {item["identity"]: item for item in json.loads((transfer / "head_bank.json").read_text())["heads"]}
    plans = json.loads((transfer / "deployment_plans.json").read_text())["plans"]
    cache, rows = {}, []
    for plan in plans:
        record = bank[plan["head_identity"]]
        if record["protocol"] != args.protocol or record["name"] not in NAMES:
            continue
        if {"hydrological_stratum", "Pt as snow", "Glaciers %"}.intersection(record["features"]):
            raise RuntimeError("Hydrological correction unexpectedly affects a fitted predictor")
        key = (record["identity"], plan["target_provider"])
        if key not in cache:
            selected = frame.loc[frame.provider.eq(plan["target_provider"])].copy()
            if record["scope"] == "documented_daily_mean":
                selected = selected.loc[selected.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
            selected = selected.reset_index(drop=True)
            if selected.empty:
                continue
            head = joblib.load(record["model_path"])
            if head["kind"] == "certificate_joint":
                selected = certificate_delivery(head["model"], selected)
            score = predict_score(head["model"], selected, tuple(head["features"]), head["kind"])
            cache[key] = selected, score
        selected, score = cache[key]
        cutoff = plan["thresholds"]["empirical"]
        admit = score <= (cutoff if cutoff is not None else -np.inf)
        for value, block in selected.groupby("hydrological_stratum_corrected"):
            mask = admit[block.index]
            rows.append({"arm": record["name"], "mode": plan["mode"], "provider": plan["target_provider"], "scope": record["scope"], "protocol": args.protocol, "family": args.family, "stratum": value, **evaluator.M357.pooled_metrics(block, mask), **evaluator.bootstrap_metrics(block, mask, settings)})
    output = OUT / args.protocol / args.family
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output / "corrected_hydrological_strata.csv", index=False)
    frame[["station_id", "provider", "independence_group", "Glaciers %", "Pt as snow", "hydrological_stratum", "hydrological_stratum_corrected"]].drop_duplicates().to_csv(output / "metadata_labels.csv", index=False)
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source, "method_lock": C.RUN / "method_lock.json", "deployment_lock": C.RUN / "deployment_lock.json", "erratum": C.DOCS / "NONPREDICTIVE_ERRATUM.md", "label_function": C.ROOT / "scripts/wrr_r3_hydrology.py"}, predictive_decisions_changed=False, snow_units="percent; majority threshold 50"))
    print(f"[373] {len(rows)} corrected descriptive subgroup rows; no predictor or threshold changed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
