#!/usr/bin/env python3
"""Audit event-episode overlap and matching from the frozen M7b catalog.

This script does not evaluate models.  Pre-event T/F/Ta SMDs are reported only
when those columns exist; the frozen catalog currently has none.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.event_matching_audit import (
    load_event_audit_json,
    load_event_catalog_for_audit,
    write_event_matching_audit,
)
from stream_recoverability.experiments.contracts import file_sha256


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "event_episode_catalog.csv",
    )
    parser.add_argument(
        "--audit-json",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "event_episode_catalog.audit.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "audits",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    catalog = load_event_catalog_for_audit(args.catalog)
    audit_json = load_event_audit_json(args.audit_json)
    audit = write_event_matching_audit(
        catalog,
        args.output_dir,
        audit_json=audit_json,
        catalog_path=args.catalog,
    )
    payload = {
        **audit.summary,
        "catalog_path": str(args.catalog),
        "catalog_sha256": file_sha256(args.catalog),
        "audit_json_path": str(args.audit_json),
        "output_dir": str(args.output_dir),
        "artifacts": sorted(audit.artifact_frames()),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
