#!/usr/bin/env python3
"""Enumerate calibration-group budgets for frozen developed-system scores."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION, empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold

RUN = C.READY / "followup_20261021"
OUT = RUN / "developed_calibration_budget"
CONFIG = C.ROOT / "configs/wrr_developed_calibration_budget_20261021.json"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def group_subsets(groups, budgets):
    units = sorted(set(np.asarray(groups).astype(str)))
    if not budgets or any(n < 1 or n > len(units) for n in budgets):
        raise ValueError("Calibration budgets must be positive and within observed group support")
    return [(n, subset) for n in budgets for subset in combinations(units, n)]


def evaluate_subset(data, subset, settings):
    mask = np.isin(data["cal_groups"], subset)
    if len(set(data["cal_groups"][mask])) != len(subset):
        raise ValueError("Selected calibration groups are absent")
    valid_cdf = data["test_cdf_available"]
    p_hot = np.full(len(valid_cdf), np.nan)
    p_hot[valid_cdf] = D.probability_calibration(data["cal_hot_probability"][mask], data["cal_truth_hot"][mask], data["test_hot_probability"][valid_cdf])
    fn = settings["illustrative_cost"]["false_negative"]
    abstention = settings["illustrative_cost"]["unknown"]
    direct_action = np.full(len(valid_cdf), 2)
    direct_action[valid_cdf] = D.cost_action(p_hot[valid_cdf], fn, abstention)
    direct_loss = float(D.action_loss(direct_action, data["test_truth_hot"], fn, abstention).mean())
    rows = []
    for kind, scores in data["scores"].items():
        empirical = empirical_threshold(scores["cal"][mask], data["cal_failure"][mask], data["cal_groups"][mask], scores["candidates"],
                                        seed=settings["seed"], draws=settings["empirical_bootstrap_draws"], risk_cap=settings["risk_cap"], alpha=settings["alpha"])
        formal = select_group_threshold(scores["cal"][mask], data["cal_failure"][mask], data["cal_groups"][mask], scores["candidates"],
                                        risk_cap=settings["risk_cap"], alpha=settings["alpha"])
        admitted = data["test_point_available"] & valid_cdf & np.isfinite(scores["test"]) & (scores["test"] <= empirical["threshold"])
        failures = admitted & data["test_failure"]
        action = np.where(admitted, data["test_point_hot"].astype(int), 2)
        group_a, group_b = [], []
        for name in sorted(set(data["test_groups"])):
            positions = data["test_groups"] == name
            group_a.append(admitted[positions].mean())
            group_b.append(failures[positions].mean())
        rows.append({"calibration_groups": len(subset), "subset": ";".join(subset), "score_kind": kind,
                     "n_calibration_cases": int(mask.sum()), "n_candidates": len(admitted), "accepted": int(admitted.sum()), "failed": int(failures.sum()),
                     "retention": float(admitted.mean()), "risk": float(failures.sum() / admitted.sum()) if admitted.any() else np.nan,
                     "equal_group_risk": float(np.mean(group_b) / np.mean(group_a)) if np.mean(group_a) else np.nan,
                     "formal_accepted": int((data["test_point_available"] & valid_cdf & np.isfinite(scores["test"]) & (scores["test"] <= formal.threshold)).sum()),
                     "empirical_threshold": empirical["threshold"], "formal_threshold": formal.threshold,
                     "magnitude_screen_loss": float(D.action_loss(action, data["test_truth_hot"], fn, abstention).mean()),
                     "direct_calibrated_CDF_loss": direct_loss, **D.action_counts(action, data["test_truth_hot"])})
    return rows


def inputs(settings):
    core = C.load_script("developed_budget_system", C.ROOT / "scripts/390_wrr_developed_probability_system.py")
    frames = {role: core.role_data(role) for role in ("development", "calibration", "test")}
    for role in ("development", "calibration"):
        frame = frames[role]
        mask = np.isfinite(frame.h30_reconstructed) & frame.h30_samples_C.map(lambda value: isinstance(value, (list, np.ndarray)) and np.isfinite(value).all())
        frames[role] = frame.loc[mask].copy()
    train, calibration, test = (core.prepare_point(frames[role], "csdi_developed_air") for role in ("development", "calibration", "test"))
    roles = [set(block.independence_group) for block in (train, calibration, test)]
    if any(roles[i] & roles[j] for i in range(3) for j in range(i + 1, 3)):
        raise RuntimeError("Calibration budget experiment roles overlap")
    generic = tuple(name for name in GENERIC if name != "estimator_disagreement")
    direct = ("reconstruction_point", "threshold_margin_C", "NN_failure_probability", "NN_target_abs90", "NN_h30_sd", "NN_width90")
    score_data = {}
    stored = pd.read_parquet(RUN / "system_factorial_developed/admission_cases.parquet")
    for kind in settings["scores"]:
        if kind == "native_CDF":
            values = [block.NN_failure_probability.to_numpy() for block in (train, calibration, test)]
            values[-1] = np.where(test.cdf_available & np.isfinite(test.reconstruction_point), values[-1], np.inf)
        else:
            features = generic + direct + (tuple(name + "_NN" for name in WINDOW_INFORMATION) if kind == "boost_window" else ())
            model = D.fit_matched(train, features, train.own_failure.astype(int), objective="probability", seed=settings["seed"])
            values = [D.predict_matched(model, block, features, objective="probability") for block in (train, calibration, test)]
        previous = stored.loc[stored.method.eq("csdi_developed_air") & stored.score_kind.eq(kind)].reset_index(drop=True)
        if not previous[core.KEYS].equals(test[core.KEYS].reset_index(drop=True)) or not np.allclose(previous.score, values[-1], rtol=0, atol=1e-12, equal_nan=True):
            raise RuntimeError("Fixed scores differ from the original developed system")
        score_data[kind] = {"cal": values[1], "test": values[2], "candidates": fixed_training_candidates(values[0])}
    cal_samples = np.stack(calibration.h30_samples_C.to_numpy())
    test_samples, cdf_available = core.ensemble_matrix(test.h30_samples_C)
    return {"cal_groups": calibration.independence_group.to_numpy(dtype=str), "cal_failure": calibration.own_failure.to_numpy(),
            "cal_truth_hot": (calibration.truth_hottest30 > calibration.local_hot_threshold_C).to_numpy(),
            "cal_hot_probability": (cal_samples > calibration.local_hot_threshold_C.to_numpy()[:, None]).mean(axis=1),
            "test_hot_probability": np.where(cdf_available, (test_samples > test.local_hot_threshold_C.to_numpy()[:, None]).mean(axis=1), np.nan),
            "test_cdf_available": cdf_available, "test_point_available": np.isfinite(test.reconstruction_point.to_numpy()),
            "test_point_hot": (test.reconstruction_point > test.local_hot_threshold_C).to_numpy(),
            "test_truth_hot": (test.truth_hottest30 > test.local_hot_threshold_C).to_numpy(), "test_failure": test.own_failure.to_numpy(),
            "test_groups": test.independence_group.to_numpy(dtype=str), "scores": score_data}


def summary(records):
    rows = []
    for (budget, kind), block in records.groupby(["calibration_groups", "score_kind"]):
        row = {"calibration_groups": budget, "score_kind": kind, "subsets": len(block), "nonempty_subsets": int(block.accepted.gt(0).sum()),
               "formal_positive_subsets": int(block.formal_accepted.gt(0).sum())}
        for name in ("retention", "risk", "magnitude_screen_loss", "direct_calibrated_CDF_loss"):
            row.update({name + "_min": block[name].min(), name + "_median": block[name].median(), name + "_max": block[name].max()})
        rows.append(row)
    return pd.DataFrame(rows)


def evidence():
    helper = C.load_script("calibration_budget_table_writer", C.ROOT / "scripts/383_wrr_followup_evidence.py")
    frame = pd.read_csv(OUT / "budget_summary.csv")
    display = frame[["calibration_groups", "score_kind", "subsets", "nonempty_subsets", "retention_min", "retention_median", "retention_max", "risk_median", "risk_max", "magnitude_screen_loss_median"]].copy()
    display["Empty"] = display.subsets - display.pop("nonempty_subsets")
    display["score_kind"] = display.score_kind.replace({"native_CDF": "Native CDF", "boost_direct": "Direct head", "boost_window": "Window head"})
    display = display.rename(columns={"calibration_groups": "Cal. G", "score_kind": "Score", "subsets": "Sets", "retention_min": "Ret. min", "retention_median": "Ret. med", "retention_max": "Ret. max", "risk_median": "Risk med", "risk_max": "Risk max", "magnitude_screen_loss_median": "Loss med"})
    display = display[["Cal. G", "Score", "Sets", "Empty", "Ret. min", "Ret. med", "Ret. max", "Risk med", "Risk max", "Loss med"]]
    caption = ("Calibration-budget sensitivity for the developed neural point on all 945 controlled Swiss test candidates. All combinations of three, five, seven and nine available calibration groups are included: 84, 126, 36 and one subsets. The old-only probability model, target-development boosted heads and training-fixed threshold families remain unchanged. Native-CDF and boosted scores use identical calibration subsets. Ranges describe subset sensitivity, not confidence intervals, new observations or full-procedure power. Risk summaries omit empty admissions; their counts are explicit. All 741 formal calibrations have zero admission. Loss uses missed-hot cost five and unknown cost 0.05. The full nine-group budget reproduces the original system exactly; no favorable subset is selected.")
    paper = C.ROOT / "paper/wrr"
    (paper / "si_r6_tables.tex").write_text("% Generated by script 393 from exhaustive calibration subsets.\n" + helper.table(display, caption, "extended_calibration_budget"))
    native3 = frame.loc[frame.calibration_groups.eq(3) & frame.score_kind.eq("native_CDF")].iloc[0]
    native7 = frame.loc[frame.calibration_groups.eq(7) & frame.score_kind.eq("native_CDF")].iloc[0]
    empty = int(native3.subsets - native3.nonempty_subsets)
    (paper / "r6_calibration_budget.tex").write_text(
        f"Calibration-set composition also matters. With the developed model and heads held fixed, all 247 subsets of three, five, seven or nine target calibration groups yield 741 score/subset evaluations on the same 945 tests. With three groups, the native CDF rule has empty admission in {empty} of {int(native3.subsets)} subsets; its nonempty test risks range from {100*native3.risk_min:.1f}\\% to {100*native3.risk_max:.1f}\\%. Even seven-group subsets reach a sample risk of {100*native7.risk_max:.1f}\\%. Every formal calibration remains empty. These ranges measure conditional sensitivity to already opened calibration groups, not a powered independent test; no subset is selected to improve the result.\n")
    paths = {"settings": CONFIG, "subset_results": OUT / "all_subsets.csv", "summary": OUT / "budget_summary.csv", "analysis_record": OUT / "run_record.json",
             "future_reference_specification": C.ROOT / "configs/wrr_next_confirmation_20261021.yaml"}
    C.write_json(RUN / "evidence/calibration_budget_bindings.json", run_record(paths, conditional_calibration_only=True, new_confirmation=False))
    print("[393] calibration sensitivity table and result paragraph generated", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--evidence-only", action="store_true")
    args = parser.parse_args()
    if args.evidence_only:
        evidence()
        return 0
    settings = json.loads(CONFIG.read_text())
    data = inputs(settings)
    tasks = group_subsets(data["cal_groups"], settings["calibration_budgets"])
    gathered = Parallel(n_jobs=args.workers, verbose=10)(delayed(evaluate_subset)(data, subset, settings) for _, subset in tasks)
    records = pd.DataFrame([row for block in gathered for row in block])
    full = records.loc[records.calibration_groups.eq(len(set(data["cal_groups"])))].set_index("score_kind")
    original = pd.read_csv(RUN / "system_factorial_developed/operating.csv")
    original = original.loc[original.method.eq("csdi_developed_air")].set_index("score_kind")
    if any(int(full.loc[kind, field]) != int(original.loc[kind, field]) for kind in settings["scores"] for field in ("accepted", "failed", "formal_accepted")):
        raise RuntimeError("Full calibration budget does not reproduce existing operating points")
    OUT.mkdir(parents=True, exist_ok=True)
    records.to_csv(OUT / "all_subsets.csv", index=False)
    summary(records).to_csv(OUT / "budget_summary.csv", index=False)
    C.write_json(OUT / "summary.json", {"distinct_subsets": len(tasks), "score_subset_rows": len(records),
                 "observed_calibration_groups": len(set(data["cal_groups"])), "original_test_candidates": len(data["test_failure"]),
                 "all_group_subsets_included": True, "fixed_scores_match_original": True, "full_budget_reproduces_original": True,
                 "source_probability_and_development_heads_held_fixed": True, "new_confirmation_or_joint_power": False})
    paths = {"settings": CONFIG, "sampler_and_system": C.ROOT / "scripts/390_wrr_developed_probability_system.py", "learner": Path(D.__file__),
             "empirical_selector": C.ROOT / "src/stream_recoverability/experiments/v19_revision/learning.py", "formal_selector": C.ROOT / "src/stream_recoverability/experiments/v19_revision/risk.py",
             "original_operating": RUN / "system_factorial_developed/operating.csv", "original_scores": RUN / "system_factorial_developed/admission_cases.parquet"}
    for role in ("development", "calibration", "test"):
        paths[role] = RUN / "probability_development" / role / "cases.parquet"
    C.write_json(OUT / "run_record.json", run_record(paths, supplementary_opened_data=True, all_subsets_not_best_subset=True))
    print(f"[393] {len(tasks)} calibration subsets, {len(records)} score/subset rows; original full-budget points reproduced", flush=True)
    evidence()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
