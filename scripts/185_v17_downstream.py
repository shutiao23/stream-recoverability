#!/usr/bin/env python3
"""Step 8 of the v17 programme: downstream consequence (H4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.downstream import (  # noqa: E402
    downstream_summary,
    one_realization_per_year,
    per_year_threshold_accuracy,
    sign_error_rate,
    station_series,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    STEP4_CEILING,
    STEP6_SCREEN,
    STEP8_DOWNSTREAM,
)


def main() -> int:
    STEP8_DOWNSTREAM.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP4_CEILING / "development_cases.parquet")
    certificates = pd.read_parquet(STEP6_SCREEN / "development_certificates.parquet")

    picked = one_realization_per_year(cases, certificates)
    series = station_series(picked)
    series.to_csv(STEP8_DOWNSTREAM / "station_series.csv", index=False)
    summary = downstream_summary(series)
    signs = sign_error_rate(series)
    per_year = per_year_threshold_accuracy(picked)
    per_year.to_csv(STEP8_DOWNSTREAM / "per_year_threshold.csv", index=False)
    summary.to_csv(STEP8_DOWNSTREAM / "summary.csv", index=False)
    signs.to_csv(STEP8_DOWNSTREAM / "sign_errors.csv", index=False)

    contrasts = {}
    for name in ("observed_days_all", "reconstruct_all", "length_screened"):
        contrasts[name] = cluster_bootstrap(
            series,
            lambda f, a=name: float(
                pd.to_numeric(f[f"slope_error_{a}"], errors="coerce").abs().mean()
                - pd.to_numeric(f["slope_error_certificate_screened"], errors="coerce").abs().mean()
            ),
        )
    (STEP8_DOWNSTREAM / "contrasts.json").write_text(json.dumps(contrasts, indent=2), encoding="utf-8")

    lines = ["# Step 8 — what changes downstream (H4)", ""]
    lines.append(
        f"Stations with at least six complete years and one outage realization per year: "
        f"**{len(series):,}** stations on **{series['network_id'].nunique()}** networks. "
        "The length-rule threshold is set to match the certificate's retention, so the "
        "comparison is at equal cost in discarded station-years."
    )
    lines.append("")
    lines.append("## Trend in the annual thermal peak, exceedance counts, and hottest-year identification")
    lines.append("")
    lines.append(summary.round(5).to_string(index=False))
    lines.append("")
    lines.append("## The per-year product: exceedance of an ecological threshold")
    lines.append("")
    lines.append(per_year.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Trend sign errors")
    lines.append("")
    lines.append(signs.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Mean absolute slope error, each treatment minus the certificate")
    lines.append("")
    lines.append("Positive means the treatment is worse than the certificate. Clustered by network.")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(contrasts, indent=2))
    lines.append("```")
    (STEP8_DOWNSTREAM / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(summary.round(5).to_string(index=False))
    print()
    print(per_year.round(4).to_string(index=False))
    print()
    print(signs.round(4).to_string(index=False))
    print()
    print(json.dumps(contrasts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
