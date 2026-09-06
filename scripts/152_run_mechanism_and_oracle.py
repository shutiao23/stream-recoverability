"""v15 evidence: the benefit law, its station-level prediction, the regime
structure, and within-duration budget sweeps with oracle/random brackets.

Four analyses that the v14 package does not contain, all on archived artifacts
(no model refits):

  A. Benefit decomposition        -> climatology MAE is flat in gap length while
                                     model MAE grows ~10x; the crossing is where
                                     the model curve meets the station's own
                                     climatological MAE.
  B. Station-level prediction     -> stations with higher climatological MAE
                                     cross later (the mechanism's testable
                                     consequence).
  C. Regime structure             -> default-difficulty suffices at short gaps,
                                     negated model error at long gaps; the
                                     differential curve is irreplaceable only in
                                     the transition zone (inverted U, peak 90 d).
  D. Budget sweep with brackets   -> within-duration budgets over
                                     B in {5,10,20,30,50}% with oracle and random
                                     rows, and the fraction of achievable value
                                     captured.

Writes results/v14/p5_mechanism/.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
OUT = ROOT / "results/v14/p5_mechanism"
SEED = 20260905

PANEL_LOSSES = {
    "first": ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv",
    "second": ROOT / "results/development_v11/second_confirmation/scoring/placement_losses.csv",
}
PANEL_PRED = {
    p: ROOT / f"results/v14/p0_differential/placement_predictions_{p}.csv"
    for p in ("first", "second")
}
PREDICTORS = {
    "diff": ("diff_prediction", +1),
    "neg_risk": ("risk_prediction", -1),
    "default_difficulty": ("default_difficulty_prediction", +1),
    "r6_diff": ("r6_diff_prediction", +1),
}
BUDGETS = (0.05, 0.10, 0.20, 0.30, 0.50)


def rho(a, b) -> float:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    return float(spearmanr(a[m], b[m]).statistic) if m.sum() > 3 else np.nan


def direct(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["direct"].astype(str).str.lower().isin({"true", "1"})]


def a_decomposition() -> pd.DataFrame:
    rows = []
    for panel, path in PANEL_LOSSES.items():
        p = pd.read_csv(path, usecols=["gap_length", "mae_deg_c", "climatology_mae_deg_c"])
        g = p.groupby("gap_length").agg(
            model_mae=("mae_deg_c", "mean"), clim_mae=("climatology_mae_deg_c", "mean")
        )
        g["benefit"] = g.clim_mae - g.model_mae
        g["model_rel_7d"] = g.model_mae / g.model_mae.iloc[0]
        g["clim_rel_7d"] = g.clim_mae / g.clim_mae.iloc[0]
        rows.append(g.reset_index().assign(panel=panel))
    return pd.concat(rows, ignore_index=True)


def b_station_prediction() -> tuple[pd.DataFrame, pd.DataFrame]:
    per_station, summary = [], []
    for panel, path in PANEL_LOSSES.items():
        p = pd.read_csv(
            path,
            usecols=[
                "network_id",
                "station_id",
                "gap_length",
                "mae_deg_c",
                "climatology_mae_deg_c",
            ],
        )
        st = (
            p.groupby(["network_id", "station_id", "gap_length"])
            .agg(model=("mae_deg_c", "mean"), clim=("climatology_mae_deg_c", "mean"))
            .reset_index()
        )
        st["benefit"] = st.clim - st.model
        rows = []
        for (net, sta), g in st.groupby(["network_id", "station_id"]):
            g = g.sort_values("gap_length")
            b = g.benefit.to_numpy()
            d = g.gap_length.to_numpy(float)
            if b[0] <= 0 or b[-1] >= 0:  # needs a single interpolable sign change
                continue
            i = int(np.where(b < 0)[0][0])
            x0, x1 = np.log10(d[i - 1]), np.log10(d[i])
            y0, y1 = b[i - 1], b[i]
            rows.append(
                {
                    "panel": panel,
                    "network_id": net,
                    "station_id": sta,
                    "crossing_days": 10 ** (x0 + (x1 - x0) * y0 / (y0 - y1)),
                    "station_clim_mae": float(g.clim.mean()),
                }
            )
        frame = pd.DataFrame(rows)
        per_station.append(frame)
        r = spearmanr(frame.station_clim_mae, np.log10(frame.crossing_days))
        q = pd.qcut(frame.station_clim_mae, 4, labels=["Q1", "Q2", "Q3", "Q4"])
        tab = (
            frame.groupby(q, observed=True)
            .agg(
                n=("crossing_days", "size"),
                clim_mae=("station_clim_mae", "mean"),
                median_crossing_days=("crossing_days", "median"),
            )
            .reset_index()
            .assign(panel=panel, spearman=float(r.statistic), p_value=float(r.pvalue))
        )
        summary.append(tab)
    return pd.concat(per_station, ignore_index=True), pd.concat(summary, ignore_index=True)


def c_regime() -> pd.DataFrame:
    rows = []
    for panel, path in PANEL_PRED.items():
        d = direct(pd.read_csv(path))
        for h, g in d.groupby("gap_length"):
            y = g.realized_benefit
            vals = {
                name: rho(sign * g[col], y) for name, (col, sign) in PREDICTORS.items()
            }
            best_single = max(vals["neg_risk"], vals["default_difficulty"])
            rows.append(
                {
                    "panel": panel,
                    "gap_length": h,
                    "n_placements": len(g),
                    **vals,
                    "best_single_term": best_single,
                    "diff_advantage": vals["diff"] - best_single,
                }
            )
    return pd.DataFrame(rows)


def d_budget_brackets() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []
    for panel, path in PANEL_PRED.items():
        d = direct(pd.read_csv(path))
        for h, g in d.groupby("gap_length"):
            y = g.realized_benefit.to_numpy(float)
            n = len(y)
            for budget in BUDGETS:
                k = max(1, int(round(budget * n)))
                oracle = np.sort(y)[::-1][:k].mean()
                random = float(
                    np.mean([y[rng.choice(n, k, replace=False)].mean() for _ in range(200)])
                )
                rec = {
                    "panel": panel,
                    "gap_length": h,
                    "budget": budget,
                    "n": n,
                    "k": k,
                    "stratum_mean": float(y.mean()),
                    "oracle": oracle,
                    "random": random,
                }
                span = oracle - random
                for name, (col, sign) in PREDICTORS.items():
                    sel = np.argsort(-(sign * g[col].to_numpy(float)), kind="stable")[:k]
                    rec[name] = float(y[sel].mean())
                    rec[f"capture_{name}"] = (
                        (rec[name] - random) / span if span > 1e-9 else np.nan
                    )
                rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dec = a_decomposition()
    stations, station_summary = b_station_prediction()
    regime = c_regime()
    budget = d_budget_brackets()

    dec.to_csv(OUT / "benefit_decomposition.csv", index=False)
    stations.to_csv(OUT / "station_crossings.csv", index=False)
    station_summary.to_csv(OUT / "station_crossing_summary.csv", index=False)
    regime.to_csv(OUT / "regime_structure.csv", index=False)
    budget.to_csv(OUT / "budget_brackets.csv", index=False)

    print("A. Benefit decomposition (climatology is flat, model grows)")
    print(dec.round(3).to_string(index=False), "\n")
    print("B. Station-level crossing vs the station's own climatological MAE")
    print(station_summary.round(3).to_string(index=False), "\n")
    print("C. Regime structure (diff advantage over the best single-term shortcut)")
    print(regime.round(3).to_string(index=False), "\n")
    print("D. Fraction of achievable value captured, mean over budgets")
    cap = budget.groupby(["panel", "gap_length"])[
        [c for c in budget.columns if c.startswith("capture_")]
    ].mean()
    print(cap.round(3).to_string())
    print(f"\nWrote 5 CSVs to {OUT}")


if __name__ == "__main__":
    main()
