#!/usr/bin/env python3
"""Dry-run or execute a bounded slice of the v9.1 open-role T2 workload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_recovery_benchmark import (
    build_workload_manifest,
    discover_failure_closure_networks,
    iter_work_items,
    json_safe,
    load_v91_budget,
    lock_tier2_sample,
    run_items,
    tier2_timing_exception_ledger,
)

DEFAULT_OUTPUT = ROOT / "results/framework/t2_recovery_benchmark_v1"


def _csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="inventory and count the full frozen artificial grid (default)",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="execute a bounded slice; requires --max-items",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-ordinal", type=int, default=0)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--roles", help="comma-separated development,validation")
    parser.add_argument("--networks", help="comma-separated HUC8 network ids")
    parser.add_argument("--models", help="comma-separated frozen Tier-1 model names")
    parser.add_argument("--gaps", help="comma-separated frozen artificial gaps")
    parser.add_argument("--information", help="comma-separated frozen conditions")
    parser.add_argument(
        "--skip-tier2-lock",
        action="store_true",
        help="do not materialize the metadata-only Tier-2 sample lock",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    execute = bool(args.execute)
    if execute and (args.max_items is None or args.max_items < 1):
        raise SystemExit("--execute requires a positive --max-items bound")
    if args.start_ordinal < 0:
        raise SystemExit("--start-ordinal must be non-negative")
    args.output.mkdir(parents=True, exist_ok=True)
    budget = load_v91_budget(ROOT)
    networks, inventory = discover_failure_closure_networks(ROOT)
    if not networks:
        raise SystemExit("no overlap-qualified open-role networks are available")
    manifest = build_workload_manifest(ROOT, networks, inventory, budget)
    manifest_path = args.output / "workload_manifest.json"
    manifest_path.write_text(
        json.dumps(json_safe(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    legacy_last_run = args.output / "last_run.json"
    if legacy_last_run.is_file():
        existing_last_run = json.loads(legacy_last_run.read_text(encoding="utf-8"))
        if existing_last_run.get("runner_contract_version") != manifest[
            "runner_contract_version"
        ]:
            legacy_payload = existing_last_run.get(
                "legacy_payload", existing_last_run
            )
            legacy_last_run.write_text(
                json.dumps(
                    {
                        "status": "legacy_obsolete_do_not_resume",
                        "active_checkpoint_namespace": "checkpoints_v3",
                        "superseded_by": "preparation_run.json",
                        "legacy_payload": legacy_payload,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
    tier2_path = None
    tier2_ledger_path = None
    if not args.skip_tier2_lock:
        tier2 = lock_tier2_sample(ROOT)
        tier2_path = args.output / "tier2_sample_lock.json"
        if tier2_path.is_file():
            existing = json.loads(tier2_path.read_text(encoding="utf-8"))
            if existing.get("sample_sha256") != tier2.get("sample_sha256"):
                raise RuntimeError("refusing to overwrite a different Tier-2 sample lock")
        tier2_path.write_text(
            json.dumps(tier2, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        tier2_ledger = tier2_timing_exception_ledger(tier2)
        tier2_ledger_path = args.output / "tier2_timing_exception_ledger.json"
        tier2_ledger_path.write_text(
            json.dumps(tier2_ledger, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    run_summary = None
    if execute:
        gaps = _csv(args.gaps)
        items = iter_work_items(
            ROOT,
            networks,
            budget,
            roles=_csv(args.roles),
            network_ids=_csv(args.networks),
            models=_csv(args.models),
            gaps=None if gaps is None else [int(value) for value in gaps],
            information_conditions=_csv(args.information),
        )
        run_summary = run_items(
            ROOT,
            networks,
            items,
            args.output,
            start_ordinal=args.start_ordinal,
            max_items=args.max_items,
        )
    preparation = {
        "runner_contract_version": manifest["runner_contract_version"],
        "mode": "execute" if execute else "dry_run",
        "workload_manifest": str(manifest_path),
        "tier2_sample_lock": None if tier2_path is None else str(tier2_path),
        "tier2_timing_exception_ledger": (
            None if tier2_ledger_path is None else str(tier2_ledger_path)
        ),
        "n_networks": len(networks),
        "n_work_items": manifest["tier_1"]["n_work_items"],
        "workload_categories": {
            key: manifest["tier_1"][key]
            for key in (
                "n_executable",
                "n_reference",
                "n_not_applicable",
                "n_data_ineligible",
                "n_external_dependency",
            )
        },
        "go_no_go": manifest["go_no_go"],
        "run": run_summary,
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    (args.output / "preparation_run.json").write_text(
        json.dumps(preparation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(preparation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
