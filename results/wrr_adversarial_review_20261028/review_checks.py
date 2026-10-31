"""Audit saved revision evidence without altering scientific outputs."""
from pathlib import Path
import importlib.util
import json
import re
import subprocess
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
REV = ROOT / "results/wrr_review_response_20261027"
NEW = ROOT / "results/wrr_adversarial_review_20261027"
report = {"scope": "saved-case recomputation, metadata hashes, paper/table/figure consistency; no full model refit"}

# Independent enumeration against the actual eligible-year table.
y = pd.read_csv(REV / "rules/eligible_station_years.csv")
assert not y.duplicated(["station_key", "year"]).any()
rules = {
    "complete_100": y.complete_year.fillna(False),
    "annual_95": y.observed_fraction.ge(.95),
    "warm_90_station_specific": y.train_warm_fraction.ge(.9),
    "warm_90_fixed_original": y.warm_observed_fraction.ge(.9),
    "july_aug_complete": y.julaug_complete.fillna(False),
    "gap_le_49_days_context": y.longest_run.le(49),
}
saved = pd.read_csv(NEW / "rule_accounting/rule_accounting_summary.csv").set_index("rule")
checks = []
for name, mask in rules.items():
    accepted = y.loc[mask & y.reported_window.notna()].sort_values("reported_window", ascending=False)
    records = {station: list(zip(g.year, g.reported_window)) for station, g in accepted.groupby("station_key")}
    admitted_new = excluded_new = 0
    for row in y.itertuples():
        others = records.get(row.station_key, [])
        other = next((v for yr, v in others if yr != row.year), np.nan)
        new = not row.complete_year and np.isfinite(row.observed_lower_bound) and row.observed_lower_bound > other + 5e-6
        if new and mask.loc[row.Index]:
            admitted_new += 1
        elif new:
            excluded_new += 1
    expected = {"admitted": int(mask.sum()), "excluded": int((~mask).sum()),
                "admitted_new_window_facts": admitted_new, "excluded_new_window_facts": excluded_new}
    assert all(int(saved.loc[name, k]) == v for k, v in expected.items())
    checks.append({"rule": name, **expected})
report["rule_accounting"] = {"years": len(y), "stations": y.station_key.nunique(), "groups": y.independence_group.nunique(), "checks": checks}

# Recompute all descriptive-stratum point metrics from quantiles and reference.
f = pd.read_parquet(NEW / "failure_strata/failure_strata_cases.parquet")
assert len(f) == 3683 and np.isfinite(f.reference_h30).all()
for method, prefix in [("D2", "D2"), ("stochastic", "stochastic_cal")]:
    truth = f.reference_h30.to_numpy()
    low, high = f[prefix + "_q05"].to_numpy(), f[prefix + "_q95"].to_numpy()
    point = f[prefix + "_q50"].to_numpy()
    coverage = (low - 1e-8 <= truth) & (truth <= high + 1e-8)
    score = high - low + 20 * np.maximum(low-truth, 0) + 20 * np.maximum(truth-high, 0)
    assert np.array_equal(coverage, f["coverage90_" + method].astype(bool))
    assert np.allclose(abs(point-truth), f["mae_" + method], atol=1e-12, rtol=0)
    assert np.allclose(score, f["interval_score90_" + method], atol=1e-12, rtol=0)
report["failure_strata"] = {
    "cases": len(f), "regions": sorted(f.region.unique()),
    "foen_n": int(f.region.eq("foen").sum()),
    "foen_stations": int(f.loc[f.region.eq("foen"), "station_key"].nunique()),
    "foen_groups": int(f.loc[f.region.eq("foen"), "independence_group"].nunique()),
    "foen_D2_coverage": float(f.loc[f.region.eq("foen"), "coverage90_D2"].mean()),
    "half_overlap_mislabelled_partial": int((f.peak_overlap.eq(.5) & f.overlap_bin.eq("partial")).sum()),
    "currently_labelled_at_least_half": int(f.overlap_bin.eq("at least half").sum()),
    "actually_at_least_half": int(f.peak_overlap.ge(.5).sum()),
}

# Each method has the same archives across constructions and simulation sizes,
# but the methods do not have identical available sets.
r = pd.read_csv(NEW / "rank_convergence/rank_convergence_cases.csv.gz")
keys = ["station_key", "replicate", "method", "construction", "draws", "seed"]
assert not r.duplicated(keys).any()
assert np.isfinite(r[["lower_error", "upper_error", "width", "interval_score"]]).all().all()
assert np.array_equal(r.covered, (r.lower_error <= 1e-12) & (r.upper_error >= -1e-12))
for method, group in r.groupby("method"):
    sets = [frozenset(zip(g.station_key, g.replicate)) for _, g in group.groupby(["construction", "draws", "seed"])]
    assert len(set(sets)) == 1
seed = r.groupby(["method", "construction", "seed", "draws"]).agg(coverage=("covered", "mean"), width=("width", "mean"), score=("interval_score", "mean")).reset_index()
cp = seed.pivot(index=["method", "construction", "seed"], columns="draws", values="coverage")
cp["change_1024_4096_pp"] = 100 * (cp[4096] - cp[1024])
cp.reset_index().to_csv(OUT / "rank_per_seed_changes.csv", index=False)
summary = pd.read_csv(NEW / "rank_convergence/rank_convergence_summary.csv")
worst = float(cp.change_1024_4096_pp.abs().max())
report["rank_check"] = {
    "rows": len(r), "maximum_absolute_per_seed_coverage_change_pp": worst,
    "maximum_absolute_three_seed_mean_change_pp": float(summary.coverage_change_1024_4096_pp.abs().max()),
    "three_seed_mean_stable_combinations": int(summary.drop_duplicates(["method", "construction"]).meets_numerical_stability_rule.sum()),
    "coverage_4096_min": float(seed.loc[seed.draws.eq(4096), "coverage"].min()),
    "coverage_4096_max": float(seed.loc[seed.draws.eq(4096), "coverage"].max()),
}

u = pd.read_csv(REV / "whole_archive/uncertainty_common_cases.csv")
u = u.loc[u.family.eq("crossed") & u["mode"].eq("forward")]
a = u.loc[u.estimator.eq("D2")].set_index(["station_key", "replicate"])
b = u.loc[u.estimator.eq("stochastic_calibrated")].set_index(["station_key", "replicate"])
common = a.index.intersection(b.index)
report["figure_uncertainty_denominators"] = []
for name, g in [("D2 displayed", a), ("D2 common to both methods", a.loc[common]), ("stochastic common", b.loc[common])]:
    report["figure_uncertainty_denominators"].append({"name": name, "archives": len(g), "annual_cases": int(g.n_incomplete.sum()),
        "annual_coverage": float((g.n_incomplete*g.coverage90).sum()/g.n_incomplete.sum()),
        "independent_trend_coverage": float(g.independent_coverage95.mean())})

manifest = pd.read_csv(NEW / "metadata_correction/design_correction_manifest.csv")
path_col = "path" if "path" in manifest else "file"
bad = []
for row in manifest.to_dict("records"):
    p = Path(row[path_col])
    if not p.is_absolute(): p = ROOT / p
    if not p.is_file(): bad.append(str(p))
report["metadata_manifest"] = {"rows": len(manifest), "mismatches": bad}
assert not bad

bc = pd.read_parquet(REV / "external_bc_air2stream/predictions.parquet")
truckee = json.loads((REV / "external_truckee_dwr/exploratory_score_status.json").read_text())
reservoir = json.loads((REV / "external_usace_reservoir/partial_history_score_status.json").read_text())
fresh = pd.read_csv(REV / "external_usgs_fresh/qualification.csv")
report["external_reference_facts"] = {
    "BC_cases_by_family": bc.design_family.value_counts().to_dict(),
    "Truckee_scored_cases": truckee["cases"],
    "reservoir_scored_cases": reservoir["cases"],
    "reservoir_scored_station_years": reservoir["target_station_years"],
    "fresh_USGS_complete_daily_station_years": int(fresh.n_complete_years.sum()),
    "fresh_USGS_stations_with_four_complete_years": int(fresh.n_complete_years.ge(4).sum()),
}

archive = ROOT / "dist/wrr_review_response_candidate.zip"
different = []
with zipfile.ZipFile(archive) as z:
    names = set(z.namelist())
    for name in names:
        p = ROOT / name
        if p.is_file() and z.read(name) != p.read_bytes(): different.append(name)
    missing_new_scripts = [f"scripts/{i}_{s}.py" for i,s in [(926,"rule_accounting"),(927,"failure_strata"),(928,"rank_convergence"),(929,"manuscript_inputs")] if f"scripts/{i}_{s}.py" not in names]
report["candidate"] = {"changed_workspace_files": sorted(different), "missing_new_scripts": missing_new_scripts}

article = (ROOT / "paper/wrr_tr/review_completion_article.tex").read_text()
macro = {}
for p in list((ROOT / "paper/wrr_tr").glob("*values.tex")) + [ROOT / "paper/wrr_tr/simple_research_claims.tex", ROOT / "paper/wrr_tr/review_completion_claims.tex"]:
    macro.update(re.findall(r"\\newcommand\{\\(\w+)\}\{([^{}]*)\}", p.read_text()))
abstract = article.split(r"\begin{abstract}")[1].split(r"\begin{plainlanguagesummary}")[0]
for k,v in macro.items(): abstract = re.sub(r"\\" + k + r"\{\}", lambda m:v, abstract)
abstract = abstract.replace(r"$^{\circ}$C", "degrees C").replace(r"\%", "%")
report["abstract_whitespace_word_count"] = len(abstract.split())
report["keypoint_character_counts"] = [len(v) for v in re.findall(r"\{([^{}]*)\}", article.split(r"\keypoints")[1].split(r"\maketitle")[0])]
si = subprocess.check_output(["pdftotext", "-layout", str(ROOT / "paper/wrr_tr/review_completion_supporting.pdf"), "-"], text=True)
page = si.split("\f")[41]
report["SI_page42"] = {"contains_failure_table": "Descriptive failure strata" in page,
    "contains_huc17_rows": "region: usgs huc17" in page,
    "float_warning": "Float too large for page by 159.95259pt" in (ROOT / "paper/wrr_tr/review_completion_supporting.log").read_text()}
OUT.joinpath("review_checks.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
