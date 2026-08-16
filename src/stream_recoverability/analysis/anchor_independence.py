"""Catalog-only audit of validation-anchor temporal independence.

The 180-day centered windows are reconstructed from ``center_date`` and
``max_supported_length`` using the same half-open centering convention as
``centered_bounds``.  Ranking stability is intentionally *not* estimated:
leave-one-anchor-out, leave-one-station-out, and bootstrap rank tables are
schema placeholders until validation-funnel outputs exist.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.experiments.validation import VALIDATION_STRATA
from stream_recoverability.masks import centered_bounds, meteorological_season

NEARBY_CENTER_DAYS = 14
JACCARD_HIGH_THRESHOLD = 0.5
B1_DECEMBER_2016_CENTERS = (pd.Timestamp("2016-12-02"), pd.Timestamp("2016-12-19"))
IDENTICAL_CROSS_STATION_CENTER = pd.Timestamp("2017-03-27")
IID_WARNING = (
    "validation ranking must not treat 105 units "
    "(3 stations × 5 anchors × 7 strata) as iid; "
    "the five 180-day anchors per station share calendar dates"
)
PENDING_RANKING_REASON = (
    "ranking_cannot_be_computed_without_validation_funnel_outputs;"
    "do_not_interpret_as_model_rank_stability;"
    + IID_WARNING
)
LEAVE_ONE_ANCHOR_OUT_COLUMNS = (
    "left_out_anchor_id",
    "model",
    "rank",
    "mean_skill_across_strata",
    "n_anchors_used",
    "pending_validation_results",
    "reason",
)
LEAVE_ONE_STATION_OUT_COLUMNS = (
    "left_out_station_id",
    "model",
    "rank",
    "mean_skill_across_strata",
    "n_stations_used",
    "pending_validation_results",
    "reason",
)
BOOTSTRAP_RANK_COLUMNS = (
    "model",
    "rank",
    "bootstrap_probability",
    "n_bootstrap",
    "pending_validation_results",
    "reason",
)
PAIRWISE_COLUMNS = (
    "left_anchor_id",
    "right_anchor_id",
    "left_station_id",
    "right_station_id",
    "left_center_date",
    "right_center_date",
    "left_season",
    "right_season",
    "left_year",
    "right_year",
    "same_station",
    "same_season",
    "center_date_distance_days",
    "left_window_days",
    "right_window_days",
    "overlap_days",
    "union_days",
    "jaccard",
    "has_temporal_overlap",
    "flag_b1_december_2016_pair",
    "flag_s2_mam_pair",
    "flag_same_center_date_cross_station",
    "flag_nearby_center_date_cross_station",
    "flag_jaccard_ge_0_5",
    "left_anchor_label",
    "right_anchor_label",
    "pair_flags",
)
YEAR_COVERAGE_COLUMNS = (
    "station_id",
    "n_anchors",
    "unique_years",
    "n_years",
    "years_equal_n_anchors",
    "note",
)
STATION_EFFECTIVE_N_COLUMNS = (
    "station_id",
    "n_anchors",
    "window_days",
    "union_days",
    "effective_n",
    "formula",
    "note",
)
NAMED_FINDING_COLUMNS = (
    "finding_id",
    "finding_name",
    "left_anchor_label",
    "right_anchor_label",
    "left_anchor_id",
    "right_anchor_id",
    "left_center_date",
    "right_center_date",
    "overlap_days",
    "jaccard",
    "n_years",
    "n_anchors",
    "effective_n",
    "statement",
    "must_not_treat_as_iid",
)
FRONTIER_EFFECTIVE_N_COLUMNS = (
    "scope",
    "station_id",
    "target",
    "n_anchors",
    "window_days",
    "union_days",
    "effective_n",
    "formula",
    "unique_years",
)
COMPONENT_COLUMNS = (
    "overlap_component_id",
    "graph_scope",
    "station_id",
    "anchor_ids",
    "anchor_count",
    "temporal_union_days",
    "has_overlap",
    "component_flags",
)
COVERAGE_COLUMNS = (
    "date",
    "year",
    "season",
    "anchors_covering_date",
    "stations_covering_date",
    "anchor_ids",
    "station_ids",
    "unique_to_one_anchor",
    "same_station_overlap",
    "cross_station_coverage",
    "temporal_overlap_flag",
)


@dataclass(frozen=True)
class AnchorIndependenceAudit:
    """Machine-readable result of :func:`audit_validation_anchor_independence`."""

    pairwise: pd.DataFrame
    same_station_pairwise: pd.DataFrame
    overlap_components: pd.DataFrame
    unique_date_coverage: pd.DataFrame
    year_coverage: pd.DataFrame
    station_effective_n: pd.DataFrame
    named_findings: pd.DataFrame
    frontier_effective_n: pd.DataFrame
    leave_one_anchor_out_ranking: pd.DataFrame
    leave_one_station_out_ranking: pd.DataFrame
    bootstrap_rank_probabilities: pd.DataFrame
    summary: dict[str, Any]

    def artifact_frames(self) -> dict[str, pd.DataFrame]:
        """Return copies keyed by the required P0-5 artifact names."""

        frames = {
            "anchor_pairwise_jaccard.csv": self.pairwise.copy(),
            "anchor_same_station_pairwise_jaccard.csv": (
                self.same_station_pairwise.copy()
            ),
            "anchor_overlap_components.csv": self.overlap_components.copy(),
            "anchor_unique_date_coverage.csv": self.unique_date_coverage.copy(),
            "anchor_year_coverage.csv": self.year_coverage.copy(),
            "anchor_station_effective_n.csv": self.station_effective_n.copy(),
            "anchor_named_findings.csv": self.named_findings.copy(),
            "leave_one_anchor_out_ranking.csv": (
                self.leave_one_anchor_out_ranking.copy()
            ),
            "leave_one_station_out_ranking.csv": (
                self.leave_one_station_out_ranking.copy()
            ),
            "bootstrap_rank_probabilities.csv": (
                self.bootstrap_rank_probabilities.copy()
            ),
        }
        if not self.frontier_effective_n.empty:
            frames["frontier_station_effective_n.csv"] = (
                self.frontier_effective_n.copy()
            )
        return frames


def _require_columns(
    frame: pd.DataFrame, columns: Sequence[str], *, context: str
) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{context} requires columns: {missing}")


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0 else 0.0


def _connected_components(
    identifiers: Sequence[str], edges: Sequence[tuple[str, str]]
) -> list[tuple[str, ...]]:
    adjacency = {identifier: set() for identifier in identifiers}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    components: list[tuple[str, ...]] = []
    visited: set[str] = set()
    for root in sorted(adjacency):
        if root in visited:
            continue
        pending = [root]
        component: list[str] = []
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            pending.extend(sorted(adjacency[current] - visited, reverse=True))
        components.append(tuple(sorted(component)))
    return components


def _join_ids(values: Sequence[str]) -> str:
    return "|".join(str(value) for value in values)


def _anchor_label(anchor_id: str, station_id: str) -> str:
    token = str(anchor_id).rsplit("-", maxsplit=1)[-1]
    if token.startswith("R") and token[1:].isdigit():
        return f"{station_id}-{token}"
    return str(anchor_id)


def _parse_center_dates(frame: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(frame["center_date"], errors="coerce").dt.normalize()
    if dates.isna().any():
        raise ValueError("center_date contains invalid dates")
    return dates


def _window_dates(center: pd.Timestamp, length: int) -> pd.DatetimeIndex:
    if not isinstance(length, (int, np.integer)) or int(length) <= 0:
        raise ValueError("max_supported_length must be a positive integer")
    length = int(length)
    # Reconstruct the date set without a global time axis: centered_bounds
    # uses start = center_index - (length - 1) // 2.
    dummy_center = (length - 1) // 2
    start_offset, _stop = centered_bounds(dummy_center, length)
    start = center + pd.Timedelta(days=int(start_offset - dummy_center))
    return pd.date_range(start, periods=length, freq="D")


def _flag_b1_december_2016(
    left_station: str,
    right_station: str,
    left_center: pd.Timestamp,
    right_center: pd.Timestamp,
) -> bool:
    if {left_station, right_station} != {"B1"}:
        return False
    return {left_center, right_center} == set(B1_DECEMBER_2016_CENTERS)


def _flag_s2_mam(
    left_station: str,
    right_station: str,
    left_season: str,
    right_season: str,
) -> bool:
    return (
        left_station == "S2"
        and right_station == "S2"
        and left_season == "MAM"
        and right_season == "MAM"
    )


def _empty_finding(**overrides: Any) -> dict[str, Any]:
    row = {column: pd.NA for column in NAMED_FINDING_COLUMNS}
    row["must_not_treat_as_iid"] = True
    row.update(overrides)
    return row


def _anchor_named_findings(
    pairwise: pd.DataFrame,
    year_coverage: pd.DataFrame,
    station_effective_n: pd.DataFrame,
    *,
    n_stations: int,
    n_anchors_per_station: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    b1 = pairwise.loc[pairwise["flag_b1_december_2016_pair"]]
    if len(b1) == 1:
        pair = b1.iloc[0]
        # Report in the required label order: R0105 (2016-12-02) then R0101.
        by_date = sorted(
            (
                (
                    pair["left_center_date"],
                    pair["left_anchor_label"],
                    pair["left_anchor_id"],
                ),
                (
                    pair["right_center_date"],
                    pair["right_anchor_label"],
                    pair["right_anchor_id"],
                ),
            )
        )
        rows.append(
            _empty_finding(
                finding_id="b1_december_2016_double_anchor",
                finding_name="B1-R0105 (2016-12-02) ↔ B1-R0101 (2016-12-19)",
                left_anchor_label=by_date[0][1],
                right_anchor_label=by_date[1][1],
                left_anchor_id=by_date[0][2],
                right_anchor_id=by_date[1][2],
                left_center_date=by_date[0][0],
                right_center_date=by_date[1][0],
                overlap_days=int(pair["overlap_days"]),
                jaccard=float(pair["jaccard"]),
                statement=(
                    "B1-R0105 (2016-12-02) and B1-R0101 (2016-12-19) share a "
                    f"{int(pair['overlap_days'])}-day window overlap "
                    f"(Jaccard {float(pair['jaccard']):.3f}). "
                    "These two DJF anchors are not independent validation units."
                ),
            )
        )
    for year_row in year_coverage.itertuples(index=False):
        rows.append(
            _empty_finding(
                finding_id=f"unique_years_{year_row.station_id}",
                finding_name=f"{year_row.station_id}_years_not_equal_anchors",
                n_years=int(year_row.n_years),
                n_anchors=int(year_row.n_anchors),
                statement=(
                    f"{year_row.station_id} unique years = {{{year_row.unique_years.replace('|', ',')}}}; "
                    f"n_years={int(year_row.n_years)} ≠ n_anchors={int(year_row.n_anchors)}"
                ),
            )
        )
    for ess_row in station_effective_n.itertuples(index=False):
        rows.append(
            _empty_finding(
                finding_id=f"effective_n_{ess_row.station_id}",
                finding_name=f"{ess_row.station_id}_union_days_over_window",
                n_anchors=int(ess_row.n_anchors),
                effective_n=float(ess_row.effective_n),
                statement=(
                    f"{ess_row.station_id} effective_n = union_days/window_days = "
                    f"{int(ess_row.union_days)}/{int(ess_row.window_days)} = "
                    f"{float(ess_row.effective_n):.2f}"
                ),
            )
        )
    identical = pairwise.loc[pairwise["flag_same_center_date_cross_station"]]
    for _, pair in identical.iterrows():
        is_declared = pd.Timestamp(pair["left_center_date"]) == IDENTICAL_CROSS_STATION_CENTER
        rows.append(
            _empty_finding(
                finding_id=(
                    "cross_station_identical_center"
                    if is_declared
                    else "cross_station_identical_center_other"
                ),
                finding_name=(
                    f"{pair['left_anchor_label']} = {pair['right_anchor_label']} = "
                    f"{pair['left_center_date']}"
                ),
                left_anchor_label=str(pair["left_anchor_label"]),
                right_anchor_label=str(pair["right_anchor_label"]),
                left_anchor_id=str(pair["left_anchor_id"]),
                right_anchor_id=str(pair["right_anchor_id"]),
                left_center_date=str(pair["left_center_date"]),
                right_center_date=str(pair["right_center_date"]),
                overlap_days=int(pair["overlap_days"]),
                jaccard=float(pair["jaccard"]),
                statement=(
                    f"{pair['left_anchor_label']} and {pair['right_anchor_label']} "
                    f"share the identical center date {pair['left_center_date']}. "
                    "Cross-station ranking units on this date are not independent."
                ),
            )
        )
    n_iid = n_stations * n_anchors_per_station * len(VALIDATION_STRATA)
    rows.append(
        _empty_finding(
            finding_id="validation_units_not_iid",
            finding_name="do_not_treat_105_units_as_iid",
            n_anchors=n_anchors_per_station,
            statement=(
                f"{IID_WARNING}. Apparent unit count = "
                f"{n_stations} stations × {n_anchors_per_station} anchors × "
                f"{len(VALIDATION_STRATA)} strata = {n_iid}."
            ),
        )
    )
    high = pairwise.loc[pairwise["flag_jaccard_ge_0_5"]]
    rows.append(
        _empty_finding(
            finding_id="same_station_jaccard_ge_0_5",
            finding_name="high_same_station_jaccard_pairs",
            n_anchors=int(len(high)),
            statement=(
                f"{int(len(high))} same-station pairs have Jaccard ≥ "
                f"{JACCARD_HIGH_THRESHOLD}; full 30-pair table is "
                "anchor_same_station_pairwise_jaccard.csv"
            ),
        )
    )
    return pd.DataFrame(rows, columns=NAMED_FINDING_COLUMNS)


def audit_frontier_effective_n(catalog: pd.DataFrame) -> pd.DataFrame:
    """Optional 365-day frontier overlap note; not performance evidence."""

    required = ("anchor_id", "station_id", "center_date", "max_supported_length")
    _require_columns(catalog, required, context="frontier overlap note")
    if catalog.empty:
        return pd.DataFrame(columns=FRONTIER_EFFECTIVE_N_COLUMNS)
    frame = catalog.copy()
    frame["anchor_id"] = frame["anchor_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    if "target" not in frame.columns:
        frame["target"] = "ALL"
    else:
        frame["target"] = frame["target"].astype(str)
    frame["center_date"] = _parse_center_dates(frame)
    frame["max_supported_length"] = pd.to_numeric(
        frame["max_supported_length"], errors="coerce"
    ).astype(int)
    years = ""
    if "year" in frame.columns:
        years = _join_ids(
            str(int(year)) for year in sorted(frame["year"].dropna().unique())
        )
    rows: list[dict[str, Any]] = []
    grouped = [
        ("station_target", ["station_id", "target"]),
        ("station", ["station_id"]),
    ]
    for scope, keys in grouped:
        for key, group in frame.groupby(keys, observed=True, sort=True):
            if not isinstance(key, tuple):
                key = (key,)
            metadata = dict(zip(keys, key, strict=True))
            union: set[pd.Timestamp] = set()
            window_days = int(group["max_supported_length"].iloc[0])
            for row in group.itertuples(index=False):
                union.update(_window_dates(row.center_date, int(row.max_supported_length)))
            rows.append(
                {
                    "scope": scope,
                    "station_id": str(metadata["station_id"]),
                    "target": str(metadata.get("target", "ALL"))
                    if scope == "station_target"
                    else "ALL",
                    "n_anchors": int(len(group)),
                    "window_days": window_days,
                    "union_days": len(union),
                    "effective_n": _safe_ratio(len(union), window_days),
                    "formula": "union_days/window_days",
                    "unique_years": years,
                }
            )
    return pd.DataFrame(rows, columns=FRONTIER_EFFECTIVE_N_COLUMNS)


def _pending_ranking_frame(columns: Sequence[str]) -> pd.DataFrame:
    row = {column: pd.NA for column in columns}
    row["pending_validation_results"] = True
    row["reason"] = PENDING_RANKING_REASON
    frame = pd.DataFrame([row], columns=list(columns))
    frame["pending_validation_results"] = True
    return frame


def _component_flags(
    members: Sequence[str],
    records: Mapping[str, Mapping[str, Any]],
    *,
    graph_scope: str,
) -> str:
    flags: list[str] = []
    member_records = [records[member] for member in members]
    stations = {str(item["station_id"]) for item in member_records}
    if len(members) > 1:
        flags.append("anchors_not_independent")
    if graph_scope == "same_station" and len(stations) != 1:
        raise AssertionError("same-station component mixed stations")
    if graph_scope == "all_stations" and len(stations) > 1:
        flags.append("cross_station_overlap")
    centers = {item["center_date"] for item in member_records}
    seasons = {item["season"] for item in member_records}
    if stations == {"B1"} and set(B1_DECEMBER_2016_CENTERS).issubset(centers):
        flags.append("b1_december_2016_pair")
    if stations == {"S2"} and "MAM" in seasons:
        mam_count = sum(item["season"] == "MAM" for item in member_records)
        if mam_count >= 2:
            flags.append("s2_mam_pair")
    return "|".join(flags)


def audit_validation_anchor_independence(
    catalog: pd.DataFrame,
) -> AnchorIndependenceAudit:
    """Audit pairwise 180-day window overlap from a frozen validation catalog.

    Parameters
    ----------
    catalog:
        Validation-anchor table with ``anchor_id``, ``station_id``,
        ``center_date``, ``season``, ``year``, and ``max_supported_length``.

    Ranking CSVs are returned as explicit pending placeholders.  They must not
    be read as evidence that any model ranking is stable.
    """

    required = (
        "anchor_id",
        "station_id",
        "center_date",
        "season",
        "year",
        "max_supported_length",
    )
    _require_columns(catalog, required, context="validation anchor independence audit")
    if catalog.empty:
        raise ValueError("validation anchor catalog is empty")
    if catalog["anchor_id"].isna().any():
        raise ValueError("anchor_id must be non-missing")
    identifiers = catalog["anchor_id"].astype(str)
    if identifiers.duplicated().any():
        raise ValueError("anchor_id values must be unique")
    if identifiers.str.strip().eq("").any():
        raise ValueError("anchor_id must not be empty")

    frame = catalog.copy()
    frame["anchor_id"] = identifiers
    frame["station_id"] = frame["station_id"].astype(str)
    frame["season"] = frame["season"].astype(str)
    frame["center_date"] = _parse_center_dates(frame)
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    if frame["year"].isna().any() or not np.isfinite(frame["year"]).all():
        raise ValueError("year must be finite")
    frame["year"] = frame["year"].astype(int)
    frame["max_supported_length"] = pd.to_numeric(
        frame["max_supported_length"], errors="coerce"
    )
    if (
        frame["max_supported_length"].isna().any()
        or not np.isfinite(frame["max_supported_length"]).all()
        or (frame["max_supported_length"] <= 0).any()
        or not np.isclose(
            frame["max_supported_length"], np.round(frame["max_supported_length"])
        ).all()
    ):
        raise ValueError("max_supported_length must be a positive integer")
    frame["max_supported_length"] = frame["max_supported_length"].astype(int)
    frame = frame.sort_values(["station_id", "anchor_id"], kind="stable").reset_index(
        drop=True
    )

    date_sets: dict[str, set[pd.Timestamp]] = {}
    records: dict[str, dict[str, Any]] = {}
    for row in frame.itertuples(index=False):
        window = _window_dates(row.center_date, int(row.max_supported_length))
        date_sets[str(row.anchor_id)] = set(window)
        records[str(row.anchor_id)] = {
            "station_id": str(row.station_id),
            "center_date": pd.Timestamp(row.center_date),
            "season": str(row.season),
            "year": int(row.year),
            "window_days": int(row.max_supported_length),
        }

    ordered_ids = [str(value) for value in frame["anchor_id"]]
    pair_rows: list[dict[str, Any]] = []
    same_station_edges: list[tuple[str, str]] = []
    all_station_edges: list[tuple[str, str]] = []
    for position, left_id in enumerate(ordered_ids):
        for right_id in ordered_ids[position + 1 :]:
            left = records[left_id]
            right = records[right_id]
            intersection = date_sets[left_id] & date_sets[right_id]
            union = date_sets[left_id] | date_sets[right_id]
            overlap_days = len(intersection)
            union_days = len(union)
            jaccard = _safe_ratio(overlap_days, union_days)
            if not np.isfinite(jaccard):
                raise ValueError("non-finite Jaccard encountered")
            same_station = left["station_id"] == right["station_id"]
            center_distance = abs(
                int((left["center_date"] - right["center_date"]).days)
            )
            flag_b1 = _flag_b1_december_2016(
                left["station_id"],
                right["station_id"],
                left["center_date"],
                right["center_date"],
            )
            flag_s2 = _flag_s2_mam(
                left["station_id"],
                right["station_id"],
                left["season"],
                right["season"],
            )
            flag_same_center = (not same_station) and center_distance == 0
            flag_nearby = (
                (not same_station)
                and 0 < center_distance <= NEARBY_CENTER_DAYS
            )
            flag_high_jaccard = same_station and jaccard >= JACCARD_HIGH_THRESHOLD
            flags = []
            if flag_b1:
                flags.append("b1_december_2016_pair")
            if flag_s2:
                flags.append("s2_mam_pair")
            if flag_same_center:
                flags.append("same_center_date_cross_station")
            if flag_nearby:
                flags.append("nearby_center_date_cross_station")
            if flag_high_jaccard:
                flags.append("jaccard_ge_0_5")
            has_overlap = overlap_days > 0
            if has_overlap:
                all_station_edges.append((left_id, right_id))
                if same_station:
                    same_station_edges.append((left_id, right_id))
            pair_rows.append(
                {
                    "left_anchor_id": left_id,
                    "right_anchor_id": right_id,
                    "left_station_id": left["station_id"],
                    "right_station_id": right["station_id"],
                    "left_center_date": left["center_date"].strftime("%Y-%m-%d"),
                    "right_center_date": right["center_date"].strftime("%Y-%m-%d"),
                    "left_season": left["season"],
                    "right_season": right["season"],
                    "left_year": left["year"],
                    "right_year": right["year"],
                    "same_station": same_station,
                    "same_season": left["season"] == right["season"],
                    "center_date_distance_days": center_distance,
                    "left_window_days": left["window_days"],
                    "right_window_days": right["window_days"],
                    "overlap_days": overlap_days,
                    "union_days": union_days,
                    "jaccard": jaccard,
                    "has_temporal_overlap": has_overlap,
                    "flag_b1_december_2016_pair": flag_b1,
                    "flag_s2_mam_pair": flag_s2,
                    "flag_same_center_date_cross_station": flag_same_center,
                    "flag_nearby_center_date_cross_station": flag_nearby,
                    "flag_jaccard_ge_0_5": flag_high_jaccard,
                    "left_anchor_label": _anchor_label(left_id, left["station_id"]),
                    "right_anchor_label": _anchor_label(right_id, right["station_id"]),
                    "pair_flags": "|".join(flags),
                }
            )
    pairwise = pd.DataFrame(pair_rows, columns=PAIRWISE_COLUMNS)

    component_rows: list[dict[str, Any]] = []
    for graph_scope, edges in (
        ("same_station", same_station_edges),
        ("all_stations", all_station_edges),
    ):
        if graph_scope == "same_station":
            components = []
            for station_id, group in frame.groupby("station_id", observed=True, sort=True):
                station_members = [str(value) for value in group["anchor_id"]]
                station_edges = [
                    edge
                    for edge in edges
                    if edge[0] in station_members and edge[1] in station_members
                ]
                for members in _connected_components(station_members, station_edges):
                    components.append((str(station_id), members))
            labeled = components
        else:
            labeled = [
                ("ALL", members)
                for members in _connected_components(ordered_ids, edges)
            ]
        prefix = "SS" if graph_scope == "same_station" else "AS"
        for position, (station_id, members) in enumerate(labeled, start=1):
            union_dates: set[pd.Timestamp] = set()
            for member in members:
                union_dates.update(date_sets[member])
            component_rows.append(
                {
                    "overlap_component_id": f"{prefix}{position:04d}",
                    "graph_scope": graph_scope,
                    "station_id": station_id,
                    "anchor_ids": _join_ids(members),
                    "anchor_count": len(members),
                    "temporal_union_days": len(union_dates),
                    "has_overlap": len(members) > 1,
                    "component_flags": _component_flags(
                        members, records, graph_scope=graph_scope
                    ),
                }
            )
    overlap_components = pd.DataFrame(component_rows, columns=COMPONENT_COLUMNS)

    coverage_by_date: dict[pd.Timestamp, list[str]] = {}
    for anchor_id, dates in date_sets.items():
        for date in dates:
            coverage_by_date.setdefault(date, []).append(anchor_id)
    coverage_rows: list[dict[str, Any]] = []
    for date in sorted(coverage_by_date):
        anchors = tuple(sorted(coverage_by_date[date]))
        stations = tuple(
            sorted({records[anchor_id]["station_id"] for anchor_id in anchors})
        )
        station_counts: dict[str, int] = {}
        for anchor_id in anchors:
            station = records[anchor_id]["station_id"]
            station_counts[station] = station_counts.get(station, 0) + 1
        coverage_rows.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "year": int(date.year),
                "season": meteorological_season(int(date.month)),
                "anchors_covering_date": len(anchors),
                "stations_covering_date": len(stations),
                "anchor_ids": _join_ids(anchors),
                "station_ids": _join_ids(stations),
                "unique_to_one_anchor": len(anchors) == 1,
                "same_station_overlap": any(count > 1 for count in station_counts.values()),
                "cross_station_coverage": len(stations) > 1,
                "temporal_overlap_flag": len(anchors) > 1,
            }
        )
    unique_date_coverage = pd.DataFrame(coverage_rows, columns=COVERAGE_COLUMNS)

    same_station_pairs = pairwise.loc[pairwise["same_station"]]
    same_station_components = overlap_components.loc[
        overlap_components["graph_scope"].eq("same_station")
    ]
    all_station_components = overlap_components.loc[
        overlap_components["graph_scope"].eq("all_stations")
    ]
    max_same_station_jaccard = (
        float(same_station_pairs["jaccard"].max()) if len(same_station_pairs) else 0.0
    )
    max_jaccard = float(pairwise["jaccard"].max()) if len(pairwise) else 0.0
    n_same_station_overlap_components = int(
        (same_station_components["anchor_count"] > 1).sum()
    )
    n_all_station_overlap_components = int(
        (all_station_components["anchor_count"] > 1).sum()
    )
    flagged = pairwise.loc[
        pairwise["flag_b1_december_2016_pair"]
        | pairwise["flag_s2_mam_pair"]
        | pairwise["flag_same_center_date_cross_station"]
        | pairwise["flag_nearby_center_date_cross_station"]
    ]
    same_station_pairwise = same_station_pairs.reset_index(drop=True)
    year_rows: list[dict[str, Any]] = []
    for station_id, group in frame.groupby("station_id", observed=True, sort=True):
        years = tuple(sorted(int(year) for year in group["year"].unique()))
        n_anchors = int(len(group))
        n_years = len(years)
        year_rows.append(
            {
                "station_id": str(station_id),
                "n_anchors": n_anchors,
                "unique_years": _join_ids(str(year) for year in years),
                "n_years": n_years,
                "years_equal_n_anchors": n_years == n_anchors,
                "note": (
                    f"n_years={n_years} ≠ n_anchors={n_anchors}"
                    if n_years != n_anchors
                    else "years_match_anchor_count"
                ),
            }
        )
    year_coverage = pd.DataFrame(year_rows, columns=YEAR_COVERAGE_COLUMNS)

    effective_rows: list[dict[str, Any]] = []
    for row in same_station_components.itertuples(index=False):
        window_days = 180
        if len(row.anchor_ids.split("|")):
            first_id = str(row.anchor_ids.split("|")[0])
            window_days = int(records[first_id]["window_days"])
        effective_n = _safe_ratio(int(row.temporal_union_days), window_days)
        effective_rows.append(
            {
                "station_id": str(row.station_id),
                "n_anchors": int(row.anchor_count),
                "window_days": window_days,
                "union_days": int(row.temporal_union_days),
                "effective_n": effective_n,
                "formula": "union_days/window_days",
                "note": (
                    f"{row.station_id} five anchors collapse to {effective_n:.2f} "
                    "independent 180-day windows"
                ),
            }
        )
    station_effective_n = pd.DataFrame(
        effective_rows, columns=STATION_EFFECTIVE_N_COLUMNS
    )

    named_findings = _anchor_named_findings(
        pairwise,
        year_coverage,
        station_effective_n,
        n_stations=int(frame["station_id"].nunique()),
        n_anchors_per_station=int(frame.groupby("station_id").size().max())
        if len(frame)
        else 0,
    )
    n_iid_units = (
        int(frame["station_id"].nunique())
        * int(frame.groupby("station_id").size().iloc[0])
        * len(VALIDATION_STRATA)
        if len(frame)
        else 0
    )
    unique_years = tuple(sorted(int(year) for year in frame["year"].unique()))
    summary = {
        "audit_status": "catalog_overlap_audit",
        "n_anchors": len(ordered_ids),
        "n_pairs": len(pairwise),
        "n_same_station_pairs": int(same_station_pairs.shape[0]),
        "n_same_station_overlapping_pairs": int(
            same_station_pairs["has_temporal_overlap"].sum()
        ),
        "n_same_station_jaccard_ge_0_5": int(
            same_station_pairs["flag_jaccard_ge_0_5"].sum()
        )
        if len(same_station_pairs)
        else 0,
        "max_same_station_jaccard": max_same_station_jaccard,
        "max_jaccard": max_jaccard,
        "n_same_station_components": int(len(same_station_components)),
        "n_same_station_overlap_components": n_same_station_overlap_components,
        "n_all_station_components": int(len(all_station_components)),
        "n_all_station_overlap_components": n_all_station_overlap_components,
        "n_unique_covered_dates": int(len(unique_date_coverage)),
        "n_dates_with_same_station_overlap": int(
            unique_date_coverage["same_station_overlap"].sum()
        )
        if len(unique_date_coverage)
        else 0,
        "n_dates_with_cross_station_coverage": int(
            unique_date_coverage["cross_station_coverage"].sum()
        )
        if len(unique_date_coverage)
        else 0,
        "n_flagged_pairs": int(len(flagged)),
        "unique_years": list(unique_years),
        "n_years": len(unique_years),
        "nearby_center_days": NEARBY_CENTER_DAYS,
        "window_rule": "centered_max_supported_length",
        "n_validation_strata": len(VALIDATION_STRATA),
        "n_apparent_iid_units": n_iid_units,
        "must_not_treat_units_as_iid": True,
        "iid_warning": IID_WARNING,
        "ranking_status": "pending_validation_results",
        "pending_validation_results": True,
        "performance_evidence": False,
    }
    return AnchorIndependenceAudit(
        pairwise,
        same_station_pairwise,
        overlap_components,
        unique_date_coverage,
        year_coverage,
        station_effective_n,
        named_findings,
        pd.DataFrame(columns=FRONTIER_EFFECTIVE_N_COLUMNS),
        _pending_ranking_frame(LEAVE_ONE_ANCHOR_OUT_COLUMNS),
        _pending_ranking_frame(LEAVE_ONE_STATION_OUT_COLUMNS),
        _pending_ranking_frame(BOOTSTRAP_RANK_COLUMNS),
        summary,
    )


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_csv(temporary, index=False, na_rep="NA")
    temporary.replace(path)


def write_anchor_independence_audit(
    catalog: pd.DataFrame,
    output_dir: str | Path,
    *,
    frontier_catalog: pd.DataFrame | None = None,
) -> AnchorIndependenceAudit:
    """Write the required P0-5 CSV artifacts, including ranking placeholders."""

    audit = audit_validation_anchor_independence(catalog)
    if frontier_catalog is not None:
        frontier = audit_frontier_effective_n(frontier_catalog)
        audit = AnchorIndependenceAudit(
            audit.pairwise,
            audit.same_station_pairwise,
            audit.overlap_components,
            audit.unique_date_coverage,
            audit.year_coverage,
            audit.station_effective_n,
            audit.named_findings,
            frontier,
            audit.leave_one_anchor_out_ranking,
            audit.leave_one_station_out_ranking,
            audit.bootstrap_rank_probabilities,
            {
                **audit.summary,
                "frontier_overlap_note": True,
                "frontier_effective_n_range": (
                    [
                        float(frontier["effective_n"].min()),
                        float(frontier["effective_n"].max()),
                    ]
                    if len(frontier)
                    else []
                ),
            },
        )
    destination = Path(output_dir)
    for name, frame in audit.artifact_frames().items():
        _atomic_csv(frame, destination / name)
    return audit


def load_validation_anchors_for_audit(path: str | Path) -> pd.DataFrame:
    """Load a validation-anchor CSV without rewriting the frozen catalog."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    return pd.read_csv(source)


__all__ = [
    "BOOTSTRAP_RANK_COLUMNS",
    "IID_WARNING",
    "JACCARD_HIGH_THRESHOLD",
    "LEAVE_ONE_ANCHOR_OUT_COLUMNS",
    "LEAVE_ONE_STATION_OUT_COLUMNS",
    "NEARBY_CENTER_DAYS",
    "PENDING_RANKING_REASON",
    "AnchorIndependenceAudit",
    "audit_frontier_effective_n",
    "audit_validation_anchor_independence",
    "load_validation_anchors_for_audit",
    "write_anchor_independence_audit",
]
