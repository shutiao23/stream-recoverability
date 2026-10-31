#!/usr/bin/env python3
"""Build the formal post-review extensions requested by the Stanford-style review.

The script reads only saved annual predictions and reference outcomes. It does
not refit a daily or annual model, download data or alter a prior frozen result.
It writes a new, self-describing result directory plus LaTeX macros and tables.

The empirical-calendar family is a simulated-mask extension, not validation on
genuinely unknown gaps. The iid linear variance benchmark is a working model,
not a coverage guarantee or a causal attribution of a percentage of error.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
REF = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
LEGACY = ROOT / "results/wrr_process_revision_20261029/time_support_cases.csv"
OUT = ROOT / "results/wrr_final_revision_20261031"
PAPER = ROOT / "paper/wrr_tr"
KEY = ["station_key", "replicate", "independence_group"]
FAMILIES = ["crossed", "calendar"]
SCHEMES = ["warm90", "uniform_exact", "cdf_all_years", "sxx_all_years", "all"]
SCHEME_LABELS = {
    "warm90": "Warm-season",
    "uniform_exact": "Uniform exact",
    "cdf_all_years": "CDF",
    "sxx_all_years": "Sxx",
    "all": "All years",
}
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 20261031
EXPECTED = {
    "crossed": {"archives": 805, "choice": 468, "subsets": 5756},
    "calendar": {"archives": 818, "choice": 280, "subsets": 2646},
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def weights(years) -> np.ndarray:
    x = (np.asarray(years, float) - np.mean(years)) / 10
    return x / np.dot(x, x)


def geometry(years, selected):
    selected = np.asarray(selected, int)
    grid = np.arange(years.min(), years.max() + 1)
    cdf = float(np.mean(((selected[:, None] <= grid).mean(axis=0) - (years[:, None] <= grid).mean(axis=0)) ** 2))
    sxx = float(np.sum((selected - selected.mean()) ** 2) / 100)
    return cdf, sxx


def paired_interval(frame: pd.DataFrame, name: str, baseline: str = "warm90") -> dict:
    wide = frame.pivot(index=KEY, columns="scheme", values="estimate_mse")[[baseline, name]].dropna()
    labels = wide.index.get_level_values("independence_group")
    groups = sorted(set(labels))
    counts = np.array([(labels == g).sum() for g in groups])
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    multiplicity = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)), size=BOOTSTRAP_DRAWS)
    sums = {scheme: np.array([wide.loc[labels == g, scheme].sum() for g in groups]) for scheme in [baseline, name]}
    change = np.sqrt(multiplicity @ sums[name] / (multiplicity @ counts)) - np.sqrt(multiplicity @ sums[baseline] / (multiplicity @ counts))
    return {
        "n": len(wide),
        "stations": wide.index.get_level_values("station_key").nunique(),
        "groups": len(groups),
        "contrast": name + " minus " + baseline,
        "rmse_difference": float(np.sqrt(wide[name].mean()) - np.sqrt(wide[baseline].mean())),
        "ci_low": float(np.quantile(change, 0.025)),
        "ci_high": float(np.quantile(change, 0.975)),
        "seed": BOOTSTRAP_SEED,
        "bootstraps": BOOTSTRAP_DRAWS,
    }


def load_reference(keep: set[tuple[str, str]]) -> dict:
    """Load the compact reference table when the original case table is absent.

    A full leave-one-year-out case parquet is local-only. The compact table
    written by this script contains only the station-year H30 values needed by
    the 41-station extension, so the packaged result can be recomputed without
    the restricted case-level file.
    """
    compact = OUT / "reference_truths.csv"
    if REF.is_file():
        reference = pd.read_parquet(REF, columns=["station_key", "year", "design_family", "eval_truth_h30"])
        reference = reference.loc[reference.year.ge(2010)].copy()
        if reference.groupby(["station_key", "year", "design_family"]).eval_truth_h30.nunique().max() != 1:
            raise RuntimeError("Reference H30 is not unique within station-year-family")
        reference = reference.drop_duplicates(["station_key", "year", "design_family"])
        reference = reference.rename(columns={"design_family": "family"})
        reference = reference[reference[["family", "station_key"]].apply(tuple, axis=1).isin(keep)]
    elif compact.is_file():
        reference = pd.read_csv(compact)
    else:
        raise RuntimeError("Neither the reference case table nor the compact reference table is available")
    required = {"family", "station_key", "year", "eval_truth_h30"}
    if not required.issubset(reference.columns):
        raise RuntimeError("Reference table fields changed")
    reference = reference[reference[["family", "station_key"]].apply(tuple, axis=1).isin(keep)]
    if reference.empty:
        raise RuntimeError("Reference table has no rows in the retained roster")
    return {
        (family, station): block.set_index("year").eval_truth_h30.sort_index()
        for (family, station), block in reference.groupby(["family", "station_key"])
    }


def reference_truth_table(reference: dict) -> pd.DataFrame:
    rows = []
    for (family, station), series in reference.items():
        for year, value in series.items():
            rows.append({"family": family, "station_key": station, "year": int(year), "eval_truth_h30": float(value)})
    return pd.DataFrame(rows).sort_values(["family", "station_key", "year"])


def reference_year_sets(trends: pd.DataFrame, reference: dict) -> pd.DataFrame:
    cohort = sorted(
        trends.loc[
            trends["mode"].eq("forward")
            & trends.family.eq("crossed")
            & trends.estimator.eq("D2")
            & trends.dependence.eq("point"),
            "station_key",
        ].unique()
    )
    rows = []
    for station in cohort:
        series = reference.get(("crossed", station))
        if series is None or not len(series):
            raise RuntimeError("Reference year set is empty: " + station)
        years = sorted(set(series.index.astype(int)))
        span = set(range(min(years), max(years) + 1))
        internal = sorted(span - set(years))
        rows.append(
            {
                "station_key": station,
                "n_reference_years": len(years),
                "first_year": years[0],
                "last_year": years[-1],
                "internal_gap_years": ";".join(map(str, internal)),
                "n_internal_gap_years": len(internal),
                "reference_years": ";".join(map(str, years)),
            }
        )
    return pd.DataFrame(rows).sort_values("station_key")


def retention_geometry(reference: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    legacy = pd.read_csv(LEGACY)
    legacy = legacy.loc[legacy["mode"].eq("forward")]
    rows, accounting = [], []
    design_rows, prediction_rows = {}, {}
    input_digest = hashlib.sha256()
    max_identity_error = 0.0
    design_compact_path = OUT / "case_designs.csv"
    prediction_compact_path = OUT / "annual_predictions_compact.csv"
    design_compact, prediction_compact = {}, {}
    if design_compact_path.is_file():
        compact = pd.read_csv(design_compact_path)
        for row in compact.itertuples(index=False):
            design_compact[(row.family, row.station_key, int(row.replicate))] = {
                "n_years": int(row.n_years),
                "masks": json.loads(row.masks),
            }
            design_rows[(row.family, row.station_key, int(row.replicate))] = {
                "family": row.family,
                "station_key": row.station_key,
                "replicate": int(row.replicate),
                "n_years": int(row.n_years),
                "masks": json.dumps(json.loads(row.masks), sort_keys=True),
            }
    if prediction_compact_path.is_file():
        compact = pd.read_csv(prediction_compact_path)
        for key, block in compact.groupby(["family", "station_key", "replicate"]):
            prediction_compact[(key[0], key[1], int(key[2]))] = block
            for row in block.itertuples(index=False):
                prediction_rows[(row.family, row.station_key, int(row.replicate), int(row.year))] = {
                    "family": row.family,
                    "station_key": row.station_key,
                    "replicate": int(row.replicate),
                    "year": int(row.year),
                    "D2": float(row.D2),
                    "warm_observed_fraction": float(row.warm_observed_fraction),
                }
    compact_digest_done = False
    for family in FAMILIES:
        roster = legacy.loc[legacy.family.eq(family) & legacy.scheme.eq("warm90")].sort_values(KEY)
        for case in roster.itertuples(index=False):
            folder = BASE / family / "forward" / f"replicate_{case.replicate:02d}" / case.station_key.replace("|", "_")
            design_path = folder / "design.json"
            prediction_path = folder / "annual_predictions.parquet"
            case_key = (family, case.station_key, int(case.replicate))
            if design_path.is_file() and prediction_path.is_file():
                for path in [design_path, prediction_path]:
                    input_digest.update(str(path.relative_to(ROOT)).encode() + hashlib.sha256(path.read_bytes()).digest())
                design = json.loads(design_path.read_text())
                prediction = pd.read_parquet(prediction_path)
                design_rows[case_key] = {"family": family, "station_key": case.station_key, "replicate": int(case.replicate),
                                         "n_years": int(design["n_years"]), "masks": json.dumps(design["masks"], sort_keys=True)}
                for row in prediction.itertuples(index=False):
                    prediction_rows[(family, case.station_key, int(case.replicate), int(row.year))] = {
                        "family": family, "station_key": case.station_key, "replicate": int(case.replicate),
                        "year": int(row.year), "D2": float(row.D2),
                        "warm_observed_fraction": float(row.warm_observed_fraction),
                    }
            else:
                if case_key not in design_compact or case_key not in prediction_compact:
                    raise RuntimeError("Neither full case inputs nor compact replay inputs are available: " + str(folder))
                design = design_compact[case_key]
                prediction = prediction_compact[case_key]
                if not compact_digest_done:
                    for path in [design_compact_path, prediction_compact_path]:
                        input_digest.update(str(path.relative_to(ROOT)).encode() + hashlib.sha256(path.read_bytes()).digest())
                    compact_digest_done = True
            ref = reference[family, case.station_key]
            years = ref.index.to_numpy(int)
            truth = ref.to_numpy(float)
            pred = prediction.set_index("year").reindex(years)
            missing = np.isin(years, list(map(int, design["masks"])))
            point = truth.copy()
            point[missing] = pred.D2.to_numpy(float)[missing]
            if not np.isfinite(point).all() or len(years) != design["n_years"]:
                raise RuntimeError("Annual prediction or reference roster changed: " + str(folder))
            warm = ~missing | pred.warm_observed_fraction.ge(0.9).to_numpy()
            if warm.sum() != case.n_years or missing.sum() != case.n_candidate_incomplete:
                raise RuntimeError("Warm-season roster or mask count changed: " + str(folder))
            complete = years[~missing]
            candidates = years[missing]
            k = int(np.sum(warm & missing))
            wfull = weights(years)
            beta = float(wfull @ truth)
            x = (years - years.mean()) / 10
            residual = truth - truth.mean() - beta * x
            sigma2 = float(np.sum(residual ** 2) / (len(years) - 2))
            ident = {
                "family": family,
                "station_key": case.station_key,
                "replicate": int(case.replicate),
                "independence_group": case.independence_group,
                "region": case.region,
            }
            options = []
            for chosen_incomplete in itertools.combinations(candidates, k):
                selected = np.sort(np.r_[complete, chosen_incomplete]).astype(int)
                cdf, sxx = geometry(years, selected)
                options.append({"chosen": tuple(chosen_incomplete), "selected": selected, "cdf": cdf, "sxx": sxx})
            expected_subsets = math.comb(len(candidates), k)
            if len(options) != expected_subsets:
                raise RuntimeError("Feasible subset enumerator changed")
            cdf_choice = min(options, key=lambda z: (round(z["cdf"], 14), -round(z["sxx"], 14), z["chosen"]))
            sxx_choice = min(options, key=lambda z: (-round(z["sxx"], 14), round(z["cdf"], 14), z["chosen"]))
            selections = {
                "warm90": years[warm],
                "cdf_all_years": cdf_choice["selected"],
                "sxx_all_years": sxx_choice["selected"],
                "all": years,
            }
            accounting.append(
                ident
                | {
                    "n_full": len(years),
                    "n_incomplete": len(candidates),
                    "k": k,
                    "n_subsets": len(options),
                    "choice": 0 < k < len(candidates),
                    "all_incomplete_kept": k == len(candidates),
                    "no_incomplete_kept": k == 0,
                }
            )

            def score(selected):
                nonlocal max_identity_error
                take = np.isin(years, selected)
                ws = np.zeros(len(years))
                ws[take] = weights(selected)
                difference = ws - wfull
                year_error = float(difference @ truth)
                reconstruction = float(ws @ (point - truth))
                estimate = float(ws @ point - beta)
                checks = [
                    abs(year_error - float(difference @ residual)),
                    abs(difference.sum()),
                    abs(float(difference @ x)),
                    abs(estimate - year_error - reconstruction),
                ]
                max_identity_error = max(max_identity_error, *checks)
                if max(checks) > 1e-10:
                    raise RuntimeError("OLS weight identity failed")
                selected_x = (years[take] - years[take].mean()) / 10
                g_formula = float(1 / np.dot(selected_x, selected_x) - 1 / np.dot(x, x))
                if abs(float(difference @ difference) - g_formula) > 1e-10:
                    raise RuntimeError("Sxx weight-distance formula failed")
                return {
                    "estimate_error": estimate,
                    "year_set_error": year_error,
                    "reconstruction_error": reconstruction,
                    "estimate_mse": estimate ** 2,
                    "year_set_mse": year_error ** 2,
                    "reconstruction_mse": reconstruction ** 2,
                    "cross_term": 2 * year_error * reconstruction,
                    "weight_distance_squared": float(difference @ difference),
                    "iid_linear_expected_year_set_mse": sigma2 * g_formula,
                    "reference_slope": beta,
                    "reference_residual_variance": sigma2,
                    "slope_sign_disagreement": int((estimate + beta) * beta < 0),
                    "retained_years": ";".join(map(str, selected)),
                    "n_retained": len(selected),
                }

            for scheme, selected in selections.items():
                scored = score(selected)
                if scheme == "warm90" and abs(scored["estimate_error"] - case.estimate_error) >= 1e-10:
                    raise RuntimeError("Warm-season reconstruction differs from the original saved case")
                rows.append(ident | {"scheme": scheme} | scored)
            sampled = [score(option["selected"]) for option in options]
            metrics = [
                "estimate_mse",
                "year_set_mse",
                "reconstruction_mse",
                "cross_term",
                "weight_distance_squared",
                "iid_linear_expected_year_set_mse",
                "slope_sign_disagreement",
            ]
            rows.append(
                ident
                | {"scheme": "uniform_exact", "n_retained": int(warm.sum()), "reference_slope": beta}
                | {name: float(np.mean([item[name] for item in sampled])) for name in metrics}
            )
    frame = pd.DataFrame(rows)
    account = pd.DataFrame(accounting)
    summaries = []
    for (family, scheme), block in frame.groupby(["family", "scheme"]):
        summaries.append(
            {
                "family": family,
                "scheme": scheme,
                "n": len(block),
                "stations": block.station_key.nunique(),
                "groups": block.independence_group.nunique(),
                "estimate_rmse": float(np.sqrt(block.estimate_mse.mean())),
                "year_set_rmse": float(np.sqrt(block.year_set_mse.mean())),
                "reconstruction_rmse": float(np.sqrt(block.reconstruction_mse.mean())),
                "iid_linear_working_year_set_rmse": float(np.sqrt(block.iid_linear_expected_year_set_mse.mean())),
                "cross_term": float(block.cross_term.mean()),
                "mean_years": float(block.n_retained.mean()),
                "sign_disagreement_count_or_expectation": float(block.slope_sign_disagreement.sum()),
            }
        )
    summary = pd.DataFrame(summaries)
    intervals = []
    for family, block in frame.groupby("family"):
        for scheme in ["cdf_all_years", "sxx_all_years", "uniform_exact", "all"]:
            intervals.append({"family": family, "scheme": scheme} | paired_interval(block, scheme))
    return frame, account, summary, pd.DataFrame(intervals), {
        "max_exact_weight_identity_error": max_identity_error,
        "annual_design_prediction_digest": input_digest.hexdigest(),
        "design_rows": list(design_rows.values()),
        "prediction_rows": list(prediction_rows.values()),
    }


def estimator_tradeoff(trends: pd.DataFrame):
    selected = trends.loc[
        trends["mode"].eq("forward") & trends.dependence.eq("point") & trends.retention.eq("all")
    ]
    availability, paired, unavailable = [], [], []
    for family, block in selected.groupby("family"):
        for method, part in block.groupby("estimator"):
            finite = part.loc[part.available & part.error.notna()]
            availability.append(
                {
                    "family": family,
                    "estimator": method,
                    "available": len(finite),
                    "total": len(part),
                    "available_rmse": float(np.sqrt(finite.squared_error.mean())),
                }
            )
        valid = block.loc[block.available & block.error.notna()]
        wide = valid.pivot(index=KEY, columns="estimator", values="error")
        for other in ["plug_in", "stochastic_calibrated"]:
            pair = wide[["D2", other]].dropna()
            case = pair.rename(columns={other: "comparator"}).reset_index().melt(
                id_vars=KEY, value_vars=["D2", "comparator"], var_name="scheme", value_name="error"
            )
            case["estimate_mse"] = case.error ** 2
            interval = paired_interval(case, "D2", baseline="comparator")
            paired.append(
                {
                    "family": family,
                    "comparator": other,
                    "D2_rmse": float(np.sqrt(pair.D2.pow(2).mean())),
                    "comparator_rmse": float(np.sqrt(pair[other].pow(2).mean())),
                }
                | interval
            )
        missing = wide.loc[wide.stochastic_calibrated.isna() & wide.D2.notna(), "D2"]
        unavailable.append(
            {
                "family": family,
                "classical_unavailable_D2_available": len(missing),
                "D2_rmse_on_that_subset": float(np.sqrt(missing.pow(2).mean())),
            }
        )
    return pd.DataFrame(availability), pd.DataFrame(paired), pd.DataFrame(unavailable)


def fmt(value, digits=4) -> str:
    return f"{float(value):.{digits}f}"


def macro_block(name: str, value: str) -> str:
    return "\\newcommand{\\" + name + "}{" + value + "}"


def write_values(summary, intervals, geometry, availability, paired, unavailable, refs, counts):
    macro = {}
    macro["SRReferenceStations"] = str(len(refs))
    macro["SRReferenceGapStations"] = str(int(refs.n_internal_gap_years.gt(0).sum()))
    macro["SRReferenceMinYears"] = str(int(refs.n_reference_years.min()))
    for family, tag in [("crossed", "Crossed"), ("calendar", "Calendar")]:
        macro[f"SR{tag}ChoiceN"] = str(int(counts.loc[family].choice))
        macro[f"SR{tag}AllKeptN"] = str(int(counts.loc[family].all_kept))
        macro[f"SR{tag}NoneKeptN"] = str(int(counts.loc[family].none_kept))
        for scheme, name in [("warm90", "Warm"), ("cdf_all_years", "CDF"),
                             ("sxx_all_years", "Sxx"), ("all", "All")]:
            macro[f"SR{tag}Sign{name}"] = str(int(summary.loc[
                summary.family.eq(family) & summary.scheme.eq(scheme),
                "sign_disagreement_count_or_expectation",
            ].iloc[0]))
    by = summary.set_index(["family", "scheme"])
    for family in FAMILIES:
        tag = "Calendar" if family == "calendar" else "Crossed"
        for scheme in SCHEMES:
            name = {
                "warm90": "Warm",
                "uniform_exact": "Uniform",
                "cdf_all_years": "CDF",
                "sxx_all_years": "Sxx",
                "all": "All",
            }[scheme]
            row = by.loc[family, scheme]
            macro[f"SR{tag}{name}RMSE"] = fmt(row.estimate_rmse)
            macro[f"SR{tag}{name}TruthRMSE"] = fmt(row.year_set_rmse)
            macro[f"SR{tag}{name}ReconRMSE"] = fmt(row.reconstruction_rmse)
            macro[f"SR{tag}{name}WorkingRMSE"] = fmt(row.iid_linear_working_year_set_rmse)
        contrast = intervals.loc[intervals.family.eq(family)].set_index("scheme")
        for scheme, name in [("cdf_all_years", "CDF"), ("sxx_all_years", "Sxx"), ("all", "All")]:
            row = contrast.loc[scheme]
            macro[f"SR{tag}{name}Difference"] = fmt(row.rmse_difference)
            macro[f"SR{tag}{name}Low"] = fmt(row.ci_low)
            macro[f"SR{tag}{name}High"] = fmt(row.ci_high)
    # Geometry working-model comparison, warm season and Sxx only.
    for family, tag in [("crossed", "Crossed"), ("calendar", "Calendar")]:
        for scheme, name in [("warm90", "Warm"), ("sxx_all_years", "Sxx")]:
            macro[f"SR{tag}{name}GeometryActual"] = fmt(by.loc[family, scheme].year_set_rmse)
            macro[f"SR{tag}{name}GeometryWorking"] = fmt(by.loc[family, scheme].iid_linear_working_year_set_rmse)
    avail = availability.set_index(["family", "estimator"])
    macro["SRAvailDTwoCrossed"] = f"{int(avail.loc['crossed','D2'].available)}/{int(avail.loc['crossed','D2'].total)}"
    macro["SRAvailDTwoCalendar"] = f"{int(avail.loc['calendar','D2'].available)}/{int(avail.loc['calendar','D2'].total)}"
    macro["SRAvailClassicCrossed"] = f"{int(avail.loc['crossed','stochastic_calibrated'].available)}/{int(avail.loc['crossed','stochastic_calibrated'].total)}"
    macro["SRAvailClassicCalendar"] = f"{int(avail.loc['calendar','stochastic_calibrated'].available)}/{int(avail.loc['calendar','stochastic_calibrated'].total)}"
    macro["SRAvailCrossedMissingN"] = str(int(unavailable.set_index("family").loc["crossed"].classical_unavailable_D2_available))
    macro["SRAvailCalendarMissingN"] = str(int(unavailable.set_index("family").loc["calendar"].classical_unavailable_D2_available))
    macro["SRAvailCrossedMissingRMSE"] = fmt(unavailable.set_index("family").loc["crossed"].D2_rmse_on_that_subset)
    macro["SRAvailCalendarMissingRMSE"] = fmt(unavailable.set_index("family").loc["calendar"].D2_rmse_on_that_subset)
    comp = paired.loc[paired.comparator.eq("stochastic_calibrated")].set_index("family")
    for family, tag in [("crossed", "Crossed"), ("calendar", "Calendar")]:
        macro[f"SR{tag}DTwoRMSE"] = fmt(comp.loc[family].D2_rmse)
        macro[f"SR{tag}ClassicRMSE"] = fmt(comp.loc[family].comparator_rmse)
        macro[f"SR{tag}PairN"] = str(int(comp.loc[family].n))
        macro[f"SR{tag}PairLow"] = fmt(comp.loc[family].ci_low)
        macro[f"SR{tag}PairHigh"] = fmt(comp.loc[family].ci_high)
    lines = ["% Generated by scripts/981_stanford_revision.py"] + [macro_block(name, value) for name, value in macro.items()]
    (PAPER / "stanford_revision_values.tex").write_text("\n".join(lines) + "\n")
    return macro


def write_calendar_table(summary, intervals):
    lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Post-review calendar-position extension on saved annual predictions. Control-gap and empirical-calendar families are reported separately; their rows are not a common cohort and their differences must not be subtracted to name a missingness mechanism. Warm-season is the original 90\% warm-season rule; the legacy one-draw random and incomplete-year-only spacing controls are not repeated here. Uniform exact averages squared errors over every feasible same-count set within each archive, then takes the cohort root. CDF and $S_{xx}$ use calendar years only and keep every fixed complete year. Intervals resample the 17 connected groups 10,000 times; they are conditional on the saved predictions and the rules compared.}",
        r"\label{tab:calendar-family}",
        r"\resizebox{\ifdim\width>\textwidth\textwidth\else\width\fi}{!}{%",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Gap family / rule & Archives & Est. RMSE & Year-set RMSE & Reconst. RMSE & $\Delta$ RMSE [95\% interval] \\",
        r"\midrule",
    ]
    by = summary.set_index(["family", "scheme"])
    contrast = intervals.set_index(["family", "scheme"])
    for family, label in [("crossed", "Controlled 30--90 day"), ("calendar", "Empirical calendar")]:
        lines.append(r"\multicolumn{6}{l}{\textit{" + label + f"; {int(by.loc[family,'warm90'].n)} actual-mask archives" + r"}} \\")
        for scheme in SCHEMES:
            row = by.loc[family, scheme]
            if scheme == "warm90":
                interval = "Reference"
            else:
                item = contrast.loc[family, scheme]
                interval = f"{fmt(item.rmse_difference)} [{fmt(item.ci_low)}, {fmt(item.ci_high)}]"
            lines.append(
                f"{SCHEME_LABELS[scheme]} & {int(row.n)} & {fmt(row.estimate_rmse)} & {fmt(row.year_set_rmse)} & {fmt(row.reconstruction_rmse)} & {interval} "
                + r"\\"
            )
        lines.append(r"\addlinespace")
    lines += [r"\bottomrule\end{tabular}}", r"\end{table}"]
    (PAPER / "stanford_calendar_table.tex").write_text("\n".join(lines) + "\n")


def write_geometry_table(summary):
    by = summary.set_index(["family", "scheme"])
    lines = [
        r"\begin{table}[t]\centering\small",
        r"\caption{Observed year-set RMSE and the iid linear-reference working benchmark, in $^{\circ}$C per decade. The benchmark uses each archive's complete-reference residual variance and the exact weight-distance formula. It is an assumption-dependent scale check, not a fitted hydrological model, a coverage guarantee or a decomposition of the observed error.}",
        r"\label{tab:retention-geometry}",
        r"\begin{tabular}{llrr}",
        r"\toprule",
        r"Gap family & Rule & Observed year-set RMSE & iid working benchmark \\",
        r"\midrule",
    ]
    for family, label in [("crossed", "Controlled 30--90 day"), ("calendar", "Empirical calendar")]:
        for scheme, rule in [("warm90", "Warm-season"), ("sxx_all_years", "$S_{xx}$")]:
            row = by.loc[family, scheme]
            lines.append(
                f"{label} & {rule} & {fmt(row.year_set_rmse)} & {fmt(row.iid_linear_working_year_set_rmse)} "
                + r"\\"
            )
        lines.append(r"\addlinespace")
    lines += [r"\bottomrule\end{tabular}", r"\end{table}"]
    (PAPER / "stanford_geometry_table.tex").write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--paper", type=Path, default=PAPER)
    args = parser.parse_args()
    out, paper = args.out, args.paper
    out.mkdir(parents=True, exist_ok=True)
    paper.mkdir(parents=True, exist_ok=True)

    compact_reference = OUT / "reference_truths.csv"
    reference_inputs = [REF] if REF.is_file() else [compact_reference]
    inputs = [LEGACY, BASE / "trends.csv", Path(__file__).resolve(), ROOT / "scripts/980_final_release.py", *reference_inputs]
    before = {str(path.relative_to(ROOT)): digest(path) for path in inputs}
    legacy = pd.read_csv(LEGACY)
    keep = set(zip(legacy.family, legacy.station_key))
    reference = load_reference(keep)
    trends = pd.read_csv(BASE / "trends.csv")
    refs = reference_year_sets(trends, reference)
    frame, account, summary, intervals, geometry_audit = retention_geometry(reference)
    design_compact = pd.DataFrame(geometry_audit.pop("design_rows")).sort_values(["family", "station_key", "replicate"])
    prediction_compact = pd.DataFrame(geometry_audit.pop("prediction_rows")).sort_values(
        ["family", "station_key", "replicate", "year"]
    )
    design_compact.to_csv(out / "case_designs.csv", index=False)
    prediction_compact.to_csv(out / "annual_predictions_compact.csv", index=False)
    availability, paired, unavailable = estimator_tradeoff(trends)

    # Exact denominator and numerical checks against the reviewed values.
    counts = account.groupby("family").agg(
        archives=("n_subsets", "size"),
        choice=("choice", "sum"),
        subsets=("n_subsets", "sum"),
        all_kept=("all_incomplete_kept", "sum"),
        none_kept=("no_incomplete_kept", "sum"),
    )
    for family, expected in EXPECTED.items():
        row = counts.loc[family]
        if (int(row.archives), int(row.choice), int(row.subsets)) != (
            expected["archives"], expected["choice"], expected["subsets"]
        ):
            raise RuntimeError(f"{family} denominator changed: {row.to_dict()}")
    if (int(counts.loc["calendar"].all_kept), int(counts.loc["calendar"].none_kept)) != (530, 8):
        raise RuntimeError("Calendar all/none-kept counts changed")
    if (int(counts.loc["crossed"].all_kept), int(counts.loc["crossed"].none_kept)) != (5, 332):
        raise RuntimeError("Controlled-gap all/none-kept counts changed")
    expected_summary = {
        ("calendar", "warm90"): 0.113597,
        ("calendar", "uniform_exact"): 0.135480,
        ("calendar", "cdf_all_years"): 0.098431,
        ("calendar", "sxx_all_years"): 0.085887,
        ("calendar", "all"): 0.067359,
        ("crossed", "warm90"): 0.445884,
        ("crossed", "uniform_exact"): 0.449225,
        ("crossed", "cdf_all_years"): 0.428370,
        ("crossed", "sxx_all_years"): 0.402260,
        ("crossed", "all"): 0.169685,
    }
    by = summary.set_index(["family", "scheme"]).estimate_rmse
    for key, value in expected_summary.items():
        if abs(float(by.loc[key]) - value) > 5e-7:
            raise RuntimeError(f"Summary RMSE changed at {key}: {float(by.loc[key])}")
    calendar_pair = intervals.loc[intervals.family.eq("calendar")].set_index("scheme")
    if not (calendar_pair.loc["cdf_all_years"].ci_low < 0 < calendar_pair.loc["cdf_all_years"].ci_high):
        raise RuntimeError("Calendar CDF interval no longer crosses zero")
    if calendar_pair.loc["sxx_all_years"].ci_high >= 0 or calendar_pair.loc["all"].ci_high >= 0:
        raise RuntimeError("Calendar Sxx or all-year interval lost its negative direction")
    if not (refs.n_internal_gap_years.gt(0).sum() == 24 and refs.n_reference_years.min() == 7 and len(refs) == 41):
        raise RuntimeError("Reference-year set counts changed")

    reference_truth_table(reference).to_csv(out / "reference_truths.csv", index=False)
    frame.to_csv(out / "retention_geometry_cases.csv", index=False)
    account.to_csv(out / "retention_choice_counts.csv", index=False)
    summary.to_csv(out / "retention_family_summary.csv", index=False)
    intervals.to_csv(out / "retention_paired_intervals.csv", index=False)
    refs.to_csv(out / "reference_year_sets.csv", index=False)
    availability.to_csv(out / "estimator_availability.csv", index=False)
    paired.to_csv(out / "estimator_paired_comparisons.csv", index=False)
    unavailable.to_csv(out / "estimator_unavailable_subset.csv", index=False)

    macros = write_values(summary, intervals, geometry_audit, availability, paired, unavailable, refs, counts)
    write_calendar_table(summary, intervals)
    write_geometry_table(summary)

    output_files = [
        "annual_predictions_compact.csv",
        "case_designs.csv",
        "reference_truths.csv",
        "retention_geometry_cases.csv",
        "retention_choice_counts.csv",
        "retention_family_summary.csv",
        "retention_paired_intervals.csv",
        "reference_year_sets.csv",
        "estimator_availability.csv",
        "estimator_paired_comparisons.csv",
        "estimator_unavailable_subset.csv",
        "data_manifest.json",
        "scope.json",
    ]
    manifest = {
        "schema": "stanford_revision_data_manifest_v1",
        "created_utc": pd.Timestamp.utcnow().isoformat(),
        "inputs": before,
        "outputs": {name: None for name in output_files},
        "paper_outputs": [
            "paper/wrr_tr/stanford_revision_values.tex",
            "paper/wrr_tr/stanford_calendar_table.tex",
            "paper/wrr_tr/stanford_geometry_table.tex",
        ],
        "reference_fallback": "results/wrr_final_revision_20261031/reference_truths.csv",
        "reference_fallback_scope": "Compact station-year H30 values for the 41-station extension; allows replay when the restricted leave-one-year-out case parquet is not packaged.",
        "compact_replay": {
            "files": ["reference_truths.csv", "case_designs.csv", "annual_predictions_compact.csv"],
            "numerical_tolerance": 1e-12,
            "note": "Re-running this script from an extracted package uses the compact CSV inputs. Values can differ at about 1e-14 from decimal roundoff; denominators and scientific conclusions are unchanged.",
        },
        "scope": "Saved annual predictions only; no model refit, no new data, no manuscript result was modified.",
    }
    for name in output_files:
        path = out / name
        if path.is_file():
            manifest["outputs"][name] = digest(path)
    for name in manifest["paper_outputs"]:
        path = ROOT / name
        manifest["outputs"][name] = digest(path)
    manifest["reference_fallback_sha256"] = digest(out / "reference_truths.csv")
    (out / "data_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    report = {
        "schema": "stanford_revision_scope_v1",
        "date": "2026-10-31 Asia/Shanghai",
        "exploratory": True,
        "new_models_fit": False,
        "existing_outputs_changed": False,
        "archives": int(len(account)),
        "geometry_rows": int(len(frame)),
        "family_counts": {family: {k: int(v) for k, v in counts.loc[family].items()} for family in FAMILIES},
        "reference_year_sets": {
            "stations": int(len(refs)),
            "internal_gap_stations": int(refs.n_internal_gap_years.gt(0).sum()),
            "minimum_years": int(refs.n_reference_years.min()),
        },
        "max_exact_weight_identity_error": geometry_audit["max_exact_weight_identity_error"],
        "bootstrap": {"draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, "unit": "connected group"},
        "sign_disagreement_counts": {
            family: {
                scheme: int(summary.loc[(summary.family.eq(family)) & (summary.scheme.eq(scheme)), "sign_disagreement_count_or_expectation"].iloc[0])
                for scheme in SCHEMES
            }
            for family in FAMILIES
        },
        "interpretation": [
            "The control-gap and empirical-calendar families are separate cohorts; their differences are not a causal missingness effect.",
            "Empirical calendars are simulated masks on saved predictions, not accuracy validation on genuinely unknown values.",
            "The iid linear variance formula is a working benchmark. Its residual variance contains real variability, curvature and observation error; it is not a noise decomposition.",
            "CDF calendar improvement is not stable enough to claim a proven rule; its interval includes zero. Sxx and all-year directions are stronger in this cohort.",
            "D2 accuracy on common cases and D2 point-estimate availability are different questions. Availability does not certify a releasable value.",
        ],
        "compact_replay": {
            "files": ["reference_truths.csv", "case_designs.csv", "annual_predictions_compact.csv"],
            "numerical_tolerance": 1e-12,
            "note": "Re-running this script from an extracted package uses the compact CSV inputs. Values can differ at about 1e-14 from decimal roundoff; denominators and scientific conclusions are unchanged.",
        },
        "input_sha256": before,
    }
    (out / "scope.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "completed", "out": str(out.relative_to(ROOT)), "macros": len(macros),
                      "geometry_rows": len(frame), "archives": len(account)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
