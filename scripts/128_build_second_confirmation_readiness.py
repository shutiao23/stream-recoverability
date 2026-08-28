#!/usr/bin/env python3
"""Combine second-confirmation source QC and enforce arrival/domain floors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.second_confirmation_guard import (
    build_authorized_readiness,
)

SECOND = ROOT / "results/development_v11/second_confirmation"
PROTOCOL = ROOT / "configs/route_a_second_confirmation_protocol.yaml"
AMENDMENT = ROOT / "configs/route_a_second_confirmation_amendment_v2.yaml"
FROZEN_ROSTER = SECOND / "frozen_scoring_roster_v2.csv"


def main() -> None:
    candidates = pd.read_csv(SECOND / "candidates.csv", dtype={"site_ids": str})
    original_qc = pd.read_csv(
        ROOT / "results/development_v11/confirmation_qc_summary.csv"
    )
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
        candidates["candidate_status"].eq("new_metadata_candidate_pending_daily_qc")
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
            SECOND / "daily_qc/networks/ccg_st_lawrence_ship_channel/"
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
    summary = build_authorized_readiness(
        root=ROOT,
        protocol_path=PROTOCOL,
        amendment_path=AMENDMENT,
        readiness_roster_path=SECOND / "readiness_roster.csv",
        frozen_roster_path=FROZEN_ROSTER,
    )
    (SECOND / "readiness.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
