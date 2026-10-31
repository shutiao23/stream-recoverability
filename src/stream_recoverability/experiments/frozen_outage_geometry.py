"""Freeze T2 natural-outage and adversarial geometry without reading outcomes.

The builder consumes only the station/date projection of open-role QC tables.
Temperature values are deliberately not loaded.  A real missing interval is a
geometry observation, not a labelled test case; it becomes benchmark-eligible
only when a disjoint, fully observed interval at the same station can be held
out as its truth-bearing counterpart.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.seeds import plain_seed, position_index

ALLOWED_ROLES = ("development", "validation")
QUALIFICATION_MODE = "failure_closure6"
RELAXATION_TRIGGER = "open_survival_projection_lt_100"
NATURAL_MIN_DAYS = 7
NATURAL_MAX_DAYS = 180
ADVERSARIAL_LENGTHS = (30, 90, 180, 365)
ADVERSARIAL_RULES: tuple[dict[str, Any], ...] = (
    {
        "stress_id": "record_left_edge",
        "placement_rule": "earliest_fully_observed_target_window",
        "target_mask_scope": "target_station_gap",
        "donor_mask_rule": "preserve_observed_donors",
        "left_boundary_required": False,
        "right_boundary_required": True,
    },
    {
        "stress_id": "record_right_edge",
        "placement_rule": "latest_fully_observed_target_window",
        "target_mask_scope": "target_station_gap",
        "donor_mask_rule": "preserve_observed_donors",
        "left_boundary_required": True,
        "right_boundary_required": False,
    },
    {
        "stress_id": "donor_thin",
        "placement_rule": "minimum_mean_donor_availability_then_seeded_random_tie_break",
        "target_mask_scope": "target_station_gap",
        "donor_mask_rule": "preserve_observed_donors",
        "left_boundary_required": True,
        "right_boundary_required": True,
    },
    {
        "stress_id": "synchronous_network_outage",
        "placement_rule": "seeded_random_fully_observed_target_window",
        "target_mask_scope": "target_station_gap",
        "donor_mask_rule": "mask_all_network_stations_during_gap",
        "left_boundary_required": True,
        "right_boundary_required": True,
    },
)


def _season(stamp: pd.Timestamp) -> str:
    return ("DJF", "MAM", "JJA", "SON")[(int(stamp.month) % 12) // 3]


STRESS_CODES = {
    str(rule["stress_id"]): index for index, rule in enumerate(ADVERSARIAL_RULES)
}


def _roster_positions(
    availability: pd.DataFrame,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Positions of networks and of stations within each network in sorted order."""

    networks = availability["network_id"].astype(str)
    stations = availability["station_id"].astype(str)
    network_positions = position_index(networks)
    station_positions = {
        str(network_id): position_index(group)
        for network_id, group in stations.groupby(networks, sort=True)
    }
    return network_positions, station_positions


def _observed_runs(dates: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    unique = pd.DatetimeIndex(dates).normalize().drop_duplicates().sort_values()
    if unique.empty:
        return []
    breaks = np.flatnonzero(np.diff(unique.asi8) != pd.Timedelta(days=1).value)
    starts = np.r_[0, breaks + 1]
    ends = np.r_[breaks, len(unique) - 1]
    return [
        (pd.Timestamp(unique[a]), pd.Timestamp(unique[b])) for a, b in zip(starts, ends)
    ]


def _internal_missing_runs(
    dates: pd.DatetimeIndex,
) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    runs = _observed_runs(dates)
    rows: list[tuple[pd.Timestamp, pd.Timestamp, int]] = []
    for (_, left_end), (right_start, _) in pairwise(runs):
        start = left_end + pd.Timedelta(days=1)
        end = right_start - pd.Timedelta(days=1)
        rows.append((start, end, int((end - start).days + 1)))
    return rows


def _window_starts(
    runs: Sequence[tuple[pd.Timestamp, pd.Timestamp]],
    length: int,
    *,
    season: str | None = None,
    require_left_boundary: bool = False,
    require_right_boundary: bool = False,
) -> list[pd.Timestamp]:
    candidates: list[pd.Timestamp] = []
    for run_start, run_end in runs:
        first = run_start + pd.Timedelta(days=int(require_left_boundary))
        last = run_end - pd.Timedelta(
            days=int(length) - 1 + int(require_right_boundary)
        )
        if last < first:
            continue
        for stamp in pd.date_range(first, last, freq="D"):
            if season is None or _season(stamp) == str(season):
                candidates.append(pd.Timestamp(stamp))
    return candidates


def _seeded_choice(
    candidates: Sequence[pd.Timestamp], *seed_parts: int
) -> pd.Timestamp | None:
    if not candidates:
        return None
    # One seeded draw selects a stable rank in the already sorted candidate
    # roster; the seed is built from roster positions, dates and lengths.
    rng = np.random.default_rng(plain_seed(*seed_parts))
    return candidates[int(rng.integers(len(candidates)))]


def _mean_donor_availability(
    stamp: pd.Timestamp,
    length: int,
    *,
    station_count: int,
    origin: pd.Timestamp,
    count_cumsum: np.ndarray,
) -> float:
    if station_count <= 1:
        return 0.0
    offset = int((pd.Timestamp(stamp) - origin).days)
    total = count_cumsum[offset + int(length)] - count_cumsum[offset]
    # The target is fully observed by construction, so subtract it.
    return float((total - int(length)) / (int(length) * (station_count - 1)))


def build_natural_outage_catalog(
    availability: pd.DataFrame,
    *,
    min_days: int = NATURAL_MIN_DAYS,
    max_days: int = NATURAL_MAX_DAYS,
) -> pd.DataFrame:
    """Bind real missing geometry to deterministic observed counterparts."""

    required = {"role", "network_id", "station_id", "date"}
    missing = required.difference(availability.columns)
    if missing:
        raise ValueError(f"availability missing columns: {sorted(missing)}")
    rows: list[dict[str, Any]] = []
    grouped = availability.assign(date=pd.to_datetime(availability["date"]))
    network_positions, station_positions = _roster_positions(grouped)
    for keys, group in grouped.groupby(["role", "network_id", "station_id"], sort=True):
        role, network_id, station_id = map(str, keys)
        if role not in ALLOWED_ROLES:
            raise ValueError(f"non-open role is forbidden: {role}")
        dates = pd.DatetimeIndex(group["date"])
        runs = _observed_runs(dates)
        candidate_cache: dict[tuple[int, str], list[pd.Timestamp]] = {}
        for start, end, length in _internal_missing_runs(dates):
            if length < int(min_days) or length > int(max_days):
                continue
            season = _season(start)
            cache_key = (length, season)
            if cache_key not in candidate_cache:
                candidate_cache[cache_key] = _window_starts(
                    runs,
                    length,
                    season=season,
                    require_left_boundary=True,
                    require_right_boundary=True,
                )
            counterpart = _seeded_choice(
                candidate_cache[cache_key],
                network_positions[network_id],
                station_positions[network_id][station_id],
                start.toordinal(),
                length,
            )
            eligible = counterpart is not None
            counterpart_end = (
                counterpart + pd.Timedelta(days=length - 1)
                if counterpart is not None
                else None
            )
            if counterpart is not None and not (
                counterpart_end < start or counterpart > end
            ):
                raise AssertionError(
                    "observed counterpart overlaps the real missing interval"
                )
            rows.append(
                {
                    "geometry_id": (
                        f"natural_{role}_{network_id}_{station_id}_"
                        f"{start.date().isoformat()}_{length}d"
                    ),
                    "suite": "natural_outage",
                    "role": role,
                    "network_id": network_id,
                    "station_id": station_id,
                    "start_date": start.date().isoformat(),
                    "end_date": end.date().isoformat(),
                    "length_days": length,
                    "season": season,
                    "actual_missing_truth_available": False,
                    "benchmark_start_date": (
                        counterpart.date().isoformat()
                        if counterpart is not None
                        else None
                    ),
                    "benchmark_end_date": (
                        counterpart_end.date().isoformat()
                        if counterpart_end is not None
                        else None
                    ),
                    "benchmark_eligible": eligible,
                    "benchmark_truth_source": (
                        "held_out_observed_counterpart" if eligible else "unavailable"
                    ),
                    "selection_uses_outcome_values": False,
                }
            )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["geometry_weight"] = 1.0 / float(len(result))
    eligible = result["benchmark_eligible"].astype(bool)
    result["benchmark_weight"] = 0.0
    if eligible.any():
        result.loc[eligible, "benchmark_weight"] = 1.0 / float(eligible.sum())
    return result.sort_values(
        ["role", "network_id", "station_id", "start_date"]
    ).reset_index(drop=True)


def build_adversarial_catalog(
    availability: pd.DataFrame,
    *,
    lengths: Sequence[int] = ADVERSARIAL_LENGTHS,
    rules: Sequence[Mapping[str, Any]] = ADVERSARIAL_RULES,
) -> pd.DataFrame:
    """Resolve preregistered stress rules using availability metadata only."""

    required = {"role", "network_id", "station_id", "date"}
    missing = required.difference(availability.columns)
    if missing:
        raise ValueError(f"availability missing columns: {sorted(missing)}")
    parsed = availability.assign(
        date=pd.to_datetime(availability["date"]).dt.normalize()
    )
    network_positions, station_positions = _roster_positions(parsed)
    rows: list[dict[str, Any]] = []
    for (role, network_id), network in parsed.groupby(
        ["role", "network_id"], sort=True
    ):
        role, network_id = str(role), str(network_id)
        if role not in ALLOWED_ROLES:
            raise ValueError(f"non-open role is forbidden: {role}")
        station_count = int(network["station_id"].nunique())
        count_by_day = network.groupby("date")["station_id"].nunique().sort_index()
        full_index = pd.date_range(
            count_by_day.index.min(), count_by_day.index.max(), freq="D"
        )
        count_array = count_by_day.reindex(full_index, fill_value=0).to_numpy(
            dtype=float
        )
        count_cumsum = np.r_[0.0, np.cumsum(count_array)]
        origin = pd.Timestamp(full_index[0])

        for station_id, station in network.groupby("station_id", sort=True):
            station_id = str(station_id)
            runs = _observed_runs(pd.DatetimeIndex(station["date"]))
            for length in lengths:
                for rule in rules:
                    stress_id = str(rule["stress_id"])
                    candidates = _window_starts(
                        runs,
                        int(length),
                        require_left_boundary=bool(rule["left_boundary_required"]),
                        require_right_boundary=bool(rule["right_boundary_required"]),
                    )
                    if not candidates:
                        continue
                    if stress_id == "record_left_edge":
                        chosen = min(candidates)
                    elif stress_id == "record_right_edge":
                        chosen = max(candidates)
                    elif stress_id == "donor_thin":
                        scores = np.asarray(
                            [
                                _mean_donor_availability(
                                    stamp,
                                    int(length),
                                    station_count=station_count,
                                    origin=origin,
                                    count_cumsum=count_cumsum,
                                )
                                for stamp in candidates
                            ]
                        )
                        thin = [
                            stamp
                            for stamp, score in zip(candidates, scores, strict=True)
                            if score == float(np.min(scores))
                        ]
                        chosen = _seeded_choice(
                            thin,
                            network_positions[network_id],
                            station_positions[network_id][station_id],
                            int(length),
                            STRESS_CODES.get(stress_id, len(STRESS_CODES)),
                        )
                    else:
                        chosen = _seeded_choice(
                            candidates,
                            network_positions[network_id],
                            station_positions[network_id][station_id],
                            int(length),
                            STRESS_CODES.get(stress_id, len(STRESS_CODES)),
                        )
                    if chosen is None:
                        continue
                    rows.append(
                        {
                            "geometry_id": (
                                f"adversarial_{role}_{network_id}_{station_id}_"
                                f"{stress_id}_{int(length)}d_{chosen.date().isoformat()}"
                            ),
                            "suite": "adversarial_stress",
                            "role": role,
                            "network_id": network_id,
                            "station_id": station_id,
                            "start_date": chosen.date().isoformat(),
                            "length_days": int(length),
                            "season": _season(chosen),
                            "stress_id": stress_id,
                            "placement_rule": str(rule["placement_rule"]),
                            "target_mask_scope": str(rule["target_mask_scope"]),
                            "donor_mask_rule": str(rule["donor_mask_rule"]),
                            "left_boundary_required": bool(
                                rule["left_boundary_required"]
                            ),
                            "right_boundary_required": bool(
                                rule["right_boundary_required"]
                            ),
                            "truth_source": "held_out_observed_days",
                            "benchmark_eligible": True,
                            "selection_uses_outcome_values": False,
                        }
                    )
    result = pd.DataFrame(rows)
    if not result.empty:
        result["stress_weight"] = 1.0 / float(len(result))
        result = result.sort_values(
            ["role", "network_id", "station_id", "stress_id", "length_days"]
        ).reset_index(drop=True)
    return result


def load_open_role_availability(
    open_role_root: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read only ``site_id,date`` from development/validation clean tables."""

    root = Path(open_role_root)
    frames: list[pd.DataFrame] = []
    sources: list[dict[str, Any]] = []
    role_sources: list[dict[str, Any]] = []
    for role in ALLOWED_ROLES:
        role_root = root / role
        role_manifest = json.loads(
            (role_root / "qc_manifest.json").read_text(encoding="utf-8")
        )
        if (
            role_manifest.get("role") != role
            or role_manifest.get("sealed_temperature_records_read") is not False
        ):
            raise ValueError(
                f"unsafe open-role manifest: {role_root / 'qc_manifest.json'}"
            )
        if (
            role_manifest.get("qualification_mode") != QUALIFICATION_MODE
            or role_manifest.get("qualified_years_min") != 6
            or role_manifest.get("relaxation_applied") is not True
            or role_manifest.get("relaxation_trigger") != RELAXATION_TRIGGER
        ):
            raise ValueError(
                f"role manifest is not the locked failure-closure-6 corpus: {role_root}"
            )
        role_sources.append(
            {
                "role": role,
                "qc_manifest": str((role_root / "qc_manifest.json").relative_to(root)),
            }
        )
        for network_root in sorted((role_root / "networks").glob("*")):
            manifest_path = network_root / "network_qc_manifest.json"
            dates_path = network_root / "daily_long_qc.csv"
            qc_path = network_root / "ingest_qc_report.csv"
            if not (
                manifest_path.is_file() and dates_path.is_file() and qc_path.is_file()
            ):
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("role") != role
                or manifest.get("sealed_temperature_records_read") is not False
            ):
                raise ValueError(f"unsafe network manifest: {manifest_path}")
            if (
                manifest.get("qualification_mode") != QUALIFICATION_MODE
                or manifest.get("qualified_years_min") != 6
                or manifest.get("relaxation_applied") is not True
                or manifest.get("relaxation_trigger") != RELAXATION_TRIGGER
            ):
                raise ValueError(
                    f"network is not governed by failure-closure-6: {manifest_path}"
                )
            if manifest.get("overlap", {}).get("complete_enough") is not True:
                continue
            qc = pd.read_csv(qc_path, dtype={"site_id": str})
            eligible = set(
                qc.loc[
                    qc["eligible_for_network"].astype(str).str.lower().eq("true"),
                    "site_id",
                ]
                .dropna()
                .astype(str)
            )
            # Security boundary: temperature_c and qualifier are never loaded.
            dates = pd.read_csv(
                dates_path, usecols=["site_id", "date"], dtype={"site_id": str}
            )
            dates = dates.loc[dates["site_id"].isin(eligible)].drop_duplicates()
            dates["role"] = role
            dates["network_id"] = str(manifest["network_id"])
            frames.append(
                dates[["role", "network_id", "site_id", "date"]].rename(
                    columns={"site_id": "station_id"}
                )
            )
            sources.append(
                {
                    "role": role,
                    "network_id": str(manifest["network_id"]),
                    "network_manifest": str(manifest_path.relative_to(root)),
                    "availability_rows": len(dates),
                }
            )
    availability = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["role", "network_id", "station_id", "date"])
    )
    return availability, {
        "sources": sources,
        "n_sources": len(sources),
        "role_manifests": role_sources,
    }


def build_binding_manifest(
    availability: pd.DataFrame,
    natural: pd.DataFrame,
    adversarial: pd.DataFrame,
    source_audit: Mapping[str, Any],
) -> dict[str, Any]:
    eligible = natural.get("benchmark_eligible", pd.Series(dtype=bool)).astype(bool)
    blocked = natural.loc[~eligible] if not natural.empty else natural
    return {
        "manifest_schema": "t2_v91_frozen_outage_geometry_binding_v1",
        "status": "frozen_open_role_geometry_not_evidence",
        "purpose": "geometry_binding_not_model_result",
        "formal_evidence": False,
        "passed": False,
        "headline_claim_licensed": False,
        "roles": list(ALLOWED_ROLES),
        "qualification_mode": QUALIFICATION_MODE,
        "qualified_years_min": 6,
        "relaxation_applied": True,
        "relaxation_trigger": RELAXATION_TRIGGER,
        "sealed_temperature_records_read": False,
        "outcome_columns_loaded": [],
        "availability_columns_loaded": ["site_id", "date"],
        "n_availability_rows": len(availability),
        "n_networks": int(availability["network_id"].nunique())
        if not availability.empty
        else 0,
        "natural_outage": {
            "n_geometry_rows": len(natural),
            "n_benchmark_eligible": int(eligible.sum()),
            "n_blocked_no_observed_counterpart": len(blocked),
            "actual_missing_truth_available": False,
            "truth_rule": "score_only_frozen_held_out_observed_counterpart",
            "min_length_days": NATURAL_MIN_DAYS,
            "max_length_days": NATURAL_MAX_DAYS,
        },
        "adversarial": {
            "n_rows": len(adversarial),
            "lengths_days": list(ADVERSARIAL_LENGTHS),
            "stress_rules": [dict(rule) for rule in ADVERSARIAL_RULES],
            "truth_rule": "resolved_start_must_be_fully_observed_before_masking",
        },
        "source_audit": dict(source_audit),
        "runner_interface": {
            "natural_outage": {
                "geometry_fields": [
                    "network_id",
                    "station_id",
                    "start_date",
                    "length_days",
                    "season",
                ],
                "plant_at": "benchmark_start_date",
                "filter": "benchmark_eligible == true",
                "truth_source": "held_out_observed_counterpart",
            },
            "adversarial": {
                "geometry_fields": [
                    "network_id",
                    "station_id",
                    "start_date",
                    "length_days",
                    "season",
                ],
                "apply": ["target_mask_scope", "donor_mask_rule"],
                "truth_source": "held_out_observed_days",
            },
        },
        "blocked_cells": [
            "sealed_role_geometry_not_built_or_read",
            "natural_rows_without_observed_counterpart_not_benchmarkable",
            "online_causal_right_boundary_execution_not_implemented",
            "meteorology_M_information_cells_unbound",
            "hydraulics_H_information_cells_unbound",
            "full_model_scoring_not_run",
            "network_interval_withheld_until_n_ge_100",
        ],
    }


def write_frozen_geometry_artifacts(
    output_dir: str | Path,
    natural: pd.DataFrame,
    adversarial: pd.DataFrame,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    natural_path = root / "natural_outage_catalog.csv"
    adversarial_path = root / "adversarial_stress_catalog.csv"
    natural.to_csv(natural_path, index=False)
    adversarial.to_csv(adversarial_path, index=False)
    frozen = json.loads(json.dumps(dict(manifest)))
    (root / "geometry_binding_manifest.json").write_text(
        json.dumps(frozen, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return frozen


def load_frozen_geometry_bindings(
    directory: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Validated loader for a future T2 work-item expander.

    This function loads geometry catalogs, not river observations.  It rejects
    non-open roles, natural rows without frozen counterpart truth, and
    adversarial rows without held-out observed truth.
    """

    root = Path(directory)
    manifest = json.loads(
        (root / "geometry_binding_manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("manifest_schema") != "t2_v91_frozen_outage_geometry_binding_v1":
        raise ValueError("unsupported outage geometry manifest")
    natural_path = root / "natural_outage_catalog.csv"
    adversarial_path = root / "adversarial_stress_catalog.csv"
    natural = pd.read_csv(natural_path, dtype={"network_id": str, "station_id": str})
    adversarial = pd.read_csv(
        adversarial_path, dtype={"network_id": str, "station_id": str}
    )
    roles = set(natural.get("role", pd.Series(dtype=str)).astype(str)) | set(
        adversarial.get("role", pd.Series(dtype=str)).astype(str)
    )
    if not roles.issubset(ALLOWED_ROLES):
        raise ValueError(f"frozen geometry contains forbidden roles: {sorted(roles)}")
    natural_ready = natural.loc[natural["benchmark_eligible"].astype(bool)]
    if (
        not natural_ready["benchmark_start_date"].notna().all()
        or not natural_ready["benchmark_truth_source"]
        .eq("held_out_observed_counterpart")
        .all()
    ):
        raise ValueError("natural benchmark row lacks frozen observed counterpart")
    counterpart_start = pd.to_datetime(natural_ready["benchmark_start_date"])
    counterpart_end = pd.to_datetime(natural_ready["benchmark_end_date"])
    missing_start = pd.to_datetime(natural_ready["start_date"])
    missing_end = pd.to_datetime(natural_ready["end_date"])
    if not (
        (counterpart_end < missing_start) | (counterpart_start > missing_end)
    ).all():
        raise ValueError("natural observed counterpart overlaps real missing geometry")
    if not adversarial["truth_source"].eq("held_out_observed_days").all():
        raise ValueError("adversarial benchmark row lacks held-out observed truth")
    return natural, adversarial, manifest


__all__ = [
    "ADVERSARIAL_LENGTHS",
    "ADVERSARIAL_RULES",
    "ALLOWED_ROLES",
    "build_adversarial_catalog",
    "build_binding_manifest",
    "build_natural_outage_catalog",
    "load_frozen_geometry_bindings",
    "load_open_role_availability",
    "write_frozen_geometry_artifacts",
]
