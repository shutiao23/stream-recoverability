#!/usr/bin/env python3
"""Step 4 of the v17 programme: ceiling analysis and the go/no-go gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.ceiling import (  # noqa: E402
    confirmation_resolution,
    gate_decision,
    mean_benefit_ceilings,
    retention_ceiling,
    tolerance_table,
)
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    NATURAL_SCALE_C,
    STEP1_PANEL,
    STEP3_CASES,
    STEP4_CEILING,
)


def main() -> int:
    STEP4_CEILING.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    n_reserved = int((split["split_role"] == "reserved").sum())

    development = cases.loc[cases["split_role"].eq("development")].copy()
    development = attach_policy_errors(development)
    development.to_parquet(STEP4_CEILING / "development_cases.parquet", index=False)

    mean_table = mean_benefit_ceilings(development)
    retention_table = retention_ceiling(development)
    resolution = confirmation_resolution(development, n_reserved)
    gate = gate_decision(mean_table, retention_table, resolution)
    tolerances = tolerance_table(development)

    mean_table.to_csv(STEP4_CEILING / "mean_benefit_ceilings.csv", index=False)
    retention_table.to_csv(STEP4_CEILING / "retention_ceiling.csv", index=False)
    resolution.to_csv(STEP4_CEILING / "confirmation_resolution.csv", index=False)
    tolerances.to_csv(STEP4_CEILING / "estimator_tolerances.csv", index=False)
    (STEP4_CEILING / "gate.json").write_text(json.dumps(gate, indent=2), encoding="utf-8")

    lines = ["# Step 4 — ceiling analysis and the go/no-go gate", ""]
    lines.append(
        "No decision rule is fit until the prize inside its action space is known and "
        "compared with the resolution the reserved panel will have. "
        f"Natural scale of the endpoint: {NATURAL_SCALE_C:.2f} °C interannual SD."
    )
    lines.append("")
    lines.append(f"Development cases: **{len(development):,}** on **{development['network_id'].nunique()}** networks, "
                 f"**{development.groupby(['network_id','station_id','year']).ngroups:,}** station-years.")
    lines.append("")
    lines.append("## Action spaces whose endpoint is mean benefit over the default")
    lines.append("")
    lines.append(mean_table.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Action space whose endpoint is the consequential-error rate among retained years")
    lines.append("")
    lines.append(retention_table.round(4).to_string(index=False))
    lines.append("")
    lines.append("## What the reserved panel can resolve")
    lines.append("")
    lines.append(resolution.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Estimator error at the declared tolerances")
    lines.append("")
    lines.append(tolerances.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(gate, indent=2))
    lines.append("```")
    (STEP4_CEILING / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(mean_table.round(4).to_string(index=False))
    print()
    print(retention_table.round(4).to_string(index=False))
    print()
    print(resolution.round(4).to_string(index=False))
    print()
    print(tolerances.round(4).to_string(index=False))
    print()
    print(json.dumps(gate, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
