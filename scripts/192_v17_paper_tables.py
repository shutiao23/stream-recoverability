#!/usr/bin/env python3
"""Tables the manuscript promises and a referee will look for.

Two gaps found in a self-audit of the draft: the text says the frontier is
reported across tolerances but only showed one, and it describes the
air-driven estimator as a coverage-limited sub-study without ever reporting
its coverage or how often it is chosen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP4_CEILING,
    STEP6_SCREEN,
    STEP7_FRONTIER,
    TOLERANCES_C,
)

STEP14 = RESULTS_ROOT / "step14_paper_tables"
RETENTION = 0.70
SCREENS = ("certificate", "length_rule", "peak_overlap_rule", "random", "oracle")


def tolerance_table() -> pd.DataFrame:
    rows = []
    for panel, path in (("development", STEP7_FRONTIER / "frontiers.csv"), ("reserved", STEP10_CONFIRM / "frontiers.csv")):
        frame = pd.read_csv(path)
        block = frame.loc[frame["retention"].eq(RETENTION) & frame["screen"].isin(SCREENS)]
        for _, row in block.iterrows():
            entry = {"panel": panel, "screen": str(row["screen"])}
            for tolerance in TOLERANCES_C:
                entry[f"rate_above_{tolerance}"] = float(row[f"rate_above_{tolerance}"])
            entry["mean_abs_error_c"] = float(row["mean_abs_error_c"])
            entry["severe_underestimate_rate"] = float(row.get("severe_underestimate_rate", float("nan")))
            rows.append(entry)
    return pd.DataFrame(rows)


def choice_table() -> pd.DataFrame:
    rows = []
    for panel, cases_path, cert_path in (
        ("development", STEP4_CEILING / "development_cases.parquet", STEP6_SCREEN / "development_certificates.parquet"),
        ("reserved", STEP10_CONFIRM / "reserved_cases.parquet", STEP10_CONFIRM / "reserved_certificates.parquet"),
    ):
        cases = pd.read_parquet(cases_path).reset_index(drop=True)
        cert = pd.read_parquet(cert_path).reset_index(drop=True)
        counts = cert["certificate_choice"].value_counts(normalize=True)
        policy = cases["policy_choice"].value_counts(normalize=True)
        for name in sorted(set(counts.index) | set(policy.index)):
            chosen = cert["certificate_choice"].eq(name)
            rows.append(
                {
                    "panel": panel,
                    "estimator": name,
                    "share_chosen_by_certificate": float(counts.get(name, 0.0)),
                    "share_chosen_by_information_rule": float(policy.get(name, 0.0)),
                    "mean_abs_error_when_chosen_c": float(
                        pd.to_numeric(cert.loc[chosen, "certificate_abs_error"], errors="coerce").mean()
                    )
                    if chosen.any()
                    else float("nan"),
                }
            )
        rows.append(
            {
                "panel": panel,
                "estimator": "__air_forcing_available__",
                "share_chosen_by_certificate": float(cases["air_available"].mean()),
                "share_chosen_by_information_rule": float("nan"),
                "mean_abs_error_when_chosen_c": float("nan"),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    STEP14.mkdir(parents=True, exist_ok=True)
    tolerances = tolerance_table()
    choices = choice_table()
    tolerances.to_csv(STEP14 / "tolerance_frontier.csv", index=False)
    choices.to_csv(STEP14 / "estimator_choice.csv", index=False)

    lines = ["# Step 14 — tables the manuscript promises", ""]
    lines.append(f"## Frontier at {RETENTION:.0%} retention, across tolerances")
    lines.append("")
    lines.append(tolerances.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Which estimator is used, and how far the air-driven branch reaches")
    lines.append("")
    lines.append(choices.round(4).to_string(index=False))
    (STEP14 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(tolerances.round(4).to_string(index=False))
    print()
    print(choices.round(4).to_string(index=False))
    (STEP14 / "summary.json").write_text(
        json.dumps({"retention": RETENTION, "tolerances": list(TOLERANCES_C)}, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
