"""Scientific checks for the common-weight and annual-within revision."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_revision_20261029"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_common_weights_balance_composition_without_implying_within_cell_balance():
    region = load_script("960_process_region_identification")
    rows = []
    for r, counts in [("foen", [8, 2]), ("gkd_bayern", [2, 4])]:
        for cell, n in zip(["a", "b"], counts):
            for _ in range(n):
                rows.append(dict(region=r, geometry=cell, years=5 if r == "foen" else 15))
    rows.append(dict(region="foen", geometry="unsupported", years=25))
    common, cells = region.common_cell_weights(pd.DataFrame(rows), ["geometry"])
    assert len(common) == 16
    assert "unsupported" not in set(common.cell)
    assert np.allclose(common.groupby("region")[["raw_common_support", "min_count", "equal_cell"]].sum(), 1)
    assert np.isclose(region.categorical_tv(common, "cell", "raw_common_support"), 7 / 15)
    assert np.isclose(region.categorical_tv(common, "cell", "min_count"), 0)
    assert np.isclose(region.categorical_tv(common, "cell", "equal_cell"), 0)
    # Equal weights in cells cannot equalize a field differing inside every cell.
    assert np.isclose(region.weighted_ks(common, "years", "min_count"), 1)
    assert np.allclose(cells.min_count_target, [.5, .5])


def test_min_count_target_and_equal_cell_target_are_distinct():
    region = load_script("960_process_region_identification")
    frame = pd.DataFrame([
        {"region": r, "geometry": cell}
        for r, counts in [("foen", [8, 3]), ("gkd_bayern", [2, 4])]
        for cell, n in zip(["a", "b"], counts)
        for _ in range(n)
    ])
    common, cells = region.common_cell_weights(frame, ["geometry"])
    assert np.allclose(cells.min_count_target, [.4, .6])
    assert np.allclose(cells.equal_cell_target, [.5, .5])
    # Retained means remain untouched inside cells; only the target changes.
    for r, block in common.groupby("region"):
        assert np.isclose(block.loc[block.cell.eq("b"), "min_count"].sum(), .6)
        assert np.isclose(block.loc[block.cell.eq("b"), "equal_cell"].sum(), .5)


def synthetic_water_panel():
    rows = []
    for station, intercept in [("s1", 3.), ("s2", 15.), ("s3", -8.)]:
        for period, years, slope in [("before_2010", [2007, 2008, 2009], .7), ("from_2010", [2010, 2011, 2012], 1.)]:
            for year, anomaly in zip(years, [-1., 0., 1.]):
                x = 20. + 2 * intercept + anomaly
                y = intercept + slope * anomaly + (2. if period == "from_2010" else 0.)
                rows.append(dict(region="test", station_key=station, independence_group=station,
                                 period=period, year=year, air_h30_target_year=x, eval_truth_h30=y))
    return pd.DataFrame(rows)


def test_within_station_period_fit_removes_between_station_offsets():
    water = load_script("process_review_water_air")
    frame = synthetic_water_panel()
    moments = water.station_moments(frame)
    before = moments.loc[moments.period.eq("before_2010"), water.MOMENTS].sum().to_numpy(float)
    assert np.isclose(water.fit_moments(before, "within_station_period")["slope"], .7)
    assert not np.isclose(water.fit_moments(before, "pooled")["slope"], .7)
    # Arbitrary station-by-period offsets do not change the within estimator.
    frame["eval_truth_h30"] += np.where(frame.station_key.eq("s1"), 300., -100.)
    moments2 = water.station_moments(frame)
    before2 = moments2.loc[moments2.period.eq("before_2010"), water.MOMENTS].sum().to_numpy(float)
    assert np.isclose(water.fit_moments(before2, "within_station_period")["slope"], .7)


def test_paired_bootstrap_preserves_before_after_station_relationship():
    water = load_script("process_review_water_air")
    summary, changes, moments = water.paired_analysis(synthetic_water_panel(), bootstraps=200, seed=11)
    within = changes.loc[changes.centering.eq("within_station_period")]
    assert np.allclose(within.slope_difference, .3)
    assert np.allclose(within.slope_difference_low, .3)
    assert np.allclose(within.slope_difference_high, .3)
    assert within.stations_both_periods.eq(3).all()
    assert summary.n.eq(9).all()
    assert moments.n.eq(3).all()


def test_saved_region_standardization_reproduces_independent_cell_diagnostic():
    saved = pd.read_csv(OUT / "region_standardized.csv").query("method == 'D2'")
    audit = pd.read_csv(ROOT / "results/wrr_process_review_20261029/regional_standardization_diagnostic.csv")
    labels = {"raw_common_support": "raw_region_weights", "min_count": "common_min_count_weights", "equal_cell": "equal_common_cell_weights"}
    for (matching, weighting), block in saved.groupby(["matching", "weighting"]):
        row = audit.loc[audit["match"].eq(matching) & audit.weighting.eq(labels[weighting])].iloc[0]
        values = block.set_index("region").coverage90
        assert np.isclose(values.foen, row.foen_coverage, atol=1e-12)
        assert np.isclose(values.gkd_bayern, row.bavaria_coverage, atol=1e-12)
    balance = pd.read_csv(OUT / "region_balance_categorical.csv")
    target_cells = balance.loc[balance.weighting.isin(["min_count", "equal_cell"]) & balance.field.eq("cell")]
    assert (target_cells.total_variation < 1e-12).all()
    continuous = pd.read_csv(OUT / "region_balance_continuous.csv")
    assert continuous.field.eq("n_complete_years").any()
    assert np.isfinite(continuous.loc[continuous.field.eq("n_complete_years"), "smd"]).all()


def test_saved_annual_within_results_reproduce_direct_centering_and_unique_denominators():
    work = pd.read_csv(OUT / "water_air_complete_years.csv")
    summary = pd.read_csv(OUT / "water_air_summary.csv").query("bootstrap_unit == 'connected_group'")
    assert not work.duplicated(["station_key", "year"]).any()
    for row in summary.itertuples(index=False):
        block = work.loc[work.region.eq(row.region) & work.period.eq(row.period)]
        assert row.n == len(block)
        assert row.stations == block.station_key.nunique()
        x, y = block.air_h30_target_year, block.eval_truth_h30
        if row.centering == "within_station_period":
            x = x - block.groupby("station_key").air_h30_target_year.transform("mean")
            y = y - block.groupby("station_key").eval_truth_h30.transform("mean")
        else:
            x, y = x - x.mean(), y - y.mean()
        assert np.isclose(row.slope, (x @ y) / (x @ x), atol=1e-11)
        assert np.isclose(row.correlation, np.corrcoef(x, y)[0, 1], atol=1e-11)
    changes = pd.read_csv(OUT / "water_air_paired_changes.csv")
    assert changes.bootstrap_draws.eq(10000).all()
    assert changes.slope_valid_draws.eq(10000).all()
    assert changes.stations.eq(changes.stations_both_periods).all()
