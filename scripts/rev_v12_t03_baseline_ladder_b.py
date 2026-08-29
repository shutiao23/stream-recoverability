#!/usr/bin/env python3
"""Revision v12, task 03 (agent B, adversarial pair) — same-unit baseline ladder.

Read-only inputs: paper/, src/, configs/, data/, results/ (except own namespace).
Writes only to: results/revision_v12/t03_baseline_ladder/agent_b/.

Rungs (all fitting-period-only; evaluated on second panel 1,446 units / 57
networks and first panel 1,440 cells / 42 networks):

  r1  global mean
  r2  gap length only (per-gap fitting means + log-linear interp/extrap)
  r3  gap length + season (2 Fourier harmonics, unweighted OLS on fitting rows)
  r4  network historical mean (per-network mean of own fitting-period losses)
  r5  network x horizon mean (fallback: r4, then r1)
  r6  station x horizon mean (fallback: r5, r4, r1)
  r7  empirical curve (previous-period, leave-one-period-out) = frozen artifact
  r8  simple route-A descriptors (fit-period coefficients on recomputed features)
  r9  conditional-covariance operator model (NA for both panels; dev-only sanity)
  r10 generic blocked-CV (per-gap leave-one-network-out mean of route-A)
  r11 risk surface (t04 stored prediction column; NOT refit)
  r12 empirical + structural meta-model (stack r8 + surface via fitting-period
      OLS; pooled-surface fixed-effects reconstructed from t04 summary JSON)

Metrics per rung per subset (second panel: 874 direct / 1,446 full; first
panel: 780 direct / 1,440 full): pooled (station-gap) Spearman, network-level
Spearman, median within-network Spearman, R2, RMSE, equal-network-weighted
calibration slope/intercept. Paired 2,000-network bootstrap DeltaRho vs the
strongest non-proposed baseline and vs rung 7 on both subsets; residualization
controls (per-horizon network Spearman; residualized pooled Spearman;
amplitude-normalized MAE).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import BSpline
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    XGBOOST_PARAMETERS,
    read_temperature_panel,
)
from stream_recoverability.experiments.recovery_roster import (  # noqa: E402
    fitting_period_empirical_losses,
)
from stream_recoverability.experiments.route_a_confirmation import (  # noqa: E402
    simple_predictors,
)

OUT = ROOT / "results/revision_v12/t03_baseline_ladder/agent_b"
OUT.mkdir(parents=True, exist_ok=True)
INTER = OUT / "intermediate"
INTER.mkdir(parents=True, exist_ok=True)

SEED = 20260829
N_BOOT = 2000

RV = ROOT / "results/development_v11/reviewer_completion"
SC = ROOT / "results/development_v11/second_confirmation"
T04 = ROOT / "results/revision_v12/t04_risk_surface/agent_a"
T01B = ROOT / "results/revision_v12/t01_paired_comparison/agent_b"

SECOND_PRED = SC / "scoring/empirical_predictions.csv"
SECOND_PLACEMENTS = SC / "scoring/placement_losses.csv"
SECOND_SIMPLE = SC / "scoring/simple_predictions.csv"
DEV_FL = RV / "development_empirical_fit_losses.csv"
CONF_FL = RV / "confirmation_empirical_fit_losses.csv"
DEV_PRED = RV / "development_empirical_predictions.csv"
CONF_PRED = RV / "confirmation_empirical_predictions.csv"
DEV_OUTCOMES = ROOT / "results/development_v11/station_gap_outcomes.csv"
NESTED_LONO = ROOT / "results/development_v11/nested_lono_predictions.csv"
OPERATOR = ROOT / "results/development_v11/complete_operator_predictions.csv"
ROUTE_A_PRED = ROOT / "results/development_v11/route_a_confirmation/predictions.csv"
SURFACE_SUMMARY = T04 / "surface_fit_summary.json"
SURFACE_COV = T04 / "station_covariates.csv"
SURFACE_SECOND = T04 / "second_panel_predictions.csv"
SURFACE_FIRST = T04 / "first_panel_predictions.csv"
CONF_DAILY = ROOT / "results/development_v11/confirmation_daily_qc/networks"
SECOND_DAILY = SC / "daily_qc/networks"
CHMI_STATIONS = ROOT / "results/development_v11/chmi_temperature/stations"
DEV_CORPUS = ROOT / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
INVENTORY = ROOT / "results/development_v11/network_inventory.csv"
AGENTB_COEF = T01B / "t2_coefficients.json"

GAP_LENGTHS = (7, 14, 30, 60, 90, 180, 365)
DIRECT_GAPS = (7, 30, 90, 180)
SIMPLE_COLS = [
    "gap_length",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
    "nearest_donor_correlation",
]

RUNG_NAMES = [
    "r1_global_mean",
    "r2_gap_only",
    "r3_gap_season",
    "r4_network_mean",
    "r5_network_x_horizon",
    "r6_station_x_horizon",
    "r7_empirical_curve",
    "r8_simple_routeA",
    "r9_covariance_operator",
    "r10_blocked_cv_mean",
    "r11_risk_surface",
    "r12_meta_stack",
]
NONPROPOSED = ["r1_global_mean", "r2_gap_only", "r3_gap_season", "r4_network_mean",
               "r5_network_x_horizon", "r6_station_x_horizon", "r8_simple_routeA",
               "r10_blocked_cv_mean"]
PROPOSED = ["r7_empirical_curve", "r9_covariance_operator", "r11_risk_surface", "r12_meta_stack"]

SURFACE_KNOTS_LOG = np.log(np.array([7.0, 30.0, 90.0, 180.0]))
SPLINE_DEGREE = 2
SURFACE_KNOTS = np.concatenate(
    [[SURFACE_KNOTS_LOG[0]] * 3, [SURFACE_KNOTS_LOG[1]], [SURFACE_KNOTS_LOG[-1]] * 3]
)
N_BASIS = len(SURFACE_KNOTS) - (SPLINE_DEGREE + 1)
COV_COLS = ["temp_sd", "temp_iqr", "climatology_mae", "acf_lag1", "acf_gap",
            "daily_gradient", "donor_r2"]

t_start = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - t_start:7.1f}s] {msg}", flush=True)


# ---------------------------------------------------------------------------
# small pure helpers (reimplemented locally; not imported from t04 script)
# ---------------------------------------------------------------------------

def season_label(dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    months = pd.DatetimeIndex(pd.to_datetime(dates)).month
    return np.select(
        [months.isin([12, 1, 2]), months.isin([3, 4, 5]), months.isin([6, 7, 8])],
        ["DJF", "MAM", "JJA"],
        default="SON",
    )


def fourier_design(doy: np.ndarray) -> np.ndarray:
    ph = 2.0 * np.pi * (doy - 1.0) / 365.25
    return np.column_stack([np.sin(ph), np.cos(ph), np.sin(2 * ph), np.cos(2 * ph)])


def b_spline_basis(log_gap: np.ndarray) -> np.ndarray:
    n = len(log_gap)
    B = np.zeros((n, N_BASIS))
    for j in range(N_BASIS):
        c = np.zeros(N_BASIS)
        c[j] = 1.0
        B[:, j] = BSpline(SURFACE_KNOTS, c, SPLINE_DEGREE, extrapolate=True)(log_gap)
    return B


def parse_years(text) -> set[int]:
    if not isinstance(text, str) or not text:
        return set()
    return {int(v) for v in text.split("|") if v}


def acf_at_lag(s: pd.Series, lag: int) -> float:
    v = s.dropna().to_numpy(dtype=float)
    n = len(v)
    if n <= lag + 10:
        return np.nan
    a, b = v[: n - lag], v[lag:]
    if np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def series_stats(s: pd.Series) -> dict:
    v = s.dropna().to_numpy(dtype=float)
    out = {"temp_sd": np.nan, "temp_iqr": np.nan, "climatology_mae": np.nan}
    if len(v) < 30:
        return out
    out["temp_sd"] = float(np.std(v))
    out["temp_iqr"] = float(np.quantile(v, 0.75) - np.quantile(v, 0.25))
    idx = s.dropna().index
    if len(idx) > 60:
        doy = idx.dayofyear.to_numpy()
        doy_mean = pd.Series(v).groupby(doy).mean()
        clim_grid = doy_mean.reindex(range(1, 367)).interpolate(limit_direction="both")
        clim = clim_grid.to_numpy()[doy - 1]
        out["climatology_mae"] = float(np.nanmean(np.abs(v - clim)))
    return out


def panel_path(network_id: str) -> Path:
    second = SECOND_DAILY / network_id / "daily_wide_temperature.csv"
    if second.is_file():
        return second
    first = CONF_DAILY / network_id / "daily_wide_temperature.csv"
    if first.is_file():
        return first
    raise FileNotFoundError(f"no daily panel for {network_id}")


def read_chmi_panel(network: str, stations: set[str]) -> pd.DataFrame:
    frames = []
    for sid in stations:
        path = CHMI_STATIONS / str(sid) / "daily_temperature.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["site_id", "date", "temperature_c"])
        df = df[df["site_id"].astype(str) == str(sid)]
        frames.append(df.set_index("date")["temperature_c"].rename(str(sid)))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1)
    out.index = pd.to_datetime(out.index)
    return out


def panel_for_network(network: str, source: str, stations: set[str]) -> pd.DataFrame:
    if source == "second" and str(network).startswith("chmi"):
        return read_chmi_panel(network, stations)
    if source == "dev":
        inv = pd.read_csv(INVENTORY, dtype={"network_id": str})
        role = str(inv.set_index("network_id")["role"].get(network, "development"))
        path = DEV_CORPUS / role / "networks" / network / "daily_wide_qc.csv"
        wide = pd.read_csv(path)
        wide["date"] = pd.to_datetime(wide["date"])
        wide = wide.set_index("date")
        keep = [c for c in wide.columns if str(c) in stations]
        return wide.loc[:, keep]
    path = (SECOND_DAILY / network / "daily_wide_temperature.csv")
    if not path.is_file():
        path = CONF_DAILY / network / "daily_wide_temperature.csv"
    wide = pd.read_csv(path)
    wide["date"] = pd.to_datetime(wide["date"])
    wide = wide.set_index("date")
    keep = [c for c in wide.columns if str(c) in stations]
    return wide.loc[:, keep]


def donor_and_years(pred_df: pd.DataFrame) -> tuple[dict, dict]:
    donor_map: dict = {}
    years_map: dict = {}
    for (net, sta), g in pred_df.groupby(["network_id", "station_id"]):
        key = (str(net), str(sta))
        donors = g["donor_station_ids"].dropna()
        if len(donors):
            donor_map[key] = [str(d) for d in str(donors.iloc[0]).split("|") if d]
        ty = g["training_years"].dropna()
        if len(ty):
            years_map[key] = parse_years(str(ty.iloc[0]))
    return donor_map, years_map


# ---------------------------------------------------------------------------
# metrics (same conventions as paper / t01: equal-network-weighted calibration)
# ---------------------------------------------------------------------------

def safe_spearman(a, b) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) < 2 or len(b) < 2:
        return np.nan
    if np.nanstd(a) == 0 or np.nanstd(b) == 0 or np.isnan(a).any() or np.isnan(b).any():
        return np.nan
    return float(spearmanr(a, b).statistic)


def metrics_row(y, p, net, label: str) -> dict:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    net = np.asarray(net, dtype=str)
    n = len(y)
    df = pd.DataFrame({"y": y, "p": p, "net": net})
    row = {"label": label, "n_units": n, "n_networks": int(df["net"].nunique())}
    row["pooled_spearman"] = safe_spearman(y, p)
    nm = df.groupby("net")[["y", "p"]].mean()
    row["network_spearman"] = safe_spearman(nm["y"], nm["p"])
    ws = []
    for g, sub in df.groupby("net"):
        if len(sub) >= 4:
            r = safe_spearman(sub["y"], sub["p"])
            if not np.isnan(r):
                ws.append(r)
    row["within_network_spearman_median"] = float(np.median(ws)) if ws else np.nan
    row["within_network_fraction_defined"] = (
        float(len(ws)) / len(nm) if len(nm) else np.nan
    )
    w = 1.0 / df.groupby("net")["net"].transform("count").to_numpy(dtype=float)
    try:
        X = np.column_stack([np.ones(n), p])
        sw = np.sqrt(w)
        coef = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
        row["calibration_slope"] = float(coef[1])
        row["calibration_intercept"] = float(coef[0])
    except Exception:
        row["calibration_slope"] = np.nan
        row["calibration_intercept"] = np.nan
    ss_res = float(np.nansum((y - p) ** 2))
    ss_tot = float(np.nansum((y - y.mean()) ** 2))
    row["r2"] = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan
    row["rmse"] = float(np.sqrt(np.nanmean((y - p) ** 2)))
    return row


def residualized_pooled_spearman(y, p, net) -> float:
    df = pd.DataFrame({"y": y, "p": p, "net": np.asarray(net, dtype=str)})
    ym = df.groupby("net")["y"].transform("mean")
    pm = df.groupby("net")["p"].transform("mean")
    return safe_spearman(df["y"] - ym, df["p"] - pm)


# ---------------------------------------------------------------------------
# stage 1: second-panel fitting-period empirical losses (exact code path)
# ---------------------------------------------------------------------------

def load_second_fitting_losses() -> pd.DataFrame:
    cache = INTER / "empirical_losses_second_panel.csv"
    if cache.is_file():
        log("loading cached second-panel fitting losses")
        return pd.read_csv(cache, dtype={"network_id": str, "station_id": str})
    pl = pd.read_csv(SECOND_PLACEMENTS, dtype={"network_id": str, "station_id": str})
    parts = []
    params = {**XGBOOST_PARAMETERS, "n_jobs": 4}
    nets = sorted(pl["network_id"].unique())
    for i, net in enumerate(nets, start=1):
        t0 = time.time()
        rows = pl[pl["network_id"] == net].copy()
        panel = read_temperature_panel(str(panel_path(net)))
        losses = fitting_period_empirical_losses(
            net, panel, rows, xgboost_parameters=params
        )
        parts.append(losses)
        log(f"  empirical losses {i}/{len(nets)} {net} ({len(losses)} rows, {time.time() - t0:.1f}s)")
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(cache, index=False)
    log(f"second-panel fitting losses: {len(out)} rows, {out.network_id.nunique()} networks")
    return out


# ---------------------------------------------------------------------------
# stage 2: rungs 4-6 predictions from fitting losses
# ---------------------------------------------------------------------------

def rungs_4_5_6(losses: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    """r4 network mean, r5 network x gap, r6 station x gap (fallback chain)."""
    out = cells[["network_id", "station_id", "gap_length"]].copy()
    net_mean = losses.groupby("network_id")["mae_deg_c"].mean()
    net_gap = losses.groupby(["network_id", "gap_length"])["mae_deg_c"].mean()
    sta_gap = losses.groupby(["station_id", "gap_length"])["mae_deg_c"].mean()
    global_mean = float(losses["mae_deg_c"].mean())
    r4 = out["network_id"].map(net_mean)
    r5 = out.apply(
        lambda r: net_gap.get((r["network_id"], int(r["gap_length"])), np.nan), axis=1
    )
    r6 = out.apply(
        lambda r: sta_gap.get((r["station_id"], int(r["gap_length"])), np.nan), axis=1
    )
    out["r4_network_mean"] = r4
    out["r5_network_x_horizon"] = r5.fillna(r4)
    out["r6_station_x_horizon"] = r6.fillna(r5).fillna(r4)
    out["r4_network_mean"] = out["r4_network_mean"].fillna(global_mean)
    out["r5_network_x_horizon"] = out["r5_network_x_horizon"].fillna(global_mean)
    out["r6_station_x_horizon"] = out["r6_station_x_horizon"].fillna(global_mean)
    return out


# ---------------------------------------------------------------------------
# stage 3: simple route-A features + coefficients
# ---------------------------------------------------------------------------

def compute_simple_features(units: pd.DataFrame, label: str) -> pd.DataFrame:
    cache = INTER / f"simple_features_{label}.csv"
    if cache.is_file():
        log(f"loading cached simple features ({label})")
        return pd.read_csv(cache, dtype={"network_id": str, "station_id": str})
    parts = []
    nets = sorted(units["network_id"].unique())
    for i, net in enumerate(nets, start=1):
        t0 = time.time()
        sub = units[units["network_id"] == net]
        stations = tuple(sorted(sub["station_id"].astype(str).unique()))
        gaps = sorted(int(g) for g in sub["gap_length"].unique())
        panel = read_temperature_panel(str(panel_path(net)))
        feat = simple_predictors(net, panel, gaps=gaps, target_stations=stations)
        parts.append(feat)
        log(f"  simple features {label} {i}/{len(nets)} {net} ({time.time() - t0:.1f}s)")
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(cache, index=False)
    return out


def fit_route_a_coeffs(frame: pd.DataFrame, outcome_col: str = "observed_recovery_loss"):
    """Equal-network-weighted OLS (route-A convention)."""
    counts = frame.groupby("network_id")["network_id"].transform("size")
    weights = 1.0 / counts.to_numpy(dtype=float)
    design = np.column_stack(
        [np.ones(len(frame)), frame[SIMPLE_COLS].to_numpy(dtype=float)]
    )
    root_weight = np.sqrt(weights)
    coef = np.linalg.lstsq(
        design * root_weight[:, None],
        frame[outcome_col].to_numpy(dtype=float) * root_weight,
        rcond=None,
    )[0]
    return float(coef[0]), tuple(float(c) for c in coef[1:])


def apply_coeffs(frame: pd.DataFrame, intercept: float, coefs) -> np.ndarray:
    return intercept + frame[SIMPLE_COLS].to_numpy(dtype=float) @ np.asarray(coefs)


# ---------------------------------------------------------------------------
# stage 4: rungs 1-3 from fitting-period losses
# ---------------------------------------------------------------------------

def per_gap_predictions(fit: pd.DataFrame, gaps: list[int]) -> dict:
    means = fit.groupby("gap_length")["mae_deg_c"].mean().to_dict()
    gs = sorted(means)
    out = {}
    for g in gaps:
        if g in means:
            out[g] = means[g]
            continue
        if g < gs[-1]:
            hi = [x for x in gs if x > g][0]
            lo = [x for x in gs if x < g][-1]
            lg = np.log
            v = means[lo] + (means[hi] - means[lo]) * (lg(g) - lg(lo)) / (lg(hi) - lg(lo))
            out[g] = float(v)
        else:
            lo, hi = gs[-2], gs[-1]
            lg = np.log
            slope = (means[hi] - means[lo]) / (lg(hi) - lg(lo))
            out[g] = float(max(0.0, means[hi] + slope * (lg(g) - lg(hi))))
    return out


def rungs_1_2(fit: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    out = cells[["network_id", "station_id", "gap_length"]].copy()
    out["r1_global_mean"] = float(fit["mae_deg_c"].mean())
    gaps = sorted(int(g) for g in cells["gap_length"].unique())
    gp = per_gap_predictions(fit, gaps)
    out["r2_gap_only"] = out["gap_length"].astype(int).map(gp)
    return out


# ---------------------------------------------------------------------------
# stage 5: rung 7 frozen empirical
# ---------------------------------------------------------------------------

def rung_7(second: pd.DataFrame, first: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = second[["network_id", "station_id", "gap_length"]].copy()
    s["r7_empirical_curve"] = second["empirical_transfer_prediction"]
    f = first[["network_id", "station_id", "gap_length"]].copy()
    f["r7_empirical_curve"] = first["old_empirical_prediction"]
    return s, f


# ---------------------------------------------------------------------------
# stage 6: rung 9 (NA on both panels; dev sanity)
# ---------------------------------------------------------------------------

def rung_9_dev_sanity() -> dict:
    dev = pd.read_csv(DEV_OUTCOMES, dtype={"network_id": str, "station_id": str})
    y = dev["observed_recovery_loss"].to_numpy(dtype=float)
    p = dev["predicted_conditional_risk"].to_numpy(dtype=float)
    return metrics_row(y, p, dev["network_id"].to_numpy(dtype=str), "dev_1260_operator")


# ---------------------------------------------------------------------------
# stage 7: rung 10 blocked-CV per-gap means (route-A LONO)
# ---------------------------------------------------------------------------

def rung_10_means() -> dict:
    cache = INTER / "lono_conf_predictions.csv"
    if not cache.is_file():
        dev = pd.read_csv(DEV_OUTCOMES, dtype={"network_id": str, "station_id": str})
        conf = pd.read_csv(ROUTE_A_PRED, dtype={"network_id": str, "station_id": str})
        rows = []
        nets = sorted(conf["network_id"].unique())
        for i, net in enumerate(nets, start=1):
            train = pd.concat([dev, conf[conf["network_id"] != net]], ignore_index=True)
            intercept, coefs = fit_route_a_coeffs(train)
            pred = apply_coeffs(conf[conf["network_id"] == net], intercept, coefs)
            rows.append(
                pd.DataFrame(
                    {
                        "network_id": net,
                        "station_id": conf[conf["network_id"] == net]["station_id"],
                        "gap_length": conf[conf["network_id"] == net]["gap_length"],
                        "lono_pred": pred,
                    }
                )
            )
            if i % 10 == 0:
                log(f"  LONO conf refits {i}/{len(nets)}")
        lono = pd.concat(rows, ignore_index=True)
        lono.to_csv(cache, index=False)
    else:
        lono = pd.read_csv(cache, dtype={"network_id": str, "station_id": str})
    dev = pd.read_csv(DEV_OUTCOMES, dtype={"network_id": str, "station_id": str})
    nested = pd.read_csv(NESTED_LONO, dtype={"network_id": str, "station_id": str})
    dev_lono = dev.merge(
        nested[["network_id", "station_id", "gap_length", "simple_prediction"]],
        on=["network_id", "station_id", "gap_length"],
    )[["network_id", "station_id", "gap_length", "simple_prediction"]]
    dev_lono = dev_lono.rename(columns={"simple_prediction": "lono_pred"})
    all_lono = pd.concat([dev_lono, lono], ignore_index=True)
    per_gap = all_lono.groupby("gap_length")["lono_pred"].mean().to_dict()
    per_gap = {int(k): float(v) for k, v in per_gap.items()}
    overall = float(all_lono["lono_pred"].mean())
    return {"per_gap": per_gap, "overall": overall}


# ---------------------------------------------------------------------------
# stage 8: rung 11 surface (stored columns, no refit)
# ---------------------------------------------------------------------------

def rung_11(second: pd.DataFrame, first: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = second[["network_id", "station_id", "gap_length"]].copy()
    s["r11_risk_surface"] = second["surface_prediction_mae"]
    f = first[["network_id", "station_id", "gap_length"]].copy()
    f["r11_risk_surface"] = first["surface_prediction_mae"]
    return s, f


# ---------------------------------------------------------------------------
# stage 9: rung 12 meta-model (stack simple + surface, fitting-period OLS)
# ---------------------------------------------------------------------------

def surface_predict(gap, fourier, cov, beta, mean, sd, med):
    """Fixed-effects-only pooled-surface prediction: expm1(X beta).

    fourier: (n, 4) per-cell mean sin1/cos1/sin2/cos2 columns (t04 convention).
    cov: (n, 7) raw covariates; NaN imputed with pooled median, then z-scored.
    """
    B = b_spline_basis(np.log(np.asarray(gap, dtype=float)))
    F = np.asarray(fourier, dtype=float)
    C = np.asarray(cov, dtype=float)
    C = np.where(np.isnan(C), np.asarray(med, dtype=float), C)
    C = (C - np.asarray(mean, dtype=float)) / np.asarray(sd, dtype=float)
    X = np.column_stack([B, F, C])
    return np.expm1(X @ np.asarray(beta, dtype=float))


def acf_gap_for_stations(frame: pd.DataFrame, source: str, years_map: dict) -> dict:
    """per (network, station, gap) acf at lag=gap from daily panel (t04 code path)."""
    out = {}
    nets = sorted(frame["network_id"].unique())
    for k, net in enumerate(nets, start=1):
        stas = set(frame[frame["network_id"] == net]["station_id"])
        panel = panel_for_network(net, source, stas)
        for sta in stas:
            if sta not in panel.columns:
                continue
            years = years_map.get((str(net), str(sta)), set())
            s = panel[sta]
            if years:
                s = s.loc[np.isin(s.index.year, list(years))]
            for g in sorted(
                int(x) for x in frame[(frame["network_id"] == net) & (frame["station_id"] == sta)]["gap_length"].unique()
            ):
                out[(str(net), str(sta), int(g))] = acf_at_lag(s, int(g))
        if (k + 1) % 15 == 0:
            log(f"  acf_gap {source} {k + 1}/{len(nets)}")
    return out


def cell_doy_means(placements: pd.DataFrame) -> pd.DataFrame:
    p = placements.copy()
    p["station_id"] = p["station_id"].astype(str)
    f = fourier_design(pd.to_datetime(p["gap_start"]).dt.dayofyear.to_numpy())
    p[["sin1", "cos1", "sin2", "cos2"]] = f
    return (
        p.groupby(["network_id", "station_id", "gap_length"])[["sin1", "cos1", "sin2", "cos2"]]
        .mean()
        .reset_index()
    )


def build_meta_components() -> dict:
    """Returns dict with surface predictions for fitting cells, second panel,
    first panel, plus validation on stored second-panel log1p."""
    summary = json.loads(SURFACE_SUMMARY.read_text(encoding="utf-8"))
    fe = summary["fixed_effects"]
    beta = [fe[k] for k in
            ["bs_0", "bs_1", "bs_2", "bs_3", "sin1", "cos1", "sin2", "cos2"] + COV_COLS]
    cs = summary["covariate_scaling_pooled"]
    mean = np.array([cs[c]["mean"] for c in COV_COLS])
    sd = np.array([cs[c]["sd"] for c in COV_COLS])
    covs = pd.read_csv(SURFACE_COV, dtype={"network_id": str, "station_id": str})

    dev_fl = pd.read_csv(DEV_FL, dtype={"network_id": str, "station_id": str})
    conf_fl = pd.read_csv(CONF_FL, dtype={"network_id": str, "station_id": str})
    dev_pred = pd.read_csv(DEV_PRED, dtype={"network_id": str, "station_id": str})
    conf_pred = pd.read_csv(CONF_PRED, dtype={"network_id": str, "station_id": str})

    dev_donors, dev_years = donor_and_years(dev_pred)
    conf_donors, conf_years = donor_and_years(conf_pred)

    # pooled median imputation (reproduces t04 fit_scaler on pooled fit rows)
    fit_all = pd.concat([dev_fl, conf_fl], ignore_index=True)
    cov_all = fit_all.merge(covs, on=["network_id", "station_id"], how="left")
    med = cov_all[COV_COLS].median().to_dict()

    cache_acf = INTER / "acf_gap_dev_conf.json"
    dev_out_a = pd.read_csv(DEV_OUTCOMES, dtype={"network_id": str, "station_id": str})
    route_a_c = pd.read_csv(ROUTE_A_PRED, dtype={"network_id": str, "station_id": str})
    acf_frame_dev = dev_out_a[["network_id", "station_id", "gap_length"]]
    acf_frame_conf = route_a_c[["network_id", "station_id", "gap_length"]]
    if not cache_acf.is_file():
        log("computing acf_gap for dev stations ...")
        dev_acf = acf_gap_for_stations(acf_frame_dev, "dev", dev_years)
        log("computing acf_gap for conf stations ...")
        conf_acf = acf_gap_for_stations(acf_frame_conf, "conf", conf_years)
        cache = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in {**dev_acf, **conf_acf}.items()}
        cache_acf.write_text(json.dumps(cache), encoding="utf-8")
    else:
        raw = json.loads(cache_acf.read_text(encoding="utf-8"))
        cache = {(k.split("|")[0], k.split("|")[1], int(k.split("|")[2])): v
                 for k, v in raw.items()}

    def surface_on_cells(cells: pd.DataFrame, acf_map: dict) -> np.ndarray:
        merged = cells.merge(covs, on=["network_id", "station_id"], how="left")
        acf = np.array([
            acf_map.get((str(r.network_id), str(r.station_id), int(r.gap_length)), np.nan)
            for r in merged.itertuples()
        ])
        C = merged[COV_COLS].copy()
        C["acf_gap"] = acf
        return surface_predict(
            merged["gap_length"].to_numpy(dtype=float),
            merged[["sin1", "cos1", "sin2", "cos2"]].to_numpy(dtype=float),
            C[COV_COLS].to_numpy(dtype=float),
            beta, mean, sd, [med[c] for c in COV_COLS],
        )

    # validation: second-panel stored cells (use stored per-cell columns)
    sec = pd.read_csv(SURFACE_SECOND, dtype={"network_id": str, "station_id": str})
    B = b_spline_basis(np.log(sec["gap_length"].to_numpy(dtype=float)))
    F = sec[["sin1", "cos1", "sin2", "cos2"]].to_numpy(dtype=float)
    C = sec[COV_COLS].to_numpy(dtype=float)
    C = np.where(np.isnan(C), np.asarray([med[c] for c in COV_COLS]), C)
    C = (C - mean) / sd
    X = np.column_stack([B, F, C])
    mu_val = X @ np.asarray(beta, dtype=float)
    val_max = float(np.max(np.abs(mu_val - sec["surface_prediction_log1p"].to_numpy(dtype=float))))
    log(f"surface reconstruction validation (second panel): max|mu - stored log1p| = {val_max:.3e}")

    def fourier_from_sincos(sin1, cos1) -> np.ndarray:
        s = np.asarray(sin1, dtype=float)
        c = np.asarray(cos1, dtype=float)
        return np.column_stack([s, c, 2.0 * s * c, c ** 2 - s ** 2])

    # meta regression cells = route-A cells (recovery-loss scale, 2,700 cells);
    # surface features = pooled surface at those cells (fixed effects only),
    # DOY from the stored per-cell placement_season_sin/cos (2nd harmonic derived)
    dev_out = pd.read_csv(DEV_OUTCOMES, dtype={"network_id": str, "station_id": str})
    route_a = pd.read_csv(ROUTE_A_PRED, dtype={"network_id": str, "station_id": str})
    dev_surf = surface_on_cells(
        dev_out.rename(columns={"placement_season_sin": "sin1",
                                "placement_season_cos": "cos1"})
        .assign(sin2=lambda d: fourier_from_sincos(d["sin1"], d["cos1"])[:, 2],
                cos2=lambda d: fourier_from_sincos(d["sin1"], d["cos1"])[:, 3]),
        cache,
    )
    conf_surf = surface_on_cells(
        route_a.rename(columns={"placement_season_sin": "sin1",
                                "placement_season_cos": "cos1"})
        .assign(sin2=lambda d: fourier_from_sincos(d["sin1"], d["cos1"])[:, 2],
                cos2=lambda d: fourier_from_sincos(d["sin1"], d["cos1"])[:, 3]),
        cache,
    )
    log(f"surface predictions: dev meta cells {len(dev_surf)}, conf meta cells {len(conf_surf)}")

    # first-panel cells for meta application (pooled surface, consistent)
    conf_ev = pd.read_csv(CONF_PRED, dtype={"network_id": str, "station_id": str})
    f1_dm = cell_doy_means(conf_ev)
    f1_cells = (
        pd.read_csv(SURFACE_FIRST, dtype={"network_id": str, "station_id": str})[
            ["network_id", "station_id", "gap_length"]
        ]
        .merge(f1_dm, on=["network_id", "station_id", "gap_length"], how="left")
    )
    f1_cells[["sin1", "cos1", "sin2", "cos2"]] = f1_cells[
        ["sin1", "cos1", "sin2", "cos2"]
    ].fillna(0.0)
    f1_surf = surface_on_cells(f1_cells, cache)
    log(f"surface predictions: first-panel {len(f1_surf)} cells")

    return {
        "dev_surf": dev_surf, "conf_surf": conf_surf, "f1_surf": f1_surf,
        "dev_out": dev_out, "route_a": route_a,
        "beta": beta, "mean": mean, "sd": sd, "med": med,
        "val_max": val_max, "sec_stored_mu": mu_val,
    }


# ---------------------------------------------------------------------------
# stage 10-14: assemble, evaluate, bootstrap, residualization, outputs
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- load frozen panels -------------------------------------------------
    second = pd.read_csv(SECOND_PRED, dtype={"network_id": str, "station_id": str})
    first = pd.read_csv(SURFACE_FIRST, dtype={"network_id": str, "station_id": str})
    pl2 = pd.read_csv(SECOND_PLACEMENTS, dtype={"network_id": str, "station_id": str})
    conf_pred = pd.read_csv(CONF_PRED, dtype={"network_id": str, "station_id": str})
    dev_out = pd.read_csv(DEV_OUTCOMES, dtype={"network_id": str, "station_id": str})
    dev_fl = pd.read_csv(DEV_FL, dtype={"network_id": str, "station_id": str})
    conf_fl = pd.read_csv(CONF_FL, dtype={"network_id": str, "station_id": str})
    log(f"second panel: {len(second)} units / {second.network_id.nunique()} networks; "
        f"first panel: {len(first)} cells / {first.network_id.nunique()} networks")

    # ---- stage 1: second-panel fitting losses --------------------------------
    losses2 = load_second_fitting_losses()
    frozen_fb = second[second["gap_length"] == 14][["network_id", "empirical_transfer_prediction"]]
    mine = losses2.groupby("network_id")["mae_deg_c"].mean().rename("mine")
    chk = frozen_fb.merge(mine, on="network_id")
    max_diff = float((chk["empirical_transfer_prediction"] - chk["mine"]).abs().max())
    log(f"validation rung4 vs frozen fallback: max |diff| = {max_diff:.3e} over {len(chk)} networks")
    if max_diff > 1e-9:
        log("WARNING: rung-4 reconstruction deviates from frozen fallback")

    # ---- rungs 4-6 (second panel; first panel from conf fit losses) -----------
    r456_2 = rungs_4_5_6(losses2, second)
    r456_1 = rungs_4_5_6(conf_fl, first)

    # ---- rungs 1-3 --------------------------------------------------------------
    fit2 = pd.concat([dev_fl, conf_fl], ignore_index=True)
    fit1 = dev_fl.copy()
    r123_2 = rungs_1_2(fit2, second)
    r123_1 = rungs_1_2(fit1, first)
    # r3: gap + season, unweighted OLS on fitting rows; cell-level mean Fourier cols
    dm2 = cell_doy_means(pl2)
    dm1 = cell_doy_means(conf_pred)

    def r3_predict(fit, cells, cell_fourier):
        F = fourier_design(pd.to_datetime(fit["gap_start"]).dt.dayofyear.to_numpy())
        X = np.column_stack([
            np.ones(len(fit)), np.log(fit["gap_length"].to_numpy(dtype=float)), F,
        ])
        beta3 = np.linalg.lstsq(X, fit["mae_deg_c"].to_numpy(dtype=float), rcond=None)[0]
        m = cells.merge(cell_fourier, on=["network_id", "station_id", "gap_length"], how="left")
        cf = m[["sin1", "cos1", "sin2", "cos2"]].fillna(0.0).to_numpy(dtype=float)
        Xc = np.column_stack([
            np.ones(len(cells)), np.log(cells["gap_length"].to_numpy(dtype=float)), cf,
        ])
        return Xc @ beta3

    r123_2["r3_gap_season"] = r3_predict(fit2, second, dm2)
    r123_1["r3_gap_season"] = r3_predict(fit1, first, dm1)
    log("rungs 1-3 built")

    # ---- rung 7 ----------------------------------------------------------------
    r7_2 = second[["network_id", "station_id", "gap_length"]].copy()
    r7_2["r7_empirical_curve"] = second["empirical_transfer_prediction"]
    r7_1 = first[["network_id", "station_id", "gap_length"]].copy()
    r7_1["r7_empirical_curve"] = first["old_empirical_prediction"]

    # ---- rung 8: simple descriptors --------------------------------------------
    units2 = second[["network_id", "station_id", "gap_length"]]
    units1 = first[["network_id", "station_id", "gap_length"]]
    feat2 = compute_simple_features(units2, "second")
    feat1 = compute_simple_features(units1, "first")
    archived2 = pd.read_csv(SECOND_SIMPLE, dtype={"network_id": str, "station_id": str})
    archived1 = pd.read_csv(ROUTE_A_PRED, dtype={"network_id": str, "station_id": str})
    arch_cols = ["acf_only", "donor_r2_only", "additive_d_over_4_heuristic",
                 "nearest_donor_correlation"]
    for label, feat, arch in [("second", feat2, archived2), ("first", feat1, archived1)]:
        m = feat.merge(arch[["network_id", "station_id", "gap_length"] + arch_cols],
                       on=["network_id", "station_id", "gap_length"], suffixes=("", "_arch"))
        diffs = [float((m[c] - m[c + "_arch"]).abs().max()) for c in arch_cols]
        log(f"feature validation {label}: max abs diffs vs archived = {diffs}")
    # fit coefficients
    dev_co, dev_cfs = fit_route_a_coeffs(dev_out)
    conf_cells_fit = pd.read_csv(ROUTE_A_PRED, dtype={"network_id": str, "station_id": str})
    fitper_frame = pd.concat([dev_out, conf_cells_fit], ignore_index=True)
    fp_co, fp_cfs = fit_route_a_coeffs(fitper_frame)
    log(f"dev-only coefs: {dev_co} {dev_cfs}")
    log(f"fit-period coefs: {fp_co} {fp_cfs}")
    ab = json.loads(AGENTB_COEF.read_text(encoding="utf-8"))
    dev_diff = max(abs(dev_co - ab["dev_only"]["intercept"]),
                   max(abs(np.asarray(dev_cfs) - np.asarray(ab["dev_only"]["coefficients"]))))
    fp_diff = max(abs(fp_co - ab["fitting_period_dev_plus_first"]["intercept"]),
                  max(abs(np.asarray(fp_cfs) - np.asarray(ab["fitting_period_dev_plus_first"]["coefficients"]))))
    log(f"coefficient validation vs agent_b: dev_only max diff {dev_diff:.3e}, "
        f"fit_period max diff {fp_diff:.3e}")
    # predictions
    f2 = second.merge(feat2, on=["network_id", "station_id", "gap_length"], how="left")
    f1 = first.merge(feat1, on=["network_id", "station_id", "gap_length"], how="left")
    r8_2 = second[["network_id", "station_id", "gap_length"]].copy()
    r8_2["r8_simple_routeA"] = apply_coeffs(f2, fp_co, fp_cfs)
    r8_2["r8_simple_devonly"] = apply_coeffs(f2, dev_co, dev_cfs)
    r8_1 = first[["network_id", "station_id", "gap_length"]].copy()
    r8_1["r8_simple_routeA"] = apply_coeffs(f1, dev_co, dev_cfs)

    # ---- rung 9 -----------------------------------------------------------------
    op_dev = rung_9_dev_sanity()

    # ---- rung 10 ------------------------------------------------------------------
    r10m = rung_10_means()
    r10_2 = second[["network_id", "station_id", "gap_length"]].copy()
    r10_2["r10_blocked_cv_mean"] = (
        r10_2["gap_length"].astype(int).map(r10m["per_gap"]).fillna(r10m["overall"])
    )
    r10_1 = first[["network_id", "station_id", "gap_length"]].copy()
    r10_1["r10_blocked_cv_mean"] = (
        r10_1["gap_length"].astype(int).map(r10m["per_gap"]).fillna(r10m["overall"])
    )

    # ---- rung 11 -------------------------------------------------------------------
    surf2 = pd.read_csv(SURFACE_SECOND, dtype={"network_id": str, "station_id": str})
    r11_2 = second[["network_id", "station_id", "gap_length"]].copy()
    r11_2["r11_risk_surface"] = surf2["surface_prediction_mae"]
    r11_1 = first[["network_id", "station_id", "gap_length"]].copy()
    r11_1["r11_risk_surface"] = first["surface_prediction_mae"]

    # ---- rung 12: meta-model ----------------------------------------------------------
    mc = build_meta_components()
    log(f"meta components built (surface validation max diff {mc['val_max']:.3e})")
    dev_meta_frame = dev_out.copy()
    dev_meta_frame["simple_pred"] = apply_coeffs(dev_out, fp_co, fp_cfs)
    dev_meta_frame["surface_pred"] = mc["dev_surf"]
    conf_meta_frame = conf_cells_fit.copy()
    conf_meta_frame["simple_pred"] = apply_coeffs(conf_cells_fit, fp_co, fp_cfs)
    conf_meta_frame["surface_pred"] = mc["conf_surf"]

    def meta_ols(frame: pd.DataFrame):
        counts = frame.groupby("network_id")["network_id"].transform("size")
        w = np.sqrt(1.0 / counts.to_numpy(dtype=float))
        X = np.column_stack([np.ones(len(frame)),
                             frame["simple_pred"].to_numpy(dtype=float),
                             frame["surface_pred"].to_numpy(dtype=float)])
        y = frame["observed_recovery_loss"].to_numpy(dtype=float)
        return np.linalg.lstsq(X * w[:, None], y * w, rcond=None)[0]

    meta2_beta = meta_ols(pd.concat([dev_meta_frame, conf_meta_frame], ignore_index=True))
    meta1_beta = meta_ols(dev_meta_frame)
    log(f"meta2 coefficients (int, simple, surface): {meta2_beta}")
    log(f"meta1 coefficients (int, simple, surface): {meta1_beta}")

    # second panel application: surface = stored-mu reconstruction (same transform)
    surf2_meta = np.expm1(mc["sec_stored_mu"])
    Xm2 = np.column_stack([np.ones(len(second)),
                           r8_2["r8_simple_routeA"].to_numpy(dtype=float), surf2_meta])
    r12_2 = second[["network_id", "station_id", "gap_length"]].copy()
    r12_2["r12_meta_stack"] = np.maximum(0.0, Xm2 @ meta2_beta)

    # first panel application: pooled-surface reconstruction on first-panel cells
    Xm1 = np.column_stack([np.ones(len(first)),
                           r8_1["r8_simple_routeA"].to_numpy(dtype=float), mc["f1_surf"]])
    r12_1 = first[["network_id", "station_id", "gap_length"]].copy()
    r12_1["r12_meta_stack"] = np.maximum(0.0, Xm1 @ meta1_beta)

    # LONO-stack sensitivity (second panel): regression on LONO simple preds
    lono_dev = pd.read_csv(NESTED_LONO, dtype={"network_id": str, "station_id": str})
    dev_lono_frame = dev_meta_frame.drop(columns=["simple_pred"]).merge(
        lono_dev[["network_id", "station_id", "gap_length", "simple_prediction"]],
        on=["network_id", "station_id", "gap_length"],
    ).rename(columns={"simple_prediction": "simple_pred"})
    conf_lono = pd.read_csv(INTER / "lono_conf_predictions.csv",
                            dtype={"network_id": str, "station_id": str})
    conf_lono_frame = conf_meta_frame.drop(columns=["simple_pred"]).merge(
        conf_lono, on=["network_id", "station_id", "gap_length"]
    ).rename(columns={"lono_pred": "simple_pred"})
    meta2_lono_beta = meta_ols(pd.concat([dev_lono_frame, conf_lono_frame], ignore_index=True))
    r12_2["r12_meta_stack_lono"] = np.maximum(0.0, Xm2 @ meta2_lono_beta)
    log(f"meta2 LONO-stack coefficients: {meta2_lono_beta}")

    # ---- assemble prediction frames -----------------------------------------------
    pred2 = second[["network_id", "station_id", "gap_length", "observed_recovery_loss"]].copy()
    for r in [r123_2, r456_2, r7_2, r8_2, r10_2, r11_2, r12_2]:
        pred2 = pred2.merge(r, on=["network_id", "station_id", "gap_length"], how="left")
    pred1 = first[["network_id", "station_id", "gap_length", "observed_recovery_loss",
                   "old_source_cell"]].copy()
    for r in [r123_1, r456_1, r7_1, r8_1, r10_1, r11_1, r12_1]:
        pred1 = pred1.merge(r, on=["network_id", "station_id", "gap_length"], how="left")
    for c in RUNG_NAMES:
        if c not in pred2.columns:
            pred2[c] = np.nan
        if c not in pred1.columns:
            pred1[c] = np.nan
    pred2["r9_covariance_operator"] = np.nan
    pred1["r9_covariance_operator"] = np.nan
    pred2.to_csv(OUT / "predictions_second_panel.csv", index=False)
    pred1.to_csv(OUT / "predictions_first_panel.csv", index=False)
    log("prediction frames written")

    # ---- metrics tables ------------------------------------------------------------
    def subset_masks(pred: pd.DataFrame, panel: str) -> dict:
        if panel == "second":
            return {"874_direct": pred["gap_length"].isin(DIRECT_GAPS),
                    "1446_full": np.ones(len(pred), dtype=bool)}
        supported = np.zeros(len(pred), dtype=bool)
        if "old_source_cell" in pred.columns:
            supported = pred["gap_length"].isin(DIRECT_GAPS) & pred["old_source_cell"].eq("other")
        return {"858_direct": pred["gap_length"].isin(DIRECT_GAPS),
                "780_supported": supported,
                "1440_full": np.ones(len(pred), dtype=bool)}

    def subset_metrics(pred: pd.DataFrame, panel: str) -> pd.DataFrame:
        rows = []
        for sname, mask in subset_masks(pred, panel).items():
            sub = pred[mask]
            for rung in RUNG_NAMES:
                p = sub[rung].to_numpy(dtype=float)
                if np.isnan(p).all():
                    continue
                y = sub["observed_recovery_loss"].to_numpy(dtype=float)
                rows.append(metrics_row(y, p, sub["network_id"].to_numpy(dtype=str),
                                        f"{panel}_{sname}_{rung}"))
            if "r12_meta_stack_lono" in pred.columns:
                p = sub["r12_meta_stack_lono"].to_numpy(dtype=float)
                y = sub["observed_recovery_loss"].to_numpy(dtype=float)
                rows.append(metrics_row(y, p, sub["network_id"].to_numpy(dtype=str),
                                        f"{panel}_{sname}_r12_meta_stack_lono"))
        return pd.DataFrame(rows)

    m2 = subset_metrics(pred2, "second")
    m1 = subset_metrics(pred1, "first")
    m2.to_csv(OUT / "ladder_metrics_second_panel.csv", index=False)
    m1.to_csv(OUT / "ladder_metrics_first_panel.csv", index=False)
    log("ladder metrics written")

    # ---- per-horizon network spearman ----------------------------------------------
    def per_horizon(pred: pd.DataFrame, panel: str) -> pd.DataFrame:
        rows = []
        for g in GAP_LENGTHS:
            sub = pred[pred["gap_length"] == g]
            for rung in RUNG_NAMES:
                p = sub[rung].to_numpy(dtype=float)
                if np.isnan(p).all():
                    continue
                y = sub["observed_recovery_loss"].to_numpy(dtype=float)
                nm = pd.DataFrame({"y": y, "p": p,
                                   "net": sub["network_id"].to_numpy(dtype=str)}).groupby("net").mean()
                rows.append({"panel": panel, "horizon": g, "n_units": len(sub),
                             "n_networks": int(sub["network_id"].nunique()), "rung": rung,
                             "network_spearman": safe_spearman(nm["y"], nm["p"]),
                             "pooled_spearman": safe_spearman(y, p)})
        return pd.DataFrame(rows)

    ph2 = per_horizon(pred2, "second")
    ph1 = per_horizon(pred1, "first")
    pd.concat([ph2, ph1], ignore_index=True).to_csv(
        OUT / "per_horizon_network_spearman.csv", index=False)

    # ---- residualized pooled spearman ------------------------------------------------
    def resid_table(pred: pd.DataFrame, panel: str) -> pd.DataFrame:
        rows = []
        for sname, mask in subset_masks(pred, panel).items():
            sub = pred[mask]
            for rung in RUNG_NAMES:
                p = sub[rung].to_numpy(dtype=float)
                if np.isnan(p).all():
                    continue
                rows.append({"panel": panel, "subset": sname, "rung": rung,
                             "residualized_pooled_spearman": residualized_pooled_spearman(
                                 sub["observed_recovery_loss"].to_numpy(dtype=float), p,
                                 sub["network_id"].to_numpy(dtype=str))})
        return pd.DataFrame(rows)

    pd.concat([resid_table(pred2, "second"), resid_table(pred1, "first")],
              ignore_index=True).to_csv(OUT / "residualized_pooled_spearman.csv", index=False)

    # ---- strongest non-proposed baseline ------------------------------------------------
    best = {}
    for panel, m in [("second", m2), ("first", m1)]:
        for sname, _ in subset_masks(pred2 if panel == "second" else pred1, panel).items():
            mm = m[(m["label"].str.contains(f"_{sname}_")) &
                   (m["label"].str.contains("|".join(NONPROPOSED), regex=True))]
            mm = mm.dropna(subset=["network_spearman"])
            if len(mm):
                winner = mm.loc[mm["network_spearman"].idxmax(), "label"]
                best[(panel, sname)] = next(r for r in RUNG_NAMES if winner.endswith(r))
    log(f"strongest non-proposed baseline by network rho: {best}")

    # ---- paired bootstrap ---------------------------------------------------------------
    rng = np.random.default_rng(SEED)

    def paired_delta(pred: pd.DataFrame, subset_mask, ycol, a, b, net, n_draws):
        sub = pred[subset_mask].reset_index(drop=True)
        y = sub[ycol].to_numpy(dtype=float)
        pa = sub[a].to_numpy(dtype=float)
        pb = sub[b].to_numpy(dtype=float)
        nets = sub[net].to_numpy(dtype=str)
        uniq = np.unique(nets)
        masks = {n: nets == n for n in uniq}
        by_a = {n: pa[masks[n]] for n in uniq}
        by_b = {n: pb[masks[n]] for n in uniq}
        by_y = {n: y[masks[n]] for n in uniq}
        d_net, d_pool, n_skip = [], [], 0
        for _ in range(n_draws):
            draw = rng.choice(uniq, size=len(uniq), replace=True)
            ya = np.concatenate([by_y[n] for n in draw])
            pa_d = np.concatenate([by_a[n] for n in draw])
            pb_d = np.concatenate([by_b[n] for n in draw])
            ma = np.array([by_y[n].mean() for n in draw])
            mpa = np.array([by_a[n].mean() for n in draw])
            mpb = np.array([by_b[n].mean() for n in draw])
            if np.nanstd(ma) == 0 or np.nanstd(mpa) == 0 or np.nanstd(mpb) == 0:
                n_skip += 1
                continue
            d_net.append(spearmanr(ma, mpa).statistic - spearmanr(ma, mpb).statistic)
            d_pool.append(spearmanr(ya, pa_d).statistic - spearmanr(ya, pb_d).statistic)
        d_net = np.asarray(d_net)
        d_pool = np.asarray(d_pool)
        out = {
            "delta_network_mean": float(np.mean(d_net)) if len(d_net) else np.nan,
            "delta_network_lo": float(np.percentile(d_net, 2.5)) if len(d_net) else np.nan,
            "delta_network_hi": float(np.percentile(d_net, 97.5)) if len(d_net) else np.nan,
            "delta_network_p_gt0": float((d_net > 0).mean()) if len(d_net) else np.nan,
            "delta_pooled_mean": float(np.mean(d_pool)) if len(d_pool) else np.nan,
            "delta_pooled_lo": float(np.percentile(d_pool, 2.5)) if len(d_pool) else np.nan,
            "delta_pooled_hi": float(np.percentile(d_pool, 97.5)) if len(d_pool) else np.nan,
            "delta_pooled_p_gt0": float((d_pool > 0).mean()) if len(d_pool) else np.nan,
            "n_draws": len(d_net), "n_skipped": n_skip,
        }
        return out

    def boot_table(pred: pd.DataFrame, panel: str, target_rungs, baseline) -> pd.DataFrame:
        rows = []
        subsets = subset_masks(pred, panel)
        for sname, mask in subsets.items():
            sub = pred[mask]
            for a in target_rungs:
                if a == baseline:
                    continue
                if sub[a].isna().any() or sub[baseline].isna().any():
                    continue
                res = paired_delta(pred, mask, "observed_recovery_loss", a, baseline,
                                   "network_id", N_BOOT)
                rows.append({"panel": panel, "subset": sname, "rung": a,
                             "baseline": baseline, **res})
        return pd.DataFrame(rows)

    # point matrix (network rho, all pairs)
    def point_matrix(pred: pd.DataFrame, panel: str) -> pd.DataFrame:
        rows = []
        subsets = subset_masks(pred, panel)
        for sname, mask in subsets.items():
            sub = pred[mask]
            net = sub["network_id"].to_numpy(dtype=str)
            y = sub["observed_recovery_loss"].to_numpy(dtype=float)
            vals = {}
            for rung in RUNG_NAMES:
                nm = pd.DataFrame({"y": y, "p": sub[rung].to_numpy(dtype=float),
                                   "net": net}).groupby("net").mean()
                vals[rung] = safe_spearman(nm["y"], nm["p"])
            for a in RUNG_NAMES:
                for b in RUNG_NAMES:
                    if a == b or np.isnan(vals[a]) or np.isnan(vals[b]):
                        continue
                    rows.append({"panel": panel, "subset": sname, "rung": a, "vs": b,
                                 "delta_network_rho": vals[a] - vals[b],
                                 "rho_a": vals[a], "rho_b": vals[b]})
        return pd.DataFrame(rows)

    pd.concat([point_matrix(pred2, "second"), point_matrix(pred1, "first")],
              ignore_index=True).to_csv(OUT / "paired_delta_point_matrix.csv", index=False)

    best_second = best.get(("second", "1446_full"), "r6_station_x_horizon")
    best_first = best.get(("first", "1440_full"), "r6_station_x_horizon")
    tb_vs_best_2 = boot_table(pred2, "second", PROPOSED, best_second)
    tb_vs_best_1 = boot_table(pred1, "first", PROPOSED, best_first)
    tb_vs_emp_2 = boot_table(pred2, "second", [r for r in RUNG_NAMES if r != "r7_empirical_curve"],
                             "r7_empirical_curve")
    tb_vs_emp_1 = boot_table(pred1, "first", [r for r in RUNG_NAMES if r != "r7_empirical_curve"],
                             "r7_empirical_curve")
    pd.concat([tb_vs_best_2, tb_vs_best_1], ignore_index=True).to_csv(
        OUT / "paired_delta_vs_strongest_baseline.csv", index=False)
    pd.concat([tb_vs_emp_2, tb_vs_emp_1], ignore_index=True).to_csv(
        OUT / "paired_delta_vs_empirical_curve.csv", index=False)
    log("paired bootstrap tables written")

    # also vs the two likely candidates (station x horizon, simple) for the record
    for cand in ["r6_station_x_horizon", "r8_simple_routeA"]:
        tb2 = boot_table(pred2, "second", PROPOSED, cand)
        tb2.to_csv(OUT / f"paired_delta_vs_{cand}.csv", index=False)

    # ---- within-network beat fractions (headline) -------------------------------------
    def beat_fraction(pred: pd.DataFrame, panel: str, baseline: str) -> pd.DataFrame:
        rows = []
        subsets = subset_masks(pred, panel)
        for sname, mask in subsets.items():
            sub = pred[mask]
            y = sub["observed_recovery_loss"].to_numpy(dtype=float)
            pb = sub[baseline].to_numpy(dtype=float)
            net = sub["network_id"].to_numpy(dtype=str)
            for rung in PROPOSED:
                if pred[rung].isna().all():
                    continue
                pa = sub[rung].to_numpy(dtype=float)
                beats, both, med_delta = [], 0, []
                for n in np.unique(net):
                    m = net == n
                    if m.sum() < 4:
                        continue
                    ra = safe_spearman(y[m], pa[m])
                    rb = safe_spearman(y[m], pb[m])
                    if not (np.isnan(ra) or np.isnan(rb)):
                        both += 1
                        beats.append(ra > rb)
                        med_delta.append(ra - rb)
                rows.append({"panel": panel, "subset": sname, "rung": rung,
                             "baseline": baseline,
                             "networks_both_defined": both,
                             "fraction_rung_beats": (np.mean(beats) if beats else np.nan),
                             "median_within_delta": (np.median(med_delta) if med_delta else np.nan)})
        return pd.DataFrame(rows)

    pd.concat([
        beat_fraction(pred2, "second", best_second),
        beat_fraction(pred1, "first", best_first),
        beat_fraction(pred2, "second", "r7_empirical_curve"),
        beat_fraction(pred1, "first", "r7_empirical_curve"),
    ], ignore_index=True).to_csv(OUT / "within_network_beat_fraction.csv", index=False)

    # ---- cross-checks -------------------------------------------------------------------
    def crosscheck(pred: pd.DataFrame, panel: str) -> pd.DataFrame:
        rows = []
        masks = subset_masks(pred, panel)
        if panel == "second":
            specs = [
                ("empirical_direct_874", "r7_empirical_curve", "874_direct"),
                ("empirical_full_1446", "r7_empirical_curve", "1446_full"),
                ("simple_devonly_full_1446", "r8_simple_devonly", "1446_full"),
                ("simple_fitperiod_full_1446", "r8_simple_routeA", "1446_full"),
                ("surface_full_1446", "r11_risk_surface", "1446_full"),
            ]
        else:
            specs = [
                ("empirical_direct_858", "r7_empirical_curve", "858_direct"),
                ("empirical_supported_780", "r7_empirical_curve", "780_supported"),
                ("empirical_full_1440", "r7_empirical_curve", "1440_full"),
                ("simple_devonly_full_1440", "r8_simple_routeA", "1440_full"),
                ("surface_full_1440", "r11_risk_surface", "1440_full"),
            ]
        for name, col, sname in specs:
            sub = pred[masks[sname]]
            rows.append(metrics_row(sub["observed_recovery_loss"].to_numpy(dtype=float),
                                    sub[col].to_numpy(dtype=float),
                                    sub["network_id"].to_numpy(dtype=str), name))
        return pd.DataFrame(rows)

    pd.concat([crosscheck(pred2, "second"), crosscheck(pred1, "first")],
              ignore_index=True).to_csv(OUT / "crosschecks.csv", index=False)

    # ---- amplitude-normalized MAE ------------------------------------------------------
    # second panel: first 15 networks with an available panel (chmi block in file order)
    sub_nets = []
    for n in sorted(second["network_id"].unique()):
        try:
            panel_path(n)
        except FileNotFoundError:
            continue
        sub_nets.append(n)
        if len(sub_nets) == 15:
            break
    log(f"amplitude-normalization subset (second panel): {len(sub_nets)} networks")
    amp_rows = []
    simple2 = pd.read_csv(SECOND_SIMPLE, dtype={"network_id": str, "station_id": str})
    ty2 = donor_and_years(simple2)[1]
    for n in sub_nets:
        p = read_temperature_panel(str(panel_path(n)))
        for sta in second[second.network_id == n].station_id:
            if sta not in p.columns:
                continue
            years = ty2.get((str(n), str(sta)), set())
            s = p[sta]
            if years:
                s = s.loc[np.isin(s.index.year, list(years))]
            st = series_stats(s)
            amp_rows.append({"network_id": n, "station_id": str(sta),
                             "temp_sd": st["temp_sd"], "temp_iqr": st["temp_iqr"]})
    amp = pd.DataFrame(amp_rows).drop_duplicates(["network_id", "station_id"])
    pred2a = pred2.merge(amp, on=["network_id", "station_id"], how="inner")
    rows = []
    for rung in RUNG_NAMES:
        if pred2a[rung].isna().all():
            continue
        err = (pred2a["observed_recovery_loss"] - pred2a[rung]).to_numpy(dtype=float)
        for scale in ["temp_sd", "temp_iqr"]:
            ne = err / pred2a[scale].to_numpy(dtype=float)
            rows.append({"panel": "second", "subset": f"amp_{len(sub_nets)}nets",
                         "normalization": scale, "rung": rung,
                         "normalized_rmse": float(np.sqrt(np.mean(ne ** 2))),
                         "n_units": len(pred2a)})
    # first panel: climatology_mae normalization (computed from conf panels)
    first_amp_rows = []
    conf_pred_full = pd.read_csv(CONF_PRED, dtype={"network_id": str, "station_id": str})
    ty1 = donor_and_years(conf_pred_full)[1]
    for n in sorted(first["network_id"].unique()):
        try:
            p = read_temperature_panel(str(panel_path(n)))
        except FileNotFoundError:
            continue
        for sta in first[first.network_id == n].station_id:
            if sta not in p.columns:
                continue
            years = ty1.get((str(n), str(sta)), set())
            s = p[sta]
            if years:
                s = s.loc[np.isin(s.index.year, list(years))]
            st = series_stats(s)
            first_amp_rows.append({"network_id": n, "station_id": str(sta),
                                   "climatology_mae": st["climatology_mae"]})
    f1a = pd.DataFrame(first_amp_rows).drop_duplicates(["network_id", "station_id"])
    pred1a = pred1.merge(f1a, on=["network_id", "station_id"], how="inner")
    for rung in RUNG_NAMES:
        if pred1a[rung].isna().all():
            continue
        err = (pred1a["observed_recovery_loss"] - pred1a[rung]).to_numpy(dtype=float)
        ne = err / pred1a["climatology_mae"].to_numpy(dtype=float)
        rows.append({"panel": "first", "subset": f"clim_mae_{len(f1a)}stations",
                     "normalization": "climatology_mae", "rung": rung,
                     "normalized_rmse": float(np.sqrt(np.mean(ne ** 2))),
                     "n_units": len(pred1a)})
    pd.DataFrame(rows).to_csv(OUT / "amplitude_normalized_mae.csv", index=False)
    log("amplitude-normalized MAE written")

    # ---- summary JSON ----------------------------------------------------------------------
    summary = {
        "seed": SEED, "n_boot": N_BOOT,
        "strongest_nonproposed_baseline": {f"{k[0]}_{k[1]}": v for k, v in best.items()},
        "rung4_vs_frozen_fallback_max_abs_diff": max_diff,
        "surface_reconstruction_max_mu_diff": mc["val_max"],
        "meta2_coefficients": list(meta2_beta),
        "meta1_coefficients": list(meta1_beta),
        "meta2_lono_coefficients": list(meta2_lono_beta),
        "dev_only_coefficients": [dev_co] + list(dev_cfs),
        "fit_period_coefficients": [fp_co] + list(fp_cfs),
        "operator_dev_sanity": {k: v for k, v in op_dev.items()
                                if k in ("pooled_spearman", "network_spearman", "r2", "rmse")},
        "runtime_seconds": time.time() - t_start,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    log(f"done in {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
