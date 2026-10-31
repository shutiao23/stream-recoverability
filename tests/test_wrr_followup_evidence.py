"""Scientific invariants for the post-review computed evidence."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/wrr_submission_ready/followup_20261021"


def csv(path):
    source = RUN / path
    if not source.exists():
        pytest.skip("Follow-up computation has not been run")
    return pd.read_csv(source)


@pytest.mark.parametrize("protocol,n", [("leave_one_year_out", 669), ("strictly_prior_years", 173)])
def test_random_rejection_is_expected_loss_on_same_original_pool(protocol, n):
    costs = csv(f"external_cost/{protocol}/decision_costs.csv")
    assert costs.n_candidates.eq(n).all()
    for _, block in costs.groupby(["threshold", "fn_cost", "abstention_cost"]):
        arm = block.set_index("arm")
        retained = 1 - arm.loc["frozen_magnitude_screen", "unknown"] / n
        expected = retained * arm.loc["reconstruct_all", "loss"] + (1 - retained) * block.abstention_cost.iloc[0]
        assert arm.loc["random_matched_screen", "loss"] == pytest.approx(expected)
        counts = block[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1)
        np.testing.assert_allclose(counts, n)


def test_high_risk_station_remains_in_frozen_primary_population():
    stations = csv("transfer/leave_one_year_out/station_results.csv")
    assert len(stations) == 7
    assert stations.n_cases.sum() == 669
    assert stations.failures.sum() == 33
    assert stations.set_index("station_id").loc["CH_2327", "failures"] == 16


def test_distinct_station_years_are_not_network_target_rows():
    populations = csv("mechanism/leave_one_year_out/population_comparison.csv").set_index("population")
    assert populations.loc["common_length_feasible", "n_station_years"] == 396
    assert populations.loc["common_length_feasible", "n_network_target_years"] == 400
    assert populations.loc["original", "n_station_years"] == 4720


@pytest.mark.parametrize("protocol", ["leave_one_year_out", "strictly_prior_years"])
def test_formal_reject_all_has_no_reported_zero_risk(protocol):
    for seed in (101, 202, 303):
        frame = csv(f"factorial/{protocol}/seed_{seed}/operating.csv")
        formal = frame.loc[frame.selection.eq("formal")]
        assert formal.accepted.eq(0).all()
        assert formal.risk.isna().all()


def test_trajectory_coverage_is_numeric_fraction():
    quality = csv("evidence/trajectory_common_all.csv")
    assert quality.coverage90.between(0, 1).all()
    assert quality.groupby(["role", "draws"]).N.nunique().eq(1).all()
    # Verify against original numeric case outcomes, guarding object-bool aggregation.
    path = RUN / "evidence/trajectory_common_test.parquet"
    if path.exists():
        cases = pd.read_parquet(path)
        for variant, block in cases.groupby("variant"):
            actual = block.covered90.astype(float).mean()
            recorded = quality.loc[quality.role.eq("test") & quality.draws.eq(128) & quality.variant.eq(variant), "coverage90"].iloc[0]
            assert actual == pytest.approx(recorded)


def test_system_unavailable_cases_remain_in_original_pool():
    costs = csv("system_factorial/original_pool_costs.csv")
    counts = costs[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1)
    np.testing.assert_allclose(counts, costs.n_candidates)
    assert costs.n_candidates.nunique() == 1
    operating = csv("system_factorial/original_pool_operating.csv")
    assert (operating.n_available + operating.n_unavailable).equals(operating.n_candidates)


def test_evidence_bindings_exclude_their_own_audit_outputs():
    path = RUN / "evidence/bindings.json"
    if not path.exists():
        pytest.skip("Evidence generation has not run")
    binding = json.loads(path.read_text())
    for record in binding["inputs"].values():
        source = Path(record["path"])
        assert "completion" not in source.parts and "evidence" not in source.parts
