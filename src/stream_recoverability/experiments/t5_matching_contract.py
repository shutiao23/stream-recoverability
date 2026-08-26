"""Outcome-blind matching contract for the v9.1 T5 regulation experiment.

The contract binds station-level regulation and six frozen matching factors to
already-open metadata.  It deliberately does not accept a recoverability
outcome: the resulting pair plan can be joined to the T2 primary outcome only
after that outcome has been frozen under the separate T2 governance path.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from stream_recoverability.data.nldi_connectivity import (
    nwis_match_key,
    parse_nldi_nwissite_ids,
)

OPEN_ROLES = frozenset({"development", "validation"})
FROZEN_MATCHING_FACTORS = (
    "donor_count",
    "donor_direction",
    "nearest_donor_distance",
    "drainage_area",
    "climate",
    "bfi",
)
EXACT_MATCH_STRATA = ("role", "donor_count", "donor_direction", "climate")
FORBIDDEN_OUTCOME_COLUMNS = frozenset(
    {
        "achieved_skill",
        "delta_r",
        "fill_mae",
        "formal_evidence",
        "operator_risk",
        "recoverability_r",
        "t2_primary_y",
    }
)


def _site_id(value: Any) -> str:
    text = str(value).strip()
    if text.lower() in {"", "nan", "none"}:
        return ""
    return text.zfill(8) if text.isdigit() and len(text) <= 8 else text


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reject_outcome_columns(frames: Sequence[pd.DataFrame]) -> None:
    """Fail closed if a caller tries to make matching outcome-dependent."""

    present = sorted(
        set().union(*(set(frame.columns) for frame in frames))
        & FORBIDDEN_OUTCOME_COLUMNS
    )
    if present:
        raise ValueError(f"outcome columns are forbidden in T5 matching: {present}")


def collapse_predictor_rosters(predictors: pd.DataFrame) -> pd.DataFrame:
    """Return one invariant, train-only donor roster per target station."""

    required = {
        "network_id",
        "station_id",
        "role",
        "n_donors",
        "donor_station_ids",
    }
    missing = sorted(required.difference(predictors.columns))
    if missing:
        raise ValueError(f"predictor sidecar missing columns: {missing}")
    reject_outcome_columns([predictors])
    data = predictors.loc[:, sorted(required)].copy()
    data["network_id"] = data["network_id"].astype(str)
    data["station_id"] = data["station_id"].map(_site_id)
    invariant = ["role", "n_donors", "donor_station_ids"]
    counts = data.groupby(["network_id", "station_id"])[invariant].nunique(
        dropna=False
    )
    if counts.gt(1).any(axis=None):
        bad = counts.loc[counts.gt(1).any(axis=1)].index.tolist()
        raise ValueError(f"donor roster varies across gap lengths: {bad[:5]}")
    return (
        data.sort_values(["network_id", "station_id"], kind="mergesort")
        .drop_duplicates(["network_id", "station_id"])
        .reset_index(drop=True)
    )


def _load_direction_ids(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(document, Mapping):
        return None
    return {nwis_match_key(item) for item in parse_nldi_nwissite_ids(document)}


def donor_direction_signature(
    target_id: str,
    donor_ids: Sequence[str],
    *,
    nldi_cache_dir: Path,
    distance_km: int = 200,
) -> tuple[str | None, str | None]:
    """Encode the frozen roster's UM/DM membership relative to its target."""

    target = _site_id(target_id)
    upstream = _load_direction_ids(
        Path(nldi_cache_dir) / f"{target}_UM_{int(distance_km)}.json"
    )
    downstream = _load_direction_ids(
        Path(nldi_cache_dir) / f"{target}_DM_{int(distance_km)}.json"
    )
    if upstream is None or downstream is None:
        return None, "direction_cache_missing"
    counts = {"U": 0, "D": 0, "B": 0, "X": 0}
    for donor in donor_ids:
        key = nwis_match_key(donor)
        in_upstream = key in upstream
        in_downstream = key in downstream
        category = (
            "B"
            if in_upstream and in_downstream
            else "U"
            if in_upstream
            else "D"
            if in_downstream
            else "X"
        )
        counts[category] += 1
    signature = "_".join(f"{key}{counts[key]}" for key in ("U", "D", "B", "X"))
    if counts["X"]:
        return signature, "donor_direction_unresolved"
    return signature, None


def _haversine_km(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float
) -> float:
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 6371.0088 * 2.0 * math.asin(min(1.0, math.sqrt(value)))


def build_station_covariates(
    predictors: pd.DataFrame,
    *,
    gages: pd.DataFrame,
    bfi: pd.DataFrame,
    station_catalog: pd.DataFrame,
    split_catalog: pd.DataFrame,
    nldi_cache_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bind the six factors and return station rows plus long-form attrition."""

    reject_outcome_columns([predictors, gages, bfi, station_catalog, split_catalog])
    rosters = collapse_predictor_rosters(predictors)

    gages_work = gages.copy()
    if "STAID" not in gages_work.columns:
        raise ValueError("full GAGES-II attributes require a STAID column")
    required_gages = {"MAJ_NDAMS_2009", "DRAIN_SQKM", "AGGECOREGION"}
    missing_gages = sorted(required_gages.difference(gages_work.columns))
    if missing_gages:
        raise ValueError(f"full GAGES-II attributes missing columns: {missing_gages}")
    gages_work["station_id"] = gages_work["STAID"].map(_site_id)
    major_dams = pd.to_numeric(gages_work["MAJ_NDAMS_2009"], errors="coerce")
    gages_work["upstream_major_dam_2009"] = major_dams.ge(1).where(
        major_dams.notna()
    )
    gages_work = gages_work.drop_duplicates("station_id").set_index("station_id")
    bfi_work = bfi.copy()
    bfi_work["STAID"] = bfi_work["STAID"].map(_site_id)
    bfi_work = bfi_work.drop_duplicates("STAID").set_index("STAID")
    coords = station_catalog.copy()
    coords["site_id"] = coords["site_id"].map(_site_id)
    coords = coords.drop_duplicates("site_id").set_index("site_id")
    split = split_catalog.copy()
    split["network_id"] = split["network_id"].astype(str)
    split = split.drop_duplicates("network_id").set_index("network_id")

    rows: list[dict[str, Any]] = []
    attrition: list[dict[str, str]] = []
    for roster in rosters.itertuples(index=False):
        network_id = str(roster.network_id)
        target = _site_id(roster.station_id)
        donors = tuple(
            _site_id(item)
            for item in str(roster.donor_station_ids).split("|")
            if _site_id(item)
        )
        reasons: list[str] = []
        role = str(roster.role)
        if role not in OPEN_ROLES:
            reasons.append("not_open_role")
        split_row = split.loc[network_id] if network_id in split.index else None
        split_role = str(split_row.get("role", "")) if split_row is not None else ""
        if split_row is None:
            reasons.append("split_catalog_missing")
        elif split_role != role:
            reasons.append("split_role_mismatch")

        gages_row = gages_work.loc[target] if target in gages_work.index else None
        if gages_row is None:
            reasons.append("gages_station_missing")
            regulated: bool | None = None
            drainage_area = float("nan")
            climate = ""
        else:
            raw_regulated = gages_row.get("upstream_major_dam_2009")
            regulated = bool(raw_regulated) if pd.notna(raw_regulated) else None
            if regulated is None:
                reasons.append("regulation_missing")
            drainage_area = float(
                pd.to_numeric(gages_row.get("DRAIN_SQKM"), errors="coerce")
            )
            if not np.isfinite(drainage_area) or drainage_area <= 0:
                reasons.append("drainage_area_missing")
            climate = str(gages_row.get("AGGECOREGION", "")).strip()
            if not climate or climate.lower() == "nan":
                reasons.append("climate_missing")

        bfi_value = (
            float(pd.to_numeric(bfi_work.loc[target].get("BFI_AVE"), errors="coerce"))
            if target in bfi_work.index
            else float("nan")
        )
        if not np.isfinite(bfi_value):
            reasons.append("bfi_missing")

        nearest_distance = float("nan")
        if target not in coords.index:
            reasons.append("target_coordinates_missing")
        else:
            target_lat = float(pd.to_numeric(coords.loc[target].get("latitude"), errors="coerce"))
            target_lon = float(pd.to_numeric(coords.loc[target].get("longitude"), errors="coerce"))
            distances: list[float] = []
            if np.isfinite(target_lat) and np.isfinite(target_lon):
                for donor in donors:
                    if donor not in coords.index:
                        continue
                    donor_lat = float(
                        pd.to_numeric(coords.loc[donor].get("latitude"), errors="coerce")
                    )
                    donor_lon = float(
                        pd.to_numeric(coords.loc[donor].get("longitude"), errors="coerce")
                    )
                    if np.isfinite(donor_lat) and np.isfinite(donor_lon):
                        distances.append(
                            _haversine_km(target_lat, target_lon, donor_lat, donor_lon)
                        )
            if distances:
                nearest_distance = min(distances)
            else:
                reasons.append("donor_coordinates_missing")

        direction, direction_reason = donor_direction_signature(
            target,
            donors,
            nldi_cache_dir=nldi_cache_dir,
        )
        if direction_reason:
            reasons.append(direction_reason)
        unique_reasons = sorted(set(reasons))
        for reason in unique_reasons:
            attrition.append(
                {"network_id": network_id, "station_id": target, "reason": reason}
            )
        rows.append(
            {
                "network_id": network_id,
                "station_id": target,
                "role": role,
                "regulated": regulated,
                "donor_count": int(roster.n_donors),
                "donor_direction": direction,
                "nearest_donor_distance_km": nearest_distance,
                "drainage_area_sqkm": drainage_area,
                "climate": climate,
                "bfi": bfi_value,
                "catalog_climate_band": (
                    str(split_row.get("climate_band", "")) if split_row is not None else ""
                ),
                "catalog_regulation_stratum": (
                    str(split_row.get("regulation_stratum", ""))
                    if split_row is not None
                    else ""
                ),
                "donor_station_ids": "|".join(donors),
                "eligible_for_matching": not unique_reasons,
            }
        )
    covariates = pd.DataFrame(rows).sort_values(
        ["network_id", "station_id"], kind="mergesort"
    )
    attrition_frame = pd.DataFrame(
        attrition, columns=["network_id", "station_id", "reason"]
    ).sort_values(["network_id", "station_id", "reason"], kind="mergesort")
    return covariates.reset_index(drop=True), attrition_frame.reset_index(drop=True)


def _scale(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size < 2:
        return 1.0
    value = float(np.quantile(finite, 0.75) - np.quantile(finite, 0.25))
    return value if value > 0 else 1.0


def make_pair_plan(covariates: pd.DataFrame) -> pd.DataFrame:
    """Max-cardinality one-to-one match within frozen categorical strata."""

    reject_outcome_columns([covariates])
    required = {
        "network_id",
        "station_id",
        "role",
        "regulated",
        "donor_count",
        "donor_direction",
        "nearest_donor_distance_km",
        "drainage_area_sqkm",
        "climate",
        "bfi",
        "eligible_for_matching",
    }
    missing = sorted(required.difference(covariates.columns))
    if missing:
        raise ValueError(f"station covariates missing columns: {missing}")
    usable = covariates.loc[covariates["eligible_for_matching"].astype(bool)].copy()
    if usable.empty:
        return pd.DataFrame(columns=_pair_columns())
    usable["log_drainage_area"] = np.log(
        pd.to_numeric(usable["drainage_area_sqkm"], errors="coerce")
    )
    scales = {
        "nearest": _scale(usable["nearest_donor_distance_km"]),
        "drainage": _scale(usable["log_drainage_area"]),
        "bfi": _scale(usable["bfi"]),
    }
    pairs: list[dict[str, Any]] = []
    for key, piece in usable.groupby(
        list(EXACT_MATCH_STRATA), dropna=False, sort=True
    ):
        treated = piece.loc[piece["regulated"].eq(True)].sort_values(
            ["network_id", "station_id"], kind="mergesort"
        )
        controls = piece.loc[piece["regulated"].eq(False)].sort_values(
            ["network_id", "station_id"], kind="mergesort"
        )
        if treated.empty or controls.empty:
            continue
        cost = np.empty((len(treated), len(controls)), dtype=float)
        for row_index, (_, treated_row) in enumerate(treated.iterrows()):
            for column_index, (_, control_row) in enumerate(controls.iterrows()):
                cost[row_index, column_index] = (
                    abs(
                        float(treated_row["nearest_donor_distance_km"])
                        - float(control_row["nearest_donor_distance_km"])
                    )
                    / scales["nearest"]
                    + abs(
                        float(treated_row["log_drainage_area"])
                        - float(control_row["log_drainage_area"])
                    )
                    / scales["drainage"]
                    + abs(float(treated_row["bfi"]) - float(control_row["bfi"]))
                    / scales["bfi"]
                )
                cost[row_index, column_index] += 1e-12 * (
                    row_index * (len(controls) + 1) + column_index
                )
        row_indices, column_indices = linear_sum_assignment(cost)
        role, donor_count, donor_direction, climate = key
        for row_index, column_index in zip(row_indices, column_indices):
            treated_row = treated.iloc[int(row_index)]
            control_row = controls.iloc[int(column_index)]
            pairs.append(
                {
                    "regulated_id": str(treated_row["station_id"]),
                    "control_id": str(control_row["station_id"]),
                    "regulated_network_id": str(treated_row["network_id"]),
                    "control_network_id": str(control_row["network_id"]),
                    "role": str(role),
                    "donor_count": int(donor_count),
                    "donor_count_abs_diff": 0,
                    "donor_direction": str(donor_direction),
                    "donor_direction_match": True,
                    "nearest_donor_distance_abs_diff": abs(
                        float(treated_row["nearest_donor_distance_km"])
                        - float(control_row["nearest_donor_distance_km"])
                    ),
                    "log_drainage_area_abs_diff": abs(
                        float(treated_row["log_drainage_area"])
                        - float(control_row["log_drainage_area"])
                    ),
                    "climate": str(climate),
                    "climate_match": True,
                    "bfi_abs_diff": abs(
                        float(treated_row["bfi"]) - float(control_row["bfi"])
                    ),
                    "standardized_l1_match_distance": float(
                        cost[int(row_index), int(column_index)]
                    ),
                }
            )
    return pd.DataFrame(pairs, columns=_pair_columns()).sort_values(
        ["role", "regulated_id", "control_id"], kind="mergesort"
    ).reset_index(drop=True)


def make_pair_attrition(
    covariates: pd.DataFrame, pairs: pd.DataFrame
) -> pd.DataFrame:
    """Explain why each complete-six-factor station was not assigned."""

    reject_outcome_columns([covariates, pairs])
    usable = covariates.loc[covariates["eligible_for_matching"].astype(bool)].copy()
    matched = {
        (str(row.regulated_network_id), str(row.regulated_id))
        for row in pairs.itertuples(index=False)
    } | {
        (str(row.control_network_id), str(row.control_id))
        for row in pairs.itertuples(index=False)
    }
    rows: list[dict[str, str]] = []
    for row in usable.itertuples(index=False):
        key = (str(row.network_id), str(row.station_id))
        if key in matched:
            continue
        opposite = usable.loc[usable["regulated"].eq(not bool(row.regulated))]
        for column in EXACT_MATCH_STRATA:
            opposite = opposite.loc[opposite[column].eq(getattr(row, column))]
        reason = (
            "no_eligible_opposite_exposure_in_exact_stratum"
            if opposite.empty
            else "not_selected_by_one_to_one_assignment"
        )
        rows.append(
            {
                "network_id": str(row.network_id),
                "station_id": str(row.station_id),
                "reason": reason,
            }
        )
    return pd.DataFrame(
        rows, columns=["network_id", "station_id", "reason"]
    ).sort_values(["network_id", "station_id", "reason"], kind="mergesort")


def _pair_columns() -> list[str]:
    return [
        "regulated_id",
        "control_id",
        "regulated_network_id",
        "control_network_id",
        "role",
        "donor_count",
        "donor_count_abs_diff",
        "donor_direction",
        "donor_direction_match",
        "nearest_donor_distance_abs_diff",
        "log_drainage_area_abs_diff",
        "climate",
        "climate_match",
        "bfi_abs_diff",
        "standardized_l1_match_distance",
    ]


def matching_readiness(
    covariates: pd.DataFrame,
    attrition: pd.DataFrame,
    pairs: pd.DataFrame,
    *,
    matching_factors: Sequence[str],
    pair_attrition: pd.DataFrame | None = None,
    input_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Return a non-result readiness and attrition manifest."""

    frozen = tuple(str(item) for item in matching_factors)
    factor_contract_matches = set(frozen) == set(FROZEN_MATCHING_FACTORS)
    eligible = covariates.loc[covariates["eligible_for_matching"].astype(bool)]
    attrition_counts = (
        attrition["reason"].value_counts().sort_index().astype(int).to_dict()
        if not attrition.empty
        else {}
    )
    pair_attrition_counts = (
        pair_attrition["reason"].value_counts().sort_index().astype(int).to_dict()
        if pair_attrition is not None and not pair_attrition.empty
        else {}
    )
    identities = {
        name: {"path": path.as_posix(), "sha256": _sha256(path)}
        for name, path in sorted((input_paths or {}).items())
        if path.is_file()
    }
    network_pair_columns = {"regulated_network_id", "control_network_id"}
    n_unique_network_pairs = (
        len(
            pairs.loc[:, sorted(network_pair_columns)]
            .astype(str)
            .drop_duplicates()
        )
        if network_pair_columns.issubset(pairs.columns)
        else 0
    )

    def maximum(column: str) -> float | None:
        if column not in pairs:
            return None
        values = pd.to_numeric(pairs[column], errors="coerce")
        return float(values.max()) if np.isfinite(values).any() else None

    max_log_drainage = maximum("log_drainage_area_abs_diff")
    balance_diagnostics = {
        "n_station_pairs": len(pairs),
        "n_unique_network_pairs": n_unique_network_pairs,
        "max_nearest_donor_distance_abs_diff_km": maximum(
            "nearest_donor_distance_abs_diff"
        ),
        "max_log_drainage_area_abs_diff": max_log_drainage,
        "max_drainage_area_ratio": (
            float(np.exp(max_log_drainage))
            if max_log_drainage is not None
            else None
        ),
        "max_bfi_abs_diff": maximum("bfi_abs_diff"),
        "max_standardized_l1_match_distance": maximum(
            "standardized_l1_match_distance"
        ),
        "caliper_invented_or_applied": False,
        "balance_supports_formal_confound_control": False,
    }
    return {
        "schema_version": "t5_v9_1_outcome_blind_matching_readiness_v1",
        "status": "descriptive_infeasible_confound_control",
        "purpose": "matching_contract_and_attrition_not_t5_evidence",
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "passed": False,
        "sealed_outcomes_opened": False,
        "t2_outcome_columns_read": False,
        "t2_primary_y_bound": False,
        "old_two_pair_result_reused": False,
        "roles_allowed": sorted(OPEN_ROLES),
        "matching_unit": "target_station",
        "exposure": "upstream_major_dam_2009",
        "exposure_derivation": "full_gages_ii_MAJ_NDAMS_2009_ge_1",
        "frozen_matching_factors": list(frozen),
        "factor_contract_matches_freeze": factor_contract_matches,
        "estimators": {
            "donor_count": "frozen_train_only_t2_donor_roster_size",
            "donor_direction": "nldi_UM_DM_200km_membership_signature",
            "nearest_donor_distance": "minimum_haversine_km_over_frozen_roster",
            "drainage_area": "gages_ii_DRAIN_SQKM",
            "climate": "gages_ii_AGGECOREGION_exact_match",
            "bfi": "gages_ii_BFI_AVE",
            "assignment": (
                "maximum_cardinality_linear_sum_assignment_within_exact_"
                "role_donor_count_direction_climate_strata"
            ),
        },
        "calipers": None,
        "caliper_note": "The v9.1 freeze names factors but does not lock calipers.",
        "n_station_rosters": len(covariates),
        "n_stations_complete_six_factors": len(eligible),
        "n_regulated_complete": int(eligible["regulated"].eq(True).sum()),
        "n_control_complete": int(eligible["regulated"].eq(False).sum()),
        "n_pair_plan_rows": len(pairs),
        "n_station_pairs": len(pairs),
        "n_unique_network_pairs": n_unique_network_pairs,
        "independent_unit": "regulated_control_network_pair",
        "pair_plan_preserved_for_audit": True,
        "pair_plan_ready": False,
        "formal_run_allowed": False,
        "causal_interpretation_allowed": False,
        "t5_pass_claim_allowed": False,
        "caliper_invented_or_applied": False,
        "rematching_performed": False,
        "balance_supports_formal_confound_control": False,
        "balance_diagnostics": balance_diagnostics,
        "forbidden_claims": [
            "causal_regulation_effect",
            "formal_confound_control",
            "three_independent_pairs",
            "t5_passed",
            "network_interval",
        ],
        "attrition_reason_counts": attrition_counts,
        "pair_attrition_reason_counts": pair_attrition_counts,
        "input_identities": identities,
    }


__all__ = [
    "EXACT_MATCH_STRATA",
    "FORBIDDEN_OUTCOME_COLUMNS",
    "FROZEN_MATCHING_FACTORS",
    "OPEN_ROLES",
    "build_station_covariates",
    "collapse_predictor_rosters",
    "donor_direction_signature",
    "make_pair_attrition",
    "make_pair_plan",
    "matching_readiness",
    "reject_outcome_columns",
]
