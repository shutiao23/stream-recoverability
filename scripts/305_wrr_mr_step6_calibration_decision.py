#!/usr/bin/env python3
"""Major-revision Step 6: calibration as a decision module.

Keeps reconstruction / ranking fixed and compares decision rules on the same
candidate pool:

A. Archive admission at a frozen false-admit risk cap (0.5 °C consequential):
   - length rule
   - peak-overlap rule
   - uncalibrated risk bound (certificate_raw_bound)
   - calibrated risk bound (certificate_bound)
   Report retention achieved and realised false-admit rate among admitted.

B. Threshold judgment (hottest-30 vs ecological thresholds 18 / 20 °C):
   - reconstruct-all (no abstention)
   - length screen then judge
   - calibrated bound screen then judge
   - interval abstention (judge only when [low,high] does not straddle threshold)
   - screen AND abstention
   All methods start from the same candidate station-years; report judged share,
   abstention share, and misclassification among judged (and among all candidates).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP10_CONFIRM,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "step6_calibration_decision"
)
WAVE2_CASES = (
    ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet"
)
WAVE2_CERT = (
    ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_certificates.parquet"
)

RISK_CAP = 0.05
TOL = PRIMARY_TOLERANCE_C
THRESHOLDS = (18.0, 20.0)
SEED = 53
BOOT = 1000


def _align(cases: pd.DataFrame, certs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cases = cases.reset_index(drop=True)
    certs = certs.reset_index(drop=True)
    assert len(cases) == len(certs)
    return cases, certs


def max_retention_under_risk(
    score: np.ndarray,
    errors: np.ndarray,
    *,
    risk_cap: float = RISK_CAP,
) -> dict:
    order = np.argsort(np.where(np.isfinite(score), score, np.inf), kind="mergesort")
    best = {"retention": 0.0, "n_admitted": 0, "false_admit_rate": float("nan")}
    n = len(errors)
    for frac in np.round(np.arange(0.05, 1.001, 0.01), 3):
        k = max(1, int(round(float(frac) * n)))
        selected = errors[order[:k]]
        rate = float(((~np.isfinite(selected)) | (selected > TOL)).mean())
        if rate <= risk_cap:
            best = {"retention": float(frac), "n_admitted": int(k), "false_admit_rate": rate}
    return best


def admission_table(cases: pd.DataFrame, certs: pd.DataFrame, *, panel: str) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    errors = pd.to_numeric(certs["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
    # Fall back to policy error if certificate error missing (should be rare).
    policy = pd.to_numeric(cases["abserr_policy"], errors="coerce").to_numpy(dtype=float)
    errors = np.where(np.isfinite(errors), errors, policy)

    scores = {
        "length_rule": pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy()
        + rng.random(len(cases)),
        "peak_overlap_rule": pd.to_numeric(cases["peak_overlap"], errors="coerce").to_numpy()
        + rng.random(len(cases)) * 1e-3,
        "uncalibrated_bound": pd.to_numeric(certs["certificate_raw_bound"], errors="coerce")
        .fillna(np.inf)
        .to_numpy(dtype=float),
        "calibrated_bound": pd.to_numeric(certs["certificate_bound"], errors="coerce")
        .fillna(np.inf)
        .to_numpy(dtype=float),
    }
    rows = []
    for name, score in scores.items():
        op = max_retention_under_risk(score, errors)
        # Also report 70% matched retention false-admit for ranking-only view.
        k70 = max(1, int(round(0.7 * len(errors))))
        order = np.argsort(np.where(np.isfinite(score), score, np.inf), kind="mergesort")
        rate70 = float(((~np.isfinite(errors[order[:k70]])) | (errors[order[:k70]] > TOL)).mean())
        rows.append(
            {
                "panel": panel,
                "rule": name,
                "task": "archive_admission_ranked_risk_cap",
                "risk_cap": RISK_CAP,
                "retention_at_risk_cap": op["retention"],
                "false_admit_rate_at_risk_cap": op["false_admit_rate"],
                "n_admitted_at_risk_cap": op["n_admitted"],
                "false_admit_rate_at_70": rate70,
                "n_candidates": int(len(cases)),
                "n_networks": int(cases["network_id"].nunique()),
            }
        )

    # Absolute-scale admission: admit iff predicted bound ≤ TOL.
    # Multiplicative calibration changes this set; ranking-only risk-cap does not.
    for name, bound in (
        ("uncalibrated_bound_le_tol", scores["uncalibrated_bound"]),
        ("calibrated_bound_le_tol", scores["calibrated_bound"]),
    ):
        admit = np.isfinite(bound) & (bound <= TOL)
        n_adm = int(admit.sum())
        rate = (
            float(((~np.isfinite(errors[admit])) | (errors[admit] > TOL)).mean())
            if n_adm
            else float("nan")
        )
        rows.append(
            {
                "panel": panel,
                "rule": name,
                "task": "archive_admission_absolute_bound",
                "risk_cap": None,
                "retention_at_risk_cap": float(admit.mean()),
                "false_admit_rate_at_risk_cap": rate,
                "n_admitted_at_risk_cap": n_adm,
                "false_admit_rate_at_70": float("nan"),
                "n_candidates": int(len(cases)),
                "n_networks": int(cases["network_id"].nunique()),
                "tolerance_c": TOL,
            }
        )
    return pd.DataFrame(rows)


def threshold_table(cases: pd.DataFrame, certs: pd.DataFrame, *, panel: str) -> pd.DataFrame:
    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
    metric = pd.to_numeric(certs["certificate_metric"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(certs["interval_low"], errors="coerce").to_numpy(dtype=float)
    high = pd.to_numeric(certs["interval_high"], errors="coerce").to_numpy(dtype=float)
    bound = pd.to_numeric(certs["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float)
    rng = np.random.default_rng(SEED + 7)

    rows = []
    n = len(cases)
    for thr in THRESHOLDS:
        truth_pos = truth > thr
        # Precompute admission masks at equal 70% retention for screen rules.
        length_score = length + rng.random(n)
        bound_score = np.where(np.isfinite(bound), bound, np.inf)
        k70 = max(1, int(round(0.7 * n)))
        admit_length = np.zeros(n, dtype=bool)
        admit_bound = np.zeros(n, dtype=bool)
        admit_length[np.argsort(length_score)[:k70]] = True
        admit_bound[np.argsort(bound_score)[:k70]] = True

        # interval_low/high are conformal intervals on signed error ε = ŷ − y.
        # Implied truth interval is [ŷ − high, ŷ − low]; abstain if thr ∈ that.
        metric_lo = metric - high
        metric_hi = metric - low
        straddles = (metric_lo <= thr) & (metric_hi >= thr)
        clear = (
            np.isfinite(metric)
            & np.isfinite(low)
            & np.isfinite(high)
            & ~straddles
        )
        strategies = {
            "reconstruct_all": np.ones(n, dtype=bool),
            "length_screen_70": admit_length,
            "calibrated_screen_70": admit_bound,
            "interval_abstention": clear,
            "screen70_and_abstention": admit_bound & clear,
        }
        for name, judged_mask in strategies.items():
            judged = judged_mask & np.isfinite(metric) & np.isfinite(truth)
            n_judged = int(judged.sum())
            if n_judged == 0:
                continue
            pred_pos = metric[judged] > thr
            true_pos = truth_pos[judged]
            mistakes = pred_pos != true_pos
            # Among all candidates: abstention is neither correct nor incorrect call.
            rows.append(
                {
                    "panel": panel,
                    "threshold_c": float(thr),
                    "rule": name,
                    "task": "threshold_judgment",
                    "n_candidates": n,
                    "n_networks": int(cases["network_id"].nunique()),
                    "share_judged": float(n_judged / n),
                    "share_abstained": float(1.0 - n_judged / n),
                    "misclassification_among_judged": float(mistakes.mean()),
                    "false_negative_among_judged": float((~pred_pos & true_pos).mean())
                    if true_pos.any()
                    else float("nan"),
                    "false_positive_among_judged": float((pred_pos & ~true_pos).mean())
                    if (~true_pos).any()
                    else float("nan"),
                    "n_correct_judgments": int((~mistakes).sum()),
                    "n_incorrect_judgments": int(mistakes.sum()),
                    "n_abstentions": int(n - n_judged),
                }
            )
    return pd.DataFrame(rows)


def retention_contrast_ci(cases: pd.DataFrame, certs: pd.DataFrame, *, panel: str) -> dict:
    """Calibrated vs uncalibrated retention at risk cap, network-clustered."""

    frame = cases[["network_id"]].copy()
    frame["error"] = pd.to_numeric(certs["certificate_abs_error"], errors="coerce")
    frame["raw"] = pd.to_numeric(certs["certificate_raw_bound"], errors="coerce").fillna(np.inf)
    frame["cal"] = pd.to_numeric(certs["certificate_bound"], errors="coerce").fillna(np.inf)

    def statistic(block: pd.DataFrame) -> float:
        e = block["error"].to_numpy(dtype=float)
        return (
            max_retention_under_risk(block["cal"].to_numpy(dtype=float), e)["retention"]
            - max_retention_under_risk(block["raw"].to_numpy(dtype=float), e)["retention"]
        )

    boot = cluster_bootstrap(frame, statistic, draws=BOOT, seed=SEED)
    return {
        "panel": panel,
        "contrast": "calibrated_minus_uncalibrated_retention_at_risk_cap_5pct",
        "point_pp": float(boot["point"]) * 100,
        "ci_low_pp": float(boot["low"]) * 100,
        "ci_high_pp": float(boot["high"]) * 100,
        "n_clusters": int(boot["n_clusters"]),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    admission_rows = []
    threshold_rows = []
    contrasts = []

    panels = {
        "reserved_retrospective": (
            pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet"),
            pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet"),
        ),
        "wave2_designed": (
            pd.read_parquet(WAVE2_CASES),
            pd.read_parquet(WAVE2_CERT),
        ),
    }
    for name, (cases, certs) in panels.items():
        cases, certs = _align(cases, certs)
        print(f"Scoring {name}...", flush=True)
        admission_rows.append(admission_table(cases, certs, panel=name))
        threshold_rows.append(threshold_table(cases, certs, panel=name))
        contrasts.append(retention_contrast_ci(cases, certs, panel=name))

    admission = pd.concat(admission_rows, ignore_index=True)
    thresholds = pd.concat(threshold_rows, ignore_index=True)
    admission.to_csv(OUT / "admission_at_risk_cap.csv", index=False)
    thresholds.to_csv(OUT / "threshold_judgment.csv", index=False)
    (OUT / "calibration_retention_contrasts.json").write_text(json.dumps(contrasts, indent=2) + "\n")

    # Predeclared success sketch: calibrated rule retains more at same risk cap
    # than length/peak rules, and interval abstention judges more years than
    # screening alone at comparable misclassification.
    success = {
        "predeclared": {
            "admission": "At false-admit ≤5%, calibrated bound retains ≥5 pp more than peak-overlap rule on held-out panels",
            "threshold": "Interval abstention judges more candidates than calibrated screen@70% at misclassification ≤0.5%",
        },
        "observed": {},
    }
    for panel in admission["panel"].unique():
        block = admission.loc[admission.panel.eq(panel)]
        cal = float(block.loc[block.rule.eq("calibrated_bound"), "retention_at_risk_cap"].iloc[0])
        peak = float(block.loc[block.rule.eq("peak_overlap_rule"), "retention_at_risk_cap"].iloc[0])
        raw = float(block.loc[block.rule.eq("uncalibrated_bound"), "retention_at_risk_cap"].iloc[0])
        success["observed"][panel] = {
            "calibrated_retention": cal,
            "peak_overlap_retention": peak,
            "uncalibrated_retention": raw,
            "cal_minus_peak_pp": (cal - peak) * 100,
            "meets_plus5_vs_peak": bool((cal - peak) >= 0.05),
            "cal_minus_raw_pp": (cal - raw) * 100,
        }
    thr_obs = {}
    for panel in thresholds["panel"].unique():
        for thr in THRESHOLDS:
            block = thresholds.loc[thresholds.panel.eq(panel) & thresholds.threshold_c.eq(thr)]
            abs_row = block.loc[block.rule.eq("interval_abstention")].iloc[0]
            scr_row = block.loc[block.rule.eq("calibrated_screen_70")].iloc[0]
            thr_obs[f"{panel}|thr={thr}"] = {
                "abstention_share_judged": float(abs_row["share_judged"]),
                "abstention_misclf": float(abs_row["misclassification_among_judged"]),
                "screen70_share_judged": float(scr_row["share_judged"]),
                "screen70_misclf": float(scr_row["misclassification_among_judged"]),
                "abstention_judges_more": bool(abs_row["share_judged"] > scr_row["share_judged"]),
                "abstention_misclf_le_0.5pct": bool(abs_row["misclassification_among_judged"] <= 0.005),
            }
    success["observed"]["threshold"] = thr_obs
    (OUT / "success_checklist.json").write_text(json.dumps(success, indent=2) + "\n")

    lines = [
        "# Step 6 — calibration as decision module",
        "",
        "## A. Archive admission at ≤5% false-admit (0.5 °C)",
        "",
        admission.to_string(index=False),
        "",
        "## Calibration retention contrast (calibrated − uncalibrated), pp",
        "",
        json.dumps(contrasts, indent=2),
        "",
        "## B. Threshold judgment (same candidate pool)",
        "",
        thresholds.to_string(index=False),
        "",
        "## Success checklist",
        "",
        json.dumps(success["observed"], indent=2),
        "",
        "Ranking-only frontiers cannot prove calibration value; this module "
        "isolates absolute-scale admit / abstain decisions.",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print((OUT / "SUMMARY.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
