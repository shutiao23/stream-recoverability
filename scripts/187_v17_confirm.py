#!/usr/bin/env python3
"""Step 10 of the v17 programme: the reserved networks, scored once.

Also runs leave-one-provider-out inside the development pool as an agency
transfer diagnostic. The reserved panel is opened exactly once, with the frozen
certificate from Step 9 and no retuning of any kind.
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
    all_frontiers,
    coverage_table,
    incumbent_operating_points,
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.mechanism import marginal_separation  # noqa: E402
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402
from stream_recoverability.experiments.v17_fitness.screen import Certificate, split_networks  # noqa: E402
from stream_recoverability.experiments.v17_fitness.downstream import (  # noqa: E402
    one_realization_per_year,
    per_year_threshold_accuracy,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    NOMINAL_COVERAGE,
    PRIMARY_TOLERANCE_C,
    STEP10_CONFIRM,
    STEP3_CASES,
    STEP4_CEILING,
    STEP9_FREEZE,
)

PRIMARY_RETENTION = 0.70
DECLARED_EFFECT_POINTS = 5.0


def leave_one_provider_out(cases: pd.DataFrame, *, seed: int = 0) -> pd.DataFrame:
    rows = []
    providers = sorted(cases["provider"].astype(str).unique())
    for provider in providers:
        test = cases.loc[cases["provider"].astype(str).eq(provider)]
        train = cases.loc[~cases["provider"].astype(str).eq(provider)]
        if len(test) < 300 or train["network_id"].nunique() < 10:
            continue
        fit_ids, cal_ids = split_networks(train["network_id"].astype(str).unique(), fraction=0.3, seed=seed)
        fit_cases = train.loc[train["network_id"].astype(str).isin(fit_ids)]
        cal_cases = train.loc[train["network_id"].astype(str).isin(cal_ids)]
        if fit_cases.empty or cal_cases.empty:
            continue
        model = Certificate(coverage=NOMINAL_COVERAGE).fit(fit_cases, cal_cases, seed=seed)
        applied = model.apply(test)
        contrast = operating_point_contrast(test, applied, retention=PRIMARY_RETENTION, seed=seed, draws=800)
        rows.append(
            {
                "provider": provider,
                "n_cases": int(len(test)),
                "n_networks": int(test["network_id"].nunique()),
                "contrast_points": float(contrast["point"] * 100),
                "ci_low_points": float(contrast["low"] * 100),
                "ci_high_points": float(contrast["high"] * 100),
                "coverage": float(pd.to_numeric(applied["covered"], errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    STEP10_CONFIRM.mkdir(parents=True, exist_ok=True)
    all_cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
    reserved = all_cases.loc[all_cases["split_role"].eq("reserved")].reset_index(drop=True)
    reserved = attach_policy_errors(reserved)
    reserved.to_parquet(STEP10_CONFIRM / "reserved_cases.parquet", index=False)

    model: Certificate = joblib.load(STEP9_FREEZE / "certificate.joblib")
    certificates = model.apply(reserved)
    certificates.to_parquet(STEP10_CONFIRM / "reserved_certificates.parquet", index=False)

    frontiers = all_frontiers(reserved, certificates)
    frontiers.to_csv(STEP10_CONFIRM / "frontiers.csv", index=False)
    incumbent = incumbent_operating_points(reserved, certificates)
    incumbent.to_csv(STEP10_CONFIRM / "incumbent_operating_points.csv", index=False)
    coverage = coverage_table(reserved, certificates)
    coverage.to_csv(STEP10_CONFIRM / "coverage.csv", index=False)

    contrast = operating_point_contrast(reserved, certificates, retention=PRIMARY_RETENTION, seed=0)
    by_regime = {}
    for regime, block in reserved.groupby("donor_regime"):
        sub = certificates.loc[block.index]
        if len(block) < 300:
            continue
        by_regime[str(regime)] = operating_point_contrast(
            block.reset_index(drop=True), sub.reset_index(drop=True), retention=PRIMARY_RETENTION, seed=0, draws=1000
        )

    picked = one_realization_per_year(reserved, certificates)
    per_year = per_year_threshold_accuracy(picked)
    per_year.to_csv(STEP10_CONFIRM / "per_year_threshold.csv", index=False)

    separation = marginal_separation(reserved)
    separation.to_csv(STEP10_CONFIRM / "marginal_separation.csv", index=False)

    development = pd.read_parquet(STEP4_CEILING / "development_cases.parquet")
    lopo = leave_one_provider_out(development)
    lopo.to_csv(STEP10_CONFIRM / "leave_one_provider_out.csv", index=False)

    marginal_coverage = float(pd.to_numeric(certificates["covered"], errors="coerce").mean())
    conditional = coverage.loc[coverage["level"].eq("conditional"), "coverage"].astype(float)
    verdict = {
        "reserved_networks_opened": True,
        "opened_on": "2026-09-23",
        "n_cases": int(len(reserved)),
        "n_networks": int(reserved["network_id"].nunique()),
        "n_station_years": int(reserved.groupby(["network_id", "station_id", "year"]).ngroups),
        "primary": {
            "retention": PRIMARY_RETENTION,
            "contrast_points": float(contrast["point"] * 100),
            "ci_points": [float(contrast["low"] * 100), float(contrast["high"] * 100)],
            "declared_effect_points": DECLARED_EFFECT_POINTS,
            "passes_effect_size": bool(-contrast["point"] * 100 >= DECLARED_EFFECT_POINTS),
            "passes_interval_excludes_zero": bool(contrast["high"] < 0),
        },
        "coverage": {
            "marginal": marginal_coverage,
            "passes_marginal_band": bool(0.87 <= marginal_coverage <= 0.93),
            "conditional_min": float(conditional.min()),
            "conditional_max": float(conditional.max()),
            "passes_conditional_band": bool(conditional.min() >= 0.85 and conditional.max() <= 0.95),
        },
        "by_donor_regime": {key: {k: float(v) for k, v in value.items()} for key, value in by_regime.items()},
    }
    verdict["primary"]["passes"] = bool(
        verdict["primary"]["passes_effect_size"] and verdict["primary"]["passes_interval_excludes_zero"]
    )
    (STEP10_CONFIRM / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    pivot = frontiers.pivot_table(index="retention", columns="screen", values=f"rate_above_{PRIMARY_TOLERANCE_C}")

    lines = ["# Step 10 — the reserved networks, scored once", ""]
    lines.append(
        f"Reserved panel: **{verdict['n_networks']}** networks, "
        f"**{verdict['n_station_years']:,}** station-years, **{verdict['n_cases']:,}** cases. "
        "The certificate is the Step-9 object applied without retuning."
    )
    lines.append("")
    lines.append(f"## Share of retained station-years with error above {PRIMARY_TOLERANCE_C} °C")
    lines.append("")
    lines.append(pivot.round(4).to_string())
    lines.append("")
    lines.append("## Against the published fixed-length guidance, at equal retention")
    lines.append("")
    lines.append(incumbent.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Conformal coverage")
    lines.append("")
    lines.append(coverage.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Per-year exceedance judgement")
    lines.append("")
    lines.append(per_year.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Leave-one-provider-out inside development (agency transfer)")
    lines.append("")
    lines.append(lopo.round(3).to_string(index=False))
    lines.append("")
    lines.append("## Which variables separate a consequential error on the reserved panel")
    lines.append("")
    lines.append(separation.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(verdict, indent=2))
    lines.append("```")
    (STEP10_CONFIRM / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(pivot.round(4).to_string())
    print()
    print(incumbent.round(4).to_string(index=False))
    print()
    print(coverage.round(4).to_string(index=False))
    print()
    print(per_year.round(4).to_string(index=False))
    print()
    print(lopo.round(3).to_string(index=False))
    print()
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
