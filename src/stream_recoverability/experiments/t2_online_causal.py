"""Bounded, open-role-only execution of the v9.1 T2 online-causal task.

The online task is derived from the already frozen offline ``WorkItem``
geometry.  It never reselects a gap.  At a gap beginning at ``s`` and ending
before ``e``, model fitting may use target observations only at times ``< s``;
prediction receives a panel truncated at ``e`` with the target hidden from
``s`` onward.  Synchronous donor values are available on their labelled day,
whereas target truth, the right boundary, and every post-gap target are absent.

PCHIP and the registered Kalman *smoother* retain their frozen identities and
are therefore structural-not-applicable online.  This module does not silently
replace either with forward fill, linear extrapolation, or a Kalman filter.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, replace
from itertools import chain
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.recoverability_spectrum import recoverability
from stream_recoverability.experiments.frozen_outage_geometry import (
    load_frozen_geometry_bindings,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    EXTENDED_INFORMATION_CONDITIONS,
    GEOMETRY_BINDING_RELATIVE_PATH,
    MIN_TRAIN_OBSERVATIONS,
    OpenNetwork,
    WorkItem,
    iter_frozen_geometry_work_items,
    iter_work_items,
    json_safe,
    read_panel,
)
from stream_recoverability.models.baselines import (
    ClimatologyBaseline,
    DonorRegressionBaseline,
    XGBoostBaseline,
)

ONLINE_TASK = "online_causal"
ONLINE_RUNNER_CONTRACT_VERSION = "t2_v91_online_causal_runner_v1"
ONLINE_CHECKPOINT_NAMESPACE = "online_checkpoints_v1"
NONNEGATIVE_DONOR_LAGS = tuple(range(31))


def _sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def placement_signature(item: WorkItem) -> str:
    """Identify frozen placement/geometry independently of task and model."""

    return _sha256(
        {
            "network_id": item.network_id,
            "role": item.role,
            "source_key": item.source_key,
            "target_station": item.target_station,
            "gap_length": item.gap_length,
            "placement": item.placement,
            "start_index": item.start_index,
            "geometry": item.geometry,
            "geometry_id": item.geometry_id,
            "geometry_catalog_file_sha256": item.geometry_catalog_file_sha256,
            "geometry_row_sha256": item.geometry_row_sha256,
            "truth_start_date": item.truth_start_date,
            "observed_missing_start_date": item.observed_missing_start_date,
            "donor_mask_rule": item.donor_mask_rule,
            "target_mask_scope": item.target_mask_scope,
            "boundary_mode": item.boundary_mode,
            "stress_id": item.stress_id,
        }
    )


def bind_online_item(item: WorkItem, *, ordinal: int | None = None) -> WorkItem:
    """Bind an offline item to online execution without changing its placement."""

    if item.task != "offline_archival":
        raise ValueError("online binding requires an offline_archival source WorkItem")
    identity = {
        "online_runner_contract_version": ONLINE_RUNNER_CONTRACT_VERSION,
        "source_runner_item_id": item.item_id,
        "placement_signature": placement_signature(item),
        "model": item.model,
        "information_condition": item.information_condition,
        "task": ONLINE_TASK,
    }
    return replace(
        item,
        ordinal=item.ordinal if ordinal is None else int(ordinal),
        item_id=_sha256(identity)[:24],
        task=ONLINE_TASK,
    )


def iter_online_items(items: Iterable[WorkItem]) -> Iterable[WorkItem]:
    """Lazily derive a sequential online workload from frozen offline items."""

    for ordinal, item in enumerate(items):
        yield bind_online_item(item, ordinal=ordinal)


def iter_online_workload(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    budget: Mapping[str, Any],
    *,
    include_frozen_geometry: bool = True,
    roles: Iterable[str] | None = None,
    network_ids: Iterable[str] | None = None,
    models: Iterable[str] | None = None,
    gaps: Iterable[int] | None = None,
    information_conditions: Iterable[str] | None = None,
) -> Iterable[WorkItem]:
    """Return artificial plus frozen-geometry online items without reselection."""

    selected_roles = None if roles is None else tuple(str(value) for value in roles)
    selected_network_ids = (
        None if network_ids is None else tuple(str(value) for value in network_ids)
    )
    selected_gaps = None if gaps is None else tuple(int(value) for value in gaps)
    selected_models = None if models is None else tuple(str(value) for value in models)
    selected_information = (
        None
        if information_conditions is None
        else tuple(str(value) for value in information_conditions)
    )
    artificial = iter_work_items(
        repo_root,
        networks,
        budget,
        roles=selected_roles,
        network_ids=selected_network_ids,
        models=selected_models,
        gaps=selected_gaps,
        information_conditions=selected_information,
    )
    source: Iterable[WorkItem] = artificial
    if include_frozen_geometry:
        binding = Path(repo_root).resolve() / GEOMETRY_BINDING_RELATIVE_PATH
        natural, adversarial, manifest = load_frozen_geometry_bindings(binding)
        selected_networks = [
            network
            for network in networks
            if (selected_roles is None or network.role in set(selected_roles))
            and (
                selected_network_ids is None
                or network.network_id in set(selected_network_ids)
            )
        ]
        frozen = iter_frozen_geometry_work_items(
            repo_root,
            selected_networks,
            budget,
            natural.loc[natural["network_id"].isin(
                [network.network_id for network in selected_networks]
            )],
            adversarial.loc[adversarial["network_id"].isin(
                [network.network_id for network in selected_networks]
            )],
            manifest,
            models=selected_models,
            information_conditions=selected_information,
        )
        if selected_gaps is not None:
            allowed_gaps = set(selected_gaps)
            frozen = (item for item in frozen if item.gap_length in allowed_gaps)
        source = chain(artificial, frozen)
    return iter_online_items(source)


def _left_boundary_available(item: WorkItem) -> bool:
    return item.boundary_mode in {"left_only", "both"}


def online_cell_contract(item: WorkItem) -> dict[str, Any]:
    """Declare model identity and timestamp-legal information consumption."""

    if item.task != ONLINE_TASK:
        raise ValueError("online_cell_contract requires task=online_causal")
    if item.start_index < 0:
        return {
            "supported": False,
            "category": "data_ineligible",
            "reason": (
                "fewer_than_frozen_common_bd_placements_are_data_eligible"
                if item.geometry == "artificial_stress"
                else "frozen_geometry_truth_window_unavailable_without_reselection"
            ),
            "consumed_information": [],
        }
    if item.model == "climatology":
        return {
            "supported": True,
            "category": "reference",
            "reason": "reference_ignores_available_information_by_design",
            "consumed_information": [],
        }
    if item.information_condition in EXTENDED_INFORMATION_CONDITIONS:
        return {
            "supported": False,
            "category": "structural_not_applicable",
            "reason": "online_timestamp_safe_meteorology_or_hydraulics_not_bound",
            "consumed_information": [],
        }
    if item.model == "pchip_or_linear":
        return {
            "supported": False,
            "category": "structural_not_applicable",
            "reason": "registered_pchip_or_linear_identity_requires_future_boundary",
            "consumed_information": [],
        }
    if item.model == "kalman":
        return {
            "supported": False,
            "category": "structural_not_applicable",
            "reason": "registered_kalman_smoother_identity_uses_future_observations",
            "consumed_information": [],
        }
    if item.model in {"donor_regression", "xgboost"}:
        if item.information_condition not in {"D", "B_union_D"}:
            return {
                "supported": False,
                "category": "structural_not_applicable",
                "reason": "model_does_not_implement_information_condition",
                "consumed_information": [],
            }
        if item.donor_mask_rule == "mask_all_network_stations_during_gap":
            return {
                "supported": False,
                "category": "structural_not_applicable",
                "reason": "donor_information_masked_by_frozen_geometry",
                "consumed_information": [],
            }
        if item.information_condition == "B_union_D":
            if not _left_boundary_available(item):
                return {
                    "supported": False,
                    "category": "structural_not_applicable",
                    "reason": "left_boundary_absent_in_frozen_geometry",
                    "consumed_information": ["D"],
                }
            return {
                "supported": True,
                "category": "executable",
                "reason": "",
                "consumed_information": ["B_left_history", "D_as_of_prediction_day"],
            }
        return {
            "supported": True,
            "category": "executable",
            "reason": "",
            "consumed_information": ["D_as_of_prediction_day"],
        }
    return {
        "supported": False,
        "category": "structural_not_applicable",
        "reason": "unknown_model",
        "consumed_information": [],
    }


def causal_exposure(panel: pd.DataFrame, item: WorkItem) -> tuple[pd.DataFrame, pd.Series]:
    """Materialize the maximum panel visible to this online gap forecast."""

    start = int(item.start_index)
    stop = start + int(item.gap_length)
    if start < 1 or stop > len(panel):
        raise ValueError("online item has no valid left-history/gap window")
    exposed = panel.iloc[:stop].copy()
    exposed.iloc[start:, exposed.columns.get_loc(item.target_station)] = np.nan
    if item.donor_mask_rule == "mask_all_network_stations_during_gap":
        donors = [column for column in exposed.columns if str(column) != item.target_station]
        exposed.loc[exposed.index[start:stop], donors] = np.nan
    train = pd.Series(False, index=exposed.index, dtype=bool)
    train.iloc[:start] = True
    return exposed, train


def _causal_boundary_frame(
    exposed: pd.DataFrame,
    *,
    target: str,
    start: int,
) -> tuple[pd.DataFrame, str]:
    """Add a named left-history feature; never synthesize a right boundary."""

    feature_name = "__causal_left_boundary_B"
    feature = pd.to_numeric(exposed[target], errors="coerce").shift(1)
    left_value = float(exposed[target].iloc[start - 1])
    feature.iloc[start:] = left_value
    result = exposed.copy()
    result[feature_name] = feature
    return result, feature_name


def _prediction_sha256(values: np.ndarray) -> str:
    array = np.asarray(values, dtype="<f8")
    return hashlib.sha256(
        array.shape.__repr__().encode() + b"|" + array.tobytes()
    ).hexdigest()


def execute_online_item(
    repo_root: str | Path,
    network: OpenNetwork,
    item: WorkItem,
) -> dict[str, Any]:
    """Execute one online item under a fail-closed timestamp boundary."""

    contract = online_cell_contract(item)
    base: dict[str, Any] = {
        **asdict(item),
        "input_sha256": network.wide_sha256,
        "runner_contract_version": ONLINE_RUNNER_CONTRACT_VERSION,
        "placement_signature": placement_signature(item),
        "available_information_condition": item.information_condition,
        "consumed_information": contract["consumed_information"],
        "information_condition_result": contract["category"] == "executable",
        "workload_category": contract["category"],
        "causal_cutoff_rule": "fit_target_strictly_before_gap_start",
        "prediction_exposure_rule": "panel_ends_at_gap_end_target_hidden_from_gap_start",
        "right_boundary_exposed_to_model": False,
        "post_gap_target_exposed_to_model": False,
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    if not contract["supported"]:
        return {
            **base,
            "status": str(contract["category"]),
            "reason": contract["reason"],
        }
    panel = read_panel(repo_root, network)
    target = item.target_station
    if target not in panel:
        return {**base, "status": "failed", "reason": "target_station_missing"}
    start = int(item.start_index)
    stop = start + int(item.gap_length)
    truth = panel[target].iloc[start:stop].to_numpy(dtype=float)
    try:
        exposed, train_mask = causal_exposure(panel, item)
    except ValueError as error:
        return {**base, "status": "data_ineligible", "reason": str(error)}
    n_train = int((train_mask & exposed[target].notna()).sum())
    if n_train < MIN_TRAIN_OBSERVATIONS:
        return {
            **base,
            "status": "data_ineligible",
            "workload_category": "data_ineligible",
            "reason": "fewer_than_365_pre_gap_target_observations",
            "n_train_target_observations": n_train,
        }
    donors = [str(column) for column in exposed.columns if str(column) != target]
    began = perf_counter()
    try:
        climatology = ClimatologyBaseline(target_col=target).fit(
            exposed, dates=exposed.index, train_mask=train_mask
        )
        climate_prediction = climatology.predict(
            exposed, dates=exposed.index
        ).iloc[start:stop]
        climate_values = climate_prediction.to_numpy(dtype=float)
        climate_valid = np.isfinite(truth) & np.isfinite(climate_values)
        if not climate_valid.any():
            return {**base, "status": "failed", "reason": "no_finite_climatology_truth_pairs"}
        climate_mae = float(
            np.mean(np.abs(climate_values[climate_valid] - truth[climate_valid]))
        )
        if item.model == "climatology":
            prediction = climate_prediction
            implementation = "causal_pre_gap_doy_climatology"
        elif item.model == "donor_regression":
            model_frame = exposed
            covariates: list[str] = []
            if item.information_condition == "B_union_D":
                model_frame, boundary = _causal_boundary_frame(
                    exposed, target=target, start=start
                )
                covariates = [boundary]
            model = DonorRegressionBaseline(
                donors,
                target_col=target,
                covariate_cols=covariates,
                candidate_lags=NONNEGATIVE_DONOR_LAGS,
            ).fit(model_frame, dates=model_frame.index, train_mask=train_mask)
            prediction = model.predict(model_frame, dates=model_frame.index).iloc[start:stop]
            implementation = (
                "causal_seasonal_ridge_nonnegative_donor_lags_plus_left_B"
                if covariates
                else "causal_seasonal_ridge_nonnegative_donor_lags_D"
            )
        elif item.model == "xgboost":
            if not XGBoostBaseline.is_available():
                return {
                    **base,
                    "status": "external_dependency",
                    "workload_category": "external_dependency",
                    "reason": "xgboost_not_installed",
                }
            model_frame = exposed
            features = list(donors)
            if item.information_condition == "B_union_D":
                model_frame, boundary = _causal_boundary_frame(
                    exposed, target=target, start=start
                )
                features.append(boundary)
            model = XGBoostBaseline(features, target_col=target).fit(
                model_frame, dates=model_frame.index, train_mask=train_mask
            )
            prediction = model.predict(model_frame, dates=model_frame.index).iloc[start:stop]
            implementation = (
                "causal_xgboost_contemporaneous_D_plus_left_B"
                if item.information_condition == "B_union_D"
                else "causal_xgboost_contemporaneous_D"
            )
        else:  # pragma: no cover - contract rejects frozen offline-only identities
            raise ValueError(f"unexpected executable online model: {item.model}")
        predicted = prediction.to_numpy(dtype=float)
        valid = np.isfinite(truth) & np.isfinite(predicted)
        if not valid.any():
            return {**base, "status": "failed", "reason": "no_finite_gap_predictions"}
        mae = float(np.mean(np.abs(predicted[valid] - truth[valid])))
        reference = contract["category"] == "reference"
        return {
            **base,
            "status": "reference_complete" if reference else "complete",
            "reason": contract["reason"] if reference else "",
            "implementation": implementation,
            "n_train_target_observations": n_train,
            "n_scored": int(valid.sum()),
            "mae_deg_c": climate_mae if reference else mae,
            "climatology_mae_deg_c": climate_mae,
            "achieved_skill": 0.0 if reference else recoverability(mae, climate_mae),
            "prediction_sha256": _prediction_sha256(predicted),
            "reference_ignores_available_information": reference,
            "runtime_seconds": float(perf_counter() - began),
        }
    except (ImportError, KeyError, RuntimeError, ValueError, np.linalg.LinAlgError) as error:
        return {
            **base,
            "status": "failed",
            "reason": f"{type(error).__name__}: {error}",
            "runtime_seconds": float(perf_counter() - began),
        }


def run_online_items(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    items: Iterable[WorkItem],
    output_dir: str | Path,
    *,
    start_ordinal: int = 0,
    max_items: int | None = None,
) -> dict[str, Any]:
    """Checkpoint only an explicitly bounded online slice."""

    if max_items is None or int(max_items) < 1:
        raise ValueError("online execution requires a positive max_items bound")
    output = Path(output_dir)
    checkpoints = output / ONLINE_CHECKPOINT_NAMESPACE
    checkpoints.mkdir(parents=True, exist_ok=True)
    lookup = {network.network_id: network for network in networks}
    selected = executed = resumed = 0
    statuses: Counter[str] = Counter()
    for item in items:
        if item.ordinal < int(start_ordinal):
            continue
        if selected >= int(max_items):
            break
        selected += 1
        path = checkpoints / f"{item.item_id}.json"
        if path.is_file():
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior.get("item_id") != item.item_id:
                raise RuntimeError(f"checkpoint identity mismatch: {path}")
            resumed += 1
            statuses[str(prior.get("status", "unknown"))] += 1
            continue
        result = execute_online_item(repo_root, lookup[item.network_id], item)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(json_safe(result), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        executed += 1
        statuses[str(result["status"])] += 1
    summary = {
        "manifest_schema": "t2_v91_online_causal_bounded_run_v1",
        "runner_contract_version": ONLINE_RUNNER_CONTRACT_VERSION,
        "task": ONLINE_TASK,
        "checkpoint_namespace": ONLINE_CHECKPOINT_NAMESPACE,
        "selected": selected,
        "executed": executed,
        "resumed": resumed,
        "statuses": dict(sorted(statuses.items())),
        "start_ordinal": int(start_ordinal),
        "max_items": int(max_items),
        "full_workload_started": False,
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    (output / "last_run.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def build_online_workload_manifest(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    inventory: Mapping[str, Any],
    budget: Mapping[str, Any],
    *,
    include_frozen_geometry: bool = True,
) -> dict[str, Any]:
    """Count the full online workload without executing a model cell."""

    categories: Counter[str] = Counter()
    reasons: Counter[tuple[str, str]] = Counter()
    geometries: Counter[str] = Counter()
    models: Counter[str] = Counter()
    information: Counter[str] = Counter()
    digest = hashlib.sha256()
    placement_digest = hashlib.sha256()
    seen_placements: set[str] = set()
    n_items = 0
    for item in iter_online_workload(
        repo_root,
        networks,
        budget,
        include_frozen_geometry=include_frozen_geometry,
    ):
        n_items += 1
        digest.update(item.item_id.encode() + b"\n")
        signature = placement_signature(item)
        if signature not in seen_placements:
            seen_placements.add(signature)
            placement_digest.update(signature.encode() + b"\n")
        geometries[item.geometry] += 1
        models[item.model] += 1
        information[item.information_condition] += 1
        contract = online_cell_contract(item)
        category = str(contract["category"])
        reason = str(contract["reason"])
        if (
            category == "executable"
            and item.model == "xgboost"
            and not XGBoostBaseline.is_available()
        ):
            category = "external_dependency"
            reason = "xgboost_not_installed"
        categories[category] += 1
        if reason:
            reasons[(category, reason)] += 1
    if sum(categories.values()) != n_items:
        raise AssertionError("online workload categories do not partition work items")
    return {
        "manifest_schema": "t2_v91_online_causal_workload_v1",
        "runner_contract_version": ONLINE_RUNNER_CONTRACT_VERSION,
        "design_id": budget["design_id"],
        "protocol_amendment": budget["protocol_amendment"],
        "design_sha256": budget["design_sha256"],
        "task": ONLINE_TASK,
        "purpose": "pipeline_verification_not_evidence",
        "runner_implementation_ready": True,
        "bounded_open_smoke_ready": True,
        "full_execution_started": False,
        "full_execution_authorized": False,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "go_no_go": "NO_GO_T2_PRIMARY_EVIDENCE",
        "no_go_reasons": [
            f"n_open_networks_{len(networks)}_lt_100_network_interval_floor",
            "online_full_workload_not_executed",
            "online_timestamp_safe_M_and_H_inputs_not_bound",
            "network_level_aggregation_blocked_no_complete_result_set",
        ],
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "n_networks": len(networks),
        "network_ids": [network.network_id for network in networks],
        "input_inventory": dict(inventory),
        "n_work_items": n_items,
        "work_item_identity_sha256": digest.hexdigest(),
        "n_unique_frozen_placements": len(seen_placements),
        "placement_roster_identity_sha256": placement_digest.hexdigest(),
        "placement_binding": {
            "source": "existing_offline_WorkItem_and_frozen_geometry",
            "reselected_for_online": False,
            "same_gap_start_and_truth_window": True,
            "same_donor_mask_rule": True,
        },
        "counts": {
            "executable": categories["executable"],
            "reference": categories["reference"],
            "structural_not_applicable": categories["structural_not_applicable"],
            "data_ineligible": categories["data_ineligible"],
            "external_dependency": categories["external_dependency"],
            "by_geometry": dict(sorted(geometries.items())),
            "by_model": dict(sorted(models.items())),
            "by_information_condition": dict(sorted(information.items())),
            "by_category_reason": {
                "|".join(key): value for key, value in sorted(reasons.items())
            },
        },
        "causal_contract": {
            "training_target": "timestamps_strictly_before_gap_start_only",
            "B": "last_observed_target_at_left_boundary_plus_earlier_target_history_only",
            "D": "same_day_or_past_donor_values_only_nonnegative_selected_lags",
            "M": "provider_value_available_on_or_before_prediction_day_only_when_bound",
            "H": "provider_value_available_on_or_before_prediction_day_only_when_bound",
            "right_boundary": "forbidden_not_exposed_to_model",
            "gap_target_truth": "score_only_never_exposed_to_model",
            "post_gap_target": "forbidden_not_exposed_to_model",
        },
        "model_identity_contract": {
            "climatology": "pre_gap_training_reference",
            "pchip_or_linear": "structural_not_applicable_no_silent_one_sided_substitution",
            "kalman": "structural_not_applicable_registered_identity_is_smoother",
            "donor_regression": "causal_nonnegative_donor_lags",
            "xgboost": "causal_contemporaneous_donor_features",
        },
    }


__all__ = [
    "NONNEGATIVE_DONOR_LAGS",
    "ONLINE_CHECKPOINT_NAMESPACE",
    "ONLINE_RUNNER_CONTRACT_VERSION",
    "ONLINE_TASK",
    "bind_online_item",
    "build_online_workload_manifest",
    "causal_exposure",
    "execute_online_item",
    "iter_online_items",
    "iter_online_workload",
    "online_cell_contract",
    "placement_signature",
    "run_online_items",
]
