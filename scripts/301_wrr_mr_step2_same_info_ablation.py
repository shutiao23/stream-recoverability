#!/usr/bin/env python3
"""Major-revision Step 2: same-capacity, same-info-budget support ablation.

Answers claim C1 in docs/reviews/wrr_major_revision_20261014/PROPOSITION_TABLE.md:
does engineered peak-window support (peak_overlap) add ranking power beyond a
generic risk model that already sees gap length, warm-season visibility, donor
quality, training size, and reconstructor disagreement?

This script ranks by a single-head quantile risk model on abserr_policy. It does
not select reconstructors; the small certificate vs certificate_screen_only gap
remains a separate, already-scored increment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    RETENTION_GRID,
    estimator_disagreement,
    frontier_for_score,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP4_CEILING,
    STEP10_CONFIRM,
)
from stream_recoverability.experiments.v17_fitness.screen import feature_frame  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "step2_same_info_ablation"
)
PROTOCOL = ROOT / "docs" / "reviews" / "wrr_major_revision_20261014" / "STEP2_PROTOCOL.md"

RETENTION = 0.70
RISK_CAP = 0.05
SEED = 17
N_SPLITS = 5
BOOT_DRAWS = 1000
LEARNING_SIZES = (10, 25, 50, None)  # None = all development nets

GENERIC = (
    "longest_run",
    "total_missing",
    "missing_fraction",
    "n_runs",
    "warm_observed_fraction",
    "month_sin",
    "month_cos",
    "n_visible_donors",
    "donor_corr_mean",
    "donor_corr_max",
    "donor_corr_min",
    "donor_coverage_mean",
    "train_resid_sd",
    "seasonal_amplitude",
    "train_metric_sd",
    "n_complete_years",
    "record_years",
    "left_flank",
    "right_flank",
    "air_available",
    "estimator_disagreement",
)
SUPPORT = GENERIC + ("peak_overlap",)
PEAK_MARGIN = SUPPORT + ("observed_peak_margin", "observed_peak", "has_complete_window")

FEATURE_SETS = {
    "generic": GENERIC,
    "generic_plus_support": SUPPORT,
    "generic_plus_support_plus_peakmargin": PEAK_MARGIN,
}


def _risk_model(seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="quantile",
        quantile=0.9,
        random_state=int(seed),
        max_depth=4,
        max_iter=350,
        learning_rate=0.06,
        min_samples_leaf=40,
    )


def _prepare(cases: pd.DataFrame) -> pd.DataFrame:
    frame = cases.copy()
    frame["estimator_disagreement"] = estimator_disagreement(frame)
    month = pd.to_numeric(frame["longest_run_month"], errors="coerce").fillna(6)
    frame["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    frame["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    return frame


def _fit_predict_risk(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: tuple[str, ...],
    *,
    seed: int,
) -> np.ndarray:
    y = pd.to_numeric(train["abserr_policy"], errors="coerce")
    mask = y.notna().to_numpy()
    X_train = feature_frame(train, features)
    # estimator_disagreement / month_* may be passed through feature_frame as NaN
    # if absent from SCREEN path; overwrite from prepared columns.
    for name in features:
        if name in train.columns:
            X_train[name] = pd.to_numeric(train[name], errors="coerce")
    X_test = feature_frame(test, features)
    for name in features:
        if name in test.columns:
            X_test[name] = pd.to_numeric(test[name], errors="coerce")
    model = _risk_model(seed).fit(X_train.loc[mask], y.loc[mask])
    return model.predict(X_test)


def oof_risk_scores(cases: pd.DataFrame, features: tuple[str, ...], *, seed: int) -> pd.Series:
    networks = sorted(cases["network_id"].astype(str).unique())
    rng = np.random.default_rng(int(seed))
    order = rng.permutation(len(networks))
    folds = {networks[int(i)]: int(pos % N_SPLITS) for pos, i in enumerate(order)}
    out = pd.Series(np.nan, index=cases.index, dtype=float)
    fold_id = cases["network_id"].astype(str).map(folds)
    for fold in range(N_SPLITS):
        test_idx = fold_id.eq(fold)
        train_idx = ~test_idx
        if not test_idx.any() or not train_idx.any():
            continue
        pred = _fit_predict_risk(
            cases.loc[train_idx],
            cases.loc[test_idx],
            features,
            seed=seed + fold,
        )
        out.loc[test_idx] = pred
    return out


def rule_scores(cases: pd.DataFrame, *, seed: int) -> dict[str, pd.Series]:
    rng = np.random.default_rng(int(seed))

    def jitter(values: pd.Series, scale: float) -> pd.Series:
        return pd.to_numeric(values, errors="coerce") + rng.random(len(values)) * float(scale)

    return {
        "length_rule": jitter(cases["longest_run"], 1.0),
        "warm_coverage_rule": jitter(-pd.to_numeric(cases["warm_observed_fraction"], errors="coerce"), 1e-3),
        "peak_overlap_rule": jitter(cases["peak_overlap"], 1e-3),
        "estimator_disagreement_rule": jitter(cases["estimator_disagreement"], 1e-3),
    }


def retention_at_risk_cap(score: pd.Series, errors: pd.Series, *, risk_cap: float = RISK_CAP) -> dict:
    values = pd.to_numeric(score, errors="coerce").to_numpy(dtype=float)
    err = pd.to_numeric(errors, errors="coerce").to_numpy(dtype=float)
    good = np.isfinite(err)
    values = np.where(np.isfinite(values), values, np.inf)[good]
    err = err[good]
    order = np.argsort(values, kind="mergesort")
    best = {"retention": 0.0, "rate_above_0.5": float("nan"), "n_retained": 0}
    for retention in RETENTION_GRID:
        k = max(1, int(round(float(retention) * len(err))))
        rate = float((err[order[:k]] > PRIMARY_TOLERANCE_C).mean())
        if rate <= risk_cap:
            best = {"retention": float(retention), "rate_above_0.5": rate, "n_retained": int(k)}
    # Also try denser grid near the optimum for a slightly sharper retention.
    for retention in np.round(np.arange(0.05, 1.001, 0.01), 3):
        k = max(1, int(round(float(retention) * len(err))))
        rate = float((err[order[:k]] > PRIMARY_TOLERANCE_C).mean())
        if rate <= risk_cap and float(retention) >= best["retention"]:
            best = {"retention": float(retention), "rate_above_0.5": rate, "n_retained": int(k)}
    return best


def contrast_at_retention(
    frame: pd.DataFrame,
    score_a: str,
    score_b: str,
    error_col: str,
    *,
    retention: float,
    draws: int,
    seed: int,
) -> dict:
    def statistic(block: pd.DataFrame) -> float:
        k = max(1, int(round(float(retention) * len(block))))
        if k > len(block):
            return float("nan")
        a = block.nsmallest(k, score_a)[error_col].to_numpy(dtype=float)
        b = block.nsmallest(k, score_b)[error_col].to_numpy(dtype=float)
        rate_a = float(((~np.isfinite(a)) | (a > PRIMARY_TOLERANCE_C)).mean())
        rate_b = float(((~np.isfinite(b)) | (b > PRIMARY_TOLERANCE_C)).mean())
        return rate_a - rate_b

    return cluster_bootstrap(frame, statistic, draws=draws, seed=seed)


def operating_rows(name: str, score: pd.Series, errors: pd.Series, kind: str) -> dict:
    frontier = frontier_for_score(score, errors)
    at70 = frontier.loc[frontier["retention"].eq(RETENTION)].iloc[0]
    risk5 = retention_at_risk_cap(score, errors)
    return {
        "screen": name,
        "kind": kind,
        "rate_above_0.5_at_70": float(at70["rate_above_0.5"]),
        "mean_abs_error_c_at_70": float(at70["mean_abs_error_c"]),
        "retention_at_risk_cap_5pct": risk5["retention"],
        "rate_above_0.5_at_risk_cap": risk5["rate_above_0.5"],
        "n_retained_at_risk_cap": risk5["n_retained"],
    }


def learning_curve_row(
    development: pd.DataFrame,
    reserved: pd.DataFrame,
    features: tuple[str, ...],
    n_train_nets: int | None,
    *,
    seed: int,
) -> dict:
    nets = sorted(development["network_id"].astype(str).unique())
    rng = np.random.default_rng(int(seed))
    if n_train_nets is None or n_train_nets >= len(nets):
        train_nets = set(nets)
        n_used = len(nets)
    else:
        picked = rng.choice(len(nets), size=int(n_train_nets), replace=False)
        train_nets = {nets[int(i)] for i in picked}
        n_used = int(n_train_nets)
    train = development.loc[development["network_id"].astype(str).isin(train_nets)]
    score = pd.Series(
        _fit_predict_risk(train, reserved, features, seed=seed),
        index=reserved.index,
    )
    errors = pd.to_numeric(reserved["abserr_policy"], errors="coerce")
    row = operating_rows(f"n_train_nets={n_used}", score, errors, "learning_curve")
    row["feature_set"] = "generic_plus_support" if features == SUPPORT else (
        "generic" if features == GENERIC else "generic_plus_support_plus_peakmargin"
    )
    row["n_train_networks"] = n_used
    return row


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    development = _prepare(pd.read_parquet(STEP4_CEILING / "development_cases.parquet"))
    reserved = _prepare(pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet"))
    errors_dev = pd.to_numeric(development["abserr_policy"], errors="coerce")
    errors_res = pd.to_numeric(reserved["abserr_policy"], errors="coerce")

    scores: dict[str, pd.Series] = {}
    scores.update(rule_scores(development, seed=SEED))
    for name, features in FEATURE_SETS.items():
        print(f"OOF scoring {name} ({len(features)} features)...", flush=True)
        scores[name] = oof_risk_scores(development, features, seed=SEED)

    op_rows = []
    frontier_pieces = []
    for name, score in scores.items():
        kind = "rule" if name.endswith("_rule") or name == "estimator_disagreement_rule" else "model"
        op_rows.append(operating_rows(name, score, errors_dev, kind))
        fr = frontier_for_score(score, errors_dev)
        fr["screen"] = name
        frontier_pieces.append(fr)

    operating = pd.DataFrame(op_rows).sort_values("rate_above_0.5_at_70")
    frontiers = pd.concat(frontier_pieces, ignore_index=True)
    operating.to_csv(OUT / "operating_points_development_oof.csv", index=False)
    frontiers.to_csv(OUT / "frontiers_development_oof.csv", index=False)

    # Network-clustered paired contrasts on development OOF.
    boot = development[["network_id"]].copy()
    boot["error"] = errors_dev
    for name, score in scores.items():
        boot[name] = pd.to_numeric(score, errors="coerce").fillna(np.inf)

    contrasts = {}
    pairs = [
        ("generic_plus_support", "peak_overlap_rule"),
        ("generic_plus_support", "generic"),
        ("generic_plus_support_plus_peakmargin", "generic_plus_support"),
        ("generic_plus_support_plus_peakmargin", "peak_overlap_rule"),
        ("generic", "peak_overlap_rule"),
        ("generic_plus_support", "length_rule"),
    ]
    for left, right in pairs:
        print(f"Bootstrapping contrast {left} - {right} @70%...", flush=True)
        stat = contrast_at_retention(
            boot,
            left,
            right,
            "error",
            retention=RETENTION,
            draws=BOOT_DRAWS,
            seed=SEED,
        )
        contrasts[f"{left}__minus__{right}"] = {
            "retention": RETENTION,
            "tolerance_c": PRIMARY_TOLERANCE_C,
            "point_rate_diff": stat["point"],
            "point_pp": float(stat["point"]) * 100,
            "ci_low_pp": float(stat["low"]) * 100,
            "ci_high_pp": float(stat["high"]) * 100,
            "n_clusters": stat["n_clusters"],
            "panel": "development_oof",
        }

    # Retention-at-risk-cap deltas (point only + cluster bootstrap on retention).
    def retention_delta(left: str, right: str) -> dict:
        def statistic(block: pd.DataFrame) -> float:
            return (
                retention_at_risk_cap(block[left], block["error"])["retention"]
                - retention_at_risk_cap(block[right], block["error"])["retention"]
            )

        return cluster_bootstrap(boot, statistic, draws=BOOT_DRAWS, seed=SEED + 99)

    for left, right in [
        ("generic_plus_support", "peak_overlap_rule"),
        ("generic_plus_support", "generic"),
        ("generic_plus_support_plus_peakmargin", "peak_overlap_rule"),
    ]:
        print(f"Bootstrapping retention@risk5 {left} - {right}...", flush=True)
        stat = retention_delta(left, right)
        contrasts[f"retention_at_risk5__{left}__minus__{right}"] = {
            "risk_cap": RISK_CAP,
            "point_retention_diff": stat["point"],
            "point_pp": float(stat["point"]) * 100,
            "ci_low_pp": float(stat["low"]) * 100,
            "ci_high_pp": float(stat["high"]) * 100,
            "n_clusters": stat["n_clusters"],
            "panel": "development_oof",
            "predeclared_success_plus5pp": bool(stat["point"] >= 0.05 and stat["low"] > 0),
        }

    # Learning curves on reserved (retrospective label).
    curve_rows = []
    for features, label in [
        (GENERIC, "generic"),
        (SUPPORT, "generic_plus_support"),
        (PEAK_MARGIN, "generic_plus_support_plus_peakmargin"),
    ]:
        for n_train in LEARNING_SIZES:
            print(f"Learning curve {label} n_train={n_train}...", flush=True)
            row = learning_curve_row(
                development, reserved, features, n_train, seed=SEED
            )
            row["feature_set"] = label
            row["panel"] = "reserved_retrospective"
            curve_rows.append(row)
    curves = pd.DataFrame(curve_rows)
    curves.to_csv(OUT / "learning_curves_reserved.csv", index=False)

    # Reserved point operating table for the full-data fit of each nest.
    reserved_ops = []
    for label, features in FEATURE_SETS.items():
        score = pd.Series(
            _fit_predict_risk(development, reserved, features, seed=SEED),
            index=reserved.index,
        )
        reserved_ops.append(operating_rows(label, score, errors_res, "model_reserved"))
    for name, score in rule_scores(reserved, seed=SEED).items():
        reserved_ops.append(operating_rows(name, score, errors_res, "rule_reserved"))
    pd.DataFrame(reserved_ops).to_csv(OUT / "operating_points_reserved.csv", index=False)

    fingerprint = {
        "protocol": str(PROTOCOL.relative_to(ROOT)),
        "seed": SEED,
        "n_splits": N_SPLITS,
        "boot_draws": BOOT_DRAWS,
        "retention": RETENTION,
        "tolerance_c": PRIMARY_TOLERANCE_C,
        "risk_cap": RISK_CAP,
        "feature_sets": {k: list(v) for k, v in FEATURE_SETS.items()},
        "n_development_cases": int(len(development)),
        "n_development_networks": int(development["network_id"].nunique()),
        "n_reserved_cases": int(len(reserved)),
        "n_reserved_networks": int(reserved["network_id"].nunique()),
        "learner": "HistGradientBoostingRegressor quantile=0.9 single-head on abserr_policy",
        "note_monthly_visibility": (
            "Case table lacks per-month visibility fractions; "
            "warm_observed_fraction + month harmonics used in generic budget."
        ),
    }
    (OUT / "protocol_fingerprint.json").write_text(json.dumps(fingerprint, indent=2) + "\n")
    (OUT / "contrasts_network_ci.json").write_text(json.dumps(contrasts, indent=2) + "\n")

    # Human summary
    lines = [
        "# Step 2 — same-info support ablation (development OOF + reserved curves)",
        "",
        "Claim C1: engineered `peak_overlap` adds inductive bias beyond a same-capacity generic risk model.",
        "",
        "## Development OOF operating points",
        "",
        operating.to_string(index=False),
        "",
        "## Network-clustered contrasts (rate diff at 70% / 0.5 °C, percentage points)",
        "",
    ]
    for key, val in contrasts.items():
        if "retention_at_risk5" in key:
            lines.append(
                f"- `{key}`: Δ retention = {val['point_pp']:.2f} pp "
                f"[{val['ci_low_pp']:.2f}, {val['ci_high_pp']:.2f}] "
                f"(success≥+5pp & CI>0: {val.get('predeclared_success_plus5pp')})"
            )
        else:
            lines.append(
                f"- `{key}`: Δ rate = {val['point_pp']:.2f} pp "
                f"[{val['ci_low_pp']:.2f}, {val['ci_high_pp']:.2f}]"
            )
    lines += [
        "",
        "## Learning curves (reserved retrospective panel)",
        "",
        curves[
            [
                "feature_set",
                "n_train_networks",
                "rate_above_0.5_at_70",
                "retention_at_risk_cap_5pct",
            ]
        ]
        .sort_values(["feature_set", "n_train_networks"])
        .to_string(index=False),
        "",
        "Reserved panel is retrospective (opened). Do not treat as sealed confirmation.",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("Wrote", OUT)
    print(operating.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
