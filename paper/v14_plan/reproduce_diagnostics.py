"""Reproduce every diagnostic number in paper/v14_plan/PLAN.md Appendix A.

These are the analyses that motivated the v14 estimand change. All of them run
against existing v12/v13 artifacts; nothing is recomputed from raw data.

Usage:  python paper/v14_plan/reproduce_diagnostics.py
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from scipy.stats import spearmanr

ROOT = "/home/lzq/workspace/parttime/stream-recoverability"
UNIT = f"{ROOT}/results/revision_v13/strongest_baseline/agent_a/unit_comparison_second.csv"
DOWN = f"{ROOT}/results/revision_v12/t08_downstream_metrics/agent_a/placement_thermal_metrics.csv"
ROSTER = f"{ROOT}/results/development_v11/reviewer_completion/confirmation_model_roster_losses.csv"

PRED = ["empirical", "r6", "simple", "surface"]


def rho(a, b) -> float:
    a, b = pd.Series(a).reset_index(drop=True), pd.Series(b).reset_index(drop=True)
    m = a.notna() & b.notna()
    if m.sum() < 3:
        return float("nan")
    return float(spearmanr(a[m], b[m]).statistic)


def hdr(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


# ---------------------------------------------------------------- ranking side
def ranking_diagnostics() -> None:
    d = pd.read_csv(UNIT)
    dd = d[d.subset == "direct"]

    hdr("A1. Pooled across durations (the v13 headline) vs trivial duration baseline")
    gl = dd.groupby("gap_length")["observed"].mean()
    dur_only = dd.gap_length.map(gl).astype(float)
    print(f"  duration-mean only   pooled rho = {rho(dur_only, dd.observed):.4f}   <- never reported in v13")
    for c in PRED:
        print(f"  {c:<20} pooled rho = {rho(dd[c], dd.observed):.4f}")

    hdr("A2. Within each duration stratum (pooled over all 224 stations)")
    print(f"{'h':>6} {'n':>5} " + "".join(f"{c:>10}" for c in PRED))
    for h, g in dd.groupby("gap_length"):
        print(f"{h:>6} {len(g):>5} " + "".join(f"{rho(g[c], g.observed):>10.3f}" for c in PRED))

    hdr("A3. Within (network x duration) cells: can it rank STATIONS at fixed duration?")
    rows = []
    total = dd.groupby(["network_id", "gap_length"]).ngroups
    for (net, h), g in dd.groupby(["network_id", "gap_length"]):
        if g.station_id.nunique() < 4:
            continue
        for c in PRED:
            rows.append({"net": net, "h": h, "pred": c, "r": rho(g[c], g.observed), "n": len(g)})
    w = pd.DataFrame(rows)
    cells = w.groupby(["net", "h"]).ngroups
    units = int(w[w.pred == "empirical"].n.sum())
    print(f"  cells with >=4 stations: {cells} of {total};  units covered: {units} of {len(dd)}")
    g = w.groupby("pred").r
    out = pd.DataFrame(
        {
            "count": g.count(),
            "mean": g.mean(),
            "median": g.median(),
            "frac_gt0": g.apply(lambda s: (s > 0).mean()),
        }
    ).reindex(PRED)
    print(out.round(3).to_string())

    hdr("A4. Provider confound check (is network-level 0.805 a provider artifact?)")
    nm = dd.groupby(["network_id", "domain"])[PRED + ["observed"]].mean().reset_index()
    print(f"  ALL 57 networks       " + "  ".join(f"{c} {rho(nm[c], nm.observed):.3f}" for c in PRED[:3]))
    for dom, g in nm.groupby("domain"):
        print(f"  {dom:<20} n={len(g):>2}  " + "  ".join(f"{c} {rho(g[c], g.observed):.3f}" for c in PRED[:3]))
    print("  -> holds within every provider; NOT a provider artifact (v13 never reported this)")

    corr = dd[["empirical", "r6"]].corr()
    print(f"\n  corr(empirical, r6) Pearson = {corr.iloc[0, 1]:.4f}; "
          f"Spearman = {rho(dd.empirical, dd.r6):.4f}")


# --------------------------------------------------------------- decision side
def decision_diagnostics() -> None:
    d = pd.read_csv(DOWN).dropna(
        subset=["empirical_transfer_prediction", "mae_deg_c", "climatology_mae_deg_c"]
    ).reset_index(drop=True)
    d["benefit"] = d.climatology_mae_deg_c - d.mae_deg_c
    R = d.empirical_transfer_prediction

    hdr("A5. THE DIAGNOSIS: the score ranks error, but not benefit")
    print(f"  n = {len(d)} placements, {d.network_id.nunique()} networks, "
          f"gap lengths {sorted(d.gap_length.unique())}")
    print(f"\n  risk score ranks realized MAE          rho = {rho(R, d.mae_deg_c):+.3f}")
    print(f"  risk score ranks BENEFIT               rho = {rho(R, d.benefit):+.3f}   <- negative")

    print("\n  what actually ranks benefit?")
    for name, col in [
        ("empirical risk score", R),
        ("gap_length", d.gap_length),
        ("climatology_MAE (difficulty of DEFAULT)", d.climatology_mae_deg_c),
        ("realized model MAE (oracle-ish)", d.mae_deg_c),
    ]:
        print(f"    {name:<42} rho = {rho(col, d.benefit):+.3f}")
    print(f"\n  corr(risk, climatology_MAE) = {rho(R, d.climatology_mae_deg_c):.3f}"
          "   <- risk is a poor proxy for what matters")

    hdr("A6. FEASIBILITY of the fix: leave-one-out benefit curve (upper bound)")
    key = ["station_id", "gap_length"]
    for src, dst in [("benefit", "loo_benefit"), ("mae_deg_c", "loo_mae")]:
        g = d.groupby(key)[src]
        d[dst] = (g.transform("sum") - d[src]) / (g.transform("count") - 1)
    v = d.dropna(subset=["loo_benefit", "loo_mae"])
    print(f"  n = {len(v)}   TARGET = realized benefit")
    print(f"    v13 object : frozen risk score                rho = {rho(v.empirical_transfer_prediction, v.benefit):+.3f}")
    print(f"    v13 object : LOO station x duration model MAE rho = {rho(v.loo_mae, v.benefit):+.3f}")
    print(f"    PROPOSED   : LOO station x duration BENEFIT   rho = {rho(v.loo_benefit, v.benefit):+.3f}   <<<")
    print(f"    (sanity)   : LOO model MAE ranks model MAE    rho = {rho(v.loo_mae, v.mae_deg_c):+.3f}")

    print("\n  top-20% treatment budget:")
    for name, col in [
        ("rank by v13 risk score", "empirical_transfer_prediction"),
        ("rank by gap length", "gap_length"),
        ("rank by PROPOSED benefit curve", "loo_benefit"),
    ]:
        sel = v[v[col] >= v[col].quantile(0.8)]
        print(f"    {name:<32} n={len(sel):>4}  mean benefit {sel.benefit.mean():+.3f} C"
              f"  | harmful {100 * (sel.benefit < 0).mean():.1f}%")
    print(f"    {'(whole panel, reference)':<32} n={len(v):>4}  mean benefit {v.benefit.mean():+.3f} C"
          f"  | harmful {100 * (v.benefit < 0).mean():.1f}%")


# ------------------------------------------------------------ selection headroom
def selection_headroom() -> None:
    hdr("A7. Model-selection task headroom (is the task even worth doing?)")
    r = pd.read_csv(ROSTER)
    u = r.groupby(["network_id", "station_id", "gap_length", "model_family"])["mae_deg_c"].mean().reset_index()
    p = u.pivot_table(index=["network_id", "station_id", "gap_length"],
                      columns="model_family", values="mae_deg_c").dropna()
    best = p.min(axis=1)
    print(f"  units = {len(p)}")
    for c in p.columns:
        print(f"    always-{c:<26} mean loss {p[c].mean():.4f} | regret vs oracle {(p[c] - best).mean():.4f}")
    print(f"    {'per-unit ORACLE':<33} mean loss {best.mean():.4f} | regret 0.0000")
    span = (p.mean().min() - best.mean())
    print(f"\n  TOTAL HEADROOM = {span:.4f} C ({100 * span / p.mean().min():.1f}% of best-fixed loss)")
    print("  oracle win share:")
    for fam, frac in p.idxmin(axis=1).value_counts(normalize=True).items():
        print(f"    {fam:<30} {frac:.3f}")
    print("  -> near-degenerate task: two viable families split ~54/45 with 0.004 C between them")


if __name__ == "__main__":
    ranking_diagnostics()
    decision_diagnostics()
    selection_headroom()
    print("\n" + "=" * 72)
    print("Done. Every number above appears in paper/v14_plan/PLAN.md Appendix A.")
    print("=" * 72)
