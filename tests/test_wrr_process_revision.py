"""Checks for the 2026-10-29 claim-to-evidence process revision."""

from pathlib import Path
import json
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper/wrr_tr"
OUT = ROOT / "results/wrr_process_review_20261028"


def test_frozen_claim_macros_remain():
    values = (PAPER / "core_claims_values.tex").read_text()
    assert r"\newcommand{\CCCohortCommon}{807}" in values
    assert r"\newcommand{\CCAllCommonRMSE}{0.169}" in values
    assert r"\newcommand{\CCPeakHiddenDTwoCov}{83.2}" in values


def test_process_macros_match_saved_tables():
    values = (PAPER / "process_revision_values.tex").read_text()
    assert r"\newcommand{\PRBavariaHiddenAirCov}{67.9}" in values
    assert r"\newcommand{\PRBavariaHiddenAirBias}{-0.479}" in values
    assert r"\newcommand{\PRTimeN}{805}" in values
    assert r"\newcommand{\PRTimeWarmRMSE}{0.446}" in values
    assert r"\newcommand{\PRTimeAllRMSE}{0.170}" in values
    assert r"\newcommand{\PRTrajUpperShift}{0.007}" in values
    assert r"\newcommand{\PRTrajTailsMoved}{yes}" in values
    time = pd.read_csv(OUT / "time_support_summary.csv")
    fwd = time.loc[time.family.eq("crossed") & time["mode"].eq("forward")].iloc[0]
    assert int(fwd.n) == 805
    assert np.isclose(fwd.warm90_estimate_rmse, fwd.warm90_truth_rmse, atol=5e-4)
    assert abs(fwd.random_same_count_estimate_rmse - fwd.warm90_estimate_rmse) < 0.02
    nested = pd.read_csv(OUT / "trajectory_nested_summary.csv").set_index("count")
    assert int(nested.loc[20].n) == 27
    # Pooled means cannot certify any-case or stratum endpoint stability.
    deltas = pd.read_csv(ROOT / "results/wrr_process_revision_20261029/trajectory_revision_case_deltas.csv")
    original = deltas.loc[deltas.seed.eq(0) & deltas.comparison.eq("20_to_500")]
    assert ((original.abs_delta_q05 > .05) | (original.abs_delta_q95 > .05)).sum() == 10
    bavaria = original.loc[original.region.eq("gkd_bayern")]
    assert bavaria.abs_delta_q95.median() > .1


def test_article_states_exploratory_questions_and_use_case():
    article = (PAPER / "review_completion_article.tex").read_text()
    assert "RQ1:" in article and "RQ2:" in article and "RQ3:" in article
    assert "exploratory rather than preregistered" in article
    assert "Native 20-path generation" in article
    assert "neither establish equivalence" in article
    assert "No target outcome enters calibration" in article
    assert "source offsets" in article
    assert "blanket claim of no advantage" in article
    assert "H1:" not in article and "H2:" not in article and "H3:" not in article
    assert "The new experiment completes the source-role step" in article
    keypoints = article.split(r"\keypoints", 1)[1].split(r"\maketitle", 1)[0]
    assert "extra paths still move those tails" in keypoints
    assert "Trial composition is therefore not the explanation" not in article
    response = (ROOT / "docs/reviews/wrr_process_revision_20261029/RESPONSE_TO_REVIEW_ZH.md").read_text()
    assert "来源角色重校准没有执行" not in response
    execution = json.loads((ROOT / "results/wrr_process_experiments_20261029/source_calibration/full/execution.json").read_text())
    assert execution["source_role_offsets_reestimated"] is True
    assert execution["convergence_established"] is False
    assert "finite-record H30 slope" in article
    assert "source-role" in article
    assert "unmatched\\_gages is not an unregulated class" in article or "do not mean unregulated" in article
    assert "native seven-day (H7)" in article.lower() or "Native seven-day (H7)" in article
    assert r"\input{process_revision_values.tex}" in article
    assert r"fig:sample-domain" in article
    assert r"fig:region-recovery" in article
    assert r"fig:time-support" in article
    assert r"fig:trajectory-budget" in article
    assert "Retaining incomplete river-temperature records" in article
    assert "climate-process trend" in article
    assert "long-complete tail" in article
    assert r"tab:archive-comparison" in article
    assert "Year-set RMSE" in article
    assert "reconstruction RMSE" in article
    assert "not a general nonstationarity test" in article


def test_gap_geometry_and_archive_comparison_are_saved():
    gaps = pd.read_csv(OUT / "gap_geometry_summary.csv").set_index("family")
    assert gaps.loc["calendar"].median_segment_length < 15
    assert gaps.loc["crossed"].median_segment_length >= 30
    assert gaps.loc["calendar"].mean_jja_fraction < gaps.loc["crossed"].mean_jja_fraction
    archive = pd.read_csv(ROOT / "results/wrr_process_revision_20261029/archive_comparison.csv").set_index("panel")
    assert int(archive.loc["trend_cohort"].stations) == 42
    assert int(archive.loc["source_remainder"].stations) == 539
    assert archive.loc["trend_cohort"].median_complete_years == 31
    assert archive.loc["source_remainder"].median_complete_years == 8
    caption = (PAPER / "process_sample_table.tex").read_text()
    assert "leave-one-year-out" in caption
    assert "saved forward controlled-gap cases" not in caption
    recon = pd.read_csv(OUT / "time_support_reconstruction.csv")
    fwd = recon.loc[recon.family.eq("crossed") & recon["mode"].eq("forward")].set_index("scheme")
    assert fwd.loc["warm90"].reconstruction_rmse < 0.02
    assert fwd.loc["warm90"].truth_rmse > 0.4
    values = (PAPER / "process_revision_values.tex").read_text()
    assert r"\newcommand{\PRTimeWarmReconRMSE}{0.002}" in values
    supporting = (PAPER / "process_revision_supporting.tex").read_text()
    assert "process_gap_geometry_table.tex" in supporting
    assert "process_gap_revision_archive_table.tex" in supporting
    assert "process_gap_revision_table.tex" in supporting
    assert r"\label{tab:gap-geometry}" in (PAPER / "process_gap_geometry_table.tex").read_text()
    assert r"\label{tab:archive-comparison}" in (PAPER / "process_gap_revision_archive_table.tex").read_text()
    assert r"\input{process_gap_revision_archive_table.tex}" in (PAPER / "process_archive_table.tex").read_text()
    assert r"\label{tab:archive-comparison}" not in (PAPER / "process_archive_table.tex").read_text()
    observed = pd.read_csv(OUT / "observed_gap_summary.csv").iloc[0]
    assert int(observed.incomplete_years) == 220
    assert observed.median_longest_run < 10
    assert observed.share_run_ge_30 < 0.2
    water = pd.read_csv(OUT / "water_air_support.csv")
    foen = water.loc[water.region.eq("foen")].set_index("period")
    bavaria = water.loc[water.region.eq("gkd_bayern")].set_index("period")
    assert foen.loc["before_2010"].correlation > 0.8
    assert bavaria.loc["before_2010"].correlation < foen.loc["before_2010"].correlation
    article = (PAPER / "review_completion_article.tex").read_text()
    assert "annual longest contiguous missing run" in article
    assert "water--air H30" in article
    values = (PAPER / "process_revision_values.tex").read_text()
    assert r"\newcommand{\PRObsMedianRun}{3}" in values
    assert r"\newcommand{\PRFoenWaterCorrHist}{0.84}" in values


def test_posting_checklist_is_separate_from_science():
    path = ROOT / "docs/reviews/wrr_process_review_20261028/POSTING_CHECKLIST.md"
    text = path.read_text()
    assert "Author" in text
    assert "LUBW" in text
    assert "permanent" in text.lower()
    supporting = (PAPER / "review_completion_supporting.tex").read_text()
    assert "process_revision_supporting.tex" in supporting
