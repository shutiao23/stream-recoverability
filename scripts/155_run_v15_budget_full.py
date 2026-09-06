#!/usr/bin/env python3
"""v15/W2.1: the complete within-duration budget sweep (WORKPLAN_v15.md
Step 2.1).

Extends the P1 budget table (which existed only at B = 0.20) to the five
registered sweep budgets B in {5, 10, 20, 30, 50}% for the full Tier-0
predictor suite, adds the negated-risk comparator, the within-stratum
oracle/random brackets, capture rates, and 95% network-cluster bootstrap CIs
(2,000 draws, seed 20260903, within provider strata on the second panel).

Selection convention mirrors scripts/143 (P1): descending predicted value,
seeded tie-break per (panel, horizon, predictor) so that the top-k set at any
budget is a prefix of the P1 B = 0.20 top-20% set — the B = 0.20 column
reproduces results/v14/p1_baselines/budget_within_duration.csv exactly.

Outputs: results/v15/budget_full/{budget_full.csv, budget_full_ci.csv, README.md}

Run: PYTHONPATH=$PWD/src python3 scripts/155_run_v15_budget_full.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P1 = ROOT / "results/v14/p1_baselines"
OUT = ROOT / "results/v15/budget_full"
SEED_BOOT = 20260903
SEED_RANDOM = 20260905
N_BOOT = 2000
N_RANDOM = 200

PREDICTORS = [
    ("diff", "diff_prediction", +1),
    ("risk", "risk_prediction", +1),
    ("neg_risk", "risk_prediction", -1),
    ("duration", "duration_only_prediction", +1),
    ("r6_diff", "r6_diff_prediction", +1),
    ("default_difficulty", "default_difficulty_prediction", +1),
    ("rh_error", "rh_error_prediction", +1),
    ("rh_benefit", "rh_benefit_prediction", +1),
    ("amplitude", "amplitude_prediction", +1),
    ("sd", "sd_prediction", +1),
    ("global", "global_prediction", +1),
]
CI_PREDICTORS = [
    ("diff", "diff_prediction", +1),
    ("risk", "risk_prediction", +1),
    ("neg_risk", "risk_prediction", -1),
    ("duration", "duration_only_prediction", +1),
    ("r6_diff", "r6_diff_prediction", +1),
    ("default_difficulty", "default_difficulty_prediction", +1),
]
BUDGETS = (0.05, 0.10, 0.20, 0.30, 0.50)
DURATIONS = (7, 14, 30, 60, 90, 180)
ROSTER = {
    "first": ROOT / "results/development_v11/route_a_confirmation/qualified_panel.csv",
    "second": ROOT / "results/development_v11/second_confirmation/frozen_scoring_roster_v2.csv",
}


def load_panel(panel: str) -> pd.DataFrame:
    d = pd.read_csv(P1 / f"placement_predictions_{panel}.csv")
    d = d.loc[d["direct"].astype(str).str.lower().isin({"true", "1"})].copy()
    d["gap_length"] = d["gap_length"].astype(int)
    d = d.loc[d["gap_length"].isin(DURATIONS)].copy()
    roster = pd.read_csv(ROSTER[panel], usecols=["network_id", "provider"])
    d = d.merge(roster, on="network_id", how="left", validate="many_to_one")
    assert d["provider"].notna().all(), f"{panel}: networks without provider"
    d = d.reset_index(drop=True)
    return d


def tie_jitter(n: int, predictor: str, panel: str, horizon: int) -> np.ndarray:
    seed = int.from_bytes(f"{panel}|{horizon}|{predictor}".encode(),
                          byteorder="big") % (2**32)
    return np.random.default_rng(seed).random(n)


def point_cell(frame: pd.DataFrame, panel: str, horizon: int,
               budget: float) -> list[dict]:
    n = len(frame)
    k = max(1, round(budget * n))
    y = frame["realized_benefit"].to_numpy(float)
    rng = np.random.default_rng(SEED_RANDOM)
    random_mean = float(np.mean([
        y[rng.choice(n, k, replace=False)].mean() for _ in range(N_RANDOM)
    ]))
    oracle = float(np.sort(y)[::-1][:k].mean())
    span = oracle - random_mean
    rows = []
    base = {"panel": panel, "horizon": horizon, "budget": budget,
            "n": n, "k": k, "stratum_mean": float(y.mean()),
            "oracle": oracle, "random": random_mean}
    pos = np.arange(n)
    for name, col, sign in PREDICTORS:
        v = frame[col].to_numpy(float)
        m = np.isfinite(v)
        if not m.any():
            continue
        vv = sign * v[m]
        order = np.lexsort((tie_jitter(m.sum(), name, panel, horizon), -vv))
        sel = pos[m][order][:k]
        treated = float(y[sel].mean())
        rows.append({**base, "predictor": name, "treated_mean": treated,
                     "harmful_rate": float((y[sel] < 0).mean()),
                     "capture": (treated - random_mean) / span
                     if abs(span) > 1e-9 else np.nan})
    return rows


def _cluster_draws(frame: pd.DataFrame, panel: str, k: int,
                   selector: callable) -> list[float]:
    net_col = frame["network_id"].to_numpy()
    y = frame["realized_benefit"].to_numpy(float)
    nets = np.unique(net_col)
    per_net = {net: np.where(net_col == net)[0] for net in nets}
    if panel == "second":
        prov_col = frame["provider"].to_numpy()
        net_prov = {net: np.unique(prov_col[net_col == net])[0] for net in nets}
    else:
        net_prov = {net: "all" for net in nets}
    provs = list(dict.fromkeys(net_prov.values()))
    rng = np.random.default_rng(SEED_BOOT)
    draws = []
    for _ in range(N_BOOT):
        idx_list = []
        for prov in provs:
            pool = np.array([net for net in nets if net_prov[net] == prov])
            for net in rng.choice(pool, len(pool), replace=True):
                idx_list.append(per_net[net])
        idx = np.concatenate(idx_list)
        draws.append(float(selector(idx, y)[: min(k, len(idx))].mean()))
    return draws


def bootstrap_ci(frame: pd.DataFrame, panel: str, horizon: int, budget: float,
                 predictor: str, col: str, sign: int) -> tuple[float, float]:
    n = len(frame)
    k = max(1, round(budget * n))
    v = sign * frame[col].to_numpy(float)
    jit = tie_jitter(n, predictor, panel, horizon)

    def selector(idx, y):
        order = np.lexsort((jit[idx], -v[idx]))
        return y[idx[order]]

    draws = _cluster_draws(frame, panel, k, selector)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def bootstrap_oracle(frame: pd.DataFrame, panel: str, horizon: int,
                     budget: float) -> tuple[float, float]:
    n = len(frame)
    k = max(1, round(budget * n))

    def selector(idx, y):
        return np.sort(y[idx])[::-1]

    draws = _cluster_draws(frame, panel, k, selector)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    point_rows: list[dict] = []
    ci_rows: list[dict] = []
    for panel in ("first", "second"):
        d = load_panel(panel)
        for horizon, g in d.groupby("gap_length"):
            for budget in BUDGETS:
                point_rows.extend(point_cell(g, panel, int(horizon), budget))
                lo, hi = bootstrap_oracle(g, panel, int(horizon), budget)
                ci_rows.append({"panel": panel, "horizon": int(horizon),
                                "budget": budget, "predictor": "oracle",
                                "ci_low": lo, "ci_high": hi})
                for name, col, sign in CI_PREDICTORS:
                    lo, hi = bootstrap_ci(g, panel, int(horizon), budget,
                                          name, col, sign)
                    ci_rows.append({"panel": panel, "horizon": int(horizon),
                                    "budget": budget, "predictor": name,
                                    "ci_low": lo, "ci_high": hi})
    points = pd.DataFrame(point_rows)
    cis = pd.DataFrame(ci_rows)
    points.to_csv(OUT / "budget_full.csv", index=False)
    cis.to_csv(OUT / "budget_full_ci.csv", index=False)

    p1 = pd.read_csv(P1 / "budget_within_duration.csv")
    p1 = p1.loc[p1["horizon"].astype(str) != "direct"]
    chk = points.loc[points["budget"] == 0.20]
    n_chk = 0
    for _, row in p1.iterrows():
        mine = chk.loc[(chk["panel"] == row["panel"])
                       & (chk["horizon"] == int(row["horizon"]))
                       & (chk["predictor"] == row["predictor"])]
        if not len(mine):
            continue
        n_chk += 1
        assert abs(float(mine.iloc[0]["treated_mean"])
                   - float(row["mean_realized_benefit"])) < 1e-9, (
            f"mismatch {row['panel']} {row['horizon']} {row['predictor']}"
        )
    print(f"B=0.20 reproduces P1 budget_within_duration.csv exactly "
          f"({n_chk} rows checked).")
    piv = points.pivot_table(index=["panel", "horizon"], columns="predictor",
                             values="treated_mean")
    print(piv.round(3).to_string())
    print(f"\nWrote {OUT}/budget_full.csv ({len(points)} rows) and "
          f"budget_full_ci.csv ({len(cis)} rows)")


if __name__ == "__main__":
    main()
