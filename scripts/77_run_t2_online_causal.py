#!/usr/bin/env python3
"""Inventory or execute a bounded open-role v9.1 T2 online-causal slice."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_online_causal import (
    build_online_workload_manifest,
    iter_online_workload,
    run_online_items,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    discover_failure_closure_networks,
    json_safe,
    load_v91_budget,
)

DEFAULT_OUTPUT = ROOT / "results/framework/t2_online_causal_v1"


def _csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="count only (default)")
    mode.add_argument(
        "--execute",
        action="store_true",
        help="run a bounded slice; requires --max-items",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--start-ordinal", type=int, default=0)
    parser.add_argument("--roles")
    parser.add_argument("--networks")
    parser.add_argument("--models")
    parser.add_argument("--gaps")
    parser.add_argument("--information")
    parser.add_argument(
        "--artificial-only",
        action="store_true",
        help="execution filter only; the manifest still counts all frozen geometries",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    if args.start_ordinal < 0:
        raise SystemExit("--start-ordinal must be non-negative")
    if args.execute and (args.max_items is None or args.max_items < 1):
        raise SystemExit("--execute requires a positive --max-items bound")
    args.output.mkdir(parents=True, exist_ok=True)
    budget = load_v91_budget(ROOT)
    networks, inventory = discover_failure_closure_networks(ROOT)
    if not networks:
        raise SystemExit("no failure-closure open networks are available")

    manifest = build_online_workload_manifest(ROOT, networks, inventory, budget)
    manifest_path = args.output / "workload_manifest.json"
    manifest_path.write_text(
        json.dumps(json_safe(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    run = None
    if args.execute:
        gaps = _csv(args.gaps)
        items = iter_online_workload(
            ROOT,
            networks,
            budget,
            include_frozen_geometry=not args.artificial_only,
            roles=_csv(args.roles),
            network_ids=_csv(args.networks),
            models=_csv(args.models),
            gaps=None if gaps is None else [int(value) for value in gaps],
            information_conditions=_csv(args.information),
        )
        run = run_online_items(
            ROOT,
            networks,
            items,
            args.output,
            start_ordinal=args.start_ordinal,
            max_items=args.max_items,
        )

    summary = {
        "manifest_schema": "t2_v91_online_causal_preparation_v1",
        "mode": "execute" if args.execute else "dry_run",
        "workload_manifest": str(manifest_path),
        "n_networks": len(networks),
        "n_work_items": manifest["n_work_items"],
        "runner_implementation_ready": manifest["runner_implementation_ready"],
        "go_no_go": manifest["go_no_go"],
        "run": run,
        "full_workload_started": False,
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    (args.output / "preparation_run.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
