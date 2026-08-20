"""Predeclared donor-C falsification transforms.

These helpers rearrange Group C (other-station hydrology) while leaving the
target series unchanged. They support predictive attribution tests. They do
not establish a causal heat-transport mechanism.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

DONOR_LAGS_DAYS = (-30, -14, -7, -3, -1, 0, 1, 3, 7, 14, 30)
DONOR_VARIABLES = ("T", "F", "L")
FALSIFICATION_CONTRASTS = (
    "observed_same_day_C",
    "lagged_C",
    "past_only_C",
    "station_identity_permutation",
    "seasonal_residual_block_permutation",
)
DEFAULT_STATIONS = ("B1", "S2", "P3")
DEFAULT_BLOCK_DAYS = 30


def donor_columns(
    columns: Sequence[str],
    *,
    target_station: str,
    variables: Sequence[str] = DONOR_VARIABLES,
) -> list[str]:
    """Return wide-table donor columns for one target station."""

    target = str(target_station)
    wanted = {str(variable) for variable in variables}
    selected: list[str] = []
    for column in columns:
        if "_" not in str(column):
            continue
        station, variable = str(column).split("_", 1)
        if station != target and variable in wanted:
            selected.append(str(column))
    return selected


def apply_donor_lag(
    wide: pd.DataFrame,
    *,
    lag_days: int,
    target_station: str,
    variables: Sequence[str] = DONOR_VARIABLES,
) -> pd.DataFrame:
    """Shift donor hydrology by ``lag_days``.

    Positive lags use earlier donor values (a physically delayed source).
    Negative lags use later donor values and are the implausible contrast.
    """

    if not float(lag_days).is_integer():
        raise ValueError("lag_days must be an integer number of days")
    result = wide.copy()
    if int(lag_days) == 0:
        return result
    for column in donor_columns(result.columns, target_station=target_station, variables=variables):
        result[column] = pd.to_numeric(result[column], errors="coerce").shift(int(lag_days))
    return result


def apply_past_only_donor(
    wide: pd.DataFrame,
    *,
    target_station: str,
    variables: Sequence[str] = DONOR_VARIABLES,
) -> pd.DataFrame:
    """Replace same-day donor values with the previous day only."""

    return apply_donor_lag(
        wide, lag_days=1, target_station=target_station, variables=variables
    )


def permute_donor_station_identity(
    wide: pd.DataFrame,
    *,
    seed: int,
    target_station: str,
    stations: Sequence[str] = DEFAULT_STATIONS,
    variables: Sequence[str] = DONOR_VARIABLES,
) -> pd.DataFrame:
    """Swap donor-station identities while keeping the target series fixed."""

    donors = [str(station) for station in stations if str(station) != str(target_station)]
    if len(donors) < 2:
        raise ValueError("station identity permutation requires at least two donor stations")
    rng = np.random.default_rng(int(seed))
    order = [str(station) for station in rng.permutation(donors)]
    if order == donors:
        order = list(reversed(donors))
    mapping = dict(zip(donors, order, strict=True))
    result = wide.copy()
    originals = {
        f"{station}_{variable}": pd.to_numeric(
            result[f"{station}_{variable}"], errors="coerce"
        ).copy()
        for station in donors
        for variable in variables
        if f"{station}_{variable}" in result.columns
    }
    for station in donors:
        for variable in variables:
            source = f"{station}_{variable}"
            destination = f"{mapping[station]}_{variable}"
            if source in originals and destination in result.columns:
                result[destination] = originals[source]
    return result


def block_permute_donor_residuals(
    wide: pd.DataFrame,
    *,
    seed: int,
    target_station: str,
    block_days: int = DEFAULT_BLOCK_DAYS,
    dayofyear_col: str | None = None,
    variables: Sequence[str] = DONOR_VARIABLES,
) -> pd.DataFrame:
    """Shuffle donor residuals in contiguous blocks after removing seasonality."""

    if block_days < 1:
        raise ValueError("block_days must be at least 1")
    result = wide.copy()
    if dayofyear_col is None:
        if "date" not in result.columns:
            raise KeyError("block permutation requires a date column or dayofyear_col")
        doy = pd.to_datetime(result["date"]).dt.dayofyear.to_numpy()
    else:
        doy = pd.to_numeric(result[dayofyear_col], errors="coerce").to_numpy()
    rng = np.random.default_rng(int(seed))
    n_rows = len(result)
    starts = list(range(0, n_rows, int(block_days)))
    shuffled_starts = list(rng.permutation(starts))
    new_index = np.concatenate(
        [
            np.arange(start, min(start + int(block_days), n_rows))
            for start in shuffled_starts
        ]
    )
    for column in donor_columns(result.columns, target_station=target_station, variables=variables):
        values = pd.to_numeric(result[column], errors="coerce")
        seasonal = pd.Series(values.to_numpy(), index=result.index).groupby(doy).transform("mean")
        residual = values - seasonal
        shuffled = residual.to_numpy()[new_index[:n_rows]]
        result[column] = seasonal.to_numpy() + shuffled
    return result


def falsification_grid(
    *,
    lags_days: Sequence[int] = DONOR_LAGS_DAYS,
    permutation_seed: int = 20260820,
    stations: Sequence[str] = DEFAULT_STATIONS,
) -> list[dict[str, Any]]:
    """Return the frozen, pre-result donor-C experiment list."""

    experiments: list[dict[str, Any]] = [
        {
            "contrast": "observed_same_day_C",
            "lag_days": 0,
            "seed": None,
            "role": "reference",
        }
    ]
    for lag in lags_days:
        if int(lag) == 0:
            continue
        experiments.append(
            {
                "contrast": "lagged_C",
                "lag_days": int(lag),
                "seed": None,
                "role": "physically_plausible" if int(lag) > 0 else "implausible_lead",
            }
        )
    experiments.append(
        {
            "contrast": "past_only_C",
            "lag_days": 1,
            "seed": None,
            "role": "no_same_day_donor",
        }
    )
    experiments.append(
        {
            "contrast": "station_identity_permutation",
            "lag_days": 0,
            "seed": int(permutation_seed),
            "role": "identity_destroyed",
            "stations": list(stations),
        }
    )
    experiments.append(
        {
            "contrast": "seasonal_residual_block_permutation",
            "lag_days": 0,
            "seed": int(permutation_seed),
            "block_days": DEFAULT_BLOCK_DAYS,
            "role": "shared_season_retained",
        }
    )
    return experiments


def interpret_falsification(summary: pd.DataFrame) -> dict[str, Any]:
    """Map a completed contrast table to the predeclared wording rule.

    The function does not invent performance numbers. It only classifies an
    already-scored table.
    """

    required = {"contrast", "skill_gain"}
    missing = sorted(required.difference(summary.columns))
    if missing:
        raise ValueError(f"falsification summary requires columns: {missing}")
    data = summary.copy()
    data["skill_gain"] = pd.to_numeric(data["skill_gain"], errors="coerce")
    reference = data.loc[data["contrast"].astype(str).eq("observed_same_day_C"), "skill_gain"]
    if reference.empty or not np.isfinite(reference.iloc[0]):
        return {
            "interpretation": "unavailable",
            "reason": "reference same-day C gain is missing",
            "claim_language": "withhold_group_C_claim",
        }
    ref_gain = float(reference.iloc[0])
    permutation = data.loc[
        data["contrast"].astype(str).eq("station_identity_permutation"), "skill_gain"
    ]
    implausible = data.loc[
        data["contrast"].astype(str).eq("lagged_C")
        & pd.to_numeric(data.get("lag_days", np.nan), errors="coerce").lt(0),
        "skill_gain",
    ]
    permutation_survives = bool(
        not permutation.empty
        and np.isfinite(permutation.iloc[0])
        and float(permutation.iloc[0]) >= ref_gain - 1e-12
    )
    implausible_survives = bool(
        not implausible.empty
        and np.isfinite(implausible.to_numpy(dtype=float)).all()
        and float(np.nanmin(implausible.to_numpy(dtype=float))) >= ref_gain - 1e-12
    )
    if permutation_survives and implausible_survives:
        language = "correlated_predictive_source_only"
        interpretation = "falsified_network_propagation"
    elif permutation_survives or implausible_survives:
        language = "predictive_attribution_not_mechanism"
        interpretation = "inconclusive"
    else:
        language = "predictive_network_source_survived_predeclared_tests"
        interpretation = "not_falsified"
    return {
        "interpretation": interpretation,
        "claim_language": language,
        "reference_skill_gain": ref_gain,
        "permutation_survives": permutation_survives,
        "implausible_lag_survives": implausible_survives,
    }


__all__ = [
    "DEFAULT_BLOCK_DAYS",
    "DONOR_LAGS_DAYS",
    "DONOR_VARIABLES",
    "FALSIFICATION_CONTRASTS",
    "apply_donor_lag",
    "apply_past_only_donor",
    "block_permute_donor_residuals",
    "donor_columns",
    "falsification_grid",
    "interpret_falsification",
    "permute_donor_station_identity",
]
