"""Reconstruction policies and the action spaces whose ceilings Step 4 measures.

The reconstruction layer is not the contribution of this study; it is the
settled part. What Step 4 asks is how much *any* decision rule could win inside
each candidate action space, so that the programme never again tests a rule in
a space where the prize is smaller than the measuring error.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_ESTIMATOR = "doy_climatology"
CANDIDATE_ESTIMATORS = (
    "observed_days",
    "doy_climatology",
    "smooth_climatology",
    "linear_interp",
    "donor_ridge",
    "air_ridge",
)
SHORT_GAP_DAYS = 30


def information_conditioned_choice(cases: pd.DataFrame) -> pd.Series:
    """The v16 information-conditioned simple policy, reimplemented on v17 cases.

    Donors when donors are visible; else air where forcing exists; else linear
    interpolation for short interior gaps; else the smooth climatology.
    """

    choice = pd.Series(DEFAULT_ESTIMATOR, index=cases.index, dtype=object)
    smooth = cases["abserr_smooth_climatology"].notna()
    choice.loc[smooth] = "smooth_climatology"
    short = (
        (pd.to_numeric(cases["longest_run"], errors="coerce") <= SHORT_GAP_DAYS)
        & cases["left_flank"].astype(bool)
        & cases["right_flank"].astype(bool)
        & cases["abserr_linear_interp"].notna()
    )
    choice.loc[short] = "linear_interp"
    air = cases["air_available"].astype(bool) & cases["abserr_air_ridge"].notna()
    choice.loc[air] = "air_ridge"
    donors = (pd.to_numeric(cases["n_visible_donors"], errors="coerce") > 0) & cases["abserr_donor_ridge"].notna()
    choice.loc[donors] = "donor_ridge"
    return choice


def gather(cases: pd.DataFrame, choice: pd.Series, prefix: str = "abserr_") -> np.ndarray:
    """Pick, for each row, the column named by ``choice``."""

    values = np.full(len(cases), np.nan, dtype=float)
    for name in choice.unique():
        column = f"{prefix}{name}"
        if column not in cases.columns:
            continue
        mask = (choice == name).to_numpy()
        values[mask] = pd.to_numeric(cases.loc[mask, column], errors="coerce").to_numpy(dtype=float)
    return values


def available_matrix(cases: pd.DataFrame, estimators=CANDIDATE_ESTIMATORS, prefix: str = "abserr_") -> pd.DataFrame:
    columns = [f"{prefix}{name}" for name in estimators if f"{prefix}{name}" in cases.columns]
    return cases[columns]


def attach_policy_errors(cases: pd.DataFrame) -> pd.DataFrame:
    """Add the deployed policy error, the default error, and the two oracles."""

    frame = cases.copy()
    choice = information_conditioned_choice(frame)
    frame["policy_choice"] = choice
    frame["abserr_policy"] = gather(frame, choice)
    frame["err_policy"] = gather(frame, choice, prefix="err_")
    frame["abserr_default"] = pd.to_numeric(frame[f"abserr_{DEFAULT_ESTIMATOR}"], errors="coerce")

    # Deployable estimator set excludes observed_days, which is a competitor
    # baseline rather than a reconstruction, and excludes unsupported methods.
    deployable = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
    matrix = available_matrix(frame, deployable)
    frame["abserr_oracle_method"] = matrix.min(axis=1, skipna=True)
    frame["oracle_method_name"] = matrix.idxmin(axis=1, skipna=True).str.replace("abserr_", "", regex=False)

    # Benefit over the named default, the v16 estimand.
    frame["bq_policy"] = frame["abserr_default"] - frame["abserr_policy"]
    frame["bq_oracle_method"] = frame["abserr_default"] - frame["abserr_oracle_method"]
    frame["bq_adopt_reject"] = frame["bq_policy"].clip(lower=0.0)
    return frame
