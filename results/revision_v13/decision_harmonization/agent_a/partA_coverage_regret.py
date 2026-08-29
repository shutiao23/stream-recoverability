"""Part A: fixed-coverage model-selection coverage-regret curves (t09 Part-2 data).

Reproduces the t09 agent_a reference results (no-abstention full panel and the
support-any+ambiguity abstention set) and computes NEW fixed-coverage
coverage-regret curves: released sets = top c fraction of units ranked by a
confidence criterion, c in {0.1..0.9, 1.0}, plus the current 8.5% abstention
point (123 units). Methods evaluated on each released set: proposed selector
(lambda=0.5), best-fixed family (dev), global blocked-CV, per-network avg-CV,
gap-length rule, random (seed 42), oracle.

All regret definitions follow results/revision_v12/t09_decision_utility/agent_a
(REPORT.md + scripts/rev_v12_t09_decision_utility_a.py): per-unit regret =
L(selected) - min_f L(f); network-balanced regret = mean over networks WITH at
least one released unit of the within-network mean per-unit regret; pooled
regret = mean per-unit regret over all released units.

Deterministic: numpy seed 42 for the random comparator and any tie-breaking;
no training, no network, no file writes outside this directory.
"""

import numpy as np
import pandas as pd

SEED = 42
RNG = np.random.default_rng(SEED)
LAMBDA = 0.5
N_UNITS = 1440
FAMILIES = ["seasonal_ridge", "donor_ridge", "xgboost"]
FAM_FULL = ["seasonal_boundary_ridge", "donor_blup_ridge", "xgboost_b_d"]
OUT = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v13/decision_harmonization/agent_a"
T09 = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v12/t09_decision_utility/agent_a"
RV = "/home/lzq/workspace/parttime/stream-recoverability/results/development_v11/reviewer_completion"
T5 = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v12/t05_model_matrix/agent_a"

# --------------------------------------------------------------------------
# load panel
# --------------------------------------------------------------------------
S = pd.read_csv(f"{T09}/selection_predictions_part2.csv")
assert len(S) == N_UNITS
for f in FAMILIES:
    S[f"pen_{f}"] = S[f"risk_{f}"] + LAMBDA * S[f"width_{f}"]
pen = S[[f"pen_{f}" for f in FAMILIES]].to_numpy()
S["pen_best"] = pen.min(axis=1)
S["pen_second"] = np.partition(pen, 1, axis=1)[:, 1]
S["margin"] = S["pen_second"] - S["pen_best"]
S["mean_width"] = S[[f"width_{f}" for f in FAMILIES]].mean(axis=1)
S["n_unit_support"] = sum((S[f"support_{f}"] == "unit").astype(int) for f in FAMILIES)

loss = S[[f"loss_{f}" for f in FAMILIES]].to_numpy()
min_loss = loss.min(axis=1)
true_best = loss.argmin(axis=1)
S["true_best_idx"] = true_best
top2 = np.argsort(loss, axis=1)[:, :2]
# t09 penalized-risk top-2 (lambda=0.5) containing the true best (proposed only)
pen_top2 = np.argsort(pen, axis=1)[:, :2]
pen_hit = np.array([true_best[i] in pen_top2[i] for i in range(N_UNITS)])

netcodes = S["network_id"].to_numpy()
net_names = S["network_id"].unique()

# --------------------------------------------------------------------------
# per-unit selections of the comparators
# --------------------------------------------------------------------------
sel = {}

# proposed selector, lambda = 0.5 (from the t09 artifact, argmin risk + 0.5*width)
sel["proposed"] = np.array([FAMILIES.index(v) for v in S["selected_lambda0.5"]], dtype=int)

# best fixed family chosen on development outcomes
dev_rost = pd.read_csv(f"{RV}/development_model_roster_losses.csv",
                       dtype={"network_id": str, "station_id": str})
dev_rost["gap_length"] = dev_rost["gap_length"].astype(float)
dev_means = dev_rost.groupby("model_family")["mae_deg_c"].mean()
best_fixed_full = dev_means.idxmin()
bf_idx = FAM_FULL.index(best_fixed_full)
sel["best_fixed"] = np.full(N_UNITS, bf_idx, dtype=int)
print("best fixed family on dev:", best_fixed_full)

# global blocked-CV: leave-one-network-out on pooled dev+first roster
roster = pd.read_csv(f"{RV}/confirmation_model_roster_losses.csv",
                     dtype={"network_id": str, "station_id": str})
unit_loss = roster.groupby(["network_id", "station_id", "gap_length",
                            "model_family"])["mae_deg_c"].mean().reset_index()
dev_unit = dev_rost.groupby(["network_id", "station_id", "gap_length",
                             "model_family"])["mae_deg_c"].mean().reset_index()
pool = pd.concat([dev_unit, unit_loss])
pool["netcode"] = pd.Categorical(pool.network_id).codes
cv_est = {}
for f in FAM_FULL:
    sub = pool[pool.model_family == f]
    cv_est[f] = float(np.mean([sub.loc[sub.netcode != c, "mae_deg_c"].mean()
                               for c in sub.netcode.unique()]))
global_cv_full = min(cv_est, key=cv_est.get)
sel["global_cv"] = np.full(N_UNITS, FAM_FULL.index(global_cv_full), dtype=int)
print("global blocked-CV family:", global_cv_full)

# per-network avg-CV: per first-panel network, LOOCV mean prediction on the
# network's own roster units (exact t09 definition)
pn_idx = np.full(N_UNITS, -1, dtype=int)
for c in np.unique(S["network_code"].to_numpy()):
    nidx = np.where(S["network_code"].to_numpy() == c)[0]
    yv = loss[nidx]
    est = {}
    for j, f in enumerate(FAMILIES):
        est[f] = float(np.mean([np.mean(np.delete(yv[:, j], i))
                                for i in range(len(yv))]))
    pn_idx[nidx] = FAMILIES.index(min(est, key=est.get))
sel["per_net_cv"] = pn_idx

# gap-length rule: argmin of the raw pooled per-family duration curve at the
# unit's gap (reconstructed exactly as in the t09 script)
def isotonic_curve_log(gaps, vals):
    order = np.argsort(gaps)
    g = gaps[order]
    v = vals[order]
    while True:
        d = np.diff(v)
        bad = np.where(d < -1e-12)[0]
        if len(bad) == 0:
            break
        i = bad[0]
        wsum = v[i] + v[i + 1]
        v[i] = wsum / 2.0
        v[i + 1] = wsum / 2.0
        g = np.concatenate([g[: i + 1], g[i + 2 :]])
        v = np.concatenate([v[: i + 1], v[i + 2 :]])
    return g, v

def eval_curve_log(g_knots, v_knots, lg):
    lg = np.atleast_1d(np.asarray(lg, dtype=float))
    out = np.empty_like(lg)
    n = len(g_knots)
    for i, x in enumerate(lg):
        if x <= g_knots[0]:
            out[i] = v_knots[0]
        elif x >= g_knots[-1]:
            if n >= 2:
                slope = (v_knots[-1] - v_knots[-2]) / (g_knots[-1] - g_knots[-2])
                out[i] = v_knots[-1] + slope * (x - g_knots[-1])
            else:
                out[i] = v_knots[-1]
        else:
            j = np.searchsorted(g_knots, x, side="right") - 1
            t = (x - g_knots[j]) / (g_knots[j + 1] - g_knots[j])
            out[i] = v_knots[j] + t * (v_knots[j + 1] - v_knots[j])
    return out

dev_fl = pd.read_csv(f"{RV}/development_empirical_fit_losses.csv",
                     dtype={"network_id": str, "station_id": str})
conf_fl = pd.read_csv(f"{RV}/confirmation_empirical_fit_losses.csv",
                      dtype={"network_id": str, "station_id": str})
stress = pd.read_csv(f"{T5}/source_fit_stress_families_1_3.csv",
                     dtype={"network_id": str, "station_id": str})
stress_data = {}
for f in FAM_FULL:
    if f == "xgboost_b_d":
        dd = pd.concat([dev_fl[["network_id", "station_id", "gap_length", "mae_deg_c"]],
                        conf_fl[["network_id", "station_id", "gap_length", "mae_deg_c"]]])
    else:
        dd = stress[stress.model_family == f][["network_id", "station_id", "gap_length", "mae_deg_c"]]
    dd = dd.dropna(subset=["mae_deg_c"])
    dd["lg"] = np.log(dd.gap_length)
    dd["y"] = np.log1p(dd.mae_deg_c)
    stress_data[f] = dd
family_curves = {}
for f in FAM_FULL:
    df = pd.DataFrame({"lg": stress_data[f]["lg"].to_numpy(),
                       "y": stress_data[f]["y"].to_numpy()})
    gs = df.groupby("lg")["y"].mean()
    family_curves[f] = isotonic_curve_log(gs.index.to_numpy(), gs.to_numpy())
gap_rule_idx = np.full(N_UNITS, -1, dtype=int)
for i, g in enumerate(S["gap_length"].to_numpy().astype(float)):
    vals = [float(np.expm1(eval_curve_log(*family_curves[f], np.log(g))[0]))
            for f in FAM_FULL]
    gap_rule_idx[i] = int(np.argmin(vals))
sel["gap_rule"] = gap_rule_idx

# random selection, seed 42: t09 convention = mean over 20 seeded draws
# (RNG_SEED=42 in the t09 script); kept for exact comparability.
RAND_N_DRAWS = 20
rand_draws = RNG.integers(0, 3, size=(RAND_N_DRAWS, N_UNITS))
sel["random"] = rand_draws.mean(axis=0).round().astype(int)

# oracle: true best family per unit
sel["oracle"] = true_best

sel_df = pd.DataFrame(sel)
METHODS = list(sel.keys())

# --------------------------------------------------------------------------
# metric functions
# --------------------------------------------------------------------------
def unit_regret_matrix():
    reg = np.empty((N_UNITS, len(METHODS) + RAND_N_DRAWS))
    for j, m in enumerate(METHODS):
        reg[:, j] = loss[np.arange(N_UNITS), sel[m]] - min_loss
    for d in range(RAND_N_DRAWS):
        reg[:, len(METHODS) + d] = loss[np.arange(N_UNITS), rand_draws[d]] - min_loss
    return reg

REG = unit_regret_matrix()
RAND_COL0 = len(METHODS)

def reg_metrics_from(reg, selv, released):
    nets_rel = np.unique(netcodes[released])
    net_means = [reg[netcodes[released] == nc].mean() for nc in nets_rel]
    nb = float(np.mean(net_means))
    po = float(reg.mean())
    acc = float(np.mean(selv[released] == true_best[released]))
    t2 = float(np.mean([selv[i] in top2[i] for i in np.where(released)[0]]))
    return nb, po, acc, t2

def released_metrics(released, method):
    """All metrics for one released set and one method (random = mean over draws)."""
    if method != "random":
        j = METHODS.index(method)
        return reg_metrics_from(REG[released, j], sel[method], released)
    vals = [reg_metrics_from(REG[released, RAND_COL0 + d], rand_draws[d], released)
            for d in range(RAND_N_DRAWS)]
    return tuple(float(np.mean([v[k] for v in vals])) for k in range(4))

def summary_row(released, method, criterion, c, note=""):
    nb, po, acc, t2 = released_metrics(released, method)
    t2p = float(pen_hit[released].mean()) if method == "proposed" else np.nan
    n_rel = int(released.sum())
    nets_rel = np.unique(netcodes[released])
    return {
        "criterion": criterion,
        "c": c,
        "method": method,
        "released_units": n_rel,
        "released_networks": len(nets_rel),
        "unit_coverage": n_rel / N_UNITS,
        "network_coverage": len(nets_rel) / len(net_names),
        "network_balanced_regret": nb,
        "pooled_regret": po,
        "selection_accuracy": acc,
        "top2_hit": t2,
        "top2_hit_pen_t09": t2p,
        "abstention_cost_units": 1 - n_rel / N_UNITS,
        "abstention_cost_networks": 1 - len(nets_rel) / len(net_names),
        "note": note,
    }

# --------------------------------------------------------------------------
# reference reproduction checks
# --------------------------------------------------------------------------
rows = []
all_mask = np.ones(N_UNITS, dtype=bool)
ref = pd.read_csv(f"{T09}/selection_regret_table_part2.csv")
ref_map = {"proposed": "proposed_risk", "best_fixed": "best_fixed_dev",
           "global_cv": "global_blockedCV", "per_net_cv": "per_network_avgCV",
           "gap_rule": "gap_length_rule"}
print("\n== reproduction vs t09 selection_regret_table_part2.csv (no abstention) ==")
for m, rn in ref_map.items():
    nb, po, acc, t2 = released_metrics(all_mask, m)
    refv = ref[(ref.selector == rn) & (ref.abstention == "none")]
    if rn == "proposed_risk":
        refv = refv[refv["lambda"] == 0.5]
    refv = refv.net_balanced_regret.iloc[0]
    print(f"{m:10s} net-balanced {nb:.6f} (ref {refv:.6f})  pooled {po:.6f}")

# support-any + ambiguity (delta=0.10, lambda=0.5) released set
amb = S["pen_second"] <= 1.10 * S["pen_best"]
supany = S["n_unit_support"] == 3
rel85 = (~amb) & supany
print("\n8.5% set: released", rel85.sum(), "networks", np.unique(netcodes[rel85]).size)
ref85 = pd.read_csv(f"{T09}/abstention_comparison_part2.csv")
ref85 = ref85[ref85.abstention == "ambiguous+support_any"].iloc[0]
r85_map = {"proposed": "proposed_net_balanced_regret",
           "best_fixed": "best_fixed_net_balanced_regret",
           "global_cv": "global_cv_net_balanced_regret",
           "per_net_cv": "per_net_cv_net_balanced_regret",
           "gap_rule": "gap_rule_net_balanced_regret",
           "random": "random_net_balanced_regret"}
for m, col in r85_map.items():
    nb, po, acc, t2 = released_metrics(rel85, m)
    tag = ""
    if m == "random":
        tag = f"  (t09 published value = pooled mean over draws; ours pooled={po:.6f})"
    print(f"{m:10s} net-balanced {nb:.6f} (ref {ref85[col]:.6f}){tag}")

# --------------------------------------------------------------------------
# fixed-coverage released sets
# --------------------------------------------------------------------------
order_key = {
    "a_ambiguity_margin": S[["margin", "network_id", "station_id", "gap_length"]]
    .sort_values(["margin", "network_id", "station_id", "gap_length"],
                 ascending=[False, True, True, True]).index.to_numpy(),
    "b_mean_width": S[["mean_width", "network_id", "station_id", "gap_length"]]
    .sort_values(["mean_width", "network_id", "station_id", "gap_length"],
                 ascending=[True, True, True, True]).index.to_numpy(),
    "c_support_completeness": S[["n_unit_support", "margin", "network_id", "station_id", "gap_length"]]
    .sort_values(["n_unit_support", "margin", "network_id", "station_id", "gap_length"],
                 ascending=[False, False, True, True, True]).index.to_numpy(),
}
CS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

for crit, idx in order_key.items():
    for c in CS:
        k = int(round(c * N_UNITS))
        released = np.zeros(N_UNITS, dtype=bool)
        released[idx[:k]] = True
        for m in METHODS:
            rows.append(summary_row(released, m, crit, c))

for m in METHODS:
    rows.append(summary_row(rel85, m, "current_85pct", float(rel85.sum()) / N_UNITS,
                            "support-any + ambiguity abstention set (lambda=0.5, delta=0.10)"))

curve = pd.DataFrame(rows)
curve.to_csv(f"{OUT}/coverage_regret_curve.csv", index=False)

# --------------------------------------------------------------------------
# comparators table
# --------------------------------------------------------------------------
comp_rows = []
for m in METHODS:
    sub = curve[(curve.method == m) & (curve.criterion != "current_85pct")]
    g = sub[sub.c.isin([0.5, 0.7, 1.0])].pivot(index="criterion", columns="c", values="network_balanced_regret")
    r50 = float(g.loc[:, 0.5].mean())
    r70 = float(g.loc[:, 0.7].mean())
    r100 = float(g.loc[:, 1.0].mean())
    grid = sub[(sub.c >= 0.1) & (sub.c < 1.0)]
    imin = grid["network_balanced_regret"].idxmin()
    r85 = float(curve[(curve.method == m) & (curve.criterion == "current_85pct")].network_balanced_regret.iloc[0])
    comp_rows.append({
        "method": m,
        "regret_no_abstention": r100,
        "regret_at_50": r50,
        "regret_at_70": r70,
        "regret_at_85pct_point": r85,
        "min_regret_any_c": float(grid.loc[imin, "network_balanced_regret"]),
        "min_c": float(grid.loc[imin, "c"]),
        "min_criterion": grid.loc[imin, "criterion"],
        "oracle_headroom": float(grid.loc[imin, "network_balanced_regret"]),
    })
comp = pd.DataFrame(comp_rows)
comp.to_csv(f"{OUT}/comparators_table.csv", index=False)

# --------------------------------------------------------------------------
# selection frequency (per method x c x criterion)
# --------------------------------------------------------------------------
freq_rows = []
for crit, idx in order_key.items():
    for c in [0.1, 0.5, 0.7, 0.9, 1.0]:
        k = int(round(c * N_UNITS))
        released = np.zeros(N_UNITS, dtype=bool)
        released[idx[:k]] = True
        for j, m in enumerate(METHODS):
            subsel = sel[m][released]
            for fi, f in enumerate(FAMILIES):
                freq_rows.append({"method": m, "criterion": crit, "c": c,
                                  "family": f, "share": float(np.mean(subsel == fi))})
for j, m in enumerate(METHODS):
    subsel = sel[m][rel85]
    for fi, f in enumerate(FAMILIES):
        freq_rows.append({"method": m, "criterion": "current_85pct", "c": float(rel85.sum()) / N_UNITS,
                          "family": f, "share": float(np.mean(subsel == fi))})
freq = pd.DataFrame(freq_rows)
freq.to_csv(f"{OUT}/selection_frequency.csv", index=False)

# --------------------------------------------------------------------------
# summary markdown (key rows)
# --------------------------------------------------------------------------
def fmt(x):
    return f"{x:.4f}"

lines = ["# Fixed-coverage coverage-regret summary (Part A)",
         "",
         "Released sets: top c fraction of the 1,440 first-panel units ranked by a",
         "confidence criterion (a) ambiguity margin (desc), (b) mean width (asc),",
         "(c) support completeness = # families with unit-level fitting-period stress",
         "(desc, then margin desc). k = round(c*1440). Regret definition identical to",
         "t09: per-unit regret = L(selected) - min_f L(f); network-balanced regret =",
         "mean over networks with >=1 released unit of within-network mean regret.",
         "The current 8.5% point = the t09 support-any + ambiguity (delta=0.10,",
         "lambda=0.5) abstention set: 123 units, 8 networks, regret 0.0067.",
         "",
         "| method | c | criterion | released_units | released_networks | unit_cov | net_cov | net_balanced_regret | pooled_regret | sel_acc | top2_hit |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
for m in ["proposed", "best_fixed", "global_cv", "per_net_cv", "gap_rule", "random", "oracle"]:
    for crit in ["a_ambiguity_margin", "b_mean_width", "c_support_completeness"]:
        for c in [0.5, 0.7]:
            r = curve[(curve.method == m) & (curve.criterion == crit) & (curve.c == c)].iloc[0]
            lines.append(f"| {m} | {c} | {crit} | {r.released_units} | {r.released_networks} | "
                         f"{fmt(r.unit_coverage)} | {fmt(r.network_coverage)} | "
                         f"{fmt(r.network_balanced_regret)} | {fmt(r.pooled_regret)} | "
                         f"{fmt(r.selection_accuracy)} | {fmt(r.top2_hit)} |")
lines += ["",
          "Reference points:",
          ""]
r = curve[(curve.criterion == "current_85pct")]
lines.append("| method | released_units | released_networks | net_balanced_regret | pooled_regret | sel_acc | top2_hit |")
lines.append("|---|---|---|---|---|---|---|")
for _, row in r.iterrows():
    lines.append(f"| {row.method} | {row.released_units} | {row.released_networks} | "
                 f"{fmt(row.network_balanced_regret)} | {fmt(row.pooled_regret)} | "
                 f"{fmt(row.selection_accuracy)} | {fmt(row.top2_hit)} |")
lines += ["",
          "No-abstention (c=1.0, all 1,440 units):",
          ""]
lines.append("| method | net_balanced_regret | pooled_regret | sel_acc | top2_hit |")
lines.append("|---|---|---|---|---|")
for m in METHODS:
    r = curve[(curve.method == m) & (curve.c == 1.0)].iloc[0]
    lines.append(f"| {m} | {fmt(r.network_balanced_regret)} | {fmt(r.pooled_regret)} | "
                 f"{fmt(r.selection_accuracy)} | {fmt(r.top2_hit)} |")
with open(f"{OUT}/coverage_regret_summary.md", "w") as fh:
    fh.write("\n".join(lines) + "\n")

print("\nwrote coverage_regret_curve.csv, coverage_regret_summary.md, comparators_table.csv, selection_frequency.csv")
