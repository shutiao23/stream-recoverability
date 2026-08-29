#!/usr/bin/env python3
"""Revision v12, task 04, agent A (adversarial pair).

Continuous support-aware risk surface replacing the network-mean fallback.

Surface: log(1 + MAE) ~ monotone P-spline f(log gap) + cyclic Fourier g(DOY)
+ fitting-time covariates + nested network/station random intercepts.

Fit ONLY on fitting-period artificial-gap placements:
  results/development_v11/reviewer_completion/development_empirical_fit_losses.csv
  results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv

Predict:
  1) second panel 1,446 cells (results/development_v11/second_confirmation/scoring/
     empirical_predictions.csv): durations 14 and 60 interpolated from the
     continuous curve, 365 extrapolated (flagged, widened interval).
  2) first panel 1,440 cells (confirmation_empirical_predictions.csv) as a
     cross-check, refitting the surface on first-panel fit losses only.

Variance components estimated by exact REML for the nested design using
block-Woodbury linear algebra. Monotonicity enforced by a penalty on negative
first differences of the spline coefficients (Eilers 2005 style). Lambda
tuned by fitting on development fit losses and validating on confirmation
fit losses (fixed-effects-only predictions, mimicking the second panel).

Writes only to results/revision_v12/t04_risk_surface/agent_a/.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import BSpline
from scipy.optimize import minimize
from scipy.stats import spearmanr

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/revision_v12/t04_risk_surface/agent_a"
OUT.mkdir(parents=True, exist_ok=True)

RV = ROOT / "results/development_v11/reviewer_completion"
SC = ROOT / "results/development_v11/second_confirmation"

DEV_FL = RV / "development_empirical_fit_losses.csv"
CONF_FL = RV / "confirmation_empirical_fit_losses.csv"
DEV_PRED = RV / "development_empirical_predictions.csv"
CONF_PRED = RV / "confirmation_empirical_predictions.csv"
SECOND_PRED = SC / "scoring/empirical_predictions.csv"
SECOND_PLACEMENTS = SC / "scoring/placement_losses.csv"
SIMPLE = SC / "scoring/simple_predictions.csv"
INVENTORY = ROOT / "results/development_v11/network_inventory.csv"
DEV_CORPUS = (
    ROOT
    / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
)
CONF_DAILY = ROOT / "results/development_v11/confirmation_daily_qc/networks"
SECOND_DAILY = SC / "daily_qc/networks"
CHMI_STATIONS = ROOT / "results/development_v11/chmi_temperature/stations"

KNOTS_LOG = np.log(np.array([7.0, 30.0, 90.0, 180.0]))
# Quadratic B-splines (degree 2) with one interior knot: 4 basis functions.
# Cubic bases need >= 5 functions over the 4 distinct fit durations and are
# rank-deficient in the pooled design; quadratic keeps the spline space full
# rank while remaining a smooth monotonicity-penalized P-spline.
SPLINE_DEGREE = 2
KNOTS = np.concatenate(
    [[KNOTS_LOG[0]] * 3, [KNOTS_LOG[1]], [KNOTS_LOG[-1]] * 3]
)
N_BASIS = len(KNOTS) - (SPLINE_DEGREE + 1)
GAP_MIN_LOG, GAP_MAX_LOG = KNOTS_LOG[0], KNOTS_LOG[-1]
Z90 = 1.6448536269514722

COV_COLS = [
    "temp_sd",
    "temp_iqr",
    "climatology_mae",
    "acf_lag1",
    "acf_gap",
    "daily_gradient",
    "donor_r2",
]


def log1p_expm1(mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    return np.expm1(mu + 0.5 * var)


def b_spline_basis(log_gap: np.ndarray) -> np.ndarray:
    n = len(log_gap)
    B = np.zeros((n, N_BASIS))
    for j in range(N_BASIS):
        c = np.zeros(N_BASIS)
        c[j] = 1.0
        B[:, j] = BSpline(KNOTS, c, SPLINE_DEGREE, extrapolate=True)(log_gap)
    return B


def fourier_design(doy: np.ndarray) -> np.ndarray:
    ph = 2.0 * np.pi * (doy - 1.0) / 365.25
    return np.column_stack([np.sin(ph), np.cos(ph), np.sin(2 * ph), np.cos(2 * ph)])


# --------------------------------------------------------------------------
# Nested variance operator: V = se^2 I + sn^2 Z_n Z_n' + ss^2 Z_s Z_s'
# --------------------------------------------------------------------------


class NestedVC:
    def __init__(self, net: np.ndarray, sta: np.ndarray):
        self.net = net
        self.sta = sta
        self.n_net = int(net.max()) + 1
        self.sta_rows = [
            np.flatnonzero(sta == s) for s in range(int(sta.max()) + 1)
        ]
        self.net_rows = [np.flatnonzero(net == n) for n in range(self.n_net)]
        self.m_s = np.array([len(r) for r in self.sta_rows])
        self.net_sta = [np.unique(sta[rows]) for rows in self.net_rows]
        self.net_of_sta = np.array(
            [self.net[self.sta_rows[s][0]] for s in range(len(self.sta_rows))]
        )

    def solve(self, theta: np.ndarray, v: np.ndarray) -> np.ndarray:
        se2, sn2, ss2 = np.exp(theta)
        out = np.asarray(v, dtype=float).copy()
        a_s = ss2 / (se2 + ss2 * self.m_s)
        for s, rows in enumerate(self.sta_rows):
            out[rows] -= a_s[s] * out[rows].sum()
        out /= se2
        d1 = 1.0 / (se2 + ss2 * self.m_s)
        for n in range(self.n_net):
            rows = self.net_rows[n]
            s_d = out[rows].sum()
            stas = self.net_sta[n]
            s_one = (self.m_s[stas] * d1[stas]).sum()
            kk = sn2 / (1.0 + sn2 * s_one)
            out[rows] -= kk * s_d * d1[self.sta[rows]]
        return out

    def _net_sone_kk(self, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        se2, sn2, ss2 = np.exp(theta)
        d1 = 1.0 / (se2 + ss2 * self.m_s)
        s_one = np.zeros(self.n_net)
        for n in range(self.n_net):
            stas = self.net_sta[n]
            s_one[n] = (self.m_s[stas] * d1[stas]).sum()
        kk = sn2 / (1.0 + sn2 * s_one)
        return s_one, kk

    def logdet(self, theta: np.ndarray) -> float:
        se2, sn2, ss2 = np.exp(theta)
        d1 = 1.0 / (se2 + ss2 * self.m_s)
        ld = 0.0
        for n in range(self.n_net):
            stas = self.net_sta[n]
            ms = self.m_s[stas]
            s_one = (ms * d1[stas]).sum()
            ld += (ms * np.log(se2) + np.log1p(ss2 * ms / se2)).sum()
            ld += np.log1p(sn2 * s_one)
        return ld

    def trace_vinv(self, theta: np.ndarray) -> float:
        se2, sn2, ss2 = np.exp(theta)
        d1 = 1.0 / (se2 + ss2 * self.m_s)
        a_s = ss2 / (se2 + ss2 * self.m_s)
        tr_sta = ((self.m_s / se2) * (1.0 - a_s)).sum()  # tr(D^-1) station blocks
        s_one, kk = self._net_sone_kk(theta)
        tr_net_corr = 0.0
        for n in range(self.n_net):
            stas = self.net_sta[n]
            tr_net_corr += kk[n] * (self.m_s[stas] * d1[stas] ** 2).sum()
        return tr_sta - tr_net_corr

    def trace_net(self, theta: np.ndarray) -> float:
        s_one, kk = self._net_sone_kk(theta)
        return float((s_one - kk * s_one**2).sum())

    def trace_sta(self, theta: np.ndarray) -> float:
        se2, sn2, ss2 = np.exp(theta)
        d1 = 1.0 / (se2 + ss2 * self.m_s)
        s_one, kk = self._net_sone_kk(theta)
        return float(((self.m_s * d1) - kk[self.net_of_sta] * (self.m_s * d1) ** 2).sum())

    def group_sums(self, M: np.ndarray, kind: str) -> np.ndarray:
        rows = self.net_rows if kind == "net" else self.sta_rows
        if M.ndim == 1:
            return np.array([[M[r].sum()] for r in rows])
        return np.array([M[r].sum(axis=0) for r in rows])


def fit_reml(
    y: np.ndarray,
    X: np.ndarray,
    net: np.ndarray,
    sta: np.ndarray,
    theta0: np.ndarray | None = None,
) -> dict:
    """Exact REML for the nested two-level random-intercept model."""
    vc = NestedVC(net, sta)
    p = X.shape[1]
    if theta0 is None:
        theta0 = np.log([0.05, 0.02, 0.02])

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        se2, sn2, ss2 = np.exp(theta)
        Vinvy = vc.solve(theta, y)
        VinvX = np.column_stack([vc.solve(theta, X[:, j]) for j in range(p)])
        XtVinvX = X.T @ VinvX
        XtVinvy = X.T @ Vinvy
        beta = np.linalg.solve(XtVinvX, XtVinvy)
        Vinvr = Vinvy - VinvX @ beta
        rVr = (y - X @ beta) @ Vinvr
        ldV = vc.logdet(theta)
        _, ldX = np.linalg.slogdet(XtVinvX)
        f = 0.5 * (ldV + ldX + rVr)
        invX = np.linalg.inv(XtVinvX)
        g_net = vc.group_sums(VinvX, "net")
        g_sta = vc.group_sums(VinvX, "sta")
        h_net = vc.group_sums(Vinvr, "net")
        h_sta = vc.group_sums(Vinvr, "sta")
        t2_net = np.einsum("np,pq,nq->", g_net, invX, g_net)
        t2_sta = np.einsum("np,pq,nq->", g_sta, invX, g_sta)
        t3_net = np.einsum("np,np->", h_net, h_net)
        t3_sta = np.einsum("np,np->", h_sta, h_sta)
        t1_net = vc.trace_net(theta)
        t1_sta = vc.trace_sta(theta)
        t1_res = vc.trace_vinv(theta)
        grad = np.array(
            [
                0.5 * se2 * (t1_res - p - Vinvr @ Vinvr),
                0.5 * sn2 * (t1_net - t2_net - t3_net),
                0.5 * ss2 * (t1_sta - t2_sta - t3_sta),
            ]
        )
        return f, grad

    res = minimize(
        objective,
        theta0,
        method="L-BFGS-B",
        jac=True,
        bounds=[(-15.0, 5.0)] * 3,
        options=dict(maxiter=200, ftol=1e-11, gtol=1e-9),
    )
    theta = res.x
    se2, sn2, ss2 = np.exp(theta)
    Vinvy = vc.solve(theta, y)
    VinvX = np.column_stack([vc.solve(theta, X[:, j]) for j in range(p)])
    XtVinvX = X.T @ VinvX
    XtVinvy = X.T @ Vinvy
    beta = np.linalg.solve(XtVinvX, XtVinvy)
    cov_beta = np.linalg.inv(XtVinvX)
    Vinvr = Vinvy - VinvX @ beta
    blup_net = (sn2 * vc.group_sums(Vinvr, "net")).ravel()
    blup_sta = (ss2 * vc.group_sums(Vinvr, "sta")).ravel()
    return dict(
        vc=vc,
        theta=theta,
        sigma2_e=se2,
        sigma2_net=sn2,
        sigma2_sta=ss2,
        sigma_e=float(np.sqrt(se2)),
        sigma_net=float(np.sqrt(sn2)),
        sigma_sta=float(np.sqrt(ss2)),
        beta=beta,
        cov_beta=cov_beta,
        blup_net=blup_net,
        blup_sta=blup_sta,
        reml_success=res.success,
        reml_nit=int(res.nit),
        reml_message=str(res.message),
    )


def penalized_monotone_fit(
    y: np.ndarray,
    X: np.ndarray,
    vc: NestedVC,
    theta: np.ndarray,
    spline_idx: np.ndarray,
    lam_s: float,
    lam_mon: float = 0.0,
    beta0: np.ndarray | None = None,
) -> dict:
    """Penalized GLS with an exactly monotone P-spline for the duration term.

    0.5 r'V^-1 r + 0.5 lam_s ||D2 c||^2, subject to D1 c >= 0.
    For a B-spline curve with nonnegative coefficient first differences the
    curve is monotone nondecreasing everywhere (all B-spline derivatives are
    positive linear combinations of the coefficient differences). This is the
    exact limit of the Eilers-style monotonicity hinge penalty (lam_mon -> inf).
    """
    p = X.shape[1]
    Vinvy = vc.solve(theta, y)
    VinvX = np.column_stack([vc.solve(theta, X[:, j]) for j in range(p)])
    XtVinvX = X.T @ VinvX
    XtVinvy = X.T @ Vinvy
    D1 = np.diff(np.eye(N_BASIS), n=1, axis=0)
    D2 = np.diff(np.eye(N_BASIS), n=2, axis=0)
    if beta0 is None:
        beta0 = np.linalg.solve(XtVinvX, XtVinvy)

    def fun_grad(beta: np.ndarray) -> tuple[float, np.ndarray]:
        r = y - X @ beta
        Vinvr = Vinvy - VinvX @ beta
        c = beta[spline_idx]
        d2c = D2 @ c
        obj = 0.5 * r @ Vinvr + 0.5 * lam_s * (d2c @ d2c)
        g = XtVinvX @ beta - XtVinvy
        g[spline_idx] += lam_s * (D2.T @ d2c)
        return obj, g

    constraints = []
    if lam_mon > 0.0:
        # soft monotonicity hinge (kept for compatibility; not used in final)
        def hinge_grad(beta: np.ndarray) -> tuple[float, np.ndarray]:
            obj, g = fun_grad(beta)
            c = beta[spline_idx]
            h = np.maximum(0.0, -(D1 @ c))
            obj += 0.5 * lam_mon * (h @ h)
            g[spline_idx] -= lam_mon * (D1.T @ h)
            return obj, g

        res = minimize(
            hinge_grad,
            beta0,
            method="L-BFGS-B",
            jac=True,
            options=dict(maxiter=600, ftol=1e-13, gtol=1e-11),
        )
    else:
        from scipy.optimize import LinearConstraint

        A = np.zeros((N_BASIS - 1, p))
        A[:, spline_idx] = D1
        mono = LinearConstraint(A, 0.0, np.inf)
        res = minimize(
            fun_grad,
            beta0,
            method="SLSQP",
            jac=True,
            constraints=[mono],
            options=dict(maxiter=600, ftol=1e-12),
        )
    beta = res.x
    c = beta[spline_idx]
    grid = np.linspace(np.log(3.0), np.log(400.0), 4000)
    curve = b_spline_basis(grid) @ c
    mono_err = float(np.min(np.diff(curve)))
    return dict(
        beta=beta,
        success=res.success,
        nit=int(res.nit),
        lam_s=float(lam_s),
        lam_mon=float(lam_mon),
        monotone=bool(mono_err >= -1e-6),
        max_neg_diff=mono_err,
        objective=float(res.fun),
    )


# --------------------------------------------------------------------------
# Daily panels and fitting-time covariates
# --------------------------------------------------------------------------


def parse_years(text: str) -> set[int]:
    if not isinstance(text, str) or not text:
        return set()
    return {int(v) for v in text.split("|") if v}


def read_wide_panel(network: str, source: str, stations: set[str]) -> pd.DataFrame:
    if source == "dev":
        role = str(INV_ROLES.get(network, "development"))
        path = DEV_CORPUS / role / "networks" / network / "daily_wide_qc.csv"
    elif source == "conf":
        path = CONF_DAILY / network / "daily_wide_temperature.csv"
    else:
        path = SECOND_DAILY / network / "daily_wide_temperature.csv"
    wide = pd.read_csv(path)
    wide["date"] = pd.to_datetime(wide["date"])
    wide = wide.set_index("date")
    keep = [c for c in wide.columns if str(c) in stations]
    return wide.loc[:, keep]


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
    return read_wide_panel(network, source, stations)


def series_stats(s: pd.Series) -> dict:
    v = s.dropna().to_numpy(dtype=float)
    out = {
        "temp_sd": np.nan,
        "temp_iqr": np.nan,
        "climatology_mae": np.nan,
        "acf_lag1": np.nan,
        "daily_gradient": np.nan,
    }
    if len(v) < 30:
        return out
    out["temp_sd"] = float(np.std(v))
    out["temp_iqr"] = float(np.quantile(v, 0.75) - np.quantile(v, 0.25))
    d = np.diff(v)
    if len(d):
        out["daily_gradient"] = float(np.mean(np.abs(d)))
    if len(v) > 2:
        a, b = v[:-1], v[1:]
        if np.std(a) > 0 and np.std(b) > 0:
            out["acf_lag1"] = float(np.corrcoef(a, b)[0, 1])
    idx = s.dropna().index
    if len(idx) > 60:
        doy = idx.dayofyear.to_numpy()
        doy_mean = pd.Series(v).groupby(doy).mean()
        clim_grid = doy_mean.reindex(range(1, 367)).interpolate(limit_direction="both")
        clim = clim_grid.to_numpy()[doy - 1]
        out["climatology_mae"] = float(np.nanmean(np.abs(v - clim)))
    return out


def acf_at_lag(s: pd.Series, lag: int) -> float:
    v = s.dropna().to_numpy(dtype=float)
    n = len(v)
    if n <= lag + 10:
        return np.nan
    a, b = v[: n - lag], v[lag:]
    if np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def donor_r2_from(wide: pd.DataFrame, target: str, donors: list[str]) -> float:
    if target not in wide.columns:
        return np.nan
    dv = wide[target].to_numpy(dtype=float)
    cols = [c for c in donors if c in wide.columns and c != target]
    if not cols:
        return np.nan
    D = wide[cols].to_numpy(dtype=float)
    mask = np.isfinite(dv) & np.isfinite(D).all(axis=1)
    if mask.sum() < 30:
        return np.nan
    y = dv[mask]
    Xd = D[mask]
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    resid = y - Xd @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    if ss_tot == 0:
        return np.nan
    return float(1.0 - ss_res / ss_tot)


def build_features_for_stations(
    network: str,
    source: str,
    station_set: set[str],
    donor_map: dict,
    fit_years_map: dict,
) -> pd.DataFrame:
    """Per-station fitting-time covariate table (panel read once per network)."""
    panel = panel_for_network(network, source, station_set)
    rows = []
    for station in station_set:
        row = {"network_id": str(network), "station_id": str(station)}
        if station not in panel.columns:
            row.update({c: np.nan for c in COV_COLS})
            rows.append(row)
            continue
        years = fit_years_map.get((str(network), str(station)), set())
        sub = panel[station]
        if years:
            sub = sub.loc[np.isin(sub.index.year, list(years))]
        stats = series_stats(sub)
        stats["acf_gap"] = acf_at_lag(sub, 7)
        donors = donor_map.get((str(network), str(station)), [])
        if years and len(donors):
            reg = panel.loc[
                np.isin(panel.index.year, list(years)), [station] + [c for c in donors if c in panel.columns]
            ]
        else:
            reg = panel
        stats["donor_r2"] = donor_r2_from(reg, station, donors)
        row.update(stats)
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Evaluation (mirrors confirmation_metrics in the paper pipeline)
# --------------------------------------------------------------------------


def evaluate(frame: pd.DataFrame, pred_col: str) -> dict:
    obs = frame["observed_recovery_loss"].to_numpy(dtype=float)
    pred = frame[pred_col].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(frame)), pred])
    counts = frame.groupby("network_id")["network_id"].transform("size")
    rw = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    (intercept, slope), *_ = np.linalg.lstsq(design * rw[:, None], obs * rw, rcond=None)
    net = frame.groupby("network_id")[[pred_col, "observed_recovery_loss"]].mean()
    return dict(
        n_station_gaps=len(frame),
        n_networks=int(frame["network_id"].nunique()),
        network_spearman=float(
            spearmanr(net[pred_col], net["observed_recovery_loss"]).statistic
        ),
        pooled_spearman=float(spearmanr(pred, obs).statistic),
        calibration_intercept=float(intercept),
        calibration_slope=float(slope),
        r2=float(1.0 - np.sum((obs - pred) ** 2) / np.sum((obs - obs.mean()) ** 2)),
        rmse=float(np.sqrt(np.mean((obs - pred) ** 2))),
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> None:
    t_start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    global INV_ROLES
    inv = pd.read_csv(INVENTORY, dtype={"network_id": str})
    INV_ROLES = inv.set_index("network_id")["role"].to_dict()

    dev_fl = pd.read_csv(DEV_FL, dtype={"network_id": str, "station_id": str})
    conf_fl = pd.read_csv(CONF_FL, dtype={"network_id": str, "station_id": str})
    second = pd.read_csv(SECOND_PRED, dtype={"network_id": str, "station_id": str})
    conf_pred = pd.read_csv(CONF_PRED, dtype={"network_id": str, "station_id": str})
    placements = pd.read_csv(SECOND_PLACEMENTS, dtype={"network_id": str, "station_id": str})
    simple = pd.read_csv(SIMPLE, dtype={"network_id": str, "station_id": str})
    dev_pred = pd.read_csv(DEV_PRED, dtype={"network_id": str, "station_id": str})

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

    dev_donors, dev_years = donor_and_years(dev_pred)
    conf_donors, conf_years = donor_and_years(conf_pred)
    sec_donors, sec_years = donor_and_years(simple)

    print("computing station covariates ...", flush=True)

    def cov_table_for(source, networks, stations, donors, years) -> pd.DataFrame:
        parts = []
        for k, net in enumerate(networks):
            parts.append(
                build_features_for_stations(net, source, stations[net], donors, years)
            )
            if (k + 1) % 15 == 0:
                print(f"  {source} panels: {k + 1}/{len(networks)}", flush=True)
        return pd.concat(parts, ignore_index=True)

    dev_feat = cov_table_for(
        "dev",
        sorted(dev_fl.network_id.unique()),
        {n: set(dev_fl[dev_fl.network_id == n].station_id) for n in dev_fl.network_id.unique()},
        dev_donors,
        dev_years,
    )
    conf_feat = cov_table_for(
        "conf",
        sorted(conf_fl.network_id.unique()),
        {n: set(conf_fl[conf_fl.network_id == n].station_id) for n in conf_fl.network_id.unique()},
        conf_donors,
        conf_years,
    )
    sec_feat = cov_table_for(
        "second",
        sorted(second.network_id.unique()),
        {n: set(second[second.network_id == n].station_id) for n in second.network_id.unique()},
        sec_donors,
        sec_years,
    )
    pd.concat([dev_feat, conf_feat, sec_feat], ignore_index=True).to_csv(
        OUT / "station_covariates.csv", index=False
    )
    print("covariates done", flush=True)

    def acf_gap_rows(source: str, frame: pd.DataFrame, years_map: dict) -> dict:
        out = {}
        for net in frame.network_id.unique():
            stas = set(frame[frame.network_id == net].station_id)
            panel = panel_for_network(net, source, stas)
            for sta in stas:
                if sta not in panel.columns:
                    continue
                years = years_map.get((str(net), str(sta)), set())
                s = panel[sta]
                if years:
                    s = s.loc[np.isin(s.index.year, list(years))]
                for g in sorted(
                    set(frame[(frame.network_id == net) & (frame.station_id == sta)].gap_length)
                ):
                    out[(str(net), str(sta), int(g))] = acf_at_lag(s, int(g))
        return out

    dev_acf = acf_gap_rows("dev", dev_fl, dev_years)
    conf_acf = acf_gap_rows("conf", conf_fl, conf_years)
    sec_acf = acf_gap_rows("second", second, sec_years)

    def assemble_fit(frame: pd.DataFrame, feat: pd.DataFrame, acf_map: dict) -> pd.DataFrame:
        f = frame.merge(feat, on=["network_id", "station_id"], how="left", suffixes=("", "_f"))
        f["acf_gap"] = [
            acf_map.get((str(r.network_id), str(r.station_id), int(r.gap_length)), np.nan)
            for r in f.itertuples()
        ]
        f["doy"] = pd.to_datetime(f["gap_start"]).dt.dayofyear
        f["y"] = np.log1p(f["mae_deg_c"])
        return f

    fit_dev = assemble_fit(dev_fl, dev_feat, dev_acf)
    fit_conf = assemble_fit(conf_fl, conf_feat, conf_acf)
    fit_pooled = pd.concat([fit_dev, fit_conf], ignore_index=True)
    print(f"fit rows: dev {len(fit_dev)}, conf {len(fit_conf)}, pooled {len(fit_pooled)}", flush=True)

    def fit_scaler(fit: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.Series]:
        med = fit[COV_COLS].median()
        mean = fit[COV_COLS].mean()
        sd = fit[COV_COLS].std().replace(0.0, 1.0)
        return mean.to_numpy(), sd.to_numpy(), med

    def scale_cov(fit: pd.DataFrame, mean: np.ndarray, sd: np.ndarray, med: pd.Series) -> np.ndarray:
        C = fit[COV_COLS].copy()
        for i, c in enumerate(COV_COLS):
            C[c] = C[c].fillna(med[c])
        return ((C.to_numpy(dtype=float) - mean) / sd).astype(float)

    def design_and_groups(fit: pd.DataFrame, C: np.ndarray):
        X, spline_idx = design_matrix(fit["gap_length"].to_numpy(), fit["doy"].to_numpy(), C)
        net, _ = pd.factorize(fit["network_id"])
        sta, _ = pd.factorize(fit["station_id"])
        return X, spline_idx, net, sta

    def design_matrix(gap_length, doy, cov):
        B = b_spline_basis(np.log(np.asarray(gap_length, dtype=float)))
        # NOTE: no explicit intercept column: the cubic B-spline basis with
        # clamped knots satisfies partition of unity (sum_j B_j = 1), so the
        # constant direction is already spanned; adding an intercept would make
        # X'V^-1X singular because log gap takes only 4 distinct values.
        parts = [B, fourier_design(np.asarray(doy, dtype=float)), cov]
        X = np.column_stack(parts)
        spline_idx = np.arange(0, N_BASIS)
        return X, spline_idx

    # ---- tuning: dev -> conf on fit losses ------------------------------------
    print("tuning lambdas (dev -> conf fit losses) ...", flush=True)
    mean_dev, sd_dev, med_dev = fit_scaler(fit_dev)
    C_dev = scale_cov(fit_dev, mean_dev, sd_dev, med_dev)
    X_dev, spl, net_dev, sta_dev = design_and_groups(fit_dev, C_dev)
    y_dev = fit_dev["y"].to_numpy()
    reml_dev = fit_reml(y_dev, X_dev, net_dev, sta_dev)
    C_conf_t = scale_cov(fit_conf, mean_dev, sd_dev, med_dev)
    X_conf_t, _, _, _ = design_and_groups(fit_conf, C_conf_t)
    y_conf_t = fit_conf["y"].to_numpy()

    grid_lam = [0.1, 0.3, 1.0, 3.0, 10.0]
    tuning_rows = []
    best = None
    for lam_s in grid_lam:
        pm = penalized_monotone_fit(
            y_dev, X_dev, reml_dev["vc"], reml_dev["theta"], spl, lam_s,
            beta0=reml_dev["beta"],
        )
        mu_conf = X_conf_t @ pm["beta"]
        rmse_conf = float(np.sqrt(np.mean((y_conf_t - mu_conf) ** 2)))
        tuning_rows.append(
            dict(lam_s=lam_s, rmse_conf_log1p=rmse_conf,
                 monotone=pm["monotone"], max_neg_diff=pm["max_neg_diff"])
        )
        if best is None or (rmse_conf < best["rmse_conf_log1p"] and pm["monotone"]):
            best = dict(lam_s=lam_s, rmse_conf_log1p=rmse_conf)
        print(f"  lam_s={lam_s}: rmse_conf={rmse_conf:.5f} mono={pm['monotone']}", flush=True)
    pd.DataFrame(tuning_rows).to_csv(OUT / "lambda_tuning.csv", index=False)
    if best is None:
        best = dict(lam_s=1.0, rmse_conf_log1p=np.nan)
    lam_s_best = best["lam_s"]
    lam_mon_best = 0.0
    print(f"best lam_s: {lam_s_best}", flush=True)

    # ---- final surface on pooled fit ------------------------------------------
    print("fitting pooled surface ...", flush=True)
    mean_p, sd_p, med_p = fit_scaler(fit_pooled)
    C_p = scale_cov(fit_pooled, mean_p, sd_p, med_p)
    X_p, spl, net_p, sta_p = design_and_groups(fit_pooled, C_p)
    y_p = fit_pooled["y"].to_numpy()
    reml_p = fit_reml(y_p, X_p, net_p, sta_p)
    pm_p = penalized_monotone_fit(
        y_p, X_p, reml_p["vc"], reml_p["theta"], spl, lam_s_best, lam_mon_best,
        beta0=reml_p["beta"],
    )
    Vinvy_p = reml_p["vc"].solve(reml_p["theta"], y_p)
    VinvX_p = np.column_stack(
        [reml_p["vc"].solve(reml_p["theta"], X_p[:, j]) for j in range(X_p.shape[1])]
    )
    Vinvr_p = Vinvy_p - VinvX_p @ pm_p["beta"]
    blup_net_p = (reml_p["sigma2_net"] * reml_p["vc"].group_sums(Vinvr_p, "net")).ravel()
    blup_sta_p = (reml_p["sigma2_sta"] * reml_p["vc"].group_sums(Vinvr_p, "sta")).ravel()

    # ---- second panel predictions ---------------------------------------------
    print("predicting second panel ...", flush=True)
    pl_season = placements.copy()
    pl_season["station_id"] = pl_season["station_id"].astype(str)
    pl_season["doy"] = pd.to_datetime(pl_season["gap_start"]).dt.dayofyear
    fourier = fourier_design(pl_season["doy"].to_numpy())
    pl_season[["sin1", "cos1", "sin2", "cos2"]] = fourier
    cell_fourier = (
        pl_season.groupby(["network_id", "station_id", "gap_length"])[
            ["sin1", "cos1", "sin2", "cos2"]
        ]
        .mean()
        .reset_index()
    )
    cells = second.merge(cell_fourier, on=["network_id", "station_id", "gap_length"], how="left")
    cells["station_id"] = cells["station_id"].astype(str)
    cells = cells.merge(sec_feat, on=["network_id", "station_id"], how="left", suffixes=("", "_f"))
    cells["acf_gap"] = [
        sec_acf.get((str(r.network_id), str(r.station_id), int(r.gap_length)), np.nan)
        for r in cells.itertuples()
    ]
    C_cells = cells[COV_COLS].copy()
    for i, c in enumerate(COV_COLS):
        C_cells[c] = C_cells[c].fillna(med_p[c])
    C_cells = ((C_cells.to_numpy(dtype=float) - mean_p) / sd_p).astype(float)
    dummy_doy = np.full(len(cells), 1.0)
    X_cells, _ = design_matrix(cells["gap_length"].to_numpy(), dummy_doy, C_cells)
    X_cells[:, N_BASIS : N_BASIS + 4] = cells[["sin1", "cos1", "sin2", "cos2"]].to_numpy(dtype=float)
    mu_cells = X_cells @ pm_p["beta"]
    sd_base = np.sqrt(
        reml_p["sigma2_e"]
        + reml_p["sigma2_net"]
        + reml_p["sigma2_sta"]
        + np.einsum("np,pq,nq->n", X_cells, reml_p["cov_beta"], X_cells)
    )
    log_gap = np.log(cells["gap_length"].to_numpy(dtype=float))
    ext_factor = np.maximum(0.0, (log_gap - GAP_MAX_LOG) / (GAP_MAX_LOG - GAP_MIN_LOG))
    is_interp = (cells["gap_length"].astype(float) > 7) & (
        cells["gap_length"].astype(float) < 180
    ) & (~cells["gap_length"].astype(float).isin([30.0, 90.0]))
    support = np.where(
        cells["gap_length"].astype(float).isin([7.0, 30.0, 90.0, 180.0]),
        "direct",
        np.where(is_interp, "interpolated", "extrapolated"),
    )
    sd_eff = sd_base * (1.0 + 2.0 * ext_factor)
    pred_mean = np.maximum(0.0, log1p_expm1(mu_cells, sd_base**2))
    lower = np.expm1(mu_cells - Z90 * sd_eff)
    upper = np.expm1(mu_cells + Z90 * sd_eff)
    cells["surface_prediction_mae"] = pred_mean
    cells["surface_lower90"] = np.maximum(0.0, lower)
    cells["surface_upper90"] = upper
    cells["surface_prediction_log1p"] = mu_cells
    cells["predictive_sd_log"] = sd_eff
    cells["predictive_sd_log_base"] = sd_base
    cells["support_status"] = support
    cells["extrapolation_factor"] = ext_factor
    cells["old_empirical_prediction"] = second["empirical_transfer_prediction"]
    cells["observed_recovery_loss"] = second["observed_recovery_loss"]
    cells["relative_width90"] = (cells["surface_upper90"] - cells["surface_lower90"]) / pred_mean
    cells.to_csv(OUT / "second_panel_predictions.csv", index=False)
    print("second panel predictions written", flush=True)

    # ---- evaluation: second panel ---------------------------------------------
    ev_rows = []
    ev_rows.append(dict(predictor="surface_full_1446", **evaluate(cells, "surface_prediction_mae")))
    old = cells.rename(columns={"old_empirical_prediction": "predicted_loss"})
    ev_rows.append(dict(predictor="old_empirical_full_1446", **evaluate(old, "predicted_loss")))
    sup = cells[cells["gap_length"].astype(float).isin([7.0, 30.0, 90.0, 180.0])]
    ev_rows.append(dict(predictor="surface_direct_874", **evaluate(sup, "surface_prediction_mae")))
    old_sup = old[old["gap_length"].astype(float).isin([7.0, 30.0, 90.0, 180.0])]
    ev_rows.append(dict(predictor="old_empirical_direct_874", **evaluate(old_sup, "predicted_loss")))
    fb = cells[~cells["gap_length"].astype(float).isin([7.0, 30.0, 90.0, 180.0])]
    ev_rows.append(dict(predictor="surface_fallback_572", **evaluate(fb, "surface_prediction_mae")))
    old_fb = old[~old["gap_length"].astype(float).isin([7.0, 30.0, 90.0, 180.0])]
    ev_rows.append(dict(predictor="old_network_mean_fallback_572", **evaluate(old_fb, "predicted_loss")))
    interp_cells = cells[cells["support_status"] == "interpolated"]
    ev_rows.append(dict(predictor="surface_interpolated_448", **evaluate(interp_cells, "surface_prediction_mae")))
    old_interp = old[old["support_status"] == "interpolated"]
    ev_rows.append(dict(predictor="old_fallback_interpolated_448", **evaluate(old_interp, "predicted_loss")))
    ext_cells = cells[cells["support_status"] == "extrapolated"]
    ev_rows.append(dict(predictor="surface_extrapolated_124", **evaluate(ext_cells, "surface_prediction_mae")))
    old_ext = old[old["support_status"] == "extrapolated"]
    ev_rows.append(dict(predictor="old_fallback_extrapolated_124", **evaluate(old_ext, "predicted_loss")))
    ev_second = pd.DataFrame(ev_rows)
    ev_second.to_csv(OUT / "evaluation_second_panel.csv", index=False)
    print("second panel evaluation written", flush=True)

    # ---- abstention curves ------------------------------------------------------
    print("abstention curves ...", flush=True)
    curve_rows = []
    for tau in [0.0, 0.05, 0.1, 0.15, 0.2, 0.217, 0.25, 0.3, 0.5, 1.0]:
        released = cells[cells["extrapolation_factor"] <= tau]
        if len(released) >= 20:
            m = evaluate(released, "surface_prediction_mae")
            curve_rows.append(
                dict(rule="extrapolation_factor", threshold=tau,
                     fraction_abstained=1.0 - len(released) / len(cells),
                     n_released=len(released), **m)
            )
    for cap in [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 25.0, 50.0, 100.0]:
        released = cells[cells["relative_width90"] <= cap]
        if len(released) >= 20:
            m = evaluate(released, "surface_prediction_mae")
            curve_rows.append(
                dict(rule="relative_width90", threshold=cap,
                     fraction_abstained=1.0 - len(released) / len(cells),
                     n_released=len(released), **m)
            )
    abst = pd.DataFrame(curve_rows)
    abst.to_csv(OUT / "abstention_curve.csv", index=False)

    # ---- first-panel cross-check ------------------------------------------------
    print("first panel cross-check ...", flush=True)
    mean_c, sd_c, med_c = fit_scaler(fit_conf)
    C_c = scale_cov(fit_conf, mean_c, sd_c, med_c)
    X_c, spl, net_c, sta_c = design_and_groups(fit_conf, C_c)
    y_c = fit_conf["y"].to_numpy()
    reml_c = fit_reml(y_c, X_c, net_c, sta_c)
    pm_c = penalized_monotone_fit(
        y_c, X_c, reml_c["vc"], reml_c["theta"], spl, lam_s_best, lam_mon_best,
        beta0=reml_c["beta"],
    )
    Vinvy_c = reml_c["vc"].solve(reml_c["theta"], y_c)
    VinvX_c = np.column_stack(
        [reml_c["vc"].solve(reml_c["theta"], X_c[:, j]) for j in range(X_c.shape[1])]
    )
    Vinvr_c = Vinvy_c - VinvX_c @ pm_c["beta"]
    blup_net_c = (reml_c["sigma2_net"] * reml_c["vc"].group_sums(Vinvr_c, "net")).ravel()
    blup_sta_c = (reml_c["sigma2_sta"] * reml_c["vc"].group_sums(Vinvr_c, "sta")).ravel()
    _, net_index_c = pd.factorize(fit_conf["network_id"])
    _, sta_index_c = pd.factorize(fit_conf["station_id"])

    pp = conf_pred.copy()
    pp["station_id"] = pp["station_id"].astype(str)
    pp["network_id"] = pp["network_id"].astype(str)
    pp = pp.merge(conf_feat, on=["network_id", "station_id"], how="left", suffixes=("", "_f"))
    pp["acf_gap"] = [
        conf_acf.get((str(r.network_id), str(r.station_id), int(r.gap_length)), np.nan)
        for r in pp.itertuples()
    ]
    C_pp = pp[COV_COLS].copy()
    for i, c in enumerate(COV_COLS):
        C_pp[c] = C_pp[c].fillna(med_c[c])
    C_pp = ((C_pp.to_numpy(dtype=float) - mean_c) / sd_c).astype(float)
    doy_pp = pd.to_datetime(pp["gap_start"]).dt.dayofyear
    X_pp, _ = design_matrix(pp["gap_length"].to_numpy(), doy_pp.to_numpy(), C_pp)
    mu_pp = X_pp @ pm_c["beta"]
    net_idx = pd.Series(np.arange(len(net_index_c)), index=net_index_c)
    sta_idx = pd.Series(np.arange(len(sta_index_c)), index=sta_index_c)
    net_codes = net_idx.reindex(pp["network_id"]).to_numpy(dtype=float)
    sta_codes = sta_idx.reindex(pp["station_id"]).to_numpy(dtype=float)
    u_net = np.zeros(len(pp))
    u_sta = np.zeros(len(pp))
    net_ok = ~np.isnan(net_codes)
    sta_ok = ~np.isnan(sta_codes)
    u_net[net_ok] = blup_net_c[net_codes[net_ok].astype(int)]
    u_sta[sta_ok] = blup_sta_c[sta_codes[sta_ok].astype(int)]
    mu_pp_full = mu_pp + u_net + u_sta
    pp["surface_placement_pred"] = np.maximum(
        0.0, log1p_expm1(mu_pp_full, reml_c["sigma2_e"])
    )
    cell_pp = (
        pp.groupby(["network_id", "station_id", "gap_length"])
        .agg(
            surface_prediction_mae=("surface_placement_pred", "mean"),
            old_empirical_prediction=("empirical_transfer_prediction", "mean"),
            observed_recovery_loss=("observed_recovery_loss", "mean"),
            n_placements=("surface_placement_pred", "size"),
        )
        .reset_index()
    )
    old_source = (
        pp.groupby(["network_id", "station_id", "gap_length"])["empirical_transfer_source"]
        .agg(lambda s: "network_mean_fallback" if (s == "network_mean_fallback").all() else "other")
        .reset_index()
        .rename(columns={"empirical_transfer_source": "old_source_cell"})
    )
    cell_pp = cell_pp.merge(old_source, on=["network_id", "station_id", "gap_length"])
    cell_pp.to_csv(OUT / "first_panel_predictions.csv", index=False)
    ev1 = []
    ev1.append(dict(predictor="surface_first_panel_1440", **evaluate(cell_pp, "surface_prediction_mae")))
    ev1.append(dict(predictor="old_empirical_first_panel_1440", **evaluate(cell_pp, "old_empirical_prediction")))
    fb_cells = cell_pp[cell_pp["old_source_cell"] == "network_mean_fallback"]
    if len(fb_cells) >= 20:
        ev1.append(dict(predictor="surface_fallback_cells", **evaluate(fb_cells, "surface_prediction_mae")))
        ev1.append(dict(predictor="old_fallback_cells", **evaluate(fb_cells, "old_empirical_prediction")))
    ev_first = pd.DataFrame(ev1)
    ev_first.to_csv(OUT / "evaluation_first_panel.csv", index=False)

    # ---- surface summary --------------------------------------------------------
    grid_curve = np.linspace(np.log(3.0), np.log(400.0), 4000)
    curve_p = b_spline_basis(grid_curve) @ pm_p["beta"][spl]
    curve_df = pd.DataFrame(
        dict(
            log_gap=grid_curve,
            gap_days=np.exp(grid_curve),
            duration_effect_log1p=curve_p,
            duration_effect_mae=np.expm1(curve_p),
        )
    )
    curve_df.to_csv(OUT / "duration_curve.csv", index=False)

    total_var = reml_p["sigma2_e"] + reml_p["sigma2_net"] + reml_p["sigma2_sta"]
    summary = {
        "n_fit_rows": {"development": len(fit_dev), "confirmation": len(fit_conf), "pooled": len(fit_pooled)},
        "variance_components_pooled": {
            "sigma2_e": float(reml_p["sigma2_e"]),
            "sigma2_net": float(reml_p["sigma2_net"]),
            "sigma2_sta": float(reml_p["sigma2_sta"]),
            "sigma_e": float(reml_p["sigma_e"]),
            "sigma_net": float(reml_p["sigma_net"]),
            "sigma_sta": float(reml_p["sigma_sta"]),
            "share_net": float(reml_p["sigma2_net"] / total_var),
            "share_sta": float(reml_p["sigma2_sta"] / total_var),
            "share_resid": float(reml_p["sigma2_e"] / total_var),
            "reml_success": reml_p["reml_success"],
            "reml_nit": reml_p["reml_nit"],
            "reml_message": reml_p["reml_message"],
        },
        "variance_components_confirmation_only": {
            "sigma2_e": float(reml_c["sigma2_e"]),
            "sigma2_net": float(reml_c["sigma2_net"]),
            "sigma2_sta": float(reml_c["sigma2_sta"]),
        },
        "variance_components_development_only": {
            "sigma2_e": float(reml_dev["sigma2_e"]),
            "sigma2_net": float(reml_dev["sigma2_net"]),
            "sigma2_sta": float(reml_dev["sigma2_sta"]),
        },
        "lambda": {"lam_s": float(lam_s_best), "lam_mon": float(lam_mon_best)},
        "tuning_best": best,
        "monotone_curve": {
            "max_neg_diff_grid": float(np.min(np.diff(curve_p))),
            "effect_mae_at_7": float(np.expm1(curve_df[curve_df.gap_days >= 6.9].iloc[0]["duration_effect_log1p"])),
            "effect_mae_at_180": float(np.expm1(curve_df[curve_df.gap_days <= 181].iloc[-1]["duration_effect_log1p"])),
            "effect_mae_at_365": float(np.expm1(curve_df[curve_df.gap_days <= 366].iloc[-1]["duration_effect_log1p"])),
        },
        "spline_coefficients": {f"bs_{j}": float(pm_p["beta"][spl[j]]) for j in range(N_BASIS)},
        "fixed_effects": {
            k: float(v)
            for k, v in zip(
                [f"bs_{j}" for j in range(N_BASIS)]
                + ["sin1", "cos1", "sin2", "cos2"]
                + COV_COLS,
                pm_p["beta"],
            )
        },
        "covariate_scaling_pooled": {
            c: {"mean": float(mean_p[i]), "sd": float(sd_p[i])} for i, c in enumerate(COV_COLS)
        },
        "season_amplitude_log1p": float(np.sqrt(pm_p["beta"][N_BASIS] ** 2 + pm_p["beta"][N_BASIS + 1] ** 2)),
        "season_harmonic2_amplitude_log1p": float(
            np.sqrt(pm_p["beta"][N_BASIS + 2] ** 2 + pm_p["beta"][N_BASIS + 3] ** 2)
        ),
        "extrapolation": {
            "max_supported_gap": 180,
            "extrapolation_factor_365": float((np.log(365) - GAP_MAX_LOG) / (GAP_MAX_LOG - GAP_MIN_LOG)),
            "widening_multiplier_365": float(
                1.0 + 2.0 * (np.log(365) - GAP_MAX_LOG) / (GAP_MAX_LOG - GAP_MIN_LOG)
            ),
        },
        "runtime_seconds": float(time.time() - t_start),
    }
    (OUT / "surface_fit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    # ---- figures ------------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    ax.plot(curve_df["gap_days"], curve_df["duration_effect_mae"], "b-", lw=2, label="monotone duration curve")
    raw = fit_pooled.groupby("gap_length")["mae_deg_c"].mean()
    ax.plot(raw.index, raw.values, "ks", ms=7, label="raw mean MAE (fit rows)")
    for g in [7, 14, 30, 60, 90, 180, 365]:
        ax.axvline(g, color="grey", lw=0.6, ls=":")
    ax.set_xscale("log")
    ax.set_xlabel("gap length (days)")
    ax.set_ylabel("duration contribution (deg C)")
    ax.set_title("Monotone duration curve (pooled fit)")
    ax.legend()
    ax2 = axes[1]
    for rule, marker in [("extrapolation_factor", "o-"), ("relative_width90", "s-")]:
        sub = abst[abst.rule == rule]
        ax2.plot(sub.fraction_abstained, sub.network_spearman, marker, label=rule)
    ax2.set_xlabel("fraction abstained")
    ax2.set_ylabel("network-level Spearman of released units")
    ax2.set_title("Abstention curve (second panel)")
    ax2.legend()
    fig.tight_layout()
    fig.savefig(OUT / "figures_risk_surface.png", dpi=140)
    plt.close(fig)

    print(json.dumps(summary, indent=2), flush=True)
    print(f"done in {time.time() - t_start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
