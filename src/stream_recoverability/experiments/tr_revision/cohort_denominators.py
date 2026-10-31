"""Denominators for method comparisons on saved uncertainty cases.

Within-method "common cases" are archives for which one estimator has every
rank and tail output. The two-method intersection is the smaller set on which
D2 and the calibrated classical estimator can be compared as a pair. Those
are different denominators.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KEY = ["family", "mode", "station_key", "replicate"]


def two_method_intersection(cases: pd.DataFrame) -> pd.DataFrame:
    required = KEY + [
        "estimator",
        "n_eligible",
        "coverage90",
        "independent_coverage95",
        "independence_group",
    ]
    missing = [column for column in required if column not in cases]
    if missing:
        raise ValueError("Uncertainty cases are missing columns: " + ", ".join(missing))
    rows = []
    for (family, mode), block in cases.groupby(["family", "mode"], sort=True):
        estimators = {
            "D2": block.loc[block.estimator.eq("D2")].set_index(KEY),
            "stochastic_calibrated": block.loc[
                block.estimator.eq("stochastic_calibrated")
            ].set_index(KEY),
        }
        for name, frame in estimators.items():
            if frame.index.has_duplicates:
                raise ValueError(f"{name} archive keys are duplicated for {family} {mode}")
        shared = estimators["D2"].index.intersection(estimators["stochastic_calibrated"].index)
        left = estimators["D2"].loc[shared]
        right = estimators["stochastic_calibrated"].loc[shared]
        if len(shared) == 0:
            raise ValueError(f"No two-method intersection for {family} {mode}")
        if not np.array_equal(left.n_eligible.to_numpy(), right.n_eligible.to_numpy()):
            raise ValueError(f"Eligible-year weights differ on the {family} {mode} intersection")
        weight = left.n_eligible.to_numpy(float)
        rows.append(
            {
                "family": family,
                "mode": mode,
                "n_own_d2": int(len(estimators["D2"])),
                "n_own_classic": int(len(estimators["stochastic_calibrated"])),
                "n_paired": int(len(shared)),
                "incomplete_years": int(weight.sum()),
                "stations": int(left.index.get_level_values("station_key").nunique()),
                "groups": int(left.independence_group.nunique()),
                "annual_weighted_d2": float(np.average(left.coverage90, weights=weight)),
                "annual_weighted_classic": float(np.average(right.coverage90, weights=weight)),
                "annual_equal_d2": float(left.coverage90.mean()),
                "annual_equal_classic": float(right.coverage90.mean()),
                "trend_independent_d2": float(left.independent_coverage95.mean()),
                "trend_independent_classic": float(right.independent_coverage95.mean()),
            }
        )
    return pd.DataFrame(rows)
