"""Fail-closed M/H consumers for a future T2 workload freeze.

The frozen v3 workload classifies every extended information cell as
structurally unavailable and binds that classification to its item identity.
This module therefore does not alter the v3 runner.  It supplies the candidate
consumer contract needed by a separately frozen successor workload.

Only open failure-closure auxiliary artifacts are accepted.  Requested M/H
features are date-aligned and standardized by ``t2_information_adapters``.
Every station-variable feature in the requested information group must have a
minimum train count and complete coverage over the scored gap.  A missing
channel (for example an unavailable L series) blocks the cell; it is never
dropped, zero-filled, or silently substituted by another channel.

Meteorology lag is also part of the candidate workload identity.  The frozen
``-1/0/+1`` roster denotes three separately required sensitivity cells; no
held-out outcome may select one lag or collapse the three cells post hoc.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.recoverability_spectrum import recoverability
from stream_recoverability.data.t2_information_adapters import (
    ADAPTER_CONTRACT_VERSION,
    HYDRAULICS_VARIABLES,
    METEOROLOGY_VARIABLES,
    FittedT2InformationAdapter,
    InformationFeatureBundle,
    attach_information_features,
    fit_t2_information_adapter,
)
from stream_recoverability.data.t2_information_corpus_acquisition import (
    NETWORK_SCHEMA_VERSION,
    SPLIT_SHA256,
    TERMINAL_STATUSES,
)
from stream_recoverability.models.baselines import (
    ClimatologyBaseline,
    DonorRegressionBaseline,
    XGBoostBaseline,
)

from .t2_recovery_benchmark import (
    EXTENDED_INFORMATION_CONDITIONS,
    MIN_TRAIN_OBSERVATIONS,
    RUNNER_CONTRACT_VERSION,
    OpenNetwork,
    WorkItem,
    _combined_model_frame,
    _prediction_sha256,
    _year_split,
    json_safe,
    read_panel,
)

AUXILIARY_ROOT = Path(
    "data_versions/global_network_corpus_v1/open_role_auxiliary/failure_closure6"
)
INTEGRATION_CONTRACT_VERSION = "t2_v91_information_runner_candidate_v4_v1"
SUPPORTED_MODELS = ("donor_regression", "xgboost")
METEOROLOGY_LAG_ROSTER = (-1, 0, 1)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError):
        return False
    return True


def _artifact_path(
    repo: Path,
    directory: Path,
    artifacts: dict[str, Any],
    key: str,
) -> Path:
    record = artifacts.get(key)
    if not isinstance(record, dict):
        raise TypeError(f"auxiliary manifest lacks artifact mapping: {key}")
    path = repo / str(record.get("path", ""))
    if not _inside(path, directory):
        raise ValueError(f"auxiliary artifact escaped its open network directory: {key}")
    if _sha256_file(path) != record.get("sha256"):
        raise ValueError(f"auxiliary artifact hash mismatch: {key}")
    return path


@dataclass(frozen=True)
class MaterializedAuxiliary:
    daily_long: pd.DataFrame
    coverage: pd.DataFrame
    audit: dict[str, Any]


@dataclass(frozen=True)
class InformationConsumerPreparation:
    supported: bool
    category: str
    reason: str
    model_frame: pd.DataFrame | None
    train_mask: pd.Series | None
    donor_columns: tuple[str, ...]
    boundary_feature: str | None
    auxiliary_features: tuple[str, ...]
    audit: dict[str, Any]


def load_materialized_auxiliary(
    repo_root: str | Path,
    network: OpenNetwork,
) -> MaterializedAuxiliary:
    """Load one integrity-checked open-role auxiliary bundle.

    Paths are derived from the already discovered open network role and ID;
    neither a manifest-provided role nor a caller-provided arbitrary path can
    redirect the loader into a sealed directory.
    """

    repo = Path(repo_root).resolve()
    if network.role not in {"development", "validation"}:
        raise ValueError("M/H integration accepts open development/validation only")
    if "sealed" in network.source_key.lower():
        raise ValueError("M/H integration refuses sealed source keys")
    root = (repo / AUXILIARY_ROOT).resolve()
    directory = root / network.role / "networks" / network.network_id
    if not _inside(directory, root):
        raise ValueError("auxiliary network directory is missing or unsafe")
    manifest_path = directory / "network_manifest.json"
    if not _inside(manifest_path, directory):
        raise ValueError("auxiliary network manifest is missing or unsafe")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_schema") != NETWORK_SCHEMA_VERSION
        or manifest.get("status") not in TERMINAL_STATUSES
        or manifest.get("acquisition_terminal") is not True
        or manifest.get("network_id") != network.network_id
        or manifest.get("role") != network.role
        or manifest.get("split_sha256") != SPLIT_SHA256
        or manifest.get("temperature_columns_read") != []
        or manifest.get("sealed_paths_traversed") is not False
        or manifest.get("sealed_temperature_records_read") is not False
        or manifest.get("performance_metrics_computed") is not False
    ):
        raise ValueError("auxiliary manifest violates the open non-outcome boundary")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise TypeError("auxiliary manifest artifacts must be a mapping")
    daily_path = _artifact_path(repo, directory, artifacts, "daily_long_auxiliary")
    coverage_path = _artifact_path(repo, directory, artifacts, "coverage")
    schema_path = _artifact_path(repo, directory, artifacts, "adapter_schema")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    expected_columns = {
        "date",
        "site_id",
        "variable",
        "value",
        "source",
        "natural_observed",
        "qc_status",
        "approval_status",
        "quality_approved",
    }
    if (
        schema.get("adapter_contract_version") != ADAPTER_CONTRACT_VERSION
        or set(schema.get("required_columns") or ()) != expected_columns
        or tuple((schema.get("variables") or {}).get("M") or ())
        != METEOROLOGY_VARIABLES
        or tuple((schema.get("variables") or {}).get("H") or ())
        != HYDRAULICS_VARIABLES
    ):
        raise ValueError("materialized auxiliary adapter schema is incompatible")

    daily = pd.read_parquet(daily_path)
    if not expected_columns.issubset(daily.columns):
        raise ValueError("materialized auxiliary table lacks required provider-QC fields")
    variables = set(daily["variable"].astype(str))
    if not variables.issubset({*METEOROLOGY_VARIABLES, *HYDRAULICS_VARIABLES}):
        raise ValueError("non-M/H variable reached information integration")
    coverage = pd.read_csv(coverage_path, dtype={"site_id": "string"})
    required_coverage = {
        "network_id",
        "role",
        "site_id",
        "variable",
        "information_group",
        "source_status",
        "eligible_coverage",
    }
    if not required_coverage.issubset(coverage.columns):
        raise ValueError("auxiliary coverage table lacks required fields")
    if set(coverage["network_id"].astype(str)) != {network.network_id}:
        raise ValueError("auxiliary coverage network identity mismatch")
    if set(coverage["role"].astype(str)) != {network.role}:
        raise ValueError("auxiliary coverage role mismatch")

    return MaterializedAuxiliary(
        daily_long=daily,
        coverage=coverage,
        audit={
            "manifest_path": str(manifest_path.relative_to(repo)),
            "manifest_sha256": _sha256_file(manifest_path),
            "daily_long_path": str(daily_path.relative_to(repo)),
            "daily_long_sha256": str(artifacts["daily_long_auxiliary"]["sha256"]),
            "coverage_path": str(coverage_path.relative_to(repo)),
            "coverage_sha256": str(artifacts["coverage"]["sha256"]),
            "adapter_schema_sha256": str(artifacts["adapter_schema"]["sha256"]),
            "materialization_status": manifest["status"],
            "n_source_failures_or_unavailable": int(
                manifest["n_source_failures_or_unavailable"]
            ),
            "sealed_paths_traversed": False,
            "sealed_temperature_records_read": False,
        },
    )


def _unsupported(
    *,
    category: str,
    reason: str,
    audit: dict[str, Any],
) -> InformationConsumerPreparation:
    return InformationConsumerPreparation(
        supported=False,
        category=category,
        reason=reason,
        model_frame=None,
        train_mask=None,
        donor_columns=(),
        boundary_feature=None,
        auxiliary_features=(),
        audit=audit,
    )


def prepare_information_item(
    panel: pd.DataFrame,
    daily_long: pd.DataFrame,
    item: WorkItem,
    *,
    meteorology_lag_days: int = 0,
    min_train_observations: int = MIN_TRAIN_OBSERVATIONS,
    adapter_cache: MutableMapping[
        str, tuple[FittedT2InformationAdapter, InformationFeatureBundle]
    ]
    | None = None,
    auxiliary_cache_identity: str | None = None,
) -> InformationConsumerPreparation:
    """Prepare an extended-information model frame without computing a score."""

    base_audit: dict[str, Any] = {
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "source_v3_runner_contract_version": RUNNER_CONTRACT_VERSION,
        "source_v3_item_id": item.item_id,
        "future_workload_freeze_required": True,
        "requested_condition": item.information_condition,
        "meteorology_lag_roster": list(METEOROLOGY_LAG_ROSTER),
        "meteorology_lag_roster_semantics": (
            "three_separate_required_sensitivity_cells_not_model_selection"
        ),
        "heldout_skill_used_to_select_meteorology_lag": False,
        "requested_feature_roster_policy": (
            "all_station_by_frozen_group_variables_required_no_channel_substitution"
        ),
        "gap_coverage_policy": "every_requested_feature_finite_on_every_gap_day",
        "train_coverage_policy": (
            f"every_requested_feature_has_at_least_{int(min_train_observations)}_train_days"
        ),
        "adapter_missing_policy": "preserve_na_no_fill",
        "model_train_missing_policy": (
            "train_only_column_median_declared_by_baseline_after_adapter_standardization"
        ),
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    if int(meteorology_lag_days) not in METEOROLOGY_LAG_ROSTER:
        raise ValueError("meteorology lag is outside the frozen -1/0/+1 roster")
    if item.information_condition not in EXTENDED_INFORMATION_CONDITIONS:
        return _unsupported(
            category="structural_not_applicable",
            reason="information_integration_requires_frozen_extended_condition",
            audit=base_audit,
        )
    if item.model not in SUPPORTED_MODELS:
        return _unsupported(
            category="structural_not_applicable",
            reason="model_has_no_declared_B_D_M_H_consumer",
            audit=base_audit,
        )
    if item.start_index < 0:
        return _unsupported(
            category="data_ineligible",
            reason="frozen_geometry_truth_or_common_placement_unavailable",
            audit=base_audit,
        )
    if item.boundary_mode == "none":
        return _unsupported(
            category="structural_not_applicable",
            reason="B_information_absent_in_frozen_geometry",
            audit=base_audit,
        )
    if item.donor_mask_rule == "mask_all_network_stations_during_gap":
        return _unsupported(
            category="structural_not_applicable",
            reason="D_information_masked_by_frozen_geometry",
            audit=base_audit,
        )
    if not isinstance(panel.index, pd.DatetimeIndex):
        raise TypeError("temperature panel must use a DatetimeIndex")
    if (
        panel.index.tz is not None
        or panel.index.has_duplicates
        or not panel.index.is_monotonic_increasing
        or not panel.index.equals(panel.index.normalize())
    ):
        raise ValueError("temperature panel requires sorted unique naive daily labels")
    target = item.target_station
    if target not in panel.columns:
        raise ValueError("target station is absent from temperature panel")
    start = int(item.start_index)
    stop = start + int(item.gap_length)
    if start < 0 or stop > len(panel):
        raise ValueError("frozen gap lies outside the temperature panel")
    donors = tuple(str(value) for value in panel.columns if str(value) != target)
    if not donors:
        raise ValueError("extended information consumer requires donor stations")

    train, _ = _year_split(panel.index)
    train[start:stop] = False
    train_mask = pd.Series(train, index=panel.index, dtype=bool)
    if adapter_cache is not None and not auxiliary_cache_identity:
        raise ValueError(
            "adapter_cache requires an integrity-bound auxiliary_cache_identity"
        )
    cache_identity = hashlib.sha256()
    cache_identity.update(ADAPTER_CONTRACT_VERSION.encode())
    cache_identity.update(str(auxiliary_cache_identity or "uncached").encode())
    cache_identity.update(np.asarray(panel.index.view("i8"), dtype="<i8").tobytes())
    cache_identity.update(train_mask.to_numpy(dtype=np.uint8).tobytes())
    cache_identity.update("\0".join(str(value) for value in panel.columns).encode())
    cache_identity.update(item.information_condition.encode())
    cache_identity.update(str(int(meteorology_lag_days)).encode("ascii"))
    cache_key = cache_identity.hexdigest()
    cached = adapter_cache.get(cache_key) if adapter_cache is not None else None
    if cached is None:
        fitted = fit_t2_information_adapter(
            daily_long,
            target_index=panel.index,
            train_mask=train_mask,
            site_ids=[str(value) for value in panel.columns],
            condition=item.information_condition,
            meteorology_lag_days=int(meteorology_lag_days),
        )
        bundle = fitted.transform(daily_long)
        if adapter_cache is not None:
            adapter_cache[cache_key] = (fitted, bundle)
        adapter_cache_hit = False
    else:
        fitted, bundle = cached
        adapter_cache_hit = True
    features = tuple(fitted.feature_names)
    gap = bundle.features.iloc[start:stop]
    gap_counts = gap.notna().sum().astype(int).to_dict()
    train_counts = {name: int(fitted.train_counts[name]) for name in features}
    insufficient_train = sorted(
        name for name, count in train_counts.items() if count < int(min_train_observations)
    )
    incomplete_gap = sorted(
        name for name, count in gap_counts.items() if count != int(item.gap_length)
    )
    base_audit.update(
        {
            "requested_information_groups": (
                ["B", "D", "M", "H"]
                if item.information_condition == "B_union_D_union_M_union_H"
                else ["B", "D", "M"]
            ),
            "meteorology_lag_days": int(meteorology_lag_days),
            "meteorology_alignment": (
                "source_date_equals_target_date_plus_lag_days"
            ),
            "hydraulics_alignment": "same_provider_calendar_day_label",
            "n_requested_auxiliary_features": len(features),
            "requested_auxiliary_features": list(features),
            "feature_train_counts": train_counts,
            "feature_gap_finite_counts": gap_counts,
            "insufficient_train_features": insufficient_train,
            "incomplete_gap_features": incomplete_gap,
            "adapter_manifest": fitted.manifest(),
            "adapter_transform_audit": dict(bundle.audit),
            "adapter_cache_key": cache_key,
            "adapter_cache_hit": adapter_cache_hit,
        }
    )
    if insufficient_train or incomplete_gap:
        return _unsupported(
            category="data_ineligible",
            reason="requested_auxiliary_feature_coverage_incomplete_fail_closed",
            audit=base_audit,
        )

    model_frame, boundary_feature = _combined_model_frame(
        panel,
        target=target,
        train_mask=train_mask,
        start=start,
        stop=stop,
        boundary_mode=item.boundary_mode,
    )
    model_frame = attach_information_features(model_frame, bundle)
    return InformationConsumerPreparation(
        supported=True,
        category="executable",
        reason="",
        model_frame=model_frame,
        train_mask=train_mask,
        donor_columns=donors,
        boundary_feature=boundary_feature,
        auxiliary_features=features,
        audit=base_audit,
    )


def prepare_materialized_information_item(
    repo_root: str | Path,
    network: OpenNetwork,
    item: WorkItem,
    *,
    meteorology_lag_days: int = 0,
    panel: pd.DataFrame | None = None,
    auxiliary: MaterializedAuxiliary | None = None,
    adapter_cache: MutableMapping[
        str, tuple[FittedT2InformationAdapter, InformationFeatureBundle]
    ]
    | None = None,
) -> InformationConsumerPreparation:
    """Prepare one candidate cell, accepting caller-owned chunk caches.

    ``panel`` and ``auxiliary`` are optional so single-item callers retain a
    convenient default.  Chunk runners should validate/load each network once
    and pass both objects here; this avoids per-item CSV reads and file hashes.
    """

    if auxiliary is None:
        auxiliary = load_materialized_auxiliary(repo_root, network)
    if panel is None:
        panel = read_panel(repo_root, network)
    preparation = prepare_information_item(
        panel,
        auxiliary.daily_long,
        item,
        meteorology_lag_days=meteorology_lag_days,
        adapter_cache=adapter_cache,
        auxiliary_cache_identity=str(auxiliary.audit["daily_long_sha256"]),
    )
    return InformationConsumerPreparation(
        supported=preparation.supported,
        category=preparation.category,
        reason=preparation.reason,
        model_frame=preparation.model_frame,
        train_mask=preparation.train_mask,
        donor_columns=preparation.donor_columns,
        boundary_feature=preparation.boundary_feature,
        auxiliary_features=preparation.auxiliary_features,
        audit={**preparation.audit, "materialized_auxiliary": auxiliary.audit},
    )


def execute_materialized_information_item(
    repo_root: str | Path,
    network: OpenNetwork,
    item: WorkItem,
    *,
    meteorology_lag_days: int = 0,
    panel: pd.DataFrame | None = None,
    auxiliary: MaterializedAuxiliary | None = None,
    adapter_cache: MutableMapping[
        str, tuple[FittedT2InformationAdapter, InformationFeatureBundle]
    ]
    | None = None,
) -> dict[str, Any]:
    """Execute one non-formal candidate cell for synthetic/unit smoke use.

    This function is intentionally not called by the frozen v3 chunk runner.
    A formal result requires a new workload freeze whose item identity includes
    this integration contract and the auxiliary artifact hash.
    """

    began = perf_counter()
    if auxiliary is None:
        auxiliary = load_materialized_auxiliary(repo_root, network)
    if panel is None:
        panel = read_panel(repo_root, network)
    preparation = prepare_materialized_information_item(
        repo_root,
        network,
        item,
        meteorology_lag_days=meteorology_lag_days,
        panel=panel,
        auxiliary=auxiliary,
        adapter_cache=adapter_cache,
    )
    base = {
        **asdict(item),
        "source_v3_item_id": item.item_id,
        "source_v3_runner_contract_version": RUNNER_CONTRACT_VERSION,
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "available_information_condition": item.information_condition,
        "consumed_information": (
            preparation.audit.get("requested_information_groups", [])
            if preparation.supported
            else []
        ),
        "workload_category": preparation.category,
        "information_audit": preparation.audit,
        "purpose": "pipeline_verification_not_evidence",
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    if not preparation.supported:
        return {
            **base,
            "status": preparation.category,
            "reason": preparation.reason,
            "runtime_seconds": float(perf_counter() - began),
        }
    assert preparation.model_frame is not None
    assert preparation.train_mask is not None
    assert preparation.boundary_feature is not None
    start = int(item.start_index)
    stop = start + int(item.gap_length)
    truth = panel[item.target_station].iloc[start:stop].to_numpy(dtype=float)
    climatology = ClimatologyBaseline(target_col=item.target_station).fit(
        panel, dates=panel.index, train_mask=preparation.train_mask
    )
    climate = climatology.predict(panel, dates=panel.index).iloc[start:stop]
    climate_mae = float(np.mean(np.abs(climate.to_numpy(dtype=float) - truth)))
    feature_names = [
        *preparation.donor_columns,
        preparation.boundary_feature,
        *preparation.auxiliary_features,
    ]
    try:
        if item.model == "donor_regression":
            model = DonorRegressionBaseline(
                preparation.donor_columns,
                target_col=item.target_station,
                covariate_cols=[
                    preparation.boundary_feature,
                    *preparation.auxiliary_features,
                ],
            )
        elif item.model == "xgboost":
            if not XGBoostBaseline.is_available():
                return {
                    **base,
                    "status": "external_dependency",
                    "reason": "xgboost_not_installed",
                    "runtime_seconds": float(perf_counter() - began),
                }
            model = XGBoostBaseline(feature_names, target_col=item.target_station)
        else:  # pragma: no cover - guarded by preparation
            raise ValueError(f"unsupported extended-information model: {item.model}")
        model.fit(
            preparation.model_frame,
            dates=panel.index,
            train_mask=preparation.train_mask,
        )
        predicted = model.predict(
            preparation.model_frame,
            dates=panel.index,
        ).iloc[start:stop].to_numpy(dtype=float)
        valid = np.isfinite(predicted) & np.isfinite(truth)
        if not valid.any():
            raise ValueError("no finite candidate gap predictions")
        mae = float(np.mean(np.abs(predicted[valid] - truth[valid])))
        return json_safe(
            {
                **base,
                "status": "candidate_complete_not_formal",
                "reason": "",
                "implementation": f"{item.model}_B_D_MH_candidate_consumer",
                "n_scored": int(valid.sum()),
                "mae_deg_c": mae,
                "climatology_mae_deg_c": climate_mae,
                "achieved_skill": recoverability(mae, climate_mae),
                "prediction_sha256": _prediction_sha256(predicted),
                "runtime_seconds": float(perf_counter() - began),
            }
        )
    except (ImportError, KeyError, RuntimeError, ValueError, np.linalg.LinAlgError) as error:
        return {
            **base,
            "status": "failed",
            "reason": f"{type(error).__name__}: {error}",
            "runtime_seconds": float(perf_counter() - began),
        }


__all__ = [
    "AUXILIARY_ROOT",
    "INTEGRATION_CONTRACT_VERSION",
    "METEOROLOGY_LAG_ROSTER",
    "InformationConsumerPreparation",
    "MaterializedAuxiliary",
    "execute_materialized_information_item",
    "load_materialized_auxiliary",
    "prepare_information_item",
    "prepare_materialized_information_item",
]
