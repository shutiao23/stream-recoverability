#!/usr/bin/env python3
"""Plan or serially acquire open-target NLDI UM/DM metadata for T5."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.t5_nldi_acquisition import (
    audit_plan_cache,
    build_open_target_plan,
    execute_missing_requests,
    file_sha256,
)

PREDICTORS = (
    ROOT
    / "results/framework/t2_recovery_benchmark_v1/train_only_predictors/"
    "train_only_predictors.csv"
)
NLDI_RELATIVE = Path("results/framework/public_catalog/nldi_cache")
NLDI_CACHE = ROOT / NLDI_RELATIVE
OUTPUT = ROOT / "results/framework/t5_nldi_acquisition_v1"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--max-new-requests", type=int, default=0)
    group.add_argument("--all", action="store_true")
    parser.add_argument("--acknowledge-request-count", type=int)
    parser.add_argument("--request-interval-seconds", type=float, default=0.3)
    return parser.parse_args()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def main() -> None:
    args = _arguments()
    existing_log_path = OUTPUT / "request_log.csv"
    history = (
        pd.read_csv(existing_log_path, dtype={"target_station_id": str})
        if existing_log_path.is_file()
        else pd.DataFrame()
    )
    predictors = pd.read_csv(
        PREDICTORS, dtype={"network_id": str, "station_id": str}
    )
    plan = build_open_target_plan(predictors, cache_dir=NLDI_RELATIVE)
    before = audit_plan_cache(plan, root=ROOT)
    counts_before = before["status"].value_counts().sort_index().astype(int).to_dict()
    missing_before = int(counts_before.get("missing", 0))
    if args.execute:
        if args.request_interval_seconds < 0.25:
            raise SystemExit("request interval must be at least 0.25 seconds")
        if args.all:
            if args.acknowledge_request_count != missing_before:
                raise SystemExit(
                    "--all requires --acknowledge-request-count equal to the current "
                    f"missing request count ({missing_before})"
                )
            limit = missing_before
        else:
            limit = int(args.max_new_requests)
            if limit < 1 or limit > 10:
                raise SystemExit(
                    "bounded execution requires --max-new-requests between 1 and 10; "
                    "use --all with the exact acknowledgement for the full serial run"
                )
        run_request_log = execute_missing_requests(
            plan,
            cache_dir=NLDI_CACHE,
            max_new_requests=limit,
            request_interval_seconds=float(args.request_interval_seconds),
            plan_root=ROOT,
        )
        mode = "full_serial_execution" if args.all else "bounded_serial_smoke"
    else:
        if args.all or args.max_new_requests or args.acknowledge_request_count:
            raise SystemExit("execution options require --execute")
        run_request_log = pd.DataFrame(
            columns=[
                "request_ordinal",
                "target_station_id",
                "direction",
                "status",
                "response_sha256",
            ]
        )
        run_request_log.attrs.update(
            {
                "halted_early": False,
                "halt_reason": None,
                "n_selected_requests": 0,
                "n_selected_requests_remaining_after_halt": 0,
            }
        )
        mode = "dry_run"
    execution_state = dict(run_request_log.attrs)
    request_log = pd.concat([history, run_request_log], ignore_index=True, sort=False)
    if not request_log.empty:
        request_log = (
            request_log.sort_values("request_ordinal", kind="mergesort")
            .drop_duplicates("request_ordinal", keep="last")
            .reset_index(drop=True)
        )
    after = audit_plan_cache(plan, root=ROOT)
    counts_after = after["status"].value_counts().sort_index().astype(int).to_dict()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    plan_path = OUTPUT / "acquisition_plan.csv"
    audit_path = OUTPUT / "cache_audit.csv"
    log_path = OUTPUT / "request_log.csv"
    _write_csv(plan, plan_path)
    _write_csv(after, audit_path)
    _write_csv(request_log, log_path)
    manifest = {
        "schema_version": "t5_v9_1_open_target_nldi_acquisition_v1",
        "purpose": "open_metadata_acquisition_not_t5_evidence",
        "mode": mode,
        "formal_evidence": False,
        "passed": False,
        "sealed_outcomes_opened": False,
        "t2_outcomes_read": False,
        "roles": ["development", "validation"],
        "n_targets": int(plan["target_station_id"].nunique()),
        "n_planned_requests": len(plan),
        "n_requests_attempted_this_run": len(run_request_log),
        "n_requests_selected_this_run": int(
            execution_state.get("n_selected_requests", 0)
        ),
        "n_requests_logged_total": len(request_log),
        "halted_early": bool(execution_state.get("halted_early", False)),
        "halt_reason": execution_state.get("halt_reason"),
        "n_selected_requests_remaining_after_halt": int(
            execution_state.get("n_selected_requests_remaining_after_halt", 0)
        ),
        "n_requests_remaining_total": int(counts_after.get("missing", 0)),
        "cache_counts_before": counts_before,
        "cache_counts_after": counts_after,
        "complete": bool(counts_after.get("complete", 0) == len(plan)),
        "serial_execution": True,
        "request_interval_seconds": float(args.request_interval_seconds),
        "resume_rule": "valid_existing_cache_is_never_requested_again",
        "recovery_source_of_truth": (
            "atomic_per_response_cache_then_full_cache_audit_on_every_resume"
        ),
        "request_log_checkpoint": (
            "cumulative_log_is_atomically_rewritten_at_run_finalization_not_per_request"
        ),
        "invalid_existing_cache_rule": "fail_closed_and_do_not_overwrite",
        "new_invalid_response_rule": "quarantine_bytes_and_leave_request_resumable",
        "input_identity": {
            "path": PREDICTORS.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(PREDICTORS),
        },
        "artifacts": {
            "acquisition_plan": {
                "path": plan_path.relative_to(OUTPUT).as_posix(),
                "sha256": file_sha256(plan_path),
            },
            "cache_audit": {
                "path": audit_path.relative_to(OUTPUT).as_posix(),
                "sha256": file_sha256(audit_path),
            },
            "request_log": {
                "path": log_path.relative_to(OUTPUT).as_posix(),
                "sha256": file_sha256(log_path),
            },
        },
    }
    manifest_path = OUTPUT / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
