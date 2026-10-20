#!/usr/bin/env python3
"""R2-02 (review op. 4, 2026-10-20b) -- where does the fitted score's gain come from?

The aligned round showed that the fitted risk score keeps 7-8 points more than the
peak-window rule.  It did not say *which information* earns that.  This script
adds the information back in layers, with one learner, one training set, one
calibration procedure and one decision protocol throughout:

    gap + season coverage      (longest run, missing share, run count, flank, month,
                                warm-season observed fraction)
  + donor information          (visible donors, donor correlation / coverage, air)
  + reconstruction diagnostics (training residual sd, estimator disagreement)
  + station history            (amplitude, metric sd, record length)
  + target support             (``peak_overlap``, the climatological peak-window share)

and the same ladder with a small logistic model, so that the answer does not
depend on the capacity of gradient boosting.  The decisive contrast is the
*same-capacity generic model that cannot read ``peak_overlap``* against the same
model that can.

Protocol (identical to ``scripts/330``): the admitted object is the stored policy
reconstruction; failure is ``abserr_policy > 0.5 C``; folds are shared-station
groups; each outer fold's threshold is chosen on inner out-of-fold calibration
scores with a simultaneous clustered bound at the 5 % cap; ties are admitted
whole; three fold seeds.

Outputs: ``results/wrr_submission_ready/major_revision_20261020b/r2_02_same_capacity_ablation/``.

Run:

    PYTHONPATH=src python3 scripts/341_wrr_same_capacity_ablation.py
"""

from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from joblib import Parallel, delayed  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import stable_seed  # noqa: E402

OUT = C.RUN / "r2_02_same_capacity_ablation"
CACHE = C.ROOT / "scratch" / "r2_02_ablation"

M330 = C.load_script("wrr330", C.ROOT / "scripts" / "330_wrr_aligned_policy_admission.py")
M311 = M330.M311
M301 = M330.M301

GAP_SEASON = (
    "longest_run",
    "total_missing",
    "missing_fraction",
    "n_runs",
    "warm_observed_fraction",
    "month_sin",
    "month_cos",
    "left_flank",
    "right_flank",
)
DONORS = (
    "n_visible_donors",
    "donor_corr_mean",
    "donor_corr_max",
    "donor_corr_min",
    "donor_coverage_mean",
    "air_available",
)
RESIDUAL = ("train_resid_sd", "estimator_disagreement")
HISTORY = ("seasonal_amplitude", "train_metric_sd", "n_complete_years", "record_years")
SUPPORT = ("peak_overlap",)
LOGIT_BASE = (
    "longest_run",
    "warm_observed_fraction",
    "n_visible_donors",
    "donor_corr_mean",
    "train_resid_sd",
    "estimator_disagreement",
)

def ordered(*groups: tuple[str, ...]) -> tuple[str, ...]:
    """Features in the canonical column order of ``301.SUPPORT``.

    Gradient boosting breaks exact split ties by column order, and in the
    designed panel ``longest_run``, ``total_missing`` and ``missing_fraction``
    are collinear for every single-run case.  Keeping one canonical order makes
    the full specification bit-identical to the fitted score of script 330 and
    makes the ladder a nested sequence of column subsets of one table.
    """

    members = set().union(*groups)
    canonical = tuple(M301.SUPPORT)
    unknown = members - set(canonical)
    if unknown:
        raise KeyError(f"features outside the canonical set: {sorted(unknown)}")
    return tuple(name for name in canonical if name in members)


#: spec name -> (features, model kind)
SPECS: dict[str, tuple[tuple[str, ...], str]] = {
    "gap_season": (ordered(GAP_SEASON), "gbr"),
    "gap_season+support": (ordered(GAP_SEASON, SUPPORT), "gbr"),
    "gap_season+donors": (ordered(GAP_SEASON, DONORS), "gbr"),
    "gap_season+donors+support": (ordered(GAP_SEASON, DONORS, SUPPORT), "gbr"),
    "gap_season+donors+residual": (ordered(GAP_SEASON, DONORS, RESIDUAL), "gbr"),
    "gap_season+donors+residual+support": (ordered(GAP_SEASON, DONORS, RESIDUAL, SUPPORT), "gbr"),
    "generic": (ordered(GAP_SEASON, DONORS, RESIDUAL, HISTORY), "gbr"),
    "generic+support": (ordered(GAP_SEASON, DONORS, RESIDUAL, HISTORY, SUPPORT), "gbr"),
    "logit_small": (LOGIT_BASE, "logit"),
    "logit_small+support": (LOGIT_BASE + SUPPORT, "logit"),
    # NOT deployable: the true hidden share of the year's own peak window.  It is
    # the upper bound on what a perfect support estimate could add.
    "generic+oracle_support": (
        ordered(GAP_SEASON, DONORS, RESIDUAL, HISTORY) + ("true_peak_hidden_fraction",),
        "gbr",
    ),
}
RULES = (
    "peak_overlap_rule",
    "length_rule",
    "calibrated_bound",
    "warm_coverage_rule",
    "oracle_support_rule",
)

CONTRASTS = [
    # the question: does engineered target support add anything to a generic model?
    ("generic+support", "generic"),
    ("gap_season+donors+residual+support", "gap_season+donors+residual"),
    ("gap_season+donors+support", "gap_season+donors"),
    ("gap_season+support", "gap_season"),
    ("logit_small+support", "logit_small"),
    # does the generic model already beat the transparent rule?
    ("generic", "peak_overlap_rule"),
    ("generic+support", "peak_overlap_rule"),
    ("logit_small", "peak_overlap_rule"),
    ("gap_season", "peak_overlap_rule"),
    # what each information layer adds
    ("gap_season+donors", "gap_season"),
    ("gap_season+donors+residual", "gap_season+donors"),
    ("generic", "gap_season+donors+residual"),
    # reference rules
    ("gap_season", "length_rule"),
    ("gap_season", "warm_coverage_rule"),
    ("generic", "calibrated_bound"),
    ("generic+support", "calibrated_bound"),
    # the room left for a better support estimate (oracle = not deployable)
    ("oracle_support_rule", "peak_overlap_rule"),
    ("generic+oracle_support", "generic+support"),
    ("generic+oracle_support", "generic"),
]


# ---------------------------------------------------------------------------
def logit_fit_predict(train: pd.DataFrame, test: pd.DataFrame, features, label: str, seed: int):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def block(frame):
        return pd.DataFrame(
            {name: pd.to_numeric(frame[name], errors="coerce") for name in features},
            index=frame.index,
        ).replace([np.inf, -np.inf], np.nan)

    pipe = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=1.0, max_iter=2000, random_state=int(seed) % (2**31)),
    )
    y = train[label].astype(int).to_numpy()
    pipe.fit(block(train), y)
    return pipe.predict_proba(block(test))[:, 1]


def fit_predict(kind, train, test, features, seed):
    if kind == "gbr":
        return C.load_311().fit_predict_risk(
            train, test, features, "abserr_policy", seed=seed % (2**31)
        )
    return logit_fit_predict(train, test, features, "bad_flag", seed)


def crossfit(task: dict) -> dict:
    """Nested group cross-fit identical in structure to ``311.crossfit_task``."""

    m311 = C.load_311()
    frame = task["frame"]
    features = task["features"]
    kind = task["kind"]
    panel, fold_seed, spec = task["panel"], int(task["fold_seed"]), task["spec"]
    n_splits, n_inner = 5, 4
    units = frame["independence_group"].astype(str).to_numpy()
    outer = m311.assign_folds(units, n_splits, fold_seed)
    outer_ids = np.array([outer[u] for u in units], dtype=int)
    test_score = np.full(len(frame), np.nan)
    cal_score = np.full((n_splits, len(frame)), np.nan)
    for fold in range(n_splits):
        test_mask = outer_ids == fold
        cal_mask = ~test_mask
        cal = frame.loc[cal_mask]
        cal_units = cal["independence_group"].astype(str).to_numpy()
        inner = m311.assign_folds(cal_units, n_inner, stable_seed("inner", panel, fold_seed, fold))
        inner_ids = np.array([inner[u] for u in cal_units], dtype=int)
        positions = np.where(cal_mask)[0]
        for k in range(n_inner):
            it = inner_ids == k
            if not it.any() or it.all():
                continue
            cal_score[fold, positions[it]] = fit_predict(
                kind,
                cal.loc[~it],
                cal.loc[it],
                features,
                stable_seed("innerfit", panel, fold_seed, fold, k),
            )
        test_score[test_mask] = fit_predict(
            kind,
            cal,
            frame.loc[test_mask],
            features,
            stable_seed("outerfit", panel, fold_seed, fold),
        )
    if not np.isfinite(test_score).all():
        raise RuntimeError(f"{panel}/{spec}/{fold_seed}: missing test score")
    return {"test_score": test_score, "cal_score_by_fold": cal_score}


# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=48)
    parser.add_argument("--draws-select", type=int, default=M330.SELECT_DRAWS)
    parser.add_argument("--draws-eval", type=int, default=M330.EVAL_DRAWS)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    panels = {}
    for panel, spec in M330.PANELS.items():
        cases = pd.read_parquet(spec["cases"]).reset_index(drop=True)
        certs = pd.read_parquet(spec["certificates"]).reset_index(drop=True)
        table = M330.independence_table(cases)
        group_of = dict(
            zip(table["network_id"].astype(str), table["independence_group"].astype(str))
        )
        cases["independence_group"] = cases["network_id"].astype(str).map(group_of)
        target = M330.policy_target(cases, certs)
        prepared = M301._prepare(cases)
        prepared["independence_group"] = cases["independence_group"].astype(str).to_numpy()
        prepared["bad_flag"] = target["bad"].astype(int)
        prepared["arm_label"] = cases["arm"].astype(str).to_numpy()
        panels[panel] = {
            "cases": cases,
            "certs": certs,
            "prepared": prepared,
            "target": target,
            "groups": cases["independence_group"].astype(str).to_numpy(),
            "rules": {
                **M330.raw_scores(cases, certs),
                "warm_coverage_rule": 1.0
                - pd.to_numeric(cases["warm_observed_fraction"], errors="coerce")
                .fillna(0.0)
                .to_numpy(dtype=float),
                "oracle_support_rule": pd.to_numeric(
                    cases["true_peak_hidden_fraction"], errors="coerce"
                )
                .fillna(1.0)
                .to_numpy(dtype=float),
            },
            "key": M330.case_key(cases),
        }
        print(f"[{panel}] {len(cases)} cases, bad rate {target['bad_rate']:.4f}", flush=True)

    # ---- cross-fit every (panel, seed, spec) ------------------------------
    needed_columns = sorted(
        {c for feats, _ in SPECS.values() for c in feats}
        | {"network_id", "independence_group", "longest_run_month", "abserr_policy", "bad_flag"}
    )
    tasks, results = [], {}
    for panel, data in panels.items():
        slim = data["prepared"][[c for c in needed_columns if c in data["prepared"].columns]]
        sha = C.sha256_file(M330.PANELS[panel]["cases"])[:12]
        for seed in M330.FOLD_SEEDS:
            for spec, (features, kind) in SPECS.items():
                path = CACHE / f"{panel}__{seed}__{spec.replace('+', '_')}__{sha}__v2.npz"
                if path.exists() and not args.no_cache:
                    payload = np.load(path)
                    results[(panel, seed, spec)] = {
                        "test_score": payload["test_score"],
                        "cal_score_by_fold": payload["cal_score_by_fold"],
                    }
                    continue
                tasks.append(
                    {
                        "panel": panel,
                        "fold_seed": seed,
                        "spec": spec,
                        "features": tuple(features),
                        "kind": kind,
                        "frame": slim,
                        "path": path,
                    }
                )
    if tasks:
        print(f"[crossfit] {len(tasks)} tasks on {args.jobs} threads", flush=True)
        outputs = Parallel(n_jobs=int(args.jobs), backend="loky", verbose=5)(
            delayed(crossfit)(t) for t in tasks
        )
        for t, o in zip(tasks, outputs):
            np.savez_compressed(t["path"], **o)
            results[(t["panel"], t["fold_seed"], t["spec"])] = o
    else:
        print("[crossfit] served from cache", flush=True)

    # ---- determinism check against the cached 330 scores -------------------
    checks = {}
    for panel in panels:
        for seed in M330.FOLD_SEEDS:
            cached = sorted((C.ROOT / "scratch" / "p0_01_aligned").glob(f"{panel}__seed{seed}__fitted_risk__*.npz"))
            if not cached:
                continue
            ref = np.load(cached[-1])["test_score"]
            mine = results[(panel, seed, "generic+support")]["test_score"]
            checks[f"{panel}|{seed}"] = {
                "max_abs_diff": float(np.max(np.abs(ref - mine))),
                "identical": bool(np.allclose(ref, mine, atol=1e-9, rtol=0.0)),
            }
    print("[determinism] generic+support vs the 330 fitted score:", json.dumps(checks), flush=True)

    # ---- decision protocol -------------------------------------------------
    pooled_rows, contrast_rows, arm_rows = [], [], []
    admission_frames = {}
    for panel, data in panels.items():
        cases = data["cases"]
        bad = data["target"]["bad"]
        error = data["target"]["error"]
        groups = data["groups"]
        group_index, n_groups = M311.factorize_networks(groups)
        arm_label = cases["arm"].astype(str).to_numpy()
        n = len(cases)
        for seed in M330.FOLD_SEEDS:
            fmap = M311.assign_folds(groups, 5, seed)
            fold_ids = np.array([fmap[g] for g in groups], dtype=int)
            scores = dict(data["rules"])
            cal_override = {}
            for spec in SPECS:
                scores[spec] = np.asarray(results[(panel, seed, spec)]["test_score"], dtype=float)
                cal_override[spec] = np.asarray(results[(panel, seed, spec)]["cal_score_by_fold"])
            names = list(SPECS) + list(RULES)
            admit_cap, admit_fixed = {}, {}
            for name in names:
                score = np.asarray(scores[name], dtype=float)
                admit = np.zeros(n, dtype=bool)
                for fold in range(5):
                    test_mask = fold_ids == fold
                    cal_mask = ~test_mask
                    cal = cal_override[name][fold][cal_mask] if name in SPECS else score[cal_mask]
                    selection = M330.select_threshold(
                        cal,
                        bad[cal_mask],
                        groups[cal_mask],
                        draws=int(args.draws_select),
                        seed=stable_seed("aligned-select", panel, seed, fold, name),
                    )
                    admit[test_mask] = score[test_mask] <= selection["threshold"]
                admit_cap[name] = admit
                admit_fixed[name] = M330.fixed_retention_admit(
                    np.where(np.isfinite(score), score, np.inf), fold_ids, data["key"]
                )
            admit_cap["reconstruct_all"] = np.isfinite(error)

            summary = M330.clustered_summary(
                admit_cap, error, group_index, n_groups, draws=int(args.draws_eval),
                seed=stable_seed("r2-ablation-eval", panel, seed),
            )
            fixed = M330.clustered_summary(
                admit_fixed, error, group_index, n_groups, draws=int(args.draws_eval),
                seed=stable_seed("r2-ablation-fixed", panel, seed),
            )
            for name, values in summary.items():
                pooled_rows.append({"panel": panel, "fold_seed": seed, "score": name, "row_type": "riskcap", **values})
            for name, values in fixed.items():
                pooled_rows.append({"panel": panel, "fold_seed": seed, "score": name, "row_type": "fixed70", **values})

            for left, right in CONTRASTS:
                for metric, table in (("retention", admit_cap), ("false_admit", admit_fixed)):
                    contrast = M330.clustered_contrast(
                        table[left], table[right], group_index, n_groups, metric=metric,
                        error=error, draws=int(args.draws_eval),
                        seed=stable_seed("r2-ablation-contrast", panel, seed, metric, left, right),
                    )
                    contrast_rows.append(
                        {"panel": panel, "fold_seed": seed, "metric": metric, "left": left, "right": right, **contrast}
                    )

            for name in names + ["reconstruct_all"]:
                for arm in sorted(set(arm_label)):
                    sel = arm_label == arm
                    adm = admit_cap[name] & sel
                    arm_rows.append(
                        {
                            "panel": panel,
                            "fold_seed": seed,
                            "score": name,
                            "arm": arm,
                            "n_cases": int(sel.sum()),
                            "retention": float(adm.sum() / sel.sum()),
                            "false_admit_rate": float(bad[adm].mean()) if adm.any() else float("nan"),
                        }
                    )
            admission_frames.setdefault(panel, []).append(
                pd.DataFrame(
                    {
                        "fold_seed": seed,
                        "network_id": cases["network_id"].astype(str),
                        "station_id": cases["station_id"].astype(str),
                        "year": cases["year"],
                        "realization_id": cases["realization_id"].astype(str),
                        "arm": arm_label,
                        "policy_bad": bad,
                        **{f"admit_{name}": admit_cap[name] for name in names + ["reconstruct_all"]},
                        **{f"score_{name}": np.asarray(scores[name], dtype=float) for name in names},
                    }
                )
            )
            print(f"[{panel}/seed{seed}] decision protocol done ({time.time() - started:.0f}s)", flush=True)

    pooled = pd.DataFrame(pooled_rows)
    contrasts = pd.DataFrame(contrast_rows)
    pooled.to_csv(OUT / "ablation_operating_points.csv", index=False)
    contrasts.to_csv(OUT / "ablation_contrasts.csv", index=False)
    pd.DataFrame(arm_rows).to_csv(OUT / "ablation_by_arm.csv", index=False)
    for panel, frames in admission_frames.items():
        pd.concat(frames, ignore_index=True).to_parquet(OUT / f"case_admissions_{panel}.parquet", index=False)

    write_summary(pooled, contrasts, pd.DataFrame(arm_rows), checks)
    C.write_fingerprint(
        OUT,
        "scripts/341_wrr_same_capacity_ablation.py",
        {panel: M330.PANELS[panel]["cases"] for panel in panels},
        extra={
            "specs": {k: {"features": list(v[0]), "model": v[1]} for k, v in SPECS.items()},
            "determinism_check": checks,
            "fold_seeds": list(M330.FOLD_SEEDS),
            "elapsed_seconds": round(time.time() - started, 1),
        },
    )
    print(f"[341] done in {time.time() - started:.0f}s -> {OUT}", flush=True)
    return 0


def write_summary(pooled, contrasts, by_arm, checks) -> None:
    lines = [
        "# R2-02 same-capacity ablation",
        "",
        "One learner, one training set, one calibration procedure, one decision protocol.",
        "Retention is at the 5 % cap on the admitted policy reconstruction (mean of three fold seeds).",
        "",
    ]
    ok = all(v["identical"] for v in checks.values()) if checks else None
    lines.append(f"Determinism check (generic+support == the 330 fitted score): {ok}")
    lines.append("")
    risk = pooled[pooled.row_type.eq("riskcap")]
    fixed = pooled[pooled.row_type.eq("fixed70")]
    for panel in risk.panel.unique():
        lines += [f"## {panel}", "", "| score | retention at cap | false-admit | failure rate at fixed 70 % |", "|---|---:|---:|---:|"]
        for name in list(SPECS) + list(RULES) + ["reconstruct_all"]:
            r = risk[(risk.panel == panel) & (risk.score == name)]
            f = fixed[(fixed.panel == panel) & (fixed.score == name)]
            if r.empty:
                continue
            frate = f"{f.false_admit_rate.mean():.3f}" if not f.empty else "-"
            lines.append(f"| {name} | {r.retention.mean():.3f} | {r.false_admit_rate.mean():.3f} | {frate} |")
        lines.append("")
    lines += ["## Paired contrasts (retention, percentage points; group-clustered 95 % interval)", ""]
    lines += ["| panel | left - right | seed 101 | seed 202 | seed 303 |", "|---|---|---|---|---|"]
    ret = contrasts[contrasts.metric.eq("retention")]
    for panel in ret.panel.unique():
        for left, right in CONTRASTS:
            cells = []
            for seed in M330.FOLD_SEEDS:
                row = ret[(ret.panel == panel) & (ret.left == left) & (ret.right == right) & (ret.fold_seed == seed)]
                if row.empty:
                    cells.append("-")
                    continue
                r = row.iloc[0]
                cells.append(f"{100 * r.point:+.1f} [{100 * r.ci_low:+.1f}, {100 * r.ci_high:+.1f}]")
            lines.append(f"| {panel} | {left} - {right} | " + " | ".join(cells) + " |")
    lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
