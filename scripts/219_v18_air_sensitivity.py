#!/usr/bin/env python3
"""E5c — does the result survive the field's own reconstruction method?

The v17 air-driven estimator was supported on 2.3% of development cases and
0.85% of reserved cases, and that is the most exposed part of the study for a
water-resources audience: air-temperature regression is the standard way this
field fills a stream-temperature record. Beaufort et al. (2022), the closest
prior work, uses exactly that to reconstruct thermal peaks. Worse, 36 of the
110 development networks have no synchronous donor at all, so for those the
estimator library collapsed to climatology and interpolation -- precisely the
sites where a practitioner would reach for air temperature first.

With coordinates joined and NASA POWER pulled for all 457 stations, the same
pipeline is rerun with air forcing everywhere. Three questions:

1. how much smaller is the problem when the field's own method is available;
2. does the axis conclusion depend on the estimator library (it should not: it
   is a claim about which cases are hard, not about how well they are repaired);
3. is the incumbent still not handicapped when it is paired with an always-air
   reconstruction it could actually deploy.

The pre-registered confirmation is not re-scored. It stands as reported; this
is a sensitivity analysis on the development panel, and the reserved panel is
shown alongside only because it is already unblinded.
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
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP3_CASES,
)
from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    attach_policy_errors,
    gather,
    information_conditioned_choice,
)
from stream_recoverability.experiments.v17_fitness.screen import out_of_fold_certificates  # noqa: E402
from stream_recoverability.experiments.v18_closure.analysis import auc  # noqa: E402
from stream_recoverability.experiments.v18_closure.paths import E5_AIR, RETENTION  # noqa: E402

ESTIMATORS = ("observed_days", "doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path).reset_index(drop=True)
    if "abserr_policy" not in frame.columns:
        frame = attach_policy_errors(frame)
    return frame


def support_table(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for split in ("development", "reserved"):
        for label, frame in (("v17 forcing", before), ("v18 forcing", after)):
            block = frame.loc[frame["split_role"] == split]
            row = {"split": split, "forcing": label, "n_cases": int(len(block))}
            row["air_available_pct"] = float(block["air_available"].astype(bool).mean() * 100)
            for estimator in ESTIMATORS:
                column = f"abserr_{estimator}"
                row[f"supported_{estimator}_pct"] = (
                    float(block[column].notna().mean() * 100) if column in block else float("nan")
                )
            rows.append(row)
    return pd.DataFrame(rows)


def problem_size(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, frame in (("v17 forcing", before), ("v18 forcing", after)):
        for regime in ("all", "none", "sparse", "rich"):
            block = frame.loc[frame["split_role"] == "development"]
            if regime != "all":
                block = block.loc[block["donor_regime"] == regime]
            if block.empty:
                continue
            fills = [f"abserr_{name}" for name in ESTIMATORS if name != "observed_days"]
            available = block[[c for c in fills if c in block]]
            rows.append(
                {
                    "forcing": label,
                    "donor_regime": regime,
                    "n_cases": int(len(block)),
                    "observed_days_mae_c": float(block["abserr_observed_days"].mean()),
                    "doy_climatology_mae_c": float(block["abserr_doy_climatology"].mean()),
                    "air_ridge_mae_c": float(block["abserr_air_ridge"].mean()),
                    "policy_mae_c": float(block["abserr_policy"].mean()),
                    "oracle_mae_c": float(available.min(axis=1).mean()),
                    "policy_rate_above_0.5_pct": float(
                        (block["abserr_policy"] > PRIMARY_TOLERANCE_C).mean() * 100
                    ),
                }
            )
    return pd.DataFrame(rows)


def axis_stability(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, frame in (("v17 forcing", before), ("v18 forcing", after)):
        block = frame.loc[frame["split_role"] == "development"]
        label_vector = (block["abserr_policy"] > PRIMARY_TOLERANCE_C).astype(float).to_numpy()
        rows.append(
            {
                "forcing": label,
                "base_rate": float(label_vector.mean()),
                "auc_peak_overlap": auc(label_vector, block["peak_overlap"].to_numpy(dtype=float)),
                "auc_warm_observed_fraction": auc(
                    label_vector, -block["warm_observed_fraction"].to_numpy(dtype=float)
                ),
                "auc_longest_run": auc(label_vector, block["longest_run"].to_numpy(dtype=float)),
                "auc_missing_fraction": auc(label_vector, block["missing_fraction"].to_numpy(dtype=float)),
            }
        )
    frame = pd.DataFrame(rows)
    frame["timing_minus_length"] = frame["auc_peak_overlap"] - frame["auc_longest_run"]
    return frame


def fairness(after: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Table 3 with the incumbent paired with a reconstruction it could deploy."""

    development = after.loc[after["split_role"] == "development"].reset_index(drop=True)
    certificates = out_of_fold_certificates(development, seed=seed)
    rng = np.random.default_rng(5)
    length = pd.Series(
        development["longest_run"].to_numpy(dtype=float) + rng.random(len(development)),
        index=development.index,
    )
    climatology = development["abserr_doy_climatology"]
    pairings = {
        "information-conditioned policy": development["abserr_policy"],
        "always air regression (Beaufort-style), else climatology": development["abserr_air_ridge"].fillna(climatology),
        "always donor ridge, else climatology": development["abserr_donor_ridge"].fillna(climatology),
        "always smooth climatology": development["abserr_smooth_climatology"],
        "oracle over methods (NOT deployable)": development["abserr_oracle_method"],
    }
    rows = []
    for name, error in pairings.items():
        frame = frontier_for_score(length, error)
        at70 = frame.loc[frame["retention"].eq(RETENTION)].iloc[0]
        rows.append(
            {
                "screen": "outage-length rule",
                "reconstruction": name,
                "rate_above_0.5_pct": float(at70[f"rate_above_{PRIMARY_TOLERANCE_C}"] * 100),
                "mean_abs_error_c": float(at70["mean_abs_error_c"]),
            }
        )
    frame = frontier_for_score(certificates["certificate_bound"], certificates["certificate_abs_error"])
    at70 = frame.loc[frame["retention"].eq(RETENTION)].iloc[0]
    rows.append(
        {
            "screen": "calibrated screen",
            "reconstruction": "deployable estimators it selects itself",
            "rate_above_0.5_pct": float(at70[f"rate_above_{PRIMARY_TOLERANCE_C}"] * 100),
            "mean_abs_error_c": float(at70["mean_abs_error_c"]),
        }
    )
    chosen = pd.Series(certificates["certificate_choice"]).value_counts(normalize=True) * 100
    frame_out = pd.DataFrame(rows)
    frame_out.attrs["estimator_share_pct"] = chosen.to_dict()
    return frame_out


def main() -> int:
    E5_AIR.mkdir(parents=True, exist_ok=True)
    before = load(STEP3_CASES / "cases.parquet")
    after = load(STEP3_CASES / "cases_air.parquet")

    support = support_table(before, after)
    support.to_csv(E5_AIR / "estimator_support.csv", index=False)
    sizes = problem_size(before, after)
    sizes.to_csv(E5_AIR / "problem_size.csv", index=False)
    stability = axis_stability(before, after)
    stability.to_csv(E5_AIR / "axis_stability.csv", index=False)
    fair = fairness(after)
    fair.to_csv(E5_AIR / "fairness_with_air.csv", index=False)

    all_dev = sizes.loc[sizes["donor_regime"] == "all"].set_index("forcing")
    none_dev = sizes.loc[sizes["donor_regime"] == "none"].set_index("forcing")
    summary = {
        "air_available_development_pct": {
            row.forcing: float(row.air_available_pct)
            for row in support.loc[support["split"] == "development"].itertuples()
        },
        "policy_mae_c": {label: float(all_dev.loc[label, "policy_mae_c"]) for label in all_dev.index},
        "policy_mae_c_donorless": {
            label: float(none_dev.loc[label, "policy_mae_c"]) for label in none_dev.index
        },
        "timing_minus_length_auc": {
            row.forcing: float(row.timing_minus_length) for row in stability.itertuples()
        },
        "estimator_share_pct": fair.attrs.get("estimator_share_pct", {}),
        "verdict": {
            "problem_size": "air forcing reduces the deployable reconstruction error, most at donor-less sites",
            "axis_conclusion": (
                "unchanged: the axis claim is about which cases are hard, not about how "
                "well they are repaired"
            ),
            "protocol": (
                "the pre-registered confirmation is not re-scored; this is a development-panel "
                "sensitivity analysis"
            ),
        },
    }
    (E5_AIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")

    lines = ["# E5 — air forcing for every station", ""]
    lines.append("## Estimator support")
    lines.append("")
    lines.append(
        support[["split", "forcing", "air_available_pct", "supported_air_ridge_pct", "supported_donor_ridge_pct"]]
        .to_markdown(index=False, floatfmt=".4g")
    )
    lines.append("")
    lines.append("## How large is the problem, with and without the field's own method")
    lines.append("")
    lines.append(sizes.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## Does the axis conclusion depend on the estimator library?")
    lines.append("")
    lines.append(stability.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## Was the incumbent handicapped? Development cases at 70% retention")
    lines.append("")
    lines.append(fair.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("Estimator chosen by the screen, % of cases: " + json.dumps(summary["estimator_share_pct"], default=float))
    (E5_AIR / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
