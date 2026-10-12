#!/usr/bin/env python3
"""P0-07 extension: seal the multi-agency transport panel before scoring.

Scans results/wrr_submission_ready/multi_agency_ingest/<provider>/networks/,
applies the pre-registered structural eligibility rule, hashes every input
panel, and writes the manifest + seal. Refuses to seal if any station has prior
use in the v17/v18 programme (see scripts/245).

Never scores anything. Scoring is scripts/250, single shot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

READY = ROOT / "results" / "wrr_submission_ready"
INGEST = READY / "multi_agency_ingest"
MANIFEST = READY / "multi_agency_inputs_manifest.csv"
SEAL = READY / "multi_agency_seal.json"
PROTOCOL = READY / "MULTI_AGENCY_TRANSPORT_PROTOCOL.md"
FREEZE = READY / "P0_06_method_freeze.json"
MIN_COMPLETE_YEARS = 4

#: Providers whose networks enter the secondary (development-provider) stratum.
SECONDARY_PROVIDERS = {"nve", "nve_hydapi"}
#: Providers excluded from the seal even though panels exist (documented in the protocol).
EXCLUDED_PROVIDERS = {"roea_es", "saih_ebro", "waterinfo_be", "ehyd"}

CONTEXT = {
    "smhi": "boreal_nordic",
    "nve": "boreal_atlantic",
    "nve_hydapi": "boreal_atlantic",
    "hubeau": "temperate_oceanic_continental",
    "ehyd": "alpine_continental",
    "uk_ea": "temperate_oceanic",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def complete_years(series: pd.Series) -> list[int]:
    values = pd.to_numeric(series, errors="coerce")
    years: list[int] = []
    for year, block in values.groupby(values.index.year):
        need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            years.append(int(year))
    return years


def measurement_by_station(provider_dir: Path) -> dict[str, dict[str, str]]:
    path = provider_dir / "stations.csv"
    if not path.is_file():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            station = str(row.get("station_id") or "").strip()
            if station:
                out[station] = {
                    "statistic": str(row.get("measurement_statistic") or "undocumented"),
                    "assurance": str(row.get("quality_assurance") or "quality_checked"),
                }
    return out


def build_manifest() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for provider_dir in sorted(p for p in INGEST.glob("*") if p.is_dir()):
        provider = provider_dir.name
        if provider.startswith("_") or provider in EXCLUDED_PROVIDERS:
            continue
        if not (provider_dir / "networks").is_dir():
            continue
        # Prefer the uniform QC pass (scripts/253) when it exists.
        qc_root = provider_dir / "networks_qc"
        panel_root = qc_root if qc_root.is_dir() and any(qc_root.iterdir()) else provider_dir / "networks"
        measures = measurement_by_station(provider_dir)
        for network_dir in sorted(panel_root.glob("*")):
            panel_path = network_dir / "daily_wide_temperature.csv"
            if not panel_path.is_file():
                continue
            panel = pd.read_csv(panel_path, parse_dates=["date"]).set_index("date")
            panel = panel.apply(pd.to_numeric, errors="coerce").sort_index()
            panel.columns = [str(c) for c in panel.columns]
            eligible: list[str] = []
            for station in panel.columns:
                if len(complete_years(panel[station])) >= MIN_COMPLETE_YEARS:
                    eligible.append(station)
            if len(eligible) < 2:
                # Pre-registered rule: network needs >=2 stations with >=4 complete years.
                continue
            rows.append(
                {
                    "network_id": network_dir.name,
                    "provider": provider,
                    "context": CONTEXT.get(provider, "unclassified"),
                    "n_stations_ge4": len(eligible),
                    "station_ids_ge4": ";".join(sorted(eligible)),
                    "input_path": str(panel_path.relative_to(ROOT)),
                    "bytes": panel_path.stat().st_size,
                    "sha256": sha256_file(panel_path),
                    "source_root": "multi_agency_transport",
                    "panel_role": (
                        "secondary_development_provider"
                        if provider in SECONDARY_PROVIDERS
                        else "primary_new_agency"
                    ),
                    "measurement_statistic": ";".join(
                        sorted({measures.get(s, {}).get("statistic", "undocumented") for s in eligible})
                    ),
                    "quality_assurance": ";".join(
                        sorted({measures.get(s, {}).get("assurance", "quality_checked") for s in eligible})
                    ),
                }
            )
    return rows


def seal(directory: Path, manifest_rows: list[dict[str, object]]) -> list[Path]:
    if not PROTOCOL.is_file():
        raise FileNotFoundError("pre-registered protocol missing")
    if SEAL.is_file():
        existing = json.loads(SEAL.read_text())
        if existing.get("scored"):
            raise RuntimeError("multi-agency seal already scored; refuse to re-seal")
    prior_path = READY / "prior_access_audit_multi_agency.csv"
    if not prior_path.is_file():
        raise RuntimeError("run scripts/245_multi_agency_prior_access_audit.py first")
    import pandas as _pd

    prior_frame = _pd.read_csv(prior_path, dtype=str)
    primary = prior_frame.loc[~prior_frame["provider"].isin(SECONDARY_PROVIDERS)]
    secondary = prior_frame.loc[prior_frame["provider"].isin(SECONDARY_PROVIDERS)]
    # Primary stratum (Amendment 1): every station never used anywhere in the
    # programme. Secondary stratum (Amendment 3): no outcome-bearing prior use,
    # because the provider took part in development by construction.
    if primary.empty or not primary["never_used_repo_wide"].astype(str).eq("True").all():
        offenders = primary.loc[
            ~primary["never_used_repo_wide"].astype(str).eq("True"),
            ["provider", "station_id", "outcome_artifacts", "descriptive_artifacts"],
        ]
        raise RuntimeError(
            "repo-wide prior-access audit found primary-stratum stations already used in the "
            "programme; remove them before sealing:\n" + offenders.head(20).to_string(index=False)
        )
    if not secondary.empty and not secondary["clean_of_outcome_use"].astype(str).eq("True").all():
        offenders = secondary.loc[
            ~secondary["clean_of_outcome_use"].astype(str).eq("True"),
            ["provider", "station_id", "outcome_artifacts"],
        ]
        raise RuntimeError(
            "secondary-stratum stations have outcome-bearing prior use:\n"
            + offenders.head(20).to_string(index=False)
        )
    prior = json.loads((READY / "prior_access_audit_summary.json").read_text()) if (
        READY / "prior_access_audit_summary.json"
    ).is_file() else {"audit": str(prior_path.relative_to(ROOT))}
    if not manifest_rows:
        raise RuntimeError("no eligible multi-agency networks found")

    fields = list(manifest_rows[0].keys())
    with MANIFEST.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest_rows)

    providers = sorted({str(r["provider"]) for r in manifest_rows})
    contexts = sorted({str(r["context"]) for r in manifest_rows})
    station_years = 0
    for row in manifest_rows:
        panel = pd.read_csv(ROOT / str(row["input_path"]), parse_dates=["date"]).set_index("date")
        panel = panel.apply(pd.to_numeric, errors="coerce")
        for station in str(row["station_ids_ge4"]).split(";"):
            station_years += len(complete_years(panel[station]))

    document = {
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "sealed_for_design_not_scored",
        "protocol_path": str(PROTOCOL.relative_to(ROOT)),
        "protocol_sha256": sha256_file(PROTOCOL),
        "freeze_path": str(FREEZE.relative_to(ROOT)),
        "freeze_sha256": sha256_file(FREEZE),
        "manifest_path": str(MANIFEST.relative_to(ROOT)),
        "manifest_sha256": sha256_file(MANIFEST),
        "n_networks": len(manifest_rows),
        "n_providers": len(providers),
        "providers": providers,
        "n_contexts": len(contexts),
        "contexts": contexts,
        "n_station_years_complete": int(station_years),
        "eligibility_rule": ">=2 stations with >=4 complete calendar years per agency network",
        "measurement_assurance": sorted({str(r["measurement_statistic"]) for r in manifest_rows}),
        "assurance_strata": sorted({str(r["quality_assurance"]) for r in manifest_rows}),
        "prior_access": prior,
        "scored": False,
        "note": (
            "Transport test designed after the USGS confirmation score (disclosed in the protocol). "
            "Score once with scripts/250; no retuning afterwards."
        ),
    }
    SEAL.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps(document, indent=2, sort_keys=True))
    return [MANIFEST, SEAL]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    if not args.seal:
        raise SystemExit("refusing to write a seal without --seal")
    rows = build_manifest()
    directory = READY / "runs" / f"seal_multi_agency_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    directory.mkdir(parents=True, exist_ok=True)
    for path in seal(directory, rows):
        (directory / path.name).write_bytes(path.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
