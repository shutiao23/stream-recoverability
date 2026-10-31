#!/usr/bin/env python3
"""Materialize the old-data probability/score bank before new water references."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import importlib
import json

import joblib
import numpy as np
import pandas as pd
import yaml

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION, empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold

OUT = C.READY / "followup_20261021/au_confirmation"
PROB = C.READY / "followup_20261021/probability_development"
CONFIG = C.ROOT / "configs/wrr_au_reference_qualification_20261021.json"
RAW = C.ROOT / "data/external/wrr_au_confirmation_20261021"


def main():
    if (RAW / "daily_references").exists() and any((RAW / "daily_references").glob("*.json")):
        raise RuntimeError("Materialize the source bank before acquiring new daily water records")
    config = json.loads(CONFIG.read_text())
    spec = yaml.safe_load((C.ROOT / config["parent_confirmation_specification"]).read_text())
    selection = json.loads((PROB / "selection.json").read_text())
    checkpoint = PROB / selection["selected"] / "model.pypots"
    if selection["selected"] != "air32":
        raise RuntimeError("Old-only probability selection changed")
    core = importlib.import_module("390_wrr_developed_probability_system")
    data = {role: core.role_data(role) for role in ("development", "calibration", "test")}
    for role in ("development", "calibration"):
        frame = data[role]
        common = np.isfinite(frame.h30_reconstructed) & frame.h30_samples_C.map(lambda value: isinstance(value, (list, np.ndarray)) and np.isfinite(value).all())
        data[role] = frame.loc[common].copy()
    train, calibration, test = (core.prepare_point(data[role], "csdi_developed_air") for role in ("development", "calibration", "test"))
    old_reference = pd.read_parquet(C.READY / "followup_20261021/system_factorial_developed/admission_cases.parquet")
    original_operating = pd.read_csv(C.READY / "followup_20261021/system_factorial_developed/operating.csv")
    generic = tuple(name for name in GENERIC if name != "estimator_disagreement")
    direct = ("reconstruction_point", "threshold_margin_C", "NN_failure_probability", "NN_target_abs90", "NN_h30_sd", "NN_width90")
    models, records = {}, []
    for kind in ("native_CDF", "boost_direct", "boost_window"):
        features = generic + direct + (tuple(name + "_NN" for name in WINDOW_INFORMATION) if kind == "boost_window" else ())
        if kind == "native_CDF":
            values = [block.NN_failure_probability.to_numpy() for block in (train, calibration, test)]
            model = None
        else:
            model = D.fit_matched(train, features, train.own_failure.astype(int), objective="probability", seed=config["predictive_choice_before_new_recovery_results"]["fitting_seed"])
            values = [D.predict_matched(model, block, features, objective="probability") for block in (train, calibration, test)]
        values[-1] = np.where(test.cdf_available & np.isfinite(test.reconstruction_point), values[-1], np.inf)
        previous = old_reference.loc[old_reference.method.eq("csdi_developed_air") & old_reference.score_kind.eq(kind)].reset_index(drop=True)
        if not previous[core.KEYS].equals(test[core.KEYS].reset_index(drop=True)) or not np.allclose(previous.score, values[-1], rtol=0, atol=1e-12, equal_nan=True):
            raise RuntimeError("Serialized source heads do not reproduce their existing old-data scores")
        candidates = fixed_training_candidates(values[0])
        empirical = empirical_threshold(values[1], calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates,
                                        seed=20261021, draws=2000, risk_cap=spec["selected_risk_cap"], alpha=.05)
        formal = select_group_threshold(values[1], calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates,
                                        risk_cap=spec["selected_risk_cap"], alpha=spec["joint_error_allocation"]["formal_calibration_per_method"])
        accepted = test.cdf_available.to_numpy() & np.isfinite(test.reconstruction_point.to_numpy()) & (values[-1] <= empirical["threshold"])
        original = original_operating.loc[original_operating.method.eq("csdi_developed_air") & original_operating.score_kind.eq(kind)].iloc[0]
        failed = int((accepted & test.own_failure.to_numpy()).sum())
        if accepted.sum() != original.accepted or failed != original.failed:
            raise RuntimeError("Old-data empirical operating point changed")
        models[kind] = {"model": model, "features": features, "candidates": candidates,
                        "empirical_threshold": empirical["threshold"], "formal_threshold": formal.threshold}
        records.append({"score_kind": kind, "features": list(features), "training_fixed_candidates": candidates.tolist(),
                        "old_implementation_replay_candidates": len(test), "old_implementation_replay_accepted": int(accepted.sum()),
                        "old_implementation_replay_failed": failed,
                        "empirical_alpha": .05, "empirical_threshold": float(empirical["threshold"]) if np.isfinite(empirical["threshold"]) else None,
                        "formal_alpha": spec["joint_error_allocation"]["formal_calibration_per_method"],
                        "formal_status": formal.status, "formal_threshold": float(formal.threshold) if np.isfinite(formal.threshold) else None,
                        "new_Australian_outcomes_used": False})
    bank = OUT / "source_heads.joblib"
    joblib.dump(models, bank)
    C.write_json(OUT / "source_head_specification.json", {
        "selected_probability_configuration": selection["selected"], "checkpoint_path": str(checkpoint.relative_to(C.ROOT)),
        "primary_candidate": "boost_window", "required_references": ["native_CDF", "boost_direct"],
        "delivered_point": "csdi_developed_air; unchanged functional definition in script 385",
        "source_heads_fit": "old opened Swiss development; replay is implementation verification on old opened tests, not a new experiment",
        "heads": records, "new_prediction_errors_opened": False})
    print("[401] air32 and two matched probability heads materialized; three old operating points reproduced; no Australian temperature values or errors opened", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
