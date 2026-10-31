"""Stream locked FOEN sealed responses into write-only byte custody.

Dry-run is the default and never constructs or opens a provider request.
Execution requires explicit sealed/full-corpus acknowledgements.  Provider
response bodies are never JSON-decoded by this runner.
"""

from __future__ import annotations
import argparse
import json
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
        "n_networks_planned": len({row.network_id for row in requests}),
        "n_stations_planned": len({(row.network_id, row.site_id) for row in requests}),
        "n_calendar_years_per_station": catalog.end_year_exclusive - catalog.start_year,
        "n_station_year_requests_planned": len(requests),
        "provider_requests_opened": False,
        "query_template_executed": False,
        "content_parsed": False,
        "json_decoded": False,
        "value_fields_inspected": False,
        "sealed_outcomes_opened": False,
        "contains_outcome_values": False,
        "formal_evidence": False,
        "purpose": "sealed_byte_custody_dry_run_not_evidence",
        "v1_failed_pilot_objects_reused": False,
    }


def run(
    *,
    execute: bool,
    max_networks: int | None,
    all_networks: bool,
    output_dir: Path,
    acknowledge_sealed: str | None = None,
    acknowledge_full_corpus: str | None = None,
    attempts: int = 3,
    pause_s: float = 0.15,
    catalog: LockedFoenCatalog | None = None,
    gate: FoenSealedCorpusGate | None = None,
    opener: Any = urllib.request.urlopen,
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
    if max_networks is not None and max_networks < 1:
        raise ValueError("--max-networks must be positive")
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
            except Exception as error:
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
    manifest = {
        "manifest_schema": "foen_sealed_custody_run_v2",
        "dry_run": False,
        "execute": True,
        "provider": "foen",
        "role": "sealed",
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
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
