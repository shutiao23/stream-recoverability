#!/usr/bin/env python3
"""P0-07: freeze the new confirmation protocol with method hashes. Do not score."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
DRAFT = READY / "P0_07_NEW_CONFIRMATION_PROTOCOL_DRAFT.md"
OUT = READY / "P0_07_NEW_CONFIRMATION_SEAL.json"
SCOUT = READY / "amendments" / "p0_07_new_confirmation_scout" / "summary.json"

FILES = [
    "src/stream_recoverability/experiments/v17_fitness/screen.py",
    "src/stream_recoverability/experiments/v17_fitness/frontier.py",
    "src/stream_recoverability/experiments/v17_fitness/estimators.py",
    "src/stream_recoverability/experiments/v17_fitness/cases.py",
    "results/v17_fitness/step9_freeze/certificate.joblib",
    "results/wrr_submission_ready/P0_06_method_freeze.json",
    "constraints-freeze-certificate.txt",
    "results/wrr_submission_ready/P0_07_NEW_CONFIRMATION_PROTOCOL_DRAFT.md",
]


def sha256(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {"path": str(path.relative_to(ROOT)), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def main() -> int:
    scout = json.loads(SCOUT.read_text()) if SCOUT.is_file() else {}
    hashes = []
    missing = []
    for rel in FILES:
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
            continue
        hashes.append(sha256(path))
    leftover = {
        "opened_usgs_ingest_networks_not_in_sealed_score": "leftover of the same recruitment wave; not a first confirmation",
        "opened_nve_secondary": "secondary stratum; cannot rescue a primary quality gate",
        "scout_unused_rows": scout.get("n_not_already_used"),
        "floors_met": False,
        "reason_floors_unmet": (
            "Scout unused rows are mostly metadata/no_temperature. "
            "Leftover USGS/NVE ingest belong to already-opened recruitment. "
            "New independent downloads required before score."
        ),
    }
    payload = {
        "protocol_id": "P0-07-new-independent-confirmation",
        "sealed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scored": False,
        "score_forbidden_until": [
            "P0-02/P0-03 method freeze remains the hashed files below",
            "new primary-panel networks meet ≥30 nets / ≥3 providers / ≥3 contexts",
            "prior-access ledger covers CSV/Parquet/JSON and station_id/site_id",
            "QA complete years have no −999999 / unconfirmed units",
            "reconstructability contract: admitted ⇒ finite hottest-30",
        ],
        "predeclared_success_rule": {
            "retention": 0.70,
            "denominator": "full candidate station-year × scenario set",
            "tolerance_C": 0.5,
            "delta_points_max": -1.0,
            "ci_upper_bound_must_be_below_zero": True,
            "min_providers_same_direction": 2,
            "quality_checked_subset_must_agree_on_same_panel_role": True,
            "reconstruction_failure_counts_as_failure": True,
        },
        "design_floors": {
            "min_networks": 30,
            "min_providers": 3,
            "min_contexts": 3,
            "min_stations_per_network": 2,
            "min_complete_years_per_station": 4,
        },
        "floors_currently_met": False,
        "recruitment": leftover,
        "method_hashes": hashes,
        "missing_hash_targets": missing,
        "draft": str(DRAFT.relative_to(ROOT)),
        "claim_status_if_unscored": "[pending — 探索期数据，不可写入结论]",
        "do_not_overwrite": [
            "results/wrr_submission_ready/p0_07_sealed_confirmation/",
            "results/wrr_submission_ready/p0_07b_multi_agency_transport/",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"wrote": str(OUT.relative_to(ROOT)), "scored": False, "n_hashes": len(hashes)}, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
