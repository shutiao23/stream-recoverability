"""Benefit predictors, including the identity between diff and seasonal empirical means."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

from stream_recoverability.experiments.recovery_roster import season_label


def _keys(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["network_id"] = out["network_id"].astype(str)
    out["station_id"] = out["station_id"].astype(str)
    if "season" not in out.columns:
        out["season"] = season_label(out["gap_start"])
    return out


def hierarchical_mean(
    history: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    value_col: str,
    name: str,
) -> pd.DataFrame:
    """Station×duration×season mean with station, network, and global fallbacks."""

    history = _keys(history)
    result = _keys(evaluation).reset_index(drop=True)
    levels = [
        (["network_id", "station_id", "gap_length", "season"], f"{name}_station_season"),
        (["network_id", "station_id", "gap_length"], f"{name}_station"),
        (["network_id", "gap_length", "season"], f"{name}_network_season"),
        (["network_id", "gap_length"], f"{name}_network"),
        (["gap_length"], f"{name}_global"),
    ]
    filled = np.full(len(result), np.nan)
    source = np.array(["unavailable"] * len(result), dtype=object)
    for keys, label in levels:
        means = history.groupby(keys, as_index=False)[value_col].mean().rename(
            columns={value_col: "_mapped"}
        )
        mapped = result[keys].merge(means, on=keys, how="left")["_mapped"].to_numpy(dtype=float)
        pick = np.isnan(filled) & np.isfinite(mapped)
        filled[pick] = mapped[pick]
        source[pick] = label
    result[name] = filled
    result[f"{name}_source"] = source
    result[f"{name}_supported"] = np.isin(
        source,
        (f"{name}_station_season", f"{name}_station", f"{name}_network_season"),
    )
    return result


def difference_identity_gap(frame: pd.DataFrame) -> float:
    """Max |diff - (default_difficulty - risk)| on rows where both terms exist."""

    if frame.empty:
        return float("nan")
    gap = (
        frame["diff_prediction"]
        - (frame["default_difficulty_prediction"] - frame["risk_prediction"])
    ).abs()
    return float(gap.max())


def attach_component_predictors(
    history: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    model_mae_col: str = "mae_deg_c",
    climatology_mae_col: str = "climatology_mae_deg_c",
) -> pd.DataFrame:
    """Build diff, risk, default_difficulty, r6-diff, and seasonal empirical benefit."""

    hist = _keys(history)
    hist["realized_benefit"] = hist[climatology_mae_col] - hist[model_mae_col]
    result = hierarchical_mean(hist, evaluation, value_col="realized_benefit", name="seasonal_empirical")
    result = hierarchical_mean(hist, result, value_col=model_mae_col, name="risk_prediction")
    result = hierarchical_mean(
        hist, result, value_col=climatology_mae_col, name="default_difficulty_prediction"
    )
    result["diff_prediction"] = (
        result["default_difficulty_prediction"] - result["risk_prediction"]
    )
    result["neg_risk_prediction"] = -result["risk_prediction"]
    hist_r6 = hist.copy()
    hist_r6["season"] = "all"
    ev_r6 = result.copy()
    ev_r6["season"] = "all"
    r6 = hierarchical_mean(
        hist_r6,
        ev_r6,
        value_col="realized_benefit",
        name="r6_diff_prediction",
    )
    result["r6_diff_prediction"] = r6["r6_diff_prediction"]
    result["r6_diff_prediction_supported"] = r6["r6_diff_prediction_supported"]
    result["diff_minus_empirical"] = result["diff_prediction"] - result["seasonal_empirical"]
    if "realized_benefit" not in result.columns and model_mae_col in result.columns:
        result["realized_benefit"] = result[climatology_mae_col] - result[model_mae_col]
    return result


def history_switch_rule(
    history: pd.DataFrame,
    *,
    model_mae_col: str = "mae_deg_c",
    climatology_mae_col: str = "climatology_mae_deg_c",
) -> pd.DataFrame:
    """Pick default_difficulty vs -risk per duration using historical prediction MAE."""

    hist = _keys(history)
    hist["realized_benefit"] = hist[climatology_mae_col] - hist[model_mae_col]
    rows: list[dict[str, object]] = []
    for gap, group in hist.groupby("gap_length"):
        # leave-one-network-out would be heavier; here we use cell means vs realized.
        difficulty = group[climatology_mae_col].mean()
        # Per-row predictors are the station-season means excluding the row's exact match
        # is overkill; compare which constant-per-gap term has lower MAE on history.
        mae_diff = float(np.mean(np.abs(group["realized_benefit"] - difficulty)))
        mae_risk = float(np.mean(np.abs(group["realized_benefit"] - (-group[model_mae_col]))))
        # Use hierarchical station-season means computed without leakage via groupby transform
        station_clim = group.groupby(["station_id", "season"])[climatology_mae_col].transform("mean")
        station_model = group.groupby(["station_id", "season"])[model_mae_col].transform("mean")
        mae_clim = float(np.mean(np.abs(group["realized_benefit"] - station_clim)))
        mae_neg = float(np.mean(np.abs(group["realized_benefit"] - (-station_model))))
        choice = "default_difficulty" if mae_clim <= mae_neg else "neg_risk"
        rows.append(
            {
                "gap_length": int(gap),
                "chosen": choice,
                "mae_default_difficulty": mae_clim,
                "mae_neg_risk": mae_neg,
                "mae_gap_constant_difficulty": mae_diff,
                "mae_raw_neg_model": mae_risk,
            }
        )
    return pd.DataFrame(rows)


def apply_switch(
    evaluation: pd.DataFrame,
    switch: pd.DataFrame,
) -> pd.Series:
    chosen = dict(zip(switch["gap_length"].astype(int), switch["chosen"].astype(str)))
    values = []
    for row in evaluation.itertuples(index=False):
        pick = chosen.get(int(row.gap_length), "default_difficulty")
        if pick == "neg_risk":
            values.append(float(row.neg_risk_prediction))
        else:
            values.append(float(row.default_difficulty_prediction))
    return pd.Series(values, index=evaluation.index, name="switch_prediction")


def ridge_benefit_predictor(
    history: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    benefit_col: str = "realized_benefit",
) -> pd.Series:
    """Same visible covariates: duration, season, station mean historical benefit."""

    hist = _keys(history)
    ev = _keys(evaluation)
    if benefit_col not in hist.columns:
        hist[benefit_col] = hist["climatology_mae_deg_c"] - hist["mae_deg_c"]
    station_mean = hist.groupby(["network_id", "station_id"])[benefit_col].mean()
    hist = hist.merge(
        station_mean.rename("station_mean_benefit"),
        left_on=["network_id", "station_id"],
        right_index=True,
        how="left",
    )
    ev = ev.merge(
        station_mean.rename("station_mean_benefit"),
        left_on=["network_id", "station_id"],
        right_index=True,
        how="left",
    )
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    seasons_train = encoder.fit_transform(hist[["season"]])
    seasons_test = encoder.transform(ev[["season"]])
    x_train = np.column_stack(
        [
            np.log(hist["gap_length"].to_numpy(dtype=float)),
            hist["gap_length"].to_numpy(dtype=float),
            hist["station_mean_benefit"].to_numpy(dtype=float),
            seasons_train,
        ]
    )
    y = hist[benefit_col].to_numpy(dtype=float)
    ok = np.isfinite(x_train).all(axis=1) & np.isfinite(y)
    model = Ridge(alpha=1.0)
    model.fit(x_train[ok], y[ok])
    x_test = np.column_stack(
        [
            np.log(ev["gap_length"].to_numpy(dtype=float)),
            ev["gap_length"].to_numpy(dtype=float),
            ev["station_mean_benefit"].fillna(float(np.nanmean(y[ok]))).to_numpy(dtype=float),
            seasons_test,
        ]
    )
    pred = model.predict(x_test)
    return pd.Series(pred, index=evaluation.index, name="ridge_covariate_prediction")


def predictor_columns() -> Sequence[str]:
    return (
        "diff_prediction",
        "r6_diff_prediction",
        "default_difficulty_prediction",
        "neg_risk_prediction",
        "seasonal_empirical",
        "switch_prediction",
        "ridge_covariate_prediction",
    )
