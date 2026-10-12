#!/usr/bin/env python3
"""The deployable three-variable rule, with its coefficients.

The ablations show that most of the certificate's advantage comes from changing
the screening axis rather than from the model on top of it. A reader who will
never run this code should still be able to act on that, so the simple rule is
fitted here on development networks, its coefficients are printed, and it is
scored out of sample on the reserved panel exactly like the certificate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import frontier_for_score  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP4_CEILING,
)

STEP16 = RESULTS_ROOT / "step16_simple_rule"
FEATURES = ("peak_overlap", "warm_observed_fraction", "longest_run")
RETENTION = 0.70


def main() -> int:
    STEP16.mkdir(parents=True, exist_ok=True)
    development = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)
    reserved = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)

    X = development[list(FEATURES)].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = (pd.to_numeric(development["abserr_policy"], errors="coerce") > PRIMARY_TOLERANCE_C).astype(int)
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=0))
    model.fit(X, y)
    scaler = model.named_steps["standardscaler"]
    logit = model.named_steps["logisticregression"]
    raw_coefficients = logit.coef_[0] / scaler.scale_
    intercept = float(logit.intercept_[0] - float(np.dot(logit.coef_[0], scaler.mean_ / scaler.scale_)))

    rows = []
    for panel, frame in (("development", development), ("reserved", reserved)):
        score = pd.Series(
            model.predict_proba(frame[list(FEATURES)].apply(pd.to_numeric, errors="coerce").fillna(0.0))[:, 1],
            index=frame.index,
        )
        error = pd.to_numeric(frame["abserr_policy"], errors="coerce")
        signed = pd.to_numeric(frame["err_policy"], errors="coerce")
        rng = np.random.default_rng(7)
        length = pd.Series(pd.to_numeric(frame["longest_run"], errors="coerce").to_numpy() + rng.random(len(frame)), index=frame.index)
        for label, values in (("three-variable rule", score), ("outage-length rule", length)):
            f = frontier_for_score(values, error, signed)
            at70 = f.loc[f["retention"].eq(RETENTION)].iloc[0]
            rows.append(
                {
                    "panel": panel,
                    "screen": label,
                    "rate_above_0.5_at_70": float(at70[f"rate_above_{PRIMARY_TOLERANCE_C}"]),
                    "mean_abs_error_at_70": float(at70["mean_abs_error_c"]),
                    "severe_underestimate_at_70": float(at70["severe_underestimate_rate"]),
                }
            )
        block = frame[["network_id"]].copy()
        block["rule"] = score
        block["length"] = length
        block["error"] = error
        block = block.dropna(subset=["error"])

        def contrast(sub: pd.DataFrame) -> float:
            k = max(1, int(round(RETENTION * len(sub))))
            a = sub.nsmallest(k, "rule")["error"].to_numpy()
            b = sub.nsmallest(k, "length")["error"].to_numpy()
            return float((a > PRIMARY_TOLERANCE_C).mean() - (b > PRIMARY_TOLERANCE_C).mean())

        rows[-1]["_"] = None
        stat = cluster_bootstrap(block, contrast, draws=1500, seed=0)
        rows.append(
            {
                "panel": panel,
                "screen": "contrast: three-variable minus length (points)",
                "rate_above_0.5_at_70": float(stat["point"] * 100),
                "mean_abs_error_at_70": float(stat["low"] * 100),
                "severe_underestimate_at_70": float(stat["high"] * 100),
            }
        )

    table = pd.DataFrame(rows).drop(columns=["_"], errors="ignore")
    table.to_csv(STEP16 / "simple_rule_scores.csv", index=False)

    rule = {
        "form": "risk score = 1 / (1 + exp(-(b0 + b1*peak_overlap + b2*warm_observed_fraction + b3*longest_run_days)))",
        "intercept_b0": round(intercept, 5),
        "coefficients": {name: round(float(value), 6) for name, value in zip(FEATURES, raw_coefficients)},
        "definitions": {
            "peak_overlap": "share of the station's climatological hottest-30 window that the outage hides, from training years only, 0-1",
            "warm_observed_fraction": "share of May-September days that remain observed, 0-1",
            "longest_run_days": "length in days of the longest consecutive outage",
        },
        "use": "rank station-years by the score and retain the lowest; or pick a cut-off from the retention your archive can afford",
        "fitted_on": "110 development networks; scored unchanged on 36 reserved networks",
    }
    (STEP16 / "rule.json").write_text(json.dumps(rule, indent=2), encoding="utf-8")

    lines = ["# Step 16 — the deployable three-variable rule", ""]
    lines.append("Fitted on development networks, applied unchanged to the reserved panel.")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(rule, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("In the contrast rows, the three numeric columns are the point estimate and the")
    lines.append("two interval ends, in percentage points.")
    lines.append("")
    lines.append(table.round(4).to_string(index=False))
    (STEP16 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(rule, indent=2))
    print()
    print(table.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
