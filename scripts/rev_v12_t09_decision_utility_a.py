#!/usr/bin/env python3
"""Revision v12, task 09 (agent A, adversarial pair): end-to-end decision utility.

PART 1 - Budget-constrained gap prioritization on the SECOND panel (1,446 units,
57 networks): rank units by 7 risk scores, evaluate CapturedLoss@B,
worst-decile recall@B, NDCG@B, regret at budgets {5,10,20,30}%; network-bootstrap
95% CIs (2,000 draws) for CapturedLoss@20% differences and NDCG@20%; abstention
coverage-risk curve (surface extrapolation flag / old fallback support tier).

PART 2 - Model-selection experiment on the FIRST panel (1,440 units, 42 networks,
families seasonal_boundary_ridge / donor_blup_ridge / xgboost_b_d): per-family
fitting-period curves + unit-level stress from t05 / empirical fit losses,
recalibrated to outer-loss scale by fitting-period-only OLS on development +
first-panel fit rows; selection with uncertainty penalty lambda*interval-width
(lambda in {0,0.5,1}) and abstention (ambiguous top-2 within 10%, or missing
support); regret vs comparators (best fixed on development outcomes, global
blocked-CV, per-network average-CV, gap-length rule, random, oracle);
network-bootstrap CIs for regret differences.

Read-only inputs under results/ and writes ONLY to
results/revision_v12/t09_decision_utility/agent_a/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
RES = ROOT / "results"
OUT = RES / "revision_v12" / "t09_decision_utility" / "agent_a"
OUT.mkdir(parents=True, exist_ok=True)

RV = RES / "development_v11" / "reviewer_completion"
SC = RES / "development_v11" / "second_confirmation" / "scoring"
T1 = RES / "revision_v12" / "t01_paired_comparison" / "agent_a"
T4 = RES / "revision_v12" / "t04_risk_surface" / "agent_a"
T5 = RES / "revision_v12" / "t05_model_matrix" / "agent_a"

RNG_SEED = 42
N_BOOT = 2000
BUDGETS = [0.05, 0.10, 0.20, 0.30]
FAMILIES = ["seasonal_boundary_ridge", "donor_blup_ridge", "xgboost_b_d"]
FAM_SHORT = {
    "seasonal_boundary_ridge": "seasonal_ridge",
    "donor_blup_ridge": "donor_ridge",
    "xgboost_b_d": "xgboost",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def isotonic_curve_log(gaps: np.ndarray, vals: np.ndarray) -> tuple:
    """Monotone (nondecreasing) curve in log gap.

    Inputs: per-gap mean of log1p values at sorted gaps. Returns (g, v) knots
    of a nondecreasing piecewise-linear curve in log gap (PAV isotonic
    regression on the means, then linear interpolation in log gap).
    """
    order = np.argsort(gaps)
    g = gaps[order]
    v = vals[order]
    # pool adjacent violators
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


def eval_curve_log(g_knots: np.ndarray, v_knots: np.ndarray, lg: np.ndarray) -> np.ndarray:
    """Evaluate piecewise-linear (in log gap) curve; extrapolate with the edge
    segment slopes beyond the knot range."""
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


def build_shared_curve(log_gaps: np.ndarray, log1p_vals: np.ndarray) -> tuple:
    """Shared monotone curve in log gap from pooled placements."""
    df = pd.DataFrame({"lg": log_gaps, "y": log1p_vals})
    gs = df.groupby("lg")["y"].mean()
    return isotonic_curve_log(gs.index.to_numpy(), gs.to_numpy())


def season_of_doy(doy: np.ndarray) -> np.ndarray:
    s = pd.Series(np.asarray(doy).astype(int)).astype(str).str.zfill(3)
    m = pd.to_datetime("2020-" + s, format="%Y-%j").dt.month
    return np.select(
        [np.isin(m, [12, 1, 2]), np.isin(m, [3, 4, 5]), np.isin(m, [6, 7, 8])],
        ["DJF", "MAM", "JJA"],
        default="SON",
    )


def ndcg_at_k(loss: np.ndarray, score_order: np.ndarray, k: int) -> float:
    """Position-discount NDCG@k. score_order = unit ids sorted by score desc.
    Gains = loss. Ties in score are broken by the precomputed order."""
    dcg = 0.0
    for i in range(min(k, len(loss))):
        uid = score_order[i]
        dcg += loss[uid] / np.log2(i + 2)
    ideal = np.argsort(-loss)
    idcg = 0.0
    for i in range(min(k, len(loss))):
        idcg += loss[ideal[i]] / np.log2(i + 2)
    return dcg / idcg if idcg > 0 else 0.0


# --------------------------------------------------------------------------
# PART 1 --------------------------------------------------------------------
# --------------------------------------------------------------------------
def part1():
    print("== PART 1: second-panel budget-constrained prioritization ==")
    emp = pd.read_csv(SC / "empirical_predictions.csv", dtype={"network_id": str, "station_id": str})
    t1 = pd.read_csv(T1 / "predictions.csv", dtype={"network_id": str, "station_id": str})
    t4 = pd.read_csv(T4 / "second_panel_predictions.csv", dtype={"network_id": str, "station_id": str})
    placements = pd.read_csv(SC / "placement_losses.csv", dtype={"network_id": str, "station_id": str})
    dev_fl = pd.read_csv(RV / "development_empirical_fit_losses.csv", dtype={"network_id": str, "station_id": str})
    conf_fl = pd.read_csv(RV / "confirmation_empirical_fit_losses.csv", dtype={"network_id": str, "station_id": str})

    u = emp.merge(
        t1[["network_id", "station_id", "gap_length", "simple_fitperiod", "horizon_group"]],
        on=["network_id", "station_id", "gap_length"],
    ).merge(
        t4[
            [
                "network_id",
                "station_id",
                "gap_length",
                "surface_prediction_mae",
                "support_status",
                "extrapolation_factor",
                "surface_lower90",
                "surface_upper90",
            ]
        ],
        on=["network_id", "station_id", "gap_length"],
    )
    assert len(u) == 1446, len(u)
    u["network_code"] = pd.Categorical(u.network_id).codes
    n_net = u.network_code.nunique()
    assert n_net == 57

    # season per unit: mean DOY of the unit's evaluation placements (roster
    # metadata gap_start, NOT outcome values) -> dominant season label.
    pl = placements.copy()
    pl["doy"] = pd.to_datetime(pl["gap_start"]).dt.dayofyear
    unit_season = pl.groupby(["network_id", "station_id", "gap_length"])["doy"].mean().reset_index(name="mean_doy")
    unit_season["season"] = season_of_doy(unit_season["mean_doy"])
    u = u.merge(unit_season[["network_id", "station_id", "gap_length", "season"]], on=["network_id", "station_id", "gap_length"])
    assert u.season.notna().all()

    # duration+season model: per-season monotone (in log gap) curve of
    # log1p(MAE) on pooled development + first-panel fitting-period placements.
    fit = pd.concat([dev_fl[["gap_length", "season", "mae_deg_c"]], conf_fl[["gap_length", "season", "mae_deg_c"]]])
    fit["lg"] = np.log(fit.gap_length)
    fit["y"] = np.log1p(fit.mae_deg_c)
    season_curves = {}
    for s in ["DJF", "MAM", "JJA", "SON"]:
        sub = fit[fit.season == s]
        gs = sub.groupby("lg")["y"].mean()
        season_curves[s] = isotonic_curve_log(gs.index.to_numpy(), gs.to_numpy())
    dur_season_log = np.array(
        [
            eval_curve_log(season_curves[r["season"]][0], season_curves[r["season"]][1], np.log(r["gap_length"]))
            for _, r in u.iterrows()
        ]
    )
    u["risk_durseason"] = np.expm1(dur_season_log)

    # policies: score per unit (higher = more urgent)
    policies = {}
    policies["gap_length"] = u["gap_length"].to_numpy().astype(float)
    policies["durseason"] = u["risk_durseason"].to_numpy()
    policies["simple"] = u["simple_fitperiod"].to_numpy()
    policies["empirical"] = u["empirical_transfer_prediction"].to_numpy()
    policies["surface"] = u["surface_prediction_mae"].to_numpy()
    policies["oracle"] = u["observed_recovery_loss"].to_numpy()

    loss = u["observed_recovery_loss"].to_numpy()
    net = u["network_code"].to_numpy()
    n = len(u)

    # random: 20 draws, seeded
    rng = np.random.default_rng(RNG_SEED)
    random_orders = [rng.permutation(n) for _ in range(20)]

    # tie-breaking: stable order per policy; gap_length ties and random draws
    # get a seeded random order within ties (documented).
    def make_order(score, seed):
        r = np.random.default_rng(seed)
        perm = r.permutation(n)
        return np.lexsort((perm, -score))

    orders = {p: make_order(scores, RNG_SEED) for p, scores in policies.items()}
    for i, o in enumerate(random_orders):
        orders[f"random_{i}"] = o

    # metrics per policy x budget
    total_loss = loss.sum()
    budgets_n = {b: int(np.ceil(b * n)) for b in BUDGETS}

    # worst-decile units per network: top ceil(0.1*n_net) by loss
    decile = {}
    per_net_units = {}
    for c in range(n_net):
        idx = np.where(net == c)[0]
        per_net_units[c] = idx
        kd = int(np.ceil(0.1 * len(idx)))
        decile[c] = idx[np.argsort(-loss[idx])[:kd]]

    rows = []
    for pname, order in orders.items():
        if pname.startswith("random_"):
            continue
        for b in BUDGETS:
            k = budgets_n[b]
            sel = order[:k]
            captured = loss[sel].sum() / total_loss
            # worst-decile recall: mean over networks of fraction of the
            # network's worst-decile units captured by the global selection
            rec = []
            for c in range(n_net):
                d = decile[c]
                if len(d) == 0:
                    continue
                rec.append(np.isin(d, sel).mean())
            wd_recall = float(np.mean(rec))
            ndcg = ndcg_at_k(loss, order, k)
            oracle_cap = loss[np.argsort(-loss)[:k]].sum() / total_loss
            rows.append(
                {
                    "policy": pname,
                    "budget": b,
                    "k": k,
                    "CapturedLoss": captured,
                    "worst_decile_recall": wd_recall,
                    "NDCG": ndcg,
                    "regret_vs_oracle": oracle_cap - captured,
                }
            )
    # random: mean over the 20 draws
    rand_metrics = {b: {"captured": [], "recall": [], "ndcg": [], "regret": []} for b in BUDGETS}
    for b in BUDGETS:
        k = budgets_n[b]
        oracle_cap = loss[np.argsort(-loss)[:k]].sum() / total_loss
        for i in range(20):
            sel = orders[f"random_{i}"][:k]
            captured = loss[sel].sum() / total_loss
            rec = [np.isin(decile[c], sel).mean() for c in range(n_net) if len(decile[c]) > 0]
            ndcg = ndcg_at_k(loss, orders[f"random_{i}"], k)
            rand_metrics[b]["captured"].append(captured)
            rand_metrics[b]["recall"].append(float(np.mean(rec)))
            rand_metrics[b]["ndcg"].append(ndcg)
            rand_metrics[b]["regret"].append(oracle_cap - captured)
    for b in BUDGETS:
        rows.append(
            {
                "policy": "random",
                "budget": b,
                "k": budgets_n[b],
                "CapturedLoss": float(np.mean(rand_metrics[b]["captured"])),
                "worst_decile_recall": float(np.mean(rand_metrics[b]["recall"])),
                "NDCG": float(np.mean(rand_metrics[b]["ndcg"])),
                "regret_vs_oracle": float(np.mean(rand_metrics[b]["regret"])),
            }
        )
    util = pd.DataFrame(rows)
    util = util.sort_values(["policy", "budget"]).reset_index(drop=True)
    util.to_csv(OUT / "utility_table_part1.csv", index=False)
    print(util.to_string(index=False))

    # top-20% selection overlap between policies (context for the report)
    k20 = budgets_n[0.20]
    overlap_rows = []
    for a in ["gap_length", "durseason", "simple", "empirical", "surface"]:
        for b in ["gap_length", "durseason", "simple", "empirical", "surface"]:
            if a >= b:
                continue
            sa = set(orders[a][:k20])
            sb = set(orders[b][:k20])
            overlap_rows.append({"policy_a": a, "policy_b": b, "jaccard": len(sa & sb) / len(sa | sb)})
    pd.DataFrame(overlap_rows).to_csv(OUT / "policy_overlap_part1.csv", index=False)

    # season effect table (duration+season model)
    season_table = []
    for s in ["DJF", "MAM", "JJA", "SON"]:
        g, v = season_curves[s]
        season_table.append({"season": s, "curve_points": ";".join(f"{np.exp(gi):.0f}:{np.expm1(vi):.3f}" for gi, vi in zip(g, v))})
    pd.DataFrame(season_table).to_csv(OUT / "durseason_curve_part1.csv", index=False)

    # ---- bootstrap: 2,000 draws, resample 57 networks with replacement ----
    # multiset convention: units of a sampled network enter the draw as many
    # times as the network was drawn (documented in REPORT.md).
    rng = np.random.default_rng(RNG_SEED)
    per_net_idx = [np.where(net == c)[0] for c in range(n_net)]
    # cumulative multiset counts along each policy's score order
    def draw_metrics(order, k, cnt_net):
        # cnt_net: number of copies per network in this draw (multinomial)
        # order: unit ids sorted by score (desc); v = copies per position
        v = cnt_net[net[order]]  # copies of each unit in the draw, in score order
        start = np.cumsum(v) - v
        mask = start < k
        take = np.where(mask, np.minimum(v, k - start), 0)
        captured = np.sum(loss[order] * take) / np.sum(loss[order] * v)
        # DCG: inner sum of 1/log2(pos+1) over positions [start+1, start+take]
        m = int(start[mask].max() + v[mask].max()) if mask.any() else 0
        inv_log = 1.0 / np.log2(np.arange(1, m + 1) + 1.0)
        S = np.concatenate([[0.0], np.cumsum(inv_log)])
        dcg = np.sum(loss[order][mask] * (S[start[mask] + take[mask]] - S[start[mask]]))
        # ideal DCG over the same multiset: iterate units sorted by loss
        v_all = cnt_net[net]
        idx_sorted = np.argsort(-loss, kind="stable")
        idcg = 0.0
        used = 0
        for uu in idx_sorted:
            c = int(v_all[uu])
            take_u = min(c, k - used)
            idcg += loss[uu] * (S[used + take_u] - S[used])
            used += take_u
            if used >= k:
                break
        ndcg = dcg / idcg if idcg > 0 else 0.0
        return captured, ndcg

    boot_rows = []
    boot_diffs = {("empirical", "simple"): [], ("empirical", "surface"): [], ("surface", "simple"): []}
    boot_policy = {p: [] for p in ["gap_length", "durseason", "simple", "empirical", "surface"]}
    boot_random = []
    for d in range(N_BOOT):
        cnt_net = rng.multinomial(n_net, np.ones(n_net) / n_net)
        k = budgets_n[0.20]
        vals = {}
        for p in ["gap_length", "durseason", "simple", "empirical", "surface"]:
            cap, ndcg = draw_metrics(orders[p], k, cnt_net)
            vals[p] = cap
            boot_policy[p].append((cap, ndcg))
        r_vals = []
        for i in range(20):
            cap, _ = draw_metrics(orders[f"random_{i}"], k, cnt_net)
            r_vals.append(cap)
        boot_random.append(float(np.mean(r_vals)))
        boot_diffs[("empirical", "simple")].append(vals["empirical"] - vals["simple"])
        boot_diffs[("empirical", "surface")].append(vals["empirical"] - vals["surface"])
        boot_diffs[("surface", "simple")].append(vals["surface"] - vals["simple"])
        if d % 500 == 0:
            print(f"  boot draw {d}/{N_BOOT}")

    def ci95(a):
        a = np.asarray(a)
        return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))

    for p in ["empirical", "gap_length", "durseason", "simple", "surface"]:
        cc = [x[0] for x in boot_policy[p]]
        boot_rows.append({"quantity": f"CapturedLoss@20%_{p}", "mean": float(np.mean(cc)), "ci_lo": ci95(cc)[0], "ci_hi": ci95(cc)[1]})
    boot_rows.append({"quantity": "CapturedLoss@20%_random", "mean": float(np.mean(boot_random)), "ci_lo": ci95(boot_random)[0], "ci_hi": ci95(boot_random)[1]})
    for p in ["gap_length", "durseason", "simple", "empirical", "surface"]:
        nd = [x[1] for x in boot_policy[p]]
        boot_rows.append({"quantity": f"NDCG@20%_{p}", "mean": float(np.mean(nd)), "ci_lo": ci95(nd)[0], "ci_hi": ci95(nd)[1]})
    for (a, b), dd in boot_diffs.items():
        boot_rows.append({"quantity": f"diff_CapturedLoss@20%_{a}-{b}", "mean": float(np.mean(dd)), "ci_lo": ci95(dd)[0], "ci_hi": ci95(dd)[1]})
    boot_df = pd.DataFrame(boot_rows)
    boot_df.to_csv(OUT / "bootstrap_part1.csv", index=False)
    print(boot_df.to_string(index=False))

    # ---- abstention coverage-risk curve (Part 1) ----
    u["horizon_group"] = u["horizon_group"].fillna("fallback")
    rules = {
        "surface_extrapolated": u.support_status == "extrapolated",
        "old_fallback_tier": u.horizon_group == "fallback",
        "union": (u.support_status == "extrapolated") | (u.horizon_group == "fallback"),
    }
    abs_rows = []
    for rule_name, mask in rules.items():
        rel = mask.to_numpy() == False  # noqa: E712
        rel_units = np.where(rel)[0]
        rel_loss = loss[rel_units]
        n_rel = len(rel_units)
        abs_loss_share = loss[~rel].sum() / total_loss
        for b in BUDGETS:
            k_rel = int(np.ceil(b * n_rel))
            order_rel = np.argsort(-u.surface_prediction_mae.to_numpy()[rel_units], kind="stable")
            sel_rel = rel_units[order_rel[:k_rel]]
            cap_rel = rel_loss[order_rel[:k_rel]].sum() / rel_loss.sum()
            oracle_rel = np.sort(rel_loss)[::-1][:k_rel].sum() / rel_loss.sum()
            abs_rows.append(
                {
                    "rule": rule_name,
                    "budget": b,
                    "fraction_abstained": float(mask.mean()),
                    "n_abstained": int(mask.sum()),
                    "n_released": n_rel,
                    "captured_loss_released_surface": float(cap_rel),
                    "oracle_captured_released": float(oracle_rel),
                    "abstained_loss_share": float(abs_loss_share),
                }
            )
    abs_df = pd.DataFrame(abs_rows)
    abs_df.to_csv(OUT / "abstention_curve_part1.csv", index=False)
    print(abs_df.to_string(index=False))

    # ---- figures ----
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    palettes = {
        "gap_length": ("#7f7f7f", "-"),
        "durseason": ("#aec7e8", "--"),
        "simple": ("#1f77b4", "-"),
        "empirical": ("#2ca02c", "-"),
        "surface": ("#d62728", "-"),
        "random": ("#c7c7c7", ":"),
        "oracle": ("#000000", "-"),
    }
    for p in ["gap_length", "durseason", "simple", "empirical", "surface", "random", "oracle"]:
        sub = util[util.policy == p]
        axes[0].plot(sub.budget * 100, sub.CapturedLoss, label=p, color=palettes[p][0], ls=palettes[p][1], lw=2)
        axes[1].plot(sub.budget * 100, sub.NDCG, label=p, color=palettes[p][0], ls=palettes[p][1], lw=2)
    axes[0].set_xlabel("budget (% of units)"); axes[0].set_ylabel("CapturedLoss@B (fraction of total loss)")
    axes[1].set_xlabel("budget (% of units)"); axes[1].set_ylabel("NDCG@B")
    for ax in axes:
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.suptitle("Part 1: second-panel prioritization utility (1,446 units, 57 networks)")
    fig.tight_layout()
    fig.savefig(OUT / "utility_curves_part1.png", dpi=150)

    fig2, ax2 = plt.subplots(figsize=(7, 5))
    for rule_name in ["surface_extrapolated", "old_fallback_tier", "union"]:
        sub = abs_df[abs_df.rule == rule_name]
        ax2.plot(sub.budget * 100, sub.captured_loss_released_surface, marker="o", label=f"{rule_name} (abst. {sub.fraction_abstained.iloc[0]*100:.1f}%)")
    ax2.set_xlabel("budget (% of released units)"); ax2.set_ylabel("CapturedLoss@B of released units (surface policy)")
    ax2.legend(fontsize=8); ax2.grid(alpha=0.3)
    ax2.set_title("Part 1: abstention coverage-risk (released-unit utility)")
    fig2.tight_layout(); fig2.savefig(OUT / "abstention_curve_part1.png", dpi=150)

    return u


# --------------------------------------------------------------------------
# PART 2 --------------------------------------------------------------------
# --------------------------------------------------------------------------
def part2():
    print("== PART 2: first-panel model-selection experiment ==")
    roster = pd.read_csv(RV / "confirmation_model_roster_losses.csv", dtype={"network_id": str, "station_id": str})
    dev_rost = pd.read_csv(RV / "development_model_roster_losses.csv", dtype={"network_id": str, "station_id": str})
    dev_rost["gap_length"] = dev_rost["gap_length"].astype(float)
    dev_fl = pd.read_csv(RV / "development_empirical_fit_losses.csv", dtype={"network_id": str, "station_id": str})
    conf_fl = pd.read_csv(RV / "confirmation_empirical_fit_losses.csv", dtype={"network_id": str, "station_id": str})
    stress = pd.read_csv(T5 / "source_fit_stress_families_1_3.csv", dtype={"network_id": str, "station_id": str})

    # unit-level outer loss per family (mean MAE over placements)
    unit_loss = roster.groupby(["network_id", "station_id", "gap_length", "model_family"])["mae_deg_c"].mean().reset_index()
    L = unit_loss.pivot_table(index=["network_id", "station_id", "gap_length"], columns="model_family", values="mae_deg_c").reset_index()
    L = L.sort_values(["network_id", "station_id", "gap_length"]).reset_index(drop=True)
    assert len(L) == 1440, len(L)
    L["network_code"] = pd.Categorical(L.network_id).codes
    n_net = L.network_code.nunique()
    assert n_net == 42

    # ---------------- per-family stress curves ----------------------------
    # xgboost stress = empirical fit losses (dev + first panel)
    # families 2/3 stress = t05 source fit stress (12 networks: 8 first + 4
    # second confirmation), pooled as in the t05 matrix analysis.
    stress_data = {}
    for f in FAMILIES:
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
    for f in FAMILIES:
        family_curves[f] = build_shared_curve(
            stress_data[f]["lg"].to_numpy(), stress_data[f]["y"].to_numpy()
        )

    # unit-level stress: per-unit monotone curve through the unit's own
    # per-gap means, evaluated at the unit's target gap; curve-only fallback.
    def unit_stress_and_support(f, units_df):
        dd = stress_data[f]
        per_gap = dd.groupby(["network_id", "station_id", "gap_length"])["mae_deg_c"].mean().reset_index()
        out_s, out_flag = [], []
        per_unit_gap = per_gap.groupby(["network_id", "station_id"])
        gmap = {k: g for k, g in per_unit_gap}
        for _, r in units_df.iterrows():
            key = (r.network_id, r.station_id)
            if key in gmap:
                sub = gmap[key]
                g = sub.gap_length.to_numpy()
                v = sub.mae_deg_c.to_numpy()
                if len(g) == 1:
                    s = float(v[0])
                else:
                    gk, vk = isotonic_curve_log(np.log(g), np.log1p(v))
                    s = float(np.expm1(eval_curve_log(gk, vk, np.log(r.gap_length))[0]))
                flag = "unit"
            else:
                gk, vk = family_curves[f]
                s = float(np.expm1(eval_curve_log(gk, vk, np.log(r.gap_length))[0]))
                flag = "curve"
            out_s.append(s)
            out_flag.append(flag)
        return np.array(out_s), np.array(out_flag)

    # ---------------- calibration to outer-loss scale ---------------------
    # OLS: outer roster loss ~ a + b * predicted stress, on dev + first-panel
    # fit rows (units where BOTH the family's fitting-period stress and the
    # roster outer loss are observed).
    calib = {}
    for f in FAMILIES:
        if f == "xgboost_b_d":
            rows_dev = dev_fl.groupby(["network_id", "station_id", "gap_length"])["mae_deg_c"].mean().reset_index()
            rows_dev["family_stress"] = rows_dev["mae_deg_c"]
            rows_conf = conf_fl.groupby(["network_id", "station_id", "gap_length"])["mae_deg_c"].mean().reset_index()
            rows_conf["family_stress"] = rows_conf["mae_deg_c"]
            cal_rows = pd.concat([rows_dev[["network_id", "station_id", "gap_length", "family_stress"]],
                                  rows_conf[["network_id", "station_id", "gap_length", "family_stress"]]])
        else:
            dd = stress[stress.model_family == f].groupby(["network_id", "station_id", "gap_length"])["mae_deg_c"].mean().reset_index()
            cal_rows = dd.rename(columns={"mae_deg_c": "family_stress"})
        out_loss = unit_loss[unit_loss.model_family == f][["network_id", "station_id", "gap_length", "mae_deg_c"]].rename(
            columns={"mae_deg_c": "outer_loss"}
        )
        m = cal_rows.merge(out_loss, on=["network_id", "station_id", "gap_length"])
        # predicted stress at the row's target gap via the unit's own curve
        s, flag = unit_stress_and_support(f, m)
        m["s"] = s
        m = m[m.s.notna()]
        X = np.column_stack([np.ones(len(m)), m.s.to_numpy()])
        y = m.outer_loss.to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        ss = np.sum((y - y.mean()) ** 2)
        r2 = 1 - np.sum(resid**2) / ss
        calib[f] = {
            "n": len(m),
            "n_networks": m.network_id.nunique(),
            "intercept": float(beta[0]),
            "slope": float(beta[1]),
            "r2": float(r2),
            "resid_sd": float(np.std(resid)),
            "panels": sorted(m.panel) if "panel" in m.columns else "dev+first" if f == "xgboost_b_d" else "first",
            "units_used": m[["network_id", "station_id", "gap_length"]].copy(),
        }
        print(f"  calib {f}: n={len(m)} networks={m.network_id.nunique()} slope={beta[1]:.3f} intercept={beta[0]:.3f} r2={r2:.3f} resid_sd={np.std(resid):.3f}")
    calib_table = pd.DataFrame(
        [{**{k: v for k, v in cb.items() if k != "units_used"}, "panels": cb["panels"]} for cb in calib.values()]
    ).assign(family=list(calib.keys()))
    calib_table.to_csv(OUT / "selection_calibration_part2.csv", index=False)

    # ---------------- predicted risks and selection -----------------------
    gaps = L.gap_length.to_numpy().astype(float)
    risks = {}
    widths = {}
    supports = {}
    for f in FAMILIES:
        s, flag = unit_stress_and_support(f, L)
        supports[f] = flag
        a, b = calib[f]["intercept"], calib[f]["slope"]
        r = a + b * s
        risks[f] = r
        w = 2 * 1.6448536269514722 * calib[f]["resid_sd"]
        ext = np.maximum(0.0, (np.log(gaps) - np.log(180.0)) / (np.log(180.0) - np.log(7.0)))
        w = w * (1 + 2 * ext)
        widths[f] = w

    R = pd.DataFrame(risks)
    W = pd.DataFrame(widths)
    sup = pd.DataFrame(supports)
    Lmat = L[FAMILIES].to_numpy()
    true_best = np.argmin(Lmat, axis=1)

    sel_out = L[["network_id", "station_id", "gap_length", "network_code"]].copy()
    for f in FAMILIES:
        sel_out[f"risk_{FAM_SHORT[f]}"] = R[f].to_numpy()
        sel_out[f"width_{FAM_SHORT[f]}"] = W[f].to_numpy()
        sel_out[f"support_{FAM_SHORT[f]}"] = sup[f].to_numpy()
        sel_out[f"loss_{FAM_SHORT[f]}"] = L[f].to_numpy()
    sel_out["true_best_family"] = [FAM_SHORT[FAMILIES[i]] for i in true_best]
    sel_out["min_loss"] = Lmat.min(axis=1)

    def select_lambda(lmbda):
        p = R.to_numpy() + lmbda * W.to_numpy()
        return np.argmin(p, axis=1), p

    def regret_for(sel_idx):
        return Lmat[np.arange(len(L)), sel_idx] - Lmat.min(axis=1)

    def net_balanced(reg, netcodes, net_set=None):
        vals = []
        for c in np.unique(netcodes):
            if net_set is not None and c not in net_set:
                continue
            m_ = reg[netcodes == c]
            if len(m_) > 0:
                vals.append(m_.mean())
        return float(np.mean(vals))

    # ----- comparators -----
    # (i) best fixed family on development outcomes
    dev_unit = dev_rost.groupby(["network_id", "station_id", "gap_length", "model_family"])["mae_deg_c"].mean().reset_index()
    dev_means = dev_unit.groupby("model_family")["mae_deg_c"].mean()
    best_fixed = dev_means.idxmin()
    bf_idx = np.full(len(L), FAMILIES.index(best_fixed), dtype=int)
    bf_reg = regret_for(bf_idx)

    # (ii) global blocked-CV: LOO over networks on pooled dev+first roster
    pool = pd.concat([dev_unit, unit_loss])
    pool["netcode"] = pd.Categorical(pool.network_id).codes
    cv_est = {}
    for f in FAMILIES:
        sub = pool[pool.model_family == f]
        losses = []
        for c in sub.netcode.unique():
            losses.append(sub.loc[sub.netcode != c, "mae_deg_c"].mean())
        cv_est[f] = float(np.mean(losses))
    global_cv = min(cv_est, key=cv_est.get)
    gc_idx = np.full(len(L), FAMILIES.index(global_cv), dtype=int)
    gc_reg = regret_for(gc_idx)

    # (iii) per-network average-CV: per first-panel network, LOO-unit CV on
    # that network's own roster units
    pn_idx = np.full(len(L), -1, dtype=int)
    for c in range(n_net):
        nidx = np.where(L.network_code.to_numpy() == c)[0]
        sub = L.iloc[nidx]
        est = {}
        for f in FAMILIES:
            yv = sub[f].to_numpy()
            est[f] = np.mean([np.mean(np.delete(yv, i)) for i in range(len(yv))])
        pn_idx[nidx] = FAMILIES.index(min(est, key=est.get))
    pn_reg = regret_for(pn_idx)

    # (iv) gap-length rule: argmin of raw family curve at the unit's gap
    gap_rule_idx = np.full(len(L), -1, dtype=int)
    for i, g in enumerate(gaps):
        vals = []
        for f in FAMILIES:
            gk, vk = family_curves[f]
            vals.append(float(np.expm1(eval_curve_log(gk, vk, np.log(g))[0])))
        gap_rule_idx[i] = int(np.argmin(vals))
    gr_reg = regret_for(gap_rule_idx)

    # (v) random (20 draws)
    rng = np.random.default_rng(RNG_SEED)
    rand_regs = np.zeros((20, len(L)))
    for i in range(20):
        idx = rng.integers(0, 3, size=len(L))
        rand_regs[i] = regret_for(idx)

    # (vii) oracle
    or_reg = np.zeros(len(L))

    # ---- common-scale sensitivity: single global scale factor c applied to
    # every family's raw stress (OLS through origin on all pooled fit rows).
    # Documented alternative used only when per-family calibration is
    # unavailable; reported here as a robustness check.
    cal_rows_all = []
    for f in FAMILIES:
        rr = calib[f]["units_used"].copy()
        rr["stress"] = unit_stress_and_support(f, rr)[0]
        out_loss_f = unit_loss[unit_loss.model_family == f][["network_id", "station_id", "gap_length", "mae_deg_c"]].rename(
            columns={"mae_deg_c": "outer"}
        )
        rr = rr.merge(out_loss_f, on=["network_id", "station_id", "gap_length"])
        cal_rows_all.append(rr)
    cal_all = pd.concat(cal_rows_all).dropna(subset=["stress", "outer"])
    c_scale = float((cal_all.stress * cal_all.outer).sum() / (cal_all.stress**2).sum())
    with open(OUT / "common_scale_c.json", "w") as fh:
        json.dump({"common_scale_c": c_scale, "n_rows": int(len(cal_all))}, fh)
    stress_L = {f: unit_stress_and_support(f, L)[0] for f in FAMILIES}
    cs_pred = np.column_stack([c_scale * stress_L[f] for f in FAMILIES])
    cs_idx = np.argmin(cs_pred, axis=1)
    cs_reg = regret_for(cs_idx)

    # ----- proposed: lambdas x abstention -----
    amb_delta = 0.10
    results = {}
    for lmbda in [0.0, 0.5, 1.0]:
        sel_idx, pmat = select_lambda(lmbda)
        reg = regret_for(sel_idx)
        # support rules
        support_any = np.any(sup.to_numpy() == "curve", axis=1)
        support_winner = np.array([sup.to_numpy()[i, sel_idx[i]] == "curve" for i in range(len(L))])
        p_sorted = np.sort(pmat, axis=1)
        ambiguous = p_sorted[:, 1] <= (1 + amb_delta) * p_sorted[:, 0]
        abst_amb = ambiguous
        abst_any = ambiguous | support_any
        abst_winner = ambiguous | support_winner
        results[lmbda] = {
            "sel_idx": sel_idx,
            "reg": reg,
            "ambiguous": ambiguous,
            "support_any": support_any,
            "support_winner": support_winner,
            "abst_amb": abst_amb,
            "abst_any": abst_any,
            "abst_winner": abst_winner,
            "pmat": pmat,
        }
        sel_out[f"selected_lambda{lmbda}"] = [FAM_SHORT[FAMILIES[i]] for i in sel_idx]

    # top-2 hit rate (proposed, penalized ranking)
    for lmbda in [0.0, 0.5, 1.0]:
        pmat = results[lmbda]["pmat"]
        top2 = np.argsort(pmat, axis=1)[:, :2]
        hit = np.array([true_best[i] in top2[i] for i in range(len(L))])
        results[lmbda]["top2_hit"] = hit

    # ----- regret table -----
    def mb_reg(reg):
        return net_balanced(reg, L.network_code.to_numpy())

    rows = []
    rows.append({"selector": "oracle", "lambda": np.nan, "abstention": "none", "fraction_abstained": 0.0,
                 "net_balanced_regret": 0.0, "worst_network_regret": 0.0, "mean_unit_regret": 0.0, "top2_hit": np.nan, "n_released": len(L)})
    for name, reg in [("best_fixed_dev", bf_reg), ("global_blockedCV", gc_reg), ("per_network_avgCV", pn_reg),
                      ("gap_length_rule", gr_reg), ("common_scale_rule", cs_reg), ("random", rand_regs.mean(axis=0))]:
        rows.append({"selector": name, "lambda": np.nan, "abstention": "none", "fraction_abstained": 0.0,
                     "net_balanced_regret": mb_reg(reg), "worst_network_regret": float(np.max([reg[L.network_code.to_numpy() == c].mean() for c in range(n_net)])),
                     "mean_unit_regret": float(reg.mean()), "top2_hit": np.nan, "n_released": len(L)})
    for lmbda in [0.0, 0.5, 1.0]:
        res = results[lmbda]
        for abname, abmask in [("none", np.zeros(len(L), bool)), ("ambiguous", res["abst_amb"]),
                               ("ambiguous+support_any", res["abst_any"]), ("ambiguous+support_winner", res["abst_winner"])]:
            rel = ~abmask
            reg = res["reg"][rel]
            nc = L.network_code.to_numpy()[rel]
            rows.append({
                "selector": "proposed_risk", "lambda": lmbda, "abstention": abname,
                "fraction_abstained": float(abmask.mean()),
                "net_balanced_regret": net_balanced(reg, nc),
                "worst_network_regret": float(np.max([reg[nc == c].mean() for c in range(n_net) if (nc == c).sum() > 0])),
                "mean_unit_regret": float(reg.mean()) if len(reg) else np.nan,
                "top2_hit": float(res["top2_hit"][rel].mean()) if len(rel) else np.nan,
                "n_released": int(rel.sum()),
            })
    reg_table = pd.DataFrame(rows)
    reg_table.to_csv(OUT / "selection_regret_table_part2.csv", index=False)
    print(reg_table.to_string(index=False))

    # ----- abstention coverage-risk curve (Part 2, lambda=0.5) -----
    res05 = results[0.5]
    abs_rows = []
    for delta in [0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30]:
        p_sorted = np.sort(res05["pmat"], axis=1)
        amb = p_sorted[:, 1] <= (1 + delta) * p_sorted[:, 0]
        for srname, srmask in [("none", np.zeros(len(L), bool)), ("winner", res05["support_winner"]), ("any", res05["support_any"])]:
            abst = amb | srmask
            rel = ~abst
            reg = res05["reg"][rel]
            nc = L.network_code.to_numpy()[rel]
            minloss = Lmat.min(axis=1)
            abstained_loss_share = minloss[abst].sum() / minloss.sum() if abst.sum() else 0.0
            abs_rows.append({
                "lambda": 0.5, "ambiguity_delta": delta, "support_rule": srname,
                "fraction_abstained": float(abst.mean()), "n_released": int(rel.sum()),
                "net_balanced_regret_released": net_balanced(reg, nc),
                "mean_unit_regret_released": float(reg.mean()) if len(reg) else np.nan,
                "abstained_loss_share": float(abstained_loss_share),
            })
    abs2 = pd.DataFrame(abs_rows)
    abs2.to_csv(OUT / "abstention_curve_part2.csv", index=False)
    print(abs2.to_string(index=False))

    # ---- comparators on the same released units (fair coverage-risk view) --
    rel_rows = []
    for abname, abmask in [("ambiguous", results[0.5]["abst_amb"]),
                           ("ambiguous+support_any", results[0.5]["abst_any"]),
                           ("ambiguous+support_winner", results[0.5]["abst_winner"])]:
        rel = ~abmask
        rel_reg = {}
        for nm, reg in [("proposed", results[0.5]["reg"]), ("best_fixed", bf_reg), ("global_cv", gc_reg),
                        ("per_net_cv", pn_reg), ("gap_rule", gr_reg), ("common_scale", cs_reg)]:
            rel_reg[nm] = net_balanced(reg[rel], L.network_code.to_numpy()[rel])
        rr_mean = float(np.mean([rand_regs[i][rel].mean() for i in range(20)]))
        rel_rows.append({
            "lambda": 0.5, "abstention": abname, "fraction_abstained": float(abmask.mean()), "n_released": int(rel.sum()),
            "proposed_net_balanced_regret": rel_reg["proposed"],
            "best_fixed_net_balanced_regret": rel_reg["best_fixed"],
            "global_cv_net_balanced_regret": rel_reg["global_cv"],
            "per_net_cv_net_balanced_regret": rel_reg["per_net_cv"],
            "gap_rule_net_balanced_regret": rel_reg["gap_rule"],
            "common_scale_net_balanced_regret": rel_reg["common_scale"],
            "random_net_balanced_regret": rr_mean,
        })
    pd.DataFrame(rel_rows).to_csv(OUT / "abstention_comparison_part2.csv", index=False)
    print(pd.DataFrame(rel_rows).to_string(index=False))

    # ----- bootstrap: 2,000 draws on 42 networks -----
    rng = np.random.default_rng(RNG_SEED)
    netcodes = L.network_code.to_numpy()
    reg_by_selector = {
        "best_fixed": bf_reg, "global_cv": gc_reg, "per_net_cv": pn_reg, "gap_rule": gr_reg, "oracle": or_reg,
    }
    for lmbda in [0.0, 0.5, 1.0]:
        reg_by_selector[f"proposed_l{lmbda}"] = results[lmbda]["reg"]
        reg_by_selector[f"proposed_l{lmbda}_abst"] = results[lmbda]["reg"]
        reg_by_selector[f"proposed_l{lmbda}_abst_mask"] = results[lmbda]["abst_any"]
    boot = {k: [] for k in ["best_fixed", "global_cv", "proposed_l0.5", "proposed_l0", "per_net_cv"]}
    boot_diff = {"proposed_l0.5_minus_best_fixed": [], "proposed_l0.5_minus_global_cv": [], "proposed_l0_minus_best_fixed": [], "proposed_l0_minus_global_cv": []}
    boot_abst = {"proposed_l0.5_abst": [], "proposed_l0_abst": []}
    rand_arr = rand_regs
    for d in range(N_BOOT):
        cnt = rng.multinomial(n_net, np.ones(n_net) / n_net)
        # per-network mean regret on the resampled multiset of networks
        def nb(reg):
            vals = []
            for c in range(n_net):
                if cnt[c] > 0:
                    vals.append(reg[netcodes == c].mean())
            return float(np.mean(vals)) if vals else np.nan

        v_bf = nb(bf_reg); v_gc = nb(gc_reg); v_pn = nb(pn_reg)
        v_p5 = nb(results[0.5]["reg"]); v_p0 = nb(results[0.0]["reg"])
        boot["best_fixed"].append(v_bf); boot["global_cv"].append(v_gc); boot["proposed_l0.5"].append(v_p5); boot["proposed_l0"].append(v_p0); boot["per_net_cv"].append(v_pn)
        boot_diff["proposed_l0.5_minus_best_fixed"].append(v_p5 - v_bf)
        boot_diff["proposed_l0.5_minus_global_cv"].append(v_p5 - v_gc)
        boot_diff["proposed_l0_minus_best_fixed"].append(v_p0 - v_bf)
        boot_diff["proposed_l0_minus_global_cv"].append(v_p0 - v_gc)
        for key, lm in [("proposed_l0.5_abst", 0.5), ("proposed_l0_abst", 0.0)]:
            rel = ~results[lm]["abst_any"]
            reg_ = results[lm]["reg"][rel]
            nc = netcodes[rel]
            vals = []
            for c in range(n_net):
                if cnt[c] > 0 and (nc == c).sum() > 0:
                    vals.append(reg_[nc == c].mean())
            boot_abst[key].append(float(np.mean(vals)) if vals else np.nan)
        if d % 500 == 0:
            print(f"  boot2 draw {d}/{N_BOOT}")

    def ci95(a):
        a = np.asarray(a, dtype=float)
        a = a[~np.isnan(a)]
        return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))

    rows = []
    for k, v in boot.items():
        rows.append({"quantity": f"regret_{k}", "mean": float(np.nanmean(v)), "ci_lo": ci95(v)[0], "ci_hi": ci95(v)[1]})
    for k, v in boot_abst.items():
        rows.append({"quantity": f"regret_{k}", "mean": float(np.nanmean(v)), "ci_lo": ci95(v)[0], "ci_hi": ci95(v)[1]})
    for k, v in boot_diff.items():
        rows.append({"quantity": f"diff_{k}", "mean": float(np.nanmean(v)), "ci_lo": ci95(v)[0], "ci_hi": ci95(v)[1]})
    boot2 = pd.DataFrame(rows)
    boot2.to_csv(OUT / "bootstrap_part2.csv", index=False)
    print(boot2.to_string(index=False))

    sel_out.to_csv(OUT / "selection_predictions_part2.csv", index=False)

    # ----- figures -----
    fig, ax = plt.subplots(figsize=(9, 5))
    order = ["best_fixed_dev", "global_blockedCV", "per_network_avgCV", "gap_length_rule", "random",
             "proposed_risk", "oracle"]
    labels = {"best_fixed_dev": "best fixed (dev)", "global_blockedCV": "global blocked-CV", "per_network_avgCV": "per-network avg-CV",
              "gap_length_rule": "gap-length rule", "random": "random", "proposed_risk": "proposed (lambda=0.5)", "oracle": "oracle"}
    colors = ["#a6cee3", "#b2df8a", "#fdbf6f", "#cab2d6", "#c7c7c7", "#d62728", "#000000"]
    means = []
    for i, s in enumerate(order):
        sub = reg_table[(reg_table.selector == s) & (reg_table.abstention == "none")]
        v = sub.net_balanced_regret.iloc[0]
        means.append(v)
        ax.bar(i, v, color=colors[i], label=labels[s])
        if s == "proposed_risk":
            pass
    # CI for proposed and comparators
    ax.errorbar(order.index("best_fixed_dev"), np.nanmean(boot["best_fixed"]),
                yerr=[[np.nanmean(boot["best_fixed"]) - ci95(boot["best_fixed"])[0]], [ci95(boot["best_fixed"])[1] - np.nanmean(boot["best_fixed"])]], fmt="none", color="k", capsize=4)
    ax.errorbar(order.index("global_blockedCV"), np.nanmean(boot["global_cv"]),
                yerr=[[np.nanmean(boot["global_cv"]) - ci95(boot["global_cv"])[0]], [ci95(boot["global_cv"])[1] - np.nanmean(boot["global_cv"])]], fmt="none", color="k", capsize=4)
    ax.errorbar(order.index("proposed_risk"), np.nanmean(boot["proposed_l0.5"]),
                yerr=[[np.nanmean(boot["proposed_l0.5"]) - ci95(boot["proposed_l0.5"])[0]], [ci95(boot["proposed_l0.5"])[1] - np.nanmean(boot["proposed_l0.5"])]], fmt="none", color="k", capsize=4)
    ax.set_xticks(range(len(order))); ax.set_xticklabels([labels[s] for s in order], rotation=15, fontsize=8)
    ax.set_ylabel("network-balanced selection regret (deg C)"); ax.grid(alpha=0.3, axis="y")
    ax.set_title("Part 2: model-selection regret on the first panel (1,440 units, 42 networks)")
    fig.tight_layout(); fig.savefig(OUT / "selection_regret_part2.png", dpi=150)

    fig2, ax2 = plt.subplots(figsize=(8, 5))
    for sr in ["none", "winner", "any"]:
        sub = abs2[abs2.support_rule == sr]
        ax2.plot(sub.fraction_abstained, sub.net_balanced_regret_released, marker="o", label=f"support rule: {sr}")
    ax2.set_xlabel("fraction abstained"); ax2.set_ylabel("network-balanced regret on released units")
    ax2.legend(fontsize=8); ax2.grid(alpha=0.3)
    ax2.set_title("Part 2: abstention coverage-risk (lambda=0.5, ambiguity sweep)")
    fig2.tight_layout(); fig2.savefig(OUT / "abstention_curve_part2.png", dpi=150)

    return L, reg_table, results


def main():
    u1 = part1()
    L2, reg_table2, _ = part2()
    summary = {
        "part1_budgets": BUDGETS,
        "part1_n_boot": N_BOOT,
        "part2_n_boot": N_BOOT,
        "part2_families": FAMILIES,
        "part2_family_short": FAM_SHORT,
    }
    with open(OUT / "summary.json", "w") as fh:
        json.dump(summary, fh, indent=2)
    print("DONE")
    print("OUT:", OUT)


if __name__ == "__main__":
    main()
