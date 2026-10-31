#!/usr/bin/env python3
"""Retain public metadata/access observations without opening temperature data."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

import pandas as pd
import requests

import wrr_r3_common as C

BASE = C.READY / "followup_20261021"
OUT = BASE / "additional_public_source_scope"
RAW = C.ROOT / "data/external/wrr_additional_sources_20261021"
PROJECT = "https://research.fs.usda.gov/rmrs/projects/norwest"
ITEM = "61dca9a7d34ed7929400c02e"
SOURCES = {
    "norwest_project.html": PROJECT,
    "norwest_processing.pdf": "https://research.fs.usda.gov/sites/default/files/2023-04/rmrs-norwest_dataprocessingprocedures.pdf",
    "norwest_archive.html": "https://www.fs.usda.gov/rds/archive/Catalog/RDS-2016-0032",
    "norwest_archive_metadata.html": "https://www.fs.usda.gov/rds/archive/products/RDS-2016-0032/_metadata_RDS-2016-0032.html",
    "norwest_point_layer.json": "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_NorWeST_ObservedPoints_01/MapServer/0?f=json",
    "ecodrought_metadata.xml": f"https://data.usgs.gov/datacatalog/metadata/USGS.{ITEM}.xml",
    "ecodrought_item_response.html": f"https://www.sciencebase.gov/catalog/item/{ITEM}?format=json",
}


class DailyLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url = None
        self.label = []
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.url = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data):
        if self.url:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "a":
            if self.url and " ".join("".join(self.label).split()) == "All Days Daily Summary":
                self.links.add(self.url)
            self.url = None


def access_state(status, content_type):
    if status != 200:
        return "request_unsuccessful_not_a_zero_observation_count"
    mime = content_type.lower().split(";")[0].strip()
    if mime in {"text/html", "application/xhtml+xml"}:
        return "html_response_not_temperature_archive"
    if mime in {"application/zip", "application/x-zip-compressed", "application/octet-stream"}:
        return "possible_archive_headers_body_and_reference_quality_unverified"
    return "response_format_requires_review"


def complete_prior_years_upper_bound(start, end):
    """Only a necessary calendar bound; never certify observed completeness."""
    complete = [year for year in range(start.year, end.year + 1)
                if start <= date(year, 1, 1) and date(year, 12, 31) <= end]
    return max((sum(year < target for year in complete)
                for target in range(start.year, end.year + 1)), default=0)


def observe(url, *, head=False, destination=None):
    method = requests.head if head else requests.get
    try:
        response = method(url, allow_redirects=True, timeout=45)
        item = {"url": url, "method": "HEAD" if head else "GET",
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "http_status": response.status_code, "content_type": response.headers.get("Content-Type", ""),
                "final_url": response.url, "content_length": response.headers.get("Content-Length"),
                "temperature_measurements_opened": False}
        if destination is not None:
            destination.write_bytes(response.content)
            item.update(path=str(destination.relative_to(C.ROOT)), bytes=len(response.content))
        return item
    except requests.RequestException as exc:
        return {"url": url, "method": "HEAD" if head else "GET",
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "http_status": None, "content_type": "", "error_type": type(exc).__name__,
                "temperature_measurements_opened": False}


def acquire():
    RAW.mkdir(parents=True, exist_ok=True)
    observations = []
    for name, url in SOURCES.items():
        observations.append(observe(url, destination=RAW / name))
    if next(row for row in observations if row["url"] == PROJECT)["http_status"] != 200:
        raise RuntimeError("The published project page could not be acquired")
    parser = DailyLinks()
    parser.feed((RAW / "norwest_project.html").read_text())
    if not parser.links or any(not url.startswith("https://www.fs.usda.gov/rm/") for url in parser.links):
        raise RuntimeError("Published daily-summary link inventory changed; review before requesting")
    with ThreadPoolExecutor(max_workers=2) as pool:
        probes = list(pool.map(lambda url: observe(url, head=True), sorted(parser.links)))
    probes.append(observe(f"https://www.sciencebase.gov/catalog/file/get/{ITEM}", head=True))
    C.write_json(RAW / "metadata_acquisition.json", {"sources": observations, "download_header_probes": probes,
                 "no_temperature_measurement_payload_requested": True, "credentials_used": False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquire", action="store_true", help="Refresh only official metadata and download headers")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.acquire:
        acquire()
    import json
    custody_path = RAW / "metadata_acquisition.json"
    custody = json.loads(custody_path.read_text())
    probes = pd.DataFrame(custody["download_header_probes"])
    probes["access_state"] = [access_state(row.http_status, row.content_type) for row in probes.itertuples()]
    probes.to_csv(OUT / "download_header_probes.csv", index=False)
    norwest = probes.loc[probes.url.str.contains("NorWeST/downloads/", regex=False)]
    layer = json.loads((RAW / "norwest_point_layer.json").read_text())
    fields = [field["name"] for field in layer["fields"]]
    metadata = ET.parse(RAW / "ecodrought_metadata.xml").getroot()
    dates = metadata.find("./idinfo/timeperd/timeinfo/rngdates")
    start, end = (datetime.strptime(dates.findtext(key), "%Y%m%d").date() for key in ["begdate", "enddate"])
    eco_sources = [row for row in custody["sources"] if "sciencebase.gov" in row["url"]]
    summary = {
        "status": "public_metadata_and_access_scope_not_new_temperature_reference",
        "NorWeST": {"published_all_days_daily_summary_links": len(norwest),
                    "header_responses_returning_HTML": int(norwest.access_state.eq("html_response_not_temperature_archive").sum()),
                    "HEAD_responses_do_not_verify_archive_body": True,
                    "observed_point_layer_fields": fields,
                    "point_layer_is_location_metadata_not_daily_temperature_truth": True,
                    "daily_Nobs_does_not_verify_distinct_hours_or_daily_time_span": True,
                    "August_coverage_rule_does_not_establish_complete_annual_H30_reference": True,
                    "modeled_scenarios_not_used_as_observed_reference": True,
                    "measurement_archives_acquired": False, "qualified_station_years": None},
        "EcoDrought": {"public_metadata_start_date": str(start), "public_metadata_end_date": str(end),
                       "optimistic_complete_prior_year_bound_within_this_archive": complete_prior_years_upper_bound(start, end),
                       "original_minimum_prior_years": 3,
                       "ScienceBase_metadata_request_status": eco_sources[0]["http_status"] if eco_sources else None,
                       "measurement_archives_acquired": False, "qualified_independent_backup_cases": None,
                       "visit_thermometer_spot_checks_do_not_establish_continuous_backup": True,
                       "derived_wet_dry_labels_are_not_independent_field_observations": True,
                       "co_location_and_instrument_custody_not_verified": True},
        "HTTP_failure_or_unknown_qualification_never_converted_to_zero_observations": True,
        "new_temperature_or_prediction_errors_opened": False,
        "no_credentials_accounts_or_outreach": True,
        "conclusion": "These public metadata and header responses do not release a usable independent reference; they do not prove that underlying observations are absent."
    }
    C.write_json(OUT / "summary.json", summary)
    C.write_json(OUT / "source_custody.json", custody)
    print(f"[423] {len(norwest)} published NorWeST daily links checked by HEAD; EcoDrought prior-year upper bound {summary['EcoDrought']['optimistic_complete_prior_year_bound_within_this_archive']}; no measurements opened", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
