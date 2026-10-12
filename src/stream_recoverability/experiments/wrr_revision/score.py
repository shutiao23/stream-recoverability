"""Score matched outages under every recoverer and compute MAE plus thermal B_q."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.development_data import joint_complete_feature_rosters
from stream_recoverability.experiments.development_recovery import (
    XGBOOST_PARAMETERS,
    _candidate_starts,
    read_temperature_panel,
    select_placements,
    year_split,
)
from stream_recoverability.experiments.recovery_roster import season_label
from stream_recoverability.experiments.wrr_revision.features import base_feature_frame
from stream_recoverability.experiments.wrr_revision.paths import (
    ARCHIVED_GAPS,
    FIRST_PANEL_ROOT,
    FIRST_PLACEMENTS,
    GAP_GRID,
    GENERATED_GAPS,
    SECOND_PANEL_ROOT,
)
from stream_recoverability.experiments.wrr_revision.recoverers import (
    FittedRecoverer,
    fit_station_recoverers,
)
from stream_recoverability.experiments.wrr_revision.thermal import (
    daily_mae,
    series_losses,
)

MIN_TRAIN_DAYS = 365
PLACEMENTS_PER_GENERATED_GAP = 12
WINDOW_DAYS = 365


def panel_directory(panel_name: str) -> Path:
    if panel_name == "first":
        return FIRST_PANEL_ROOT
    if panel_name == "second":
        return SECOND_PANEL_ROOT
    raise KeyError(panel_name)


def load_panel(network_id: str, panel_name: str = "first") -> pd.DataFrame:
    path = panel_directory(panel_name) / str(network_id) / "daily_wide_temperature.csv"
    return read_temperature_panel(str(path))


def archived_placements(
    network_id: str,
    path: Path = FIRST_PLACEMENTS,
    *,
    information_condition: str = "B_union_D",
) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["gap_start", "gap_end"])
    selected = frame.loc[
        frame["network_id"].astype(str).eq(str(network_id))
        & frame["information_condition"].eq(information_condition)
    ].copy()
    selected["station_id"] = selected["station_id"].astype(str)
    return selected


def generated_placements(
    panel: pd.DataFrame,
    *,
    target_station: str,
    donors: Sequence[str],
    evaluation_mask: pd.Series,
    gap_lengths: Sequence[int] = GENERATED_GAPS,
    count: int = PLACEMENTS_PER_GENERATED_GAP,
) -> list[dict[str, object]]:
    empty = pd.DataFrame(index=panel.index)
    rows: list[dict[str, object]] = []
    for gap_length in (int(value) for value in gap_lengths):
        starts = _candidate_starts(
            panel,
            empty,
            target_station=str(target_station),
            donors=tuple(donors) if donors else (),
            meteorology=(),
            hydraulics=(),
            evaluation_mask=evaluation_mask,
            gap_length=gap_length,
        )
        for placement, start in enumerate(select_placements(starts, count=count)):
            stop = int(start) + gap_length
            rows.append(
                {
                    "station_id": str(target_station),
                    "gap_length": gap_length,
                    "placement": int(placement),
                    "gap_start": panel.index[int(start)],
                    "gap_end": panel.index[stop - 1],
                    "source": "generated",
                }
            )
    return rows


def _window_slice(n: int, start: int, stop: int) -> slice:
    centre = (int(start) + int(stop) - 1) // 2
    left = max(0, centre - WINDOW_DAYS // 2)
    right = min(n, left + WINDOW_DAYS)
    left = max(0, right - WINDOW_DAYS)
    return slice(left, right)


def _complete_series(
    truth: pd.Series,
    fill: np.ndarray,
    start: int,
    gap_length: int,
) -> pd.Series:
    series = truth.copy()
    series.iloc[int(start) : int(start) + int(gap_length)] = fill
    return series


def score_gap(
    recoverer: FittedRecoverer,
    *,
    features: pd.DataFrame,
    target: pd.Series,
    start: int,
    gap_length: int,
    default_fill: np.ndarray,
    air: pd.Series | None = None,
    discharge: pd.Series | None = None,
) -> dict[str, float] | None:
    try:
        prediction = recoverer.predict_gap(
            features=features,
            target=target,
            start=start,
            gap_length=gap_length,
            air=air,
            discharge=discharge,
        )
    except Exception:
        return None
    truth = target.iloc[int(start) : int(start) + int(gap_length)].to_numpy(dtype=float)
    if prediction is None or len(prediction) != len(truth) or not np.isfinite(prediction).all():
        return None
    default = default_fill[int(start) : int(start) + int(gap_length)]
    if not np.isfinite(default).all() or not np.isfinite(truth).all():
        return None
    reconstructed = _complete_series(target, prediction, start, gap_length)
    default_series = _complete_series(target, default, start, gap_length)
    window = _window_slice(len(target), start, int(start) + int(gap_length))
    losses = series_losses(
        target.iloc[window],
        default_series.iloc[window],
        reconstructed.iloc[window],
    )
    losses["mae_deg_c"] = daily_mae(truth, prediction)
    losses["climatology_mae_deg_c"] = daily_mae(truth, default)
    losses["mae_benefit"] = losses["climatology_mae_deg_c"] - losses["mae_deg_c"]
    return losses


def score_network(
    network_id: str,
    panel: pd.DataFrame,
    *,
    placements: pd.DataFrame | None = None,
    air_by_station: Mapping[str, pd.Series] | None = None,
    discharge_by_station: Mapping[str, pd.Series] | None = None,
    xgboost_parameters: Mapping[str, object] | None = None,
    include_external: bool = True,
    generate_extra_gaps: bool = True,
    target_stations: Sequence[str] | None = None,
    include_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Fit every recoverer once per station and score the matched placement set."""

    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    train_mask, training_years, evaluation_years = year_split(daily.index)
    evaluation_mask = ~train_mask
    if placements is None:
        archived = archived_placements(network_id)
    elif placements.empty:
        archived = pd.DataFrame(
            columns=["station_id", "gap_length", "placement", "gap_start", "source"]
        )
    else:
        archived = placements
    rows: list[dict[str, object]] = []
    stations = tuple(daily.columns) if target_stations is None else tuple(map(str, target_stations))
    for station in stations:
        if station not in daily.columns:
            continue
        donors, _, _ = joint_complete_feature_rosters(
            daily.loc[train_mask],
            target=station,
            donor_candidates=tuple(column for column in daily.columns if column != station),
            meteorology_candidates=(),
            hydraulics_candidates=(),
            min_pairs=MIN_TRAIN_DAYS,
        )
        donors = tuple(
            donor
            for donor in donors
            if int((evaluation_mask & daily[donor].notna()).sum()) >= 60
        )
        if int((train_mask & daily[station].notna()).sum()) < MIN_TRAIN_DAYS:
            continue
        air = None if air_by_station is None else air_by_station.get(station)
        discharge = None if discharge_by_station is None else discharge_by_station.get(station)
        features = base_feature_frame(daily, donors=donors, air=air, discharge=discharge)
        recoverers = fit_station_recoverers(
            daily,
            target_station=station,
            donors=donors,
            train_mask=train_mask,
            features=features,
            air=air,
            discharge=discharge,
            xgboost_parameters=xgboost_parameters or XGBOOST_PARAMETERS,
            include_external=include_external,
            include_names=include_names,
        )
        default_fill = recoverers["doy_climatology"].extra["values"]
        station_archive = archived.loc[archived["station_id"].astype(str).eq(station)]
        tasks: list[dict[str, object]] = []
        for item in station_archive.itertuples(index=False):
            if int(item.gap_length) not in ARCHIVED_GAPS and int(item.gap_length) not in GAP_GRID:
                continue
            start = daily.index.get_indexer([pd.Timestamp(item.gap_start)])[0]
            if start < 1:
                continue
            tasks.append(
                {
                    "gap_length": int(item.gap_length),
                    "placement": int(item.placement),
                    "gap_start": pd.Timestamp(item.gap_start),
                    "start": int(start),
                    "source": "archived",
                }
            )
        extra_lengths = GENERATED_GAPS if len(station_archive) else GAP_GRID
        if generate_extra_gaps:
            tasks.extend(
                {
                    **item,
                    "start": int(daily.index.get_indexer([pd.Timestamp(item["gap_start"])])[0]),
                }
                for item in generated_placements(
                    daily,
                    target_station=station,
                    donors=donors,
                    evaluation_mask=evaluation_mask,
                    gap_lengths=extra_lengths,
                )
            )
        for task in tasks:
            start = int(task["start"])
            gap_length = int(task["gap_length"])
            if start < 1 or start + gap_length >= len(daily):
                continue
            season = str(season_label([pd.Timestamp(task["gap_start"])])[0])
            for recoverer in recoverers.values():
                scored = score_gap(
                    recoverer,
                    features=features,
                    target=daily[station],
                    start=start,
                    gap_length=gap_length,
                    default_fill=np.asarray(default_fill, dtype=float),
                    air=air,
                    discharge=discharge,
                )
                if scored is None:
                    continue
                rows.append(
                    {
                        "network_id": str(network_id),
                        "station_id": station,
                        "gap_length": gap_length,
                        "placement": int(task["placement"]),
                        "gap_start": pd.Timestamp(task["gap_start"]),
                        "season": season,
                        "recoverer": recoverer.name,
                        "family": recoverer.family,
                        "training_protocol": recoverer.training_protocol,
                        "uses_boundary": recoverer.uses_boundary,
                        "information_group": recoverer.information_group,
                        "n_train_rows": recoverer.n_train_rows,
                        "placement_source": task.get("source", "archived"),
                        "training_years": "|".join(map(str, training_years)),
                        "evaluation_years": "|".join(map(str, evaluation_years)),
                        "donor_station_ids": "|".join(donors),
                        **scored,
                    }
                )
    return pd.DataFrame(rows)


def crossing_day(frame: pd.DataFrame, *, recoverer: str) -> pd.DataFrame:
    """Interpolate the first non-positive mean MAE benefit on the duration grid.

    Stations that never cross are right-censored at their last evaluated length.
    """

    rows: list[dict[str, object]] = []
    selected = frame.loc[frame["recoverer"].eq(recoverer)]
    for (network, station), group in selected.groupby(["network_id", "station_id"], sort=False):
        means = (
            group.groupby("gap_length", as_index=False)["mae_benefit"].mean().sort_values("gap_length")
        )
        lengths = means["gap_length"].to_numpy(dtype=float)
        benefits = means["mae_benefit"].to_numpy(dtype=float)
        last_positive = lengths[benefits > 0]
        last_length = float(lengths.max()) if len(lengths) else float("nan")
        crossed = False
        crossing = float("nan")
        for left, right, b_left, b_right in zip(
            lengths[:-1], lengths[1:], benefits[:-1], benefits[1:]
        ):
            if b_left > 0 and b_right <= 0:
                if b_left == b_right:
                    crossing = float(right)
                else:
                    frac = b_left / (b_left - b_right)
                    crossing = float(left + frac * (right - left))
                crossed = True
                break
        rows.append(
            {
                "network_id": network,
                "station_id": station,
                "recoverer": recoverer,
                "crossed": crossed,
                "crossing_day": crossing if crossed else last_length,
                "censoring": "observed" if crossed else "right_censored",
                "last_evaluated_length": last_length,
                "last_positive_length": float(last_positive.max()) if len(last_positive) else float("nan"),
                "n_lengths": int(len(lengths)),
            }
        )
    return pd.DataFrame(rows)


def recoverer_duration_summary(frame: pd.DataFrame) -> pd.DataFrame:
    keys = ["recoverer", "information_group", "training_protocol", "uses_boundary", "gap_length"]
    return (
        frame.groupby(keys, as_index=False)
        .agg(
            n_placements=("mae_deg_c", "size"),
            n_networks=("network_id", "nunique"),
            n_stations=("station_id", "nunique"),
            mae_mean=("mae_deg_c", "mean"),
            benefit_mean=("mae_benefit", "mean"),
            harmful_rate=("mae_benefit", lambda s: float((s < 0).mean())),
            hottest_30_benefit=("hottest_30_benefit", "mean"),
            exceed_days_20_benefit=("exceed_days_20_benefit", "mean"),
        )
        .sort_values(["gap_length", "recoverer"])
        .reset_index(drop=True)
    )
