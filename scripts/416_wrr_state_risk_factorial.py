#!/usr/bin/env python3
"""Compare conditional H30 laws at one fixed numerical point on opened data."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
import importlib
import json

import numpy as np
import pandas as pd

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision import decision_baselines as D
from stream_recoverability.experiments.v19_revision.learning import GENERIC, WINDOW_INFORMATION, empirical_threshold
from stream_recoverability.experiments.v19_revision.risk import fixed_training_candidates, select_group_threshold
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps
from stream_recoverability.experiments.v19_revision.target_risk_laws import CDF_FEATURES

G = importlib.import_module("415_wrr_state_risk_generator")
OUT = G.OUT / "factorial"
ROLES = ("development", "calibration", "test")


def role_data(role):
    frame = pd.read_parquet(G.OUT / "trajectories" / role / "cases.parquet")
    source = C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0/cases.parquet"
    base = pd.read_parquet(source)
    base = base.loc[base.replicate.eq(0) & base.design_family.eq("crossed_contiguous") & base.statistic_class.eq("daily_mean")].copy()
    data = {}
    for law in G.LAWS:
        selected = frame.loc[frame.law.eq(law)]
        if len(selected) != len(base):
            raise RuntimeError("A declared law lost original candidates")
        extra = selected[G.KEYS + ["status", "h30_samples_C", *CDF_FEATURES, *(name + "_CDF" for name in WINDOW_INFORMATION)]]
        merged = base.merge(extra, on=G.KEYS, how="left", validate="one_to_one", suffixes=("", "_law"))
        merged["reconstruction_point"] = merged.policy_metric
        merged["threshold_margin_C"] = merged.reconstruction_point - merged.local_hot_threshold_C
        merged["own_failure"] = ~np.isfinite(merged.reconstruction_point) | (np.abs(merged.reconstruction_point - merged.truth_hottest30) > .5)
        merged["cdf_available"] = merged.h30_samples_C.map(lambda value: isinstance(value, (list, np.ndarray)) and len(value) >= 32 and np.isfinite(value).all())
        data[law] = merged
    return data


def common_support(data, laws):
    first = data[laws[0]]
    keep = np.ones(len(first), dtype=bool)
    for law in laws:
        if not first[G.KEYS].equals(data[law][G.KEYS]):
            raise RuntimeError("CDF laws do not share the same candidate ordering")
        keep &= data[law].cdf_available.to_numpy() & np.isfinite(data[law].reconstruction_point.to_numpy())
    return keep


def quality(frame, keep, *, role, law, support, draws=32):
    eligible = keep & frame.cdf_available.to_numpy()
    sizes = frame.h30_samples_C.map(lambda value: len(value) if isinstance(value, (list, np.ndarray)) else 0)
    eligible &= sizes.to_numpy() >= draws
    block = frame.loc[eligible]
    if not len(block):
        return None
    samples = np.stack(block.h30_samples_C.to_numpy())[:, :draws]
    truth, point = block.truth_hottest30.to_numpy(), block.reconstruction_point.to_numpy()
    lower, upper = np.quantile(samples, [.05, .95], axis=1)
    median = np.median(samples, axis=1)
    failure_p = np.mean(np.abs(samples - point[:, None]) > .5, axis=1)
    hot_p = np.mean(samples > block.local_hot_threshold_C.to_numpy()[:, None], axis=1)
    point_valid = np.isfinite(point)
    return {"role": role, "law": law, "support": support, "draws": draws,
            "original_candidates": len(frame), "n": len(block), "groups": block.independence_group.nunique(),
            "station_years": len(block.drop_duplicates(["station_id", "year"])),
            "fixed_point_MAE_C": float(np.abs(point[point_valid] - truth[point_valid]).mean()) if point_valid.any() else np.nan,
            "CDF_median_MAE_C": float(np.abs(median - truth).mean()),
            "CDF_median_bias_C": float((median - truth).mean()), "CRPS_C": float(np.mean([sample_crps(values, value) for values, value in zip(samples, truth)])),
            "coverage90": float(((lower <= truth) & (truth <= upper)).mean()), "width90_C": float((upper - lower).mean()),
            "n_failure_probability_available": int(point_valid.sum()),
            "failure_Brier": float(np.mean((failure_p[point_valid] - block.own_failure.to_numpy()[point_valid]) ** 2)) if point_valid.any() else np.nan,
            "hot_Brier": float(np.mean((hot_p - (truth > block.local_hot_threshold_C.to_numpy())) ** 2))}


def select():
    settings = json.loads(G.CONFIG.read_text())
    data = role_data("development")
    common = common_support(data, settings["same_air_information_laws"])
    rows = [quality(frame, common, role="development", law=law, support="common_air", draws=32) for law, frame in data.items() if law in settings["same_air_information_laws"]]
    table = pd.DataFrame(rows)
    candidates = table.loc[table.law.isin(["seasonal_slow", "seasonal_air_slow"])].sort_values(["CRPS_C", "law"])
    chosen = candidates.iloc[0]
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "development_selection_quality.csv", index=False)
    C.write_json(OUT / "development_selection.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_law": chosen.law, "selection_endpoint": "old_development_common_air_H30_CRPS_at_32_draws",
        "calibration_or_test_used_by_selection": False, "previously_opened_old_outcomes": True,
        "prospective_predictive_bank_registered": False, "new_confirmation": False})
    print(f"[416] old-development selection={chosen.law}; no prospective candidate or new-confirmation claim", flush=True)
    return 0


def decision_rows(identity, frame, admitted, probability, settings):
    truth = (frame.truth_hottest30 > frame.local_hot_threshold_C).to_numpy()
    point_available = np.isfinite(frame.reconstruction_point.to_numpy())
    point_hot = (frame.reconstruction_point.to_numpy() > frame.local_hot_threshold_C.to_numpy()).astype(int)
    rows = []
    for fn_cost in settings["false_negative_costs"]:
        for abstention_cost in settings["abstention_costs"]:
            all_action = np.where(point_available, point_hot, 2)
            policies = {"reconstruct_all": all_action, "magnitude_screen": np.where(admitted, point_hot, 2),
                        "direct_calibrated_CDF_cost": np.where(np.isfinite(probability), D.cost_action(np.nan_to_num(probability, nan=.5), fn_cost, abstention_cost), 2),
                        "all_unknown": np.full(len(frame), 2), "all_hot": np.ones(len(frame), dtype=int), "all_cool": np.zeros(len(frame), dtype=int)}
            for name, action in policies.items():
                rows.append({**identity, "policy": name, "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                             "loss": float(D.action_loss(action, truth, fn_cost, abstention_cost).mean()), **D.action_counts(action, truth)})
            retention = float(admitted.sum() / point_available.sum()) if point_available.any() else 0.
            base_loss = D.action_loss(all_action, truth, fn_cost, abstention_cost)
            counts = D.action_counts(all_action, truth)
            random_counts = dict(counts)
            for key in ("true_positive", "true_negative", "false_negative", "false_positive"):
                random_counts[key] *= retention
            random_counts["unknown"] = int((~admitted).sum())
            rows.append({**identity, "policy": "random_matched_screen", "fn_cost": fn_cost, "abstention_cost": abstention_cost,
                         "loss": float((retention * base_loss + (1 - retention) * abstention_cost).mean()),
                         "counts_are_expectations": True, **random_counts})
    return rows


def evaluate():
    settings = json.loads(G.CONFIG.read_text())
    data = {role: role_data(role) for role in ROLES}
    common = {role: common_support(block, list(G.LAWS)) for role, block in data.items()}
    quality_rows, operating, costs, groups, curves, reliability, predictions = [], [], [], [], [], [], []
    generic = tuple(name for name in GENERIC if name != "estimator_disagreement") + ("reconstruction_point", "threshold_margin_C", "deployable_adjustment_C")
    direct_features = generic + CDF_FEATURES
    window_features = direct_features + tuple(name + "_CDF" for name in WINDOW_INFORMATION)
    family_cells = len(G.LAWS) * len(settings["score_heads"])
    formal_alpha = settings["formal_calibration_family_alpha"] / family_cells
    for role, block in data.items():
        for law, frame in block.items():
            for support, keep in (("all_available", np.ones(len(frame), dtype=bool)), ("common_all_laws", common[role])):
                for draws in settings["sampling_sensitivity"]:
                    record = quality(frame, keep, role=role, law=law, support=support, draws=draws)
                    if record:
                        quality_rows.append(record)
    for law in G.LAWS:
        train, calibration = (data[role][law].loc[common[role]].copy() for role in ("development", "calibration"))
        test = data["test"][law]
        role_groups = [set(frame.independence_group) for frame in (train, calibration, test)]
        if any(role_groups[i] & role_groups[j] for i, j in ((0, 1), (0, 2), (1, 2))):
            raise RuntimeError("An old component crosses learning, calibration and evaluation roles")
        reference_failure = data["test"][G.LAWS[0]].own_failure.to_numpy()
        if not np.array_equal(reference_failure, test.own_failure.to_numpy()):
            raise RuntimeError("Changing a law changed the delivered numerical error event")
        sample_cal = np.stack(calibration.h30_samples_C.to_numpy())[:, :32]
        raw_cal = np.mean(sample_cal > calibration.local_hot_threshold_C.to_numpy()[:, None], axis=1)
        cdf_valid = test.cdf_available.to_numpy()
        valid = cdf_valid & np.isfinite(test.reconstruction_point.to_numpy())
        probability = np.full(len(test), np.nan)
        raw_test = np.mean(np.stack(test.loc[cdf_valid, "h30_samples_C"].to_numpy())[:, :32] > test.loc[cdf_valid, "local_hot_threshold_C"].to_numpy()[:, None], axis=1)
        probability[cdf_valid] = D.probability_calibration(raw_cal, calibration.truth_hottest30 > calibration.local_hot_threshold_C, raw_test)
        for kind in settings["score_heads"]:
            features = window_features if kind == "boost_window" else direct_features
            if kind == "native_CDF":
                train_score, cal_score, score = (frame.CDF_failure_probability.to_numpy() for frame in (train, calibration, test))
            else:
                model = D.fit_matched(train, features, train.own_failure.astype(int), objective="probability", seed=settings["head_seed"])
                train_score, cal_score, score = [D.predict_matched(model, frame, features, objective="probability") for frame in (train, calibration, test)]
            score = np.where(valid, score, np.inf)
            candidates = fixed_training_candidates(train_score)
            empirical = empirical_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates,
                                             seed=settings["head_seed"], draws=settings["bootstrap_draws"], risk_cap=settings["risk_cap"], alpha=settings["empirical_calibration_alpha"])
            formal = select_group_threshold(cal_score, calibration.own_failure.to_numpy(), calibration.independence_group.to_numpy(), candidates,
                                            risk_cap=settings["risk_cap"], alpha=formal_alpha)
            admitted = valid & (score <= empirical["threshold"])
            failed = admitted & test.own_failure.to_numpy()
            identity = {"law": law, "score_kind": kind, "information_tier": "air_and_flow" if law == "seasonal_air_flow_slow" else "available_air",
                        "n_candidates": len(test), "n_groups": test.independence_group.nunique()}
            ga, gb = [], []
            for group, positions in test.groupby("independence_group").indices.items():
                a, b = float(admitted[positions].mean()), float(failed[positions].mean())
                ga.append(a); gb.append(b)
                groups.append({**identity, "group": group, "group_candidates": len(positions), "admission_fraction": a, "failure_and_admission_fraction": b})
            operating.append({**identity, "cdf_available": int(valid.sum()), "accepted": int(admitted.sum()), "failed": int(failed.sum()),
                              "retention": float(admitted.mean()), "risk": float(failed.sum() / admitted.sum()) if admitted.any() else np.nan,
                              "equal_group_retention": float(np.mean(ga)), "equal_group_risk": float(np.mean(gb) / np.mean(ga)) if np.mean(ga) else np.nan,
                              "formal_accepted": int((valid & (score <= formal.threshold)).sum()), "formal_status": formal.status,
                              "formal_alpha_per_cell": formal_alpha, "training_common_candidates": len(train), "calibration_common_candidates": len(calibration)})
            costs.extend(decision_rows(identity, test, admitted, probability, settings))
            saved = test[G.KEYS + ["independence_group", "own_failure", "reconstruction_point", "cdf_available"]].copy()
            saved["law"], saved["score_kind"] = law, kind
            saved["score"], saved["admitted"], saved["hot_probability"] = score, admitted, probability
            predictions.append(saved)
            matched = test.loc[common["test"]].copy()
            matched_score = score[common["test"]]
            keys = matched[G.KEYS].astype(str).agg("|".join, axis=1).to_numpy()
            order = np.lexsort((keys, matched_score))
            failure = matched.own_failure.to_numpy()[order]
            for fraction in np.arange(.05, 1.001, .05):
                count = min(len(order), max(1, int(round(fraction * len(order)))))
                curves.append({**identity, "support": "common_all_laws", "matched_n": len(order), "requested_retention": fraction,
                               "accepted": count, "risk": float(failure[:count].mean()), "counts_are_independent_events": False})
        raw_failure_p = test.loc[valid, "CDF_failure_probability"].to_numpy()
        actual_failure = test.loc[valid, "own_failure"].to_numpy()
        for lower in np.arange(0, 1, .1):
            keep = (raw_failure_p >= lower) & (raw_failure_p < lower + .1 if lower < .9 else raw_failure_p <= 1)
            reliability.append({"law": law, "endpoint": "fixed_point_tolerance_exceedance", "bin_lower": lower,
                                "n": int(keep.sum()), "mean_probability": float(raw_failure_p[keep].mean()) if keep.any() else np.nan,
                                "observed_fraction": float(actual_failure[keep].mean()) if keep.any() else np.nan})
    for name, rows in (("distribution_quality", quality_rows), ("operating", operating), ("decision_costs", costs),
                       ("group_results", groups), ("fixed_retention_risk", curves), ("failure_reliability", reliability)):
        pd.DataFrame(rows).to_csv(OUT / (name + ".csv"), index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(OUT / "predictions.parquet", index=False)
    counts = pd.DataFrame(costs)[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1)
    if not np.allclose(counts, len(data["test"][G.LAWS[0]])):
        raise RuntimeError("A downstream policy lost original candidates")
    print(f"[416] {family_cells} matched cells; all original test candidates retained; no new confirmation", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["select", "evaluate"])
    args = parser.parse_args()
    return select() if args.action == "select" else evaluate()


if __name__ == "__main__":
    raise SystemExit(main())
