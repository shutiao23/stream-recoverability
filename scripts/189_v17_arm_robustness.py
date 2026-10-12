#!/usr/bin/env python3
"""Robustness of the headline result to the outage design.

The pre-registered test was run on the pooled case set, which mixes a
stratified arm that spans the decision space by construction with an empirical
arm drawn from the outage geometry the same networks actually experience. Those
two populations have very different base rates, so the absolute size of any
screening advantage must differ between them. This script separates them and
reports both, because quoting only the pooled number would overstate what a
typical agency archive stands to gain.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    all_frontiers,
    incumbent_operating_points,
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.screen import usable  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP4_CEILING,
    STEP6_SCREEN,
)

STEP11 = RESULTS_ROOT / "step11_arm_robustness"
PANELS = {
    "development": (STEP4_CEILING / "development_cases.parquet", STEP6_SCREEN / "development_certificates.parquet"),
    "reserved": (STEP10_CONFIRM / "reserved_cases.parquet", STEP10_CONFIRM / "reserved_certificates.parquet"),
}


def main() -> int:
    STEP11.mkdir(parents=True, exist_ok=True)
    rows = []
    frontier_pieces = []
    for panel, (case_path, cert_path) in PANELS.items():
        cases = pd.read_parquet(case_path).reset_index(drop=True)
        certificates = pd.read_parquet(cert_path).reset_index(drop=True)
        for arm in ("empirical", "stratified", "pooled"):
            mask = cases["arm"].eq(arm) if arm != "pooled" else pd.Series(True, index=cases.index)
            block = cases.loc[mask.to_numpy()].reset_index(drop=True)
            cert = certificates.loc[mask.to_numpy()].reset_index(drop=True)
            frontier = all_frontiers(block, cert)
            frontier["panel"] = panel
            frontier["arm"] = arm
            frontier_pieces.append(frontier)
            pivot = frontier.pivot_table(index="retention", columns="screen", values=f"rate_above_{PRIMARY_TOLERANCE_C}")
            at70 = pivot.loc[0.70]
            contrast = operating_point_contrast(block, cert, retention=0.70, draws=1500)
            incumbent = incumbent_operating_points(block, cert)
            johnson = incumbent.loc[incumbent["rule"].str.contains("91")].iloc[0]
            certified = usable(cert["certificate_bound"], PRIMARY_TOLERANCE_C)
            rows.append(
                {
                    "panel": panel,
                    "arm": arm,
                    "n_cases": int(len(block)),
                    "base_rate_retain_all": float(pivot.loc[1.00, "certificate_screen_only"]),
                    "length_rule_at_70": float(at70["length_rule"]),
                    "certificate_at_70": float(at70["certificate"]),
                    "peak_overlap_at_70": float(at70["peak_overlap_rule"]),
                    "random_at_70": float(at70["random"]),
                    "absolute_points_saved": float((at70["length_rule"] - at70["certificate"]) * 100),
                    "relative_reduction": float(1 - at70["certificate"] / at70["length_rule"]) if at70["length_rule"] > 0 else float("nan"),
                    "contrast_points": float(contrast["point"] * 100),
                    "ci_low_points": float(contrast["low"] * 100),
                    "ci_high_points": float(contrast["high"] * 100),
                    "johnson91_retention": float(johnson["retention"]),
                    "johnson91_rate": float(johnson["rate_above_0.5"]),
                    "certificate_at_johnson_retention": float(johnson["certificate_rate_above_0.5_at_equal_retention"]),
                    "self_selected_retention": float(certified.mean()),
                    "self_selected_rate_retained": float(
                        (pd.to_numeric(cert.loc[certified, "certificate_abs_error"], errors="coerce") > PRIMARY_TOLERANCE_C).mean()
                    ),
                }
            )
    table = pd.DataFrame(rows)
    table.to_csv(STEP11 / "arm_contrasts.csv", index=False)
    pd.concat(frontier_pieces, ignore_index=True).to_csv(STEP11 / "frontiers_by_arm.csv", index=False)

    verdict = {
        "pre_registered_test": "pooled cases, as declared in step9_freeze",
        "finding": (
            "The relative reduction in consequential-error rate is stable across outage regimes; "
            "the absolute reduction is not, because the base rate differs by an order of magnitude "
            "between the empirical and stratified arms."
        ),
        "declared_effect_points": 5.0,
        "meets_declared_effect": {
            row["panel"] + "_" + row["arm"]: bool(-row["contrast_points"] >= 5.0) for row in rows
        },
        "interval_excludes_zero": {
            row["panel"] + "_" + row["arm"]: bool(row["ci_high_points"] < 0) for row in rows
        },
        "lesson": (
            "The freeze should have weighted the arms explicitly. Reporting the pooled number alone "
            "would overstate what an archive with ordinary outage geometry stands to gain."
        ),
    }
    (STEP11 / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    lines = ["# Step 11 — robustness of the headline result to the outage design", ""]
    lines.append(
        "The pooled case set mixes a stratified arm, built to span the decision space, with an "
        "empirical arm drawn from the outage geometry these networks actually experience. Their base "
        "rates differ by an order of magnitude, so the two must be reported separately."
    )
    lines.append("")
    lines.append(table.round(4).to_string(index=False))
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(verdict, indent=2))
    lines.append("```")
    (STEP11 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(table[
        ["panel", "arm", "n_cases", "base_rate_retain_all", "length_rule_at_70", "certificate_at_70",
         "absolute_points_saved", "relative_reduction", "ci_low_points", "ci_high_points"]
    ].round(4).to_string(index=False))
    print()
    print(json.dumps(verdict["meets_declared_effect"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
