#!/usr/bin/env python3
"""Acquire a metadata-selected, unregistered new-USGS reference cohort.

The roster is fixed from the existing prior-contact and NLDI audits, before
any temperature requests in this study. This exploratory intake does not
claim a preregistered or climate-independent confirmation.
"""
from __future__ import annotations
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import pandas as pd
import requests
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.national import clean_native_features

ROOT = T.ROOT
OUT = ROOT / "results/wrr_review_response_20261027/external_usgs"
SCOPE = ROOT / "results/wrr_submission_ready/followup_20261021/usgs_metadata_extension/effective_candidate_scope.csv"
CATALOG = ROOT / "data/external/wrr_usgs_new_reference_20261021/metadata/combined_daily_mean_temperature_metadata.json"
URL = "https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items"


def roster():
    scope = pd.read_csv(SCOPE, dtype=str)
    source = scope.loc[scope.not_yet_excluded_metadata_candidate.eq("True")
                       & scope.network_status.eq("complete")
                       & scope.all_component_candidate_checks_complete.eq("True")
                       & scope.same_HUC8_as_prior_record.eq("False")].copy()
    source = source.loc[pd.to_datetime(source.begin, utc=True).dt.year.le(2009)
                        & pd.to_datetime(source.end, utc=True).dt.year.ge(2024)]
    source = source.loc[~source.station_name.str.contains(
        "LAKE|RESERVOIR|CANAL|TAILRACE|DIVERSION|POWERPLANT|REGULATING", case=False, na=False)]
    prior = pd.read_csv(ROOT / "results/additional_usgs_observed/cohort_metadata.csv", dtype=str)
    source = source.loc[~source.station_id.isin(prior.station_id)]
    source = source.sort_values(["HUC2_region_proxy", "begin", "station_id"])
    source = source.drop_duplicates("provisional_network_index_component")
    source = source.groupby("HUC2_region_proxy", sort=True, group_keys=False).head(2)
    catalog = {f["id"]: f["properties"] for f in json.loads(CATALOG.read_text())["features"]}
    timezones = T.load_script("response_usgs_timezones", ROOT / "scripts/490_review_completion_national_availability.py")
    rows = []
    for r in source.to_dict("records"):
        meta = catalog[r["series_id"]]
        zone = timezones.native_zone(meta)
        rows.append(r | {"native_zone": zone, "hydrologic_unit_code": meta.get("hydrologic_unit_code"),
                         "time_zone_abbreviation": meta.get("time_zone_abbreviation"),
                         "uses_daylight_savings": meta.get("uses_daylight_savings")})
    return pd.DataFrame(rows)


def acquire(row, session, logs):
    path = OUT / "raw" / (row["station_id"] + ".json.gz")
    if path.exists():
        return json.loads(gzip.decompress(path.read_bytes()))
    params = {"f":"json", "time_series_id":row["series_id"], "properties":"time,value,approval_status,qualifier",
              "skipGeometry":"true", "limit":50000,
              "datetime":"1980-01-01T00:00:00Z/2026-01-01T00:00:00Z"}
    url, features, pages = URL, [], []
    while url:
        response = session.get(url, params=params, timeout=90)
        logs.append(dict(station_id=row["station_id"], url=response.url,
                         requested_utc=datetime.now(timezone.utc).isoformat(),
                         status=response.status_code, retry_after=response.headers.get("Retry-After")))
        (OUT / "requests.json").write_text(json.dumps(logs, indent=2) + "\n")
        response.raise_for_status()
        page = response.json()
        features.extend(page["features"])
        pages.append(response.url)
        url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
        params = None
        time.sleep(3)
    document = {"features":features, "request_pages":pages}
    path.write_bytes(gzip.compress(json.dumps(document).encode()))
    return document


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "raw").mkdir(exist_ok=True)
    (OUT / "daily").mkdir(exist_ok=True)
    candidates = roster()
    path = OUT / "cohort.csv"
    if path.exists():
        old = pd.read_csv(path, dtype=str)
        if old.series_id.tolist() != candidates.series_id.tolist():
            raise RuntimeError("Metadata-selected cohort has changed")
    else:
        candidates.to_csv(path, index=False)
    plan = {"cohort_count":len(candidates), "selection":"up to two earliest metadata-supported stations per HUC2, distinct indexed components; no known prior station or HUC8 contact; exclusion of named nonriver structures",
            "candidate_years":"1981-2025; no target temperature or prediction outcome used in selection",
            "reference":"approved nonestimated, QC-passing daily mean on every calendar day; at least four complete years",
            "scope":"unregistered exploratory new-station test; metadata-only prior-contact and river-index screens do not prove climate independence",
            "previous_protocol_change":"the prior metadata-only cohort is now opened for this narrowly scoped exploratory study; not a frozen formal-risk confirmation"}
    (OUT / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    logs_path = OUT / "requests.json"
    logs = json.loads(logs_path.read_text()) if logs_path.exists() else []
    session = requests.Session()
    session.headers["User-Agent"] = "stream-temperature reference research"
    rows = []
    for row in candidates.to_dict("records"):
        try:
            if not row["native_zone"]:
                raise ValueError("missing verified native timezone")
            document = acquire(row, session, logs)
            values = [f.get("properties", f) for f in document["features"]]
            daily, qc = clean_native_features(row, values)
            daily.loc[daily.estimated.fillna(False), "water_c"] = float("nan")
            daily.to_parquet(OUT / "daily" / (row["station_id"] + ".parquet"), index=False)
            s = daily.set_index("date").water_c
            complete = []
            for year in range(1981, 2026):
                dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
                if s.reindex(dates).notna().all():
                    complete.append(year)
            rows.append(dict(station_id=row["station_id"], status="acquired",
                             n_daily_values=len(daily), n_complete_years=len(complete),
                             complete_years=";".join(map(str, complete)), eligible=len(complete)>=4,
                             qc_summary=json.dumps(qc, default=str)))
        except (requests.RequestException, ValueError, KeyError) as exc:
            rows.append(dict(station_id=row["station_id"], status="unavailable", eligible=False,
                             reason=f"{type(exc).__name__}: {exc}"))
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 429:
                print("USGS rate limited the intake; remaining candidates stay unrequested", flush=True)
                break
        print(f"USGS {row['station_id']}: {rows[-1]['status']}", flush=True)
    qualification = candidates[["station_id", "station_name", "HUC2_region_proxy", "provisional_network_index_component"]].merge(
        pd.DataFrame(rows), on="station_id", how="left", validate="one_to_one")
    qualification["status"] = qualification.status.fillna("not_requested")
    qualification["eligible"] = qualification.eligible.fillna(False)
    qualification.to_csv(OUT / "qualification.csv", index=False)
    status = dict(n_candidates=len(candidates), n_acquired=int(qualification.status.eq("acquired").sum()),
                  n_unavailable=int(qualification.status.ne("acquired").sum()),
                  n_eligible=int(qualification.eligible.sum()), reconstruction_accuracy_evaluated=False)
    contact = OUT / "prior_contact_addendum.csv"
    if contact.exists():
        audit = pd.read_csv(contact, dtype={"station_id": str})
        status.update(new_independent_reference_eligible=0,
                      prior_contact_stations=int(audit.prior_temperature_contact.sum()),
                      interpretation="All 15 had prior national-panel contact; 10 were scored in E10. This is opened historical evidence, not independent confirmation.")
    (OUT / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2), flush=True)


if __name__ == "__main__":
    main()
