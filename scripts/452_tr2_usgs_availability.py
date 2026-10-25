#!/usr/bin/env python3
"""TR2-M4a: eligibility of new USGS stations from availability metadata only.

The 155 candidates retained by the earlier USGS intake (no prior cache contact,
not excluded by known network connections) are queried on the USGS OGC API
for the dates on which an approved daily mean water temperature exists, using
``properties=time,approval_status``. No temperature value is requested or
stored. From these dates alone the script derives complete years, real gap
calendars, a missingness stratum, donor networks (same HUC8) and conservative
independence groups (HUC8 joined with the intake's network components), which
decide whether a test is possible (gate 2).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import wrr_tr_common as T

SCOPE = T.ROOT / "results/wrr_submission_ready/followup_20261021/usgs_metadata_extension/effective_candidate_scope.csv"
RAW = T.ROOT / "data/external/wrr_target_recovery_20261022/usgs_new/availability"
OUT = T.OUT / "e10_sealed_usgs"
API = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items"
AGENT = {"User-Agent": "stream-recoverability target-recovery availability audit (research use)"}


def fetch_dates(series_id: str) -> list[dict]:
    path = RAW / f"{series_id}.json"
    if path.exists():
        return json.loads(path.read_text())["features"]
    url = f"{API}?f=json&time_series_id={series_id}&properties=time,approval_status&skipGeometry=true&limit=10000"
    features, pages = [], []
    while url:
        for attempt in range(8):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=180) as response:
                    document = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                wait = int(error.headers.get("Retry-After", 30)) if error.code == 429 else 10 * (attempt + 1)
                time.sleep(min(wait, 600))
            except (urllib.error.URLError, TimeoutError):
                time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"Availability request failed: {url}")
        # Only dates and approval status are kept; the request never asks for values.
        page = [{"time": item["properties"]["time"], "approval_status": item["properties"].get("approval_status")} for item in document.get("features", [])]
        features += page
        pages.append(url)
        # The service keeps offering a "next" link after the last page; stop at an empty or short page.
        url = next((link["href"] for link in document.get("links", []) if link.get("rel") == "next"), None)
        if not page or len(page) < 10000 or len(pages) >= 30:
            url = None
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"series_id": series_id, "requests": pages, "features": features}) + "\n")
    return features


def runs(missing: np.ndarray) -> list[tuple[int, int]]:
    starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
    ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
    return [(int(s) + 1, int(e - s)) for s, e in zip(starts, ends)]


def station_availability(row: dict) -> tuple[dict, list[dict]]:
    features = fetch_dates(row["series_id"])
    approved = sorted({item["time"][:10] for item in features if str(item.get("approval_status", "")).lower() == "approved"})
    any_status = {item["time"][:10] for item in features}
    summary = {"station_id": row["station_id"], "series_id": row["series_id"], "n_dates": len(any_status), "n_approved": len(approved)}
    calendars = []
    if not approved:
        return {**summary, "n_complete_years": 0}, calendars
    dates = pd.DatetimeIndex(approved)
    first, last = dates.min(), dates.max()
    index = pd.date_range(f"{first.year}-01-01", f"{last.year}-12-31", freq="D")
    present = pd.Series(False, index=index)
    present.loc[dates] = True
    complete, incomplete = [], []
    for year in range(first.year, last.year + 1):
        block = present.loc[str(year)]
        if block.all():
            complete.append(year)
        elif first.year < year < last.year and block.any():
            incomplete.append(year)
            calendars.append({"station_id": row["station_id"], "year": year, "runs": ";".join(f"{s}:{n}" for s, n in runs(~block.to_numpy()))})
    active_years = [year for year in range(first.year + 1, last.year)]
    summary.update({
        "first_approved": str(first.date()), "last_approved": str(last.date()), "n_complete_years": len(complete),
        "complete_years": ";".join(map(str, complete)), "n_incomplete_active_years": len(incomplete),
        "incomplete_share_active": float(len(incomplete) / len(active_years)) if active_years else np.nan,
        "missing_fraction_active": float(1 - present.loc[str(first.year + 1) : str(last.year - 1)].mean()) if active_years else np.nan,
        "n_provisional_or_other": int(len(any_status) - len(approved)),
    })
    return summary, calendars


def union_groups(frame: pd.DataFrame) -> pd.Series:
    """Conservative independence groups: stations sharing a HUC8 or an intake network component are joined."""

    parent = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def join(a, b):
        parent[find(a)] = find(b)

    for row in frame.itertuples(index=False):
        station = f"s:{row.station_id}"
        join(station, f"h:{row.HUC8}")
        if isinstance(row.provisional_network_index_component, str) and row.provisional_network_index_component:
            join(station, f"c:{row.provisional_network_index_component}")
    roots = {station: find(f"s:{station}") for station in frame.station_id}
    labels = {root: f"usgsnew_g{index:03d}" for index, root in enumerate(sorted(set(roots.values())))}
    return frame.station_id.map(lambda station: labels[roots[station]])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    settings = T.settings()
    scope = pd.read_csv(SCOPE, dtype=str)
    candidates = scope.loc[scope.not_yet_excluded_metadata_candidate.eq("True")].copy()
    candidates["HUC8"] = candidates.HUC8.str.zfill(8)
    print(f"[452] {len(candidates)} retained candidates", flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(station_availability, candidates[["station_id", "series_id"]].to_dict("records")))
    availability = pd.DataFrame([summary for summary, _ in results])
    calendars = pd.DataFrame([item for _, items in results for item in items])
    roster = candidates.merge(availability, on=["station_id", "series_id"], how="left")
    roster["group_all"] = union_groups(roster)
    roster["network_id"] = "usgsnew_" + roster.HUC8
    # HUC is stored with and without its leading zero; the zero-padded HUC8 carries the region reliably.
    roster["huc2"] = roster.HUC8.str[:2]
    roster["eligible"] = roster.n_complete_years.fillna(0).astype(int) >= settings["sealed_min_complete_years"]
    roster["missingness_stratum"] = np.where(roster.incomplete_share_active >= 0.5, "high", "low")
    OUT.mkdir(parents=True, exist_ok=True)
    roster.to_csv(OUT / "availability_roster.csv", index=False)
    calendars.to_csv(OUT / "availability_calendars.csv", index=False)
    eligible = roster.loc[roster.eligible]
    groups = eligible.group_all.nunique()
    gate = "full" if groups >= settings["sealed_min_groups_full"] else ("descriptive" if groups >= settings["sealed_min_groups_descriptive"] else "no_test")
    raw_files = [str(path.relative_to(T.ROOT)) for path in sorted(RAW.glob("*.json"))]
    summary = {
        "n_candidates": len(roster), "n_with_approved_dates": int((roster.n_approved.fillna(0) > 0).sum()),
        "n_eligible_stations": int(len(eligible)), "n_eligible_complete_years": int(eligible.n_complete_years.sum()),
        "n_independence_groups_eligible": int(groups), "n_huc2_eligible": int(eligible.huc2.nunique()),
        "n_networks_eligible": int(eligible.network_id.nunique()), "missingness_strata": eligible.missingness_stratum.value_counts().to_dict(),
        "gate_2": gate, "values_requested": False,
        "statement": "Only dates with an approved daily mean and their approval status were retrieved; no water-temperature value was requested, stored or summarised.",
        "raw_files": raw_files,
    }
    T.write_json(OUT / "availability_summary.json", summary)
    print({key: value for key, value in summary.items() if key != "raw_files"}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
