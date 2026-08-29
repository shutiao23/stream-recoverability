#!/usr/bin/env python3
"""Part A — fixed-coverage model-selection coverage-regret curves (v13 decision harmonization, agent_b).

Input  (read-only): results/revision_v12/t09_decision_utility/agent_a/selection_predictions_part2.csv
                     results/revision_v12/t09_decision_utility/agent_a/selection_calibration_part2.csv
Outputs (this dir): coverage_regret_curve.csv, comparators_table.csv, selection_frequency.csv,
                     coverage_regret_summary.md (written by this script), plus reproduction check rows
                     appended to REPORT.md by the caller.

Regret definition (reused from t09 agent_a REPORT.md, verified bit-for-bit):
  - Unit = (network, station, gap). Per-family loss = outer roster loss (loss_<family> column).
  - Per-unit regret = loss(selected family) - min_f loss_f.
  - Network-balanced regret = mean over networks of within-network mean regret.
  - t09 convention: mean over all 42 networks (0 regret for empty networks).
    This analysis additionally reports the released-network convention: mean over networks
    with >= 1 released unit only. coverage_regret_curve.csv uses the released-network
    convention (networks with zero released units are "not released", per spec).
  - Lambda = 0.5 primary (t09 headline lambda; verified: selected_lambda0.5 == argmin risk+0.5*width
    on 100% of units; no-abstention net-balanced regret 0.0849530 reproduces).
  - Ambiguity (t09): ambiguous iff 2nd-smallest penalized risk <= 1.10 * smallest.
  - Support-any abstention: any family with support == 'curve'.
  - Verified reproductions (see REPORT.md): best-fixed xgboost 0.0814985; global CV 0.0814985;
    per-network CV (full-roster per-network argmin mean loss) 0.0382955; gap rule
    (argmin of reconstructed duration curve C_f(g)) 0.0926710; support_any+ambiguity released
    set = 123 units / 8 networks, net-balanced regret 0.0067202.
  - top2_hit (curve CSV): share of released units where the selected family's loss is within the
    two smallest losses (method-agnostic). The t09 definition (true-best within top-2 penalized
    risks, proposed only) reproduces 0.8965 at the no-abstention point and is reported separately.

Fixed-coverage design:
  Released set = top c fraction of units ranked by a confidence criterion
    (a) ambiguity_margin: 2nd-smallest penalized risk - smallest penalized risk (lambda=0.5), descending;
    (b) mean_width: mean over families of interval width, ascending;
    (c) support_completeness: # families with unit-level support (0-3), descending, tie-break
        ambiguity margin descending, then stable unit order.
  c in {0.1, 0.2, ..., 0.9} (n = round(c*1440); all c*1440 integral) + c=1.0 no-abstention point
  + the t09 8.5% abstention point (criterion 'abstention_rule': released = not ambiguous AND
  all families unit-supported; c = 123/1440 = 0.0854).

Methods (selection within released set):
  proposed       argmin penalized risk, lambda=0.5 (verified == selected_lambda0.5)
  best_fixed     xgboost (dev-chosen best family, t09)
  global_cv      xgboost (leave-one-network-out blocked CV; identical choice on this panel)
  per_network_cv per-network argmin of full-roster mean loss (t09 convention, verified 0.1636 on
                 the 123-unit set)
  gap_rule       per-unit argmin of reconstructed duration curve C_f(g) (verified 0.0926710
                 no-abstention; 0.1447 on the 123-unit set)
  random         seeded uniform draw per unit (RandomState(42)), single deterministic draw
  oracle         per-unit true best family (zero regret, accuracy 1)

Deterministic seeds: 42. No training, no network writes.
"""
import numpy as np
import pandas as pd

RNG = 42
LAM = 0.5
OUT = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v13/decision_harmonization/agent_b"
T09 = "/home/lzq/workspace/parttime/stream-recoverability/results/revision_v12/t09_decision_utility/agent_a"

df = pd.read_csv(f"{T09}/selection_predictions_part2.csv")
cal = pd.read_csv(f"{T09}/selection_calibration_part2.csv")
cal["family"] = cal["family"].map(
    {"seasonal_boundary_ridge": "seasonal_ridge", "donor_blup_ridge": "donor_ridge", "xgboost_b_d": "xgboost"}
)
FAMS = ["seasonal_ridge", "donor_ridge", "xgboost"]
N = len(df)
loss = df[[f"loss_{f}" for f in FAMS]].values
min_loss = loss.min(axis=1)
nets = df["network_id"].values
gap = df["gap_length"].values

# ---------- derived quantities (lambda = 0.5) ----------
pen = np.column_stack([df[f"risk_{f}"] + LAM * df[f"width_{f}"] for f in FAMS])
pen_sorted = np.sort(pen, axis=1)
ambiguity_margin = pen_sorted[:, 1] - pen_sorted[:, 0]
ambiguous = pen_sorted[:, 1] <= 1.10 * pen_sorted[:, 0]
support_unit = np.column_stack([df[f"support_{f}"] == "unit" for f in FAMS])
n_unit_support = support_unit.sum(axis=1)
support_any_missing = (n_unit_support < 3)
mean_width = df[[f"width_{f}" for f in FAMS]].mean(axis=1).values

# reconstructed duration curve C_f(g) (exact: inversion of the recalibration on curve-support
# units, per-gap median; within-gap sd of inverted values ~1e-14)
C = {}
for f in FAMS:
    a, b = cal.loc[cal["family"] == f, ["intercept", "slope"]].values[0]
    inv = (df[f"risk_{f}"] - a) / b
    C[f] = {}
    for g, idx in df.groupby("gap_length").groups.items():
        curv = idx[df.loc[idx, f"support_{f}"] == "curve"]
        C[f][g] = inv.loc[curv].median()

# ---------- per-unit selections per method ----------
def reg(u_idx, sel_fam):
    """Per-unit regret vector on unit indices u_idx given family labels."""
    s = np.array([FAMS.index(x) for x in sel_fam])
    return loss[u_idx, s] - min_loss[u_idx]

sel = {}
sel["proposed"] = df["selected_lambda0.5"].values
sel["best_fixed"] = np.full(N, "xgboost")
sel["global_cv"] = np.full(N, "xgboost")
per_net_full = {}
for net, idx in df.groupby("network_id").groups.items():
    per_net_full[net] = FAMS[loss[idx].mean(axis=0).argmin()]
sel["per_network_cv"] = np.array([per_net_full[n] for n in nets])
sel["gap_rule"] = np.array([FAMS[np.argmin([C[f][g] for f in FAMS])] for g in gap])
rng = np.random.RandomState(RNG)
sel["random"] = np.array([FAMS[i] for i in rng.randint(0, 3, size=N)])
sel["oracle"] = np.array([FAMS[i] for i in loss.argmin(axis=1)])

# ---------- confidence rankings ----------
def rank_by(key, ascending):
    """Stable rank: sort by key then by original unit index (deterministic)."""
    order = np.lexsort((np.arange(N), key)) if not ascending else np.lexsort((np.arange(N), key))
    rank = np.empty(N, dtype=int)
    rank[order] = np.arange(N)
    return rank

criteria = {}
criteria["ambiguity_margin"] = rank_by(-ambiguity_margin, False)      # largest margin first
criteria["mean_width"] = rank_by(mean_width, True)                     # smallest width first
# support completeness: #unit-support desc, then margin desc, then stable index
sc_key = -(n_unit_support.astype(float) * 1e9 + ambiguity_margin)  # lexicographic via float precision guard
order = np.lexsort((np.arange(N), -ambiguity_margin, -n_unit_support.astype(float)))
rank = np.empty(N, dtype=int)
rank[order] = np.arange(N)
criteria["support_completeness"] = rank

C_LIST = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
METHODS = ["proposed", "best_fixed", "global_cv", "per_network_cv", "gap_rule", "random", "oracle"]

# ---------- released-set metrics ----------
def evaluate(released_mask, method, net_bal_convention="released"):
    u = np.where(released_mask)[0]
    r = reg(u, sel[method][released_mask])
    released_nets = pd.Series(nets[released_mask])
    if len(u) == 0:
        return dict(released_units=0, released_networks=0, network_balanced_regret=np.nan,
                    pooled_regret=np.nan, selection_accuracy=np.nan, top2_hit=np.nan)
    if net_bal_convention == "released":
        nb = released_nets.groupby(released_nets).apply(lambda s: r[s.index].mean()).mean()
    else:  # t09 convention: mean over all 42 networks, 0 for empty
        nb = pd.Series(0.0, index=pd.Series(nets).unique())
        for net, s in released_nets.groupby(released_nets):
            nb[net] = r[s.index].mean()
        nb = nb.mean()
    sel_fam = sel[method][released_mask]
    true_best = np.array([FAMS[i] for i in loss[u].argmin(axis=1)])
    acc = (sel_fam == true_best).mean()
    loss_sel = loss[u, np.array([FAMS.index(x) for x in sel_fam])]
    second_min = np.partition(loss[u], 1, axis=1)[:, 1]
    top2 = (loss_sel <= second_min).mean()
    return dict(released_units=len(u), released_networks=released_nets.nunique(),
                network_balanced_regret=nb, pooled_regret=r.mean(),
                selection_accuracy=acc, top2_hit=top2)

# ---------- coverage-regret curve table ----------
rows = []
for crit_name, rank in criteria.items():
    for c in C_LIST:
        k = int(round(c * N))
        rel = rank < k
        for m in METHODS:
            ev = evaluate(rel, m)
            rows.append(dict(
                criterion=crit_name, c=c, method=m,
                released_units=ev["released_units"], released_networks=ev["released_networks"],
                unit_coverage=ev["released_units"] / N, network_coverage=ev["released_networks"] / 42,
                network_balanced_regret=ev["network_balanced_regret"], pooled_regret=ev["pooled_regret"],
                selection_accuracy=ev["selection_accuracy"], top2_hit=ev["top2_hit"],
                abstention_cost_units=1 - ev["released_units"] / N,
                abstention_cost_networks=1 - ev["released_networks"] / 42))
    # no-abstention point (c = 1.0)
    rel = np.ones(N, dtype=bool)
    for m in METHODS:
        ev = evaluate(rel, m)
        rows.append(dict(criterion=crit_name, c=1.0, method=m,
                         released_units=N, released_networks=42, unit_coverage=1.0,
                         network_coverage=1.0, network_balanced_regret=ev["network_balanced_regret"],
                         pooled_regret=ev["pooled_regret"], selection_accuracy=ev["selection_accuracy"],
                         top2_hit=ev["top2_hit"], abstention_cost_units=0.0, abstention_cost_networks=0.0))
# t09 8.5% abstention point (support_any + ambiguity), lambda=0.5
rel_abst = (~ambiguous) & (~support_any_missing)
for m in METHODS:
    ev = evaluate(rel_abst, m)
    rows.append(dict(criterion="abstention_rule", c=rel_abst.sum() / N, method=m,
                     released_units=ev["released_units"], released_networks=ev["released_networks"],
                     unit_coverage=ev["released_units"] / N, network_coverage=ev["released_networks"] / 42,
                     network_balanced_regret=ev["network_balanced_regret"], pooled_regret=ev["pooled_regret"],
                     selection_accuracy=ev["selection_accuracy"], top2_hit=ev["top2_hit"],
                     abstention_cost_units=1 - ev["released_units"] / N,
                     abstention_cost_networks=1 - ev["released_networks"] / 42))

curve = pd.DataFrame(rows)
curve.to_csv(f"{OUT}/coverage_regret_curve.csv", index=False)

# ---------- comparators table ----------
comp_rows = []
for crit_name in ["ambiguity_margin", "mean_width", "support_completeness"]:
    sub = curve[(curve["criterion"] == crit_name)]
    for m in METHODS:
        noa = sub[(sub["method"] == m) & (sub["c"] == 1.0)]["network_balanced_regret"].iloc[0]
        at50 = sub[(sub["method"] == m) & (sub["c"] == 0.5)]["network_balanced_regret"].iloc[0]
        at70 = sub[(sub["method"] == m) & (sub["c"] == 0.7)]["network_balanced_regret"].iloc[0]
        mc = sub[(sub["method"] == m)]["network_balanced_regret"].idxmin()
        min_reg = sub.loc[mc, "network_balanced_regret"]
        min_c = sub.loc[mc, "c"]
        oracle_at_c = sub[(sub["method"] == "oracle") & (sub["c"] == min_c)]["network_balanced_regret"].iloc[0]
        comp_rows.append(dict(
            criterion=crit_name, method=m, regret_no_abstention=noa, regret_at_50=at50,
            regret_at_70=at70, min_regret_any_c=min_reg, min_c=min_c,
            oracle_headroom=min_reg - oracle_at_c))
comparators = pd.DataFrame(comp_rows)
comparators.to_csv(f"{OUT}/comparators_table.csv", index=False)

# ---------- selection frequency ----------
freq_rows = []
for crit_name in ["ambiguity_margin", "mean_width", "support_completeness"]:
    rank = criteria[crit_name]
    for c in C_LIST + [1.0]:
        k = int(round(c * N))
        rel = rank < k
        for m in METHODS:
            sel_fam = sel[m][rel]
            for f in FAMS:
                freq_rows.append(dict(criterion=crit_name, method=m, c=c, family=f,
                                      share=(sel_fam == f).mean()))
freq = pd.DataFrame(freq_rows)
freq.to_csv(f"{OUT}/selection_frequency.csv", index=False)

# ---------- summary markdown ----------
def fmt(v, nd=4):
    return "nan" if pd.isna(v) else f"{v:.{nd}f}"

lines = ["# Fixed-coverage coverage-regret summary (Part A)",
         "",
         "Panels: 1,440 units, 42 networks, first panel (t09). Regret = per-unit outer-loss regret,",
         "network-balanced = mean over released networks of within-network mean (networks with zero",
         "released units count as not released). Lambda = 0.5 penalized risk. Full procedures in REPORT.md.",
         ""]
for crit in ["ambiguity_margin", "mean_width", "support_completeness"]:
    lines.append(f"## Criterion: {crit}")
    lines.append("")
    lines.append("| c | method | released | networks | net cov | net-bal regret | pooled regret | accuracy | top2 |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    for c in [0.5, 0.7, 1.0]:
        sub = curve[(curve["criterion"] == crit) & (curve["c"] == c)]
        for _, r in sub.iterrows():
            lines.append(f"| {c} | {r['method']} | {r['released_units']} | {r['released_networks']} | "
                         f"{fmt(r['network_coverage'])} | {fmt(r['network_balanced_regret'])} | "
                         f"{fmt(r['pooled_regret'])} | {fmt(r['selection_accuracy'])} | {fmt(r['top2_hit'])} |")
    lines.append("")
lines.append("## t09 8.5% abstention point (support_any + ambiguity, criterion 'abstention_rule')")
lines.append("")
lines.append("| method | released | networks | net-bal regret | pooled regret | accuracy | top2 |")
lines.append("|---|---:|---:|---:|---:|---:|---:|")
for _, r in curve[curve["criterion"] == "abstention_rule"].iterrows():
    lines.append(f"| {r['method']} | {r['released_units']} | {r['released_networks']} | "
                 f"{fmt(r['network_balanced_regret'])} | {fmt(r['pooled_regret'])} | "
                 f"{fmt(r['selection_accuracy'])} | {fmt(r['top2_hit'])} |")
lines.append("")
lines.append("## No-abstention reference (c=1.0; identical across criteria)")
lines.append("")
lines.append("| method | net-bal regret | pooled regret | accuracy | top2 |")
lines.append("|---|---:|---:|---:|---:|")
for _, r in curve[(curve["criterion"] == "ambiguity_margin") & (curve["c"] == 1.0)].iterrows():
    lines.append(f"| {r['method']} | {fmt(r['network_balanced_regret'])} | {fmt(r['pooled_regret'])} | "
                 f"{fmt(r['selection_accuracy'])} | {fmt(r['top2_hit'])} |")
lines.append("")
lines.append("Notes: best_fixed and global_cv coincide (both select xgboost). random = single seeded "
             "draw (seed 42). top2 = selected loss within the two smallest losses. "
             "t09 top-2-hit definition (true-best within top-2 penalized risks) gives 0.8965 for the "
             "proposed selector at the no-abstention point (reproduced).")
with open(f"{OUT}/coverage_regret_summary.md", "w") as fh:
    fh.write("\n".join(lines) + "\n")

# ---------- reproduction checks (printed for REPORT.md) ----------
checks = {}
checks["no_abstention_proposed_net_balanced"] = evaluate(np.ones(N, dtype=bool), "proposed")["network_balanced_regret"]
checks["no_abstention_proposed_pooled"] = evaluate(np.ones(N, dtype=bool), "proposed")["pooled_regret"]
checks["no_abstention_best_fixed"] = evaluate(np.ones(N, dtype=bool), "best_fixed")["network_balanced_regret"]
checks["no_abstention_per_net_cv"] = evaluate(np.ones(N, dtype=bool), "per_network_cv")["network_balanced_regret"]
checks["no_abstention_gap_rule"] = evaluate(np.ones(N, dtype=bool), "gap_rule")["network_balanced_regret"]
ev = evaluate(rel_abst, "proposed")
checks["abstention_released_units"] = ev["released_units"]
checks["abstention_released_networks"] = ev["released_networks"]
checks["abstention_proposed_net_balanced"] = ev["network_balanced_regret"]
checks["abstention_proposed_pooled"] = ev["pooled_regret"]
# t09 top-2-hit definition on full panel
tb = loss.argmin(axis=1)
order = np.argsort(pen, axis=1)
checks["top2_t09_definition"] = ((order[:, 0] == tb) | (order[:, 1] == tb)).mean()

print("REPRODUCTION CHECKS (lambda=0.5):")
for k, v in checks.items():
    print(f"  {k}: {v:.10f}" if isinstance(v, float) else f"  {k}: {v}")
print("\nFiles written: coverage_regret_curve.csv, comparators_table.csv, selection_frequency.csv, coverage_regret_summary.md")
