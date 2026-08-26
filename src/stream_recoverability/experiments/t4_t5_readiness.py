"""Read-only readiness contracts for the v9.1 T4/T5 experiments.

This module does not score river temperatures and does not write artifacts.  It
keeps development outputs from being mistaken for a formal T4 or T5 result while
the T2 primary outcome and topology-matched pair table are still incomplete.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

T4_SCORE_COLUMNS = frozenset(
    {
        "network_id",
        "station_id",
        "gap_length",
        "fill_mae",
        "achieved_skill",
        "recoverability_r",
        "truth_source",
        "geometry_source",
        "formal_evidence",
    }
)

# The freeze names the matching factors but does not lock calipers.  A formal
# pair table must therefore expose the factor-level diagnostics without this
# auditor inventing post-hoc tolerances.
T5_PAIR_AUDIT_COLUMNS = frozenset(
    {
        "regulated_id",
        "control_id",
        "delta_r",
        "donor_count_abs_diff",
        "donor_direction_match",
        "nearest_donor_distance_abs_diff",
        "log_drainage_area_abs_diff",
        "climate_match",
        "bfi_abs_diff",
    }
)


def _missing_columns(frame: pd.DataFrame, required: Sequence[str]) -> list[str]:
    return sorted(set(required).difference(frame.columns))


def audit_t4_scores(
    scores: pd.DataFrame,
    *,
    required_geometry_networks: Sequence[str] = (),
) -> dict[str, Any]:
    """Audit provenance and coverage only; never decide that T4 passed."""

    missing = _missing_columns(scores, T4_SCORE_COLUMNS)
    scored_networks = (
        set(scores["network_id"].dropna().astype(str))
        if "network_id" in scores.columns
        else set()
    )
    required_networks = {str(item) for item in required_geometry_networks}
    absent_geometry_networks = sorted(required_networks.difference(scored_networks))
    provenance_ok = False
    if not missing and not scores.empty:
        provenance_ok = bool(
            scores["truth_source"].eq("held_out_observed_days").all()
            and scores["geometry_source"].eq("real_missing_blocks_length_season").all()
            and ~scores["formal_evidence"].fillna(True).astype(bool).any()
        )
    finite_outcomes = 0
    if {"fill_mae", "achieved_skill", "recoverability_r"}.issubset(scores.columns):
        finite = np.isfinite(
            scores[["fill_mae", "achieved_skill", "recoverability_r"]]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        ).all(axis=1)
        finite_outcomes = int(finite.sum())
    return {
        "contract": "t4_v9_1_natural_outage_input_v1",
        "missing_columns": missing,
        "provenance_ok": provenance_ok,
        "n_rows": len(scores),
        "n_finite_rows": finite_outcomes,
        "n_networks": len(scored_networks),
        "required_geometry_networks": sorted(required_networks),
        "missing_geometry_networks": absent_geometry_networks,
        "input_contract_ready": bool(
            not missing
            and provenance_ok
            and finite_outcomes > 0
            and not absent_geometry_networks
        ),
        "passed": False,
        "purpose": "input_readiness_not_evidence",
    }


def audit_t5_pairs(
    pairs: pd.DataFrame,
    *,
    matching_factors: Sequence[str],
) -> dict[str, Any]:
    """Check that every frozen matching factor is auditable per finite pair."""

    missing = _missing_columns(pairs, T5_PAIR_AUDIT_COLUMNS)
    frozen = {str(item) for item in matching_factors}
    expected = {
        "donor_count",
        "donor_direction",
        "nearest_donor_distance",
        "drainage_area",
        "climate",
        "bfi",
    }
    freeze_complete = expected.issubset(frozen)
    finite_pairs = 0
    one_to_one = False
    if {"regulated_id", "control_id", "delta_r"}.issubset(pairs.columns):
        finite_pairs = int(
            np.isfinite(pd.to_numeric(pairs["delta_r"], errors="coerce")).sum()
        )
        one_to_one = bool(
            not pairs["regulated_id"].duplicated().any()
            and not pairs["control_id"].duplicated().any()
        )
    return {
        "contract": "t5_v9_1_topology_matched_regulation_input_v1",
        "frozen_matching_factors": sorted(frozen),
        "freeze_factor_set_complete": freeze_complete,
        "missing_pair_audit_columns": missing,
        "n_pairs_declared": len(pairs),
        "n_pairs_with_finite_delta_r": finite_pairs,
        "one_to_one_pairing": one_to_one,
        "input_contract_ready": bool(
            freeze_complete
            and not missing
            and finite_pairs == len(pairs)
            and finite_pairs > 0
            and one_to_one
        ),
        "passed": False,
        "purpose": "input_readiness_not_evidence",
    }


def readiness_manifest(
    freeze: Mapping[str, Any],
    *,
    t4_scores: pd.DataFrame,
    t4_geometry_networks: Sequence[str],
    t5_pairs: pd.DataFrame,
    twin_e_manifest: Mapping[str, Any] | None,
    t2_primary_y_bound: bool = False,
) -> dict[str, Any]:
    """Compose a non-result manifest that remains blocked until T2 is bound."""

    t4 = audit_t4_scores(t4_scores, required_geometry_networks=t4_geometry_networks)
    factors = freeze.get("t5_confound_control", {}).get("matching_factors", [])
    t5 = audit_t5_pairs(t5_pairs, matching_factors=factors)
    twin_gate = dict((twin_e_manifest or {}).get("gate", {}))
    twin_status = str(twin_gate.get("status", "missing"))
    twin_passed = bool(twin_gate.get("passed", False))
    formal_run_allowed = bool(
        t2_primary_y_bound and t4["input_contract_ready"] and t5["input_contract_ready"]
    )
    if not t2_primary_y_bound:
        status = "blocked_waiting_for_t2_primary_y"
    elif not t4["input_contract_ready"] or not t5["input_contract_ready"]:
        status = "blocked_input_contract_incomplete"
    else:
        status = "ready_for_formal_runner_not_a_result"
    return {
        "schema_version": "t4_t5_v9_1_readiness_v1",
        "design_id": freeze.get("design_id"),
        "protocol_amendment": freeze.get("protocol_amendment"),
        "status": status,
        "purpose": "pipeline_contract_not_evidence",
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "sealed_outcomes_opened": False,
        "t2_primary_y_bound": bool(t2_primary_y_bound),
        "t4": t4,
        "t5_real_river": t5,
        "t5_twin_e": {
            "status": twin_status,
            "passed": twin_passed,
            "negative_result_locked": bool(
                not twin_passed and twin_status == "twin_e_operator_calibration_miss"
            ),
            "generator_retuning_allowed": False,
        },
        "formal_run_allowed": formal_run_allowed,
        "passed": False,
    }


def geometry_networks_from_blocks(paths: Sequence[str | Path]) -> list[str]:
    """Return the union of network IDs named by frozen outage catalogs."""

    networks: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            continue
        frame = pd.read_csv(path, dtype={"network_id": str})
        if "network_id" in frame.columns:
            networks.update(frame["network_id"].dropna().astype(str))
    return sorted(networks)


__all__ = [
    "T4_SCORE_COLUMNS",
    "T5_PAIR_AUDIT_COLUMNS",
    "audit_t4_scores",
    "audit_t5_pairs",
    "geometry_networks_from_blocks",
    "readiness_manifest",
]
