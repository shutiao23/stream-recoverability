#!/usr/bin/env python3
"""Strongest-baseline harmonization analysis, agent_a (adversarial pair).

Definitive empirical-vs-strongest-fair-baseline comparison for the WRR revision.
Baseline = station x horizon historical mean of fitting-period MAE
(t03 ladder rung r6_station_gap).  All resampling uses np.random.default_rng(42).

Read-only inputs (never modified):
  results/revision_v12/t01_paired_comparison/agent_a/predictions.csv
  results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_second.csv
  results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_first.csv
  results/revision_v12/t03_baseline_ladder/agent_a/master_ladder_table.csv
  results/revision_v12/t01_paired_comparison/agent_a/paired_bootstrap.csv
  results/revision_v12/t03_baseline_ladder/agent_a/paired_bootstrap.csv

Writes ONLY to results/revision_v13/strongest_baseline/agent_a/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "results/revision_v13/strongest_baseline/agent_a"
OUT.mkdir(parents=True, exist_ok=True)

T01_SECOND = ROOT / "results/revision_v12/t01_paired_comparison/agent_a/predictions.csv"
T03_SECOND = ROOT / "results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_second.csv"
T03_FIRST = ROOT / "results/revision_v12/t03_baseline_ladder/agent_a/unit_predictions_first.csv"
MASTER = ROOT / "results/revision_v12/t03_baseline_ladder/agent_a/master_ladder_table.csv"
T01_BOOT = ROOT / "results/revision_v12/t01_paired_comparison/agent_a/paired_bootstrap.csv"

DIRECT_HORIZONS = (7, 30, 90, 180)
REPEATS = 2000
SEED_OFFICIAL = 42
SEED_VERIFY = 0  # reference scripts used 0; used only for verification vs v12

METHODS = {
    "empirical": "empirical_transfer_prediction",
    "r6": "r6_station_gap",
    "simple": "simple_fitperiod",  # second panel; == r8_simple
    "surface": "surface_prediction_mae",  # == r11_surface
}


def fit_linear(design: np.ndarray, outcome: np.ndarray, weight: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(design * weight[:, None], outcome * weight, rcond=None)[0]


def metrics(frame: pd.DataFrame, prediction: str, outcome: str = "observed_recovery_loss") -> dict:
    """Matches metrics() in scripts/rev_v12_t01_paired_comparison_a.py / t03."""
    usable = frame[["network_id", prediction, outcome]].dropna()
    predicted = usable[prediction].to_numpy(dtype=float)
    observed = usable[outcome].to_numpy(dtype=float)
    network = usable.groupby("network_id")[[prediction, outcome]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), predicted])
    if np.allclose(predicted, predicted[0]):
        slope = float("nan")
        intercept = float(np.average(observed, weights=weight))
    else:
        intercept, slope = fit_linear(design, observed, weight)
        intercept, slope = float(intercept), float(slope)
    with np.errstate(invalid="ignore"):
        r2 = 1.0 - np.sum((observed - predicted) ** 2) / np.sum((observed - observed.mean()) ** 2)
    return {
        "n": int(len(usable)),
        "n_networks": int(len(network)),
        "pooled_spearman": float(spearmanr(predicted, observed).statistic),
        "network_spearman": float(
            spearmanr(network[prediction], network[outcome]).statistic
        ),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "r2": float(r2),
        "rmse": float(np.sqrt(np.mean(np.square(observed - predicted)))),
    }


def within_network_spearman_series(
    frame: pd.DataFrame, prediction: str, outcome: str = "observed_recovery_loss", min_units: int = 4
) -> pd.Series:
    rows = {}
    for network, values in frame.groupby("network_id"):
        if len(values) < min_units:
            continue
        predicted = values[prediction].to_numpy(dtype=float)
        observed = values[outcome].to_numpy(dtype=float)
        if np.allclose(predicted, predicted[0]) or np.allclose(observed, observed[0]):
            continue
        rows[network] = float(spearmanr(predicted, observed).statistic)
    return pd.Series(rows, name="spearman")


def residualized_spearman(frame: pd.DataFrame, prediction: str, outcome: str = "observed_recovery_loss") -> float:
    usable = frame[["network_id", prediction, outcome]].dropna()
    predicted = usable[prediction] - usable.groupby("network_id")[prediction].transform("mean")
    observed = usable[outcome] - usable.groupby("network_id")[outcome].transform("mean")
    if np.allclose(predicted, predicted[0]) or np.allclose(observed, observed[0]):
        return float("nan")
    return float(spearmanr(predicted, observed).statistic)


def paired_bootstrap(
    frame: pd.DataFrame,
    prediction_a: str,
    prediction_b: str,
    outcome: str = "observed_recovery_loss",
    *,
    repeats: int,
    seed: int,
) -> dict:
    """Network-cluster paired bootstrap (algorithm identical to v12 t01/t03 scripts)."""
    rng = np.random.default_rng(seed)
    networks = np.asarray(sorted(frame["network_id"].unique()))
    by_network = {net: grp for net, grp in frame.groupby("network_id")}
    deltas_pooled = []
    deltas_network = []
    rho_a_pooled, rho_b_pooled = [], []
    rho_a_network, rho_b_network = [], []
    skipped = 0
    for _ in range(repeats):
        sampled = rng.choice(networks, size=len(networks), replace=True)
        if len(np.unique(sampled)) < 2:
            skipped += 1
            continue
        parts = []
        for draw, network in enumerate(sampled):
            part = by_network[network].copy()
            part["network_id"] = f"draw_{draw}"
            parts.append(part)
        boot = pd.concat(parts, ignore_index=True)
        ma = metrics(boot, prediction_a, outcome)
        mb = metrics(boot, prediction_b, outcome)
        deltas_pooled.append(ma["pooled_spearman"] - mb["pooled_spearman"])
        deltas_network.append(ma["network_spearman"] - mb["network_spearman"])
        rho_a_pooled.append(ma["pooled_spearman"])
        rho_b_pooled.append(mb["pooled_spearman"])
        rho_a_network.append(ma["network_spearman"])
        rho_b_network.append(mb["network_spearman"])

    def stats(vals):
        arr = np.asarray(vals)
        return (
            float(np.mean(arr)),
            float(np.quantile(arr, 0.025)),
            float(np.quantile(arr, 0.975)),
            float(np.mean(arr > 0.0)),
        )

    out = {"repeats": repeats, "seed": seed, "skipped_degenerate_draws": skipped}
    for level, delta, ra, rb in (
        ("pooled", deltas_pooled, rho_a_pooled, rho_b_pooled),
        ("network", deltas_network, rho_a_network, rho_b_network),
    ):
        mean, low, high, win = stats(delta)
        out[f"delta_mean_{level}"] = mean
        out[f"ci_low_{level}"] = low
        out[f"ci_high_{level}"] = high
        out[f"win_fraction_{level}"] = win
        out[f"rho_empirical_mean_{level}"] = float(np.mean(ra))
        out[f"rho_r6_mean_{level}"] = float(np.mean(rb))
    return out


def main() -> None:
    t01 = pd.read_csv(T01_SECOND, dtype={"network_id": str, "station_id": str})
    sec = pd.read_csv(T03_SECOND, dtype={"network_id": str, "station_id": str})
    first = pd.read_csv(T03_FIRST, dtype={"network_id": str, "station_id": str})
    master = pd.read_csv(MASTER)

    # ---- input consistency ---------------------------------------------------
    merged = t01.merge(sec, on=["network_id", "station_id", "gap_length"], suffixes=("_t01", "_t03"))
    assert len(merged) == len(t01) == len(sec), "second-panel files must align 1:1"
    assert np.allclose(merged.empirical_transfer_prediction_t01, merged.empirical_transfer_prediction_t03)
    assert np.allclose(merged.observed_recovery_loss_t01, merged.observed_recovery_loss_t03)
    assert np.allclose(merged.simple_fitperiod_t01, merged.simple_fitperiod_t03)
    assert np.allclose(sec.r8_simple, sec.simple_fitperiod), "r8_simple must equal simple_fitperiod"
    assert np.allclose(sec.r11_surface, sec.surface_prediction_mae)
    assert np.allclose(sec.empirical, sec.empirical_transfer_prediction)
    assert np.allclose(first.empirical, first.empirical_transfer_prediction)
    assert np.allclose(first.r11_surface, first.surface_prediction_mae)
    assert (sec.horizon_group == np.where(sec.gap_length.isin(DIRECT_HORIZONS), "direct", "fallback")).all()
    assert sec.gap_length.isin(DIRECT_HORIZONS).sum() == 874
    assert first.gap_length.isin(DIRECT_HORIZONS).sum() == 858

    first = first.copy()
    first["horizon_group"] = np.where(first.gap_length.isin(DIRECT_HORIZONS), "direct", "fallback")

    # ---- cells ---------------------------------------------------------------
    cells = [
        ("second", "direct_874", sec[sec.horizon_group == "direct"].copy()),
        ("second", "all_1446", sec.copy()),
        ("first", "direct_858", first[first.horizon_group == "direct"].copy()),
        ("first", "all_1440", first.copy()),
    ]
    method_cols = {
        "second": {"empirical": "empirical_transfer_prediction", "r6": "r6_station_gap",
                   "simple": "simple_fitperiod", "surface": "surface_prediction_mae"},
        "first": {"empirical": "empirical_transfer_prediction", "r6": "r6_station_gap",
                  "simple": "r8_simple", "surface": "surface_prediction_mae"},
    }

    # ---- summary metrics ------------------------------------------------------
    summary_rows = []
    for panel, subset, frame in cells:
        obs_net_mean = frame.groupby("network_id")["observed_recovery_loss"].transform("mean")
        obs_control = float(spearmanr(obs_net_mean, frame["observed_recovery_loss"]).statistic)
        for method, col in method_cols[panel].items():
            row = {"panel": panel, "subset": subset, "method": method}
            row.update(metrics(frame, col))
            row["network_mean_only_pooled"] = obs_control  # t01 definition: control on observed structure
            net_pred_mean = frame.groupby("network_id")[col].transform("mean")
            row["netmean_pred_only_pooled"] = float(spearmanr(net_pred_mean, frame["observed_recovery_loss"]).statistic)
            summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUT / "summary_metrics.csv", index=False)

    # ---- verification vs master ladder ----------------------------------------
    verify_rows = []
    for panel, subset, frame in cells:
        for method, col in method_cols[panel].items():
            m = metrics(frame, col)
            master_rung = {"second": {"empirical": "empirical", "r6": "r6_station_gap",
                                      "simple": "r8_simple", "surface": "r11_surface"},
                           "first": {"empirical": "empirical", "r6": "r6_station_gap",
                                     "simple": "r8_simple", "surface": "r11_surface"}}[panel][method]
            mr = master[(master.panel == panel) & (master.subset == subset) & (master.rung == master_rung)]
            if len(mr) == 0:
                continue
            mr = mr.iloc[0]
            verify_rows.append({
                "panel": panel, "subset": subset, "method": method,
                "pooled_match": np.isclose(m["pooled_spearman"], mr["pooled_spearman"], atol=1e-9),
                "network_match": np.isclose(m["network_spearman"], mr["network_spearman"], atol=1e-9),
                "slope_match": np.isclose(m["calibration_slope"], mr["calibration_slope"], atol=1e-9),
                "intercept_match": np.isclose(m["calibration_intercept"], mr["calibration_intercept"], atol=1e-9),
                "r2_match": np.isclose(m["r2"], mr["r2"], atol=1e-9),
                "rmse_match": np.isclose(m["rmse"], mr["rmse"], atol=1e-9),
            })
    pd.DataFrame(verify_rows).to_csv(OUT / "master_ladder_verification.csv", index=False)

    # ---- predictor correlations ------------------------------------------------
    corr_rows = []
    for panel, subset, frame in cells:
        emp = frame["empirical_transfer_prediction"]
        r6 = frame["r6_station_gap"]
        simp = frame[method_cols[panel]["simple"]]
        corr_rows.append({
            "panel": panel, "subset": subset, "n": len(frame),
            "corr_empirical_r6_spearman": float(spearmanr(emp, r6).statistic),
            "corr_empirical_r6_pearson": float(pearsonr(emp, r6).statistic),
            "corr_empirical_simple_spearman": float(spearmanr(emp, simp).statistic),
            "corr_empirical_simple_pearson": float(pearsonr(emp, simp).statistic),
        })
    pd.DataFrame(corr_rows).to_csv(OUT / "predictor_correlation.csv", index=False)

    # ---- paired bootstrap (official seed 42) ------------------------------------
    boot_rows = []
    boot_verify = []
    for panel, subset, frame in cells:
        res = paired_bootstrap(frame, "empirical_transfer_prediction", "r6_station_gap",
                               repeats=REPEATS, seed=SEED_OFFICIAL)
        for level in ("pooled", "network"):
            boot_rows.append({
                "panel": panel, "subset": subset, "level": level,
                "delta_mean": res[f"delta_mean_{level}"],
                "ci_low": res[f"ci_low_{level}"],
                "ci_high": res[f"ci_high_{level}"],
                "win_fraction": res[f"win_fraction_{level}"],
                "rho_empirical_boot_mean": res[f"rho_empirical_mean_{level}"],
                "rho_r6_boot_mean": res[f"rho_r6_mean_{level}"],
                "n_networks": frame["network_id"].nunique(), "n_units": len(frame),
                "repeats": REPEATS, "seed": SEED_OFFICIAL,
                "skipped_degenerate_draws": res["skipped_degenerate_draws"],
            })
        # verification run with the reference seed 0 (t01 used 0)
        res0 = paired_bootstrap(frame, "empirical_transfer_prediction", "r6_station_gap",
                                repeats=REPEATS, seed=SEED_VERIFY)
        for level in ("pooled", "network"):
            boot_verify.append({
                "panel": panel, "subset": subset, "level": level,
                "delta_mean": res0[f"delta_mean_{level}"],
                "ci_low": res0[f"ci_low_{level}"],
                "ci_high": res0[f"ci_high_{level}"],
                "win_fraction": res0[f"win_fraction_{level}"],
                "repeats": REPEATS, "seed": SEED_VERIFY,
            })
    pd.DataFrame(boot_rows).to_csv(OUT / "paired_bootstrap.csv", index=False)
    pd.DataFrame(boot_verify).to_csv(OUT / "paired_bootstrap_seed0_verification.csv", index=False)

    # ---- per-horizon network Spearman (second panel) ------------------------------
    horizon_rows = []
    for horizon in DIRECT_HORIZONS:
        frame = sec[sec.gap_length.eq(horizon)]
        row = {"horizon": horizon, "n_units": len(frame), "n_networks": int(frame.network_id.nunique())}
        for method in ("empirical", "r6", "simple"):
            col = method_cols["second"][method]
            net = frame.groupby("network_id")[[col, "observed_recovery_loss"]].mean()
            row[f"{method}_network_spearman"] = float(
                spearmanr(net[col], net["observed_recovery_loss"]).statistic)
        horizon_rows.append(row)
    pd.DataFrame(horizon_rows).to_csv(OUT / "per_horizon_network_spearman.csv", index=False)

    # ---- within-network decomposition (direct subsets) -----------------------------
    decomp_rows = []
    for panel, subset, frame in cells:
        if not subset.startswith("direct"):
            continue
        for method, col in method_cols[panel].items():
            series = within_network_spearman_series(frame, col)
            decomp_rows.append({
                "panel": panel, "subset": subset, "method": method,
                "network_demeaned_pooled_rho": residualized_spearman(frame, col),
                "median_within_network_rho": float(series.median()) if len(series) else float("nan"),
                "mean_within_network_rho": float(series.mean()) if len(series) else float("nan"),
                "n_networks_defined": int(len(series)),
                "within_q1": float(series.quantile(0.25)) if len(series) else float("nan"),
                "within_q3": float(series.quantile(0.75)) if len(series) else float("nan"),
            })
    pd.DataFrame(decomp_rows).to_csv(OUT / "within_network_decomposition.csv", index=False)

    # ---- panel composition -----------------------------------------------------------
    comp_rows = []
    for panel, frame in (("second", sec), ("first", first)):
        for subset in ("all", "direct"):
            sub = frame if subset == "all" else frame[frame.horizon_group == "direct"]
            for domain, grp in sub.groupby("domain"):
                comp_rows.append({
                    "panel": panel, "subset": subset, "domain": domain,
                    "n_networks": grp.network_id.nunique(), "n_stations": grp.station_id.nunique(),
                    "n_units": len(grp),
                })
            comp_rows.append({
                "panel": panel, "subset": subset, "domain": "TOTAL",
                "n_networks": sub.network_id.nunique(), "n_stations": sub.station_id.nunique(),
                "n_units": len(sub),
            })
        for hg, grp in frame.groupby("horizon_group"):
            comp_rows.append({
                "panel": panel, "subset": f"horizon_group_{hg}", "domain": "TOTAL",
                "n_networks": grp.network_id.nunique(), "n_stations": grp.station_id.nunique(),
                "n_units": len(grp),
            })
    pd.DataFrame(comp_rows).to_csv(OUT / "panel_composition.csv", index=False)

    # ---- unit comparison tables ---------------------------------------------------------
    for panel, frame, outname in (
        ("second", sec, "unit_comparison_second.csv"),
        ("first", first, "unit_comparison_first.csv"),
    ):
        out = pd.DataFrame({
            "network_id": frame.network_id,
            "station_id": frame.station_id,
            "gap_length": frame.gap_length,
            "horizon_group": frame.horizon_group,
            "empirical": frame["empirical_transfer_prediction"],
            "r6": frame["r6_station_gap"],
            "simple": frame[method_cols[panel]["simple"]],
            "surface": frame["surface_prediction_mae"],
            "observed": frame["observed_recovery_loss"],
            "domain": frame["domain"],
            "subset": np.where(frame.horizon_group == "direct", "direct", "fallback"),
        })
        out.to_csv(OUT / outname, index=False)

    # ---- machine-readable verification summary ---------------------------------------------
    summary = {
        "input_consistency": "OK",
        "master_ladder_verification": [
            {k: (bool(v) if isinstance(v, np.bool_) else v) for k, v in r.items()}
            for r in verify_rows
        ],
        "bootstrap_seed0_verification": boot_verify,
        "t01_bootstrap_reference": pd.read_csv(T01_BOOT).to_dict(orient="records"),
    }
    (OUT / "verification_summary.json").write_text(json.dumps(summary, indent=1))

    print("done")
    for row in boot_rows:
        print(row["panel"], row["subset"], row["level"],
              f"delta {row['delta_mean']:.5f} [{row['ci_low']:.5f}, {row['ci_high']:.5f}] win {row['win_fraction']:.4f}")
    print("verify (seed0):")
    for row in boot_verify:
        print(row["panel"], row["subset"], row["level"],
              f"delta {row['delta_mean']:.5f} [{row['ci_low']:.5f}, {row['ci_high']:.5f}] win {row['win_fraction']:.4f}")


if __name__ == "__main__":
    main()
