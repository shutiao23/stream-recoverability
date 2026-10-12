#!/usr/bin/env python3
"""Post-seal diagnostic: does the USGS confirmation hold on prior-access-clean subsets?

The primary sealed score (scripts/234) was computed once on all 39 networks and
is not re-run here. A repo-wide, provider-aware prior-access audit
(scripts/245) shows that some of those networks were used in earlier programme
iterations (framework/, development_v11/, revision_v12/, regulation_panel_*).
This script reports the same already-scored contrast restricted to

  * networks with no outcome-bearing prior use, and
  * networks with no prior use of any kind,

as a transparency diagnostic. It cannot strengthen the primary result; it can
only show whether the primary result depends on previously used networks, and
it is reported whichever way it falls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import operating_point_contrast  # noqa: E402

READY = ROOT / "results" / "wrr_submission_ready"
SEALED = READY / "p0_07_sealed_confirmation"
OUT = READY / "amendments" / "sealed_usgs_prior_access_diagnostic"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    audit = pd.read_csv(READY / "prior_access_audit_sealed_usgs.csv", dtype=str)
    audit["clean_outcome"] = audit["clean_of_outcome_use"].astype(str).eq("True")
    audit["clean_any"] = audit["never_used_repo_wide"].astype(str).eq("True")
    cases = pd.read_parquet(SEALED / "sealed_cases.parquet")
    certificates = pd.read_parquet(SEALED / "sealed_certificates.parquet")
    cases = cases.reset_index(drop=True).assign(station_id=lambda f: f["station_id"].astype(str))
    certificates = certificates.reset_index(drop=True)

    # Network-level clean means EVERY station in the network is clean.
    clean_outcome_networks = set(
        audit.groupby("network_id")["clean_outcome"].all().loc[lambda s: s].index.astype(str)
    )
    clean_all_networks = set(
        audit.groupby("network_id")["clean_any"].all().loc[lambda s: s].index.astype(str)
    )
    clean_outcome_stations = set(audit.loc[audit["clean_outcome"], "station_id"].astype(str))
    clean_all_stations = set(audit.loc[audit["clean_any"], "station_id"].astype(str))

    subsets = {
        "primary_all_39_networks": (set(audit["network_id"].astype(str)), None),
        "networks_clean_of_outcome_use": (clean_outcome_networks, None),
        "networks_clean_of_any_prior_use": (clean_all_networks, None),
        "stations_clean_of_outcome_use": (None, clean_outcome_stations),
        "stations_clean_of_any_prior_use": (None, clean_all_stations),
    }
    rows = []
    for name, (networks, stations) in subsets.items():
        if networks is not None:
            mask = cases["network_id"].astype(str).isin(networks)
        else:
            mask = cases["station_id"].isin(stations)  # type: ignore[arg-type]
        block = cases.loc[mask].reset_index(drop=True)
        sub_cert = certificates.loc[mask].reset_index(drop=True)
        if len(block) < 200:
            rows.append({"subset": name, "n_cases": int(len(block)), "note": "below 200 cases; not scored"})
            continue
        contrast = operating_point_contrast(block, sub_cert, retention=0.70, seed=0, draws=1200)
        empirical_mask = block["arm"].astype(str).eq("empirical")
        empirical = None
        if int(empirical_mask.sum()) >= 200:
            empirical = operating_point_contrast(
                block.loc[empirical_mask].reset_index(drop=True),
                sub_cert.loc[empirical_mask].reset_index(drop=True),
                retention=0.70,
                seed=0,
                draws=800,
            )
        rows.append(
            {
                "subset": name,
                "n_networks": int(block["network_id"].nunique()),
                "n_stations": int(block["station_id"].nunique()),
                "n_cases": int(len(block)),
                "pooled_contrast_points": float(contrast["point"] * 100),
                "pooled_ci_low_points": float(contrast["low"] * 100),
                "pooled_ci_high_points": float(contrast["high"] * 100),
                "empirical_contrast_points": float(empirical["point"] * 100) if empirical else None,
                "empirical_ci_low_points": float(empirical["low"] * 100) if empirical else None,
                "empirical_ci_high_points": float(empirical["high"] * 100) if empirical else None,
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "clean_subset_contrasts.csv", index=False)

    payload = {
        "status": "post_seal_transparency_diagnostic",
        "primary_score_unchanged": str((SEALED / "verdict.json").relative_to(ROOT)),
        "audit": str((READY / "prior_access_audit_sealed_usgs.csv").relative_to(ROOT)),
        "n_networks_with_outcome_prior_use": int(
            audit.loc[audit["n_outcome_artifacts"].astype(int).gt(0), "network_id"].nunique()
        ),
        "rows": rows,
        "interpretation_limit": (
            "Subsets are read from an already-sealed score, so they are a robustness diagnostic, "
            "not new confirmation. The primary verdict is not revised; the manuscript must report "
            "the contamination rate and this diagnostic."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
