"""Catalog-only audit of event-episode matching and date-overlap clustering.

Matching is audited as declared: same station, same season, and exact window
length.  Standardized mean differences for pre-event T/F/Ta are computed only
when those paired columns exist on the catalog; otherwise
``covariate_status=not_in_catalog`` and SMD fields stay NA.  M7a aggregate
stress rows are refused in the same table as M7b episode pairs.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.experiments.contracts import file_sha256

MINIMUM_INFERENCE_N = 5
MATCHING_RULE = "station_season_exact_length"
CONTROL_RULE_STATEMENT = (
    "matched controls use station, season, and exact window length only; "
    "year and day-of-year enter only as ranking distances, not hard constraints"
)
DECLARED_SEASONS = ("DJF", "MAM", "JJA", "SON")
PRE_EVENT_COVARIATE_PAIRS = (
    ("pre_event_T", "control_pre_event_T"),
    ("pre_event_F", "control_pre_event_F"),
    ("pre_event_Ta", "control_pre_event_Ta"),
)
GRAPH_COLUMNS = (
    "left_event_id",
    "right_event_id",
    "left_station_id",
    "right_station_id",
    "left_event_type",
    "right_event_type",
    "left_season",
    "right_season",
    "same_station",
    "same_event_type",
    "same_season",
    "overlap_days",
    "union_days",
    "jaccard",
    "overlap_class",
    "experiment_family",
)
N_LT5_COLUMNS = (
    "station_id",
    "event_type",
    "season",
    "n_pairs",
    "n_analysis_eligible",
    "inference_status",
    "descriptive_only_reason",
    "stratum_status",
)
MISSING_STRATA_COLUMNS = (
    "station_id",
    "event_type",
    "season",
    "n_pairs",
    "stratum_status",
    "note",
)
FLOOD_OVERLAP_COLUMNS = (
    "left_event_id",
    "right_event_id",
    "station_id",
    "left_window_start_date",
    "left_window_end_date",
    "right_window_start_date",
    "right_window_end_date",
    "overlap_days",
    "jaccard",
    "overlap_class",
)
EVENT_FINDING_COLUMNS = (
    "finding_id",
    "finding_name",
    "n_value",
    "fraction",
    "statement",
)
CLUSTER_COLUMNS = (
    "event_id",
    "pair_id",
    "anchor_id",
    "station_id",
    "event_type",
    "season",
    "episode_length",
    "analysis_eligible",
    "cluster_id",
    "cluster_size",
    "station_cluster_id",
    "station_cluster_size",
    "station_event_type_cluster_id",
    "station_event_type_cluster_size",
    "experiment_family",
)
BALANCE_COLUMNS = (
    "stratum_grain",
    "station_id",
    "event_type",
    "season",
    "episode_length",
    "n_event",
    "n_control",
    "n_pairs",
    "n_analysis_eligible",
    "n_unique_event_ids",
    "n_unique_control_ids",
    "matched_1to1",
    "matching_rule",
    "mean_control_match_year_distance",
    "mean_control_match_doy_distance",
    "max_control_match_doy_distance",
    "covariate_status",
    "smd_T",
    "smd_F",
    "smd_Ta",
    "control_rule",
    "abutting_n",
    "abutting_fraction",
    "event_control_gap_status",
    "inference_status",
    "descriptive_only_reason",
    "experiment_family",
)
ESS_COLUMNS = (
    "scope",
    "station_id",
    "event_type",
    "season",
    "episode_length",
    "n_episodes",
    "n_clusters",
    "n_multi_episode_clusters",
    "largest_cluster_size",
    "effective_n",
    "n_unique_event_dates",
    "inference_status",
    "descriptive_only_reason",
    "experiment_family",
)


@dataclass(frozen=True)
class EventMatchingAudit:
    """Machine-readable result of :func:`audit_event_matching`."""

    overlap_graph: pd.DataFrame
    cluster_id: pd.DataFrame
    control_balance: pd.DataFrame
    effective_sample_size: pd.DataFrame
    n_lt5_strata: pd.DataFrame
    missing_strata: pd.DataFrame
    flood_same_type_overlaps: pd.DataFrame
    named_findings: pd.DataFrame
    summary: dict[str, Any]

    def artifact_frames(self) -> dict[str, pd.DataFrame]:
        """Return copies keyed by the required P0-6 artifact names."""

        return {
            "event_overlap_graph.csv": self.overlap_graph.copy(),
            "event_cluster_id.csv": self.cluster_id.copy(),
            "event_control_balance.csv": self.control_balance.copy(),
            "event_effective_sample_size.csv": self.effective_sample_size.copy(),
            "event_n_lt5_strata.csv": self.n_lt5_strata.copy(),
            "event_missing_strata.csv": self.missing_strata.copy(),
            "event_flood_same_type_overlaps.csv": self.flood_same_type_overlaps.copy(),
            "event_named_findings.csv": self.named_findings.copy(),
        }


def _require_columns(
    frame: pd.DataFrame, columns: Sequence[str], *, context: str
) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{context} requires columns: {missing}")


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0 else 0.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    return value


def _connected_components(
    identifiers: Sequence[str], edges: Sequence[tuple[str, str]]
) -> list[tuple[str, ...]]:
    adjacency = {identifier: set() for identifier in identifiers}
    for left, right in edges:
        if left not in adjacency or right not in adjacency:
            raise ValueError("overlap edge references an unknown event_id")
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


def _parse_dates(series: pd.Series, *, name: str) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce").dt.normalize()
    if dates.isna().any():
        raise ValueError(f"{name} contains invalid dates")
    return dates


def _inclusive_dates(start: pd.Timestamp, stop: pd.Timestamp) -> set[pd.Timestamp]:
    if stop < start:
        raise ValueError("episode window end precedes start")
    return set(pd.date_range(start, stop, freq="D"))


def _inclusive_gap_days(
    left_start: pd.Timestamp,
    left_end: pd.Timestamp,
    right_start: pd.Timestamp,
    right_end: pd.Timestamp,
) -> int:
    if left_end < right_start:
        return int((right_start - left_end).days) - 1
    if right_end < left_start:
        return int((left_start - right_end).days) - 1
    return -1


def _overlap_class(
    *,
    same_station: bool,
    same_event_type: bool,
    left_event_type: str,
    right_event_type: str,
) -> str:
    if same_station and same_event_type and left_event_type == "flood":
        return "same_type_flood"
    if same_station and same_event_type:
        return "same_type"
    if same_station:
        return "cross_type"
    return "cross_station"


def _coerce_bool(series: pd.Series, *, name: str) -> pd.Series:
    if series.dtype == bool:
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    mapping = {"true": True, "false": False, "1": True, "0": False}
    if not normalized.isin(mapping).all():
        raise ValueError(f"{name} must be boolean")
    return normalized.map(mapping).astype(bool)


def _experiment_family(frame: pd.DataFrame) -> str:
    families: set[str] = set()
    identity_columns = [
        column
        for column in ("event_id", "pair_id", "anchor_id", "control_id")
        if column in frame.columns
    ]
    for column in identity_columns:
        values = frame[column].astype(str).str.upper()
        if values.str.startswith("M7A").any():
            families.add("M7a")
        if values.str.startswith("M7B").any():
            families.add("M7b")
    if "experiment" in frame.columns:
        experiment = frame["experiment"].astype(str).str.upper()
        if experiment.eq("M7A").any():
            families.add("M7a")
        if experiment.eq("M7B").any():
            families.add("M7b")
    if not families:
        raise ValueError(
            "cannot determine M7a/M7b family from catalog identifiers; "
            "refusing to mix families by omission"
        )
    if families == {"M7a", "M7b"}:
        raise ValueError("refusing to mix M7a and M7b in one matching audit")
    return next(iter(families))


def _present_covariate_pairs(columns: Sequence[str]) -> tuple[tuple[str, str, str], ...]:
    available = set(columns)
    found: list[tuple[str, str, str]] = []
    for event_column, control_column in PRE_EVENT_COVARIATE_PAIRS:
        if event_column in available and control_column in available:
            variable = event_column.removeprefix("pre_event_")
            found.append((variable, event_column, control_column))
    return tuple(found)


def _standardized_mean_difference(
    event_values: np.ndarray, control_values: np.ndarray
) -> float:
    event = np.asarray(event_values, dtype=float)
    control = np.asarray(control_values, dtype=float)
    usable = np.isfinite(event) & np.isfinite(control)
    event = event[usable]
    control = control[usable]
    if event.size < 2 or control.size < 2:
        return float("nan")
    event_sd = float(np.std(event, ddof=1))
    control_sd = float(np.std(control, ddof=1))
    pooled = float(np.sqrt((event_sd**2 + control_sd**2) / 2.0))
    if pooled == 0.0:
        return 0.0 if np.isclose(float(event.mean()), float(control.mean())) else float(
            "nan"
        )
    return float((event.mean() - control.mean()) / pooled)


def _inference_status(n_units: int) -> tuple[str, str]:
    if n_units < MINIMUM_INFERENCE_N:
        return (
            "descriptive_only",
            f"n<{MINIMUM_INFERENCE_N}",
        )
    return "eligible_for_descriptive_inference", ""


def _label_clusters(
    identifiers: Sequence[str], edges: Sequence[tuple[str, str]], *, prefix: str
) -> dict[str, tuple[str, int]]:
    mapping: dict[str, tuple[str, int]] = {}
    for position, members in enumerate(
        _connected_components(identifiers, edges), start=1
    ):
        cluster_id = f"{prefix}{position:04d}"
        for member in members:
            mapping[member] = (cluster_id, len(members))
    return mapping


def _verify_audit_json(
    catalog: pd.DataFrame, audit_json: Mapping[str, Any], catalog_path: Path | None
) -> None:
    expected_pairs = audit_json.get("episode_pair_count")
    if expected_pairs is not None and int(expected_pairs) != len(catalog):
        raise ValueError(
            "event catalog row count does not match audit.json episode_pair_count"
        )
    group_counts = audit_json.get("group_counts")
    if group_counts:
        expected = pd.DataFrame(group_counts)
        _require_columns(
            expected,
            ["station_id", "event_type", "season", "episode_count"],
            context="event catalog audit.json group_counts",
        )
        actual = (
            catalog.groupby(["station_id", "event_type", "season"], observed=True)
            .size()
            .rename("episode_count")
            .reset_index()
        )
        merged = expected.merge(
            actual,
            on=["station_id", "event_type", "season"],
            how="outer",
            suffixes=("_audit", "_catalog"),
        )
        left = pd.to_numeric(merged["episode_count_audit"], errors="coerce")
        right = pd.to_numeric(merged["episode_count_catalog"], errors="coerce")
        if left.isna().any() or right.isna().any() or not left.eq(right).all():
            raise ValueError(
                "event catalog group counts do not match audit.json group_counts"
            )
    if catalog_path is not None:
        declared = audit_json.get("catalog_file_sha256")
        if declared:
            observed = file_sha256(catalog_path)
            if observed != str(declared):
                raise ValueError(
                    "event catalog file hash does not match audit.json "
                    "catalog_file_sha256"
                )


def audit_event_matching(
    catalog: pd.DataFrame,
    *,
    audit_json: Mapping[str, Any] | None = None,
    catalog_path: str | Path | None = None,
) -> EventMatchingAudit:
    """Audit M7b episode overlap, matching strata, and effective sample size.

    Parameters
    ----------
    catalog:
        Frozen event/control episode table.
    audit_json:
        Optional companion ``event_episode_catalog.audit.json``.  When present,
        group counts and the file hash are checked fail-closed.
    catalog_path:
        Path used only to verify ``catalog_file_sha256`` when ``audit_json``
        declares one.
    """

    required = (
        "event_id",
        "pair_id",
        "anchor_id",
        "control_id",
        "station_id",
        "event_type",
        "season",
        "episode_length",
        "window_start_date",
        "window_end_date",
        "analysis_eligible",
    )
    _require_columns(catalog, required, context="event matching audit")
    if catalog.empty:
        raise ValueError("event catalog is empty")
    family = _experiment_family(catalog)
    frame = catalog.copy()
    frame["event_id"] = frame["event_id"].astype(str)
    if frame["event_id"].duplicated().any():
        raise ValueError("event_id values must be unique")
    if frame["event_id"].str.strip().eq("").any():
        raise ValueError("event_id must not be empty")
    frame["pair_id"] = frame["pair_id"].astype(str)
    frame["anchor_id"] = frame["anchor_id"].astype(str)
    frame["control_id"] = frame["control_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    frame["event_type"] = frame["event_type"].astype(str)
    frame["season"] = frame["season"].astype(str)
    frame["episode_length"] = pd.to_numeric(frame["episode_length"], errors="coerce")
    if (
        frame["episode_length"].isna().any()
        or not np.isfinite(frame["episode_length"]).all()
        or (frame["episode_length"] <= 0).any()
    ):
        raise ValueError("episode_length must be a positive finite number")
    frame["episode_length"] = frame["episode_length"].astype(int)
    frame["window_start_date"] = _parse_dates(
        frame["window_start_date"], name="window_start_date"
    )
    frame["window_end_date"] = _parse_dates(
        frame["window_end_date"], name="window_end_date"
    )
    frame["analysis_eligible"] = _coerce_bool(
        frame["analysis_eligible"], name="analysis_eligible"
    )
    has_control_dates = {
        "control_start_date",
        "control_end_date",
    }.issubset(frame.columns)
    if has_control_dates:
        frame["control_start_date"] = _parse_dates(
            frame["control_start_date"], name="control_start_date"
        )
        frame["control_end_date"] = _parse_dates(
            frame["control_end_date"], name="control_end_date"
        )
        frame["event_control_gap_days"] = [
            _inclusive_gap_days(
                pd.Timestamp(row.window_start_date),
                pd.Timestamp(row.window_end_date),
                pd.Timestamp(row.control_start_date),
                pd.Timestamp(row.control_end_date),
            )
            for row in frame.itertuples(index=False)
        ]
        frame["event_control_abutting"] = frame["event_control_gap_days"].eq(0)
        gap_status = "computed_from_catalog"
    else:
        frame["event_control_gap_days"] = pd.NA
        frame["event_control_abutting"] = False
        gap_status = "control_dates_not_in_catalog"
    for distance_column in (
        "control_match_year_distance",
        "control_match_day_of_year_distance",
    ):
        if distance_column in frame.columns:
            frame[distance_column] = pd.to_numeric(
                frame[distance_column], errors="coerce"
            )
    if audit_json is not None:
        _verify_audit_json(
            frame,
            audit_json,
            Path(catalog_path) if catalog_path is not None else None,
        )

    frame = frame.sort_values(
        ["station_id", "event_type", "season", "event_id"], kind="stable"
    ).reset_index(drop=True)
    date_sets: dict[str, set[pd.Timestamp]] = {}
    for row in frame.itertuples(index=False):
        date_sets[str(row.event_id)] = _inclusive_dates(
            pd.Timestamp(row.window_start_date), pd.Timestamp(row.window_end_date)
        )

    event_ids = [str(value) for value in frame["event_id"]]
    meta = frame.set_index("event_id")
    graph_rows: list[dict[str, Any]] = []
    overlap_edges: list[tuple[str, str]] = []
    station_edges: dict[str, list[tuple[str, str]]] = {}
    type_edges: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for position, left_id in enumerate(event_ids):
        for right_id in event_ids[position + 1 :]:
            intersection = date_sets[left_id] & date_sets[right_id]
            if not intersection:
                continue
            union = date_sets[left_id] | date_sets[right_id]
            left = meta.loc[left_id]
            right = meta.loc[right_id]
            overlap_edges.append((left_id, right_id))
            if str(left["station_id"]) == str(right["station_id"]):
                station_edges.setdefault(str(left["station_id"]), []).append(
                    (left_id, right_id)
                )
            type_key = (str(left["station_id"]), str(left["event_type"]))
            if str(left["station_id"]) == str(right["station_id"]) and str(
                left["event_type"]
            ) == str(right["event_type"]):
                type_edges.setdefault(type_key, []).append((left_id, right_id))
            jaccard = _safe_ratio(len(intersection), len(union))
            if not np.isfinite(jaccard):
                raise ValueError("non-finite event Jaccard encountered")
            graph_rows.append(
                {
                    "left_event_id": left_id,
                    "right_event_id": right_id,
                    "left_station_id": str(left["station_id"]),
                    "right_station_id": str(right["station_id"]),
                    "left_event_type": str(left["event_type"]),
                    "right_event_type": str(right["event_type"]),
                    "left_season": str(left["season"]),
                    "right_season": str(right["season"]),
                    "same_station": str(left["station_id"]) == str(right["station_id"]),
                    "same_event_type": str(left["event_type"])
                    == str(right["event_type"]),
                    "same_season": str(left["season"]) == str(right["season"]),
                    "overlap_days": len(intersection),
                    "union_days": len(union),
                    "jaccard": jaccard,
                    "overlap_class": _overlap_class(
                        same_station=str(left["station_id"])
                        == str(right["station_id"]),
                        same_event_type=str(left["event_type"])
                        == str(right["event_type"]),
                        left_event_type=str(left["event_type"]),
                        right_event_type=str(right["event_type"]),
                    ),
                    "experiment_family": family,
                }
            )
    overlap_graph = pd.DataFrame(graph_rows, columns=GRAPH_COLUMNS)

    global_clusters = _label_clusters(event_ids, overlap_edges, prefix="EC")
    station_cluster_maps: dict[str, tuple[str, int]] = {}
    for station_id, group in frame.groupby("station_id", observed=True, sort=True):
        members = [str(value) for value in group["event_id"]]
        labeled = _label_clusters(
            members,
            station_edges.get(str(station_id), []),
            prefix="SC",
        )
        for event_id, (cluster_id, cluster_size) in labeled.items():
            station_cluster_maps[event_id] = (
                f"ST{station_id}-{cluster_id}",
                cluster_size,
            )
    type_cluster_maps: dict[str, tuple[str, int]] = {}
    for (station_id, event_type), group in frame.groupby(
        ["station_id", "event_type"], observed=True, sort=True
    ):
        members = [str(value) for value in group["event_id"]]
        prefix = f"ET{station_id}{event_type}"
        labeled = _label_clusters(
            members,
            type_edges.get((str(station_id), str(event_type)), []),
            prefix="TC",
        )
        for event_id, (cluster_id, cluster_size) in labeled.items():
            type_cluster_maps[event_id] = (
                f"{prefix}-{cluster_id}",
                cluster_size,
            )

    cluster_rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        event_id = str(row.event_id)
        cluster_id, cluster_size = global_clusters[event_id]
        station_cluster_id, station_cluster_size = station_cluster_maps[event_id]
        type_cluster_id, type_cluster_size = type_cluster_maps[event_id]
        cluster_rows.append(
            {
                "event_id": event_id,
                "pair_id": str(row.pair_id),
                "anchor_id": str(row.anchor_id),
                "station_id": str(row.station_id),
                "event_type": str(row.event_type),
                "season": str(row.season),
                "episode_length": int(row.episode_length),
                "analysis_eligible": bool(row.analysis_eligible),
                "cluster_id": cluster_id,
                "cluster_size": int(cluster_size),
                "station_cluster_id": station_cluster_id,
                "station_cluster_size": int(station_cluster_size),
                "station_event_type_cluster_id": type_cluster_id,
                "station_event_type_cluster_size": int(type_cluster_size),
                "experiment_family": family,
            }
        )
    cluster_id_frame = pd.DataFrame(cluster_rows, columns=CLUSTER_COLUMNS)

    covariate_pairs = _present_covariate_pairs(frame.columns)
    covariate_status = (
        "computed_from_catalog" if covariate_pairs else "not_in_catalog"
    )
    smd_lookup = {variable: (event, control) for variable, event, control in covariate_pairs}

    def _smd_for(subset: pd.DataFrame, variable: str) -> float:
        if variable not in smd_lookup:
            return float("nan")
        event_column, control_column = smd_lookup[variable]
        return _standardized_mean_difference(
            pd.to_numeric(subset[event_column], errors="coerce").to_numpy(),
            pd.to_numeric(subset[control_column], errors="coerce").to_numpy(),
        )

    def _distance_mean(subset: pd.DataFrame, column: str) -> float:
        if column not in subset.columns:
            return float("nan")
        values = pd.to_numeric(subset[column], errors="coerce")
        finite = values[np.isfinite(values.to_numpy(dtype=float))]
        return float(finite.mean()) if len(finite) else float("nan")

    def _distance_max(subset: pd.DataFrame, column: str) -> float:
        if column not in subset.columns:
            return float("nan")
        values = pd.to_numeric(subset[column], errors="coerce")
        finite = values[np.isfinite(values.to_numpy(dtype=float))]
        return float(finite.max()) if len(finite) else float("nan")

    balance_rows: list[dict[str, Any]] = []

    def _append_balance(
        subset: pd.DataFrame,
        *,
        grain: str,
        station_id: str,
        event_type: str,
        season: str,
        episode_length: Any,
    ) -> None:
        n_pairs = len(subset)
        status, reason = _inference_status(n_pairs)
        n_event = int(subset["event_id"].nunique())
        n_control = int(subset["control_id"].nunique())
        if has_control_dates and n_pairs:
            abutting_n = int(subset["event_control_abutting"].sum())
            abutting_fraction = float(abutting_n / n_pairs)
        else:
            abutting_n = pd.NA
            abutting_fraction = float("nan")
        balance_rows.append(
            {
                "stratum_grain": grain,
                "station_id": station_id,
                "event_type": event_type,
                "season": season,
                "episode_length": episode_length,
                "n_event": n_event,
                "n_control": n_control,
                "n_pairs": n_pairs,
                "n_analysis_eligible": int(subset["analysis_eligible"].sum()),
                "n_unique_event_ids": n_event,
                "n_unique_control_ids": n_control,
                "matched_1to1": n_event == n_pairs and n_control == n_pairs,
                "matching_rule": MATCHING_RULE,
                "mean_control_match_year_distance": _distance_mean(
                    subset, "control_match_year_distance"
                ),
                "mean_control_match_doy_distance": _distance_mean(
                    subset, "control_match_day_of_year_distance"
                ),
                "max_control_match_doy_distance": _distance_max(
                    subset, "control_match_day_of_year_distance"
                ),
                "covariate_status": covariate_status,
                "smd_T": _smd_for(subset, "T"),
                "smd_F": _smd_for(subset, "F"),
                "smd_Ta": _smd_for(subset, "Ta"),
                "control_rule": MATCHING_RULE,
                "abutting_n": abutting_n,
                "abutting_fraction": abutting_fraction,
                "event_control_gap_status": gap_status,
                "inference_status": status,
                "descriptive_only_reason": reason,
                "experiment_family": family,
            }
        )

    _append_balance(
        frame,
        grain="overall",
        station_id="ALL",
        event_type="ALL",
        season="ALL",
        episode_length=pd.NA,
    )
    for (station_id, event_type, season), group in frame.groupby(
        ["station_id", "event_type", "season"], observed=True, sort=True
    ):
        _append_balance(
            group,
            grain="station_event_season",
            station_id=str(station_id),
            event_type=str(event_type),
            season=str(season),
            episode_length=pd.NA,
        )
    for (station_id, event_type, season, length), group in frame.groupby(
        ["station_id", "event_type", "season", "episode_length"],
        observed=True,
        sort=True,
    ):
        _append_balance(
            group,
            grain="station_event_season_length",
            station_id=str(station_id),
            event_type=str(event_type),
            season=str(season),
            episode_length=int(length),
        )
    control_balance = pd.DataFrame(balance_rows, columns=BALANCE_COLUMNS)

    cluster_lookup = cluster_id_frame.set_index("event_id")

    def _ess_row(
        subset: pd.DataFrame,
        *,
        scope: str,
        station_id: str,
        event_type: str,
        season: str,
        episode_length: Any,
        cluster_column: str,
    ) -> dict[str, Any]:
        event_ids_in_scope = [str(value) for value in subset["event_id"]]
        cluster_ids = cluster_lookup.loc[event_ids_in_scope, cluster_column]
        n_clusters = int(cluster_ids.nunique())
        sizes = cluster_ids.value_counts()
        union_dates: set[pd.Timestamp] = set()
        for event_id in event_ids_in_scope:
            union_dates.update(date_sets[event_id])
        status, reason = _inference_status(len(subset))
        return {
            "scope": scope,
            "station_id": station_id,
            "event_type": event_type,
            "season": season,
            "episode_length": episode_length,
            "n_episodes": len(subset),
            "n_clusters": n_clusters,
            "n_multi_episode_clusters": int((sizes > 1).sum()),
            "largest_cluster_size": int(sizes.max()) if len(sizes) else 0,
            "effective_n": n_clusters,
            "n_unique_event_dates": len(union_dates),
            "inference_status": status,
            "descriptive_only_reason": reason,
            "experiment_family": family,
        }

    ess_rows = [
        _ess_row(
            frame,
            scope="overall_date_overlap_clusters",
            station_id="ALL",
            event_type="ALL",
            season="ALL",
            episode_length=pd.NA,
            cluster_column="cluster_id",
        )
    ]
    for station_id, group in frame.groupby("station_id", observed=True, sort=True):
        ess_rows.append(
            _ess_row(
                group,
                scope="station_date_overlap_clusters",
                station_id=str(station_id),
                event_type="ALL",
                season="ALL",
                episode_length=pd.NA,
                cluster_column="station_cluster_id",
            )
        )
    for (station_id, event_type, season), group in frame.groupby(
        ["station_id", "event_type", "season"], observed=True, sort=True
    ):
        ess_rows.append(
            _ess_row(
                group,
                scope="station_event_season_type_clusters",
                station_id=str(station_id),
                event_type=str(event_type),
                season=str(season),
                episode_length=pd.NA,
                cluster_column="station_event_type_cluster_id",
            )
        )
    effective_sample_size = pd.DataFrame(ess_rows, columns=ESS_COLUMNS)

    season_grain = control_balance.loc[
        control_balance["stratum_grain"].eq("station_event_season")
    ]
    length_grain = control_balance.loc[
        control_balance["stratum_grain"].eq("station_event_season_length")
    ]
    smallest_season_n = (
        int(season_grain["n_pairs"].min()) if len(season_grain) else 0
    )
    smallest_length_n = (
        int(length_grain["n_pairs"].min()) if len(length_grain) else 0
    )
    n_lt5 = season_grain.loc[season_grain["n_pairs"] < MINIMUM_INFERENCE_N].copy()
    n_lt5_strata = n_lt5.assign(stratum_status="present_n_lt_5")[
        list(N_LT5_COLUMNS)
    ].reset_index(drop=True)

    stations = tuple(sorted(frame["station_id"].unique()))
    event_types = tuple(sorted(frame["event_type"].unique()))
    present = set(
        zip(
            season_grain["station_id"].astype(str),
            season_grain["event_type"].astype(str),
            season_grain["season"].astype(str),
            strict=True,
        )
    ) if len(season_grain) else set()
    missing_rows = [
        {
            "station_id": station_id,
            "event_type": event_type,
            "season": season,
            "n_pairs": 0,
            "stratum_status": "missing_stratum",
            "note": "no catalog episodes in this station/event_type/season cell",
        }
        for station_id in stations
        for event_type in event_types
        for season in DECLARED_SEASONS
        if (station_id, event_type, season) not in present
    ]
    missing_strata = pd.DataFrame(missing_rows, columns=MISSING_STRATA_COLUMNS)

    flood_graph = overlap_graph.loc[
        overlap_graph["overlap_class"].eq("same_type_flood")
    ].copy()
    flood_rows: list[dict[str, Any]] = []
    for edge in flood_graph.itertuples(index=False):
        left = meta.loc[str(edge.left_event_id)]
        right = meta.loc[str(edge.right_event_id)]
        flood_rows.append(
            {
                "left_event_id": str(edge.left_event_id),
                "right_event_id": str(edge.right_event_id),
                "station_id": str(edge.left_station_id),
                "left_window_start_date": pd.Timestamp(
                    left["window_start_date"]
                ).strftime("%Y-%m-%d"),
                "left_window_end_date": pd.Timestamp(
                    left["window_end_date"]
                ).strftime("%Y-%m-%d"),
                "right_window_start_date": pd.Timestamp(
                    right["window_start_date"]
                ).strftime("%Y-%m-%d"),
                "right_window_end_date": pd.Timestamp(
                    right["window_end_date"]
                ).strftime("%Y-%m-%d"),
                "overlap_days": int(edge.overlap_days),
                "jaccard": float(edge.jaccard),
                "overlap_class": "same_type_flood",
            }
        )
    flood_same_type_overlaps = pd.DataFrame(flood_rows, columns=FLOOD_OVERLAP_COLUMNS)
    n_cross_type = (
        int(overlap_graph["overlap_class"].eq("cross_type").sum())
        if len(overlap_graph)
        else 0
    )
    overall_balance = control_balance.loc[
        control_balance["stratum_grain"].eq("overall")
    ]
    abutting_fraction = (
        float(overall_balance["abutting_fraction"].iloc[0])
        if len(overall_balance)
        else float("nan")
    )
    abutting_n = (
        int(overall_balance["abutting_n"].iloc[0])
        if len(overall_balance) and pd.notna(overall_balance["abutting_n"].iloc[0])
        else pd.NA
    )
    effective_n_overall = int(
        effective_sample_size.loc[
            effective_sample_size["scope"].eq("overall_date_overlap_clusters"),
            "effective_n",
        ].iloc[0]
    )
    named_findings = pd.DataFrame(
        [
            {
                "finding_id": "control_rule_station_season_length_only",
                "finding_name": "control_matching_rule",
                "n_value": len(frame),
                "fraction": float("nan"),
                "statement": CONTROL_RULE_STATEMENT,
            },
            {
                "finding_id": "abutting_gap_zero",
                "finding_name": "event_control_abutting_fraction",
                "n_value": abutting_n if pd.notna(abutting_n) else pd.NA,
                "fraction": abutting_fraction,
                "statement": (
                    f"{abutting_n} of {len(frame)} event/control pairs abut "
                    f"(gap=0; fraction {abutting_fraction:.3f}). "
                    f"Gap status: {gap_status}."
                    if has_control_dates
                    else "control window dates are absent; abutting fraction not computed"
                ),
            },
            {
                "finding_id": "pre_event_covariates",
                "finding_name": "pre_event_T_F_Ta",
                "n_value": 0 if covariate_status == "not_in_catalog" else 1,
                "fraction": float("nan"),
                "statement": (
                    f"covariate_status={covariate_status} for pre-event T/F/Ta; "
                    "SMDs are not invented"
                ),
            },
            {
                "finding_id": "n_lt5_strata",
                "finding_name": "descriptive_only_station_event_season",
                "n_value": int(len(n_lt5_strata)),
                "fraction": float("nan"),
                "statement": (
                    f"{int(len(n_lt5_strata))} station/event_type/season strata have "
                    f"n<{MINIMUM_INFERENCE_N}; listed in event_n_lt5_strata.csv"
                ),
            },
            {
                "finding_id": "missing_strata",
                "finding_name": "absent_station_event_season_cells",
                "n_value": int(len(missing_strata)),
                "fraction": float("nan"),
                "statement": (
                    f"{int(len(missing_strata))} station/event_type/season cells have "
                    "zero episodes; listed in event_missing_strata.csv"
                ),
            },
            {
                "finding_id": "same_type_flood_window_overlaps",
                "finding_name": "flood_same_type_overlap_pairs",
                "n_value": int(len(flood_same_type_overlaps)),
                "fraction": float("nan"),
                "statement": (
                    f"{int(len(flood_same_type_overlaps))} same-station same-type "
                    "flood window-overlap pairs; listed in "
                    "event_flood_same_type_overlaps.csv"
                ),
            },
            {
                "finding_id": "cross_type_window_overlaps",
                "finding_name": "cross_type_same_station_overlaps",
                "n_value": n_cross_type,
                "fraction": float("nan"),
                "statement": (
                    f"{n_cross_type} same-station cross-type window overlaps "
                    "(flood/high_temperature/low_flow/rapid_warming sharing dates)"
                ),
            },
            {
                "finding_id": "cluster_effective_n",
                "finding_name": "date_overlap_effective_n",
                "n_value": effective_n_overall,
                "fraction": _safe_ratio(effective_n_overall, len(frame)),
                "statement": (
                    f"Date-overlap clustering yields effective_n="
                    f"{effective_n_overall} versus {len(frame)} episodes; "
                    "M7a is not mixed into this M7b table"
                ),
            },
            {
                "finding_id": "m7_family_not_mixed",
                "finding_name": "m7b_only",
                "n_value": len(frame),
                "fraction": float("nan"),
                "statement": f"experiment_family={family}; M7a rows are refused",
            },
        ],
        columns=EVENT_FINDING_COLUMNS,
    )
    summary = {
        "audit_status": "event_matching_overlap_audit",
        "experiment_family": family,
        "matching_rule": MATCHING_RULE,
        "control_rule": CONTROL_RULE_STATEMENT,
        "n_episodes": len(frame),
        "n_analysis_eligible": int(frame["analysis_eligible"].sum()),
        "n_overlap_edges": len(overlap_graph),
        "n_date_overlap_clusters": int(cluster_id_frame["cluster_id"].nunique()),
        "largest_cluster_size": int(cluster_id_frame["cluster_size"].max()),
        "effective_n_overall": effective_n_overall,
        "smallest_station_event_season_n": smallest_season_n,
        "smallest_matching_stratum_n": smallest_length_n,
        "n_descriptive_only_season_strata": int(len(n_lt5_strata)),
        "n_missing_season_strata": int(len(missing_strata)),
        "n_same_type_flood_overlaps": int(len(flood_same_type_overlaps)),
        "n_cross_type_overlaps": n_cross_type,
        "n_descriptive_only_matching_strata": int(
            length_grain["inference_status"].eq("descriptive_only").sum()
        ),
        "abutting_n": int(abutting_n) if pd.notna(abutting_n) else None,
        "abutting_fraction": abutting_fraction,
        "event_control_gap_status": gap_status,
        "covariate_status": covariate_status,
        "performance_evidence": False,
        "m7a_mixed": False,
    }
    summary = _json_safe(summary)
    return EventMatchingAudit(
        overlap_graph,
        cluster_id_frame,
        control_balance,
        effective_sample_size,
        n_lt5_strata,
        missing_strata,
        flood_same_type_overlaps,
        named_findings,
        summary,
    )


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_csv(temporary, index=False, na_rep="NA")
    temporary.replace(path)


def write_event_matching_audit(
    catalog: pd.DataFrame,
    output_dir: str | Path,
    *,
    audit_json: Mapping[str, Any] | None = None,
    catalog_path: str | Path | None = None,
) -> EventMatchingAudit:
    """Write the required P0-6 CSV artifacts."""

    audit = audit_event_matching(
        catalog, audit_json=audit_json, catalog_path=catalog_path
    )
    destination = Path(output_dir)
    for name, frame in audit.artifact_frames().items():
        _atomic_csv(frame, destination / name)
    return audit


def load_event_catalog_for_audit(path: str | Path) -> pd.DataFrame:
    """Load an event-episode CSV without regenerating the frozen catalog."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    return pd.read_csv(source)


def load_event_audit_json(path: str | Path) -> dict[str, Any]:
    """Load the companion catalog audit JSON."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("event catalog audit.json must be an object")
    return payload


__all__ = [
    "BALANCE_COLUMNS",
    "CLUSTER_COLUMNS",
    "CONTROL_RULE_STATEMENT",
    "ESS_COLUMNS",
    "GRAPH_COLUMNS",
    "MATCHING_RULE",
    "MINIMUM_INFERENCE_N",
    "PRE_EVENT_COVARIATE_PAIRS",
    "EventMatchingAudit",
    "audit_event_matching",
    "load_event_audit_json",
    "load_event_catalog_for_audit",
    "write_event_matching_audit",
]
