"""Network-random-intercept analysis at station-by-gap resolution."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import chi2
from statsmodels.regression.mixed_linear_model import MixedLM


def _fit(
    frame: pd.DataFrame,
    predictors: Sequence[str],
    *,
    outcome: str,
):
    values = frame[list(predictors)].to_numpy(dtype=float)
    standardized = (values - values.mean(axis=0)) / values.std(axis=0)
    design = np.column_stack([np.ones(len(frame)), standardized])
    return MixedLM(
        frame[outcome].to_numpy(dtype=float),
        design,
        groups=frame["network_id"].to_numpy(),
    ).fit(reml=False, method="powell")


def _summary(result, predictors: Sequence[str]) -> dict[str, float | str]:
    fixed = result.model.exog @ result.fe_params
    fixed_variance = float(np.var(fixed))
    network_variance = float(np.asarray(result.cov_re)[0, 0])
    residual_variance = float(result.scale)
    total = fixed_variance + network_variance + residual_variance
    values: dict[str, float | str] = {
        "predictors": "|".join(predictors),
        "log_likelihood": float(result.llf),
        "fixed_variance": fixed_variance,
        "network_random_intercept_variance": network_variance,
        "residual_variance": residual_variance,
        "marginal_r2": fixed_variance / total,
        "conditional_r2": (fixed_variance + network_variance) / total,
        "n_station_gaps": float(result.nobs),
        "n_networks": float(len(np.unique(result.model.groups))),
    }
    for name, coefficient in zip(("intercept", *predictors), result.fe_params):
        values[f"coefficient_{name}"] = float(coefficient)
    return values


def compare_mixed_models(
    frame: pd.DataFrame,
    *,
    simple_predictors: Sequence[str],
    operator: str = "complete_operator_risk",
    outcome: str = "observed_recovery_loss",
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Fit simple and operator-extended mixed models on identical rows."""

    simple = _fit(frame, simple_predictors, outcome=outcome)
    extended_columns = (*simple_predictors, operator)
    extended = _fit(frame, extended_columns, outcome=outcome)
    summaries = pd.DataFrame(
        [_summary(simple, simple_predictors), _summary(extended, extended_columns)]
    )
    likelihood_ratio = float(2.0 * (extended.llf - simple.llf))
    increment = {
        "likelihood_ratio": likelihood_ratio,
        "likelihood_ratio_df": 1.0,
        "likelihood_ratio_p": float(chi2.sf(likelihood_ratio, 1)),
        "marginal_r2_increment": float(
            summaries.iloc[1]["marginal_r2"] - summaries.iloc[0]["marginal_r2"]
        ),
        "conditional_r2_increment": float(
            summaries.iloc[1]["conditional_r2"]
            - summaries.iloc[0]["conditional_r2"]
        ),
    }
    return summaries, increment


__all__ = ["compare_mixed_models"]
