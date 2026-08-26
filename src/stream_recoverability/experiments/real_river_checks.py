"""Checks on downloaded public rivers: overlap, real gaps, leave-one-river-out."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    empirical_information_set_conditionals,
)
from stream_recoverability.analysis.hierarchical_confirmation import (
    evaluate_success,
)
from stream_recoverability.analysis.recoverability_spectrum import (
    recoverability,
    spectrum_from_conditionals,
)
from stream_recoverability.experiments.sensor_policy import (
    budget_curve,
    policy_success,
)
from stream_recoverability.experiments.synthetic_river import advection_chain


def year_split(index: pd.DatetimeIndex, train_frac: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    """Chronological year split. Earlier years train; later years test."""

    years = np.array(sorted(pd.unique(index.year)))
    cut = max(1, int(round(len(years) * train_frac)))
    train_years = set(years[:cut])
    train = np.array([year in train_years for year in index.year])
    return train, ~train


def _year_split(index: pd.DatetimeIndex, train_frac: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    return year_split(index, train_frac)


def donor_regression_mae(
    target: np.ndarray,
    donors: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
) -> float:
    """Later-year donor-regression MAE with coefficients fixed on train years."""

    return _donor_regression_mae(target, donors, train, test)


def _donor_regression_mae(
    target: np.ndarray,
    donors: np.ndarray,
    train: np.ndarray,
    test: np.ndarray,
) -> float:
    if donors.size == 0 or int(train.sum()) < donors.shape[1] + 2:
        return float("nan")
    y_train = target[train]
    x_train = np.column_stack([np.ones(int(train.sum())), donors[train]])
    valid = np.isfinite(y_train) & np.isfinite(x_train).all(axis=1)
    if int(valid.sum()) < x_train.shape[1] + 1:
        return float("nan")
    coef = np.linalg.lstsq(x_train[valid], y_train[valid], rcond=None)[0]
    y_test = target[test]
    x_test = np.column_stack([np.ones(int(test.sum())), donors[test]])
    ok = np.isfinite(y_test) & np.isfinite(x_test).all(axis=1)
    if int(ok.sum()) < 10:
        return float("nan")
    pred = x_test[ok] @ coef
    return float(np.mean(np.abs(pred - y_test[ok])))


def river_station_scores(
    name: str, wide: pd.DataFrame, gap_length: int = 30
) -> list[dict[str, float | str]]:
    """Fit the related-structure score on early years; score a simple fill later."""

    values = wide.to_numpy(dtype=float)
    train, test = _year_split(wide.index)
    if int(train.sum()) < 365 or int(test.sum()) < 180:
        return [
            {
                "network_id": name,
                "reason": "not_enough_years_after_split",
                "observed_recovery_loss": float("nan"),
                "predicted_conditional_risk": float("nan"),
            }
        ]
    rows: list[dict[str, float | str]] = []
    for target in range(values.shape[1]):
        donors = [index for index in range(values.shape[1]) if index != target]
        try:
            conditionals = empirical_information_set_conditionals(
                values[train],
                target=target,
                donors=donors,
                gap_length=gap_length,
            )
        except (np.linalg.LinAlgError, ValueError):
            continue
        spectrum = spectrum_from_conditionals(conditionals)
        climatology = float(np.nanmean(values[train, target]))
        climate_mae = float(np.nanmean(np.abs(values[test, target] - climatology)))
        donor_mae = _donor_regression_mae(
            values[:, target],
            values[:, donors],
            train,
            test,
        )
        if not np.isfinite(climate_mae) or climate_mae == 0 or not np.isfinite(donor_mae):
            continue
        rows.append(
            {
                "network_id": name,
                "station_id": str(wide.columns[target]),
                "predicted_conditional_risk": float(
                    conditionals["B_union_D"]["expected_mae_conditional"]
                ),
                "observed_recovery_loss": float(donor_mae),
                "observed_skill_vs_climatology": recoverability(donor_mae, climate_mae),
                "predicted_skill": float(conditionals["B_union_D"]["predicted_skill"]),
                "tau": spectrum.tau,
                "tau_sign": spectrum.sign,
                "reason": "",
            }
        )
    if not rows:
        return [
            {
                "network_id": name,
                "reason": "could_not_score_any_station",
                "observed_recovery_loss": float("nan"),
                "predicted_conditional_risk": float("nan"),
            }
        ]
    return rows


def score_rivers(panels: Mapping[str, pd.DataFrame], gap_length: int = 30) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    for name, wide in panels.items():
        rows.extend(river_station_scores(name, wide, gap_length=gap_length))
    return pd.DataFrame(rows)


def leave_one_river_out(scores: pd.DataFrame) -> dict[str, object]:
    usable = scores.loc[
        np.isfinite(scores.get("predicted_conditional_risk", pd.Series(dtype=float)))
        & np.isfinite(scores.get("observed_recovery_loss", pd.Series(dtype=float)))
    ]
    if usable.empty or usable["network_id"].nunique() < 3:
        return {
            "passed": False,
            "reason": "fewer_than_three_rivers_with_scores",
            "n_rivers": int(usable["network_id"].nunique()) if not usable.empty else 0,
        }
    return evaluate_success(usable)


def empirical_river_from_panel(name: str, wide: pd.DataFrame):
    """Same-day covariance of a real river. Used only to compare station-picking rules."""

    from stream_recoverability.analysis.conditional_observability import ridge_psd
    from stream_recoverability.experiments.synthetic_river import SyntheticRiver

    values = wide.to_numpy(dtype=float)
    cov = pd.DataFrame(values).cov().to_numpy(dtype=float)
    cov = ridge_psd(np.nan_to_num(cov, nan=0.0))
    n = cov.shape[0]
    return SyntheticRiver(
        name=name,
        transition=np.zeros((n, n)),
        process_noise=cov,
        sigma=cov,
        station_names=tuple(str(column) for column in wide.columns),
        target=0,
        donors=tuple(range(1, n)),
        regime="empirical",
        notes="Observed same-day covariance. Not a known-dynamics river.",
    )


def real_river_sensor_check(panels: Mapping[str, pd.DataFrame], k: int = 3) -> pd.DataFrame:
    """On downloaded rivers, compare our station pick with random, spacing, and correlation."""

    rows = []
    for name, wide in panels.items():
        if wide.shape[1] < max(k, 3):
            continue
        river = empirical_river_from_panel(name, wide)
        curve = budget_curve(river, budgets=(min(k, river.n_stations - 1),), random_repeats=6)
        success = policy_success(curve, reduction_min=0.15)
        if success.empty:
            continue
        row = success.iloc[0].to_dict()
        row["network_id"] = name
        rows.append(row)
    return pd.DataFrame(rows)


def simple_baseline_errors(scores: pd.DataFrame) -> pd.DataFrame:
    """How well predicted risk tracks observed error, versus just ranking stations."""

    usable = scores.loc[
        np.isfinite(scores.get("predicted_conditional_risk", pd.Series(dtype=float)))
        & np.isfinite(scores.get("observed_recovery_loss", pd.Series(dtype=float)))
    ]
    if usable.empty:
        return pd.DataFrame()
    rows = []
    for network_id, group in usable.groupby("network_id"):
        pred = group["predicted_conditional_risk"].to_numpy(dtype=float)
        obs = group["observed_recovery_loss"].to_numpy(dtype=float)
        if len(group) < 3 or float(np.var(pred)) == 0:
            continue
        pred_rank = pd.Series(pred).rank().to_numpy()
        obs_rank = pd.Series(obs).rank().to_numpy()
        rows.append(
            {
                "network_id": network_id,
                "predicted_vs_observed_spearman": float(
                    pd.Series(pred).corr(pd.Series(obs), method="spearman")
                ),
                "rank_mae": float(np.mean(np.abs(pred_rank - obs_rank))),
                "n_stations": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def synthetic_sensor_note() -> pd.DataFrame:
    """Keep the fake-river sensor test visible; real-river placement needs more stations."""

    return policy_success(budget_curve(advection_chain(), budgets=(2, 3), random_repeats=3))


__all__ = [
    "donor_regression_mae",
    "leave_one_river_out",
    "real_river_sensor_check",
    "river_station_scores",
    "score_rivers",
    "simple_baseline_errors",
    "year_split",
]
