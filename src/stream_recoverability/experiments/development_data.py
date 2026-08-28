"""Plain data loaders for the open v11 development analysis.

The v11 workflow is iterative development work. It reads and writes ordinary,
replaceable tables without a separate custody layer.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.analysis.development_calibration import (
    station_gap_operator_predictions,
)


def joint_complete_feature_rosters(
    frame: pd.DataFrame,
    *,
    target: str,
    donor_candidates: tuple[str, ...],
    meteorology_candidates: tuple[str, ...],
    hydraulics_candidates: tuple[str, ...],
    min_pairs: int = 365,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Select D/M/H columns with one shared consecutive-day fitting support."""

    def consecutive_pairs(columns: tuple[str, ...]) -> int:
        complete = np.isfinite(frame.loc[:, columns].to_numpy(dtype=float)).all(axis=1)
        return int((complete[:-1] & complete[1:]).sum())

    ranked_donors = []
    for station in donor_candidates:
        pair = frame[[target, station]].dropna()
        if len(pair) >= min_pairs:
            ranked_donors.append((abs(float(pair.corr().iloc[0, 1])), station))
    donors: list[str] = []
    for _, station in sorted(ranked_donors, reverse=True):
        if consecutive_pairs((target, *donors, station)) >= min_pairs:
            donors.append(station)

    meteorology: list[str] = []
    for feature in meteorology_candidates:
        if consecutive_pairs((target, *donors, *meteorology, feature)) >= min_pairs:
            meteorology.append(feature)

    hydraulics: list[str] = []
    for feature in hydraulics_candidates:
        if (
            consecutive_pairs(
                (target, *donors, *meteorology, *hydraulics, feature)
            )
            >= min_pairs
        ):
            hydraulics.append(feature)
    return tuple(donors), tuple(meteorology), tuple(hydraulics)


def read_table(path: str | Path) -> pd.DataFrame:
    """Read a CSV or Parquet table from ``path``."""

    source = Path(path)
    if source.suffix == ".parquet":
        return pd.read_parquet(source)
    return pd.read_csv(source, dtype={"network_id": str, "station_id": str})


def station_gap_outcomes(
    results: pd.DataFrame,
    *,
    model: str = "xgboost",
    information_condition: str = "B_union_D",
) -> pd.DataFrame:
    """Collapse repeated placements to one realized-loss row per station-gap."""

    selected = results.loc[
        results["model"].eq(model)
        & results["information_condition"].eq(information_condition)
        & results["status"].isin(("complete", "reference_complete"))
    ].copy()
    predictor_columns = [
        column
        for column in (
            "predicted_conditional_risk",
            "gap_length_only",
            "acf_only",
            "donor_r2_only",
            "additive_d_over_4_heuristic",
        )
        if column in selected.columns
    ]
    keys = ["network_id", "station_id", "gap_length"]
    predictors = selected.groupby(keys, as_index=False)[predictor_columns].first()
    outcome = selected.groupby(keys, as_index=False).agg(
        realized_loss=("observed_recovery_loss", "mean"),
        placement_sd=("observed_recovery_loss", "std"),
        n_placements=("observed_recovery_loss", "size"),
    )
    return predictors.merge(outcome, on=keys).sort_values(keys).reset_index(drop=True)


def load_station_gap_outcomes(
    path: str | Path,
    *,
    model: str = "xgboost",
    information_condition: str = "B_union_D",
) -> pd.DataFrame:
    """Read first-layer results and return the station-gap development table."""

    return station_gap_outcomes(
        read_table(path),
        model=model,
        information_condition=information_condition,
    )


def load_auxiliary_networks(root: str | Path, *, role: str = "development") -> pd.DataFrame:
    """Concatenate the materialized meteorology/hydraulics tables by network."""

    frames = []
    directory = Path(root) / role / "networks"
    for path in sorted(directory.glob("*/daily_long_auxiliary.parquet")):
        frame = pd.read_parquet(path)
        frame.insert(0, "network_id", path.parent.name)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def complete_operator_network_predictions(
    temperature_path: str | Path,
    auxiliary_path: str | Path,
    *,
    network_id: str,
    gaps: tuple[int, ...] = (30, 90, 180),
    target_stations: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Build train-period B/D/M/H predictions for one open river network."""

    temperature = (
        pd.read_csv(temperature_path, parse_dates=["date"])
        .set_index("date")
        .sort_index()
        .asfreq("D")
    )
    auxiliary = pd.read_parquet(auxiliary_path)
    auxiliary["date"] = pd.to_datetime(auxiliary["date"])
    auxiliary["feature"] = (
        auxiliary["site_id"].astype(str) + "__" + auxiliary["variable"].astype(str)
    )
    auxiliary_wide = auxiliary.pivot(
        index="date", columns="feature", values="value"
    )
    years = sorted(temperature.index.year.unique())
    train_years = years[: round(len(years) * 0.7)]
    temperature = temperature.loc[temperature.index.year.isin(train_years)]
    rows = []
    stations = list(temperature.columns.astype(str))
    targets = stations if target_stations is None else list(target_stations)

    for target in targets:
        available_meteorology = [
            f"{target}__{variable}"
            for variable in ("Ta", "P", "W", "RH", "Rs")
            if f"{target}__{variable}" in auxiliary_wide
        ]
        available_hydraulics = [
            f"{target}__{variable}"
            for variable in ("F", "L")
            if f"{target}__{variable}" in auxiliary_wide
        ]
        joined = temperature.join(auxiliary_wide)
        donors, meteorology, hydraulics = joint_complete_feature_rosters(
            joined,
            target=target,
            donor_candidates=tuple(station for station in stations if station != target),
            meteorology_candidates=tuple(available_meteorology),
            hydraulics_candidates=tuple(available_hydraulics),
        )
        base_columns = [target, *donors]
        columns = [*base_columns, *meteorology, *hydraulics]
        series = joined.loc[:, columns]
        day_means = series.groupby(series.index.dayofyear).transform("mean")
        anomalies = series - day_means
        prediction = station_gap_operator_predictions(
            anomalies,
            network_id=network_id,
            target_stations=(target,),
            gaps=gaps,
            donor_stations={target: tuple(donors)},
            meteorology_columns=meteorology,
            hydraulics_columns=hydraulics,
            memory_weighting="regime",
        ).assign(
            donor_station_ids="|".join(donors),
            nearest_donor_correlation=max(
                abs(float(anomalies[target].corr(anomalies[donor])))
                for donor in donors
            ),
            meteorology_feature_count=len(meteorology),
            hydraulics_feature_count=len(hydraulics),
            meteorology_feature_ids="|".join(
                feature.split("__", 1)[1] for feature in meteorology
            ),
            hydraulics_feature_ids="|".join(
                feature.split("__", 1)[1] for feature in hydraulics
            ),
            operator_training_years="|".join(map(str, train_years)),
        )
        rows.append(prediction)
    return pd.concat(rows, ignore_index=True)


__all__ = [
    "complete_operator_network_predictions",
    "joint_complete_feature_rosters",
    "load_auxiliary_networks",
    "load_station_gap_outcomes",
    "read_table",
    "station_gap_outcomes",
]
