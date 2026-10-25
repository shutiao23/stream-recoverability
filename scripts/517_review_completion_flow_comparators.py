#!/usr/bin/env python3
"""Matched MOVE.1 and stochastic comparisons for the opened low-flow example.

The historical plug-in uses log-flow regression. Exponentiating its prediction
is not an original-unit conditional mean, so a universal Jensen bias sign is
not asserted. All historical cases and features must reproduce before reporting.
"""
from __future__ import annotations
import os
for key in ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]:
    os.environ[key] = "1"
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
import wrr_tr_common as T
from stream_recoverability.seeds import position_index

OUT = T.ROOT / "results/wrr_review_completion_20261024/flow_comparators"
CORE = T.load_script("review_flow_reference", T.ROOT / "scripts/461_tr2_flow_demo.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def worker(job, fingerprint):
    path = OUT / "station_cases" / (job[0] + ".parquet")
    meta = path.with_suffix(".json")
    if path.exists() and meta.exists() and json.loads(meta.read_text()).get("fingerprint") == fingerprint:
        return path
    core = T.load_script("review_flow_classical_worker", T.ROOT / "scripts/461_tr2_flow_demo.py")
    frame = pd.DataFrame(core.station_cases(*job, classical=True))
    frame.to_parquet(path, index=False)
    T.write_json(meta, {"fingerprint": fingerprint, "n_cases": len(frame)})
    return path


def align(frame):
    keys = ["site", "year", "design_family", "design"]
    frame = frame.copy()
    frame["within_design_position"] = frame.groupby(keys, sort=False).cumcount()
    return frame.set_index(keys + ["within_design_position"]).sort_index()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    (OUT / "station_cases").mkdir(parents=True, exist_ok=True)
    historical_path = T.SCRATCH / "s1_flow_cases.parquet"
    historical_predictions = CORE.OUT / "case_predictions.parquet"
    sources = [Path(__file__), T.ROOT / "scripts/461_tr2_flow_demo.py", CORE.FLOW, CORE.SITES,
               historical_path, historical_predictions,
               T.ROOT / "src/stream_recoverability/experiments/tr_revision/baselines.py"]
    hashes = {str(p.relative_to(T.ROOT)): digest(p) for p in sources}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    T.write_json(OUT / "design.json", {"input_sha256": hashes, "fingerprint": fingerprint,
        "working_uncertainty": "20 Gaussian AR1 residual bridges using other-year in-sample regression residuals; not calibrated predictive coverage",
        "information": "MOVE.1 and one-donor Ridge use the same best available donor and other-year log-anomaly pairs; historical Ridge and stochastic bridge use up to three donors",
        "scope": "opened positive-flow perennial subset, April--March climatic years; historical masks and source feature controls fixed; no new blind transfer or20-seed stability claim"})
    panel, sites = CORE.load()
    near = {site: [d for d in items if d in panel.columns] for site, items in CORE.neighbours(sites).items()}
    pool = CORE.calendar_pool(panel)
    positions = position_index(panel.columns)
    jobs = [(site, panel[[site] + near[site]], near[site], pool,
             f"usgs_huc{sites.huc2[site]}", positions[site]) for site in panel.columns if site in sites.index]
    paths = Parallel(n_jobs=args.workers, verbose=10)(delayed(worker)(job, fingerprint) for job in jobs)
    parts = [pd.read_parquet(path) for path in paths]
    cases = pd.concat([p for p in parts if len(p)], ignore_index=True)
    cases = cases.loc[np.isfinite(cases.plugin_log7q) & np.isfinite(cases.truth_log7q)].reset_index(drop=True)
    old = align(pd.read_parquet(historical_path))
    new = align(cases)
    pd.testing.assert_frame_equal(old, new[old.columns], check_exact=False, atol=1e-10, rtol=0)
    predictions = align(pd.read_parquet(historical_predictions))
    if not new.index.equals(predictions.index):
        raise RuntimeError("Historical low-flow prediction identities differ")
    for name in ["truth_log7q", "plugin_log7q", "recorded_log7q"]:
        np.testing.assert_allclose(new[name], predictions[name], atol=1e-10, rtol=0, equal_nan=True)
    new["d2_log7q"] = predictions.d2_log7q
    new["historical_D2_q05"] = predictions.d2_q05
    new["historical_D2_q95"] = predictions.d2_q95
    cases = new.reset_index()
    cases.to_parquet(OUT / "case_predictions.parquet", index=False)
    T.write_json(OUT / "historical_control_audit.json", {"passed": True, "n_cases": len(cases),
        "historical_columns_compared": len(old.columns), "absolute_tolerance": 1e-10,
        "mask_identity": "same deterministic source station_cases generation, unchanged random stream; full historical source features and point controls match"})
    reference = json.loads((CORE.OUT / "summary.json").read_text())
    tolerance = reference["tolerance_log"]
    estimates = {name: cases[column] for name, column in {
        "historical_multidonor_log_Ridge": "plugin_log7q", "historical_D2": "d2_log7q",
        "single_donor_log_Ridge": "single_donor_ridge_log7q", "MOVE1_log_anomaly": "move1_log7q",
        "stochastic_log_AR1_median": "stochastic_log7q", "observed_days": "recorded_log7q"}.items()}
    rows, paired, rules = [], [], []
    for family, block in cases.groupby("design_family"):
        scopes = {"all": block.index, "danger": block.index[block.lowflow_overlap.ge(.5)],
                  "donor_danger": block.index[block.lowflow_overlap.ge(.5) & block.layer_donor.eq(1)]}
        for scope, index in scopes.items():
            truth = cases.loc[index, "truth_log7q"]
            for name, value in estimates.items():
                error = value.loc[index] - truth
                valid = error.notna()
                rows.append({"family": family, "scope": scope, "estimator": name, "n_eligible": len(index),
                    "n_valid": int(valid.sum()), "availability": float(valid.mean()), "bias_log": error.mean(),
                    "geometric_bias_percent": float(100*np.expm1(error.mean())), "mae_log": error.abs().mean(),
                    "failure_rate": float(error[valid].abs().gt(tolerance).mean())})
            for left, right in [("MOVE1_log_anomaly", "single_donor_log_Ridge"),
                                ("MOVE1_log_anomaly", "historical_D2"),
                                ("stochastic_log_AR1_median", "historical_D2")]:
                a, b = estimates[left].loc[index]-truth, estimates[right].loc[index]-truth
                keep = a.notna() & b.notna()
                by_site = pd.DataFrame({"site": cases.loc[index, "site"], "left": a.abs(), "right": b.abs()}).loc[keep].groupby("site")[["left", "right"]].mean()
                paired.append({"family": family, "scope": scope, "left": left, "right": right,
                    "n_common": int(keep.sum()), "left_mae_log": a[keep].abs().mean(), "right_mae_log": b[keep].abs().mean(),
                    "n_sites": len(by_site), "site_fraction_left_not_worse": float(by_site.left.le(by_site.right).mean())})
        for name, value in estimates.items():
            for rule, selected in {"all": np.ones(len(block), bool), "one_feature_50": block.lowflow_overlap.lt(.5),
                                   "one_feature_25": block.lowflow_overlap.lt(.25), "annual90": block.observed_fraction.ge(.9)}.items():
                error = value.loc[block.index]-block.truth_log7q
                selected = np.asarray(selected) & error.notna().to_numpy()
                rules.append({"family": family, "estimator": name, "rule": rule, "n_eligible": len(block),
                    "n_used": int(selected.sum()), "retention": float(selected.mean()),
                    "failure_risk": float(error.loc[selected].abs().gt(tolerance).mean())})
    pd.DataFrame(rows).to_csv(OUT / "scorecard.csv", index=False)
    pd.DataFrame(paired).to_csv(OUT / "paired_effects.csv", index=False)
    pd.DataFrame(rules).to_csv(OUT / "rules.csv", index=False)
    T.write_json(OUT / "status.json", {"complete": True, "n_cases": len(cases), "n_sites": cases.site.nunique(),
        "n_complete_years": len(cases.drop_duplicates(["site", "year"])), "tolerance_log": tolerance,
        "historical_controls_passed": True, "source_inputs_sha256": hashes,
        "source_annual_models_retrained": False, "new_NZ_water_values_requested": False,
        "limits": "Working log-flow model; neither universal bias sign, natural-gap accuracy, regulatory validity nor climate transfer established"})
    print(json.dumps({"complete": True, "cases": len(cases), "sites": cases.site.nunique()}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
