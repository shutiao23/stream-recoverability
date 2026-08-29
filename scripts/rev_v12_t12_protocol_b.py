#!/usr/bin/env python3
"""v3 external-confirmation protocol power analysis (agent b, adversarial).

Network-bootstrap power simulation for the outcome-disjoint confirmation
panel. The observed second-panel paired effects (empirical-transfer predictor
versus the strongest simple-descriptor baseline) are drawn from
results/development_v11/second_confirmation/scoring/empirical_predictions.csv
and simple_predictions.csv (1,446 units; 57 networks; direct-support horizons
7/30/90/180 days).

For every simulated panel we resample networks with replacement and
block-bootstrap units within each network, recompute per-network paired
endpoints, scale each network's effect by a frozen margin multiplier
(0.5x / 1x / 1.5x the observed mean effect; 0x with random sign flips
calibrates test size), and apply the frozen one-sided paired Wilcoxon test
across the panel's networks. Power is the fraction of replicates with
p < 0.05.

Endpoints (protocol v3 primaries):
  d_rho     network DeltaRho, empirical vs baseline, direct-support units
  dcap_B    per-network DeltaCapturedLoss at budget B in {5,10,20,30}%
  d_ndcg    per-network DeltaNDCG, empirical vs baseline

Writes to results/revision_v12/t12_confirmation_protocol/agent_b/:
  power_analysis.csv            long-form (size, margin, endpoint, power)
  panel_effect_distribution.csv sampling distribution of the panel effect
  power_analysis_summary.json   recommended n, guidance margins, multipliers
  power_curve.png               power curves per endpoint
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
OUT = (
    ROOT
    / "results/revision_v12/t12_confirmation_protocol/agent_b"
)
SCORING = ROOT / "results/development_v11/second_confirmation/scoring"

SEED = 11
ALPHA = 0.05
POWER_TARGET = 0.80
SIZES = [40, 60, 80, 100, 120, 140, 160]
MARGINS = [0.0, 0.5, 1.0, 1.5]
N_REPS = 600
SUPPORTED_HORIZONS = [7, 30, 90, 180]
BUDGETS = [0.05, 0.10, 0.20, 0.30]
ENDPOINTS = ["d_rho", "dcap_0.05", "dcap_0.10", "dcap_0.20", "dcap_0.30", "d_ndcg"]
SCAN_SIZES = [160]
SCAN_MARGINS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
SCAN_REPS = 400


def _rho(x: np.ndarray, y: np.ndarray) -> float:
    rx = np.argsort(np.argsort(x))
    ry = np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def _network_stats(pe: np.ndarray, ps: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Per-network paired endpoints on one network's unit draws."""
    n = len(y)
    out: dict[str, float] = {
        "d_rho": _rho(pe, y) - _rho(ps, y),
    }
    total = float(y.sum())
    for budget in BUDGETS:
        k = max(1, int(np.ceil(budget * n)))
        cap_emp = float(y[np.argsort(-pe)[:k]].sum()) / total
        cap_simple = float(y[np.argsort(-ps)[:k]].sum()) / total
        out[f"dcap_{budget:.2f}"] = cap_emp - cap_simple
    disc = 1.0 / np.log2(np.arange(2, n + 2))
    order = np.argsort(-pe)
    order_simple = np.argsort(-ps)
    order_ideal = np.argsort(-y)
    idcg = float((y[order_ideal] * disc).sum())
    dcg = float((y[order] * disc).sum())
    dcg_simple = float((y[order_simple] * disc).sum())
    out["d_ndcg"] = (dcg - dcg_simple) / idcg if idcg > 0 else 0.0
    return out


def _one_sided_wilcoxon(values: np.ndarray, rng: np.random.Generator, margin: float) -> float:
    if margin == 0.0:
        # Exact-size calibration: randomly flip each network's observed
        # effect sign so the H0 median is zero with the same magnitudes.
        tested = np.where(rng.random(len(values)) < 0.5, values, -values)
    else:
        tested = margin * values
    nonzero = tested[tested != 0.0]
    if len(nonzero) == 0:
        return 1.0
    return float(wilcoxon(nonzero, alternative="greater").pvalue)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    empirical = pd.read_csv(SCORING / "empirical_predictions.csv")
    simple = pd.read_csv(
        SCORING / "simple_predictions.csv",
        usecols=["network_id", "station_id", "gap_length", "predicted_loss"],
    )
    merged = empirical.merge(
        simple, on=["network_id", "station_id", "gap_length"], suffixes=("", "_simple")
    )
    panel = merged[merged["gap_length"].isin(SUPPORTED_HORIZONS)].copy()
    if len(panel) != 874:
        print(f"note: direct-support units = {len(panel)} (874 expected)")

    nets: list[tuple[str, np.ndarray, np.ndarray, np.ndarray]] = []
    for network_id, grp in panel.groupby("network_id", sort=False):
        nets.append(
            (
                str(network_id),
                grp["empirical_transfer_prediction"].to_numpy(dtype=float),
                grp["predicted_loss"].to_numpy(dtype=float),
                grp["observed_recovery_loss"].to_numpy(dtype=float),
            )
        )
    n_networks = len(nets)
    print(f"loaded {len(panel)} direct-support units across {n_networks} networks")

    observed_rows = []
    for network_id, pe, ps, y in nets:
        row = _network_stats(pe, ps, y)
        row["network_id"] = network_id
        observed_rows.append(row)
    observed = pd.DataFrame(observed_rows)
    observed_effect = {k: float(observed[k].mean()) for k in ENDPOINTS}
    observed_median = {k: float(observed[k].median()) for k in ENDPOINTS}
    observed_positive = {k: float((observed[k] > 0).mean()) for k in ENDPOINTS}

    def simulate(size: int, margin: float, reps: int) -> tuple[dict[str, float], list[dict[str, float]]]:
        """Return power dict and the panel median delta (unscaled) per replicate."""
        power = {k: 0 for k in ENDPOINTS}
        effect_rows: list[dict[str, float]] = []
        for _ in range(reps):
            picks = rng.integers(0, n_networks, size=size)
            per_network: dict[str, list[float]] = {k: [] for k in ENDPOINTS}
            for index in picks:
                _, pe, ps, y = nets[index]
                units = rng.integers(0, len(pe), size=len(pe))
                stats = _network_stats(pe[units], ps[units], y[units])
                for k in ENDPOINTS:
                    per_network[k].append(stats[k])
            pvalues = {
                k: _one_sided_wilcoxon(np.asarray(v, dtype=float), rng, margin)
                for k, v in per_network.items()
            }
            for k in ENDPOINTS:
                power[k] += float(pvalues[k] < ALPHA)
            effect_rows.append(
                {
                    "size": size,
                    "margin": margin,
                    "panel_median_delta_1x": float(np.median(per_network["d_rho"])),
                }
                | {k: float(np.median(per_network[k])) for k in ENDPOINTS}
            )
        return {k: v / reps for k, v in power.items()}, effect_rows

    rows: list[dict[str, object]] = []
    effect_rows_all: list[dict[str, object]] = []
    for size in SIZES:
        for margin in MARGINS:
            power, effects = simulate(size, margin, N_REPS)
            effect_rows_all.extend(effects)
            for k in ENDPOINTS:
                rows.append(
                    {
                        "panel_size": size,
                        "margin": margin,
                        "margin_label": "null" if margin == 0.0 else f"{margin:g}x",
                        "endpoint": k,
                        "power": round(power[k], 4),
                        "n_reps": N_REPS,
                        "alpha": ALPHA,
                        "observed_mean_effect": round(observed_effect[k], 6),
                        "observed_median_effect": round(observed_median[k], 6),
                    }
                )
            print(f"size {size} margin {margin:g}: " + ", ".join(
                f"{k}={power[k]:.3f}" for k in ("d_rho", "dcap_0.05", "dcap_0.20", "d_ndcg")
            ), flush=True)

    for size in SCAN_SIZES:
        for margin in SCAN_MARGINS:
            power, effects = simulate(size, margin, SCAN_REPS)
            effect_rows_all.extend(effects)
            for k in ENDPOINTS:
                rows.append(
                    {
                        "panel_size": size,
                        "margin": margin,
                        "margin_label": "scan",
                        "endpoint": k,
                        "power": round(power[k], 4),
                        "n_reps": SCAN_REPS,
                        "alpha": ALPHA,
                        "observed_mean_effect": round(observed_effect[k], 6),
                        "observed_median_effect": round(observed_median[k], 6),
                    }
                )
            print(f"scan size {size} margin {margin:g}: " + ", ".join(
                f"{k}={power[k]:.3f}" for k in ("d_rho", "dcap_0.05", "dcap_0.20", "d_ndcg")
            ), flush=True)

    power_df = pd.DataFrame(rows)
    power_df.to_csv(OUT / "power_analysis.csv", index=False)

    effect_dist = (
        pd.DataFrame(effect_rows_all)
        .groupby("size")
        .agg(
            median_delta_rho=("d_rho", "median"),
            p25_delta_rho=("d_rho", lambda v: np.percentile(v, 25)),
            median_dcap_05=("dcap_0.05", "median"),
            median_dcap_10=("dcap_0.10", "median"),
            median_dcap_20=("dcap_0.20", "median"),
            median_dcap_30=("dcap_0.30", "median"),
            median_d_ndcg=("d_ndcg", "median"),
        )
        .round(6)
        .reset_index()
    )
    effect_dist.to_csv(OUT / "panel_effect_distribution.csv", index=False)

    main_grid = power_df[
        power_df["margin"].isin([0.5, 1.0, 1.5])
    ].copy()
    scan = power_df[power_df["margin_label"].eq("scan")].copy()

    def recommended_size(endpoint: str) -> dict[str, object]:
        curve = main_grid[main_grid["endpoint"].eq(endpoint) & main_grid["margin"].eq(1.0)]
        curve = curve.sort_values("panel_size")
        reached = curve[curve["power"] >= POWER_TARGET]
        if reached.empty:
            n_recommended = None
        else:
            n_recommended = int(reached["panel_size"].iloc[0])
            lower = curve[curve["panel_size"] < n_recommended]
            if not lower.empty and lower["power"].iloc[-1] < POWER_TARGET:
                x0, x1 = float(lower["panel_size"].iloc[-1]), float(n_recommended)
                y0, y1 = float(lower["power"].iloc[-1]), float(
                    curve[curve["panel_size"] == n_recommended]["power"].iloc[0]
                )
                if y1 > y0:
                    n_recommended = round(x0 + (POWER_TARGET - y0) / (y1 - y0) * (x1 - x0), 1)
        scan_curve = scan[scan["endpoint"].eq(endpoint)].sort_values("margin")
        scan_reached = scan_curve[scan_curve["power"] >= POWER_TARGET]
        required_margin = (
            float(scan_reached["margin"].iloc[0]) if not scan_reached.empty else None
        )
        return {
            "endpoint": endpoint,
            "n_for_80pct_at_1x": n_recommended,
            "required_margin_multiplier_at_160": required_margin,
            "required_mean_effect_at_160": (
                round(required_margin * observed_effect[endpoint], 6)
                if required_margin is not None
                else None
            ),
            "observed_mean_effect": round(observed_effect[endpoint], 6),
            "observed_median_effect": round(observed_median[endpoint], 6),
            "fraction_positive_networks": round(observed_positive[endpoint], 4),
        }

    summary = {
        "seed": SEED,
        "alpha": ALPHA,
        "power_target": POWER_TARGET,
        "n_reps_main_grid": N_REPS,
        "n_reps_scan": SCAN_REPS,
        "data_source": {
            "predictions": str(SCORING / "empirical_predictions.csv"),
            "baseline": str(SCORING / "simple_predictions.csv"),
            "networks": n_networks,
            "direct_support_units": int(len(panel)),
            "supported_horizons": SUPPORTED_HORIZONS,
            "test": "one-sided paired Wilcoxon across networks, alpha=0.05",
            "bootstrap": "networks resampled with replacement; units block-bootstrapped within networks",
        },
        "observed_effect": observed_effect,
        "observed_median_effect": observed_median,
        "observed_fraction_positive": observed_positive,
        "size_at_null_margin_160": {
            k: float(
                power_df[
                    power_df["endpoint"].eq(k)
                    & power_df["panel_size"].eq(160)
                    & power_df["margin"].eq(0.0)
                ]["power"].iloc[0]
            )
            for k in ENDPOINTS
        },
        "endpoint_summary": {k: recommended_size(k) for k in ENDPOINTS},
    }
    (OUT / "power_analysis_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["endpoint_summary"], indent=1))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    plot_map = [
        ("d_rho", "network DeltaRho (direct support)"),
        ("dcap_0.05", "DeltaCapturedLoss @5%"),
        ("dcap_0.20", "DeltaCapturedLoss @20%"),
        ("d_ndcg", "DeltaNDCG"),
    ]
    for ax, (endpoint, label) in zip(axes.ravel(), plot_map):
        for margin, style in [(0.5, "-o"), (1.0, "-s"), (1.5, "-^")]:
            curve = main_grid[
                main_grid["endpoint"].eq(endpoint) & main_grid["margin"].eq(margin)
            ].sort_values("panel_size")
            ax.plot(curve["panel_size"], curve["power"], style, label=f"{margin:g}x observed")
        scan_curve = scan[scan["endpoint"].eq(endpoint)].sort_values("margin")
        ax.axhline(POWER_TARGET, color="grey", linestyle="--", linewidth=1)
        ax.axhline(ALPHA, color="black", linestyle=":", linewidth=1)
        ax.set_title(f"{label}\nobserved mean effect {observed_effect[endpoint]:+.4f}", fontsize=10)
        ax.set_xlabel("panel size (scored networks)")
        ax.set_ylabel("power (one-sided paired Wilcoxon)")
        ax.set_ylim(-0.03, 1.03)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="lower right")
    fig.suptitle(
        "v3 external-confirmation power analysis: network bootstrap, "
        f"{n_networks} observed networks, {N_REPS} replicates",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "power_curve.png", dpi=150)
    print(f"wrote outputs to {OUT}")


if __name__ == "__main__":
    main()
