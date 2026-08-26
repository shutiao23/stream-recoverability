"""QC already-downloaded catalog-v3 development/validation response objects.

Every raw object is opened through :class:`HUC8CorpusGate`; direct cache reads
are deliberately absent.  Sealed roles are rejected before registry or object
access.  This module performs no downloads.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from stream_recoverability.data.ingest_qc import clean_long_frame, qc_long_frame
from stream_recoverability.data.public_temperature import (
    overlap_report,
    river_wide_panel,
)
from stream_recoverability.data.sealed_corpus import (
    QC_ROLES,
    SEALED_ROLE,
    HUC8CorpusGate,
    LockedV3Catalog,
    SealedOutcomeAccessError,
    StationRequest,
)

MIN_STATIONS = 3
MIN_QUALIFIED_YEARS = 8
MIN_CONCURRENT_DAYS = 5 * 365


def parse_nwis_daily_json(
    handle: BinaryIO,
    *,
    expected_site_id: str,
    expected_start: str,
    expected_end: str,
) -> pd.DataFrame:
    """Parse one open-role NWIS daily-value response into the ingest schema."""

    document = json.load(handle)
    if not isinstance(document, dict):
        raise TypeError("NWIS response must be a JSON mapping")
    value = document.get("value") or {}
    if not isinstance(value, dict):
        raise TypeError("NWIS response value must be a mapping")
    series = value.get("timeSeries") or []
    if not isinstance(series, list):
        raise TypeError("NWIS timeSeries must be a list")
    rows: list[dict[str, Any]] = []
    observed_codes: set[str] = set()
    for item in series:
        if not isinstance(item, dict):
            raise TypeError("NWIS timeSeries entries must be mappings")
        source = item.get("sourceInfo") or {}
        if isinstance(source, dict):
            for code in source.get("siteCode") or []:
                if isinstance(code, dict) and code.get("value") is not None:
                    observed_codes.add(str(code["value"]))
        values_blocks = item.get("values") or []
        if not isinstance(values_blocks, list):
            raise TypeError("NWIS values blocks must be a list")
        for block in values_blocks:
            if not isinstance(block, dict):
                raise TypeError("NWIS values block must be a mapping")
            points = block.get("value") or []
            if not isinstance(points, list):
                raise TypeError("NWIS value points must be a list")
            for point in points:
                if not isinstance(point, dict):
                    raise TypeError("NWIS value point must be a mapping")
                qualifiers = point.get("qualifiers")
                if isinstance(qualifiers, list):
                    qualifier = ",".join(str(item) for item in qualifiers)
                elif qualifiers is None:
                    qualifier = ""
                else:
                    qualifier = str(qualifiers)
                rows.append(
                    {
                        "site_id": str(expected_site_id),
                        "date": point.get("dateTime"),
                        "temperature_c": point.get("value"),
                        "qualifier": qualifier,
                    }
                )
    if observed_codes and observed_codes != {str(expected_site_id)}:
        raise ValueError(
            "NWIS response siteCode differs from locked station request: "
            f"{sorted(observed_codes)}"
        )
    frame = pd.DataFrame(
        rows, columns=["site_id", "date", "temperature_c", "qualifier"]
    )
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce").dt.tz_localize(
        None
    ).dt.normalize()
    frame["temperature_c"] = pd.to_numeric(
        frame["temperature_c"], errors="coerce"
    )
    frame = frame.dropna(subset=["date"]).sort_values("date", kind="mergesort")
    start = pd.Timestamp(expected_start)
    end = pd.Timestamp(expected_end)
    if start > end or (not frame.empty and (frame["date"].min() < start or frame["date"].max() > end)):
        raise ValueError("NWIS response dates fall outside the locked request interval")
    return frame


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _complete_enough(report: dict[str, Any]) -> bool:
    return bool(
        int(report.get("n_stations") or 0) >= MIN_STATIONS
        and float(report.get("overlap_years") or 0.0) >= 8.0
        and int(report.get("days_with_min_stations") or 0) >= MIN_CONCURRENT_DAYS
    )


def _attrition(
    *,
    n_requested: int,
    n_registered: int,
    n_nonempty: int,
    report: pd.DataFrame,
) -> pd.DataFrame:
    accepted = (
        int(report["verdict"].astype(str).str.startswith("accepted").sum())
        if not report.empty
        else 0
    )
    eligible = (
        int(report["eligible_for_network"].fillna(False).sum())
        if not report.empty
        else 0
    )
    return pd.DataFrame(
        [
            {"level": "station", "stage": "locked_network_members", "n": n_requested},
            {"level": "station", "stage": "registered_raw_objects", "n": n_registered},
            {"level": "station", "stage": "parsed_nonempty", "n": n_nonempty},
            {"level": "station", "stage": "qc_verdict_accepted", "n": accepted},
            {"level": "station", "stage": "qualified_years_ge_8", "n": eligible},
            {
                "level": "station",
                "stage": "rejected_sentinel",
                "n": int(report["verdict"].eq("rejected_sentinel").sum())
                if not report.empty
                else 0,
            },
        ]
    )


def run_open_role_qc(
    *,
    role: str,
    output_dir: str | Path,
    catalog: LockedV3Catalog | None = None,
    gate: HUC8CorpusGate | None = None,
    max_networks: int | None = None,
) -> dict[str, Any]:
    """QC only registered raw objects for one open split role."""

    if role == SEALED_ROLE:
        raise SealedOutcomeAccessError("sealed role is not available to the QC runner")
    if role not in QC_ROLES:
        raise PermissionError(f"QC runner rejects split role {role!r}")
    catalog = LockedV3Catalog.load() if catalog is None else catalog
    gate = HUC8CorpusGate(catalog) if gate is None else gate
    if gate.catalog is not catalog:
        raise ValueError("runner catalog and custody gate must be the same locked view")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[StationRequest]] = defaultdict(list)
    for request in catalog.requests(role):
        grouped[request.network_id].append(request)
    network_ids = sorted(grouped)
    if max_networks is not None:
        if max_networks < 1:
            raise ValueError("max_networks must be positive")
        network_ids = network_ids[:max_networks]

    aggregate_qc: list[pd.DataFrame] = []
    aggregate_attrition: list[pd.DataFrame] = []
    overlap_rows: list[dict[str, Any]] = []
    n_registry_reused = 0
    n_objects_missing = 0
    for network_id in network_ids:
        requests = grouped[network_id]
        frames: list[pd.DataFrame] = []
        station_status: dict[str, dict[str, Any]] = {}
        n_registered = 0
        for request in requests:
            opened = gate.open_registered_for_qc(network_id, request.site_id)
            if opened is None:
                n_objects_missing += 1
                station_status[request.site_id] = {"status": "not_downloaded"}
                continue
            record, handle = opened
            n_registered += 1
            n_registry_reused += int(record.get("reused_registry") is True)
            with handle:
                frame = parse_nwis_daily_json(
                    handle,
                    expected_site_id=request.site_id,
                    expected_start=request.start,
                    expected_end=request.end,
                )
            station_status[request.site_id] = {
                "status": "parsed_empty" if frame.empty else "parsed",
                "n_rows": len(frame),
                "registry_sha256": record["sha256"],
                "registry_reused": bool(record.get("reused_registry")),
            }
            if not frame.empty:
                frames.append(frame)
        if n_registered == 0:
            continue

        raw_long = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(
                columns=["site_id", "date", "temperature_c", "qualifier"]
            )
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
        report.loc[insufficient, "exclusion_reason"] = (
            "qualified_years_lt_8"
        )

        network_dir = destination / "networks" / network_id
        network_dir.mkdir(parents=True, exist_ok=True)
        report.to_csv(network_dir / "ingest_qc_report.csv", index=False)
        clean = clean_long_frame(
            raw_long,
            report=report,
            min_qualified_years=MIN_QUALIFIED_YEARS,
        )
        clean.to_csv(network_dir / "daily_long_qc.csv", index=False)
        wide = river_wide_panel(
            [group.copy() for _, group in clean.groupby("site_id", sort=False)]
        )
        wide.to_csv(network_dir / "daily_wide_qc.csv")
        overlap = overlap_report(wide, min_stations=MIN_STATIONS)
        overlap["complete_enough"] = _complete_enough(overlap)
        overlap.update(
            {
                "network_id": network_id,
                "role": role,
                "n_requested_stations": len(requests),
                "n_registered_raw_objects": n_registered,
                "n_parsed_nonempty": len(frames),
                "n_qc_eligible_stations": int(
                    report["eligible_for_network"].fillna(False).sum()
                ),
                "network_interval_reported": False,
            }
        )
        attrition = _attrition(
            n_requested=len(requests),
            n_registered=n_registered,
            n_nonempty=len(frames),
            report=report,
        )
        attrition.insert(0, "network_id", network_id)
        attrition.to_csv(network_dir / "attrition_summary.csv", index=False)
        _atomic_json(
            network_dir / "network_qc_manifest.json",
            {
                "manifest_schema": "huc8_open_role_network_qc_v1",
                "network_id": network_id,
                "role": role,
                "split_sha256": catalog.split_sha256,
                "status": "complete",
                "stations": station_status,
                "overlap": overlap,
                "sealed_temperature_records_read": False,
                "network_interval_reported": False,
                "formal_evidence": False,
            },
        )
        aggregate_qc.append(report)
        aggregate_attrition.append(attrition)
        overlap_rows.append(overlap)

    qc = pd.concat(aggregate_qc, ignore_index=True) if aggregate_qc else pd.DataFrame()
    attrition = (
        pd.concat(aggregate_attrition, ignore_index=True)
        if aggregate_attrition
        else pd.DataFrame(columns=["network_id", "level", "stage", "n"])
    )
    overlaps = pd.DataFrame(overlap_rows)
    qc.to_csv(destination / "ingest_qc_report.csv", index=False)
    attrition.to_csv(destination / "attrition_summary.csv", index=False)
    overlaps.to_csv(destination / "overlap_attrition.csv", index=False)
    manifest = {
        "manifest_schema": "huc8_open_role_corpus_qc_v1",
        "role": role,
        "split_sha256": catalog.split_sha256,
        "n_networks_selected": len(network_ids),
        "n_networks_with_registered_objects": len(overlap_rows),
        "n_registry_objects_reused": n_registry_reused,
        "n_objects_not_downloaded": n_objects_missing,
        "n_networks_complete_enough": sum(
            row.get("complete_enough") is True for row in overlap_rows
        ),
        "sealed_temperature_records_read": False,
        "network_interval_reported": False,
        "formal_evidence": False,
        "purpose": "open_role_ingest_qc_not_evidence",
    }
    _atomic_json(destination / "qc_manifest.json", manifest)
    return manifest


__all__ = ["parse_nwis_daily_json", "run_open_role_qc"]
