#!/usr/bin/env python3
"""Independent exhaustive audit of the new year-set and same-day-gap experiment.

Does not import 969 or any analysis-generator functions. Reopens the original
annual references, annual predictions, mask designs and daily observations;
uses itertools, integer calendar counts and direct numpy polynomial fits.
Writes only time_gap_independent_audit.json in the new experiment directory.
"""
from __future__ import annotations

import calendar
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_experiments_20261029"
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
REFERENCE = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
ELIGIBLE = ROOT / "results/wrr_review_response_20261027/rules/eligible_station_years.csv"
DAILY = ROOT / "scratch/wrr_target_recovery_20261021/archive_daily.parquet"
KEY = ["station_key", "replicate", "independence_group"]
FIELDS = ["estimate_mse", "year_set_mse", "reconstruction_mse", "cross_term", "cdf_distance", "sxx", "span", "mean_year", "end_abs_weight", "max_abs_weight"]


class AuditFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AuditFailure(message)


def same(a, b, message, atol=1e-9):
    if not np.allclose(a, b, rtol=0, atol=atol, equal_nan=True):
        error = float(np.nanmax(abs(np.asarray(a, float) - np.asarray(b, float))))
        raise AuditFailure(f"{message}; maximum absolute difference={error}")


def years_from_string(value):
    if value is None or pd.isna(value) or str(value) == "":
        return tuple()
    return tuple(map(int, str(value).split(";")))


def direct_fit(years, outcomes):
    return float(np.polyfit(np.asarray(years, float), np.asarray(outcomes, float), 1)[0] * 10)


def geometry(selected, full):
    """Integer ECDF counts and exact rational Sxx, with all complete years."""
    m, n = len(selected), len(full)
    numerators = [sum(year <= grid for year in selected) * n - sum(year <= grid for year in full) * m
                  for grid in range(min(full), max(full) + 1)]
    cdf = Fraction(sum(value * value for value in numerators), (max(full) - min(full) + 1) * m * m * n * n)
    sxx = Fraction(m * sum(year * year for year in selected) - sum(selected) ** 2, 100 * m)
    x = (np.asarray(selected, float) - np.mean(selected)) / 10
    leverage = x / float(sxx)
    return dict(cdf_distance=float(cdf), sxx=float(sxx), span=max(selected) - min(selected),
                mean_year=float(np.mean(selected)), end_abs_weight=float(abs(leverage[0]) + abs(leverage[-1])),
                max_abs_weight=float(abs(leverage).max()))


def score(full, truth, point, selected):
    keep = np.isin(full, selected)
    target = direct_fit(full, truth)
    selected_truth = direct_fit(np.asarray(full)[keep], np.asarray(truth)[keep])
    reconstructed = direct_fit(np.asarray(full)[keep], np.asarray(point)[keep])
    e, s, r = reconstructed - target, selected_truth - target, reconstructed - selected_truth
    return dict(estimate_error=e, year_set_error=s, reconstruction_error=r,
                estimate_mse=e * e, year_set_mse=s * s, reconstruction_mse=r * r,
                cross_term=2 * s * r, **geometry(tuple(selected), tuple(full)))


def raw_annual_audit():
    reference = pd.read_parquet(REFERENCE, columns=["station_key", "year", "design_family", "eval_truth_h30"])
    reference = reference.loc[reference.design_family.eq("crossed") & reference.year.ge(2010)]
    truth_by_station = {station: part.drop_duplicates("year").set_index("year").eval_truth_h30.sort_index()
                        for station, part in reference.groupby("station_key")}
    trends = pd.read_csv(BASE / "trends.csv")
    trends = trends.loc[trends.family.eq("crossed") & trends["mode"].eq("forward") & trends.estimator.eq("D2") & trends.dependence.eq("point")]
    old = pd.read_csv(ROOT / "results/wrr_process_revision_20261029/time_support_cases.csv")
    old = old.loc[old.family.eq("crossed") & old["mode"].eq("forward")].set_index(KEY + ["scheme"])
    accounting = pd.read_parquet(OUT / "time_archive_accounting.parquet").set_index(KEY)
    saved_subsets = pd.read_parquet(OUT / "time_all_feasible_subsets.parquet").set_index(KEY + ["subset_id"])
    saved_fixed = pd.read_parquet(OUT / "time_fixed_geometry_selections.parquet").set_index(KEY + ["scheme"])
    saved_expected = pd.read_parquet(OUT / "time_exact_random_expectations.parquet").set_index(KEY)
    saved_draws = pd.read_parquet(OUT / "time_random_selection_draws.parquet").set_index(KEY + ["draw_seed"])
    independent_rows, expected_rows, archive_rows, draw_rows = [], [], [], []
    excluded, year_rosters = [], {}
    tie_counts = {"cdf_primary_ties": 0, "sxx_primary_ties": 0}
    annual_input_digest = hashlib.sha256()
    for (station, replicate), part in trends.groupby(["station_key", "replicate"], sort=True):
        folder = BASE / "crossed/forward" / f"replicate_{replicate:02d}" / station.replace("|", "_")
        design = json.loads((folder / "design.json").read_text())
        for original_path in [folder / "design.json", folder / "annual_predictions.parquet"]:
            annual_input_digest.update(str(original_path.relative_to(ROOT)).encode())
            annual_input_digest.update(hashlib.sha256(original_path.read_bytes()).digest())
        group = design["independence_group"]
        key = (station, int(replicate), group)
        stored = accounting.loc[key]
        series = truth_by_station[station]
        full = series.index.to_numpy(int)
        truth = series.to_numpy(float)
        masks = set(map(int, design["masks"]))
        incomplete = tuple(int(year) for year in full if year in masks)
        complete = tuple(int(year) for year in full if year not in masks)
        point = truth.copy()
        retained = set(complete)
        if incomplete:
            predictions = pd.read_parquet(folder / "annual_predictions.parquet", columns=["year", "D2", "warm_observed_fraction"]).set_index("year")
            for index, year in enumerate(full):
                if year in masks:
                    point[index] = predictions.loc[year].D2
                    if predictions.loc[year].warm_observed_fraction >= .9:
                        retained.add(int(year))
        require(np.isfinite(point).all(), "Raw annual point is nonfinite")
        k = len(retained) - len(complete)
        saved = part.set_index("retention")
        common = bool(saved.loc["all"].available and saved.loc["warm90"].available)
        require(common == bool(stored.original_common) and bool(incomplete) == bool(stored.actual_mask), "Raw common/actual-mask archive classification differs")
        require(years_from_string(stored.complete_years) == complete and years_from_string(stored.candidate_incomplete_years) == incomplete,
                "Raw fixed complete/incomplete year roster differs")
        require(k == stored.k and len(retained) == stored.n_warm and len(full) == stored.n_full, "Raw warm-season year-count accounting differs")
        identity = dict(station_key=station, replicate=int(replicate), independence_group=group, region=design["region"])
        all_score = score(full, truth, point, tuple(full))
        same(all_score["estimate_error"], saved.loc["all"].error, "Raw all-year slope differs")
        archive_rows.append(identity | dict(original_common=common, primary=common and bool(incomplete),
                                             nontrivial_choice=common and 0 < k < len(incomplete), all_estimate_mse=all_score["estimate_mse"]))
        year_rosters[station] = (group, tuple(full))
        if not common:
            require(len(retained) < 5 and not saved.loc["warm90"].available, "Excluded archive has a usable warm-season comparison")
            excluded.append(identity | dict(n_warm=len(retained)))
            continue
        options = []
        for subset_id, chosen in enumerate(itertools.combinations(incomplete, k)):
            selected = tuple(sorted(complete + chosen))
            actual = score(full, truth, point, selected)
            expected_key = key + (subset_id,)
            saved_row = saved_subsets.loc[expected_key]
            require(years_from_string(saved_row.retained_years) == selected and years_from_string(saved_row.chosen_incomplete_years) == chosen,
                    "Feasible subset enumeration or lexicographic subset ID differs")
            same([actual[field] for field in FIELDS], saved_row[FIELDS].to_numpy(float), "Independently fitted subset metrics differ")
            same([actual[field] for field in ["estimate_error", "year_set_error", "reconstruction_error"]],
                 saved_row[["estimate_error", "year_set_error", "reconstruction_error"]].to_numpy(float), "Direct subset error decomposition differs")
            options.append(dict(subset_id=subset_id, chosen=chosen, selected=selected, **actual))
        require(len(options) == math.comb(len(incomplete), k), "The full same-count combination set is not exhaustive")
        probabilities = saved_subsets.loc[key].uniform_subset_probability.to_numpy(float)
        same(probabilities, 1 / len(options), "Feasible subsets do not have equal conditional probabilities", atol=1e-14)
        same(probabilities.sum(), 1, "Conditional subset probabilities do not sum to one", atol=1e-12)
        cdf_objective = [(round(row["cdf_distance"], 14), -round(row["sxx"], 14), row["chosen"]) for row in options]
        sxx_objective = [(-round(row["sxx"], 14), round(row["cdf_distance"], 14), row["chosen"]) for row in options]
        cdf_index = min(range(len(options)), key=cdf_objective.__getitem__)
        sxx_index = min(range(len(options)), key=sxx_objective.__getitem__)
        tie_counts["cdf_primary_ties"] += int(sum(value[0] == min(item[0] for item in cdf_objective) for value in cdf_objective) > 1)
        tie_counts["sxx_primary_ties"] += int(sum(value[0] == min(item[0] for item in sxx_objective) for value in sxx_objective) > 1)
        retained_lookup = {row["selected"]: row["subset_id"] for row in options}
        indices = {"warm90": retained_lookup[tuple(sorted(retained))], "cdf_all_years": cdf_index, "sxx_all_years": sxx_index}
        for name, old_name in [("legacy_random", "random_same_count"), ("legacy_time_balanced", "time_balanced")]:
            indices[name] = retained_lookup[years_from_string(old.loc[key + (old_name,)].retained_years)] if incomplete else 0
        for name, selected_index in indices.items():
            chosen = options[selected_index]
            row = saved_fixed.loc[key + (name,)]
            require(years_from_string(row.retained_years) == chosen["selected"], "Outcome-blind fixed selection or tie-break differs: " + name)
            flagged = saved_subsets.loc[key]
            require(int(flagged[name + "_selected"].sum()) == 1 and bool(flagged.loc[selected_index, name + "_selected"]), "Subset selection flags disagree with independent optimum")
            independent_rows.append(identity | dict(scheme=name) | {field: chosen[field] for field in FIELDS})
        independent_rows.append(identity | dict(scheme="all") | {field: all_score[field] for field in FIELDS})
        mean = {field: float(np.mean([row[field] for row in options])) for field in FIELDS}
        same([mean[field] for field in FIELDS], saved_expected.loc[key, FIELDS].to_numpy(float), "Within-archive uniform-subset expectations differ")
        expected_rows.append(identity | dict(scheme="uniform_random_expected") | mean)
        token = hashlib.sha256(station.encode()).digest()
        words = [int.from_bytes(token[start:start + 4], "little") for start in range(0, 16, 4)]
        for seed in range(200):
            sequence = np.random.SeedSequence([969, int(replicate), seed, *words])
            index = int(np.random.Generator(np.random.PCG64(sequence)).integers(len(options)))
            chosen = options[index]
            row = saved_draws.loc[key + (seed,)]
            require(int(row.subset_id) == index, "Random year-subset seed mapping differs")
            same([chosen[field] for field in FIELDS[:4]], row[FIELDS[:4]].to_numpy(float), "Random subset draw scores differ")
            draw_rows.append(identity | dict(draw_seed=seed, estimate_mse=chosen["estimate_mse"]))
    archive = pd.DataFrame(archive_rows).set_index(KEY).sort_index()
    scores = pd.DataFrame(independent_rows + expected_rows)
    draws = pd.DataFrame(draw_rows)
    require((len(archive), int(archive.original_common.sum()), int(archive.primary.sum()), int(archive.nontrivial_choice.sum()), len(saved_subsets), len(saved_draws)) ==
            (820, 807, 805, 468, 5758, 807 * 200), "Exhaustive enumeration/denominator counts differ")
    require(len(excluded) == 13, "Exactly thirteen unavailable warm-season cases must be excluded")
    return archive, scores, draws, year_rosters, dict(passed=True, raw_archives=820, original_common=807, actual_mask_common=805,
        nontrivial_choice=468, independently_fitted_feasible_sets=5758, random_seed_archive_rows_checked=len(draws),
        exclusions=excluded, optimizer_ties=tie_counts, original_design_prediction_set_sha256=annual_input_digest.hexdigest(),
        geometry_scope="CDF and Sxx use calendar years, including every fixed complete year; rational integer-count geometry and direct polyfit use no temperature outcome in selection.")


def aggregation_audit(archive, scores, draws):
    summary = pd.read_csv(OUT / "time_sensitivity_summary.csv").set_index(["scope", "weighting", "scheme"])
    variation = pd.read_csv(OUT / "time_random_selection_variation.csv").set_index(["scope", "weighting"])
    cluster = pd.read_csv(OUT / "time_sensitivity_paired_cluster.csv").set_index(["scope", "weighting", "scheme", "field"])
    seed_summary = pd.read_csv(OUT / "time_random_seed_summary.csv").set_index(["scope", "weighting", "draw_seed"])
    checks, bootstrap_checks, primary = 0, 0, []
    primary_random_estimands = {}
    for scope, selected_mask in [("actual_mask_common", archive.primary), ("choice_only", archive.nontrivial_choice), ("original_common", archive.original_common)]:
        roster = archive.loc[selected_mask].copy()
        keys = roster.index
        group_labels = keys.get_level_values("independence_group").to_numpy()
        group_names = sorted(set(group_labels))
        for weighting in ("equal_archive", "equal_station", "equal_group"):
            if weighting == "equal_archive":
                w = np.ones(len(roster))
            else:
                field = "station_key" if weighting == "equal_station" else "independence_group"
                labels = keys.get_level_values(field)
                counts = pd.Series(labels).value_counts()
                w = np.array([1 / counts[label] for label in labels])
            schemes = sorted(scores.scheme.unique())
            matrices = {}
            for field in FIELDS:
                matrices[field] = np.column_stack([scores.loc[scores.scheme.eq(scheme)].set_index(KEY).reindex(keys)[field].to_numpy(float) for scheme in schemes])
            for position, scheme in enumerate(schemes):
                row = summary.loc[(scope, weighting, scheme)]
                same([np.average(matrices[field][:, position], weights=w) for field in FIELDS if field != "mean_year"],
                     row[[field for field in FIELDS if field != "mean_year"]].to_numpy(float), "Independent aggregate scheme summary differs")
                same([np.sqrt(np.average(matrices[field][:, position], weights=w)) for field in FIELDS[:3]],
                     row[["estimate_rmse", "year_set_rmse", "reconstruction_rmse"]].to_numpy(float), "Root of expected MSE is misreported")
                checks += 1
            exact_position = schemes.index("uniform_random_expected")
            exact_root = float(np.sqrt(np.average(matrices["estimate_mse"][:, exact_position], weights=w)))
            seed_mse = []
            draw_matrix = draws.pivot(index=KEY, columns="draw_seed", values="estimate_mse").reindex(keys).to_numpy(float)
            for seed in range(200):
                value = float(np.average(draw_matrix[:, seed], weights=w))
                same(value, seed_summary.loc[(scope, weighting, seed)].estimate_mse, "Independent cohort random-seed MSE differs")
                seed_mse.append(value)
            seed_mse = np.asarray(seed_mse)
            row = variation.loc[(scope, weighting)]
            same([exact_root, np.sqrt(seed_mse).mean(), np.sqrt(seed_mse.mean()), np.quantile(np.sqrt(seed_mse), .025), np.quantile(np.sqrt(seed_mse), .975)],
                 row[["exact_sqrt_expected_mse", "mean_draw_rmse", "sqrt_mean_draw_mse", "selection_percentile_low", "selection_percentile_high"]].to_numpy(float), "Expected MSE, mean realized RMSE and root of realized mean MSE are conflated")
            require(np.sqrt(seed_mse).mean() <= np.sqrt(seed_mse.mean()) + 1e-12, "Jensen inequality for realized random RMSE fails")
            if scope == "actual_mask_common" and weighting == "equal_archive":
                primary_random_estimands = dict(exact_sqrt_expected_mse=exact_root,
                                               mean_realized_rmse=float(np.sqrt(seed_mse).mean()),
                                               sqrt_mean_realized_mse=float(np.sqrt(seed_mse.mean())),
                                               conditional_selection_percentiles=np.quantile(np.sqrt(seed_mse), [.025, .975]).tolist())
            # Reproduce the declared group multiplicities, then explicitly
            # expand paired archive rows. This avoids 969's group-sum formula.
            rng = np.random.default_rng(2026102969)
            multiplicities = rng.multinomial(len(group_names), np.ones(len(group_names)) / len(group_names), size=10000)
            members = [np.flatnonzero(group_labels == group) for group in group_names]
            boot = {field: np.empty((10000, len(schemes))) for field in ("estimate_mse", "year_set_mse")}
            for draw, counts in enumerate(multiplicities):
                expanded = np.concatenate([np.tile(index, count) for index, count in zip(members, counts) if count])
                for field in boot:
                    boot[field][draw] = np.sqrt(np.average(matrices[field][expanded], axis=0, weights=w[expanded]))
            warm = schemes.index("warm90")
            for field in boot:
                for position, scheme in enumerate(schemes):
                    if scheme == "warm90":
                        continue
                    delta = boot[field][:, position] - boot[field][:, warm]
                    row = cluster.loc[(scope, weighting, scheme, field)]
                    low, high = np.quantile(delta, [.025, .975])
                    point = np.sqrt(np.average(matrices[field][:, position], weights=w)) - np.sqrt(np.average(matrices[field][:, warm], weights=w))
                    same([point, low, high], row[["rmse_difference", "group_percentile_low", "group_percentile_high"]].to_numpy(float), "Explicit paired-group bootstrap interval differs")
                    bootstrap_checks += 1
                    if scope == "actual_mask_common" and weighting == "equal_archive" and field == "estimate_mse":
                        primary.append(dict(scheme=scheme, difference=float(point), low=float(low), high=float(high)))
    return dict(passed=True, weighted_scheme_summaries=checks, independently_expanded_group_interval_checks=bootstrap_checks,
                primary_cluster_groups=17, resamples_per_scope_weighting=10000, paired_bootstrap_seed=2026102969,
                random_realizations=200, primary_intervals=primary, primary_random_estimands=primary_random_estimands,
                interpretation="Uniform expectations first average squared errors within each archive. sqrt(E[MSE]), mean realized RMSE and sqrt(mean realized MSE) are separately recomputed. Group resampling carries all paired archive rows and original scope weights.")


def longest_run(days):
    best = current = 0
    previous = -2
    for day in sorted(days):
        current = current + 1 if day == previous + 1 else 1
        best, previous = max(best, current), day
    return best


def missing_span_days(spec, n_days):
    result = set()
    for part in str(spec).split(";"):
        if part:
            start, length = map(int, part.split(":"))
            require(start >= 0 and length > 0 and start + length <= n_days, "Trial missingness is outside its calendar year")
            result.update(range(start, start + length))
    return result


def gap_audit(year_rosters):
    eligible = pd.read_csv(ELIGIBLE)
    eligible = eligible.loc[eligible.station_key.isin(year_rosters) & eligible.year.between(1981, 2025)]
    require(not eligible.duplicated(["station_key", "year"]).any(), "Observed peer station-year is duplicated")
    daily = pd.read_parquet(DAILY, columns=["station_key", "date", "water_c"], filters=[("station_key", "in", sorted(year_rosters))])
    daily["date"] = pd.to_datetime(daily.date)
    require(not daily.duplicated(["station_key", "date"]).any(), "Raw station-day is duplicated")
    finite = daily.loc[np.isfinite(daily.water_c)]
    present = {station: set(block.date) for station, block in finite.groupby("station_key", observed=True)}
    peers = {}
    def add(source, replicate, group, year, station, missing):
        peers.setdefault((source, replicate, group, year), []).append((station, missing))
    for row in eligible.itertuples(index=False):
        dates = list(pd.date_range(f"{row.year}-01-01", f"{row.year}-12-31"))
        absent = {position for position, date in enumerate(dates) if date not in present[row.station_key]}
        require(longest_run(absent) == row.longest_run and bool(not absent) == row.complete_year, "Observed daily sets do not reproduce eligible-year missingness")
        add("observed", 0, row.independence_group, int(row.year), row.station_key, absent)
    design_digest = hashlib.sha256()
    for family in ("calendar", "crossed"):
        for path in sorted((BASE / family / "forward").glob("replicate_*/*/design.json")):
            design = json.loads(path.read_text())
            design_digest.update(str(path.relative_to(ROOT)).encode())
            design_digest.update(hashlib.sha256(path.read_bytes()).digest())
            station = design["station_key"]
            for year in year_rosters[station][1]:
                n_days = 366 if calendar.isleap(year) else 365
                absent = missing_span_days(design["masks"].get(str(year), ""), n_days)
                add(family, int(design["replicate"]), design["independence_group"], year, station, absent)
    saved = pd.read_csv(OUT / "gap_overlap_station_year_cases.csv").set_index(["source", "replicate", "independence_group", "year", "station_key"])
    records = []
    for key, members in peers.items():
        for position, (station, missing) in enumerate(members):
            if not missing:
                continue
            others = [other_missing for other_position, (_, other_missing) in enumerate(members) if other_position != position]
            union = set().union(*others) if others else set()
            shared_days = len(missing & union)
            identity = key + (station,)
            actual = dict(source=key[0], replicate=key[1], independence_group=key[2], year=key[3], station_key=station,
                          longest_run=longest_run(missing), missing_days=len(missing), peer_evaluable=bool(others),
                          evaluable_peer_stations=len(others), same_year_missing_peer=any(bool(other) for other in others),
                          same_day_missing_peer_days=shared_days, any_same_day_missing_peer=bool(shared_days))
            row = saved.loc[identity]
            for field in ("longest_run", "missing_days", "peer_evaluable", "evaluable_peer_stations", "same_year_missing_peer", "same_day_missing_peer_days", "any_same_day_missing_peer"):
                require(actual[field] == row[field], "Independent daily peer-set calculation differs: " + field)
            records.append(actual)
    require(len(records) == len(saved) == 220 + 3806 + 3777, "Incomplete station-year peer accounting changed")
    frame = pd.DataFrame(records)
    summary = pd.read_csv(OUT / "gap_overlap_summary.csv").set_index(["source", "period"])
    output = []
    for source, block in frame.groupby("source"):
        periods = [("2010-2025", block.loc[block.year.ge(2010)])]
        if source == "observed":
            periods.append(("1981-2025", block))
        for period, part in periods:
            peer = part.loc[part.peer_evaluable]
            row = summary.loc[(source, period)]
            same([len(part), len(peer), len(part) - len(peer), peer.missing_days.sum(), peer.same_day_missing_peer_days.sum(),
                  peer.any_same_day_missing_peer.mean(), part.longest_run.median(), part.longest_run.ge(30).mean()],
                 row[["n_incomplete_rows", "n_peer_evaluable_incomplete_rows", "n_no_evaluable_peer_excluded", "peer_evaluable_missing_station_days",
                      "shared_missing_station_days", "same_day_overlap_fraction_peer_evaluable", "median_annual_longest", "share_annual_ge30"]].to_numpy(float),
                 "Independent daily missingness denominator/summary differs")
            output.append(dict(source=source, period=period, incomplete_rows=len(part), peer_evaluable_rows=len(peer),
                               no_evaluable_peer_excluded=len(part) - len(peer), overlapping_incomplete_rows=int(peer.any_same_day_missing_peer.sum()),
                               missing_station_days=int(peer.missing_days.sum()), shared_missing_station_days=int(peer.same_day_missing_peer_days.sum())))
    observed = next(row for row in output if row["source"] == "observed" and row["period"] == "2010-2025")
    require((observed["incomplete_rows"], observed["peer_evaluable_rows"], observed["missing_station_days"], observed["shared_missing_station_days"]) == (109, 74, 2086, 40),
            "Primary observed same-day overlap denominator differs")
    return dict(passed=True, independently_checked_incomplete_rows=len(records), raw_trial_design_set_sha256=design_digest.hexdigest(),
                summaries=output, denominator="Only group-years with another evaluable station enter peer rates; single-station group-years remain explicitly excluded rather than coded false.",
                scope="Date-set overlap describes co-missingness and does not identify common causes or availability of the donors actually selected by a reconstructor.")


def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    report_path = OUT / "time_gap_independent_audit.json"
    try:
        archive, scores, draws, rosters, annual = raw_annual_audit()
        aggregate = aggregation_audit(archive, scores, draws)
        gaps = gap_audit(rosters)
        paths = [REFERENCE, ELIGIBLE, DAILY, BASE / "trends.csv", ROOT / "results/wrr_process_revision_20261029/time_support_cases.csv"]
        audited = ["time_all_feasible_subsets.parquet", "time_archive_accounting.parquet", "time_exact_random_expectations.parquet",
                   "time_fixed_geometry_selections.parquet", "time_random_selection_draws.parquet", "time_sensitivity_summary.csv",
                   "time_sensitivity_paired_cluster.csv", "time_random_selection_variation.csv", "time_random_seed_summary.csv", "gap_overlap_station_year_cases.csv", "gap_overlap_summary.csv"]
        report = dict(status="passed", script="scripts/974_independent_time_gap_audit.py", independent=True,
                      method="No 969 imports; itertools exhaustive sets, rational calendar geometry, direct numpy polyfit, explicit expanded paired-group resamples and pairwise daily missing-date unions.",
                      annual_enumeration=annual, aggregate_and_paired_inference=aggregate, same_day_gaps=gaps,
                      raw_input_sha256={str(path.relative_to(ROOT)): hash_file(path) for path in paths},
                      audited_result_sha256={str((OUT / name).relative_to(ROOT)): hash_file(OUT / name) for name in audited})
    except Exception as error:
        report = dict(status="failed", script="scripts/974_independent_time_gap_audit.py", error=str(error).replace(str(ROOT), "{workspace}"))
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        raise
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(dict(status="passed", report=str(report_path.relative_to(ROOT)), feasible_subsets=5758,
                          independently_expanded_interval_checks=aggregate["independently_expanded_group_interval_checks"],
                          daily_gap_rows=gaps["independently_checked_incomplete_rows"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
