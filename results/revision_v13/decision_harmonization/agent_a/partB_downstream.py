"""Part B: downstream multi-untreated-baseline thermal comparison (t08 data).

Inputs (read-only):
- agent_b/placement_metrics.csv: 1,755 placements x {truth, recon, missing
  (no-fill), clim (climatology)} thermal metrics + absolute errors
- agent_b/metric_error_summary.csv, agent_b/budget_comparison.csv
- agent_a/placement_thermal_metrics.csv, agent_a/budget_combined.csv,
  agent_a/reconstruction_series.parquet

Outputs (this directory only): downstream_baseline_comparison.csv,
budget_joint_table.csv, divergence_note.md, REPORT.md.

Deterministic; no training; no writes outside this directory.
"""

import numpy as np
import pandas as pd

OUT = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v13/decision_harmonization/agent_a"
TB = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v12/t08_downstream_metrics/agent_b"
TA = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v12/t08_downstream_metrics/agent_a"

METRICS = ["annual_mean", "summer_mean", "amplitude", "phase_doy", "p90",
           "summer_max", "exceed_days_20", "exceed_days_25", "cdd10", "trend_slope"]
LABELS = {
    "annual_mean": "annual mean (degC)", "summer_mean": "summer JJA mean (degC)",
    "amplitude": "amplitude Jul-Jan (degC)", "phase_doy": "phase (day of peak)",
    "p90": "90th percentile (degC)", "summer_max": "summer maximum (degC)",
    "exceed_days_20": "days > 20 degC", "exceed_days_25": "days > 25 degC",
    "cdd10": "degree days > 10 degC", "trend_slope": "trend slope (degC/yr)",
}

p = pd.read_csv(f"{TB}/placement_metrics.csv")
assert len(p) == 1755
networks = p.network_id.unique()

rows = []
for m in METRICS:
    er, em, ec = p[f"{m}_err_recon"], p[f"{m}_err_missing"], p[f"{m}_err_clim"]
    # 3-way common support: placements where every scenario defines the metric
    cs = ~er.isna() & ~em.isna() & ~ec.isna()
    # placement-level means
    mean_r, mean_m, mean_c = er[cs].mean(), em[cs].mean(), ec[cs].mean()
    # network-level median: median over networks of per-network mean error
    def net_med(col):
        nm = p.loc[cs, :].groupby("network_id")[col].mean()
        return float(nm.median()), int(nm.shape[0])
    med_r, n_net_r = net_med(f"{m}_err_recon")
    med_m, n_net_m = net_med(f"{m}_err_missing")
    med_c, n_net_c = net_med(f"{m}_err_clim")
    # ratios and shares on the 3-way common support
    ratio_rm = float(er[cs].mean() / em[cs].mean())
    ratio_rc = float(er[cs].mean() / ec[cs].mean())
    share_wc = float((er[cs] > ec[cs]).mean())
    share_wm = float((er[cs] > em[cs]).mean())
    # own-support means (each scenario on its own available placements)
    rows.append({
        "metric": m, "label": LABELS[m],
        "n_common_support": int(cs.sum()),
        "n_placements_recon": int(er.notna().sum()),
        "n_placements_missing": int(em.notna().sum()),
        "n_placements_clim": int(ec.notna().sum()),
        "mean_err_recon": mean_r, "mean_err_missing": mean_m, "mean_err_clim": mean_c,
        "mean_err_recon_own": er.mean(), "mean_err_missing_own": em.mean(), "mean_err_clim_own": ec.mean(),
        "netmedian_err_recon": med_r, "netmedian_err_missing": med_m, "netmedian_err_clim": med_c,
        "ratio_recon_missing": ratio_rm, "ratio_recon_clim": ratio_rc,
        "share_recon_worse_than_clim": share_wc, "share_recon_worse_than_missing": share_wm,
    })
base = pd.DataFrame(rows)
base.to_csv(f"{OUT}/downstream_baseline_comparison.csv", index=False)
print(base[["metric", "mean_err_recon", "mean_err_missing", "mean_err_clim",
            "ratio_recon_missing", "ratio_recon_clim",
            "share_recon_worse_than_clim", "share_recon_worse_than_missing"]].round(4).to_string(index=False))

# --------------------------------------------------------------------------
# cross-check vs agent_b's own station-gap-level summary
# --------------------------------------------------------------------------
own = pd.read_csv(f"{TB}/metric_error_summary.csv")
own_map = {"exceed_days_20": "exceed_days_20", "exceed_days_25": "exceed_days_25",
           "cdd10": "cdd10", "trend_slope": "trend_slope"}
print("\ncross-check: station-gap-level means (agent_b metric_error_summary.csv):")
chk = []
for _, r in own.iterrows():
    chk.append(f"{r.metric}: recon {r.mean_err_recon:.4f} missing {r.mean_err_missing:.4f} "
               f"clim {r.mean_err_clim:.4f} ratio {r.mean_recon_over_missing:.3f}")
print("\n".join(chk))

# --------------------------------------------------------------------------
# joint budget table: policy x metric x default
# --------------------------------------------------------------------------
# agent_b: no-treatment default = no-fill (gap days dropped); units = 270
# station-gaps (261 amplitude), budget top 20%
bb = pd.read_csv(f"{TB}/budget_comparison.csv")
bb_map = {"exceed_days_20": "exceed_20_days", "exceed_days_25": "exceed_25_days",
          "cdd10": "degree_days_10"}
# agent_a: no-treatment default = climatology fill; units = 393 placements of
# 1965 (top 20%), oracles excluded here
ba = pd.read_csv(f"{TA}/budget_combined.csv")
ba = ba[ba.policy.isin(["risk", "gap_length", "random"])]

joint = []
for m in METRICS:
    m_b = bb_map.get(m, m)
    m_a = "r_" + m_b
    for pol_b, pol_a in [("top20_risk", "risk"), ("top20_length", "gap_length"), ("random20", "random")]:
        rb = bb[(bb.policy == pol_b) & (bb.metric == m)]
        ra = ba[(ba.policy == pol_a)]
        row = {"policy": pol_a, "metric": m, "metric_agent_b": m_b}
        if len(rb):
            row["default"] = "no_fill"
            row["reduction"] = float(rb.reduction.iloc[0])
            row["n_units"] = int(rb.n_units.iloc[0])
            joint.append(row)
        if m_a in ra.columns:
            row = {"policy": pol_a, "metric": m, "metric_agent_b": m_b,
                   "default": "climatology", "reduction": float(ra[m_a].iloc[0]),
                   "n_units": 393}
            joint.append(row)
jt = pd.DataFrame(joint)
jt.to_csv(f"{OUT}/budget_joint_table.csv", index=False)
print("\njoint budget table (reduction, positive = reduction in aggregate distortion):")
print(jt.pivot_table(index=["policy", "metric"], columns="default", values="reduction").round(3).to_string())

# --------------------------------------------------------------------------
# review-claim verification
# --------------------------------------------------------------------------
print("\n== review claims verification ==")
for m in ["annual_mean", "cdd10", "trend_slope"]:
    r = base[base.metric == m].iloc[0]
    print(f"agent_b no-fill ratio {m}: {r.ratio_recon_missing:.3f} (claim 12-14%)")
for m in ["p90", "amplitude", "exceed_days_20"]:
    r = base[base.metric == m].iloc[0]
    print(f"agent_b no-fill ratio {m}: {r.ratio_recon_missing:.3f} (claim 30-37%)")
print("agent_b days>25 ratio (outside claimed band, reported for completeness):",
      f"{base[base.metric=='exceed_days_25'].iloc[0].ratio_recon_missing:.3f}")
print("\nagent_a climatology-default risk-policy reductions (budget_combined.csv):")
for m, claim in [("degree_days_10", -17.9), ("exceed_20_days", -22.2), ("exceed_25_days", -42.5),
                 ("amplitude", -33.8), ("summer_mean", -23.0), ("annual_mean", "slightly positive")]:
    v = float(ba.loc[ba.policy == "risk", "r_" + m].iloc[0]) * 100
    print(f"  {m}: {v:+.2f}% (claim {claim})")

# --------------------------------------------------------------------------
# linear-interpolation baseline
# --------------------------------------------------------------------------
import pyarrow.parquet as pq
pf = pq.ParquetFile(f"{TA}/reconstruction_series.parquet")
cols = pf.schema.names
interp_present = any("interp" in c.lower() or "pchip" in c.lower() or "linear" in c.lower() for c in cols)
print("\nlinear-interp baseline computable:", interp_present,
      "(parquet cols:", cols, ")")
print("agent_a placement_thermal_metrics.csv cols:", list(pd.read_csv(f"{TA}/placement_thermal_metrics.csv", nrows=1).columns))
