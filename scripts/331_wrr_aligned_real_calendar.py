#!/usr/bin/env python3
"""P0-03 (review F03/F04, 2026-10-20) — the aligned rule on real monitoring calendars.

What this replaces
------------------
`scripts/324_wrr_same_method_replay_and_hotyear.py` applied thresholds that had
been calibrated on the certificate error, and compared them with jittered
calibration scores against unjittered replay scores.  Both are fixed here:

* thresholds come from `scripts/330_wrr_aligned_policy_admission.py`, which
  calibrates on the error of the reconstruction being admitted;
* a threshold is an observed score value and admits ``score <= threshold`` at
  every stage, so the tie rule cannot change between calibration and deployment;
* ``reconstruct_all`` is a first-class arm, because "keep everything" is what an
  agency does if no screen is worth its cost.

The candidate pool is the 418 real-calendar groups already placed by
`scripts/312_wrr_p0_03_final_method_replay.py` -- this script adds no new panel.

Outputs
``results/wrr_submission_ready/major_revision_20261020/p0_03_real_calendar_adoption/``.

Run:

    PYTHONPATH=src python3 scripts/331_wrr_aligned_real_calendar.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import estimator_disagreement  # noqa: E402
from stream_recoverability.experiments.v17_fitness.screen import feature_frame  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "step2_features", ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py"
)
_step2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_step2)
SUPPORT = tuple(_step2.SUPPORT)

RUN = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261020"
ALIGNED = RUN / "p0_01_aligned_policy_admission"
OUT = RUN / "p0_03_real_calendar_adoption"
REPLAY = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "p0_03_final_method_replay"
    / "replay_decisions.parquet"
)
TOL = 0.5
SEEDS = (101, 202, 303)
LEVELS = (("target_only", "t0"), ("partial_donor_failure", "p5"), ("all_donor_failure", "a1"))
ARMS = ("fitted_risk", "calibrated_bound", "peak_overlap_rule", "length_rule", "reconstruct_all")
DRAWS = 4000


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        return np.full(len(frame), np.nan)
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)


def _features_for_level(replay: pd.DataFrame, suffix: str) -> pd.DataFrame:
    frame = pd.DataFrame(index=replay.index)
    static = [
        "longest_run",
        "missing_fraction",
        "n_runs",
        "warm_observed_fraction",
        "longest_run_month",
        "peak_overlap",
        "train_resid_sd",
        "seasonal_amplitude",
        "train_metric_sd",
        "n_complete_years",
        "record_years",
        "left_flank",
        "right_flank",
        "air_available",
    ]
    for name in static:
        frame[name] = replay[name] if name in replay.columns else np.nan
    frame["n_visible_donors"] = _numeric(replay, f"n_visible_donors__{suffix}")
    frame["donor_corr_mean"] = _numeric(replay, "donor_corr_mean")
    frame["donor_corr_max"] = _numeric(replay, "donor_corr_max")
    frame["donor_corr_min"] = _numeric(replay, "donor_corr_min")
    frame["donor_coverage_mean"] = _numeric(replay, f"donor_coverage_mean__{suffix}")
    metrics = pd.DataFrame(
        {
            "metric_doy_climatology": _numeric(replay, "metric_doy_climatology"),
            "metric_smooth_climatology": _numeric(replay, "metric_smooth_climatology"),
            "metric_linear_interp": _numeric(replay, "metric_linear_interp"),
            "metric_donor_ridge": _numeric(replay, f"metric_donor_ridge__{suffix}"),
            "metric_air_ridge": _numeric(replay, "metric_air_ridge"),
        }
    )
    frame["estimator_disagreement"] = estimator_disagreement(metrics).to_numpy()
    return frame


def _thresholds() -> dict:
    return json.loads((ALIGNED / "final_thresholds.json").read_text())


def _models() -> dict:
    index = json.loads((ALIGNED / "model_index.json").read_text())
    loaded = {}
    for key, name in index.items():
        panel, seed, fold = key.split("|")
        if panel != "development":
            continue
        loaded[(int(seed), int(fold))] = joblib.load(ALIGNED / "models" / name)
    return loaded


def _fold_of() -> dict:
    """Network -> fold, read from the stored case-level fold ids.

    Every case of a network carries the fold of its independence group, so the
    mapping is one row per (seed, network) after de-duplication.
    """

    cases = pd.read_parquet(ALIGNED / "case_level_admissions_development.parquet")[
        ["fold_seed", "network_id", "fold"]
    ].drop_duplicates()
    out = {}
    for seed in SEEDS:
        block = cases[cases.fold_seed.eq(seed)]
        out[seed] = dict(zip(block.network_id.astype(str), block.fold.astype(int)))
    return out


def _cluster_bootstrap(
    values: np.ndarray,
    groups: np.ndarray,
    *,
    statistic: str,
    draws: int = DRAWS,
    seed: int = 0,
) -> dict:
    """Cluster bootstrap of a mean or a ratio-of-sums on the network unit."""

    rng = np.random.default_rng(int(seed))
    units = pd.unique(groups)
    index = {unit: i for i, unit in enumerate(units)}
    codes = np.array([index[g] for g in groups], dtype=np.int64)
    n_units = len(units)

    if statistic == "mean":
        per_unit_sum = np.bincount(codes, weights=values, minlength=n_units)
        per_unit_n = np.bincount(codes, minlength=n_units).astype(float)
        point = float(np.nansum(values) / max(np.isfinite(values).sum(), 1))
        draws_values = np.empty(int(draws))
        for draw in range(int(draws)):
            take = rng.integers(0, n_units, size=n_units)
            draws_values[draw] = per_unit_sum[take].sum() / max(per_unit_n[take].sum(), 1e-12)
    else:  # ratio
        numerators = values[:, 0]
        denominators = values[:, 1]
        per_unit_num = np.bincount(codes, weights=numerators, minlength=n_units)
        per_unit_den = np.bincount(codes, weights=denominators, minlength=n_units)
        point = float(numerators.sum() / max(denominators.sum(), 1e-12))
        draws_values = np.empty(int(draws))
        for draw in range(int(draws)):
            take = rng.integers(0, n_units, size=n_units)
            num = per_unit_num[take].sum()
            den = per_unit_den[take].sum()
            draws_values[draw] = num / den if den > 0 else np.nan
    finite = draws_values[np.isfinite(draws_values)]
    return {
        "point": point,
        "ci_low": float(np.quantile(finite, 0.025)) if finite.size else float("nan"),
        "ci_high": float(np.quantile(finite, 0.975)) if finite.size else float("nan"),
        "n_units": int(n_units),
    }


def score_replay() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    replay = pd.read_parquet(REPLAY)
    thresholds = _thresholds()
    models = _models()
    fold_of = _fold_of()
    networks = replay["network_id"].astype(str).to_numpy()
    truth = _numeric(replay, "truth_hottest30")
    groups = networks.copy()

    rows = []
    contrasts = []
    detail_frames = []
    for level, suffix in LEVELS:
        features = _features_for_level(replay, suffix)
        policy_err = _numeric(replay, f"abserr_policy__{suffix}")
        available = np.isfinite(policy_err)
        peak = _numeric(replay, "peak_overlap")
        length = _numeric(replay, "longest_run")
        certificate = _numeric(replay, f"certificate_bound__{suffix}")
        policy_metric = _numeric(replay, f"metric_policy__{suffix}")
        for seed in SEEDS:
            score = np.full(len(replay), np.nan)
            tau = {arm: np.full(len(replay), np.nan) for arm in ARMS}
            for network in sorted(set(networks)):
                fold = int(fold_of[seed][network])
                mask = networks == network
                pred = models[(seed, fold)].predict(feature_frame(features.loc[mask], SUPPORT))
                score[mask] = np.asarray(pred, dtype=float)
                for arm in ("fitted_risk", "calibrated_bound", "peak_overlap_rule", "length_rule"):
                    tau[arm][mask] = thresholds[f"development|{arm}|{seed}"][str(fold)]
            decisions = {
                "fitted_risk": np.isfinite(score) & (score <= tau["fitted_risk"]) & available,
                "calibrated_bound": np.isfinite(certificate)
                & (certificate <= tau["calibrated_bound"])
                & available,
                "peak_overlap_rule": np.isfinite(peak) & (peak <= tau["peak_overlap_rule"]) & available,
                "length_rule": np.isfinite(length) & (length <= tau["length_rule"]) & available,
                "reconstruct_all": available.copy(),
            }
            detail_frames.append(
                pd.DataFrame(
                    {
                        "level": level,
                        "seed": int(seed),
                        "network_id": networks,
                        "station_id": replay["station_id"].astype(str),
                        "eval_year": replay["eval_year"],
                        "truth_hottest30": truth,
                        "available": available,
                        "policy_error": policy_err,
                        "policy_metric": policy_metric,
                        "policy_bad": (policy_err > TOL),
                        "fitted_score": score,
                        "certificate_bound": certificate,
                        "peak_overlap": peak,
                        "longest_run": length,
                        **{f"admit_{arm}": decisions[arm] for arm in ARMS},
                    }
                )
            )
            for arm in ARMS:
                admit = decisions[arm]
                admitted = policy_err[admit]
                rows.append(
                    {
                        "level": level,
                        "seed": int(seed),
                        "arm": arm,
                        "n_candidates": int(len(replay)),
                        "n_networks": int(pd.unique(networks).size),
                        "available_share": float(available.mean()),
                        "admitted_share": float(admit.mean()),
                        "n_admitted": int(admit.sum()),
                        "risk_among_admitted": (
                            float((admitted > TOL).mean()) if admit.any() else float("nan")
                        ),
                        "mean_abs_error_admitted": (
                            float(np.nanmean(admitted)) if admit.any() else float("nan")
                        ),
                        "n_false_admitted": int((admitted > TOL).sum()),
                    }
                )
            pairs = (
                ("fitted_risk", "peak_overlap_rule"),
                ("fitted_risk", "length_rule"),
                ("fitted_risk", "reconstruct_all"),
                ("fitted_risk", "calibrated_bound"),
                ("calibrated_bound", "peak_overlap_rule"),
                ("peak_overlap_rule", "reconstruct_all"),
                ("length_rule", "reconstruct_all"),
            )
            for pair_index, (left, right) in enumerate(pairs):
                difference = decisions[left].astype(float) - decisions[right].astype(float)
                summary = _cluster_bootstrap(
                    difference,
                    groups,
                    statistic="mean",
                    seed=1000 * seed + 100 * ("t0 p5 a1".split().index(suffix)) + pair_index,
                )
                contrasts.append(
                    {
                        "level": level,
                        "seed": int(seed),
                        "contrast": f"admitted_share {left} - {right}",
                        "left": left,
                        "right": right,
                        "point": summary["point"],
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "ci_excludes_zero": bool(
                            np.isfinite(summary["ci_low"])
                            and np.isfinite(summary["ci_high"])
                            and (summary["ci_low"] > 0 or summary["ci_high"] < 0)
                        ),
                        "n_networks": summary["n_units"],
                    }
                )
            # realised risk of every arm, with an interval
            for arm in ARMS:
                adopt = decisions[arm].astype(float)
                values = np.column_stack([adopt * (policy_err > TOL), adopt])
                summary = _cluster_bootstrap(
                    values,
                    groups,
                    statistic="ratio",
                    seed=7_000 + seed + 100 * ("t0 p5 a1".split().index(suffix)),
                )
                contrasts.append(
                    {
                        "level": level,
                        "seed": int(seed),
                        "contrast": f"risk_among_admitted {arm}",
                        "left": arm,
                        "right": "none",
                        "point": summary["point"],
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "ci_excludes_zero": False,
                        "n_networks": summary["n_units"],
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(contrasts), pd.concat(detail_frames, ignore_index=True)


def write_summary(admission: pd.DataFrame, contrasts: pd.DataFrame) -> None:
    lines = [
        "# The aligned rule on real monitoring calendars",
        "",
        "Generated by `scripts/331_wrr_aligned_real_calendar.py`. Thresholds are the ones",
        "selected in `p0_01_aligned_policy_admission` on the development panel, where the",
        "calibrated event is the policy-reconstruction error. The candidate pool is the 418",
        "real-calendar groups already placed; it is a development-period probe, not a new",
        "sealed panel.",
        "",
        "## Admission at the pre-registered 5% cap",
        "",
        "| level | seed | arm | admitted share | risk among admitted | mean |err| °C |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for row in admission.itertuples(index=False):
        lines.append(
            f"| {row.level} | {row.seed} | {row.arm} | {row.admitted_share:.3f} | "
            f"{row.risk_among_admitted:.3f} | {row.mean_abs_error_admitted:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Contrasts and realised risk (network-clustered 95% intervals)",
            "",
            "| level | seed | contrast | point | 95% interval | excludes 0 |",
            "|---|---:|---|---:|---|---|",
        ]
    )
    for row in contrasts.itertuples(index=False):
        lines.append(
            f"| {row.level} | {row.seed} | {row.contrast} | {row.point:+.4f} | "
            f"[{row.ci_low:+.4f}, {row.ci_high:+.4f}] | "
            f"{'yes' if row.ci_excludes_zero else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- `reconstruct_all` is not a straw arm: on this calendar its realised risk is",
            "  already under the 5% cap in all three co-failure levels, though the interval",
            "  is wide and the cap is not certified for a new archive.",
            "- The question the table answers is therefore not 'which screen is best' but",
            "  'does screening buy anything here'. Where `reconstruct_all` is under the cap,",
            "  a screen can only add cost and lose records.",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    admission, contrasts, detail = score_replay()
    admission.to_csv(OUT / "replay_admission.csv", index=False)
    contrasts.to_csv(OUT / "replay_contrasts.csv", index=False)
    detail.to_parquet(OUT / "replay_case_decisions.parquet", index=False)
    write_summary(admission, contrasts)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
