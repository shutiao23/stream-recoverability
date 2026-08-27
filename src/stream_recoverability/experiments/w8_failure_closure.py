"""W8 failure-closure: retitle to predictability, never retune.

The W7 first-layer increment versus ``donor_r2_only`` is a development
stop-loss, not confirmatory T2.  If that increment is below 0.05 the
locked action is ``retitle_to_predictability``.  Retuning the Schur
operator, Twin E, or isolation/φ is never licensed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from stream_recoverability.experiments.t2_recovery_benchmark import json_safe
from stream_recoverability.experiments.t2_w7_open_role_bd_slice import (
    GO_NO_GO,
    N_NETWORKS_MIN,
    W8_INCREMENTAL_R2_TRIGGER,
)

MANIFEST_SCHEMA = "w8_failure_closure_v1"
PURPOSE = "development_retitle_not_evidence"
ACTION_RETITLE = "retitle_to_predictability"
ACTION_KEEP = "keep_operator_title_still_not_t2"
ACTION_UNDEFINED = "increment_undefined_keep_operator_title_still_not_t2"
FORBIDDEN_ACTIONS = frozenset(
    {
        "retune_operator_and_phi",
        "retune_operator",
        "retune_twin_e",
        "retune_phi_or_isolation",
    }
)
DEFAULT_W7_SLICE = (
    Path("results")
    / "framework"
    / "t2_recovery_benchmark_v1"
    / "w7_open_role_bd_slice"
    / "w7_open_role_bd_slice_manifest.json"
)
DEVELOPMENT_TITLE = (
    "Fitting-period covariance as a predictability diagnostic for "
    "stream-temperature gap skill"
)
DEVELOPMENT_TITLE_NOT = (
    "Operator novelty over donor R²; a monitoring decision rule; confirmatory T2"
)

REQUIRED_FALSE = (
    "passed",
    "formal_evidence",
    "headline_claim_licensed",
    "confirmatory_eligible",
    "operator_retuned",
    "twin_e_retuned",
    "phi_or_isolation_retuned",
    "design_freeze_v4_retargeted",
    "catalog_98_name_huc2_downloaded",
    "historical_two_network_manuscript_retitled",
    "slice_is_confirmatory_t2",
    "sealed_outcomes_opened",
    "new_temperatures_downloaded",
)


class W8FailureClosureError(ValueError):
    """Raised when a W8 record would retune, pass, or overwrite protected work."""


def _assert_open_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise W8FailureClosureError(f"refusing a sealed path: {path}")


def w8_failure_closure_action(incremental_r2_vs_donor: float | None) -> str:
    """Map the W7 increment onto the locked W8 action. Never retune."""

    if incremental_r2_vs_donor is None:
        return ACTION_UNDEFINED
    value = float(incremental_r2_vs_donor)
    if not np.isfinite(value):
        return ACTION_UNDEFINED
    if value < W8_INCREMENTAL_R2_TRIGGER:
        return ACTION_RETITLE
    return ACTION_KEEP


def operator_or_phi_retune_licensed(
    incremental_r2_vs_donor: float | None = None,
) -> bool:
    """Retuning is never licensed, including when the increment is below 0.05."""

    del incremental_r2_vs_donor
    return False


def write_w8_failure_closure(
    *,
    output_dir: str | Path,
    w7_manifest: Mapping[str, Any],
    repo_root: str | Path | None = None,
    w7_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Write the W8 development retitle record. ``passed`` is always false."""

    output = Path(output_dir)
    _assert_open_path(output)
    if repo_root is not None:
        _assert_open_path(Path(repo_root))
    if any("sealed" in part.lower() for part in output.resolve().parts):
        raise W8FailureClosureError("W8 writer refuses sealed output")
    if "public_rivers" in output.resolve().parts:
        raise W8FailureClosureError("W8 writer refuses to overwrite public_rivers")
    if "twin_e" in output.resolve().parts:
        raise W8FailureClosureError("W8 writer refuses Twin E holdout paths")

    increment_raw = w7_manifest.get("operator_incremental_r2_vs_donor_r2_only")
    increment: float | None
    try:
        increment = None if increment_raw is None else float(increment_raw)
    except (TypeError, ValueError) as error:
        raise W8FailureClosureError("W7 increment is not numeric") from error
    if increment is not None and not np.isfinite(increment):
        increment = None
    action = w8_failure_closure_action(increment)
    if action in FORBIDDEN_ACTIONS:
        raise W8FailureClosureError("W8 action cannot be a retune")
    trigger = bool(w7_manifest.get("w8_failure_closure_trigger"))
    if increment is not None and increment < W8_INCREMENTAL_R2_TRIGGER and not trigger:
        raise W8FailureClosureError("W7 increment < 0.05 but trigger was not set")
    if action == ACTION_RETITLE and not trigger:
        raise W8FailureClosureError("retitle action requires the W7 trigger")

    n_networks = int(w7_manifest.get("n_networks") or 0)
    if bool(w7_manifest.get("operator_retuned")):
        raise W8FailureClosureError("W7 slice already retuned the operator")
    if bool(w7_manifest.get("passed")):
        raise W8FailureClosureError("W7 slice cannot be treated as passed T2")
    if bool(w7_manifest.get("slice_is_confirmatory_t2")):
        raise W8FailureClosureError("W7 slice is not confirmatory T2")

    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "manifest_schema": MANIFEST_SCHEMA,
        "purpose": PURPOSE,
        "passed": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "go_no_go": GO_NO_GO,
        "n_networks": n_networks,
        "n_networks_min_t2": N_NETWORKS_MIN,
        "network_inference_status": "withheld_n_lt_100_network_interval",
        "operator_incremental_r2_vs_donor_r2_only": increment,
        "w8_incremental_r2_threshold": W8_INCREMENTAL_R2_TRIGGER,
        "w8_failure_closure_trigger": trigger,
        "w8_failure_closure_action": action,
        "w8_failure_closure_reason": str(
            w7_manifest.get("w8_failure_closure_reason") or ""
        ),
        "operator_retuned": False,
        "twin_e_retuned": False,
        "phi_or_isolation_retuned": False,
        "operator_or_phi_retune_licensed": False,
        "design_freeze_v4_retargeted": False,
        "catalog_98_name_huc2_downloaded": False,
        "historical_two_network_manuscript_retitled": False,
        "slice_is_confirmatory_t2": False,
        "sealed_outcomes_opened": False,
        "new_temperatures_downloaded": False,
        "broader_w7_may_revise_increment": True,
        "broader_w7_may_not_retune": True,
        "development_title": DEVELOPMENT_TITLE,
        "development_title_not": DEVELOPMENT_TITLE_NOT,
        "w7_manifest_path": (
            "" if w7_manifest_path is None else str(Path(w7_manifest_path))
        ),
        "w7_n_networks": n_networks,
        "w7_purpose": str(w7_manifest.get("purpose") or ""),
        "what_this_is": (
            "W8 development failure-closure record. Operator incremental R² "
            "versus donor_r2_only is below 0.05 on the W7 development slice, "
            "so the next-paper headline is predictability rather than operator "
            "novelty. Retune is forbidden."
        ),
        "what_this_is_not": (
            "Not confirmatory T2. Not a license to retune the operator, Twin E, "
            "or φ. Not a retitle of the historical two-network manuscript. "
            "Not a claim that T3/T4/T5/T7 passed. Broader W7 may revise the "
            "increment; it may not retune."
        ),
    }
    for key in REQUIRED_FALSE:
        if manifest[key] is not False:
            raise W8FailureClosureError(f"W8 writer cannot set {key} true")
    if manifest["w8_failure_closure_action"] in FORBIDDEN_ACTIONS:
        raise W8FailureClosureError("W8 writer refused a retune action")
    if n_networks >= N_NETWORKS_MIN and manifest["network_inference_status"] == "tested":
        raise W8FailureClosureError("W8 cannot emit tested inference")

    payload = json_safe(manifest)
    (output / "w8_failure_closure_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def write_w8_failure_closure_from_w7_path(
    *,
    repo_root: str | Path,
    output_dir: str | Path,
    w7_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load the committed W7 slice and write the W8 record."""

    repo = Path(repo_root).resolve()
    slice_path = (
        Path(w7_manifest_path).resolve()
        if w7_manifest_path is not None
        else (repo / DEFAULT_W7_SLICE).resolve()
    )
    _assert_open_path(repo)
    _assert_open_path(slice_path)
    payload = json.loads(slice_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise W8FailureClosureError("W7 slice manifest is not a mapping")
    return write_w8_failure_closure(
        output_dir=output_dir,
        w7_manifest=payload,
        repo_root=repo,
        w7_manifest_path=slice_path,
    )


__all__ = [
    "ACTION_KEEP",
    "ACTION_RETITLE",
    "ACTION_UNDEFINED",
    "DEVELOPMENT_TITLE",
    "FORBIDDEN_ACTIONS",
    "MANIFEST_SCHEMA",
    "PURPOSE",
    "W8FailureClosureError",
    "operator_or_phi_retune_licensed",
    "w8_failure_closure_action",
    "write_w8_failure_closure",
    "write_w8_failure_closure_from_w7_path",
]
