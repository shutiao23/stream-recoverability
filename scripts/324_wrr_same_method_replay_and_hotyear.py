#!/usr/bin/env python3
"""Apply the locked fitted-risk rule to the real-calendar replay and the hot-year split.

The score is the development outer-fold model from
``major_revision_20261019/p0_02_isolated_risk_thresholds``. A replay network is
scored by the model whose training fold did not contain it. The threshold is
that fold's simultaneous-bound threshold. Peak-window and length rules use the
thresholds selected for those scores on the same fold. No replay label is read.

The hot-year split uses the same admission columns already stored for the
designed-outage panels. It separates prediction error from selection shift.
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

from stream_recoverability.experiments.v17_fitness.frontier import estimator_disagreement  # noqa: E402
from stream_recoverability.experiments.v17_fitness.screen import feature_frame  # noqa: E402

# Keep this import path identical to scripts/301 so the feature list cannot drift.
sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "step2_features", ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py"
)
_step2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_step2)
SUPPORT = tuple(_step2.SUPPORT)

ISOLATED = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261019"
    / "p0_02_isolated_risk_thresholds"
)
REPLAY = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "p0_03_final_method_replay"
    / "replay_decisions.parquet"
)
OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261019"
    / "p0_05_same_method_replay"
)
TOL = 0.5
SEEDS = (101, 202, 303)
LEVELS = (("target_only", "t0"), ("partial_donor_failure", "p5"), ("all_donor_failure", "a1"))
HOT_LEVELS = (18.0, 20.0)
ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
PANEL_CASES = {
    "development": ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet",
    "wave2_confirmation": ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet",
}


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


def _thresholds(panel: str, score: str, seed: int) -> dict[int, float]:
    table = pd.read_csv(ISOLATED / "crossfit_risk_cap_table.csv")
    rows = table[
        table.panel.eq(panel)
        & table.score.eq(score)
        & table.fold_seed.eq(seed)
        & table.row_type.eq("fold")
    ]
    return {int(row.fold): float(row.threshold) for row in rows.itertuples(index=False)}


def _cluster_mean_diff(diff: np.ndarray, groups: np.ndarray, draws: int = 2000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    uniq = pd.unique(groups)
    point = float(np.nanmean(diff))
    stats = np.empty(draws)
    for draw in range(draws):
        chosen = rng.choice(uniq, size=uniq.size, replace=True)
        parts = [diff[groups == group] for group in chosen]
        stats[draw] = np.nanmean(np.concatenate(parts)) if parts else np.nan
    finite = stats[np.isfinite(stats)]
    return {
        "point": point,
        "ci_low": float(np.quantile(finite, 0.025)) if finite.size else float("nan"),
        "ci_high": float(np.quantile(finite, 0.975)) if finite.size else float("nan"),
        "n_groups": int(len(uniq)),
    }


def score_replay() -> pd.DataFrame:
    replay = pd.read_parquet(REPLAY)
    assignments = pd.read_csv(ISOLATED / "fold_assignments.csv")
    dev = assignments[assignments.panel.eq("development")]
    fold_of = {
        seed: dict(zip(dev.network_id.astype(str), dev[f"fold_seed_{seed}"].astype(int)))
        for seed in SEEDS
    }
    models = {
        (seed, fold): joblib.load(
            ISOLATED / "models" / f"model_development_fitted_risk_seed{seed}_fold{fold}.joblib"
        )
        for seed in SEEDS
        for fold in range(5)
    }
    taus = {
        (score, seed): _thresholds("development", score, seed)
        for score in ("fitted_risk", "peak_overlap_rule", "length_rule")
        for seed in SEEDS
    }
    networks = replay["network_id"].astype(str).to_numpy()
    rows = []
    detail_frames = []
    for level, suffix in LEVELS:
        features = _features_for_level(replay, suffix)
        policy_err = _numeric(replay, f"abserr_policy__{suffix}")
        available = np.isfinite(policy_err)
        peak = _numeric(replay, "peak_overlap")
        length = _numeric(replay, "longest_run")
        for seed in SEEDS:
            score = np.full(len(replay), np.nan)
            tau_fit = np.full(len(replay), np.nan)
            tau_peak = np.full(len(replay), np.nan)
            tau_length = np.full(len(replay), np.nan)
            for network in sorted(set(networks)):
                fold = int(fold_of[seed][network])
                mask = networks == network
                pred = models[(seed, fold)].predict(feature_frame(features.loc[mask], SUPPORT))
                score[mask] = np.asarray(pred, dtype=float)
                tau_fit[mask] = taus[("fitted_risk", seed)][fold]
                tau_peak[mask] = taus[("peak_overlap_rule", seed)][fold]
                tau_length[mask] = taus[("length_rule", seed)][fold]
            decisions = {
                "fitted_risk": np.isfinite(score) & (score <= tau_fit) & available,
                "peak_overlap_rule": np.isfinite(peak) & (peak <= tau_peak) & available,
                "length_rule": np.isfinite(length) & (length <= tau_length) & available,
                "reconstruct_all": available.copy(),
            }
            detail = pd.DataFrame(
                {
                    "level": level,
                    "seed": seed,
                    "network_id": networks,
                    "available": available,
                    "policy_err": policy_err,
                    "fitted_score": score,
                    "fitted_admit": decisions["fitted_risk"],
                    "peak_admit": decisions["peak_overlap_rule"],
                    "length_admit": decisions["length_rule"],
                }
            )
            detail_frames.append(detail)
            for name, admit in decisions.items():
                admitted_err = policy_err[admit]
                rows.append(
                    {
                        "level": level,
                        "seed": int(seed),
                        "method": name,
                        "n_groups": int(len(replay)),
                        "n_networks": int(pd.unique(networks).size),
                        "available_share": float(available.mean()),
                        "admitted_share": float(admit.mean()),
                        "consequential_error_among_admitted": (
                            float((admitted_err > TOL).mean()) if admit.any() else float("nan")
                        ),
                        "mean_abserr_among_admitted": (
                            float(np.nanmean(admitted_err)) if admit.any() else float("nan")
                        ),
                    }
                )
    detail = pd.concat(detail_frames, ignore_index=True)
    contrasts = []
    for level, _suffix in LEVELS:
        for seed in SEEDS:
            block = detail[(detail.level == level) & (detail.seed == seed)]
            for left, right in (
                ("fitted_admit", "peak_admit"),
                ("fitted_admit", "length_admit"),
            ):
                diff = block[left].astype(float).to_numpy() - block[right].astype(float).to_numpy()
                level_index = [name for name, _suffix in LEVELS].index(level)
                summary = _cluster_mean_diff(
                    diff,
                    block["network_id"].to_numpy(),
                    seed=1000 * seed + 10 * level_index + (0 if "peak" in right else 1),
                )
                contrasts.append(
                    {
                        "level": level,
                        "seed": int(seed),
                        "contrast": f"{left}_minus_{right}",
                        "admitted_share_diff": summary["point"],
                        "ci_low": summary["ci_low"],
                        "ci_high": summary["ci_high"],
                        "n_networks": summary["n_groups"],
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(contrasts)


def _policy_prediction(cases: pd.DataFrame) -> np.ndarray:
    choice = cases["policy_choice"].astype(str).to_numpy()
    pred = np.full(len(cases), np.nan)
    for name in ESTIMATORS:
        mask = choice == name
        column = f"hottest30_{name}"
        if column not in cases.columns or not mask.any():
            continue
        pred[mask] = pd.to_numeric(cases.loc[mask, column], errors="coerce").to_numpy(dtype=float)
    return pred


def hot_year() -> pd.DataFrame:
    groups = pd.read_csv(ISOLATED / "independence_groups.csv")
    rows = []
    for panel, path in PANEL_CASES.items():
        cases = pd.read_parquet(path).reset_index(drop=True)
        admissions = pd.read_parquet(
            ISOLATED / f"case_level_admissions_{panel}.parquet"
        ).reset_index(drop=True)
        if len(cases) != len(admissions):
            raise RuntimeError(f"{panel}: cases and admissions differ in length")
        if not cases["network_id"].astype(str).equals(admissions["network_id"].astype(str)):
            raise RuntimeError(f"{panel}: admissions are not row-aligned with cases")
        pred = _policy_prediction(cases)
        truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
        group_of = dict(
            zip(
                groups.loc[groups.panel.eq(panel), "network_id"].astype(str),
                groups.loc[groups.panel.eq(panel), "independence_group"].astype(str),
            )
        )
        group = cases["network_id"].astype(str).map(group_of).to_numpy()
        methods = {
            "fitted_risk": admissions["admit_riskcap_fitted_risk_seed101"].to_numpy(dtype=bool),
            "peak_overlap_rule": admissions["admit_riskcap_peak_overlap_rule_seed101"].to_numpy(dtype=bool),
            "length_rule": admissions["admit_riskcap_length_rule_seed101"].to_numpy(dtype=bool),
            "calibrated_bound": admissions["admit_riskcap_calibrated_bound_seed101"].to_numpy(dtype=bool),
            "reconstruct_all": np.isfinite(pred) & np.isfinite(truth),
        }
        for hot in HOT_LEVELS:
            truth_hot = truth > hot
            pred_hot = pred > hot
            full = float(np.nanmean(truth_hot))
            for name, admit in methods.items():
                if name == "reconstruct_all":
                    use = admit
                else:
                    use = admit & np.isfinite(truth) & np.isfinite(pred)
                if not use.any():
                    continue
                p_a = float(truth_hot[use].mean())
                p_hat = float(pred_hot[use].mean())
                rows.append(
                    {
                        "panel": panel,
                        "hot_c": hot,
                        "method": name,
                        "fold_seed": 101,
                        "n_admitted": int(use.sum()),
                        "admitted_share": float(use.mean()),
                        "p_full": full,
                        "p_A": p_a,
                        "p_hat_A": p_hat,
                        "prediction_error": p_hat - p_a,
                        "selection_shift": p_a - full,
                        "total_bias": p_hat - full,
                        "n_groups": int(pd.unique(group[use]).size),
                    }
                )
    return pd.DataFrame(rows)


def _fmt(value: float, digits: int = 3) -> str:
    if not np.isfinite(value):
        return "NA"
    return f"{value:.{digits}f}"


def write_summary(replay: pd.DataFrame, contrasts: pd.DataFrame, hot: pd.DataFrame) -> None:
    lines = [
        "# Same locked method on the real-calendar replay and the hot-year split",
        "",
        "The fitted risk score is the development outer-fold model from the isolated run. "
        "Each replay network is scored by the model fitted on the other folds, and the "
        "threshold is that fold's simultaneous-bound threshold. Peak-window and length rules "
        "use the thresholds selected for those scores on the same fold. The reconstruction "
        "being accepted or refused is the stored policy reconstruction for that co-failure "
        "level. Observed-window-only output is not counted as an admission.",
        "",
        "This replay was built from the 418 candidate groups already placed. It does not add "
        "a new sealed panel.",
        "",
        "## Admission",
        "",
        "| level | seed | method | admitted share | error rate among admitted | mean abs error °C |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for row in replay.itertuples(index=False):
        lines.append(
            f"| {row.level} | {row.seed} | {row.method} | {_fmt(row.admitted_share)} | "
            f"{_fmt(row.consequential_error_among_admitted)} | {_fmt(row.mean_abserr_among_admitted)} |"
        )
    lines.extend(["", "## Admitted-share difference, fitted risk minus the named rule", ""])
    lines.append("| level | seed | contrast | difference | 95% interval | networks |")
    lines.append("|---|---:|---|---:|---|---:|")
    for row in contrasts.itertuples(index=False):
        lines.append(
            f"| {row.level} | {row.seed} | {row.contrast} | {_fmt(row.admitted_share_diff)} | "
            f"[{_fmt(row.ci_low)}, {_fmt(row.ci_high)}] | {row.n_networks} |"
        )
    lines.extend(
        [
            "",
            "## Hot-year composition, seed 101",
            "",
            "p_full is the hot-year share of every candidate. p_A is the true hot-year share "
            "among admitted records. p_hat_A is the predicted hot-year share among those same "
            "records. prediction_error = p_hat_A - p_A. selection_shift = p_A - p_full. "
            "total_bias = p_hat_A - p_full. Shares are case-weighted.",
            "",
            "| panel | hot °C | method | admitted share | p_full | p_A | p_hat_A | prediction | selection | total |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in hot.itertuples(index=False):
        lines.append(
            f"| {row.panel} | {row.hot_c:.0f} | {row.method} | {_fmt(row.admitted_share)} | "
            f"{_fmt(row.p_full)} | {_fmt(row.p_A)} | {_fmt(row.p_hat_A)} | "
            f"{_fmt(row.prediction_error)} | {_fmt(row.selection_shift)} | {_fmt(row.total_bias)} |"
        )
    lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    replay, contrasts = score_replay()
    hot = hot_year()
    replay.to_csv(OUT / "replay_admission.csv", index=False)
    contrasts.to_csv(OUT / "replay_contrasts.csv", index=False)
    hot.to_csv(OUT / "hot_year_decomposition.csv", index=False)
    write_summary(replay, contrasts, hot)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
