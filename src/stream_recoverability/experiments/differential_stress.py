"""Differential (incremental-benefit) stress losses for default handling.

v14 P0: the historical block stress test is applied to both the recovery
model and the default handling method it would replace (climatology,
linear interpolation).  The target estimand changes from "model MAE" to the
per-placement incremental benefit

    benefit = MAE(default handling) - MAE(model)

which is positive when reconstruction beats the default and negative when
it is actively harmful relative to doing nothing.

The fitting-period model losses (inner year split) already exist as archived
artifacts; this module only needs to score the default handlers on the very
same inner artificial-gap geometry and to difference the two.  The transfer
machinery in ``recovery_roster.empirical_transfer_predictions`` is generic
over its loss column, so a benefit frame with the same schema as the
archived fit losses can be fed into it unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.development_recovery import (
    _boundary_values,
    _candidate_starts,
    _climatology_prediction,
    year_split,
)
from stream_recoverability.experiments.recovery_roster import (
    season_label,
    select_placements,
)

DEFAULT_HANDLERS = ("climatology", "linear_interp")

# nofill (gap days dropped) has no MAE; it is meaningful only at the
# downstream-metric level and is deliberately out of scope here (P4).
_GEOMETRY_KEYS = (
    "network_id",
    "station_id",
    "gap_length",
    "season",
    "placement",
    "gap_start",
)


def handler_prediction(
    handler: str,
    target: pd.Series,
    *,
    start: int,
    gap_length: int,
    train_mask: pd.Series,
) -> np.ndarray:
    """Return the point reconstruction of a default handler over one gap.

    ``climatology`` estimates day-of-year medians on ``train_mask`` only
    (never the scored window); ``linear_interp`` is parameter-free,
    interpolating between the two flanking observed values.
    """

    if handler == "climatology":
        return _climatology_prediction(target, train_mask, target.index)[
            start : start + gap_length
        ]
    if handler == "linear_interp":
        return _boundary_values(target, int(start), int(gap_length))
    raise ValueError(f"unknown default handler {handler!r}")


def _inner_fit_mask(
    daily_index: pd.DatetimeIndex, inner_fit_years: str
) -> pd.Series:
    years = tuple(
        int(value) for value in str(inner_fit_years).split("|") if value != "nan"
    )
    if not years:
        raise ValueError("empty inner_fit_years roster")
    return pd.Series(daily_index.year.isin(years), index=daily_index, dtype=bool)


def _as_string_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ("network_id", "station_id"):
        if column in result.columns:
            result[column] = result[column].astype(str)
    return result


def _replay_default_rows(
    network_id: str,
    panel: pd.DataFrame,
    fit_losses: pd.DataFrame,
    *,
    handler: str,
) -> pd.DataFrame:
    """Score ``handler`` on the archived inner-fit placement geometry.

    The archived fit losses already record the deterministic inner
    (station, gap_length, season, placement, gap_start) geometry and the
    inner year split.  We replay the same windows against the same panel and
    replace the XGBoost MAE with the handler MAE, so the model and default
    sides are paired by construction.
    """

    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    rows: list[dict[str, object]] = []
    for raw_station, station_rows in fit_losses.groupby(
        "station_id", sort=False, dropna=False
    ):
        station = str(raw_station)
        if station not in daily.columns:
            continue
        split_values = station_rows["inner_fit_years"].dropna().unique()
        if not len(split_values) or len(split_values) > 1:
            raise ValueError(
                f"{network_id}/{station}: inconsistent inner_fit_years roster"
            )
        train_mask = _inner_fit_mask(daily.index, str(split_values[0]))
        train_days = int((train_mask & daily[station].notna()).sum())
        if handler == "climatology" and train_days < 1:
            continue
        target = daily[station]
        for row in station_rows.itertuples(index=False):
            gap_start = pd.Timestamp(row.gap_start)
            start = daily.index.get_indexer([gap_start])[0]
            gap = int(row.gap_length)
            if start < 1 or start + gap >= len(daily):
                continue
            truth = daily[station].iloc[start : start + gap].to_numpy(dtype=float)
            if not np.isfinite(truth).all():
                continue
            predicted = handler_prediction(
                handler,
                target,
                start=start,
                gap_length=gap,
                train_mask=train_mask,
            )
            if not np.isfinite(predicted).all():
                continue
            rows.append(
                {
                    "network_id": str(network_id),
                    "station_id": station,
                    "gap_length": gap,
                    "season": str(row.season),
                    "placement": int(row.placement),
                    "gap_start": gap_start,
                    "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                    "model_family": f"default_{handler}",
                    "outer_training_years": str(row.outer_training_years),
                    "inner_fit_years": str(row.inner_fit_years),
                    "inner_score_years": str(row.inner_score_years),
                }
            )
    return pd.DataFrame(rows)


def default_handling_losses_from_fit_rows(
    network_id: str,
    panel: pd.DataFrame,
    fit_losses: pd.DataFrame,
    *,
    handler: str,
) -> pd.DataFrame:
    """Replay the archived inner-fit geometry for a single default handler."""

    network_losses = fit_losses.loc[
        fit_losses["network_id"].astype(str).eq(str(network_id))
    ].copy()
    if not len(network_losses):
        return pd.DataFrame()
    return _replay_default_rows(network_id, panel, network_losses, handler=handler)


def default_handling_losses(
    network_id: str,
    panel: pd.DataFrame,
    placements: pd.DataFrame,
    *,
    handler: str,
    gaps: Sequence[int] = (7, 30, 90, 180),
    placements_per_season: int = 20,
    min_train_days: int = 365,
) -> pd.DataFrame:
    """Standalone default-handling analogue of the empirical fit losses.

    Identical inner-split geometry to
    ``recovery_roster.fitting_period_empirical_losses`` (outer 70/30 year
    split, then an inner 70/30 split of the fitting years), but the scored
    reconstruction is the default handler instead of XGBoost.  Intended for
    synthetic/unit tests and independent regeneration; production runs
    replay archived geometry via ``default_handling_losses_from_fit_rows``.
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
        station = str(raw_station)
        if station not in daily.columns:
            continue
        donor_text = str(station_rows["donor_station_ids"].iloc[0])
        donors = tuple(
            str(value)
            for value in donor_text.split("|")
            if value and value != "nan"
        )
        if not donors or int((inner_fit & daily[station].notna()).sum()) < 1:
            continue
        target = daily[station]
        train_mask = inner_fit
        for gap in (int(value) for value in gaps):
            candidates = _candidate_starts(
                daily,
                pd.DataFrame(index=daily.index),
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
                    if start < 1 or start + gap >= len(daily):
                        continue
                    truth = daily[station].iloc[start : start + gap].to_numpy(
                        dtype=float
                    )
                    if not np.isfinite(truth).all():
                        continue
                    predicted = handler_prediction(
                        handler,
                        target,
                        start=int(start),
                        gap_length=gap,
                        train_mask=train_mask,
                    )
                    if not np.isfinite(predicted).all():
                        continue
                    rows.append(
                        {
                            "network_id": str(network_id),
                            "station_id": station,
                            "gap_length": gap,
                            "season": str(season),
                            "placement": placement,
                            "gap_start": daily.index[start],
                            "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                            "model_family": f"default_{handler}",
                            "outer_training_years": "|".join(
                                map(str, outer_training_years)
                            ),
                            "inner_fit_years": "|".join(map(str, inner_fit_years)),
                            "inner_score_years": "|".join(map(str, inner_score_years)),
                        }
                    )
    return pd.DataFrame(rows)


def differential_fitting_losses(
    model_losses: pd.DataFrame,
    default_losses: pd.DataFrame,
) -> pd.DataFrame:
    """Align model and default losses by placement and difference them.

    The returned frame keeps the archived fit-losses schema (the
    ``mae_deg_c`` column now holds the per-placement benefit) so that
    ``recovery_roster.empirical_transfer_predictions`` consumes it unchanged;
    ``model_mae_deg_c`` and ``default_mae_deg_c`` are retained for
    inspection.
    """

    model = _as_string_keys(model_losses)
    default = _as_string_keys(default_losses)
    model["gap_start"] = pd.to_datetime(model["gap_start"])
    default["gap_start"] = pd.to_datetime(default["gap_start"])
    keys = list(_GEOMETRY_KEYS)
    merged = model.merge(default, on=keys, how="inner", suffixes=("_model", "_default"))
    result = pd.DataFrame(
        {
            "network_id": merged["network_id"],
            "station_id": merged["station_id"],
            "gap_length": merged["gap_length"].astype(int),
            "season": merged["season"],
            "placement": merged["placement"].astype(int),
            "gap_start": pd.to_datetime(merged["gap_start"]),
            "mae_deg_c": (
                merged["mae_deg_c_default"].to_numpy(dtype=float)
                - merged["mae_deg_c_model"].to_numpy(dtype=float)
            ),
            "model_family": "differential_"
            + str(default["model_family"].iloc[0]).removeprefix("default_"),
            "outer_training_years": merged["outer_training_years_model"],
            "inner_fit_years": merged["inner_fit_years_model"],
            "inner_score_years": merged["inner_score_years_model"],
            "model_mae_deg_c": merged["mae_deg_c_model"],
            "default_mae_deg_c": merged["mae_deg_c_default"],
        }
    )
    return result.sort_values(keys).reset_index(drop=True)


def realized_default_mae(
    evaluation_placements: pd.DataFrame,
    *,
    model_mae_column: str = "mae_deg_c",
    default_mae_column: str = "climatology_mae_deg_c",
) -> pd.Series:
    """Realized per-placement benefit from a scored evaluation table.

    The archived placement tables carry the model MAE and the climatology
    MAE (climatology estimated on the outer training years only) for every
    evaluation placement, so the realized benefit requires no recomputation.
    """

    placements = evaluation_placements.copy()
    model_mae = placements[model_mae_column].to_numpy(dtype=float)
    default_mae = placements[default_mae_column].to_numpy(dtype=float)
    valid = np.isfinite(model_mae) & np.isfinite(default_mae)
    benefit = pd.Series(np.nan, index=placements.index, dtype=float)
    benefit.loc[valid] = default_mae[valid] - model_mae[valid]
    return benefit


def r6_differential_predictions(
    differential_fitting: pd.DataFrame,
    evaluation_placements: pd.DataFrame,
) -> pd.DataFrame:
    """Station x duration historical benefit means with level fallbacks.

    Direct analogue of the v13 ``r6`` strongest-fitting-record baseline but
    applied to the benefit estimand: the curve is the fitting-period mean
    benefit within (station, gap_length), falling back to (network,
    gap_length), then network, then the global mean.  Returns the evaluation
    placements with a ``r6_diff_prediction`` column.
    """

    differential = _as_string_keys(differential_fitting)
    keys = ["network_id", "station_id", "gap_length"]
    curve = (
        differential.groupby(keys, as_index=False)["mae_deg_c"]
        .mean()
        .rename(columns={"mae_deg_c": "r6_diff_prediction"})
    )
    fallback_network_gap = (
        differential.groupby(["network_id", "gap_length"], as_index=False)[
            "mae_deg_c"
        ]
        .mean()
        .rename(columns={"mae_deg_c": "_network_gap"})
    )
    fallback_network = (
        differential.groupby("network_id", as_index=False)["mae_deg_c"]
        .mean()
        .rename(columns={"mae_deg_c": "_network"})
    )
    global_mean = float(differential["mae_deg_c"].mean())
    evaluation = _as_string_keys(evaluation_placements)
    result = (
        evaluation.copy()
        .merge(curve, on=keys, how="left")
        .merge(fallback_network_gap, on=["network_id", "gap_length"], how="left")
        .merge(fallback_network, on="network_id", how="left")
    )
    result["r6_diff_prediction"] = (
        result["r6_diff_prediction"]
        .fillna(result["_network_gap"])
        .fillna(result["_network"])
        .fillna(global_mean)
    )
    return result.drop(columns=["_network_gap", "_network"])


__all__ = [
    "DEFAULT_HANDLERS",
    "default_handling_losses",
    "default_handling_losses_from_fit_rows",
    "differential_fitting_losses",
    "handler_prediction",
    "realized_default_mae",
    "r6_differential_predictions",
]
