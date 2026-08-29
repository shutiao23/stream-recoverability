#!/usr/bin/env python3
"""Part B — downstream multi-untreated-baseline thermal comparison (v13 decision harmonization, agent_b).

Inputs (read-only):
  results/revision_v12/t08_downstream_metrics/agent_b/placement_metrics.csv   (1,755 placements)
  results/revision_v12/t08_downstream_metrics/agent_b/budget_comparison.csv   (no-fill default)
  results/revision_v12/t08_downstream_metrics/agent_a/budget_comparison.csv   (climatology default)
  results/revision_v12/t08_downstream_metrics/agent_a/budget_combined.csv
  results/revision_v12/t08_downstream_metrics/agent_a/placement_thermal_metrics.csv
  results/revision_v12/t08_downstream_metrics/agent_a/reconstruction_series.parquet

Outputs (this dir): downstream_baseline_comparison.csv, budget_joint_table.csv,
                     divergence_note.md, interp_availability.txt (linear-interpolation baseline status).

Definitions:
  - err_recon = |truth - reconstructed|, err_missing = |truth - no-fill|, err_clim = |truth - climatology|
    (phase error is the circular day difference, as stored in placement_metrics.csv).
  - Per-metric means are placement-level means over defined rows (skipna); amplitude/summer metrics are
    undefined for some placements (window lacks the relevant season), reported per (metric, scenario).
  - Network-level median = median over the 15 networks of per-network mean error.
  - ratio_recon_missing = mean_err_recon / mean_err_missing (placement-level means);
    ratio_recon_clim = mean_err_recon / mean_err_clim.
  - share_recon_worse_than_X = share of placements with err_recon > err_X over rows where both are defined.
  - Budget joint table: policy (risk / gap_length / random) x metric x default (no_fill from agent_b,
    climatology from agent_a); reduction = 1 - aggregate distortion(treated)/aggregate(untreated),
    fractions as stored in the source CSVs; n_units = 270 (agent_b; 261 amplitude) / 1965 (agent_a;
    1950 for summer metrics and amplitude).
  - Linear-interpolation baseline: 'not computable' — neither agent produced a linear-interpolation
    reconstruction (agent_a reconstruction_series.parquet stores truth/reconstruction/climatology only;
    agent_a placement_thermal_metrics.csv stores only reconstruction and climatology errors), and
    recomputing it would require re-running the downstream metric pipeline (windowing, phase smoothing,
    trend OLS) on a new fill, which is outside this read-only artifact analysis.
"""
import numpy as np
import pandas as pd

OUT = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v13/decision_harmonization/agent_b"
T08B = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v12/t08_downstream_metrics/agent_b"
T08A = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v12/t08_downstream_metrics/agent_a"

METRICS = ["annual_mean", "summer_mean", "amplitude", "phase_doy", "p90", "summer_max",
           "exceed_days_20", "exceed_days_25", "cdd10", "trend_slope"]

df = pd.read_csv(f"{T08B}/placement_metrics.csv")
assert len(df) == 1755
net = df["network_id"]

# ---------- (1) per-metric means, network-level medians, ratios ----------
# Common-support convention (agent_b REPORT.md): means over placements where the metric is
# computable under EVERY scenario (recon, missing, clim all defined); otherwise comparing
# recon vs no-fill mixes different placement subsets (e.g. amplitude is undefined under
# no-fill when the gap swallows July/January). Skipna means are reported in REPORT.md.
rows = []
rows_skipna = []
for m in METRICS:
    e = {s: df[f"{m}_err_{s}"] for s in ["recon", "missing", "clim"]}
    common = e["recon"].notna() & e["missing"].notna() & e["clim"].notna()
    means = {s: float(e[s][common].mean()) for s in e}
    n_def = {s: int(e[s].notna().sum()) for s in e}
    net_mean = {s: e[s][common].groupby(net[common]).mean() for s in e}
    net_med = {s: float(net_mean[s].median()) for s in e}
    share_worse_missing = float((e["recon"][common] > e["missing"][common]).mean())
    share_worse_clim = float((e["recon"][common] > e["clim"][common]).mean())
    rows.append(dict(
        metric=m, mean_err_recon=means["recon"], mean_err_missing=means["missing"], mean_err_clim=means["clim"],
        ratio_recon_missing=means["recon"] / means["missing"], ratio_recon_clim=means["recon"] / means["clim"],
        share_recon_worse_than_clim=share_worse_clim, share_recon_worse_than_missing=share_worse_missing,
        n_common=int(common.sum()), n_recon=n_def["recon"], n_missing=n_def["missing"], n_clim=n_def["clim"],
        median_err_recon=net_med["recon"], median_err_missing=net_med["missing"], median_err_clim=net_med["clim"]))
    skip = {s: float(e[s].mean()) for s in e}
    rows_skipna.append(dict(metric=m, n_recon=n_def["recon"], n_missing=n_def["missing"], n_clim=n_def["clim"],
                            skipna_mean_err_recon=skip["recon"], skipna_mean_err_missing=skip["missing"],
                            skipna_mean_err_clim=skip["clim"],
                            skipna_ratio_recon_missing=skip["recon"] / skip["missing"],
                            skipna_ratio_recon_clim=skip["recon"] / skip["clim"]))

base = pd.DataFrame(rows)
base[["metric", "mean_err_recon", "mean_err_missing", "mean_err_clim", "ratio_recon_missing",
      "ratio_recon_clim", "share_recon_worse_than_clim", "share_recon_worse_than_missing"]].to_csv(
    f"{OUT}/downstream_baseline_comparison.csv", index=False)
# network-level medians in a side table (documented in REPORT.md)
base[["metric", "n_common", "n_recon", "n_missing", "n_clim", "median_err_recon", "median_err_missing",
      "median_err_clim"]].to_csv(f"{OUT}/network_median_errors.csv", index=False)
pd.DataFrame(rows_skipna).to_csv(f"{OUT}/skipna_means.csv", index=False)

# ---------- (3) budget joint table ----------
b_b = pd.read_csv(f"{T08B}/budget_comparison.csv")
b_a = pd.read_csv(f"{T08A}/budget_comparison.csv")
policy_map_b = {"top20_risk": "risk", "top20_length": "gap_length", "random20": "random"}

jt = []
for _, r in b_b.iterrows():
    jt.append(dict(policy=policy_map_b[r["policy"]], metric=r["metric"], default="no_fill",
                   reduction=r["reduction"], n_units=r["n_units"]))
A2B = {"degree_days_10": "cdd10", "exceed_20_days": "exceed_days_20", "exceed_25_days": "exceed_days_25"}
for _, r in b_a[b_a["policy"].isin(["risk", "gap_length", "random"])].iterrows():
    m = A2B.get(r["metric"], r["metric"])
    if m in METRICS:
        jt.append(dict(policy=r["policy"], metric=m, default="climatology",
                       reduction=r["reduction_mean"], n_units=1965))
joint = pd.DataFrame(jt)
joint.to_csv(f"{OUT}/budget_joint_table.csv", index=False)

# ---------- (4) review-claims verification values (printed) ----------
print("== placement-level ratios (recon/missing), common support ==")
for _, r in base.iterrows():
    print(f"  {r['metric']:15s} {r['ratio_recon_missing']:.4f}  {r['ratio_recon_clim']:.4f}  "
          f"worse_vs_missing={r['share_recon_worse_than_missing']:.4f} worse_vs_clim={r['share_recon_worse_than_clim']:.4f}")
print("\n== station-gap-level shares (recon > missing, mean over placements on common support) ==")
for m in METRICS:
    g = df.groupby(["network_id", "station_id", "gap_length"])
    agg = g[[f"{m}_err_recon", f"{m}_err_missing"]].mean()
    agg = agg[agg[f"{m}_err_recon"].notna() & agg[f"{m}_err_missing"].notna()]
    share = float((agg[f"{m}_err_recon"] > agg[f"{m}_err_missing"]).mean())
    print(f"  {m:15s} n_gaps={len(agg):4d} share={share:.4f}")
print("\n== agent_a climatology-default risk-policy reductions (fraction) ==")
for _, r in b_a[b_a["policy"] == "risk"].iterrows():
    print(f"  {r['metric']:15s} {r['reduction_mean']:.4f}")
print("\n== agent_b no-fill risk-policy reductions (fraction) ==")
for _, r in b_b[b_b["policy"] == "top20_risk"].iterrows():
    print(f"  {r['metric']:15s} {r['reduction']:.4f}")

# ---------- (5) linear-interpolation baseline status ----------
par = pd.read_parquet(f"{T08A}/reconstruction_series.parquet")
pa_pl = pd.read_csv(f"{T08A}/placement_thermal_metrics.csv")
interp_status = ("not computable: no linear-interpolation reconstruction is present in the read-only "
                 "artifacts. agent_a/reconstruction_series.parquet stores only truth, reconstruction "
                 "(XGBoost) and climatology series (columns: %s); agent_a/placement_thermal_metrics.csv "
                 "stores errors for reconstruction and climatology only; agent_b/placement_metrics.csv "
                 "stores truth/recon/missing/clim metrics but no interp fill. Computing err_interp would "
                 "require re-running the downstream metric pipeline (window definition, phase smoothing, "
                 "trend OLS) on a newly created linear-interpolated fill, which is outside this "
                 "read-only artifact analysis." % ", ".join(par.columns))
with open(f"{OUT}/interp_availability.txt", "w") as fh:
    fh.write(interp_status + "\n")
print("\nInterp baseline:", interp_status[:120], "...")
