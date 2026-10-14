#!/usr/bin/env python3
"""F03 diagnostic: recompute quality-checked contrast on the primary panel only.

Does not overwrite the sealed verdict. Writes an amendment showing that the
historical quality_checked gate mixed NVE secondary cases and that the true
primary quality-checked subset fails the pre-registered CI rule.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    operating_point_contrast,
)

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "f03_primary_qc_diagnostic"
DELTA_POINTS = -1.0
PRIMARY_RETENTION = 0.7


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(READY / "p0_07b_multi_agency_transport" / "transport_cases.parquet")
    certs = pd.read_parquet(
        READY / "p0_07b_multi_agency_transport" / "transport_certificates.parquet"
    )
    manifest = pd.read_csv(READY / "multi_agency_inputs_manifest.csv").drop_duplicates("network_id")
    roles = manifest.set_index("network_id")["panel_role"].astype(str)
    assurance = (
        manifest.assign(quality_assurance=manifest["quality_assurance"].astype(str).str.split(";"))
        .explode("quality_assurance")
        .drop_duplicates("network_id")
        .set_index("network_id")["quality_assurance"]
        .astype(str)
    )
    frame = cases.copy()
    frame["panel_role"] = frame["network_id"].map(roles)
    frame["quality_assurance"] = frame["network_id"].map(assurance)
    frame = frame.reset_index(drop=True)
    certs = certs.reset_index(drop=True)

    def contrast(mask: pd.Series) -> dict | None:
        block = frame.loc[mask]
        if len(block) < 200:
            return {
                "n_cases": int(len(block)),
                "n_networks": int(block["network_id"].nunique()),
                "n_stations": int(block["station_id"].nunique()),
                "below_floor": True,
            }
        sub = certs.loc[block.index]
        stat = operating_point_contrast(
            block.reset_index(drop=True),
            sub.reset_index(drop=True),
            retention=PRIMARY_RETENTION,
            seed=0,
            draws=800,
        )
        return {
            "n_cases": int(len(block)),
            "n_networks": int(block["network_id"].nunique()),
            "n_stations": int(block["station_id"].nunique()),
            "contrast_points": float(stat["point"] * 100),
            "ci_low_points": float(stat["low"] * 100),
            "ci_high_points": float(stat["high"] * 100),
            "n_candidate_cases": stat.get("n_candidate_cases"),
            "n_cert_reconstruction_failures": stat.get("n_cert_reconstruction_failures"),
            "selected_reconstruction_failure_rate": stat.get("selected_reconstruction_failure_rate"),
            "below_floor": False,
        }

    historical_qc = contrast(frame["quality_assurance"].eq("quality_checked"))
    primary = frame["panel_role"].eq("primary_new_agency")
    primary_qc = contrast(primary & frame["quality_assurance"].eq("quality_checked"))
    primary_all = contrast(primary)
    secondary = contrast(frame["panel_role"].eq("secondary_development_provider"))

    def supported(block: dict | None) -> bool:
        if not block or block.get("below_floor"):
            return False
        return bool(block["contrast_points"] <= DELTA_POINTS and block["ci_high_points"] < 0)

    # Count NVE share inside historical QC
    hist_qc_mask = frame["quality_assurance"].eq("quality_checked")
    nve_share = float(frame.loc[hist_qc_mask, "provider"].astype(str).eq("nve").mean()) if hist_qc_mask.any() else None

    report = {
        "finding": "F03",
        "historical_quality_checked_mixed_panels": historical_qc,
        "nve_share_of_historical_quality_checked": nve_share,
        "primary_panel_all": primary_all,
        "primary_quality_checked_only": primary_qc,
        "secondary_nve": secondary,
        "predeclared_rule": (
            "delta <= -1.0 pp and 95% network-clustered CI upper < 0; "
            "pooled primary and primary quality-checked-only must agree"
        ),
        "primary_pooled_supported": supported(primary_all),
        "primary_qc_supported": supported(primary_qc),
        "transport_supported_under_corrected_gate": bool(
            supported(primary_all) and supported(primary_qc)
        ),
        "verdict": (
            "fail_corrected_gate"
            if not (supported(primary_all) and supported(primary_qc))
            else "pass_corrected_gate"
        ),
        "note": (
            "Diagnostic on archived certificates; sealed verdict.json left intact. "
            "Formal confirmation remains pending after F01/F02 repairs."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
