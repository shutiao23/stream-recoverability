#!/usr/bin/env python3
"""Is the headline driven by the largest agencies?

The pooled contrast weights cases equally, and the panel is not balanced: one
provider contributes 56 of the 110 development networks and the network sizes
differ by an order of magnitude. The bootstrap clusters by network, which fixes
the interval but not the point estimate. This recomputes the contrast with each
network, each station and each provider weighted equally, and reports the
per-network distribution so a reader can see whether the result is carried by a
few places.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP4_CEILING,
    STEP6_SCREEN,
)

STEP19 = RESULTS_ROOT / "step19_weighting"
RETENTION = 0.70
PANELS = {
    "development": (STEP4_CEILING / "development_cases.parquet", STEP6_SCREEN / "development_certificates.parquet"),
    "reserved": (STEP10_CONFIRM / "reserved_cases.parquet", STEP10_CONFIRM / "reserved_certificates.parquet"),
}


def contrast_within(block: pd.DataFrame) -> float:
    """Screen each unit separately and contrast inside it, then average."""

    k = max(1, int(round(RETENTION * len(block))))
    certificate = block.nsmallest(k, "cert_score")["cert_error"].to_numpy()
    length = block.nsmallest(k, "length")["policy_error"].to_numpy()
    return float((certificate > PRIMARY_TOLERANCE_C).mean() - (length > PRIMARY_TOLERANCE_C).mean())


def main() -> int:
    STEP19.mkdir(parents=True, exist_ok=True)
    rows = []
    per_network_frames = []
    for panel, (case_path, cert_path) in PANELS.items():
        cases = pd.read_parquet(case_path).reset_index(drop=True)
        cert = pd.read_parquet(cert_path).reset_index(drop=True)
        rng = np.random.default_rng(31)
        frame = cases[["network_id", "station_id", "provider"]].copy()
        frame["length"] = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy() + rng.random(len(cases))
        frame["policy_error"] = pd.to_numeric(cases["abserr_policy"], errors="coerce")
        frame["cert_score"] = pd.to_numeric(cert["certificate_bound"], errors="coerce")
        frame["cert_error"] = pd.to_numeric(cert["certificate_abs_error"], errors="coerce")
        frame = frame.dropna(subset=["policy_error", "cert_error", "cert_score"])

        pooled = cluster_bootstrap(frame, contrast_within, draws=1200, seed=0)
        rows.append({"panel": panel, "weighting": "case-equal (pooled)", **{k: pooled[k] for k in ("point", "low", "high")}})

        for unit in ("network_id", "station_id", "provider"):
            values = {
                key: contrast_within(block)
                for key, block in frame.groupby(unit, sort=True)
                if len(block) >= 40
            }
            per_unit = pd.Series(values, name="contrast")
            per_unit.index.name = unit
            if unit == "network_id":
                per_network_frames.append(per_unit.reset_index().assign(panel=panel))
            stat = cluster_bootstrap(
                per_unit.reset_index().assign(network_id=lambda f: f[unit]),
                lambda f: float(pd.to_numeric(f["contrast"], errors="coerce").mean()),
                draws=1200,
                seed=0,
            )
            rows.append(
                {
                    "panel": panel,
                    "weighting": f"{unit.replace('_id', '')}-equal",
                    "point": stat["point"],
                    "low": stat["low"],
                    "high": stat["high"],
                    "n_units": int(len(per_unit)),
                }
            )

    table = pd.DataFrame(rows)
    table[["point", "low", "high"]] = table[["point", "low", "high"]] * 100
    table.to_csv(STEP19 / "weighting.csv", index=False)
    per_network = pd.concat(per_network_frames, ignore_index=True)
    per_network["contrast_points"] = per_network["contrast"] * 100
    per_network.to_csv(STEP19 / "per_network_contrast.csv", index=False)

    distribution = {}
    for panel, block in per_network.groupby("panel"):
        values = block["contrast_points"]
        distribution[panel] = {
            "n_networks": int(len(values)),
            "median": float(values.median()),
            "share_favouring_certificate": float((values < 0).mean()),
            "q90": float(values.quantile(0.90)),
            "worst": float(values.max()),
        }
    (STEP19 / "summary.json").write_text(json.dumps(distribution, indent=2), encoding="utf-8")

    lines = ["# Step 19 — is the headline carried by the largest agencies?", ""]
    lines.append("Contrast in percentage points; negative favours the certificate.")
    lines.append("")
    lines.append(table.round(3).to_string(index=False))
    lines.append("")
    lines.append("## Distribution over individual networks")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(distribution, indent=2))
    lines.append("```")
    (STEP19 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(table.round(3).to_string(index=False))
    print()
    print(json.dumps(distribution, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
