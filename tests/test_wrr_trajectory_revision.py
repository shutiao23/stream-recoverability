"""Scientific checks for fixed-input, stratified trajectory-budget sensitivity."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_revision_20261029"


@pytest.fixture(scope="module")
def trajectory():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = spec_from_file_location("trajectory_revision_test", ROOT / "scripts/962_process_trajectory_budget.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stratum_tail_count_does_not_hide_moving_minority(trajectory):
    rows = []
    for region, n, change in (("foen", 18, .001), ("gkd_bayern", 9, .12)):
        for k in range(n):
            for count in (20, 100, 500):
                rows.append(dict(seed=0, station_key=f"{region}|{k}", year=2011,
                    region=region, reconstructor="donor_ridge" if region == "foen" else "air_ridge",
                    independence_group=region, count=count, q05=10., q50=11.,
                    q95=12. + (change if count > 20 else 0), width90=2., coverage90=1.))
    replay = pd.DataFrame(rows).sample(frac=1, random_state=42)
    deltas = trajectory.case_deltas(replay)
    final = deltas.loc[deltas.comparison.eq("20_to_500")]
    assert final.abs_delta_q95.median() < .05  # A misleading pooled trigger would miss Bavaria.
    tails = trajectory.tail_summary(deltas)
    moving = tails.loc[tails.comparison.eq("20_to_500") & tails.region.eq("gkd_bayern")].iloc[0]
    assert moving.n_q95_exceeds_005 == 9
    assert moving.n_either_tail_exceeds_005 == 9
    assert moving.median_abs_delta_q95 == pytest.approx(.12)


def test_saved_budgets_are_nested_prefix_scores(trajectory):
    cases = pd.read_csv(OUT / "trajectory_revision_nested_cases.csv")
    draws = pd.read_parquet(OUT / "trajectory_revision_h30_draws.parquet")
    manifest = pd.read_csv(OUT / "trajectory_revision_frozen_manifest.csv").set_index(["station_key", "year"])
    assert set(cases.seed) == {0, 1, 2}
    assert len(cases) == 3 * 27 * 3
    lookup = cases.set_index(["seed", "station_key", "year", "count"])
    for row in draws.itertuples(index=False):
        values = np.asarray(row.h30_draws)
        assert len(values) == 500
        source = manifest.loc[(row.station_key, row.year)]
        for count in (20, 100, 500):
            actual = lookup.loc[(row.seed, row.station_key, row.year, count)]
            expected = trajectory.scores(values[:count], source.truth, source.bound)
            for value in ("q05", "q50", "q95", "width90", "coverage90", "crps"):
                assert actual[value] == pytest.approx(expected[value], abs=1e-10)


def test_frozen_inputs_and_bridge_parameters_are_identical_across_seeds(trajectory):
    manifest = pd.read_csv(OUT / "trajectory_revision_frozen_manifest.csv")
    cases = pd.read_csv(OUT / "trajectory_revision_nested_cases.csv")
    assert (cases.groupby(["station_key", "year"]).input_sha256.nunique() == 1).all()
    assert (cases.groupby(["station_key", "year"]).bridge_seed.nunique() == 3).all()
    for row in manifest.itertuples(index=False):
        with np.load(OUT / row.input_file) as inputs:
            assert trajectory.array_hash(inputs["observed"], inputs["mean"], inputs["residual"]) == row.input_sha256
            residual = inputs["residual"]
            finite = residual[np.isfinite(residual)]
            assert row.residual_mu == pytest.approx(finite.mean())
            assert row.residual_sigma == pytest.approx(max(finite.std(ddof=1), .001))


def test_original_cases_and_seed_zero_quantiles_reproduce(trajectory):
    manifest = pd.read_csv(OUT / "trajectory_revision_frozen_manifest.csv")
    original = pd.read_csv(trajectory.ORIGINAL)
    trajectory.validate_case_set(manifest, original)
    with pytest.raises(ValueError, match="case set"):
        trajectory.validate_case_set(manifest.iloc[:-1], original)
    cases = pd.read_csv(OUT / "trajectory_revision_nested_cases.csv")
    new = cases.loc[cases.seed.eq(0)].set_index(["station_key", "year", "count"]).sort_index()
    old = original.set_index(["station_key", "year", "count"]).sort_index()
    np.testing.assert_allclose(new[["q05", "q50", "q95"]], old[["q05", "q50", "q95"]], rtol=0, atol=1e-8)


def test_stratified_endpoint_and_coverage_counts_recompute(trajectory):
    cases = pd.read_csv(OUT / "trajectory_revision_nested_cases.csv")
    deltas = trajectory.case_deltas(cases)
    saved = pd.read_csv(OUT / "trajectory_revision_stratum_tails.csv")
    calculated = trajectory.tail_summary(deltas)
    pd.testing.assert_frame_equal(saved, calculated, check_dtype=False, atol=1e-10)
    zero = deltas.loc[deltas.seed.eq(0) & deltas.comparison.eq("20_to_500")]
    assert zero.q95_exceeds_005.sum() == 7
    assert zero.either_tail_exceeds_005.sum() == 10
    scores = trajectory.score_summary(cases, strata=False).set_index(["seed", "count"])
    assert scores.loc[(0, 20)].n_covered == 23
    assert scores.loc[(0, 500)].n_covered == 25


def test_source_calibration_and_scope_are_explicit(trajectory):
    status = trajectory.source_calibration_status()
    assert status["source_role_offsets_reestimated"] is False
    assert status["source_role_calibration_sensitivity_executed"] is False
    assert status["target_subset_even_odd_calibration_executed"] is False
    assert status["trajectory_count_convergence_established"] is False
    assert status["fine_method_ranking_robustness_established"] is False
    groups = pd.read_csv(OUT / "trajectory_revision_group_scope.csv")
    assert groups.independence_group.nunique() == 2
    assert sorted(groups.n_cases) == [9, 18]
    assert sorted(groups.n_stations) == [3, 3]
