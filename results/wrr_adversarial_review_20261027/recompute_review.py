"""Read-only scientific rechecks for the 27 October adversarial review.

Writes only to this audit directory. Does not refit or change paper results.
The Monte Carlo check is a post-hoc numerical sensitivity, not new validation.
"""
from pathlib import Path
import json
import re
import sys
import zipfile

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from stream_recoverability.experiments.tr_revision.archive import LEVELS, marginal_draws

OUT = Path(__file__).resolve().parent
BASE = ROOT / "results/wrr_review_response_20261027"
report = {"scope": "saved-case arithmetic and numerical sensitivity; no model refitting"}
reference = pd.read_parquet(ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet",
                           columns=["station_key", "year", "design_family", "eval_truth_h30"])
assert reference.groupby(["station_key", "year", "design_family"]).eval_truth_h30.nunique().max() == 1
truth_lookup = reference.drop_duplicates(["station_key", "year", "design_family"]).rename(columns={"design_family": "family", "eval_truth_h30": "reference_h30"})
t = pd.read_csv(BASE / "whole_archive/trends.csv")
primary = t.loc[t.retention.eq("all") & t.dependence.eq("point") & t.available]
units = primary[["station_key", "independence_group", "region"]].drop_duplicates()
report["units"] = dict(stations=len(units), groups=units.independence_group.nunique(),
                       regions=units.region.nunique(), by_region=units.region.value_counts().to_dict())
paired = []
for (family, mode), g in primary.groupby(["family", "mode"]):
    p = g.pivot(index=["station_key", "independence_group", "region", "replicate"],
                columns="estimator", values="squared_error")
    p = p[["D2", "stochastic_calibrated"]].dropna()
    delta = p.D2 - p.stochastic_calibrated
    no_bavaria = p.index.get_level_values("region") != "gkd_bayern"
    paired.append(dict(family=family, mode=mode, n=len(p),
        d2_rmse=float(np.sqrt(p.D2.mean())), stochastic_rmse=float(np.sqrt(p.stochastic_calibrated.mean())),
        mse_difference=float(delta.mean()), group_equal_mse_difference=float(delta.groupby(level="independence_group").mean().mean()),
        without_bavaria_mse_difference=float(delta[no_bavaria].mean())))
report["paired_trends"] = paired

factor = pd.read_csv(BASE / "whole_archive/factorial_contrasts.csv")
report["factorial_identity_max_error"] = float((factor.symmetric_retention + factor.symmetric_estimator - factor.total_gain).abs().max())
f = factor.loc[factor.family.eq("crossed") & factor["mode"].eq("offline") & factor.estimator.eq("D2")].dropna()
report["offline_controlled_retention_share"] = float(f.symmetric_retention.mean() / f.total_gain.mean())

tc = pd.read_csv(BASE / "whole_archive/task_calibrated_trends.csv")
tc = tc.loc[tc.family.eq("crossed") & tc["mode"].eq("forward") & tc.estimator.eq("D2")]
report["forward_controlled_task"] = dict(n=len(tc), stations=tc.station_key.nunique(), groups=tc.independence_group.nunique(),
    width_min=float(tc.width95.min()), coverage=float(tc.missing_coverage95.mean()),
    source_group_counts=sorted(map(int, tc.n_source_groups.unique())))

cols = ["station_key", "independence_group", "year", "eval_truth_h30", "observed_lower_bound__observed_days",
        "D2", "h30__policy"] + [f"{method}_q{int(100*q):02d}" for method in ["D2", "stochastic_cal"] for q in LEVELS]
blocks = []
stale = 0
design_count = 0
for family in ["calendar", "crossed"]:
    for mode in ["offline", "forward"]:
        for path in sorted((BASE / "whole_archive" / family / mode).glob("replicate_*/*/annual_predictions.parquet")):
            d = pd.read_parquet(path)
            design = json.loads(path.with_name("design.json").read_text())
            design_count += 1
            stale += "held region and connected groups excluded" in design.get("annual_model", "")
            if d.empty:
                continue
            d = d[cols].copy()
            d["family"] = family
            d["mode"] = mode
            d["replicate"] = int(path.parent.parent.name.removeprefix("replicate_"))
            blocks.append(d)
cases = pd.concat(blocks, ignore_index=True)
cases = cases.merge(truth_lookup, on=["station_key", "year", "family"], how="left", validate="many_to_one")
assert np.isfinite(cases.reference_h30).all(), "Every evaluated year needs a separate complete-reference truth"
report["truth_source"] = "Complete-reference seed_00 table, joined by station/year/family; masked feature files intentionally omit target truth"
cases["eval_truth_h30"] = cases.reference_h30
report["saved_archive_designs"] = {"count": design_count, "old_unqualified_region_exclusion_text": stale}
qcols = [c for c in cols if "_q" in c] + ["D2", "h30__policy"]
below = cases[qcols].to_numpy() < cases.observed_lower_bound__observed_days.to_numpy()[:, None] - 1e-8
report["annual_support"] = {"cases": len(cases), "below_bound_values": int(below.sum())}
strata = []
for (family, mode), g in cases.groupby(["family", "mode"]):
    qcols = [f"{method}_q{int(100*q):02d}" for method in ["D2", "stochastic_cal"] for q in LEVELS]
    g = g.loc[np.isfinite(g[qcols].to_numpy()).all(axis=1) & g.observed_lower_bound__observed_days.notna()].copy()
    bound = g.observed_lower_bound__observed_days.to_numpy()
    y = g.eval_truth_h30.to_numpy()
    hidden = y > bound + 1e-8
    for method in ["D2", "stochastic_cal"]:
        low, high = g[f"{method}_q05"].to_numpy(), g[f"{method}_q95"].to_numpy()
        covered = (low - 1e-8 <= y) & (y <= high + 1e-8)
        zero = (high - low) <= 1e-8
        strata.append(dict(family=family, mode=mode, method=method, n=len(g),
            hidden_n=int(hidden.sum()), coverage=float(covered.mean()), hidden_coverage=float(covered[hidden].mean()),
            zero_width=int(zero.sum()), zero_width_uncovered=int((zero & ~covered).sum())))
report["annual_common_strata"] = strata
q = norm.ppf(LEVELS)[None, :]
report["normal_sanity"] = {tail: np.quantile(marginal_draws(q, 100000, tails=tail)[:, 0], [.025, .975]).tolist()
                           for tail in ["constant", "normal"]}
log = (OUT / "review_test.log").read_text()
report["passed_tests"] = sum(map(int, re.findall(r"(\d+) passed", log)))

package = ROOT / "dist/wrr_review_response_candidate.zip"
changed = []
matched = 0
with zipfile.ZipFile(package) as z:
    for n in z.namelist():
        p = ROOT / n
        if p.is_file():
            matched += 1
            if z.read(n) != p.read_bytes():
                changed.append(n)
report["package"] = {"workspace_files": matched, "changed": changed}
(OUT / "recomputed_evidence.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2), flush=True)

# The fully observed terms cancel when sampled slope minus reference slope is computed.
# Only incomplete years need to be sampled, but weights use the full reference-year set.
ref_years = {station: np.sort(g.year.unique()) for station, g in reference.loc[reference.year.ge(2010)].groupby("station_key")}
forward = cases.loc[cases.family.eq("crossed") & cases["mode"].eq("forward")]
numerical = []
for (station, replicate), g in forward.groupby(["station_key", "replicate"], sort=True):
    g = g.sort_values("year")
    years = ref_years[station]
    x = (years - years.mean()) / 10
    weights = (x / (x @ x))[np.searchsorted(years, g.year.to_numpy())]
    for method in ["D2", "stochastic_cal"]:
        q = g[[f"{method}_q{int(100*l):02d}" for l in LEVELS]].to_numpy()
        if not np.isfinite(q).all():
            continue
        y = g.eval_truth_h30.to_numpy()
        for n in [256, 1024, 4096]:
            sample = marginal_draws(q, n, lower_bounds=g.observed_lower_bound__observed_days.to_numpy())
            for seed in [202610271, 202610272, 202610273]:
                key = int.from_bytes(f"{station}|{replicate}|{seed}"[:8], "little")
                rng = np.random.default_rng(key)
                errors = np.zeros(n)
                for j in range(len(g)):
                    errors += weights[j] * (rng.permutation(sample[:, j]) - y[j])
                low, high = np.quantile(errors, [.025, .975])
                assert np.isfinite([low, high]).all()
                width = high - low
                score = width + 40 * max(low, 0) + 40 * max(-high, 0)
                numerical.append(dict(station_key=station, independence_group=g.independence_group.iloc[0], replicate=int(replicate),
                                      method=method, draws=n, seed=seed, covered=bool(low - 1e-12 <= 0 <= high + 1e-12),
                                      lower_error=low, upper_error=high, width=width, interval_score=score))
num = pd.DataFrame(numerical)
num.to_csv(OUT / "monte_carlo_numerical_cases.csv", index=False)
summary = num.groupby(["method", "draws", "seed"]).agg(n=("covered", "size"), coverage=("covered", "mean"),
        width=("width", "mean"), interval_score=("interval_score", "mean")).reset_index()
summary.to_csv(OUT / "monte_carlo_numerical_summary.csv", index=False)
print(summary.to_string(index=False), flush=True)
