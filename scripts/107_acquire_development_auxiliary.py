#!/usr/bin/env python3
"""Download plain M/H data for current open development and validation networks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.development_auxiliary import (
    discover_networks,
    run_acquisition,
)

DEFAULT_OUTPUT = (
    ROOT
    / "data_versions/global_network_corpus_v1/development_auxiliary/failure_closure6"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-id", action="append", default=[])
    parser.add_argument(
        "--role",
        action="append",
        choices=("development", "validation"),
        default=[],
    )
    parser.add_argument("--max-networks", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    roles = tuple(args.role) or ("development", "validation")
    if args.plan_only:
        networks = [
            network
            for network in discover_networks(ROOT)
            if network.role in roles
            and (not args.network_id or network.network_id in set(args.network_id))
        ]
        if args.max_networks is not None:
            networks = networks[: args.max_networks]
        result = {
            "n_networks": len(networks),
            "n_sites": sum(len(network.sites) for network in networks),
            "n_requests": sum(len(network.sites) + 1 for network in networks),
            "roles": roles,
            "output_root": str(args.output_root),
        }
    else:
        result = run_acquisition(
            ROOT,
            args.output_root,
            network_ids=args.network_id,
            roles=roles,
            max_networks=args.max_networks,
            workers=args.workers,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
