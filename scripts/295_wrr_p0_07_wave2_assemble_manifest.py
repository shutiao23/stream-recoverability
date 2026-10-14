#!/usr/bin/env python3
"""Assemble wave-2 confirmation input manifest from ready provider panels.

Does not score. Writes hashed manifest under p0_07_wave2_ingest/.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest"
TEMP_MIN, TEMP_MAX = -5.0, 45.0
MIN_YEARS = 4
MIN_STATIONS = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def complete_years(series: pd.Series) -> list[int]:
    values = pd.to_numeric(series, errors="coerce")
    arr = values.to_numpy(dtype=float)
    arr = np.where(np.isfinite(arr) & ((arr < TEMP_MIN) | (arr > TEMP_MAX)), np.nan, arr)
    values = pd.Series(arr, index=values.index)
    years = []
    for year, block in values.groupby(values.index.year):
        expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
        finite = block.dropna()
        if len(finite) >= expected - 1 and np.isfinite(finite.to_numpy(dtype=float)).all():
            years.append(int(year))
    return years


def programme_used_station_ids() -> set[str]:
    """Station ids already used in development / opened confirmation / transport."""
    used: set[str] = set()
    paths = [
        ROOT / "results/v17_fitness/step1_panel/station_roster.csv",
        ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi/stations_all.csv",
        ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi/stations.csv",
        ROOT / "results/wrr_submission_ready/multi_agency_ingest/uk_ea/stations.csv",
        ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau/stations.csv",
        ROOT / "results/wrr_submission_ready/multi_agency_ingest/nve/stations.csv",
        ROOT / "results/wrr_submission_ready/confirmation_ingest",
    ]
    for path in paths:
        if path.is_file():
            frame = pd.read_csv(path, dtype=str, low_memory=False)
            for col in ("station_id", "site_id"):
                if col in frame.columns:
                    used |= set(frame[col].dropna().astype(str))
        elif path.is_dir():
            for csv in path.rglob("station_eligibility.csv"):
                frame = pd.read_csv(csv, dtype=str)
                if "station_id" in frame.columns:
                    used |= set(frame["station_id"].dropna().astype(str))
            for csv in path.rglob("stations.csv"):
                frame = pd.read_csv(csv, dtype=str)
                for col in ("station_id", "site_id"):
                    if col in frame.columns:
                        used |= set(frame[col].dropna().astype(str))
    return used


def context_for(provider: str, network_id: str) -> str:
    if provider == "usgs":
        digits = "".join(ch for ch in network_id if ch.isdigit())
        if "huc6" in network_id and len(digits) >= 6:
            return f"usgs_huc2_{digits[-6:-4]}"
        if len(digits) >= 2:
            return f"usgs_huc2_{digits[:2]}"
        return "usgs_unknown"
    return {
        "hubeau": "france",
        "uk_ea": "uk",
        "smhi": "sweden",
        "eccc_automated": "canada",
        "nve": "norway_secondary",
    }.get(provider, provider)


def collect_usgs(used: set[str]) -> list[dict]:
    rows = []
    nets = OUT / "networks"
    if not nets.is_dir():
        return rows
    for net_dir in sorted(nets.iterdir()):
        panel_path = net_dir / "daily_wide_temperature.csv"
        if not panel_path.is_file():
            continue
        if not str(net_dir.name).startswith("usgs_"):
            continue
        panel = pd.read_csv(panel_path, index_col=0, parse_dates=True)
        eligible = []
        for col in panel.columns:
            sid = str(col)
            if sid in used:
                continue
            years = complete_years(panel[col])
            if len(years) >= MIN_YEARS:
                eligible.append(sid)
        if len(eligible) < MIN_STATIONS:
            continue
        rows.append(
            {
                "network_id": net_dir.name,
                "provider": "usgs",
                "context": context_for("usgs", net_dir.name),
                "panel_role": "primary_new_agency",
                "n_stations_ge4": len(eligible),
                "station_ids_ge4": ";".join(sorted(eligible)),
                "input_path": str(panel_path.relative_to(ROOT)),
                "bytes": panel_path.stat().st_size,
                "sha256": sha256_file(panel_path),
            }
        )
    return rows


def collect_provider(name: str, used: set[str], *, panel_role: str = "primary_new_agency") -> list[dict]:
    rows = []
    root = OUT / name / "networks"
    if not root.is_dir():
        return rows
    for net_dir in sorted(root.iterdir()):
        panel_path = net_dir / "daily_wide_temperature.csv"
        if not panel_path.is_file():
            continue
        panel = pd.read_csv(panel_path, index_col=0, parse_dates=True)
        eligible = []
        for col in panel.columns:
            sid = str(col)
            if sid in used:
                continue
            years = complete_years(panel[col])
            if len(years) >= MIN_YEARS:
                eligible.append(sid)
        if len(eligible) < MIN_STATIONS:
            continue
        rows.append(
            {
                "network_id": net_dir.name,
                "provider": name if name != "eccc" else "eccc_automated",
                "context": context_for(name if name != "eccc" else "eccc_automated", net_dir.name),
                "panel_role": panel_role,
                "n_stations_ge4": len(eligible),
                "station_ids_ge4": ";".join(sorted(eligible)),
                "input_path": str(panel_path.relative_to(ROOT)),
                "bytes": panel_path.stat().st_size,
                "sha256": sha256_file(panel_path),
            }
        )
    return rows


def main() -> int:
    used = programme_used_station_ids()
    print(f"programme_used_stations {len(used)}", flush=True)
    rows = []
    rows.extend(collect_usgs(used))
    rows.extend(collect_provider("hubeau", used))
    rows.extend(collect_provider("uk_ea", used))
    rows.extend(collect_provider("smhi", used))
    rows.extend(collect_provider("eccc", used))
    manifest = pd.DataFrame(rows)
    if manifest.empty:
        raise SystemExit("no wave-2 ready networks")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "wave2_inputs_manifest.csv"
    manifest.to_csv(path, index=False)
    providers = sorted(manifest["provider"].unique())
    contexts = sorted(manifest["context"].unique())
    summary = {
        "n_networks": int(len(manifest)),
        "n_providers": int(len(providers)),
        "providers": providers,
        "n_contexts": int(len(contexts)),
        "contexts": contexts,
        "floors_met": bool(
            len(manifest) >= 30 and len(providers) >= 3 and len(contexts) >= 3
        ),
        "manifest_sha256": sha256_file(path),
        "scored": False,
        "note": "Wave-2 assembled manifest only; not scored.",
    }
    (OUT / "wave2_manifest_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if summary["floors_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
