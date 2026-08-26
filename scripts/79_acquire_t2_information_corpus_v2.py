#!/usr/bin/env python3
"""Plan or run legacy-NWIS v2 M/H acquisition without touching OGC v1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    DEFAULT_HTTP_429_COOLDOWN_SECONDS,
    DEFAULT_MAX_TRANSIENT_RETRIES,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    DEFAULT_RETRY_BACKOFF_INITIAL_SECONDS,
    DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    run_v2_corpus_acquisition,
)

DEFAULT_EXECUTE_OUTPUT = (
    ROOT
    / "data_versions/global_network_corpus_v1/open_role_auxiliary_legacy_v2"
    / "failure_closure6"
)
DEFAULT_DRY_RUN_OUTPUT = (
    ROOT
    / "results/framework/t2_information_adapters_v2"
    / "corpus_acquisition_dry_run"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--network-id", action="append", default=[])
    selection.add_argument("--max-networks", type=int)
    selection.add_argument("--all", action="store_true", dest="all_networks")
    parser.add_argument("--acknowledge-network-count", type=int)
    parser.add_argument("--acknowledge-all-network-count", type=int)
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--max-transient-retries",
        type=int,
        default=DEFAULT_MAX_TRANSIENT_RETRIES,
    )
    parser.add_argument(
        "--retry-backoff-initial-seconds",
        type=float,
        default=DEFAULT_RETRY_BACKOFF_INITIAL_SECONDS,
    )
    parser.add_argument(
        "--retry-backoff-max-seconds",
        type=float,
        default=DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    )
    parser.add_argument(
        "--http-429-cooldown-seconds",
        type=float,
        default=DEFAULT_HTTP_429_COOLDOWN_SECONDS,
    )
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    parser.set_defaults(resume=True)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or (
        DEFAULT_EXECUTE_OUTPUT if args.execute else DEFAULT_DRY_RUN_OUTPUT
    )
    manifest = run_v2_corpus_acquisition(
        ROOT,
        output,
        execute=args.execute,
        network_ids=args.network_id,
        max_networks=args.max_networks,
        all_networks=args.all_networks,
        acknowledged_network_count=args.acknowledge_network_count,
        acknowledge_all_network_count=args.acknowledge_all_network_count,
        resume=args.resume,
        request_interval_seconds=args.request_interval_seconds,
        max_transient_retries=args.max_transient_retries,
        retry_backoff_initial_seconds=args.retry_backoff_initial_seconds,
        retry_backoff_max_seconds=args.retry_backoff_max_seconds,
        http_429_cooldown_seconds=args.http_429_cooldown_seconds,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
