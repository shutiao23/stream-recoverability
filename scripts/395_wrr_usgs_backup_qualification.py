#!/usr/bin/env python3
"""Audit public primary/secondary channel records under prespecified daily support."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_public_backup_20261021"
OUT = C.READY / "followup_20261021/public_backup_search"
CONFIG = C.ROOT / "configs/wrr_usgs_backup_20261021.json"
UTC_OFFSETS = {"UTC": 0, "GMT": 0, "AKST": -9, "AKDT": -8, "PST": -8, "PDT": -7,
               "MST": -7, "MDT": -6, "CST": -6, "CDT": -5, "EST": -5, "EDT": -4,
               "HST": -10, "AST": -4, "ADT": -3}
CHANNELS = {"15008000": ("261663_00010", "345020_00010"),
            "12056500": ("150723_00010", "352066_00010")}


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def native_times(frame):
    """Explicit abbreviation offsets preserve distinct hours at DST fall-back."""
    offsets = frame.tz_cd.map(UTC_OFFSETS)
    if offsets.isna().any():
        raise ValueError(f"Unrecognised native time-zone code: {frame.loc[offsets.isna(), 'tz_cd'].unique()}")
    naive = pd.to_datetime(frame.datetime, errors="raise", format="mixed")
    return pd.to_datetime(naive - pd.to_timedelta(offsets, unit="h"), utc=True)


def observation_frame(frame, channel, approved_only=True):
    if channel not in frame or channel + "_cd" not in frame:
        raise ValueError(f"Required native channel missing: {channel}")
    codes = frame[channel + "_cd"].fillna("").str.strip()
    # Approved estimated/ice-affected values must not become observed references.
    accepted = codes.eq("A") if approved_only else codes.isin(["A", "P"])
    values = pd.to_numeric(frame[channel], errors="coerce").where(accepted)
    return pd.DataFrame({"Time_UTC": native_times(frame),
                         "WaterTemperature_Celsius": values})


def read_native(site):
    path = RAW / f"usgs_{site}_native_temperature.rdb"
    frame = pd.read_csv(path, sep="\t", comment="#", dtype=str).iloc[1:].copy()
    if set(frame.site_no.dropna()) != {site} or set(frame.agency_cd.dropna()) != {"USGS"}:
        raise ValueError("Native record does not match the selected station")
    descriptions = {}
    with path.open() as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            match = re.match(r"#\s+([a-zA-Z0-9]+)\s+00010\s+(.+)", line)
            if match:
                descriptions[match[1] + "_00010"] = match[2].strip()
    primary, backup = CHANNELS[site]
    if site == "15008000" and ("Primary" not in descriptions.get(primary, "") or "Secondary" not in descriptions.get(backup, "")):
        raise ValueError("Official primary/secondary channel designations changed")
    if site == "12056500" and "QWsonde-EXO" not in descriptions.get(backup, ""):
        raise ValueError("Water-quality sonde designation changed")
    return frame, descriptions


def qualify(acquisition_path=None, allow_pending=False):
    settings = json.loads(CONFIG.read_text())
    selection_path = OUT / "usgs_metadata_selection.json"
    acquisition_path = acquisition_path or OUT / "usgs_acquisition.json"
    acquisition = json.loads(acquisition_path.read_text())
    original = C.load_script("usgs_original_daily_qualification", C.ROOT / "scripts/388_wrr_natural_backup_validation.py")
    rows, channel_rows = [], []
    acquired_sites = {row["site"] for row in acquisition["records"]}
    for item in settings["candidates"]:
        site = item["site"]
        if site not in acquired_sites:
            if not allow_pending:
                raise RuntimeError("Required candidate is absent from the acquisition manifest")
            for year in item["candidate_years"]:
                rows.append({"site": site, "name": item["name"], "year": year,
                             "record_reference_eligible": None,
                             "physical_sensor_independence_verified": False,
                             "independently_verified_natural_gap_confirmation": False,
                             "acquisition_pending": True,
                             "all_failed_criteria": "not_evaluated_acquisition_pending",
                             "temperature_reconstruction_errors_evaluated": False})
            continue
        frame, descriptions = read_native(site)
        daily = {}
        for channel in CHANNELS[site]:
            strict = observation_frame(frame, channel)
            exploratory = observation_frame(frame, channel, approved_only=False)
            daily[channel] = original.qualified_daily(strict, settings)
            # This diagnostic never changes the reference qualification mask.
            exploratory_daily = original.qualified_daily(exploratory, settings)
            codes = frame[channel + "_cd"].fillna("").str.strip()
            finite = pd.to_numeric(frame[channel], errors="coerce").notna()
            channel_rows.append({"site": site, "channel": channel,
                                 "description": descriptions[channel],
                                 "finite_approved_native_values": int((finite & codes.eq("A")).sum()),
                                 "finite_provisional_native_values": int((finite & codes.eq("P")).sum()),
                                 "other_or_missing_native_status_values": int((finite & ~codes.isin(["A", "P"])).sum()),
                                 "qualified_approved_daily_values": int(daily[channel].notna().sum()),
                                 "coverage_only_daily_values_if_provisional_were_allowed": int(exploratory_daily.notna().sum()),
                                 "provisional_values_accepted_as_reference": False})
        primary, backup = (daily[c] for c in CHANNELS[site])
        history = original.complete_years(primary)
        for year in item["candidate_years"]:
            dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
            p, b = primary.reindex(dates), backup.reindex(dates)
            missing = p.isna()
            overlap = p.notna() & b.notna()
            difference = (p - b).abs().loc[overlap]
            flags = {
                "has_actual_primary_missing_days": bool(missing.any()),
                "primary_annual_boundaries_observed": bool(p.iloc[[0, -1]].notna().all()),
                "backup_covers_every_missing_primary_day": bool(b.loc[missing].notna().all()),
                "has_90_approved_overlap_days": bool(overlap.sum() >= settings["reference_QC"]["minimum_visible_overlap_days"]),
                "approved_sensors_match_under_locked_QC": bool(len(difference) and difference.mean() <= settings["reference_QC"]["maximum_visible_daily_MAE_C"] and difference.quantile(.95) <= settings["reference_QC"]["maximum_visible_daily_abs95_C"]),
                "has_three_complete_prior_primary_years": bool(sum(y < year for y in history) >= 3),
            }
            rows.append({"site": site, "name": item["name"], "year": year,
                         "primary_channel": CHANNELS[site][0], "backup_channel": CHANNELS[site][1],
                         "missing_primary_daily_values": int(missing.sum()),
                         "approved_backup_daily_values_in_target_year": int(b.notna().sum()),
                         "approved_visible_overlap_days": int(overlap.sum()),
                         "visible_pair_MAE_C": float(difference.mean()) if len(difference) else None,
                         "visible_pair_abs95_C": float(difference.quantile(.95)) if len(difference) else None,
                         "complete_prior_primary_years_in_acquired_window": ";".join(str(y) for y in history if y < year),
                         **flags,
                         "record_reference_eligible": bool(all(flags.values())),
                         "acquisition_pending": False,
                         "physical_sensor_independence_verified": False,
                         "independently_verified_natural_gap_confirmation": False,
                         "all_failed_criteria": ";".join(k for k, value in flags.items() if not value),
                         "temperature_reconstruction_errors_evaluated": False})
    OUT.mkdir(exist_ok=True, parents=True)
    pd.DataFrame(rows).to_csv(OUT / "usgs_pair_year_qualification.csv", index=False)
    pd.DataFrame(channel_rows).to_csv(OUT / "usgs_channel_quality.csv", index=False)
    C.write_json(OUT / "usgs_qualification_summary.json", {
        "candidate_sites": len(settings["candidates"]), "candidate_pair_years": len(rows),
        "available_pair_years_evaluated": sum(not r["acquisition_pending"] for r in rows),
        "pending_pair_years_not_evaluated": sum(r["acquisition_pending"] for r in rows),
        "record_reference_eligible_pair_years": sum(r["record_reference_eligible"] is True for r in rows),
        "independently_verified_natural_gap_confirmations": 0,
        "backup_native_approved_observations": sum(r["finite_approved_native_values"] for r in channel_rows if r["channel"] in {v[1] for v in CHANNELS.values()}),
        "physical_sensor_hardware_and_exact_position_unverified": True,
        "no_recovery_outcomes_opened_or_used_for_selection": True,
        "left_edge_caveat": "First acquired local day may be a partial UTC day. Complete prior years are a verified lower bound within the acquired window, not a claim that earlier provider years were incomplete.",
        "reference_daily_definition": settings["time_zone"],
        "provisional_data_are_not_missing_data": True,
        "provisional_backup_data_are_not_approved_reference_truth": True,
    })
    C.write_json(OUT / "usgs_qualification_run_record.json", run_record(
                 {"protocol": CONFIG, "metadata_selection": selection_path, "acquisition": acquisition_path,
                  "shared_daily_implementation": C.ROOT / "scripts/388_wrr_natural_backup_validation.py"},
                 predictor_configuration_changed=False))
    print(f"[395] {len(rows)} candidate pair-years; {sum(r['record_reference_eligible'] is True for r in rows)} record-reference eligible; {sum(r['acquisition_pending'] for r in rows)} pending; physical sensor equivalence remains unverified", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["qualify"])
    parser.parse_args()
    qualify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
