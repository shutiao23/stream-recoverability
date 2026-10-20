"""Descriptive catchment labels using the external resource's percent units."""

from __future__ import annotations

import numpy as np
import pandas as pd


def hydrological_strata(frame: pd.DataFrame) -> np.ndarray:
    glacier = pd.to_numeric(frame["Glaciers %"], errors="coerce")
    snow_percent = pd.to_numeric(frame["Pt as snow"], errors="coerce")
    return np.select(
        [glacier > 0, (glacier == 0) & (snow_percent >= 50), (glacier == 0) & snow_percent.notna()],
        ["glacier_influenced", "snow_dominated", "other_mountain_catchment"],
        default="unknown_hydrological_attributes",
    )
