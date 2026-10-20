#!/usr/bin/env python3
"""Recompute the review's scientific findings without modifying earlier results."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

OUT = C.RUN / "r3_01_review_evidence"
R2 = C.READY / "major_revision_20261020b"
ALIGNED = C.READY / "major_revision_20261020"
INPUTS = {
    "windows": R2 / "r2_03_three_windows" / "cases_three_windows.parquet",
    "admissions": ALIGNED / "p0_01_aligned_policy_admission" / "case_level_admissions_wave2_confirmation.parquet",
    "replay": ALIGNED / "p0_03_real_calendar_adoption" / "replay_case_decisions.parquet",
    "development": C.ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet",
    "crossed": C.READY / "amendments/position_length_paired/crossed_development_cases.parquet",
    "ablation": R2 / "r2_02_same_capacity_ablation/ablation_contrasts.csv",
}


def switch_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, block in frame.loc[frame.error.notna()].groupby("reconstructor"):
        positive = block.loc[block.false_peak_channel > 1e-10]
        under = positive.error < -1e-10
        visible = block.loc[block.true_hidden_fraction == 0]
        rows.append(
            {
                "reconstructor": name,
                "n_finite": len(block),
                "n_positive_switch_increment": len(positive),
                "n_switch_still_underestimates": int(under.sum()),
                "share_switch_still_underestimates": float(under.mean()),
                "n_switch_overestimates": int((positive.error > 1e-10).sum()),
                "mean_hidden_channel_C": float(block.hide_channel.mean()),
                "mean_switch_increment_C": float(block.false_peak_channel.mean()),
                "mean_signed_error_C": float(block.error.mean()),
                "n_visible_window": len(visible),
                "n_visible_window_overestimates": int((visible.error > 0.1).sum()),
            }
        )
    return pd.DataFrame(rows)


def group_risk(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for seed, block in frame.groupby("fold_seed"):
        for arm in ("fitted_risk", "peak_overlap_rule", "calibrated_bound", "reconstruct_all"):
            accepted = block.loc[block[f"admit_riskcap_{arm}"].astype(bool)]
            for group, part in accepted.groupby("independence_group"):
                rows.append(
                    {
                        "fold_seed": int(seed),
                        "arm": arm,
                        "group": group,
                        "providers": ";".join(sorted(part.provider.astype(str).unique())),
                        "n_admitted": len(part),
                        "n_failed": int(part.policy_bad.sum()),
                        "risk": float(part.policy_bad.mean()),
                        "n_unique_station_years": len(part[["station_id", "year"]].drop_duplicates()),
                    }
                )
    return pd.DataFrame(rows)


def calibration_counterexample() -> dict:
    selector = C.load_script("review349_selector", C.ROOT / "scripts/330_wrr_aligned_policy_admission.py")
    result = selector.select_threshold(
        np.zeros(240), np.zeros(240), np.repeat(np.arange(12), 20), seed=42
    )
    return {
        "n_independent_groups": 12,
        "n_cases_per_group": 20,
        "observed_failures": 0,
        "selected_retention": float(result["retention_cal"]),
        "bootstrap_upper": float(result["upper_cal"]),
        "illustrative_population_group_failure_probability": 0.06,
        "probability_all_calibration_groups_successful": float(0.94**12),
        "exact_one_sided_group_binomial_upper": float(1 - 0.05 ** (1 / 12)),
        "interpretation": "constructed independent-group counterexample, not measured river failure rate",
    }


def main() -> int:
    settings = C.protocol()
    OUT.mkdir(parents=True, exist_ok=True)
    windows = pd.read_parquet(INPUTS["windows"])
    switches = switch_summary(windows)
    switches.to_csv(OUT / "window_switch_signs.csv", index=False)
    admissions = pd.read_parquet(INPUTS["admissions"])
    risks = group_risk(admissions)
    risks.to_csv(OUT / "risk_by_independent_group.csv", index=False)
    summaries = []
    for (seed, arm), block in risks.groupby(["fold_seed", "arm"]):
        summaries.append(
            {
                "fold_seed": int(seed),
                "arm": arm,
                "pooled_risk": float(block.n_failed.sum() / block.n_admitted.sum()),
                "equal_group_risk": float(block.risk.mean()),
                "n_groups": len(block),
                "n_groups_sample_risk_exceeds_cap": int((block.risk > settings["risk_cap"]).sum()),
                "maximum_sample_group_risk": float(block.risk.max()),
                "population_group_violation_claim": False,
            }
        )
    pd.DataFrame(summaries).to_csv(OUT / "risk_scope_summary.csv", index=False)
    crossed = pd.read_parquet(INPUTS["crossed"])
    crossed = crossed.loc[crossed.arm == "stratified"]
    counts = crossed.groupby("provider").agg(
        cases=("year", "size"), networks=("network_id", "nunique"), stations=("station_id", "nunique")
    )
    counts.to_csv(OUT / "controlled_panel_providers.csv")
    replay = pd.read_parquet(INPUTS["replay"])
    replay = replay.loc[(replay.seed == 101) & (replay.level == "target_only")]
    replay_keys = replay.rename(columns={"eval_year": "year"})[["network_id", "station_id", "year"]]
    replay_keys = replay_keys.astype(str).drop_duplicates()
    development = pd.read_parquet(INPUTS["development"])
    keys = development[["network_id", "station_id", "year"]].astype(str).drop_duplicates()
    overlap = replay_keys.merge(keys, on=["network_id", "station_id", "year"])
    overlap.to_csv(OUT / "replay_target_overlap.csv", index=False)
    ablation = pd.read_csv(INPUTS["ablation"])
    comparison = ablation.loc[
        (ablation.metric == "retention")
        & (ablation.left == "generic+support")
        & (ablation.right == "generic")
    ].copy()
    margin = settings["equivalence_margin_retention"]
    comparison["equivalence_margin"] = margin
    comparison["interval_within_declared_margin"] = (
        (comparison.ci_low > -margin) & (comparison.ci_high < margin)
    )
    comparison["evidence_role"] = "retrospective margin chosen after these outcomes were opened"
    comparison.to_csv(OUT / "retrospective_equivalence_diagnostic.csv", index=False)
    inventory = []
    for relative in [
        "major_revision_20261014/p1_transfer_measurement/SUMMARY.md",
        "major_revision_20261014/p1_learning_curve_repeats/SUMMARY.md",
        "amendments/mnar_day_level/summary.json",
        "major_revision_20261020/p0_03_real_calendar_adoption/SUMMARY.md",
    ]:
        path = C.READY / relative
        inventory.append({"path": relative, "exists": path.exists(), "sha256": C.digest(path) if path.exists() else None})
    summary = {
        "status": "retrospective_review_findings_recomputed",
        "counterexample": calibration_counterexample(),
        "real_replay_unique_target_station_years": len(replay_keys),
        "real_replay_targets_also_in_development_design": len(overlap),
        "controlled_panel_providers": counts.reset_index().to_dict("records"),
        "available_old_evidence": inventory,
        "warm_2018_2022_unique_station_years": len(
            development.loc[development.year.isin([2018, 2022]), ["network_id", "station_id", "year"]].drop_duplicates()
        ),
        "new_independent_validation": False,
    }
    C.write_json(OUT / "summary.json", summary)
    C.write_json(OUT / "protocol_fingerprint.json", C.fingerprint(Path(__file__), INPUTS))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
