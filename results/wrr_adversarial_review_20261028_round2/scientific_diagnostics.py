"""Reviewer-only diagnostics of existing predictions and finite-record targets.

No fit, calibration or main research artifact is changed. The retained-truth
comparator is an evaluation oracle and cannot be deployed on missing values.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
REF = ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet"

def slope(years, values):
    x = (np.asarray(years, float) - np.mean(years)) / 10
    return float(x @ np.asarray(values, float) / (x @ x))

reference = pd.read_parquet(REF, columns=["station_key", "year", "design_family", "eval_truth_h30"])
assert reference.groupby(["station_key", "year", "design_family"]).eval_truth_h30.nunique().max() == 1
lookup = {(family, station): g.drop_duplicates("year").set_index("year").eval_truth_h30.sort_index()
          for (family, station), g in reference.groupby(["design_family", "station_key"])}
trends = pd.read_csv(BASE / "trends.csv")
trends = trends.loc[trends.estimator.eq("D2") & trends.dependence.eq("point")]
rows = []
for (family, mode, station, replicate), group in trends.groupby(["family", "mode", "station_key", "replicate"]):
    saved = group.set_index("retention")
    if not saved.loc[["all", "warm90"], "available"].all():
        continue
    folder = BASE / family / mode / f"replicate_{replicate:02d}" / station.replace("|", "_")
    design = json.loads((folder / "design.json").read_text())
    ref = lookup[family, station]
    if mode == "forward": ref = ref.loc[ref.index >= 2010]
    years, truth = ref.index.to_numpy(), ref.to_numpy()
    missing = np.isin(years, [int(y) for y in design["masks"]])
    point = truth.copy()
    keep = ~missing
    if missing.any():
        predicted = pd.read_parquet(folder / "annual_predictions.parquet", columns=["year", "warm_observed_fraction", "D2"]).set_index("year").reindex(years)
        point[missing] = predicted.D2.to_numpy()[missing]
        keep |= predicted.warm_observed_fraction.ge(.9).to_numpy()
    assert keep.sum() == int(saved.loc["warm90", "n_retained"])
    full = slope(years, truth)
    all_error = slope(years, point) - full
    retained_error = slope(years[keep], point[keep]) - full
    oracle_error = slope(years[keep], truth[keep]) - full
    reconstruction = slope(years[keep], point[keep]) - slope(years[keep], truth[keep])
    assert abs(all_error - saved.loc["all", "error"]) < 1e-10
    assert abs(retained_error - saved.loc["warm90", "error"]) < 1e-10
    assert abs(retained_error - oracle_error - reconstruction) < 1e-10
    rows.append(dict(family=family, mode=mode, station_key=station, replicate=int(replicate),
                     independence_group=group.independence_group.iloc[0], region=group.region.iloc[0],
                     years=len(years), retained=int(keep.sum()), all_error=all_error,
                     retained_error=retained_error, retained_truth_error=oracle_error,
                     retained_reconstruction_error=reconstruction))
cases = pd.DataFrame(rows)
cases.to_csv(OUT / "retained_truth_diagnostic_cases.csv", index=False)
summaries=[]
for (family,mode), g in cases.groupby(["family", "mode"]):
    summaries.append(dict(family=family, mode=mode, n=len(g), stations=g.station_key.nunique(), groups=g.independence_group.nunique(),
        all_D2_rmse=float(np.sqrt(np.mean(g.all_error**2))),
        warm_D2_rmse=float(np.sqrt(np.mean(g.retained_error**2))),
        warm_true_H30_rmse=float(np.sqrt(np.mean(g.retained_truth_error**2))),
        warm_reconstruction_component_rms=float(np.sqrt(np.mean(g.retained_reconstruction_error**2))),
        selection_mse=float(np.mean(g.retained_truth_error**2)),
        reconstruction_mse=float(np.mean(g.retained_reconstruction_error**2)),
        cross_term=float(np.mean(2*g.retained_truth_error*g.retained_reconstruction_error)),
        total_warm_mse=float(np.mean(g.retained_error**2))))
summary=pd.DataFrame(summaries)
summary.to_csv(OUT / "retained_truth_diagnostic_summary.csv", index=False)
print("RETAINED-TRUTH DIAGNOSTIC", flush=True)
print(summary.to_string(index=False),flush=True)

r=pd.read_csv(ROOT / "results/wrr_adversarial_review_20261027/rank_convergence/rank_convergence_cases.csv.gz")
r=r.loc[r.draws.eq(4096)]
per_archive=r.groupby(["method","construction","station_key","replicate","independence_group","region"]).agg(coverage=("covered","mean"),width=("width","mean"),score=("interval_score","mean")).reset_index()
coverage=[]
for (method,construction), g in per_archive.groupby(["method","construction"]):
    group=g.groupby("independence_group").coverage.agg(["sum","size","mean"])
    rng=np.random.default_rng(20261028)
    indices=rng.integers(len(group),size=(5000,len(group)))
    bootstrap=group['sum'].to_numpy()[indices].sum(axis=1)/group['size'].to_numpy()[indices].sum(axis=1)
    coverage.append(dict(method=method, construction=construction, n=len(g), groups=len(group),
        pooled=float(g.coverage.mean()), group_equal=float(group['mean'].mean()),
        cluster_low=float(np.quantile(bootstrap,.025)),cluster_high=float(np.quantile(bootstrap,.975)),
        without_bavaria=float(g.loc[g.region.ne('gkd_bayern'),'coverage'].mean())))
pd.DataFrame(coverage).to_csv(OUT / "coverage_group_diagnostic.csv",index=False)
print("COVERAGE GROUP DIAGNOSTIC",flush=True)
print(pd.DataFrame(coverage).to_string(index=False),flush=True)
(OUT / "scientific_diagnostics_status.json").write_text(json.dumps({
    "status":"passed_saved_case_recomputation", "retention_cases":len(cases),
    "saved_D2_point_trends_reproduced":2*len(cases), "rank_rows_4096":len(r),
    "limits":["Post-hoc reviewer diagnostics on the same archive, not new independent validation", "True retained-year H30 is an evaluation-only oracle", "Additive decomposition includes a cross term and is not a causal percentage", "Group bootstrap describes the available groups; no climate-population guarantee"]},indent=2)+"\n")
