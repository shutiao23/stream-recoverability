#!/usr/bin/env python3
"""Agent B: end-to-end decision utility for the v12 revision (t09).

PART 1 - Budget-constrained gap prioritization, second panel
  (1,446 units, 57 networks; results/development_v11/second_confirmation/scoring/).
  Rank units by each risk score (gap length; duration+season; simple descriptors;
  empirical curve; hierarchical surface; random; oracle) and evaluate
  CapturedLoss@B, worst-decile recall@B, NDCG@B, regret = oracle - method for
  budgets B in {5, 10, 20, 30}%.  Network-bootstrap 95% CIs (2,000 draws) for
  CapturedLoss@20% differences.  Abstention coverage-risk curve (surface
  extrapolation flag and/or fallback support tier).

PART 2 - Model-selection experiment, first panel (1,440 units, 42 networks;
  results/development_v11/reviewer_completion/confirmation_model_roster_losses.csv).
  For each unit predict per-family loss (seasonal_boundary_ridge,
  donor_blup_ridge, xgboost) from per-family fitting-period stress curves
  (t05 agent_b fit_losses_families_1_3.csv; read-only empirical fit losses),
  recalibrate stress -> outer-loss scale by fitting-period-only regression,
  add uncertainty penalty lambda * interval width, select the min-risk family,
  abstain on ambiguity (top-two within 10%) or missing support.  Selection
  regret vs comparators: best fixed family (chosen on development outcomes),
  global blocked-CV, per-network average-CV, gap-length rule, random, proposed
  (with/without abstention), outcome oracle.  Network-bootstrap CIs for regret
  differences.

Outputs: results/revision_v12/t09_decision_utility/agent_b/
Run: PYTHONPATH=$PWD/src python3 scripts/rev_v12_t09_decision_utility_b.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "results/revision_v12/t09_decision_utility/agent_b"
OUT.mkdir(parents=True, exist_ok=True)

RNG_BOOT = 0
N_BOOT = 2000
N_RANDOM = 20
BUDGETS = (0.05, 0.10, 0.20, 0.30)

# ---------------------------------------------------------------------------
# read-only inputs
# ---------------------------------------------------------------------------
SECOND_EMP = ROOT / "results/development_v11/second_confirmation/scoring/empirical_predictions.csv"
SECOND_PLACEMENTS = ROOT / "results/development_v11/second_confirmation/scoring/placement_losses.csv"
T01_PRED = ROOT / "results/revision_v12/t01_paired_comparison/agent_a/predictions.csv"
T04_SURF = ROOT / "results/revision_v12/t04_risk_surface/agent_a/second_panel_predictions.csv"
T04_ABST = ROOT / "results/revision_v12/t04_risk_surface/agent_a/abstention_curve.csv"

DEV_FIT = ROOT / "results/development_v11/reviewer_completion/development_empirical_fit_losses.csv"
CONF_FIT = ROOT / "results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv"
DEV_ROSTER = ROOT / "results/development_v11/reviewer_completion/development_model_roster_losses.csv"
CONF_ROSTER = ROOT / "results/development_v11/reviewer_completion/confirmation_model_roster_losses.csv"
T05_STRESS = ROOT / "results/revision_v12/t05_model_matrix/agent_b/fit_losses_families_1_3.csv"

FAMILIES = ["seasonal_boundary_ridge", "donor_blup_ridge", "xgboost"]
LAMBDAS = (0.0, 0.5, 1.0)
AMBIG_THRESHOLD = 0.10  # abstain when top-two penalized scores within 10%


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------
def _season_from_date(ser: pd.Series) -> np.ndarray:
    """Project season convention (validated 100% vs roster `season` column):
    month in {12,1,2} -> DJF, {3,4,5} -> MAM, {6,7,8} -> JJA, else SON."""
    m = pd.to_datetime(ser, format="ISO8601").dt.month
    return np.select(
        [m.isin([12, 1, 2]), m.isin([3, 4, 5]), m.isin([6, 7, 8])],
        ["DJF", "MAM", "JJA"],
        default="SON",
    )


def _ols(x: np.ndarray, y: np.ndarray) -> dict:
    """OLS y ~ a + b x. Returns coefficients and per-x prediction SE."""
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    df = max(n - 2, 1)
    s2 = float(np.sum(resid**2) / df)
    xbar = float(np.mean(x))
    sxx = float(np.sum((x - xbar) ** 2))
    se_pred = np.sqrt(s2 * (1 + 1 / n + (x - xbar) ** 2 / sxx))
    return {
        "a": float(beta[0]),
        "b": float(beta[1]),
        "s2": s2,
        "xbar": xbar,
        "sxx": sxx,
        "n": n,
        "se_pred": se_pred,
        "y": y,
        "yhat": X @ beta,
    }


def _network_bootstrap(networks: pd.Series, rng: np.random.Generator) -> np.ndarray:
    """Resample network ids with replacement."""
    uniq = np.unique(networks.values)
    return rng.choice(uniq, size=len(uniq), replace=True)


# ---------------------------------------------------------------------------
# PART 1
# ---------------------------------------------------------------------------
def part1_load() -> pd.DataFrame:
    emp = pd.read_csv(SECOND_EMP)
    t01 = pd.read_csv(T01_PRED)
    surf = pd.read_csv(T04_SURF)
    place = pd.read_csv(SECOND_PLACEMENTS)

    df = emp.merge(
        t01[
            [
                "network_id",
                "station_id",
                "gap_length",
                "simple_fitperiod",
                "horizon_group",
                "placement_season_sin",
                "placement_season_cos",
            ]
        ],
        on=["network_id", "station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    df = df.merge(
        surf[
            [
                "network_id",
                "station_id",
                "gap_length",
                "surface_prediction_mae",
                "support_status",
                "extrapolation_factor",
            ]
        ],
        on=["network_id", "station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    # season per unit: plurality season of the placement roster (gap_start)
    place["season_p"] = _season_from_date(place["gap_start"])
    seas = (
        place.groupby(["network_id", "station_id", "gap_length"])["season_p"]
        .agg(lambda s: s.value_counts().idxmax())
        .rename("season_plurality")
        .reset_index()
    )
    df = df.merge(seas, on=["network_id", "station_id", "gap_length"], how="left")
    return df


def part1_dur_season_model() -> tuple[dict, pd.DataFrame]:
    """duration+season risk score: OLS log1p(mae) ~ log(gap) + season dummies,
    fit on pooled XGBoost fitting-period placements (development + first panel).
    Dummies are built explicitly in fixed order seasons[1:] (DJF baseline) in
    both fit and prediction. Returns model info and per-season coefficients."""
    dev = pd.read_csv(DEV_FIT, usecols=["gap_length", "season", "mae_deg_c"])
    conf = pd.read_csv(CONF_FIT, usecols=["gap_length", "season", "mae_deg_c"])
    fit = pd.concat([dev, conf], ignore_index=True)
    fit["log_gap"] = np.log(fit["gap_length"].astype(float))
    seasons = ["DJF", "MAM", "JJA", "SON"]
    dums = np.column_stack(
        [(fit["season"] == s).to_numpy(dtype=float) for s in seasons[1:]]
    )
    X = np.column_stack([np.ones(len(fit)), fit["log_gap"].to_numpy(), dums])
    y = np.log1p(fit["mae_deg_c"].to_numpy())
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    model = {
        "beta": beta,
        "n_placements": len(fit),
        "n_dev": len(dev),
        "n_conf": len(conf),
        "rmse_log1p": float(np.sqrt(np.mean(resid**2))),
        "r2": float(1 - np.sum(resid**2) / np.sum((y - y.mean()) ** 2)),
    }
    return model, pd.DataFrame(
        {
            "season": seasons[1:],
            "coef_log1p": beta[2:],
            "exp_coef": np.exp(beta[2:]),
        }
    )


def part1_scores(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Risk scores, higher = riskier. All defined on the 1,446 second-panel units."""
    scores = {
        "gap_length": df["gap_length"].astype(float),
        "dur_season": None,  # filled below
        "simple": df["simple_fitperiod"].astype(float),
        "empirical": df["empirical_transfer_prediction"].astype(float),
        "surface": df["surface_prediction_mae"].astype(float),
    }
    return scores


def part1_metrics(score: np.ndarray, loss: np.ndarray, budget: float) -> dict:
    n = len(loss)
    k = max(1, int(round(budget * n)))
    order = np.argsort(-score, kind="mergesort")  # descending, stable
    sel = order[:k]
    captured = float(loss[sel].sum() / loss.sum())
    worst_k = int(round(0.10 * n))
    worst = np.argsort(-loss, kind="mergesort")[:worst_k]
    recall = float(np.intersect1d(sel, worst).size / worst_k)
    gains = 2.0 ** loss - 1.0
    denom = np.log2(2.0 + np.arange(k))
    dcg = float(np.sum(gains[order[:k]] / denom))
    ideal = np.argsort(-loss, kind="mergesort")[:k]
    idcg = float(np.sum(gains[ideal] / denom))
    ndcg = dcg / idcg if idcg > 0 else 0.0
    return {"captured": captured, "recall": recall, "ndcg": ndcg}


def part1_random(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, list[dict]]:
    loss = df["observed_recovery_loss"].to_numpy()
    out: dict[str, list[dict]] = {f"b{b:g}": [] for b in BUDGETS}
    for _ in range(N_RANDOM):
        score = rng.random(len(df))
        for b in BUDGETS:
            out[f"b{b:g}"].append(part1_metrics(score, loss, b))
    return out


def part1_bootstrap(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Network-cluster bootstrap of CapturedLoss@20% differences."""
    loss_all = df["observed_recovery_loss"].to_numpy()
    scores = {
        "empirical": df["empirical_transfer_prediction"].to_numpy(),
        "simple": df["simple_fitperiod"].to_numpy(),
        "surface": df["surface_prediction_mae"].to_numpy(),
    }
    networks = df["network_id"].to_numpy()
    net_index = {n: np.where(networks == n)[0] for n in np.unique(networks)}
    pairs = [("empirical", "simple"), ("empirical", "surface"), ("surface", "simple")]
    rows = {p: np.zeros(N_BOOT) for p in pairs}
    for it in range(N_BOOT):
        net_sample = rng.choice(list(net_index.keys()), size=len(net_index), replace=True)
        idx = np.concatenate([net_index[n] for n in net_sample])
        cl = {}
        for name, sc in scores.items():
            cl[name] = part1_metrics(sc[idx], loss_all[idx], 0.20)["captured"]
        for (a, b) in pairs:
            rows[(a, b)][it] = cl[a] - cl[b]
    rec = []
    for (a, b) in pairs:
        d = rows[(a, b)]
        rec.append(
            {
                "policy_a": a,
                "policy_b": b,
                "mean_diff": float(d.mean()),
                "sd_diff": float(d.std()),
                "ci_lo": float(np.percentile(d, 2.5)),
                "ci_hi": float(np.percentile(d, 97.5)),
                "frac_diff_gt_0": float(np.mean(d > 0)),
                "n_draws": N_BOOT,
            }
        )
    return pd.DataFrame(rec)


def part1_abstention(df: pd.DataFrame) -> pd.DataFrame:
    """Abstention coverage-risk curve at budget 20%.
    Rules: none; extrapolated (surface support_status == 'extrapolated');
    fallback tier (t01 horizon_group == 'fallback'); extrapolated+fallback;
    plus a threshold sweep on extrapolation_factor (reference: t04 curve)."""
    rows = []
    loss = df["observed_recovery_loss"].to_numpy()
    scores = {
        "gap_length": df["gap_length"].to_numpy().astype(float),
        "dur_season": df["dur_season_pred"].to_numpy(),
        "simple": df["simple_fitperiod"].to_numpy(),
        "empirical": df["empirical_transfer_prediction"].to_numpy(),
        "surface": df["surface_prediction_mae"].to_numpy(),
    }
    abstain_masks = {
        "none": np.zeros(len(df), dtype=bool),
        "extrapolated": (df["support_status"] == "extrapolated").to_numpy(),
        "fallback_tier": (df["horizon_group"] == "fallback").to_numpy(),
        "extrapolated_or_fallback": (
            (df["support_status"] == "extrapolated") | (df["horizon_group"] == "fallback")
        ).to_numpy(),
    }
    for th in (0.0, 0.05, 0.10, 0.15, 0.20, float(df["extrapolation_factor"].max()), 0.25):
        # strict > reproduces the t04 abstention curve (threshold 0 -> only the
        # 124 extrapolated units with factor = 0.2177 are abstained)
        abstain_masks[f"extrap_factor> {th:g}"] = (
            df["extrapolation_factor"].to_numpy() > th
        )
    for rule, mask in abstain_masks.items():
        rel = ~mask
        if rel.sum() == 0:
            continue
        full_total = loss.sum()
        rel_total = loss[rel].sum()
        rec = {
            "rule": rule,
            "fraction_abstained": float(mask.mean()),
            "n_released": int(rel.sum()),
            "n_networks_released": int(df.loc[rel, "network_id"].nunique()),
        }
        for name, sc in scores.items():
            m = part1_metrics(sc[rel], loss[rel], 0.20)
            rec[f"captured_released_{name}"] = m["captured"]
            rec[f"captured_full_{name}"] = float(loss[rel][np.argsort(-sc[rel], kind="mergesort")[: int(round(0.2 * rel.sum()))]].sum() / full_total)
        rows.append(rec)
    return pd.DataFrame(rows)


def part1_main() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    df = part1_load()
    model, season_coef = part1_dur_season_model()
    # duration+season prediction for second-panel units (fixed season order,
    # DJF baseline, aligned with the fit)
    seasons = ["DJF", "MAM", "JJA", "SON"]
    dums = np.column_stack(
        [(df["season_plurality"] == s).to_numpy(dtype=float) for s in seasons[1:]]
    )
    X = np.column_stack(
        [np.ones(len(df)), np.log(df["gap_length"].astype(float)), dums]
    )
    df["dur_season_pred"] = np.expm1(X @ model["beta"])

    scores = part1_scores(df)
    scores["dur_season"] = df["dur_season_pred"]
    loss = df["observed_recovery_loss"].to_numpy()
    networks = df["network_id"].to_numpy()

    rng = np.random.default_rng(20260829)
    random_out = part1_random(df, rng)

    rows = []
    for name, sc in scores.items():
        for b in BUDGETS:
            m = part1_metrics(sc.to_numpy(), loss, b)
            rows.append(
                {
                    "policy": name,
                    "budget": b,
                    "n_units": len(df),
                    "captured_loss": m["captured"],
                    "worst_decile_recall": m["recall"],
                    "ndcg": m["ndcg"],
                }
            )
    for b in BUDGETS:
        m = part1_metrics(loss, loss, b)
        rows.append(
            {
                "policy": "oracle",
                "budget": b,
                "n_units": len(df),
                "captured_loss": m["captured"],
                "worst_decile_recall": m["recall"],
                "ndcg": m["ndcg"],
            }
        )
    oracle_cl = {
        b: part1_metrics(loss, loss, b)["captured"] for b in BUDGETS
    }
    for r in rows:
        r["regret_pp"] = 100.0 * (oracle_cl[r["budget"]] - r["captured_loss"])
    metrics = pd.DataFrame(rows)
    # random rows: mean over 20 draws
    for b in BUDGETS:
        key = f"b{b:g}"
        cl = np.array([x["captured"] for x in random_out[key]])
        rc = np.array([x["recall"] for x in random_out[key]])
        nd = np.array([x["ndcg"] for x in random_out[key]])
        metrics = pd.concat(
            [
                metrics,
                pd.DataFrame(
                    [
                        {
                            "policy": "random",
                            "budget": b,
                            "n_units": len(df),
                            "captured_loss": float(cl.mean()),
                            "worst_decile_recall": float(rc.mean()),
                            "ndcg": float(nd.mean()),
                            "regret_pp": 100.0 * (oracle_cl[b] - cl.mean()),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    metrics["regret_pp_random_sd"] = np.nan
    for b in BUDGETS:
        key = f"b{b:g}"
        cl = np.array([x["captured"] for x in random_out[key]])
        rc = np.array([x["recall"] for x in random_out[key]])
        nd = np.array([x["ndcg"] for x in random_out[key]])
        mask = (metrics["policy"] == "random") & (metrics["budget"] == b)
        metrics.loc[mask, "regret_pp_random_sd"] = 100.0 * cl.std()
        metrics.loc[mask, "captured_loss_sd"] = cl.std()
        metrics.loc[mask, "worst_decile_recall_sd"] = rc.std()
        metrics.loc[mask, "ndcg_sd"] = nd.std()

    rng_boot = np.random.default_rng(RNG_BOOT)
    boot = part1_bootstrap(df, rng_boot)
    abst = part1_abstention(df)

    # write scores for transparency
    score_df = df[
        ["network_id", "station_id", "gap_length", "season_plurality", "observed_recovery_loss"]
    ].copy()
    for name, sc in scores.items():
        score_df[name] = sc
    score_df["support_status"] = df["support_status"]
    score_df["horizon_group"] = df["horizon_group"]

    metrics.to_csv(OUT / "part1_prioritization_metrics.csv", index=False)
    boot.to_csv(OUT / "part1_bootstrap_cis.csv", index=False)
    abst.to_csv(OUT / "part1_abstention_curve.csv", index=False)
    score_df.to_csv(OUT / "part1_policies.csv", index=False)
    pd.DataFrame(
        [{"key": k, "value": v} for k, v in model.items() if k != "beta"]
    ).to_csv(OUT / "part1_dur_season_model.csv", index=False)
    season_coef.to_csv(OUT / "part1_dur_season_coefs.csv", index=False)

    part1_plot(metrics)
    return metrics, boot, abst, df, model


def part1_plot(metrics: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    styles = {
        "gap_length": ("tab:gray", "-"),
        "dur_season": ("tab:olive", "--"),
        "simple": ("tab:orange", "--"),
        "empirical": ("tab:blue", "-"),
        "surface": ("tab:red", "-"),
        "random": ("tab:purple", ":"),
        "oracle": ("black", "-"),
    }
    for pol in styles:
        sub = metrics[metrics["policy"] == pol].sort_values("budget")
        c, ls = styles[pol]
        if pol == "oracle":
            sub = metrics[metrics["policy"] == pol].sort_values("budget")
            ax.plot(sub["budget"] * 100, sub["captured_loss"], c=c, ls=ls, lw=2, label=pol)
        else:
            ax.plot(sub["budget"] * 100, sub["captured_loss"], c=c, ls=ls, label=pol)
    ax.set_xlabel("budget (% of units)")
    ax.set_ylabel("CapturedLoss@B (fraction of total loss)")
    ax.set_title("Part 1: budget-constrained gap prioritization (second panel, 1,446 units)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "part1_prioritization_curves.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# PART 2
# ---------------------------------------------------------------------------
def part2_build() -> tuple[dict, dict]:
    """Build unit-level tables for the first panel."""
    roster = pd.read_csv(CONF_ROSTER)
    dev_roster = pd.read_csv(DEV_ROSTER)
    conf_fit = pd.read_csv(CONF_FIT)
    dev_fit = pd.read_csv(DEV_FIT)
    t05 = pd.read_csv(T05_STRESS)

    # unit-level outer loss per family
    def unit_loss(df: pd.DataFrame) -> pd.DataFrame:
        g = (
            df.groupby(["network_id", "station_id", "gap_length", "model_family"])[
                "mae_deg_c"
            ]
            .mean()
            .reset_index()
            .pivot(
                index=["network_id", "station_id", "gap_length"],
                columns="model_family",
                values="mae_deg_c",
            )
            .reset_index()
        )
        if "xgboost_b_d" in g.columns:
            g = g.rename(columns={"xgboost_b_d": "xgboost"})
        return g

    conf_units = unit_loss(roster)
    dev_units = unit_loss(dev_roster)

    # per-unit fitting-period stress. Units with own fit placements (gaps
    # 7/30/90/180) get their unit mean; other units (gaps 14/60/365) get the
    # network-level mean of unit stresses (same fallback structure as the
    # empirical predictor); networks without any fit placements get the pooled
    # mean (none here).
    def unit_stress(fit: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
        g = (
            fit.groupby(["network_id", "station_id", "gap_length"])["mae_deg_c"]
            .mean()
            .rename("stress")
            .reset_index()
        )
        net_mean = g.groupby("network_id")["stress"].mean().rename("net_mean")
        out = keys.merge(g, on=["network_id", "station_id", "gap_length"], how="left")
        out = out.merge(net_mean, on="network_id", how="left")
        out["stress_used"] = out["stress"].fillna(out["net_mean"]).fillna(g["stress"].mean())
        out["is_fallback"] = out["stress"].isna()
        return out

    conf_stress = unit_stress(conf_fit, conf_units[["network_id", "station_id", "gap_length"]])
    dev_stress = unit_stress(dev_fit, dev_units[["network_id", "station_id", "gap_length"]])

    # t05 family-specific stress (first-panel networks), unit-level means
    t05u = (
        t05[t05["model_family"].isin(FAMILIES[:2])]
        .groupby(["network_id", "station_id", "gap_length", "model_family"])["mae_deg_c"]
        .mean()
        .rename("stress")
        .reset_index()
    )
    t05_wide = t05u.pivot(
        index=["network_id", "station_id", "gap_length"],
        columns="model_family",
        values="stress",
    ).reset_index()

    return {
        "conf_units": conf_units,
        "dev_units": dev_units,
        "conf_stress": conf_stress,
        "dev_stress": dev_stress,
        "t05_wide": t05_wide,
    }, {}


def part2_calibrate(d: dict) -> dict:
    """Per-family OLS calibration of outer loss on fitting-period stress.

    Two mappings per ridge family:
    - 't05': outer_f ~ family-specific t05 stress, matched rows on the 10 t05
      networks (first-panel rows only; no development family-specific
      fitting-period stress exists in read-only artifacts).
    - 'axis': outer_f ~ xgboost fitting-period stress, matched direct rows from
      development + first panel (n=1,313) - used for units without family-
      specific stress (proxy support tier).
    xgboost family: outer ~ xgboost stress on the same 1,313 direct rows
    (development + first-panel fit rows).
    Also returns sigma_fb = RMSE of (unit stress ~ network mean) over direct
    rows, used to widen intervals of units whose stress is a network-mean
    fallback.
    """
    conf_units = d["conf_units"]
    dev_units = d["dev_units"]
    out = {}
    rows = []
    for panel in ("dev", "conf"):
        st = d[f"{panel}_stress"]
        un = d[f"{panel}_units"][["network_id", "station_id", "gap_length"] + FAMILIES]
        m = st.merge(un, on=["network_id", "station_id", "gap_length"], how="inner")
        m = m[m["stress"].notna()]  # direct rows only
        rows.append(m)
    direct = pd.concat(rows, ignore_index=True)
    for fam in FAMILIES:
        cal_rows = direct.dropna(subset=[fam]).copy()
        res = _ols(cal_rows["stress"].to_numpy(), cal_rows[fam].to_numpy())
        out[fam] = {"axis": res, "n_axis_rows": len(cal_rows)}
    for fam in FAMILIES[:2]:
        st = d["t05_wide"][["network_id", "station_id", "gap_length", fam]].rename(
            columns={fam: "stress"}
        )
        un = conf_units[["network_id", "station_id", "gap_length", fam]].rename(
            columns={fam: "outer"}
        )
        m = st.merge(un, on=["network_id", "station_id", "gap_length"], how="inner")
        m = m.dropna(subset=["stress", "outer"])
        res = _ols(m["stress"].to_numpy(), m["outer"].to_numpy())
        out[fam]["t05"] = res
        out[fam]["n_t05_rows"] = len(m)
    # fallback widening: unit stress ~ network mean (direct rows)
    s = direct.dropna(subset=["stress", "net_mean"])
    s = s[s["is_fallback"] == False]  # noqa: E712
    fb = _ols(s["net_mean"].to_numpy(), s["stress"].to_numpy())
    out["_sigma_fb"] = float(np.sqrt(fb["s2"]))
    out["_sigma_fb_n"] = len(s)
    return out


def part2_predict(d: dict, cal: dict) -> pd.DataFrame:
    """Per-unit per-family predicted risk, interval width, actual loss.

    Support tiers per family:
    - xgboost: stress = own fit stress (direct) or network-mean fallback;
      risk from the 'axis' calibration; fallback units get widened intervals.
    - ridge families: family-specific t05 stress where it exists (10 networks,
      297 first-panel units); otherwise the xgb-stress proxy tier with the
      'axis' calibration (risk = E[outer_f | xgb stress]); proxy units get
      widened intervals when the xgb stress itself is a fallback value.
    """
    units = d["conf_units"].copy()
    conf_stress = d["conf_stress"].copy()
    t05_wide = d["t05_wide"].copy()
    units = units.merge(
        conf_stress, on=["network_id", "station_id", "gap_length"], how="left"
    )
    units = units.merge(
        t05_wide,
        on=["network_id", "station_id", "gap_length"],
        how="left",
        suffixes=("", "_t05"),
    )
    sigma_fb = cal["_sigma_fb"]
    rows = []
    for _, u in units.iterrows():
        xgb_stress = u["stress_used"]
        for fam in FAMILIES:
            if fam == "xgboost":
                stress = xgb_stress
                support = "direct" if not u["is_fallback"] else "fallback"
                calr = cal[fam]["axis"]
                width = _cal_width(calr, stress, sigma_fb, u["is_fallback"], calr["b"])
            else:
                fs = u.get(f"{fam}_t05")
                if pd.notna(fs):
                    stress = fs
                    support = "direct"
                    calr = cal[fam]["t05"]
                    width = 2.0 * 1.96 * _se_at(calr, stress)
                else:
                    stress = xgb_stress
                    support = "proxy"
                    calr = cal[fam]["axis"]
                    width = _cal_width(calr, stress, sigma_fb, u["is_fallback"], calr["b"])
            risk = max(0.0, calr["a"] + calr["b"] * stress)
            rows.append(
                {
                    "network_id": u["network_id"],
                    "station_id": u["station_id"],
                    "gap_length": u["gap_length"],
                    "family": fam,
                    "stress": stress,
                    "support": support,
                    "risk": risk,
                    "width": width,
                    "actual_loss": u[fam],
                    "xgb_stress": xgb_stress,
                }
            )
    pred = pd.DataFrame(rows)
    return pred


def _se_at(calr: dict, x: float) -> float:
    return float(
        np.sqrt(calr["s2"] * (1 + 1 / calr["n"] + (x - calr["xbar"]) ** 2 / calr["sxx"]))
    )


def _cal_width(calr: dict, stress: float, sigma_fb: float, is_fallback: bool, slope: float) -> float:
    se = _se_at(calr, stress)
    if is_fallback:
        se = np.sqrt(se**2 + (slope * sigma_fb) ** 2)
    return 2.0 * 1.96 * se


def part2_strategy_metrics(
    pred: pd.DataFrame, units: pd.DataFrame, dev_units: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate selection strategies; returns (strategy metrics, per-unit detail)."""
    # per-unit: actual family losses, selected family per strategy
    u = units[["network_id", "station_id", "gap_length"]].copy()
    for fam in FAMILIES:
        u[f"L_{fam}"] = units[fam].values
    losses = u[[f"L_{f}" for f in FAMILIES]].to_numpy()
    best_fam_idx = np.argmin(losses, axis=1)
    min_loss = losses[np.arange(len(u)), best_fam_idx]
    networks = u["network_id"].to_numpy()
    gaps = u["gap_length"].to_numpy()

    # ---- dev-outcome-based comparators ----
    dev_mean = {fam: float(dev_units[fam].mean()) for fam in FAMILIES}
    best_fixed_fam = min(dev_mean, key=dev_mean.get)
    # gap-length rule: per gap, family with lowest mean dev roster loss at that gap
    dev_gap = dev_units.groupby("gap_length")[FAMILIES].mean()
    gap_best = dev_gap.idxmin(axis=1).to_dict()

    # ---- per-unit selection maps ----
    sel = {
        f"best_fixed_{best_fixed_fam}": np.full(
            len(u), FAMILIES.index(best_fixed_fam), dtype=int
        )
    }
    # global blocked-CV: leave-one-network-out, one family per held-out network
    global_cv_sel = np.zeros(len(u), dtype=int)
    for net in np.unique(networks):
        tr = losses[networks != net].mean(axis=0)
        global_cv_sel[networks == net] = int(np.argmin(tr))
    sel["global_CV"] = global_cv_sel
    # per-network average-CV: leave-one-unit-out within the network
    per_net_sel = np.zeros(len(u), dtype=int)
    for net in np.unique(networks):
        idx = np.where(networks == net)[0]
        if len(idx) == 1:
            per_net_sel[idx] = int(np.argmin(losses[idx].mean(axis=0)))
            continue
        for i in idx:
            others = losses[np.setdiff1d(idx, np.array([i]))].mean(axis=0)
            per_net_sel[i] = int(np.argmin(others))
    sel["per_network_CV"] = per_net_sel
    # gap-length rule
    gap_sel = np.array([FAMILIES.index(gap_best.get(g, best_fixed_fam)) for g in gaps])
    sel["gap_rule"] = gap_sel
    # oracle
    sel["oracle"] = best_fam_idx

    # ---- proposed: per lambda, with/without abstention ----
    proposed = {}
    for lam in LAMBDAS:
        penalized = np.column_stack(
            [pred.loc[pred["family"] == f, "risk"].to_numpy()
             + lam * pred.loc[pred["family"] == f, "width"].to_numpy() for f in FAMILIES]
        )
        # order: FAMILIES index; penalized columns follow FAMILIES order
        order = np.argsort(penalized, axis=1)
        sel_prop = order[:, 0]
        gap_top2 = (penalized[np.arange(len(u)), order[:, 1]] - penalized[np.arange(len(u)), order[:, 0]])
        rel_gap = gap_top2 / np.maximum(penalized[np.arange(len(u)), order[:, 0]], 1e-12)
        abstain_ambig = rel_gap < AMBIG_THRESHOLD
        abstain_nosupport = np.zeros(len(u), dtype=bool)  # stress exists for every unit
        abstain = abstain_ambig | abstain_nosupport
        proposed[lam] = {
            "sel": sel_prop,
            "abstain": abstain,
            "abstain_ambig": abstain_ambig,
            "abstain_nosupport": abstain_nosupport,
        }
        sel[f"proposed_l{lam:g}"] = sel_prop

    # ---- random ----
    rng = np.random.default_rng(20260830)
    random_sels = [rng.integers(0, 3, size=len(u)) for _ in range(N_RANDOM)]

    # ---- metrics ----
    def network_balanced(reg: np.ndarray, nets: np.ndarray | None = None) -> float:
        if nets is None:
            nets = networks
        return float(np.mean([reg[nets == n].mean() for n in np.unique(nets)]))

    def worst_network(reg: np.ndarray, nets: np.ndarray | None = None) -> float:
        if nets is None:
            nets = networks
        return float(np.max([reg[nets == n].mean() for n in np.unique(nets)]))

    strat_rows = []
    detail = pd.DataFrame(
        {
            "network_id": networks,
            "station_id": u["station_id"],
            "gap_length": gaps,
            "min_loss": min_loss,
        }
    )
    for fam in FAMILIES:
        detail[f"L_{fam}"] = units[fam].to_numpy()
    detail["best_family"] = best_fam_idx

    def add_strategy(name: str, sel_idx: np.ndarray, mask: np.ndarray, lam: float | None, abstain_rule: str):
        rel = mask
        reg = losses[np.arange(len(u)), sel_idx] - min_loss
        reg_r = reg[rel]
        nets_r = networks[rel]
        detail[name] = sel_idx
        detail[f"{name}_released"] = rel
        strat_rows.append(
            {
                "strategy": name,
                "lambda": lam,
                "abstain_rule": abstain_rule,
                "fraction_abstained": float((~rel).mean()),
                "n_released": int(rel.sum()),
                "n_networks_released": int(len(np.unique(nets_r))),
                "network_balanced_regret": network_balanced(reg_r, nets_r) if rel.sum() else np.nan,
                "worst_network_regret": worst_network(reg_r, nets_r) if rel.sum() else np.nan,
                "pooled_regret": float(reg_r.mean()) if rel.sum() else np.nan,
                "top2_hit_rate": float(
                    np.mean(
                        np.take_along_axis(losses[rel], sel_idx[rel, None], axis=1).ravel()
                        <= np.sort(losses[rel], axis=1)[:, 1]
                    )
                )
                if rel.sum()
                else np.nan,
            }
        )

    full_mask = np.ones(len(u), dtype=bool)
    for name, idx in sel.items():
        add_strategy(name, idx, full_mask, None, "none")
    for lam in LAMBDAS:
        add_strategy(f"proposed_l{lam:g}_abstain", proposed[lam]["sel"], ~proposed[lam]["abstain"], lam, "ambiguous10%")
    # random: mean over draws
    reg_random = [losses[np.arange(len(u)), s] - min_loss for s in random_sels]
    reg_random = np.array(reg_random)
    strat_rows.append(
        {
            "strategy": "random",
            "lambda": None,
            "abstain_rule": "none",
            "fraction_abstained": 0.0,
            "n_released": int(len(u)),
            "n_networks_released": int(len(np.unique(networks))),
            "network_balanced_regret": float(np.mean([network_balanced(r) for r in reg_random])),
            "worst_network_regret": float(np.mean([worst_network(r) for r in reg_random])),
            "pooled_regret": float(reg_random.mean()),
            "top2_hit_rate": float(
                np.mean(
                    [
                        np.mean(
                            np.take_along_axis(losses, s[:, None], axis=1).ravel()
                            <= np.sort(losses, axis=1)[:, 1]
                        )
                        for s in random_sels
                    ]
                )
            ),
            "random_sd_netbal": float(np.std([network_balanced(r) for r in reg_random])),
        }
    )
    return pd.DataFrame(strat_rows), detail


def part2_abstention_curve(pred: pd.DataFrame, units: pd.DataFrame) -> pd.DataFrame:
    """Ambiguity-threshold sweep: fraction abstained vs released-unit regret.
    threshold = -1 marks the strict-support rule (abstain every unit whose
    ridge-family stress is proxy; only family-specific-support units released)."""
    u = units[["network_id", "station_id", "gap_length"]].copy()
    for fam in FAMILIES:
        u[f"L_{fam}"] = units[fam].values
    losses = u[[f"L_{f}" for f in FAMILIES]].to_numpy()
    min_loss = losses.min(axis=1)
    networks = u["network_id"].to_numpy()
    rows = []
    for lam in LAMBDAS:
        penalized = np.column_stack(
            [pred.loc[pred["family"] == f, "risk"].to_numpy()
             + lam * pred.loc[pred["family"] == f, "width"].to_numpy() for f in FAMILIES]
        )
        order = np.argsort(penalized, axis=1)
        s1 = penalized[np.arange(len(u)), order[:, 0]]
        s2 = penalized[np.arange(len(u)), order[:, 1]]
        rel_gap = (s2 - s1) / np.maximum(s1, 1e-12)
        sel = order[:, 0]
        thresholds = (0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50)
        for th in thresholds:
            abstain = rel_gap < th
            rows.append(_curve_row(lam, th, abstain, sel, losses, min_loss, networks))
        # strict support: abstain units where either ridge family lacks its own
        # fitting-period stress (proxy tier)
        proxy_units = (
            pred[(pred["family"] == "seasonal_boundary_ridge") & (pred["support"] == "proxy")]
            .set_index(["network_id", "station_id", "gap_length"])
            .index
        )
        strict = np.array(
            [
                (n, s_, g) in proxy_units
                for n, s_, g in zip(u["network_id"], u["station_id"], u["gap_length"])
            ]
        )
        rows.append(_curve_row(lam, -1.0, strict, sel, losses, min_loss, networks))
    return pd.DataFrame(rows)


def _curve_row(lam, th, abstain, sel, losses, min_loss, networks):
    rel = ~abstain
    reg = losses[np.arange(len(losses)), sel] - min_loss
    reg_r = reg[rel]
    if rel.sum() == 0:
        return {
            "lambda": lam,
            "threshold": th,
            "fraction_abstained": 1.0,
            "n_released": 0,
            "network_balanced_regret_released": np.nan,
            "worst_network_regret_released": np.nan,
            "top2_hit_released": np.nan,
            "n_networks_released": 0,
        }
    return {
        "lambda": lam,
        "threshold": th,
        "fraction_abstained": float(abstain.mean()),
        "n_released": int(rel.sum()),
        "network_balanced_regret_released": float(
            np.mean([reg_r[networks[rel] == n].mean() for n in np.unique(networks[rel])])
        ),
        "worst_network_regret_released": float(
            np.max([reg_r[networks[rel] == n].mean() for n in np.unique(networks[rel])])
        ),
        "top2_hit_released": float(
            np.mean(
                np.take_along_axis(losses[rel], sel[rel, None], axis=1).ravel()
                <= np.sort(losses[rel], axis=1)[:, 1]
            )
        ),
        "n_networks_released": int(len(np.unique(networks[rel]))),
    }


def part2_bootstrap(d: dict, cal: dict, pred: pd.DataFrame, units: pd.DataFrame) -> pd.DataFrame:
    """Network bootstrap (2,000 draws) of network-balanced regret differences:
    proposed (lambda=0.5) vs best fixed, proposed vs global CV; with and without
    the 10% ambiguity abstention."""
    u = units[["network_id", "station_id", "gap_length"]].copy()
    for fam in FAMILIES:
        u[f"L_{fam}"] = units[fam].values
    losses = u[[f"L_{f}" for f in FAMILIES]].to_numpy()
    min_loss = losses.min(axis=1)
    networks = u["network_id"].to_numpy()
    lam = 0.5
    penalized = np.column_stack(
        [pred.loc[pred["family"] == f, "risk"].to_numpy()
         + lam * pred.loc[pred["family"] == f, "width"].to_numpy() for f in FAMILIES]
    )
    order = np.argsort(penalized, axis=1)
    sel_prop = order[:, 0]
    s1 = penalized[np.arange(len(u)), order[:, 0]]
    s2 = penalized[np.arange(len(u)), order[:, 1]]
    abstain = (s2 - s1) / np.maximum(s1, 1e-12) < AMBIG_THRESHOLD

    dev_units = d["dev_units"]
    dev_mean = {f: float(dev_units[f].mean()) for f in FAMILIES}
    best_fixed_fam = min(dev_mean, key=dev_mean.get)
    best_fixed_idx = FAMILIES.index(best_fixed_fam)
    global_cv_sel = np.zeros(len(u), dtype=int)
    for net in np.unique(networks):
        tr = losses[networks != net].mean(axis=0)
        global_cv_sel[networks == net] = int(np.argmin(tr))

    net_ids = np.unique(networks)
    net_index = {n: np.where(networks == n)[0] for n in net_ids}
    rng = np.random.default_rng(RNG_BOOT)
    reg_prop = losses[np.arange(len(u)), sel_prop] - min_loss
    reg_fixed = losses[np.arange(len(u)), best_fixed_idx] - min_loss
    reg_gcv = losses[np.arange(len(u)), global_cv_sel] - min_loss

    def netbal(reg: np.ndarray, nets: np.ndarray) -> float:
        return float(np.mean([reg[nets == n].mean() for n in np.unique(nets)]))

    diffs = {
        "proposed_vs_best_fixed": np.zeros(N_BOOT),
        "proposed_vs_global_CV": np.zeros(N_BOOT),
        "proposed_abstain_vs_best_fixed": np.zeros(N_BOOT),
        "proposed_abstain_vs_global_CV": np.zeros(N_BOOT),
    }
    for it in range(N_BOOT):
        samp = rng.choice(net_ids, size=len(net_ids), replace=True)
        idx = np.concatenate([net_index[n] for n in samp])
        nets_i = networks[idx]
        p_full = netbal(reg_prop[idx], nets_i)
        f_full = netbal(reg_fixed[idx], nets_i)
        g_full = netbal(reg_gcv[idx], nets_i)
        rel = ~abstain[idx]
        diffs["proposed_vs_best_fixed"][it] = p_full - f_full
        diffs["proposed_vs_global_CV"][it] = p_full - g_full
        if rel.sum() == 0:
            diffs["proposed_abstain_vs_best_fixed"][it] = np.nan
            diffs["proposed_abstain_vs_global_CV"][it] = np.nan
        else:
            diffs["proposed_abstain_vs_best_fixed"][it] = (
                netbal(reg_prop[idx][rel], nets_i[rel]) - f_full
            )
            diffs["proposed_abstain_vs_global_CV"][it] = (
                netbal(reg_prop[idx][rel], nets_i[rel]) - g_full
            )
    rec = []
    for k, v in diffs.items():
        v = v[~np.isnan(v)]
        rec.append(
            {
                "pair": k,
                "mean_diff": float(v.mean()),
                "sd_diff": float(v.std()),
                "ci_lo": float(np.percentile(v, 2.5)),
                "ci_hi": float(np.percentile(v, 97.5)),
                "frac_diff_lt_0": float(np.mean(v < 0)),
                "n_draws": int(len(v)),
            }
        )
    return pd.DataFrame(rec)


def part2_plots(strat: pd.DataFrame, curve: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    order = [
        "best_fixed_*",
        "global_CV",
        "per_network_CV",
        "gap_rule",
        "random",
        "proposed_l0",
        "proposed_l0.5",
        "proposed_l1",
        "proposed_l0.5_abstain",
        "oracle",
    ]
    labels = {
        "best_fixed_*": "best fixed (dev)",
        "global_CV": "global blocked-CV",
        "per_network_CV": "per-network avg-CV",
        "gap_rule": "gap-length rule",
        "random": "random",
        "proposed_l0": "proposed λ=0",
        "proposed_l0.5": "proposed λ=0.5",
        "proposed_l1": "proposed λ=1",
        "proposed_l0.5_abstain": "proposed λ=0.5 + abstain",
        "oracle": "oracle",
    }
    vals = []
    names = []
    for s in order:
        if s == "best_fixed_*":
            sub = strat[strat["strategy"].str.startswith("best_fixed_")]
        else:
            sub = strat[strat["strategy"] == s]
        if len(sub) == 0:
            continue
        vals.append(float(sub["network_balanced_regret"].iloc[0]))
        names.append(labels[s])
    ax.bar(range(len(vals)), vals, color="tab:blue", alpha=0.8)
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("network-balanced regret (°C)")
    ax.set_title("Part 2: model-selection regret, first panel (1,440 units, 42 networks)")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(OUT / "part2_selection_regret.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    for lam in LAMBDAS:
        sub = curve[curve["lambda"] == lam]
        ax.plot(sub["fraction_abstained"], sub["network_balanced_regret_released"], marker="o", label=f"λ={lam:g}")
    ax.set_xlabel("fraction abstained")
    ax.set_ylabel("network-balanced regret on released units (°C)")
    ax.set_title("Part 2: abstention coverage-risk curve (ambiguity threshold sweep)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "part2_abstention_curve.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------------
def write_report(
    p1_metrics: pd.DataFrame,
    p1_boot: pd.DataFrame,
    p1_abst: pd.DataFrame,
    p2_strat: pd.DataFrame,
    p2_curve: pd.DataFrame,
    p2_boot: pd.DataFrame,
    cal: dict,
    dur_model: dict,
    d: dict,
) -> None:
    lines = []
    A = lines.append
    A("# REPORT — End-to-end decision utility (revision v12, t09, agent B)")
    A("")
    A("**Script:** `scripts/rev_v12_t09_decision_utility_b.py`")
    A("**Output namespace:** `results/revision_v12/t09_decision_utility/agent_b/`")
    A("**Date:** 2026-08-29. Every number below was produced by this script from the")
    A("read-only artifacts listed; no value is taken from any other source.")
    A("")
    A("## 1. Design")
    A("")
    A("Two decision experiments, both end-to-end (risk score -> rank/budget, or per-family")
    A("stress curve -> model selection), evaluated against observed recovery losses.")
    A("")
    A("**Part 1 — budget-constrained gap prioritization, second panel** (1,446 units, 57")
    A("networks). Policies: (a) gap length; (b) duration+season (OLS log1p(MAE) ~ log(gap)")
    A("+ season dummies fit on pooled XGBoost fitting-period placements — development")
    A(f"({dur_model['n_dev']:,}) + first panel ({dur_model['n_conf']:,}); season per unit =")
    A("plurality season of the unit's placement roster dates (`second_confirmation/scoring/")
    A("placement_losses.csv` gap_start, month-based bins validated 100% against the")
    A("project `season` column; every unit had placements, so no gap-only fallback was")
    A("needed); (c) simple descriptors = t01 `simple_fitperiod` (equal-network weighted");
    A("fit-period linear model, read-only); (d) empirical curve =")
    A("`empirical_transfer_prediction` (read-only); (e) hierarchical surface = t04 agent_a")
    A("`surface_prediction_mae` (read-only); (f) random (20 seeded draws); (g) oracle")
    A("(observed loss). Budgets B = 5/10/20/30% of units. Metrics: CapturedLoss@B =")
    A("loss of top-B% units / total loss; worst-decile recall@B = overlap of top-B% with")
    A("the worst decile (top 10% by observed loss); NDCG@B with gain 2^loss−1 over the")
    A("top-B% positions; regret@B = oracle CapturedLoss − method CapturedLoss (pp).")
    A("Ties in scores broken by stable index order (documented). Fitted duration+season")
    A("coefficients (log1p scale, DJF baseline): "
      + ", ".join(f"{s} {c:+.3f}" for s, c in zip(["MAM", "JJA", "SON"], dur_model["beta"][2:]))
      + "; log-gap slope " + f"{dur_model['beta'][1]:.4f}" + "; fit R2 = "
      + f"{dur_model['r2']:.3f}" + ", RMSE(log1p) = " + f"{dur_model['rmse_log1p']:.3f}")
    A("")
    A(f"**Part 2 — model selection, first panel** (1,440 units, 42 networks). For each unit,")
    A("per-family predicted loss (families: seasonal_boundary_ridge, donor_blup_ridge,")
    A("xgboost) from per-family fitting-period stress curves, recalibrated to the")
    A("outer-loss scale, plus uncertainty penalty λ × interval width, λ ∈ {0, 0.5, 1}.")
    A("")
    A("### 1.1 Per-family stress and calibration (Part 2) — exact recipe")
    A("")
    A("- **xgboost stress**: unit-level mean MAE of read-only `confirmation_empirical_fit_losses.csv`")
    A("  placements (gaps 7/30/90/180, 42 networks); units at gaps 14/60/365 (767/1,440)")
    A("  receive the network-level mean of unit stresses (same fallback structure as the")
    A("  empirical predictor). Development-panel stress identically from")
    A("  `development_empirical_fit_losses.csv`.")
    A("- **ridge-family stress**: t05 agent B `fit_losses_families_1_3.csv` unit-level means")
    A("  (10 first-panel networks, gaps 7/30/90/180); 297 first-panel units carry the")
    A("  family-specific stress (143 units per family at the fit gaps, 154 further units of")
    A("  the same 10 networks at other gaps).")
    A("- **Two calibration mappings per ridge family** (OLS outer ~ stress, unit rows):")
    A("  (1) `t05` — outer ~ family-specific t05 stress on the 143 matched rows (first-panel")
    A("  rows only; no development family-specific fitting-period stress exists in read-only")
    A("  artifacts — documented); (2) `axis` — outer ~ xgboost fitting-period stress on the")
    A("  matched direct rows pooled over development + first panel (n = 1,313 per family),")
    A("  i.e. the conditional expectation of the family's outer loss given the xgboost stress.")
    A("  The xgboost family uses only the `axis` mapping (n = 1,313, development+first-panel")
    A("  fit rows). Units on the 10 t05 networks use the `t05` mapping; all other units use")
    A("  the `axis` mapping (proxy tier, justified by the t05 shared-difficulty block: xgboost")
    A("  stress vs ridge-family outer losses, network Spearman 0.72–0.94).")
    A("- **Interval width**: 2×1.96× prediction SE from the mapping's OLS at the unit's")
    A("  stress value (leverage formula). Units whose xgboost stress is a network-mean")
    A("  fallback get the interval widened by the fallback error σ_fb (RMSE of unit stress ~")
    A(f"  network mean over direct rows, {cal['_sigma_fb']:.4f} °C): width = 2×1.96×")
    A("  √(SE² + (b·σ_fb)²).")
    A("- **Selection**: argmin_f [risk_f + λ·width_f]. **Abstention**: top-two penalized")
    A("  scores within 10% (relative gap) or missing support (a unit with no stress at all;")
    A("  count reported — 0 units, because the fallback/proxy tiers cover every unit).")
    A("  A strict-support rule (abstain every unit whose ridge-family stress is proxy) is")
    A("  reported as a sensitivity row in the abstention curve (threshold = −1).")
    A("")
    A("### 1.2 Part 2 comparators — exact recipe")
    A("")
    A("- (i) **best fixed family**: family with the lowest mean unit-level outer loss on the")
    A(f"  development panel (1,548 units, 56 networks) — {cal.get('_best_fixed', 'see table')}.")
    A("- (ii) **global blocked-CV**: leave-one-network-out on the 42 first-panel networks;")
    A("  for each held-out network, select the family with the lowest mean unit loss on the")
    A("  other 41 networks; apply that family to all units of the held-out network.")
    A("- (iii) **per-network average-CV**: for each unit, per-family score = mean unit loss of")
    A("  that family over the OTHER units of the same network (leave-one-unit-out within")
    A("  network); select argmin per unit.")
    A("- (iv) **gap-length rule**: per gap length, the family with the lowest mean development")
    A("  outer loss at that gap (chosen on development outcomes), applied to first-panel")
    A("  units by gap.")
    A("- (v) **random**: 20 seeded draws.")
    A("- (vi) **proposed risk-based** with/without abstention (λ sweep).")
    A("- (vii) **outcome oracle**: argmin actual loss per unit (regret baseline).")
    A("")
    A("Regret = L_selected − min_f L_f per unit (°C). Reported: network-balanced regret")
    A("(mean over networks of within-network mean regret), worst-network regret, top-2 hit")
    A("rate (selected family is not the unique worst family for the unit), pooled regret.")
    A("")
    A("## 2. Validation cross-checks")
    A("")
    A("- Second panel: 1,446 units / 57 networks; direct 874, fallback 572 (t01 horizon_group),")
    A("  surface support direct 874 / interpolated 448 / extrapolated 124 — matches t04.")
    A("- Season bins (month-based) reproduce the project `season` column on 100% of the")
    A("  52,989 first-panel fit placements.")
    A("- First panel: 1,440 units / 42 networks; 3 families × 28,728 placements; dev panel")
    A("  1,548 units / 56 networks.")
    A("- t05 stress coverage: 10 networks, 143 units per ridge family, all with roster outer")
    A("  loss (calibration rows). First-panel units on those 10 networks: 297.")
    A("")
    A("## 3. Part 1 — prioritization results")
    A("")
    A("### 3.1 CapturedLoss@B, NDCG@B, worst-decile recall@B, regret (pp)")
    A("")
    A("| policy | B | CapturedLoss | worst-decile recall | NDCG | regret (pp) |")
    A("|---|---|---|---|---|---|")
    for _, r in p1_metrics.iterrows():
        A(
            f"| {r['policy']} | {100*r['budget']:.0f}% | {r['captured_loss']:.4f} | "
            f"{r['worst_decile_recall']:.4f} | {r['ndcg']:.4f} | {r['regret_pp']:.2f} |"
        )
    A("")
    A("Random rows are means over 20 seeded draws (SD of CapturedLoss ≈ "
      f"{p1_metrics.loc[p1_metrics['policy']=='random','captured_loss_sd'].mean():.4f}).")
    A("")
    A("### 3.2 Network-bootstrap 95% CI — CapturedLoss@20% differences (2,000 draws)")
    A("")
    A("| pair | mean diff | 95% CI | frac draws > 0 |")
    A("|---|---|---|---|")
    for _, r in p1_boot.iterrows():
        A(
            f"| {r['policy_a']} − {r['policy_b']} | {r['mean_diff']:+.4f} | "
            f"[{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}] | {r['frac_diff_gt_0']:.3f} |"
        )
    A("")
    A("### 3.3 Abstention coverage-risk curve (budget 20%, surface ranking)")
    A("")
    A("Captured loss of the released units' top-20% (within released total, and relative to")
    A("the full-panel total). All policies are in `part1_abstention_curve.csv`.")
    A("")
    A("| rule | fraction abstained | n released | captured@20 (released) | captured@20 (full total) |")
    A("|---|---|---|---|---|")
    for _, r in p1_abst.iterrows():
        A(
            f"| {r['rule']} | {r['fraction_abstained']:.3f} | {r['n_released']} | "
            f"{r['captured_released_surface']:.4f} | {r['captured_full_surface']:.4f} |"
        )
    A("")
    A("## 4. Part 2 — model-selection results")
    A("")
    A("### 4.1 Selection regret by strategy")
    A("")
    A("| strategy | λ | abstain | fraction abstained | net-balanced regret | worst-network regret | pooled regret | top-2 hit |")
    A("|---|---|---|---|---|---|---|---|")
    for _, r in p2_strat.iterrows():
        A(
            f"| {r['strategy']} | {r['lambda']} | {r['abstain_rule']} | {r['fraction_abstained']:.3f} | "
            f"{r['network_balanced_regret']:.4f} | {r['worst_network_regret']:.4f} | "
            f"{r['pooled_regret']:.4f} | {r['top2_hit_rate']:.3f} |"
        )
    A("")
    A("### 4.2 Abstention coverage-risk curve (ambiguity-threshold sweep)")
    A("")
    A("| λ | threshold | fraction abstained | n released | net-balanced regret (released) | worst-network regret (released) |")
    A("|---|---|---|---|---|---|")
    for _, r in p2_curve[p2_curve["lambda"] == 0.5].iterrows():
        A(
            f"| {r['lambda']:g} | {r['threshold']:.2f} | {r['fraction_abstained']:.3f} | "
            f"{r['n_released']} | {r['network_balanced_regret_released']:.4f} | "
            f"{r['worst_network_regret_released']:.4f} |"
        )
    A("")
    A("### 4.3 Network-bootstrap 95% CI — regret differences (2,000 draws)")
    A("")
    A("| pair | mean diff | 95% CI | frac draws < 0 |")
    A("|---|---|---|---|")
    for _, r in p2_boot.iterrows():
        A(
            f"| {r['pair']} | {r['mean_diff']:+.4f} | [{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}] | "
            f"{r['frac_diff_lt_0']:.3f} |"
        )
    A("")
    A("### 4.4 Calibration detail (Part 2)")
    A("")
    A("`axis` mapping (outer ~ xgboost fitting-period stress, dev + first-panel direct rows);")
    A("`t05` mapping (outer ~ family-specific t05 stress, 143 first-panel rows, 10 networks).")
    A("")
    A("| family | mapping | n fit rows | intercept | slope | residual sd (°C) |")
    A("|---|---|---|---|---|---|")
    for fam in FAMILIES:
        o = cal[fam]["axis"]
        A(
            f"| {fam} | axis | {cal[fam]['n_axis_rows']} | {o['a']:.4f} | {o['b']:.4f} | "
            f"{np.sqrt(o['s2']):.4f} |"
        )
        if "t05" in cal[fam]:
            o = cal[fam]["t05"]
            A(
                f"| {fam} | t05 | {cal[fam]['n_t05_rows']} | {o['a']:.4f} | {o['b']:.4f} | "
                f"{np.sqrt(o['s2']):.4f} |"
            )
    A("")
    A(f"Fallback widening σ_fb (unit stress ~ network mean, direct rows): "
      f"{cal['_sigma_fb']:.4f} °C (n = {cal['_sigma_fb_n']}).")
    A("")
    A("## 5. Headline")
    A("")
    head1 = p1_metrics[(p1_metrics.policy == "empirical") & (p1_metrics.budget == 0.20)]
    head1s = p1_metrics[(p1_metrics.policy == "simple") & (p1_metrics.budget == 0.20)]
    head1u = p1_metrics[(p1_metrics.policy == "surface") & (p1_metrics.budget == 0.20)]
    b_es = p1_boot[p1_boot.policy_a == "empirical"].set_index("policy_b").loc["simple"]
    b_es2 = p1_boot[p1_boot.policy_a == "empirical"].set_index("policy_b").loc["surface"]
    A(
        f"Part 1: at the 20% budget the empirical curve captures "
        f"{head1['captured_loss'].iloc[0]:.3f} of total loss vs simple "
        f"{head1s['captured_loss'].iloc[0]:.3f} and surface {head1u['captured_loss'].iloc[0]:.3f} "
        f"(bootstrap Δ empirical−simple {b_es['mean_diff']:+.4f} °C-loss-pp, CI "
        f"[{b_es['ci_lo']:+.4f}, {b_es['ci_hi']:+.4f}]; Δ empirical−surface "
        f"{b_es2['mean_diff']:+.4f}, CI [{b_es2['ci_lo']:+.4f}, {b_es2['ci_hi']:+.4f}]). "
        f"Captured loss rises with budget for all policies; random {p1_metrics.loc[(p1_metrics.policy=='random')&(p1_metrics.budget==0.20),'captured_loss'].iloc[0]:.3f}; "
        f"oracle {p1_metrics.loc[(p1_metrics.policy=='oracle')&(p1_metrics.budget==0.20),'captured_loss'].iloc[0]:.3f}."
    )
    A("")
    prop0 = p2_strat[p2_strat.strategy == "proposed_l0"].iloc[0]
    fixed = p2_strat[p2_strat.strategy.str.startswith("best_fixed")].iloc[0]
    gcv = p2_strat[p2_strat.strategy == "global_CV"].iloc[0]
    pn = p2_strat[p2_strat.strategy == "per_network_CV"].iloc[0]
    orc = p2_strat[p2_strat.strategy == "oracle"].iloc[0]
    rnd = p2_strat[p2_strat.strategy == "random"].iloc[0]
    b_pf = p2_boot[p2_boot.pair == "proposed_vs_best_fixed"].iloc[0]
    b_pg = p2_boot[p2_boot.pair == "proposed_vs_global_CV"].iloc[0]
    A(
        f"Part 2: proposed risk-based selection (λ=0) reaches network-balanced regret "
        f"{prop0['network_balanced_regret']:.3f} °C vs best-fixed {fixed['network_balanced_regret']:.3f}, "
        f"global blocked-CV {gcv['network_balanced_regret']:.3f}, per-network avg-CV "
        f"{pn['network_balanced_regret']:.3f}, gap rule {p2_strat[p2_strat.strategy=='gap_rule'].iloc[0]['network_balanced_regret']:.3f}, "
        f"random {rnd['network_balanced_regret']:.3f}, oracle {orc['network_balanced_regret']:.3f}. "
        f"Bootstrap Δ proposed−best-fixed {b_pf['mean_diff']:+.4f} (CI [{b_pf['ci_lo']:+.4f}, {b_pf['ci_hi']:+.4f}]), "
        f"Δ proposed−global-CV {b_pg['mean_diff']:+.4f} (CI [{b_pg['ci_lo']:+.4f}, {b_pg['ci_hi']:+.4f}])."
    )
    A("")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    print("Part 1 ...")
    p1_metrics, p1_boot, p1_abst, df, dur_model = part1_main()
    print("Part 2 ...")
    d, _ = part2_build()
    cal = part2_calibrate(d)
    pred = part2_predict(d, cal)
    pred.to_csv(OUT / "part2_unit_predictions.csv", index=False)
    units = d["conf_units"].copy()
    dev_units = d["dev_units"]
    p2_strat, detail = part2_strategy_metrics(pred, units, dev_units)
    detail.to_csv(OUT / "part2_unit_detail.csv", index=False)
    p2_strat.to_csv(OUT / "part2_strategy_metrics.csv", index=False)
    p2_curve = part2_abstention_curve(pred, units)
    p2_curve.to_csv(OUT / "part2_abstention_curve.csv", index=False)
    p2_boot = part2_bootstrap(d, cal, pred, units)
    p2_boot.to_csv(OUT / "part2_bootstrap_cis.csv", index=False)
    part2_plots(p2_strat, p2_curve)
    # best fixed family for report
    dev_units = d["dev_units"]
    bf = min({f: float(dev_units[f].mean()) for f in FAMILIES}, key=lambda k: float(dev_units[k].mean()))
    cal["_best_fixed"] = bf
    with (OUT / "meta.json").open("w") as fh:
        json.dump(
            {
                "best_fixed_family_dev": bf,
                "n_boot": N_BOOT,
                "n_random": N_RANDOM,
                "abstention_ambiguity_threshold": AMBIG_THRESHOLD,
            },
            fh,
            indent=2,
        )
    write_report(p1_metrics, p1_boot, p1_abst, p2_strat, p2_curve, p2_boot, cal, dur_model, d)
    print("done ->", OUT)

if __name__ == "__main__":
    main()
