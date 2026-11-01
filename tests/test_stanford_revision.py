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
        assert np.isclose(np.sqrt(block.estimate_mse.mean()), row.estimate_rmse, rtol=0, atol=1e-12)
        assert np.isclose(np.sqrt(block.year_set_mse.mean()), row.year_set_rmse, rtol=0, atol=1e-12)
        assert np.isclose(np.sqrt(block.reconstruction_mse.mean()), row.reconstruction_rmse, rtol=0, atol=1e-12)
        assert np.isclose(np.sqrt(block.iid_linear_expected_year_set_mse.mean()),
                          row.iid_linear_working_year_set_rmse, rtol=0, atol=1e-12)
    # The exact uniform averages preserve the same MSE identity within each archive.
    uniform = cases.loc[cases.scheme.eq("uniform_exact")]
    assert np.allclose(
        uniform.estimate_mse,
        uniform.year_set_mse + uniform.reconstruction_mse + uniform.cross_term,
        rtol=0, atol=1e-12,
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
            assert np.isclose(float(np.quantile(change, 0.025)), row.ci_low, rtol=0, atol=1e-12)
            assert np.isclose(float(np.quantile(change, 0.975)), row.ci_high, rtol=0, atol=1e-12)


def test_known_calendar_snapshot():
    """Frozen-input regression snapshot; not a general significance criterion."""
    intervals = pd.read_csv(OUT / "retention_paired_intervals.csv").set_index(["family", "scheme"])
    cdf = intervals.loc[("calendar", "cdf_all_years")]
    sxx = intervals.loc[("calendar", "sxx_all_years")]
    all_years = intervals.loc[("calendar", "all")]
    assert cdf.ci_low < 0 < cdf.ci_high
    assert sxx.ci_high < 0
    assert all_years.ci_high < 0
    summary = pd.read_csv(OUT / "retention_family_summary.csv").set_index(["family", "scheme"])
    assert summary.loc[("calendar", "warm90"), "sign_disagreement_count"] == 3
    assert summary.loc[("calendar", "cdf_all_years"), "sign_disagreement_count"] == 5
    assert summary.loc[("calendar", "sxx_all_years"), "sign_disagreement_count"] == 4
    assert summary.loc[("calendar", "all"), "sign_disagreement_count"] == 0
    assert np.isclose(summary.loc[("calendar", "uniform_exact"), "sign_disagreement_expected_count"],
                      8.24047619047619, rtol=0, atol=1e-12)
    assert np.isclose(summary.loc[("crossed", "uniform_exact"), "sign_disagreement_expected_count"],
                      55.35191197691197, rtol=0, atol=1e-12)


def test_calendar_and_geometry_tables_are_complete():
    table = (PAPER / "stanford_calendar_table.tex").read_text()
    assert "Empirical calendar" in table and "Controlled 30--90 day" in table
    assert "CDF" in table and "Sxx" in table and "All years" in table
    assert "0.0004" in table and "-0.0706" in table
    geo = (PAPER / "stanford_geometry_table.tex").read_text()
    assert "iid working benchmark" in geo
    assert "0.4865" in geo and "0.1616" in geo
    assert "coverage guarantee" in geo


def test_selection_invariants_are_outcome_blind():
    designs = pd.read_csv(OUT / "case_designs.csv")
    cases = pd.read_csv(OUT / "retention_geometry_cases.csv")
    truths = pd.read_csv(OUT / "reference_truths.csv")
    account = pd.read_csv(OUT / "retention_choice_counts.csv")
    selected_columns = ["family", "station_key", "replicate"]
    samples = []
    for family, block in account.loc[account.choice].groupby("family"):
        block = block.sort_values("n_subsets", ascending=False)
        samples.append(block.head(8))
        samples.append(block.sample(min(12, len(block)), random_state=20261101))
    sample = pd.concat(samples).drop_duplicates(selected_columns)
    for row in sample.itertuples(index=False):
        key = (row.family, row.station_key, int(row.replicate))
        design = designs.loc[
            designs.family.eq(key[0]) & designs.station_key.eq(key[1]) & designs.replicate.eq(key[2])
        ].iloc[0]
        masks = set(int(value) for value in json.loads(design.masks))
        years = truths.loc[
            truths.family.eq(key[0]) & truths.station_key.eq(key[1]), "year"
        ].astype(int).tolist()
        complete = [year for year in years if year not in masks]
        candidates = [year for year in years if year in masks]
        for scheme in ["warm90", "cdf_all_years", "sxx_all_years", "all"]:
            selected = cases.loc[
                cases.family.eq(key[0])
                & cases.station_key.eq(key[1])
                & cases.replicate.eq(key[2])
                & cases.scheme.eq(scheme)
            ].iloc[0]
            retained = [] if pd.isna(selected.retained_years) else [
                int(value) for value in str(selected.retained_years).split(";")
            ]
            assert len(retained) == int(selected.n_retained)
            assert len(set(retained)) == len(retained)
            if scheme != "uniform_exact":
                assert set(complete).issubset(retained)
            if scheme in {"warm90", "cdf_all_years", "sxx_all_years"}:
                warm = cases.loc[
                    cases.family.eq(key[0])
                    & cases.station_key.eq(key[1])
                    & cases.replicate.eq(key[2])
                    & cases.scheme.eq("warm90")
                ].iloc[0]
                warm_years = [int(value) for value in str(warm.retained_years).split(";")]
                assert len(retained) == len(warm_years)
        warm = cases.loc[
            cases.family.eq(key[0])
            & cases.station_key.eq(key[1])
            & cases.replicate.eq(key[2])
            & cases.scheme.eq("warm90")
        ].iloc[0]
        warm_years = set(int(value) for value in str(warm.retained_years).split(";"))
        k = len(warm_years & set(candidates))
        options = []
        for chosen in itertools.combinations(candidates, k):
            selected = sorted(set(complete) | set(chosen))
            grid = np.arange(min(years), max(years) + 1)
            cdf = float(np.mean(((np.array(selected)[:, None] <= grid).mean(axis=0)
                                 - (np.array(years)[:, None] <= grid).mean(axis=0)) ** 2))
            sxx = float(np.sum((np.array(selected) - np.mean(selected)) ** 2) / 100)
            options.append((cdf, sxx, tuple(chosen)))
        cdf_choice = min(options, key=lambda item: (round(item[0], 14), -round(item[1], 14), item[2]))
        sxx_choice = min(options, key=lambda item: (-round(item[1], 14), round(item[0], 14), item[2]))
        for scheme, choice in [("cdf_all_years", cdf_choice), ("sxx_all_years", sxx_choice)]:
            stored = cases.loc[
                cases.family.eq(key[0])
                & cases.station_key.eq(key[1])
                & cases.replicate.eq(key[2])
                & cases.scheme.eq(scheme)
            ].iloc[0]
            retained = tuple(int(value) for value in str(stored.retained_years).split(";"))
            assert retained == tuple(sorted(set(complete) | set(choice[2])))

def test_estimator_availability_is_not_accuracy():
    availability = pd.read_csv(OUT / "estimator_availability.csv").set_index(["family", "estimator"])
    assert int(availability.loc[("crossed", "D2")].available) == 820
    assert int(availability.loc[("crossed", "stochastic_calibrated")].available) == 738
    assert int(availability.loc[("calendar", "stochastic_calibrated")].available) == 701
    unavailable = pd.read_csv(OUT / "estimator_unavailable_subset.csv").set_index("family")
    assert int(unavailable.loc["crossed"].classical_unavailable_D2_available) == 82
    assert int(unavailable.loc["calendar"].classical_unavailable_D2_available) == 119
    assert np.isclose(unavailable.loc["crossed"].D2_rmse_on_that_subset, 0.24365608377809578, rtol=0, atol=1e-12)
    assert np.isclose(unavailable.loc["calendar"].D2_rmse_on_that_subset, 0.0933100659683678, rtol=0, atol=1e-12)
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
    reference = module.load_reference(keep, OUT)
    assert len(reference) == len(keep)
    expected = compact.set_index(["family", "station_key", "year"]).eval_truth_h30
    for (family, station), series in reference.items():
        for year, value in series.items():
            assert np.isclose(value, expected.loc[(family, station, year)], rtol=0, atol=1e-12)


def _subset_slope_weights(years, selected):
    years = np.asarray(years, float)
    selected = np.asarray(selected, float)
    weights = np.zeros(len(years))
    mask = np.isin(years, selected)
    x_selected = (selected - selected.mean()) / 10
    weights[mask] = x_selected / np.dot(x_selected, x_selected)
    return weights


def test_subset_ols_identity_uses_each_sets_own_centering():
    years = np.arange(2000, 2006)
    selected = years[:5]
    full = _subset_slope_weights(years, years)
    subset = _subset_slope_weights(years, selected)
    x_full = (years - years.mean()) / 10
    difference = subset - full
    assert np.isclose(difference.sum(), 0.0, rtol=0, atol=1e-12)
    assert np.isclose(difference @ x_full, 0.0, rtol=0, atol=1e-12)
    sxx_full = np.dot(x_full, x_full)
    x_subset = (selected - selected.mean()) / 10
    sxx_subset = np.dot(x_subset, x_subset)
    assert np.isclose(difference @ difference, 1 / sxx_subset - 1 / sxx_full, rtol=0, atol=1e-12)

    h = 0.1 * (years - 2000)
    assert np.isclose(full @ h, 1.0, rtol=0, atol=1e-12)
    assert np.isclose(subset @ h, 1.0, rtol=0, atol=1e-12)
    assert np.isclose(subset @ (h + 100), 1.0, rtol=0, atol=1e-12)
    shifted_years = years - 1900
    assert np.isclose(
        _subset_slope_weights(shifted_years, shifted_years[:5]) @ h,
        1.0,
        rtol=0,
        atol=1e-12,
    )

    truncated = np.zeros(len(years))
    truncated[:5] = full[:5]
    assert not np.isclose(truncated @ h, 1.0, rtol=0, atol=1e-9)
    assert not np.isclose(truncated.sum(), 0.0, rtol=0, atol=1e-9)

    si = (PAPER / "stanford_geometry_supporting.tex").read_text()
    assert "x_{A,y}" in si and "w_{A,y}" in si and "S_{xx,A}" in si
    assert "w_{S,y}=w_{F,y}" not in si


def test_manifest_hashes_are_current_and_exclude_self():
    import hashlib

    manifest = json.loads((OUT / "data_manifest.json").read_text())
    assert "data_manifest.json" not in manifest["outputs"]
    assert "scope.json" in manifest["outputs"]
    assert "table_spec.json" in manifest["outputs"]
    for label, expected in manifest["outputs"].items():
        path = OUT / label
        if not path.is_file():
            path = Path(label)
        assert path.is_file(), label
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, label


def test_table_spec_covers_all_declared_tables():
    spec = json.loads((OUT / "table_spec.json").read_text())
    assert len(spec["tables"]) == 11
    for name, table_spec in spec["tables"].items():
        frame = pd.read_csv(OUT / name)
        assert list(frame.columns) == table_spec["columns"], name
        assert set(table_spec["keys"]).issubset(frame.columns), name
        assert not frame.duplicated(table_spec["keys"]).any(), name
        assert set(table_spec["numeric"]).issubset(frame.columns), name


def test_scope_sign_quantities_match_summary():
    summary = pd.read_csv(OUT / "retention_family_summary.csv").set_index(["family", "scheme"])
    scope = json.loads((OUT / "scope.json").read_text())
    for family in ["crossed", "calendar"]:
        for scheme in ["warm90", "uniform_exact", "cdf_all_years", "sxx_all_years", "all"]:
            row = summary.loc[(family, scheme)]
            entry = scope["sign_disagreement"][family][scheme]
            if pd.notna(row.sign_disagreement_count):
                assert entry["count"] == int(row.sign_disagreement_count)
                assert entry["expected_count"] is None
                assert entry["quantity"] == "count"
            else:
                assert entry["count"] is None
                assert np.isclose(entry["expected_count"], row.sign_disagreement_expected_count,
                                  rtol=0, atol=1e-12)
                assert entry["quantity"] == "expected_count"
