"""Fail-closed freeze and execution contract for the T2 v4 M/H workload.

Version 3 remains immutable: its items are used only as a deterministic source
grid.  V4 gives every source item a new identity.  Extended information cells
are expanded into three separately required meteorology-lag cells and bind the
legacy-NWIS v2 corpus plan plus the exact per-network auxiliary artifacts.

No formal workload may be constructed until all 67 frozen open networks have
terminal, integrity-valid v2 auxiliary bundles.  A bounded pilot can use a
single terminal network, but its manifest and results are explicitly pipeline
verification rather than evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    NETWORK_SCHEMA_VERSION as V2_NETWORK_SCHEMA_VERSION,
)
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    PLAN_SCHEMA_VERSION as V2_PLAN_SCHEMA_VERSION,
)
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    TERMINAL_STATUSES as V2_TERMINAL_STATUSES,
)
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    load_v2_corpus_plan,
    plan_as_dict,
)
from stream_recoverability.models.baselines import ClimatologyBaseline

from .t2_information_runner_integration import (
    INTEGRATION_CONTRACT_VERSION,
    METEOROLOGY_LAG_ROSTER,
    SUPPORTED_MODELS,
    V2_AUXILIARY_ROOT,
    execute_materialized_information_item,
    load_materialized_auxiliary_v2,
)
from .t2_recovery_benchmark import (
    EXTENDED_INFORMATION_CONDITIONS,
    RUNNER_CONTRACT_VERSION,
    OpenNetwork,
    WorkItem,
    _fit_cache_key,
    _prediction_sha256,
    _resolve_fit,
    _year_split,
    execute_item,
    iter_all_work_items,
    json_safe,
    read_panel,
)

V3_WORKLOAD_SCHEMA = "t2_v91_open_role_workload_v3"
V4_WORKLOAD_SCHEMA = "t2_v91_open_role_workload_v4"
V4_INDEX_DRAFT_SCHEMA = "t2_v91_open_role_workload_v4_index_draft_v1"
V4_PRE_SCORE_FREEZE_SCHEMA = "t2_v91_v4_pre_score_freeze_bundle_v1"
V4_RUNNER_CONTRACT_VERSION = "t2_v91_runner_v4_legacy_mh_lag_grid_v1"
V4_READINESS_SCHEMA = "t2_v91_open_role_workload_v4_readiness_v1"
V4_ITEM_INDEX_SCHEMA = "t2_v91_open_role_work_item_index_v4"
EXPECTED_NETWORK_COUNT = 67
EXPECTED_V3_WORK_ITEMS = 1_384_025
EXPECTED_V3_EXTENDED_WORK_ITEMS = 553_610
EXPECTED_V4_WORK_ITEMS = 2_491_245
ITEM_INDEX_ROW_GROUP_SIZE = 20_000
EXECUTION_CODE_INVENTORY_SCHEMA = "t2_v91_v4_execution_code_inventory_v1"
EXECUTION_CODE_PATHS = (
    "src/stream_recoverability/experiments/t2_recovery_benchmark.py",
    "src/stream_recoverability/experiments/t2_workload_v4.py",
    "src/stream_recoverability/experiments/t2_chunk_executor_v4.py",
    "src/stream_recoverability/experiments/t2_batch_orchestrator.py",
    "src/stream_recoverability/experiments/t2_cached_executor.py",
    "src/stream_recoverability/experiments/t2_information_runner_integration.py",
    "src/stream_recoverability/data/t2_information_adapters.py",
    "src/stream_recoverability/data/t2_information_corpus_acquisition.py",
    "src/stream_recoverability/data/t2_information_corpus_acquisition_v2.py",
    "src/stream_recoverability/models/baselines.py",
    "src/stream_recoverability/analysis/recoverability_spectrum.py",
    "src/stream_recoverability/experiments/t2_result_aggregation_v4.py",
    "src/stream_recoverability/experiments/t2_primary_aggregation_v2.py",
    "src/stream_recoverability/experiments/t4_t5_post_t2.py",
    "pyproject.toml",
    "environment.yml",
)

COVERAGE_SEMANTICS: dict[str, Any] = {
    "requested_roster": (
        "all_station_by_frozen_group_variables_required_no_channel_substitution"
    ),
    "train_min_days_per_feature": 365,
    "gap": "every_requested_feature_finite_on_every_gap_day",
    "missing_channel": "cell_data_ineligible_no_fill_no_drop",
    "adapter_standardization": "mean_population_sd_train_days_only",
    "meteorology_lag_roster": list(METEOROLOGY_LAG_ROSTER),
    "meteorology_lag_cell_semantics": (
        "all_three_reported_separately_no_heldout_selection"
    ),
}


class V4FreezeBlocked(ValueError):
    """Raised before a formal v4 workload or result can be created."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=16)
def _cached_sha256_file(path_text: str, size: int, mtime_ns: int) -> str:
    del size, mtime_ns
    return _sha256_file(Path(path_text))


def _stable_sha256_file(path: Path) -> str:
    stat = path.stat()
    return _cached_sha256_file(str(path), stat.st_size, stat.st_mtime_ns)


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        check=False,
    )


def build_committed_execution_inventory(repo_root: str | Path) -> dict[str, Any]:
    """Bind every scoring dependency to committed, HEAD-clean repository bytes."""

    repo = Path(repo_root).resolve()
    head = _git(repo, "rev-parse", "HEAD")
    if head.returncode != 0:
        raise V4FreezeBlocked("v4 execution-code freeze requires a Git HEAD")
    status = _git(repo, "status", "--porcelain", "--", *EXECUTION_CODE_PATHS)
    if status.returncode != 0 or status.stdout.strip():
        raise V4FreezeBlocked(
            "v4 execution-code paths must be committed and HEAD-clean"
        )
    records = []
    for relative in EXECUTION_CODE_PATHS:
        path = (repo / relative).resolve()
        try:
            path.relative_to(repo)
        except ValueError as error:  # pragma: no cover - constant inventory
            raise V4FreezeBlocked("v4 execution-code path escaped repository") from error
        if not path.is_file():
            raise V4FreezeBlocked(f"v4 execution-code path is absent: {relative}")
        committed = _git(repo, "rev-parse", f"HEAD:{relative}")
        worktree = _git(repo, "hash-object", relative)
        if (
            committed.returncode != 0
            or worktree.returncode != 0
            or committed.stdout.strip() != worktree.stdout.strip()
        ):
            raise V4FreezeBlocked(
                f"v4 execution-code path differs from HEAD: {relative}"
            )
        records.append(
            {
                "path": relative,
                "file_sha256": _sha256_file(path),
                "git_blob": committed.stdout.decode("ascii").strip(),
            }
        )
    inventory_sha = _canonical_sha(records)
    return {
        "manifest_schema": EXECUTION_CODE_INVENTORY_SCHEMA,
        "source_head_commit": head.stdout.decode("ascii").strip(),
        "paths": records,
        "path_roster": list(EXECUTION_CODE_PATHS),
        "inventory_sha256": inventory_sha,
        "all_paths_committed_unchanged": True,
    }


COVERAGE_SEMANTICS_SHA256 = _canonical_sha(COVERAGE_SEMANTICS)


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V4FreezeBlocked(f"cannot read v4 prerequisite {path}: {error}") from error
    if not isinstance(value, dict):
        raise V4FreezeBlocked(f"v4 prerequisite is not a mapping: {path}")
    return value


def _validated_v3_contract(v3: Mapping[str, Any]) -> tuple[int, str, int]:
    tier = v3.get("tier_1")
    if not isinstance(tier, Mapping):
        raise V4FreezeBlocked("source v3 workload lacks tier_1")
    try:
        n_items = int(tier.get("n_work_items", -1))
    except (TypeError, ValueError) as error:
        raise V4FreezeBlocked("source v3 item count is invalid") from error
    identity_sha = str(tier.get("work_item_identity_sha256", ""))
    counts = tier.get("counts_by_role_model_information")
    if not isinstance(counts, Mapping):
        raise V4FreezeBlocked("source v3 workload lacks cell counts")
    normalized_counts = {str(key): int(value) for key, value in counts.items()}
    count_total = sum(normalized_counts.values())
    extended = sum(
        value
        for key, value in normalized_counts.items()
        if key.rsplit("|", 1)[-1] in EXTENDED_INFORMATION_CONDITIONS
    )
    if (
        n_items != EXPECTED_V3_WORK_ITEMS
        or count_total != EXPECTED_V3_WORK_ITEMS
        or extended != EXPECTED_V3_EXTENDED_WORK_ITEMS
        or len(identity_sha) != 64
    ):
        raise V4FreezeBlocked(
            "source v3 count/hash contract differs from the frozen 1,384,025-item grid"
        )
    return n_items, identity_sha, extended


def _safe_artifact(
    repo: Path,
    network_dir: Path,
    artifacts: Mapping[str, Any],
    key: str,
) -> tuple[str, str]:
    record = artifacts.get(key)
    if not isinstance(record, Mapping):
        raise V4FreezeBlocked(f"v2 network manifest lacks artifact: {key}")
    path = repo / str(record.get("path", ""))
    try:
        path.resolve(strict=True).relative_to(network_dir.resolve(strict=True))
    except (FileNotFoundError, ValueError) as error:
        raise V4FreezeBlocked(
            f"v2 artifact is absent or escaped its network: {key}"
        ) from error
    sha = str(record.get("sha256", ""))
    if len(sha) != 64 or _sha256_file(path) != sha:
        raise V4FreezeBlocked(f"v2 artifact SHA mismatch: {key}")
    return str(path.relative_to(repo)), sha


@dataclass(frozen=True)
class V2NetworkBinding:
    network_id: str
    role: str
    network_manifest_schema: str
    network_plan_sha256: str
    network_manifest_path: str
    network_manifest_sha256: str
    daily_long_sha256: str
    coverage_sha256: str
    adapter_schema_sha256: str
    materialization_status: str

    def identity(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class V4Prerequisites:
    ready: bool
    corpus_plan_path: str
    corpus_plan_file_sha256: str
    corpus_plan_sha256: str
    split_sha256: str
    n_networks_expected: int
    n_networks_terminal: int
    missing_network_ids: tuple[str, ...]
    invalid_networks: Mapping[str, str]
    bindings: Mapping[str, V2NetworkBinding]


@dataclass(frozen=True)
class V4WorkItem:
    ordinal: int
    item_id: str
    source_v3_item: WorkItem
    meteorology_lag_days: int | None
    auxiliary_corpus_plan_sha256: str
    auxiliary_corpus_plan_file_sha256: str
    auxiliary_binding: V2NetworkBinding
    coverage_semantics_sha256: str = COVERAGE_SEMANTICS_SHA256

    @property
    def network_id(self) -> str:
        return self.source_v3_item.network_id

    def runner_item(self) -> WorkItem:
        return replace(self.source_v3_item, ordinal=self.ordinal, item_id=self.item_id)


def audit_v4_prerequisites(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    *,
    allow_legacy_pipeline_smoke: bool = False,
) -> V4Prerequisites:
    """Validate the v2 plan and terminal artifact identities without outcomes."""

    repo = Path(repo_root).resolve()
    auxiliary_root = (repo / V2_AUXILIARY_ROOT).resolve()
    if "sealed" in str(auxiliary_root).lower():
        raise V4FreezeBlocked("v4 auxiliary root must not be sealed")
    plan_path = auxiliary_root / "corpus_request_plan.json"
    plan = _read_mapping(plan_path)
    current_plan = plan_as_dict(load_v2_corpus_plan(repo))
    plan_schema = str(plan.get("manifest_schema", ""))
    schema_accepted = plan_schema == V2_PLAN_SCHEMA_VERSION or (
        allow_legacy_pipeline_smoke
        and plan_schema.startswith("t2_v91_open_role_mh_corpus_request_plan_v2")
    )
    if (
        not schema_accepted
        or int(plan.get("n_networks", -1)) != EXPECTED_NETWORK_COUNT
        or plan.get("sealed_paths_traversed") is not False
        or plan.get("temperature_columns_read") != []
        or plan.get("performance_metrics_computed") is not False
        or plan.get("v1_ogc_root_read_or_mutated") is not False
    ):
        raise V4FreezeBlocked("v2 corpus plan violates the frozen open-only contract")
    if not allow_legacy_pipeline_smoke and _canonical_json(plan) != _canonical_json(
        current_plan
    ):
        raise V4FreezeBlocked(
            "v2 corpus plan differs from the deterministic current acquisition plan"
        )
    if len(str(plan.get("plan_sha256", ""))) != 64:
        raise V4FreezeBlocked("v2 corpus plan lacks a valid self SHA-256")
    plan_without_sha = dict(plan)
    declared_plan_sha = str(plan_without_sha.pop("plan_sha256"))
    if _canonical_sha(plan_without_sha) != declared_plan_sha:
        raise V4FreezeBlocked("v2 corpus plan self SHA-256 mismatch")
    expected = [(network.network_id, network.role) for network in networks]
    planned = [
        (str(row.get("network_id")), str(row.get("role")))
        for row in (plan.get("networks") or [])
    ]
    if len(networks) != EXPECTED_NETWORK_COUNT or planned != expected:
        raise V4FreezeBlocked("v2 plan roster differs from the 67-network v3 roster")

    plan_by_id = {str(row["network_id"]): row for row in (plan.get("networks") or [])}
    bindings: dict[str, V2NetworkBinding] = {}
    invalid: dict[str, str] = {}
    missing: list[str] = []
    for network in networks:
        directory = auxiliary_root / network.role / "networks" / network.network_id
        manifest_path = directory / "network_manifest.json"
        if not manifest_path.is_file():
            missing.append(network.network_id)
            continue
        try:
            manifest = _read_mapping(manifest_path)
            manifest_schema = str(manifest.get("manifest_schema"))
            schema_accepted = manifest_schema == V2_NETWORK_SCHEMA_VERSION or (
                allow_legacy_pipeline_smoke
                and manifest_schema == "t2_v91_open_role_mh_network_acquisition_v2"
            )
            planned_network_sha = str(
                plan_by_id[network.network_id]["network_plan_sha256"]
            )
            if (
                not schema_accepted
                or manifest.get("status") not in V2_TERMINAL_STATUSES
                or manifest.get("acquisition_terminal") is not True
                or manifest.get("network_id") != network.network_id
                or manifest.get("role") != network.role
                or manifest.get("network_plan_sha256") != planned_network_sha
                or manifest.get("split_sha256") != plan.get("split_sha256")
                or manifest.get("temperature_columns_read") != []
                or manifest.get("sealed_paths_traversed") is not False
                or manifest.get("sealed_temperature_records_read") is not False
                or manifest.get("performance_metrics_computed") is not False
                or manifest.get("v1_ogc_root_read_or_mutated") is not False
            ):
                raise V4FreezeBlocked("terminal manifest contract mismatch")
            artifacts = manifest.get("artifacts")
            if not isinstance(artifacts, Mapping):
                raise V4FreezeBlocked("network artifacts are not a mapping")
            _, daily_sha = _safe_artifact(
                repo, directory, artifacts, "daily_long_auxiliary"
            )
            _, coverage_sha = _safe_artifact(repo, directory, artifacts, "coverage")
            _, schema_sha = _safe_artifact(repo, directory, artifacts, "adapter_schema")
            bindings[network.network_id] = V2NetworkBinding(
                network_id=network.network_id,
                role=network.role,
                network_manifest_schema=manifest_schema,
                network_plan_sha256=planned_network_sha,
                network_manifest_path=str(manifest_path.relative_to(repo)),
                network_manifest_sha256=_sha256_file(manifest_path),
                daily_long_sha256=daily_sha,
                coverage_sha256=coverage_sha,
                adapter_schema_sha256=schema_sha,
                materialization_status=str(manifest["status"]),
            )
        except (KeyError, OSError, TypeError, ValueError, V4FreezeBlocked) as error:
            invalid[network.network_id] = str(error)

    ready = (
        len(bindings) == EXPECTED_NETWORK_COUNT
        and not missing
        and not invalid
        and all(
            binding.network_manifest_schema == V2_NETWORK_SCHEMA_VERSION
            for binding in bindings.values()
        )
    )
    return V4Prerequisites(
        ready=ready,
        corpus_plan_path=str(plan_path.relative_to(repo)),
        corpus_plan_file_sha256=_sha256_file(plan_path),
        corpus_plan_sha256=str(plan["plan_sha256"]),
        split_sha256=str(plan["split_sha256"]),
        n_networks_expected=EXPECTED_NETWORK_COUNT,
        n_networks_terminal=len(bindings),
        missing_network_ids=tuple(missing),
        invalid_networks=dict(sorted(invalid.items())),
        bindings=bindings,
    )


def build_v4_readiness_manifest(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    *,
    source_v3_workload_path: str | Path,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    v3_path = Path(source_v3_workload_path).resolve()
    v3 = _read_mapping(v3_path)
    if (
        v3.get("manifest_schema") != V3_WORKLOAD_SCHEMA
        or v3.get("runner_contract_version") != RUNNER_CONTRACT_VERSION
        or v3.get("sealed_temperature_records_read") is not False
        or v3.get("network_ids") != [network.network_id for network in networks]
        or (v3.get("input_inventory") or {}).get("sealed_input_roots_allowed") != []
    ):
        raise V4FreezeBlocked("source v3 workload contract mismatch")
    v3_n_items, v3_identity_sha, v3_extended_items = _validated_v3_contract(v3)
    try:
        prerequisites = audit_v4_prerequisites(repo, networks)
    except V4FreezeBlocked as error:
        auxiliary_root = (repo / V2_AUXILIARY_ROOT).resolve()
        plan_path = auxiliary_root / "corpus_request_plan.json"
        plan = _read_mapping(plan_path)
        prerequisites = V4Prerequisites(
            ready=False,
            corpus_plan_path=str(plan_path.relative_to(repo)),
            corpus_plan_file_sha256=_sha256_file(plan_path),
            corpus_plan_sha256=str(plan.get("plan_sha256", "")),
            split_sha256=str(plan.get("split_sha256", "")),
            n_networks_expected=EXPECTED_NETWORK_COUNT,
            n_networks_terminal=0,
            missing_network_ids=tuple(network.network_id for network in networks),
            invalid_networks={"__corpus_plan__": str(error)},
            bindings={},
        )
    execution_blockers = []
    if not prerequisites.ready:
        execution_blockers.append(
            f"v2_auxiliary_terminal_{prerequisites.n_networks_terminal}_of_"
            f"{prerequisites.n_networks_expected}"
        )
    evidence_blockers = [
        "n_open_networks_67_lt_100_network_interval_floor",
        "complete_v4_result_set_missing",
    ]
    return {
        "manifest_schema": V4_READINESS_SCHEMA,
        "status": "ready_for_formal_v4_freeze"
        if prerequisites.ready
        else "blocked_fail_closed",
        "execution_readiness": (
            "ready_for_formal_v4_freeze"
            if prerequisites.ready
            else "blocked_fail_closed"
        ),
        "evidence_readiness": "blocked_fail_closed",
        "network_inference_status": "withheld_n_lt_100_network_interval",
        "passed": False,
        "purpose": "pipeline_readiness_not_evidence",
        "formal_evidence": False,
        "formal_workload_generated": False,
        "formal_result_generated": False,
        "blockers": execution_blockers,
        "execution_blockers": execution_blockers,
        "evidence_blockers": evidence_blockers,
        "source_v3_workload_path": str(v3_path.relative_to(repo)),
        "source_v3_workload_sha256": _sha256_file(v3_path),
        "source_v3_n_work_items": v3_n_items,
        "source_v3_extended_work_items": v3_extended_items,
        "source_v3_work_item_identity_sha256": v3_identity_sha,
        "expected_v4_n_work_items": EXPECTED_V4_WORK_ITEMS,
        "source_v3_remains_immutable": True,
        "v4_runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "meteorology_lag_roster": list(METEOROLOGY_LAG_ROSTER),
        "all_meteorology_lag_cells_required": True,
        "coverage_semantics": COVERAGE_SEMANTICS,
        "coverage_semantics_sha256": COVERAGE_SEMANTICS_SHA256,
        "auxiliary": {
            "source": "legacy_nwis_v2",
            "corpus_plan_path": prerequisites.corpus_plan_path,
            "corpus_plan_file_sha256": prerequisites.corpus_plan_file_sha256,
            "corpus_plan_sha256": prerequisites.corpus_plan_sha256,
            "split_sha256": prerequisites.split_sha256,
            "n_networks_expected": prerequisites.n_networks_expected,
            "n_networks_terminal": prerequisites.n_networks_terminal,
            "missing_network_ids": list(prerequisites.missing_network_ids),
            "invalid_networks": dict(prerequisites.invalid_networks),
        },
        "model_information_contract": {
            "extended_executable_models": list(SUPPORTED_MODELS),
            "extended_reference_models": ["climatology"],
            "other_extended_models": ["pchip_or_linear", "kalman"],
            "other_extended_status": "structural_not_applicable",
        },
        "batch_orchestration": {
            "contract_spec": "configs/t2_workload_v4_contract.json",
            "executor_adapter": "t2_v91_chunk_executor_v4",
            "status": (
                "ready_after_formal_freeze"
                if prerequisites.ready
                else "blocked_until_formal_freeze"
            ),
        },
        "temperature_columns_read": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "network_interval_reported": False,
    }


def _v4_identity(
    source: WorkItem,
    *,
    lag: int | None,
    prerequisites: V4Prerequisites,
    binding: V2NetworkBinding,
) -> dict[str, Any]:
    return {
        "source_v3_item_id": source.item_id,
        "source_v3_runner_contract_version": RUNNER_CONTRACT_VERSION,
        "v4_runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "auxiliary_source": "legacy_nwis_v2",
        "auxiliary_corpus_plan_sha256": prerequisites.corpus_plan_sha256,
        "auxiliary_corpus_plan_file_sha256": prerequisites.corpus_plan_file_sha256,
        "auxiliary_network_binding": binding.identity(),
        "information_condition": source.information_condition,
        "meteorology_lag_days": lag,
        "coverage_semantics_sha256": COVERAGE_SEMANTICS_SHA256,
    }


def iter_v4_work_items(
    source_items: Iterable[WorkItem],
    prerequisites: V4Prerequisites,
    *,
    require_full_corpus: bool = True,
) -> Iterable[V4WorkItem]:
    """Re-key a v3 source stream and expand each extended item by lag."""

    if require_full_corpus and not prerequisites.ready:
        raise V4FreezeBlocked(
            f"formal v4 freeze requires 67 terminal networks; found "
            f"{prerequisites.n_networks_terminal}"
        )
    ordinal = 0
    for source in source_items:
        binding = prerequisites.bindings.get(source.network_id)
        if binding is None:
            raise V4FreezeBlocked(
                f"source item has no terminal v2 auxiliary binding: {source.network_id}"
            )
        lags: tuple[int | None, ...] = (
            tuple(METEOROLOGY_LAG_ROSTER)
            if source.information_condition in EXTENDED_INFORMATION_CONDITIONS
            else (None,)
        )
        for lag in lags:
            identity = _v4_identity(
                source, lag=lag, prerequisites=prerequisites, binding=binding
            )
            yield V4WorkItem(
                ordinal=ordinal,
                item_id=_canonical_sha(identity)[:24],
                source_v3_item=source,
                meteorology_lag_days=lag,
                auxiliary_corpus_plan_sha256=prerequisites.corpus_plan_sha256,
                auxiliary_corpus_plan_file_sha256=prerequisites.corpus_plan_file_sha256,
                auxiliary_binding=binding,
            )
            ordinal += 1


def _index_row(item: V4WorkItem) -> dict[str, Any]:
    return {
        "ordinal": int(item.ordinal),
        "item_id": item.item_id,
        "source_v3_ordinal": int(item.source_v3_item.ordinal),
        "source_v3_item_id": item.source_v3_item.item_id,
        "network_id": item.network_id,
        "meteorology_lag_days": (
            "none"
            if item.meteorology_lag_days is None
            else str(int(item.meteorology_lag_days))
        ),
        "source_item_json": _canonical_json(json_safe(asdict(item.source_v3_item))),
    }


def _write_v4_item_index(
    path: Path,
    source_items: Iterable[WorkItem],
    prerequisites: V4Prerequisites,
    *,
    expected_v3_identity_sha256: str,
) -> dict[str, Any]:
    """Write the complete random-access v4 index while proving the v3 stream."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    source_digest = hashlib.sha256()
    v4_digest = hashlib.sha256()
    counts = Counter()
    lag_counts = Counter()
    source_count = 0
    source_extended = 0
    v4_count = 0
    batch: list[dict[str, Any]] = []
    writer: pq.ParquetWriter | None = None

    def flush() -> None:
        nonlocal writer
        if not batch:
            return
        table = pa.Table.from_pylist(batch)
        if writer is None:
            writer = pq.ParquetWriter(
                path,
                table.schema,
                compression="zstd",
                use_dictionary=True,
            )
        writer.write_table(table, row_group_size=ITEM_INDEX_ROW_GROUP_SIZE)
        batch.clear()

    try:
        for source in source_items:
            if int(source.ordinal) != source_count:
                raise V4FreezeBlocked(
                    "source v3 ordinals are not exactly contiguous from zero"
                )
            source_digest.update(source.item_id.encode("utf-8"))
            source_digest.update(b"\n")
            source_count += 1
            if source.information_condition in EXTENDED_INFORMATION_CONDITIONS:
                source_extended += 1
            for item in iter_v4_work_items(
                (source,), prerequisites, require_full_corpus=True
            ):
                # A one-source iterator starts at zero; assign the one global
                # namespace before hashing or serializing it.
                item = replace(item, ordinal=v4_count)
                v4_digest.update(item.item_id.encode("utf-8"))
                v4_digest.update(b"\n")
                counts[(source.model, source.information_condition)] += 1
                lag_counts[
                    (
                        source.model,
                        source.information_condition,
                        (
                            "none"
                            if item.meteorology_lag_days is None
                            else str(item.meteorology_lag_days)
                        ),
                    )
                ] += 1
                batch.append(_index_row(item))
                v4_count += 1
                if len(batch) >= ITEM_INDEX_ROW_GROUP_SIZE:
                    flush()
        flush()
    finally:
        if writer is not None:
            writer.close()
    if (
        source_count != EXPECTED_V3_WORK_ITEMS
        or source_extended != EXPECTED_V3_EXTENDED_WORK_ITEMS
        or source_digest.hexdigest() != expected_v3_identity_sha256
        or v4_count != EXPECTED_V4_WORK_ITEMS
    ):
        if path.exists():
            path.unlink()
        raise V4FreezeBlocked("v3-to-v4 item stream count/identity verification failed")
    return {
        "manifest_schema": V4_ITEM_INDEX_SCHEMA,
        "format": "parquet",
        "file_sha256": _sha256_file(path),
        "n_rows": v4_count,
        "source_v3_n_rows": source_count,
        "source_v3_extended_rows": source_extended,
        "source_v3_item_identity_sha256": source_digest.hexdigest(),
        "work_item_identity_sha256": v4_digest.hexdigest(),
        "row_group_size": ITEM_INDEX_ROW_GROUP_SIZE,
        "columns": [
            "ordinal",
            "item_id",
            "source_v3_ordinal",
            "source_v3_item_id",
            "network_id",
            "meteorology_lag_days",
            "source_item_json",
        ],
        "counts_by_model_information": {
            "|".join(key): value for key, value in sorted(counts.items())
        },
        "counts_by_model_information_lag": {
            "|".join(key): value for key, value in sorted(lag_counts.items())
        },
    }


def load_v4_index_slice(
    repo_root: str | Path,
    workload: Mapping[str, Any],
    prerequisites: V4Prerequisites,
    *,
    start: int,
    end: int,
) -> list[V4WorkItem]:
    """Read and revalidate one ordinal range without rebuilding prior items."""

    import pandas as pd

    repo = Path(repo_root).resolve()
    record = workload.get("item_index")
    if not isinstance(record, Mapping):
        raise V4FreezeBlocked("v4 workload lacks its frozen item index")
    if (
        record.get("manifest_schema") != V4_ITEM_INDEX_SCHEMA
        or int(record.get("n_rows", -1)) != EXPECTED_V4_WORK_ITEMS
        or int(record.get("source_v3_n_rows", -1)) != EXPECTED_V3_WORK_ITEMS
        or int(record.get("source_v3_extended_rows", -1))
        != EXPECTED_V3_EXTENDED_WORK_ITEMS
        or record.get("work_item_identity_sha256")
        != workload.get("work_item_identity_sha256")
        or record.get("source_v3_item_identity_sha256")
        != workload.get("source_v3_work_item_identity_sha256")
    ):
        raise V4FreezeBlocked("v4 item index metadata differs from workload freeze")
    path = (repo / str(record.get("path", ""))).resolve()
    try:
        path.relative_to(repo)
    except ValueError as error:
        raise V4FreezeBlocked("v4 item index escaped the repository") from error
    if any("sealed" in part.lower() for part in path.parts) or not path.is_file():
        raise V4FreezeBlocked("v4 item index is absent or unsafe")
    if _stable_sha256_file(path) != record.get("file_sha256"):
        raise V4FreezeBlocked("v4 item index SHA-256 mismatch")
    frame = pd.read_parquet(
        path,
        filters=[("ordinal", ">=", int(start)), ("ordinal", "<", int(end))],
    ).sort_values("ordinal", kind="stable")
    if len(frame) != end - start or frame["ordinal"].astype(int).tolist() != list(
        range(start, end)
    ):
        raise V4FreezeBlocked("v4 item index range is incomplete")
    items: list[V4WorkItem] = []
    for row in frame.to_dict(orient="records"):
        source_value = json.loads(str(row["source_item_json"]))
        source = WorkItem(**source_value)
        if (
            int(row["source_v3_ordinal"]) != source.ordinal
            or str(row["source_v3_item_id"]) != source.item_id
            or str(row["network_id"]) != source.network_id
        ):
            raise V4FreezeBlocked("v4 item index source identity mismatch")
        binding = prerequisites.bindings.get(source.network_id)
        if binding is None:
            raise V4FreezeBlocked("v4 indexed item has no current auxiliary binding")
        lag_label = str(row["meteorology_lag_days"])
        lag = None if lag_label == "none" else int(lag_label)
        identity = _v4_identity(
            source, lag=lag, prerequisites=prerequisites, binding=binding
        )
        item_id = _canonical_sha(identity)[:24]
        if item_id != str(row["item_id"]):
            raise V4FreezeBlocked("v4 indexed item identity differs from frozen inputs")
        items.append(
            V4WorkItem(
                ordinal=int(row["ordinal"]),
                item_id=item_id,
                source_v3_item=source,
                meteorology_lag_days=lag,
                auxiliary_corpus_plan_sha256=prerequisites.corpus_plan_sha256,
                auxiliary_corpus_plan_file_sha256=(
                    prerequisites.corpus_plan_file_sha256
                ),
                auxiliary_binding=binding,
            )
        )
    return items


def build_v4_workload_manifest(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    *,
    source_v3_workload_path: str | Path,
    source_items: Iterable[WorkItem],
    item_index_write_path: str | Path,
    item_index_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the create-once index draft used by the pre-score audit.

    This object is deliberately not executable.  The final workload is made
    only after an independent pre-score bundle binds the draft and its index.
    """

    repo = Path(repo_root).resolve()
    v3_path = Path(source_v3_workload_path).resolve()
    build_v4_readiness_manifest(repo, networks, source_v3_workload_path=v3_path)
    prerequisites = audit_v4_prerequisites(repo, networks)
    if not prerequisites.ready:
        raise V4FreezeBlocked(
            "formal v4 workload forbidden before v2 reaches 67/67 terminal"
        )
    source_v3 = _read_mapping(v3_path)
    _, source_identity_sha, _ = _validated_v3_contract(source_v3)
    index_write_path = Path(item_index_write_path).resolve()
    index_manifest_path = Path(item_index_manifest_path or index_write_path).resolve()
    try:
        index_manifest_path.relative_to(repo)
    except ValueError as error:
        raise V4FreezeBlocked(
            "v4 item index must remain inside the repository"
        ) from error
    index = _write_v4_item_index(
        index_write_path,
        source_items,
        prerequisites,
        expected_v3_identity_sha256=source_identity_sha,
    )
    index["path"] = str(index_manifest_path.relative_to(repo))
    input_inventory = source_v3.get("input_inventory")
    if not isinstance(input_inventory, Mapping):
        raise V4FreezeBlocked("source v3 workload lacks its input inventory")
    auxiliary_bindings = {
        key: value.identity() for key, value in prerequisites.bindings.items()
    }
    return {
        "manifest_schema": V4_INDEX_DRAFT_SCHEMA,
        "execution_allowed": False,
        "final_workload_required": True,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "source_v3_workload_path": str(v3_path.relative_to(repo)),
        "source_v3_workload_sha256": _sha256_file(v3_path),
        "source_v3_work_item_identity_sha256": source_identity_sha,
        "source_v3_remains_immutable": True,
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "auxiliary_source": "legacy_nwis_v2",
        "auxiliary_corpus_plan_path": prerequisites.corpus_plan_path,
        "auxiliary_corpus_plan_file_sha256": prerequisites.corpus_plan_file_sha256,
        "auxiliary_corpus_plan_sha256": prerequisites.corpus_plan_sha256,
        "auxiliary_network_bindings": auxiliary_bindings,
        "auxiliary_network_bindings_sha256": _canonical_sha(auxiliary_bindings),
        "input_inventory": dict(input_inventory),
        "input_sha256_by_network": {
            network.network_id: network.wide_sha256 for network in networks
        },
        "input_sha256_by_network_sha256": _canonical_sha(
            {network.network_id: network.wide_sha256 for network in networks}
        ),
        "coverage_semantics": COVERAGE_SEMANTICS,
        "coverage_semantics_sha256": COVERAGE_SEMANTICS_SHA256,
        "meteorology_lag_roster": list(METEOROLOGY_LAG_ROSTER),
        "extended_item_lag_multiplier": len(METEOROLOGY_LAG_ROSTER),
        "extended_executable_models": list(SUPPORTED_MODELS),
        "extended_reference_models": ["climatology"],
        "other_extended_models": ["pchip_or_linear", "kalman"],
        "other_extended_status": "structural_not_applicable",
        "batch_orchestration_contract_spec": "configs/t2_workload_v4_contract.json",
        "n_networks": len(networks),
        "network_ids": [network.network_id for network in networks],
        "n_work_items": EXPECTED_V4_WORK_ITEMS,
        "work_item_identity_sha256": index["work_item_identity_sha256"],
        "item_index": index,
        "counts_by_model_information": index["counts_by_model_information"],
        "counts_by_model_information_lag": index["counts_by_model_information_lag"],
        "purpose": "create_once_item_index_draft_for_pre_score_freeze",
        "formal_evidence": False,
        "sealed_input_roots_allowed": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "passed": False,
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_once_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        existing = path.read_bytes()
        if existing != payload:
            raise V4FreezeBlocked(
                "formal v4 workload is create-once and already differs"
            )
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def freeze_v4_workload(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    *,
    source_v3_workload_path: str | Path,
    source_items: Iterable[WorkItem],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create the immutable item-index draft; never create an executable workload."""

    repo = Path(repo_root).resolve()
    output = Path(output_dir).resolve()
    workload_path = output / "index_draft_manifest.json"
    index_path = output / "item_index.parquet"
    if any("sealed" in part.lower() for part in output.parts):
        raise V4FreezeBlocked("formal v4 freeze refuses a sealed path")
    output.mkdir(parents=True, exist_ok=True)
    if workload_path.exists():
        workload = _read_mapping(workload_path)
        record = workload.get("item_index")
        prerequisites = audit_v4_prerequisites(repo, networks)
        bindings = {
            key: value.identity() for key, value in prerequisites.bindings.items()
        }
        if (
            workload.get("manifest_schema") != V4_INDEX_DRAFT_SCHEMA
            or int(workload.get("n_work_items", -1)) != EXPECTED_V4_WORK_ITEMS
            or not isinstance(record, Mapping)
            or (repo / str(record.get("path", ""))).resolve() != index_path
            or not index_path.is_file()
            or _sha256_file(index_path) != record.get("file_sha256")
            or workload.get("auxiliary_corpus_plan_sha256")
            != prerequisites.corpus_plan_sha256
            or workload.get("auxiliary_corpus_plan_file_sha256")
            != prerequisites.corpus_plan_file_sha256
            or workload.get("auxiliary_network_bindings") != bindings
            or _sha256_file(Path(source_v3_workload_path).resolve())
            != workload.get("source_v3_workload_sha256")
        ):
            raise V4FreezeBlocked("existing formal v4 freeze failed custody validation")
        return workload

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".item_index.", suffix=".parquet.tmp", dir=output
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        workload = build_v4_workload_manifest(
            repo,
            networks,
            source_v3_workload_path=source_v3_workload_path,
            source_items=source_items,
            item_index_write_path=temporary,
            item_index_manifest_path=index_path,
        )
        expected_index_sha = str(workload["item_index"]["file_sha256"])
        if index_path.exists():
            if _sha256_file(index_path) != expected_index_sha:
                raise V4FreezeBlocked(
                    "orphan v4 item index differs from candidate freeze"
                )
        else:
            try:
                os.link(temporary, index_path)
            except FileExistsError:
                if _sha256_file(index_path) != expected_index_sha:
                    raise V4FreezeBlocked("concurrent v4 item index differs")
            _fsync_directory(output)
        _create_once_json(workload_path, workload)
    finally:
        if temporary.exists():
            temporary.unlink()
    return workload


def _bound_file_record(
    repo: Path, manifest_path: Path, record: Mapping[str, Any], *, name: str
) -> dict[str, Any]:
    """Resolve and verify one repository-local SHA-bound pre-score artifact."""

    raw = Path(str(record.get("path", "")))
    path = (
        raw.resolve() if raw.is_absolute() else (manifest_path.parent / raw).resolve()
    )
    try:
        relative = path.relative_to(repo)
    except ValueError as error:
        raise V4FreezeBlocked(f"{name} escaped the repository") from error
    if any("sealed" in part.lower() for part in path.parts) or not path.is_file():
        raise V4FreezeBlocked(f"{name} is absent or unsafe")
    sha = _sha256_file(path)
    if sha != record.get("sha256"):
        raise V4FreezeBlocked(f"{name} SHA-256 mismatch")
    return {**dict(record), "path": str(relative), "sha256": sha}


def finalize_v4_workload(
    repo_root: str | Path,
    *,
    index_draft_manifest_path: str | Path,
    pre_score_freeze_manifest_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Bind the draft/index and all pre-score bytes into the executable workload."""

    repo = Path(repo_root).resolve()
    draft_path = Path(index_draft_manifest_path).resolve()
    freeze_path = Path(pre_score_freeze_manifest_path).resolve()
    output = Path(output_path).resolve()
    for path in (draft_path, freeze_path, output):
        try:
            path.relative_to(repo)
        except ValueError as error:
            raise V4FreezeBlocked(
                "v4 final freeze must remain inside the repository"
            ) from error
        if any("sealed" in part.lower() for part in path.parts):
            raise V4FreezeBlocked("v4 final freeze refuses sealed paths")
    draft = _read_mapping(draft_path)
    freeze = _read_mapping(freeze_path)
    execution_inventory = build_committed_execution_inventory(repo)
    if (
        draft.get("manifest_schema") != V4_INDEX_DRAFT_SCHEMA
        or draft.get("execution_allowed") is not False
        or int(draft.get("n_work_items", -1)) != EXPECTED_V4_WORK_ITEMS
    ):
        raise V4FreezeBlocked(
            "final workload requires a valid non-executable index draft"
        )
    if (
        freeze.get("manifest_schema") != V4_PRE_SCORE_FREEZE_SCHEMA
        or freeze.get("status") != "complete_outcome_blind_pre_score_freeze"
        or freeze.get("index_draft_manifest_sha256") != _sha256_file(draft_path)
        or freeze.get("item_index_file_sha256")
        != (draft.get("item_index") or {}).get("file_sha256")
        or freeze.get("sealed_paths_traversed") is not False
        or freeze.get("sealed_temperature_records_read") is not False
        or freeze.get("v4_results_read") is not False
        or freeze.get("selection_uses_outcomes") is not False
        or freeze.get("achieved_skill_read") is not False
        or freeze.get("base_lattice_status") != "frozen_before_v4_scoring"
    ):
        raise V4FreezeBlocked("pre-score freeze bundle does not bind the index draft")
    sensitivity_statuses = freeze.get("sensitivity_lattice_statuses")
    sensitivity_records = freeze.get("sensitivity_lattices")
    if (
        not isinstance(sensitivity_statuses, Mapping)
        or set(sensitivity_statuses) != {"M", "M_H"}
        or any(
            status not in {"ready", "blocked_insufficient_pre_score_support"}
            for status in sensitivity_statuses.values()
        )
        or not isinstance(sensitivity_records, Mapping)
        or set(sensitivity_records) != {"M", "M_H"}
    ):
        raise V4FreezeBlocked("pre-score freeze requires exact M and M_H sensitivities")
    required_records = (
        "eligibility_manifest",
        "eligibility_table",
        "feasibility_census",
        "exhaustive_item_ledger",
        "base_lattice_manifest",
        "base_lattice",
        "predictor_manifest",
        "predictor_table",
    )
    bound: dict[str, Any] = {}
    for name in required_records:
        record = freeze.get(name)
        if not isinstance(record, Mapping):
            raise V4FreezeBlocked(f"pre-score freeze omits {name}")
        bound[name] = _bound_file_record(repo, freeze_path, record, name=name)
    sensitivity = {
        str(key): _bound_file_record(
            repo, freeze_path, value, name=f"sensitivity_{key}"
        )
        for key, value in sensitivity_records.items()
        if isinstance(value, Mapping)
    }
    if set(sensitivity) != {"M", "M_H"}:
        raise V4FreezeBlocked("pre-score sensitivity lattice records are invalid")
    final = {
        **draft,
        "manifest_schema": V4_WORKLOAD_SCHEMA,
        "execution_allowed": True,
        "final_workload_required": False,
        "index_draft_manifest": {
            "path": str(draft_path.relative_to(repo)),
            "sha256": _sha256_file(draft_path),
        },
        "pre_score_freeze": {
            "manifest_schema": V4_PRE_SCORE_FREEZE_SCHEMA,
            "path": str(freeze_path.relative_to(repo)),
            "sha256": _sha256_file(freeze_path),
            "artifacts": bound,
            "sensitivity_lattices": sensitivity,
        },
        "execution_code_inventory": execution_inventory,
        "purpose": "formal_workload_bound_to_committed_pre_score_freeze",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _create_once_json(output, final)
    return final


def _execute_extended_climatology_reference(
    repo_root: str | Path,
    network: OpenNetwork,
    item: V4WorkItem,
    *,
    panel: Any | None,
    base_execution_cache: Any | None,
) -> dict[str, Any]:
    """Execute a v4 extended-condition reference without consulting v3 routing."""

    source = item.source_v3_item
    runner_item = item.runner_item()
    base = {
        **asdict(runner_item),
        "input_sha256": network.wide_sha256,
        "available_information_condition": source.information_condition,
        "consumed_information": [],
        "information_condition_result": False,
        "workload_category": "reference",
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    if item.meteorology_lag_days not in METEOROLOGY_LAG_ROSTER:
        raise V4FreezeBlocked(
            "extended climatology item lacks a frozen meteorology lag"
        )
    if source.start_index < 0:
        reason = (
            "fewer_than_frozen_common_bd_placements_are_data_eligible"
            if source.geometry == "artificial_stress"
            else "frozen_geometry_truth_window_unavailable_without_reselection"
        )
        return {**base, "status": "data_ineligible", "reason": reason}
    if panel is None:
        panel_loader = getattr(base_execution_cache, "panel", None)
        panel = (
            panel_loader(network)
            if panel_loader is not None
            else read_panel(repo_root, network)
        )
    target = source.target_station
    if target not in panel:
        return {**base, "status": "failed", "reason": "target_station_missing"}
    start = int(source.start_index)
    stop = start + int(source.gap_length)
    truth = panel[target].iloc[start:stop].to_numpy(dtype=float)
    train, _ = _year_split(panel.index)
    train[start:stop] = False
    train_mask = panel[target].notna() & train
    began = perf_counter()
    try:
        fit_key = _fit_cache_key(
            input_sha256=network.wide_sha256,
            target_station=target,
            model="climatology",
            information_condition=source.information_condition,
            meteorology_lag_days=int(item.meteorology_lag_days),
            frame=panel,
            train_mask=train_mask,
            feature_columns=[target],
        )
        resolver = getattr(base_execution_cache, "resolve_fit", None)
        model = _resolve_fit(
            resolver,
            fit_key,
            lambda: ClimatologyBaseline(target_col=target).fit(
                panel, dates=panel.index, train_mask=train_mask
            ),
        )
        predicted = (
            model.predict(panel, dates=panel.index)
            .iloc[start:stop]
            .to_numpy(dtype=float)
        )
        valid = np.isfinite(truth) & np.isfinite(predicted)
        if not valid.any():
            return {**base, "status": "failed", "reason": "no_finite_gap_predictions"}
        mae = float(np.mean(np.abs(predicted[valid] - truth[valid])))
        return {
            **base,
            "status": "reference_complete",
            "reason": "reference_ignores_available_information_by_design",
            "implementation": "training_doy_climatology",
            "n_scored": int(valid.sum()),
            "mae_deg_c": mae,
            "climatology_mae_deg_c": mae,
            "achieved_skill": 0.0,
            "prediction_sha256": _prediction_sha256(predicted),
            "reference_ignores_available_information": True,
            "runtime_seconds": float(perf_counter() - began),
        }
    except (
        ImportError,
        KeyError,
        RuntimeError,
        ValueError,
        np.linalg.LinAlgError,
    ) as error:
        return {
            **base,
            "status": "failed",
            "reason": f"{type(error).__name__}: {error}",
            "runtime_seconds": float(perf_counter() - began),
        }


def execute_v4_item(
    repo_root: str | Path,
    network: OpenNetwork,
    item: V4WorkItem,
    *,
    panel: Any | None = None,
    auxiliary: Any | None = None,
    adapter_cache: Any | None = None,
    base_execution_cache: Any | None = None,
) -> dict[str, Any]:
    """Route one identity-bound v4 item; callers enforce formal freeze state."""

    source = item.source_v3_item
    runner_item = item.runner_item()
    extended = source.information_condition in EXTENDED_INFORMATION_CONDITIONS
    binding_fields = {
        "ordinal": item.ordinal,
        "item_id": item.item_id,
        "source_v3_item_id": source.item_id,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "meteorology_lag_days": item.meteorology_lag_days,
        "auxiliary_corpus_plan_sha256": item.auxiliary_corpus_plan_sha256,
        "auxiliary_corpus_plan_file_sha256": (item.auxiliary_corpus_plan_file_sha256),
        "auxiliary_network_manifest_sha256": (
            item.auxiliary_binding.network_manifest_sha256
        ),
        "coverage_semantics_sha256": item.coverage_semantics_sha256,
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    if extended and source.model not in {*SUPPORTED_MODELS, "climatology"}:
        return {
            **asdict(runner_item),
            **binding_fields,
            "status": "structural_not_applicable",
            "workload_category": "structural_not_applicable",
            "reason": "model_has_no_declared_B_D_M_H_consumer",
            "consumed_information": [],
        }
    if extended and source.model == "climatology":
        raw = _execute_extended_climatology_reference(
            repo_root,
            network,
            item,
            panel=panel,
            base_execution_cache=base_execution_cache,
        )
    elif extended and source.model in SUPPORTED_MODELS:
        if item.meteorology_lag_days not in METEOROLOGY_LAG_ROSTER:
            raise V4FreezeBlocked("extended v4 item lacks a frozen meteorology lag")
        if auxiliary is None:
            auxiliary = load_materialized_auxiliary_v2(repo_root, network)
        audit = auxiliary.audit
        expected = item.auxiliary_binding
        if (
            audit.get("source_contract") != "legacy_nwis_v2"
            or audit.get("manifest_sha256") != expected.network_manifest_sha256
            or audit.get("network_plan_sha256") != expected.network_plan_sha256
            or audit.get("daily_long_sha256") != expected.daily_long_sha256
            or audit.get("coverage_sha256") != expected.coverage_sha256
            or audit.get("adapter_schema_sha256") != expected.adapter_schema_sha256
        ):
            raise V4FreezeBlocked(
                "loaded v2 auxiliary bytes differ from v4 item identity"
            )
        raw = execute_materialized_information_item(
            repo_root,
            network,
            source,
            meteorology_lag_days=int(item.meteorology_lag_days),
            panel=panel,
            auxiliary=auxiliary,
            adapter_cache=adapter_cache,
            fit_resolver=(
                None
                if base_execution_cache is None
                else base_execution_cache.resolve_fit
            ),
        )
    else:
        raw = (
            execute_item(repo_root, network, runner_item)
            if base_execution_cache is None
            else base_execution_cache.execute(
                network,
                runner_item,
                meteorology_lag_days=item.meteorology_lag_days,
            )
        )
    result = json_safe(dict(raw))
    result.update(binding_fields)
    if result.get("status") == "candidate_complete_not_formal":
        result["status"] = "complete"
    return result


def iter_formal_v4_items(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    budget: Mapping[str, Any],
) -> Iterable[V4WorkItem]:
    """Convenience stream for a future formal chunk executor."""

    prerequisites = audit_v4_prerequisites(repo_root, networks)
    return iter_v4_work_items(
        iter_all_work_items(repo_root, networks, budget), prerequisites
    )


__all__ = [
    "COVERAGE_SEMANTICS",
    "COVERAGE_SEMANTICS_SHA256",
    "EXECUTION_CODE_INVENTORY_SCHEMA",
    "EXECUTION_CODE_PATHS",
    "EXPECTED_NETWORK_COUNT",
    "EXPECTED_V3_EXTENDED_WORK_ITEMS",
    "EXPECTED_V3_WORK_ITEMS",
    "EXPECTED_V4_WORK_ITEMS",
    "V4_INDEX_DRAFT_SCHEMA",
    "V4_ITEM_INDEX_SCHEMA",
    "V4_PRE_SCORE_FREEZE_SCHEMA",
    "V4_RUNNER_CONTRACT_VERSION",
    "V4_WORKLOAD_SCHEMA",
    "V4FreezeBlocked",
    "V4Prerequisites",
    "V4WorkItem",
    "audit_v4_prerequisites",
    "build_committed_execution_inventory",
    "build_v4_readiness_manifest",
    "build_v4_workload_manifest",
    "execute_v4_item",
    "finalize_v4_workload",
    "freeze_v4_workload",
    "iter_formal_v4_items",
    "iter_v4_work_items",
    "load_v4_index_slice",
]
