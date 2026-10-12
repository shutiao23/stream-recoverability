#!/usr/bin/env python3
"""Close the open problem: coverage at a single new site.

Pooled split conformal gave the right coverage averaged over networks and too
little inside the hardest ones — a tenth percentile of 0.839 and a minimum of
0.709 across the reserved networks. Conformal validity assumes exchangeability,
which does not hold between river networks. This calibrates on the per-network
conformal quantiles instead, targeting "most networks are covered" rather than
"cases are covered on average", and measures what that costs in width.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    frontier_for_score,
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.screen import Certificate  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP9_FREEZE,
)

STEP18 = RESULTS_ROOT / "step18_cluster_conformal"
RETENTION = 0.70


def per_network(cases: pd.DataFrame, applied: pd.DataFrame, minimum: int = 40) -> pd.DataFrame:
    frame = cases[["network_id"]].copy()
    frame["covered"] = pd.to_numeric(applied["covered"], errors="coerce")
    grouped = frame.groupby("network_id").agg(n=("covered", "size"), coverage=("covered", "mean"))
    return grouped.loc[grouped["n"] >= minimum].reset_index()


def describe(coverage: pd.Series) -> dict:
    return {
        "n_networks": int(len(coverage)),
        "mean": float(coverage.mean()),
        "median": float(coverage.median()),
        "q10": float(coverage.quantile(0.10)),
        "min": float(coverage.min()),
        "share_below_0.80": float((coverage < 0.80).mean()),
        "share_below_0.85": float((coverage < 0.85).mean()),
    }


def main() -> int:
    STEP18.mkdir(parents=True, exist_ok=True)
    reserved = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
    model: Certificate = joblib.load(STEP9_FREEZE / "certificate.joblib")

    levels = (0.5, 0.6, 0.7, 0.8, 0.9)
    variants = {}
    settings = [("pooled", {})] + [
        (f"cluster_{level:.1f}", {"cluster_aware": True, "cluster_level": level}) for level in levels
    ]
    for label, kwargs in settings:
        applied = model.apply(reserved, **kwargs)
        applied.to_parquet(STEP18 / f"reserved_certificates_{label}.parquet", index=False)
        coverage = per_network(reserved, applied)
        coverage.to_csv(STEP18 / f"per_network_coverage_{label}.csv", index=False)
        contrast = operating_point_contrast(reserved, applied, retention=RETENTION, seed=0, draws=1200)
        frontier = frontier_for_score(
            applied["certificate_bound"], applied["certificate_abs_error"], applied["certificate_signed_error"]
        )
        at70 = frontier.loc[frontier["retention"].eq(RETENTION)].iloc[0]
        variants[label] = {
            "marginal_coverage": float(pd.to_numeric(applied["covered"], errors="coerce").mean()),
            "per_network": describe(coverage["coverage"]),
            "median_interval_width_c": float(pd.to_numeric(applied["interval_width"], errors="coerce").median()),
            "mean_interval_width_c": float(pd.to_numeric(applied["interval_width"], errors="coerce").mean()),
            "bound_coverage": float(pd.to_numeric(applied["bound_covered"], errors="coerce").mean()),
            "rate_above_tolerance_at_70": float(at70[f"rate_above_{PRIMARY_TOLERANCE_C}"]),
            "contrast_points_vs_length_rule": float(contrast["point"] * 100),
            "contrast_ci_points": [float(contrast["low"] * 100), float(contrast["high"] * 100)],
        }

    acceptable = [
        label
        for label, value in variants.items()
        if label != "pooled" and value["per_network"]["share_below_0.85"] == 0.0
    ]
    cheapest = min(acceptable, key=lambda k: variants[k]["median_interval_width_c"]) if acceptable else None
    verdict = {
        "question": "can the interval be made honest at a single new site, and what does it cost?",
        "pooled": variants["pooled"]["per_network"],
        "cheapest_setting_with_no_network_below_0.85": cheapest,
        "cheapest": variants[cheapest]["per_network"] if cheapest else None,
        "width_cost_ratio": (
            variants[cheapest]["median_interval_width_c"] / max(variants["pooled"]["median_interval_width_c"], 1e-9)
            if cheapest
            else None
        ),
        "screening_unaffected": all(
            abs(value["contrast_points_vs_length_rule"] - variants["pooled"]["contrast_points_vs_length_rule"]) < 1e-6
            for value in variants.values()
        ),
        "note": (
            "The ranking the screen uses is a monotone transform of the bound, so a change of "
            "calibration scale cannot move the retention-error frontier at all. Only the interval "
            "and the self-selected operating point change."
        ),
    }
    (STEP18 / "summary.json").write_text(json.dumps({"variants": variants, "verdict": verdict}, indent=2), encoding="utf-8")

    lines = ["# Step 18 — cluster-aware conformal calibration", ""]
    lines.append(
        "Pooled calibration is valid for a population of networks. The cluster settings target "
        "validity inside a stated share of networks instead, by calibrating on the per-network "
        "conformal quantiles. The level is the share of calibration networks the scale is set to "
        "cover, and it buys site-level honesty with interval width."
    )
    lines.append("")
    table = pd.DataFrame(
        [
            {
                "calibration": label,
                "marginal_coverage": value["marginal_coverage"],
                "per_network_mean": value["per_network"]["mean"],
                "per_network_q10": value["per_network"]["q10"],
                "per_network_min": value["per_network"]["min"],
                "share_below_0.85": value["per_network"]["share_below_0.85"],
                "median_width_c": value["median_interval_width_c"],
                "rate_at_70": value["rate_above_tolerance_at_70"],
            }
            for label, value in variants.items()
        ]
    )
    lines.append(table.round(4).to_string(index=False))
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(verdict, indent=2))
    lines.append("```")
    (STEP18 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(table.round(4).to_string(index=False))
    print()
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
