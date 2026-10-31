#!/usr/bin/env python3
"""Qualify an additional public NEON reference cohort without selecting by error.

The source is a CC-BY author redistribution of NEON PRT half-hourly records.
ARIK was opened in a feasibility probe before this intake; the remaining site
roster was fixed from metadata before their temperatures were examined. This
is an unregistered exploratory assessment, not a blinded confirmation.
"""
from __future__ import annotations
import io
import json
from pathlib import Path
import zipfile
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
import wrr_tr_common as T

ROOT = T.ROOT
SOURCE = ROOT / "results/wrr_submission_ready/followup_20261021/public_backup_search/figshare_prt_directory.json"
OUT = ROOT / "results/wrr_review_response_20261027/external_neon"


def site_one(site, offset, length):
    reader = T.load_script("neon_public_range", ROOT / "scripts/397_wrr_public_neon_metadata.py")
    name = f"Temperature (PRT) in surface water/{site}/TSW_30min.feather"
    with zipfile.ZipFile(reader.PublicArchive(offset, length)) as z:
        raw = pd.read_feather(io.BytesIO(z.read(name)))
    positions = raw[["horizontalPosition", "verticalPosition"]].dropna().astype(str).drop_duplicates()
    if positions.empty:
        return dict(site=site, status="no_sensor_position"), pd.DataFrame()
    horizontal, vertical = positions.sort_values(["horizontalPosition", "verticalPosition"]).iloc[0]
    raw = raw.loc[raw.horizontalPosition.astype(str).eq(horizontal)
                  & raw.verticalPosition.astype(str).eq(vertical)].copy()
    raw["start"] = pd.to_datetime(raw.startDateTime, utc=True, errors="coerce")
    raw["end"] = pd.to_datetime(raw.endDateTime, utc=True, errors="coerce")
    raw["value"] = pd.to_numeric(raw.surfWaterTempMean, errors="coerce")
    valid_time = raw.start.notna() & raw.end.sub(raw.start).eq(pd.Timedelta(minutes=30))
    valid_time &= raw.start.dt.minute.isin([0, 30]) & raw.start.dt.second.eq(0)
    unique = ~raw.duplicated("start", keep=False)
    raw["good"] = valid_time & unique & raw.finalQF.eq(0) & np.isfinite(raw.value)
    raw["date"] = raw.start.dt.tz_localize(None).dt.normalize()
    raw["valid_value"] = raw.value.where(raw.good)
    daily = raw.groupby("date").agg(
        n_valid=("good", "sum"), mean_temperature=("valid_value", "mean"),
        n_rows=("start", "size"), n_duplicates=("start", lambda x: int(x.duplicated(keep=False).sum()))
    ).reset_index()
    daily["site"] = site
    daily["horizontal_position"] = horizontal
    daily["vertical_position"] = vertical
    daily["strict_temperature_c"] = daily.mean_temperature.where(daily.n_valid.eq(48))
    daily["sensitivity_temperature_c"] = daily.mean_temperature.where(daily.n_valid.ge(46))
    daily["year"] = daily.date.dt.year
    annual = daily.groupby("year").agg(
        n_strict_days=("strict_temperature_c", "count"),
        n_sensitivity_days=("sensitivity_temperature_c", "count"),
        n_reported_days=("date", "size")
    ).reset_index()
    annual["expected_days"] = annual.year.map(lambda y: 366 if pd.Timestamp(int(y), 12, 31).is_leap_year else 365)
    annual["strict_complete"] = annual.n_strict_days.eq(annual.expected_days)
    annual["sensitivity_complete"] = annual.n_sensitivity_days.eq(annual.expected_days)
    return dict(site=site, status="acquired", selected_horizontal=horizontal,
                selected_vertical=vertical, n_raw_rows=len(raw),
                n_complete_strict=int(annual.strict_complete.sum()),
                n_complete_46_of_48=int(annual.sensitivity_complete.sum()),
                strict_years=";".join(map(str, annual.loc[annual.strict_complete, "year"])),
                sensitivity_years=";".join(map(str, annual.loc[annual.sensitivity_complete, "year"])),
                release_counts=json.dumps(raw.release.value_counts(dropna=False).to_dict())), daily


def site_attempt(site, offset, length):
    try:
        return site_one(site, offset, length)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        return dict(site=site, status="unavailable", error=f"{type(exc).__name__}: {exc}",
                    n_complete_strict=np.nan, n_complete_46_of_48=np.nan), pd.DataFrame()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    directory = json.loads(SOURCE.read_text())
    sites = sorted(directory["sites"])
    # KING was independently identified in the existing metadata audit as an
    # upstream source-station overlap. Keep it in the qualification denominator.
    plan = {"sites": sites, "previously_opened_pilot": ["ARIK"],
            "excluded_from_new_station_accuracy": {"KING": "source USGS station in upstream watershed"},
            "selection": "all 24 river/stream sites in the existing public metadata directory; no prediction error selection",
            "primary_daily_reference": "48 unique valid 30-minute observations; finalQF=0; UTC day",
            "sensitivity_daily_reference": "at least 46 unique valid 30-minute observations; finalQF=0; UTC day",
            "annual_eligibility": "at least four complete calendar years; no filling of missing days",
            "source": "https://doi.org/10.6084/m9.figshare.28074452",
            "independence": "new NEON sites are exploratory and shared climate/catchments may remain dependent",
            "registration": "unregistered; ARIK was opened during feasibility before this plan"}
    plan_path = OUT / "intake_plan.json"
    if plan_path.exists() and json.loads(plan_path.read_text()) != plan:
        raise RuntimeError("Intake plan differs from the existing fixed roster")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    reader = T.load_script("neon_public_catalog", ROOT / "scripts/397_wrr_public_neon_metadata.py")
    with zipfile.ZipFile(reader.PublicArchive()) as outer:
        info = next(x for x in outer.infolist() if x.filename == directory["archive"])
        offset, length = reader.nested_offset(info), info.file_size
    results = Parallel(n_jobs=4, prefer="threads", verbose=10)(
        delayed(site_attempt)(site, offset, length) for site in sites
    )
    qualification = pd.DataFrame([r for r, _ in results])
    qualification["overlaps_source_watershed"] = qualification.site.eq("KING")
    qualification["strict_reference_eligible"] = qualification.n_complete_strict.ge(4) & ~qualification.overlaps_source_watershed
    qualification["sensitivity_reference_eligible"] = qualification.n_complete_46_of_48.ge(4) & ~qualification.overlaps_source_watershed
    qualification.to_csv(OUT / "qualification.csv", index=False)
    parts = [v for _, v in results if not v.empty]
    daily = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    daily.to_parquet(OUT / "quality_controlled_daily.parquet", index=False)
    status = {"candidates":len(sites), "acquired":int(qualification.status.eq("acquired").sum()),
              "strict_reference_eligible":int(qualification.strict_reference_eligible.sum()),
              "relaxed_reference_eligible":int(qualification.sensitivity_reference_eligible.sum()),
              "strict_reference_scope":"a UTC daily mean with all 48 half-hourly values passing NEON finalQF",
              "relaxed_scope":"at least 46 of 48 values: observed-interval average, not a fully observed day",
              "reconstruction_accuracy_evaluated":False,
              "interpretation":"qualification only; no artificial masks or recovery scores have yet been calculated"}
    (OUT / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(qualification.to_string(index=False), flush=True)
    print(json.dumps(status, indent=2), flush=True)


if __name__ == "__main__":
    main()
