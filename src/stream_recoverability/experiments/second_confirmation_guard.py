"""Fail-closed bindings for the amended Route A second confirmation.

The scorer must not treat an arbitrary JSON boolean as authorization.  This
module recomputes every material gate from repository-canonical, hash-bound
protocol, amendment, and exact-roster artifacts before any panel is opened.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

READINESS_SCHEMA_VERSION = 2


class SecondConfirmationGateError(RuntimeError):
    """Raised before temperature access when authorization cannot be proven."""


def attrition_gate_summary(
    *,
    attempted_networks: int,
    attrited_networks: int,
    scored_networks: int,
    minimum: int = 40,
) -> dict[str, Any]:
    """Declare whether post-QC attrition permits performance reporting."""

    if attempted_networks < 0 or attrited_networks < 0 or scored_networks < 0:
        raise ValueError("network counts must be non-negative")
    if attrited_networks + scored_networks != attempted_networks:
        raise ValueError("attempted must equal attrited plus scored networks")
    passed = scored_networks >= minimum
    return {
        "attempted_networks": attempted_networks,
        "attrited_networks": attrited_networks,
        "scored_networks": scored_networks,
        "minimum_scored_network_floor": minimum,
        "attrition_floor_passed": passed,
        "performance_reporting_authorized": passed,
        "status": (
            "scored_after_readiness_authorization"
            if passed
            else "scored_but_invalid_below_attrition_floor"
        ),
    }


def validate_scored_result_gate(summary: dict[str, Any], *, minimum: int = 40) -> None:
    """Reject downstream analyses unless post-QC attrition licensed reporting."""

    if summary.get("status") != "scored_after_readiness_authorization":
        raise SecondConfirmationGateError(
            "second-confirmation scoring status is invalid"
        )
    if summary.get("performance_reporting_authorized") is not True:
        raise SecondConfirmationGateError("performance reporting is not authorized")
    if int(summary.get("scored_networks", -1)) < minimum:
        raise SecondConfirmationGateError("scored-network attrition floor failed")
    if summary.get("attrition_floor_passed") is not True:
        raise SecondConfirmationGateError("attrition floor is not marked passed")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SecondConfirmationGateError(f"invalid YAML mapping: {path}")
    return value


def effective_requirements(
    protocol: dict[str, Any], amendment: dict[str, Any]
) -> dict[str, int]:
    if amendment.get("parent_protocol_id") != protocol.get("protocol_id"):
        raise SecondConfirmationGateError("amendment parent protocol mismatch")
    if amendment.get("status") != "frozen_pre_outcome_scoring":
        raise SecondConfirmationGateError("amendment is not frozen pre-outcome")
    invariants = amendment.get("invariants", {})
    if invariants.get("recovery_outcomes_seen_before_amendment") is not False:
        raise SecondConfirmationGateError("amendment lacks the pre-outcome invariant")
    requirements = amendment.get("effective_domain_requirements", {}).get(
        "minimum_networks_by_domain", {}
    )
    if not requirements:
        raise SecondConfirmationGateError(
            "amendment has no effective domain requirements"
        )
    return {str(key): int(value) for key, value in requirements.items()}


def frozen_roster_from_qc(
    readiness_roster: pd.DataFrame,
    amendment: dict[str, Any],
) -> pd.DataFrame:
    """Return the deterministic, exact qualified roster declared by v2."""

    frozen = amendment["frozen_scoring_roster"]
    columns = [
        "network_id",
        "provider",
        "domain",
        "qc_status",
        "complete_enough",
    ]
    missing = set(columns) - set(readiness_roster.columns)
    if missing:
        raise SecondConfirmationGateError(
            f"readiness roster lacks required columns: {sorted(missing)}"
        )
    selected = readiness_roster.loc[
        readiness_roster["qc_status"].eq("qualified")
        & readiness_roster["complete_enough"].astype(bool),
        columns,
    ].copy()
    selected["network_id"] = selected["network_id"].astype(str)
    selected = selected.sort_values("network_id", kind="mergesort").reset_index(
        drop=True
    )
    if selected["network_id"].duplicated().any():
        raise SecondConfirmationGateError(
            "qualified roster contains duplicate network IDs"
        )
    expected_total = int(frozen["exact_networks"])
    if len(selected) != expected_total:
        raise SecondConfirmationGateError(
            f"frozen roster count differs: {len(selected)} != {expected_total}"
        )
    actual = selected.groupby("domain").size().to_dict()
    expected = {
        str(key): int(value)
        for key, value in frozen["exact_networks_by_domain"].items()
    }
    if actual != expected:
        raise SecondConfirmationGateError(
            f"frozen domain composition differs: {actual} != {expected}"
        )
    return selected


def build_authorized_readiness(
    *,
    root: Path,
    protocol_path: Path,
    amendment_path: Path,
    readiness_roster_path: Path,
    frozen_roster_path: Path,
) -> dict[str, Any]:
    protocol = _read_yaml(protocol_path)
    amendment = _read_yaml(amendment_path)
    requirements = effective_requirements(protocol, amendment)
    readiness_roster = pd.read_csv(readiness_roster_path, dtype={"network_id": str})
    expected_frozen = frozen_roster_from_qc(readiness_roster, amendment)
    if frozen_roster_path.is_file():
        existing = pd.read_csv(frozen_roster_path, dtype={"network_id": str})
        try:
            pd.testing.assert_frame_equal(existing, expected_frozen, check_dtype=False)
        except AssertionError as exc:
            raise SecondConfirmationGateError(
                "existing frozen scoring roster differs from deterministic QC roster"
            ) from exc
    else:
        frozen_roster_path.parent.mkdir(parents=True, exist_ok=True)
        expected_frozen.to_csv(frozen_roster_path, index=False)

    reference_config = amendment["frozen_scoring_roster"]["independence_references"]
    reference_paths = {
        key: (root / str(value)).resolve() for key, value in reference_config.items()
    }
    for key, path in reference_paths.items():
        if not path.is_file():
            raise SecondConfirmationGateError(f"independence reference absent: {key}")
    frozen_ids = set(expected_frozen["network_id"].astype(str))
    development_ids = set(
        pd.read_csv(reference_paths["development_outcomes"], dtype={"network_id": str})[
            "network_id"
        ].astype(str)
    )
    first_scored_ids = set(
        pd.read_csv(
            reference_paths["first_confirmation_outcomes"], dtype={"network_id": str}
        )["network_id"].astype(str)
    )
    first_qc_ids = set(
        pd.read_csv(
            reference_paths["first_confirmation_qc_panel"], dtype={"network_id": str}
        )["network_id"].astype(str)
    )
    development_overlap = sorted(frozen_ids & development_ids)
    first_scored_overlap = sorted(frozen_ids & first_scored_ids)
    qc_only_overlap = sorted(frozen_ids & (first_qc_ids - first_scored_ids))
    declared_qc_only = sorted(
        str(value)
        for value in amendment["frozen_scoring_roster"][
            "first_confirmation_qc_only_reused"
        ]
    )
    if development_overlap or first_scored_overlap:
        raise SecondConfirmationGateError(
            "frozen roster overlaps a development or first-confirmation outcome-scored network"
        )
    if qc_only_overlap != declared_qc_only:
        raise SecondConfirmationGateError(
            "first-confirmation QC-only reuse differs from the amendment declaration"
        )

    by_domain = expected_frozen.groupby("domain").size().to_dict()
    checks = {
        domain: {
            "required": required,
            "arrived": int(by_domain.get(domain, 0)),
            "passed": bool(by_domain.get(domain, 0) >= required),
        }
        for domain, required in requirements.items()
    }
    candidate_count = len(readiness_roster)
    qualified_count = len(expected_frozen)
    candidate_pass = candidate_count >= int(protocol["candidate_floor"])
    minimum_pass = qualified_count >= int(protocol["minimum_valid_scored_networks"])
    target_pass = qualified_count >= int(protocol["target_scored_networks"][0])
    domain_pass = all(item["passed"] for item in checks.values())
    authorized = candidate_pass and minimum_pass and target_pass and domain_pass
    result = {
        "readiness_schema_version": READINESS_SCHEMA_VERSION,
        "protocol_id": protocol["protocol_id"],
        "amendment_id": amendment["amendment_id"],
        "gate_mode": "amendment_v2_hash_bound_exact_roster",
        "protocol_path": relative_path(protocol_path, root),
        "protocol_sha256": sha256_file(protocol_path),
        "amendment_path": relative_path(amendment_path, root),
        "amendment_sha256": sha256_file(amendment_path),
        "readiness_roster_path": relative_path(readiness_roster_path, root),
        "readiness_roster_sha256": sha256_file(readiness_roster_path),
        "frozen_scoring_roster_path": relative_path(frozen_roster_path, root),
        "frozen_scoring_roster_sha256": sha256_file(frozen_roster_path),
        "independence_audit": {
            "development_outcome_overlap_count": len(development_overlap),
            "development_outcome_overlap_networks": development_overlap,
            "first_confirmation_outcome_overlap_count": len(first_scored_overlap),
            "first_confirmation_outcome_overlap_networks": first_scored_overlap,
            "first_confirmation_qc_only_reuse_count": len(qc_only_overlap),
            "first_confirmation_qc_only_reuse_networks": qc_only_overlap,
            "outcome_scored_network_disjoint": not (
                development_overlap or first_scored_overlap
            ),
        },
        "candidate_networks": candidate_count,
        "candidate_floor_passed": candidate_pass,
        "qualified_networks_before_scoring": qualified_count,
        "minimum_arrival_floor_passed": minimum_pass,
        "target_60_networks_arrived": target_pass,
        "qualified_by_domain": {
            str(key): int(value) for key, value in by_domain.items()
        },
        "domain_checks": checks,
        "domain_composition_passed": domain_pass,
        "outcomes_scored_before_amendment": False,
        "scoring_authorized": bool(authorized),
        "scoring_status": "authorized_not_run"
        if authorized
        else "withheld_until_all_arrival_floors_pass",
    }
    for key, path in reference_paths.items():
        result[f"{key}_path"] = relative_path(path, root)
        result[f"{key}_sha256"] = sha256_file(path)
    return result


def validate_canonical_authorization(
    readiness: dict[str, Any],
    *,
    readiness_path: Path,
    canonical_readiness_path: Path,
    root: Path,
) -> pd.DataFrame:
    """Recompute the canonical gate and return its exact frozen roster."""

    if readiness_path.resolve() != canonical_readiness_path.resolve():
        raise SecondConfirmationGateError(
            "authorized scoring requires the repository-canonical readiness path"
        )
    if readiness.get("readiness_schema_version") != READINESS_SCHEMA_VERSION:
        raise SecondConfirmationGateError("unsupported or missing readiness schema")
    required_paths = {
        "protocol_path": "protocol_sha256",
        "amendment_path": "amendment_sha256",
        "readiness_roster_path": "readiness_roster_sha256",
        "frozen_scoring_roster_path": "frozen_scoring_roster_sha256",
        "development_outcomes_path": "development_outcomes_sha256",
        "first_confirmation_outcomes_path": "first_confirmation_outcomes_sha256",
        "first_confirmation_qc_panel_path": "first_confirmation_qc_panel_sha256",
    }
    resolved: dict[str, Path] = {}
    for path_key, digest_key in required_paths.items():
        relative = readiness.get(path_key)
        if not isinstance(relative, str):
            raise SecondConfirmationGateError(f"readiness lacks {path_key}")
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise SecondConfirmationGateError(
                f"{path_key} escapes repository root"
            ) from exc
        if not path.is_file() or sha256_file(path) != readiness.get(digest_key):
            raise SecondConfirmationGateError(f"{path_key} hash binding failed")
        resolved[path_key] = path

    recomputed = build_authorized_readiness(
        root=root,
        protocol_path=resolved["protocol_path"],
        amendment_path=resolved["amendment_path"],
        readiness_roster_path=resolved["readiness_roster_path"],
        frozen_roster_path=resolved["frozen_scoring_roster_path"],
    )
    if json.dumps(recomputed, sort_keys=True) != json.dumps(readiness, sort_keys=True):
        raise SecondConfirmationGateError(
            "canonical readiness content differs from recomputed gate"
        )
    if not recomputed["scoring_authorized"]:
        raise SecondConfirmationGateError("recomputed gate does not authorize scoring")
    return pd.read_csv(
        resolved["frozen_scoring_roster_path"], dtype={"network_id": str}
    )


__all__ = [
    "SecondConfirmationGateError",
    "attrition_gate_summary",
    "build_authorized_readiness",
    "frozen_roster_from_qc",
    "sha256_file",
    "validate_canonical_authorization",
    "validate_scored_result_gate",
]
