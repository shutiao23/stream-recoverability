#!/usr/bin/env python3
"""Cache locked HUC8 response bytes under role-aware custody.

The command is a dry run unless ``--execute`` is supplied.  A sealed execution
also requires an explicit acknowledgement.  Provider responses are streamed
as opaque bytes into :mod:`sealed_corpus`; this script never decodes or parses
sealed content and never runs QC on it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.sealed_corpus import (
    SEALED_ROLE,
    CorpusCustodyError,
    HUC8CorpusGate,
    LockedV3Catalog,
    StationRequest,
    registry_manifest,
)

NWIS_DV = "https://waterservices.usgs.gov/nwis/dv/"
DEFAULT_RUN_DIR = ROOT / "data_versions/global_network_corpus_v1/w4_custody"
SEALED_ACK = "sealed-bytes-write-only-no-qc"
FULL_CORPUS_ACK = "full-corpus-download-authorized"


def _request_url(request: StationRequest) -> str:
    return NWIS_DV + "?" + urllib.parse.urlencode(
        {
            "format": "json",
            "sites": request.site_id,
            "parameterCd": "00010",
            "statCd": "00003",
            "startDT": request.start,
            "endDT": request.end,
        }
    )


def _response_chunks(response: Any, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    while True:
        chunk = response.read(chunk_size)
        if not chunk:
            return
        yield chunk


def _select_networks(
    requests: list[StationRequest], *, max_networks: int | None
) -> list[StationRequest]:
    network_ids = sorted({row.network_id for row in requests})
    selected = set(network_ids if max_networks is None else network_ids[:max_networks])
    return [row for row in requests if row.network_id in selected]


def _dry_manifest(
    catalog: LockedV3Catalog,
    *,
    role: str,
    requests: list[StationRequest],
) -> dict[str, Any]:
    return {
        "manifest_schema": "huc8_corpus_custody_run_v1",
        "dry_run": True,
        "execute": False,
        "role": role,
        "split_sha256": catalog.split_sha256,
        "n_networks_planned": len({row.network_id for row in requests}),
        "n_stations_planned": len(requests),
        "provider_responses_opened": False,
        "content_parsed": False,
        "sealed_outcomes_opened": False,
        "contains_outcome_values": False,
        "formal_evidence": False,
        "purpose": "download_custody_pipeline_verification_not_evidence",
    }


def run(
    *,
    role: str,
    execute: bool,
    max_networks: int | None,
    output_dir: Path,
    acknowledge_sealed: str | None = None,
    all_networks: bool = False,
    acknowledge_full_corpus: str | None = None,
    attempts: int = 3,
    pause_s: float = 0.25,
    catalog: LockedV3Catalog | None = None,
    gate: HUC8CorpusGate | None = None,
    opener: Any = urllib.request.urlopen,
) -> dict[str, Any]:
    catalog = LockedV3Catalog.load() if catalog is None else catalog
    gate = HUC8CorpusGate(catalog) if gate is None else gate
    if gate.catalog is not catalog:
        raise ValueError("runner catalog and custody gate must be the same locked view")
    requests = _select_networks(catalog.requests(role), max_networks=max_networks)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"{role}_custody_manifest.json"
    if not execute:
        manifest = _dry_manifest(catalog, role=role, requests=requests)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest

    if max_networks is None and not all_networks:
        raise ValueError("execute requires --max-networks or explicit --all-networks")
    if max_networks is not None and max_networks < 1:
        raise ValueError("--max-networks must be positive")
    if all_networks and acknowledge_full_corpus != FULL_CORPUS_ACK:
        raise PermissionError(
            "full-corpus execution requires --acknowledge-full-corpus "
            f"{FULL_CORPUS_ACK!r}"
        )
    if role == SEALED_ROLE and acknowledge_sealed != SEALED_ACK:
        raise PermissionError(
            f"sealed execution requires --acknowledge-sealed {SEALED_ACK!r}"
        )

    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    n_reused = 0
    for request in requests:
        error: BaseException | None = None
        try:
            existing = gate.resume_record(request.network_id, request.site_id)
        except (CorpusCustodyError, OSError, ValueError) as caught:
            failures.append(
                {
                    "network_id": request.network_id,
                    "site_id": request.site_id,
                    "error_type": type(caught).__name__,
                    "error": str(caught),
                }
            )
            continue
        if existing is not None:
            records.append(existing)
            n_reused += 1
            continue
        for attempt in range(1, attempts + 1):
            try:
                provider_request = urllib.request.Request(
                    _request_url(request),
                    headers={
                        "User-Agent": "stream-recoverability/0.1 custody-only",
                        "Accept": "application/json",
                    },
                )
                with opener(provider_request, timeout=120) as response:
                    record = gate.cache_stream(
                        request.network_id,
                        request.site_id,
                        _response_chunks(response),
                    )
                records.append(record)
                error = None
                break
            except FileExistsError:
                # Immutable objects are intentionally not reopened to verify or
                # resume them.  Their existing registry is the custody record.
                error = FileExistsError("immutable object or registry already exists")
                break
            # Provider libraries may raise several unrelated transport errors;
            # all are retained as custody failures and retried without parsing.
            except Exception as caught:  # noqa: BLE001
                error = caught
                if attempt < attempts:
                    time.sleep(min(8.0, float(2 ** (attempt - 1))))
        if error is not None:
            failures.append(
                {
                    "network_id": request.network_id,
                    "site_id": request.site_id,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
        if pause_s > 0:
            time.sleep(pause_s)

    custody = registry_manifest(records)
    manifest = {
        "manifest_schema": "huc8_corpus_custody_run_v1",
        "dry_run": False,
        "execute": True,
        "role": role,
        "split_sha256": catalog.split_sha256,
        "n_networks_requested": len({row.network_id for row in requests}),
        "n_stations_requested": len(requests),
        "n_stations_registered": len(records),
        "n_reused": n_reused,
        "n_newly_registered": len(records) - n_reused,
        "n_failures": len(failures),
        "content_parsed": False,
        "sealed_outcomes_opened": False,
        "contains_outcome_values": False,
        "formal_evidence": False,
        "purpose": "download_custody_pipeline_verification_not_evidence",
        "custody": custody,
        "failures": failures,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--role", choices=["development", "validation", "sealed"], required=True
    )
    parser.add_argument("--execute", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--max-networks", type=int)
    selection.add_argument("--all-networks", action="store_true")
    parser.add_argument("--acknowledge-sealed")
    parser.add_argument("--acknowledge-full-corpus")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RUN_DIR)
    args = parser.parse_args()
    max_networks = None if args.all_networks else args.max_networks
    manifest = run(
        role=args.role,
        execute=args.execute,
        max_networks=max_networks,
        output_dir=args.output_dir,
        acknowledge_sealed=args.acknowledge_sealed,
        all_networks=args.all_networks,
        acknowledge_full_corpus=args.acknowledge_full_corpus,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
