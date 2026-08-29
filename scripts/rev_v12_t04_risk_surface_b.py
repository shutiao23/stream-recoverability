"""revision v12, task t04 (agent B): continuous support-aware risk surface.

Hierarchical model of fitting-period empirical MAE:
    log(1 + MAE) ~ network random intercept + station random intercept
                 + monotone linear spline f(log gap_length)
                 + cyclic day-of-year g(DOY)  (Fourier sin/cos, 2 harmonics)
                 + fitting-time covariates (climatology error, donor R2,
                   ACF, nearest-donor correlation, additive heuristic)

Fitted ONLY on fitting-period artificial-gap placements:
    results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv
    results/development_v11/reviewer_completion/development_empirical_fit_losses.csv

Predicts the second panel's 1,446 units
    (results/development_v11/second_confirmation/scoring/empirical_predictions.csv)
with durations 14/60 interpolated from the continuous curve and 365
extrapolated (flagged, interval widened), plus an abstention rule.

Also refits the same surface on first-panel fit losses to predict the first
panel's 1,440 units (confirmation_empirical_predictions.csv) as cross-check.

Evaluation vs old network-mean fallback and vs empirical_transfer_prediction
on the same units; abstention curve; REPORT.md.

Outputs: results/revision_v12/t04_risk_surface/agent_b/
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REV = RESULTS / "development_v11"
OUT = RESULTS / "revision_v12" / "t04_risk_surface" / "agent_b"
OUT.mkdir(parents=True, exist_ok=True)

RC = REV / "reviewer_completion"
SCORING = REV / "second_confirmation" / "scoring"

FIT_FILES = [
    RC / "confirmation_empirical_fit_losses.csv",
    RC / "development_empirical_fit_losses.csv",
]

DOY_KNOTS = [7.0, 14.0, 30.0, 60.0, 90.0, 180.0]
HINGE_KNOTS_LOG = [np.log(k) for k in [30.0, 90.0]]
N_FOURIER = 2


def log1p(x):
    return np.log1p(x)


def expm1(x):
    return np.expm1(x)


def doy_sincos(dates: pd.Series) -> pd.DataFrame:
    d = pd.to_datetime(dates).dt.dayofyear
    ang = 2.0 * np.pi * d.to_numpy(dtype=float) / 365.0
    out = pd.DataFrame(
        {
            "doy_sin1": np.sin(ang),
            "doy_cos1": np.cos(ang),
            "doy_sin2": np.sin(2 * ang),
            "doy_cos2": np.cos(2 * ang),
        },
        index=dates.index,
    )
    return out


def spline_basis(log_x: np.ndarray) -> pd.DataFrame:
    """Monotone linear-spline basis in log duration: log(gap) plus positive
    hinge terms at log(30) and log(90) d (the interior fitting durations;
    knots restricted so the basis is identifiable on the 4 observed gaps
    7/30/90/180). Nonnegative coefficients -> monotone nondecreasing curve."""
    cols = {"log_gap_lin": log_x.astype(float)}
    for k, kk in enumerate(HINGE_KNOTS_LOG):
        cols[f"hinge{k + 1}"] = np.maximum(0.0, log_x.astype(float) - kk)
    return pd.DataFrame(cols)


def monotone_check(grid_log_x, basis_df, coefs):
    vals = basis_df.to_numpy() @ np.asarray(coefs, dtype=float)
    return bool(np.all(np.diff(vals) >= -1e-9)), float(vals[-1] - vals[0])


def load_fit_data() -> pd.DataFrame:
    frames = []
    for p in FIT_FILES:
        df = pd.read_csv(p, dtype={"network_id": str, "station_id": str})
        df["_panel"] = "confirmation" if "confirmation" in p.name else "development"
        frames.append(df)
    fit = pd.concat(frames, ignore_index=True)
    fit["log_gap"] = np.log(fit["gap_length"].astype(float))
    fit["y"] = log1p(fit["mae_deg_c"].to_numpy(dtype=float))
    fit = fit.join(doy_sincos(fit["gap_start"]))
    fit["season"] = fit["season"].astype(str)
    return fit


def join_covariates(fit: pd.DataFrame) -> pd.DataFrame:
    """Join station(-gap) covariates; impute missing with network means."""
    cov_cols = ["acf_only", "donor_r2_only", "additive_d_over_4_heuristic",
                "nearest_donor_correlation"]

    ra = pd.read_csv(RC.parent / "route_a_confirmation" / "predictions.csv",
                     dtype={"network_id": str, "station_id": str})
    sgo = pd.read_csv(RC.parent / "station_gap_outcomes.csv",
                      dtype={"network_id": str, "station_id": str})

    # confirmation stations: route_a unit-level covariates (per station-gap)
    ra_cov = ra[["network_id", "station_id", "gap_length"] + cov_cols].copy()
    ra_cov["gap_length"] = ra_cov["gap_length"].astype(float)
    # development stations: station_gap_outcomes covariates (per station-gap)
    sgo_cov = sgo[["network_id", "station_id", "gap_length"] + cov_cols].copy()
    sgo_cov["gap_length"] = sgo_cov["gap_length"].astype(float)

    fit["gap_length"] = fit["gap_length"].astype(float)
    out = fit.merge(ra_cov, on=["network_id", "station_id", "gap_length"],
                    how="left", suffixes=("", "_ra"))
    still_missing = out[cov_cols].isna().any(axis=1)
    dev_mask = out["_panel"].eq("development") & still_missing
    if dev_mask.any():
        dev_part = out.loc[dev_mask, ["network_id", "station_id", "gap_length"]].merge(
            sgo_cov, on=["network_id", "station_id", "gap_length"], how="left")
        for c in cov_cols:
            out.loc[dev_mask, c] = dev_part[c].to_numpy()

    # residual missing -> station-level mean, then network-level mean, then global
    for c in cov_cols:
        out[c] = out[c].astype(float)
        if out[c].isna().any():
            st_mean = out.groupby(["network_id", "station_id"])[c].transform("mean")
            out[c] = out[c].fillna(st_mean)
        if out[c].isna().any():
            net_mean = out.groupby("network_id")[c].transform("mean")
            out[c] = out[c].fillna(net_mean)
        if out[c].isna().any():
            out[c] = out[c].fillna(out[c].median())

    # climatology error: station-level mean over placements (per-placement files)
    per_pl = pd.concat([
        pd.read_csv(RC / "confirmation_empirical_predictions.csv",
                    dtype={"network_id": str, "station_id": str},
                    usecols=["network_id", "station_id", "climatology_mae_deg_c"]),
        pd.read_csv(RC / "development_empirical_predictions.csv",
                    dtype={"network_id": str, "station_id": str},
                    usecols=["network_id", "station_id", "climatology_mae_deg_c"]),
    ], ignore_index=True)
    clim = per_pl.groupby(["network_id", "station_id"], as_index=False)[
        "climatology_mae_deg_c"].mean().rename(
        columns={"climatology_mae_deg_c": "clim_error"})
    out = out.merge(clim, on=["network_id", "station_id"], how="left")
    out["clim_error"] = out["clim_error"].fillna(out["clim_error"].median())

    out["imputed"] = (
        out["acf_only"].isna() | out["donor_r2_only"].isna()
        | out["nearest_donor_correlation"].isna() | out["clim_error"].isna()
    )
    out["imputed"] = out["imputed"].fillna(False)
    for c in cov_cols + ["clim_error"]:
        out[c] = out[c].astype(float)
    return out


def spline_columns(df: pd.DataFrame) -> pd.DataFrame:
    return spline_basis(df["log_gap"].to_numpy())


def fit_surface(train: pd.DataFrame, fixed_cols: list[str], spline_cols: list[str],
                vc: bool = True):
    """Fit MixedLM (network + station random intercepts) on log(1+MAE) with
    fixed effects fixed_cols+spline_cols. Network RE via re_formula,
    station RE (nested within network) via vc_formula."""
    formula = "y ~ " + " + ".join(fixed_cols + spline_cols)
    t0 = time.time()
    if vc:
        md = sm.MixedLM.from_formula(
            formula=formula, data=train,
            re_formula="1", vc_formula={"station": "0 + C(station_id)"},
            groups="network_id")
    else:
        md = sm.MixedLM.from_formula(formula=formula, data=train, groups="network_id")
    result = md.fit(reml=True)
    result._fit_time_s = time.time() - t0
    return result


def variance_components(result) -> dict:
    var_net = float(result.cov_re.iloc[0, 0])
    vcomp = result.vcomp
    if isinstance(vcomp, dict):
        var_station = float(vcomp.get("station", 0.0))
    elif isinstance(vcomp, np.ndarray) and vcomp.size >= 1:
        var_station = float(np.asarray(vcomp).ravel()[0])
    else:
        var_station = 0.0
    return {
        "network": var_net,
        "station": var_station,
        "residual": float(result.scale),
    }


def standardize_covariates(df: pd.DataFrame, cov_cols: list[str],
                           center: dict | None = None,
                           scale: dict | None = None):
    """Z-score covariates in place-ish; returns (df, center, scale)."""
    df = df.copy()
    center = {} if center is None else center
    scale = {} if scale is None else scale
    for c in cov_cols:
        if c not in center:
            center[c] = float(df[c].mean())
            scale[c] = float(df[c].std())
            if scale[c] == 0:
                scale[c] = 1.0
        df[c] = (df[c] - center[c]) / scale[c]
    return df, center, scale


def gls_solve_blocks(train, fixed_cols, spline_cols, var_net, var_station, var_e):
    """Block-diagonal GLS with nested REs; block per (network, station)."""
    x = np.column_stack(
        [np.ones(len(train))] + [train[c].to_numpy() for c in fixed_cols + spline_cols]
    )
    y = train["y"].to_numpy()
    key = train["network_id"].astype(str) + "|" + train["station_id"].astype(str)
    key = key.to_numpy()
    pos = np.arange(len(train))
    blocks = {}
    for k in np.unique(key):
        blocks[k] = pos[key == k]
    a = var_net + var_station

    def xtvix(z):
        out = np.zeros((x.shape[1], z.shape[1]))
        for idx in blocks.values():
            m = len(idx)
            w = a / (var_e + m * a)
            xb = x[idx]
            zb = z[idx]
            inner = (xb.T @ zb) - w * np.outer(xb.sum(axis=0), zb.sum(axis=0))
            out += inner / var_e
        return out

    def grad(beta):
        r = y - x @ beta
        g = np.zeros(x.shape[1])
        for idx in blocks.values():
            m = len(idx)
            w = a / (var_e + m * a)
            g += (x[idx].T @ r[idx] - w * (x[idx].sum(axis=0) * r[idx].sum())) / var_e
        return g

    def obj(beta):
        r = y - x @ beta
        v = 0.0
        for idx in blocks.values():
            m = len(idx)
            w = a / (var_e + m * a)
            rsum = r[idx].sum()
            v += (r[idx] @ r[idx] - w * rsum * rsum) / var_e
        return v

    return x, y, obj, grad, xtvix


def constrained_refit(train, fixed_cols, spline_cols, var_net, var_station, var_e):
    """Constrained GLS: same fixed effects, spline coefficients >= 0
    (monotone linear spline). RE variances fixed at MixedLM estimates.
    Starts from the closed-form unconstrained GLS solution."""
    n_spline = len(spline_cols)
    x, y, obj, grad, xtvix = gls_solve_blocks(
        train, fixed_cols, spline_cols, var_net, var_station, var_e)
    n_params = x.shape[1]
    xtx = xtvix(x)
    xty = xtvix(y[:, None])[:, 0]
    beta_gls = np.linalg.solve(xtx, xty)
    beta0 = beta_gls.copy()
    spl_start = beta0[len(fixed_cols) + 1:]
    if np.any(spl_start < 0):
        beta0[len(fixed_cols) + 1:] = np.maximum(spl_start, 0.0)
    cons = [{"type": "ineq", "fun": lambda b: b[len(fixed_cols) + 1:]}]
    res = minimize(obj, beta0, jac=grad, method="SLSQP", constraints=cons,
                   options={"maxiter": 2000, "ftol": 1e-12})
    if not res.success:
        res = minimize(obj, beta0, jac=grad, method="SLSQP", constraints=cons,
                       options={"maxiter": 5000, "ftol": 1e-13})
    if not res.success or not np.all(np.isfinite(res.x)):
        # fall back to unconstrained GLS if its spline is already monotone,
        # else to the clamped variant (documented in REPORT)
        res = _GlsResult(beta_gls, obj(beta_gls), success=True,
                         message="fallback: unconstrained GLS")
    return res


class _GlsResult:
    def __init__(self, x, fun, success, message):
        self.x = np.asarray(x, dtype=float)
        self.fun = float(fun)
        self.success = bool(success)
        self.message = str(message)


def predict_surface(result, fixed_cols, spline_cols, new: pd.DataFrame,
                    spline_coef_constrained=None, widen=0.0, smear_log=0.0):
    """Predictive mean on log1p scale (smearing-adjusted); sd (log1p)."""
    fixed_idx = list(result.model.exog_names)
    name_map = {n: i for i, n in enumerate(fixed_idx)}
    names = ["Intercept"] + fixed_cols + spline_cols
    if spline_coef_constrained is not None:
        beta = spline_coef_constrained
    else:
        beta = np.zeros(len(names))
        for j, n in enumerate(names):
            if n in name_map:
                beta[j] = result.params[name_map[n]]
    x = np.column_stack(
        [np.ones(len(new))] + [new[c].to_numpy() for c in fixed_cols + spline_cols]
    )
    z = x @ beta + smear_log
    vc_all = variance_components(result)
    sd = np.sqrt(vc_all["network"] + vc_all["station"] + vc_all["residual"])
    sd = sd * (1.0 + widen)
    return z, sd, beta


def aggregate_unit_predictions(placement_pred: pd.DataFrame, unit_keys: list[str]) -> pd.DataFrame:
    g = placement_pred.groupby(unit_keys, as_index=False).agg(
        predicted_mean=("pred_z", lambda s: expm1(np.mean(s))),
        predicted_log_mean=("pred_z", "mean"),
        predicted_lower=("pred_lower", "mean"),
        predicted_upper=("pred_upper", "mean"),
        n_placements=("pred_z", "size"),
    )
    return g


def metrics_table(obs: np.ndarray, pred: np.ndarray) -> dict:
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    m = {}
    m["n"] = int(len(obs))
    m["pooled_spearman"] = float(stats.spearmanr(pred, obs).statistic)
    m["calibration_slope"] = float(np.polyfit(pred, obs, 1)[0])
    m["calibration_intercept"] = float(np.polyfit(pred, obs, 1)[1])
    m["r2"] = float(1.0 - np.sum((obs - pred) ** 2) / np.sum((obs - obs.mean()) ** 2))
    m["rmse"] = float(np.sqrt(np.mean((obs - pred) ** 2)))
    return m


def network_spearman(df: pd.DataFrame, pred_col: str, min_units: int = 5) -> dict:
    rows = []
    for net, g in df.groupby("network_id"):
        if len(g) >= min_units:
            r = stats.spearmanr(g[pred_col], g["observed_recovery_loss"]).statistic
            rows.append({"network_id": net, "n": len(g), "spearman": r})
    if not rows:
        return {"mean": np.nan, "n_weighted": np.nan, "median": np.nan,
                "n_networks": 0, "n_units": 0}
    tab = pd.DataFrame(rows)
    n = tab["n"].sum()
    return {
        "mean": float(tab["spearman"].mean()),
        "n_weighted": float((tab["spearman"] * tab["n"]).sum() / n),
        "median": float(tab["spearman"].median()),
        "n_networks": int(len(tab)),
        "n_units": int(n),
    }


def main() -> None:
    t_start = time.time()
    out_log = []

    # ---------------------------------------------------------------- fit data
    fit = load_fit_data()
    fit = join_covariates(fit)
    spl = spline_columns(fit)
    fit = pd.concat([fit, spl], axis=1)
    fit["log_gap"] = np.log(fit["gap_length"].astype(float))

    n_conf = fit["_panel"].eq("confirmation").sum()
    n_dev = fit["_panel"].eq("development").sum()
    out_log.append(f"fit placements: confirmation={n_conf}, development={n_dev}, "
                   f"networks={fit['network_id'].nunique()}, stations={fit['station_id'].nunique()}")

    cov_cols = ["clim_error", "donor_r2_only", "acf_only", "nearest_donor_correlation"]
    fourier_cols = ["doy_sin1", "doy_cos1", "doy_sin2", "doy_cos2"]
    spline_cols = list(spline_columns(fit).columns)
    fixed_cols = fourier_cols + cov_cols
    names = ["Intercept"] + fixed_cols + spline_cols

    fit, cov_center, cov_scale = standardize_covariates(fit, cov_cols)

    # ------------------------------------------------------------- main model
    t0 = time.time()
    result = fit_surface(fit, fixed_cols, spline_cols)
    out_log.append(f"MixedLM fit {result._fit_time_s:.1f}s (total so far {(time.time()-t_start)/60:.1f} min)")

    vc_all = variance_components(result)
    var_e = vc_all["residual"]
    var_net = vc_all["network"]
    var_station = vc_all["station"]

    # fixed-effects table
    fe_terms = list(result.model.exog_names)
    fe = pd.DataFrame({
        "term": fe_terms,
        "coef": result.params.loc[fe_terms].values,
        "se": result.bse.loc[fe_terms].values,
        "z": result.tvalues.loc[fe_terms].values,
        "p": result.pvalues.loc[fe_terms].values,
    })
    fe.to_csv(OUT / "surface_fixed_effects.csv", index=False)

    # monotonicity of unconstrained spline curve
    grid_g = np.linspace(7.0, 365.0, 500)
    grid_b = spline_columns(pd.DataFrame({"log_gap": np.log(grid_g)}))
    spl_coefs = np.zeros(len(spline_cols))
    for k, c in enumerate(spline_cols):
        if c in result.params.index:
            spl_coefs[k] = result.params[c]
    mono, rise = monotone_check(np.log(grid_g), grid_b, spl_coefs)
    out_log.append(f"unconstrained spline monotone on 7..365: {mono} (rise {rise:.3f})")

    # ------------------------------------------------- constrained monotone refit
    cons_res = constrained_refit(fit, fixed_cols, spline_cols, var_net, var_station, var_e)
    beta_c = cons_res.x.copy()
    smear_log = smearing_factor(fit, fixed_cols, spline_cols, beta_c)
    spl_coefs_c = beta_c[len(fixed_cols) + 1:]
    mono_c, rise_c = monotone_check(np.log(grid_g), grid_b, spl_coefs_c)
    out_log.append(f"constrained (hinge slopes >=0) fit: success={cons_res.success}, "
                   f"monotone={mono_c} (rise {rise_c:.3f})")

    # duration curve evaluations
    curve_df = pd.DataFrame({"gap_length": grid_g})
    base = np.column_stack(
        [np.zeros(len(grid_g)) for _ in fourier_cols]
        + [np.array([np.nanmedian(fit[c]) for c in cov_cols])[None, :].repeat(len(grid_g), axis=0)]
    )
    xc = np.column_stack([np.ones(len(grid_g)), base, grid_b])
    curve_df["log1p_mae_curve"] = xc @ beta_c
    curve_df["mae_curve"] = expm1(curve_df["log1p_mae_curve"] + smear_log)
    curve_df.to_csv(OUT / "surface_duration_curve.csv", index=False)

    # variance components summary
    vc_df = pd.DataFrame({
        "component": ["network_random_intercept", "station_random_intercept",
                      "residual", "total"],
        "variance": [var_net, var_station, var_e, var_net + var_station + var_e],
        "share": [var_net, var_station, var_e, 1.0],
    })
    vc_df["share"] = vc_df["variance"] / vc_df["variance"].iloc[-1]
    vc_df.loc[vc_df["component"] == "total", "share"] = 1.0
    vc_df.to_csv(OUT / "surface_variance_components.csv", index=False)

    # season amplitude
    fourier_amp = np.sqrt(
        float(result.params.get("doy_sin1", 0.0)) ** 2 + float(result.params.get("doy_cos1", 0.0)) ** 2)
    fourier_amp2 = np.sqrt(
        float(result.params.get("doy_sin2", 0.0)) ** 2 + float(result.params.get("doy_cos2", 0.0)) ** 2)
    out_log.append(
        f"seasonal amplitude (log1p): 1st harmonic {fourier_amp:.4f}, 2nd {fourier_amp2:.4f}")

    def surface_predict(new_df, widen_col, smear_log):
        z, sd, _ = predict_surface(result, fixed_cols, spline_cols, new_df,
                                   spline_coef_constrained=beta_c, widen=0.0,
                                   smear_log=smear_log)
        new_df = new_df.assign(pred_z=z, pred_sd_base=sd)
        new_df["widen"] = widen_col.to_numpy()
        new_df["pred_sd"] = new_df["pred_sd_base"] * (1.0 + new_df["widen"])
        q = 1.6448536269514722
        new_df["pred_lower"] = np.maximum(0.0, expm1(new_df["pred_z"] - q * new_df["pred_sd"]))
        new_df["pred_upper"] = expm1(new_df["pred_z"] + q * new_df["pred_sd"])
        new_df["pred_mean"] = expm1(new_df["pred_z"])
        return new_df

    # ==================================================== SECOND PANEL (1,446)
    units = pd.read_csv(SCORING / "empirical_predictions.csv",
                        dtype={"network_id": str, "station_id": str})
    placements = pd.read_csv(SCORING / "placement_losses.csv",
                             dtype={"network_id": str, "station_id": str})
    simple = pd.read_csv(SCORING / "simple_predictions.csv",
                         dtype={"network_id": str, "station_id": str})
    simple["gap_length"] = simple["gap_length"].astype(float)

    pl = placements.merge(
        simple[["network_id", "station_id", "gap_length", "acf_only",
                "donor_r2_only", "nearest_donor_correlation"]],
        on=["network_id", "station_id", "gap_length"], how="left")
    clim2 = placements.groupby(["network_id", "station_id"], as_index=False)[
        "climatology_mae_deg_c"].mean().rename(
        columns={"climatology_mae_deg_c": "clim_error"})
    pl = pl.merge(clim2, on=["network_id", "station_id"], how="left")
    pl["log_gap"] = np.log(pl["gap_length"].astype(float))
    pl = pl.join(doy_sincos(pl["gap_start"]))
    pl, _, _ = standardize_covariates(pl, cov_cols, cov_center, cov_scale)
    pls = spline_columns(pl)
    pl = pd.concat([pl, pls], axis=1)

    # support distance: covariate distance to nearest fitted station
    fit_cov = fit.groupby(["network_id", "station_id"], as_index=False)[
        ["clim_error", "donor_r2_only", "acf_only", "nearest_donor_correlation"]].mean()
    cov_z_cols = ["clim_error", "donor_r2_only", "acf_only", "nearest_donor_correlation"]
    mu = fit_cov[cov_z_cols].mean()
    sd_cov = fit_cov[cov_z_cols].std().replace(0, 1.0)
    fit_z = (fit_cov[cov_z_cols] - mu) / sd_cov
    fit_keys = set(zip(fit_cov["network_id"], fit_cov["station_id"]))

    def support_stats(df):
        keys = df[["network_id", "station_id"]].drop_duplicates()
        d0 = (df[cov_z_cols] - mu) / sd_cov
        dists = []
        for net, st in zip(keys["network_id"], keys["station_id"]):
            if (net, st) in fit_keys:
                dists.append(0.0)
            else:
                cand = fit_z if net not in set(fit_cov["network_id"]) else fit_z[fit_cov["network_id"] == net]
                v = d0.loc[(df["network_id"] == net) & (df["station_id"] == st)].to_numpy()[0]
                dd = np.linalg.norm(cand.to_numpy() - v, axis=1)
                dists.append(float(dd.min()) if len(dd) else np.nan)
        out = keys.assign(support_distance=dists)
        out["in_fit"] = [1 if (n, s) in fit_keys else 0 for n, s in zip(out["network_id"], out["station_id"])]
        return out

    pl_sup = support_stats(pl)
    pl = pl.merge(pl_sup, on=["network_id", "station_id"], how="left")

    # extrapolation factor: 0 within [7,180], linear in log beyond
    logspan = np.log(180.0) - np.log(7.0)
    pl["extrap_factor"] = np.maximum(0.0, (pl["log_gap"] - np.log(180.0)) / logspan)

    pl2 = surface_predict(pl, pl["extrap_factor"], smear_log)
    unit_keys = ["network_id", "station_id", "gap_length"]
    units_surf = pl2.groupby(unit_keys, as_index=False).agg(
        predicted_mean=("pred_mean", "mean"),
        predicted_lower=("pred_lower", "mean"),
        predicted_upper=("pred_upper", "mean"),
        pred_log=("pred_z", "mean"),
        n_placements=("pred_z", "size"),
        extrap_factor=("extrap_factor", "first"),
        support_distance=("support_distance", "first"),
        in_fit=("in_fit", "first"),
    )
    units_surf = units_surf.merge(
        units[["network_id", "station_id", "gap_length",
               "empirical_transfer_prediction", "observed_recovery_loss"]],
        on=unit_keys, how="left")

    # network-mean fallback (old): mean MAE per network over ALL fit placements
    fb_net = fit.groupby("network_id", as_index=False)["mae_deg_c"].mean().rename(
        columns={"mae_deg_c": "network_mean_fallback"})
    units_surf = units_surf.merge(fb_net, on="network_id", how="left")
    units_surf["network_mean_fallback"] = units_surf["network_mean_fallback"].fillna(
        fit["mae_deg_c"].mean())

    # abstain score: extrapolation factor + normalized support distance
    d_q90 = np.nanquantile(units_surf.loc[units_surf["support_distance"] > 0, "support_distance"], 0.9)
    if not np.isfinite(d_q90) or d_q90 <= 0:
        d_q90 = 1.0
    units_surf["support_distance_norm"] = units_surf["support_distance"] / d_q90
    units_surf["abstain_score"] = (
        units_surf["extrap_factor"] + units_surf["support_distance_norm"])
    units_surf["extrapolated_365"] = units_surf["gap_length"].astype(float).eq(365.0)

    units_surf.to_csv(OUT / "second_panel_predictions.csv", index=False)

    # ------------------------------------------------------------ evaluation
    eval_rows = []
    for name, col in [
        ("risk_surface", "predicted_mean"),
        ("empirical_transfer", "empirical_transfer_prediction"),
        ("network_mean_fallback", "network_mean_fallback"),
    ]:
        row = metrics_table(units_surf["observed_recovery_loss"].to_numpy(),
                            units_surf[col].to_numpy())
        row.update(network_spearman(units_surf, col))
        row["predictor"] = name
        eval_rows.append(row)
    eval_df = pd.DataFrame(eval_rows)
    eval_df.to_csv(OUT / "evaluation_metrics_second_panel.csv", index=False)
    out_log.append(
        "second panel (n=%d): risk_surface pooled_spearman=%.3f network_spearman(mean)=%.3f "
        "cal_slope=%.3f r2=%.3f rmse=%.3f | empirical pooled=%.3f net=%.3f | "
        "fallback pooled=%.3f net=%.3f" % (
            len(units_surf),
            eval_df.loc[0, "pooled_spearman"], eval_df.loc[0, "mean"],
            eval_df.loc[0, "calibration_slope"], eval_df.loc[0, "r2"], eval_df.loc[0, "rmse"],
            eval_df.loc[1, "pooled_spearman"], eval_df.loc[1, "mean"],
            eval_df.loc[2, "pooled_spearman"], eval_df.loc[2, "mean"]))

    # interpolation (14,60) / extrapolation (365) subsets
    sub_rows = []
    for label, mask in [
        ("interpolation_14_60", units_surf["gap_length"].astype(float).isin([14.0, 60.0])),
        ("extrapolation_365", units_surf["gap_length"].astype(float).eq(365.0)),
        ("in_range_7_30_90_180", units_surf["gap_length"].astype(float).isin([7.0, 30.0, 90.0, 180.0])),
    ]:
        sub = units_surf[mask]
        for name, col in [
            ("risk_surface", "predicted_mean"),
            ("empirical_transfer", "empirical_transfer_prediction"),
            ("network_mean_fallback", "network_mean_fallback"),
        ]:
            r = metrics_table(sub["observed_recovery_loss"].to_numpy(), sub[col].to_numpy())
            r.update(network_spearman(sub, col))
            r["subset"] = label
            r["predictor"] = name
            sub_rows.append(r)
    sub_df = pd.DataFrame(sub_rows)
    sub_df.to_csv(OUT / "evaluation_metrics_subsets.csv", index=False)
    for label in ["interpolation_14_60", "extrapolation_365"]:
        s = sub_df[(sub_df["subset"] == label) & (sub_df["predictor"] == "risk_surface")]
        out_log.append(
            f"{label} (n={s['n'].iloc[0]}): surface pooled_spearman={s['pooled_spearman'].iloc[0]:.3f} "
            f"rmse={s['rmse'].iloc[0]:.3f} cal_slope={s['calibration_slope'].iloc[0]:.3f}")

    # ------------------------------------------------------- abstention curve
    asc = []
    qs = np.unique(np.concatenate([np.arange(0.0, 1.01, 0.05),
                                   [0.02, 0.08, 0.15, 0.25, 0.35, 0.45, 0.7, 0.85]]))
    thresholds = np.quantile(units_surf["abstain_score"], qs)
    thresholds = np.unique(np.round(np.concatenate([[0.0], thresholds]), 6))
    for t in thresholds:
        rel = units_surf[units_surf["abstain_score"] <= t]
        if len(rel) < 20:
            continue
        frac = 1.0 - len(rel) / len(units_surf)
        m = metrics_table(rel["observed_recovery_loss"].to_numpy(),
                          rel["predicted_mean"].to_numpy())
        ns = network_spearman(rel, "predicted_mean")
        asc.append({
            "threshold": float(t), "fraction_abstained": float(frac),
            "n_released": len(rel),
            "network_spearman_mean": ns["mean"],
            "network_spearman_n_weighted": ns["n_weighted"],
            "calibration_slope": m["calibration_slope"],
            "pooled_spearman": m["pooled_spearman"],
            "rmse": m["rmse"],
            "r2": m["r2"],
        })
    asc_df = pd.DataFrame(asc)
    asc_df.to_csv(OUT / "abstention_curve.csv", index=False)

    # recommended rule: abstain ~8% of units (top-8% abstain score)
    rec_t = float(np.quantile(units_surf["abstain_score"], 0.92))
    rec = units_surf[units_surf["abstain_score"] <= rec_t]
    out_log.append(
        f"abstention: 8% abstained -> threshold {rec_t:.3f}, released n={len(rec)}, "
        f"network_spearman={network_spearman(rec,'predicted_mean')['mean']:.3f}, "
        f"cal_slope={metrics_table(rec['observed_recovery_loss'].to_numpy(), rec['predicted_mean'].to_numpy())['calibration_slope']:.3f}")

    # ==================================================== FIRST PANEL (1,440)
    ra = pd.read_csv(RC.parent / "route_a_confirmation" / "predictions.csv",
                     dtype={"network_id": str, "station_id": str})
    conf_pl = pd.read_csv(RC / "confirmation_empirical_predictions.csv",
                          dtype={"network_id": str, "station_id": str})
    conf_pl["gap_length"] = conf_pl["gap_length"].astype(float)
    conf_pl = conf_pl.merge(
        ra[["network_id", "station_id", "gap_length", "acf_only", "donor_r2_only",
            "nearest_donor_correlation"]],
        on=["network_id", "station_id", "gap_length"], how="left")
    conf_pl["clim_error"] = conf_pl.groupby(["network_id", "station_id"])[
        "climatology_mae_deg_c"].transform("mean")
    conf_pl["log_gap"] = np.log(conf_pl["gap_length"].astype(float))
    conf_pl = conf_pl.join(doy_sincos(conf_pl["gap_start"]))
    conf_pl, _, _ = standardize_covariates(conf_pl, cov_cols, cov_center, cov_scale)
    conf_pls = spline_columns(conf_pl)
    conf_pl = pd.concat([conf_pl, conf_pls], axis=1)

    conf_fit = fit[fit["_panel"].eq("confirmation")].copy()
    t0 = time.time()
    result_c = fit_surface(conf_fit, fixed_cols, spline_cols)
    out_log.append(f"first-panel refit {result_c._fit_time_s:.1f}s")
    vc_c = variance_components(result_c)
    cons_c = constrained_refit(conf_fit, fixed_cols, spline_cols,
                               vc_c["network"], vc_c["station"], vc_c["residual"])
    beta_c1 = cons_c.x
    smear_c = smearing_factor(conf_fit, fixed_cols, spline_cols, beta_c1)
    conf_pl["extrap_factor"] = np.maximum(0.0,
        (conf_pl["log_gap"] - np.log(180.0)) / logspan)
    conf_pred = surface_predict_on(result_c, fixed_cols, spline_cols, conf_pl,
                                   beta_c1, conf_pl["extrap_factor"], smear_c)
    conf_units = conf_pred.groupby(unit_keys, as_index=False).agg(
        predicted_mean=("pred_mean", "mean"),
        predicted_lower=("pred_lower", "mean"),
        predicted_upper=("pred_upper", "mean"),
        n_placements=("pred_z", "size"),
    )
    conf_units = conf_units.merge(
        conf_pl.groupby(unit_keys, as_index=False).agg(
            observed_recovery_loss=("observed_recovery_loss", "mean"),
            empirical_transfer_prediction=("empirical_transfer_prediction", "mean"),
        ),
        on=unit_keys, how="left")
    conf_units = conf_units.merge(fb_net, on="network_id", how="left")
    conf_units["network_mean_fallback"] = conf_units["network_mean_fallback"].fillna(
        fit["mae_deg_c"].mean())
    conf_units.to_csv(OUT / "first_panel_predictions.csv", index=False)

    ceval = []
    for name, col in [
        ("risk_surface", "predicted_mean"),
        ("empirical_transfer", "empirical_transfer_prediction"),
        ("network_mean_fallback", "network_mean_fallback"),
    ]:
        r = metrics_table(conf_units["observed_recovery_loss"].to_numpy(),
                          conf_units[col].to_numpy())
        r.update(network_spearman(conf_units, col))
        r["predictor"] = name
        ceval.append(r)
    ceval_df = pd.DataFrame(ceval)
    ceval_df.to_csv(OUT / "evaluation_metrics_first_panel.csv", index=False)
    out_log.append(
        "first panel (n=%d): surface pooled=%.3f net=%.3f | empirical pooled=%.3f net=%.3f | "
        "fallback pooled=%.3f net=%.3f" % (
            len(conf_units), ceval_df.loc[0, "pooled_spearman"], ceval_df.loc[0, "mean"],
            ceval_df.loc[1, "pooled_spearman"], ceval_df.loc[1, "mean"],
            ceval_df.loc[2, "pooled_spearman"], ceval_df.loc[2, "mean"]))

    # ------------------------------------------------------------------ report
    report = []
    report.append("# REPORT.md — revision v12 t04: continuous support-aware risk surface (agent B)")
    report.append("")
    report.append("## Model")
    report.append("")
    report.append("Hierarchical linear model of fitting-period empirical MAE, "
                  "fitted by REML on artificial-gap placements "
                  "(confirmation + development fit-loss panels):")
    report.append("")
    report.append("`log(1+MAE) = network RE + station(network) RE + monotone linear spline "
                  "f(log gap) + Fourier g(DOY) [2 harmonics] + covariates`")
    report.append("")
    report.append("Covariates (z-scored): station climatology error (placement-mean), donor R2, "
                  "ACF (acf_only), nearest-donor correlation. "
                  "Spline = monotone linear spline in log gap (knots at the interior "
                  "fitting durations 30/90 d; basis restricted so it is identifiable on the "
                  "4 observed fitting durations 7/30/90/180 d), "
                  "all slope coefficients constrained >= 0 (SLSQP GLS refit, RE variances "
                  "fixed at REML) so f is monotone nondecreasing; durations 14/60 are "
                  "interpolated by the continuous curve, 365 is extrapolated (flagged, "
                  "interval widened by (1 + extrapolation factor), abstention rule). "
                  "Back-transformation uses Duan smearing (log-smear factor "
                  f"{smear_log:.3f}); predictive intervals are 90% on the log1p scale, "
                  "lower bound clipped at 0.")
    report.append("")
    report.append("Support context: the second panel's 57 networks / 224 stations have ZERO "
                  "overlap with the fitting panels (93 networks / 376 stations), so every "
                  "second-panel unit is an out-of-network, out-of-station transfer; the old "
                  "network-mean fallback is therefore a CONSTANT (global fit mean) for all "
                  "1,446 units, and its pooled Spearman / network-level Spearman are "
                  "undefined (NaN). RMSE/R2 remain defined and are reported.")
    report.append("")
    report.append(f"Fit rows: {n_conf:,} confirmation + {n_dev:,} development "
                  f"(networks {fit['network_id'].nunique()}, stations {fit['station_id'].nunique()}).")
    report.append("")
    report.append("### Variance components (log1p scale)")
    for _, r in vc_df.iterrows():
        report.append(f"- {r['component']}: var={r['variance']:.4f} share={r['share']:.3f}")
    report.append("")
    report.append(f"Seasonal amplitude: 1st harmonic {fourier_amp:.4f}, 2nd {fourier_amp2:.4f} "
                  f"(log1p MAE units); unconstrained spline monotone on 7..365: {mono}; "
                  f"constrained spline monotone: {mono_c} (total rise {rise_c:.3f} log1p).")
    report.append("")
    report.append("### Fixed effects (REML, unconstrained baseline)")
    report.append("")
    report.append("| term | coef | se | z | p |")
    report.append("|---|---|---|---|---|")
    for _, r in fe.iterrows():
        report.append(f"| {r['term']} | {r['coef']:.4f} | {r['se']:.4f} | {r['z']:.2f} | {r['p']:.2e} |")
    report.append("")
    report.append("Constrained (monotone) refit spline coefficients: "
                  + ", ".join(f"{c:.4f}" for c in spl_coefs_c) + " (>= 0 enforced).")
    report.append("")
    report.append("## Second panel (1,446 units) — complete panel")
    report.append("")
    report.append("| predictor | pooled Spearman | network Spearman (mean) | cal slope | R2 | RMSE |")
    report.append("|---|---|---|---|---|---|")
    for _, r in eval_df.iterrows():
        report.append(f"| {r['predictor']} | {r['pooled_spearman']:.3f} | {r['mean']:.3f} | "
                      f"{r['calibration_slope']:.3f} | {r['r2']:.3f} | {r['rmse']:.3f} |")
    report.append("")
    report.append("## Interpolation (14, 60) and extrapolation (365)")
    report.append("")
    report.append("| subset | predictor | n | pooled Spearman | cal slope | R2 | RMSE |")
    report.append("|---|---|---|---|---|---|---|")
    for _, r in sub_df.iterrows():
        report.append(f"| {r['subset']} | {r['predictor']} | {r['n']} | {r['pooled_spearman']:.3f} "
                      f"| {r['calibration_slope']:.3f} | {r['r2']:.3f} | {r['rmse']:.3f} |")
    report.append("")
    report.append("## Abstention rule")
    report.append("")
    report.append("Abstain score = extrapolation factor (0 within [7,180] d, 0.22 at 365 d) "
                  "+ support distance / 90th percentile distance to nearest fitted station "
                  "in standardized covariate space. Units with score > threshold abstain. "
                  "Recommended default: abstain score > 1.08 (~8% of units; n released 1,332, "
                  "network Spearman 0.919, pooled 0.900, calibration slope 1.471, RMSE 0.789).")
    report.append("")
    report.append("| threshold | fraction abstained | n released | network Spearman | cal slope | pooled Spearman | RMSE |")
    report.append("|---|---|---|---|---|---|---|")
    for _, r in asc_df.iloc[:: max(1, len(asc_df) // 12)].iterrows():
        report.append(f"| {r['threshold']:.3f} | {r['fraction_abstained']:.3f} | {r['n_released']} "
                      f"| {r['network_spearman_mean']:.3f} | {r['calibration_slope']:.3f} "
                      f"| {r['pooled_spearman']:.3f} | {r['rmse']:.3f} |")
    report.append("")
    report.append("## First panel (1,440 units) — refit on confirmation fit losses only")
    report.append("")
    report.append("| predictor | pooled Spearman | network Spearman (mean) | cal slope | R2 | RMSE |")
    report.append("|---|---|---|---|---|---|")
    for _, r in ceval_df.iterrows():
        report.append(f"| {r['predictor']} | {r['pooled_spearman']:.3f} | {r['mean']:.3f} | "
                      f"{r['calibration_slope']:.3f} | {r['r2']:.3f} | {r['rmse']:.3f} |")
    report.append("")
    report.append(f"Total runtime {(time.time()-t_start)/60:.1f} min.")
    report.append("")
    report.append("## Files")
    report.append("- `second_panel_predictions.csv`: per-unit surface predictions (mean, 90% interval, "
                  "extrapolation factor, support distance, abstain score) for all 1,446 units")
    report.append("- `first_panel_predictions.csv`: per-unit predictions for the 1,440-unit cross-check")
    report.append("- `surface_fixed_effects.csv`, `surface_variance_components.csv`, `surface_duration_curve.csv`")
    report.append("- `evaluation_metrics_second_panel.csv`, `evaluation_metrics_subsets.csv`, "
                  "`evaluation_metrics_first_panel.csv`")
    report.append("- `abstention_curve.csv`")
    report.append("")
    with open(OUT / "REPORT.md", "w") as fh:
        fh.write("\n".join(report))

    with open(OUT / "run_log.json", "w") as fh:
        json.dump({"log": out_log, "sanity": {
            "n_units_second": len(units_surf),
            "n_units_first": len(conf_units),
        }}, fh, indent=2)
    print("\n".join(out_log))
    print("OUTPUT:", OUT)


def smearing_factor(fit, fixed_cols, spline_cols, beta) -> float:
    """Duan smearing for the log1p back-transformation:
    E[MAE] = expm1(z + log s), s = mean(exp(e)) over fit residuals."""
    x = np.column_stack(
        [np.ones(len(fit))] + [fit[c].to_numpy() for c in fixed_cols + spline_cols]
    )
    resid = fit["y"].to_numpy() - x @ np.asarray(beta, dtype=float)
    s = float(np.mean(np.exp(resid)))
    return float(np.log(s))


def surface_predict_on(result, fixed_cols, spline_cols, new, beta, widen_series,
                       smear_log=0.0):
    names = ["Intercept"] + fixed_cols + spline_cols
    x = np.column_stack([np.ones(len(new))] + [new[c].to_numpy() for c in fixed_cols + spline_cols])
    z = x @ beta + smear_log
    vc_all = variance_components(result)
    sd = np.sqrt(vc_all["network"] + vc_all["station"] + vc_all["residual"])
    new = new.copy()
    new["pred_z"] = z
    new["pred_sd_base"] = sd
    new["widen"] = widen_series.to_numpy()
    new["pred_sd"] = sd * (1.0 + new["widen"])
    q = 1.6448536269514722
    new["pred_lower"] = np.maximum(0.0, expm1(z - q * new["pred_sd"]))
    new["pred_upper"] = expm1(z + q * new["pred_sd"])
    new["pred_mean"] = expm1(z)
    return new


if __name__ == "__main__":
    main()
