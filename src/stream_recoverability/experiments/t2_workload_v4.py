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
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    NETWORK_SCHEMA_VERSION as V2_NETWORK_SCHEMA_VERSION,
)
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    PLAN_SCHEMA_VERSION as V2_PLAN_SCHEMA_VERSION,
)
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    TERMINAL_STATUSES as V2_TERMINAL_STATUSES,
)

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
    execute_item,
    iter_all_work_items,
    json_safe,
)

V3_WORKLOAD_SCHEMA = "t2_v91_open_role_workload_v3"
V4_WORKLOAD_SCHEMA = "t2_v91_open_role_workload_v4"
V4_RUNNER_CONTRACT_VERSION = "t2_v91_runner_v4_legacy_mh_lag_grid_v1"
V4_READINESS_SCHEMA = "t2_v91_open_role_workload_v4_readiness_v1"
EXPECTED_NETWORK_COUNT = 67
LEGACY_V2_PLAN_SCHEMA_VERSION = "t2_v91_open_role_mh_corpus_request_plan_v2"

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


def _canonical_sha(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


COVERAGE_SEMANTICS_SHA256 = _canonical_sha(COVERAGE_SEMANTICS)


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V4FreezeBlocked(f"cannot read v4 prerequisite {path}: {error}") from error
    if not isinstance(value, dict):
        raise V4FreezeBlocked(f"v4 prerequisite is not a mapping: {path}")
    return value


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
        raise V4FreezeBlocked(f"v2 artifact is absent or escaped its network: {key}") from error
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
    if (
        plan.get("manifest_schema")
        not in {V2_PLAN_SCHEMA_VERSION, LEGACY_V2_PLAN_SCHEMA_VERSION}
        or int(plan.get("n_networks", -1)) != EXPECTED_NETWORK_COUNT
        or plan.get("sealed_paths_traversed") is not False
        or plan.get("temperature_columns_read") != []
        or plan.get("performance_metrics_computed") is not False
        or plan.get("v1_ogc_root_read_or_mutated") is not False
    ):
        raise V4FreezeBlocked("v2 corpus plan violates the frozen open-only contract")
    expected = [(network.network_id, network.role) for network in networks]
    planned = [
        (str(row.get("network_id")), str(row.get("role")))
        for row in (plan.get("networks") or [])
    ]
    if len(networks) != EXPECTED_NETWORK_COUNT or planned != expected:
        raise V4FreezeBlocked("v2 plan roster differs from the 67-network v3 roster")

    plan_by_id = {
        str(row["network_id"]): row for row in (plan.get("networks") or [])
    }
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
                and manifest_schema
                == "t2_v91_open_role_mh_network_acquisition_v2"
            )
            planned_network_sha = str(plan_by_id[network.network_id]["network_plan_sha256"])
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
            _, daily_sha = _safe_artifact(repo, directory, artifacts, "daily_long_auxiliary")
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
    ):
        raise V4FreezeBlocked("source v3 workload contract mismatch")
    prerequisites = audit_v4_prerequisites(repo, networks)
    blockers = []
    if not prerequisites.ready:
        blockers.append(
            f"v2_auxiliary_terminal_{prerequisites.n_networks_terminal}_of_"
            f"{prerequisites.n_networks_expected}"
        )
    return {
        "manifest_schema": V4_READINESS_SCHEMA,
        "status": "ready_for_formal_v4_freeze" if prerequisites.ready else "blocked_fail_closed",
        "passed": False,
        "purpose": "pipeline_readiness_not_evidence",
        "formal_evidence": False,
        "formal_workload_generated": False,
        "formal_result_generated": False,
        "blockers": blockers,
        "source_v3_workload_path": str(v3_path.relative_to(repo)),
        "source_v3_workload_sha256": _sha256_file(v3_path),
        "source_v3_work_item_identity_sha256": str(
            (v3.get("tier_1") or {}).get("work_item_identity_sha256")
        ),
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
            "other_extended_models": "structural_not_applicable",
        },
        "batch_orchestration": {
            "contract_spec": "configs/t2_workload_v4_contract.json",
            "executor_adapter": None,
            "status": "readiness_only_no_execution_adapter",
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


def build_v4_workload_manifest(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    *,
    source_v3_workload_path: str | Path,
    source_items: Iterable[WorkItem],
) -> dict[str, Any]:
    """Build the formal v4 freeze, refusing any incomplete v2 corpus."""

    repo = Path(repo_root).resolve()
    v3_path = Path(source_v3_workload_path).resolve()
    readiness = build_v4_readiness_manifest(
        repo, networks, source_v3_workload_path=v3_path
    )
    prerequisites = audit_v4_prerequisites(repo, networks)
    if not prerequisites.ready:
        raise V4FreezeBlocked("formal v4 workload forbidden before v2 reaches 67/67 terminal")
    digest = hashlib.sha256()
    counts = Counter()
    lag_counts = Counter()
    n_items = 0
    for item in iter_v4_work_items(source_items, prerequisites):
        digest.update(item.item_id.encode("utf-8"))
        digest.update(b"\n")
        source = item.source_v3_item
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
        n_items += 1
    source_v3 = _read_mapping(v3_path)
    input_inventory = source_v3.get("input_inventory")
    if not isinstance(input_inventory, Mapping):
        raise V4FreezeBlocked("source v3 workload lacks its input inventory")
    auxiliary_bindings = {
        key: value.identity() for key, value in prerequisites.bindings.items()
    }
    return {
        "manifest_schema": V4_WORKLOAD_SCHEMA,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "source_v3_workload_path": str(v3_path.relative_to(repo)),
        "source_v3_workload_sha256": readiness["source_v3_workload_sha256"],
        "source_v3_work_item_identity_sha256": readiness[
            "source_v3_work_item_identity_sha256"
        ],
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
        "other_extended_models": "structural_not_applicable",
        "batch_orchestration_contract_spec": "configs/t2_workload_v4_contract.json",
        "n_networks": len(networks),
        "network_ids": [network.network_id for network in networks],
        "n_work_items": n_items,
        "work_item_identity_sha256": digest.hexdigest(),
        "counts_by_model_information": {
            "|".join(key): value for key, value in sorted(counts.items())
        },
        "counts_by_model_information_lag": {
            "|".join(key): value for key, value in sorted(lag_counts.items())
        },
        "purpose": "formal_workload_freeze_not_performance_evidence",
        "formal_evidence": False,
        "sealed_input_roots_allowed": [],
        "sealed_paths_traversed": False,
        "sealed_temperature_records_read": False,
        "performance_metrics_computed": False,
        "network_interval_reported": False,
        "passed": False,
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
    if extended and source.model not in SUPPORTED_MODELS:
        return {
            **asdict(runner_item),
            "source_v3_item_id": source.item_id,
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
            "meteorology_lag_days": item.meteorology_lag_days,
            "status": "structural_not_applicable",
            "workload_category": "structural_not_applicable",
            "reason": "model_has_no_declared_B_D_M_H_consumer",
            "consumed_information": [],
            "formal_evidence": False,
            "sealed_temperature_records_read": False,
        }
    if extended:
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
            raise V4FreezeBlocked("loaded v2 auxiliary bytes differ from v4 item identity")
        raw = execute_materialized_information_item(
            repo_root,
            network,
            runner_item,
            meteorology_lag_days=int(item.meteorology_lag_days),
            panel=panel,
            auxiliary=auxiliary,
            adapter_cache=adapter_cache,
        )
    else:
        raw = (
            execute_item(repo_root, network, runner_item)
            if base_execution_cache is None
            else base_execution_cache.execute(network, runner_item)
        )
    result = json_safe(dict(raw))
    result.update(
        {
            "ordinal": item.ordinal,
            "item_id": item.item_id,
            "source_v3_item_id": source.item_id,
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
            "meteorology_lag_days": item.meteorology_lag_days,
            "auxiliary_corpus_plan_sha256": item.auxiliary_corpus_plan_sha256,
            "auxiliary_network_manifest_sha256": (
                item.auxiliary_binding.network_manifest_sha256
            ),
            "coverage_semantics_sha256": item.coverage_semantics_sha256,
            "formal_evidence": False,
            "sealed_temperature_records_read": False,
        }
    )
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
    "EXPECTED_NETWORK_COUNT",
    "V4_RUNNER_CONTRACT_VERSION",
    "V4_WORKLOAD_SCHEMA",
    "V4FreezeBlocked",
    "V4Prerequisites",
    "V4WorkItem",
    "audit_v4_prerequisites",
    "build_v4_readiness_manifest",
    "build_v4_workload_manifest",
    "execute_v4_item",
    "iter_formal_v4_items",
    "iter_v4_work_items",
]
