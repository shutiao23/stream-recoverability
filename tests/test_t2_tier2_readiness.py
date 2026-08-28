from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from stream_recoverability.experiments.t2_tier2_readiness import (
    ALL_DEEP_OBLIGATIONS,
    build_tier2_deep_readiness_manifest,
    validate_tier2_sample_lock,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = (
    ROOT / "results/framework/t2_recovery_benchmark_v1/tier2_sample_lock.json"
)
READINESS_PATH = (
    ROOT
    / "results/framework/t2_recovery_benchmark_v1/"
    "tier2_deep_budget_readiness_manifest.json"
)


def _sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def test_sample_validation_rejects_reselection_or_horizon_shrink() -> None:
    sample = _sample()
    validate_tier2_sample_lock(sample)

    replaced = copy.deepcopy(sample)
    replaced["sample"][0]["network_id"] = "huc8_posthoc_replacement"
    with pytest.raises(ValueError, match="frozen SHA-256"):
        validate_tier2_sample_lock(replaced)

    horizon_shrunk = copy.deepcopy(sample)
    horizon_shrunk["gaps_all_required"] = [90]
    with pytest.raises(ValueError, match="30/90/180"):
        validate_tier2_sample_lock(horizon_shrunk)

    model_shrunk = copy.deepcopy(sample)
    model_shrunk["models"] = ["air2stream", "saits"]
    with pytest.raises(ValueError, match="roster changed"):
        validate_tier2_sample_lock(model_shrunk)


def test_current_fixed_sample_budget_failure_is_explicit_and_fail_closed() -> None:
    manifest = build_tier2_deep_readiness_manifest(
        ROOT, run_constructor_smoke=False
    )
    eligibility = manifest["sample_eligibility"]
    assert manifest["status"] == (
        "budget_failure_fixed_sample_cannot_meet_locked_minimum_on_current_corpus"
    )
    assert eligibility["n_sample_total"] == 30
    assert eligibility["n_sample_open_role"] == 22
    assert eligibility["n_sample_sealed_metadata_only"] == 8
    assert eligibility["n_sample_open_currently_qualified"] == 14
    assert eligibility["n_sample_open_currently_failed"] == 8
    assert (
        eligibility[
            "current_frozen_corpus_upper_bound_if_every_unread_sealed_row_qualifies"
        ]
        == 22
    )
    assert eligibility[
        "shortfall_below_locked_minimum_even_if_all_unread_sealed_qualify"
    ] == 6
    assert eligibility["locked_budget_feasible_on_current_frozen_corpus"] is False
    assert all(
        row["failure_reason"] == "fewer_than_3_qc_eligible_stations"
        for row in eligibility["open_currently_failed"]
    )
    assert manifest["budget_failure"]["posthoc_reselection_is_a_valid_remedy"] is False
    assert manifest["sample_lock"]["sample_reselection_performed"] is False
    assert manifest["sealed_temperature_records_read"] is False
    assert eligibility["sealed_rows_counted_as_qualified"] is False


def test_dry_run_covers_all_gaps_without_training_prediction_or_scoring() -> None:
    manifest = build_tier2_deep_readiness_manifest(
        ROOT, run_constructor_smoke=False
    )
    dry_run = manifest["dry_run"]
    assert dry_run["network_id"] in set(
        manifest["sample_eligibility"]["open_currently_qualified_ids"]
    )
    assert dry_run["gaps_all_required"] == [30, 90, 180]
    assert [row["gap_length_days"] for row in dry_run["cells"]] == [30, 90, 180]
    assert all(row["n_frozen_eligible_placements"] == 20 for row in dry_run["cells"])
    assert all(row["model_fit_called"] is False for row in dry_run["cells"])
    assert all(row["model_predict_called"] is False for row in dry_run["cells"])
    assert all(row["outcome_metric_computed"] is False for row in dry_run["cells"])
    assert dry_run["sealed_input_roots_allowed"] == []
    assert dry_run["sealed_temperature_records_read"] is False


def test_model_audit_preserves_every_obligation_and_honest_run_state() -> None:
    manifest = build_tier2_deep_readiness_manifest(
        ROOT, run_constructor_smoke=False
    )
    readiness = manifest["model_readiness"]
    assert readiness["required_obligations"] == list(ALL_DEEP_OBLIGATIONS)
    assert readiness["n_end_to_end_ready"] == 0
    assert readiness["deep_models_run"] is False
    models = readiness["models"]
    assert models["saits"]["repository_implementation"].endswith("adapter_present")
    assert models["csdi"]["repository_implementation"].endswith("adapter_present")
    for name in ("air2stream", "grin", "pgdl_or_graph_wavenet"):
        assert models[name]["t2_end_to_end_status"].startswith("not_ready")
    mentions = readiness["source_evidence"]["model_name_mentions"]
    roster_only_path = {
        "src/stream_recoverability/experiments/t2_recovery_benchmark.py"
    }
    assert {row["path"] for row in mentions["air2stream"]} == roster_only_path | {
        "src/stream_recoverability/experiments/process_hybrid_sensitivity.py"
    }
    process_manifest = json.loads(
        (
            ROOT
            / "results/development_v11/reviewer_completion/process_hybrid_manifest.json"
        ).read_text()
    )
    assert process_manifest["published_air2stream_implementation"] is False
    assert process_manifest["reviewer3_air2stream_requirement_satisfied"] is False
    assert {row["path"] for row in mentions["grin"]} == roster_only_path
    assert {
        row["path"] for row in mentions["pgdl_or_graph_wavenet"]
    } == roster_only_path
    assert manifest["frozen_contract"]["gaps_all_required"] == [30, 90, 180]
    assert manifest["frozen_contract"]["sample_changed"] is False


def test_stored_constructor_smoke_is_all_gap_and_not_a_deep_model_run() -> None:
    manifest = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    smoke = manifest["constructor_smoke"]
    assert smoke["status"] == "passed_constructor_only_not_training_or_inference"
    assert smoke["deep_models_run"] is False
    assert smoke["model_fit_called"] is False
    assert smoke["model_predict_called"] is False
    assert {
        (row["model"], row["gap_length_days"]) for row in smoke["rows"]
    } == {
        (model, gap)
        for model in ("saits", "csdi")
        for gap in (30, 90, 180)
    }
    assert all(row["constructor_passed"] is True for row in smoke["rows"])
    assert all(row["model_fit_called"] is False for row in smoke["rows"])
    assert all(row["model_predict_called"] is False for row in smoke["rows"])
    assert manifest["deep_models_run"] is False
    assert manifest["sealed_temperature_records_read"] is False
