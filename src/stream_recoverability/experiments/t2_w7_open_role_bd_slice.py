"""Honest W7 first-layer T2 slice aggregation. Not confirmatory evidence.

This writer may only summarize a bounded cheap-model B / D / B_union_D slice
on open-role failure_closure6 networks.  It cannot license T2, cannot emit a
tested network CI, and cannot set ``passed`` true.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.hierarchical_confirmation import evaluate_success
from stream_recoverability.experiments.recoverability_baselines import incremental_fit
from stream_recoverability.experiments.t2_recovery_benchmark import (
    BASE_INFORMATION_CONDITIONS,
    TIER1_MODELS,
    json_safe,
)
from stream_recoverability.experiments.t2_result_aggregation import (
    CHUNK_SCHEMA,
    PREDICTOR_COLUMNS,
    AggregationContractError,
)

MANIFEST_SCHEMA = "t2_w7_open_role_bd_slice_v1"
PURPOSE = "development_slice_not_evidence"
GO_NO_GO = "NO_GO_T2_PRIMARY_EVIDENCE"
W8_INCREMENTAL_R2_TRIGGER = 0.05
N_NETWORKS_MIN = 100
CHEAP_MODELS = TIER1_MODELS
FIRST_LAYER_INFORMATION = BASE_INFORMATION_CONDITIONS
EXTENDED_INFORMATION = ("B_union_D_union_M", "B_union_D_union_M_union_H")
FORBIDDEN_SCORED_NETWORK_IDS = frozenset(
    {
        "huc8_03110203",
        "suwannee_river_huc31",
        "loire_mainstem",
        "swiss_aar_rhine",
    }
)
JOIN_KEYS = ("network_id", "station_id", "gap_length")
PROTECTED_RELATIVE_PATHS = (
    "results/framework/public_rivers/operator_ablation_manifest.json",
    "results/framework/public_rivers_v2/operator_ablation_manifest.json",
    "results/framework/synthetic_v2/twin_e",
)


class W7SliceContractError(AggregationContractError):
    """Raised when a W7 slice write would cross a locked evidence boundary."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_open_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise W7SliceContractError(f"refusing a sealed path: {path}")


def _assert_output_not_protected(output_dir: Path, repo_root: Path | None) -> None:
    resolved = output_dir.resolve()
    lowered = {part.lower() for part in resolved.parts}
    if "sealed" in lowered or "twin_e" in lowered:
        raise W7SliceContractError(f"W7 slice refuses protected output path: {resolved}")
    if repo_root is None:
        return
    repo = repo_root.resolve()
    public = (repo / "results/framework/public_rivers").resolve()
    try:
        resolved.relative_to(public)
    except ValueError:
        pass
    else:
        raise W7SliceContractError("W7 slice refuses to write under public_rivers")
    for relative in PROTECTED_RELATIVE_PATHS:
        protected = (repo / relative).resolve()
        if resolved == protected or resolved == protected.parent:
            raise W7SliceContractError(f"W7 slice refuses protected path: {protected}")


def development_inference_status(n_networks: int) -> str:
    """Network CIs stay withheld for this development slice. Never ``tested``."""

    if int(n_networks) < N_NETWORKS_MIN:
        return "withheld_n_lt_100_network_interval"
    return "withheld_development_slice_not_confirmatory"


def _read_table(path: Path, format_name: str) -> pd.DataFrame:
    if format_name == "parquet":
        return pd.read_parquet(path)
    if format_name == "csv":
        return pd.read_csv(path)
    raise W7SliceContractError(f"unsupported table format: {format_name}")


def load_w7_chunk_results(
    chunk_manifest_paths: Sequence[str | Path],
    *,
    workload_manifest_sha256: str,
) -> pd.DataFrame:
    """Load SHA-bound chunk tables without requiring the full 1.38M-item set."""

    frames: list[pd.DataFrame] = []
    for raw in chunk_manifest_paths:
        path = Path(raw).resolve()
        _assert_open_path(path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise W7SliceContractError(f"chunk manifest is not a mapping: {path}")
        if manifest.get("manifest_schema") != CHUNK_SCHEMA:
            raise W7SliceContractError("W7 slice received a foreign chunk schema")
        if manifest.get("workload_manifest_sha256") != workload_manifest_sha256:
            raise W7SliceContractError("chunk workload SHA-256 mismatch")
        if manifest.get("sealed_temperature_records_read") is not False:
            raise W7SliceContractError("chunk reports sealed temperature reads")
        if manifest.get("passed") is True:
            raise W7SliceContractError("chunk manifest claims passed=true")
        results_name = manifest.get("results_path")
        if not isinstance(results_name, str) or Path(results_name).name != results_name:
            raise W7SliceContractError("chunk has an unsafe results_path")
        results_path = path.parent / results_name
        _assert_open_path(results_path)
        if not results_path.is_file() or _sha256_file(results_path) != manifest.get(
            "results_sha256"
        ):
            raise W7SliceContractError("chunk result bytes differ from manifest")
        frame = _read_table(results_path, str(manifest.get("results_format")))
        if int(manifest.get("n_records", -1)) != len(frame):
            raise W7SliceContractError("chunk result count mismatch")
        frames.append(frame)
    if not frames:
        raise W7SliceContractError("W7 slice has no chunk result tables")
    combined = pd.concat(frames, ignore_index=True)
    if combined["ordinal"].duplicated().any() or combined["item_id"].duplicated().any():
        raise W7SliceContractError("duplicate ordinal or item_id across W7 chunks")
    return combined.sort_values("ordinal", kind="stable").reset_index(drop=True)


def _load_predictors(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    manifest_path = Path(path).resolve()
    _assert_open_path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise W7SliceContractError("predictor manifest is not a mapping")
    table_name = manifest.get("predictions_path") or manifest.get("parquet_path")
    fmt = str(manifest.get("predictions_format") or "csv")
    if manifest.get("parquet_path") and Path(str(manifest.get("parquet_path"))).suffix == ".parquet":
        parquet = manifest_path.parent / str(manifest["parquet_path"])
        if parquet.is_file():
            table_name = parquet.name
            fmt = "parquet"
    if not isinstance(table_name, str):
        raise W7SliceContractError("predictor manifest lacks a table path")
    table_path = (manifest_path.parent / table_name).resolve()
    _assert_open_path(table_path)
    predictors = _read_table(table_path, fmt)
    missing = set(JOIN_KEYS).union(PREDICTOR_COLUMNS) - set(predictors.columns)
    if missing:
        raise W7SliceContractError(f"predictor table missing columns: {sorted(missing)}")
    return predictors


def _finite_delta(nested: pd.DataFrame, added: str) -> float:
    if nested.empty or "added" not in nested.columns:
        return float("nan")
    match = nested.loc[nested["added"].eq(added), "delta_r2"]
    if match.empty:
        return float("nan")
    return float(pd.to_numeric(match.iloc[0], errors="coerce"))


def _evaluate_success_summary(
    joined: pd.DataFrame, n_networks: int
) -> dict[str, Any]:
    """Call locked evaluate_success, then strip any confirmatory license."""

    status = development_inference_status(n_networks)
    summary = {
        "passed": False,
        "passed_numeric_floors": False,
        "confirmatory_eligible": False,
        "n_networks_min": N_NETWORKS_MIN,
        "thresholds_locked": True,
        "spearman_inference_status": status,
    }
    needed = {"predicted_conditional_risk", "observed_recovery_loss", "network_id"}
    if joined.empty or not needed.issubset(joined.columns) or n_networks < 3:
        return summary
    usable = joined.loc[
        np.isfinite(
            pd.to_numeric(joined["predicted_conditional_risk"], errors="coerce")
        )
        & np.isfinite(
            pd.to_numeric(joined["observed_recovery_loss"], errors="coerce")
        )
    ].copy()
    if usable["network_id"].nunique() < 3:
        return summary
    raw = evaluate_success(
        usable,
        predicted="predicted_conditional_risk",
        observed="observed_recovery_loss",
    )
    summary["passed_numeric_floors"] = bool(raw.get("passed_numeric_floors", False))
    summary["thresholds_locked"] = bool(raw.get("thresholds_locked", True))
    summary["passed"] = False
    summary["confirmatory_eligible"] = False
    summary["n_networks_min"] = N_NETWORKS_MIN
    summary["spearman_inference_status"] = status
    if summary["spearman_inference_status"] == "tested":
        summary["spearman_inference_status"] = development_inference_status(n_networks)
    return summary


def write_w7_open_role_bd_slice(
    *,
    output_dir: str | Path,
    results: pd.DataFrame,
    predictors: pd.DataFrame | None = None,
    workload: Mapping[str, Any] | None = None,
    workload_manifest_sha256: str = "",
    repo_root: str | Path | None = None,
    items_planned: int | None = None,
) -> dict[str, Any]:
    """Write a development-only W7 aggregation. ``passed`` is always false."""

    output = Path(output_dir)
    repo = None if repo_root is None else Path(repo_root)
    _assert_open_path(output)
    _assert_output_not_protected(output, repo)
    if results.empty:
        raise W7SliceContractError("W7 slice has no result rows")
    if results.get("sealed_temperature_records_read", pd.Series(dtype=object)).eq(
        True
    ).any():
        raise W7SliceContractError("result rows report sealed temperature reads")

    roster = [str(value) for value in ((workload or {}).get("network_ids") or [])]
    roster_set = set(roster)
    frame = results.copy()
    frame["network_id"] = frame["network_id"].astype(str)
    frame["model"] = frame["model"].astype(str)
    frame["information_condition"] = frame["information_condition"].astype(str)
    frame["status"] = frame["status"].astype(str)
    if "target_station" in frame.columns and "station_id" not in frame.columns:
        frame["station_id"] = frame["target_station"].astype(str)

    first_layer = frame.loc[
        frame["model"].isin(CHEAP_MODELS)
        & frame["information_condition"].isin(FIRST_LAYER_INFORMATION)
    ].copy()
    extended = frame.loc[frame["information_condition"].isin(EXTENDED_INFORMATION)].copy()
    scored_mask = first_layer["status"].isin({"complete", "reference_complete"})
    scored_ids = sorted(set(first_layer.loc[scored_mask, "network_id"].astype(str)))
    leaked = sorted(set(scored_ids).intersection(FORBIDDEN_SCORED_NETWORK_IDS))
    scored_ids = [network for network in scored_ids if network not in FORBIDDEN_SCORED_NETWORK_IDS]
    if roster_set:
        scored_ids = [network for network in scored_ids if network in roster_set]
    n_networks = len(scored_ids)

    executable_complete = first_layer.loc[
        first_layer["status"].eq("complete")
        & first_layer["network_id"].isin(scored_ids)
    ].copy()
    predictor_frame = pd.DataFrame() if predictors is None else predictors.copy()
    joined = pd.DataFrame()
    nested_vs_donor = pd.DataFrame()
    nested_full = pd.DataFrame()
    operator_increment = float("nan")
    if not executable_complete.empty and not predictor_frame.empty:
        missing = set(JOIN_KEYS).union(PREDICTOR_COLUMNS) - set(predictor_frame.columns)
        if missing:
            raise W7SliceContractError(f"predictor table missing columns: {sorted(missing)}")
        outcomes = executable_complete.rename(
            columns={
                "mae_deg_c": "observed_recovery_loss",
                "achieved_skill": "observed_achieved_skill",
            }
        )
        joined = outcomes.merge(
            predictor_frame[list(JOIN_KEYS) + list(PREDICTOR_COLUMNS)],
            on=list(JOIN_KEYS),
            how="inner",
        )
        finite = joined.loc[
            np.isfinite(pd.to_numeric(joined["observed_achieved_skill"], errors="coerce"))
            & np.isfinite(pd.to_numeric(joined["donor_r2_only"], errors="coerce"))
            & np.isfinite(
                pd.to_numeric(joined["predicted_conditional_risk"], errors="coerce")
            )
        ]
        if len(finite) > 3:
            nested_vs_donor = incremental_fit(
                finite,
                outcome="observed_achieved_skill",
                predictors=("donor_r2_only", "predicted_conditional_risk"),
            )
            nested_full = incremental_fit(
                finite,
                outcome="observed_achieved_skill",
                predictors=(
                    "gap_length_only",
                    "acf_only",
                    "donor_r2_only",
                    "additive_d_over_4_heuristic",
                    "predicted_conditional_risk",
                ),
            )
            operator_increment = _finite_delta(
                nested_vs_donor, "predicted_conditional_risk"
            )

    increment_defined = bool(np.isfinite(operator_increment))
    w8_trigger = bool(increment_defined and operator_increment < W8_INCREMENTAL_R2_TRIGGER)
    if w8_trigger:
        w8_reason = "operator_incremental_r2_vs_donor_r2_only_lt_0.05"
    elif not increment_defined:
        w8_reason = "operator_incremental_r2_undefined"
    else:
        w8_reason = "operator_incremental_r2_vs_donor_r2_only_ge_0.05"

    confirmation = _evaluate_success_summary(joined, n_networks)
    inference_status = development_inference_status(n_networks)
    mh_status = dict(sorted(Counter(extended["status"].astype(str)).items())) if not extended.empty else {}
    mh_complete = int(mh_status.get("complete", 0))
    first_layer_status = dict(sorted(Counter(first_layer["status"].astype(str)).items()))
    qualification = ""
    if workload:
        qualification = str(
            (workload.get("geometry_binding") or {}).get("qualification_mode")
            or (workload.get("input_inventory") or {}).get("qualification_mode")
            or ""
        )

    output.mkdir(parents=True, exist_ok=True)
    first_layer_path = output / "first_layer_results.parquet"
    first_layer.to_parquet(first_layer_path, index=False)
    if not nested_vs_donor.empty:
        nested_vs_donor.to_csv(output / "operator_vs_donor_r2_nested.csv", index=False)
    if not nested_full.empty:
        nested_full.to_csv(output / "nested_ablation.csv", index=False)
    if not joined.empty:
        joined.to_parquet(output / "joined_first_layer_complete.parquet", index=False)

    planned = int(items_planned) if items_planned is not None else int(len(frame))
    manifest: dict[str, Any] = {
        "manifest_schema": MANIFEST_SCHEMA,
        "n_networks": n_networks,
        "passed": False,
        "purpose": PURPOSE,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "go_no_go": GO_NO_GO,
        "evaluate_success": confirmation,
        "network_inference_status": inference_status,
        "network_interval": None,
        "qualification_mode": qualification or "failure_closure6",
        "new_temperatures_downloaded": False,
        "sealed_outcomes_opened": False,
        "europe_complete_enough_used": False,
        "items_executed": int(len(frame)),
        "items_planned": planned,
        "n_first_layer_items": int(len(first_layer)),
        "n_first_layer_complete": int(first_layer_status.get("complete", 0)),
        "n_first_layer_reference_complete": int(
            first_layer_status.get("reference_complete", 0)
        ),
        "n_first_layer_executable_complete": int(len(executable_complete)),
        "first_layer_status_counts": first_layer_status,
        "all_status_counts": dict(sorted(Counter(frame["status"].astype(str)).items())),
        "cheap_models": list(CHEAP_MODELS),
        "first_layer_information_conditions": list(FIRST_LAYER_INFORMATION),
        "extended_information_conditions_skipped_as_first_layer": list(
            EXTENDED_INFORMATION
        ),
        "n_extended_information_items_in_ordinal_range": int(len(extended)),
        "extended_information_status_counts": mh_status,
        "mh_items_complete": mh_complete,
        "mh_relabeled_as_executable": False,
        "scored_network_ids": scored_ids,
        "forbidden_network_ids_excluded": sorted(FORBIDDEN_SCORED_NETWORK_IDS),
        "forbidden_network_ids_leaked_into_input": leaked,
        "operator_incremental_r2_vs_donor_r2_only": (
            None if not increment_defined else float(operator_increment)
        ),
        "w8_failure_closure_trigger": w8_trigger,
        "w8_failure_closure_reason": w8_reason,
        "w8_incremental_r2_threshold": W8_INCREMENTAL_R2_TRIGGER,
        "operator_retuned": False,
        "geometry_reselected": False,
        "twin_e_holdout_touched": False,
        "later_year_public_rivers_overwritten": False,
        "workload_manifest_sha256": workload_manifest_sha256,
        "aggregation_complete_workload": False,
        "slice_is_confirmatory_t2": False,
        "what_this_is": (
            "W7 first-layer cheap-model B/D/B_union_D development slice on "
            "open-role failure_closure6 networks."
        ),
        "what_this_is_not": (
            "Not confirmatory T2. Not primary evidence. n<100 so cluster-bootstrap "
            "CIs stay withheld. M/H cells are not executable. Do not sell this slice "
            "as a T2 pass."
        ),
    }
    if confirmation.get("spearman_inference_status") == "tested" or confirmation.get(
        "passed"
    ):
        raise W7SliceContractError("W7 slice writer refused to emit tested/passed inference")
    if manifest["passed"] is not False or manifest["evaluate_success"]["passed"] is not False:
        raise W7SliceContractError("W7 slice writer cannot set passed true")
    if manifest["evaluate_success"]["spearman_inference_status"] == "tested":
        raise W7SliceContractError("W7 slice writer cannot emit tested Spearman CIs")
    if set(scored_ids) & FORBIDDEN_SCORED_NETWORK_IDS:
        raise W7SliceContractError("Suwannee/Loire/Swiss leaked into scored HUC8 ids")

    payload = json_safe(manifest)
    (output / "w7_open_role_bd_slice_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def aggregate_w7_open_role_bd_slice_from_chunks(
    *,
    repo_root: str | Path,
    output_dir: str | Path,
    workload_manifest_path: str | Path,
    chunk_manifest_paths: Sequence[str | Path],
    predictor_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Production entry: bind frozen workload SHA, load chunks, write the slice."""

    repo = Path(repo_root).resolve()
    workload_path = Path(workload_manifest_path).resolve()
    _assert_open_path(repo)
    _assert_open_path(workload_path)
    workload = json.loads(workload_path.read_text(encoding="utf-8"))
    if not isinstance(workload, dict):
        raise W7SliceContractError("workload manifest is not a mapping")
    workload_sha = _sha256_file(workload_path)
    results = load_w7_chunk_results(
        chunk_manifest_paths, workload_manifest_sha256=workload_sha
    )
    predictors = _load_predictors(
        None if predictor_manifest_path is None else Path(predictor_manifest_path)
    )
    return write_w7_open_role_bd_slice(
        output_dir=output_dir,
        results=results,
        predictors=predictors if not predictors.empty else None,
        workload=workload,
        workload_manifest_sha256=workload_sha,
        repo_root=repo,
        items_planned=len(results),
    )


__all__ = [
    "CHEAP_MODELS",
    "FIRST_LAYER_INFORMATION",
    "FORBIDDEN_SCORED_NETWORK_IDS",
    "GO_NO_GO",
    "MANIFEST_SCHEMA",
    "N_NETWORKS_MIN",
    "PURPOSE",
    "W7SliceContractError",
    "W8_INCREMENTAL_R2_TRIGGER",
    "aggregate_w7_open_role_bd_slice_from_chunks",
    "development_inference_status",
    "load_w7_chunk_results",
    "write_w7_open_role_bd_slice",
]
