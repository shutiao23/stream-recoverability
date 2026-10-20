"""Invariants of the 2026-10-20b attribution round.

These pin the facts the manuscript rests on to the artifacts that produce them, and
they pin the manuscript against the descriptions that the design audit showed to be
false.  A failure means either an artifact drifted or the text went back to a claim
the case tables contradict.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261020b"
ARCHIVED_MANUSCRIPT = ROOT / "paper_archived" / "wrr_20261020b" / "wrr_manuscript.tex"
MANUSCRIPT = ARCHIVED_MANUSCRIPT if ARCHIVED_MANUSCRIPT.exists() else ROOT / "paper" / "wrr" / "wrr_manuscript.tex"

pytestmark = pytest.mark.skipif(not RUN.exists(), reason="run `make wrr-round-20261020b` first")


def _csv(rel: str) -> pd.DataFrame:
    return pd.read_csv(RUN / rel)


def test_error_identity_holds_and_false_peak_is_nonnegative():
    ident = pd.read_csv(RUN / "r2_03_three_windows/identity_check.csv", index_col=0)["value"]
    assert float(ident["max_abs_identity_residual_C"]) < 1e-9
    assert float(ident["min_false_peak_channel_C"]) > -1e-9
    assert float(ident["share_false_peak_channel_negative_beyond_1e-9"]) == 0.0
    assert float(ident["share_hide_channel_zero_when_true_window_visible"]) == 1.0


def test_design_audit_describes_the_generator():
    inv = _csv("r2_01_design_audit/arm_inventory.csv")
    big = inv[inv.panel.isin(["development", "external"]) & inv.arm.eq("all")]
    assert int(big.n_cases.sum()) == 53_721
    strat = inv[inv.panel.isin(["development", "external"]) & inv.arm.eq("stratified")]
    emp = inv[inv.panel.isin(["development", "external"]) & inv.arm.eq("empirical")]
    assert (int(strat.n_cases.sum()), int(emp.n_cases.sum())) == (33_749, 19_972)
    # the manuscript says "no scattered days": every stratified outage is one run
    assert (strat.share_single_run == 1.0).all()
    cross = inv[inv.panel.eq("crossed_mechanism") & inv.arm.eq("stratified")].iloc[0]
    assert (int(cross.n_cases), int(cross.n_station_years), int(cross.n_networks)) == (1899, 211, 12)


def test_crossed_panel_is_paired_within_station_years():
    cells = _csv("r2_01_design_audit/length_by_overlap_cells.csv")
    crossed = cells[cells.panel.eq("crossed_mechanism") & cells.target_length.isin([30, 60, 90])]
    assert len(crossed) == 9
    assert (crossed.n_station_years == 211).all()


def test_length_and_support_still_covary_outside_the_crossed_panel():
    corr = _csv("r2_01_design_audit/length_support_correlation.csv")
    pooled = corr[corr.arm.eq("all") & corr.pair.eq("length_vs_true_hidden_share")]
    for panel in ("development", "external"):
        assert pooled[pooled.panel.eq(panel)].pearson.iloc[0] > 0.4
    crossed = corr[corr.panel.eq("crossed_mechanism") & corr.arm.eq("all") & corr.pair.eq("length_vs_climatological_overlap")]
    assert abs(crossed.pearson.iloc[0]) < 0.05


def test_real_replay_rests_on_few_independent_gaps():
    ind = pd.read_csv(RUN / "r2_01_design_audit/real_calendar_independence.csv", index_col=0)["value"]
    assert int(ind["n_groups"]) == 418
    assert int(ind["n_source_incomplete_station_years"]) == 59
    assert int(ind["n_target_station_years"]) == 67


def test_ladder_reproduces_the_aligned_fitted_score_bit_for_bit():
    fp = json.loads((RUN / "r2_02_same_capacity_ablation/protocol_fingerprint.json").read_text())
    checks = fp["determinism_check"]
    assert len(checks) == 6
    assert all(item["identical"] for item in checks.values()), checks


def test_support_share_adds_nothing_to_a_full_generic_model():
    con = _csv("r2_02_same_capacity_ablation/ablation_contrasts.csv")
    rows = con[(con.metric == "retention") & con.left.eq("generic+support") & con.right.eq("generic")]
    assert len(rows) == 6
    assert (rows.point.abs() < 0.015).all(), rows[["panel", "fold_seed", "point"]]
    ext = rows[rows.panel.eq("wave2_confirmation")]
    assert ((ext.ci_low < 0) & (ext.ci_high > 0)).all()  # every external interval includes zero


def test_generic_model_still_beats_the_transparent_rule():
    con = _csv("r2_02_same_capacity_ablation/ablation_contrasts.csv")
    rows = con[(con.metric == "retention") & con.left.eq("generic") & con.right.eq("peak_overlap_rule")]
    assert (rows.ci_low > 0).all()


def test_hot_years_are_not_refused_more_than_records_in_general():
    hot = _csv("r2_04_hot_year_null/hot_year_selection_null.csv")
    sel = hot[
        hot.population.eq("designed") & hot.panel.eq("wave2_confirmation") & hot.hot_c.eq(20.0)
        & hot.arm.isin(["fitted_risk", "calibrated_bound", "generic"])
    ]
    assert (sel.excess_hot_refusal < 0).all()
    assert (sel.excess_ci_high < 0.005).all()


def test_screening_rule_never_waves_through_a_failing_network():
    conf = _csv("r2_05_screening_need/real_calendar_rule_confusion.csv")
    assert (conf.screen_needed_but_not_advised == 0).all()
    assert (conf.n_networks == 14).all()


def test_claim_registry_binds_every_number_to_the_text():
    check = json.loads((RUN / "claim_binding_check.json").read_text())
    assert check["claims"] >= 30
    assert check["missing_from_manuscript"] == []


def test_manuscript_no_longer_makes_the_claims_the_audit_refuted():
    text = " ".join(MANUSCRIPT.read_text(encoding="utf-8").split())
    assert "scattered at random" not in text
    assert "\\{30, 60, 90, 180\\}" not in text
    assert "vary gap length and hidden support independently" not in text
    assert "the ordering of the five methods at 90 days is the same as at 30" not in text
    assert "falls to the design value instead of the $+0.45$" not in text
    assert "66.7" not in text
    abstract = text.split("\\begin{abstract}")[1].split("\\begin{plainlanguagesummary}")[0]
    assert "refuse hot years no more often than other records" in abstract
    # the designed-panel refusal must not be attached to the real calendars again
    assert "screening refuses a quarter to a half of the true hot years" not in abstract


def test_si_tables_are_generated_not_typed():
    tex = (ROOT / "paper" / "wrr" / "si_r2_tables.tex").read_text(encoding="utf-8")
    assert tex.startswith("%% Generated by scripts/346_wrr_si_tables_r2.py")
    assert tex.count("\\begin{table}") == 16
    assert not re.search(r"\bTODO\b|\bnan\b", tex)
