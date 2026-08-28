"""Deterministic cross-provider roster construction for LSTM sensitivity."""

from __future__ import annotations

import pandas as pd


def provider_domain_subset(
    candidates: pd.DataFrame, *, per_provider: int = 2
) -> pd.DataFrame:
    """Select bounded networks without consulting any recovery loss values."""

    if per_provider <= 0:
        raise ValueError("per_provider must be positive")
    required = {
        "network_id",
        "provider",
        "domain",
        "source_panel",
        "n_eligible_stations",
    }
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"candidate roster lacks columns: {sorted(missing)}")
    frame = candidates.copy()
    frame["network_id"] = frame["network_id"].astype(str)
    frame["n_eligible_stations"] = pd.to_numeric(
        frame["n_eligible_stations"], errors="raise"
    )
    source_order = {"first_confirmation": 0, "second_confirmation": 1}
    frame["_source_order"] = frame["source_panel"].map(source_order)
    if frame["_source_order"].isna().any():
        raise ValueError("unknown source_panel in LSTM candidate roster")
    frame = frame.sort_values(
        [
            "provider",
            "_source_order",
            "n_eligible_stations",
            "domain",
            "network_id",
        ],
        kind="mergesort",
    )
    selected = frame.groupby("provider", sort=True, as_index=False).head(per_provider)
    return selected.drop(columns="_source_order").reset_index(drop=True)


__all__ = ["provider_domain_subset"]
