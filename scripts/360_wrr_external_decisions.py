#!/usr/bin/env python3
"""Score frozen deployment plans, preserving magnitude and judgement denominators."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import json
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import wrr_r3_common as C

from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.paths import stable_seed
from stream_recoverability.experiments.v19_revision.learning import certificate_delivery, predict_score
from stream_recoverability.experiments.v19_revision.partial_identification import observed_h30_lower_bound, observationally_resolved_hot

OUT = C.RUN / "r3_10_external_decisions"
TRANSFER = C.RUN / "r3_09_frozen_transfer"
M359 = C.load_script("r3_deployment_interface", C.ROOT / "scripts/359_wrr_freeze_and_transfer.py")
M357 = C.load_script("r3_evaluation_interface", C.ROOT / "scripts/357_wrr_decision_report.py")
M351 = C.load_script("r3_external_event_labels", C.ROOT / "scripts/351_wrr_representative_recovery.py")


def bootstrap_metrics(frame: pd.DataFrame, admitted: np.ndarray, settings: dict) -> dict:
    units, group_index = np.unique(frame.independence_group.astype(str), return_inverse=True)
    accepted = np.bincount(group_index, weights=admitted.astype(float), minlength=len(units))
    failed = np.bincount(group_index, weights=admitted * frame.policy_bad.to_numpy(), minlength=len(units))
    total = np.bincount(group_index, minlength=len(units))
    if len(units) < 2:
        return {"retention_ci_low": np.nan, "retention_ci_high": np.nan, "risk_ci_low": np.nan, "risk_ci_high": np.nan, "n_independent_groups": len(units)}
    weights = np.random.default_rng(settings["seed"]).multinomial(len(units), np.full(len(units), 1 / len(units)), size=settings["bootstrap_draws"])
    sampled_admission = weights @ accepted
    sampled_retention = sampled_admission / (weights @ total)
    risk = np.divide(weights @ failed, sampled_admission, out=np.full(len(weights), np.nan), where=sampled_admission > 0)
    finite = risk[np.isfinite(risk)]
    risk_limits = np.quantile(finite, [0.025, 0.975]) if len(finite) else [np.nan, np.nan]
    retention_limits = np.quantile(sampled_retention, [0.025, 0.975])
    return {"retention_ci_low": float(retention_limits[0]), "retention_ci_high": float(retention_limits[1]), "risk_ci_low": float(risk_limits[0]), "risk_ci_high": float(risk_limits[1]), "n_independent_groups": len(units), "zero_admission_bootstrap_draws": int((sampled_admission == 0).sum())}


def cost_scenarios(frame: pd.DataFrame, admitted: np.ndarray, threshold: np.ndarray, lower: np.ndarray, settings: dict, identity: dict) -> list[dict]:
    truth_hot = frame.truth_hottest30.to_numpy() > threshold
    prediction = frame.policy_metric.to_numpy()
    available = np.isfinite(prediction)
    predicted_hot = prediction > threshold
    units, group_index = np.unique(frame.independence_group.astype(str), return_inverse=True)
    group_total = np.bincount(group_index, minlength=len(units))
    weights = np.random.default_rng(stable_seed("r3-external-utility", len(units))).multinomial(len(units), np.full(len(units), 1 / len(units)), size=settings["bootstrap_draws"])
    baseline = M357.confusion(frame, available, threshold)
    rows = []
    variants = [("magnitude_screen", admitted, predicted_hot, 0.0)]
    for margin in (0.0, 0.1, 0.2):
        verified = observationally_resolved_hot(lower, threshold, measurement_margin_c=margin)
        if (verified & ~truth_hot).any():
            raise RuntimeError("An observational lower-bound label contradicts the complete-record reference")
        variants.append(("screen_plus_observed_hot", admitted | verified, predicted_hot | verified, margin))
    baseline_fn = available & truth_hot & ~predicted_hot
    baseline_fp = available & ~truth_hot & predicted_hot
    for variant, judged, hot, margin in variants:
        counts = M357.confusion(frame, judged, threshold, hot)
        false_negative = judged & truth_hot & ~hot
        false_positive = judged & ~truth_hot & hot
        extra_abstention = (~judged).astype(float) - (~available).astype(float)
        fn_group = np.bincount(group_index, weights=false_negative.astype(float) - baseline_fn.astype(float), minlength=len(units))
        fp_group = np.bincount(group_index, weights=false_positive.astype(float) - baseline_fp.astype(float), minlength=len(units))
        abstention_group = np.bincount(group_index, weights=extra_abstention, minlength=len(units))
        for missed_cost in settings["false_negative_costs"]:
            original_loss = missed_cost * baseline["false_negative"] + baseline["false_positive"]
            fixed_loss = missed_cost * counts["false_negative"] + counts["false_positive"]
            for abstention_cost in settings["abstention_costs"]:
                difference = (fixed_loss - original_loss + abstention_cost * extra_abstention.sum()) / len(frame)
                per_group = missed_cost * fn_group + fp_group + abstention_cost * abstention_group
                draws = (weights @ per_group) / (weights @ group_total)
                lower_loss, upper_loss = np.quantile(draws, [0.025, 0.975]) if len(units) > 1 else [np.nan, np.nan]
                rows.append({**identity, "judgement_policy": variant, "measurement_margin_C": margin, "false_negative_cost": missed_cost, "abstention_cost": abstention_cost, "loss_difference_vs_reconstruct_all": float(difference), "loss_difference_ci_low": float(lower_loss), "loss_difference_ci_high": float(upper_loss), "magnitude_admissions": int(admitted.sum()), "judgement_admissions": int(judged.sum()), "observationally_rescued_labels": int((judged & ~admitted).sum()), **counts})
    return rows


def add_observation_and_event_information(frame: pd.DataFrame, source: Path, protocol_name: str) -> pd.DataFrame:
    jobs = json.loads((source / "jobs.json").read_text())["jobs"]
    panel_paths = {job["network_id"]: job["input_path"] for job in jobs}
    raw = C.ROOT / "data/external/wrr_revision_20261020c/hydroshare"
    flow = pd.read_csv(raw / "MEAS_Qt", sep=None, engine="python")
    flow_date = next(name for name in flow if name.lower() in {"date", "datetime"})
    flow.index = pd.to_datetime(flow[flow_date], errors="coerce")
    published = pd.read_csv(raw / "WaterTemp_ExtremeEvents_perCatchment.csv")
    for name in ("start_date", "end_date"):
        if name in published:
            text = published[name].astype(str)
            published[name] = pd.to_datetime(text, errors="coerce", dayfirst=not text.str.match(r"^\d{4}-").all())

    @lru_cache(maxsize=64)
    def panel(network: str) -> pd.DataFrame:
        value = read_temperature_panel(panel_paths[network])
        value.columns = value.columns.astype(str)
        return value

    @lru_cache(maxsize=None)
    def annual(network: str, station: str, year: int):
        target = panel(network)[station]
        held = target.index.year == year
        dates = target.index[held]
        truth = target.loc[held].to_numpy(dtype=float)
        allowed = pd.Series(target.index.year < year if protocol_name == "strictly_prior_years" else target.index.year != year, index=target.index)
        threshold = M351.seasonal_threshold(target, allowed, dates, 0.95)
        events = M351.event_days(truth, threshold, 3)
        low_flow = np.zeros(len(dates), dtype=bool)
        q_available = np.zeros(len(dates), dtype=bool)
        if station in flow:
            series = pd.to_numeric(flow[station], errors="coerce")
            series = series.where(series >= 0)
            history = series.loc[series.index.year < year if protocol_name == "strictly_prior_years" else series.index.year != year]
            monthly = history.groupby(history.index.month).quantile(0.2)
            current = series.reindex(dates).to_numpy(dtype=float)
            limits = pd.Series(dates.month).map(monthly).to_numpy(dtype=float)
            q_available = np.isfinite(current) & np.isfinite(limits)
            low_flow = q_available & (current <= limits)
        published_days = np.zeros(len(dates), dtype=bool)
        if {"station_ID", "start_date", "end_date"}.issubset(published):
            selected = published.loc[published.station_ID.astype(str).eq(station)]
            for episode in selected.itertuples(index=False):
                published_days |= (dates >= episode.start_date) & (dates <= episode.end_date)
        return truth, events, low_flow, q_available, published_days

    lower_values, compound, source_event_overlap, flow_coverage = [], [], [], []
    for row in frame.itertuples(index=False):
        truth, events, low_flow, q_available, published_days = annual(row.network_id, row.station_id, int(row.year))
        mask = np.zeros(len(truth), dtype=bool)
        for run in row.mask_runs.split(";"):
            start, length = map(int, run.split(":"))
            mask[start : start + length] = True
        observed = truth.copy()
        observed[mask] = np.nan
        lower = observed_h30_lower_bound(observed)
        if np.isfinite(row.policy_metric) and lower > row.policy_metric + 1e-8:
            raise RuntimeError("Delivered reconstruction changed an observed complete window")
        lower_values.append(lower)
        required = mask & events
        if (required & low_flow).any():
            compound.append("gap_intersects_compound_event")
        elif not required.any():
            compound.append("no_gap_thermal_event_overlap")
        elif not q_available[required].all():
            compound.append("flow_incomplete_on_gap_event_days")
        else:
            compound.append("observed_no_compound_event_overlap")
        flow_coverage.append(float(q_available[required].mean()) if required.any() else np.nan)
        source_event_overlap.append(bool((mask & published_days).any()))
    result = frame.copy()
    result["observed_h30_lower_bound"] = lower_values
    result["compound_heat_lowflow"] = compound
    result["published_event_overlap"] = source_event_overlap
    result["gap_event_discharge_coverage"] = flow_coverage
    return result


def smoke() -> None:
    bank = json.loads((TRANSFER / "head_bank.json").read_text())["heads"]
    record = next(item for item in bank if item["status"] == "fitted" and item["name"] == "uncertain_support" and item["regime"] == "source_only" and item["scope"] == "documented_daily_mean" and item["protocol"] == "leave_one_year_out")
    source = C.source_cases("leave_one_year_out")
    data = pd.read_parquet(source)
    data = data.loc[data.statistic_class.eq("daily_mean")].head(1024)
    head = joblib.load(record["model_path"])
    score = predict_score(head["model"], data, tuple(head["features"]), head["kind"])
    cutoff = record["source_thresholds"]["empirical"]
    admitted = score <= (cutoff if cutoff is not None else -np.inf)
    counts = M357.confusion(data, admitted, data.local_hot_threshold_C.to_numpy())
    if sum(counts[name] for name in ["true_positive", "true_negative", "false_negative", "false_positive", "abstained"]) != len(data):
        raise RuntimeError("Original candidate denominator was not preserved")
    C.write_json(OUT / "source_smoke.json", {"n_old_cases": len(data), "denominator_identity_verified": True, "new_external_values_or_outcomes_used": False})
    print("[360] old-source deployment smoke passed", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["calibration", "test"], default="test")
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--family", choices=["admission", "crossed", "events", "real_calendars"], default="admission")
    parser.add_argument("--cofailure", type=float, choices=[0, 0.5, 1], default=0)
    parser.add_argument("--source-smoke", action="store_true")
    args = parser.parse_args()
    settings = C.protocol()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.source_smoke:
        smoke()
        return 0
    gate = C.load_script("r3_external_decision_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access(args.role)
    source = C.RUN / "r3_08_external_recovery" / args.role / args.protocol / args.family / f"cofailure_{args.cofailure:g}"
    frame = pd.read_parquet(source / "cases.parquet")
    if args.protocol == "strictly_prior_years":
        frame = frame.loc[frame.year.between(2019, 2022)]
        if (frame.maximum_training_calendar_year >= frame.year).any():
            raise RuntimeError("External prospective case uses future observations")
    frame = add_observation_and_event_information(frame, source, args.protocol)
    heads = {item["identity"]: item for item in json.loads((TRANSFER / "head_bank.json").read_text())["heads"]}
    plans = json.loads((TRANSFER / "deployment_plans.json").read_text())["plans"]
    output = OUT / args.role / args.protocol / args.family / f"cofailure_{args.cofailure:g}"
    output.mkdir(parents=True, exist_ok=True)
    operating, costs, strata, comparisons, group_rows = [], [], [], [], []
    prediction_cache, admissions = {}, {}
    for plan in plans:
        record = heads[plan["head_identity"]]
        if record["protocol"] != args.protocol:
            continue
        selected = frame.loc[frame.provider.eq(plan["target_provider"])]
        if record["scope"] == "documented_daily_mean":
            selected = selected.loc[selected.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
        selected = selected.reset_index(drop=True)
        if selected.empty:
            continue
        cache_key = (record["identity"], plan["target_provider"])
        if cache_key not in prediction_cache:
            if record["model_path"]:
                model = joblib.load(record["model_path"])
                if model["kind"] == "certificate_joint":
                    selected = certificate_delivery(model["model"], selected)
                scores = predict_score(model["model"], selected, tuple(model["features"]), model["kind"])
            else:
                scores = M359.raw_score(selected, record["name"])
            prediction_cache[cache_key] = (scores, selected)
        scores, selected = prediction_cache[cache_key]
        identity = {"arm": record["name"], "mode": plan["mode"], "scope": record["scope"], "provider": plan["target_provider"], "protocol": args.protocol, "family": args.family, "cofailure": args.cofailure}
        for decision in ("empirical", "certified"):
            cutoff = plan["thresholds"][decision]
            admitted = scores <= (cutoff if cutoff is not None else -np.inf)
            operating.append({**identity, "selection": decision, **M357.pooled_metrics(selected, admitted), **bootstrap_metrics(selected, admitted, settings)})
            if decision != "empirical":
                continue
            key = (plan["mode"], record["scope"], plan["target_provider"], record["name"])
            admissions[key] = (selected, admitted)
            for dimension in ["hydrological_stratum", "warm_anomaly", "compound_heat_lowflow", "published_event_overlap", "event_phase", "policy_choice"]:
                for value, block in selected.groupby(dimension):
                    indices = block.index.to_numpy()
                    strata.append({**identity, "stratum_type": dimension, "stratum": value, **M357.pooled_metrics(block, admitted[indices]), **bootstrap_metrics(block, admitted[indices], settings)})
            for group, block in selected.groupby("independence_group"):
                indices = block.index.to_numpy()
                group_rows.append({**identity, "group": group, "inference_status": "one_dependent_component_not_a_risk_certificate", **M357.pooled_metrics(block, admitted[indices])})
            for threshold_name, threshold in [("local_training_q90", selected.local_hot_threshold_C.to_numpy()), ("fixed18", np.full(len(selected), 18.0)), ("fixed20", np.full(len(selected), 20.0))]:
                costs.extend(cost_scenarios(selected, admitted, threshold, selected.observed_h30_lower_bound.to_numpy(), settings, {**identity, "threshold_definition": threshold_name}))
    reference_pairs = [("uncertain_support", "generic_target_disagreement"), ("uncertain_support", "generic_direct_h30_uncertainty"), ("uncertain_support", "generic_both_diagnostics"), ("uncertain_support", "certificate"), ("uncertain_support", "policy_certificate"), ("uncertain_support", "certificate_joint"), ("uncertain_support", "complete_diagnostic_model"), ("generic_target_disagreement", "generic_daily_disagreement")]
    for key, (selected, admitted) in admissions.items():
        mode, scope, provider, left = key
        for candidate_left, right in reference_pairs:
            other = (mode, scope, provider, right)
            if left != candidate_left or other not in admissions:
                continue
            right_frame, right_admission = admissions[other]
            if not selected[["station_id", "year", "realization_id"]].equals(right_frame[["station_id", "year", "realization_id"]]):
                raise RuntimeError("External contrasts do not share an identical candidate pool")
            comparison = M357.paired_retention(selected, admitted, right_admission, seed=stable_seed("r3-new-comparison", mode, scope, provider, left, right), draws=settings["bootstrap_draws"])
            comparisons.append({"mode": mode, "scope": scope, "provider": provider, "left": left, "right": right, **comparison})
    for name, rows in [("operating_points", operating), ("decision_costs", costs), ("stratum_results", strata), ("paired_contrasts", comparisons), ("group_results", group_rows)]:
        pd.DataFrame(rows).to_csv(output / f"{name}.csv", index=False)
    frame.to_parquet(output / "case_information.parquet", index=False)
    interval_rows = []
    for provider, block in frame.groupby("provider"):
        finite = np.isfinite(block.h30_interval_lower_C) & np.isfinite(block.h30_interval_upper_C)
        covered = finite & (block.truth_hottest30 >= block.h30_interval_lower_C) & (block.truth_hottest30 <= block.h30_interval_upper_C)
        interval_rows.append({"provider": provider, "n_original_candidates": len(block), "n_finite_bands": int(finite.sum()), "nominal_scenario_mass": 0.9, "complete_candidate_coverage": float(covered.mean()), "finite_band_coverage": float(covered[finite].mean()) if finite.any() else np.nan, "mean_width_C": float(block.loc[finite, "h30_interval_width_C"].mean()) if finite.any() else np.nan, "claim": "uncalibrated fixed-policy scenario band; not selected-risk control"})
    pd.DataFrame(interval_rows).to_csv(output / "scenario_interval_diagnostics.csv", index=False)
    C.write_json(output / "summary.json", {"external_role": args.role, "protocol": args.protocol, "family": args.family, "cofailure": args.cofailure, "n_original_candidates": len(frame), "n_original_station_years": len(frame[["station_id", "year"]].drop_duplicates()), "n_frozen_plan_operating_points": len(operating), "n_original_pool_cost_scenarios": len(costs), "observed_hot_rescue_changes_magnitude_admission": False, "guarantee_target": "complete recorded daily-mean reference, with separate measurement-margin sensitivities", "new_test_models_or_thresholds_refitted": False})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"cases": source / "cases.parquet", "plans": TRANSFER / "deployment_plans.json", "method_lock": C.RUN / "method_lock.json", "deployment_lock": C.RUN / "deployment_lock.json"}))
    print(f"[360] {len(frame)} original candidates; frozen decisions and downstream information scored", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
