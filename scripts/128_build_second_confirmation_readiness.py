#!/usr/bin/env python3
"""Combine second-confirmation source QC and enforce arrival/domain floors."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SECOND = ROOT / "results/development_v11/second_confirmation"
PROTOCOL = ROOT / "configs/route_a_second_confirmation_protocol.yaml"


def main() -> None:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    candidates = pd.read_csv(SECOND / "candidates.csv", dtype={"site_ids": str})
    original_qc = pd.read_csv(ROOT / "results/development_v11/confirmation_qc_summary.csv")
    new_usgs_qc = pd.read_csv(SECOND / "qc_summary.csv")
    nve_candidates = pd.read_csv(SECOND / "nve/candidates.csv", dtype={"site_ids": str})
    nve_qc = pd.read_csv(SECOND / "nve/network_qc_summary.csv")
    canada_candidate_path = SECOND / "canada_candidate.csv"

    carried = candidates.loc[
        candidates["candidate_status"].eq("carried_unscored_candidate")
    ].merge(
        original_qc[["network_id", "qc_status", "complete_enough"]],
        on="network_id",
        how="left",
    )
    new_usgs = candidates.loc[
        candidates["candidate_status"].eq(
            "new_metadata_candidate_pending_daily_qc"
        )
    ].merge(
        new_usgs_qc[["network_id", "qc_status", "complete_enough"]],
        on="network_id",
        how="left",
    )
    nve = nve_candidates.merge(
        nve_qc[["network_id", "qc_status", "complete_enough"]],
        on="network_id",
        how="left",
    )
    parts = [carried, new_usgs, nve]
    if canada_candidate_path.is_file():
        canada = pd.read_csv(canada_candidate_path, dtype={"site_ids": str})
        canada_qc = pd.read_csv(
            SECOND
            / "daily_qc/networks/ccg_st_lawrence_ship_channel/"
            "network_qc_summary.csv"
        )
        parts.append(
            canada.merge(
                canada_qc[["network_id", "qc_status", "complete_enough"]],
                on="network_id",
                how="left",
            )
        )
    roster = pd.concat(parts, ignore_index=True, sort=False)
    roster["qc_status"] = roster["qc_status"].fillna("qc_not_run")
    roster["complete_enough"] = roster["complete_enough"].fillna(False).astype(bool)
    roster.to_csv(SECOND / "readiness_roster.csv", index=False)

    qualified = roster.loc[roster["qc_status"].eq("qualified")].copy()
    by_domain = qualified.groupby("domain").size().to_dict()
    requirements = protocol["providers"]["minimum_networks_by_domain"]
    domain_checks = {
        domain: {
            "required": int(required),
            "arrived": int(by_domain.get(domain, 0)),
            "passed": bool(by_domain.get(domain, 0) >= required),
        }
        for domain, required in requirements.items()
    }
    candidate_count = int(len(roster))
    qualified_count = int(len(qualified))
    candidate_pass = candidate_count >= int(protocol["candidate_floor"])
    minimum_pass = qualified_count >= int(protocol["minimum_valid_scored_networks"])
    target_pass = qualified_count >= int(protocol["target_scored_networks"][0])
    domain_pass = all(item["passed"] for item in domain_checks.values())
    summary = {
        "protocol_id": protocol["protocol_id"],
        "candidate_networks": candidate_count,
        "candidate_floor_passed": candidate_pass,
        "qualified_networks_before_scoring": qualified_count,
        "minimum_arrival_floor_passed": minimum_pass,
        "target_60_networks_arrived": target_pass,
        "qualified_by_domain": {str(key): int(value) for key, value in by_domain.items()},
        "domain_checks": domain_checks,
        "domain_composition_passed": domain_pass,
        "scoring_authorized": bool(candidate_pass and minimum_pass and domain_pass),
        "scoring_status": (
            "authorized_not_run"
            if candidate_pass and minimum_pass and domain_pass
            else "withheld_until_all_arrival_floors_pass"
        ),
    }
    (SECOND / "readiness.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
