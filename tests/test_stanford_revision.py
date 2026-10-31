"""Checks the saved Stanford-review extension against independent arithmetic."""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_final_revision_20261031"
PAPER = ROOT / "paper/wrr_tr"
KEY = ["station_key", "replicate", "independence_group"]


def test_family_counts_and_reference_year_sets():
    account = pd.read_csv(OUT / "retention_choice_counts.csv")
    assert len(account) == 1623
    grouped = account.groupby("family")
    assert int(grouped.size().loc["crossed"]) == 805
    assert int(grouped.size().loc["calendar"]) == 818
    assert int(grouped.choice.sum().loc["crossed"]) == 468
    assert int(grouped.choice.sum().loc["calendar"]) == 280
    assert int(grouped.n_subsets.sum().loc["crossed"]) == 5756
    assert int(grouped.n_subsets.sum().loc["calendar"]) == 2646
    assert int(grouped.all_incomplete_kept.sum().loc["calendar"]) == 530
    assert int(grouped.no_incomplete_kept.sum().loc["calendar"]) == 8
    refs = pd.read_csv(OUT / "reference_year_sets.csv")
    assert len(refs) == 41
    assert int(refs.n_internal_gap_years.gt(0).sum()) == 24
    assert int(refs.n_reference_years.min()) == 7
    assert refs.reference_years.str.split(";").map(len).equals(refs.n_reference_years)


def test_summaries_recompute_from_cases():
    cases = pd.read_csv(OUT / "retention_geometry_cases.csv")
    assert len(cases) == 8115
    summary = pd.read_csv(OUT / "retention_family_summary.csv").set_index(["family", "scheme"])
    for (family, scheme), block in cases.groupby(["family", "scheme"]):
        row = summary.loc[(family, scheme)]
        assert np.isclose(np.sqrt(block.estimate_mse.mean()), row.estimate_rmse, atol=1e-12)
        assert np.isclose(np.sqrt(block.year_set_mse.mean()), row.year_set_rmse, atol=1e-12)
        assert np.isclose(np.sqrt(block.reconstruction_mse.mean()), row.reconstruction_rmse, atol=1e-12)
        assert np.isclose(np.sqrt(block.iid_linear_expected_year_set_mse.mean()),
                          row.iid_linear_working_year_set_rmse, atol=1e-12)
    # The exact uniform averages preserve the same MSE identity within each archive.
    uniform = cases.loc[cases.scheme.eq("uniform_exact")]
    assert np.allclose(
        uniform.estimate_mse,
        uniform.year_set_mse + uniform.reconstruction_mse + uniform.cross_term,
        atol=1e-12,
    )


def test_paired_intervals_recompute_with_documented_resampling():
    cases = pd.read_csv(OUT / "retention_geometry_cases.csv")
    saved = pd.read_csv(OUT / "retention_paired_intervals.csv").set_index(["family", "scheme"])
    draws = 10000
    seed = 20261031
    for family in ["crossed", "calendar"]:
        block = cases.loc[cases.family.eq(family)]
        wide = block.pivot(index=KEY, columns="scheme", values="estimate_mse")
        labels = wide.index.get_level_values("independence_group")
        groups = sorted(set(labels))
        counts = np.array([(labels == group).sum() for group in groups])
        rng = np.random.default_rng(seed)
        multiplicity = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)), size=draws)
        baseline = np.array([wide.loc[labels == group, "warm90"].sum() for group in groups])
        for scheme in ["cdf_all_years", "sxx_all_years", "uniform_exact", "all"]:
            sums = np.array([wide.loc[labels == group, scheme].sum() for group in groups])
            change = np.sqrt(multiplicity @ sums / (multiplicity @ counts)) - np.sqrt(
                multiplicity @ baseline / (multiplicity @ counts)
            )
            row = saved.loc[(family, scheme)]
            assert np.isclose(float(np.quantile(change, 0.025)), row.ci_low, atol=1e-12)
            assert np.isclose(float(np.quantile(change, 0.975)), row.ci_high, atol=1e-12)


def test_calendar_evidence_stays_mixed_and_table_is_complete():
    intervals = pd.read_csv(OUT / "retention_paired_intervals.csv").set_index(["family", "scheme"])
    cdf = intervals.loc[("calendar", "cdf_all_years")]
    sxx = intervals.loc[("calendar", "sxx_all_years")]
    all_years = intervals.loc[("calendar", "all")]
    assert cdf.ci_low < 0 < cdf.ci_high
    assert sxx.ci_high < 0
    assert all_years.ci_high < 0
    summary = pd.read_csv(OUT / "retention_family_summary.csv")
    signs = summary.set_index(["family", "scheme"]).sign_disagreement_count_or_expectation
    assert signs.loc[("calendar", "warm90")] == 3
    assert signs.loc[("calendar", "cdf_all_years")] == 5
    assert signs.loc[("calendar", "sxx_all_years")] == 4
    assert signs.loc[("calendar", "all")] == 0
    table = (PAPER / "stanford_calendar_table.tex").read_text()
    assert "Empirical calendar" in table and "Controlled 30--90 day" in table
    assert "CDF" in table and "Sxx" in table and "All years" in table
    assert "0.0004" in table and "-0.0706" in table
    geo = (PAPER / "stanford_geometry_table.tex").read_text()
    assert "iid working benchmark" in geo
    assert "0.4865" in geo and "0.1616" in geo
    assert "coverage guarantee" in geo


def test_estimator_availability_is_not_accuracy():
    availability = pd.read_csv(OUT / "estimator_availability.csv").set_index(["family", "estimator"])
    assert int(availability.loc[("crossed", "D2")].available) == 820
    assert int(availability.loc[("crossed", "stochastic_calibrated")].available) == 738
    assert int(availability.loc[("calendar", "stochastic_calibrated")].available) == 701
    unavailable = pd.read_csv(OUT / "estimator_unavailable_subset.csv").set_index("family")
    assert int(unavailable.loc["crossed"].classical_unavailable_D2_available) == 82
    assert int(unavailable.loc["calendar"].classical_unavailable_D2_available) == 119
    assert np.isclose(unavailable.loc["crossed"].D2_rmse_on_that_subset, 0.24365608377809578, atol=1e-12)
    assert np.isclose(unavailable.loc["calendar"].D2_rmse_on_that_subset, 0.0933100659683678, atol=1e-12)
    paired = pd.read_csv(OUT / "estimator_paired_comparisons.csv").set_index(["family", "comparator"])
    crossed = paired.loc[("crossed", "stochastic_calibrated")]
    calendar = paired.loc[("calendar", "stochastic_calibrated")]
    assert crossed.ci_low > 0
    assert calendar.ci_low < 0 < calendar.ci_high


def test_compact_case_inputs_are_packaged():
    designs = pd.read_csv(OUT / "case_designs.csv")
    predictions = pd.read_csv(OUT / "annual_predictions_compact.csv")
    assert len(designs) == 1623
    assert set(designs.columns) == {"family", "station_key", "replicate", "n_years", "masks"}
    assert {"family", "station_key", "replicate", "year", "D2", "warm_observed_fraction"}.issubset(predictions.columns)
    assert len(predictions) > 7000
    assert predictions.D2.notna().all()
    assert predictions.warm_observed_fraction.notna().all()
    for row in designs.head(10).itertuples(index=False):
        assert row.masks.startswith("{")


def test_scope_records_post_hoc_status_and_inputs():
    scope = json.loads((OUT / "scope.json").read_text())
    assert scope["exploratory"] is True
    assert scope["new_models_fit"] is False
    assert scope["existing_outputs_changed"] is False
    assert scope["archives"] == 1623
    assert scope["geometry_rows"] == 8115
    assert scope["reference_year_sets"] == {"stations": 41, "internal_gap_stations": 24, "minimum_years": 7}
    assert "not accuracy validation" in " ".join(scope["interpretation"])
    manifest = json.loads((OUT / "data_manifest.json").read_text())
    assert len(manifest["inputs"]) >= 4
    assert "retention_geometry_cases.csv" in manifest["outputs"]


def test_compact_reference_allows_replay_without_case_parquet(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("stanford_revision_981_test", ROOT / "scripts/981_stanford_revision.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    compact = pd.read_csv(OUT / "reference_truths.csv")
    keep = set(zip(compact.family, compact.station_key))
    monkeypatch.setattr(module, "REF", ROOT / "does-not-exist.parquet")
    reference = module.load_reference(keep)
    assert len(reference) == len(keep)
    expected = compact.set_index(["family", "station_key", "year"]).eval_truth_h30
    for (family, station), series in reference.items():
        for year, value in series.items():
            assert np.isclose(value, expected.loc[(family, station, year)], atol=1e-12)
