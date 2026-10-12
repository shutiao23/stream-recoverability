#!/usr/bin/env python3
"""E2 — deploy both rules on the station-years that really have holes in them.

Everything the v17 study reports is computed on a complete station-year with a
synthetic hole punched in it. That is the only way to have truth, and it means
the rule has never once acted on a record that actually has a gap. The 2,422
genuinely incomplete station-years in the same archive appear in that programme
only as a source of realistic outage geometry.

They cannot be scored. They can be decided, and three things follow that do not
need a truth:

E2a  how often the incumbent and a timing rule disagree, at matched retention;
E2b  what a risk model fitted on the scored cases predicts for each admitted
     set -- an extrapolation, checked for calibration on the reserved panel
     first and labelled as an extrapolation throughout;
E2c  what happens to an archive-level number under each rule.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import STEP3_CASES  # noqa: E402
from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    gather,
    information_conditioned_choice,
)
from stream_recoverability.experiments.v17_fitness.screen import feature_frame  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v18_closure.deployment import real_year_table  # noqa: E402
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    E2_DEPLOYMENT,
    JOHNSON_FILLED_DAYS,
    JOHNSON_UNFILLED_DAYS,
    MAX_PEAK_HIDDEN_FOR_ADMISSION,
    PRIMARY_TOLERANCE_C,
)

EXCEEDANCE_C = 20.0
RETENTION_GRID = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def ranked_admission(score: np.ndarray, retention: float, seed: int) -> np.ndarray:
    """Keep the ``retention`` share with the smallest score, ties broken at random."""

    rng = np.random.default_rng(int(seed))
    order = np.lexsort((rng.random(len(score)), np.asarray(score, dtype=float)))
    keep = np.zeros(len(score), dtype=bool)
    keep[order[: int(round(float(retention) * len(score)))]] = True
    return keep


# ------------------------------------------------------------------ E2a

def threshold_disagreement(incomplete: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The two rules as an agency would actually write them, not as rankings."""

    rows = []
    for label, days in (
        ("Johnson unfilled, longest run <= 49 d", JOHNSON_UNFILLED_DAYS),
        ("Johnson with imputation, longest run <= 140 d", JOHNSON_FILLED_DAYS),
    ):
        length_admits = incomplete["longest_run"] <= days
        timing_admits = incomplete["peak_overlap"] <= MAX_PEAK_HIDDEN_FOR_ADMISSION
        rows.append(
            {
                "incumbent": label,
                "n_station_years": int(len(incomplete)),
                "length_admits_pct": float(length_admits.mean() * 100),
                "timing_admits_pct": float(timing_admits.mean() * 100),
                "agree_admit": int((length_admits & timing_admits).sum()),
                "agree_reject": int((~length_admits & ~timing_admits).sum()),
                "admitted_by_length_rejected_by_timing": int((length_admits & ~timing_admits).sum()),
                "rejected_by_length_admitted_by_timing": int((~length_admits & timing_admits).sum()),
                "disagreement_pct": float((length_admits != timing_admits).mean() * 100),
            }
        )
    frame = pd.DataFrame(rows)

    unfilled = incomplete.assign(
        disagree=(
            (incomplete["longest_run"] <= JOHNSON_UNFILLED_DAYS)
            != (incomplete["peak_overlap"] <= MAX_PEAK_HIDDEN_FOR_ADMISSION)
        ).astype(float),
        dangerous=(
            (incomplete["longest_run"] <= JOHNSON_UNFILLED_DAYS)
            & (incomplete["peak_overlap"] > MAX_PEAK_HIDDEN_FOR_ADMISSION)
        ).astype(float),
    )
    summary = {
        "disagreement_interval": cluster_bootstrap(
            unfilled, lambda block: float(block["disagree"].mean()), seed=20260924
        ),
        "dangerous_cell_interval": cluster_bootstrap(
            unfilled, lambda block: float(block["dangerous"].mean()), seed=20260924
        ),
        "any_peak_day_hidden_pct": float((incomplete["peak_overlap"] > 0).mean() * 100),
        "half_the_peak_window_hidden_n": int((incomplete["peak_overlap"] > 0.5).sum()),
        "median_missing_days": float(incomplete["total_missing"].median()),
        "p90_missing_days": float(incomplete["total_missing"].quantile(0.90)),
    }
    return frame, summary


def matched_retention_disagreement(incomplete: pd.DataFrame) -> pd.DataFrame:
    """The same comparison as a ranking, swept over retention."""

    rows = []
    for retention in RETENTION_GRID:
        length_keep = ranked_admission(incomplete["longest_run"].to_numpy(), retention, 1)
        timing_keep = ranked_admission(incomplete["peak_overlap"].to_numpy(), retention, 2)
        rows.append(
            {
                "retention": retention,
                "disagreement_pct": float((length_keep != timing_keep).mean() * 100),
                "admitted_by_length_rejected_by_timing": int((length_keep & ~timing_keep).sum()),
                "rejected_by_length_admitted_by_timing": int((~length_keep & timing_keep).sum()),
                "mean_peak_overlap_length_admitted": float(
                    incomplete.loc[length_keep, "peak_overlap"].mean()
                ),
                "mean_peak_overlap_timing_admitted": float(
                    incomplete.loc[timing_keep, "peak_overlap"].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def disagreement_by_provider(incomplete: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for provider, block in incomplete.groupby("provider"):
        if len(block) < 20:
            continue
        length_admits = block["longest_run"] <= JOHNSON_UNFILLED_DAYS
        timing_admits = block["peak_overlap"] <= MAX_PEAK_HIDDEN_FOR_ADMISSION
        rows.append(
            {
                "provider": provider,
                "n_incomplete_station_years": int(len(block)),
                "disagreement_pct": float((length_admits != timing_admits).mean() * 100),
                "admitted_by_length_rejected_by_timing": int((length_admits & ~timing_admits).sum()),
                "rejected_by_length_admitted_by_timing": int((~length_admits & timing_admits).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("n_incomplete_station_years", ascending=False)


# ------------------------------------------------------------------ E2b

def fit_risk_model(cases: pd.DataFrame, seed: int = 0) -> tuple[HistGradientBoostingClassifier, pd.DataFrame]:
    """P(consequential error) from decision-time features, fitted on scored cases.

    Every feature it uses is one the real incomplete years also carry, which is
    what makes the transport possible. The model is fitted on development cases
    and its calibration is checked on the reserved panel before it is applied
    to records that cannot be scored at all.
    """

    development = cases.loc[cases["split_role"] == "development"].copy()
    reserved = cases.loc[cases["split_role"] == "reserved"].copy()
    for block in (development, reserved):
        block["policy_abs_error"] = gather(block, information_conditioned_choice(block))
    development = development.dropna(subset=["policy_abs_error"])
    reserved = reserved.dropna(subset=["policy_abs_error"])

    y = (development["policy_abs_error"] > PRIMARY_TOLERANCE_C).astype(int)
    model = HistGradientBoostingClassifier(
        max_depth=4, max_iter=350, learning_rate=0.06, min_samples_leaf=40, random_state=seed
    ).fit(feature_frame(development), y)

    predicted = model.predict_proba(feature_frame(reserved))[:, 1]
    actual = (reserved["policy_abs_error"] > PRIMARY_TOLERANCE_C).astype(int).to_numpy()
    deciles = pd.qcut(predicted, 10, labels=False, duplicates="drop")
    calibration = (
        pd.DataFrame({"decile": deciles, "predicted": predicted, "actual": actual})
        .groupby("decile")
        .agg(n=("actual", "size"), predicted=("predicted", "mean"), actual=("actual", "mean"))
        .reset_index()
    )
    calibration["difference_points"] = (calibration["predicted"] - calibration["actual"]) * 100
    return model, calibration


def transported_risk(model, incomplete: pd.DataFrame) -> pd.DataFrame:
    """The predicted consequential-error rate of each admitted set."""

    risk = model.predict_proba(feature_frame(incomplete))[:, 1]
    frame = incomplete.assign(predicted_risk=risk)
    rules = {
        "admit everything": np.ones(len(frame), dtype=bool),
        "Johnson unfilled (<= 49 d)": (frame["longest_run"] <= JOHNSON_UNFILLED_DAYS).to_numpy(),
        "Johnson with imputation (<= 140 d)": (frame["longest_run"] <= JOHNSON_FILLED_DAYS).to_numpy(),
        "peak window <= 10% hidden": (frame["peak_overlap"] <= MAX_PEAK_HIDDEN_FOR_ADMISSION).to_numpy(),
    }
    rows = []
    for name, keep in rules.items():
        rows.append(
            {
                "rule": name,
                "retention_pct": float(keep.mean() * 100),
                "predicted_consequential_rate_pct": float(risk[keep].mean() * 100),
                "predicted_rate_among_excluded_pct": (
                    float(risk[~keep].mean() * 100) if (~keep).any() else float("nan")
                ),
            }
        )
    # A ranked screen at the retention each threshold rule implies, so the
    # comparison is at equal retention rather than at equal threshold.
    for name, keep in rules.items():
        if name == "admit everything":
            continue
        matched = ranked_admission(risk, float(keep.mean()), 7)
        rows.append(
            {
                "rule": f"risk-ranked screen at the retention of {name}",
                "retention_pct": float(matched.mean() * 100),
                "predicted_consequential_rate_pct": float(risk[matched].mean() * 100),
                "predicted_rate_among_excluded_pct": float(risk[~matched].mean() * 100),
            }
        )
    return pd.DataFrame(rows), frame


# ------------------------------------------------------------------ E2c

def archive_consequence(frame: pd.DataFrame, complete: pd.DataFrame) -> pd.DataFrame:
    """What a regional summary looks like under each admission rule.

    Two numbers an archive is used for: the mean annual peak it reports, and how
    many station-years it counts above a cold-water criterion. Both are computed
    on the union of the fully observed years -- which every rule admits -- and
    whichever incomplete years the rule admits, repaired by the deployed policy.
    """

    rules = {
        "observed days, no screening (current default)": (
            np.ones(len(frame), dtype=bool),
            "metric_observed_days",
        ),
        "repair everything, no screening": (np.ones(len(frame), dtype=bool), "metric_policy"),
        "Johnson unfilled (<= 49 d)": (
            (frame["longest_run"] <= JOHNSON_UNFILLED_DAYS).to_numpy(),
            "metric_policy",
        ),
        "Johnson with imputation (<= 140 d)": (
            (frame["longest_run"] <= JOHNSON_FILLED_DAYS).to_numpy(),
            "metric_policy",
        ),
        "peak window <= 10% hidden": (
            (frame["peak_overlap"] <= MAX_PEAK_HIDDEN_FOR_ADMISSION).to_numpy(),
            "metric_policy",
        ),
    }
    baseline_peak = float(complete["metric_policy"].mean())
    baseline_exceed = float((complete["metric_policy"] > EXCEEDANCE_C).mean())
    rows = []
    for name, (keep, column) in rules.items():
        block = frame.loc[keep].dropna(subset=[column])
        admitted = block[column]
        pooled = pd.concat([complete["metric_policy"], admitted])
        rows.append(
            {
                "rule": name,
                "incomplete_years_admitted": int(len(admitted)),
                "archive_station_years": int(len(pooled)),
                "mean_annual_peak_c": float(pooled.mean()),
                "shift_vs_complete_only_c": float(pooled.mean() - baseline_peak),
                "share_above_20c_pct": float((pooled > EXCEEDANCE_C).mean() * 100),
                "share_shift_points": float(((pooled > EXCEEDANCE_C).mean() - baseline_exceed) * 100),
                # Archive quality, measurable without a truth: a year whose peak
                # window is mostly hidden reports a peak that was inferred
                # rather than observed, whatever estimator produced it.
                "admitted_with_any_peak_day_hidden": int((block["peak_overlap"] > 0).sum()),
                "admitted_with_half_the_peak_window_hidden": int((block["peak_overlap"] > 0.5).sum()),
                "admitted_with_peak_window_wholly_hidden": int((block["peak_overlap"] >= 0.999).sum()),
                "mean_peak_overlap_admitted": float(block["peak_overlap"].mean()),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    E2_DEPLOYMENT.mkdir(parents=True, exist_ok=True)
    cached = E2_DEPLOYMENT / "real_station_years.parquet"
    if "--reuse" in sys.argv and cached.exists():
        years = pd.read_parquet(cached)
    else:
        years = real_year_table(workers=48)
        years.to_parquet(cached)
    incomplete = years.loc[~years["complete"]].dropna(subset=["peak_overlap"]).reset_index(drop=True)
    complete = years.loc[years["complete"]].reset_index(drop=True)

    thresholds, disagreement_summary = threshold_disagreement(incomplete)
    thresholds.to_csv(E2_DEPLOYMENT / "threshold_disagreement.csv", index=False)
    matched = matched_retention_disagreement(incomplete)
    matched.to_csv(E2_DEPLOYMENT / "matched_retention_disagreement.csv", index=False)
    by_provider = disagreement_by_provider(incomplete)
    by_provider.to_csv(E2_DEPLOYMENT / "disagreement_by_provider.csv", index=False)

    cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
    model, calibration = fit_risk_model(cases)
    calibration.to_csv(E2_DEPLOYMENT / "risk_model_calibration_on_reserved.csv", index=False)
    transported, scored = transported_risk(model, incomplete)
    transported.to_csv(E2_DEPLOYMENT / "transported_risk.csv", index=False)
    scored.to_parquet(E2_DEPLOYMENT / "incomplete_years_scored.parquet")

    consequence = archive_consequence(incomplete, complete)
    consequence.to_csv(E2_DEPLOYMENT / "archive_consequence.csv", index=False)

    summary = {
        "n_station_years": int(len(years)),
        "n_complete": int(years["complete"].sum()),
        "n_incomplete": int((~years["complete"]).sum()),
        "n_incomplete_decidable": int(len(incomplete)),
        "disagreement": disagreement_summary,
        "risk_model_max_decile_miscalibration_points": float(
            calibration["difference_points"].abs().max()
        ),
        "verdict": {
            "prediction": "the two rules disagree on a material share of real incomplete years",
            "threshold": "a disagreement rate below 3% would make the axis substitution immaterial in practice",
            "outcome": (
                "supported"
                if thresholds.loc[0, "disagreement_pct"] >= 3.0
                else "not supported"
            ),
        },
    }
    (E2_DEPLOYMENT / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")

    lines = ["# E2 — deployment on the incomplete archive", ""]
    lines.append(
        f"{summary['n_station_years']:,} real station-years: {summary['n_complete']:,} fully observed "
        f"and {summary['n_incomplete']:,} incomplete, of which {summary['n_incomplete_decidable']:,} "
        "carry a climatological peak window and can be decided."
    )
    lines.append("")
    lines.append("## E2a — do the rules disagree?")
    lines.append("")
    lines.append(thresholds.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append(matched.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append(by_provider.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## E2b — transported risk (extrapolation)")
    lines.append("")
    lines.append(
        "The risk model is fitted on development cases and its calibration checked on the "
        f"reserved panel first: the largest decile miscalibration is "
        f"{summary['risk_model_max_decile_miscalibration_points']:.2f} points."
    )
    lines.append("")
    lines.append(calibration.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append(transported.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## E2c — what changes in the archive")
    lines.append("")
    lines.append(consequence.to_markdown(index=False, floatfmt=".4g"))
    (E2_DEPLOYMENT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
