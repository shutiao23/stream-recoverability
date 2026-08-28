"""Recovery-model roster and fitting-period empirical-transfer baseline.

The original v11 outcome used one gradient-boosting model.  This module adds
two deliberately different, inexpensive families on exactly the same gaps:
a seasonal/boundary regression and a ridge-stabilized donor BLUP.  It also
constructs an empirical loss curve inside the fitting years by fitting the
frozen XGBoost family on early fitting years and scoring artificial gaps in
later fitting years.  Evaluation years are never used to build that curve.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from stream_recoverability.experiments.development_recovery import (
    XGBOOST_PARAMETERS,
    _boundary_values,
    _candidate_starts,
    _model_frame,
    select_placements,
    year_split,
)


MODEL_FAMILIES = (
    "xgboost_b_d",
    "seasonal_boundary_ridge",
    "donor_blup_ridge",
)


def season_label(dates: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Meteorological season labels in fixed DJF/MAM/JJA/SON order."""

    months = pd.DatetimeIndex(pd.to_datetime(dates)).month
    return np.select(
        [months.isin([12, 1, 2]), months.isin([3, 4, 5]), months.isin([6, 7, 8])],
        ["DJF", "MAM", "JJA"],
        default="SON",
    )


def _normalise_station(value: object, columns: pd.Index) -> str:
    station = str(value)
    if station in columns:
        return station
    if station.replace(".0", "").isdigit():
        numeric = station.replace(".0", "")
        widths = sorted({len(str(column)) for column in columns}, reverse=True)
        for width in widths:
            candidate = numeric.zfill(width)
            if candidate in columns:
                return candidate
    raise KeyError(f"station {value!r} is absent from the temperature panel")


def _ridge_model(frame: pd.DataFrame, target: pd.Series, mask: pd.Series) -> object:
    usable = mask & target.notna()
    if int(usable.sum()) <= max(30, frame.shape[1] + 5):
        raise ValueError("insufficient complete fitting rows for ridge model")
    model = make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0)
    )
    model.fit(frame.loc[usable], target.loc[usable])
    return model


def score_model_roster_on_placements(
    network_id: str,
    panel: pd.DataFrame,
    placements: pd.DataFrame,
) -> pd.DataFrame:
    """Score two additional model families on an existing XGBoost gap roster."""

    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    train_mask, training_years, evaluation_years = year_split(daily.index)
    rows: list[dict[str, object]] = []
    selected = placements.loc[
        placements["network_id"].astype(str).eq(str(network_id))
        & placements["information_condition"].eq("B_union_D")
    ].copy()
    selected["gap_start"] = pd.to_datetime(selected["gap_start"])
    for raw_station, station_rows in selected.groupby("station_id", sort=False):
        station = _normalise_station(raw_station, daily.columns)
        donor_text = str(station_rows["donor_station_ids"].iloc[0])
        donors = tuple(
            _normalise_station(value, daily.columns)
            for value in donor_text.split("|")
            if value and value != "nan"
        )
        empty_aux = pd.DataFrame(index=daily.index)
        seasonal = _model_frame(
            daily,
            empty_aux,
            target_station=station,
            donors=(),
            meteorology=(),
            hydraulics=(),
            train_mask=train_mask,
        )
        donor_frame = _model_frame(
            daily,
            empty_aux,
            target_station=station,
            donors=donors,
            meteorology=(),
            hydraulics=(),
            train_mask=train_mask,
        )
        models = {
            "seasonal_boundary_ridge": (_ridge_model(seasonal, daily[station], train_mask), seasonal),
            "donor_blup_ridge": (_ridge_model(donor_frame, daily[station], train_mask), donor_frame),
        }
        for placement in station_rows.itertuples(index=False):
            start = daily.index.get_indexer([pd.Timestamp(placement.gap_start)])[0]
            gap = int(placement.gap_length)
            if start < 1 or start + gap >= len(daily):
                continue
            truth = daily[station].iloc[start : start + gap].to_numpy(dtype=float)
            if not np.isfinite(truth).all():
                continue
            for family, (model, frame) in models.items():
                prediction_frame = frame.iloc[start : start + gap].copy()
                prediction_frame["B__boundary_temperature"] = _boundary_values(
                    daily[station], start, gap
                )
                if prediction_frame.isna().any(axis=None):
                    continue
                predicted = model.predict(prediction_frame)
                rows.append(
                    {
                        "network_id": str(network_id),
                        "station_id": station,
                        "gap_length": gap,
                        "placement": int(placement.placement),
                        "gap_start": pd.Timestamp(placement.gap_start),
                        "season": season_label([placement.gap_start])[0],
                        "model_family": family,
                        "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                        "rmse_deg_c": float(np.sqrt(np.mean(np.square(predicted - truth)))),
                        "training_years": "|".join(map(str, training_years)),
                        "evaluation_years": "|".join(map(str, evaluation_years)),
                    }
                )
    return pd.DataFrame(rows)


def fitting_period_empirical_losses(
    network_id: str,
    panel: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    gaps: Sequence[int] = (7, 30, 90, 180),
    placements_per_season: int = 20,
    min_train_days: int = 365,
    xgboost_parameters: Mapping[str, object] = XGBOOST_PARAMETERS,
) -> pd.DataFrame:
    """Score stratified artificial gaps wholly inside the fitting period.

    The outer 70/30 year split remains untouched.  Inside its fitting years,
    the first 70% of years fit XGBoost and the remaining years supply observed
    artificial-gap truth.  Thus empirical-transfer errors are available before
    the outer evaluation period begins.
    """

    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    outer_train, outer_training_years, _ = year_split(daily.index)
    training_index = daily.index[outer_train]
    inner_relative, inner_fit_years, inner_score_years = year_split(training_index)
    inner_fit = pd.Series(False, index=daily.index)
    inner_fit.loc[training_index] = inner_relative.to_numpy(dtype=bool)
    inner_score = outer_train & ~inner_fit
    rows: list[dict[str, object]] = []
    network_rows = placements.loc[
        placements["network_id"].astype(str).eq(str(network_id))
        & placements["information_condition"].eq("B_union_D")
    ]
    for raw_station, station_rows in network_rows.groupby("station_id", sort=False):
        station = _normalise_station(raw_station, daily.columns)
        donor_text = str(station_rows["donor_station_ids"].iloc[0])
        donors = tuple(
            _normalise_station(value, daily.columns)
            for value in donor_text.split("|")
            if value and value != "nan"
        )
        if not donors or int((inner_fit & daily[station].notna()).sum()) < min_train_days:
            continue
        empty_aux = pd.DataFrame(index=daily.index)
        frame = _model_frame(
            daily,
            empty_aux,
            target_station=station,
            donors=donors,
            meteorology=(),
            hydraulics=(),
            train_mask=inner_fit,
        )
        fit_rows = inner_fit & daily[station].notna()
        model = XGBRegressor(**dict(xgboost_parameters))
        model.fit(frame.loc[fit_rows], daily.loc[fit_rows, station])
        for gap in (int(value) for value in gaps):
            candidates = _candidate_starts(
                daily,
                empty_aux,
                target_station=station,
                donors=donors,
                meteorology=(),
                hydraulics=(),
                evaluation_mask=inner_score,
                gap_length=gap,
            )
            if not len(candidates):
                continue
            starts_frame = pd.DataFrame(
                {
                    "start": candidates,
                    "date": daily.index[candidates],
                    "season": season_label(daily.index[candidates]),
                }
            )
            for season, candidates_by_season in starts_frame.groupby("season"):
                chosen = select_placements(
                    candidates_by_season["start"].to_numpy(dtype=int),
                    count=placements_per_season,
                )
                for placement, start in enumerate(chosen):
                    prediction_frame = frame.iloc[start : start + gap].copy()
                    prediction_frame["B__boundary_temperature"] = _boundary_values(
                        daily[station], int(start), gap
                    )
                    if prediction_frame.isna().any(axis=None):
                        continue
                    truth = daily[station].iloc[start : start + gap].to_numpy(dtype=float)
                    predicted = model.predict(prediction_frame)
                    rows.append(
                        {
                            "network_id": str(network_id),
                            "station_id": station,
                            "gap_length": gap,
                            "season": str(season),
                            "placement": placement,
                            "gap_start": daily.index[start],
                            "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                            "model_family": "xgboost_b_d",
                            "outer_training_years": "|".join(
                                map(str, outer_training_years)
                            ),
                            "inner_fit_years": "|".join(map(str, inner_fit_years)),
                            "inner_score_years": "|".join(
                                map(str, inner_score_years)
                            ),
                        }
                    )
    return pd.DataFrame(rows)


def empirical_transfer_predictions(
    empirical_losses: pd.DataFrame,
    evaluation_placements: pd.DataFrame,
) -> pd.DataFrame:
    """Map fitting-period gap-by-season curves to outer evaluation placements."""

    curve = (
        empirical_losses.groupby(
            ["network_id", "station_id", "gap_length", "season"], as_index=False
        )["mae_deg_c"]
        .mean()
        .rename(columns={"mae_deg_c": "empirical_transfer_prediction"})
    )
    fallback_station = (
        empirical_losses.groupby(
            ["network_id", "station_id", "gap_length"], as_index=False
        )["mae_deg_c"]
        .mean()
        .rename(columns={"mae_deg_c": "_station_gap_fallback"})
    )
    fallback_network = (
        empirical_losses.groupby(["network_id", "gap_length"], as_index=False)[
            "mae_deg_c"
        ]
        .mean()
        .rename(columns={"mae_deg_c": "_network_gap_fallback"})
    )
    evaluation = evaluation_placements.loc[
        evaluation_placements["information_condition"].eq("B_union_D")
    ].copy()
    evaluation["station_id"] = evaluation["station_id"].astype(str)
    evaluation["season"] = season_label(evaluation["gap_start"])
    result = evaluation.merge(
        curve,
        on=["network_id", "station_id", "gap_length", "season"],
        how="left",
    ).merge(
        fallback_station,
        on=["network_id", "station_id", "gap_length"],
        how="left",
    ).merge(
        fallback_network,
        on=["network_id", "gap_length"],
        how="left",
    )
    result["empirical_transfer_source"] = np.select(
        [
            result["empirical_transfer_prediction"].notna(),
            result["_station_gap_fallback"].notna(),
        ],
        ["station_gap_season", "station_gap"],
        default="network_gap",
    )
    result["empirical_transfer_prediction"] = (
        result["empirical_transfer_prediction"]
        .fillna(result["_station_gap_fallback"])
        .fillna(result["_network_gap_fallback"])
    )
    return result.drop(columns=["_station_gap_fallback", "_network_gap_fallback"])


__all__ = [
    "MODEL_FAMILIES",
    "empirical_transfer_predictions",
    "fitting_period_empirical_losses",
    "score_model_roster_on_placements",
    "season_label",
]
