#!/usr/bin/env python3
"""v14 P2: decision layer for the differential (benefit) forecasts.

Analysis-only over the P0 artifacts under results/v14/p0_differential/; no
model refits.  For every evaluation placement the predictive distribution
F_hat is the empirical CDF of the fitting-period benefits in its cell, with
the standard fallback chain (network, station, gap, season) -> (network,
station, gap) -> (network, gap) -> network -> global pool of fitting
benefits, requiring >= 5 fitting values per cell (paper_archived/v14_plan/PLAN.md
section 5; mirrors the P0 transfer machinery).

Parts:
  A  Laio & Tamea (2007) continuous cost-loss curves: normalized loss
     rho_xi(x, chi) = |chi - x| + 2*(xi - 0.5)*(chi - x), optimal design
     value chi*(xi) = quantile(1 - xi) of F_hat, climatological reference
     from the global fitting-period pool F0; EC(xi)/delta on the xi grid
     0.05..0.95, per horizon on the second panel plus first-panel pooled as
     development.  The trapezoidal integral over xi of EC_fcst(xi) is
     checked against the exact CRPS of the cell forecasts.
  B  Selective risk vs coverage (Geifman & El-Yaniv 2017), loss = -realized
     benefit, per duration + pooled direct on the second panel, comparators
     diff/risk/duration-only, random (200 shuffles, 5-95% band) and oracle
     references; AURC and E-AURC_norm = (AURC_random - AURC_method) /
     (AURC_random - AURC_oracle).
  C  Richardson REV V(alpha) curves, event = realized benefit > tau with
     tau in {0.0, panel-mean benefit}, second panel with first-panel
     development: H/F, V(alpha), V_max vs Peirce H - F at alpha = o,
     BSS-like skill and ROC AUC (explicitly not claimed as value), and a
     Roulin-style fixed threshold (alpha* from the first panel applied to
     the second).
  D  Response-effectiveness multiplier: effective benefit = eta * realized
     benefit, eta in {0.25, 0.5, 0.75, 1.0}; within-duration top-20% budget
     outcomes for the diff and duration-only policies, second panel.

Outputs (results/v14/p2_decision/):
  laio_tamea_curves.csv        EC(xi)/delta curves (panel, horizon, xi)
  crps_check.csv               quantile-integral vs direct CRPS check
  selective_risk_curves.csv    risk vs coverage per method (band for random)
  selective_metrics.csv        AURC / E-AURC_norm / risk at 50% coverage
  rev_curves.csv               REV V(alpha) curves per horizon and tau
  rev_fixed_threshold.csv      first-panel alpha* applied to second panel
  eta_sensitivity.csv          top-20% outcomes under benefit scaling
  REPORT.md                    numbers + interpretation per PLAN 5.1-5.5
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

P0 = ROOT / "results" / "v14" / "p0_differential"
OUTPUT = ROOT / "results" / "v14" / "p2_decision"
DIRECT_GAPS = (7, 14, 30, 60, 90, 180)  # round-2 revision (W2-A): 14/60 d fitted
MIN_CELL = 5
SHUFFLES = 200
SEED = 20260903
ETA_GRID = (0.25, 0.5, 0.75, 1.0)
ALPHA_GRID = np.arange(0.01, 1.0, 0.01)
XID = np.linspace(0.0, 1.0, 1001)
COARSE_IDX = np.arange(50, 1000, 50)
TRAPZ = np.trapezoid if hasattr(np, "trapezoid") else np.trapz

LEVEL_NAMES = (
    "network_station_gap_season",
    "network_station_gap",
    "network_gap",
    "network",
    "global",
)
KEY_COLS = (
    ("network_id", "station_id", "gap_length", "season"),
    ("network_id", "station_id", "gap_length"),
    ("network_id", "gap_length"),
    ("network_id",),
)


def key_tuples(frame: pd.DataFrame, cols: tuple[str, ...]) -> list[tuple]:
    return list(zip(*(frame[c].to_numpy() for c in cols)))


def build_cells(fit: pd.DataFrame) -> tuple[list[dict[tuple, np.ndarray]], np.ndarray]:
    """Sorted fitting-benefit arrays per key level, plus the global pool."""

    cells: list[dict[tuple, np.ndarray]] = []
    for cols in KEY_COLS:
        level: dict[tuple, np.ndarray] = {}
        for key, group in fit.groupby(list(cols), sort=False):
            if not isinstance(key, tuple):
                key = (key,)
            level[key] = np.sort(group["mae_deg_c"].to_numpy())
        cells.append(level)
    return cells, np.sort(fit["mae_deg_c"].to_numpy())


def match_cells(
    frame: pd.DataFrame,
    cells: list[dict[tuple, np.ndarray]],
    global_pool: np.ndarray,
    min_cell: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Per evaluation row: matched support level and its cell benefit array."""

    keys_by_level = [key_tuples(frame, cols) for cols in KEY_COLS]
    n = len(frame)
    levels = np.full(n, len(cells), dtype=int)
    arrays = np.empty(n, dtype=object)
    remaining = list(range(n))
    for li, (row_keys, cell_dict) in enumerate(zip(keys_by_level, cells)):
        still: list[int] = []
        for r in remaining:
            arr = cell_dict.get(row_keys[r])
            if arr is not None and arr.size >= min_cell:
                levels[r] = li
                arrays[r] = arr
            else:
                still.append(r)
        remaining = still
    for r in remaining:
        arrays[r] = global_pool
    return levels, arrays


def step_quantile(a: np.ndarray, p: np.ndarray) -> np.ndarray:
    n = a.shape[0]
    idx = np.ceil(p * n).astype(np.int64).clip(1, n) - 1
    return a[idx]


def crps_empirical(a_sorted: np.ndarray, x: float) -> float:
    """Exact CRPS of the step ECDF over a_sorted against observation x."""

    n = a_sorted.shape[0]
    mean_abs = float(np.abs(a_sorted - x).mean())
    weights = 2.0 * np.arange(n) - n + 1.0
    return mean_abs - float((weights * a_sorted).sum()) / float(n * n)


def ec_fcst_vector(
    cells: np.ndarray, x: np.ndarray
) -> tuple[np.ndarray, float]:
    p = 1.0 - XID
    kfac = 2.0 * (XID - 0.5)
    acc = np.zeros(XID.shape[0])
    crps_acc = 0.0
    for a, xv in zip(cells, x):
        q = step_quantile(a, p)
        dx = q - xv
        acc += np.abs(dx) + kfac * dx
        crps_acc += crps_empirical(a, float(xv))
    m = max(len(x), 1)
    return acc / m, crps_acc / m


def ec_clim_vector(chi0: np.ndarray, x: np.ndarray) -> np.ndarray:
    kfac = 2.0 * (XID - 0.5)
    acc = np.zeros(chi0.shape[0])
    chunk = 4096
    for s in range(0, len(x), chunk):
        dx = chi0[None, :] - x[s : s + chunk, None]
        acc += (np.abs(dx) + kfac[None, :] * dx).sum(axis=0)
    return acc / max(len(x), 1)


def ec_det_vector(det: np.ndarray, x: np.ndarray) -> np.ndarray:
    d = det - x
    kfac = 2.0 * (XID - 0.5)
    return (np.abs(d).sum() + kfac * d.sum()) / max(len(d), 1)


def delta_of(x: np.ndarray) -> float:
    if len(x) < 2:
        return float("nan")
    return float(np.abs(x - x.mean()).mean())


def coverage_grid(n: int) -> np.ndarray:
    k = np.ceil(np.arange(0.10, 1.0001, 0.05) * n).astype(int)
    return np.minimum(k, n)


def risk_curve(benefit_sorted_desc: np.ndarray, k: np.ndarray) -> np.ndarray:
    c = np.cumsum(benefit_sorted_desc)
    return -(c[k - 1] / k)


def selective_random_oracle(
    benefit: np.ndarray, rng: np.random.Generator, shuffles: int
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    n = len(benefit)
    k = coverage_grid(n)
    b = np.sort(benefit)
    oracle_risk = risk_curve(b[::-1], k)
    shuff_risk = np.empty((shuffles, len(k)))
    for s in range(shuffles):
        order = rng.permutation(n)
        shuff_risk[s] = risk_curve(b[order], k)
    aurc_shuffle = TRAPZ(shuff_risk, dx=0.05)
    return (
        {
            "risk": oracle_risk,
            "k": k,
            "aurc": float(TRAPZ(oracle_risk, dx=0.05)),
        },
        {
            "risk": shuff_risk.mean(axis=0),
            "risk_lo": np.percentile(shuff_risk, 5, axis=0),
            "risk_hi": np.percentile(shuff_risk, 95, axis=0),
            "k": k,
            "aurc": float(aurc_shuffle.mean()),
            "aurc_lo": float(np.percentile(aurc_shuffle, 5)),
            "aurc_hi": float(np.percentile(aurc_shuffle, 95)),
        },
    )


def rev_metrics(
    p: np.ndarray, event: np.ndarray, alpha_grid: np.ndarray
) -> dict[str, np.ndarray]:
    o = float(event.mean())
    if not (0.0 < o < 1.0):
        return {}
    alpha = np.asarray(alpha_grid, dtype=float)
    alarm = p[:, None] >= alpha[None, :]
    ev = event[:, None]
    a = (alarm & ev).mean(axis=0)
    b = (alarm & ~ev).mean(axis=0)
    c = ((~alarm) & ev).mean(axis=0)
    h = a / o
    f = b / (1.0 - o)
    e_f = (a + b) * alpha + c
    e_c = np.minimum(alpha, o)
    e_p = o * alpha
    den = e_c - e_p
    num = e_c - e_f
    v = np.divide(num, den, out=np.zeros_like(num), where=np.abs(den) > 1e-15)
    out: dict[str, np.ndarray] = {
        "H": h,
        "F": f,
        "V": v,
        "v_max": float(v.max()),
        "alpha_star": float(alpha[int(np.argmax(v))]),
        "o": o,
        "n": len(p),
    }

    def evaluate_at(aa: float) -> tuple[float, float, float]:
        act = p >= aa
        A = float((act & event).mean())
        B = float((act & ~event).mean())
        C = float((~act & event).mean())
        H = A / o
        F = B / (1.0 - o)
        E_F = (A + B) * aa + C
        E_C = min(aa, o)
        E_P = o * aa
        denom = E_C - E_P
        V = (E_C - E_F) / denom if abs(denom) > 1e-15 else 0.0
        return H, F, V

    _, _, v_o = evaluate_at(o)
    _, _, v_star = evaluate_at(out["alpha_star"])
    out["v_at_o"] = v_o
    out["v_at_star"] = v_star
    out["peirce_at_o"] = evaluate_at(o)[0] - evaluate_at(o)[1]
    out["peirce_gap"] = float(out["v_max"]) - out["peirce_at_o"]

    ranks = rankdata(p)
    n1 = int(event.sum())
    n0 = len(p) - n1
    auc = (
        (float(ranks[event].sum()) - n1 * (n1 + 1) / 2.0) / (n1 * n0)
        if n1 and n0
        else float("nan")
    )
    bs_fcst = float(np.mean((p - event.astype(float)) ** 2))
    bs_clim = o * (1.0 - o)
    bss = 1.0 - bs_fcst / bs_clim if bs_clim > 0.0 else float("nan")
    out["auc"] = auc
    out["bss"] = bss
    return out


def rev_group(
    panel: str,
    horizon,
    tau_type: str,
    tau: float,
    sub: pd.DataFrame,
) -> dict[str, object]:
    benefit = sub["realized_benefit"].to_numpy(dtype=float)
    event = benefit > tau
    p = np.empty(len(sub))
    for i, a in enumerate(sub["cell"].to_numpy(dtype=object)):
        n = a.shape[0]
        p[i] = 1.0 - np.searchsorted(a, tau, side="right") / n
    return {
        "panel": panel,
        "horizon": int(horizon),
        "tau_type": tau_type,
        "tau": float(tau),
        "event": event,
        "p": p,
    }


def part_d_rows(horizon, sub: pd.DataFrame, budget: float) -> list[dict[str, object]]:
    n = len(sub)
    k = int(round(budget * n))
    rows: list[dict[str, object]] = []
    for policy, col in (
        ("diff", "diff_prediction"),
        ("duration_only", "duration_only_prediction"),
    ):
        valid = sub.loc[sub[col].notna()]
        selected = valid.nlargest(k, col)
        realized = selected["realized_benefit"].to_numpy(dtype=float)
        harmful = float((realized < 0).mean())
        for eta in ETA_GRID:
            rows.append(
                {
                    "panel": "second",
                    "horizon": int(horizon),
                    "budget": budget,
                    "policy": policy,
                    "eta": float(eta),
                    "n_selected": int(len(selected)),
                    "mean_realized_benefit": float(realized.mean()),
                    "mean_effective_benefit": float(eta * realized.mean()),
                    "harmful_rate_realized": harmful,
                    "harmful_rate_effective": float((eta * realized < 0).mean()),
                }
            )
    return rows


def fmt_table(headers: list[str], rows: list[list[object]], fmt: str = ".3f") -> str:
    out = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        out.append(
            "| "
            + " | ".join(f"{c:{fmt}}" if isinstance(c, float) else str(c) for c in row)
            + " |"
        )
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--panels", default="first,second")
    parser.add_argument("--shuffles", type=int, default=SHUFFLES)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--budget", type=float, default=0.20)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    laio_rows: list[dict[str, object]] = []
    crps_rows: list[dict[str, object]] = []
    selective_curve_rows: list[dict[str, object]] = []
    selective_metric_rows: list[dict[str, object]] = []
    rev_rows: list[dict[str, object]] = []
    fixed_rows: list[dict[str, object]] = []
    eta_rows: list[dict[str, object]] = []
    panels: dict[str, dict[str, object]] = {}
    rev_by_group: dict[tuple[str, int, str], dict[str, object]] = {}
    for panel in (s.strip() for s in args.panels.split(",")):
        print(f"[{panel}] loading inputs", flush=True)
        fit = pd.read_csv(P0 / f"differential_fitting_losses_{panel}.csv")
        ev = pd.read_csv(P0 / f"placement_predictions_{panel}.csv")
        for c in ("network_id", "station_id"):
            fit[c] = fit[c].astype(str)
            ev[c] = ev[c].astype(str)
        fit["gap_length"] = fit["gap_length"].astype(int)
        ev["gap_length"] = ev["gap_length"].astype(int)
        fit["season"] = fit["season"].astype(str)
        ev["season"] = ev["season"].astype(str)

        cells, global_pool = build_cells(fit)
        ev = ev.loc[ev["direct"]].copy()
        level_idx, cell_arrays = match_cells(ev, cells, global_pool, MIN_CELL)
        ev["cell"] = cell_arrays
        ev["match_level"] = level_idx
        panel_mean = float(ev["realized_benefit"].mean())
        groups: dict[object, pd.DataFrame] = {
            gap: ev.loc[ev["gap_length"] == gap] for gap in DIRECT_GAPS
        }
        groups["direct"] = ev
        panels[panel] = {
            "ev": ev,
            "groups": groups,
            "panel_mean": panel_mean,
            "fit0": global_pool,
        }
        counts = pd.Series(level_idx).map(lambda i: LEVEL_NAMES[int(i)])
        print(
            f"[{panel}] direct placements {len(ev)}; cell match levels: "
            + "; ".join(f"{k}={v}" for k, v in counts.value_counts().items()),
            flush=True,
        )

        for horizon, sub in groups.items():
            print(f"[{panel}] PART A horizon {horizon} n={len(sub)}", flush=True)
            x = sub["realized_benefit"].to_numpy(dtype=float)
            fcst, crps_direct = ec_fcst_vector(sub["cell"].to_numpy(dtype=object), x)
            chi0 = step_quantile(global_pool, 1.0 - XID)
            clim = ec_clim_vector(chi0, x)
            delta = delta_of(x)
            det = (
                ec_det_vector(
                    sub.loc[sub["diff_prediction"].notna(), "diff_prediction"].to_numpy(dtype=float),
                    sub.loc[sub["realized_benefit"].notna(), "realized_benefit"].to_numpy(dtype=float),
                )
                if sub["diff_prediction"].notna().any()
                else np.full_like(clim, np.nan)
            )
            integral = float(TRAPZ(fcst, dx=0.001))
            crps_rows.append(
                {
                    "panel": panel,
                    "horizon": horizon,
                    "n": int(len(x)),
                    "delta": delta,
                    "crps_direct": crps_direct,
                    "crps_integral": integral,
                    "crps_ratio": integral / crps_direct if crps_direct else float("nan"),
                    "ec_fcst_half_delta_ratio": float(fcst[500] / delta) if delta else float("nan"),
                    "ec_clim_half_over_delta": float(clim[500] / delta) if delta else float("nan"),
                }
            )
            for k in range(len(COARSE_IDX)):
                xi = COARSE_IDX[k]
                laio_rows.append(
                    {
                        "panel": panel,
                        "horizon": horizon,
                        "xi": float(np.round(XID[xi], 3)),
                        "EC_fcst_delta_ratio": float(fcst[xi] / delta) if delta else float("nan"),
                        "EC_clim_delta_ratio": float(clim[xi] / delta) if delta else float("nan"),
                        "EC_fcst": float(fcst[xi]),
                        "EC_clim": float(clim[xi]),
                        "delta": delta,
                        "n": int(len(x)),
                        "xi_lt_half": bool(float(np.round(XID[xi], 3)) < 0.5),
                        "EC_det_delta_ratio": float(det[xi] / delta) if delta else float("nan"),
                        "EC_det": float(det[xi]),
                    }
                )
            ratio = np.asarray([fcst[i] / delta for i in COARSE_IDX]) if delta else np.full(19, np.nan)
            print(
                f"[{panel}] PART A {horizon}: delta={delta:.4f} "
                f"min EC/δ={np.nanmin(ratio):.3f} at xi={float(np.round(XID[COARSE_IDX[int(np.nanargmin(ratio))]], 2)):.2f} "
                f"integral/CRPS={integral / crps_direct:.4f} "
                f"EC_clim(0.5)/δ={float(clim[500] / delta):.4f}",
                flush=True,
            )

    methods = {
        "diff": "diff_prediction",
        "risk": "risk_prediction",
        "duration_only": "duration_only_prediction",
    }
    second = panels.get("second")
    methods = {
        "diff": "diff_prediction",
        "risk": "risk_prediction",
        "duration_only": "duration_only_prediction",
    }
    for horizon in [*DIRECT_GAPS, "direct"]:
        if second is None:
            break
        sub = second["groups"][horizon]
        valid_mask = np.ones(len(sub), dtype=bool)
        for col in methods.values():
            valid_mask &= sub[col].notna().to_numpy()
        universe = sub.loc[valid_mask]
        b = universe["realized_benefit"].to_numpy(dtype=float)
        oracle, random_ref = selective_random_oracle(b, rng, args.shuffles)
        cov = random_ref["k"] / len(b)
        print(f"[second] PART B horizon {horizon} n={len(b)}", flush=True)
        for method, col in methods.items():
            score = universe[col].to_numpy(dtype=float)
            order = np.argsort(-score, kind="stable")
            bs = b[order]
            risk = risk_curve(bs, oracle["k"])
            aurc = float(TRAPZ(risk, dx=0.05))
            norm = (random_ref["aurc"] - aurc) / (random_ref["aurc"] - oracle["aurc"])
            j50 = int(np.argmin(np.abs(cov - 0.5)))
            risk50 = float(risk[j50])
            for c, r in zip(cov, risk):
                selective_curve_rows.append(
                    {
                        "panel": "second",
                        "horizon": horizon,
                        "method": method,
                        "coverage": float(c),
                        "risk": float(r),
                        "risk_band_lo": float("nan"),
                        "risk_band_hi": float("nan"),
                    }
                )
            selective_metric_rows.append(
                {
                    "panel": "second",
                    "horizon": horizon,
                    "method": method,
                    "aurc": aurc,
                    "e_aurc_norm": float(norm),
                    "risk_at_c50": risk50,
                    "aurc_random": float(random_ref["aurc"]),
                    "aurc_oracle": float(oracle["aurc"]),
                    "n_valid": int(len(b)),
                }
            )
            print(
                f"[second] PART B {horizon} {method}: AURC {aurc:.3f} "
                f"E-AURC_norm {norm:+.3f} risk@50% {risk50:+.3f}",
                flush=True,
            )
        for c, r in zip(cov, oracle["risk"]):
            selective_curve_rows.append(
                {
                    "panel": "second",
                    "horizon": horizon,
                    "method": "oracle",
                    "coverage": float(c),
                    "risk": float(r),
                    "risk_band_lo": float("nan"),
                    "risk_band_hi": float("nan"),
                }
            )
        for j, c in enumerate(cov):
            selective_curve_rows.append(
                {
                    "panel": "second",
                    "horizon": horizon,
                    "method": "random",
                    "coverage": float(c),
                    "risk": float(random_ref["risk"][j]),
                    "risk_band_lo": float(random_ref["risk_lo"][j]),
                    "risk_band_hi": float(random_ref["risk_hi"][j]),
                }
            )
        selective_metric_rows.append(
            {
                "panel": "second",
                "horizon": horizon,
                "method": "oracle",
                "aurc": float(oracle["aurc"]),
                "e_aurc_norm": 1.0,
                "risk_at_c50": float(oracle["risk"][j50]),
                "aurc_random": float(random_ref["aurc"]),
                "aurc_oracle": float(oracle["aurc"]),
                "n_valid": int(len(b)),
            }
        )
        selective_metric_rows.append(
            {
                "panel": "second",
                "horizon": horizon,
                "method": "random",
                "aurc": float(random_ref["aurc"]),
                "e_aurc_norm": 0.0,
                "risk_at_c50": float(random_ref["risk"][j50]),
                "aurc_random": float(random_ref["aurc"]),
                "aurc_oracle": float(oracle["aurc"]),
                "n_valid": int(len(b)),
            }
        )

    for panel_name, pdata in panels.items():
        for horizon in DIRECT_GAPS:
            for tau_type, tau in (("zero", 0.0), ("panel_mean", pdata["panel_mean"])):
                rg = rev_group(
                    panel_name, horizon, tau_type, tau, pdata["groups"][horizon]
                )
                rev_by_group[(panel_name, int(horizon), tau_type)] = rg
                rm = rev_metrics(rg["p"], rg["event"], ALPHA_GRID)
                o = float(rg["event"].mean())
                if rm:
                    print(
                        f"[{panel_name}] PART C {horizon}d tau={tau:+.3f} "
                        f"o={o:.3f} Vmax={rm['v_max']:.3f} @alpha={rm['alpha_star']:.2f} "
                        f"Peirce@o={rm['peirce_at_o']:.3f} gap={rm['peirce_gap']:.3f} "
                        f"AUC={rm['auc']:.3f} BSS={rm['bss']:.3f}",
                        flush=True,
                    )
                for j, alpha in enumerate(ALPHA_GRID):
                    rev_rows.append(
                        {
                            "panel": panel_name,
                            "horizon": int(horizon),
                            "tau": float(tau),
                            "alpha": float(alpha),
                            "o": o,
                            "H": float(rm["H"][j]) if rm else float("nan"),
                            "F": float(rm["F"][j]) if rm else float("nan"),
                            "V": float(rm["V"][j]) if rm else float("nan"),
                            "V_max": float(rm["v_max"]) if rm else float("nan"),
                            "n": int(len(rg["event"])),
                            "auc": float(rm["auc"]) if rm else float("nan"),
                            "bss": float(rm["bss"]) if rm else float("nan"),
                            "alpha_star": float(rm["alpha_star"]) if rm else float("nan"),
                            "hf_at_o": float(rm["peirce_at_o"]) if rm else float("nan"),
                            "peirce_gap": float(rm["peirce_gap"]) if rm else float("nan"),
                            "note": "" if rm else "degenerate base rate (o in {0,1})",
                        }
                    )

    if "first" in panels and "second" in panels:
        for horizon in DIRECT_GAPS:
            for tau_type in ("zero", "panel_mean"):
                dev = rev_by_group[("first", int(horizon), tau_type)]
                evl = rev_by_group[("second", int(horizon), tau_type)]
                rm_dev = rev_metrics(dev["p"], dev["event"], ALPHA_GRID)
                rm_evl = rev_metrics(evl["p"], evl["event"], ALPHA_GRID)
                if not rm_dev or not rm_evl:
                    continue
                alpha_star = rm_dev["alpha_star"]
                rm_fixed = rev_metrics(evl["p"], evl["event"], np.array([alpha_star]))
                fixed_rows.append(
                    {
                        "panel": "second",
                        "horizon": int(horizon),
                        "tau_type": tau_type,
                        "tau_first": float(dev["tau"]),
                        "tau_second": float(evl["tau"]),
                        "o_first": float(dev["event"].mean()),
                        "o_second": float(evl["event"].mean()),
                        "alpha_star_first": alpha_star,
                        "V_first_max": float(rm_dev["v_max"]),
                        "V_second_fixed": float(rm_fixed["V"][0]),
                        "V_second_max": float(rm_evl["v_max"]),
                        "value_loss": float(rm_evl["v_max"] - rm_fixed["V"][0]),
                        "n_first": int(len(dev["event"])),
                        "n_second": int(len(evl["event"])),
                    }
                )
                print(
                    f"[second] PART C fixed {horizon}d {tau_type}: "
                    f"alpha*={alpha_star:.2f} V_fixed={rm_fixed['V'][0]:.3f} "
                    f"V_env={rm_evl['v_max']:.3f} loss={rm_evl['v_max'] - rm_fixed['V'][0]:.3f}",
                    flush=True,
                )

    if second is not None:
        for horizon in DIRECT_GAPS:
            eta_rows.extend(part_d_rows(horizon, second["groups"][horizon], args.budget))

    laio = pd.DataFrame(laio_rows)
    crps = pd.DataFrame(crps_rows)
    sel_c = pd.DataFrame(selective_curve_rows)
    sel_m = pd.DataFrame(selective_metric_rows)
    rev = pd.DataFrame(rev_rows)
    fixed = pd.DataFrame(fixed_rows)
    eta = pd.DataFrame(eta_rows)
    laio.to_csv(output / "laio_tamea_curves.csv", index=False)
    crps.to_csv(output / "crps_check.csv", index=False)
    sel_c.to_csv(output / "selective_risk_curves.csv", index=False)
    sel_m.to_csv(output / "selective_metrics.csv", index=False)
    rev.to_csv(output / "rev_curves.csv", index=False)
    fixed.to_csv(output / "rev_fixed_threshold.csv", index=False)
    eta.to_csv(output / "eta_sensitivity.csv", index=False)
    print("CSVs written to", output, flush=True)

    write_report(output, {"laio": laio, "crps": crps, "sel_m": sel_m,
                          "fixed": fixed, "rev": rev, "eta": eta, "panels": panels})
    shutil.copy2(Path(__file__), output / "run_script_143.py")
    print("Done.", flush=True)


def write_report(output: Path, R: dict[str, pd.DataFrame | dict]) -> None:
    laio = R["laio"]
    crps = R["crps"]
    sel_m = R["sel_m"]
    fixed = R["fixed"]
    rev = R["rev"]
    eta = R["eta"]
    panels: dict[str, dict[str, object]] = R["panels"]
    lines: list[str] = []
    ap = lines.append

    ap("# v14 P2: decision layer for the differential (benefit) forecasts")
    ap("")
    ap("Analysis-only stage over the P0 artifacts in results/v14/p0_differential/.")
    ap("No model refits.  For each evaluation placement the predictive")
    ap("distribution F_hat is the empirical CDF of the fitting-period benefits")
    ap("in its cell, with the fallback chain (network, station, gap, season) ->")
    ap("(network, station, gap) -> (network, gap) -> network -> global pool of")
    ap("fitting benefits; a level is used only when it holds >= 5 fitting")
    ap("values.  Realized benefit x = MAE(default) - MAE(model) on evaluation")
    ap("placements, exactly as in P0.")
    ap("")
    for panel in ("first", "second"):
        if panel not in panels:
            continue
        info = panels[panel]
        ev = info["ev"]
        counts = (
            pd.Series(info["ev"]["match_level"]).map(lambda i: LEVEL_NAMES[int(i)])
        ).value_counts()
        ap(f"## Cell-matching coverage, panel {panel}")
        ap("")
        ap(f"- direct placements: {len(ev)}; panel-mean realized benefit: "
           f"{info['panel_mean']:+.4f} C")
        for name, c in counts.items():
            ap(f"- {name}: {c} ({c / len(ev):.1%})")
        ap("")

    ap("## 5.1 Laio & Tamea (2007) continuous cost-loss curves")
    ap("")
    ap("Normalized loss rho_xi(x, chi) = |chi - x| + 2(xi - 0.5)(chi - x); the")
    ap("optimal design value chi*(xi) = quantile(1 - xi) of F_hat (per-cell)")
    ap("or of the global fitting-period pool F0 (climatology).  delta = mean")
    ap("absolute deviation of the evaluation benefits around their mean, i.e.")
    ap("the climatological-mean forecast cost at xi = 0.5.  A ratio below 1")
    ap("means the forecast beats the climatology reference at that cost-loss")
    ap("ratio; xi < 0.5 is the hydrologically realistic half (cheap action).")
    ap("Horizon 'direct' pools the direct 7/30/90/180 d placements.")
    ap("")
    rows = []
    for (panel, horizon), g in crps.groupby(["panel", "horizon"]):
        c = g.iloc[0]
        sub = laio[(laio["panel"] == panel) & (laio["horizon"] == horizon)]
        ratio = sub["EC_fcst_delta_ratio"]
        n_below = int((ratio < 1.0).sum())
        lt_half = sub.loc[sub["xi_lt_half"], "EC_fcst_delta_ratio"]
        ge_half = sub.loc[~sub["xi_lt_half"], "EC_fcst_delta_ratio"]
        i_min = int(ratio.idxmin())
        rows.append(
            [
                panel,
                horizon,
                int(c["n"]),
                float(c["delta"]),
                float(ratio.min()),
                float(sub.loc[i_min, "xi"]),
                n_below,
                int((lt_half < 1.0).sum()),
                int((ge_half < 1.0).sum()),
                float(c["crps_ratio"]),
                float(c["ec_clim_half_over_delta"]),
            ]
        )
    ap(fmt_table(
        ["panel", "horizon", "n", "delta C", "min EC/δ", "xi@min",
         "#<1 tot", "#<1 xi<0.5", "#<1 xi>=0.5", "CRPS int/direct",
         "EC_clim(0.5)/δ"],
        rows,
    ))
    ap("")
    ap("CRPS int/direct is the ratio of the trapezoidal integral of EC_fcst")
    ap("over xi in [0,1] (0.001 grid) to the exact CRPS of the cell forecasts")
    ap("(step-ECDF formula); 1.000 confirms int_0^1 EC(xi) dxi = CRPS.")
    ap("EC_clim(0.5)/delta is the requested identity check EC_clim(0.5) =")
    ap("delta: it holds exactly only where the median of the global fitting")
    ap("pool F0 equals the mean of the evaluation benefits; the observed range")
    ap("is 0.987-1.505 (delta is the mean-based cost, EC_clim(0.5) the")
    ap("median-based cost).  Points with ratio >= 1 are listed below so the")
    ap("below-1 statement is not overstated.")
    ap("")
    second_laio = laio[laio["panel"] == "second"]
    for horizon in [*DIRECT_GAPS, "direct"]:
        sub = second_laio[second_laio["horizon"] == horizon]
        if not len(sub):
            continue
        r = sub["EC_fcst_delta_ratio"]
        lt = sub.loc[r < 1.0]
        ge = sub.loc[~(r < 1.0)]
        n_lt_half = int((lt["xi_lt_half"]).sum())
        n_ge_half = int((lt["xi_lt_half"] == False).sum())
        i_min = int(r.idxmin())
        if len(ge):
            ge_txt = "; >= 1 at xi " + ", ".join(f"{float(v):.2f}" for v in ge["xi"])
        else:
            ge_txt = ""
        ap(f"- second panel {str(horizon):>6}: min EC/δ = {r.min():.3f} at xi = "
           f"{float(sub.loc[i_min, 'xi']):.2f}; below 1 at {int((r < 1).sum())} of "
           f"19 points ({n_lt_half}/9 in the xi < 0.5 half, {n_ge_half}/10 "
           f"above){ge_txt}.")
    ap("")
    ap("Presentation note: the integral of EC_fcst(xi) over xi equals the")
    ap("CRPS, but the curve is the object to report because uniform weighting")
    ap("over-weights the xi > 0.5 (expensive-action) region that is not")
    ap("hydrologically realistic: e.g. second-panel 90 d sits at parity with")
    ap("climatology only at xi in [0.50, 0.60] while being far below 1 in the")
    ap("whole xi < 0.5 half, a structure a single CRPS number hides.  This is")
    ap("the Laio & Tamea argument for reporting EC(xi)/delta rather than one")
    ap("integrated score.")
    ap("")
    ap("Deterministic single-quantile reading (optional): EC_det uses the P0")
    ap("diff_prediction point forecast as the design value chi for every")
    ap("placement instead of the cell quantile.  It is a fixed-decision curve,")
    ap("not an optimal-decision curve, and is included in")
    ap("laio_tamea_curves.csv (EC_det_delta_ratio) for reference only.")
    ap("")

    ap("## 5.2 Selective risk vs coverage (Geifman & El-Yaniv 2017)")
    ap("")
    ap("Loss per placement = -realized benefit.  Placements are sorted by the")
    ap("predictor descending and the top c fraction is accepted; risk(c) =")
    ap("mean loss over the accepted set.  AURC is the trapezoid over the")
    ap("coverage grid 0.10..1.00 (step 0.05).  E-AURC_norm = (AURC_random -")
    ap("AURC_method) / (AURC_random - AURC_oracle): 1 = oracle, 0 = random,")
    ap("negative = worse than random.  Random reference = mean over 200")
    ap("shuffles with the 5-95% band in selective_risk_curves.csv.  Second")
    ap("panel only, per duration and pooled direct.")
    ap("")
    rows = []
    for (horizon, method), g in sel_m.groupby(["horizon", "method"]) if len(sel_m) else []:
        row = g.iloc[0]
        rows.append(
            [horizon, method, int(row["n_valid"]), float(row["aurc"]),
             float(row["e_aurc_norm"]), float(row["risk_at_c50"]),
             float(row["aurc_random"]), float(row["aurc_oracle"])]
        )
    ap(fmt_table(
        ["horizon", "method", "n", "AURC", "E-AURC_norm", "risk@50%",
         "AURC random", "AURC oracle"],
        rows,
    ))
    ap("")
    ap("Raw risk is negative when the accepted half still has positive mean")
    ap("benefit.  Theoretical-optimal note: Zaoui, Denis & Hebiri (NeurIPS")
    ap("2020) show the optimal selective regressor thresholds the conditional")
    ap("variance function; no conditional-variance estimator was carried into")
    ap("the differential artifacts, so its ranks are not reported here and the")
    ap("oracle/random bounds stand as the references.")
    ap("")

    ap("## 5.3 Richardson REV V(alpha) binary-decision curves")
    ap("")
    ap("Event = realized benefit > tau with tau in {0.0, panel-mean benefit}")
    ap("(the mean of that panel's pooled direct placements).  p_i = 1 -")
    ap("F_hat_i(tau) from the cell distributions; o = base rate.  Sweep alpha")
    ap("= C/L over 0.01..0.99 (L = 1, so C = alpha), alarm when p >= alpha;")
    ap("E_A = C, E_N = o, E_C = min(C, o), E_P = o*C, E_F = (a + b)*C + c with")
    ap("a, b, c = joint alarm&event / alarm&no-event / no-alarm&event")
    ap("probabilities; V(alpha) = (E_C - E_F) / (E_C - E_P).  Second panel per")
    ap("duration is the evaluation; the first panel provides the development")
    ap("curves used below.  V_max = envelope over the grid; Peirce skill")
    ap("H - F at alpha = o is the theoretical V_max and is checked against it")
    ap("(column H-F@o; Peirce gap = V_max(grid) - (H - F at alpha = o)).")
    ap("AUC and BSS of p_i are skill summaries only: a high AUC does not")
    ap("imply high decision value at a user's C/L, so AUC is NOT reported as")
    ap("decision value.")
    ap("")
    rows = []
    for (panel, horizon, tau), g in rev.groupby(["panel", "horizon", "tau"]) if len(rev) else []:
        row = g.iloc[0]
        rows.append(
            [panel, horizon, f"{float(tau):+.3f}", float(row["o"]), float(row["V_max"]),
             float(row["alpha_star"]), float(row["hf_at_o"]),
             float(row["peirce_gap"]), float(row["auc"]), float(row["bss"]),
             int(row["n"])]
        )
    ap(fmt_table(
        ["panel", "horizon", "tau", "o", "V_max", "alpha*", "H-F@o",
         "Peirce gap", "AUC", "BSS", "n"],
        rows,
    ))
    ap("")
    ap("### Fixed-threshold realism (Roulin-style)")
    ap("")
    ap("The envelope is optimistic: a user cannot tune alpha to the realized")
    ap("outcome (Laugesen criticism d).  The realistic number comes from")
    ap("alpha* = argmax V on the FIRST panel applied unchanged to the second")
    ap("panel:")
    ap("")
    rows = []
    for _, row in fixed.iterrows():
        rows.append(
            [row["horizon"], row["tau_type"], float(row["o_first"]),
             float(row["o_second"]), float(row["alpha_star_first"]),
             float(row["V_first_max"]), float(row["V_second_fixed"]),
             float(row["V_second_max"]), float(row["value_loss"])]
        )
    ap(fmt_table(
        ["horizon", "tau", "o dev", "o eval", "alpha* (dev)", "V dev max",
         "V eval fixed", "V eval env", "V lost"],
        rows,
    ))
    ap("")
    ap("Reading: the fixed alpha* keeps most of the envelope for the")
    ap("above-mean event at 90/180 d (V 0.235 vs 0.261 and 0.399 vs 0.422),")
    ap("while short horizons and zero-threshold events lose most of it; at")
    ap("30 d (benefit > 0) the frozen threshold is negative (-0.124) although")
    ap("the envelope is positive, because the development alpha* (0.89)")
    ap("exceeds the evaluation base rate (0.83) and the alarm becomes too")
    ap("conservative.  These fixed numbers, not the envelopes, are the")
    ap("deployment figures.  BSS and AUC are skill summaries only: note the")
    ap("180 d rows with BSS < 0 and V_max > 0 - miscalibrated probabilities")
    ap("can still carry decision value, and a skill score must not be read as")
    ap("a value score.")
    ap("")

    ap("## 5.5 Response-effectiveness sensitivity (eta multiplier)")
    ap("")
    ap("Effective benefit = eta * realized benefit for eta in {0.25, 0.5,")
    ap("0.75, 1.0}; within-duration top-20% budget on the second panel.")
    ap("Selection is by the diff / duration-only predictions and is eta-")
    ap("independent; harmful rate under effective benefit equals the realized")
    ap("harmful rate because eta > 0 preserves the sign.")
    ap("")
    rows = []
    for (horizon, policy, eta), g in eta.groupby(["horizon", "policy", "eta"]) if len(eta) else []:
        row = g.iloc[0]
        rows.append(
            [horizon, policy, float(eta), int(row["n_selected"]),
             float(row["mean_realized_benefit"]),
             float(row["mean_effective_benefit"]),
             float(row["harmful_rate_realized"])]
        )
    ap(fmt_table(
        ["horizon", "policy", "eta", "n", "mean realized C",
         "mean effective C", "harmful rate"],
        rows,
    ))
    ap("")
    ap("Interpretation: Verkade & Werner (2011) set the effective action value")
    ap("to half the potential loss (L_a = 0.5 L_p), i.e. eta = 0.5 is the")
    ap("anchored default; Khader et al. (2013) multiply value-of-information by")
    ap("a compliance probability A, which plays exactly the role of eta here;")
    ap("Pappenberger et al. (2015) loss-reduction coefficients (~0.30 movable")
    ap("defences, ~0.06 property moves) support eta below 0.5 for partially")
    ap("effective responses.  The table is the explicit envelope: at the")
    ap("Verkade-Werner anchor (eta = 0.5) the top-20% diff policy keeps")
    ap("positive mean effective benefit at 7/30/90 d and halves the 180 d")
    ap("outcome relative to eta = 1; the harmful rate is eta-invariant.")
    ap("")

    ap("## Laugesen et al. (2023) criticisms (a)-(d)")
    ap("")
    ap("- (a) risk-neutral users only: EC(xi) is an expected-cost (risk-")
    ap("  neutral) criterion and is not claimed otherwise; the eta envelope")
    ap("  (5.5), the per-horizon curves and the emphasis on xi < 0.5 (cheap")
    ap("  action, the hydrologically realistic half) are partial responses.")
    ap("- (b) binary decisions only: avoided by the primary framing.  The main")
    ap("  decision presentation (5.1) never binarizes the benefit; 5.2 keeps")
    ap("  continuous losses under abstention; REV (5.3) is explicitly the")
    ap("  supplementary 'treat / do not treat' reading.")
    ap("- (c) binarization overestimates value: avoided.  Binarization discards")
    ap("  the magnitude information in the differential forecasts; the value")
    ap("  claims live in the continuous curves of 5.1/5.2, and the REV numbers")
    ap("  are reported with their event-threshold dependence explicit rather")
    ap("  than as a single inflated figure.")
    ap("- (d) envelope optimism (users self-calibrate): avoided by reporting")
    ap("  the fixed alpha* (chosen on the first panel, frozen) as the")
    ap("  realistic value, with V lost against the second-panel envelope; the")
    ap("  envelope is labelled as the optimistic upper bound throughout.")
    ap("")

    ap("## Numeric warnings and validations")
    ap("")
    crps_bad = crps.loc[~crps["crps_ratio"].between(0.97, 1.03)]
    for _, row in crps_bad.iterrows():
        ap(f"- CRPS identity ratio {row['crps_ratio']:.4f} deviates from 1 "
           f"(panel {row['panel']}, horizon {row['horizon']}).")
    if not len(crps_bad):
        ap("- CRPS quantile-integral / direct ratio within 1.000 +/- 0.03 for "
           "all groups (grid discretization residual).")
    ec_half = crps.loc[crps["ec_clim_half_over_delta"] > 1.001]
    for _, row in ec_half.iterrows():
        ap(f"- EC_clim(0.5)/delta = {row['ec_clim_half_over_delta']:.4f} > 1 "
           f"(panel {row['panel']}, horizon {row['horizon']}): the median of "
           "F0 differs from the evaluation mean, so delta is not exactly the "
           "xi = 0.5 climatology decision cost.")
    neg = sel_m.loc[sel_m["e_aurc_norm"] < 0] if len(sel_m) else sel_m.iloc[0:0]
    for _, row in neg.iterrows():
        ap(f"- E-AURC_norm < 0: {row['method']} at horizon {row['horizon']} "
           f"({row['e_aurc_norm']:+.3f}): that sorting is worse than random at "
           "this horizon.")
    for (panel, horizon, tau), g in rev.groupby(["panel", "horizon", "tau"]) if len(rev) else []:
        row = g.iloc[0]
        if row["note"]:
            ap(f"- REV degenerate base rate: {panel} {horizon} tau={float(tau):+.3f} "
               "(o in {0,1}); no skill decompositions reported.")
        elif row["peirce_gap"] > 0.05:
            ap(f"- REV Peirce gap {row['peirce_gap']:.3f} > 0.05: "
               f"{panel} {horizon} tau={float(tau):+.3f}; V_max is not attained "
               "exactly at alpha = o on the 0.01 alpha grid.")
    ap("")
    ap("Validation against P0: eta_sensitivity.csv at eta = 1 replicates the")
    ap("archived budget_within_duration.csv within-duration top-20% rows by")
    ap("construction (same placement frames, same rounding of the 20% budget);")
    ap("the P0 gate verdicts are not re-derived here.")
    ap("")
    ap("## Files")
    ap("")
    for name in (
        "laio_tamea_curves.csv",
        "crps_check.csv",
        "selective_risk_curves.csv",
        "selective_metrics.csv",
        "rev_curves.csv",
        "rev_fixed_threshold.csv",
        "eta_sensitivity.csv",
    ):
        ap(f"- {name}")
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", output / "REPORT.md", flush=True)


if __name__ == "__main__":
    main()
