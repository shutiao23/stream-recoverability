#!/usr/bin/env python3
"""Was the incumbent handicapped?

A referee is entitled to ask whether the length rule looks bad because it was
paired with a weak reconstruction. This pairs it with every reconstruction in
the study, including one that is not deployable at all: an oracle that picks
the best estimator for each case with perfect hindsight. If the certificate
still wins against that, the advantage is in the screening axis rather than in
the reconstruction.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import frontier_for_score  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP4_CEILING,
    STEP6_SCREEN,
)

STEP15 = RESULTS_ROOT / "step15_baseline_strength"
RETENTION = 0.70

PANELS = {
    "development": (STEP4_CEILING / "development_cases.parquet", STEP6_SCREEN / "development_certificates.parquet"),
    "reserved": (STEP10_CONFIRM / "reserved_cases.parquet", STEP10_CONFIRM / "reserved_certificates.parquet"),
}


def main() -> int:
    STEP15.mkdir(parents=True, exist_ok=True)
    rows = []
    contrasts = {}
    for panel, (case_path, cert_path) in PANELS.items():
        cases = pd.read_parquet(case_path).reset_index(drop=True)
        cert = pd.read_parquet(cert_path).reset_index(drop=True)
        rng = np.random.default_rng(5)
        length = pd.Series(
            pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy() + rng.random(len(cases)),
            index=cases.index,
        )
        pairings = {
            "information-conditioned policy (used in the paper)": cases["abserr_policy"],
            "always donor ridge, else climatology": cases["abserr_donor_ridge"].fillna(cases["abserr_doy_climatology"]),
            "always smooth climatology": cases["abserr_smooth_climatology"],
            "oracle over methods (NOT deployable)": cases["abserr_oracle_method"],
        }
        for name, error in pairings.items():
            frame = frontier_for_score(length, error)
            at70 = frame.loc[frame["retention"].eq(RETENTION)].iloc[0]
            rows.append(
                {
                    "panel": panel,
                    "screen": "outage-length rule",
                    "reconstruction": name,
                    "rate_above_0.5_at_70": float(at70[f"rate_above_{PRIMARY_TOLERANCE_C}"]),
                    "mean_abs_error_at_70": float(at70["mean_abs_error_c"]),
                    "retain_all_rate": float((pd.to_numeric(error, errors="coerce") > PRIMARY_TOLERANCE_C).mean()),
                }
            )
        frame = frontier_for_score(cert["certificate_bound"], cert["certificate_abs_error"])
        at70 = frame.loc[frame["retention"].eq(RETENTION)].iloc[0]
        rows.append(
            {
                "panel": panel,
                "screen": "certificate",
                "reconstruction": "deployable estimators, chosen by the certificate",
                "rate_above_0.5_at_70": float(at70[f"rate_above_{PRIMARY_TOLERANCE_C}"]),
                "mean_abs_error_at_70": float(at70["mean_abs_error_c"]),
                "retain_all_rate": float((pd.to_numeric(cert["certificate_abs_error"], errors="coerce") > PRIMARY_TOLERANCE_C).mean()),
            }
        )

        block = cases[["network_id"]].copy()
        block["length"] = length
        block["oracle_error"] = pd.to_numeric(cases["abserr_oracle_method"], errors="coerce")
        block["cert_score"] = pd.to_numeric(cert["certificate_bound"], errors="coerce")
        block["cert_error"] = pd.to_numeric(cert["certificate_abs_error"], errors="coerce")
        block = block.dropna(subset=["oracle_error", "cert_error"])

        def contrast(frame: pd.DataFrame) -> float:
            k = max(1, int(round(RETENTION * len(frame))))
            cert_kept = frame.nsmallest(k, "cert_score")["cert_error"].to_numpy()
            length_kept = frame.nsmallest(k, "length")["oracle_error"].to_numpy()
            return float((cert_kept > PRIMARY_TOLERANCE_C).mean() - (length_kept > PRIMARY_TOLERANCE_C).mean())

        contrasts[panel] = cluster_bootstrap(block, contrast, draws=1500, seed=0)

    table = pd.DataFrame(rows)
    table.to_csv(STEP15 / "baseline_strength.csv", index=False)
    (STEP15 / "summary.json").write_text(
        json.dumps({"certificate_minus_length_rule_with_oracle_reconstruction": contrasts}, indent=2),
        encoding="utf-8",
    )

    lines = ["# Step 15 — was the incumbent handicapped?", ""]
    lines.append(
        f"At {RETENTION:.0%} retention. The last pairing gives the length rule a reconstruction "
        "no one can deploy: the best estimator per case, chosen with hindsight."
    )
    lines.append("")
    lines.append(table.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Certificate minus the length rule armed with the oracle reconstruction")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(contrasts, indent=2))
    lines.append("```")
    (STEP15 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(table.round(4).to_string(index=False))
    print()
    print(json.dumps({k: {"point_points": round(v["point"] * 100, 2), "ci_points": [round(v["low"] * 100, 2), round(v["high"] * 100, 2)]} for k, v in contrasts.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
