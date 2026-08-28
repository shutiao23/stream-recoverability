#!/usr/bin/env python3
"""Consolidate open-role, sealed-custody, and Europe counts into one manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CORPUS = ROOT / "data_versions/global_network_corpus_v1"
OUTPUT = CORPUS / "qualified_corpus_v1"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_qualified_corpus(repo_root: Path = ROOT) -> dict:
    attrition = _read_json(CORPUS / "global_attrition_v1/global_attrition_summary.json")
    europe = _read_json(
        repo_root / "results/framework/public_rivers_europe/uk_ea_spatial_daily_manifest.json"
    )
    sealed = _read_json(CORPUS / "w4_custody/sealed_custody_manifest.json")
    sealed_qc = _read_json(
        repo_root
        / "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/sealed_qc_manifest.json"
    )
    sealed_objects = list((sealed.get("custody") or sealed).get("objects", []))
    sealed_networks = len({obj["network_id"] for obj in sealed_objects})
    open_complete = int(attrition.get("open_complete_enough", 0))
    europe_complete = int(europe.get("n_complete_enough", 0))
    # FOEN networks were prospectively locked before any value query and were
    # evaluated under the same one-shot QC ceremony.  Once they pass that QC,
    # they are independent qualified networks and must be included in corpus
    # accounting.  The provider-specific HUC8 count is retained below for
    # auditability; it is not the all-provider total.
    sealed_qc_complete = int(sealed_qc.get("n_eligible_networks", 0))
    sealed_huc8_complete = int(sealed_qc.get("n_huc8_eligible_networks", 0))
    sealed_foen_complete = int(sealed_qc.get("n_foen_eligible_networks", 0))
    qualified_total = open_complete + sealed_qc_complete + europe_complete
    floor = 100
    sealed_bytes_opened = sealed_qc.get("sealed_temperature_records_read") is True
    blockers: list[str] = []
    if open_complete < 100:
        blockers.append(f"open_role_survival_stalled_at_{open_complete}_of_103_downloaded")
    if not sealed_bytes_opened:
        blockers.append("sealed_temperature_qc_blocked_until_t7_evaluate_once")
    if europe_complete == 0:
        blockers.append("europe_uk_ea_zero_complete_enough_after_15_cluster_pass")
    if qualified_total < floor:
        blockers.append(f"corpus_floor_gap_{floor - qualified_total}")
    return {
        "manifest_schema": "qualified_network_corpus_v1",
        "formal_evidence": False,
        "purpose": "corpus_accounting_not_confirmatory",
        "network_ci_floor": floor,
        "network_ci_floor_met": qualified_total >= floor,
        "qualified_total": qualified_total,
        "corpus_floor_gap": max(0, floor - qualified_total),
        "components": {
            "open_role_complete_enough_failure_closure6": open_complete,
            "sealed_qc_complete_enough": sealed_qc_complete,
            "sealed_qc_huc8_complete_enough": sealed_huc8_complete,
            "sealed_qc_foen_complete_enough": sealed_foen_complete,
            "europe_supplement_complete_enough": europe_complete,
        },
        "custody_metadata_only": {
            "sealed_custody_networks": sealed_networks,
            "sealed_qc_permitted_objects": int(
                sealed_qc.get("n_sealed_objects_read")
                or attrition.get("sealed_qc_permitted_objects", 0)
            ),
            "sealed_bytes_opened_for_qc": sealed_bytes_opened,
        },
        "sealed_qc_source": (
            "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/sealed_qc_manifest.json"
            if sealed_qc
            else None
        ),
        "blockers_to_floor": blockers,
        "passed": qualified_total >= floor,
        "attrition_source": "data_versions/global_network_corpus_v1/global_attrition_v1/global_attrition_summary.json",
    }


def main() -> None:
    manifest = build_qualified_corpus()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "qualified_corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
