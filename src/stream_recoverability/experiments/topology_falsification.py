"""E5: donor-geometry matched subsets that can alias recoverability type."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from stream_recoverability.analysis.recoverability_spectrum import spectrum_from_var1
from stream_recoverability.experiments.synthetic_river import (
    SyntheticRiver,
    advection_chain,
    endpoint_downstream_terminus,
    endpoint_upstream_origin,
)


def geometry_label(target: int, donors: Sequence[int]) -> str:
    donors = tuple(int(item) for item in donors)
    if not donors:
        return "no_donors"
    upstream = [item for item in donors if item < target]
    downstream = [item for item in donors if item > target]
    if upstream and not downstream:
        return "upstream_only"
    if downstream and not upstream:
        return "downstream_only"
    if len(upstream) == 1 and len(downstream) == 1:
        return "one_upstream_one_downstream"
    return "mixed_or_unbalanced"


def matched_subset_table(
    river: SyntheticRiver,
    *,
    gap_length: int = 30,
    donor_count: int = 2,
) -> pd.DataFrame:
    """Evaluate \(\tau\) under matched donor-count geometries."""

    rows = []
    stations = [index for index in range(river.n_stations) if index != river.target]
    # All donor_count-subsets keep count fixed.
    from itertools import combinations

    for donors in combinations(stations, donor_count):
        spectrum = spectrum_from_var1(
            river.transition,
            river.sigma,
            target=river.target,
            donors=donors,
            gap_length=gap_length,
        )
        rows.append(
            {
                "river": river.name,
                "target": river.target,
                "donors": ",".join(str(item) for item in donors),
                "geometry": geometry_label(river.target, donors),
                "n_donors": donor_count,
                "gap_length": gap_length,
                **spectrum.as_dict(),
            }
        )
    return pd.DataFrame(rows)


def endpoint_alias_audit(gap_length: int = 30) -> pd.DataFrame:
    """Compare one-sided endpoint graphs with a mid-chain control."""

    rivers = [
        endpoint_upstream_origin(),
        endpoint_downstream_terminus(),
        advection_chain(n_stations=5),
    ]
    rows = []
    for river in rivers:
        spectrum = spectrum_from_var1(
            river.transition,
            river.sigma,
            target=river.target,
            donors=river.donors,
            gap_length=gap_length,
        )
        rows.append(
            {
                "river": river.name,
                "target": river.target,
                "geometry": geometry_label(river.target, river.donors),
                "network_endpoint": river.target in {0, river.n_stations - 1},
                **spectrum.as_dict(),
            }
        )
    return pd.DataFrame(rows)


def geometry_stability(table: pd.DataFrame) -> dict[str, float | bool]:
    """Spectrum is unstable if geometry flips the sign at fixed donor count."""

    if table.empty or "sign" not in table or "geometry" not in table:
        return {"stable": False, "n_geometries": 0.0, "n_sign_changes": float("nan")}
    signs = table.groupby("geometry")["sign"].agg(lambda values: set(values.tolist()))
    unique_signs = set().union(*signs.tolist()) if len(signs) else set()
    return {
        "stable": len(unique_signs) <= 1,
        "n_geometries": float(table["geometry"].nunique()),
        "n_distinct_signs": float(len(unique_signs)),
        "n_sign_changes": float(max(len(unique_signs) - 1, 0)),
    }


def run_topology_suite() -> dict[str, pd.DataFrame | dict[str, float | bool]]:
    chain = advection_chain(n_stations=6)
    matched = matched_subset_table(chain, donor_count=2)
    return {
        "matched_subsets": matched,
        "endpoint_audit": endpoint_alias_audit(),
        "stability": geometry_stability(matched),
    }


__all__ = [
    "endpoint_alias_audit",
    "geometry_label",
    "geometry_stability",
    "matched_subset_table",
    "run_topology_suite",
]
