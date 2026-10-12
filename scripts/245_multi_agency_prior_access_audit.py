#!/usr/bin/env python3
"""Repo-wide prior-access audit for confirmation panels (F01, corrected scope).

The original P0-07 audit checked the v16/v17 ledgers only. A repo-wide scan shows
that earlier programme iterations (framework/, development_v11/, revision_v12/,
regulation_panel_*/) also contain station-level artifacts, so "never used in the
programme" has to be tested against every artifact, provider-aware, and split
into descriptive (catalogue/metadata) versus outcome-bearing
(losses/predictions/scores) use.

Populations audited:
  * sealed_usgs   -- stations of the scored USGS confirmation panel
  * multi_agency  -- stations ingested for the transport panel

Writes:
  results/wrr_submission_ready/prior_access_audit_sealed_usgs.csv
  results/wrr_submission_ready/prior_access_audit_multi_agency.csv
  results/wrr_submission_ready/prior_access_audit_summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

READY = ROOT / "results" / "wrr_submission_ready"
INGEST = READY / "multi_agency_ingest"

EXCLUDE_PARTS = (
    "wrr_submission_ready/p0_07_sealed_confirmation",
    "wrr_submission_ready/runs",
    "wrr_submission_ready/amendments",
    "wrr_submission_ready/confirmation_seal",
    "wrr_submission_ready/multi_agency_seal",
    "wrr_submission_ready/prior_access_audit",
    "confirmation_inputs_manifest",
    "confirmation_external_worksheet",
    "confirmation_ingest",
    "multi_agency_ingest",
    "multi_agency_inputs_manifest",
    "usgs_confirmation",
    "nve_confirmation",
    "confirmation_recruitment",
    "confirmation_daily_qc",
    "second_confirmation",
    "raw_cache",
)
OUTCOME_TOKENS = (
    "loss",
    "prediction",
    "predictions",
    "score",
    "scores",
    "metric",
    "metrics",
    "outcome",
    "performance",
    "residual",
    "error",
)
PROVIDER_PREFIXES = {
    "usgs": ("usgs", "huc8", "huc4", "huc2", "confirm"),
    "arso": ("arso",),
    "chmi": ("chmi",),
    "foen": ("foen",),
    "gkd_bayern": ("gkd", "bayern"),
    "lubw": ("lubw",),
    "nve_hydapi": ("nve",),
    "rws_waterwebservices": ("rws", "rijks"),
    "syke": ("syke",),
    "smhi": ("smhi",),
    "hubeau": ("hubeau", "france"),
    "ehyd": ("ehyd",),
    "uk_ea": ("uk_ea", "ukea", "ea_"),
}


def infer_provider(network_id: str, provider_column: str = "") -> str | None:
    text = f"{provider_column} {network_id}".lower()
    if provider_column:
        for provider, tokens in PROVIDER_PREFIXES.items():
            if any(token in provider_column.lower() for token in tokens):
                return provider
    for provider, tokens in PROVIDER_PREFIXES.items():
        if any(text.startswith(token) or f"_{token}" in text or text.startswith(f"{token}_") for token in tokens):
            return provider
    return None


def scan_artifacts() -> list[dict[str, str]]:
    """Every (artifact, provider, network_id, station_id) row in repo CSVs."""

    rows: list[dict[str, str]] = []
    paths = sorted(Path(ROOT).glob("results/**/*.csv")) + sorted(Path(ROOT).glob("metadata/**/*.csv"))
    for path in paths:
        text = str(path).replace(str(ROOT) + "/", "")
        if any(part in text for part in EXCLUDE_PARTS):
            continue
        try:
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or "station_id" not in reader.fieldnames:
                    continue
                has_provider = "provider" in reader.fieldnames
                has_network = "network_id" in reader.fieldnames
                for row in reader:
                    station = str(row.get("station_id") or "").strip()
                    if not station:
                        continue
                    network = str(row.get("network_id") or "") if has_network else ""
                    provider = str(row.get("provider") or "") if has_provider else ""
                    rows.append(
                        {
                            "artifact": text,
                            "provider": infer_provider(network, provider) or "",
                            "network_id": network,
                            "station_id": station,
                            "use_class": "outcome_bearing"
                            if any(token in path.stem.lower() for token in OUTCOME_TOKENS)
                            else "descriptive",
                        }
                    )
        except (OSError, csv.Error, UnicodeDecodeError):
            continue
    return rows


def population_stations(population: str) -> dict[str, dict[str, str]]:
    """station_id -> {provider, network_id} for the population under audit."""

    out: dict[str, dict[str, str]] = {}
    if population == "sealed_usgs":
        import pandas as pd

        cases = pd.read_parquet(READY / "p0_07_sealed_confirmation/sealed_cases.parquet")
        for (network, station), _ in cases.groupby(["network_id", "station_id"]):
            out[str(station)] = {"provider": "usgs", "network_id": str(network)}
    elif population == "multi_agency":
        for stations_csv in sorted(INGEST.glob("*/stations.csv")):
            provider = stations_csv.parent.name
            with stations_csv.open(newline="") as handle:
                for row in csv.DictReader(handle):
                    station = str(row.get("station_id") or "").strip()
                    if station:
                        out[station] = {
                            "provider": provider,
                            "network_id": str(row.get("network_id") or ""),
                        }
    else:
        raise ValueError(population)
    return out


def audit(population: str, artifacts: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    stations = population_stations(population)
    rows: list[dict[str, object]] = []
    for station, meta in sorted(stations.items()):
        provider = meta["provider"]
        hits = [
            row
            for row in artifacts
            if row["station_id"] == station and (row["provider"] in ("", provider))
        ]
        outcome = sorted({row["artifact"] for row in hits if row["use_class"] == "outcome_bearing"})
        descriptive = sorted({row["artifact"] for row in hits if row["use_class"] == "descriptive"})
        rows.append(
            {
                "population": population,
                "provider": provider,
                "network_id": meta["network_id"],
                "station_id": station,
                "n_outcome_artifacts": len(outcome),
                "n_descriptive_artifacts": len(descriptive),
                "outcome_artifacts": ";".join(outcome[:4]),
                "descriptive_artifacts": ";".join(descriptive[:4]),
                "never_used_repo_wide": len(hits) == 0,
                "clean_of_outcome_use": len(outcome) == 0,
            }
        )
    n = len(rows)
    by_network: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_network.setdefault(str(row["network_id"]), []).append(row)
    clean_networks = [
        network
        for network, group in by_network.items()
        if all(bool(row["clean_of_outcome_use"]) for row in group)
    ]
    never_used_networks = [
        network
        for network, group in by_network.items()
        if all(bool(row["never_used_repo_wide"]) for row in group)
    ]
    summary = {
        "population": population,
        "n_stations": n,
        "n_networks": len(by_network),
        "n_never_used_repo_wide": sum(1 for r in rows if r["never_used_repo_wide"]),
        "n_clean_of_outcome_use": sum(1 for r in rows if r["clean_of_outcome_use"]),
        "n_with_outcome_use": sum(1 for r in rows if r["n_outcome_artifacts"]),
        # Network-level: a network counts as clean only if every station is clean.
        "n_networks_never_used_repo_wide": len(never_used_networks),
        "n_networks_clean_of_outcome_use": len(clean_networks),
        "n_networks_with_any_outcome_use": len(by_network) - len(clean_networks),
        "clean_networks": sorted(clean_networks),
        "never_used_networks": sorted(never_used_networks),
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", default="all", choices=("sealed_usgs", "multi_agency", "all"))
    args = parser.parse_args()
    artifacts = scan_artifacts()
    populations = ["sealed_usgs", "multi_agency"] if args.population == "all" else [args.population]
    summaries = {}
    for population in populations:
        rows, summary = audit(population, artifacts)
        path = READY / f"prior_access_audit_{population}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        summaries[population] = summary | {"path": str(path.relative_to(ROOT))}
        print(json.dumps(summary, indent=2, sort_keys=True))
    payload = {
        "n_artifact_rows_scanned": len(artifacts),
        "n_artifacts_scanned": len({row['artifact'] for row in artifacts}),
        "populations": summaries,
        "scope_note": (
            "Repo-wide scan of every CSV carrying a station_id column, provider-aware by "
            "network/provider prefix. 'descriptive' artifacts are catalogues and metadata; "
            "'outcome_bearing' artifacts contain losses, predictions, scores or metrics. "
            "Provider station catalogues keyed by site_id (e.g. results/framework/public_catalog/"
            "ehyd_surface_temperature_stations.csv) carry no series values and are outside this "
            "scan by construction; they are metadata, not series use. Nested files under the "
            "excluded confirmation/transport directories belong to the panels under audit."
        ),
    }
    (READY / "prior_access_audit_summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
