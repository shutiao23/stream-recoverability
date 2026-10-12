#!/usr/bin/env python3
"""Steps 6-7 of the v17 programme: the certificate and the frontier."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    all_frontiers,
    coverage_table,
    incumbent_operating_points,
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.screen import (  # noqa: E402
    out_of_fold_certificates,
    usable,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    NOMINAL_COVERAGE,
    PRIMARY_TOLERANCE_C,
    STEP4_CEILING,
    STEP6_SCREEN,
    STEP7_FRONTIER,
    TOLERANCES_C,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    STEP6_SCREEN.mkdir(parents=True, exist_ok=True)
    STEP7_FRONTIER.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)

    certificates = out_of_fold_certificates(cases, seed=args.seed)
    mondrian = out_of_fold_certificates(cases, seed=args.seed, mondrian=True)
    certificates.to_parquet(STEP6_SCREEN / "development_certificates.parquet", index=False)
    mondrian.to_parquet(STEP6_SCREEN / "development_certificates_mondrian.parquet", index=False)

    coverage = coverage_table(cases, certificates)
    coverage_m = coverage_table(cases, mondrian)
    coverage["calibration"] = "split"
    coverage_m["calibration"] = "mondrian"
    coverage_all = pd.concat([coverage, coverage_m], ignore_index=True)
    coverage_all.to_csv(STEP6_SCREEN / "coverage.csv", index=False)

    frontiers = all_frontiers(cases, certificates, seed=args.seed)
    frontiers.to_csv(STEP7_FRONTIER / "frontiers.csv", index=False)
    incumbent = incumbent_operating_points(cases, certificates)
    incumbent.to_csv(STEP7_FRONTIER / "incumbent_operating_points.csv", index=False)

    contrasts = {}
    for retention in (0.6, 0.7, 0.8, 0.9):
        contrasts[f"retention_{retention}"] = operating_point_contrast(
            cases, certificates, retention=retention, seed=args.seed
        )
    (STEP7_FRONTIER / "operating_point_contrasts.json").write_text(
        json.dumps(contrasts, indent=2), encoding="utf-8"
    )

    # Self-selected operating point: certify at the declared tolerance.
    certified = usable(certificates["certificate_bound"], PRIMARY_TOLERANCE_C)
    self_selected = {
        "tolerance_c": PRIMARY_TOLERANCE_C,
        "retention": float(certified.mean()),
        "rate_above_tolerance_retained": float(
            (pd.to_numeric(certificates.loc[certified, "certificate_abs_error"], errors="coerce") > PRIMARY_TOLERANCE_C).mean()
        ),
        "rate_above_tolerance_excluded": float(
            (pd.to_numeric(certificates.loc[~certified, "certificate_abs_error"], errors="coerce") > PRIMARY_TOLERANCE_C).mean()
        ),
        "mean_abs_error_retained": float(
            pd.to_numeric(certificates.loc[certified, "certificate_abs_error"], errors="coerce").mean()
        ),
    }
    (STEP6_SCREEN / "self_selected_operating_point.json").write_text(
        json.dumps(self_selected, indent=2), encoding="utf-8"
    )

    pivot = frontiers.pivot_table(index="retention", columns="screen", values=f"rate_above_{PRIMARY_TOLERANCE_C}")
    mean_pivot = frontiers.pivot_table(index="retention", columns="screen", values="mean_abs_error_c")

    lines = ["# Steps 6-7 — the certificate and the retention-error frontier", ""]
    lines.append(f"Development cases: **{len(cases):,}** on **{cases['network_id'].nunique()}** networks. "
                 f"All certificates are out-of-fold: no network appears in its own fitting or calibration set.")
    lines.append("")
    lines.append(f"## Share of retained station-years with hottest-30 error above {PRIMARY_TOLERANCE_C} °C")
    lines.append("")
    lines.append(pivot.round(4).to_string())
    lines.append("")
    lines.append("## Mean absolute error among retained station-years (°C)")
    lines.append("")
    lines.append(mean_pivot.round(4).to_string())
    lines.append("")
    lines.append("## Against the published fixed-length guidance, at equal retention")
    lines.append("")
    lines.append(incumbent.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Headline contrast, network-clustered bootstrap")
    lines.append("")
    lines.append("Certificate minus fixed-length rule, in the rate of error above 0.5 °C at matched retention.")
    lines.append("Negative means the certificate keeps a cleaner sample.")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(contrasts, indent=2))
    lines.append("```")
    lines.append("")
    lines.append(f"## Conformal coverage at nominal {NOMINAL_COVERAGE:.2f}")
    lines.append("")
    lines.append(coverage_all.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Self-selected operating point")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(self_selected, indent=2))
    lines.append("```")
    (STEP7_FRONTIER / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(pivot.round(4).to_string())
    print()
    print(incumbent.round(4).to_string(index=False))
    print()
    print(json.dumps(contrasts, indent=2))
    print()
    print(coverage_all.round(4).to_string(index=False))
    print()
    print(json.dumps(self_selected, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
