"""Immutable analysis-data versions and their provenance manifests.

The published measurements are never edited in place.  Each named version is
derived from the prepared long table, written to its own directory, and given a
fresh scaler fitted only on that version's training values.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pandas as pd

from .prepare import assign_time_split, fit_train_scaler, to_daily_wide
from .quality import attach_qc_fields, qc_counts


@dataclass(frozen=True)
class DataVersionDefinition:
    """A fixed, reviewable transformation applied to the published table."""

    name: str
    description: str
    evidence_role: str
    sensitivity_only: bool = False


_DEFINITIONS = {
    "published_v1": DataVersionDefinition(
        name="published_v1",
        description="Published values with no additional quality exclusions or adjustments.",
        evidence_role="published_reference",
    ),
    "no_s2_suspect_v1": DataVersionDefinition(
        name="no_s2_suspect_v1",
        description=(
            "Excludes S2 T, F, and L analysis values from 2013-01-01 through "
            "2019-12-31 while preserving the published raw values and observation flags."
        ),
        evidence_role="quality_exclusion_sensitivity",
        sensitivity_only=True,
    ),
    "b1_no_level_v1": DataVersionDefinition(
        name="b1_no_level_v1",
        description=(
            "Excludes B1 water-level (L) analysis values over the full record while "
            "preserving the published raw values and observation flags."
        ),
        evidence_role="information_ablation",
        sensitivity_only=True,
    ),
    "b1_shift_sensitivity_v1": DataVersionDefinition(
        name="b1_shift_sensitivity_v1",
        description=(
            "Hypothetical sensitivity only: subtracts exactly 8.48 m from B1 L "
            "analysis values on and after 2019-01-01. This is not a factual correction."
        ),
        evidence_role="hypothetical_shift_sensitivity",
        sensitivity_only=True,
    ),
    "published_v2": DataVersionDefinition(
        name="published_v2",
        description=(
            "Published values with split QC fields. observed_unflagged rows are "
            "analysis-eligible with provider_qc_status=unknown. B1 level from "
            "2019-01-01 and S2 hydrology for 2013-2019 are flagged, not silently edited."
        ),
        evidence_role="published_reference",
    ),
    "no_s2_suspect_v2": DataVersionDefinition(
        name="no_s2_suspect_v2",
        description=(
            "published_v2 plus exclusion of S2 T, F, and L analysis values from "
            "2013-01-01 through 2019-12-31."
        ),
        evidence_role="quality_exclusion_sensitivity",
        sensitivity_only=True,
    ),
    "b1_no_level_v2": DataVersionDefinition(
        name="b1_no_level_v2",
        description=(
            "published_v2 plus exclusion of B1 water-level (L) analysis values "
            "over the full record."
        ),
        evidence_role="information_ablation",
        sensitivity_only=True,
    ),
    "b1_shift_sensitivity_v2": DataVersionDefinition(
        name="b1_shift_sensitivity_v2",
        description=(
            "published_v2 plus a hypothetical -8.48 m adjustment to B1 L on and "
            "after 2019-01-01. This is not a factual correction."
        ),
        evidence_role="hypothetical_shift_sensitivity",
        sensitivity_only=True,
    ),
}

DATA_VERSION_DEFINITIONS: Mapping[str, DataVersionDefinition] = MappingProxyType(
    _DEFINITIONS
)
DATA_VERSION_NAMES = tuple(DATA_VERSION_DEFINITIONS)
_V1_VERSIONS = frozenset(
    {
        "published_v1",
        "no_s2_suspect_v1",
        "b1_no_level_v1",
        "b1_shift_sensitivity_v1",
    }
)
_V2_VERSIONS = frozenset(
    {
        "published_v2",
        "no_s2_suspect_v2",
        "b1_no_level_v2",
        "b1_shift_sensitivity_v2",
    }
)
_TRANSFORM_ALIASES = {
    "published_v2": "published_v1",
    "no_s2_suspect_v2": "no_s2_suspect_v1",
    "b1_no_level_v2": "b1_no_level_v1",
    "b1_shift_sensitivity_v2": "b1_shift_sensitivity_v1",
}

_REQUIRED_LONG_COLUMNS = {
    "date",
    "station_id",
    "variable",
    "raw_value",
    "value",
    "natural_observed",
    "quality_approved",
    "qc_status",
}
_S2_SUSPECT_START = pd.Timestamp("2013-01-01")
_S2_SUSPECT_END = pd.Timestamp("2019-12-31")
_B1_SHIFT_START = pd.Timestamp("2019-01-01")
_B1_SHIFT_METRES = 8.48


def get_data_version_definition(data_version: str) -> DataVersionDefinition:
    """Return a named definition, rejecting unregistered ad-hoc versions."""

    try:
        return DATA_VERSION_DEFINITIONS[data_version]
    except KeyError as error:
        choices = ", ".join(DATA_VERSION_NAMES)
        raise ValueError(
            f"Unknown data_version {data_version!r}; choose one of: {choices}"
        ) from error


def _transform_key(data_version: str) -> str:
    return _TRANSFORM_ALIASES.get(data_version, data_version)


def _validate_source_long(
    long_data: pd.DataFrame, data_version: str | None = None
) -> None:
    missing = sorted(_REQUIRED_LONG_COLUMNS.difference(long_data.columns))
    if missing:
        raise KeyError(f"Prepared daily_long is missing required columns: {missing}")
    if long_data.empty:
        raise ValueError("Prepared daily_long is empty")
    if pd.to_datetime(long_data["date"], errors="coerce").isna().any():
        raise ValueError("Prepared daily_long contains invalid dates")

    if "data_version" in long_data:
        source_versions = set(long_data["data_version"].dropna().astype(str).unique())
        if not source_versions:
            return
        if data_version in _V2_VERSIONS:
            allowed = {"published_v1", "published_v2"}
        else:
            allowed = {"published_v1"}
        if source_versions - allowed:
            raise ValueError(
                "Data versions must be built from an unversioned or published_v1 source; "
                f"found {sorted(source_versions)}"
            )


def _target_mask(long_data: pd.DataFrame, data_version: str) -> pd.Series:
    dates = pd.to_datetime(long_data["date"]).dt.normalize()
    stations = long_data["station_id"].astype(str)
    variables = long_data["variable"].astype(str)
    transform = _transform_key(data_version)
    if transform == "published_v1":
        return pd.Series(False, index=long_data.index)
    if transform == "no_s2_suspect_v1":
        return (
            stations.eq("S2")
            & variables.isin(("T", "F", "L"))
            & dates.between(_S2_SUSPECT_START, _S2_SUSPECT_END, inclusive="both")
        )
    if transform == "b1_no_level_v1":
        return stations.eq("B1") & variables.eq("L")
    if transform == "b1_shift_sensitivity_v1":
        return stations.eq("B1") & variables.eq("L") & dates.ge(_B1_SHIFT_START)
    raise AssertionError(f"Unhandled registered data version: {data_version}")


def _changed_count(left: pd.Series, right: pd.Series) -> int:
    equal = left.eq(right) | (left.isna() & right.isna())
    return int((~equal).sum())


def apply_data_version(long_data: pd.DataFrame, data_version: str) -> pd.DataFrame:
    """Apply one fixed version without reordering rows or altering source evidence.

    ``raw_value`` and ``natural_observed`` are invariants.  Exclusion versions
    change only analysis eligibility (``value`` and ``quality_approved``); the
    shift version changes only the derived analysis value.
    """

    get_data_version_definition(data_version)
    _validate_source_long(long_data, data_version)
    result = long_data.copy()
    raw_before = result["raw_value"].copy()
    observed_before = result["natural_observed"].copy()
    transform = _transform_key(data_version)
    if data_version in _V2_VERSIONS:
        result = attach_qc_fields(result)

    result["data_version"] = data_version
    result["data_version_action"] = "unchanged"
    target = _target_mask(result, data_version)

    if transform == "no_s2_suspect_v1":
        result.loc[target, "value"] = np.nan
        result.loc[target, "quality_approved"] = False
        if "analysis_eligible" in result:
            result.loc[target, "analysis_eligible"] = False
        result.loc[target, "qc_status"] = "excluded_s2_suspect_period"
        result.loc[target, "data_version_action"] = "excluded_s2_hydrology_2013_2019"
    elif transform == "b1_no_level_v1":
        result.loc[target, "value"] = np.nan
        result.loc[target, "quality_approved"] = False
        if "analysis_eligible" in result:
            result.loc[target, "analysis_eligible"] = False
        result.loc[target, "qc_status"] = "excluded_b1_level"
        result.loc[target, "data_version_action"] = "excluded_b1_level"
    elif transform == "b1_shift_sensitivity_v1":
        result.loc[target, "value"] = (
            pd.to_numeric(result.loc[target, "value"], errors="coerce")
            - _B1_SHIFT_METRES
        )
        result.loc[target, "data_version_action"] = "hypothetical_b1_level_minus_8.48_m"
    if data_version in _V2_VERSIONS:
        flagged = result["known_issue_flag"].fillna(False).astype(bool)
        result.loc[flagged & result["data_version_action"].eq("unchanged"), "data_version_action"] = (
            "flagged_known_issue"
        )

    if _changed_count(raw_before, result["raw_value"]):
        raise RuntimeError("A data-version transformation altered raw_value")
    if _changed_count(observed_before, result["natural_observed"]):
        raise RuntimeError("A data-version transformation altered natural_observed")
    return result


def build_version_frames(
    source_long: pd.DataFrame,
    data_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build versioned long/wide tables and a version-specific train scaler."""

    versioned_long = apply_data_version(source_long, data_version)
    if "split" not in versioned_long:
        versioned_long = assign_time_split(versioned_long)
    versioned_wide, measurement_columns = to_daily_wide(versioned_long)
    versioned_wide.insert(2, "data_version", data_version)

    train = versioned_wide.loc[versioned_wide["split"] == "train"]
    active_columns = [
        column for column in measurement_columns if train[column].notna().any()
    ]
    excluded_columns = [
        column for column in measurement_columns if column not in active_columns
    ]
    scaler = fit_train_scaler(versioned_wide, active_columns)
    scaler["data_version"] = data_version
    scaler["excluded_features"] = {
        column: {"reason": "no_analysis_values_in_training_split"}
        for column in excluded_columns
    }
    return versioned_long, versioned_wide, scaler


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_input_path(path: Path) -> str:
    """Prefer a repository-relative provenance path when one is available."""

    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def _transformation_counts(
    source_long: pd.DataFrame,
    versioned_long: pd.DataFrame,
    data_version: str,
) -> dict[str, int]:
    target = _target_mask(source_long, data_version)
    source_values = pd.to_numeric(source_long["value"], errors="coerce")
    version_values = pd.to_numeric(versioned_long["value"], errors="coerce")
    values_excluded = source_values.notna() & version_values.isna()
    adjusted = (
        source_values.notna()
        & version_values.notna()
        & ~np.isclose(
            source_values.fillna(0.0),
            version_values.fillna(0.0),
            rtol=0.0,
            atol=1e-12,
        )
    )
    source_quality = source_long["quality_approved"].fillna(False).astype(bool)
    version_quality = versioned_long["quality_approved"].fillna(False).astype(bool)
    return {
        "target_rows": int(target.sum()),
        "analysis_values_excluded": int(values_excluded.sum()),
        "quality_eligibility_removed": int((source_quality & ~version_quality).sum()),
        "analysis_values_adjusted": int(adjusted.sum()),
        "raw_values_changed": _changed_count(
            source_long["raw_value"], versioned_long["raw_value"]
        ),
        "natural_observed_flags_changed": _changed_count(
            source_long["natural_observed"], versioned_long["natural_observed"]
        ),
    }


def _counts(
    source_long: pd.DataFrame,
    versioned_long: pd.DataFrame,
    versioned_wide: pd.DataFrame,
    scaler: Mapping[str, Any],
) -> tuple[dict[str, int], dict[str, Any]]:
    input_counts = {
        "long_rows": len(source_long),
        "dates": int(pd.to_datetime(source_long["date"]).nunique()),
        "stations": int(source_long["station_id"].nunique()),
        "variables": int(source_long["variable"].nunique()),
        "analysis_values": int(
            pd.to_numeric(source_long["value"], errors="coerce").notna().sum()
        ),
        "natural_observed_values": int(
            source_long["natural_observed"].fillna(False).sum()
        ),
        "quality_approved_values": int(
            source_long["quality_approved"].fillna(False).sum()
        ),
        **{
            f"source_{key}": value
            for key, value in qc_counts(source_long).items()
        },
    }
    output_counts: dict[str, Any] = {
        "long_rows": len(versioned_long),
        "wide_rows": len(versioned_wide),
        "analysis_values": int(
            pd.to_numeric(versioned_long["value"], errors="coerce").notna().sum()
        ),
        "natural_observed_values": int(
            versioned_long["natural_observed"].fillna(False).sum()
        ),
        "quality_approved_values": int(
            versioned_long["quality_approved"].fillna(False).sum()
        ),
        "split_wide_rows": {
            str(split): int(count)
            for split, count in versioned_wide["split"].value_counts(sort=False).items()
        },
        "scaled_features": len(scaler["features"]),
        "excluded_scaler_features": len(scaler["excluded_features"]),
    }
    return input_counts, output_counts


def _write_one_version(
    source_long: pd.DataFrame,
    input_path: Path,
    input_sha256: str,
    output_root: Path,
    data_version: str,
) -> dict[str, Any]:
    definition = get_data_version_definition(data_version)
    version_dir = output_root / data_version
    if version_dir.exists():
        raise FileExistsError(
            f"Immutable data-version directory already exists: {version_dir}. "
            "Use a new output root after reviewing provenance."
        )

    versioned_long, versioned_wide, scaler = build_version_frames(
        source_long, data_version
    )
    input_counts, output_counts = _counts(
        source_long, versioned_long, versioned_wide, scaler
    )
    transformation_counts = _transformation_counts(
        source_long, versioned_long, data_version
    )

    split_dir = version_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=False)
    long_path = version_dir / "daily_long.parquet"
    wide_path = version_dir / "daily_wide.parquet"
    scaler_path = version_dir / "scaler.json"
    versioned_long.to_parquet(long_path, index=False)
    versioned_wide.to_parquet(wide_path, index=False)
    split_paths: dict[str, Path] = {}
    for split in ("train", "validation", "test"):
        split_path = split_dir / f"{split}.parquet"
        versioned_wide.loc[versioned_wide["split"] == split].to_parquet(
            split_path, index=False
        )
        split_paths[split] = split_path
    with scaler_path.open("w", encoding="utf-8") as handle:
        json.dump(scaler, handle, ensure_ascii=False, indent=2, allow_nan=False)

    artifacts = {
        "daily_long.parquet": {"sha256": _sha256_file(long_path)},
        "daily_wide.parquet": {"sha256": _sha256_file(wide_path)},
        "scaler.json": {"sha256": _sha256_file(scaler_path)},
    }
    artifacts.update(
        {
            f"splits/{split}.parquet": {"sha256": _sha256_file(path)}
            for split, path in split_paths.items()
        }
    )
    manifest: dict[str, Any] = {
        "manifest_schema_version": 1,
        "data_version": data_version,
        "definition": asdict(definition),
        "input_path": _portable_input_path(input_path),
        "input_sha256": input_sha256,
        "input_counts": input_counts,
        "output_counts": output_counts,
        "transformation_counts": transformation_counts,
        "artifacts": artifacts,
    }
    with (version_dir / "version_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, allow_nan=False)
    return manifest


def build_data_versions(
    input_long_path: str | Path,
    output_root: str | Path = "data_versions",
    data_versions: Iterable[str] = DATA_VERSION_NAMES,
) -> dict[str, dict[str, Any]]:
    """Materialise one or more registered versions under ``output_root``.

    Existing version directories are never overwritten.  This makes a version
    name an immutable contract between data preparation and downstream runs.
    """

    input_path = Path(input_long_path)
    if not input_path.is_file():
        raise FileNotFoundError(f"Prepared daily_long file not found: {input_path}")
    requested = tuple(data_versions)
    if not requested:
        raise ValueError("At least one data version must be requested")
    if len(set(requested)) != len(requested):
        raise ValueError(f"Duplicate data versions requested: {requested}")
    for data_version in requested:
        get_data_version_definition(data_version)

    root = Path(output_root)
    existing = [
        root / data_version
        for data_version in requested
        if (root / data_version).exists()
    ]
    if existing:
        paths = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Immutable data-version directories already exist: {paths}"
        )

    source_long = pd.read_parquet(input_path)
    _validate_source_long(source_long)
    input_sha256 = _sha256_file(input_path)
    manifests: dict[str, dict[str, Any]] = {}
    for data_version in requested:
        manifests[data_version] = _write_one_version(
            source_long=source_long,
            input_path=input_path,
            input_sha256=input_sha256,
            output_root=root,
            data_version=data_version,
        )
    return manifests


__all__ = [
    "DATA_VERSION_DEFINITIONS",
    "DATA_VERSION_NAMES",
    "DataVersionDefinition",
    "apply_data_version",
    "build_data_versions",
    "build_version_frames",
    "get_data_version_definition",
]
