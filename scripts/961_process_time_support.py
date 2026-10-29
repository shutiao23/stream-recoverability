#!/usr/bin/env python3
"""Same-count random and time-balanced retention controls for finite-record slopes.

The controls reuse saved annual predictions. They do not read withheld complete
H30 when choosing years. Complete-year truth is used only after the year set is
fixed, as an evaluation oracle.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from stream_recoverability.seeds import plain_seed, position_index

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
REF = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
OUT = ROOT / "results/wrr_process_revision_20261029"
PAPER = ROOT / "paper/wrr_tr"
SCHEMES = ("warm90", "random_same_count", "time_balanced", "all")
PAIR_INDEX = ["station_key", "replicate", "independence_group"]
BOOTSTRAP_SEED = 20261029
BOOTSTRAPS = 10_000


def slope(years, values):
    x = (np.asarray(years, float) - np.mean(years)) / 10
    return float(x @ np.asarray(values, float) / (x @ x))


def ols_weights(years):
    x = (np.asarray(years, float) - np.mean(years)) / 10
    return x / (x @ x)


def time_balanced(candidates: np.ndarray, k: int) -> np.ndarray:
    candidates = np.array(sorted(map(int, candidates)))
    if k >= len(candidates):
        return candidates
    if k <= 0:
        return np.array([], dtype=int)
    if k == 1:
        return candidates[[len(candidates) // 2]]
    chosen = [int(candidates[0]), int(candidates[-1])]
    remaining = [int(y) for y in candidates[1:-1]]
    while len(chosen) < k and remaining:
        best = None
        best_score = -np.inf
        for year in remaining:
            new = np.sort(np.append(chosen, year))
            score = float(np.diff(new).min())
            if score > best_score:
                best_score = score
                best = year
        chosen.append(best)
        remaining.remove(best)
    return np.array(sorted(chosen), dtype=int)


def load_truth():
    reference = pd.read_parquet(
        REF, columns=["station_key", "year", "design_family", "eval_truth_h30"]
    )
    if reference.groupby(["station_key", "year", "design_family"]).eval_truth_h30.nunique().max() != 1:
        raise RuntimeError("Reference truth is not unique")
    return {
        (family, station): g.drop_duplicates("year").set_index("year").eval_truth_h30.sort_index()
        for (family, station), g in reference.groupby(["design_family", "station_key"])
    }


def keep_random(complete, incomplete, k, seed):
    rng = np.random.default_rng(seed)
    incomplete = np.array(sorted(incomplete))
    if k >= len(incomplete):
        chosen = incomplete
    else:
        chosen = np.sort(rng.choice(incomplete, size=k, replace=False))
    return np.array(sorted(set(complete).union(chosen)), dtype=int)


def keep_balanced(complete, incomplete, k):
    chosen = time_balanced(np.asarray(incomplete), k)
    return np.array(sorted(set(complete).union(chosen)), dtype=int)


def summarize(cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (family, mode), group in cases.groupby(["family", "mode"]):
        row = {
            "family": family,
            "mode": mode,
            "n": len(group) // group.scheme.nunique(),
            "stations": int(group.station_key.nunique()),
            "groups": int(group.independence_group.nunique()),
        }
        for scheme, block in group.groupby("scheme"):
            row[f"{scheme}_n_years"] = float(block.n_years.mean())
            row[f"{scheme}_span"] = float(block.span.mean())
            row[f"{scheme}_hot_fraction"] = float(block.hot_fraction.mean())
            row[f"{scheme}_end_weight"] = float(block.end_weight.mean())
            row[f"{scheme}_estimate_rmse"] = float(np.sqrt(np.mean(block.estimate_error**2)))
            row[f"{scheme}_truth_rmse"] = float(np.sqrt(np.mean(block.truth_error**2)))
            row[f"{scheme}_reconstruction_rmse"] = float(np.sqrt(np.mean(block.reconstruction**2)))
        rows.append(row)
    return pd.DataFrame(rows)


def error_decomposition(cases: pd.DataFrame) -> pd.DataFrame:
    """Keep the signed cross term: the errors are not orthogonal components."""
    if not np.allclose(cases.estimate_error, cases.truth_error + cases.reconstruction, atol=1e-12):
        raise RuntimeError("E = S + R failed for a saved archive")
    rows = []
    for (family, mode, scheme), block in cases.groupby(["family", "mode", "scheme"]):
        e, s, r = (block[col].to_numpy(float) for col in ("estimate_error", "truth_error", "reconstruction"))
        mse_e, mse_s, mse_r = (float(np.mean(x**2)) for x in (e, s, r))
        cross = float(2 * np.mean(s * r))
        if not np.isclose(mse_e, mse_s + mse_r + cross, atol=1e-12):
            raise RuntimeError("MSE cross-term identity failed")
        rows.append(dict(family=family, mode=mode, scheme=scheme, n=len(block),
                         estimate_rmse=np.sqrt(mse_e), year_set_rmse=np.sqrt(mse_s),
                         reconstruction_rmse=np.sqrt(mse_r), estimate_mse=mse_e,
                         year_set_mse=mse_s, reconstruction_mse=mse_r,
                         twice_cross_term=cross, identity_residual=mse_e-mse_s-mse_r-cross,
                         max_case_identity_error=float(np.max(np.abs(e-s-r))),
                         n_years=float(block.n_years.mean()), span=float(block.span.mean()),
                         end_weight=float(block.end_weight.mean())))
    return pd.DataFrame(rows)


def paired_cluster_bootstrap(cases: pd.DataFrame, n_bootstraps=BOOTSTRAPS, seed=BOOTSTRAP_SEED) -> pd.DataFrame:
    """Resample connected groups, retaining every paired station-replicate row.

    Each draw gives all archives in the sampled group its draw multiplicity.
    The statistic remains an archive-weighted RMSE, not an equal-group RMSE.
    Percentile intervals describe this cohort; they are not equivalence tests.
    """
    paired = cases.pivot(index=PAIR_INDEX, columns="scheme", values=["estimate_error", "truth_error"])
    if paired.isna().any().any() or set(paired.estimate_error.columns) != set(SCHEMES):
        raise RuntimeError("Bootstrap requires exactly four paired schemes per archive")
    group = paired.index.get_level_values("independence_group")
    groups = np.array(sorted(set(group)))
    ns = np.array([(group == g).sum() for g in groups])
    rng = np.random.default_rng(seed)
    multiplicity = rng.multinomial(len(groups), np.full(len(groups), 1/len(groups)), size=n_bootstraps)
    denominator = multiplicity @ ns
    rows = []
    for field in ("estimate_error", "truth_error"):
        ss = {scheme: np.array([np.sum(paired[field][scheme].to_numpy()[group == g]**2)
                               for g in groups]) for scheme in SCHEMES}
        for scheme in SCHEMES[1:]:
            delta = (np.sqrt((multiplicity @ ss[scheme])/denominator)
                     - np.sqrt((multiplicity @ ss["warm90"])/denominator))
            rows.append(dict(field=field, contrast=scheme + " minus warm90", n=len(paired),
                             groups=len(groups), rmse_difference=float(np.sqrt(paired[field][scheme].pow(2).mean())
                                                                       - np.sqrt(paired[field].warm90.pow(2).mean())),
                             cluster_percentile_low=float(np.quantile(delta, .025)),
                             cluster_percentile_high=float(np.quantile(delta, .975)),
                             bootstraps=n_bootstraps, seed=seed))
    return pd.DataFrame(rows)


def choice_opportunity(cases: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    paired = cases.pivot(index=PAIR_INDEX, columns="scheme", values="n_incomplete_kept")
    choice = (paired.warm90 > 0) & (paired.warm90 < paired["all"])
    rows = []
    for label, selected in [("all_archives", np.ones(len(paired), dtype=bool)),
                            ("nontrivial_year_choice", choice.to_numpy()),
                            ("identical_by_construction", (~choice).to_numpy())]:
        keys = paired.index[selected]
        block = cases.set_index(PAIR_INDEX).loc[keys].reset_index()
        for scheme, part in block.groupby("scheme"):
            rows.append(dict(subset=label, scheme=scheme, n=len(part),
                             estimate_rmse=float(np.sqrt(np.mean(part.estimate_error**2))),
                             year_set_rmse=float(np.sqrt(np.mean(part.truth_error**2))),
                             reconstruction_rmse=float(np.sqrt(np.mean(part.reconstruction**2)))))
    counts = pd.DataFrame([dict(n=len(paired), no_incomplete_kept=int(paired.warm90.eq(0).sum()),
                               all_incomplete_kept=int(paired.warm90.eq(paired["all"]).sum()),
                               identical_by_construction=int((~choice).sum()),
                               nontrivial_year_choice=int(choice.sum()))])
    return pd.DataFrame(rows), counts


def write_tex(summary, decomposition, paired, choices, counts, audit):
    """Independent inputs; the 2026-10-28 review snapshot remains unchanged."""
    def forward(frame):
        return frame.loc[frame.family.eq("crossed") & frame["mode"].eq("forward")]

    s = forward(summary).iloc[0]
    d = forward(decomposition).set_index("scheme")
    p = forward(paired).loc[lambda x: x.field.eq("estimate_error")].set_index("contrast")
    c = forward(counts).iloc[0]
    choice = forward(choices).loc[lambda x: x.subset.eq("nontrivial_year_choice")].set_index("scheme")
    rejected = forward(audit).loc[lambda x: x.original_common & ~x.included]
    names = {"warm90": "Warm-season 90\\%", "random_same_count": "Same-count random",
             "time_balanced": "Same-count time-balanced", "all": "All supported years"}
    macros = {"PTRTimeN": int(s.n), "PTRTimeGroups": int(s.groups),
              "PTRTimeOriginalN": int(s.n + len(rejected)), "PTRTimeIdenticalN": int(c.identical_by_construction),
              "PTRTimeChoiceN": int(c.nontrivial_year_choice), "PTRTimeNoneKeptN": int(c.no_incomplete_kept),
              "PTRTimeAllKeptN": int(c.all_incomplete_kept),
              "PTRTimeIdenticalPercent": f"{100*c.identical_by_construction/c.n:.1f}"}
    for scheme, prefix in [("warm90", "Warm"), ("random_same_count", "Random"),
                           ("time_balanced", "Balanced"), ("all", "All")]:
        macros[f"PTRTime{prefix}RMSE"] = f"{d.loc[scheme].estimate_rmse:.4f}"
        macros[f"PTRTime{prefix}ChoiceRMSE"] = f"{choice.loc[scheme].estimate_rmse:.4f}"
    (PAPER / "process_time_revision_values.tex").write_text(
        "\n".join("\\newcommand{\\" + name + "}{" + str(value) + "}" for name, value in macros.items()) + "\n")
    lines = [r"\begin{table}[t]\centering\small",
             r"\caption{Finite-record H30 slope RMSE ($^{\circ}$C per decade) on \PTRTimeN{} forward controlled-gap archives with actual masked years. All schemes are paired. The all-supported-year oracle year-set error is zero by target definition; its estimated error remains a substantive comparison.}",
             r"\label{tab:time-support-legacy-weak}", r"\begin{tabular}{lrrrrr}\toprule",
             r"Retention & Years & Estimate & Year-set & Reconstruction & Span (years) \\\midrule"]
    for scheme in SCHEMES:
        row = d.loc[scheme]
        lines.append(f"{names[scheme]} & {row.n_years:.2f} & {row.estimate_rmse:.4f} & {row.year_set_rmse:.4f} & {row.reconstruction_rmse:.4f} & {row.span:.2f} " + r"\\")
    lines += [r"\bottomrule\end{tabular}", r"\end{table}"]
    (PAPER / "process_time_revision_table.tex").write_text("\n".join(lines) + "\n")
    lines = [r"\subsection{Paired time-support diagnostics}",
             r"These exploratory comparisons use one reproducible random subset per station--replicate archive, shared by the retained analysis. They do not average over all random year selections. The time-balanced heuristic spreads only the added incomplete years; it does not optimize their placement jointly with the fixed complete years. Its mean span changes only from "
             + f"{d.loc['warm90'].span:.3f} to {d.loc['time_balanced'].span:.3f} years. "
             + r"Thus year count and time position or slope leverage remain inseparable.",
             r"The following 95\% percentile intervals resample the 17 connected groups 10,000 times with seed 20261029, carrying every paired station--replicate archive with its group. Each statistic weights archives equally, including repeated masks. These intervals describe the present cohort and do not establish equivalence.",
             r"\begin{table}[t]\centering\small\caption{Paired estimated-slope RMSE contrasts, comparator minus warm-season screen ($^{\circ}$C per decade).}\label{tab:time-paired-revision}",
             r"\begin{tabular}{lrr}\toprule Comparator & Difference & 95\% group-resampling interval \\\midrule"]
    for scheme in SCHEMES[1:]:
        row = p.loc[scheme + " minus warm90"]
        lines.append(f"{names[scheme]} & {row.rmse_difference:+.4f} & [{row.cluster_percentile_low:+.4f}, {row.cluster_percentile_high:+.4f}] " + r"\\")
    lines += [r"\bottomrule\end{tabular}\end{table}",
              f"The same-count rules are identical by construction in {int(c.identical_by_construction)}/{int(c.n)} archives "
              + f"({100*c.identical_by_construction/c.n:.1f}\\%): {int(c.no_incomplete_kept)} retain no incomplete year and {int(c.all_incomplete_kept)} retain every incomplete year. "
              + f"Only {int(c.nontrivial_year_choice)} archives offer a choice between different same-sized subsets. "
              + "Their estimated RMSEs are " + ", ".join(f"{choice.loc[scheme].estimate_rmse:.4f} ({names[scheme]})" for scheme in SCHEMES[:3])
              + r" $^{\circ}$C per decade. Similar overall point estimates therefore partly reflect identical selections.",
              r"For each archive, $S$ is the complete-year slope on the selected set minus the full finite-record slope, $R$ is the estimated slope minus the complete-year slope on that selected set, and $E=S+R$. Consequently,",
              r"\[\operatorname{MSE}(E)=\operatorname{MSE}(S)+\operatorname{MSE}(R)+2\operatorname{mean}(SR).\]",
              r"For the same-count random control, the numerical identity is $"
              + f"{d.loc['random_same_count'].estimate_mse:.6f}={d.loc['random_same_count'].year_set_mse:.6f}+{d.loc['random_same_count'].reconstruction_mse:.6f}{d.loc['random_same_count'].twice_cross_term:+.6f}"
              + r"$. The negative cross term shows error cancellation; RMSE differences and normalized squared terms are not independent causal contributions.",
              r"\paragraph{Relationship to the 807-archive core comparison.} Two of the original common archives have no masked year and empty annual-prediction schemas: Bavaria station 10081004, replicate 6 (14 complete years), and station 11405000, replicate 14 (7 complete years). Their design masks are empty and saved warm-season and all-year slope errors are both zero. The prior diagnostic skipped them because the empty prediction files contain neither a year nor a D2 column. The present 805-archive diagnostic explicitly retains that actual-mask scope; this is not a reconstruction failure. A saved 807-archive sensitivity restores their zero errors to every scheme. The remaining 13 of the 820 forward archives lack an available warm-season comparison and are outside both common denominators."]
    (PAPER / "process_time_revision_supporting.tex").write_text("\n\n".join(lines) + "\n")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lookup = load_truth()
    trends = pd.read_csv(BASE / "trends.csv")
    trends = trends.loc[
        trends.estimator.eq("D2")
        & trends.dependence.eq("point")
        & trends["mode"].isin(["forward", "offline"])
        & trends.family.isin(["calendar", "crossed"])
    ]
    stations = position_index(trends.station_key.unique())
    rows = []
    audit_rows = []
    for (family, mode, station, replicate), group in trends.groupby(
        ["family", "mode", "station_key", "replicate"]
    ):
        saved = group.set_index("retention")
        original_common = bool(saved.loc[["all", "warm90"], "available"].all())
        audit = dict(family=family, mode=mode, station_key=station, replicate=int(replicate),
                     independence_group=group.independence_group.iloc[0], original_common=original_common,
                     included=False, reason="warm90_or_all_unavailable",
                     n_years=int(group.n_years.iloc[0]), n_incomplete=int(group.n_incomplete.iloc[0]),
                     design_mask_years=np.nan, prediction_schema="", saved_warm90_error=saved.loc["warm90", "error"],
                     saved_all_error=saved.loc["all", "error"])
        audit_rows.append(audit)
        if not original_common:
            continue
        folder = BASE / family / mode / f"replicate_{replicate:02d}" / station.replace("|", "_")
        predictions = folder / "annual_predictions.parquet"
        design = json.loads((folder / "design.json").read_text())
        audit["design_mask_years"] = len(design["masks"])
        if not predictions.is_file():
            audit["reason"] = "annual_predictions_missing"
            continue
        try:
            schema = set(pq.read_schema(predictions).names)
        except OSError:
            audit["reason"] = "annual_predictions_unreadable"
            continue
        audit["prediction_schema"] = ";".join(sorted(schema))
        if "year" not in schema or "D2" not in schema:
            audit["reason"] = ("no_mask_empty_prediction_schema" if not design["masks"]
                               else "annual_predictions_columns_missing")
            continue
        ref = lookup[family, station]
        if mode == "forward":
            ref = ref.loc[ref.index >= 2010]
        years = ref.index.to_numpy(int)
        truth = ref.to_numpy(float)
        missing = np.isin(years, [int(y) for y in design["masks"]])
        predicted = (
            pd.read_parquet(
                folder / "annual_predictions.parquet",
                columns=["year", "warm_observed_fraction", "D2"],
            )
            .set_index("year")
            .reindex(years)
        )
        point = truth.copy()
        point[missing] = predicted.D2.to_numpy()[missing]
        warm_keep = ~missing | predicted.warm_observed_fraction.ge(0.9).to_numpy()
        hot = truth > np.quantile(truth, 0.9)
        if int(warm_keep.sum()) != int(saved.loc["warm90", "n_retained"]):
            raise RuntimeError("Warm-season count does not match the saved trend file")
        if not np.isfinite(point[missing]).all():
            audit["reason"] = "nonfinite_prediction_for_masked_year"
            continue
        complete = years[~missing]
        incomplete = years[missing]
        k = int((warm_keep & missing).sum())
        station_index = stations[station]
        random_years = keep_random(
            complete, incomplete, k, plain_seed(961, station_index, int(replicate), 1)
        )
        balanced_years = keep_balanced(complete, incomplete, k)
        schemes = {
            "warm90": years[warm_keep],
            "random_same_count": random_years,
            "time_balanced": balanced_years,
            "all": years,
        }
        if warm_keep.sum() < 5:
            audit["reason"] = "fewer_than_five_retained_years"
            continue
        audit["included"] = True
        audit["reason"] = "included_actual_mask_archive"
        full = slope(years, truth)
        for name, keep_years in schemes.items():
            keep = np.isin(years, keep_years)
            if keep.sum() < 5 or not np.isfinite(point[keep]).all():
                continue
            weights = ols_weights(years[keep])
            ends = keep_years.min(), keep_years.max()
            end_weight = float(np.abs(weights[np.isin(years[keep], ends)]).sum())
            rows.append(
                dict(
                    family=family,
                    mode=mode,
                    station_key=station,
                    replicate=int(replicate),
                    independence_group=group.independence_group.iloc[0],
                    region=group.region.iloc[0],
                    scheme=name,
                    n_years=int(keep.sum()),
                    n_incomplete_kept=int((keep & missing).sum()),
                    n_candidate_incomplete=int(missing.sum()),
                    retained_years=";".join(map(str, keep_years)),
                    span=int(keep_years.max() - keep_years.min()),
                    hot_fraction=float(hot[keep].mean()) if hot.any() else np.nan,
                    end_weight=end_weight,
                    estimate_error=slope(years[keep], point[keep]) - full,
                    truth_error=slope(years[keep], truth[keep]) - full,
                    reconstruction=slope(years[keep], point[keep]) - slope(years[keep], truth[keep]),
                )
            )
    cases = pd.DataFrame(rows)
    paired_sizes = cases.groupby(["family", "mode", "station_key", "replicate"]).scheme.nunique()
    if not paired_sizes.eq(len(SCHEMES)).all():
        raise RuntimeError("Every included archive must have all four schemes")
    cases.to_csv(OUT / "time_support_cases.csv", index=False)
    audit = pd.DataFrame(audit_rows)
    audit.to_csv(OUT / "time_support_archive_audit.csv", index=False)
    summary = summarize(cases)
    summary.to_csv(OUT / "time_support_summary.csv", index=False)
    decomposition = error_decomposition(cases)
    decomposition.to_csv(OUT / "time_support_error_decomposition.csv", index=False)
    paired_frames, choice_frames, count_frames = [], [], []
    for (family, mode), block in cases.groupby(["family", "mode"]):
        paired_frames.append(paired_cluster_bootstrap(block).assign(family=family, mode=mode))
        choice, count = choice_opportunity(block)
        choice_frames.append(choice.assign(family=family, mode=mode))
        count_frames.append(count.assign(family=family, mode=mode))
    paired = pd.concat(paired_frames, ignore_index=True)
    choices = pd.concat(choice_frames, ignore_index=True)
    counts = pd.concat(count_frames, ignore_index=True)
    paired.to_csv(OUT / "time_support_paired_cluster.csv", index=False)
    choices.to_csv(OUT / "time_support_choice_opportunity.csv", index=False)
    counts.to_csv(OUT / "time_support_design_counts.csv", index=False)
    zero_masks = audit.loc[audit.original_common & ~audit.included & audit.reason.eq("no_mask_empty_prediction_schema")]
    sensitivity_rows = []
    for row in decomposition.to_dict("records"):
        zeros = zero_masks.loc[zero_masks.family.eq(row["family"]) & zero_masks["mode"].eq(row["mode"])]
        if len(zeros) and not (zeros.saved_all_error.eq(0) & zeros.saved_warm90_error.eq(0)).all():
            raise RuntimeError("No-mask sensitivity must have verified zero saved errors")
        n, total = row["n"], row["n"] + len(zeros)
        sensitivity_rows.append(dict(family=row["family"], mode=row["mode"], scheme=row["scheme"],
                                     n=total, n_restored_zero_mask=len(zeros),
                                     estimate_rmse=row["estimate_rmse"]*np.sqrt(n/total),
                                     year_set_rmse=row["year_set_rmse"]*np.sqrt(n/total),
                                     reconstruction_rmse=row["reconstruction_rmse"]*np.sqrt(n/total)))
    pd.DataFrame(sensitivity_rows).to_csv(OUT / "time_support_zero_mask_sensitivity.csv", index=False)
    write_tex(summary, decomposition, paired, choices, counts, audit)
    print(summary.to_string(index=False), flush=True)
    (OUT / "time_support_report.json").write_text(
        json.dumps(
            {
                "scope": "Saved D2 whole-archive predictions; random and balanced rules use year and availability only.",
                "n_rows": int(len(cases)),
                "random_selection": "One deterministic random subset per archive; plain_seed(961, station_position, replicate, 1). No repeated-random-selection inference.",
                "time_balanced": "Greedy spread of selected incomplete years only; fixed complete years are not included in the optimization.",
                "cluster_resampling": {"draws": BOOTSTRAPS, "seed": BOOTSTRAP_SEED,
                                       "unit": "connected group; paired archive rows and their original row weights are preserved"},
                "error_identity": "E=S+R; MSE(E)=MSE(S)+MSE(R)+2 mean(SR). Signed cross terms are reported, not attributed causally.",
                "primary_scope": "Actual-mask archives among original all/warm90 common cases; zero-mask empty schemas are audited and restored in a separate sensitivity.",
                "limits": [
                    "Finite complete-record slope, not a climate-process trend",
                    "Random and balanced schemes are diagnostics, not proposed archive rules",
                    "Hot-year labels use complete-year truth after selection",
                    "Similar point estimates do not establish equivalence",
                    "Year count and time position or leverage are not separately identified",
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
