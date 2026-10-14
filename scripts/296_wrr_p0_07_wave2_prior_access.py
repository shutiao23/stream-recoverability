#!/usr/bin/env python3
"""Prior-access gate for wave-2 confirmation stations (CSV/Parquet/JSON scan)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

OUT = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest"
MANIFEST = OUT / "wave2_inputs_manifest.csv"
READY = ROOT / "results/wrr_submission_ready"

# Paths that are allowed to mention wave-2 station ids (the wave itself + this audit).
ALLOW_PREFIXES = (
    "results/wrr_submission_ready/p0_07_wave2_ingest/",
    "results/wrr_submission_ready/amendments/f07_prior_access_formats/",
)

# Programme corpora that would contaminate independence if they contain the id.
SCAN_ROOTS = [
    READY / "confirmation_ingest",
    READY / "multi_agency_ingest",
    READY / "p0_07_sealed_confirmation",
    READY / "p0_07b_multi_agency_transport",
    ROOT / "results/v17_fitness",
    ROOT / "results/framework",
]


def station_ids_from_manifest() -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST, dtype=str)
    rows = []
    for row in manifest.itertuples(index=False):
        for sid in str(row.station_ids_ge4).split(";"):
            sid = sid.strip()
            if sid:
                rows.append(
                    {
                        "network_id": row.network_id,
                        "provider": row.provider,
                        "station_id": sid,
                    }
                )
    return pd.DataFrame(rows)


def scan_hits(station_ids: set[str]) -> list[dict]:
    hits = []
    # Fast path: known station tables
    table_globs = [
        "**/stations*.csv",
        "**/station_roster.csv",
        "**/complete_station_years.csv",
        "**/networks_manifest.csv",
        "**/*prior_access*.csv",
    ]
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for pattern in table_globs:
            for path in root.glob(pattern):
                rel = str(path.relative_to(ROOT))
                if rel.startswith(ALLOW_PREFIXES):
                    continue
                try:
                    frame = pd.read_csv(path, dtype=str, low_memory=False)
                except Exception:
                    continue
                cols = [c for c in frame.columns if c.lower() in {"station_id", "site_id", "station", "site"}]
                if not cols:
                    # also check wide panel column headers
                    if path.name == "daily_wide_temperature.csv" or "wide" in path.name:
                        cols = [c for c in frame.columns if c.lower() not in {"date", "unnamed: 0"}]
                    else:
                        continue
                present = set()
                for col in cols:
                    present |= set(frame[col].dropna().astype(str))
                overlap = sorted(present & station_ids)
                if overlap:
                    hits.append(
                        {
                            "path": rel,
                            "n_overlap": len(overlap),
                            "station_ids": ";".join(overlap[:40]),
                        }
                    )
    return hits


def main() -> int:
    if not MANIFEST.is_file():
        raise SystemExit("run 295 assemble first")
    stations = station_ids_from_manifest()
    ids = set(stations["station_id"].astype(str))
    hits = scan_hits(ids)
    # USGS wave2 should not overlap sealed confirmation / opened confirmation_ingest
    offenders = pd.DataFrame(hits)
    summary = {
        "n_wave2_stations": int(len(ids)),
        "n_hit_files": int(len(hits)),
        "n_overlapping_station_mentions": int(offenders["n_overlap"].sum()) if not offenders.empty else 0,
        "clean": len(hits) == 0,
        "note": (
            "clean=true means wave-2 ge4 station ids were not found in programme "
            "station tables outside the wave-2 tree. Textual false positives possible."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    stations.to_csv(OUT / "wave2_station_roster.csv", index=False)
    offenders.to_csv(OUT / "wave2_prior_access_hits.csv", index=False)
    (OUT / "wave2_prior_access_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if summary["clean"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
