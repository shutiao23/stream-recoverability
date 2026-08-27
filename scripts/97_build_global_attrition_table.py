#!/usr/bin/env python3
"""Consolidate catalog-v3 QC manifests into a paper-ready attrition table."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CORPUS = ROOT / "data_versions/global_network_corpus_v1"
OUTPUT = CORPUS / "global_attrition_v1"


def _read_qc(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_attrition(repo_root: Path = ROOT) -> dict:
    corpus = repo_root / "data_versions/global_network_corpus_v1"
    feasibility = repo_root / "docs/network_catalog_v3_feasibility.md"
    dev_qc = _read_qc(corpus / "open_role_qc/failure_closure6/development/qc_manifest.json")
    val_qc = _read_qc(corpus / "open_role_qc/failure_closure6/validation/qc_manifest.json")
    pilot = _read_qc(corpus / "w3_development_pilot/pilot_manifest.json")
    europe = _read_qc(
        repo_root / "results/framework/public_rivers_europe/uk_ea_spatial_daily_manifest.json"
    )
    sealed = _read_qc(corpus / "w4_custody/sealed_custody_manifest.json")
    sealed_objects = list((sealed.get("custody") or sealed).get("objects", []))
    sealed_networks = len({obj["network_id"] for obj in sealed_objects})
    sealed_qc_permitted = sum(1 for obj in sealed_objects if obj.get("qc_permitted"))
    catalog_candidates = 166
    if feasibility.is_file():
        for line in feasibility.read_text(encoding="utf-8").splitlines():
            if "official_huc_prefix):" in line and "**166**" in line:
                catalog_candidates = 166
                break
    open_selected = int(dev_qc.get("n_networks_selected", 0)) + int(
        val_qc.get("n_networks_selected", 0)
    )
    open_complete = int(dev_qc.get("n_networks_complete_enough", 0)) + int(
        val_qc.get("n_networks_complete_enough", 0)
    )
    rows = [
        {
            "stage": "catalog_span_huc8_candidates",
            "n_networks": catalog_candidates,
            "note": "station-year inventory; not post-download QC",
        },
        {
            "stage": "split_pool_excluding_never_sealed",
            "n_networks": 147,
            "note": "locked 50/20/30 before download",
        },
        {
            "stage": "open_role_downloaded",
            "n_networks": open_selected,
            "note": "development + validation custody",
        },
        {
            "stage": "open_role_complete_enough_failure_closure6",
            "n_networks": open_complete,
            "note": "6-year qualified years after ingest QC",
        },
        {
            "stage": "europe_uk_ea_spatial_downloaded",
            "n_networks": int(europe.get("n_clusters_downloaded", 0)),
            "note": "W6 UK EA spatial clusters; not T8 unless complete_enough",
        },
        {
            "stage": "europe_uk_ea_complete_enough",
            "n_networks": int(europe.get("n_complete_enough", 0)),
            "note": "6-year overlap QC on Europe supplement",
        },
        {
            "stage": "sealed_custody_networks",
            "n_networks": sealed_networks,
            "note": "write-only vault; qc_permitted=0 until confirmatory opening",
        },
        {
            "stage": "sealed_qc_permitted_objects",
            "n_networks": sealed_qc_permitted,
            "note": "temperature bytes not opened for open QC",
        },
        {
            "stage": "w3_pilot_complete_enough",
            "n_networks": int(pilot.get("n_networks_complete_enough", 0)),
            "note": "20-network development pilot",
        },
        {
            "stage": "t2_workload_eligible_overlap",
            "n_networks": 67,
            "note": "overlap-qualified for v4 workload manifest",
        },
        {
            "stage": "network_ci_floor",
            "n_networks": 100,
            "note": "required for network-level interval; not yet met",
        },
        {
            "stage": "target_150",
            "n_networks": 150,
            "note": "requires Europe and/or further USGS survival",
        },
    ]
    frame = pd.DataFrame(rows)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT / "global_attrition.csv", index=False)
    manifest = {
        "manifest_schema": "catalog_v3_global_attrition_v1",
        "formal_evidence": False,
        "catalog_candidates": catalog_candidates,
        "open_selected": open_selected,
        "open_complete_enough": open_complete,
        "network_ci_floor_met": open_complete >= 100,
        "target_150_met": open_complete >= 150,
        "europe_complete_enough": int(europe.get("n_complete_enough", 0)),
        "sealed_custody_networks": sealed_networks,
        "sealed_qc_permitted_objects": sealed_qc_permitted,
        "corpus_floor_gap": max(0, 100 - open_complete),
        "europe_supplement_required": bool(pilot.get("europe_supplement_required", True)),
        "relaxation_applied": bool(dev_qc.get("relaxation_applied", False)),
        "qualified_years_min": dev_qc.get("qualified_years_min", 8),
        "rows": rows,
        "purpose": "attrition_accounting_not_confirmatory",
    }
    (OUTPUT / "global_attrition_summary.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    manifest = build_attrition()
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
