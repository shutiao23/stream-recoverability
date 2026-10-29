"""Scientific invariants for the 2026-10-29 time-support and gap revision."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_revision_20261029"


def load_script(filename):
    spec = spec_from_file_location(filename.removesuffix(".py"), ROOT / "scripts" / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TIME = load_script("961_process_time_support.py")
GAPS = load_script("964_process_gap_and_archive.py")


def forward(frame):
    return frame.loc[frame.family.eq("crossed") & frame["mode"].eq("forward")]


def test_error_components_keep_cancellation_instead_of_causal_shares():
    block = pd.DataFrame(dict(family=["x", "x"], mode=["forward"] * 2, scheme=["warm90"] * 2,
                              estimate_error=[0., 0.], truth_error=[1., -1.],
                              reconstruction=[-1., 1.], n_years=[8, 8], span=[12, 12], end_weight=[.4, .4]))
    row = TIME.error_decomposition(block).iloc[0]
    assert row.estimate_mse == 0
    assert row.year_set_mse == row.reconstruction_mse == 1
    assert row.twice_cross_term == -2
    bad = block.copy()
    bad.loc[0, "estimate_error"] = 1
    with pytest.raises(RuntimeError, match="E = S"):
        TIME.error_decomposition(bad)


def test_cluster_bootstrap_pairs_schemes_and_is_independent_of_row_order():
    rows = []
    for group, station, replicate, error in [("g1", "a", 0, .2), ("g1", "a", 1, .9), ("g2", "b", 0, 2.)]:
        for scheme in TIME.SCHEMES:
            rows.append(dict(independence_group=group, station_key=station, replicate=replicate,
                             scheme=scheme, estimate_error=error, truth_error=error / 2))
    cases = pd.DataFrame(rows)
    original = TIME.paired_cluster_bootstrap(cases, n_bootstraps=500)
    reordered = TIME.paired_cluster_bootstrap(cases.sample(frac=1, random_state=4), n_bootstraps=500)
    pd.testing.assert_frame_equal(original, reordered)
    assert original[["rmse_difference", "cluster_percentile_low", "cluster_percentile_high"]].eq(0).all().all()
    with pytest.raises(RuntimeError, match="paired"):
        TIME.paired_cluster_bootstrap(cases.iloc[1:], n_bootstraps=5)


def test_longest_gap_measures_contiguous_union_including_adjacent_segments():
    assert GAPS.merged_gap_lengths([(30, 2), (10, 3), (12, 4), (16, 4)]) == [10, 2]
    assert GAPS.merged_gap_lengths([]) == []
    with pytest.raises(ValueError, match="positive"):
        GAPS.merged_gap_lengths([(2, 0)])


def test_same_count_identical_cases_and_selection_opportunity_are_auditable():
    cases = forward(pd.read_csv(OUT / "time_support_cases.csv"))
    kept = cases.pivot(index=TIME.PAIR_INDEX, columns="scheme", values="n_incomplete_kept")
    years = cases.pivot(index=TIME.PAIR_INDEX, columns="scheme", values="retained_years")
    choice = (kept.warm90 > 0) & (kept.warm90 < kept["all"])
    assert int((~choice).sum()) == 337
    assert int(choice.sum()) == 468
    for scheme in TIME.SCHEMES[1:3]:
        assert kept[scheme].equals(kept.warm90)
        assert years.loc[~choice, scheme].equals(years.loc[~choice, "warm90"])
    # The limited heuristic spreads incomplete candidates without consulting
    # either the temperatures or the already fixed complete-year locations.
    assert TIME.keep_balanced([1999], [2000, 2004, 2010], 2).tolist() == [1999, 2000, 2010]
    assert TIME.keep_balanced([2009], [2000, 2004, 2010], 2).tolist() == [2000, 2009, 2010]
    choice_scores = forward(pd.read_csv(OUT / "time_support_choice_opportunity.csv"))
    assert choice_scores.loc[choice_scores.subset.eq("nontrivial_year_choice"), "n"].eq(468).all()


def test_two_denominator_exclusions_have_no_masks_and_restore_only_zero_errors():
    audit = forward(pd.read_csv(OUT / "time_support_archive_audit.csv"))
    common = audit.loc[audit.original_common]
    excluded = common.loc[~common.included]
    assert len(common) == 807 and int(common.included.sum()) == 805
    assert set(zip(excluded.station_key, excluded.replicate)) == {
        ("gkd_bayern|10081004", 6), ("gkd_bayern|11405000", 14)}
    assert excluded.reason.eq("no_mask_empty_prediction_schema").all()
    assert excluded[["n_incomplete", "design_mask_years", "saved_warm90_error", "saved_all_error"]].eq(0).all().all()
    restored = forward(pd.read_csv(OUT / "time_support_zero_mask_sensitivity.csv")).set_index("scheme")
    primary = forward(pd.read_csv(OUT / "time_support_error_decomposition.csv")).set_index("scheme")
    assert restored.n.eq(807).all()
    np.testing.assert_allclose(restored.estimate_rmse**2 * 807, primary.estimate_rmse**2 * 805)


def test_gap_metrics_have_same_definition_with_explicit_different_repeat_weights():
    summary = pd.read_csv(OUT / "gap_common_statistic_comparison.csv")
    main = summary.loc[summary.primary_comparison].set_index("source")
    assert set(main.period) == {"2010-2025"}
    assert main.loc["observed", "n"] == main.loc["observed", "unique_station_years"] == 109
    assert main.loc["observed", "median_annual_longest"] == 4
    assert main.loc["calendar", "n"] == 3806 and main.loc["calendar", "median_annual_longest"] == 6
    assert main.loc["crossed", "n"] == 3777 and main.loc["crossed", "median_annual_longest"] == 60
    annual = pd.read_csv(OUT / "gap_annual_longest_cases.csv")
    for source, block in annual.groupby("family"):
        row = main.loc[source]
        assert row.replicates == 20 and row.unit == "incomplete_station_year_replicate"
        assert row.n == len(block)
        assert row.median_annual_longest == block.longest_run.median()
        assert row.share_annual_ge30 == pytest.approx(block.longest_run.ge(30).mean())
    historical = summary.loc[~summary.primary_comparison].iloc[0]
    assert historical.period == "1981-2025" and historical.n == 220


def test_archive_count_is_unique_complete_years_including_the_held_out_year():
    audit = pd.read_csv(OUT / "archive_complete_year_count_audit.csv")
    assert len(audit) == 581 and audit.station_key.is_unique
    assert (audit.unique_complete_station_years - audit.training_complete_years).eq(1).all()
    summary = pd.read_csv(OUT / "archive_comparison.csv").set_index("panel")
    for panel, block in audit.groupby("panel"):
        assert summary.loc[panel, "median_complete_years"] == block.unique_complete_station_years.median()
    assert summary.loc["trend_cohort", "median_complete_years"] == 31
    assert summary.loc["source_remainder", "median_complete_years"] == 8
