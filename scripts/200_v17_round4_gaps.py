#!/usr/bin/env python3
"""Four gaps a fourth reading finds in the current manuscript.

1. The mechanism behind the metric dichotomy is asserted, not tested. "An
   average is a sum over days so what matters is how many are missing; an
   extreme lives in a window so what matters is whether the window survived"
   makes a sharp, falsifiable prediction about which covariate the error scales
   with. Test it.
2. The dichotomy is established on four endpoints but only one gets a screen.
   If timing governs the amplitude too, a screen on the amplitude should also
   beat the length rule out of sample.
3. A perfect 0 of 938 missed exceedances is not impressive if few retained
   years sit anywhere near the threshold. Restrict to the years where the call
   is actually close.
4. Screening is not the only thing an interval can be used for. A scientist may
   prefer to keep every year and abstain only where the interval straddles the
   threshold. That is a different action space and a real competitor, and the
   paper never tries it.
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
from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    gather,
    information_conditioned_choice,
)
from stream_recoverability.experiments.v17_fitness.screen import out_of_fold_certificates  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP4_CEILING,
    STEP6_SCREEN,
)

STEP20 = RESULTS_ROOT / "step20_round4"
RETENTION = 0.70
THRESHOLD_C = 20.0


# ---------------------------------------------------------------- gap 1
def mechanism_gradients(cases: pd.DataFrame) -> pd.DataFrame:
    """Does each endpoint's error scale with the covariate the story names?"""

    choice = information_conditioned_choice(cases)
    frame = cases[["total_missing", "peak_overlap"]].apply(pd.to_numeric, errors="coerce").copy()
    frame["missing_bin"] = pd.qcut(frame["total_missing"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
    frame["overlap_bin"] = pd.cut(
        frame["peak_overlap"], [-0.001, 0.001, 0.5, 1.001], labels=["none", "<half", "most/all"]
    )
    rows = []
    for metric in ("hottest30", "annual_mean"):
        frame["err"] = gather(cases, choice, prefix=f"abserr_{metric}_")
        grid = frame.groupby(["missing_bin", "overlap_bin"], observed=True)["err"].mean().unstack()
        # Gradient along each axis, averaged over the other.
        along_missing = float(grid.mean(axis=1).iloc[-1] / max(grid.mean(axis=1).iloc[0], 1e-9))
        along_overlap = float(grid.mean(axis=0).iloc[-1] / max(grid.mean(axis=0).iloc[0], 1e-9))
        for missing_bin in grid.index:
            for overlap_bin in grid.columns:
                rows.append(
                    {
                        "metric": metric,
                        "missing_quartile": str(missing_bin),
                        "peak_overlap": str(overlap_bin),
                        "mean_abs_error_c": float(grid.loc[missing_bin, overlap_bin]),
                    }
                )
        rows.append(
            {
                "metric": metric,
                "missing_quartile": "RATIO Q4/Q1",
                "peak_overlap": "averaged",
                "mean_abs_error_c": along_missing,
            }
        )
        rows.append(
            {
                "metric": metric,
                "missing_quartile": "averaged",
                "peak_overlap": "RATIO most-or-all / none",
                "mean_abs_error_c": along_overlap,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- gap 2
def amplitude_screen(development: pd.DataFrame, reserved: pd.DataFrame, scale: float) -> dict:
    """Does a screen trained on the amplitude also beat the length rule?"""

    tolerance = (PRIMARY_TOLERANCE_C / 1.062) * scale
    out: dict[str, object] = {"tolerance_c": tolerance}
    for label, frame in (("development", development), ("reserved", reserved)):
        choice = information_conditioned_choice(frame)
        error = pd.Series(gather(frame, choice, prefix="abserr_amplitude30_"), index=frame.index)
        block = frame.copy()
        block["abserr_policy"] = error
        block["err_policy"] = error
        for name in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge"):
            block[f"abserr_{name}"] = pd.to_numeric(block.get(f"abserr_amplitude30_{name}"), errors="coerce")
            block[f"err_{name}"] = block[f"abserr_{name}"]
        certificates = out_of_fold_certificates(block.reset_index(drop=True), seed=0)
        rng = np.random.default_rng(41)
        length = pd.Series(
            pd.to_numeric(frame["longest_run"], errors="coerce").to_numpy() + rng.random(len(frame)),
            index=frame.index,
        )

        def rate(score: pd.Series, err: pd.Series) -> float:
            f = frontier_for_score(score, err)
            return float(f.loc[f["retention"].eq(RETENTION), f"rate_above_{PRIMARY_TOLERANCE_C}"].iloc[0])

        # Score at the amplitude's own tolerance rather than the peak's.
        def rate_at(score: np.ndarray, err: np.ndarray) -> float:
            good = np.isfinite(err)
            s = np.where(np.isfinite(score), score, np.inf)[good]
            e = err[good]
            order = np.argsort(s, kind="mergesort")
            k = max(1, int(round(RETENTION * len(e))))
            return float((e[order[:k]] > tolerance).mean())

        cert_err = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce").to_numpy()
        cert_score = pd.to_numeric(certificates["certificate_bound"], errors="coerce").to_numpy()
        out[label] = {
            "n_cases": int(len(frame)),
            "length_rule_at_70": rate_at(length.to_numpy(), error.to_numpy()),
            "certificate_at_70": rate_at(cert_score, cert_err),
        }
        out[label]["points_saved"] = (out[label]["length_rule_at_70"] - out[label]["certificate_at_70"]) * 100
    return out


# ---------------------------------------------------------------- gap 3
def near_threshold(reserved: pd.DataFrame, certificates: pd.DataFrame) -> pd.DataFrame:
    """Restrict the exceedance judgement to years where the call is close."""

    truth = pd.to_numeric(reserved["truth_hottest30"], errors="coerce")
    bound = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
    length = pd.to_numeric(reserved["longest_run"], errors="coerce")
    retention = float((bound <= PRIMARY_TOLERANCE_C).mean())
    length_threshold = float(length.quantile(retention))
    choice = information_conditioned_choice(reserved)
    policy_metric = truth + pd.Series(gather(reserved, choice, prefix="err_"), index=reserved.index)

    estimates = {
        "observed_days_all": (pd.to_numeric(reserved["metric_observed_days"], errors="coerce"), pd.Series(True, index=reserved.index)),
        "reconstruct_all": (policy_metric, pd.Series(True, index=reserved.index)),
        "length_screened": (policy_metric, length <= length_threshold),
        "certificate_screened": (pd.to_numeric(certificates["certificate_metric"], errors="coerce"), bound <= PRIMARY_TOLERANCE_C),
    }
    rows = []
    for margin in (None, 1.0, 0.5):
        close = pd.Series(True, index=reserved.index) if margin is None else (truth - THRESHOLD_C).abs() <= margin
        for name, (values, keep) in estimates.items():
            mask = keep & close & values.notna() & truth.notna()
            if int(mask.sum()) == 0:
                continue
            predicted = values[mask] > THRESHOLD_C
            actual = truth[mask] > THRESHOLD_C
            rows.append(
                {
                    "subset": "all retained" if margin is None else f"truth within {margin} °C of 20",
                    "treatment": name,
                    "n_scored": int(mask.sum()),
                    "misclassification_rate": float((predicted != actual).mean()),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- gap 4
def abstain_versus_screen(reserved: pd.DataFrame, certificates: pd.DataFrame) -> pd.DataFrame:
    """Keep every year and abstain where the interval straddles the threshold.

    The natural alternative to discarding a station-year is to keep it and
    decline only the specific judgement the uncertainty cannot support.
    """

    truth = pd.to_numeric(reserved["truth_hottest30"], errors="coerce")
    low = pd.to_numeric(certificates["interval_low"], errors="coerce")
    high = pd.to_numeric(certificates["interval_high"], errors="coerce")
    metric = pd.to_numeric(certificates["certificate_metric"], errors="coerce")
    bound = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
    actual = truth > THRESHOLD_C

    # The interval is on the signed error, so the metric interval is metric + [low, high].
    interval_low, interval_high = metric + low, metric + high
    decisive = (interval_low > THRESHOLD_C) | (interval_high < THRESHOLD_C)

    rows = []
    for label, keep in (
        ("screen at the 0.5 °C tolerance", bound <= PRIMARY_TOLERANCE_C),
        ("abstain only where the interval straddles 20 °C", decisive),
        ("both", (bound <= PRIMARY_TOLERANCE_C) & decisive),
    ):
        mask = keep & metric.notna() & truth.notna()
        if int(mask.sum()) == 0:
            continue
        predicted = metric[mask] > THRESHOLD_C
        rows.append(
            {
                "policy": label,
                "share_of_years_judged": float(mask.mean()),
                "n_judged": int(mask.sum()),
                "misclassification_rate": float((predicted != actual[mask]).mean()),
                "false_negative_rate": float(((~predicted) & actual[mask]).sum() / max(1, int(actual[mask].sum()))),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    STEP20.mkdir(parents=True, exist_ok=True)
    development = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)
    reserved = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
    reserved_cert = pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet").reset_index(drop=True)
    generality = pd.read_csv(RESULTS_ROOT / "step17_metric_generality" / "metric_generality.csv").set_index("metric")

    gradients = mechanism_gradients(development)
    gradients.to_csv(STEP20 / "mechanism_gradients.csv", index=False)

    amplitude = amplitude_screen(development, reserved, float(generality.loc["amplitude30", "interannual_sd"]))
    (STEP20 / "amplitude_screen.json").write_text(json.dumps(amplitude, indent=2), encoding="utf-8")

    close = near_threshold(reserved, reserved_cert)
    close.to_csv(STEP20 / "near_threshold.csv", index=False)

    abstain = abstain_versus_screen(reserved, reserved_cert)
    abstain.to_csv(STEP20 / "abstain_versus_screen.csv", index=False)

    lines = ["# Step 20 — four gaps a fourth reading finds", ""]
    lines.append("## 1. Does each endpoint's error scale with the covariate the mechanism names?")
    lines.append("")
    lines.append(gradients.round(4).to_string(index=False))
    lines.append("")
    lines.append("## 2. Does a screen on the amplitude also beat the length rule?")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(amplitude, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 3. The exceedance judgement, restricted to years where the call is close")
    lines.append("")
    lines.append(close.round(4).to_string(index=False))
    lines.append("")
    lines.append("## 4. Screening versus abstaining on the judgement itself")
    lines.append("")
    lines.append(abstain.round(4).to_string(index=False))
    (STEP20 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(gradients.round(4).to_string(index=False))
    print()
    print(json.dumps(amplitude, indent=2))
    print()
    print(close.round(4).to_string(index=False))
    print()
    print(abstain.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
