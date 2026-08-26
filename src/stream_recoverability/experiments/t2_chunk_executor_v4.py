"""Atomic chunk execution for a fully frozen T2 v4 workload.

The entry point validates the 67-network v2 auxiliary corpus before creating
an output directory.  Consequently the current bounded pilot can exercise
item routing, but cannot be promoted into a formal v4 chunk.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .t2_cached_executor import StrictFitExecutionCache
from .t2_information_runner_integration import (
    load_materialized_auxiliary_v2,
)
from .t2_recovery_benchmark import (
    discover_failure_closure_networks,
)
from .t2_workload_v4 import (
    EXPECTED_V4_WORK_ITEMS,
    V4_PRE_SCORE_FREEZE_SCHEMA,
    V4_RUNNER_CONTRACT_VERSION,
    V4_WORKLOAD_SCHEMA,
    V4FreezeBlocked,
    audit_v4_prerequisites,
    execute_v4_item,
    load_v4_index_slice,
)

V4_CHUNK_SCHEMA = "t2_v91_result_chunk_v4"
MAX_V4_CHUNK_ITEMS = 5_000
TERMINAL_STATUSES = frozenset(
    {
        "complete",
        "reference_complete",
        "structural_not_applicable",
        "data_ineligible",
        "external_dependency",
        "failed",
    }
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _item_stream_sha(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row["item_id"]).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V4FreezeBlocked(f"cannot read v4 workload: {error}") from error
    if not isinstance(value, dict):
        raise V4FreezeBlocked("v4 workload must be a mapping")
    return value


def _require_committed_head(repo: Path, paths: list[Path]) -> None:
    """Require frozen bytes to exist unchanged in HEAD before first scoring."""

    relative = []
    for path in paths:
        try:
            relative.append(str(path.resolve().relative_to(repo)))
        except ValueError as error:
            raise V4FreezeBlocked(
                "pre-score artifact escaped the repository"
            ) from error
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *relative],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise V4FreezeBlocked(
            "pre-score freeze/workload must be committed and HEAD-clean"
        )
    for rel, path in zip(relative, paths, strict=True):
        tracked = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=repo, capture_output=True, check=False
        )
        if tracked.returncode != 0 or hashlib.sha256(
            tracked.stdout
        ).hexdigest() != _sha256_file(path):
            raise V4FreezeBlocked(
                "pre-score freeze bytes are not the committed HEAD bytes"
            )


def _validate_pre_score_freeze(
    repo: Path, workload_path: Path, workload: dict[str, Any]
) -> tuple[str, list[Path]]:
    record = workload.get("pre_score_freeze")
    if workload.get("execution_allowed") is not True or not isinstance(record, dict):
        raise V4FreezeBlocked(
            "v4 execution requires the final pre-score-bound workload"
        )
    manifest_path = (repo / str(record.get("path", ""))).resolve()
    if not manifest_path.is_file() or _sha256_file(manifest_path) != record.get(
        "sha256"
    ):
        raise V4FreezeBlocked("pre-score freeze manifest differs from final workload")
    manifest = _read_json(manifest_path)
    if (
        manifest.get("manifest_schema") != V4_PRE_SCORE_FREEZE_SCHEMA
        or manifest.get("status") != "complete_outcome_blind_pre_score_freeze"
        or manifest.get("v4_results_read") is not False
        or manifest.get("selection_uses_outcomes") is not False
        or manifest.get("achieved_skill_read") is not False
        or manifest.get("sealed_temperature_records_read") is not False
    ):
        raise V4FreezeBlocked("pre-score freeze manifest contract mismatch")
    paths = [workload_path, manifest_path]
    for name, bound in (
        ("item index", workload.get("item_index") or {}),
        ("index draft", workload.get("index_draft_manifest") or {}),
    ):
        path = (repo / str(bound.get("path", ""))).resolve()
        declared_sha = (
            bound.get("file_sha256") if name == "item index" else bound.get("sha256")
        )
        if not path.is_file() or _sha256_file(path) != declared_sha:
            raise V4FreezeBlocked(f"{name} differs from final workload")
        paths.append(path)
    for artifact in (record.get("artifacts") or {}).values():
        if not isinstance(artifact, dict):
            raise V4FreezeBlocked("pre-score artifact record is invalid")
        path = (repo / str(artifact.get("path", ""))).resolve()
        if not path.is_file() or _sha256_file(path) != artifact.get("sha256"):
            raise V4FreezeBlocked("pre-score artifact differs from final workload")
        paths.append(path)
    for artifact in (record.get("sensitivity_lattices") or {}).values():
        if isinstance(artifact, dict):
            path = (repo / str(artifact.get("path", ""))).resolve()
            if not path.is_file() or _sha256_file(path) != artifact.get("sha256"):
                raise V4FreezeBlocked("sensitivity lattice differs from final workload")
            paths.append(path)
    _require_committed_head(repo, paths)
    return str(record["sha256"]), paths


def _validate_range(start: int, end: int) -> tuple[int, int]:
    if isinstance(start, bool) or isinstance(end, bool):
        raise V4FreezeBlocked("v4 chunk ordinals must be integers")
    start_int, end_int = int(start), int(end)
    if start_int != start or end_int != end or start_int < 0 or end_int <= start_int:
        raise V4FreezeBlocked("v4 chunk requires exact 0 <= start < end ordinals")
    if end_int - start_int > MAX_V4_CHUNK_ITEMS:
        raise V4FreezeBlocked("v4 chunk exceeds the 5000-item maximum")
    return start_int, end_int


def _read_results(path: Path, results_format: str) -> pd.DataFrame:
    if results_format == "parquet":
        return pd.read_parquet(path)
    if results_format == "csv":
        return pd.read_csv(path)
    raise V4FreezeBlocked("v4 chunk has an unsupported results format")


def _validate_results(
    frame: pd.DataFrame,
    *,
    manifest: dict[str, Any],
    start: int,
    end: int,
) -> None:
    required = {
        "ordinal",
        "item_id",
        "source_v3_item_id",
        "network_id",
        "runner_contract_version",
        "status",
        "auxiliary_corpus_plan_sha256",
        "auxiliary_corpus_plan_file_sha256",
        "auxiliary_network_manifest_sha256",
        "coverage_semantics_sha256",
        "pre_score_freeze_sha256",
        "sealed_temperature_records_read",
    }
    if not required.issubset(frame.columns):
        raise V4FreezeBlocked("v4 chunk result table lacks identity/status fields")
    ordinals = pd.to_numeric(frame["ordinal"], errors="coerce")
    if ordinals.isna().any() or [int(value) for value in ordinals] != list(
        range(start, end)
    ):
        raise V4FreezeBlocked("v4 chunk result ordinals are not contiguous")
    if frame["item_id"].astype(str).duplicated().any():
        raise V4FreezeBlocked("v4 chunk result item ids are not unique")
    if not frame["runner_contract_version"].eq(V4_RUNNER_CONTRACT_VERSION).all():
        raise V4FreezeBlocked("v4 chunk result runner contract drifted")
    if not frame["status"].astype(str).isin(TERMINAL_STATUSES).all():
        raise V4FreezeBlocked("v4 chunk result has a nonterminal status")
    if not frame["sealed_temperature_records_read"].eq(False).all():
        raise V4FreezeBlocked(
            "v4 chunk result does not attest sealed outcomes stayed closed"
        )
    if (
        not frame["auxiliary_corpus_plan_sha256"]
        .eq(manifest.get("auxiliary_corpus_plan_sha256"))
        .all()
    ):
        raise V4FreezeBlocked("v4 chunk row corpus-plan binding mismatch")
    if (
        not frame["auxiliary_corpus_plan_file_sha256"]
        .eq(manifest.get("auxiliary_corpus_plan_file_sha256"))
        .all()
    ):
        raise V4FreezeBlocked("v4 chunk row corpus-plan file binding mismatch")
    if (
        not frame["coverage_semantics_sha256"]
        .eq(manifest.get("coverage_semantics_sha256"))
        .all()
    ):
        raise V4FreezeBlocked("v4 chunk row coverage-semantics binding mismatch")
    if (
        not frame["pre_score_freeze_sha256"]
        .eq(manifest.get("pre_score_freeze_sha256"))
        .all()
    ):
        raise V4FreezeBlocked("v4 chunk row pre-score-freeze binding mismatch")
    expected_bindings = manifest.get("auxiliary_network_bindings") or {}
    for row in frame[["network_id", "auxiliary_network_manifest_sha256"]].to_dict(
        orient="records"
    ):
        expected = expected_bindings.get(str(row["network_id"])) or {}
        if row["auxiliary_network_manifest_sha256"] != expected.get(
            "network_manifest_sha256"
        ):
            raise V4FreezeBlocked("v4 chunk row auxiliary binding mismatch")
    identities = [
        {"ordinal": int(row["ordinal"]), "item_id": str(row["item_id"])}
        for row in frame[["ordinal", "item_id"]].to_dict(orient="records")
    ]
    if manifest.get("ordinal_item_identity_sha256") != _canonical_sha(identities):
        raise V4FreezeBlocked("v4 chunk ordinal/item identity SHA mismatch")
    if manifest.get("item_id_stream_sha256") != _item_stream_sha(identities):
        raise V4FreezeBlocked("v4 chunk item-id stream SHA mismatch")
    if str(frame.iloc[0]["item_id"]) != manifest.get("first_item_id"):
        raise V4FreezeBlocked("v4 chunk first item id mismatch")
    if str(frame.iloc[-1]["item_id"]) != manifest.get("last_item_id"):
        raise V4FreezeBlocked("v4 chunk last item id mismatch")


def _resume_existing(
    chunk_dir: Path,
    *,
    expected_binding: dict[str, Any],
    start: int,
    end: int,
) -> dict[str, Any]:
    manifest_path = chunk_dir / "manifest.json"
    if not manifest_path.is_file():
        raise V4FreezeBlocked("existing v4 chunk is incomplete or foreign")
    manifest = _read_json(manifest_path)
    for key, expected in expected_binding.items():
        if manifest.get(key) != expected:
            raise V4FreezeBlocked(f"existing v4 chunk binding mismatch: {key}")
    results_name = manifest.get("results_path")
    if not isinstance(results_name, str) or Path(results_name).name != results_name:
        raise V4FreezeBlocked("existing v4 chunk results path is unsafe")
    results_path = chunk_dir / results_name
    if not results_path.is_file():
        raise V4FreezeBlocked("existing v4 chunk result table is missing")
    if _sha256_file(results_path) != manifest.get("results_sha256"):
        raise V4FreezeBlocked("existing v4 chunk result-table SHA mismatch")
    frame = _read_results(results_path, str(manifest.get("results_format")))
    if len(frame) != end - start or len(frame) != int(manifest.get("n_records", -1)):
        raise V4FreezeBlocked("existing v4 chunk result row count mismatch")
    _validate_results(frame, manifest=manifest, start=start, end=end)
    return manifest


def execute_t2_v4_chunk(
    *,
    repo_root: str | Path,
    workload_manifest_path: str | Path,
    output_dir: str | Path,
    start_ordinal: int,
    end_ordinal_exclusive: int,
    results_format: str = "parquet",
) -> dict[str, Any]:
    """Execute one formal-freeze-bound v4 chunk; never bypass 67/67 readiness."""

    start, end = _validate_range(start_ordinal, end_ordinal_exclusive)
    if results_format not in {"parquet", "csv"}:
        raise V4FreezeBlocked("v4 results format must be parquet or csv")
    repo = Path(repo_root).resolve()
    workload_path = Path(workload_manifest_path).resolve()
    output = Path(output_dir).resolve()
    if any(
        "sealed" in part.lower()
        for path in (workload_path, output)
        for part in path.parts
    ):
        raise V4FreezeBlocked("v4 chunk refuses sealed paths")
    workload = _read_json(workload_path)
    if (
        workload.get("manifest_schema") != V4_WORKLOAD_SCHEMA
        or workload.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION
        or workload.get("sealed_input_roots_allowed") != []
        or workload.get("sealed_temperature_records_read") is not False
        or int(workload.get("n_work_items", 0)) != EXPECTED_V4_WORK_ITEMS
        or workload.get("execution_allowed") is not True
    ):
        raise V4FreezeBlocked("v4 workload contract mismatch")
    expected_n = int(workload.get("n_work_items", 0))
    if expected_n < 1 or end > expected_n:
        raise V4FreezeBlocked("v4 chunk range exceeds the frozen workload")
    source_v3_path = (repo / str(workload.get("source_v3_workload_path", ""))).resolve()
    try:
        source_v3_path.relative_to(repo)
    except ValueError as error:
        raise V4FreezeBlocked("v4 source workload escaped the repository") from error
    if not source_v3_path.is_file() or _sha256_file(source_v3_path) != workload.get(
        "source_v3_workload_sha256"
    ):
        raise V4FreezeBlocked("source v3 workload bytes differ from v4 freeze")

    networks, discovered_inventory = discover_failure_closure_networks(repo)
    prerequisites = audit_v4_prerequisites(repo, networks)
    if not prerequisites.ready:
        raise V4FreezeBlocked(
            f"v4 chunk forbidden before 67 terminal networks; found "
            f"{prerequisites.n_networks_terminal}"
        )
    input_map = {network.network_id: network.wide_sha256 for network in networks}
    binding_map = {
        key: value.identity() for key, value in prerequisites.bindings.items()
    }
    input_inventory_sha = _canonical_sha(input_map)
    binding_sha = _canonical_sha(binding_map)
    if (
        workload.get("network_ids") != [network.network_id for network in networks]
        or workload.get("input_inventory") != discovered_inventory
        or workload.get("input_sha256_by_network") != input_map
        or workload.get("input_sha256_by_network_sha256") != input_inventory_sha
        or workload.get("auxiliary_corpus_plan_sha256")
        != prerequisites.corpus_plan_sha256
        or workload.get("auxiliary_corpus_plan_file_sha256")
        != prerequisites.corpus_plan_file_sha256
        or workload.get("auxiliary_network_bindings") != binding_map
        or workload.get("auxiliary_network_bindings_sha256") != binding_sha
    ):
        raise V4FreezeBlocked("current v2 auxiliary identities differ from v4 freeze")

    pre_score_freeze_sha, _ = _validate_pre_score_freeze(repo, workload_path, workload)

    workload_sha = _sha256_file(workload_path)
    chunk_identity = _canonical_sha(
        {
            "workload_manifest_sha256": workload_sha,
            "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
            "input_sha256_by_network_sha256": input_inventory_sha,
            "auxiliary_network_bindings_sha256": binding_sha,
            "pre_score_freeze_sha256": pre_score_freeze_sha,
            "start_ordinal": start,
            "end_ordinal_exclusive": end,
            "results_format": results_format,
        }
    )
    expected_binding = {
        "manifest_schema": V4_CHUNK_SCHEMA,
        "runner_contract_version": V4_RUNNER_CONTRACT_VERSION,
        "workload_manifest_sha256": workload_sha,
        "workload_item_identity_sha256": workload["work_item_identity_sha256"],
        "item_index_file_sha256": workload["item_index"]["file_sha256"],
        "coverage_semantics_sha256": workload["coverage_semantics_sha256"],
        "auxiliary_corpus_plan_sha256": prerequisites.corpus_plan_sha256,
        "auxiliary_corpus_plan_file_sha256": (prerequisites.corpus_plan_file_sha256),
        "auxiliary_network_bindings_sha256": binding_sha,
        "auxiliary_network_bindings": binding_map,
        "input_sha256_by_network_sha256": input_inventory_sha,
        "input_sha256_by_network": input_map,
        "pre_score_freeze_sha256": pre_score_freeze_sha,
        "chunk_identity_sha256": chunk_identity,
        "start_ordinal": start,
        "end_ordinal_exclusive": end,
        "n_records": end - start,
        "results_format": results_format,
        "results_path": f"results.{results_format}",
        "completeness": "complete",
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
        "passed": False,
    }
    items = load_v4_index_slice(
        repo,
        workload,
        prerequisites,
        start=start,
        end=end,
    )
    identities = [{"ordinal": item.ordinal, "item_id": item.item_id} for item in items]
    expected_binding.update(
        {
            "ordinal_item_identity_sha256": _canonical_sha(identities),
            "item_id_stream_sha256": _item_stream_sha(identities),
            "first_item_id": items[0].item_id,
            "last_item_id": items[-1].item_id,
        }
    )
    chunk_dir = output / f"chunk_{start:07d}_{end:07d}"
    if chunk_dir.exists():
        return _resume_existing(
            chunk_dir,
            expected_binding=expected_binding,
            start=start,
            end=end,
        )

    if len(items) != end - start or [item.ordinal for item in items] != list(
        range(start, end)
    ):
        raise V4FreezeBlocked("v4 item stream violated frozen ordinal continuity")

    lookup = {network.network_id: network for network in networks}
    auxiliary_cache: dict[str, Any] = {}
    adapter_caches: defaultdict[str, dict[str, Any]] = defaultdict(dict)
    base_cache = StrictFitExecutionCache(repo)
    records: list[dict[str, Any]] = []
    for item in items:
        network = lookup[item.network_id]
        extended_supported = (
            item.meteorology_lag_days is not None
            and item.source_v3_item.model in {"donor_regression", "xgboost"}
        )
        if extended_supported:
            if network.network_id not in auxiliary_cache:
                auxiliary_cache[network.network_id] = load_materialized_auxiliary_v2(
                    repo, network
                )
            result = execute_v4_item(
                repo,
                network,
                item,
                panel=base_cache.panel(network),
                auxiliary=auxiliary_cache[network.network_id],
                adapter_cache=adapter_caches[network.network_id],
                base_execution_cache=base_cache,
            )
        else:
            result = execute_v4_item(
                repo, network, item, base_execution_cache=base_cache
            )
        if (
            result.get("item_id") != item.item_id
            or int(result.get("ordinal", -1)) != item.ordinal
            or result.get("runner_contract_version") != V4_RUNNER_CONTRACT_VERSION
            or result.get("sealed_temperature_records_read") is not False
            or result.get("status") not in TERMINAL_STATUSES
        ):
            raise V4FreezeBlocked("v4 runner returned an invalid or nonterminal row")
        result["pre_score_freeze_sha256"] = pre_score_freeze_sha
        records.append(result)

    frame = pd.DataFrame(records)
    manifest = {
        **expected_binding,
        "status_counts": dict(
            sorted(Counter(str(row["status"]) for row in records).items())
        ),
        "purpose": "bounded_pipeline_execution_not_evidence",
        "headline_claim_licensed": False,
        "execution_cache": dict(base_cache.stats()),
    }
    output.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{chunk_dir.name}.", dir=output))
    try:
        result_path = staging / str(manifest["results_path"])
        if results_format == "parquet":
            frame.to_parquet(result_path, index=False)
        else:
            frame.to_csv(result_path, index=False)
        result_descriptor = os.open(result_path, os.O_RDONLY)
        try:
            os.fsync(result_descriptor)
        finally:
            os.close(result_descriptor)
        manifest["results_sha256"] = _sha256_file(result_path)
        manifest_path = staging / "manifest.json"
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(result_path, 0o444)
        os.chmod(manifest_path, 0o444)
        try:
            os.rename(staging, chunk_dir)
            output_descriptor = os.open(output, os.O_RDONLY)
            try:
                os.fsync(output_descriptor)
            finally:
                os.close(output_descriptor)
        except OSError:
            if not chunk_dir.exists():
                raise
            resumed = _resume_existing(
                chunk_dir,
                expected_binding=expected_binding,
                start=start,
                end=end,
            )
            shutil.rmtree(staging)
            return resumed
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return manifest


__all__ = [
    "MAX_V4_CHUNK_ITEMS",
    "V4_CHUNK_SCHEMA",
    "execute_t2_v4_chunk",
]
