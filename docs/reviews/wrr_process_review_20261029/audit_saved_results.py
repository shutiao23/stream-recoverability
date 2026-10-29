#!/usr/bin/env python3
"""Independent descriptive peer-review checks. Does not refit or alter manuscript results.

Cell standardization and cluster bootstrap below are reviewer diagnostics, not
new confirmatory tests or causal estimates. All original input files stay intact.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "results/wrr_process_review_20261029"
OLD = ROOT / "results/wrr_process_review_20261028"
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
CASE = ROOT / "results/wrr_adversarial_review_20261027/failure_strata/failure_strata_cases.parquet"
SEED = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"
OUT.mkdir(parents=True, exist_ok=True)


def save(frame, name):
    frame.to_csv(OUT / name, index=False)
    print(name, frame.shape, flush=True)


raw = pd.read_parquet(CASE)
traj = pd.read_csv(OLD / "trajectory_nested_cases.csv")
wide = traj.pivot(index=["station_key", "year"], columns="count", values=["q05", "q50", "q95", "coverage90", "width90"])
deltas = wide.index.to_frame(index=False)
for field in ["q05", "q50", "q95", "coverage90", "width90"]:
    deltas[field + "_change"] = (wide[field][500] - wide[field][20]).to_numpy()
deltas = deltas.merge(traj.loc[traj["count"].eq(20), ["station_key", "year", "region", "independence_group"]], validate="one_to_one")
deltas = deltas.merge(raw.loc[raw.replicate.eq(0), ["station_key", "year", "policy_choice", "peak_hidden"]], on=["station_key", "year"], validate="one_to_one", how="left")
assert deltas.policy_choice.notna().all()
save(deltas, "trajectory_case_deltas.csv")
rows = []
for label, part in [("all", deltas), *list(deltas.groupby("region")), *list(deltas.groupby("policy_choice"))]:
    for q in ["q05", "q50", "q95"]:
        v = part[q + "_change"].abs()
        rows.append(dict(stratum=label, quantile=q, n=len(v), groups=part.independence_group.nunique(), median=v.median(), mean=v.mean(), p90=v.quantile(.90), p95=v.quantile(.95), maximum=v.max(), n_over_005=int((v > .05).sum())))
save(pd.DataFrame(rows), "trajectory_tail_summary.csv")

regional = raw.loc[raw.region.isin(["foen", "gkd_bayern"])].copy()
regional["year_bin"] = pd.cut(regional.year, [2009, 2014, 2019, 2026], labels=["2010-2014", "2015-2019", "2020-2025"])
regional["cover"] = ((regional.D2_q05 - 1e-8 <= regional.reference_h30) & (regional.reference_h30 <= regional.D2_q95 + 1e-8)).astype(float)
rows = []
cell_rows = []
keys = ["gap_bin", "overlap_bin", "year_bin", "donor_bin"]
for name, fields in [("geometry", keys), ("geometry_plus_policy", keys + ["policy_choice"])]:
    reg = regional.copy()
    reg["cell"] = reg[fields].astype(str).agg("|".join, axis=1)
    ns = reg.groupby(["cell", "region"]).size().unstack(fill_value=0)
    common = ns.loc[(ns.foen > 0) & (ns.gkd_bayern > 0)]
    means = reg.groupby(["cell", "region"]).cover.mean().unstack().loc[common.index]
    pa = common.foen / common.foen.sum()
    pb = common.gkd_bayern / common.gkd_bayern.sum()
    tv = .5 * np.abs(pa - pb).sum()
    overlap = common.min(axis=1); overlap = overlap / overlap.sum()
    equal = pd.Series(1 / len(common), index=common.index)
    for weight_name, weight in [("raw_region_weights", None), ("common_min_count_weights", overlap), ("equal_common_cell_weights", equal)]:
        fa = float((means.foen * (pa if weight is None else weight)).sum())
        ba = float((means.gkd_bayern * (pb if weight is None else weight)).sum())
        rows.append(dict(match=name, weighting=weight_name, n_cells=len(common), foen_n=int(common.foen.sum()), bavaria_n=int(common.gkd_bayern.sum()), common_cell_total_variation=float(tv), foen_coverage=fa, bavaria_coverage=ba, foen_minus_bavaria_pp=100*(fa-ba)))
    for cell in common.index:
        cell_rows.append(dict(match=name, cell=cell, foen_n=int(common.loc[cell, "foen"]), bavaria_n=int(common.loc[cell, "gkd_bayern"]), foen_share=pa[cell], bavaria_share=pb[cell], min_count_weight=overlap[cell], foen_coverage=means.loc[cell,"foen"], bavaria_coverage=means.loc[cell,"gkd_bayern"]))
save(pd.DataFrame(rows), "regional_standardization_diagnostic.csv")
save(pd.DataFrame(cell_rows), "regional_common_cells.csv")

time = pd.read_csv(OLD / "time_support_cases.csv")
time = time.loc[time.family.eq("crossed") & time["mode"].eq("forward")].copy()
assert np.allclose(time.estimate_error, time.truth_error + time.reconstruction, atol=1e-12)
rows = []
for scheme, p in time.groupby("scheme"):
    rows.append(dict(scheme=scheme, n=len(p), estimate_rmse=np.sqrt(np.mean(p.estimate_error**2)), year_set_rmse=np.sqrt(np.mean(p.truth_error**2)), reconstruction_rmse=np.sqrt(np.mean(p.reconstruction**2)), estimate_mse=np.mean(p.estimate_error**2), year_set_mse=np.mean(p.truth_error**2), reconstruction_mse=np.mean(p.reconstruction**2), twice_cross_term=2*np.mean(p.truth_error*p.reconstruction), n_years=p.n_years.mean(), span=p.span.mean(), end_weight=p.end_weight.mean()))
save(pd.DataFrame(rows), "time_error_decomposition.csv")
index = ["station_key", "replicate", "independence_group"]
tw = time.pivot(index=index, columns="scheme", values=["estimate_error", "truth_error"])
assert len(tw) == 805 and tw.notna().all().all()
group = tw.index.get_level_values("independence_group")
groups = np.array(sorted(set(group)))
ns = np.array([(group == g).sum() for g in groups])
rng = np.random.default_rng(20261029)
multiplicity = rng.multinomial(len(groups), np.full(len(groups), 1/len(groups)), size=10000)
denom = multiplicity @ ns
rows = []
for field in ["estimate_error", "truth_error"]:
    ss = {s: np.array([np.sum(tw[field][s].to_numpy()[group == g]**2) for g in groups]) for s in tw[field].columns}
    for s in ["random_same_count", "time_balanced", "all"]:
        diff = np.sqrt((multiplicity @ ss[s])/denom) - np.sqrt((multiplicity @ ss["warm90"])/denom)
        rows.append(dict(field=field, contrast=s+" minus warm90", n=len(tw), groups=len(groups), rmse_difference=np.sqrt(tw[field][s].pow(2).mean())-np.sqrt(tw[field]["warm90"].pow(2).mean()), cluster_percentile_low=np.quantile(diff,.025), cluster_percentile_high=np.quantile(diff,.975), bootstraps=len(diff)))
save(pd.DataFrame(rows), "time_paired_cluster_diagnostic.csv")
kw = time.pivot(index=index, columns="scheme", values="n_incomplete_kept")
nontrivial = (kw.warm90 > 0) & (kw.warm90 < kw["all"])
rows = []
for label, selected in [("all_archives", np.ones(len(tw), dtype=bool)), ("nontrivial_year_choice", nontrivial.to_numpy()), ("identical_by_construction", (~nontrivial).to_numpy())]:
    for s in tw.estimate_error.columns:
        rows.append(dict(subset=label, scheme=s, n=int(selected.sum()), estimate_rmse=np.sqrt(tw.estimate_error[s].loc[selected].pow(2).mean()), year_set_rmse=np.sqrt(tw.truth_error[s].loc[selected].pow(2).mean())))
save(pd.DataFrame(rows), "time_choice_opportunity.csv")

seed = pd.read_parquet(SEED, columns=["station_key", "year", "region", "independence_group", "n_complete_years", "eval_truth_h30", "air_h30_target_year"])
trends = pd.read_csv(BASE / "trends.csv", usecols=["station_key", "mode"])
keys = set(trends.station_key)
forward_keys = set(trends.loc[trends["mode"].eq("forward"), "station_key"])
air = seed.loc[seed.station_key.isin(keys) & seed.region.isin(["foen", "gkd_bayern"])].drop_duplicates(["station_key", "year"]).dropna(subset=["eval_truth_h30", "air_h30_target_year"])
rows = []
for region, part in air.groupby("region"):
    for period, block in [("before_2010", part.loc[part.year < 2010]), ("from_2010", part.loc[part.year >= 2010])]:
        for centering in ["pooled", "within_station_period"]:
            x, y = block.air_h30_target_year, block.eval_truth_h30
            if centering == "within_station_period":
                x = x - block.groupby("station_key").air_h30_target_year.transform("mean")
                y = y - block.groupby("station_key").eval_truth_h30.transform("mean")
            else:
                x, y = x - x.mean(), y - y.mean()
            rows.append(dict(region=region, period=period, centering=centering, n=len(block), stations=block.station_key.nunique(), groups=block.independence_group.nunique(), slope=np.dot(x,y)/np.dot(x,x), correlation=np.corrcoef(x,y)[0,1]))
save(pd.DataFrame(rows), "water_air_pooled_within_diagnostic.csv")

roster = seed.drop_duplicates("station_key").set_index("station_key")
roster["unique_years"] = seed.groupby("station_key").year.nunique()
roster["panel"] = np.where(roster.index.isin(keys), "trend_cohort", "source_remainder")
save(roster.reset_index()[["station_key", "panel", "n_complete_years", "unique_years"]], "archive_count_audit.csv")

eligible = pd.read_csv(ROOT / "results/wrr_review_response_20261027/rules/eligible_station_years.csv")
eligible = eligible.loc[eligible.station_key.isin(keys)]
obs = eligible.loc[~eligible.complete_year]
gap_rows = []
for period, part in [("1981-2025", obs), ("2010-2025", obs.loc[obs.year >= 2010])]:
    gap_rows.append(dict(source="observed", period=period, unit="incomplete_station_year", n=len(part), stations=part.station_key.nunique(), median_annual_longest=part.longest_run.median(), p90_annual_longest=part.longest_run.quantile(.9), share_annual_ge30=(part.longest_run>=30).mean(), share_annual_ge60=(part.longest_run>=60).mean(), julaug_complete=part.julaug_complete.mean()))
annual_masks = []
for family in ["calendar", "crossed"]:
    for design_path in sorted((BASE/family/"forward").glob("replicate_*/*/design.json")):
        design = json.loads(design_path.read_text())
        for year, spec in design["masks"].items():
            runs = [tuple(map(int,s.split(":"))) for s in spec.split(";") if s]
            annual_masks.append(dict(family=family, station_key=design["station_key"], replicate=design_path.parent.parent.name, year=int(year), longest_run=max(n for _,n in runs), n_runs=len(runs)))
am = pd.DataFrame(annual_masks)
for family, part in am.groupby("family"):
    gap_rows.append(dict(source=family, period="2010-2025", unit="incomplete_station_year_replicate", n=len(part), stations=part.station_key.nunique(), median_annual_longest=part.longest_run.median(), p90_annual_longest=part.longest_run.quantile(.9), share_annual_ge30=(part.longest_run>=30).mean(), share_annual_ge60=(part.longest_run>=60).mean()))
save(pd.DataFrame(gap_rows), "gap_common_statistic_diagnostic.csv")
save(am, "mask_annual_longest.csv")

manifest_inputs = [CASE, SEED, OLD/"trajectory_nested_cases.csv", OLD/"time_support_cases.csv", ROOT/"results/wrr_review_response_20261027/rules/eligible_station_years.csv", ROOT/"paper/wrr_tr/review_completion_article.tex", ROOT/"paper/wrr_tr/review_completion_article.pdf", ROOT/"paper/wrr_tr/review_completion_supporting.pdf", ROOT/"scripts/960_process_region_identification.py", ROOT/"scripts/961_process_time_support.py", ROOT/"scripts/962_process_trajectory_budget.py", ROOT/"scripts/963_process_revision_report.py", ROOT/"scripts/964_process_gap_and_archive.py"]
scope = dict(date="2026-10-29 Asia/Shanghai", purpose="Independent peer-review diagnostics on saved outputs; no model refit, no changes to manuscript or submitted results", bootstrap="10000 resamples of 17 connected groups, preserving all paired archive rows; percentile intervals are descriptive and not an equivalence test", regional_standardization="Uses common cell weights min(n_FOEN,n_Bavaria) or equal cells; sensitivity check, not causal identification; original matching only restricted common support", trajectory_either_tail_over_005=int(((deltas.q05_change.abs()>.05)|(deltas.q95_change.abs()>.05)).sum()), trajectory_groups=deltas.independence_group.unique().tolist(), observed_station_keys_not_forward=sorted(set(eligible.station_key)-forward_keys), forward_keys_not_observation=sorted(forward_keys-set(eligible.station_key)), input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in manifest_inputs})
(OUT/"audit_scope.json").write_text(json.dumps(scope, indent=2)+"\n")
print(json.dumps({k:v for k,v in scope.items() if k!="input_sha256"}, indent=2), flush=True)
