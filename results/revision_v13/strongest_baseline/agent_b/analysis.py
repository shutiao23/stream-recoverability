#!/usr/bin/env python3
"""Strongest-baseline harmonization analysis (agent_b, adversarial pair).

Definitive empirical-vs-strongest-fair-baseline comparison for the WRR
revision. Strongest fair baseline = station x horizon historical mean of
fitting-period MAE (t03 ladder rung r6_station_gap).

Reproduces t03/t01 conventions exactly (metrics(), equal-network WLS
calibration with sqrt(1/n) root weights, relabeled-draw network bootstrap)
but uses seed 42 for all resampling, as mandated by the task. A seed-0
verification run compares against the archived t03 paired_bootstrap.csv
before the seed-42 outputs are written.

Read-only inputs (never modified); writes only inside this directory.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr

warnings.filterwarnings("ignore")

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
T01 = ROOT / "results/revision_v12/t01_paired_comparison/agent_a"
T03 = ROOT / "results/revision_v12/t03_baseline_ladder/agent_a"

DIRECT_HORIZONS = (7, 30, 90, 180)
FINAL_SEED = 42
VERIFY_SEED = 0
REPEATS = 2000

PRED_COLS = {
    "empirical": "empirical",
    "r6": "r6",
    "simple": "simple",
    "surface": "surface",
}


# --------------------------------------------------------------------------- #
# metric definitions (bit-compatible with scripts/rev_v12_t03_baseline_ladder_a)
# --------------------------------------------------------------------------- #
def _fit_linear(design, outcome, weight):
    return np.linalg.lstsq(design * weight[:, None], outcome * weight, rcond=None)[0]


def metrics(frame: pd.DataFrame, prediction: str, outcome: str) -> dict:
    """Pooled/network Spearman, equal-network WLS calibration, R2, RMSE."""
    usable = frame[["network_id", prediction, outcome]].dropna()
    predicted = usable[prediction].to_numpy(dtype=float)
    observed = usable[outcome].to_numpy(dtype=float)
    net = usable.groupby("network_id")[[prediction, outcome]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), predicted])
    constant_pred = bool(np.allclose(predicted, predicted[0]))
    if constant_pred:
        slope = float("nan")
        intercept = float(np.average(observed, weights=weight))
    else:
        intercept, slope = _fit_linear(design, observed, weight)
        intercept, slope = float(intercept), float(slope)
    ss_res = float(np.sum(np.square(observed - predicted)))
    ss_tot = float(np.sum(np.square(observed - np.mean(observed))))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "n": int(len(usable)),
        "n_networks": int(len(net)),
        "pooled_spearman": float(spearmanr(predicted, observed).statistic),
        "network_spearman": float(spearmanr(net[prediction], net[outcome]).statistic),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "r2": r2,
        "rmse": float(np.sqrt(np.mean(np.square(observed - predicted)))),
    }


def within_network_spearman_median(frame: pd.DataFrame, prediction: str, outcome: str,
                                   min_units: int = 4) -> dict:
    rows = {}
    for network, values in frame.groupby("network_id"):
        if len(values) < min_units:
            continue
        p = values[prediction].to_numpy(dtype=float)
        o = values[outcome].to_numpy(dtype=float)
        if np.allclose(p, p[0]) or np.allclose(o, o[0]):
            continue
        rows[network] = float(spearmanr(p, o).statistic)
    series = pd.Series(rows)
    return {
        "n_networks_within_defined": int(len(series)),
        "within_network_spearman_median": float(series.median()) if len(series) else float("nan"),
        "within_network_spearman_mean": float(series.mean()) if len(series) else float("nan"),
    }


def residualized_spearman(frame: pd.DataFrame, prediction: str, outcome: str) -> float:
    usable = frame[["network_id", prediction, outcome]].dropna()
    p = usable[prediction] - usable.groupby("network_id")[prediction].transform("mean")
    o = usable[outcome] - usable.groupby("network_id")[outcome].transform("mean")
    if np.allclose(p, p.iloc[0]) or np.allclose(o, o.iloc[0]):
        return float("nan")
    return float(spearmanr(p, o).statistic)


def network_mean_only_pooled(frame: pd.DataFrame, outcome: str) -> float:
    usable = frame[["network_id", outcome]].dropna()
    nm = usable.groupby("network_id")[outcome].transform("mean")
    return float(spearmanr(nm, usable[outcome]).statistic)


# --------------------------------------------------------------------------- #
# paired network bootstrap (t03 convention, relabeled draws)
# --------------------------------------------------------------------------- #
def paired_bootstrap(frame: pd.DataFrame, pred_a: str, pred_b: str, outcome: str,
                     *, repeats: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    networks = np.asarray(sorted(frame["network_id"].unique()))
    by_network = {net: group for net, group in frame.groupby("network_id")}
    d_station, d_network = [], []
    boot_a_net, boot_b_net = [], []
    boot_a_station, boot_b_station = [], []
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
        ma = metrics(boot, pred_a, outcome)
        mb = metrics(boot, pred_b, outcome)
        d_station.append(ma["pooled_spearman"] - mb["pooled_spearman"])
        d_network.append(ma["network_spearman"] - mb["network_spearman"])
        boot_a_net.append(ma["network_spearman"])
        boot_b_net.append(mb["network_spearman"])
        boot_a_station.append(ma["pooled_spearman"])
        boot_b_station.append(mb["pooled_spearman"])
    d_station, d_network = np.asarray(d_station), np.asarray(d_network)
    return {
        "repeats": int(repeats),
        "seed": int(seed),
        "skipped_degenerate_draws": skipped,
        "delta_pooled_spearman_mean": float(np.mean(d_station)),
        "delta_pooled_spearman_ci95": [float(np.quantile(d_station, 0.025)), float(np.quantile(d_station, 0.975))],
        "fraction_delta_pooled_positive": float(np.mean(d_station > 0.0)),
        "delta_network_spearman_mean": float(np.mean(d_network)),
        "delta_network_spearman_ci95": [float(np.quantile(d_network, 0.025)), float(np.quantile(d_network, 0.975))],
        "fraction_delta_network_positive": float(np.mean(d_network > 0.0)),
        "empirical_network_boot_mean": float(np.mean(boot_a_net)),
        "r6_network_boot_mean": float(np.mean(boot_b_net)),
        "empirical_station_gap_boot_mean": float(np.mean(boot_a_station)),
        "r6_station_gap_boot_mean": float(np.mean(boot_b_station)),
    }


# --------------------------------------------------------------------------- #
# load + build unit tables
# --------------------------------------------------------------------------- #
def build_second() -> pd.DataFrame:
    t01 = pd.read_csv(T01 / "predictions.csv")
    t03 = pd.read_csv(T03 / "unit_predictions_second.csv")
    key = ["network_id", "station_id", "gap_length"]
    assert t01.duplicated(key).sum() == 0 and t03.duplicated(key).sum() == 0
    df = t01[key + ["simple_fitperiod", "empirical_transfer_prediction",
                    "observed_recovery_loss", "provider", "domain", "horizon_group"]].merge(
        t03[key + ["r6_station_gap", "r8_simple", "surface_prediction_mae", "r4_network",
                   "r5_network_gap", "empirical"]].rename(columns={"empirical": "empirical_t03"}),
        on=key, how="inner")
    assert len(df) == 1446
    assert (df["r8_simple"] - df["simple_fitperiod"]).abs().max() < 1e-12
    assert (df["empirical_t03"] - df["empirical_transfer_prediction"]).abs().max() < 1e-12
    df = df.drop(columns=["empirical_t03"])
    assert ((df["horizon_group"] == "direct") == df["gap_length"].isin(DIRECT_HORIZONS)).all()
    df = df.rename(columns={
        "empirical_transfer_prediction": "empirical", "r6_station_gap": "r6",
        "simple_fitperiod": "simple", "surface_prediction_mae": "surface",
    })
    df["subset"] = np.where(df["horizon_group"] == "direct", "direct", "all")
    return df


def build_first() -> pd.DataFrame:
    p1 = pd.read_csv(T03 / "unit_predictions_first.csv")
    key = ["network_id", "station_id", "gap_length"]
    assert p1.duplicated(key).sum() == 0
    df = p1[key + ["empirical_transfer_prediction", "observed_recovery_loss",
                   "provider", "domain", "r6_station_gap", "r8_simple",
                   "surface_prediction_mae", "empirical"]].copy()
    df = df.rename(columns={"empirical": "empirical_t03"})
    df["horizon_group"] = np.where(df["gap_length"].isin(DIRECT_HORIZONS), "direct", "fallback")
    assert (df["empirical_t03"] - df["empirical_transfer_prediction"]).abs().max() < 1e-12
    df = df.drop(columns=["empirical_t03"])
    assert len(df) == 1440 and (df["horizon_group"] == "direct").sum() == 858
    df = df.rename(columns={
        "empirical_transfer_prediction": "empirical", "r6_station_gap": "r6",
        "r8_simple": "simple", "surface_prediction_mae": "surface",
    })
    df["subset"] = np.where(df["horizon_group"] == "direct", "direct", "all")
    return df


# --------------------------------------------------------------------------- #
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log: list[str] = []

    def logln(msg: str = "") -> None:
        print(msg, flush=True)
        log.append(msg)

    # ------------------------------------------------------------- assemble
    second = build_second()
    first = build_first()
    cells = {
        "second_direct_874": second.loc[second["horizon_group"] == "direct"].copy(),
        "second_all_1446": second.copy(),
        "first_direct_858": first.loc[first["horizon_group"] == "direct"].copy(),
        "first_all_1440": first.copy(),
    }
    for name, df in cells.items():
        assert len(df) == int(name.split("_")[-1]), (name, len(df))

    # unit comparison tables (full panels)
    cols = ["network_id", "station_id", "gap_length", "horizon_group",
            "empirical", "r6", "simple", "surface", "observed_recovery_loss", "subset"]
    second[cols].to_csv(OUT / "unit_comparison_second.csv", index=False)
    first[cols].to_csv(OUT / "unit_comparison_first.csv", index=False)

    # ------------------------------------------------------------- metrics
    metric_rows = []
    for cell, df in cells.items():
        panel, subset = cell.split("_", 1)
        nmo = network_mean_only_pooled(df, "observed_recovery_loss")
        for method, col in PRED_COLS.items():
            m = metrics(df, col, "observed_recovery_loss")
            metric_rows.append({
                "panel": panel, "subset": subset, "method": method,
                "n": m["n"], "n_networks": m["n_networks"],
                "pooled_spearman": m["pooled_spearman"],
                "network_spearman": m["network_spearman"],
                "network_mean_only_pooled": nmo,
                "calib_slope": m["calibration_slope"],
                "calib_intercept": m["calibration_intercept"],
                "r2": m["r2"], "rmse": m["rmse"],
            })
    summary = pd.DataFrame(metric_rows)
    summary.to_csv(OUT / "summary_metrics.csv", index=False)

    # pipeline validation against master ladder
    ladder = pd.read_csv(T03 / "master_ladder_table.csv")
    checks = []
    for (panel, subset), grp in summary.groupby(["panel", "subset"]):
        for method, col in PRED_COLS.items():
            row = grp.loc[grp["method"] == method].iloc[0]
            ladder_rung = {
                "empirical": "empirical", "r6": "r6_station_gap",
                "simple": "r8_simple", "surface": "r11_surface",
            }[method]
            lr = ladder[(ladder["panel"] == panel) & (ladder["subset"] == subset) &
                        (ladder["rung"] == ladder_rung)]
            if lr.empty:
                continue
            lr = lr.iloc[0]
            checks.append({
                "panel": panel, "subset": subset, "method": method,
                "pooled_spearman_match": abs(row["pooled_spearman"] - lr["pooled_spearman"]) < 1e-12,
                "network_spearman_match": abs(row["network_spearman"] - lr["network_spearman"]) < 1e-12,
                "calib_slope_match": abs(row["calib_slope"] - lr["calibration_slope"]) < 1e-10,
                "calib_intercept_match": abs(row["calib_intercept"] - lr["calibration_intercept"]) < 1e-10,
                "r2_match": abs(row["r2"] - lr["r2"]) < 1e-12,
                "rmse_match": abs(row["rmse"] - lr["rmse"]) < 1e-12,
                "pooled_ref": float(lr["pooled_spearman"]),
                "network_ref": float(lr["network_spearman"]),
            })
    check_df = pd.DataFrame(checks)
    check_df.to_csv(OUT / "ladder_verification.csv", index=False)
    n_fail = int((~check_df[[c for c in check_df.columns if c.endswith("_match")]]).sum().sum())
    logln(f"[verify] ladder cross-check rows: {len(check_df)}, mismatching cells: {n_fail}")
    if n_fail:
        bad = check_df[~(check_df[[c for c in check_df.columns if c.endswith("_match")]]).all(axis=1)]
        logln(f"[verify] FAILED cells:\n{bad.to_string(index=False)}")

    # ------------------------------------------------------------- bootstrap
    boot_rows = []
    for cell, df in cells.items():
        panel, subset = cell.split("_", 1)
        for seed in (VERIFY_SEED, FINAL_SEED):
            b = paired_bootstrap(df, "empirical", "r6", "observed_recovery_loss",
                                 repeats=REPEATS, seed=seed)
            for level, key in (("network", "network"), ("station_gap", "pooled")):
                boot_rows.append({
                    "panel": panel, "subset": subset, "level": level,
                    "seed": seed, "repeats": b["repeats"],
                    "skipped_degenerate_draws": b["skipped_degenerate_draws"],
                    "delta_mean": b[f"delta_{key}_spearman_mean"],
                    "ci_low": b[f"delta_{key}_spearman_ci95"][0],
                    "ci_high": b[f"delta_{key}_spearman_ci95"][1],
                    "win_fraction": b[f"fraction_delta_{key}_positive"],
                    "empirical_boot_mean": b[f"empirical_{'network' if level=='network' else 'station_gap'}_boot_mean"],
                    "r6_boot_mean": b[f"r6_{'network' if level=='network' else 'station_gap'}_boot_mean"],
                })
    boot_df = pd.DataFrame(boot_rows)
    boot_df[boot_df["seed"] == VERIFY_SEED].to_csv(OUT / "paired_bootstrap_seed0_verification.csv", index=False)
    boot_df[boot_df["seed"] == FINAL_SEED].to_csv(OUT / "paired_bootstrap.csv", index=False)

    # verify against archived t03 paired_bootstrap.csv (seed 0)
    t03b = pd.read_csv(T03 / "paired_bootstrap.csv")
    v0 = boot_df[boot_df["seed"] == VERIFY_SEED]
    for _, row in v0.iterrows():
        key = (row["panel"], row["subset"])
        ref = t03b[(t03b["panel"] == key[0]) & (t03b["subset"] == key[1]) &
                   (t03b["method_a"] == "empirical") & (t03b["method_b"] == "r6_station_gap")]
        if ref.empty:
            continue
        ref = ref.iloc[0]
        if row["level"] == "network":
            ref_val, ref_ci, ref_frac = (ref["delta_network_spearman_mean"], ref["delta_network_spearman_ci95"],
                                         ref["fraction_delta_network_positive"])
        else:
            ref_val, ref_ci, ref_frac = (ref["delta_pooled_spearman_mean"], ref["delta_pooled_spearman_ci95"],
                                         ref["fraction_delta_pooled_positive"])
        d = abs(row["delta_mean"] - ref_val)
        logln(f"[verify] seed0 {key} {row['level']}: mine {row['delta_mean']:.6f} vs t03 {ref_val:.6f} "
              f"(|diff| {d:.2e}, CI {row['ci_low']:.4f},{row['ci_high']:.4f} vs {ref_ci}, "
              f"win {row['win_fraction']:.4f} vs {ref_frac:.4f})")

    # ------------------------------------------------------------- per-horizon (second direct)
    hz = second.loc[second["horizon_group"] == "direct"]
    hz_rows = []
    for gap, g in hz.groupby("gap_length"):
        m_emp = metrics(g, "empirical", "observed_recovery_loss")
        m_r6 = metrics(g, "r6", "observed_recovery_loss")
        m_sim = metrics(g, "simple", "observed_recovery_loss")
        hz_rows.append({
            "horizon": int(gap), "n_units": m_emp["n"], "n_networks": m_emp["n_networks"],
            "empirical_network_spearman": m_emp["network_spearman"],
            "r6_network_spearman": m_r6["network_spearman"],
            "simple_network_spearman": m_sim["network_spearman"],
        })
    pd.DataFrame(hz_rows).sort_values("horizon").to_csv(OUT / "per_horizon_network_spearman.csv", index=False)

    # ------------------------------------------------------------- predictor correlations
    corr_rows = []
    for cell, df in cells.items():
        for a, b in (("empirical", "r6"), ("empirical", "simple")):
            sub = df[[a, b]].dropna()
            corr_rows.append({
                "subset": cell,
                "pair": f"{a}_vs_{b}",
                "spearman": float(spearmanr(sub[a], sub[b]).statistic),
                "pearson": float(pearsonr(sub[a], sub[b]).statistic),
                "n": len(sub),
            })
    pd.DataFrame(corr_rows).to_csv(OUT / "predictor_correlation.csv", index=False)

    # ------------------------------------------------------------- within-network decomposition
    dec_rows = []
    for cell in ("second_direct_874", "first_direct_858"):
        df = cells[cell]
        nmo = network_mean_only_pooled(df, "observed_recovery_loss")
        for method, col in PRED_COLS.items():
            w = within_network_spearman_median(df, col, "observed_recovery_loss")
            dec_rows.append({
                "panel": cell.split("_")[0], "subset": cell.split("_", 1)[1],
                "method": method,
                "network_demeaned_pooled_rho": residualized_spearman(df, col, "observed_recovery_loss"),
                "median_within_network_rho": w["within_network_spearman_median"],
                "mean_within_network_rho": w["within_network_spearman_mean"],
                "n_networks_within_defined": w["n_networks_within_defined"],
                "network_mean_only_pooled_rho": nmo,
            })
    pd.DataFrame(dec_rows).to_csv(OUT / "within_network_decomposition.csv", index=False)

    # ------------------------------------------------------------- panel composition
    comp_rows = []
    for panel, df in (("second", second), ("first", first)):
        row = {
            "panel": panel,
            "n_networks": df["network_id"].nunique(),
            "n_stations": df["station_id"].nunique(),
            "n_units": len(df),
            "n_direct_units": int((df["horizon_group"] == "direct").sum()),
            "n_fallback_units": int((df["horizon_group"] == "fallback").sum()),
        }
        for domain, g in df.groupby("domain"):
            row[f"domain_{domain}_networks"] = g["network_id"].nunique()
            row[f"domain_{domain}_stations"] = g["station_id"].nunique()
            row[f"domain_{domain}_units"] = len(g)
        comp_rows.append(row)
    pd.DataFrame(comp_rows).to_csv(OUT / "panel_composition.csv", index=False)

    # ------------------------------------------------------------- summary json
    (OUT / "verification_summary.json").write_text(json.dumps({
        "ladder_verification_failures": n_fail,
        "bootstrap_seed": FINAL_SEED,
        "bootstrap_repeats": REPEATS,
        "checks": checks,
    }, indent=2, default=str))

    logln("done")


if __name__ == "__main__":
    main()
