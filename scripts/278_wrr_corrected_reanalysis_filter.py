#!/usr/bin/env python3
"""P0-06 interim: filter archived sealed cases for impossible truths; rescore.

This is a corrected reanalysis diagnostic on an opened panel, not a first
confirmation. Does not overwrite sealed verdict.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    operating_point_contrast,
)

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "p0_06_corrected_reanalysis"
TEMP_MIN, TEMP_MAX = -5.0, 50.0
RETENTION = 0.7


def valid_truth(series: pd.Series) -> pd.Series:
    v = pd.to_numeric(series, errors="coerce")
    return v.notna() & (v >= TEMP_MIN) & (v <= TEMP_MAX)


def score(name: str, cases: pd.DataFrame, certs: pd.DataFrame) -> dict:
    if len(cases) < 200:
        return {"panel": name, "n_cases": int(len(cases)), "below_floor": True}
    stat = operating_point_contrast(
        cases.reset_index(drop=True),
        certs.reset_index(drop=True),
        retention=RETENTION,
        seed=0,
        draws=800,
    )
    return {
        "panel": name,
        "n_cases": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "contrast_points": float(stat["point"] * 100),
        "ci_low_points": float(stat["low"] * 100),
        "ci_high_points": float(stat["high"] * 100),
        "n_cert_reconstruction_failures": stat.get("n_cert_reconstruction_failures"),
        "selected_reconstruction_failure_rate": stat.get("selected_reconstruction_failure_rate"),
        "below_floor": False,
        "evidence_type": "corrected_reanalysis_opened_panel",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    reports = {}

    # USGS sealed
    cases = pd.read_parquet(READY / "p0_07_sealed_confirmation/sealed_cases.parquet")
    certs = pd.read_parquet(READY / "p0_07_sealed_confirmation/sealed_certificates.parquet")
    mask = valid_truth(cases["truth_hottest30"])
    reports["usgs_historical_full_denom"] = score("usgs_historical_full_denom", cases, certs)
    reports["usgs_truth_plausible_only"] = score(
        "usgs_truth_plausible_only", cases.loc[mask], certs.loc[mask.to_numpy()]
    )

    # Transport primary
    tcases = pd.read_parquet(READY / "p0_07b_multi_agency_transport/transport_cases.parquet")
    tcerts = pd.read_parquet(READY / "p0_07b_multi_agency_transport/transport_certificates.parquet")
    manifest = pd.read_csv(READY / "multi_agency_inputs_manifest.csv").drop_duplicates("network_id")
    roles = manifest.set_index("network_id")["panel_role"].astype(str)
    primary = tcases["network_id"].map(roles).eq("primary_new_agency")
    tmask = valid_truth(tcases["truth_hottest30"])
    reports["transport_primary_full_denom"] = score(
        "transport_primary_full_denom", tcases.loc[primary], tcerts.loc[primary.to_numpy()]
    )
    reports["transport_primary_truth_plausible"] = score(
        "transport_primary_truth_plausible",
        tcases.loc[primary & tmask],
        tcerts.loc[(primary & tmask).to_numpy()],
    )

    summary = {
        "status": "interim_filter_reanalysis",
        "may_enter_abstract_or_conclusions": False,
        "label": "[pending — 探索期数据，不可写入结论] / corrected reanalysis only",
        "n_usgs_cases_dropped_implausible_truth": int((~mask).sum()),
        "n_transport_primary_dropped_implausible_truth": int((primary & ~tmask).sum()),
        "panels": reports,
        "note": (
            "Filtering impossible truths is necessary but not sufficient: donor "
            "training may still be contaminated. Full rebuild from sanitized daily "
            "panels remains required (rebuild_plan.json)."
        ),
    }
    (OUT / "interim_filter_rescore.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
