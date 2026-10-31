"""Decision-time features of a TR case; no column derived from the hidden truth."""

from __future__ import annotations

import numpy as np
import pandas as pd

LAYERS = ("donor_ridge", "air_ridge", "linear_interp", "smooth_climatology", "doy_climatology")
QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
BASE = (
    "n_visible_donors", "donor_corr_mean", "total_missing", "missing_fraction", "n_runs", "longest_run",
    "warm_observed_fraction", "peak_overlap", "train_h30_sd", "n_complete_years", "law_sigma_a", "law_phi_a",
    "law_mu_r_warm", "law_sigma_r_warm", "law_phi_r", "law_peak_anomaly_mean", "law_peak_anomaly_sd",
    "air_gap_z_mean", "air_warm_z_mean", "visible_edge_anomaly", "estimator_disagreement",
    "daily_estimator_disagreement", "reconstructor_oof_daily_sd", "hist_reconstructor_oof_daily_bias",
    "hist_reconstructor_oof_daily_abs90", "hist_reconstructor_oof_lag1", "hist_historical_mask_h30_abs90",
    "hist_historical_mask_h30_bias", "law_mu_r_peak", "law_sigma_r_peak",
)


def hidden_share_moments(frame: pd.DataFrame) -> pd.DataFrame:
    """Moments of the hidden share of each training year's true peak window under this mask."""

    shares = frame.law_hidden_shares.fillna("").map(lambda text: np.array([float(v) for v in text.split(";") if v], dtype=float))
    return pd.DataFrame(
        {
            "law_hidden_mean": shares.map(lambda v: v.mean() if len(v) else np.nan),
            "law_hidden_sq_mean": shares.map(lambda v: (v**2).mean() if len(v) else np.nan),
            "law_hidden_any": shares.map(lambda v: (v > 0).mean() if len(v) else np.nan),
            "law_hidden_half": shares.map(lambda v: (v >= 0.5).mean() if len(v) else np.nan),
        },
        index=frame.index,
    )


def design_matrix(frame: pd.DataFrame, target: str = "h30", simulation: bool = True) -> pd.DataFrame:
    """Features relative to the delivered plug-in point so that models learn corrections."""

    point = frame[f"{target}__policy"]
    columns = {name: frame[name] for name in BASE if name in frame}
    columns.update(hidden_share_moments(frame))
    for layer in LAYERS:
        columns[f"layer_{layer}"] = frame.policy_choice.eq(layer).astype(float)
    columns["air_available"] = frame.air_available.astype(float)
    columns["clim_peak_minus_point"] = frame.clim_peak - frame.h30__policy
    columns["train_h30_minus_point"] = frame.train_h30_mean - frame.h30__policy
    for name in ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge", "air2stream3", "observed_days"):
        column = f"{target}__{name}"
        if column in frame:
            columns[f"{name}_minus_point"] = frame[column] - point
    if "observed_lower_bound__observed_days" in frame:
        columns["lower_bound_minus_point"] = frame["observed_lower_bound__observed_days"] - frame.h30__policy
    if simulation:
        if target == "h30":
            for prefix in ("state", "raw"):
                for q in QUANTILES:
                    column = f"{prefix}_h30_q{int(q * 100):02d}"
                    if column in frame:
                        columns[f"{column}_minus_point"] = frame[column] - point
                if f"{prefix}_h30_sd" in frame:
                    columns[f"{prefix}_h30_sd"] = frame[f"{prefix}_h30_sd"]
                if f"{prefix}_pfail_point_050" in frame:
                    columns[f"{prefix}_pfail_point_050"] = frame[f"{prefix}_pfail_point_050"]
        else:
            for suffix in ("q05", "q50", "q95"):
                column = f"state_{target}_{suffix}"
                if column in frame:
                    columns[f"{column}_minus_point"] = frame[column] - point
    return pd.DataFrame(columns, index=frame.index).astype(float)
