#!/usr/bin/env python3
"""Identify Bavaria versus FOEN recovery differences without claiming a process.

The comparison reuses saved forward controlled-gap annual cases. Common support
and common-weight standardization use visible trial and information fields.
Peak-hidden labels use withheld complete
references and are evaluation-only. Regulation labels of unmatched_gages do not
mean unregulated rivers.
"""
from __future__ import annotations

import json
import hashlib
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "results/wrr_adversarial_review_20261027/failure_strata/failure_strata_cases.parquet"
OUT = ROOT / "results/wrr_process_revision_20261029"
PAPER = ROOT / "paper/wrr_tr"
TOL = 1e-8
BOOT = 2000
SEED = 20261028
REGIONS = ("foen", "gkd_bayern")
MATCHES = {
    "geometry": ["gap_bin", "overlap_bin", "year_bin", "donor_bin"],
    "geometry_plus_policy": ["gap_bin", "overlap_bin", "year_bin", "donor_bin", "policy_choice"],
}


def year_bin(year: pd.Series) -> pd.Series:
    return pd.cut(
        year,
        bins=[2009, 2014, 2019, 2025],
        labels=["2010-2014", "2015-2019", "2020-2025"],
        right=True,
    )


def complete_bin(values: pd.Series) -> pd.Series:
    return pd.cut(
        values,
        bins=[-0.1, 10.1, 20.1, np.inf],
        labels=["<=10", "11-20", "21+"],
    )


def bootstrap_mean(values: np.ndarray, groups: np.ndarray, seed: int) -> tuple[float, float, float]:
    values = np.asarray(values, float)
    groups = np.asarray(groups)
    if len(values) == 0 or len(values) != len(groups) or not np.isfinite(values).all() or pd.isna(groups).any():
        raise ValueError("Cluster bootstrap requires finite values and nonmissing, paired group labels")
    unique = np.array(sorted(set(groups)))
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(BOOT):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        index = np.concatenate([np.flatnonzero(groups == group) for group in chosen])
        draws.append(float(np.mean(values[index])))
    return float(np.mean(values)), float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def score_block(block: pd.DataFrame, prefix: str) -> dict:
    truth = block.reference_h30.to_numpy(float)
    point = block[f"{prefix}_q50"].to_numpy(float) if f"{prefix}_q50" in block else block["D2"].to_numpy(float)
    if prefix == "D2":
        low, high, point = block.D2_q05.to_numpy(float), block.D2_q95.to_numpy(float), block.D2.to_numpy(float)
    else:
        low, high, point = (
            block.stochastic_cal_q05.to_numpy(float),
            block.stochastic_cal_q95.to_numpy(float),
            block.stochastic_cal_q50.to_numpy(float),
        )
    groups = block.independence_group.to_numpy()
    error = point - truth
    cover = (low - TOL <= truth) & (truth <= high + TOL)
    below = truth < low - TOL
    above = truth > high + TOL
    out = {
        "n": int(len(block)),
        "stations": int(block.station_key.nunique()),
        "groups": int(block.independence_group.nunique()),
    }
    for name, values in {
        "mae": np.abs(error),
        "bias": error,
        "coverage90": cover.astype(float),
        "width90": high - low,
        "below_interval": below.astype(float),
        "above_interval": above.astype(float),
    }.items():
        mean, low_ci, high_ci = bootstrap_mean(values, groups, SEED)
        out[name] = mean
        out[f"{name}_low"] = low_ci
        out[f"{name}_high"] = high_ci
    return out


def summarize_strata(work: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region, region_block in work.groupby("region"):
        for hidden, hidden_block in region_block.groupby("peak_hidden"):
            for policy, block in hidden_block.groupby("policy_choice"):
                for method, prefix in [("D2", "D2"), ("classical", "stochastic")]:
                    row = score_block(block, prefix)
                    row.update(
                        region=region,
                        peak_hidden=bool(hidden),
                        policy_choice=policy,
                        method=method,
                    )
                    rows.append(row)
    return pd.DataFrame(rows)


def matched_table(work: pd.DataFrame, keys: list[str], label: str) -> pd.DataFrame:
    work = work.copy()
    work["cell"] = work[keys].astype(str).agg("|".join, axis=1)
    counts = work.groupby(["cell", "region"]).size().unstack(fill_value=0)
    if "foen" not in counts or "gkd_bayern" not in counts:
        raise RuntimeError("Both regions are required for matching")
    common = counts.loc[(counts.foen > 0) & (counts.gkd_bayern > 0)].index
    rows = []
    for region, region_block in work.groupby("region"):
        supported = region_block.loc[region_block.cell.isin(common)]
        leftover = region_block.loc[~region_block.cell.isin(common)]
        for part, block in [("common_support", supported), ("unmatched", leftover)]:
            if block.empty:
                continue
            for method, prefix in [("D2", "D2"), ("classical", "stochastic")]:
                row = score_block(block, prefix)
                row.update(
                    matching=label,
                    region=region,
                    part=part,
                    method=method,
                    n_region=len(region_block),
                    support_fraction=len(supported) / len(region_block),
                    n_common_cells=int(len(common)),
                )
                rows.append(row)
    return pd.DataFrame(rows)


def residual_table(work: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (region, policy), block in work.groupby(["region", "policy_choice"]):
        groups = block.independence_group.to_numpy()
        row = {
            "region": region,
            "policy_choice": policy,
            "n": len(block),
            "stations": int(block.station_key.nunique()),
            "groups": int(block.independence_group.nunique()),
        }
        for column in [
            "n_visible_donors",
            "donor_corr_mean",
            "n_complete_years",
            "hist_reconstructor_oof_daily_bias",
            "hist_reconstructor_oof_daily_abs90",
            "hist_reconstructor_oof_lag1",
            "law_phi_r",
            "law_sigma_r_warm",
            "air_warm_z_mean",
            "reconstructor_oof_daily_sd",
        ]:
            values = pd.to_numeric(block[column], errors="coerce").to_numpy(float)
            finite = np.isfinite(values)
            if finite.sum() == 0:
                row[column] = np.nan
                continue
            mean, low, high = bootstrap_mean(values[finite], groups[finite], SEED)
            row[column] = mean
            row[f"{column}_low"] = low
            row[f"{column}_high"] = high
        rows.append(row)
    return pd.DataFrame(rows)


def protocol_table(work: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region, block in work.groupby("region"):
        rows.append(
            {
                "region": region,
                "stations": int(block.station_key.nunique()),
                "groups": int(block.independence_group.nunique()),
                "cases": int(len(block)),
                "statistic_class": ",".join(sorted(block.statistic_class.dropna().unique())),
                "regulation_status": ",".join(sorted(block.regulation_status.dropna().unique())),
                "policy_air_ridge": float(block.policy_choice.eq("air_ridge").mean()),
                "policy_donor_ridge": float(block.policy_choice.eq("donor_ridge").mean()),
                "mean_visible_donors": float(block.n_visible_donors.mean()),
                "mean_complete_training_years": float(block.n_complete_years.mean()),
                "hidden_peak_fraction": float(block.peak_hidden.mean()),
            }
        )
    return pd.DataFrame(rows)


def composition_table(work: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, name in [
        ("gap_bin", "longest_gap"),
        ("overlap_bin", "training_peak_overlap"),
        ("year_bin", "year_position"),
        ("donor_bin", "visible_donors"),
        ("complete_bin", "training_complete_years"),
        ("policy_choice", "reconstructor"),
    ]:
        counts = pd.crosstab(work.region, work[column], normalize="index")
        for region, row in counts.iterrows():
            for stratum, share in row.items():
                rows.append(
                    {
                        "field": name,
                        "region": region,
                        "stratum": str(stratum),
                        "share": float(share),
                    }
                )
    return pd.DataFrame(rows)


def common_cell_weights(work: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return common-support cases with case weights summing to one per region.

    Both standardized targets have exactly the same cell distribution in each
    region. They retain the observed conditional outcome means within cells;
    neither adjustment identifies a reconstructor or region intervention.
    """
    work = work.copy()
    if work[keys + ["region"]].isna().any().any():
        raise ValueError("Missing common-support cell fields or regional identity")
    if not set(work.region).issubset(set(REGIONS)):
        raise ValueError("Unexpected region in two-region standardization")
    if work[keys].astype(str).apply(lambda column: column.str.contains("|", regex=False)).any().any():
        raise ValueError("Cell field contains the reserved delimiter")
    work["cell"] = work[keys].astype(str).agg("|".join, axis=1)
    counts = work.groupby(["cell", "region"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=REGIONS, fill_value=0)
    common = counts.loc[counts.gt(0).all(axis=1)].copy()
    if common.empty:
        raise ValueError("No cross-region common cells")
    cells = common.rename(columns={r: f"{r}_n" for r in REGIONS})
    for region in REGIONS:
        cells[f"{region}_share"] = common[region] / common[region].sum()
    cells["min_count_target"] = common.min(axis=1) / common.min(axis=1).sum()
    cells["equal_cell_target"] = 1 / len(common)
    supported = work.loc[work.cell.isin(common.index)].copy()
    supported["raw_common_support"] = supported.groupby("region").cell.transform("size").rdiv(1)
    n_cell = supported.groupby(["region", "cell"]).cell.transform("size")
    for name, target in [("min_count", "min_count_target"), ("equal_cell", "equal_cell_target")]:
        supported[name] = supported.cell.map(cells[target]) / n_cell
    return supported, cells.reset_index()


def outcome_values(block: pd.DataFrame, method: str) -> dict[str, np.ndarray]:
    truth = block.reference_h30.to_numpy(float)
    if method == "D2":
        point, low, high = (block[c].to_numpy(float) for c in ["D2", "D2_q05", "D2_q95"])
    elif method == "classical":
        point, low, high = (
            block[c].to_numpy(float)
            for c in ["stochastic_cal_q50", "stochastic_cal_q05", "stochastic_cal_q95"]
        )
    else:
        raise ValueError(f"Unknown regional outcome method: {method}")
    if not np.isfinite(np.column_stack([truth, point, low, high])).all():
        raise ValueError("Regional outcomes require finite reference, point and interval endpoints")
    if (low > high).any():
        raise ValueError("Regional interval endpoints are reversed")
    error = point - truth
    return {
        "coverage90": ((low - TOL <= truth) & (truth <= high + TOL)).astype(float),
        "mae": np.abs(error), "bias": error, "width90": high - low,
        "below_interval": (truth < low - TOL).astype(float),
        "above_interval": (truth > high + TOL).astype(float),
    }


def categorical_tv(block: pd.DataFrame, column: str, weight: str) -> float:
    distributions = []
    for region in REGIONS:
        part = block.loc[block.region.eq(region)]
        category = part[column].astype("object").fillna("<missing>").astype(str)
        distributions.append(part[weight].groupby(category).sum())
    a, b = distributions[0].align(distributions[1], fill_value=0)
    return float(0.5 * (a - b).abs().sum())


def weighted_continuous(block: pd.DataFrame, column: str, weight: str) -> tuple[float, float, float]:
    values = pd.to_numeric(block[column], errors="coerce").to_numpy(float)
    weights = block[weight].to_numpy(float)
    finite = np.isfinite(values)
    missing = float(weights[~finite].sum() / weights.sum())
    if not finite.any():
        return np.nan, np.nan, missing
    values, weights = values[finite], weights[finite]
    mean = np.average(values, weights=weights)
    return float(mean), float(np.average((values - mean) ** 2, weights=weights)), missing


def weighted_ks(block: pd.DataFrame, column: str, weight: str) -> float:
    curves = []
    observed = pd.to_numeric(block[column], errors="coerce").to_numpy(float)
    grid = np.unique(observed[np.isfinite(observed)])
    for region in REGIONS:
        part = block.loc[block.region.eq(region)]
        x = pd.to_numeric(part[column], errors="coerce").to_numpy(float)
        w = part[weight].to_numpy(float)
        finite = np.isfinite(x)
        if not finite.any():
            return np.nan
        order = np.argsort(x[finite])
        values, weights = x[finite][order], w[finite][order]
        cdf = np.r_[0, np.cumsum(weights) / weights.sum()]
        curves.append(cdf[np.searchsorted(values, grid, side="right")])
    return float(np.max(np.abs(curves[0] - curves[1])))


def standardized_tables(work: pd.DataFrame) -> dict[str, pd.DataFrame]:
    scores, support, cells_out, categorical, continuous = [], [], [], [], []
    discrete = ["cell", "gap_bin", "overlap_bin", "year_bin", "donor_bin", "complete_bin", "policy_choice"]
    numeric = [
        "longest_run", "peak_overlap", "year", "n_visible_donors", "donor_corr_mean",
        "n_complete_years", "train_h30_mean", "train_h30_sd", "air_warm_z_mean",
        "hist_reconstructor_oof_daily_bias", "hist_reconstructor_oof_daily_abs90",
        "hist_reconstructor_oof_lag1", "reconstructor_oof_daily_sd",
    ]
    for matching, keys in MATCHES.items():
        supported, cells = common_cell_weights(work, keys)
        cells["matching"] = matching
        cells_out.append(cells)
        full = work.copy()
        full["cell"] = full[keys].astype(str).agg("|".join, axis=1)
        full["full_region"] = full.groupby("region").cell.transform("size").rdiv(1)
        for region in REGIONS:
            original, retained = [x.loc[x.region.eq(region)] for x in [work, supported]]
            support.append(dict(
                matching=matching, region=region, n_region=len(original), n_supported=len(retained),
                n_excluded=len(original) - len(retained), support_fraction=len(retained) / len(original),
                loss_fraction=1 - len(retained) / len(original), n_common_cells=len(cells),
                original_stations=original.station_key.nunique(), supported_stations=retained.station_key.nunique(),
                original_groups=original.independence_group.nunique(), supported_groups=retained.independence_group.nunique(),
            ))
            for weighting in ["raw_common_support", "min_count", "equal_cell"]:
                w = retained[weighting].to_numpy(float)
                for method in ["D2", "classical"]:
                    scores.append(dict(
                        matching=matching, weighting=weighting, region=region, method=method,
                        n=len(retained), stations=retained.station_key.nunique(),
                        groups=retained.independence_group.nunique(), n_common_cells=len(cells),
                        effective_case_n=float(1 / (w @ w)),
                        **{name: float(w @ v) for name, v in outcome_values(retained, method).items()},
                    ))
        reference_sd = {}
        for column in numeric:
            variances = [weighted_continuous(full.loc[full.region.eq(r)], column, "full_region")[1] for r in REGIONS]
            reference_sd[column] = float(np.sqrt(np.mean(variances)))
        for weighting, block in [("full_region", full), *[(w, supported) for w in ["raw_common_support", "min_count", "equal_cell"]]]:
            for column in discrete:
                categorical.append(dict(matching=matching, weighting=weighting, field=column,
                                        total_variation=categorical_tv(block, column, weighting)))
            for column in numeric:
                metrics = [weighted_continuous(block.loc[block.region.eq(r)], column, weighting) for r in REGIONS]
                a, b = metrics
                denominator = reference_sd[column]
                continuous.append(dict(
                    matching=matching, weighting=weighting, field=column,
                    foen_mean=a[0], bavaria_mean=b[0], foen_sd=np.sqrt(a[1]), bavaria_sd=np.sqrt(b[1]),
                    foen_missing_weight=a[2], bavaria_missing_weight=b[2], mean_difference=a[0] - b[0],
                    smd=(a[0] - b[0]) / denominator if denominator > 0 else np.nan,
                    reference_pooled_sd=denominator, weighted_ks=weighted_ks(block, column, weighting),
                ))
    return {
        "region_standardized": pd.DataFrame(scores), "region_support_loss": pd.DataFrame(support),
        "region_common_cells": pd.concat(cells_out, ignore_index=True),
        "region_balance_categorical": pd.DataFrame(categorical),
        "region_balance_continuous": pd.DataFrame(continuous),
    }


def write_revision_tex(tables: dict[str, pd.DataFrame]) -> None:
    scores = tables["region_standardized"].query("method == 'D2'")
    support = tables["region_support_loss"].set_index(["matching", "region"])
    categorical = tables["region_balance_categorical"].set_index(["matching", "weighting", "field"])
    continuous = tables["region_balance_continuous"].set_index(["matching", "weighting", "field"])
    lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Descriptive regional coverage standardization on common cells. Min-count weights are the primary common target; equal-cell weights are a sensitivity analysis. Coverage is in percent and differences are percentage points. Geometry cells contain gap, training-peak overlap, year and visible-donor bins. Adding the reconstructor changes the supported population; it does not identify a reconstructor effect.}",
        r"\label{tab:region-standardized}", r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrr}", r"\toprule",
        r"Cells & Weights & FOEN & Bavaria & Difference \\", r"\midrule",
    ]
    macros = []
    for matching, title, tag in [("geometry", "Geometry", "Geometry"), ("geometry_plus_policy", "+ reconstructor", "Policy")]:
        for weighting, weight_label, weight_tag in [("raw_common_support", "Original", "Raw"), ("min_count", "Min-count", "Min"), ("equal_cell", "Equal-cell", "Equal")]:
            block = scores.loc[scores.matching.eq(matching) & scores.weighting.eq(weighting)].set_index("region")
            f, b = block.loc["foen"].coverage90, block.loc["gkd_bayern"].coverage90
            lines.append(f"{title} & {weight_label} & {100*f:.2f} & {100*b:.2f} & {100*(f-b):.2f} " + r"\\")
            for suffix, value in [("FoenCov", 100*f), ("BavariaCov", 100*b), ("Gap", 100*(f-b))]:
                macros.append(r"\newcommand{\PRR" + tag + weight_tag + suffix + "}{" + f"{value:.2f}" + "}")
        for region, rtag in [("foen", "Foen"), ("gkd_bayern", "Bavaria")]:
            row = support.loc[(matching, region)]
            for suffix, value in [("Supported", str(int(row.n_supported))), ("Total", str(int(row.n_region))), ("SupportPct", f"{100*row.support_fraction:.1f}"), ("LossPct", f"{100*row.loss_fraction:.1f}")]:
                macros.append(r"\newcommand{\PRR" + tag + rtag + suffix + "}{" + value + "}")
        for weight, wtag in [("raw_common_support", "Raw"), ("min_count", "Min"), ("equal_cell", "Equal")]:
            tv = categorical.loc[(matching, weight, "cell")].total_variation
            macros.append(r"\newcommand{\PRR" + tag + wtag + "TV}{" + f"{tv:.3f}" + "}")
    f_support = support.loc[("geometry_plus_policy", "foen")]
    b_support = support.loc[("geometry_plus_policy", "gkd_bayern")]
    lines += [
        r"\bottomrule\end{tabular}}",
        r"\par\footnotesize Reconstructor common support retains "
        + f"{int(f_support.n_supported)}/{int(f_support.n_region):,} FOEN and {int(b_support.n_supported)}/{int(b_support.n_region):,} Bavaria cases. "
        + "Switzerland has no air-ridge cases, so Bavaria's air-reconstruction failure stratum has no cross-region counterpart.",
        r"\end{table}",
    ]
    balance = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Remaining balance after regional standardization. TV denotes total variation of discrete distributions. History denotes training complete-year count. SMD denotes the FOEN-minus-Bavaria mean difference divided by the pooled population standard deviation in the original two regions, kept fixed across weighting schemes. Full continuous means, missing-weight fractions and weighted Kolmogorov distances are saved with the analysis. Zero joint-cell TV does not ensure balance within bins.}",
        r"\label{tab:region-balance}", r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrr}", r"\toprule",
        r"Cells & Weights & Joint TV & Policy TV & History-bin TV & History SMD \\", r"\midrule",
    ]
    for matching, title in [("geometry", "Geometry"), ("geometry_plus_policy", "+ reconstructor")]:
        for weighting, label in [("full_region", "Full"), ("raw_common_support", "Common raw"), ("min_count", "Min-count"), ("equal_cell", "Equal-cell")]:
            tvs = [categorical.loc[(matching, weighting, field)].total_variation for field in ["cell", "policy_choice", "complete_bin"]]
            smd = continuous.loc[(matching, weighting, "n_complete_years")].smd
            balance.append(f"{title} & {label} & " + " & ".join(f"{v:.3f}" for v in [*tvs, smd]) + " " + r"\\")
    balance += [r"\bottomrule\end{tabular}}", r"\end{table}"]
    PAPER.mkdir(parents=True, exist_ok=True)
    for name, content in [("process_region_revision_table.tex", lines), ("process_region_revision_balance.tex", balance), ("process_region_revision_values.tex", macros)]:
        (PAPER / name).write_text("\n".join(content) + "\n")


def prepare_region_cases(raw: pd.DataFrame) -> pd.DataFrame:
    work = raw.loc[raw.region.isin(REGIONS) & raw.family.eq("crossed") & raw["mode"].eq("forward")].copy()
    identity = ["station_key", "year", "replicate", "region", "independence_group"]
    if work[identity].isna().any().any():
        raise ValueError("Missing regional case identity or connected group")
    if work.duplicated(["station_key", "year", "replicate"]).any():
        raise ValueError("Duplicate station-year-replicate case in regional denominator")
    if work.groupby("station_key")[["region", "independence_group"]].nunique().gt(1).any().any():
        raise ValueError("Inconsistent station region or connected group")
    if not work.year.between(2010, 2025).all() or not work.year.eq(work.year.astype(int)).all():
        raise ValueError("Regional evaluation years must be integers in 2010-2025")
    work["year_bin"] = year_bin(work.year)
    work["complete_bin"] = complete_bin(work.n_complete_years)
    if work[["gap_bin", "overlap_bin", "year_bin", "donor_bin", "policy_choice", "complete_bin"]].isna().any().any():
        raise ValueError("Missing regional composition fields")
    for method in ["D2", "classical"]:
        outcome_values(work, method)
    return work


def main() -> int:
    global OUT, PAPER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--paper", type=Path, default=PAPER, help="Destination of generated TeX inputs")
    args = parser.parse_args()
    OUT, PAPER = args.output, args.paper
    OUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(CASES)
    work = prepare_region_cases(raw)
    protocol = protocol_table(work)
    strata = summarize_strata(work)
    protocol.to_csv(OUT / "region_protocol.csv", index=False)
    composition_table(work).to_csv(OUT / "region_composition.csv", index=False)
    strata.to_csv(OUT / "region_policy_hidden.csv", index=False)
    residual_table(work).to_csv(OUT / "region_training_support.csv", index=False)
    trial = matched_table(
        work,
        ["gap_bin", "overlap_bin", "year_bin", "donor_bin"],
        "gap_overlap_year_donors",
    )
    info = matched_table(
        work,
        ["gap_bin", "overlap_bin", "year_bin", "donor_bin", "policy_choice"],
        "trial_plus_reconstructor",
    )
    pd.concat([trial, info], ignore_index=True).to_csv(OUT / "region_matched.csv", index=False)
    hidden = work.loc[work.peak_hidden].copy()
    hidden_match = matched_table(
        hidden,
        ["gap_bin", "overlap_bin", "year_bin", "donor_bin", "policy_choice"],
        "hidden_peak_trial_plus_reconstructor",
    )
    hidden_match.to_csv(OUT / "region_hidden_matched.csv", index=False)
    standardized = standardized_tables(work)
    for name, table in standardized.items():
        table.to_csv(OUT / f"{name}.csv", index=False)
    write_revision_tex(standardized)
    report = {
        "scope": "Saved crossed forward annual cases; common support and common-weight standardization are descriptive and do not identify causal region, reconstructor or river-process effects.",
        "denominator": {"input_rows": len(raw), "selected_crossed_forward_rows": len(work), "unit": "station-year-replicate; repeated masks are retained, not unique annual observations", "duplicate_or_nonfinite_outcomes": "fail closed; missing intervals are not counted as failed coverage"},
        "primary_target": "Common-cell weights proportional to min(n_FOEN, n_Bavaria); individual case weights target_cell / n_region_cell.",
        "sensitivity_target": "Equal weights across common cells.",
        "balance": "Discrete total variation; continuous weighted means, SMD with fixed original-region pooled SD, and weighted KS. Training complete years count training years, not all observed unique complete years.",
        "inference": "Standardized estimates are descriptive point summaries. Original common-support and stratum summaries retain the original group bootstrap; standardization is not an equivalence or causal test.",
        "input_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "interpretation": "A regional coverage gap remains under common geometry weights. Policy common support discards most Bavaria cases and excludes its air-ridge stratum; gap attenuation cannot quantify a reconstructor explanation.",
        "n_bavaria": int(work.region.eq("gkd_bayern").sum()),
        "n_foen": int(work.region.eq("foen").sum()),
        "excluded": [
            "unmatched_gages is not an unregulated label",
            "peak_hidden uses withheld complete-year truth",
            "region and provider are confounded",
            "no credible flow or regulation subset is used",
        ],
    }
    (OUT / "region_identification_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(protocol.to_string(index=False), flush=True)
    print(strata.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
