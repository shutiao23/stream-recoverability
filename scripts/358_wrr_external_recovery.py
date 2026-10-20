#!/usr/bin/env python3
"""Compile new-source recovery cases while enforcing the final-test method lock."""

from __future__ import annotations

import os

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C

OUT = C.RUN / "r3_08_external_recovery"
DAILY = C.ROOT / "data/external/wrr_revision_20261020c/daily"
SOURCE = C.ROOT / "data/external/wrr_revision_20261020c/hydroshare"
ELIGIBILITY = C.RUN / "r3_06_independence_risk/external_eligibility_addendum.csv"
M351 = C.load_script("r3_external_recovery_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")


def build_external_station(job: dict, settings: dict, salt: str) -> dict:
    module = C.load_script("r3_external_worker_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    return module.build_station(job, settings, salt)


def verify_role_access(role: str) -> None:
    if role == "development":
        return
    lock_path = C.RUN / ("deployment_lock.json" if role == "test" else "method_lock.json")
    if not lock_path.exists():
        raise RuntimeError(f"External {role} recovery requires {lock_path.name} before outcome computation")
    paths = [lock_path]
    if role == "test":
        paths.append(C.RUN / "method_lock.json")
    for path in paths:
        lock = json.loads(path.read_text())
        for item in lock["inputs"].values():
            if C.digest(Path(item["path"])) != item["sha256"]:
                raise RuntimeError("Frozen implementation or model changed before external evaluation")


def source_bundles(role: str) -> tuple[list[dict], pd.DataFrame, Path]:
    metadata = pd.read_csv(ELIGIBILITY, dtype={"original_id": str})
    metadata = metadata.loc[metadata.external_role.eq(role) & metadata.eligible_after_full_input_audit]
    manifests = []
    for path in (DAILY / role).glob("*.json"):
        content = json.loads(path.read_text())
        if content.get("status") == "downloaded":
            manifests.append(content)
    manifest = pd.DataFrame(manifests)
    if manifest.empty:
        raise RuntimeError(f"No continuous daily inputs for external role {role}")
    metadata = metadata.merge(manifest[["station_ID", "daily_path", "sha256", "eligible_four_complete_years"]], on="station_ID", validate="one_to_one")
    bundle_dir = OUT / "source_bundles" / role
    bundle_dir.mkdir(parents=True, exist_ok=True)
    air = pd.read_csv(SOURCE / "CERRA_Ta", sep=None, engine="python")
    date_column = next(name for name in air if name.lower() in {"date", "datetime"})
    dates = pd.to_datetime(air[date_column], errors="raise")
    air_rows, jobs = [], []
    for group, block in metadata.groupby("independence_group"):
        parts = []
        for row in block.itertuples(index=False):
            path = Path(row.daily_path)
            if C.digest(path) != row.sha256:
                raise RuntimeError("An acquired external daily file changed after custody")
            daily = pd.read_parquet(path).set_index("date").temperature_c.rename(row.station_ID)
            parts.append(daily)
            if row.station_ID in air:
                values = pd.to_numeric(air[row.station_ID], errors="coerce").to_numpy()
                air_rows.append(pd.DataFrame({"date": dates, "station_id": row.station_ID, "network_id": group, "air_temperature_c": values}))
        panel = pd.concat(parts, axis=1).sort_index()
        destination = bundle_dir / f"{group}.csv"
        encoded = panel.rename_axis("date").to_csv().encode()
        if destination.exists():
            import hashlib

            if C.digest(destination) != hashlib.sha256(encoded).hexdigest():
                raise RuntimeError("A compiled external source bundle changed")
        else:
            temporary = destination.with_name(destination.name + f".{os.getpid()}.partial")
            temporary.write_bytes(encoded)
            temporary.replace(destination)
        checksum = C.digest(destination)
        for row in block.loc[block.eligible_four_complete_years].itertuples(index=False):
            jobs.append({"network_id": group, "station_id": row.station_ID, "provider": row.provider, "independence_group": group, "input_path": str(destination), "source_sha256": checksum, "statistic_class": "daily_mean" if row.provider == "foen" else "project_aggregated_from_subdaily", "regulation_status": "near_natural_published_selection", "split_role": f"new_external_{role}", "fit_protocol": "leave_one_year_out", "smoke": False})
    forcing = pd.concat(air_rows, ignore_index=True) if air_rows else pd.DataFrame(columns=["date", "station_id", "network_id", "air_temperature_c"])
    forcing_path = bundle_dir / "air_forcing.parquet"
    if not forcing_path.exists():
        temporary = forcing_path.with_name(forcing_path.name + f".{os.getpid()}.partial")
        forcing.to_parquet(temporary, index=False)
        temporary.replace(forcing_path)
    for job in jobs:
        job["air_input_path"] = str(forcing_path)
    return jobs, metadata, forcing_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["development", "calibration", "test"], default="development")
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--events", action="store_true")
    parser.add_argument("--real-calendars", action="store_true")
    parser.add_argument("--admission", action="store_true")
    parser.add_argument("--cofailure", type=float, choices=[0, 0.5, 1], default=0)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    settings = C.protocol()
    if sum([args.events, args.real_calendars, args.admission]) > 1:
        raise ValueError("Choose one replay design family per run")
    verify_role_access(args.role)
    jobs, metadata, forcing = source_bundles(args.role)
    family = "events" if args.events else ("real_calendars" if args.real_calendars else ("admission" if args.admission else "crossed"))
    output = OUT / args.role / args.protocol / family / f"cofailure_{args.cofailure:g}"
    output.mkdir(parents=True, exist_ok=True)
    M351.CACHE.mkdir(parents=True, exist_ok=True)
    for job in jobs:
        job["fit_protocol"] = args.protocol
        job["cofailure_fraction"] = args.cofailure
        job["design_mode"] = family
    metadata.to_csv(output / "eligible_station_metadata.csv", index=False)
    salt = C.digest(Path(__file__)) + C.digest(Path(M351.__file__)) + C.digest(forcing)
    print(f"[358] external {args.role}, {len(jobs)} stations, events={args.events}, donor cofailure={args.cofailure}", flush=True)
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(build_external_station)(job, settings, salt) for job in jobs)
    frames = [pd.read_parquet(result["cache"]) for result in results if result["cache"]]
    frames = [frame for frame in frames if len(frame)]
    if not frames:
        raise RuntimeError("No eligible external recovery case was generated")
    cases = pd.concat(frames, ignore_index=True)
    additional = metadata[["station_ID", "hydrological_stratum", "Mountain_region", "Glaciers %", "Pt as snow", "Mean elev"]].rename(columns={"station_ID": "station_id"})
    cases = cases.merge(additional, on="station_id", validate="many_to_one")
    cases.to_parquet(output / "cases.parquet", index=False)
    C.write_json(output / "summary.json", {"external_role": args.role, "fit_protocol": args.protocol, "n_cases": len(cases), "n_stations": cases.station_id.nunique(), "n_independent_groups": cases.independence_group.nunique(), "n_station_years": len(cases[["station_id", "year"]].drop_duplicates()), "cofailure_fraction": args.cofailure, "event_relative_replay": args.events, "performance_summary_computed": False})
    C.write_json(output / "jobs.json", {"jobs": jobs, "station_results": results})
    C.write_json(output / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"eligibility": ELIGIBILITY, "forcing": forcing, "recovery_core": Path(M351.__file__)}))
    print(f"[358] completed external {args.role}: {len(cases)} cases", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
