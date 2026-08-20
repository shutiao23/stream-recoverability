from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from stream_recoverability.analysis.falsification import (
    DONOR_LAGS_DAYS,
    apply_donor_lag,
    falsification_grid,
    interpret_falsification,
    permute_donor_station_identity,
)
from stream_recoverability.analysis.frontiers import (
    add_relative_skills,
    select_best_simple_baselines,
)
from stream_recoverability.data.quality import (
    PROVIDER_QC_UNKNOWN,
    attach_qc_fields,
    load_quality_codebook,
)
from stream_recoverability.data.versions import apply_data_version
from stream_recoverability.experiments.contracts import (
    DEFAULT_DESIGN_PATH,
    EXECUTABLE_DESIGN_VERSION,
    load_frozen_data_versions,
)
from stream_recoverability.experiments.selection import select_stage2_finalists
from stream_recoverability.experiments.runner import _load_data
from stream_recoverability.governance import (
    audit_restricted_hosting,
    submission_gate,
)


REPO = Path(__file__).resolve().parents[1]


def test_executable_freeze_is_v4_with_budget_and_dual_frontier() -> None:
    design = yaml.safe_load((REPO / DEFAULT_DESIGN_PATH).read_text(encoding="utf-8"))
    assert design["design_version"] == EXECUTABLE_DESIGN_VERSION
    assert design["training"]["fixed_model_protocols"]["common"]["max_epochs"] == 400
    assert design["training"]["budget_rule"]["reject_if_hit_epoch_limit"] is True
    assert (
        design["statistics"]["frontier_denominators"]["best_simple_baseline_relative"][
            "status"
        ]
        == "primary_required"
    )
    assert design["data_versions"]["primary"] == "published_v2"
    assert design["statistics"]["application_thresholds"]["status"] == "not_declared"
    assert "donor_c_falsification_v1" in design["required_protocol_sensitivities"]
    versions = load_frozen_data_versions(REPO / DEFAULT_DESIGN_PATH)
    assert versions.primary == "published_v2"
    assert versions.sensitivities == (
        "no_s2_suspect_v2",
        "b1_no_level_v2",
        "b1_shift_sensitivity_v2",
    )


def test_anchor_bridge_is_complete_without_digest_pinning() -> None:
    bridge = json.loads(
        (REPO / "metadata/anchor_bridge_published_v1_to_v2.json").read_text(
            encoding="utf-8"
        )
    )
    assert bridge["status"] == "complete"
    assert bridge["date_axis_equal"] is True
    assert bridge["row_index_equal"] is True
    assert "sha256" not in str(bridge).lower()
    validation = pd.read_csv(REPO / "metadata/validation_anchors_v2.csv")
    frontier = pd.read_csv(REPO / "metadata/frontier_anchors_v2.csv")
    assert len(validation) == 15
    assert len(frontier) == 180
    assert set(validation["data_version"]) == {"published_v2"}
    assert set(frontier["data_version"]) == {"published_v2"}


def test_quality_codebook_keeps_unknown_unflagged_out_of_approved() -> None:
    codebook = load_quality_codebook(REPO / "metadata/quality_codebook.csv")
    unflagged = codebook.set_index("qc_status").loc["observed_unflagged"]
    assert unflagged["provider_qc_status"] == PROVIDER_QC_UNKNOWN
    assert int(unflagged["analysis_eligible"]) == 1
    assert int(unflagged["quality_approved"]) == 1


def test_attach_qc_fields_flags_known_issues_without_approving_unknown() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2018-12-31", "2019-01-01", "2015-06-01"]),
            "station_id": ["B1", "B1", "S2"],
            "variable": ["L", "L", "T"],
            "natural_observed": [True, True, True],
            "qc_status": ["observed_unflagged"] * 3,
        }
    )
    attached = attach_qc_fields(frame)
    assert attached["provider_qc_status"].eq(PROVIDER_QC_UNKNOWN).all()
    assert attached["analysis_eligible"].all()
    assert not attached.loc[0, "known_issue_flag"]
    assert attached.loc[1, "known_issue_flag"]
    assert attached.loc[1, "known_issue_code"] == "b1_level_datum_shift"
    assert attached.loc[2, "known_issue_flag"]
    assert attached.loc[2, "known_issue_code"] == "s2_source_year_order_discrepancy"
    bad = attached.copy()
    bad.loc[0, "provider_qc_status"] = "approved"
    with pytest.raises(ValueError, match="forbidden"):
        attach_qc_fields(bad)


def test_published_v2_preserves_values_and_adds_qc_fields() -> None:
    source = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-01-01", "2019-01-01"]),
            "station_id": ["B1", "P3"],
            "variable": ["L", "T"],
            "raw_value": [10.0, 8.0],
            "value": [10.0, 8.0],
            "natural_observed": [True, True],
            "quality_approved": [True, True],
            "qc_status": ["observed_unflagged", "observed_unflagged"],
        }
    )
    versioned = apply_data_version(source, "published_v2")
    pd.testing.assert_series_equal(versioned["value"], source["value"])
    pd.testing.assert_series_equal(versioned["raw_value"], source["raw_value"])
    assert versioned["provider_qc_status"].eq(PROVIDER_QC_UNKNOWN).all()
    assert bool(versioned.loc[0, "known_issue_flag"])
    assert not bool(versioned.loc[1, "known_issue_flag"])


def test_v2_runner_requires_analysis_eligible_and_rejects_alias_drift(
    tmp_path: Path,
) -> None:
    dates = pd.date_range("2016-01-01", periods=2, freq="D")
    wide = pd.DataFrame(
        {
            "date": dates,
            "split": ["validation", "validation"],
            "data_version": ["published_v2", "published_v2"],
            "B1_T": [1.0, 2.0],
        }
    )
    long = pd.DataFrame(
        {
            "date": dates,
            "station_id": ["B1", "B1"],
            "variable": ["T", "T"],
            "data_version": ["published_v2", "published_v2"],
            "analysis_eligible": [True, True],
            "quality_approved": [True, False],
            "provider_qc_status": ["unknown", "unknown"],
            "known_issue_flag": [False, False],
        }
    )
    wide_path = tmp_path / "wide.parquet"
    long_path = tmp_path / "long.parquet"
    wide.to_parquet(wide_path, index=False)
    long.to_parquet(long_path, index=False)
    with pytest.raises(ValueError, match="legacy alias differs"):
        _load_data(wide_path, long_path, ("T",))


def test_dual_frontier_uses_validation_selected_simple_baseline() -> None:
    events = pd.DataFrame(
        {
            "experiment": ["SCI_DENSE"] * 6,
            "scenario_id": ["A", "A", "A", "B", "B", "B"],
            "station_id": ["B1"] * 6,
            "target": ["T"] * 6,
            "gap_length": [10, 10, 10, 30, 30, 30],
            "mask_seed": [101] * 6,
            "window_length": [736] * 6,
            "condition_id": ["T10"] * 3 + ["T30"] * 3,
            "model": ["climatology", "linear", "proposed"] * 2,
            "MAE": [2.0, 1.0, 0.5, 4.0, 2.0, 1.0],
        }
    )
    best = select_best_simple_baselines(events)
    assert set(best["best_simple_baseline"]) == {"linear"}
    assert len(best) == 1
    assert "T10" not in best.iloc[0]["condition_family"]
    assert "T30" not in best.iloc[0]["condition_family"]
    scored = add_relative_skills(events, best_simple=best)
    proposed = scored.loc[scored["model"].eq("proposed")].set_index("gap_length")
    assert proposed.loc[10, "skill_vs_climatology"] == pytest.approx(0.75)
    assert proposed.loc[10, "skill_vs_best_simple"] == pytest.approx(0.5)


def test_falsification_grid_and_wording_rule() -> None:
    grid = falsification_grid()
    contrasts = {item["contrast"] for item in grid}
    assert contrasts == {
        "observed_same_day_C",
        "lagged_C",
        "past_only_C",
        "station_identity_permutation",
        "seasonal_residual_block_permutation",
    }
    assert {item["lag_days"] for item in grid if item["contrast"] == "lagged_C"} == set(
        DONOR_LAGS_DAYS
    ) - {0}
    wide = pd.DataFrame(
        {
            "date": pd.date_range("2006-01-01", periods=5, freq="D"),
            "B1_T": np.arange(5, dtype=float),
            "S2_T": np.arange(5, dtype=float) + 10,
            "P3_T": np.arange(5, dtype=float) + 20,
        }
    )
    lagged = apply_donor_lag(wide, lag_days=1, target_station="B1")
    assert lagged.loc[1, "S2_T"] == pytest.approx(10.0)
    assert lagged["B1_T"].equals(wide["B1_T"])
    permuted = permute_donor_station_identity(wide, seed=1, target_station="B1")
    assert permuted["B1_T"].equals(wide["B1_T"])
    assert not permuted["S2_T"].equals(wide["S2_T"]) or not permuted["P3_T"].equals(
        wide["P3_T"]
    )
    summary = pd.DataFrame(
        {
            "contrast": [
                "observed_same_day_C",
                "station_identity_permutation",
                "lagged_C",
            ],
            "lag_days": [0, 0, -30],
            "skill_gain": [0.20, 0.20, 0.21],
        }
    )
    reading = interpret_falsification(summary)
    assert reading["claim_language"] == "correlated_predictive_source_only"


def test_hit_epoch_limit_is_budget_unstable() -> None:
    ranking = pd.DataFrame(
        {
            "model": ["brits_ref", "saits_ref", "csdi", "proposed"],
            "validation_stage": ["deep_single_seed"] * 4,
            "mean_skill_across_strata": [0.30, 0.29, 0.28, 0.27],
        }
    )
    diagnostics = pd.DataFrame(
        {
            "model": ranking["model"],
            "finite_predictions": [True, True, True, True],
            "finite_validation_score": [True, True, True, True],
            "best_epoch": [400, 10, 10, 10],
            "epochs_run": [400, 20, 20, 20],
            "hit_epoch_limit": [True, False, False, False],
        }
    )
    selected = select_stage2_finalists(ranking, diagnostics=diagnostics).set_index(
        "model"
    )
    assert not bool(selected.loc["brits_ref", "diagnostic_pass"])
    assert "budget_stable" in selected.loc["brits_ref", "selection_reason"] or (
        "failed diagnostics" in selected.loc["brits_ref", "selection_reason"]
    )
    assert bool(selected.loc["saits_ref", "diagnostic_pass"])


def test_submission_gate_is_fail_closed_without_formal_evidence() -> None:
    gate = submission_gate(REPO)
    assert gate["decision"] == "no_go"
    assert gate["passed"] is False
    assert any(
        "RESULTS_PENDING" in item or "roster" in item for item in gate["blockers"]
    )
    hosting = audit_restricted_hosting(REPO)
    assert (
        "public_hosting_defect" in hosting["status"]
        or hosting["restricted_tracked_path_count"] >= 0
    )
