#!/usr/bin/env python3
"""P0-07 sealed confirmation entrypoint.

Dry-run lists never-used candidates and records hashes. Unseal scores once
against the frozen plan and refuses if seal hashes drifted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from stream_recoverability.experiments.wrr_submission_ready.run_identity import (
    preflight_current_study,
    run_fail_closed,
    sha256_file,
)

READY = ROOT / "results" / "wrr_submission_ready"
SEAL = READY / "confirmation_seal.json"


def _file_hash(path: Path) -> str:
    return sha256_file(path)


def build_seal() -> dict:
    freeze = READY / "P0_06_method_freeze.json"
    ledger = READY / "prior_access_ledger_reserved_networks.csv"
    manifest = READY / "current_data_manifest.csv"
    prior = pd.read_csv(ledger)
    candidates = prior.loc[prior["prior_access_bucket"] == "candidate_unseen"].copy()
    return {
        "freeze_sha256": _file_hash(freeze),
        "ledger_sha256": _file_hash(ledger),
        "manifest_sha256": _file_hash(manifest),
        "n_candidate_unseen_networks_in_current_reserved_join": int(candidates["network_id"].nunique()),
        "candidate_network_ids": sorted(candidates["network_id"].astype(str)),
        "note": (
            "These candidate_unseen labels are relative to the v16 evidence_use ledger. "
            "Recruitment must still verify no later descriptive/scoring use and expand "
            "beyond the eight networks if power requires it."
        ),
        "scored": False,
    }


def dry_run(directory: Path, manifest) -> list[Path]:
    seal = build_seal()
    path = directory / "confirmation_seal_candidate.json"
    path.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n")
    # Persist a repo-level seal only on dry-run when absent, so later unseal can verify.
    if not SEAL.exists():
        SEAL.write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n")
    summary = {
        "preflight": preflight_current_study(),
        "seal_path": str(path.relative_to(ROOT)),
        "repo_seal_path": str(SEAL.relative_to(ROOT)),
        "status": "dry_run_complete_not_scored",
    }
    summary_path = directory / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return [path, summary_path, SEAL]


def unseal(directory: Path, manifest) -> list[Path]:
    if not SEAL.exists():
        raise FileNotFoundError("Run --dry-run first to write confirmation_seal.json")
    sealed = json.loads(SEAL.read_text())
    current = build_seal()
    for key in ("freeze_sha256", "ledger_sha256", "manifest_sha256"):
        if sealed[key] != current[key]:
            raise RuntimeError(f"seal drift on {key}: refuse to score")
    if sealed.get("scored"):
        raise RuntimeError("confirmation already marked scored; refuse to re-score")
    # Scoring requires a recruited never-used panel larger than the residual
    # candidate_unseen join. Until that panel is ingested, fail closed.
    summary = ROOT / "results" / "wrr_submission_ready" / "confirmation_recruitment_summary.json"
    detail = ""
    if summary.is_file():
        detail = " Current audit: " + summary.read_text().strip()
    raise RuntimeError(
        "No sealed never-used confirmation panel has been ingested yet. "
        "In-repo audit found 0 never-used networks with ≥4 complete years/station "
        "(need ≥30). Recruit externally per EXTERNAL_CONFIRMATION_RECRUITMENT.md, "
        "freeze input hashes, then replace this guard with a single score against "
        "P0_06_method_freeze.json. Do not score the opened v17 reserved panel again."
        + detail
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--unseal", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.unseal:
        raise SystemExit("specify exactly one of --dry-run or --unseal")
    if args.dry_run:
        run_fail_closed("P0-07 sealed confirmation dry-run", dry_run)
        print("dry-run ok; seal at", SEAL)
        return
    run_fail_closed("P0-07 sealed confirmation unseal", unseal)


if __name__ == "__main__":
    main()
