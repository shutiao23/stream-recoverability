#!/usr/bin/env python3
"""TR2-M4d: the evaluation of the round-2 models on the sealed USGS stations.

The endpoints are those of the second preregistration (N1-N4): realised risk under the frozen label-free
expected-risk rule (R7b, factor k) in both populations, the 90% coverage of
the calibrated D2* intervals in the hardest decision-time difficulty bin, the
bias reduction in the P1 stratum, and the ranking gain over the best published
rule at equal realised risk. Secondary and descriptive results follow the
preregistration: R7a beside R7b, missingness strata, worst region and group,
the HUC8-overlap sensitivity, per-region admission, the recovery law, and the
number of local groups that a local correction factor would need.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_law as L
import wrr_tr_rules as R
from stream_recoverability.seeds import position_index

OUT = T.OUT / "e10_sealed_usgs"
BUNDLE = T.load_script("tr2_bundle_for_sealed", T.ROOT / "scripts/455_tr2_final_models.py")
E4 = T.load_script("tr2_e4_for_sealed", T.ROOT / "scripts/432_tr_e4_estimators.py")
E5 = T.load_script("tr2_e5_for_sealed", T.ROOT / "scripts/436_tr_e5_rules.py")
RULE = T.load_script("tr2_rule_for_sealed", T.ROOT / "scripts/453_tr2_expected_risk.py")
POPULATIONS = (("deploy", "calendar"), ("mech", "crossed"))
LOCAL_SIZES = (2, 4, 8, 16)


def bootstrap_risk(accept: np.ndarray, fail: np.ndarray, groups: np.ndarray, draws: int, seed: int) -> tuple[float, float, float]:
    frame = pd.DataFrame({"g": groups, "a": accept, "f": fail})
    boot = T.group_bootstrap(frame, "g", lambda f: float(f.loc[f.a, "f"].mean()) if f.a.any() else np.nan, draws, seed)
    point = float(fail[accept].mean()) if accept.any() else np.nan
    return point, float(np.nanquantile(boot, 0.025)), float(np.nanquantile(boot, 0.975))


def local_calibration(score: np.ndarray, fail: np.ndarray, groups: np.ndarray, alpha: float, repeats: int, seed: int) -> pd.DataFrame:
    """Correction factor re-estimated on m labelled local groups, applied to the remaining groups."""

    rng = np.random.default_rng(seed)
    unique = np.unique(groups)
    rows = []
    for m in LOCAL_SIZES:
        if m >= len(unique) - 4:
            continue
        for repeat in range(repeats):
            labelled = rng.choice(unique, size=m, replace=False)
            inside = np.isin(groups, labelled)
            accept = RULE.admit(score[inside], np.ones(inside.sum()), alpha, 1.0)
            predicted = score[inside][accept].mean() if accept.any() else np.nan
            ratio = fail[inside][accept].mean() / predicted if accept.any() and predicted > 0 else 1.0
            factor = max(1.0, float(ratio))
            rest = ~inside
            admitted = RULE.admit(score[rest], np.ones(rest.sum()), alpha, factor)
            risk = float(fail[rest][admitted].mean()) if admitted.any() else np.nan
            rows.append({"m": m, "repeat": repeat, "factor": factor, "risk": risk, "retention": float(admitted.mean())})
    frame = pd.DataFrame(rows)
    return frame.groupby("m").agg(share_risk_le_7pct=("risk", lambda r: float((r <= 0.07).mean())), median_risk=("risk", "median"), median_retention=("retention", "median"), median_factor=("factor", "median")).reset_index()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-source", action="store_true", help="exercise the code path on two source regions with the candidate bundle; writes to scratch only")
    args = parser.parse_args()
    global OUT
    if args.dry_run_source:
        OUT = T.SCRATCH / "sealed2_dry_run"
        OUT.mkdir(parents=True, exist_ok=True)
        cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
        cases = cases.loc[cases.region.isin(["usgs_huc07", "usgs_huc18"])].reset_index(drop=True)
        # Alternate stations between two pseudo strata.
        positions = position_index(cases.station_key)
        cases["missingness_stratum"] = np.where(cases.station_key.map(positions) % 2 == 0, "high", "low")
        cases.to_parquet(OUT / "cases.parquet", index=False)
    target = OUT / "sealed_results.json"
    settings = T.settings()
    meta = json.loads((BUNDLE.BUNDLE / "bundle.json").read_text())
    tolerance, alpha = meta["tolerance_c"], meta["expected_risk"]["alpha"]
    factors = meta["expected_risk"]["factor_k"]
    cases = pd.read_parquet(OUT / "cases.parquet")
    n_built = len(cases)
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    scored = BUNDLE.apply_bundle(cases)
    levels = tuple(meta["levels"])
    quantiles = scored[[f"d2_q{int(level * 100):02d}" for level in levels]].to_numpy()
    cases["d2_point"] = scored.d2_point.to_numpy()
    cases["difficulty_group"] = scored.difficulty_group.to_numpy()
    truth = cases.eval_truth_h30.to_numpy()
    fail_d2 = (np.abs(cases.d2_point.to_numpy() - truth) > tolerance).astype(float)
    fail_p0 = (np.abs(cases.h30__policy.to_numpy() - truth) > tolerance).astype(float)
    groups = cases.independence_group.astype(str).to_numpy()
    draws, seed = settings["bootstrap_draws"], settings["seed"]

    # N1 (and R7a, k = 1, missingness strata, HUC8 overlap, per-region admission, worst region and group).
    design = pd.read_csv(OUT / "sealed_design_roster.csv", dtype={"station_id": str}) if not args.dry_run_source else None
    prior = set(design.loc[design.same_HUC8_as_prior_record.astype(str).eq("True"), "station_id"]) if design is not None else set()
    rows, admitted = [], {}
    for population, family in POPULATIONS:
        selected = cases.design_family.eq(family).to_numpy()
        for name in ("R7b", "R7a"):
            score = scored[name].to_numpy()
            for factor_label, factor in (("k", factors[name]), ("k1", 1.0)):
                accept = np.zeros(len(cases), dtype=bool)
                accept[selected] = RULE.admit(score[selected], np.ones(selected.sum()), alpha, factor)
                point, low, high = bootstrap_risk(accept[selected], fail_d2[selected], groups[selected], draws, seed)
                row = {"population": population, "score": name, "factor": factor_label, "factor_value": factor, "n_cases": int(selected.sum()), "n_groups": int(len(np.unique(groups[selected]))),
                       "retention": float(accept[selected].mean()), "risk": point, "risk_lower95": low, "risk_upper95": high,
                       "predicted_risk_admitted": float(score[accept].mean()) if accept.any() else np.nan,
                       "unscreened_risk_D2": float(fail_d2[selected].mean()), "unscreened_risk_P0": float(fail_p0[selected].mean())}
                for stratum in ("high", "low"):
                    inside = selected & cases.missingness_stratum.eq(stratum).to_numpy()
                    row[f"risk_{stratum}_missingness"] = float(fail_d2[inside & accept].mean()) if (inside & accept).any() else np.nan
                    row[f"retention_{stratum}_missingness"] = float(accept[inside].mean()) if inside.any() else np.nan
                    row[f"n_{stratum}_missingness"] = int(inside.sum())
                if name == "R7b" and factor_label == "k":
                    admitted[population] = accept
                    region = pd.DataFrame({"region": cases.region, "a": accept, "f": fail_d2}).loc[selected]
                    by_region = region.groupby("region").apply(lambda b: pd.Series({"n": len(b), "risk": b.loc[b.a, "f"].mean() if b.a.any() else np.nan}))
                    big = by_region.loc[by_region.n >= 200]
                    row["worst_region_risk_ge200"] = float(big.risk.max()) if len(big) else np.nan
                    row["worst_region_ge200"] = str(big.risk.idxmax()) if len(big) and big.risk.notna().any() else ""
                    _, worst = E5.group_risk(accept[selected], fail_d2[selected].astype(bool), groups[selected])
                    row["worst_group_risk_ge20"] = worst
                    # Sensitivity: stations outside HUC8s that also hold a station of the earlier records.
                    outside = selected & ~cases.station_key.str.split("|").str[-1].isin(prior).to_numpy()
                    keep = RULE.admit(score[outside], np.ones(outside.sum()), alpha, factor)
                    row["risk_without_prior_huc8"] = float(fail_d2[outside][keep].mean()) if keep.any() else np.nan
                    row["retention_without_prior_huc8"] = float(keep.mean()) if outside.any() else np.nan
                    # Sensitivity: the rule applied within each HUC2 region instead of the pooled station set.
                    per_region = np.zeros(len(cases), dtype=bool)
                    for value in np.unique(cases.region.to_numpy()[selected]):
                        inside = selected & cases.region.eq(value).to_numpy()
                        per_region[inside] = RULE.admit(score[inside], np.ones(inside.sum()), alpha, factor)
                    row["risk_per_region_admission"] = float(fail_d2[per_region].mean()) if per_region.any() else np.nan
                    row["retention_per_region_admission"] = float(per_region[selected].mean())
                rows.append(row)
    rule_table = pd.DataFrame(rows)
    rule_table.to_csv(OUT / "sealed_expected_risk.csv", index=False)
    primary = {population: rule_table.loc[(rule_table.population == population) & (rule_table.score == "R7b") & (rule_table.factor == "k")].iloc[0] for population, _ in POPULATIONS}

    # N2: coverage of the calibrated 90% intervals by decision-time difficulty group.
    covered = (truth >= quantiles[:, 0]) & (truth <= quantiles[:, -1])
    width = quantiles[:, -1] - quantiles[:, 0]
    coverage = pd.DataFrame({"family": cases.design_family, "group": cases.difficulty_group, "covered": covered, "width": width}).groupby(["family", "group"]).agg(n=("covered", "size"), coverage90=("covered", "mean"), width90=("width", "mean")).reset_index()
    coverage.to_csv(OUT / "sealed_coverage.csv", index=False)
    hardest = cases.difficulty_group.str.startswith("bin4").to_numpy()
    hard_boot = T.group_bootstrap(pd.DataFrame({"g": groups[hardest], "c": covered[hardest]}), "g", lambda f: float(f.c.mean()), draws, seed)

    # N3: bias reduction in the P1 stratum.
    stratum = (cases.design_family.eq("crossed") & cases.policy_choice.eq("air_ridge") & cases.eval_true_peak_hidden_fraction.ge(0.5)).to_numpy()
    error0 = cases.h30__policy.to_numpy() - truth
    error2 = cases.d2_point.to_numpy() - truth

    def reduction(frame: pd.DataFrame) -> float:
        b0 = frame.e0.mean()
        return float(1 - abs(frame.e2.mean()) / abs(b0)) if b0 else np.nan

    p1_frame = pd.DataFrame({"g": groups[stratum], "e0": error0[stratum], "e2": error2[stratum]})
    p1_boot = T.group_bootstrap(p1_frame, "g", reduction, draws, seed) if len(p1_frame) else np.array([np.nan])

    # N4: the full rule comparison and the ranking gain at equal realised risk.
    features = R.mask_features(cases)
    fixed = R.fixed_rules(features, cases, as_written=True)
    law = L.apply_law(cases, tolerance, True, "v2")
    law_p = L.apply_law(cases, tolerance, True, "v2p")
    scores = {
        **R.parametric_scores(features, cases),
        "R4_daily_disagreement": cases.daily_estimator_disagreement, "R5_h30_target_disagreement": cases.estimator_disagreement,
        "R6_recovery_law_pfail": law.law_pfail,
        "R7a_target_aware_pfail (D2* distribution)": scored.R7a.reset_index(drop=True),
        "R7b_direct_failure_probability (D2*)": scored.R7b.reset_index(drop=True),
    }
    delivered = {"P0": cases.h30__policy, "Pobs": cases.h30__observed_days, "D2*": cases.d2_point}
    current = list(fixed) + ["R1_annual_missing_fraction", "R2_warm_missing_fraction", "R3_observed_lower_bound (NRFA-type)"]
    tables, gains = [], {}
    for population, family in POPULATIONS:
        weight = cases.design_family.eq(family).to_numpy().astype(float)
        frame, curves = E5.evaluate(cases, scores, fixed, delivered, weight, tolerance, settings["risk_levels"])
        frame.insert(0, "population", population)
        tables.append(frame)
        curves.insert(0, "population", population)
        curves.to_parquet(OUT / f"sealed_curves_{population}.parquet", index=False)
        gains[population] = E5.endpoint(cases, scores, fixed, delivered, weight, tolerance, current, "P0", "D2*", "R7b_direct_failure_probability (D2*)")
        gains[f"{population}_R7a"] = E5.endpoint(cases, scores, fixed, delivered, weight, tolerance, current, "P0", "D2*", "R7a_target_aware_pfail (D2* distribution)")
        # Failure rate among the years each fixed rule rejects (Table 2 column), for D2*.
        selected = weight > 0
        for name, accept in fixed.items():
            rejected = selected & ~accept.to_numpy()
            frame.loc[(frame.rule == name) & (frame.delivered == "D2*"), "rejected_failure_rate_D2"] = float(fail_d2[rejected].mean()) if rejected.any() else np.nan
    pd.concat(tables, ignore_index=True).to_csv(OUT / "sealed_risk_retention.csv", index=False)

    # Estimators on the sealed cases.
    table = {
        "P0": {"point": cases.h30__policy}, "Pobs": {"point": cases.h30__observed_days}, "P1": {"point": cases.get("h30__air2stream3")},
        "P3": {"point": cases.state_h30_q50, "levels": levels, "quantiles": cases[[f"state_h30_q{int(q * 100):02d}" for q in levels]].to_numpy()},
        "P3raw": {"point": cases.raw_h30_q50, "levels": levels, "quantiles": cases[[f"raw_h30_q{int(q * 100):02d}" for q in levels]].to_numpy()},
        "D2*": {"point": cases.d2_point, "levels": levels, "quantiles": quantiles},
    }
    metrics = []
    for population, family in POPULATIONS:
        frame = E4.metrics(cases, table, "h30", pd.Series(cases.design_family.eq(family).astype(float).to_numpy(), index=cases.index), tolerance)
        frame.insert(0, "population", population)
        metrics.append(frame)
    pd.concat(metrics, ignore_index=True).to_csv(OUT / "sealed_estimator_metrics.csv", index=False)

    # Local calibration need (preregistered for the failure version; computed in either case).
    local = []
    for population, family in POPULATIONS:
        selected = cases.design_family.eq(family).to_numpy()
        frame = local_calibration(scored.R7b.to_numpy()[selected], fail_d2[selected], groups[selected], alpha, 500, seed)
        frame.insert(0, "population", population)
        local.append(frame)
    local = pd.concat(local, ignore_index=True)
    local.to_csv(OUT / "sealed_local_calibration.csv", index=False)
    needed = {}
    for population, _ in POPULATIONS:
        block = local.loc[(local.population == population) & (local.share_risk_le_7pct >= 0.8)]
        needed[population] = int(block.m.min()) if len(block) else None

    n1 = {population: {"risk": float(primary[population].risk), "risk_upper95": float(primary[population].risk_upper95), "retention": float(primary[population].retention)} for population, _ in POPULATIONS}
    n1_success = bool(all(np.isfinite(v["risk"]) and v["risk"] <= 0.07 and v["retention"] > 0 for v in n1.values()))
    hard = float(covered[hardest].mean()) if hardest.any() else np.nan
    p1_reduction = reduction(p1_frame) if len(p1_frame) else np.nan
    result = {
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "n_cases_built": n_built, "n_cases": len(cases), "n_station_years": int(cases[["station_key", "year"]].drop_duplicates().shape[0]),
        "n_stations": int(cases.station_key.nunique()), "n_groups": int(cases.independence_group.nunique()), "n_regions": int(cases.region.nunique()),
        "n_cases_by_family": cases.design_family.value_counts().to_dict(), "layer_shares": cases.policy_choice.value_counts(normalize=True).to_dict(),
        "calendar_source": {"own": float(cases.loc[cases.design_family.eq("calendar")].apply(lambda r: str(r.calendar_source).split(":")[0] == r.station_key, axis=1).mean())},
        "N1_expected_risk_R7b": n1, "N1_success": n1_success, "N1_rule": f"realised risk <= 7% in deploy and mech with k = {factors['R7b']:.4f}",
        "N2_hardest_bin_coverage90": hard, "N2_lower95": float(np.nanquantile(hard_boot, 0.025)), "N2_upper95": float(np.nanquantile(hard_boot, 0.975)), "N2_n": int(hardest.sum()), "N2_success": bool(np.isfinite(hard) and hard >= 0.85),
        "N3_P1_stratum": {"n": int(stratum.sum()), "n_groups": int(len(np.unique(groups[stratum]))), "bias_P0": float(error0[stratum].mean()) if stratum.any() else None, "bias_D2": float(error2[stratum].mean()) if stratum.any() else None,
                          "reduction": p1_reduction, "reduction_lower95": float(np.nanquantile(p1_boot, 0.025)), "reduction_upper95": float(np.nanquantile(p1_boot, 0.975)),
                          "coverage90": float(covered[stratum].mean()) if stratum.any() else None},
        "N3_success": bool(np.isfinite(p1_reduction) and p1_reduction >= 0.5),
        "N4_ranking_gain_R7b": {population: gains[population] for population, _ in POPULATIONS}, "N4_ranking_gain_R7a": {population: gains[f"{population}_R7a"] for population, _ in POPULATIONS},
        "law": {population: {"predicted_P0_failure_v2": float(law.law_pfail[cases.design_family.eq(family)].mean()), "predicted_P0_failure_v2p": float(law_p.law_pfail[cases.design_family.eq(family)].mean()),
                             "observed_P0_failure": float(fail_p0[cases.design_family.eq(family).to_numpy()].mean())} for population, family in POPULATIONS},
        "local_groups_needed_for_80pct": needed,
        "transfer_section": "transfer_pass.tex" if n1_success else "transfer_fail.tex",
    }
    T.write_json(target, result)
    print(json.dumps(result, indent=2), flush=True)
    print(rule_table.round(4).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
