"""Plain fixed-model recovery scoring for open development networks.

Temperature values are split by calendar year: the first 70% of years are
used to fit one XGBoost model per target and information condition, and the
remaining years supply artificial outage truth.  The fitted models are reused
for every gap length and placement.  Outputs are ordinary replaceable tables.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from stream_recoverability.experiments.development_data import (
    joint_complete_feature_rosters,
)

GAP_LENGTHS = (7, 14, 30, 60, 90, 180, 365)
INFORMATION_CONDITIONS = (
    "B_union_D",
    "B_union_D_union_M_union_H",
)
METEOROLOGY_VARIABLES = ("Ta", "P", "W", "RH", "Rs")
HYDRAULICS_VARIABLES = ("F", "L")
XGBOOST_PARAMETERS = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "random_state": 0,
    "n_jobs": 1,
    "objective": "reg:squarederror",
    "verbosity": 0,
}


def read_temperature_panel(path: str) -> pd.DataFrame:
    """Read a daily wide temperature CSV and insert absent calendar days."""

    panel = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    panel = panel.apply(pd.to_numeric, errors="coerce").sort_index()
    daily_index = pd.date_range(panel.index.min(), panel.index.max(), freq="D")
    panel = panel.reindex(daily_index)
    panel.index.name = "date"
    return panel


def year_split(
    index: pd.DatetimeIndex, *, training_fraction: float = 0.7
) -> tuple[pd.Series, tuple[int, ...], tuple[int, ...]]:
    """Return a first-years training mask and the two year rosters."""

    years = tuple(int(value) for value in sorted(pd.unique(index.year)))
    cut = min(len(years) - 1, max(1, round(len(years) * training_fraction)))
    training_years = years[:cut]
    evaluation_years = years[cut:]
    mask = pd.Series(index.year.isin(training_years), index=index, dtype=bool)
    return mask, training_years, evaluation_years


def auxiliary_features(
    daily_long: pd.DataFrame | None,
    *,
    target_station: str,
    target_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Pivot naturally observed target-site meteorology and hydraulics.

    Meteorology uses finite NASA POWER provider values.  Hydraulics uses
    finite, naturally observed USGS values carrying Approved status.  No
    interpolation or backfilling is applied.
    """

    if daily_long is None:
        return pd.DataFrame(index=target_index)
    values = daily_long.loc[
        daily_long["site_id"].astype(str).eq(str(target_station))
        & daily_long["variable"].isin(
            (*METEOROLOGY_VARIABLES, *HYDRAULICS_VARIABLES)
        )
        & daily_long["natural_observed"].astype(bool)
    ].copy()
    values["value"] = pd.to_numeric(values["value"], errors="coerce")
    meteorology = values["variable"].isin(METEOROLOGY_VARIABLES)
    hydraulics = values["variable"].isin(HYDRAULICS_VARIABLES)
    values = values.loc[
        (
            meteorology
            & values["source"].eq("nasa_power_daily_point")
            & values["qc_status"].eq("provider_value")
        )
        | (
            hydraulics
            & values["approval_status"].eq("Approved")
            & values["quality_approved"].astype(bool)
            & values["qc_status"].isin(("approved", "approved_estimated"))
        )
    ]
    values["date"] = pd.to_datetime(values["date"])
    values["feature"] = np.where(
        values["variable"].isin(METEOROLOGY_VARIABLES),
        "M__" + values["variable"].astype(str),
        "H__" + values["variable"].astype(str),
    )
    return values.pivot(index="date", columns="feature", values="value").reindex(
        target_index
    )


def active_donors(
    panel: pd.DataFrame,
    *,
    target_station: str,
    train_mask: pd.Series,
    min_train_days: int,
) -> tuple[str, ...]:
    """Select donors with the declared minimum paired training observations."""

    target = panel[target_station].notna() & train_mask
    return tuple(
        str(column)
        for column in panel.columns
        if str(column) != str(target_station)
        and int((target & panel[column].notna()).sum()) >= min_train_days
    )


def _active_auxiliary_columns(
    features: pd.DataFrame,
    *,
    prefix: str,
    train_mask: pd.Series,
    min_train_days: int,
) -> tuple[str, ...]:
    return tuple(
        str(column)
        for column in features.columns
        if str(column).startswith(prefix)
        and int((features[column].notna() & train_mask).sum()) >= min_train_days
    )


def _seasonal_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    phase = 2.0 * np.pi * (index.dayofyear.to_numpy(dtype=float) - 1.0) / np.where(
        index.is_leap_year, 366.0, 365.0
    )
    return pd.DataFrame(
        {
            "doy_sin_1": np.sin(phase),
            "doy_cos_1": np.cos(phase),
            "doy_sin_2": np.sin(2.0 * phase),
            "doy_cos_2": np.cos(2.0 * phase),
            "doy_sin_3": np.sin(3.0 * phase),
            "doy_cos_3": np.cos(3.0 * phase),
        },
        index=index,
    )


def _model_frame(
    panel: pd.DataFrame,
    auxiliary: pd.DataFrame,
    *,
    target_station: str,
    donors: Sequence[str],
    meteorology: Sequence[str],
    hydraulics: Sequence[str],
    train_mask: pd.Series,
) -> pd.DataFrame:
    target_train = panel[target_station].where(train_mask)
    boundary = (target_train.shift(1) + target_train.shift(-1)) / 2.0
    features = _seasonal_features(panel.index)
    features["B__boundary_temperature"] = boundary
    for donor in donors:
        features[f"D__{donor}"] = panel[donor]
    for column in (*meteorology, *hydraulics):
        features[column] = auxiliary[column]
    return features


def _candidate_starts(
    panel: pd.DataFrame,
    auxiliary: pd.DataFrame,
    *,
    target_station: str,
    donors: Sequence[str],
    meteorology: Sequence[str],
    hydraulics: Sequence[str],
    evaluation_mask: pd.Series,
    gap_length: int,
) -> np.ndarray:
    target = panel[target_station].notna().to_numpy(dtype=bool)
    evaluation = evaluation_mask.to_numpy(dtype=bool)
    donor_all = panel[list(donors)].notna().all(axis=1).to_numpy(dtype=bool)
    met_all = (
        np.ones(len(panel), dtype=bool)
        if not meteorology
        else auxiliary[list(meteorology)].notna().all(axis=1).to_numpy(dtype=bool)
    )
    hydro_all = (
        np.ones(len(panel), dtype=bool)
        if not hydraulics
        else auxiliary[list(hydraulics)].notna().all(axis=1).to_numpy(dtype=bool)
    )
    window = np.ones(int(gap_length), dtype=int)
    complete = (
        np.convolve(target.astype(int), window, mode="valid") == gap_length
    )
    complete &= np.convolve(evaluation.astype(int), window, mode="valid") == gap_length
    complete &= np.convolve(donor_all.astype(int), window, mode="valid") == gap_length
    complete &= np.convolve(met_all.astype(int), window, mode="valid") == gap_length
    complete &= np.convolve(hydro_all.astype(int), window, mode="valid") == gap_length
    starts = np.arange(len(complete))
    bounded = (starts > 0) & (starts + gap_length < len(panel))
    bounded &= target[np.maximum(starts - 1, 0)]
    bounded &= target[np.minimum(starts + gap_length, len(panel) - 1)]
    return starts[complete & bounded]


def select_placements(candidates: Sequence[int], *, count: int) -> np.ndarray:
    """Select up to ``count`` placements evenly across eligible test windows."""

    starts = np.asarray(candidates, dtype=int)
    if len(starts) <= count:
        return starts
    positions = np.linspace(0, len(starts) - 1, num=count, dtype=int)
    return starts[positions]


def _boundary_values(target: pd.Series, start: int, gap_length: int) -> np.ndarray:
    left = float(target.iloc[start - 1])
    right = float(target.iloc[start + gap_length])
    fraction = np.arange(1, gap_length + 1, dtype=float) / (gap_length + 1.0)
    return left + fraction * (right - left)


def _climatology_prediction(
    target: pd.Series, train_mask: pd.Series, index: pd.DatetimeIndex
) -> np.ndarray:
    training = pd.DataFrame(
        {
            "day": target.index.dayofyear,
            "value": target.to_numpy(dtype=float),
        },
        index=target.index,
    ).loc[train_mask & target.notna()]
    day_values = training.groupby("day")["value"].median()
    fallback = float(training["value"].median())
    return day_values.reindex(index.dayofyear).fillna(fallback).to_numpy(dtype=float)


def station_gap_summary(placement_losses: pd.DataFrame) -> pd.DataFrame:
    """Collapse placement losses to the station-by-gap estimand."""

    keys = ["network_id", "station_id", "gap_length", "information_condition"]
    return (
        placement_losses.groupby(keys, as_index=False, sort=False)
        .agg(
            n_placements=("placement", "size"),
            observed_recovery_loss=("mae_deg_c", "mean"),
            placement_loss_sd=("mae_deg_c", "std"),
            median_mae_deg_c=("mae_deg_c", "median"),
            rmse_deg_c=("rmse_deg_c", "mean"),
            climatology_mae_deg_c=("climatology_mae_deg_c", "mean"),
            achieved_skill=("achieved_skill", "mean"),
            first_gap_start=("gap_start", "min"),
            last_gap_end=("gap_end", "max"),
        )
        .sort_values(keys)
        .reset_index(drop=True)
    )


def score_network(
    network_id: str,
    temperature_panel: pd.DataFrame,
    daily_long_auxiliary: pd.DataFrame | None,
    *,
    target_stations: Sequence[str] | None = None,
    gap_lengths: Sequence[int] = GAP_LENGTHS,
    placements_per_gap: int = 20,
    min_train_days: int = 365,
    training_fraction: float = 0.7,
    xgboost_parameters: Mapping[str, object] = XGBOOST_PARAMETERS,
) -> dict[str, pd.DataFrame]:
    """Fit fixed XGBoost models and score artificial test-period gaps."""

    panel = temperature_panel.copy().sort_index()
    daily_index = pd.date_range(panel.index.min(), panel.index.max(), freq="D")
    panel = panel.reindex(daily_index)
    panel.index.name = "date"
    panel.columns = panel.columns.astype(str)
    train_mask, training_years, evaluation_years = year_split(
        panel.index, training_fraction=training_fraction
    )
    evaluation_mask = ~train_mask
    targets = tuple(panel.columns) if target_stations is None else tuple(target_stations)
    placement_rows: list[dict[str, object]] = []
    eligibility_rows: list[dict[str, object]] = []

    for target in targets:
        auxiliaries = auxiliary_features(
            daily_long_auxiliary,
            target_station=str(target),
            target_index=panel.index,
        )
        fitting_frame = panel.loc[train_mask].join(auxiliaries.loc[train_mask])
        donors, meteorology, hydraulics = joint_complete_feature_rosters(
            fitting_frame,
            target=str(target),
            donor_candidates=tuple(
                str(column) for column in panel.columns if str(column) != str(target)
            ),
            meteorology_candidates=tuple(
                f"M__{variable}"
                for variable in METEOROLOGY_VARIABLES
                if f"M__{variable}" in auxiliaries
            ),
            hydraulics_candidates=tuple(
                f"H__{variable}"
                for variable in HYDRAULICS_VARIABLES
                if f"H__{variable}" in auxiliaries
            ),
            min_pairs=min_train_days,
        )
        train_target_days = int((train_mask & panel[target].notna()).sum())
        base_qualified = train_target_days >= min_train_days and len(donors) > 0
        full_qualified = base_qualified and len(meteorology) > 0 and len(hydraulics) > 0
        base_reason = (
            "eligible"
            if base_qualified
            else "insufficient_training_target_days"
            if train_target_days < min_train_days
            else "no_donor_with_minimum_paired_training_days"
        )
        full_reason = (
            "eligible"
            if full_qualified
            else base_reason
            if not base_qualified
            else "no_meteorology_with_minimum_training_days"
            if not meteorology
            else "no_hydraulics_with_minimum_training_days"
        )
        condition_columns = {
            "B_union_D": ((), ()),
            "B_union_D_union_M_union_H": (meteorology, hydraulics),
        }
        condition_qualified = {
            "B_union_D": base_qualified,
            "B_union_D_union_M_union_H": full_qualified,
        }
        condition_reason = {
            "B_union_D": base_reason,
            "B_union_D_union_M_union_H": full_reason,
        }
        models: dict[str, XGBRegressor] = {}
        frames: dict[str, pd.DataFrame] = {}
        for condition in INFORMATION_CONDITIONS:
            if condition_qualified[condition]:
                met_columns, hydro_columns = condition_columns[condition]
                frame = _model_frame(
                    panel,
                    auxiliaries,
                    target_station=str(target),
                    donors=donors,
                    meteorology=met_columns,
                    hydraulics=hydro_columns,
                    train_mask=train_mask,
                )
                fitting = train_mask & panel[target].notna()
                model = XGBRegressor(**dict(xgboost_parameters))
                model.fit(frame.loc[fitting], panel.loc[fitting, target])
                frames[condition] = frame
                models[condition] = model

        climatology = _climatology_prediction(panel[target], train_mask, panel.index)
        for gap_length in (int(value) for value in gap_lengths):
            candidates: dict[str, np.ndarray] = {}
            for condition in INFORMATION_CONDITIONS:
                met_columns, hydro_columns = condition_columns[condition]
                candidates[condition] = (
                    _candidate_starts(
                        panel,
                        auxiliaries,
                        target_station=str(target),
                        donors=donors,
                        meteorology=met_columns,
                        hydraulics=hydro_columns,
                        evaluation_mask=evaluation_mask,
                        gap_length=gap_length,
                    )
                    if condition_qualified[condition]
                    else np.asarray([], dtype=int)
                )
            if full_qualified:
                common = np.intersect1d(
                    candidates["B_union_D"],
                    candidates["B_union_D_union_M_union_H"],
                )
                selected = select_placements(common, count=placements_per_gap)
                selected_by_condition = {
                    condition: selected for condition in INFORMATION_CONDITIONS
                }
            else:
                selected_by_condition = {
                    "B_union_D": select_placements(
                        candidates["B_union_D"], count=placements_per_gap
                    ),
                    "B_union_D_union_M_union_H": np.asarray([], dtype=int),
                }

            for condition in INFORMATION_CONDITIONS:
                selected = selected_by_condition[condition]
                reason = condition_reason[condition]
                if condition_qualified[condition] and not len(selected):
                    reason = "no_eligible_evaluation_windows"
                eligibility_rows.append(
                    {
                        "network_id": str(network_id),
                        "station_id": str(target),
                        "gap_length": gap_length,
                        "information_condition": condition,
                        "eligible": bool(condition_qualified[condition] and len(selected)),
                        "reason": reason,
                        "train_target_days": train_target_days,
                        "donor_feature_count": len(donors),
                        "meteorology_feature_count": len(meteorology),
                        "hydraulics_feature_count": len(hydraulics),
                        "meteorology_feature_ids": "|".join(
                            column.removeprefix("M__") for column in meteorology
                        ),
                        "hydraulics_feature_ids": "|".join(
                            column.removeprefix("H__") for column in hydraulics
                        ),
                        "candidate_windows": len(candidates[condition]),
                        "selected_placements": len(selected),
                    }
                )
                for placement, start in enumerate(selected):
                    stop = int(start) + gap_length
                    prediction_frame = frames[condition].iloc[start:stop].copy()
                    prediction_frame["B__boundary_temperature"] = _boundary_values(
                        panel[target], int(start), gap_length
                    )
                    prediction = models[condition].predict(prediction_frame)
                    truth = panel[target].iloc[start:stop].to_numpy(dtype=float)
                    climate = climatology[start:stop]
                    mae = float(np.mean(np.abs(prediction - truth)))
                    rmse = float(np.sqrt(np.mean(np.square(prediction - truth))))
                    climate_mae = float(np.mean(np.abs(climate - truth)))
                    placement_rows.append(
                        {
                            "network_id": str(network_id),
                            "station_id": str(target),
                            "gap_length": gap_length,
                            "placement": placement,
                            "gap_start": panel.index[start],
                            "gap_end": panel.index[stop - 1],
                            "information_condition": condition,
                            "model": "xgboost",
                            "n_scored": gap_length,
                            "mae_deg_c": mae,
                            "rmse_deg_c": rmse,
                            "climatology_mae_deg_c": climate_mae,
                            "achieved_skill": (
                                float("nan")
                                if climate_mae == 0.0
                                else 1.0 - mae / climate_mae
                            ),
                            "observed_recovery_loss": mae,
                            "training_years": "|".join(map(str, training_years)),
                            "evaluation_years": "|".join(map(str, evaluation_years)),
                            "donor_station_ids": "|".join(donors),
                            "meteorology_feature_count": len(meteorology),
                            "hydraulics_feature_count": len(hydraulics),
                            "meteorology_feature_ids": "|".join(
                                column.removeprefix("M__") for column in meteorology
                            ),
                            "hydraulics_feature_ids": "|".join(
                                column.removeprefix("H__") for column in hydraulics
                            ),
                        }
                    )

    placement_losses = pd.DataFrame(placement_rows)
    eligibility = pd.DataFrame(eligibility_rows)
    summary = station_gap_summary(placement_losses) if len(placement_losses) else pd.DataFrame()
    return {
        "placement_losses": placement_losses,
        "station_gap_summary": summary,
        "eligibility": eligibility,
    }


__all__ = [
    "GAP_LENGTHS",
    "INFORMATION_CONDITIONS",
    "XGBOOST_PARAMETERS",
    "active_donors",
    "auxiliary_features",
    "read_temperature_panel",
    "score_network",
    "select_placements",
    "station_gap_summary",
    "year_split",
]
