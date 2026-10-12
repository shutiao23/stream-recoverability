#!/usr/bin/env python3
"""Is the central claim an artefact of how the endpoint, the threshold, or the
reference series were defined?

Four checks, each aimed at a specific way the paper could be wrong rather than
at a general wish for more experiments.

1. The title rests on AUC point estimates with no uncertainty. Put clustered
   intervals on the contrasts that carry it.
2. The peak is a thirty-day mean; much regulatory practice uses a seven-day
   window. A shorter extreme is more localised in time, so the mechanism
   predicts the timing effect should be *stronger* there. That is a prediction
   the paper can be wrong about.
3. The reference series is treated as exact. Loggers carry roughly 0.15 C of
   error. Perturb the reference and see whether anything moves.
4. The exceedance result uses 20 C without a named standard. Sweep it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import frontier_for_score  # noqa: E402
from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    gather,
    information_conditioned_choice,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    EXCEEDANCE_SWEEP_C,
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    SENSOR_NOISE_C,
    STEP10_CONFIRM,
    STEP4_CEILING,
    STEP6_SCREEN,
)

STEP22 = RESULTS_ROOT / "step22_robustness"
RETENTION = 0.70
TOLERANCE_FRACTION = PRIMARY_TOLERANCE_C / 1.062


def natural_scale(cases: pd.DataFrame, metric: str) -> float:
    truth = cases.groupby(["network_id", "station_id", "year"])[f"truth_{metric}"].first().reset_index()
    per_station = truth.groupby(["network_id", "station_id"])[f"truth_{metric}"].agg(["std", "size"])
    return float(per_station.loc[per_station["size"] >= 4, "std"].dropna().mean())


def auc_contrast(cases: pd.DataFrame, metric: str, tolerance: float) -> dict:
    """AUC(peak overlap) minus AUC(outage length), clustered by network."""

    choice = information_conditioned_choice(cases)
    error = pd.Series(gather(cases, choice, prefix=f"abserr_{metric}_"), index=cases.index)
    block = cases[["network_id"]].copy()
    block["label"] = (error > tolerance).astype(int)
    block["peak_overlap"] = pd.to_numeric(cases["peak_overlap"], errors="coerce")
    block["warm"] = -pd.to_numeric(cases["warm_observed_fraction"], errors="coerce")
    block["length"] = pd.to_numeric(cases["longest_run"], errors="coerce")
    block = block.dropna()

    def contrast(frame: pd.DataFrame) -> float:
        if frame["label"].nunique() < 2:
            return float("nan")
        timing = max(
            roc_auc_score(frame["label"], frame["peak_overlap"]),
            roc_auc_score(frame["label"], frame["warm"]),
        )
        return float(timing - roc_auc_score(frame["label"], frame["length"]))

    stat = cluster_bootstrap(block, contrast, draws=1200, seed=0)
    return {
        "metric": metric,
        "tolerance_c": tolerance,
        "n": int(len(block)),
        "base_rate": float(block["label"].mean()),
        "auc_timing_minus_length": stat["point"],
        "ci_low": stat["low"],
        "ci_high": stat["high"],
        "timing_wins": bool(stat["low"] > 0),
        "length_wins": bool(stat["high"] < 0),
    }


def _rate_locked(score: pd.Series, clean_errors: pd.Series, eval_errors: pd.Series) -> float:
    """Rank by ``score`` using the clean finite mask; evaluate ``eval_errors`` on that set."""

    values = pd.to_numeric(score, errors="coerce").to_numpy(dtype=float)
    clean = pd.to_numeric(clean_errors, errors="coerce").to_numpy(dtype=float)
    eval_err = pd.to_numeric(eval_errors, errors="coerce").to_numpy(dtype=float)
    good = np.isfinite(clean) & np.isfinite(eval_err)
    values = np.where(np.isfinite(values), values, np.inf)[good]
    eval_err = eval_err[good]
    order = np.argsort(values, kind="mergesort")
    k = max(1, int(round(float(RETENTION) * len(eval_err))))
    return float((eval_err[order[:k]] > PRIMARY_TOLERANCE_C).mean())


def noise_sensitivity(cases: pd.DataFrame, certificates: pd.DataFrame) -> dict:
    """Recompute the headline with a perturbed reference series.

    Clean and noisy branches must use the same reconstruction choice, the same
    ranking scores, and the same retained cases. Using information-conditioned
    choice for the noisy arm while the certificate arm reports certificate
    errors compares different methods, not sensor noise.
    """

    choice = certificates["certificate_choice"]
    clean = pd.Series(gather(cases, choice, prefix="abserr_"), index=cases.index)
    noisy = pd.Series(gather(cases, choice, prefix="abserr_noisy_"), index=cases.index)
    rng = np.random.default_rng(83)
    length = pd.Series(
        pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy() + rng.random(len(cases)), index=cases.index
    )
    score = pd.to_numeric(certificates["certificate_bound"], errors="coerce")

    length_clean = _rate_locked(length, clean, clean)
    length_noisy = _rate_locked(length, clean, noisy)
    cert_clean = _rate_locked(score, clean, clean)
    cert_noisy = _rate_locked(score, clean, noisy)
    return {
        "sensor_noise_c": SENSOR_NOISE_C,
        "method_locked_to": "certificate_choice",
        "mean_abs_error_clean_c": float(clean.mean()),
        "mean_abs_error_noisy_c": float(noisy.mean()),
        "length_rule_at_70_clean": length_clean,
        "length_rule_at_70_noisy": length_noisy,
        "certificate_at_70_clean": cert_clean,
        "certificate_at_70_noisy": cert_noisy,
        "contrast_clean_points": (length_clean - cert_clean) * 100,
        "contrast_noisy_points": (length_noisy - cert_noisy) * 100,
    }


def threshold_sweep(cases: pd.DataFrame, certificates: pd.DataFrame) -> pd.DataFrame:
    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce")
    bound = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
    length = pd.to_numeric(cases["longest_run"], errors="coerce")
    choice = information_conditioned_choice(cases)
    policy_metric = truth + pd.Series(gather(cases, choice, prefix="err_"), index=cases.index)
    cert_metric = pd.to_numeric(certificates["certificate_metric"], errors="coerce")
    retention = float((bound <= PRIMARY_TOLERANCE_C).mean())
    length_threshold = float(length.quantile(retention))

    rows = []
    for threshold in EXCEEDANCE_SWEEP_C:
        actual = truth > threshold
        if actual.mean() < 0.02 or actual.mean() > 0.98:
            continue
        for name, values, keep in (
            ("observed_days", pd.to_numeric(cases["metric_observed_days"], errors="coerce"), pd.Series(True, index=cases.index)),
            ("reconstruct_all", policy_metric, pd.Series(True, index=cases.index)),
            ("length_screened", policy_metric, length <= length_threshold),
            ("certificate_screened", cert_metric, bound <= PRIMARY_TOLERANCE_C),
        ):
            mask = keep & values.notna() & truth.notna()
            if int(mask.sum()) == 0:
                continue
            predicted = values[mask] > threshold
            rows.append(
                {
                    "threshold_c": float(threshold),
                    "base_rate_exceeding": float(actual.mean()),
                    "treatment": name,
                    "retention": float(mask.mean()),
                    "misclassification_rate": float((predicted != actual[mask]).mean()),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    STEP22.mkdir(parents=True, exist_ok=True)
    development = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)
    dev_cert = pd.read_parquet(STEP6_SCREEN / "development_certificates.parquet").reset_index(drop=True)
    reserved = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
    res_cert = pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet").reset_index(drop=True)

    metrics = ["hottest7", "hottest30", "amplitude30", "annual_mean", "coldest30"]
    contrasts = []
    for metric in metrics:
        if f"truth_{metric}" not in development.columns:
            continue
        scale = natural_scale(development, metric)
        contrasts.append(auc_contrast(development, metric, TOLERANCE_FRACTION * scale))
    contrast_table = pd.DataFrame(contrasts)
    contrast_table.to_csv(STEP22 / "auc_contrasts.csv", index=False)

    noise = noise_sensitivity(development, dev_cert)
    noise_reserved = noise_sensitivity(reserved, res_cert)
    (STEP22 / "noise_sensitivity.json").write_text(
        json.dumps({"development": noise, "reserved": noise_reserved}, indent=2), encoding="utf-8"
    )

    sweep = threshold_sweep(reserved, res_cert)
    sweep.to_csv(STEP22 / "threshold_sweep.csv", index=False)
    pivot = sweep.pivot_table(index="threshold_c", columns="treatment", values="misclassification_rate")

    lines = ["# Step 22 — endpoint, threshold and reference-series robustness", ""]
    lines.append("## Which axis wins, with clustered intervals on the contrast")
    lines.append("")
    lines.append("Positive means timing beats outage length. The seven-day peak is the")
    lines.append("regulatory-style window; the mechanism predicts the timing effect is")
    lines.append("stronger there than at thirty days, because a shorter extreme is more")
    lines.append("localised in time.")
    lines.append("")
    lines.append(contrast_table.round(4).to_string(index=False))
    lines.append("")
    lines.append(f"## Reference series perturbed by {SENSOR_NOISE_C} °C of instrument error")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({"development": noise, "reserved": noise_reserved}, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Exceedance misclassification across ecological thresholds, reserved panel")
    lines.append("")
    lines.append(pivot.round(4).to_string())
    (STEP22 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(contrast_table.round(4).to_string(index=False))
    print()
    print(json.dumps({"development": noise, "reserved": noise_reserved}, indent=2))
    print()
    print(pivot.round(4).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
