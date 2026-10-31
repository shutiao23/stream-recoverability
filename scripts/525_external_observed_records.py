#!/usr/bin/env python3
"""Check the observation-only claim on additional approved USGS daily records.

The ordinary cohort CSV records the metadata-selected candidates and all
qualification failures. This is an unregistered observational corroboration,
not a new reconstruction-accuracy or climate-transfer guarantee. No imputer,
forecasting rule or threshold is fitted to these temperatures.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd
import requests

import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.national import (
    annual_source_panel,
    clean_native_features,
    native_daily_dates,
)

OUT = T.ROOT / "results/additional_usgs_observed"
DATA = T.ROOT / "data/external/additional_usgs_observed"


def approved_series(properties, zone):
    """Preserve the provider's approved daily values without heuristic censoring."""
    frame = pd.DataFrame(properties)
    frame["date"] = native_daily_dates(frame.time, zone)
    frame["value"] = pd.to_numeric(frame.value, errors="coerce")
    frame["approved"] = frame.approval_status.astype(str).str.lower().eq("approved")
    values = {}
    for date, block in frame.groupby("date", sort=True):
        unique = block.value.dropna().unique()
        values[date] = (
            float(unique[0])
            if len(unique) == 1 and block.approved.all() and np.isfinite(unique[0])
            else np.nan
        )
    return pd.Series(values, dtype=float).sort_index()


def observed_witnesses(row, approved, quality_clean):
    """Compare approved windows with every approved-complete reference year.

    The incomplete year must have a genuine absent, null, contradictory or
    unapproved day in the original provider series. An extra heuristic-QC flag
    alone cannot create a witness. Reference years retain all approved finite
    reported values, making this check stronger than using only QC-filtered
    references. One reference year defines a maximum, but not an incidence rate.
    """
    years = range(
        max(1981, int(row["first_full_year"])),
        min(2025, int(row["last_full_year"])) + 1,
    )
    references = []
    for year in years:
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
        block = approved.reindex(dates)
        if block.notna().all():
            references.append(
                (year, float(block.rolling(30, min_periods=30).mean().max()))
            )
    maximum = max((value for _, value in references), default=np.nan)
    witnesses, bounds = [], []
    for year in years:
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
        raw = approved.reindex(dates)
        if raw.notna().all():
            continue
        means = quality_clean.reindex(dates).rolling(30, min_periods=30).mean()
        if not means.notna().any():
            continue
        end = means.idxmax()
        window = pd.date_range(end - pd.Timedelta(days=29), end)
        values = approved.reindex(window)
        record = {
            "station_id": str(row["station_id"]),
            "station_name": row["monitoring_location_name"],
            "year": year,
            "huc2": str(row["hydrologic_unit_code"])[:2],
            "n_raw_complete_years": len(references),
            "reference_years": ";".join(str(y) for y, _ in references),
            "maximum_raw_complete_H30": maximum,
            "observed_window_start": str(window[0].date()),
            "observed_window_end": str(end.date()),
            "window_mean": float(values.mean()),
            "excess": float(values.mean() - maximum),
            "n_absent_or_unapproved": int(raw.isna().sum()),
            "approved_window_values": ";".join(format(v, ".12g") for v in values),
        }
        bounds.append(record)
        if np.isfinite(maximum) and values.notna().all() and record["excess"] > 1e-9:
            witnesses.append(record)
    return references, bounds, witnesses


def acquire(row, session, request_log, refresh):
    path = DATA / "raw" / (str(row["station_id"]) + ".json.gz")
    if path.exists() and not refresh:
        return json.loads(gzip.decompress(path.read_bytes()))
    params = {
        "f": "json",
        "time_series_id": row["series_id"],
        "properties": "time,value,approval_status,qualifier",
        "skipGeometry": "true",
        "limit": 50000,
        "datetime": "1980-01-01T00:00:00Z/2026-01-01T00:00:00Z",
    }
    url = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items"
    features = []
    pages = []
    while url:
        response = session.get(url, params=params, timeout=90)
        request_log.append(
            {
                "station_id": str(row["station_id"]),
                "url": response.url,
                "requested_utc": datetime.now(timezone.utc).isoformat(),
                "status": response.status_code,
                "retry_after": response.headers.get("Retry-After"),
            }
        )
        T.write_json(OUT / "acquisition.json", request_log)
        response.raise_for_status()
        document = response.json()
        features.extend(document["features"])
        pages.append(response.url)
        url = next(
            (
                link["href"]
                for link in document.get("links", [])
                if link.get("rel") == "next"
            ),
            None,
        )
        params = None
        time.sleep(4)
    document["features"] = features
    document["request_pages"] = pages
    path.write_bytes(gzip.compress(json.dumps(document).encode()))
    return document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (DATA / "raw").mkdir(parents=True, exist_ok=True)
    (DATA / "daily").mkdir(exist_ok=True)
    cohort = pd.read_csv(
        OUT / "cohort_metadata.csv",
        dtype={"station_id": str, "series_id": str, "hydrologic_unit_code": str},
    )
    requests_path = OUT / "acquisition.json"
    request_log = (
        json.loads(requests_path.read_text()) if requests_path.exists() else []
    )
    session = requests.Session()
    session.headers["User-Agent"] = "stream-recoverability observation-only research"
    key = next(
        (
            os.environ.get(name)
            for name in ["USGS_WATERDATA_API_KEY", "USGS_API_KEY"]
            if os.environ.get(name)
        ),
        None,
    )
    if key:
        session.headers["X-Api-Key"] = key
    qualification, all_bounds, witnesses, raw_summary = [], [], [], []
    for row in cohort.to_dict("records"):
        document = acquire(row, session, request_log, args.refresh)
        properties = [value.get("properties", value) for value in document["features"]]
        daily, qc = clean_native_features(row, properties)
        annual = annual_source_panel(row, daily)
        daily.to_parquet(
            DATA / "daily" / (str(row["station_id"]) + ".parquet"), index=False
        )
        complete = annual.loc[annual.complete]
        qualification.append(
            {
                "station_id": str(row["station_id"]),
                "station_name": row["monitoring_location_name"],
                "n_returned_daily": len(properties),
                "n_complete_years": len(complete),
                "complete_years": ";".join(map(str, complete.year.astype(int))),
                "eligible": len(complete) >= 4,
                "quality_summary": json.dumps(qc, default=str),
            }
        )
        approved = approved_series(properties, row.get("native_zone"))
        references, bounds, found = observed_witnesses(
            row,
            approved,
            daily.set_index("date").water_c.where(~daily.set_index("date").estimated),
        )
        all_bounds.extend(bounds)
        witnesses.extend(found)
        raw_summary.append(
            {
                "station_id": str(row["station_id"]),
                "n_raw_approved_complete_years": len(references),
                "n_robust_witness_years": len(found),
            }
        )
    pd.DataFrame(qualification).to_csv(OUT / "qualification.csv", index=False)
    pd.DataFrame(raw_summary).to_csv(OUT / "raw_reference_summary.csv", index=False)
    pd.DataFrame(all_bounds).to_csv(OUT / "all_approved_window_bounds.csv", index=False)
    pd.DataFrame(witnesses).to_csv(OUT / "robust_record_witnesses.csv", index=False)
    status = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(cohort),
        "n_acquired": len(qualification),
        "n_reconstruction_reference_eligible": sum(
            row["eligible"] for row in qualification
        ),
        "n_observed_record_comparisons": sum(
            row["n_raw_approved_complete_years"] > 0 for row in raw_summary
        ),
        "n_witness_station_years": len(witnesses),
        "n_witness_stations": len({row["station_id"] for row in witnesses}),
        "interpretation": "Additional unregistered observation-only corroboration; sparse complete reference support, tabulated in raw_reference_summary.csv. Not a random sample, incidence estimate, new imputation-accuracy validation or climate-transfer guarantee.",
    }
    T.write_json(OUT / "status.json", status)
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
