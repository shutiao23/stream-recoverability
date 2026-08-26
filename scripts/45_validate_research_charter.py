#!/usr/bin/env python3
"""Fail closed if the next-paper charter, freeze, or catalog drift."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.study_freeze import (
    load_study_freeze,
    study_is_confirmatory,
)
from stream_recoverability.data.network_catalog import (
    load_network_catalog,
    validate_catalog,
)


def main() -> None:
    charter = (ROOT / "docs/research_charter_v1.md").read_text(encoding="utf-8")
    for marker in (
        "人话",
        "到底要算什么",
        "怎样算过关",
        "怎样算失败",
        "现在做到哪",
    ):
        assert marker in charter, marker
    protocol_v9 = ROOT / "docs/protocol_change_v8_to_v9.md"
    assert protocol_v9.is_file(), (
        "v9 freeze requires docs/protocol_change_v8_to_v9.md; "
        "refusing to invent a protocol here"
    )
    freeze = load_study_freeze()
    assert (
        freeze.get("design_id") == "design_freeze_v9"
        or freeze.get("design_version") == "design_freeze_v9"
    ), "default study freeze must be design_freeze_v9"
    assert freeze["formal_evidence"] is False
    assert freeze["sealed_outcomes_opened"] is False
    assert freeze["headline_claim_licensed"] is False
    assert freeze["reservoir_mechanism_in_headline"] is False
    assert freeze["hard_type_labels_are_primary"] is False
    assert freeze["eventwise_best_envelope_is_primary"] is False
    assert freeze["national_dam_auc_is_recoverability_evidence"] is False
    assert study_is_confirmatory(freeze) is False
    historical = freeze["split_rule"]["historical_seen_networks"]
    assert "jinsha_upper" in historical
    assert "chattahoochee_upper_middle" in historical
    assert freeze.get("jinsha_outcomes_reusable_as_confirmation") is False
    assert freeze.get("chattahoochee_outcomes_reusable_as_confirmation") is False
    never_sealed = set(freeze["split_rule"].get("never_sealed_networks") or [])
    assert {
        "jinsha_upper",
        "chattahoochee_upper_middle",
        "delaware_river_huc20",
        "clearwater_river_huc17",
    }.issubset(never_sealed)
    not_public_daily = set(
        freeze["split_rule"].get(
            "not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public"
        )
        or []
    )
    assert {"loire_mainstem", "swiss_aar_rhine"}.issubset(not_public_daily)
    assert freeze.get("not_an_executable_design") is True
    assert freeze.get("executable") is False
    t2 = freeze["locked_success_criterion"]["t2_large_sample_primary"]
    assert float(t2["out_of_network_spearman_min"]) >= 0.60
    assert float(t2["network_bootstrap_lower_bound_min"]) >= 0.40
    ledger = (ROOT / "paper/boundary_ledger.md").read_text(encoding="utf-8")
    assert "## BL-015" in ledger
    assert "forced_donor_dominated" in ledger
    catalog = load_network_catalog()
    violations = validate_catalog(catalog)
    assert not violations, violations
    historical = [
        network
        for network in catalog["networks"]
        if network.get("historical_seen")
    ]
    assert {item["network_id"] for item in historical} == {
        "jinsha_upper",
        "chattahoochee_upper_middle",
    }
    assert all(item["split_role"] != "sealed" for item in historical)
    sealed = [network for network in catalog["networks"] if network["split_role"] == "sealed"]
    assert all(item.get("sealed_outcomes_opened") is False for item in sealed)
    assert all(item.get("temperature_record_unverified") is True for item in sealed)
    print("research charter, freeze, and catalog contracts hold")


if __name__ == "__main__":
    main()
