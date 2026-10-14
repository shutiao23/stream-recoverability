#!/usr/bin/env python3
"""Expand P0-07 wave-2 USGS: restore full-state catalog, HUC6 nets, near-miss fills."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import importlib.util  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

spec = importlib.util.spec_from_file_location("w2", ROOT / "scripts/287_wrr_p0_07_wave2_usgs_recruit.py")
w2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w2)

OUT = w2.OUT
ALL_STATES = sorted(set(w2.WAVE2_STATES) | {"de", "nj", "ct", "ma", "vt", "nh", "ri"})


def recompute_ready(rows: list[dict]) -> dict:
    ready = [
        r
        for r in rows
        if r.get("ok")
        and int(r.get("n_stations_ge4") or 0) >= 2
        and not str(r["network_id"]).endswith("_0000")
    ]
    summary = {
        "status": "wave2_partial_ingest",
        "scored": False,
        "n_attempted": len(rows),
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
        "catalog": "results/wrr_submission_ready/p0_07_wave2_ingest/wave2_catalog.csv",
        "candidates": "results/wrr_submission_ready/p0_07_wave2_ingest/wave2_candidate_networks.csv",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def choose_huc6(catalog: pd.DataFrame, burned_huc4: set[str], burned_net: set[str]) -> pd.DataFrame:
    work = catalog.loc[catalog["span_years"].fillna(0) >= 4].copy()
    work["huc6"] = work["huc"].map(lambda h: "".join(ch for ch in str(h) if ch.isdigit()).zfill(8)[:6])
    rows = []
    for huc6, block in work.groupby("huc6"):
        if len(huc6) < 6:
            continue
        huc4 = huc6[:4]
        net_id = f"usgs_wave2_huc6_{huc6}"
        if net_id in burned_net:
            continue
        # Prefer HUC6 only when HUC4 was not already ready (avoid double-count same basin)
        if huc4 in burned_huc4:
            continue
        if len(block) < 2:
            continue
        top = block.sort_values("span_years", ascending=False).head(6)
        rows.append(
            {
                "network_id": net_id,
                "huc4": huc4,
                "huc6": huc6,
                "n_catalog_sites": int(len(block)),
                "site_ids": ";".join(top["site_id"].map(w2.pad_site)),
                "states": ",".join(sorted(set(top["state_cd"].astype(str)))),
                "median_span_years": float(top["span_years"].median()),
            }
        )
    return pd.DataFrame(rows).sort_values(["n_catalog_sites", "median_span_years"], ascending=False)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-catalog", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cat_path = OUT / "wave2_catalog.csv"
    if args.skip_catalog and cat_path.is_file() and cat_path.stat().st_size > 1000:
        catalog = pd.read_csv(cat_path, dtype={"site_id": str, "huc": str, "huc4": str})
        catalog["site_id"] = catalog["site_id"].map(w2.pad_site)
        catalog["huc4"] = catalog["huc"].map(w2.pad_huc4)
        print(f"catalog reused: {len(catalog)} sites / {catalog['state_cd'].nunique()} states", flush=True)
    else:
        print("re-cataloging", ALL_STATES, flush=True)
        catalog = w2.catalog_states(ALL_STATES, 0.3)
        catalog["site_id"] = catalog["site_id"].map(w2.pad_site)
        catalog["huc4"] = catalog["huc"].map(w2.pad_huc4)
        catalog.to_csv(cat_path, index=False)
        print(f"catalog restored: {len(catalog)} sites / {catalog['state_cd'].nunique()} states", flush=True)

    prev = pd.read_csv(OUT / "wave2_download_results.csv")
    # coerce site id columns in eligibility files later
    rows = prev.to_dict("records")
    done = set(prev["network_id"].astype(str))
    ready_huc4 = set()
    for nid in json.loads((OUT / "summary.json").read_text())["ready_network_ids"]:
        digits = "".join(ch for ch in str(nid) if ch.isdigit())
        if digits:
            ready_huc4.add(digits[:4].zfill(4) if "huc6" not in nid else digits[:4])

    # Burn only HUC4s already attempted in wave2 or ready; keep programme-used
    # HUC4s out of choose_networks via used_huc4s, but do not over-burn from
    # noisy digit extraction on non-wave2 ids.
    burned = set(w2.used_huc4s()) | set(ready_huc4)
    for nid in done:
        if str(nid).startswith("usgs_wave2_") and "huc6" not in str(nid):
            digits = "".join(ch for ch in str(nid) if ch.isdigit())
            if len(digits) >= 4:
                burned.add(digits[-4:].zfill(4))

    # HUC4 candidates not yet attempted
    huc4_nets = w2.choose_networks(catalog, burned)
    if huc4_nets.empty:
        huc4_nets = pd.DataFrame(
            columns=["network_id", "huc4", "n_catalog_sites", "site_ids", "states", "median_span_years"]
        )
    huc4_nets.to_csv(OUT / "wave2_candidate_networks.csv", index=False)
    new_huc4 = huc4_nets.loc[~huc4_nets["network_id"].astype(str).isin(done)] if len(huc4_nets) else huc4_nets
    print(f"new HUC4 candidates: {len(new_huc4)} (burned_huc4={len(burned)})", flush=True)
    for row in new_huc4.head(25).itertuples(index=False):
        sites = [w2.pad_site(s) for s in str(row.site_ids).split(";")[:5]]
        print("download", row.network_id, flush=True)
        rows.append(w2.download_network(row.network_id, sites, 0.3))
        done.add(row.network_id)

    # Near-miss fill: 1 ge4 station → pull remaining span>=3 sites
    cur = pd.DataFrame(rows)
    near = cur.loc[(cur["ok"] == True) & (cur["n_stations_ge4"].fillna(0) == 1)]  # noqa: E712
    for row in near.itertuples(index=False):
        huc4 = "".join(ch for ch in str(row.network_id) if ch.isdigit())[-4:].zfill(4)
        if "huc6" in str(row.network_id):
            continue
        block = catalog.loc[
            (catalog["huc4"] == huc4) & (catalog["span_years"].fillna(0) >= 3)
        ].sort_values("span_years", ascending=False)
        panel = OUT / "networks" / row.network_id / "daily_wide_temperature.csv"
        have = set()
        if panel.is_file():
            have = {w2.pad_site(c) for c in pd.read_csv(panel, nrows=0).columns if c != "date"}
        sites = [s for s in block["site_id"].map(w2.pad_site) if s not in have][:8]
        if not sites:
            continue
        print("near-miss fill", row.network_id, len(sites), flush=True)
        tmp_id = f"{row.network_id}_fill"
        w2.download_network(tmp_id, sites, 0.25)
        tmp = OUT / "networks" / tmp_id / "daily_wide_temperature.csv"
        if not tmp.is_file():
            continue
        wide_new = pd.read_csv(tmp, parse_dates=["date"]).set_index("date")
        wide_new.columns = [w2.pad_site(c) for c in wide_new.columns]
        if panel.is_file():
            wide_old = pd.read_csv(panel, parse_dates=["date"]).set_index("date")
            wide_old.columns = [w2.pad_site(c) for c in wide_old.columns]
            wide = wide_old.join(wide_new, how="outer", rsuffix="_dup")
            wide = wide.loc[:, ~wide.columns.str.endswith("_dup")]
        else:
            wide = wide_new
        wide.sort_index().to_csv(panel)
        elig = []
        for site_id in wide.columns:
            col = pd.to_numeric(wide[site_id], errors="coerce")
            years = []
            for year in sorted({int(y) for y in col.index.year}):
                idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
                vals = col.reindex(idx).to_numpy(dtype=float)
                if len(vals) >= 365 and np.isfinite(vals).all():
                    if -5 <= float(np.min(vals)) <= float(np.max(vals)) <= 50:
                        years.append(year)
            elig.append(
                {
                    "network_id": row.network_id,
                    "station_id": site_id,
                    "n_complete_years": len(years),
                    "complete_years": ";".join(map(str, years)),
                }
            )
        elig_df = pd.DataFrame(elig)
        elig_df.to_csv(panel.parent / "station_eligibility.csv", index=False)
        ge4 = elig_df.loc[elig_df.n_complete_years >= 4]
        for i, rec in enumerate(rows):
            if rec["network_id"] == row.network_id:
                rows[i] = {
                    "network_id": row.network_id,
                    "ok": True,
                    "path": str(panel.relative_to(ROOT)),
                    "sha256": w2.sha256(panel),
                    "bytes": panel.stat().st_size,
                    "n_stations": int(wide.shape[1]),
                    "n_stations_ge4": int(len(ge4)),
                    "station_ids_ge4": ";".join(ge4.station_id.astype(str)),
                    "errors": [],
                }
                print(" ->", row.network_id, "ge4", len(ge4), flush=True)
                break
        import shutil

        shutil.rmtree(OUT / "networks" / tmp_id, ignore_errors=True)

    # Refresh ready huc4 after fills
    summary = recompute_ready(rows)
    ready_huc4 = set()
    for nid in summary["ready_network_ids"]:
        digits = "".join(ch for ch in str(nid) if ch.isdigit())
        if digits:
            ready_huc4.add(digits[:4].zfill(4))

    # HUC6 expansion for basins not ready at HUC4
    huc6 = choose_huc6(catalog, ready_huc4 | burned, done)
    huc6.to_csv(OUT / "wave2_huc6_candidates.csv", index=False)
    print(f"HUC6 candidates: {len(huc6)}", flush=True)
    for row in huc6.head(20).itertuples(index=False):
        sites = [w2.pad_site(s) for s in str(row.site_ids).split(";")[:5]]
        print("download", row.network_id, flush=True)
        rows.append(w2.download_network(row.network_id, sites, 0.3))
        done.add(row.network_id)

    pd.DataFrame(rows).to_csv(OUT / "wave2_download_results.csv", index=False)
    summary = recompute_ready(rows)
    print(json.dumps({k: summary[k] for k in ("n_attempted", "n_ready_ge2_stations_ge4_years", "floors_met")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
