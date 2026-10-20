#!/usr/bin/env python3
"""Validation suite for the P0-04 deliverables (scratch copy of the final check).

Run from the repo root:
    PYTHONPATH=src python3 scratch/p0_04/validate_p0_04.py

Re-derives every internal identity of the six output files and re-checks the
protocol fingerprint against the bytes on disk. Read-only.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

OUT = Path("results/wrr_submission_ready/major_revision_20261014/p0_04_env_closed_loop")
ok = True


def chk(name: str, cond: bool, extra: str = "") -> None:
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ((" | " + extra) if extra else ""))


d = pd.read_csv(OUT / "share_decomposition.csv")
c = pd.read_csv(OUT / "decision_counts.csv")
e = pd.read_csv(OUT / "equal_budget_comparison.csv")
f = pd.read_csv(OUT / "efficiency_frontiers.csv")
r = pd.read_csv(OUT / "rng_sensitivity.csv")
fp = json.load(open(OUT / "protocol_fingerprint.json"))

chk("deliverables exist", all((OUT / x).exists() for x in [
    "share_decomposition.csv", "decision_counts.csv", "equal_budget_comparison.csv",
    "efficiency_frontiers.csv", "rng_sensitivity.csv", "protocol_fingerprint.json",
    "SUMMARY.md"]))
chk("script sha256 matches disk", fp["script_sha256"] == hashlib.sha256(
    Path("scripts/313_wrr_p0_04_env_closed_loop.py").read_bytes()).hexdigest())
chk("git HEAD matches", fp["repo"]["git_head"] == subprocess.run(
    ["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip())
for nm, df in [("decomp", d), ("counts", c), ("equal", e), ("frontiers", f),
               ("sensitivity", r)]:
    chk(f"{nm}: threshold tagged everywhere", df.threshold_c.notna().all()
        and (df.hot_year_metric == "truth_hottest30").all())
    chk(f"{nm}: both thresholds", set(df.threshold_c.unique()) == {18.0, 20.0})
chk("decomposition identity exact",
    (d.prediction_error_pp + d.selection_shift_pp - d.total_deviation_pp).abs().max() < 1e-12)
chk("three weightings", set(d.weighting.unique()) ==
    {"per_case", "per_station_year", "network_weighted"})
required = ["reconstruct_all", "length_screen_70", "peak_overlap_screen_70",
            "calibrated_screen_70", "interval_abstention", "screen70_and_abstention"]
chk("six required rules in every group", all(
    set(required).issubset(set(g.rule)) for _, g in d.groupby(["panel", "subset", "threshold_c"])))
ra = d[d.rule == "reconstruct_all"]
chk("reconstruct_all non-zero predicted share", ra.p_hat_A.notna().all())
chk("reconstruct_all selection shift exactly 0 and flagged",
    (ra.selection_shift_pp.abs() < 1e-12).all() and ra.selection_shift_structural_zero.all())
chk("reconstruct_all total == prediction error",
    (ra.total_deviation_pp - ra.prediction_error_pp).abs().max() < 1e-12)
nan_decomp = d[d.p_hat_A.isna()]
chk("undefined shares NaN + reason", nan_decomp.gap_reason.str.len().gt(0).all()
    and len(nan_decomp) > 0)
ng = c[c.gap_reason.isna()]
chk("counts identities", bool(
    (ng.n_correct + ng.n_incorrect == ng.n_decided).all()
    and (ng.n_missed_hot_years + ng.n_false_alarms == ng.n_incorrect).all()
    and (ng.n_abstained_true_hot + ng.n_abstained_true_not_hot == ng.n_abstained_or_excluded).all()
    and (ng.n_admitted == ng.n_decided).all()))
chk("counts gap rows only wave-2 elevation rules",
    set(c[c.gap_reason.notna()].rule) == {"elev_balanced_screen_70",
                                          "elev_balanced_and_abstention"})
chk("equal-budget criteria complete per group", all(
    set(e.criterion.unique()) == set(g.criterion)
    for _, g in e.groupby(["panel", "subset", "threshold_c", "rule"])))
chk("equal-budget single best label per group", all(
    g.best_rule.nunique() == 1
    for _, g in e[e.computable].groupby(["panel", "subset", "threshold_c", "criterion"])
    if g.is_best.any()))
bud = e[e.criterion == "equal_budget_0p5pct"]
chk("budget-matched rows within budget",
    (bud[bud.meets_budget.fillna(False)].error_rate_all_candidates <= 0.005 + 1e-12).all())
cov = e[e.criterion.str.startswith("equal_coverage")]
chk("coverage matches inside bracket guard",
    (cov[cov.coverage_match_ok.fillna(False)].interp_bracket_width <= 0.02 + 1e-12).all())
chk("wave2@18C judge-all inside 0.5% budget", bool(c.loc[
    (c.panel == "wave2_designed") & (c.subset == "pooled") & (c.threshold_c == 18.0)
    & (c.rule == "reconstruct_all"), "meets_0p5pct_budget"].iloc[0]))
chk("step8/step6 cross-checks reproduced",
    fp["cross_check"]["all_step8_rows_reproduced"]
    and fp["cross_check"]["all_step6_rows_reproduced"])
chk("SUMMARY quotes the review arithmetic", "0.3995%" in (OUT / "SUMMARY.md").read_text())
print()
print("ALL CHECKS PASS" if ok else "SOME CHECKS FAILED")
