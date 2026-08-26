"""Load and validate the next-paper recoverability study freeze."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STUDY_FREEZE = REPOSITORY_ROOT / "configs/design_freeze_v9.yaml"
LEGACY_STUDY_FREEZE_V1 = REPOSITORY_ROOT / "configs/recoverability_study_freeze_v1.yaml"
REQUIRED_KEYS = (
    "design_id",
    "status",
    "core_question",
    "primary_estimand",
    "proposed_operator",
    "split_rule",
    "provisional_success_criterion",
    "falsifiers",
    "failure_closure",
    "sealed_outcomes_opened",
    "formal_evidence",
    "headline_claim_licensed",
    "reservoir_mechanism_in_headline",
)


def load_study_freeze(path: str | Path = DEFAULT_STUDY_FREEZE) -> dict[str, Any]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("study freeze must be a mapping")
    missing = [key for key in REQUIRED_KEYS if key not in document]
    if missing:
        raise ValueError(f"study freeze missing {missing}")
    if document.get("formal_evidence") is True:
        raise ValueError("this freeze must not claim formal evidence yet")
    if document.get("sealed_outcomes_opened") is True:
        raise ValueError("sealed outcomes are marked opened; refuse to treat as freeze")
    if document.get("headline_claim_licensed") is True:
        raise ValueError("headline claim is not licensed by the charter")
    if document.get("reservoir_mechanism_in_headline") is True:
        raise ValueError("reservoir mechanism is not a licensed headline")
    if document.get("design_id") == "design_freeze_v9" or document.get(
        "design_version"
    ) == "design_freeze_v9":
        locked = document.get("locked_success_criterion")
        if not isinstance(locked, dict):
            raise ValueError("design_freeze_v9 requires locked_success_criterion")
        t2 = locked.get("t2_large_sample_primary")
        if not isinstance(t2, dict):
            raise ValueError("design_freeze_v9 requires t2_large_sample_primary")
        if float(t2.get("out_of_network_spearman_min", 0)) < 0.60:
            raise ValueError("v9 Spearman floor may not be lowered below 0.60")
        if float(t2.get("network_bootstrap_lower_bound_min", 0)) < 0.40:
            raise ValueError("v9 must keep the 0.40 CI floor; do not drop it after the pilot miss")
        never_sealed = document.get("split_rule", {}).get("never_sealed_networks") or []
        required_burned = {
            "jinsha_upper",
            "chattahoochee_upper_middle",
            "delaware_river_huc20",
            "willamette_river_huc17",
            "suwannee_river_huc31",
            "yellowstone_river_huc10",
            "rio_grande_huc13",
            "madison_river_huc10",
            "cahaba_river_huc31",
            "mckenzie_river_huc17",
            "mahoning_river_huc50",
            "roanoke_river_huc30",
            "santa_fe_river_huc31",
            "clearwater_river_huc17",
        }
        missing_burned = sorted(required_burned.difference(never_sealed))
        if missing_burned:
            raise ValueError(f"v9 never_sealed_networks missing {missing_burned}")
    return document


def study_is_confirmatory(document: dict[str, Any] | None = None) -> bool:
    freeze = document if document is not None else load_study_freeze()
    return bool(
        freeze.get("formal_evidence")
        and freeze.get("sealed_outcomes_opened")
        and freeze.get("headline_claim_licensed")
    )


__all__ = [
    "DEFAULT_STUDY_FREEZE",
    "LEGACY_STUDY_FREEZE_V1",
    "load_study_freeze",
    "study_is_confirmatory",
]
