"""Check source-role leakage boundaries and actual recalibration sensitivity."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_experiments_20261029/source_calibration"


@pytest.fixture(scope="module")
def analysis():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = spec_from_file_location("source_calibration_test", ROOT / "scripts/968_process_source_calibration.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fallback_uses_positive_case_count_before_bootstrap_multiplicity(analysis):
    # Forty-nine copies with large bootstrap multiplicities cannot satisfy a
    # fifty-case fallback threshold. Exactly fifty genuine cases can.
    c = pd.DataFrame({"difficulty": ["local"] * 49 + ["other"] * 51,
                      "eval_truth_h30": [10.] * 49 + [20.] * 51,
                      "observed_lower_bound__observed_days": [np.nan] * 100})
    q = np.ones((100, 7))
    weight = np.r_[np.full(49, 20.), np.ones(51)]
    corrections, diagnostics = analysis.offsets(c, q, weight, ["local", "other"])
    local = next(row for row in diagnostics if row["cell"] == "local")
    assert local["positive_valid_cell_cases"] == 49 and local["fallback"]
    assert corrections["local"] == corrections["__pooled__"]
    c.loc[49, "difficulty"] = "local"
    corrections, diagnostics = analysis.offsets(c, q, np.ones(100), ["local", "other"])
    local = next(row for row in diagnostics if row["cell"] == "local")
    assert local["positive_valid_cell_cases"] == 50 and not local["fallback"]
    assert corrections["local"] != corrections["__pooled__"]


def test_original_source_roles_weights_cutoff_and_target_groups_are_preserved():
    plan = json.loads((OUT / "plan.json").read_text())
    role_cases = pd.read_csv(OUT / "source_role_cases.csv")
    targets = pd.read_csv(OUT / "fixed_target_cases.csv")
    assert plan["union_source_cases"] == 2370
    assert role_cases.year.lt(2010).all() and role_cases.training_partition.eq("train").all()
    for region, n, total_weight in [("foen", 1142, 2899), ("gkd_bayern", 1228, 2242)]:
        source = role_cases.loc[role_cases.calibration_region.eq(region)]
        assert len(source) == n and source.calibration_weight.sum() == total_weight
        assert not set(source.independence_group) & set(targets.loc[targets.region.eq(region)].independence_group)
        assert plan["source_roles"][region]["historical_offset_max_abs_error"] == 0
        assert plan["source_roles"][region]["historical_target_calibrated_max_abs_error"] == 0


def test_all_source_and_target_native20_quantities_reproduce_historical_generation():
    source = pd.read_csv(OUT / "full/source_native20_checks.csv")
    target = pd.read_csv(OUT / "full/target_native20_checks.csv")
    assert len(source) == 2370 and source.finite.all()
    assert source.native20_max_abs_draw_error.eq(0).all()
    assert source.native20_max_abs_quantile_error.eq(0).all()
    assert len(target) == 27
    assert target.native20_max_abs_draw_error.eq(0).all()
    assert target.native20_max_abs_quantile_error.eq(0).all()
    availability = pd.read_csv(OUT / "full/source_pool_availability.csv")
    assert len(availability) == 2370 * 3
    assert availability.availability_unchanged.all()
    assert availability.original_native20_available.all()
    assert len(pd.read_csv(OUT / "full/source_unavailable_cases.csv")) == 0


def test_regenerated_native20_is_distinct_from_nested20():
    draws = pd.read_parquet(OUT / "full/source_nested_draws.parquet")
    zero = draws.loc[draws.seed.eq(0)]
    differences = [not np.array_equal(np.asarray(row.native20), np.asarray(row.draws)[:20]) for row in zero.itertuples(index=False)]
    assert sum(differences) > 0
    assert all(len(row.draws) == 500 for row in draws.itertuples(index=False))


def test_actual_offset_pools_do_not_change_with_budget_or_monte_carlo_seed():
    pools = pd.read_csv(OUT / "full/source_reestimated_offsets.csv")
    for field in ("positive_valid_cell_cases", "selected_pool_cases", "weighted_pool_rows", "fallback"):
        assert pools.groupby(["region", "cell"])[field].nunique().eq(1).all()
    targets = pd.read_csv(OUT / "full/target_three_layer_cases.csv")
    assert len(targets) == 27 * 3 * 3 * 3
    assert targets.groupby(["seed", "count", "layer"]).size().eq(27).all()
    assert (targets.q05 >= targets.bound - 1e-10).all()
    assert targets[["q05", "q10", "q25", "q50", "q75", "q90", "q95"]].diff(axis=1).iloc[:, 1:].ge(-1e-10).all().all()


def test_three_layer_stage_contrast_holds_the_target_random_draws_fixed():
    cases = pd.read_csv(OUT / "full/target_three_layer_cases.csv")
    contrasts = pd.read_csv(OUT / "full/target_source_offset_stage_contrasts.csv")
    keys = ["seed", "count", "station_key", "year", "region", "reconstructor", "independence_group"]
    fixed = cases.loc[cases.layer.eq("fixed_old_offset")].set_index(keys)
    updated = cases.loc[cases.layer.eq("reestimated_source_offset")].set_index(keys)
    for metric in ("q05", "q95", "covered90", "crps256_normal"):
        saved = contrasts.loc[contrasts.metric.eq(metric)].set_index(keys).sort_index()
        actual = (updated[metric] - fixed[metric]).sort_index()
        np.testing.assert_allclose(actual, saved.source_offset_change, atol=1e-12, rtol=0)
    assert contrasts.loc[contrasts.metric.eq("q95")].source_offset_change.abs().gt(.05).any()


def test_fixed_d2_and_crps_use_the_same_original_quantile_reference(analysis):
    reference = pd.read_csv(OUT / "full/target_historical_reference.csv")
    targets = pd.read_csv(OUT / "fixed_target_cases.csv")
    d2 = reference.loc[reference.method.eq("fixed_D2")].set_index(["station_key", "year"]).sort_index()
    original = targets.set_index(["station_key", "year"]).sort_index()
    for probability in (5, 10, 25, 50, 75, 90, 95):
        np.testing.assert_array_equal(d2[f"q{probability:02d}"], original[f"D2_q{probability:02d}"])
    execution = json.loads((OUT / "full/execution.json").read_text())
    assert execution["d2_refit"] is False
    assert execution["source_role_offsets_reestimated"] is True
    assert execution["source_calibration_targets_used"] is False
    assert execution["convergence_established"] is False


@pytest.fixture
def resume_cache_fixture(analysis, tmp_path, monkeypatch):
    """A synthetic cache in pytest's temporary directory, never an experiment stamp."""
    forcing = tmp_path / "forcing.parquet"
    pd.DataFrame({"date": pd.to_datetime(["2001-01-01"]), "station_id": ["unit_station"],
                  "network_id": ["unit_network"], "air_temperature_c": [4.0]}).to_parquet(forcing, index=False)
    config = tmp_path / "config.json"
    config.write_text(Path(analysis.T.CONFIG).read_text())
    panel = tmp_path / "panel.csv"
    pd.DataFrame({"date": ["2001-01-01"], "unit_station": [3.0]}).to_csv(panel, index=False)
    monkeypatch.setattr(analysis.T, "AIR", forcing)
    monkeypatch.setattr(analysis.T, "CONFIG", config)
    monkeypatch.setattr(analysis, "OUT", tmp_path / "cache")
    job = dict(station_key="unit|unit_station", station_id="unit_station", network_id="unit_network",
               station_index=17, provider="unit", region="unit_region", independence_group="unit_group", roster="source",
               latitude=45.0, input_path=str(panel), air_input_path=str(forcing))
    cases = pd.DataFrame({"case_id": ["unit_case"]})
    shared = analysis.daily_reconstruction_shared_signature()
    signature = analysis.daily_reconstruction_signature(job, shared)
    parts = analysis.OUT / "full/station_parts"
    parts.mkdir(parents=True)
    stem = job["station_key"].replace("|", "_")
    metadata = parts / f"{stem}_metadata.json"
    metadata.write_text(json.dumps({"daily_reconstruction_signature": signature}) + "\n")
    pd.DataFrame({"case_id": ["unit_case"] * 3, "seed": [0, 1, 2]}).to_parquet(parts / f"{stem}_draws.parquet", index=False)
    for name in ("manifest.csv", "native20_checks.csv"):
        cases.to_csv(parts / f"{stem}_{name}", index=False)
    return job, cases, forcing, config, metadata


def test_resume_accepts_a_matching_complete_daily_signature(analysis, resume_cache_fixture):
    job, cases, forcing, config, metadata = resume_cache_fixture
    before = metadata.read_bytes()
    saved = analysis.resume_station(job, cases, "full", analysis.daily_reconstruction_shared_signature())
    assert saved["daily_reconstruction_signature"]["job"]["station_index"] == 17
    assert metadata.read_bytes() == before


def test_resume_rejects_actual_temporary_forcing_content_change(analysis, resume_cache_fixture):
    job, cases, forcing, config, metadata = resume_cache_fixture
    before = metadata.read_bytes()
    changed = pd.read_parquet(forcing)
    changed.loc[0, "air_temperature_c"] += 1.0
    changed.to_parquet(forcing, index=False)
    with pytest.raises(RuntimeError, match="air_forcing.*rerun without --resume"):
        analysis.resume_station(job, cases, "full", analysis.daily_reconstruction_shared_signature())
    assert metadata.read_bytes() == before


def test_resume_rejects_actual_temporary_configuration_content_change(analysis, resume_cache_fixture):
    job, cases, forcing, config, metadata = resume_cache_fixture
    before = metadata.read_bytes()
    changed = json.loads(config.read_text())
    changed["southern_hemisphere_shift_days"] += 1
    config.write_text(json.dumps(changed) + "\n")
    with pytest.raises(RuntimeError, match="source_config.*rerun without --resume"):
        analysis.resume_station(job, cases, "full", analysis.daily_reconstruction_shared_signature())
    assert metadata.read_bytes() == before


@pytest.mark.parametrize("field,value", [("station_index", 18), ("network_id", "another_network"),
                                         ("station_id", "another_station"), ("latitude", -45.0)])
def test_resume_rejects_job_identity_or_hemisphere_changes(analysis, resume_cache_fixture, field, value):
    job, cases, forcing, config, metadata = resume_cache_fixture
    before = metadata.read_bytes()
    changed = job | {field: value}
    with pytest.raises(RuntimeError, match="job.*rerun without --resume"):
        analysis.resume_station(changed, cases, "full", analysis.daily_reconstruction_shared_signature())
    assert metadata.read_bytes() == before


def test_resume_refuses_to_backfill_an_older_unsigned_cache(analysis, resume_cache_fixture):
    job, cases, forcing, config, metadata = resume_cache_fixture
    metadata.write_text(json.dumps({"input_panel_sha256": analysis.sha(job["input_path"]), "station_index": 17}) + "\n")
    before = metadata.read_bytes()
    with pytest.raises(RuntimeError, match="lacks.*signature.*rerun without --resume"):
        analysis.resume_station(job, cases, "full", analysis.daily_reconstruction_shared_signature())
    assert metadata.read_bytes() == before
