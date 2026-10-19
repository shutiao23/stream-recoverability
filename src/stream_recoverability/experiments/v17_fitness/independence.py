"""Validation units from shared stations, not from network-label strings.

Donors in this project are the other stations of the same network
(``panel.StationYear.donors``). A station that appears under two network labels
is therefore both a repeated target record and shared donor supervision. The
validation group is the connected component of that overlap graph. Cases keep
their gap scenarios, but every scenario of a component stays in one fold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: str, right: str) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def station_membership(cases: pd.DataFrame) -> pd.DataFrame:
    needed = ["network_id", "station_id"]
    missing = [name for name in needed if name not in cases.columns]
    if missing:
        raise KeyError(f"cases are missing {missing}")
    frame = cases[needed].dropna().copy()
    frame["network_id"] = frame["network_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    return frame.drop_duplicates()


def independence_table(cases: pd.DataFrame) -> pd.DataFrame:
    """One row per network label, with its unsplittable validation group."""

    membership = station_membership(cases)
    networks = sorted(membership["network_id"].unique())
    components = _UnionFind()
    for network in networks:
        components.find(network)
    for _station, block in membership.groupby("station_id", sort=False):
        present = sorted(block["network_id"].unique())
        for other in present[1:]:
            components.union(present[0], other)
    roots = {network: components.find(network) for network in networks}
    group_of_root = {
        root: f"g{index:04d}" for index, root in enumerate(sorted(set(roots.values())))
    }
    stations = membership.groupby("network_id")["station_id"].agg(lambda values: tuple(sorted(set(values))))
    rows = []
    for network in networks:
        station_ids = stations.loc[network]
        rows.append(
            {
                "network_id": network,
                "independence_group": group_of_root[roots[network]],
                "n_stations": int(len(station_ids)),
                "station_ids": ";".join(station_ids),
            }
        )
    table = pd.DataFrame(rows)
    sizes = table.groupby("independence_group")["network_id"].transform("size")
    table["n_network_labels_in_group"] = sizes.astype(int)
    return table


def overlap_pairs(table: pd.DataFrame) -> pd.DataFrame:
    """Network-label pairs that share at least one station."""

    rows = []
    for group, block in table.groupby("independence_group", sort=True):
        if len(block) < 2:
            continue
        records = list(block.itertuples(index=False))
        for left_index, left in enumerate(records):
            left_ids = set(str(left.station_ids).split(";"))
            for right in records[left_index + 1 :]:
                right_ids = set(str(right.station_ids).split(";"))
                shared = sorted(left_ids & right_ids)
                if not shared:
                    continue
                rows.append(
                    {
                        "independence_group": group,
                        "network_a": left.network_id,
                        "network_b": right.network_id,
                        "n_shared_stations": len(shared),
                        "shared_station_ids": ";".join(shared),
                    }
                )
    return pd.DataFrame(rows)


def eligibility_row(panel: str, cases: pd.DataFrame, table: pd.DataFrame) -> dict:
    stations = cases["station_id"].astype(str)
    years = cases["year"] if "year" in cases.columns else pd.Series(np.nan, index=cases.index)
    station_year = pd.DataFrame({"station_id": stations, "year": years}).drop_duplicates()
    keyed = pd.DataFrame(
        {
            "network_id": cases["network_id"].astype(str),
            "station_id": stations,
            "year": years,
        }
    ).drop_duplicates()
    shared_station_years = int((keyed.groupby(["station_id", "year"])["network_id"].nunique() > 1).sum())
    return {
        "panel": panel,
        "n_cases": int(len(cases)),
        "n_network_labels": int(table["network_id"].nunique()),
        "n_unique_stations": int(stations.nunique()),
        "n_station_years": int(len(station_year)),
        "n_station_network_rows": int(
            keyed.drop_duplicates(["network_id", "station_id"]).shape[0]
        ),
        "n_independence_groups": int(table["independence_group"].nunique()),
        "n_groups_with_multiple_labels": int(
            (table.groupby("independence_group")["network_id"].nunique() > 1).sum()
        ),
        "n_station_years_under_multiple_labels": shared_station_years,
        "donor_rule": (
            "donors are other stations in the same network; shared-station components "
            "therefore also keep shared donor supervision inside one validation group"
        ),
    }


def group_fold_map(table: pd.DataFrame, n_splits: int, seed: int, assign_folds) -> dict[str, int]:
    """Map each network label to a fold. Labels in one component share the fold."""

    groups = sorted(table["independence_group"].astype(str).unique())
    fold_of_group = assign_folds(groups, n_splits, seed)
    group_of = dict(zip(table["network_id"].astype(str), table["independence_group"].astype(str)))
    return {network: int(fold_of_group[group]) for network, group in group_of.items()}


def shared_stations_across_folds(cases: pd.DataFrame, table: pd.DataFrame, fold_of_network: dict[str, int]) -> int:
    """Count stations whose cases fall in more than one fold. Correct splits return 0."""

    frame = cases[["network_id", "station_id"]].copy()
    frame["network_id"] = frame["network_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    frame["fold"] = frame["network_id"].map(fold_of_network)
    if frame["fold"].isna().any():
        missing = sorted(frame.loc[frame["fold"].isna(), "network_id"].unique())
        raise KeyError(f"networks without a fold: {missing[:8]}")
    counts = frame.drop_duplicates(["station_id", "fold"]).groupby("station_id")["fold"].nunique()
    return int((counts > 1).sum())


def shared_station_years_across_folds(
    cases: pd.DataFrame, fold_of_network: dict[str, int]
) -> int:
    frame = cases[["network_id", "station_id", "year"]].copy()
    frame["network_id"] = frame["network_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    frame["fold"] = frame["network_id"].map(fold_of_network)
    counts = (
        frame.drop_duplicates(["station_id", "year", "fold"])
        .groupby(["station_id", "year"])["fold"]
        .nunique()
    )
    return int((counts > 1).sum())
