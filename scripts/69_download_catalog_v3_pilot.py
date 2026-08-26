#!/usr/bin/env python3
"""Run the locked 20-network HUC8 development download/QC pilot.

The split lock is verified before even a dry run.  Only rows whose locked role
is ``development`` can enter the plan.  Validation/sealed temperatures are
neither requested nor inspected.  Each network has an atomic, resumable JSON
manifest and each station has its own exact-date cache entry.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame
from stream_recoverability.data.nwis_temperature import nwis_daily_temperature
from stream_recoverability.data.public_temperature import overlap_report, river_wide_panel
from stream_recoverability.data.v3_download_policy import plan_v3_development_pilot


DEFAULT_OUTPUT = ROOT / "data_versions/global_network_corpus_v1/w3_development_pilot"
DEFAULT_CACHE = ROOT / "data/public_rivers_v3"
MIN_STATIONS = 3
MIN_QUALIFIED_YEARS = 8
MIN_CONCURRENT_DAYS = 5 * 365


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _fetch_with_backoff(
    station: dict[str, str],
    *,
    cache_dir: Path,
    fetcher: Callable[..., pd.DataFrame] = nwis_daily_temperature,
    attempts: int = 3,
    base_backoff_s: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[pd.DataFrame | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        try:
            frame = fetcher(
                station["site_id"],
                station["start"],
                station["end"],
                cache_dir=cache_dir,
            )
            return frame, errors
        except Exception as error:  # the manifest must preserve provider failures
            errors.append(
                {
                    "attempt": attempt,
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
            if attempt < attempts:
                sleep(float(base_backoff_s) * (2 ** (attempt - 1)))
    return None, errors


def _network_complete_enough(report: dict[str, Any]) -> bool:
    return bool(
        int(report.get("n_stations") or 0) >= MIN_STATIONS
        and float(report.get("overlap_years") or 0.0) >= 8.0
        and int(report.get("days_with_min_stations") or 0) >= MIN_CONCURRENT_DAYS
    )


def _plan_rows(plan: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for network in plan["networks"]:
        for station in network["stations"]:
            rows.append(
                {
                    "network_id": network["network_id"],
                    "role": network["role"],
                    "climate_band": network["climate_band"],
                    "regulation_stratum": network["regulation_stratum"],
                    "size_tertile": network["size_tertile"],
                    **station,
                }
            )
    return pd.DataFrame(rows)


def _dry_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: plan[key] for key in (
            "policy",
            "split_sha256",
            "pilot_seed",
            "pilot_size",
            "sample_network_ids_sha256",
            "stratification_columns",
            "n_development_available",
            "n_validation_selected",
            "n_sealed_selected",
            "sealed_temperature_records_read",
            "retired_name_huc2_plan_used",
        )},
        "dry_run": True,
        "temperatures_downloaded": False,
        "n_networks_planned": len(plan["networks"]),
        "n_stations_planned": sum(len(row["stations"]) for row in plan["networks"]),
        "network_interval_reported": False,
        "formal_evidence": False,
        "purpose": "w3_download_and_ingest_pipeline_verification",
    }


def run_pilot(
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    cache_dir: Path = DEFAULT_CACHE,
    dry_run: bool = False,
    max_networks: int = 0,
    force: bool = False,
    attempts: int = 3,
    base_backoff_s: float = 1.0,
    pause_s: float = 0.25,
    fetcher: Callable[..., pd.DataFrame] = nwis_daily_temperature,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    plan = plan_v3_development_pilot()
    output_dir.mkdir(parents=True, exist_ok=True)
    _plan_rows(plan).to_csv(output_dir / "pilot_download_plan.csv", index=False)
    if dry_run:
        manifest = _dry_manifest(plan)
        _atomic_json(output_dir / "pilot_manifest.json", manifest)
        return manifest

    networks = list(plan["networks"])
    if max_networks > 0:
        networks = networks[: int(max_networks)]
    all_qc: list[pd.DataFrame] = []
    overlap_rows: list[dict[str, Any]] = []
    for network in networks:
        network_id = str(network["network_id"])
        network_dir = output_dir / "networks" / network_id
        manifest_path = network_dir / "network_manifest.json"
        if manifest_path.is_file() and not force:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            if previous.get("status") == "complete":
                qc_path = network_dir / "ingest_qc_report.csv"
                if qc_path.is_file():
                    all_qc.append(pd.read_csv(qc_path, dtype={"site_id": str}))
                overlap_rows.append(dict(previous.get("overlap") or {}, network_id=network_id))
                continue

        network_manifest: dict[str, Any] = {
            "network_id": network_id,
            "role": "development",
            "split_sha256": plan["split_sha256"],
            "status": "in_progress",
            "sealed_temperature_records_read": False,
            "stations": {},
        }
        _atomic_json(manifest_path, network_manifest)
        frames: list[pd.DataFrame] = []
        for station in network["stations"]:
            site_id = station["site_id"]
            exact_cache = (
                cache_dir
                / "nwis"
                / f"{site_id}_{station['start']}_{station['end']}.csv"
            )
            cached_before = exact_cache.is_file()
            frame, errors = _fetch_with_backoff(
                station,
                cache_dir=cache_dir,
                fetcher=fetcher,
                attempts=attempts,
                base_backoff_s=base_backoff_s,
                sleep=sleep,
            )
            station_record = {
                **station,
                "cached_before": cached_before,
                "errors": errors,
                "status": "failed" if frame is None else ("empty" if frame.empty else "fetched"),
                "n_rows": 0 if frame is None else int(len(frame)),
            }
            network_manifest["stations"][site_id] = station_record
            _atomic_json(manifest_path, network_manifest)
            if frame is not None and not frame.empty:
                frames.append(frame)
            if not cached_before and pause_s > 0:
                sleep(pause_s)

        if frames:
            raw_long = pd.concat(frames, ignore_index=True)
        else:
            raw_long = pd.DataFrame(
                columns=["site_id", "date", "temperature_c", "qualifier"]
            )
        report = qc_long_frame(raw_long)
        report["network_id"] = network_id
        report["eligible_for_network"] = (
            report["verdict"].astype(str).str.startswith("accepted")
            & pd.to_numeric(report["qualified_years"], errors="coerce").ge(
                MIN_QUALIFIED_YEARS
            )
        )
        report["exclusion_reason"] = ""
        rejected = ~report["verdict"].astype(str).str.startswith("accepted")
        report.loc[rejected, "exclusion_reason"] = report.loc[rejected, "verdict"]
        insufficient = ~rejected & ~report["eligible_for_network"]
        report.loc[insufficient, "exclusion_reason"] = "qualified_years_lt_8"
        network_dir.mkdir(parents=True, exist_ok=True)
        report.to_csv(network_dir / "ingest_qc_report.csv", index=False)
        all_qc.append(report)

        clean = clean_long_frame(
            raw_long, report=report, min_qualified_years=MIN_QUALIFIED_YEARS
        )
        clean.to_csv(network_dir / "daily_long_qc.csv", index=False)
        wide = river_wide_panel(
            [group.copy() for _, group in clean.groupby("site_id", sort=False)]
        )
        if not wide.empty:
            wide.to_csv(network_dir / "daily_wide_qc.csv")
        overlap = overlap_report(wide, min_stations=MIN_STATIONS)
        overlap["complete_enough"] = _network_complete_enough(overlap)
        overlap.update(
            {
                "network_id": network_id,
                "n_requested_stations": len(network["stations"]),
                "n_downloaded_nonempty": len(frames),
                "n_qc_eligible_stations": int(report["eligible_for_network"].sum()),
                "role": "development",
                "network_interval_reported": False,
            }
        )
        overlap_rows.append(overlap)
        network_manifest.update(
            {
                "status": "complete",
                "overlap": overlap,
                "rejected_stations_absent_from_wide": True,
                "network_interval_reported": False,
            }
        )
        _atomic_json(manifest_path, network_manifest)

    qc = pd.concat(all_qc, ignore_index=True) if all_qc else pd.DataFrame()
    overlap_frame = pd.DataFrame(overlap_rows)
    qc.to_csv(output_dir / "ingest_qc_report.csv", index=False)
    overlap_frame.to_csv(output_dir / "overlap_attrition.csv", index=False)
    verdict_counts = (
        {str(key): int(value) for key, value in qc["verdict"].value_counts().items()}
        if not qc.empty and "verdict" in qc
        else {}
    )
    complete = (
        int(overlap_frame["complete_enough"].fillna(False).sum())
        if not overlap_frame.empty and "complete_enough" in overlap_frame
        else 0
    )
    station_records: list[dict[str, Any]] = []
    for network in networks:
        path = output_dir / "networks" / str(network["network_id"]) / "network_manifest.json"
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        station_records.extend((document.get("stations") or {}).values())
    n_station_failed = sum(row.get("status") == "failed" for row in station_records)
    n_station_empty = sum(row.get("status") == "empty" for row in station_records)
    n_station_retry_errors = sum(bool(row.get("errors")) for row in station_records)
    projected = 166.0 * complete / len(overlap_frame) if len(overlap_frame) else 0.0
    attrition = pd.DataFrame(
        [
            {"level": "network", "stage": "pilot_selected", "n": len(networks)},
            {
                "level": "network",
                "stage": "download_and_qc_completed",
                "n": len(overlap_frame),
            },
            {"level": "network", "stage": "complete_enough", "n": complete},
            {
                "level": "station",
                "stage": "requested",
                "n": len(station_records),
            },
            {
                "level": "station",
                "stage": "downloaded_nonempty",
                "n": sum(row.get("status") == "fetched" for row in station_records),
            },
            {
                "level": "station",
                "stage": "qc_verdict_accepted",
                "n": int(qc["verdict"].astype(str).str.startswith("accepted").sum())
                if not qc.empty
                else 0,
            },
            {
                "level": "station",
                "stage": "qualified_years_ge_8",
                "n": int(qc["eligible_for_network"].fillna(False).sum())
                if not qc.empty
                else 0,
            },
            {
                "level": "station",
                "stage": "rejected_sentinel",
                "n": int(qc["verdict"].eq("rejected_sentinel").sum())
                if not qc.empty
                else 0,
            },
            {
                "level": "station",
                "stage": "qualified_years_lt_8",
                "n": int(qc["exclusion_reason"].eq("qualified_years_lt_8").sum())
                if not qc.empty
                else 0,
            },
        ]
    )
    attrition.to_csv(output_dir / "attrition_summary.csv", index=False)
    manifest = {
        **{key: plan[key] for key in (
            "policy",
            "split_sha256",
            "pilot_seed",
            "pilot_size",
            "sample_network_ids_sha256",
            "stratification_columns",
            "n_development_available",
            "n_validation_selected",
            "n_sealed_selected",
            "sealed_temperature_records_read",
            "retired_name_huc2_plan_used",
        )},
        "dry_run": False,
        "n_networks_planned": len(plan["networks"]),
        "n_networks_attempted_this_invocation": len(networks),
        "n_networks_in_attrition": int(len(overlap_frame)),
        "n_networks_complete_enough": complete,
        "pilot_survival_fraction": complete / len(overlap_frame) if len(overlap_frame) else 0.0,
        "catalog_units_for_point_extrapolation": 166,
        "projected_complete_enough_at_catalog_scale": projected,
        "projected_below_network_ci_floor_100": projected < 100.0,
        "projected_below_target_150": projected < 150.0,
        "six_year_relaxation_triggered": projected < 100.0,
        "europe_supplement_required": True,
        "europe_required_for_target_150": projected < 150.0,
        "europe_required_for_non_na_sealed": True,
        "non_na_sealed_current_vs_target": "0/10",
        "n_stations_in_qc": int(len(qc)),
        "n_stations_eligible_for_network": (
            int(qc["eligible_for_network"].fillna(False).sum())
            if not qc.empty and "eligible_for_network" in qc
            else 0
        ),
        "station_verdict_counts": verdict_counts,
        "n_station_download_failures": int(n_station_failed),
        "n_station_empty_downloads": int(n_station_empty),
        "n_station_requests_with_retry_errors": int(n_station_retry_errors),
        "station_download_failure_fraction": (
            n_station_failed / len(station_records) if station_records else 0.0
        ),
        "network_interval_reported": False,
        "network_ci_status": "withheld_n_lt_100_network_interval",
        "formal_evidence": False,
        "purpose": "w3_download_and_ingest_pipeline_verification",
    }
    _atomic_json(output_dir / "pilot_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-networks", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--base-backoff-s", type=float, default=1.0)
    parser.add_argument("--pause-s", type=float, default=0.25)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    manifest = run_pilot(
        output_dir=args.output,
        cache_dir=args.cache,
        dry_run=args.dry_run,
        max_networks=args.max_networks,
        force=args.force,
        attempts=args.attempts,
        base_backoff_s=args.base_backoff_s,
        pause_s=args.pause_s,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
