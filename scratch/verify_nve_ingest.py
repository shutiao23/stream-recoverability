#!/usr/bin/env python3
"""Verification pass over the NVE multi-agency ingest outputs (read-only).

Checks the output contract, recomputes every headline number from the written
files, and confirms the QC pipeline's own arithmetic.  Writes
``results/wrr_submission_ready/multi_agency_ingest/nve/verification.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "wrr_submission_ready" / "multi_agency_ingest" / "nve"
ROSTER = ROOT / "results" / "v17_fitness" / "step1_panel" / "station_roster.csv"
MIN_COMPLETE_YEARS = 4
MIN_STATIONS_PER_NETWORK = 2


def complete_years(series: pd.Series) -> list[int]:
    values = pd.to_numeric(series, errors="coerce")
    out = []
    for year, block in values.groupby(values.index.year):
        year = int(year)
        leap = (year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)
        need = 366 if leap else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            out.append(year)
    return out


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    report: dict = {"checks": [], "failures": []}

    def check(name: str, ok: bool, detail: object) -> None:
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["failures"].append({"check": name, "detail": detail})

    ingest = json.loads((OUT / "ingest.json").read_text())
    manifest = pd.read_csv(OUT / "networks_manifest.csv", dtype=str)
    stations = pd.read_csv(OUT / "stations.csv", dtype={"station_id": str})
    ledger = pd.read_csv(OUT / "qc_ledger.csv", dtype={"station_id": str})
    years_file = pd.read_csv(OUT / "complete_station_years.csv", dtype={"station_id": str})
    roster = pd.read_csv(ROSTER, dtype=str)
    v17_ids = set(roster["station_id"].astype(str))

    # ---- contract: one directory per network with the two files
    dirs = sorted(p.name for p in (OUT / "networks").iterdir() if p.is_dir())
    check("network_directories", dirs == sorted(manifest["network_id"]), dirs)
    for row in manifest.itertuples():
        csv = ROOT / row.daily_wide_temperature_csv
        st = ROOT / row.stations_csv
        check(f"{row.network_id}:files_exist", csv.is_file() and st.is_file(), str(csv))
        check(
            f"{row.network_id}:sha256_matches_manifest",
            sha256(csv) == row.daily_wide_temperature_sha256,
            sha256(csv),
        )

    # ---- recompute every headline number from the written panels
    n_networks = 0
    n_stations = 0
    n_station_years = 0
    wide_rows = 0
    first_columns_ok = True
    blanks_are_nan = True
    per_station_mismatch = []
    for row in manifest.itertuples():
        panel = pd.read_csv(ROOT / row.daily_wide_temperature_csv, parse_dates=["date"])
        first_columns_ok &= panel.columns[0] == "date" and "Unnamed: 0" not in panel.columns
        wide_rows += len(panel)
        station_cols = [c for c in panel.columns if c != "date"]
        if panel[station_cols].isna().to_numpy().sum() == 0:
            blanks_are_nan &= True
        # all-missing columns would mean a station was written without data
        check(
            f"{row.network_id}:no_empty_station_column",
            not (panel[station_cols].notna().sum() == 0).any(),
            station_cols,
        )
        n_networks += 1
        n_stations += len(station_cols)
        net_years = 0
        for column in station_cols:
            series = pd.to_numeric(panel.set_index("date")[column], errors="coerce")
            years = complete_years(series)
            net_years += len(years)
            recorded = stations.loc[stations.station_id.eq(column), "n_complete_years"]
            if len(recorded) != 1 or int(recorded.iloc[0]) != len(years):
                per_station_mismatch.append(
                    {"station_id": column, "written": int(recorded.iloc[0]) if len(recorded) else None,
                     "recomputed": len(years)}
                )
            if len(years) < MIN_COMPLETE_YEARS:
                per_station_mismatch.append(
                    {"station_id": column, "written": "eligible", "recomputed": len(years)}
                )
        check(
            f"{row.network_id}:station_years",
            net_years == int(row.n_complete_station_years),
            {"written": int(row.n_complete_station_years), "recomputed": net_years},
        )
        n_station_years += net_years

    check("recomputed_networks", n_networks == int(ingest["final_counts"]["networks_kept"]), n_networks)
    check("recomputed_stations", n_stations == int(ingest["final_counts"]["stations_in_kept_networks"]), n_stations)
    check(
        "recomputed_station_years",
        n_station_years == int(ingest["final_counts"]["complete_station_years_in_kept_networks"]),
        n_station_years,
    )
    check("stations_csv_rows_match_panels", len(stations) == n_stations, len(stations))
    check("stations_csv_network_id_matches_dirs", set(stations.network_id) == set(dirs), sorted(set(stations.network_id)))
    check("date_is_first_column_everywhere", first_columns_ok, first_columns_ok)
    check("per_station_year_agreement", not per_station_mismatch, per_station_mismatch)
    check(
        "every_written_station_has_ge4_years",
        stations.n_complete_years.min() >= MIN_COMPLETE_YEARS,
        int(stations.n_complete_years.min()),
    )
    check(
        "every_network_has_ge2_eligible_stations",
        stations.groupby("network_id").size().min() >= MIN_STATIONS_PER_NETWORK,
        int(stations.groupby("network_id").size().min()),
    )

    # ---- rule 6: no v17 station id anywhere in the panel
    overlap = sorted(set(stations.station_id.astype(str)) & v17_ids)
    check("no_v17_station_id_in_panel", not overlap, overlap)
    check(
        "no_svalbard_station_in_panel",
        not stations.station_id.astype(str).str.startswith("400.").any(),
        sorted(stations.loc[stations.station_id.astype(str).str.startswith("400."), "station_id"]),
    )

    # ---- complete-year definition: >=365 (366) QC-passing days
    year_counts = (
        years_file.groupby("station_id").size().rename("n_years").reset_index()
        .merge(stations[["station_id", "n_complete_years"]], on="station_id", how="outer")
    )
    mismatch = year_counts[
        year_counts.n_years.fillna(-1).astype(int) != year_counts.n_complete_years.fillna(-1).astype(int)
    ]
    check("complete_station_years_file_agrees", mismatch.empty, mismatch.to_dict("records"))

    # ---- QC arithmetic: ledger drops + accepted == raw rows for that station
    raw = pd.read_parquet(OUT / "raw_cache" / "observations_raw.parquet")
    raw_per_station = raw["station_id"].astype(str).value_counts()
    ledger_full = ledger.copy()
    ledger_full["n_values_returned"] = ledger_full["station_id"].map(raw_per_station)
    incomplete = ledger_full[ledger_full["n_values_returned"].isna()]
    check("qc_ledger_covers_every_requested_station", incomplete.empty, len(incomplete))
    arithmetic = (
        ledger_full["n_values_accepted"] + ledger_full["n_values_dropped_total"]
        == ledger_full["n_values_returned"]
    )
    check("qc_ledger_arithmetic", bool(arithmetic.all()), int((~arithmetic).sum()))
    drop_columns = [c for c in ledger.columns if c.startswith("dropped_")]
    reason_sum = ledger[drop_columns].sum().sum()
    check(
        "drop_reasons_sum_to_dropped_total",
        int(reason_sum) == int(ledger["n_values_dropped_total"].sum()),
        {"reasons": int(reason_sum), "total": int(ledger["n_values_dropped_total"].sum())},
    )
    check(
        "raw_rows_match_record",
        len(raw) == int(ingest["qc_counts"]["raw_observation_rows"]),
        len(raw),
    )

    # ---- physical plausibility of the written values (not a performance check)
    stacked = []
    for row in manifest.itertuples():
        panel = pd.read_csv(ROOT / row.daily_wide_temperature_csv, parse_dates=["date"]).set_index("date")
        stacked.append(panel.stack())
    values = pd.concat(stacked)
    report["value_sanity"] = {
        "n_values": int(len(values)),
        "min_c": float(values.min()),
        "max_c": float(values.max()),
        "mean_c": float(values.mean()),
        "n_below_zero": int((values < 0).sum()),
        "n_below_minus_0p5": int((values < -0.5).sum()),
        "n_above_30": int((values > 30).sum()),
    }
    check("values_inside_plausible_range", report["value_sanity"]["n_above_30"] == 0, report["value_sanity"])

    # ---- read-only inputs unchanged
    drift = []
    for rel, digest in ingest.get("inputs_sha256", {}).items():
        if sha256(ROOT / rel) != digest:
            drift.append(rel)
    check("read_only_inputs_unchanged", not drift, drift)

    report["summary"] = {
        "networks": n_networks,
        "stations": n_stations,
        "complete_station_years": n_station_years,
        "panel_value_rows": report["value_sanity"]["n_values"],
        "network_ids": dirs,
        "networks_with_no_v17_station": int(
            (~manifest["network_in_v17_basin"].astype(str).str.lower().eq("true")).sum()
        ),
    }
    report["ok"] = not report["failures"]
    (OUT / "verification.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report["summary"], indent=1))
    print("checks:", len(report["checks"]), "failures:", len(report["failures"]))
    for failure in report["failures"]:
        print("FAIL:", failure)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
