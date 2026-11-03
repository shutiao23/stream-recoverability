#!/usr/bin/env python3
"""Reviewer-side recomputations for the 2026-11-03 adversarial EMS audit.

Reads only saved tables; fits no model and changes no saved result. Checks:

1. Trend-error scale on the archives whose year set actually changes, sign
   flips by the station's complete-record |t|, and the implied inflation of
   total trend uncertainty, sqrt(1 + mean((e/SE)^2)) - 1.
2. Hamed-Rao modified Mann-Kendall with the published variance factor
   n/n* = 1 + 2/[n(n-1)(n-2)] sum (n-k)(n-k-1)(n-k-2) r_k (Sen-detrended
   ranks, lags significant at 5%), against the saved trend_signal values.
3. Wild cluster intervals of scripts/986_wild_cluster_bootstrap.py with a
   mean-zero influence function, against the saved intervals.
4. Controlled-gap mask geometry from case_designs.csv.

Run from the repository root:
  python docs/reviews/ems_dual_review_20261102/adversarial_checks_20261103.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN = REPO_ROOT / "results/wrr_final_revision_20261031"
EMS = REPO_ROOT / "results/ems_revision_20261102"


def station_table() -> pd.DataFrame:
    trend = pd.read_csv(EMS / "trend_signal.csv")
    stations = trend[trend.record_type.eq("station")]
    return stations.pivot(
        index="station_key", columns="metric", values="value"
    ).apply(pd.to_numeric, errors="coerce")


def trend_scale(stations: pd.DataFrame) -> list[dict]:
    cases = pd.read_csv(FROZEN / "retention_geometry_cases.csv").join(
        stations[["ols_se", "ols_slope"]], on="station_key"
    )
    cases["ratio"] = cases.estimate_error.abs() / cases.ols_se
    cases["abs_t"] = (cases.ols_slope / cases.ols_se).abs()
    key = ["station_key", "replicate"]
    rows = []
    for family, frame in cases.groupby("family"):
        sets = frame.pivot_table(
            index=key, columns="scheme", values="retained_years", aggfunc="first"
        )
        changed = set(sets.index[sets["warm90"] != sets["all"]])
        for scheme in ("warm90", "all"):
            part = frame[frame.scheme.eq(scheme)].set_index(key)
            moved = part[[index in changed for index in part.index]]
            rows.append(
                {
                    "family": family,
                    "scheme": scheme,
                    "n": len(part),
                    "n_changed_year_set": len(moved),
                    "rmse_changed": float(np.sqrt((moved.estimate_error**2).mean())),
                    "median_ratio_changed": float(moved.ratio.median()),
                    "p90_ratio_changed": float(moved.ratio.quantile(0.9)),
                    "pct_ratio_gt1_changed": float(100 * (moved.ratio > 1).mean()),
                    "sign_flips": int(part.slope_sign_disagreement.sum()),
                    "sign_flips_abs_t_below_1": int(
                        part.loc[part.abs_t < 1, "slope_sign_disagreement"].sum()
                    ),
                    "sign_flips_abs_t_at_least_2": int(
                        part.loc[part.abs_t >= 2, "slope_sign_disagreement"].sum()
                    ),
                    "total_uncertainty_inflation_pct": float(
                        100 * (np.sqrt(1 + (part.ratio**2).mean()) - 1)
                    ),
                }
            )
    return rows


def mann_kendall(y: np.ndarray) -> tuple[float, float]:
    n = len(y)
    s = float(sum(np.sign(y[j] - y[i]) for i in range(n - 1) for j in range(i + 1, n)))
    _, counts = np.unique(y, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5) - np.sum(counts * (counts - 1) * (2 * counts + 5))) / 18
    return s, float(var_s)


def hamed_rao(stations: pd.DataFrame) -> dict:
    truths = pd.read_csv(FROZEN / "reference_truths.csv").drop_duplicates(
        ["station_key", "year"]
    )
    year_sets = (
        pd.read_csv(FROZEN / "reference_year_sets.csv")
        .drop_duplicates("station_key")
        .set_index("station_key")
    )
    rows = []
    for station, frame in truths.groupby("station_key"):
        years = {int(v) for v in str(year_sets.loc[station, "reference_years"]).split(";")}
        frame = frame[frame.year.astype(int).isin(years)].sort_values("year")
        y = frame.eval_truth_h30.to_numpy(float)
        x = frame.year.to_numpy(float) / 10
        n = len(y)
        s, var_s = mann_kendall(y)
        sen = np.median([(y[j] - y[i]) / (x[j] - x[i]) for i in range(n - 1) for j in range(i + 1, n)])
        ranks = stats.rankdata(y - sen * x)
        ranks -= ranks.mean()
        factor = 1.0
        for lag in range(1, n - 2):
            r = float(ranks[lag:] @ ranks[:-lag] / (ranks @ ranks))
            if abs(r) > stats.norm.ppf(0.975) / np.sqrt(n):
                factor += 2 / (n * (n - 1) * (n - 2)) * (n - lag) * (n - lag - 1) * (n - lag - 2) * r
        if factor <= 0:
            rows.append((float("nan"), factor))
            continue
        z = (s - np.sign(s)) / np.sqrt(var_s * factor) if s else 0.0
        rows.append((float(2 * stats.norm.sf(abs(z))), factor))
    p_values = np.array([row[0] for row in rows])
    return {
        "stations": len(rows),
        "hamed_rao_p_below_005_published_formula": int((p_values < 0.05).sum()),
        "stations_with_nonpositive_factor": int(np.isnan(p_values).sum()),
        "hamed_rao_p_below_005_saved": int((stations.hamed_rao_p < 0.05).sum()),
        "saved_hamed_rao_n_star_median": float(stations.hamed_rao_n_star.median()),
        "stations_with_significant_lag": int(sum(row[1] != 1.0 for row in rows)),
        "note": "saved n_star is the factor n/n*; saved Var* = Var(S)*n/(n/n*) = Var(S)*n*",
    }


def wild_bootstrap() -> dict:
    spec = importlib.util.spec_from_file_location(
        "wcb", REPO_ROOT / "scripts/986_wild_cluster_bootstrap.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def centered(mse_a, mse_b, labels, weights="rademacher", seed=module.SEED, draws=module.DRAWS):
        mse_a, mse_b = np.asarray(mse_a, float), np.asarray(mse_b, float)
        rmse_a, rmse_b = np.sqrt(mse_a.mean()), np.sqrt(mse_b.mean())
        influence = 0.5 * ((mse_a - mse_a.mean()) / rmse_a - (mse_b - mse_b.mean()) / rmse_b)
        groups, share = module.cluster_shares(pd.Series(labels))
        contributions = np.array([influence[labels == g].mean() for g in groups])
        rng = np.random.default_rng(seed)
        support = [-1.0, 1.0] if weights == "rademacher" else module.WEBB
        low, high = np.quantile(
            rng.choice(support, size=(draws, len(groups))) @ (share * contributions),
            [0.025, 0.975],
        )
        estimate = float(rmse_a - rmse_b)
        return {"estimate": estimate, "ci_low": estimate + low, "ci_high": estimate + high,
                "groups": len(groups), "draws": draws, "weights": weights, "seed": seed}

    module.wild_influence_interval = centered
    fixed = pd.DataFrame(module.retention_rows() + module.estimator_rows())
    saved = pd.read_csv(EMS / "wild_cluster_bootstrap.csv")
    key = ["family", "contrast"]
    merged = fixed[key + ["estimate", "wild_rademacher_ci_low", "wild_rademacher_ci_high"]].merge(
        saved[key + ["wild_rademacher_ci_low", "wild_rademacher_ci_high",
                     "group_boot_ci_low", "group_boot_ci_high"]],
        on=key, suffixes=("_centered", "_saved"),
    )
    group_width = merged.group_boot_ci_high - merged.group_boot_ci_low
    merged["ratio_saved"] = (merged.wild_rademacher_ci_high_saved - merged.wild_rademacher_ci_low_saved) / group_width
    merged["ratio_centered"] = (merged.wild_rademacher_ci_high_centered - merged.wild_rademacher_ci_low_centered) / group_width
    merged["zero_in_centered"] = (merged.wild_rademacher_ci_low_centered <= 0) & (merged.wild_rademacher_ci_high_centered >= 0)
    merged["zero_in_group"] = (merged.group_boot_ci_low <= 0) & (merged.group_boot_ci_high >= 0)
    return {
        "median_width_ratio_saved": float(merged.ratio_saved.median()),
        "median_width_ratio_centered": float(merged.ratio_centered.median()),
        "method_dependent_centered": merged.loc[
            merged.zero_in_centered != merged.zero_in_group, key
        ].to_dict("records"),
        "rows": merged.round(4).to_dict("records"),
    }


def mask_geometry() -> dict:
    designs = pd.read_csv(FROZEN / "case_designs.csv")
    crossed = designs[designs.family.eq("crossed")]
    masked_share, starts, summer = [], [], []
    for row in crossed.itertuples():
        masks = json.loads(row.masks)
        masked_share.append(len(masks) / row.n_years)
        for value in masks.values():
            for segment in filter(None, str(value).split(";")):
                start, length = map(int, segment.split(":"))
                starts.append(start)
                summer.append(not (start + length - 1 < 152 or start > 243))
    return {
        "archives": len(crossed),
        "median_masked_year_share": float(np.median(masked_share)),
        "archives_with_every_year_masked": int(sum(share == 1 for share in masked_share)),
        "segments": len(starts),
        "pct_segments_without_jun_aug_overlap": float(100 * (1 - np.mean(summer))),
        "pct_segments_starting_before_doy_120": float(100 * np.mean(np.array(starts) < 120)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).with_suffix(".json"))
    args = parser.parse_args()
    stations = station_table()
    result = {
        "inputs": [str(p.relative_to(REPO_ROOT)) for p in (
            FROZEN / "retention_geometry_cases.csv", FROZEN / "reference_truths.csv",
            FROZEN / "reference_year_sets.csv", FROZEN / "case_designs.csv",
            EMS / "trend_signal.csv", EMS / "wild_cluster_bootstrap.csv")],
        "trend_scale": trend_scale(stations),
        "hamed_rao": hamed_rao(stations),
        "wild_bootstrap": wild_bootstrap(),
        "mask_geometry": mask_geometry(),
    }
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "inputs"}, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
