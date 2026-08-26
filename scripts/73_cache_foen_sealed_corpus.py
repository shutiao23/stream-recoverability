#!/usr/bin/env python3
"""Stream locked FOEN sealed responses into write-only byte custody.

Dry-run is the default and never constructs or opens a provider request.
Execution requires explicit sealed/full-corpus acknowledgements and a commit
whose custody implementation and lock files byte-match the working tree.
Provider response bodies are never JSON-decoded by this runner.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.foen_sealed_corpus import (
    FOEN_ENDPOINT,
    FoenCustodyError,
    FoenSealedCorpusGate,
    FoenYearRequest,
    LockedFoenCatalog,
    registry_manifest,
)

DEFAULT_RUN_DIR = ROOT / "data_versions/global_network_corpus_v1/w6_foen_custody_v2"
SEALED_ACK = "foen-sealed-opaque-bytes-no-json"
FULL_CORPUS_ACK = "foen-all-ten-sealed-networks-authorized"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
IMPLEMENTATION_COMMIT_PATHS = (
    ".gitignore",
    "configs/foen_daily_value_query_v1.graphql",
    "configs/foen_daily_value_query_v2.graphql",
    "configs/foen_prospective_catalog_v1.yaml",
    "configs/foen_prospective_split_v2.yaml",
    "configs/foen_prospective_split_v1.yaml",
    "docs/foen_v2_retry_checklist.md",
    "docs/protocol_deviation_foen_failed_pilot_v1_to_v2.md",
    "docs/protocol_condition_foen_public_daily_v9_1.md",
    "results/framework/public_catalog/foen_prospective_split_v1.csv",
    "results/framework/public_catalog/foen_graphql_schema_audit_v2.json",
    "scripts/73_cache_foen_sealed_corpus.py",
    "src/stream_recoverability/governance.py",
    "src/stream_recoverability/data/foen_sealed_corpus.py",
    "tests/test_foen_sealed_corpus.py",
)


def verify_implementation_commit(commit: str) -> str:
    """Require the executable custody path to byte-match one real commit."""

    if not _COMMIT.fullmatch(str(commit)):
        raise ValueError("implementation commit must be a full 40-character SHA")
    resolved = subprocess.check_output(
        ["git", "rev-parse", f"{commit}^{{commit}}"], cwd=ROOT, text=True
    ).strip()
    if resolved != commit:
        raise ValueError("implementation commit did not resolve exactly")
    for relative in IMPLEMENTATION_COMMIT_PATHS:
        current = (ROOT / relative).read_bytes()
        try:
            committed = subprocess.check_output(
                ["git", "show", f"{commit}:{relative}"], cwd=ROOT
            )
        except subprocess.CalledProcessError as error:
            raise ValueError(f"implementation commit lacks {relative}") from error
        if committed != current:
            raise ValueError(
                f"working tree differs from implementation commit: {relative}"
            )
    return resolved


def _response_chunks(response: Any, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    while True:
        chunk = response.read(chunk_size)
        if not chunk:
            return
        yield chunk


def _graphql_body(catalog: LockedFoenCatalog, request: FoenYearRequest) -> bytes:
    return json.dumps(
        {
            "query": catalog.query_template,
            "variables": {
                "station": request.site_id,
                "from": request.start,
                "to": request.end_exclusive,
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _provider_request(catalog: LockedFoenCatalog, request: FoenYearRequest) -> Any:
    return urllib.request.Request(
        FOEN_ENDPOINT,
        data=_graphql_body(catalog, request),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "stream-recoverability/0.1 foen-custody-only",
        },
    )


def _select_networks(
    requests: list[FoenYearRequest], *, max_networks: int | None
) -> list[FoenYearRequest]:
    network_ids = sorted({row.network_id for row in requests})
    selected = set(network_ids if max_networks is None else network_ids[:max_networks])
    return [row for row in requests if row.network_id in selected]


def _dry_manifest(
    catalog: LockedFoenCatalog, requests: list[FoenYearRequest]
) -> dict[str, Any]:
    return {
        "manifest_schema": "foen_sealed_custody_run_v2",
        "dry_run": True,
        "execute": False,
        "provider": "foen",
        "role": "sealed",
        "split_sha256": catalog.split_sha256,
        "catalog_sha256": catalog.catalog_sha256,
        "query_template_sha256": catalog.query_template_sha256,
        "n_networks_planned": len({row.network_id for row in requests}),
        "n_stations_planned": len({(row.network_id, row.site_id) for row in requests}),
        "n_calendar_years_per_station": catalog.end_year_exclusive - catalog.start_year,
        "n_station_year_requests_planned": len(requests),
        "provider_requests_opened": False,
        "query_template_executed": False,
        "commit_required_before_execute": True,
        "content_parsed": False,
        "json_decoded": False,
        "value_fields_inspected": False,
        "sealed_outcomes_opened": False,
        "contains_outcome_values": False,
        "formal_evidence": False,
        "purpose": "sealed_byte_custody_dry_run_not_evidence",
        "v1_failed_pilot_objects_reused": False,
    }


def _opaque_diversity(records: list[dict[str, Any]]) -> dict[str, Any]:
    shas = [str(row.get("response_sha256") or "") for row in records]
    unique = len(set(shas))
    return {
        "n_response_objects": len(records),
        "n_unique_response_sha256": unique,
        "all_response_bodies_byte_identical": bool(len(records) > 1 and unique == 1),
        "opaque_response_diversity_gate_pass": bool(len(records) > 1 and unique > 1),
    }


def _require_completed_diverse_pilot(
    catalog: LockedFoenCatalog, gate: FoenSealedCorpusGate
) -> dict[str, Any]:
    pilot_requests = _select_networks(catalog.requests(), max_networks=1)
    records = []
    for request in pilot_requests:
        record = gate.resume_record(request.network_id, request.site_id, request.year)
        if record is None:
            raise PermissionError(
                "full FOEN v2 run requires a complete one-network pilot"
            )
        records.append(record)
    summary = _opaque_diversity(records)
    if not summary["opaque_response_diversity_gate_pass"]:
        raise PermissionError(
            "full FOEN v2 run forbidden: pilot response bodies lack byte diversity"
        )
    return summary


def run(
    *,
    execute: bool,
    max_networks: int | None,
    all_networks: bool,
    output_dir: Path,
    acknowledge_sealed: str | None = None,
    acknowledge_full_corpus: str | None = None,
    implementation_commit: str | None = None,
    attempts: int = 3,
    pause_s: float = 0.15,
    catalog: LockedFoenCatalog | None = None,
    gate: FoenSealedCorpusGate | None = None,
    opener: Any = urllib.request.urlopen,
    commit_verifier: Any = verify_implementation_commit,
) -> dict[str, Any]:
    catalog = LockedFoenCatalog.load() if catalog is None else catalog
    gate = FoenSealedCorpusGate(catalog) if gate is None else gate
    if gate.catalog is not catalog:
        raise ValueError(
            "runner catalog and FOEN custody gate must be the same locked view"
        )
    requests = _select_networks(catalog.requests(), max_networks=max_networks)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "foen_sealed_custody_manifest.json"
    if not execute:
        manifest = _dry_manifest(catalog, requests)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest

    if max_networks is None and not all_networks:
        raise ValueError("execute requires --max-networks or explicit --all-networks")
    if max_networks is not None and max_networks < 1:
        raise ValueError("--max-networks must be positive")
    if max_networks is not None and max_networks != 1:
        raise ValueError("FOEN v2 pilot must use exactly --max-networks 1")
    if acknowledge_sealed != SEALED_ACK:
        raise PermissionError(
            f"FOEN sealed execution requires --acknowledge-sealed {SEALED_ACK!r}"
        )
    if all_networks and acknowledge_full_corpus != FULL_CORPUS_ACK:
        raise PermissionError(
            "full FOEN execution requires --acknowledge-full-corpus "
            f"{FULL_CORPUS_ACK!r}"
        )
    if implementation_commit is None:
        raise PermissionError("FOEN execution requires a committed implementation SHA")
    verified_commit = str(commit_verifier(implementation_commit))
    pilot_preflight = (
        _require_completed_diverse_pilot(catalog, gate) if all_networks else None
    )

    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    n_reused = 0
    for request in requests:
        try:
            existing = gate.resume_record(
                request.network_id, request.site_id, request.year
            )
        except (FoenCustodyError, OSError, ValueError) as error:
            failures.append(
                {
                    **request.metadata(),
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            continue
        if existing is not None:
            records.append(existing)
            n_reused += 1
            continue

        caught: BaseException | None = None
        for attempt in range(1, int(attempts) + 1):
            try:
                provider_request = _provider_request(catalog, request)
                with opener(provider_request, timeout=120) as response:
                    record = gate.cache_stream(
                        request.network_id,
                        request.site_id,
                        request.year,
                        _response_chunks(response),
                    )
                records.append(record)
                caught = None
                break
            except FileExistsError as error:
                caught = error
                break
            except Exception as error:  # noqa: BLE001 - opaque transport failure
                caught = error
                if attempt < attempts:
                    time.sleep(min(8.0, float(2 ** (attempt - 1))))
        if caught is not None:
            failures.append(
                {
                    **request.metadata(),
                    "error_type": type(caught).__name__,
                    "error": str(caught),
                }
            )
        if pause_s > 0:
            time.sleep(pause_s)

    custody = registry_manifest(records)
    diversity = _opaque_diversity(records)
    manifest = {
        "manifest_schema": "foen_sealed_custody_run_v2",
        "dry_run": False,
        "execute": True,
        "provider": "foen",
        "role": "sealed",
        "implementation_commit": verified_commit,
        "split_sha256": catalog.split_sha256,
        "catalog_sha256": catalog.catalog_sha256,
        "query_template_sha256": catalog.query_template_sha256,
        "n_networks_requested": len({row.network_id for row in requests}),
        "n_stations_requested": len(
            {(row.network_id, row.site_id) for row in requests}
        ),
        "n_station_year_requests": len(requests),
        "n_objects_registered": len(records),
        "n_reused": n_reused,
        "n_newly_registered": len(records) - n_reused,
        "n_failures": len(failures),
        "content_parsed": False,
        "json_decoded": False,
        "value_fields_inspected": False,
        "sealed_outcomes_opened": False,
        "contains_outcome_values": False,
        "formal_evidence": False,
        "purpose": "sealed_byte_custody_not_evidence",
        "v1_failed_pilot_objects_reused": False,
        "opaque_response_diversity": diversity,
        "full_run_pilot_preflight": pilot_preflight,
        "custody": custody,
        "failures": failures,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--max-networks", type=int)
    selection.add_argument("--all-networks", action="store_true")
    parser.add_argument("--acknowledge-sealed")
    parser.add_argument("--acknowledge-full-corpus")
    parser.add_argument("--implementation-commit")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RUN_DIR)
    args = parser.parse_args()
    max_networks = None if args.all_networks else args.max_networks
    manifest = run(
        execute=args.execute,
        max_networks=max_networks,
        all_networks=args.all_networks,
        output_dir=args.output_dir,
        acknowledge_sealed=args.acknowledge_sealed,
        acknowledge_full_corpus=args.acknowledge_full_corpus,
        implementation_commit=args.implementation_commit,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
