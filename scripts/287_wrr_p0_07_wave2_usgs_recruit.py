#!/usr/bin/env python3
"""P0-07 wave-2 USGS recruitment: states never used in the opened confirmation wave.

The batch1/batch2 confirmation_ingest panels (including leftover unscored
networks) belong to an already-opened recruitment wave and must not be scored
as first confirmation. This script catalogs daily-mean temperature sites from
*new* states, groups by zero-padded HUC4, downloads a small site set per
network into ``p0_07_wave2_ingest/``, and audits complete years with −999999
already mapped to NA.

Does not score. Floors (≥30 nets / ≥3 providers / ≥3 contexts) still require
non-USGS providers in later steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.data.nwis_temperature import (  # noqa: E402
    nwis_daily_temperature,
    nwis_state_daily_temperature_catalog,
)

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "p0_07_wave2_ingest"
CACHE = ROOT / "data" / "public_rivers" / "nwis_wave2"

# States queried in usgs_confirmation_recruitment_pilot_summary.json — burned.
PILOT_STATES = {
    "ak", "me", "ny", "nc", "tn", "nm", "az", "wa", "or", "id", "mt", "wy",
    "co", "ut", "nv", "ca", "tx", "fl", "mn", "wi",
}
# Fresh states for wave-2 (continental US remainder with likely stream T).
WAVE2_STATES = [
    "va", "sc", "ga", "al", "ms", "la", "ar", "ok", "ks", "ne", "sd", "nd",
    "ia", "il", "in", "oh", "pa", "wv", "ky", "md", "mo", "mi",
]


def pad_site(site_id: object) -> str:
    text = "".join(ch for ch in str(site_id).strip() if ch.isdigit())
    return text.zfill(8) if text else ""


def pad_huc4(huc: object) -> str:
    text = "".join(ch for ch in str(huc).strip() if ch.isdigit())
    if len(text) >= 4:
        return text[:4].zfill(4)
    return text.zfill(4)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def used_huc4s() -> set[str]:
    used: set[str] = set()
    for rel in (
        "results/v17_fitness/step1_panel/station_roster.csv",
        "results/wrr_submission_ready/usgs_confirmation_provisional_networks.csv",
        "results/wrr_submission_ready/usgs_confirmation_networks_merged.csv",
    ):
        path = ROOT / rel
        if not path.is_file():
            continue
        frame = pd.read_csv(path)
        col = "network_id" if "network_id" in frame.columns else "provisional_network_id"
        for value in frame[col].astype(str):
            digits = "".join(ch for ch in value if ch.isdigit())
            if len(digits) >= 4:
                used.add(digits[-4:].zfill(4) if "confirm" in value else digits[:4].zfill(4))
                if "confirm_" in value:
                    used.add(digits.zfill(4)[-4:])
    for path in (READY / "confirmation_ingest").rglob("daily_wide_temperature.csv"):
        digits = "".join(ch for ch in path.parent.name if ch.isdigit())
        if digits:
            used.add(digits.zfill(4)[-4:])
    return used


def complete_years(series: pd.Series) -> list[int]:
    years = []
    for year, block in series.groupby(series.index.year):
        values = pd.to_numeric(block, errors="coerce")
        expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
        if len(values) >= expected - 1 and values.notna().all() and np.isfinite(values.to_numpy(dtype=float)).all():
            # Reject absurd °C after noData mapping.
            if float(values.min()) < -5 or float(values.max()) > 50:
                continue
            years.append(int(year))
    return years


def catalog_states(states: list[str], pause: float) -> pd.DataFrame:
    frames = []
    for state in states:
        try:
            table = nwis_state_daily_temperature_catalog(state)
        except Exception as exc:  # noqa: BLE001
            print(f"catalog {state}: FAIL {exc}", flush=True)
            time.sleep(pause)
            continue
        if table.empty:
            print(f"catalog {state}: 0 sites", flush=True)
            time.sleep(pause)
            continue
        table = table.copy()
        table["state_cd"] = state
        table["site_id"] = table["site_id"].map(pad_site)
        table["huc4"] = table["huc"].map(pad_huc4)
        print(f"catalog {state}: {len(table)} sites", flush=True)
        frames.append(table)
        time.sleep(pause)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates("site_id")


def choose_networks(catalog: pd.DataFrame, burned: set[str], min_sites: int = 2) -> pd.DataFrame:
    work = catalog.loc[catalog["span_years"].fillna(0) >= 4].copy()
    rows = []
    for huc4, block in work.groupby("huc4"):
        if not huc4 or huc4 in burned:
            continue
        if len(block) < min_sites:
            continue
        block = block.sort_values("span_years", ascending=False)
        top = block.head(6)
        rows.append(
            {
                "network_id": f"usgs_wave2_{huc4}",
                "huc4": huc4,
                "n_catalog_sites": int(len(block)),
                "site_ids": ";".join(top["site_id"].astype(str)),
                "states": ",".join(sorted(set(top["state_cd"].astype(str)))),
                "median_span_years": float(top["span_years"].median()),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["n_catalog_sites", "median_span_years"], ascending=False)


def download_network(network_id: str, site_ids: list[str], pause: float) -> dict:
    net_dir = OUT / "networks" / network_id
    net_dir.mkdir(parents=True, exist_ok=True)
    series = {}
    errors = []
    for site_id in site_ids:
        try:
            frame = nwis_daily_temperature(
                site_id,
                start="1980-01-01",
                end="2025-12-31",
                cache_dir=CACHE.parent,
            )
            # cache path uses nwis/; wave2 uses same function cache under public_rivers
            if frame.empty:
                errors.append({"site_id": site_id, "error": "empty"})
                continue
            s = frame.set_index("date")["temperature_c"]
            s.index = pd.to_datetime(s.index)
            series[site_id] = s
        except Exception as exc:  # noqa: BLE001
            errors.append({"site_id": site_id, "error": str(exc)[:240]})
        time.sleep(pause)
    if not series:
        return {"network_id": network_id, "ok": False, "errors": errors}
    wide = pd.DataFrame(series).sort_index()
    path = net_dir / "daily_wide_temperature.csv"
    wide.to_csv(path)
    eligibility = []
    for site_id in wide.columns:
        col = pd.to_numeric(wide[site_id], errors="coerce")
        years: list[int] = []
        for year in sorted(set(int(y) for y in col.index.year)):
            idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
            vals = col.reindex(idx).to_numpy(dtype=float)
            if len(vals) >= 365 and np.isfinite(vals).all():
                if float(np.min(vals)) < -5 or float(np.max(vals)) > 50:
                    continue
                years.append(int(year))
        eligibility.append(
            {
                "network_id": network_id,
                "station_id": site_id,
                "n_complete_years": len(years),
                "complete_years": ";".join(str(y) for y in years),
            }
        )
    elig = pd.DataFrame(eligibility)
    elig.to_csv(net_dir / "station_eligibility.csv", index=False)
    ge4 = elig.loc[elig["n_complete_years"] >= 4]
    return {
        "network_id": network_id,
        "ok": True,
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "n_stations": int(wide.shape[1]),
        "n_stations_ge4": int(len(ge4)),
        "station_ids_ge4": ";".join(ge4["station_id"].astype(str)),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-networks", type=int, default=40)
    parser.add_argument("--sites-per-network", type=int, default=4)
    parser.add_argument("--pause", type=float, default=0.35)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--states", default=",".join(WAVE2_STATES))
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    states = [s.strip().lower() for s in args.states.split(",") if s.strip()]
    overlap = sorted(set(states) & PILOT_STATES)
    if overlap:
        raise SystemExit(f"refusing pilot/opened states in wave2: {overlap}")

    burned = used_huc4s()
    catalog = catalog_states(states, args.pause)
    if catalog.empty:
        raise SystemExit("empty wave2 catalog")
    catalog_path = OUT / "wave2_catalog.csv"
    catalog.to_csv(catalog_path, index=False)
    networks = choose_networks(catalog, burned)
    networks_path = OUT / "wave2_candidate_networks.csv"
    networks.to_csv(networks_path, index=False)
    print(f"candidates: {len(networks)} (burned huc4={len(burned)})", flush=True)

    if args.catalog_only or networks.empty:
        summary = {
            "status": "catalog_only" if args.catalog_only else "no_candidates",
            "n_catalog_sites": int(len(catalog)),
            "n_candidate_networks": int(len(networks)),
            "states": states,
            "scored": False,
            "floors_met": False,
            "note": "Wave-2 USGS only; need ≥2 more providers before score.",
        }
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        return 0

    results = []
    for row in networks.head(args.max_networks).itertuples(index=False):
        site_ids = str(row.site_ids).split(";")[: args.sites_per_network]
        print(f"download {row.network_id} sites={site_ids}", flush=True)
        results.append(download_network(row.network_id, site_ids, args.pause))

    ready = [r for r in results if r.get("ok") and int(r.get("n_stations_ge4") or 0) >= 2]
    pd.DataFrame(results).to_csv(OUT / "wave2_download_results.csv", index=False)
    summary = {
        "status": "wave2_partial_ingest",
        "scored": False,
        "n_attempted": len(results),
        "n_ready_ge2_stations_ge4_years": len(ready),
        "design_floor_networks": 30,
        "floors_met": False,
        "providers_in_wave": ["usgs"],
        "ready_network_ids": [r["network_id"] for r in ready],
        "note": (
            "Opened confirmation_ingest leftovers must not be merged into this "
            "wave for a first-confirmation score. Add ≥2 non-USGS providers and "
            "reach ≥30 networks before sealing a score."
        ),
        "catalog": str(catalog_path.relative_to(ROOT)),
        "candidates": str(networks_path.relative_to(ROOT)),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
