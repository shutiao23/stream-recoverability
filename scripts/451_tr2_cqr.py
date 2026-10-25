#!/usr/bin/env python3
"""TR2-M2: conformal calibration of the D2* quantiles by decision-time difficulty.

Split-conformal quantile calibration in the spirit of conformalized quantile
regression (Romano, Patterson and Candes 2019), applied level by level: for
level tau in difficulty group g, the offset is the finite-sample tau-quantile of
the residual y - q_tau among calibration cases of g, and the calibrated
quantile is q_tau plus that offset (levels are then sorted). Groups cross the
share of the climatological peak window hidden (0, (0, .25], ..., (.75, 1])
with the information layer (neighbour, air, other); a group smaller than the
configured minimum borrows the air layer of the same bin. Calibration is
leave-one-region-out and never uses the held-out region. Offsets computed on
all source cases are stored for the frozen pipeline.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_features as F

OUT = T.OUT / "e4_estimators"
LEVELS = F.QUANTILES


def difficulty_groups(cases: pd.DataFrame, settings: dict, counts: dict[str, int] | None = None) -> pd.Series:
    edges = settings["conformal_overlap_bins"]
    overlap = cases.peak_overlap.to_numpy()
    bins = np.where(overlap <= 0, 0, np.clip(np.searchsorted(edges, overlap, side="left"), 1, len(edges) - 1))
    layer = cases.policy_choice.where(cases.policy_choice.isin(["donor_ridge", "air_ridge"]), "other").to_numpy()
    groups = pd.Series([f"bin{b}|{l}" for b, l in zip(bins, layer)], index=cases.index)
    if counts is not None:
        small = {g for g, n in counts.items() if g.endswith("|other") and n < settings["conformal_min_group_cases"]}
        groups = groups.where(~groups.isin(small), groups.str.replace("|other", "|air_ridge", regex=False))
    return groups


def offsets(residuals: np.ndarray) -> np.ndarray:
    """Finite-sample conformal offsets for each level from residuals y - q_tau (n x levels)."""

    n = len(residuals)
    out = np.empty(len(LEVELS))
    for j, level in enumerate(LEVELS):
        ordered = np.sort(residuals[:, j])
        if level >= 0.5:
            k = math.ceil((n + 1) * level)
            out[j] = ordered[min(k, n) - 1]
        else:
            k = math.floor((n + 1) * level)
            out[j] = ordered[max(k, 1) - 1]
    return out


def main() -> int:
    settings = T.settings()
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof = pd.read_parquet(OUT / "oof_predictions.parquet")
    if len(oof) != len(cases) or not (oof.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
        raise RuntimeError("Out-of-fold predictions are not aligned with the cases")
    names = [f"h30__P5b_q{int(level * 100):02d}" for level in LEVELS]
    q = oof[names].to_numpy()
    truth = cases.eval_truth_h30.to_numpy()
    raw_groups = difficulty_groups(cases, settings)
    groups = difficulty_groups(cases, settings, raw_groups.value_counts().to_dict())
    residual = truth[:, None] - q
    calibrated = np.full_like(q, np.nan)
    regions = cases.region.to_numpy()
    for region in np.unique(regions):
        held = regions == region
        for group in groups[held].unique():
            target = held & (groups.to_numpy() == group)
            pool = ~held & (groups.to_numpy() == group)
            if pool.sum() < 50:
                pool = ~held
            calibrated[target] = q[target] + offsets(residual[pool])
    calibrated = np.sort(calibrated, axis=1)
    out = cases[["station_key", "year", "realization_id", "region", "independence_group", "design_family", "policy_choice"]].copy()
    out["difficulty_group"] = groups.to_numpy()
    for level, values in zip(LEVELS, calibrated.T):
        out[f"h30__D2c_q{int(level * 100):02d}"] = values
    out.to_parquet(OUT / "oof_calibrated.parquet", index=False)
    # Offsets on all source cases, for the frozen pipeline.
    full = {group: offsets(residual[(groups == group).to_numpy()]).tolist() for group in sorted(groups.unique())}
    T.write_json(OUT / "conformal_offsets.json", {"levels": list(LEVELS), "groups": full, "group_counts": groups.value_counts().to_dict(), "merged_small_other_layer_into_air": sorted(set(raw_groups) - set(groups))})

    rows = []
    for label, lower, upper in (("raw", q[:, 0], q[:, -1]), ("calibrated", calibrated[:, 0], calibrated[:, -1])):
        covered = (truth >= lower) & (truth <= upper)
        width = upper - lower
        for population in ("all", "mech", "deploy"):
            selected = np.ones(len(cases), dtype=bool) if population == "all" else cases.design_family.eq("crossed" if population == "mech" else "calendar").to_numpy()
            for group in sorted(groups.unique()):
                keep = selected & (groups.to_numpy() == group)
                if keep.sum() < 30:
                    continue
                rows.append({"version": label, "population": population, "group": group, "n": int(keep.sum()), "n_groups": int(cases.loc[keep, "independence_group"].nunique()), "coverage90": float(covered[keep].mean()), "width90": float(width[keep].mean())})
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "conformal_group_coverage.csv", index=False)
    calibrated_all = table.loc[(table.version == "calibrated") & (table.population == "all")]
    gate = bool(calibrated_all.coverage90.between(0.85, 0.95).all())
    # P1 stratum with the calibrated median as the delivered value.
    stratum = cases.design_family.eq("crossed") & cases.policy_choice.eq("air_ridge") & cases.eval_true_peak_hidden_fraction.ge(0.5)
    median = calibrated[:, LEVELS.index(0.5)]
    frame = pd.DataFrame({"independence_group": cases.loc[stratum, "independence_group"].to_numpy(), "e0": (cases.h30__policy - cases.eval_truth_h30)[stratum].to_numpy(), "e": (median - truth)[stratum.to_numpy()], "c": ((truth >= calibrated[:, 0]) & (truth <= calibrated[:, -1]))[stratum.to_numpy()].astype(float)})
    reduction = lambda f: float(1 - abs(f.e.mean()) / abs(f.e0.mean()))
    boot = T.group_bootstrap(frame, "independence_group", reduction, settings["bootstrap_draws"], settings["seed"])
    cover = T.group_bootstrap(frame, "independence_group", lambda f: float(f.c.mean()), settings["bootstrap_draws"], settings["seed"] + 1)
    summary = {
        "gate_1_every_group_coverage_85_95": gate, "n_groups_evaluated": int(len(calibrated_all)),
        "min_group_coverage": float(calibrated_all.coverage90.min()), "max_group_coverage": float(calibrated_all.coverage90.max()),
        "raw_min_group_coverage": float(table.loc[(table.version == "raw") & (table.population == "all")].coverage90.min()),
        "P1_bias_P0": float(frame.e0.mean()), "P1_bias_D2c": float(frame.e.mean()), "P1_reduction": reduction(frame),
        "P1_reduction_lower95": float(np.quantile(boot, 0.025)), "P1_reduction_upper95": float(np.quantile(boot, 0.975)),
        "P1_coverage90": float(frame.c.mean()), "P1_coverage90_lower95": float(np.quantile(cover, 0.025)), "P1_coverage90_upper95": float(np.quantile(cover, 0.975)),
        "P1_n": int(len(frame)), "P1_n_groups": int(frame.independence_group.nunique()),
    }
    T.write_json(OUT / "conformal_summary.json", summary)
    print(table.loc[table.population.eq("all")].pivot_table(index="group", columns="version", values=["coverage90", "width90"]).round(3).to_string(), flush=True)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
