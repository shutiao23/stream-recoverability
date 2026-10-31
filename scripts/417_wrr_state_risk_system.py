#!/usr/bin/env python3
"""Cross numerical points with state/neural laws, own errors and use decisions."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

from datetime import datetime, timezone
import importlib
import json

import numpy as np
import pandas as pd

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION, empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold
from stream_recoverability.experiments.v19_revision.target_risk_laws import CDF_FEATURES, tolerance_features

F = importlib.import_module("416_wrr_state_risk_factorial")
G = F.G
CONFIG = C.ROOT / "configs/wrr_state_risk_system_20261021.json"
OUT = G.OUT / "system_factorial"


def median_points(frame):
    return frame.h30_samples_C.map(lambda value: float(np.median(value[:32])) if isinstance(value, (list, np.ndarray)) and len(value) >= 32 and np.isfinite(value).all() else np.nan).to_numpy()


def point_frame(frame, points):
    result = frame.copy()
    result["reconstruction_point"] = np.asarray(points, dtype=float)
    result["threshold_margin_C"] = result.reconstruction_point - result.local_hot_threshold_C
    result["own_failure"] = ~np.isfinite(result.reconstruction_point) | (np.abs(result.reconstruction_point - result.truth_hottest30) > .5)
    features = [tolerance_features(value[:32] if isinstance(value, (list, np.ndarray)) else np.array([]), point)
                for value, point in zip(result.h30_samples_C, result.reconstruction_point)]
    for name in CDF_FEATURES:
        result[name] = [row[name] for row in features]
    return result


def choose_references():
    selection = json.loads((F.OUT / "development_selection.json").read_text())
    table = pd.read_csv(F.OUT / "development_selection_quality.csv")
    neural = table.loc[table.law.str.startswith("neural_")].sort_values(["CRPS_C", "law"]).iloc[0].law
    OUT.mkdir(parents=True, exist_ok=True)
    C.write_json(OUT / "development_reference_choice.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_state_law": selection["selected_law"], "selected_neural_law": neural,
        "calibration_or_test_used_to_choose_reference": False, "new_confirmation": False})
    return selection["selected_law"], neural


def main():
    settings, parent = json.loads(CONFIG.read_text()), json.loads(G.CONFIG.read_text())
    state_law, neural_law = choose_references()
    roles = {role: F.role_data(role) for role in F.ROLES}
    matrices, common = {}, {}
    specifications = {
        "available_air": (settings["primary_air_points"], (neural_law, state_law)),
        "air_and_flow": (settings["supplementary_flow_points"], (state_law, "seasonal_air_flow_slow")),
    }
    for role, laws in roles.items():
        first = laws[neural_law]
        physics = pd.read_parquet(C.RUN / "r3_12_process_reference" / role / "leave_one_year_out/cases.parquet")
        points = {"priority": first.policy_metric.to_numpy(), "neural_median32": median_points(laws[neural_law]),
                  "state_median32": median_points(laws[state_law]), "flow_state_median32": median_points(laws["seasonal_air_flow_slow"])}
        for method in ("air2stream3", "air2stream8"):
            values = physics.loc[physics.method.eq(method) & physics.status.eq("available"), G.KEYS + ["h30_reconstructed"]]
            points[method] = first[G.KEYS].merge(values, on=G.KEYS, how="left", validate="one_to_one").h30_reconstructed.to_numpy()
        matrices[role], common[role] = {}, {}
        for tier, (methods, cdfs) in specifications.items():
            cells = {(point, law): point_frame(laws[law], points[point]) for point in methods for law in cdfs}
            keep = np.ones(len(first), dtype=bool)
            for frame in cells.values():
                keep &= frame.cdf_available.to_numpy() & np.isfinite(frame.reconstruction_point.to_numpy())
            matrices[role][tier], common[role][tier] = cells, keep
    expected = sum(len(points) * len(laws) * len(settings["scores"]) for points, laws in specifications.values())
    if expected != settings["formal_calibration_cells"]:
        raise RuntimeError("The prespecified system-factorial cell count changed")
    alpha = settings["formal_calibration_family_alpha"] / expected
    generic = tuple(name for name in GENERIC if name != "estimator_disagreement") + ("reconstruction_point", "threshold_margin_C", "deployable_adjustment_C")
    operating, costs, predictions, availability = [], [], [], []
    for tier, (methods, cdfs) in specifications.items():
        for method in methods:
            for law in cdfs:
                train, calibration = (matrices[role][tier][(method, law)].loc[common[role][tier]].copy() for role in ("development", "calibration"))
                test = matrices["test"][tier][(method, law)]
                units = [set(frame.independence_group) for frame in (train, calibration, test)]
                if any(units[i] & units[j] for i, j in ((0, 1), (0, 2), (1, 2))):
                    raise RuntimeError("A system-factorial group crosses roles")
                for role in F.ROLES:
                    frame = matrices[role][tier][(method, law)]
                    availability.append({"tier": tier, "role": role, "point": method, "law": law, "original_candidates": len(frame),
                                         "point_available": int(np.isfinite(frame.reconstruction_point).sum()), "cdf_available": int(frame.cdf_available.sum()),
                                         "common_candidates": int(common[role][tier].sum()), "groups": frame.independence_group.nunique()})
                cal_samples = np.stack(calibration.h30_samples_C.to_numpy())[:, :32]
                raw_cal = np.mean(cal_samples > calibration.local_hot_threshold_C.to_numpy()[:, None], axis=1)
                cdf_available = test.cdf_available.to_numpy()
                point_available = np.isfinite(test.reconstruction_point.to_numpy())
                valid = cdf_available & point_available
                probability = np.full(len(test), np.nan)
                samples = np.stack(test.loc[cdf_available, "h30_samples_C"].to_numpy())[:, :32]
                raw_test = np.mean(samples > test.loc[cdf_available, "local_hot_threshold_C"].to_numpy()[:, None], axis=1)
                probability[cdf_available] = D.probability_calibration(raw_cal, calibration.truth_hottest30 > calibration.local_hot_threshold_C, raw_test)
                for kind in settings["scores"]:
                    features = generic + CDF_FEATURES + (tuple(name + "_CDF" for name in WINDOW_INFORMATION) if kind == "boost_window" else ())
                    if kind == "native_CDF":
                        train_score, cal_score, score = [frame.CDF_failure_probability.to_numpy() for frame in (train, calibration, test)]
                    else:
                        model = D.fit_matched(train, features, train.own_failure.astype(int), objective="probability", seed=parent["head_seed"])
                        train_score, cal_score, score = [D.predict_matched(model, frame, features, objective="probability") for frame in (train, calibration, test)]
                    score = np.where(valid, score, np.inf)
                    candidates = fixed_training_candidates(train_score)
                    empirical = empirical_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates,
                                                     seed=parent["head_seed"], draws=parent["bootstrap_draws"], risk_cap=parent["risk_cap"], alpha=parent["empirical_calibration_alpha"])
                    formal = select_group_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates,
                                                    risk_cap=parent["risk_cap"], alpha=alpha)
                    admitted = valid & (score <= empirical["threshold"])
                    failures = admitted & test.own_failure.to_numpy()
                    matched = test.loc[common["test"][tier]]
                    identity = {"tier": tier, "point": method, "law": law, "score_kind": kind,
                                "n_candidates": len(test), "n_groups": test.independence_group.nunique()}
                    operating.append({**identity, "point_available": int(point_available.sum()), "cdf_available": int(cdf_available.sum()),
                                      "accepted": int(admitted.sum()), "failed": int(failures.sum()), "retention": float(admitted.mean()),
                                      "risk": float(failures.sum() / admitted.sum()) if admitted.any() else np.nan,
                                      "formal_accepted": int((valid & (score <= formal.threshold)).sum()), "formal_status": formal.status,
                                      "formal_alpha_per_cell": alpha, "matched_point_MAE_C": float(np.abs(matched.reconstruction_point - matched.truth_hottest30).mean()),
                                      "matched_test_cases": len(matched), "training_common_cases": len(train), "calibration_common_cases": len(calibration)})
                    costs.extend(F.decision_rows(identity, test, admitted, probability, parent))
                    saved = test[G.KEYS + ["independence_group", "reconstruction_point", "own_failure", "cdf_available"]].copy()
                    saved["tier"], saved["point"], saved["law"], saved["score_kind"] = tier, method, law, kind
                    saved["score"], saved["admitted"], saved["hot_probability"] = score, admitted, probability
                    predictions.append(saved)
    if len(operating) != expected:
        raise RuntimeError("The full point/law/score factorial was not evaluated")
    for name, records in (("operating", operating), ("decision_costs", costs), ("availability", availability)):
        pd.DataFrame(records).to_csv(OUT / (name + ".csv"), index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(OUT / "predictions.parquet", index=False)
    costs = pd.DataFrame(costs)
    if not np.allclose(costs[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1), costs.n_candidates):
        raise RuntimeError("A system decision lost its original-pool denominator")
    print(f"[417] {expected} complete point/law/score cells; own errors and original-pool costs retained", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
