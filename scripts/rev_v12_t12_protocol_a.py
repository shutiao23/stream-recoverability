#!/usr/bin/env python3
"""rev_v12_t12_protocol_a.py — power analysis for the v3 external-confirmation protocol.

Route A, third panel (outcome-disjoint). Planning anchor data: the second-panel
scoring outputs (57 scored networks, 1,446 station-gap units) with the
empirical-transfer predictor and the strongest tested baseline (simple
descriptor model), both paired to the same observed recovery losses.

Endpoint families (per-network paired differences, mean across networks):
  (a)  d_rho_sup   Spearman(empirical, observed) - Spearman(simple, observed),
                   direct-support horizons {7,30,90,180} only        [PRIMARY]
  (b)  d_cap_b     captured-loss@budget b: empirical top-k minus RANDOM
                   prioritization (k/n), budgets 5/10/20/30%         [PRIMARY]
  (c)  d_ndcg_b    NDCG@budget b: empirical minus E[NDCG of random ranking]
                   budgets 5/10/20/30%                              [PRIMARY]
  (d)  d_rho_therm thermal-sparsity proxy: d_rho on a 30% subset of
                   direct-support units                              [PRIMARY proxy]
  (a2) d_rho_net   pooled network-level Spearman delta (network-mean
                   predictions vs network-mean outcomes, supported units)
                   [headline statistic; threshold-crossing power]
  (diag) d_rho_all, d_cap_simple_b20, d_ndcg_simple_b20: empirical minus simple
                   within-network (negative second-panel anchors; margins frozen
                   at 0, power reported as documentation)

Power: network-bootstrap panels of size 40..160 at effect scales 0.5x/1x/1.5x of
the signed observed anchor; one-sided network-level t-test, alpha=0.05.
For (a2): P(panel pooled delta >= scale x anchor). Recommended size = smallest
with power >= 0.80 at scale 1.0.

Writes (results/revision_v12/t12_confirmation_protocol/agent_a/):
  per_network_observed_deltas.csv  effect_bootstrap_distribution.csv
  power_table.csv  recommended_sample_size.json  observed_effects.json
  power_curve.png
"""

import json
import os

import numpy as np
import pandas as pd
from scipy import stats as sps

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "results/revision_v12/t12_confirmation_protocol/agent_a"
EMP_CSV = "results/development_v11/second_confirmation/scoring/empirical_predictions.csv"
SIMPLE_CSV = "results/development_v11/second_confirmation/scoring/simple_predictions.csv"

SEED = 20260828
SUPPORTED_HORIZONS = (7, 30, 90, 180)
BUDGETS = (0.05, 0.10, 0.20, 0.30)
THERMAL_FRACTION = 0.30
SIZES = (40, 60, 80, 100, 120, 140, 160)
SCALES = (0.5, 1.0, 1.5)
ALPHA = 0.05
B_POWER = 250
B_DIST = 800

rng = np.random.default_rng(SEED)


TIE_JITTER_SCALE = 1e-6


def tie_break_jitter(gap):
    """Deterministic tie-break for equal predictions: longer gap first.

    pred' = pred + jitter with jitter increasing in gap length, so descending
    order of pred' places longer gaps first inside any tie block.
    """
    return (gap / 365.0) * TIE_JITTER_SCALE


def spearman_rank(x, y):
    if len(x) < 3 or np.all(x == x[0]) or np.all(y == y[0]):
        return np.nan
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rx, ry)[0, 1])


def scalar_metrics(emp_p, base_p, obs, sup_mask, budgets, gap_p):
    """All observed per-network quantities for one network (no resampling)."""
    n = len(obs)
    out = {}
    jit = tie_break_jitter(gap_p)
    emp_j = emp_p + jit
    base_j = base_p + jit
    for lbl, x in (("emp", emp_j), ("base", base_j)):
        out["rho_all_" + lbl] = spearman_rank(x, obs)
        if sup_mask.sum() >= 3:
            out["rho_sup_" + lbl] = spearman_rank(x[sup_mask], obs[sup_mask])
        else:
            out["rho_sup_" + lbl] = np.nan
    out["d_rho_sup"] = out["rho_sup_emp"] - out["rho_sup_base"]
    out["d_rho_all"] = out["rho_all_emp"] - out["rho_all_base"]

    total = obs.sum()
    ideal_desc = np.sort(obs)[::-1]
    for b in budgets:
        k = max(1, int(np.ceil(b * n)))
        frac = k / n
        denom = np.log2(np.arange(2.0, k + 2.0))
        dk = denom.sum()
        idcg = float((ideal_desc[:k] / denom).sum())
        ndcg_rand = (obs.mean() * dk / idcg) if idcg > 0 else 0.0

        def cap(pred):
            if total <= 0:
                return 0.0
            idx = np.argsort(-pred)[:k]
            return float(obs[idx].sum() / total)

        def ndcg(pred):
            idx = np.argsort(-pred)[:k]
            dcg = float((obs[idx] / denom).sum())
            return dcg / idcg if idcg > 0 else 0.0

        pct = int(b * 100)
        cap_emp, cap_base = cap(emp_j), cap(base_j)
        ndcg_emp, ndcg_base = ndcg(emp_j), ndcg(base_j)
        out["cap_emp_b%02d" % pct] = cap_emp
        out["cap_base_b%02d" % pct] = cap_base
        out["ndcg_emp_b%02d" % pct] = ndcg_emp
        out["ndcg_base_b%02d" % pct] = ndcg_base
        out["ndcg_rand_b%02d" % pct] = ndcg_rand
        out["d_cap_simple_b%02d" % pct] = cap_emp - cap_base
        out["d_cap_rand_b%02d" % pct] = cap_emp - frac
        out["d_ndcg_simple_b%02d" % pct] = ndcg_emp - ndcg_base
        out["d_ndcg_rand_b%02d" % pct] = ndcg_emp - ndcg_rand

    sup_idx = np.where(sup_mask)[0]
    if len(sup_idx) >= 3:
        m = max(3, int(np.ceil(THERMAL_FRACTION * len(sup_idx))))
        import zlib
        rng_net = np.random.default_rng(zlib.crc32(b"rev_v12_t12_thermal") & 0xFFFFFFFF)
        sel = np.sort(rng_net.choice(sup_idx, size=m, replace=False))
        out["d_rho_therm"] = (
            spearman_rank(emp_j[sel], obs[sel]) - spearman_rank(base_j[sel], obs[sel])
        )
    else:
        out["d_rho_therm"] = np.nan
    return out


def main():
    os.makedirs(OUT, exist_ok=True)

    emp = pd.read_csv(EMP_CSV)
    sim = pd.read_csv(SIMPLE_CSV)[["network_id", "station_id", "gap_length", "predicted_loss"]]
    df = emp.merge(sim, on=["network_id", "station_id", "gap_length"])
    if len(df) != len(emp):
        raise RuntimeError("merge mismatch")
    if df[["empirical_transfer_prediction", "predicted_loss", "observed_recovery_loss"]].isna().any().any():
        raise RuntimeError("missing values after merge")
    df["sup"] = df["gap_length"].isin(SUPPORTED_HORIZONS)

    net_ids = sorted(df["network_id"].unique())
    n_networks = len(net_ids)
    M = int(df.groupby("network_id").size().max())
    print("networks:", n_networks, "units:", len(df), "max units:", M)

    by_net = {nid: g for nid, g in df.groupby("network_id")}
    N_PER_NET = np.array([len(by_net[nid]) for nid in net_ids], dtype=int)
    ROW_OF = {nid: r for r, nid in enumerate(net_ids)}

    def pad(col):
        out = np.zeros((n_networks, M), dtype=float)
        for r, nid in enumerate(net_ids):
            v = by_net[nid][col].to_numpy(dtype=float)
            out[r, : len(v)] = v
        return out

    EMP_M = pad("empirical_transfer_prediction")
    BASE_M = pad("predicted_loss")
    OBS_M = pad("observed_recovery_loss")
    SUP_M = pad("sup")
    GAP_M = pad("gap_length")

    BUDGETS_PCT = [int(b * 100) for b in BUDGETS]
    POS = np.arange(M, dtype=float)
    DENOM_ALL = np.log2(POS + 2.0)

    def pearson_pair(x, y):
        m = np.isfinite(x) & np.isfinite(y)
        nv = np.maximum(m.sum(axis=1).astype(float), 1.0)
        xc = np.where(m, x, 0.0)
        xc = xc - (xc * m).sum(axis=1, keepdims=True) / nv[:, None]
        xc = np.where(m, xc, 0.0)
        yc = np.where(m, y, 0.0)
        yc = yc - (yc * m).sum(axis=1, keepdims=True) / nv[:, None]
        yc = np.where(m, yc, 0.0)
        num = (xc * yc).sum(axis=1)
        den = np.sqrt((xc * xc).sum(axis=1) * (yc * yc).sum(axis=1))
        rho = np.where(den > 0, num / np.maximum(den, 1e-300), np.nan)
        xmin = np.where(m, x, np.inf).min(axis=1)
        xmax = np.where(m, x, -np.inf).max(axis=1)
        ymin = np.where(m, y, np.inf).min(axis=1)
        ymax = np.where(m, y, -np.inf).max(axis=1)
        nvalid = m.sum(axis=1).astype(float)
        bad = (nvalid < 3) | (xmin == xmax) | (ymin == ymax)
        rho[bad] = np.nan
        return rho

    def rho_delta_cols(e_v, b_v, o_v):
        """Paired rho deltas (empirical - simple) for the masked matrices.
        Predictions already include the frozen tie-break jitter."""
        r_e = np.argsort(np.argsort(e_v, axis=1, kind="stable"), axis=1, kind="stable").astype(float)
        r_b = np.argsort(np.argsort(b_v, axis=1, kind="stable"), axis=1, kind="stable").astype(float)
        r_o = np.argsort(np.argsort(o_v, axis=1, kind="stable"), axis=1, kind="stable").astype(float)
        ok = np.isfinite(e_v) & np.isfinite(o_v)
        d_emp = pearson_pair(np.where(ok, r_e, np.nan), np.where(ok, r_o, np.nan))
        d_base = pearson_pair(np.where(ok, r_b, np.nan), np.where(ok, r_o, np.nan))
        return d_emp - d_base

    def panel_deltas(sampled_ids):
        """Vectorized per-network deltas for a bootstrap panel (networks with
        replacement; unit rows block-bootstrapped within each network)."""
        N = len(sampled_ids)
        rows = np.array([ROW_OF[i] for i in sampled_ids], dtype=int)
        n = N_PER_NET[rows]
        U = rng.random((N, M))
        idx = np.floor(U * n[:, None]).astype(int)
        valid = POS[None, :] < n[:, None]
        nvalid = valid.sum(axis=1).astype(float)

        def gather(X):
            return np.take_along_axis(X[rows], idx, axis=1)

        emp_b, base_b, obs_b = gather(EMP_M), gather(BASE_M), gather(OBS_M)
        sup_b = gather(SUP_M) > 0.5
        gap_b = gather(GAP_M)
        jit_b = tie_break_jitter(gap_b)
        emp_j = emp_b + jit_b
        base_j = base_b + jit_b

        e_v = np.where(valid, emp_j, -np.inf)
        b_v = np.where(valid, base_j, -np.inf)
        o_v = np.where(valid, obs_b, -np.inf)
        d_rho_all = rho_delta_cols(e_v, b_v, o_v)

        sup_v = valid & sup_b
        n_sup = sup_v.sum(axis=1).astype(float)
        es = np.where(sup_v, emp_j, -np.inf)
        bs = np.where(sup_v, base_j, -np.inf)
        os_ = np.where(sup_v, obs_b, -np.inf)
        d_rho_sup = rho_delta_cols(es, bs, os_)
        d_rho_sup[n_sup < 3] = np.nan

        # (d) thermal-sparsity proxy: 30% subset of supported units
        U3 = rng.random((N, M))
        keys = np.where(sup_v, U3, np.inf)
        order3 = np.argsort(keys, axis=1, kind="stable")
        tgt = np.maximum(3, np.floor(THERMAL_FRACTION * n_sup)).astype(int)
        sel3 = np.zeros((N, M))
        np.put_along_axis(sel3, order3, (POS[None, :] < tgt[:, None]).astype(float), axis=1)
        tv = sel3 > 0.5
        et = np.where(tv, emp_j, -np.inf)
        bt = np.where(tv, base_j, -np.inf)
        ot = np.where(tv, obs_b, -np.inf)
        d_rho_therm = rho_delta_cols(et, bt, ot)
        d_rho_therm[tv.sum(axis=1) < 3] = np.nan

        # (a2) pooled network-level delta (supported units)
        ns = np.maximum(n_sup, 1.0)
        m_emp = np.nansum(np.where(sup_v, emp_b, np.nan), axis=1) / ns
        m_base = np.nansum(np.where(sup_v, base_b, np.nan), axis=1) / ns
        m_obs = np.nansum(np.where(sup_v, obs_b, np.nan), axis=1) / ns
        okn = n_sup >= 3
        d_rho_net = np.full(N, np.nan)
        if okn.sum() >= 3:
            d_rho_net[0] = (
                spearman_rank(m_emp[okn], m_obs[okn]) - spearman_rank(m_base[okn], m_obs[okn])
            )

        # (b)/(c) budget endpoints: shared orderings, per-budget masks
        order_e = np.argsort(-e_v, axis=1, kind="stable")
        order_b = np.argsort(-b_v, axis=1, kind="stable")
        ideal = np.sort(o_v, axis=1)[:, ::-1]
        obs_total = np.where(valid, obs_b, 0.0).sum(axis=1)
        zt = obs_total > 0

        cols = {}
        for b in BUDGETS:
            k = np.maximum(1, np.ceil(b * nvalid)).astype(int)
            sel = POS[None, :] < k[:, None]
            frac = k / n
            o_sel_e = np.where(sel, np.take_along_axis(o_v, order_e, axis=1), 0.0)
            o_sel_b = np.where(sel, np.take_along_axis(o_v, order_b, axis=1), 0.0)
            cap_e = np.where(zt, o_sel_e.sum(axis=1) / np.maximum(obs_total, 1e-300), 0.0)
            cap_b = np.where(zt, o_sel_b.sum(axis=1) / np.maximum(obs_total, 1e-300), 0.0)
            pct = int(b * 100)
            cols["d_cap_rand_b%02d" % pct] = cap_e - frac
            cols["d_cap_simple_b%02d" % pct] = cap_e - cap_b

            dcg_e = (o_sel_e / DENOM_ALL).sum(axis=1)
            dcg_b = (o_sel_b / DENOM_ALL).sum(axis=1)
            idcg = np.where(sel, ideal / DENOM_ALL, 0.0).sum(axis=1)
            idcg_pos = idcg > 0
            ndcg_e = np.where(idcg_pos, dcg_e / np.maximum(idcg, 1e-300), 0.0)
            ndcg_b = np.where(idcg_pos, dcg_b / np.maximum(idcg, 1e-300), 0.0)
            mean_gain = obs_total / np.maximum(nvalid, 1e-300)
            dk_k = np.where(sel, DENOM_ALL, 0.0).sum(axis=1)
            ndcg_rand = np.where(idcg_pos, mean_gain * dk_k / np.maximum(idcg, 1e-300), 0.0)
            cols["d_ndcg_rand_b%02d" % pct] = ndcg_e - ndcg_rand
            cols["d_ndcg_simple_b%02d" % pct] = ndcg_e - ndcg_b

        cols.update({
            "d_rho_sup": d_rho_sup,
            "d_rho_all": d_rho_all,
            "d_rho_therm": d_rho_therm,
            "d_rho_net": d_rho_net,
        })
        return np.column_stack([cols[k] for k in ENDPOINT_ORDER])

    ENDPOINT_ORDER = (
        ["d_rho_sup", "d_rho_all", "d_rho_therm", "d_rho_net"]
        + ["d_cap_rand_b%02d" % b for b in BUDGETS_PCT]
        + ["d_cap_simple_b%02d" % b for b in BUDGETS_PCT]
        + ["d_ndcg_rand_b%02d" % b for b in BUDGETS_PCT]
        + ["d_ndcg_simple_b%02d" % b for b in BUDGETS_PCT]
    )

    # ---- 1. observed per-network metrics ----
    mets_keys = None
    obs_rows = []
    for nid in net_ids:
        g = by_net[nid]
        mets = scalar_metrics(
            g["empirical_transfer_prediction"].to_numpy(dtype=float),
            g["predicted_loss"].to_numpy(dtype=float),
            g["observed_recovery_loss"].to_numpy(dtype=float),
            g["sup"].to_numpy(dtype=bool),
            list(BUDGETS),
            g["gap_length"].to_numpy(dtype=float),
        )
        if mets_keys is None:
            mets_keys = sorted(mets.keys())
        obs_rows.append([nid, len(g), int(g["sup"].sum())] + [mets[k] for k in mets_keys])
    per_net = pd.DataFrame(obs_rows, columns=["network_id", "n_units", "n_supported"] + mets_keys)
    per_net.to_csv(os.path.join(OUT, "per_network_observed_deltas.csv"), index=False)

    observed = {}
    for ep in ENDPOINT_ORDER:
        if ep == "d_rho_net":
            continue
        v = per_net[ep].dropna()
        observed[ep] = {
            "n_networks": int(len(v)),
            "mean": float(v.mean()),
            "sd": float(v.std(ddof=1)),
            "median": float(v.median()),
            "q25": float(v.quantile(0.25)),
            "q75": float(v.quantile(0.75)),
        }
    for lbl, sup_only in (("sup", True), ("all", False)):
        mm = df[df["sup"]] if sup_only else df
        g = mm.groupby("network_id")
        me = g["empirical_transfer_prediction"].mean().to_numpy()
        mb = g["predicted_loss"].mean().to_numpy()
        mo = g["observed_recovery_loss"].mean().to_numpy()
        rho_e = spearman_rank(me, mo)
        rho_b = spearman_rank(mb, mo)
        observed["pooled_rho_%s_emp" % lbl] = {"value": rho_e}
        observed["pooled_rho_%s_simple" % lbl] = {"value": rho_b}
        observed["d_rho_net_%s" % lbl] = {"value": rho_e - rho_b}
    observed["d_rho_net"] = {"mean": observed["d_rho_net_sup"]["value"], "sd": np.nan}
    with open(os.path.join(OUT, "observed_effects.json"), "w") as fh:
        json.dump(observed, fh, indent=2)
    print("anchors:", {k: round(observed[k]["mean"], 4) for k in ENDPOINT_ORDER if k in observed})

    # ---- 2. bootstrap distribution of panel mean effects ----
    power_endpoints = (["d_rho_sup"]
                       + ["d_cap_rand_b%02d" % b for b in BUDGETS_PCT]
                       + ["d_ndcg_rand_b%02d" % b for b in BUDGETS_PCT]
                       + ["d_rho_therm", "d_rho_net"])
    diag_endpoints = ["d_cap_simple_b20", "d_ndcg_simple_b20", "d_rho_all"]

    dist_rows = []
    for ep in power_endpoints:
        e = ENDPOINT_ORDER.index(ep)
        vals = np.empty(B_DIST)
        for b in range(B_DIST):
            samp = rng.choice(n_networks, size=n_networks, replace=True)
            d = panel_deltas([net_ids[i] for i in samp])[:, e]
            d = d[np.isfinite(d)]
            vals[b] = d.mean()
        dist_rows.append({
            "endpoint": ep,
            "mean": float(vals.mean()),
            "sd": float(vals.std(ddof=1)),
            "p5": float(np.quantile(vals, 0.05)),
            "p50": float(np.quantile(vals, 0.50)),
            "p95": float(np.quantile(vals, 0.95)),
        })
    dist_df = pd.DataFrame(dist_rows)
    dist_df.to_csv(os.path.join(OUT, "effect_bootstrap_distribution.csv"), index=False)
    print("bootstrap distribution done")

    # ---- 3. power simulation ----
    power_rows = []
    power_grid = {ep: {} for ep in power_endpoints}

    def run_grid(ep):
        e = ENDPOINT_ORDER.index(ep)
        anchor = observed[ep]["mean"]
        for scale in SCALES:
            power_grid[ep][scale] = {}
            for size in SIZES:
                tcrit = sps.t.ppf(1.0 - ALPHA, size - 1)
                n_rej = 0
                effs = np.empty(B_POWER)
                for b in range(B_POWER):
                    samp = rng.choice(n_networks, size=size, replace=True)
                    d = panel_deltas([net_ids[i] for i in samp])[:, e]
                    d = d[np.isfinite(d)]
                    if ep == "d_rho_net":
                        pooled = float(d[0]) if len(d) else np.nan
                        eff = pooled
                        reject = pooled >= scale * anchor
                    elif len(d) < 2:
                        reject = False
                        eff = 0.0
                    else:
                        d = d * scale
                        sd = d.std(ddof=1)
                        mean = d.mean()
                        eff = float(mean)
                        if sd == 0:
                            reject = mean > 0
                        else:
                            t = mean / (sd / np.sqrt(len(d)))
                            reject = t > tcrit
                    n_rej += int(reject)
                    effs[b] = eff
                power = n_rej / B_POWER
                power_grid[ep][scale][size] = power
                power_rows.append({
                    "endpoint": ep,
                    "anchor": anchor,
                    "effect_scale": scale,
                    "margin": scale * anchor,
                    "panel_size": size,
                    "power": power,
                    "mean_panel_effect": float(effs.mean()),
                })
                print("power %-18s scale %.1f size %3d -> %.3f" % (ep, scale, size, power))

    for ep in power_endpoints:
        run_grid(ep)

    for ep in diag_endpoints:
        e = ENDPOINT_ORDER.index(ep)
        for size in SIZES:
            tcrit = sps.t.ppf(1.0 - ALPHA, size - 1)
            n_rej = 0
            for b in range(B_POWER):
                samp = rng.choice(n_networks, size=size, replace=True)
                d = panel_deltas([net_ids[i] for i in samp])[:, e]
                d = d[np.isfinite(d)]
                if len(d) < 2:
                    reject = False
                else:
                    sd = d.std(ddof=1)
                    mean = d.mean()
                    if sd == 0:
                        reject = mean > 0
                    else:
                        t = mean / (sd / np.sqrt(len(d)))
                        reject = t > tcrit
                n_rej += int(reject)
            power_rows.append({
                "endpoint": ep,
                "anchor": observed[ep]["mean"],
                "effect_scale": 0.0,
                "margin": 0.0,
                "panel_size": size,
                "power": n_rej / B_POWER,
                "mean_panel_effect": observed[ep]["mean"],
            })
            print("power %-18s margin 0.0 size %3d -> %.3f" % (ep, size, n_rej / B_POWER))

    power_df = pd.DataFrame(power_rows)
    power_df.to_csv(os.path.join(OUT, "power_table.csv"), index=False)

    # ---- 4. recommended sample size (80% power at scale 1.0) ----
    rec = {}
    for ep in power_endpoints:
        rec[ep] = {}
        for scale in SCALES:
            hits = [s for s in SIZES if power_grid[ep][scale][s] >= 0.80]
            rec[ep]["scale_%.1f" % scale] = (min(hits) if hits else None)
    with open(os.path.join(OUT, "recommended_sample_size.json"), "w") as fh:
        json.dump(rec, fh, indent=2)

    # ---- 5. power curve figure ----
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    panels = [
        ("d_rho_sup", "(a) DeltaRho, direct-support units (empirical - simple)"),
        ("d_cap_rand_b20", "(b) DeltaCapturedLoss@20% vs random prioritization"),
        ("d_ndcg_rand_b20", "(c) DeltaNDCG@20% vs random prioritization"),
        ("d_rho_therm", "(d) DeltaRho, thermal-sparsity proxy (30% of direct-support)"),
    ]
    colors = {0.5: "#d62728", 1.0: "#1f77b4", 1.5: "#2ca02c"}
    for ax, (ep, title) in zip(axes.ravel(), panels):
        for scale in SCALES:
            xs = list(SIZES)
            ys = [power_grid[ep][scale][s] for s in SIZES]
            ax.plot(xs, ys, marker="o", ms=4, lw=1.6, color=colors[scale],
                    label="%.1fx observed effect" % scale)
        ax.axhline(0.80, color="black", ls="--", lw=1.0)
        ax.axvline(n_networks, color="gray", ls=":", lw=1.0)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("scored networks in panel")
        ax.set_ylabel("power (one-sided, alpha=0.05)")
        ax.set_ylim(0.0, 1.02)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="lower right")
    fig.suptitle("Third-panel confirmation: network-bootstrap power curves (planning anchor: 57-network second panel)",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(os.path.join(OUT, "power_curve.png"), dpi=160)
    plt.close(fig)

    print("\nrecommended_sample_size.json:")
    print(json.dumps(rec, indent=2))
    print("done ->", OUT)


if __name__ == "__main__":
    main()
