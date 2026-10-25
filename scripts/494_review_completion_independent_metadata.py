#!/usr/bin/env python3
"""Qualify the fixed Horizons candidate collection without opening water values."""
from __future__ import annotations

import concurrent.futures
import argparse
import json
import re
from datetime import datetime, timezone

import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.independent import (
    complete_hot_years_in_span, fetch_metadata,
)

OUT = T.ROOT / "results/wrr_review_completion_20261024/independent_study/horizons_metadata"
ENDPOINT = "https://envirodata.horizons.govt.nz/api/hilltop/data"


def main():
    global OUT, ENDPOINT
    parser=argparse.ArgumentParser()
    parser.add_argument("--agency",choices=["horizons","greater_wellington"],default="horizons")
    args=parser.parse_args()
    if args.agency=="greater_wellington":
        OUT=OUT.parent/"greater_wellington"
        ENDPOINT="https://hilltop.gw.govt.nz/Data.hts"
    cache = OUT / "requests"
    if args.agency=="horizons":
        collections = fetch_metadata(ENDPOINT, cache, "CollectionList")
        sites = sorted({i.findtext("SiteName") for c in collections.findall("Collection")
                        if c.get("Name") == "WaterTemperature" for i in c.findall("Item")})
    else:
        listing=fetch_metadata(ENDPOINT,cache,"SiteList",Measurement="Water Temperature",Location="LatLong")
        sites=sorted(s.get("Name") for s in listing.findall("Site"))
    if not sites:
        raise RuntimeError("The predefined WaterTemperature metadata collection is absent")

    def qualify(site):
        info = fetch_metadata(ENDPOINT, cache, "SiteInfo", Site=site).find("Site")
        fields = {} if info is None else {e.tag: (e.text or "").strip() for e in info}
        measurements = fetch_metadata(ENDPOINT, cache, "MeasurementList", Site=site, Units="Yes")
        rows = []
        for ds in measurements.findall("DataSource"):
            for measurement in ds.findall("Measurement"):
                if measurement.get("Name") != "Water Temperature":
                    continue
                start, end = ds.findtext("From"), ds.findtext("To")
                span = complete_hot_years_in_span(start, end)
                continuous = (ds.findtext("TSType") == "StdSeries" and
                              ds.findtext("Interpolation") in {"Instant", "Average"} and
                              measurement.findtext("Units") in {"°C", "degC", "C"} and
                              measurement.find("VM") is None)
                # Unknown physical types do not become qualified river sites.
                excludes = bool(re.search(r"\b(lake|lagoon|drain|beach|estuary|bore)\b", site, re.I))
                if args.agency=="horizons":
                    river_metadata = bool(fields.get("RiverNumber") and fields.get("NZReach") and fields.get("Catchment"))
                    group=fields.get("Catchment")
                else:
                    river_metadata=bool(fields.get("RiverNumber") and fields.get("RiverName") and fields.get("SurfaceWaterZone"))
                    # Deliberately merge tributaries and even distinct rivers
                    # within one agency surface-water management zone. It is
                    # not an inferred number of independent catchments.
                    group=fields.get("SurfaceWaterZone")
                reason = ("not_continuous_temperature" if not continuous else
                          "nonriver_or_ambiguous_name_excluded" if excludes else
                          "river_connectivity_metadata_unresolved" if not river_metadata else
                          "fewer_than_four_calendar_supported_hot_years" if span < 4 else
                          "metadata_potential_only_requires_registered_value_QC")
                rows.append({"site": site, "datasource": ds.get("Name"),
                             "measurement": measurement.findtext("RequestAs"),
                             "series_type": ds.findtext("TSType"), "interpolation": ds.findtext("Interpolation"),
                             "units": measurement.findtext("Units"), "from": start, "to": end,
                             "calendar_supported_hot_years": span, "continuous_series": continuous,
                             "catchment": fields.get("Catchment"), "river_number": fields.get("RiverNumber"),
                             "river_name":fields.get("RiverName"),"surface_water_zone":fields.get("SurfaceWaterZone"),
                             "conservative_group":group,
                             "nz_reach": fields.get("NZReach"), "reach_version": fields.get("NZReachVersion"),
                             "latitude": fields.get("Latitude"), "longitude": fields.get("Longitude"),
                             "license": fields.get("DataLicense"), "metadata_status": reason,
                             "potentially_eligible": continuous and not excludes and river_metadata and span >= 4})
        if not rows:
            rows.append({"site": site, "metadata_status": "no_exact_continuous_water_temperature_measurement",
                         "potentially_eligible": False})
        return rows

    rows, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(qualify, site): site for site in sites}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                rows.extend(future.result())
            except Exception as error:
                errors.append({"site": futures[future], "error": str(error)})
            print(f"metadata sites {index}/{len(sites)}", flush=True)
    frame = pd.DataFrame(rows).sort_values(["site", "metadata_status"])
    frame.to_csv(OUT / "series_qualification.csv", index=False)
    potential = frame.loc[frame.potentially_eligible.fillna(False)].copy()
    potential.to_csv(OUT / "potential_roster.csv", index=False)
    T.write_json(OUT / "qualification_summary.json", {
        "updated_utc": datetime.now(timezone.utc).isoformat(), "endpoint": ENDPOINT,
        "agency":args.agency,"collection": "WaterTemperature" if args.agency=="horizons" else "exact Water Temperature SiteList", "collection_sites": len(sites), "series_rows": len(frame),
        "potentially_eligible_sites": potential.site.nunique(),
        "potentially_eligible_catchments": potential.catchment.nunique() if "catchment" in potential else 0,
        "potential_conservative_groups":potential.conservative_group.nunique() if "conservative_group" in potential else 0,
        "metadata_status_counts": frame.metadata_status.value_counts().to_dict(), "errors": errors,
        "all_sites_resolved": not errors, "temperature_observations_requested": False,
        "grouping_status": "Horizons Catchment is a conservative starting group" if args.agency=="horizons" else "Greater Wellington SurfaceWaterZone conservatively merges rivers; management-zone counts do not establish independent or exchangeable errors",
        "interpretation": "Calendar span is necessary, not proof of four complete hot years. A zero eligible roster is a metadata-eligibility failure, not a failed predictive test.",
    })
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
