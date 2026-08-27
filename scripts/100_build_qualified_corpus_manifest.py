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
    sealed_objects = list((sealed.get("custody") or sealed).get("objects", []))
    sealed_networks = len({obj["network_id"] for obj in sealed_objects})
    open_complete = int(attrition.get("open_complete_enough", 0))
    europe_complete = int(europe.get("n_complete_enough", 0))
    sealed_qc_complete = 0
    qualified_total = open_complete + sealed_qc_complete + europe_complete
    floor = 100
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
            "europe_supplement_complete_enough": europe_complete,
        },
        "custody_metadata_only": {
            "sealed_custody_networks": sealed_networks,
            "sealed_qc_permitted_objects": int(
                attrition.get("sealed_qc_permitted_objects", 0)
            ),
            "sealed_bytes_opened_for_qc": False,
        },
        "blockers_to_floor": [
            "open_role_survival_stalled_at_67_of_103_downloaded",
            "sealed_temperature_qc_blocked_until_t7_evaluate_once",
            "europe_uk_ea_zero_complete_enough_after_15_cluster_pass",
        ],
        "passed": False,
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
