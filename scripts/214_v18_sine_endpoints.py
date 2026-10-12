#!/usr/bin/env python3
"""E3 — the axis comparison on Johnson et al.'s own estimands.

The v17 manuscript corrects a piece of guidance while measuring a different
statistic. Johnson et al. (2021) fit a sine wave by linear regression to the
annual series and take a mean, a phase and an amplitude; they do not compute a
hottest 30-day mean and they make no claim about warm-season extremes. As
written, that leaves the paper open to the charge of refuting a claim nobody
made. Running our comparison on their three estimands closes it -- and the
theory makes three predictions sharp enough to fail.

Declared before the table was produced:

P1  the fitted MEAN is a whole-year functional, so the length axis should win,
    as it does for the arithmetic annual mean.
P2  the PHASE is a location parameter whose influence is largest a quarter-year
    from the peak, so peak-window overlap should be a POOR axis for it and the
    transition windows should beat both peak overlap and outage length. This is
    the prediction that separates "condition on the estimand's support" from
    "condition on timing".
P3  the AMPLITUDE is supported on both extremes, so it should sit between.
P4  for all three, the influence-weighted hidden mass -- the exact form of "the
    support of the estimand" -- should be at least as good as the best
    hand-chosen axis.

Together these say that what Johnson et al. saw as timing mattering
"inconsistently in space and time" is three different supports being observed
at once.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v18_closure.analysis import (  # noqa: E402
    axis_table,
    clustered_auc_contrast,
    interannual_scale,
)
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    E3_SINE,
    RESULTS_ROOT,
    TOLERANCE_FRACTION,
)

ENDPOINTS = ("sine_mean", "sine_amplitude", "sine_phase")
AXES = (
    "peak_overlap",
    "warm_observed_fraction",
    "transition_overlap",
    "longest_run",
    "total_missing",
    "missing_fraction",
)
HIGHER_IS_WORSE = {"warm_observed_fraction": False}
TOLERANCE_FRACTIONS = (0.25, TOLERANCE_FRACTION, 1.0)
PROTOCOLS = {"repaired": "abserr_{name}", "observed_days_only": "abserr_observed_{name}"}


def scored(cases: pd.DataFrame, endpoint: str, protocol: str, fraction: float) -> tuple[pd.DataFrame, float, float]:
    column = PROTOCOLS[protocol].format(name=endpoint)
    scale = interannual_scale(cases, f"truth_{endpoint}")
    tolerance = float(fraction) * scale
    block = cases.dropna(subset=[column]).copy()
    block["consequential"] = (block[column] > tolerance).astype(float)
    return block, scale, tolerance


def main() -> int:
    E3_SINE.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(RESULTS_ROOT / "endpoint_cases.parquet")
    development = cases.loc[cases["split_role"] == "development"].reset_index(drop=True)

    rows, contrasts = [], []
    for endpoint in ENDPOINTS:
        influence = f"influence_hidden_{endpoint}"
        for protocol in PROTOCOLS:
            for fraction in TOLERANCE_FRACTIONS:
                block, scale, tolerance = scored(development, endpoint, protocol, fraction)
                label = block["consequential"].to_numpy()
                row = {
                    "endpoint": endpoint,
                    "protocol": protocol,
                    "tolerance_fraction": float(fraction),
                    "interannual_sd": scale,
                    "tolerance": tolerance,
                    "n": int(len(block)),
                    "base_rate": float(label.mean()),
                }
                row.update(axis_table(block, label, (*AXES, influence), higher_is_worse=HIGHER_IS_WORSE))
                row["auc_influence_hidden"] = row.pop(f"auc_{influence}")
                candidates = {k: v for k, v in row.items() if k.startswith("auc_") and np.isfinite(v)}
                row["best_axis"] = max(candidates, key=candidates.get).replace("auc_", "")
                rows.append(row)

        block, _, _ = scored(development, endpoint, "repaired", TOLERANCE_FRACTION)
        for left, right in (
            ("missing_fraction", "peak_overlap"),
            ("transition_overlap", "peak_overlap"),
            ("transition_overlap", "missing_fraction"),
            (influence, "peak_overlap"),
            (influence, "missing_fraction"),
        ):
            contrast = clustered_auc_contrast(
                block, "consequential", left, right, higher_is_worse=HIGHER_IS_WORSE
            )
            contrast["endpoint"] = endpoint
            contrasts.append(contrast)

    table = pd.DataFrame(rows)
    table.to_csv(E3_SINE / "sine_axis_comparison.csv", index=False)
    contrast_table = pd.DataFrame(contrasts)
    contrast_table.to_csv(E3_SINE / "auc_contrasts.csv", index=False)

    primary = table.loc[
        (table["protocol"] == "repaired") & (table["tolerance_fraction"] == TOLERANCE_FRACTION)
    ].set_index("endpoint")

    def best(endpoint: str) -> str:
        return str(primary.loc[endpoint, "best_axis"])

    verdicts = {
        "P1_mean_is_length_governed": {
            "prediction": "for the fitted mean, outage size beats peak-window overlap",
            "outcome": bool(
                primary.loc["sine_mean", "auc_missing_fraction"]
                > primary.loc["sine_mean", "auc_peak_overlap"]
            ),
            "auc_missing_fraction": float(primary.loc["sine_mean", "auc_missing_fraction"]),
            "auc_peak_overlap": float(primary.loc["sine_mean", "auc_peak_overlap"]),
        },
        "P2_phase_is_transition_governed": {
            "prediction": (
                "for the phase, the transition windows beat both peak-window overlap "
                "and outage length"
            ),
            "outcome": bool(
                primary.loc["sine_phase", "auc_transition_overlap"]
                > max(
                    primary.loc["sine_phase", "auc_peak_overlap"],
                    primary.loc["sine_phase", "auc_longest_run"],
                )
            ),
            "auc_transition_overlap": float(primary.loc["sine_phase", "auc_transition_overlap"]),
            "auc_peak_overlap": float(primary.loc["sine_phase", "auc_peak_overlap"]),
            "auc_longest_run": float(primary.loc["sine_phase", "auc_longest_run"]),
        },
        "P3_amplitude_is_intermediate": {
            "prediction": "the amplitude's peak-overlap advantage lies between the other two",
            "peak_minus_length_by_endpoint": {
                endpoint: float(
                    primary.loc[endpoint, "auc_peak_overlap"] - primary.loc[endpoint, "auc_missing_fraction"]
                )
                for endpoint in ENDPOINTS
            },
        },
        "P4_influence_weighting_is_at_least_as_good": {
            "prediction": "the influence-weighted hidden mass is the best or joint-best axis",
            "best_axis_by_endpoint": {endpoint: best(endpoint) for endpoint in ENDPOINTS},
            "influence_auc_by_endpoint": {
                endpoint: float(primary.loc[endpoint, "auc_influence_hidden"]) for endpoint in ENDPOINTS
            },
        },
    }
    order_invariant = (
        table.loc[table["protocol"] == "repaired"]
        .groupby("endpoint")["best_axis"]
        .nunique()
        .to_dict()
    )
    summary = {
        "n_cases": int(len(development)),
        "verdicts": verdicts,
        "best_axis_unique_across_tolerances": {k: int(v) for k, v in order_invariant.items()},
    }
    (E3_SINE / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")

    columns = [
        "endpoint",
        "protocol",
        "base_rate",
        "auc_peak_overlap",
        "auc_warm_observed_fraction",
        "auc_transition_overlap",
        "auc_longest_run",
        "auc_missing_fraction",
        "auc_influence_hidden",
        "best_axis",
    ]
    lines = ["# E3 — the axis comparison on Johnson et al.'s estimands", ""]
    lines.append(
        "Sine-wave linear regression, three parameters, development cases, each scored "
        f"at {TOLERANCE_FRACTION:.2f} of its own interannual standard deviation."
    )
    lines.append("")
    lines.append(
        table.loc[table["tolerance_fraction"] == TOLERANCE_FRACTION, columns].to_markdown(
            index=False, floatfmt=".4g"
        )
    )
    lines.append("")
    lines.append("## Network-clustered contrasts")
    lines.append("")
    lines.append(
        contrast_table[["endpoint", "left", "right", "point", "low", "high", "excludes_zero"]].to_markdown(
            index=False, floatfmt=".4g"
        )
    )
    lines.append("")
    lines.append("## Verdicts against the declared predictions")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(verdicts, indent=2, default=float))
    lines.append("```")
    (E3_SINE / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
