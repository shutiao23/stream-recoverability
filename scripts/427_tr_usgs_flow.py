#!/usr/bin/env python3
"""TR-E1b: USGS daily discharge (00060, mean) and site metadata for the opened USGS stations.

Responses are cached verbatim so the flow table can be rebuilt offline.
Discharge enters only the missingness audit and flow-state strata.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

RAW = T.ROOT / "data/external/wrr_target_recovery_20261021/usgs"
OUT = T.OUT / "e1_archive"
DV = "https://waterservices.usgs.gov/nwis/dv/?format=rdb&sites={site}&parameterCd=00060&statCd=00003&startDT=1979-01-01&endDT=2026-09-30"
SITE = "https://waterservices.usgs.gov/nwis/site/?format=rdb&sites={sites}&siteOutput=expanded&siteStatus=all"
AGENT = {"User-Agent": "stream-recoverability target-recovery audit (research use)"}


def fetch(url: str, path: Path, retries: int = 4) -> Path:
    if path.exists() and path.stat().st_size:
        return path
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=180) as response:
                payload = response.read()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            path.with_suffix(path.suffix + ".url").write_text(url + "\n")
            return path
        except urllib.error.HTTPError as error:
            if error.code == 404:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"# HTTP 404: no data\n")
                return path
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Failed: {url}")


def read_rdb(path: Path) -> pd.DataFrame:
    lines = [line for line in path.read_text(errors="replace").splitlines() if line and not line.startswith("#")]
    if len(lines) < 2:
        return pd.DataFrame()
    return pd.read_csv(io.StringIO("\n".join([lines[0]] + lines[2:])), sep="\t", dtype=str)


def parse_flow(site: str, path: Path) -> pd.DataFrame:
    frame = read_rdb(path)
    if frame.empty or "datetime" not in frame:
        return pd.DataFrame(columns=["site", "date", "flow_cms", "flow_code"])
    value_columns = [name for name in frame if name.endswith("_00060_00003")]
    if not value_columns:
        return pd.DataFrame(columns=["site", "date", "flow_cms", "flow_code"])
    # Prefer the series with most numeric values when a site publishes several.
    counts = {name: pd.to_numeric(frame[name], errors="coerce").notna().sum() for name in value_columns}
    column = max(counts, key=counts.get)
    values = pd.to_numeric(frame[column], errors="coerce") * 0.0283168
    return pd.DataFrame({"site": site, "date": pd.to_datetime(frame["datetime"]), "flow_cms": values, "flow_code": frame.get(column + "_cd", "")})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    roster = T.roster()
    sites = sorted(roster.loc[roster.provider.eq("usgs"), "station_id"].astype(str).unique())
    print(f"[427] {len(sites)} USGS sites", flush=True)
    site_paths = []
    for start in range(0, len(sites), 80):
        chunk = sites[start : start + 80]
        site_paths.append(fetch(SITE.format(sites=",".join(chunk)), RAW / "site" / f"sites_{start:04d}.rdb"))
    metadata = pd.concat([read_rdb(path) for path in site_paths], ignore_index=True)
    metadata = metadata.loc[metadata.agency_cd.eq("USGS")].drop_duplicates("site_no")
    keep = ["site_no", "station_nm", "dec_lat_va", "dec_long_va", "alt_va", "huc_cd", "drain_area_va", "state_cd"]
    metadata = metadata[[name for name in keep if name in metadata]]
    metadata["huc2"] = metadata.huc_cd.astype(str).str[:2]
    with ThreadPoolExecutor(args.workers) as pool:
        paths = list(pool.map(lambda site: fetch(DV.format(site=site), RAW / "dv" / f"{site}.rdb"), sites))
    flows = pd.concat([parse_flow(site, path) for site, path in zip(sites, paths)], ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    flows.to_parquet(OUT / "usgs_flow.parquet", index=False)
    metadata.to_csv(OUT / "usgs_site_metadata.csv", index=False)
    manifest = pd.DataFrame(
        [{"path": str(path.relative_to(T.ROOT)), "bytes": path.stat().st_size} for path in site_paths + paths]
    )
    manifest.to_csv(RAW / "manifest.csv", index=False)
    summary = {
        "n_sites": len(sites), "n_sites_with_metadata": int(metadata.site_no.nunique()),
        "n_sites_with_flow": int(flows.dropna(subset=["flow_cms"]).site.nunique()), "n_flow_days": int(flows.flow_cms.notna().sum()),
        "huc2_counts": metadata.huc2.value_counts().to_dict(),
    }
    T.write_json(OUT / "usgs_flow_summary.json", summary)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
