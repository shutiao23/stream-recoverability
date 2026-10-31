"""Checks for the adversarial-review revision artifacts.

These tests read saved tables.  They do not refit a model or rerun the
computationally expensive rank-convergence sensitivity.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REVISION = ROOT / "results/wrr_review_response_20261027"
ADVERSARIAL = ROOT / "results/wrr_adversarial_review_20261027"
PAPER = ROOT / "paper/wrr_tr"

def test_common_cohort_replaces_the_mixed_denominator():
    frame = pd.read_csv(REVISION / "whole_archive/figure_cohort_common.csv")
    row = frame.loc[
        frame.family.eq("crossed") & frame["mode"].eq("forward")
    ].iloc[0]
    assert int(row.n_all) == 820
    assert int(row.n_warm90) == 807
    assert int(row.n_common) == 807
    assert np.isclose(row.all_rmse_common, 0.169474, atol=5e-6)
    assert np.isclose(row.warm90_rmse_common, 0.445331, atol=5e-6)
    assert int(row.stations) == 41
    assert int(row.groups) == 17

def test_rule_accounting_uses_all_eligible_station_years():
    frame = pd.read_csv(
        ADVERSARIAL / "rule_accounting/rule_accounting_summary.csv"
    ).set_index("rule")
    assert int(frame.loc["complete_100", "eligible_station_years"]) == 2700
    assert int(frame.loc["complete_100", "admitted"]) == 2139
    assert int(frame.loc["complete_100", "excluded_new_window_facts"]) == 35
    assert int(frame.loc["warm_90_station_specific", "excluded_new_window_facts"]) == 2
    assert int(frame.loc["warm_90_station_specific", "admitted_new_window_facts"]) == 19
    increments = pd.read_csv(
        ADVERSARIAL / "rule_accounting/warm90_excluded_increments.csv"
    )
    assert len(increments) == 2
    assert np.allclose(
        sorted(increments.excess_over_accepted_record), [0.113333, 0.149999], atol=1e-5
    )

def test_peak_visibility_strata_and_region_sensitivity_are_present():
    frame = pd.read_csv(
        ADVERSARIAL / "failure_strata/failure_strata_summary.csv"
    )
    hidden = frame.loc[
        frame.stratum_type.eq("reference peak")
        & frame.stratum.eq("reference peak above bound")
    ].set_index("method")
    assert int(hidden.loc["D2"].n) == 2146
    assert np.isclose(hidden.loc["D2"].coverage90, 0.832246, atol=1e-6)
    assert np.isclose(hidden.loc["stochastic"].coverage90, 0.816403, atol=1e-6)
    leave = pd.read_csv(
        ADVERSARIAL / "failure_strata/failure_strata_leave_region_out.csv"
    )
    bavaria = leave.loc[
        leave.excluded_region.eq("gkd_bayern") & leave.metric.eq("mae")
    ].iloc[0]
    assert bavaria.difference_D2_minus_stochastic < 0

def test_metadata_correction_covers_all_historical_designs_without_rewriting():
    manifest = pd.read_csv(
        ADVERSARIAL / "metadata_correction/design_correction_manifest.csv"
    )
    assert len(manifest) == 3320
    assert manifest.original_text_present.all()
    assert "sha256" not in manifest.columns

def test_core_claims_and_table_inputs_are_wired_into_the_manuscript():
    values = (PAPER / "core_claims_values.tex").read_text()
    assert r"\newcommand{\CCCohortCommon}{807}" in values
    assert r"\newcommand{\CCAllCommonRMSE}{0.169}" in values
    assert r"\newcommand{\CCPeakHiddenDTwoCov}{83.2}" in values
    article = (PAPER / "review_completion_article.tex").read_text()
    for label in [
        "\\input{core_claims_table.tex}",
        "\\input{rule_accounting_table.tex}",
        "\\input{method_version_table.tex}",
        "\\input{peak_visibility_main_table.tex}",
        "\\input{rank_convergence_table.tex}",
    ]:
        assert label in article
    for filename, label in [
        ("core_claims_table.tex", "tab:core-claims"),
        ("rule_accounting_table.tex", "tab:rule-accounting"),
        ("method_version_table.tex", "tab:method-versions"),
        ("external_qualification_table.tex", "tab:external-qualification"),
        ("peak_visibility_main_table.tex", "tab:peak-visibility-main"),
    ]:
        assert label in (PAPER / filename).read_text()
    if (ADVERSARIAL / "rank_convergence/rank_convergence_summary.csv").exists():
        assert "tab:rank-convergence" in (
            PAPER / "rank_convergence_table.tex"
        ).read_text()
    supporting = (PAPER / "review_completion_supporting.tex").read_text()
    assert "metadata_correction.tex" in supporting
    assert "failure_strata_table.tex" in supporting

def test_rank_convergence_uses_the_common_cases_when_available():
    path = ADVERSARIAL / "rank_convergence/rank_convergence_summary.csv"
    assert path.exists(), "rank-convergence summary is required evidence"
    frame = pd.read_csv(path)
    assert set(frame.draws) == {256, 1024, 4096}
    d2 = frame.loc[frame.method.eq("D2")]
    assert d2.n_archives.nunique() == 1
    assert int(d2.n_archives.iloc[0]) == 818
    stochastic = frame.loc[frame.method.eq("stochastic_cal")]
    assert int(stochastic.n_archives.iloc[0]) == 736

def test_figures_do_not_use_an_undefined_gray_band():
    source = (
        ROOT
        / "src/stream_recoverability/experiments/tr_revision/review_figures.py"
    ).read_text()
    assert "axhspan(90, 97" not in source
    assert "common station-repetition rows" in source
    assert "n_paired.max()" not in source
    assert "two_method_intersection" in source
    assert "ylim=(74, 101)" in source
    assert "not a paired comparison" in source or "not paired" in source

def test_overlap_boundary_matches_the_at_least_half_definition():
    import importlib.util
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "failure_strata_bounds", ROOT / "scripts/927_failure_strata.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    labels = module.overlap_labels(pd.Series([0.0, 0.001, 0.5, 1.0, 0.499]))
    assert list(labels.astype(str)) == [
        "no overlap",
        "no overlap",
        "at least half",
        "at least half",
        "partial",
    ]
    cases = pd.read_parquet(ADVERSARIAL / "failure_strata/failure_strata_cases.parquet")
    exact = cases.loc[np.isclose(cases.peak_overlap, 0.5)]
    assert len(exact) == 47
    assert set(exact.overlap_bin.astype(str)) == {"at least half"}
    summary = pd.read_csv(ADVERSARIAL / "failure_strata/failure_strata_summary.csv")
    half = summary.loc[
        summary.stratum_type.eq("training peak overlap")
        & summary.stratum.eq("at least half")
        & summary.method.eq("D2")
    ].iloc[0]
    partial = summary.loc[
        summary.stratum_type.eq("training peak overlap")
        & summary.stratum.eq("partial")
        & summary.method.eq("D2")
    ].iloc[0]
    assert int(half.n) == 1874
    assert int(partial.n) == 577

def test_switzerland_label_and_external_counts_come_from_saved_results():
    values = (PAPER / "core_claims_values.tex").read_text()
    assert r"\newcommand{\CCRegionSwitzerlandCov}{98.7}" in values
    assert "CCRegionFinlandCov" not in values
    results = (PAPER / "simple_research_results.tex").read_text()
    assert "Swiss FOEN" in results
    assert "in Finland" not in results
    assert "0.4 percentage" not in results
    assert r"\CCRankSeedChangeMax" in results
    assert r"\CCPairFwdN" in results
    table = (PAPER / "external_qualification_table.tex").read_text()
    for phrase in ["288 controlled gaps", "84 calendar gaps", "72 controlled-gap masks", "306 exploratory"]:
        assert phrase in table
    assert "No H30 model was scored" not in table
    assert "108 masks" not in table
    article = (PAPER / "review_completion_article.tex").read_text()
    assert r"[-5,50]" in article
    assert r"\RioBoundedYears" in article
    assert "372 controlled-gap" not in article
    methods = (PAPER / "method_version_table.tex").read_text()
    assert "do not share one annual distribution" in methods or "own bounded annual marginals" in methods
    assert "not project a trend interval onto an annual lower bound" in methods

def test_two_method_intersection_is_the_paired_denominator():
    from stream_recoverability.experiments.tr_revision.cohort_denominators import (
        two_method_intersection,
    )

    cases = pd.read_csv(
        REVISION / "whole_archive/uncertainty_common_cases.csv"
    )
    paired = two_method_intersection(cases)
    row = paired.loc[paired.family.eq("crossed") & paired["mode"].eq("forward")].iloc[0]
    assert int(row.n_own_d2) == 818
    assert int(row.n_own_classic) == 736
    assert int(row.n_paired) == 736
    assert int(row.incomplete_years) == 3328
    assert np.isclose(row.annual_weighted_d2, 0.9072, atol=5e-4)
    assert np.isclose(row.annual_weighted_classic, 0.8810, atol=5e-4)
    assert np.isclose(row.trend_independent_d2, 0.8913, atol=5e-4)
    assert np.isclose(row.trend_independent_classic, 0.8628, atol=5e-4)
    factor = pd.read_csv(REVISION / "whole_archive/factorial_paired_summary.csv")
    forward = factor.loc[factor.family.eq("crossed") & factor["mode"].eq("forward")]
    assert int(forward.loc[forward.estimator.eq("D2"), "n_paired"].iloc[0]) == 807
    assert int(
        forward.loc[forward.estimator.eq("stochastic_calibrated"), "n_paired"].iloc[0]
    ) == 725

def test_seed_mean_change_is_not_reported_as_a_single_run_maximum():
    cases = pd.read_csv(
        ADVERSARIAL / "rank_convergence/rank_convergence_cases.csv.gz",
        usecols=["method", "construction", "seed", "draws", "covered"],
    )
    per_seed = cases.groupby(
        ["method", "construction", "seed", "draws"], observed=True
    ).covered.mean().unstack("draws")
    single = float((per_seed[4096] - per_seed[1024]).abs().max() * 100)
    assert np.isclose(single, 0.815, atol=5e-4)
    values = (PAPER / "core_claims_values.tex").read_text()
    assert r"\newcommand{\CCRankSeedChangeMax}{0.815}" in values
    assert r"\newcommand{\CCRankChangeMax}{0.36}" in values
    text = (PAPER / "simple_research_results.tex").read_text()
    assert "three-seed mean" in text
    assert "single-seed" in text

def test_abstract_and_key_points_meet_the_text_limits():
    article = (PAPER / "review_completion_article.tex").read_text()
    points = article.split(r"\keypoints", 1)[1].split(r"\maketitle", 1)[0]
    entries = [item.strip() for item in points.splitlines() if item.strip().startswith("{")]
    assert entries
    assert all("D2" not in item for item in entries)
    assert all(len(item.strip("{}")) <= 140 for item in entries)
    abstract = article.split(r"\begin{abstract}", 1)[1].split(r"\begin{plainlanguagesummary}", 1)[0]
    commands = {}
    for path in PAPER.glob("*.tex"):
        for name, value in re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}", path.read_text()):
            commands[name] = value
    expanded = abstract
    for _ in range(4):
        expanded = re.sub(
            r"\\([A-Za-z]+)\{\}",
            lambda match: commands.get(match.group(1), match.group(0)),
            expanded,
        )
    expanded = re.sub(r"\$[^$]*\$", " math ", expanded)
    expanded = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*", " ", expanded)
    expanded = expanded.replace("--", " ")
    words = re.findall(r"[A-Za-z0-9]+(?:\.[0-9]+)?", expanded)
    assert len(words) < 250, len(words)


def test_figure_inputs_are_packaged_and_intervals_cannot_be_omitted():
    bundle = (ROOT / "scripts/536_prepare_review_bundle.py").read_text()
    for name in (
        "whole_archive/trends.csv",
        "whole_archive/figure_cohort_common.csv",
        "whole_archive/figure_uncertainty_bootstrap.csv",
    ):
        assert name in bundle
        assert (REVISION / name).is_file()
    from stream_recoverability.experiments.tr_revision.review_figures import (
        require_group_intervals,
    )
    import pytest
    with pytest.raises(ValueError, match="must not omit intervals"):
        require_group_intervals(None, [("crossed", "forward", "D2", "independent")])
    methods = (PAPER / "simple_research_methods.tex").read_text()
    assert "LightGBM" in methods
    assert "do not identify a complete central 90" in methods
    assert "20 residual-bridge trajectories" in methods
