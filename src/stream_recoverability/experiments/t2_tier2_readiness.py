"""Fail-closed readiness audit for the frozen v9.1 Tier-2 deep budget.

The Tier-2 sample was instantiated after open-role downloads had started.  It
therefore cannot be repaired by selecting a different set of networks after QC.
This module binds the existing sample lock to the current open six-year corpus,
audits executable model paths, and permits constructor-only smoke checks.  It
never traverses a sealed data directory and never trains, predicts, or scores a
deep model.
"""

from __future__ import annotations

import gc
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from importlib import metadata as importlib_metadata
from importlib import util as importlib_util
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    TIER2_GAPS,
    TIER2_MODELS,
    deterministic_placements,
    discover_failure_closure_networks,
    load_v91_budget,
    read_panel,
)
from stream_recoverability.models.reference_baselines import (
    PyPOTSReferenceImputer,
    ReferenceTrainingConfig,
    require_pypots_15,
)

SAMPLE_LOCK_RELATIVE_PATH = Path(
    "results/framework/t2_recovery_benchmark_v1/tier2_sample_lock.json"
)
TIMING_LEDGER_RELATIVE_PATH = Path(
    "results/framework/t2_recovery_benchmark_v1/tier2_timing_exception_ledger.json"
)
READINESS_RELATIVE_PATH = Path(
    "results/framework/t2_recovery_benchmark_v1/"
    "tier2_deep_budget_readiness_manifest.json"
)
ALL_DEEP_OBLIGATIONS = (
    "air2stream",
    "saits",
    "csdi",
    "grin",
    "pgdl_or_graph_wavenet",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sample_sha(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        list(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _distribution_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def validate_tier2_sample_lock(sample: Mapping[str, Any]) -> None:
    """Reject any sample, model, or horizon drift before readiness is audited."""

    rows = sample.get("sample")
    if not isinstance(rows, list) or len(rows) != 30:
        raise ValueError("Tier-2 sample lock must contain exactly 30 rows")
    identifiers = [str(row.get("network_id") or "") for row in rows]
    if any(not value for value in identifiers) or len(set(identifiers)) != len(
        identifiers
    ):
        raise ValueError("Tier-2 sample lock has missing or duplicate network ids")
    if _canonical_sample_sha(rows) != sample.get("sample_sha256"):
        raise ValueError("Tier-2 sample rows no longer match their frozen SHA-256")
    if int(sample.get("n_networks", -1)) != len(rows):
        raise ValueError("Tier-2 sample count disagrees with frozen rows")
    if tuple(sample.get("n_allowed_range") or ()) != (28, 32):
        raise ValueError("Tier-2 allowed sample range changed")
    if tuple(sample.get("models") or ()) != TIER2_MODELS:
        raise ValueError("Tier-2 four-model sensitivity roster changed")
    if tuple(int(value) for value in sample.get("gaps_all_required") or ()) != TIER2_GAPS:
        raise ValueError("Tier-2 must retain all 30/90/180-day gaps")
    if not sample.get("pgdl_or_graph_wavenet"):
        raise ValueError("PGDL/Graph WaveNet roster obligation disappeared")
    if sample.get("deep_models_run") is not False:
        raise ValueError("sample lock may not claim that deep models ran")
    if sample.get("sealed_temperature_records_read") is not False:
        raise ValueError("sample lock records a sealed-temperature read")


def _load_locked_inputs(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    sample_path = repo / SAMPLE_LOCK_RELATIVE_PATH
    ledger_path = repo / TIMING_LEDGER_RELATIVE_PATH
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    validate_tier2_sample_lock(sample)
    if ledger.get("sample_sha256") != sample["sample_sha256"]:
        raise ValueError("Tier-2 timing ledger is not bound to the sample lock")
    if ledger.get("sample_preregistered") is not False:
        raise ValueError("late Tier-2 sample may not be called preregistered")
    if ledger.get("sealed_temperature_records_read") is not False:
        raise ValueError("Tier-2 timing ledger records a sealed-temperature read")
    return sample, ledger


def _open_attrition_rows(repo: Path) -> dict[str, dict[str, Any]]:
    """Read only the two explicitly open failure-closure attrition tables."""

    base = repo / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
    result: dict[str, dict[str, Any]] = {}
    fields = (
        "network_id",
        "role",
        "complete_enough",
        "n_requested_stations",
        "n_qc_eligible_stations",
        "overlap_years",
    )
    for role in ("development", "validation"):
        path = base / role / "overlap_attrition.csv"
        frame = pd.read_csv(path)
        for row in frame.to_dict(orient="records"):
            network_id = str(row["network_id"])
            result[network_id] = {
                field: (
                    bool(row[field])
                    if field == "complete_enough"
                    else int(row[field])
                    if field in {"n_requested_stations", "n_qc_eligible_stations"}
                    else float(row[field])
                    if field == "overlap_years"
                    else str(row[field])
                )
                for field in fields
            }
    return result


def _dry_run_cells(
    repo: Path,
    sample_open_qualified: set[str],
    *,
    gaps: Sequence[int] = TIER2_GAPS,
) -> tuple[dict[str, Any], int]:
    """Bind one outcome-blind input cell per required gap to an open sample row."""

    networks, inventory = discover_failure_closure_networks(repo)
    candidates = [
        network for network in networks if network.network_id in sample_open_qualified
    ]
    if not candidates:
        raise RuntimeError("no frozen-sample open qualified network is available")
    network = min(candidates, key=lambda value: value.network_id)
    panel = read_panel(repo, network)
    target = next(
        (
            str(column)
            for column in sorted(panel.columns)
            if all(
                len(
                    deterministic_placements(
                        panel,
                        target=str(column),
                        gap_length=int(gap),
                        count=20,
                    )
                )
                == 20
                for gap in gaps
            )
        ),
        None,
    )
    if target is None:
        raise RuntimeError("no target supports all required Tier-2 gap dry runs")
    cells: list[dict[str, Any]] = []
    for gap in gaps:
        starts = deterministic_placements(
            panel, target=target, gap_length=int(gap), count=20
        )
        if len(starts) != 20:
            raise RuntimeError(f"dry-run target has fewer than 20 placements for gap {gap}")
        start = int(starts[0])
        cells.append(
            {
                "network_id": network.network_id,
                "role": network.role,
                "target_station": target,
                "gap_length_days": int(gap),
                "placement": 0,
                "start_index": start,
                "start_date": panel.index[start].date().isoformat(),
                "end_date": panel.index[start + int(gap) - 1].date().isoformat(),
                "n_features": int(panel.shape[1]),
                "n_frozen_eligible_placements": len(starts),
                "input_contract_only": True,
                "model_fit_called": False,
                "model_predict_called": False,
                "outcome_metric_computed": False,
            }
        )
    return (
        {
            "status": "passed_input_contract_only_not_model_execution",
            "network_is_in_unchanged_frozen_sample": True,
            "network_is_open_failure_closure6_qualified": True,
            "network_id": network.network_id,
            "network_manifest_path": network.manifest_path,
            "network_wide_path": network.wide_path,
            "network_wide_sha256": network.wide_sha256,
            "gaps_all_required": [int(value) for value in gaps],
            "cells": cells,
            "temperature_values_used_only_to_verify_input_eligibility": True,
            "outcome_values_used_for_model_or_sample_selection": False,
            "predictions_or_scores_generated": False,
            "sealed_temperature_records_read": False,
            "open_inventory_roots": inventory["allowed_input_roots"],
            "sealed_input_roots_allowed": inventory["sealed_input_roots_allowed"],
        },
        int(panel.shape[1]),
    )


def _constructor_smoke(n_features: int, *, enabled: bool) -> dict[str, Any]:
    """Initialize official cores only; never call fit, predict, or score."""

    pypots_version = _distribution_version("pypots")
    torch_version = _distribution_version("torch")
    if not enabled:
        return {
            "status": "not_run",
            "models": ["saits", "csdi"],
            "gaps_all_required": list(TIER2_GAPS),
            "model_fit_called": False,
            "model_predict_called": False,
            "deep_models_run": False,
            "pypots_version": pypots_version,
            "torch_version": torch_version,
        }
    bindings = require_pypots_15()
    config = ReferenceTrainingConfig(
        epochs=1,
        patience=1,
        batch_size=1,
        validation_sampling_times=1,
        prediction_sampling_times=1,
        device="cpu",
    )
    rows: list[dict[str, Any]] = []
    for model_name in ("saits", "csdi"):
        for gap in TIER2_GAPS:
            adapter = PyPOTSReferenceImputer(
                model_name, n_steps=int(gap), n_features=int(n_features)
            )
            estimator = adapter._instantiate(config, bindings)
            rows.append(
                {
                    "model": model_name,
                    "gap_length_days": int(gap),
                    "n_steps": int(gap),
                    "n_features": int(n_features),
                    "official_wrapper_module": estimator.__class__.__module__,
                    "official_core_module": estimator.model.__class__.__module__,
                    "parameter_count": int(
                        sum(parameter.numel() for parameter in estimator.model.parameters())
                    ),
                    "constructor_passed": True,
                    "model_fit_called": False,
                    "model_predict_called": False,
                    "outcome_metric_computed": False,
                }
            )
            del estimator, adapter
            gc.collect()
    return {
        "status": "passed_constructor_only_not_training_or_inference",
        "implementation": "official_pypots_1.5",
        "pypots_version": bindings.version,
        "torch_version": torch_version,
        "gaps_all_required": list(TIER2_GAPS),
        "rows": rows,
        "model_fit_called": False,
        "model_predict_called": False,
        "deep_models_run": False,
    }


def _python_source_mentions(repo: Path) -> dict[str, list[dict[str, Any]]]:
    """Inventory model-name mentions in executable source, excluding this audit."""

    tokens = {
        "air2stream": ("air2stream",),
        "saits": ("saits",),
        "csdi": ("csdi",),
        "grin": ("grin",),
        "pgdl_or_graph_wavenet": ("pgdl", "graph_wavenet", "graph wavenet"),
    }
    source_root = repo / "src/stream_recoverability"
    this_path = Path(__file__).resolve()
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in tokens}
    for path in sorted(source_root.rglob("*.py")):
        if path.resolve() == this_path:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for model_name, needles in tokens.items():
            matching = [
                number
                for number, line in enumerate(lines, start=1)
                if any(needle in line.lower() for needle in needles)
            ]
            if matching:
                result[model_name].append(
                    {
                        "path": str(path.relative_to(repo)),
                        "line_numbers": matching,
                    }
                )
    return result


def _model_readiness(repo: Path, constructor: Mapping[str, Any]) -> dict[str, Any]:
    reference_path = repo / "src/stream_recoverability/models/reference_baselines.py"
    runner_path = repo / "src/stream_recoverability/experiments/t2_recovery_benchmark.py"
    project_path = repo / "pyproject.toml"
    pypots_version = _distribution_version("pypots")
    torch_version = _distribution_version("torch")
    source_mentions = _python_source_mentions(repo)
    shared = {
        "t2_runner_trains_deep_models": False,
        "t2_runner_declares_tier2_metadata_only": True,
        "tier2_training_protocol_wired": False,
        "deep_model_training_run": False,
        "deep_model_inference_run": False,
    }
    return {
        "required_obligations": list(ALL_DEEP_OBLIGATIONS),
        "source_evidence": {
            "reference_adapter_path": str(reference_path.relative_to(repo)),
            "reference_adapter_sha256": _sha256_file(reference_path),
            "t2_runner_path": str(runner_path.relative_to(repo)),
            "t2_runner_sha256": _sha256_file(runner_path),
            "project_dependency_path": str(project_path.relative_to(repo)),
            "project_dependency_sha256": _sha256_file(project_path),
            "implementation_search_scope": "src/stream_recoverability/**/*.py",
            "audit_module_excluded_from_search": str(Path(__file__).resolve().relative_to(repo)),
            "model_name_mentions": source_mentions,
            "absence_interpretation": (
                "a roster-string mention is not an executable implementation; "
                "only SAITS/CSDI resolve to model adapter code"
            ),
        },
        "models": {
            "saits": {
                **shared,
                "repository_implementation": "official_pypots_1.5_adapter_present",
                "dependency_status": "available_exact_pin",
                "pypots_version": pypots_version,
                "torch_version": torch_version,
                "constructor_smoke_status": constructor["status"],
                "t2_end_to_end_status": "not_ready_no_t2_training_or_scoring_adapter",
            },
            "csdi": {
                **shared,
                "repository_implementation": "official_pypots_1.5_adapter_present",
                "dependency_status": "available_exact_pin",
                "pypots_version": pypots_version,
                "torch_version": torch_version,
                "constructor_smoke_status": constructor["status"],
                "t2_end_to_end_status": "not_ready_no_t2_training_or_scoring_adapter",
            },
            "air2stream": {
                **shared,
                "repository_implementation": "absent_protocol_mentions_only",
                "dependency_status": "not_declared_or_importable",
                "importable_module": bool(importlib_util.find_spec("air2stream")),
                "required_information_contract": "air_temperature_and_optional_discharge_not_wired",
                "t2_end_to_end_status": "not_ready_no_implementation_or_adapter",
            },
            "grin": {
                **shared,
                "repository_implementation": "absent_protocol_mentions_only",
                "dependency_status": "not_declared_or_importable",
                "importable_module": bool(importlib_util.find_spec("grin")),
                "torch_geometric_importable": bool(
                    importlib_util.find_spec("torch_geometric")
                ),
                "graph_contract": "no_frozen_graph_tensor_or_t2_adapter",
                "t2_end_to_end_status": "not_ready_no_implementation_or_adapter",
            },
            "pgdl_or_graph_wavenet": {
                **shared,
                "repository_implementation": "absent_roster_obligation_has_no_executable_identity",
                "dependency_status": "not_declared",
                "torch_version": torch_version,
                "torch_geometric_importable": bool(
                    importlib_util.find_spec("torch_geometric")
                ),
                "graph_contract": "no_frozen_model_identity_graph_tensor_or_t2_adapter",
                "t2_end_to_end_status": "not_ready_no_implementation_or_adapter",
            },
        },
        "n_end_to_end_ready": 0,
        "deep_models_run": False,
    }


def build_tier2_deep_readiness_manifest(
    repo_root: str | Path,
    *,
    run_constructor_smoke: bool = True,
) -> dict[str, Any]:
    """Build the immutable-sample budget failure and model readiness record."""

    repo = Path(repo_root).resolve()
    sample, ledger = _load_locked_inputs(repo)
    budget = load_v91_budget(repo)
    sample_rows = list(sample["sample"])
    sealed_rows = [row for row in sample_rows if row["role"] == "sealed"]
    open_rows = [row for row in sample_rows if row["role"] != "sealed"]
    open_ids = {str(row["network_id"]) for row in open_rows}
    networks, inventory = discover_failure_closure_networks(repo)
    qualified_ids = {network.network_id for network in networks}
    sample_open_qualified = open_ids & qualified_ids
    sample_open_failed = open_ids - qualified_ids
    attrition = _open_attrition_rows(repo)
    failed_rows = []
    for network_id in sorted(sample_open_failed):
        row = attrition.get(network_id)
        if row is None:
            failed_rows.append(
                {
                    "network_id": network_id,
                    "complete_enough": False,
                    "failure_reason": "absent_from_open_failure_closure6_attrition",
                }
            )
        else:
            failed_rows.append(
                {
                    **row,
                    "failure_reason": (
                        "fewer_than_3_qc_eligible_stations"
                        if int(row["n_qc_eligible_stations"]) < 3
                        else "not_complete_enough_under_frozen_failure_closure6"
                    ),
                }
            )
    minimum = int(sample["n_allowed_range"][0])
    current_upper_bound = len(sample_open_qualified) + len(sealed_rows)
    dry_run, n_features = _dry_run_cells(repo, sample_open_qualified)
    constructor = _constructor_smoke(n_features, enabled=run_constructor_smoke)
    model_readiness = _model_readiness(repo, constructor)
    sample_lock_path = repo / SAMPLE_LOCK_RELATIVE_PATH
    timing_path = repo / TIMING_LEDGER_RELATIVE_PATH
    return {
        "manifest_schema": "t2_v91_tier2_deep_budget_readiness_v1",
        "status": "budget_failure_fixed_sample_cannot_meet_locked_minimum_on_current_corpus",
        "design_id": sample["design_id"],
        "protocol_amendment": sample["protocol_amendment"],
        "purpose": sample["purpose"],
        "formal_evidence": False,
        "not_t2_primary_y": True,
        "deep_models_run": False,
        "deep_model_training_run": False,
        "deep_model_inference_run": False,
        "sealed_temperature_records_read": False,
        "sample_lock": {
            "path": str(SAMPLE_LOCK_RELATIVE_PATH),
            "file_sha256": _sha256_file(sample_lock_path),
            "sample_sha256": sample["sample_sha256"],
            "canonical_sample_sha256_recomputed": _canonical_sample_sha(sample_rows),
            "n_networks": len(sample_rows),
            "role_counts": dict(sorted(Counter(row["role"] for row in sample_rows).items())),
            "sample_preregistered": False,
            "sample_locked_before_download": False,
            "sample_frozen_before_tier2_model_execution": True,
            "sample_reselection_allowed": False,
            "sample_reselection_performed": False,
            "gaps_all_required": list(TIER2_GAPS),
            "models": list(TIER2_MODELS),
            "pgdl_or_graph_wavenet": sample["pgdl_or_graph_wavenet"],
        },
        "timing_exception": {
            "path": str(TIMING_LEDGER_RELATIVE_PATH),
            "file_sha256": _sha256_file(timing_path),
            "ledger_id": ledger["ledger_id"],
            "status": ledger["status"],
            "resolution": ledger["resolution"],
            "required_reporting": ledger["required_reporting"],
        },
        "sample_eligibility": {
            "qualification_mode": "failure_closure6",
            "n_sample_total": len(sample_rows),
            "n_sample_open_role": len(open_rows),
            "n_sample_sealed_metadata_only": len(sealed_rows),
            "n_sample_open_currently_qualified": len(sample_open_qualified),
            "n_sample_open_currently_failed": len(sample_open_failed),
            "open_currently_qualified_ids": sorted(sample_open_qualified),
            "open_currently_failed": failed_rows,
            "sealed_metadata_only_ids": sorted(str(row["network_id"]) for row in sealed_rows),
            "locked_minimum_n": minimum,
            "current_frozen_corpus_upper_bound_if_every_unread_sealed_row_qualifies": current_upper_bound,
            "shortfall_below_locked_minimum_even_if_all_unread_sealed_qualify": minimum
            - current_upper_bound,
            "locked_budget_feasible_on_current_frozen_corpus": current_upper_bound
            >= minimum,
            "non_sample_qualified_networks_may_substitute": False,
            "failed_sample_rows_may_be_replaced": False,
            "sealed_rows_counted_as_qualified": False,
            "sealed_results_inferred": False,
            "open_inventory_n_qualified_all_networks": inventory["n_networks_eligible"],
            "open_inventory_roles_all_networks": inventory["roles"],
            "sealed_input_roots_allowed": inventory["sealed_input_roots_allowed"],
        },
        "budget_failure": {
            "failure_class": "fixed_sample_attrition_below_preregistered_allowed_range",
            "passed": False,
            "posthoc_reselection_is_a_valid_remedy": False,
            "dropping_failed_rows_is_a_valid_remedy": False,
            "selecting_only_one_of_30_90_180_is_a_valid_remedy": False,
            "dropping_unimplemented_model_classes_is_a_valid_remedy": False,
            "can_claim_compliant_tier2_sensitivity": False,
            "honest_resolution": (
                "retain_the_unchanged_sample_and_report_budget_failure; do_not replace "
                "failed or sealed rows and do not claim the locked Tier-2 sensitivity"
            ),
        },
        "dry_run": dry_run,
        "constructor_smoke": constructor,
        "model_readiness": model_readiness,
        "frozen_contract": {
            "design_sha256": budget["design_sha256"],
            "n_allowed_range": list(sample["n_allowed_range"]),
            "gaps_all_required": list(TIER2_GAPS),
            "all_model_obligations": list(ALL_DEEP_OBLIGATIONS),
            "outcome_selected_model_or_horizon": False,
            "sample_changed": False,
        },
    }


__all__ = [
    "ALL_DEEP_OBLIGATIONS",
    "READINESS_RELATIVE_PATH",
    "build_tier2_deep_readiness_manifest",
    "validate_tier2_sample_lock",
]
