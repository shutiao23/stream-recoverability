"""Roster-authorized donor-C falsification with one frozen checkpoint per seed."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.falsification import (
    falsification_grid,
    interpret_falsification,
)
from stream_recoverability.evaluation.event_metrics import compute_event_metrics
from stream_recoverability.models.baselines import DonorRegressionBaseline
from .formal_authorization import (
    authorize_proposed_estimand,
    authorize_roster_suite,
)
from .grid import ExperimentGrid, ExperimentScenario
from .runner import ExperimentRunner
from .science import (
    EVIDENCE_TABLE_FIELDS,
    _atomic_csv,
    _atomic_json,
    _atomic_parquet,
    _checkpoint_artifact_identity,
    _compensation_checkpoint_files,
    _compensation_training_seeds,
    _load_compensation_checkpoint,
    build_compensation_grid,
    predict_proposed_information_combinations,
    training_doy_climatology,
)

SUITE = "science_donor_falsification"
EXPERIMENT = "SCI_DONOR_FALSIFICATION"
FULL_INFORMATION = ("A", "B", "C", "D")
DONOR_VARIABLES = ("T", "F", "L")
PERMUTATION_SEED = 20260820
BLOCK_DAYS = 30


def _slug(spec: Mapping[str, Any]) -> str:
    contrast = str(spec["contrast"])
    if contrast == "lagged_C":
        lag = int(spec["lag_days"])
        return f"LAG{'P' if lag >= 0 else 'M'}{abs(lag):02d}"
    return {
        "observed_same_day_C": "SAME",
        "past_only_C": "PAST",
        "station_identity_permutation": "IDPERM",
        "seasonal_residual_block_permutation": "SEASPERM",
    }[contrast]


def build_donor_falsification_grid(
    manifest_path: str | Path = "study_manifest.yaml",
    *,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v2",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = "metadata/frontier_anchors_v2.csv",
) -> tuple[ExperimentGrid, dict[str, dict[str, Any]]]:
    """Cross fixed T-gap masks with each target/donor/contrast declaration."""

    base = build_compensation_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )
    stations = tuple(
        dict.fromkeys(
            station
            for condition in base.conditions
            for station in condition.station_ids
        )
    )
    specs = falsification_grid(permutation_seed=PERMUTATION_SEED, stations=stations)
    conditions = []
    scenarios = []
    by_condition: dict[str, dict[str, Any]] = {}
    base_condition_lookup = {
        condition.condition_id: condition for condition in base.conditions
    }
    for base_condition in base.conditions:
        target_station = str(base_condition.station_ids[0])
        for donor_station in stations:
            if donor_station == target_station:
                continue
            for spec in specs:
                condition_id = (
                    f"SCI-DONOR-{target_station}-FROM-{donor_station}-"
                    f"T-D{int(base_condition.gap_length):03d}-{_slug(spec)}"
                )
                condition = replace(
                    base_condition,
                    experiment=EXPERIMENT,
                    condition_id=condition_id,
                )
                conditions.append(condition)
                by_condition[condition_id] = {
                    **dict(spec),
                    "target_station": target_station,
                    "donor_station": donor_station,
                    "donor_relation": (
                        "upstream"
                        if stations.index(donor_station)
                        < stations.index(target_station)
                        else "downstream"
                    ),
                }
    for base_scenario in base.scenarios:
        base_id = base_scenario.condition.condition_id
        target_station = str(base_condition_lookup[base_id].station_ids[0])
        for condition in conditions:
            if str(condition.station_ids[0]) != target_station or int(
                condition.gap_length
            ) != int(base_scenario.condition.gap_length):
                continue
            bound = replace(
                base_scenario.condition,
                experiment=EXPERIMENT,
                condition_id=condition.condition_id,
            )
            scenarios.append(ExperimentScenario(bound, base_scenario.mask_seed))
    grid = ExperimentGrid(
        suite=SUITE,
        conditions=tuple(conditions),
        scenarios=tuple(scenarios),
        mask_seeds=base.mask_seeds,
        training_seeds=base.training_seeds,
        external_validation_status=base.external_validation_status,
        frontier_anchor_catalog_path=base.frontier_anchor_catalog_path,
        frontier_anchor_catalog_sha256=base.frontier_anchor_catalog_sha256,
        frontier_anchor_count=base.frontier_anchor_count,
    )
    if len(grid.scenarios) != len(base.scenarios) * 2 * len(specs):
        raise AssertionError("donor-C grid inventory is incomplete")
    return grid, by_condition


def _shift(values: np.ndarray, lag: int) -> np.ndarray:
    result = np.full_like(values, np.nan, dtype=np.float32)
    if lag == 0:
        return values.astype(np.float32, copy=True)
    if lag > 0:
        result[lag:] = values[:-lag]
    else:
        result[:lag] = values[-lag:]
    return result


def transform_donor_values(
    values: np.ndarray,
    *,
    dates: pd.DatetimeIndex,
    train_rows: np.ndarray,
    station_ids: Sequence[str],
    variable_names: Sequence[str],
    spec: Mapping[str, Any],
) -> np.ndarray:
    """Transform only one declared donor; seasonal means use train rows only."""

    result = np.asarray(values, dtype=np.float32).copy()
    donor = tuple(station_ids).index(str(spec["donor_station"]))
    target = tuple(station_ids).index(str(spec["target_station"]))
    variables = [tuple(variable_names).index(name) for name in DONOR_VARIABLES]
    contrast = str(spec["contrast"])
    lag = int(spec.get("lag_days", 0) or 0)
    if contrast in {"lagged_C", "past_only_C"}:
        lag = 1 if contrast == "past_only_C" else lag
        for variable in variables:
            result[:, donor, variable] = _shift(result[:, donor, variable], lag)
    elif contrast == "station_identity_permutation":
        alternatives = [
            index for index in range(len(station_ids)) if index not in {target, donor}
        ]
        if not alternatives:
            raise ValueError("station permutation requires a second donor")
        result[:, donor, variables] = values[:, alternatives[0], variables]
    elif contrast == "seasonal_residual_block_permutation":
        rng = np.random.default_rng(int(spec.get("seed", PERMUTATION_SEED)))
        day_of_year = dates.dayofyear.to_numpy()
        blocks = [
            np.arange(start, min(start + BLOCK_DAYS, len(result)))
            for start in range(0, len(result), BLOCK_DAYS)
        ]
        order = rng.permutation(len(blocks))
        permutation = np.concatenate([blocks[index] for index in order])
        for variable in variables:
            series = values[:, donor, variable].astype(float)
            training = pd.DataFrame(
                {"doy": day_of_year[train_rows], "value": series[train_rows]}
            )
            seasonal_lookup = training.groupby("doy", observed=True)["value"].mean()
            fallback = float(training["value"].mean())
            seasonal = (
                pd.Series(day_of_year).map(seasonal_lookup).fillna(fallback).to_numpy()
            )
            residual = series - seasonal
            result[:, donor, variable] = seasonal + residual[permutation]
    elif contrast != "observed_same_day_C":
        raise ValueError(f"unsupported donor-C contrast: {contrast}")
    return result


def _score_unit(
    runner: ExperimentRunner,
    scenario: ExperimentScenario,
    spec: Mapping[str, Any],
    training_seed: int,
    model: Any,
    mean: np.ndarray,
    scale: np.ndarray,
    climatology_by_station: Mapping[int, np.ndarray],
    *,
    device: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    station = runner.data.station_ids.index(str(spec["target_station"]))
    target_index = runner.data.variable_names.index("T")
    artificial, metadata = runner._generate_mask(scenario)
    transformed = transform_donor_values(
        runner.data.values,
        dates=runner.data.dates,
        train_rows=runner.train_rows,
        station_ids=runner.data.station_ids,
        variable_names=runner.data.variable_names,
        spec=spec,
    )
    natural = runner.data.natural_observed & np.isfinite(transformed)
    climatology_matrix = np.column_stack(
        [climatology_by_station[index] for index in range(len(runner.data.station_ids))]
    )
    prediction = predict_proposed_information_combinations(
        model,
        transformed,
        natural,
        artificial,
        runner.data.seasonal_features,
        mean,
        scale,
        target_index=target_index,
        training_climatology=(
            climatology_matrix.astype(np.float32) - mean[:, target_index][None, :]
        )
        / scale[:, target_index][None, :],
        information_combinations=(FULL_INFORMATION,),
        window_length=scenario.condition.window_length,
        device=device,
    )["S0+A+B+C+D"]
    truth = runner.data.values[:, station, target_index].astype(float)
    quality = runner.data.quality_approved[:, station, target_index]
    hidden = artificial[:, station, target_index]
    positions = np.flatnonzero(hidden & quality & np.isfinite(truth))
    q = {name: values[:, station] for name, values in prediction.items()}
    reference = runner._training_reference(station, target_index)
    row_metadata = {
        **metadata,
        "scenario_id": scenario.scenario_id,
        "station_id": str(spec["target_station"]),
        "model": "proposed",
        "training_seed": training_seed,
        "mask_seed": scenario.mask_seed,
        "target": "T",
        "gap_length": scenario.condition.gap_length,
    }
    event = compute_event_metrics(
        truth,
        q["q50"],
        quality,
        hidden,
        target="T",
        metadata=row_metadata,
        climatology_pred=climatology_by_station[station],
        dates=runner.data.dates,
        quantile_predictions=q,
        high_threshold=reference.q90,
        low_threshold=reference.q10,
        normalization_iqr=reference.iqr,
        normalization_std=reference.std,
    )
    common = {
        "experiment": EXPERIMENT,
        "mask_type": scenario.condition.mask_type,
        "station_ids": json.dumps(list(scenario.condition.station_ids)),
        "condition_id": scenario.condition.condition_id,
        "contrast": str(spec["contrast"]),
        "lag_days": int(spec.get("lag_days", 0) or 0),
        "donor_station_id": str(spec["donor_station"]),
        "donor_relation": str(spec["donor_relation"]),
        "component_estimator": "proposed_checkpoint",
        "information_combination": "S0+A+B+C+D",
        "fit_split": "train",
        "tuning_split": "validation_checkpoint",
        "evaluation_split": runner.evaluation_split,
        "window_length": scenario.condition.window_length,
        "training_protocol": scenario.condition.training_protocol,
        "anchor_id": scenario.condition.anchor_id,
        "anchor_target": scenario.condition.anchor_target,
        "anchor_mask_seed": scenario.condition.anchor_mask_seed,
        "center_date": scenario.condition.center_date,
        "center_index": scenario.condition.center_index,
        "anchor_data_version": scenario.condition.anchor_data_version,
        "anchor_evaluation_split": scenario.condition.anchor_evaluation_split,
        "anchor_source_split": scenario.condition.anchor_source_split,
        "anchor_max_supported_length": scenario.condition.anchor_max_supported_length,
        "anchor_start_month": scenario.condition.anchor_start_month,
        "anchor_season": scenario.condition.anchor_season,
        "anchor_year": scenario.condition.anchor_year,
        "anchor_hydrologic_state": scenario.condition.anchor_hydrologic_state,
        "formal_evidence": True,
        "evidence_role": "formal_development_evaluation",
    }
    event.update(common)
    event["skill_gain"] = event.get("skill")
    daily = pd.DataFrame(
        {
            "date": runner.data.dates[positions],
            "station_id": str(spec["target_station"]),
            "target": "T",
            "scenario_id": scenario.scenario_id,
            "model": "proposed",
            "training_seed": training_seed,
            "mask_seed": scenario.mask_seed,
            "y_true": truth[positions],
            "y_pred": q["q50"][positions],
            "q05": q["q05"][positions],
            "q25": q["q25"][positions],
            "q50": q["q50"][positions],
            "q75": q["q75"][positions],
            "q95": q["q95"][positions],
            "quality_approved": quality[positions],
            "artificial_mask": hidden[positions],
            **common,
        }
    )
    for field in EVIDENCE_TABLE_FIELDS:
        daily[field] = runner.evidence_contract[field]
        event[field] = runner.evidence_contract[field]
    events = pd.DataFrame([event])
    if daily.empty or not np.isfinite(daily[["y_true", "y_pred"]]).all().all():
        raise ValueError("donor-C unit has no finite paired target evidence")
    return daily, events


def _score_donor_regression_unit(
    runner: ExperimentRunner,
    scenario: ExperimentScenario,
    spec: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    station_id = str(spec["target_station"])
    station = runner.data.station_ids.index(station_id)
    target_index = runner.data.variable_names.index("T")
    artificial, metadata = runner._generate_mask(scenario)
    transformed = transform_donor_values(
        runner.data.values,
        dates=runner.data.dates,
        train_rows=runner.train_rows,
        station_ids=runner.data.station_ids,
        variable_names=runner.data.variable_names,
        spec=spec,
    )
    frame = runner._wide_frame(transformed)
    fit_mask = (
        runner.train_rows
        & runner.data.quality_approved[:, station, target_index]
        & np.isfinite(transformed[:, station, target_index])
    )
    other_stations = [
        value for value in runner.data.station_ids if value != station_id
    ]
    model = DonorRegressionBaseline(
        [f"{value}_T" for value in other_stations],
        f"{station_id}_T",
        covariate_cols=(f"{station_id}_Ta",),
    ).fit(frame, train_mask=fit_mask)
    pred = model.predict(frame).to_numpy(dtype=float)
    truth = runner.data.values[:, station, target_index].astype(float)
    quality = runner.data.quality_approved[:, station, target_index]
    hidden = artificial[:, station, target_index]
    positions = np.flatnonzero(hidden & quality & np.isfinite(truth))
    climatology = training_doy_climatology(
        runner.data.dates,
        runner.data.values[:, station, target_index],
        runner.train_rows,
        quality,
    )
    reference = runner._training_reference(station, target_index)
    row_metadata = {
        **metadata,
        "scenario_id": scenario.scenario_id,
        "station_id": station_id,
        "model": "donor_regression",
        "training_seed": None,
        "mask_seed": scenario.mask_seed,
        "target": "T",
        "gap_length": scenario.condition.gap_length,
    }
    event = compute_event_metrics(
        truth,
        pred,
        quality,
        hidden,
        target="T",
        metadata=row_metadata,
        climatology_pred=climatology,
        dates=runner.data.dates,
        high_threshold=reference.q90,
        low_threshold=reference.q10,
        normalization_iqr=reference.iqr,
        normalization_std=reference.std,
    )
    common = {
        "experiment": EXPERIMENT,
        "mask_type": scenario.condition.mask_type,
        "station_ids": json.dumps(list(scenario.condition.station_ids)),
        "condition_id": scenario.condition.condition_id,
        "contrast": str(spec["contrast"]),
        "lag_days": int(spec.get("lag_days", 0) or 0),
        "donor_station_id": str(spec["donor_station"]),
        "donor_relation": str(spec["donor_relation"]),
        "component_estimator": "donor_regression",
        "fit_split": "train",
        "evaluation_split": runner.evaluation_split,
        "window_length": scenario.condition.window_length,
        "anchor_id": scenario.condition.anchor_id,
        "center_date": scenario.condition.center_date,
        "formal_evidence": True,
        "evidence_role": "formal_development_evaluation",
    }
    event.update(common)
    event["skill_gain"] = event.get("skill")
    daily = pd.DataFrame(
        {
            "date": runner.data.dates[positions],
            "station_id": station_id,
            "target": "T",
            "scenario_id": scenario.scenario_id,
            "model": "donor_regression",
            "training_seed": None,
            "mask_seed": scenario.mask_seed,
            "y_true": truth[positions],
            "y_pred": pred[positions],
            "quality_approved": quality[positions],
            "artificial_mask": hidden[positions],
            **common,
        }
    )
    for field in EVIDENCE_TABLE_FIELDS:
        daily[field] = runner.evidence_contract[field]
        event[field] = runner.evidence_contract[field]
    events = pd.DataFrame([event])
    if daily.empty or not np.isfinite(daily[["y_true", "y_pred"]]).all().all():
        raise ValueError("donor-regression unit has no finite paired target evidence")
    return daily, events


def _run_donor_regression_falsification(
    *,
    finalized_model_roster_path: str | Path,
    selection_data_version_manifest_path: str | Path,
    manifest_path: str | Path,
    config_path: str | Path,
    design_path: str | Path,
    data_version_manifest_path: str | Path | None,
    wide_path: str | Path,
    quality_path: str | Path,
    output_dir: str | Path,
    mask_dir: str | Path,
    mask_seeds: Sequence[int] | None,
    data_version: str,
    evaluation_split: str,
    frontier_anchor_path: str | Path | None,
    max_scenarios: int | None,
    resume: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Score donor-C contrasts with donor regression, not the proposed model."""

    output = Path(output_dir)
    models, authorization = authorize_roster_suite(
        finalized_model_roster_path,
        suite=SUITE,
        target_scope=("T",),
        design_path=design_path,
        study_manifest_path=manifest_path,
        experiment_config_path=config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    if "donor_regression" not in models:
        raise ValueError("donor falsification requires donor_regression on the roster")
    authorization = {
        **authorization,
        "expected_models": ["donor_regression"],
        "model_scope": "authorized_donor_regression_estimand",
    }
    grid, specs = build_donor_falsification_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output,
        mask_dir=mask_dir,
        config_path=config_path,
        design_path=design_path,
        manifest_path=manifest_path,
        data_version_manifest_path=data_version_manifest_path,
        models=("donor_regression",),
        training_seeds=(),
        formal_authorization=authorization,
        resume=resume,
    )
    selected_scenarios = grid.scenarios
    if max_scenarios is not None:
        if max_scenarios < 1:
            raise ValueError("max_scenarios must be positive")
        selected_scenarios = selected_scenarios[:max_scenarios]
    invocation_skips: list[dict[str, Any]] = []
    for scenario in selected_scenarios:
        spec = specs[scenario.condition.condition_id]
        unit = output / "units" / scenario.scenario_id / "donor_regression"
        status_path = unit / "status.json"
        daily_path = unit / "daily_predictions.parquet"
        event_path = unit / "event_metrics.parquet"
        if (
            resume
            and status_path.is_file()
            and daily_path.is_file()
            and event_path.is_file()
        ):
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                if status.get("status") == "complete":
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        try:
            daily, events = _score_donor_regression_unit(runner, scenario, spec)
            _atomic_parquet(daily, daily_path)
            _atomic_parquet(events, event_path)
            _atomic_json(
                {
                    "status": "complete",
                    "scenario_id": scenario.scenario_id,
                    "contrast": spec["contrast"],
                    "donor_station_id": spec["donor_station"],
                    "daily_rows": len(daily),
                    "event_rows": len(events),
                },
                status_path,
            )
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            invocation_skips.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "training_seed": None,
                    "reason_code": "donor_falsification_unit_failed",
                    "reason": str(error),
                }
            )
            _atomic_json(
                {
                    "status": "failed",
                    "scenario_id": scenario.scenario_id,
                    "reason": str(error),
                },
                status_path,
            )

    daily_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    completed_keys: list[str] = []
    for scenario in grid.scenarios:
        unit = output / "units" / scenario.scenario_id / "donor_regression"
        daily_path = unit / "daily_predictions.parquet"
        event_path = unit / "event_metrics.parquet"
        if daily_path.is_file() and event_path.is_file():
            daily_parts.append(pd.read_parquet(daily_path))
            event_parts.append(pd.read_parquet(event_path))
            completed_keys.append(f"{scenario.scenario_id}|donor_regression:none")
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    events = (
        pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    )
    skipped = pd.DataFrame(invocation_skips)
    _atomic_parquet(daily, output / "daily_predictions.parquet")
    _atomic_parquet(events, output / "event_metrics.parquet")
    _atomic_csv(skipped, output / "skipped_runs.csv")
    expected_keys = sorted(
        f"{scenario.scenario_id}|donor_regression:none" for scenario in grid.scenarios
    )
    completed_keys = sorted(set(completed_keys))
    complete = completed_keys == expected_keys
    if not events.empty and {"contrast", "skill"}.issubset(events.columns):
        summary = events.groupby(
            ["contrast", "lag_days"], dropna=False, as_index=False
        ).agg(skill_gain=("skill", "mean"))
        interpretation = interpret_falsification(summary)
    else:
        interpretation = {"status": "incomplete"}
    _atomic_json(interpretation, output / "donor_falsification_interpretation.json")
    exact = {
        "expected_run_unit_keys": expected_keys,
        "completed_run_unit_keys": completed_keys,
        "retryable_run_unit_keys": sorted(set(expected_keys) - set(completed_keys)),
        "structural_skip_run_unit_keys": [],
        "expected_evidence_run_unit_keys": expected_keys,
        "completed_evidence_run_unit_keys": completed_keys,
        "finite_prediction_run_unit_keys": completed_keys,
        "finite_event_metric_run_unit_keys": completed_keys,
        "checkpoint_required_run_unit_keys": [],
        "checkpoint_valid_run_unit_keys": [],
    }
    counts = {
        f"{key.removesuffix('_keys')}_count": len(value) for key, value in exact.items()
    }
    manifest = {
        "schema_version": "donor_c_falsification_run_v1",
        "suite": SUITE,
        "models": ["donor_regression"],
        "expected_formal_models": ["donor_regression"],
        "component_estimator": "donor_regression",
        "status": "complete" if complete else "partial",
        "complete": complete,
        "formal_design_complete": complete,
        "formal_mask_seed_complete": set(grid.mask_seeds) == set(range(101, 121)),
        "run_unit_complete": complete,
        "evidence_complete": complete,
        "finite_predictions": complete,
        "finite_event_metrics": complete,
        "retryable_run_keys": exact["retryable_run_unit_keys"],
        **exact,
        **counts,
        "completed_daily_rows": len(daily),
        "completed_event_rows": len(events),
        "daily_rows": len(daily),
        "event_rows": len(events),
        "training_profile": runner.training_profile_name,
        "data_version": runner.data.data_version,
        "evaluation_split": runner.evaluation_split,
        "formal_evidence": complete,
        "evidence_role": "formal_development_evaluation",
        "formal_execution_authorization": runner.formal_authorization,
        "interpretation": interpretation,
        **runner.evidence_contract,
    }
    _atomic_json(manifest, output / "run_manifest.json")
    return daily, events, skipped


def run_donor_falsification(
    *,
    finalized_model_roster_path: str | Path,
    selection_data_version_manifest_path: str | Path,
    checkpoint_dir: str | Path,
    manifest_path: str | Path = "study_manifest.yaml",
    config_path: str | Path = "configs/experiments.yaml",
    design_path: str | Path = "configs/design_freeze_v4.yaml",
    data_version_manifest_path: str | Path | None = None,
    wide_path: str | Path = "data_versions/published_v2/daily_wide.parquet",
    quality_path: str | Path = "data_versions/published_v2/daily_long.parquet",
    output_dir: str | Path = "results/science_experiments/donor_falsification",
    mask_dir: str | Path = "masks/science_donor_falsification",
    training_seeds: Sequence[int] | None = None,
    mask_seeds: Sequence[int] | None = None,
    data_version: str = "published_v2",
    evaluation_split: str = "development_test",
    frontier_anchor_path: str | Path | None = "metadata/frontier_anchors_v2.csv",
    max_scenarios: int | None = None,
    device: str = "cpu",
    estimator: str = "donor_regression",
    resume: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Execute or resume the complete target–donor–contrast formal suite."""

    estimator_name = str(estimator).strip().lower()
    if estimator_name == "donor_regression":
        return _run_donor_regression_falsification(
            finalized_model_roster_path=finalized_model_roster_path,
            selection_data_version_manifest_path=selection_data_version_manifest_path,
            manifest_path=manifest_path,
            config_path=config_path,
            design_path=design_path,
            data_version_manifest_path=data_version_manifest_path,
            wide_path=wide_path,
            quality_path=quality_path,
            output_dir=output_dir,
            mask_dir=mask_dir,
            mask_seeds=mask_seeds,
            data_version=data_version,
            evaluation_split=evaluation_split,
            frontier_anchor_path=frontier_anchor_path,
            max_scenarios=max_scenarios,
            resume=resume,
        )
    if estimator_name != "proposed":
        raise ValueError(
            "donor falsification estimator must be donor_regression or proposed"
        )

    output = Path(output_dir)
    roster, authorization = authorize_proposed_estimand(
        finalized_model_roster_path,
        suite=SUITE,
        design_path=design_path,
        study_manifest_path=manifest_path,
        experiment_config_path=config_path,
        selection_data_version_manifest_path=selection_data_version_manifest_path,
    )
    if authorization is None:
        manifest = {
            "schema_version": "donor_c_falsification_run_v1",
            "suite": SUITE,
            "status": "not_applicable",
            "complete": False,
            "formal_design_complete": False,
            "not_applicable_reason": "proposed validation decision is framework_only",
            "formal_evidence": False,
            "evidence_role": "not_applicable",
            "models": ["proposed"],
            "expected_formal_models": [],
            "data_version": data_version,
            "evaluation_split": evaluation_split,
            "finalized_model_roster": {
                "path": roster.manifest_path,
                "selected_models": list(roster.selected_models),
                "proposed_decision": roster.proposed_decision,
            },
        }
        _atomic_json(manifest, output / "run_manifest.json")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    grid, specs = build_donor_falsification_grid(
        manifest_path,
        mask_seeds=mask_seeds,
        data_version=data_version,
        evaluation_split=evaluation_split,
        frontier_anchor_path=frontier_anchor_path,
    )
    selected_seeds = _compensation_training_seeds(grid, training_seeds, None)
    checkpoints = _compensation_checkpoint_files(
        grid,
        selected_seeds,
        checkpoint_path=None,
        checkpoint_dir=checkpoint_dir,
        checkpoint_template="proposed-S{seed}-W{window}-{protocol}.pt",
    )
    runner = ExperimentRunner(
        grid,
        wide_path=wide_path,
        quality_path=quality_path,
        output_dir=output,
        mask_dir=mask_dir,
        config_path=config_path,
        design_path=design_path,
        manifest_path=manifest_path,
        data_version_manifest_path=data_version_manifest_path,
        models=("proposed",),
        training_seeds=selected_seeds,
        formal_authorization=authorization,
        resume=resume,
    )
    windows = {condition.window_length for condition in grid.conditions}
    protocols = {condition.training_protocol for condition in grid.conditions}
    if len(windows) != 1 or len(protocols) != 1:
        raise ValueError("donor-C suite requires one checkpoint window/protocol")
    window = next(iter(windows))
    protocol = next(iter(protocols))
    loaded = {
        seed: _load_compensation_checkpoint(
            checkpoints[seed],
            runner,
            training_seed=seed,
            window_length=window,
            training_protocol=protocol,
            device=device,
        )
        for seed in selected_seeds
    }
    target_index = runner.data.variable_names.index("T")
    climatology_by_station = {
        station: training_doy_climatology(
            runner.data.dates,
            runner.data.values[:, station, target_index],
            runner.train_rows,
            runner.data.quality_approved[:, station, target_index],
        )
        for station in range(len(runner.data.station_ids))
    }
    selected_scenarios = grid.scenarios
    if max_scenarios is not None:
        if max_scenarios < 1:
            raise ValueError("max_scenarios must be positive")
        selected_scenarios = selected_scenarios[:max_scenarios]
    invocation_skips: list[dict[str, Any]] = []
    for scenario in selected_scenarios:
        spec = specs[scenario.condition.condition_id]
        for seed, (model, mean, scale) in loaded.items():
            unit = output / "units" / scenario.scenario_id / f"S{seed}"
            status_path = unit / "status.json"
            daily_path = unit / "daily_predictions.parquet"
            event_path = unit / "event_metrics.parquet"
            if (
                resume
                and status_path.is_file()
                and daily_path.is_file()
                and event_path.is_file()
            ):
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    if status.get("status") == "complete":
                        continue
                except (OSError, json.JSONDecodeError):
                    pass
            try:
                daily, events = _score_unit(
                    runner,
                    scenario,
                    spec,
                    seed,
                    model,
                    mean,
                    scale,
                    climatology_by_station,
                    device=device,
                )
                _atomic_parquet(daily, daily_path)
                _atomic_parquet(events, event_path)
                _atomic_json(
                    {
                        "status": "complete",
                        "scenario_id": scenario.scenario_id,
                        "training_seed": seed,
                        "contrast": spec["contrast"],
                        "donor_station_id": spec["donor_station"],
                        "daily_rows": len(daily),
                        "event_rows": len(events),
                    },
                    status_path,
                )
            except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
                invocation_skips.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "training_seed": seed,
                        "reason_code": "donor_falsification_unit_failed",
                        "reason": str(error),
                    }
                )
                _atomic_json(
                    {
                        "status": "failed",
                        "scenario_id": scenario.scenario_id,
                        "training_seed": seed,
                        "reason": str(error),
                    },
                    status_path,
                )

    daily_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    completed_keys: list[str] = []
    for scenario in grid.scenarios:
        for seed in grid.training_seeds:
            unit = output / "units" / scenario.scenario_id / f"S{seed}"
            daily_path = unit / "daily_predictions.parquet"
            event_path = unit / "event_metrics.parquet"
            if daily_path.is_file() and event_path.is_file():
                daily_parts.append(pd.read_parquet(daily_path))
                event_parts.append(pd.read_parquet(event_path))
                completed_keys.append(f"{scenario.scenario_id}|proposed:{seed}")
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    events = (
        pd.concat(event_parts, ignore_index=True) if event_parts else pd.DataFrame()
    )
    skipped = pd.DataFrame(invocation_skips)
    _atomic_parquet(daily, output / "daily_predictions.parquet")
    _atomic_parquet(events, output / "event_metrics.parquet")
    _atomic_csv(skipped, output / "skipped_runs.csv")
    expected_keys = sorted(
        f"{scenario.scenario_id}|proposed:{seed}"
        for scenario in grid.scenarios
        for seed in grid.training_seeds
    )
    completed_keys = sorted(set(completed_keys))
    complete = completed_keys == expected_keys
    checkpoint_rows = []
    for seed, checkpoint in checkpoints.items():
        if seed not in loaded:
            continue
        artifact = _checkpoint_artifact_identity(checkpoint)
        checkpoint_rows.append(
            {
                "model": "proposed",
                "training_seed": seed,
                "checkpoint": {
                    "path": str(checkpoint.resolve()),
                    "size": artifact["size"],
                    "sha256": artifact["sha256"],
                },
                "checkpoint_sidecar": None,
                "checkpoint_contract_valid": True,
            }
        )
    exact = {
        "expected_run_unit_keys": expected_keys,
        "completed_run_unit_keys": completed_keys,
        "retryable_run_unit_keys": sorted(set(expected_keys) - set(completed_keys)),
        "structural_skip_run_unit_keys": [],
        "expected_evidence_run_unit_keys": expected_keys,
        "completed_evidence_run_unit_keys": completed_keys,
        "finite_prediction_run_unit_keys": completed_keys,
        "finite_event_metric_run_unit_keys": completed_keys,
        "checkpoint_required_run_unit_keys": expected_keys,
        "checkpoint_valid_run_unit_keys": (
            expected_keys if set(loaded) == set(grid.training_seeds) else []
        ),
    }
    counts = {
        f"{key.removesuffix('_keys')}_count": len(value) for key, value in exact.items()
    }
    counts["checkpoint_required_run_count"] = counts.pop(
        "checkpoint_required_run_unit_count"
    )
    counts["checkpoint_valid_run_count"] = counts.pop("checkpoint_valid_run_unit_count")
    manifest = {
        "schema_version": "donor_c_falsification_run_v1",
        "suite": SUITE,
        "models": ["proposed"],
        "expected_formal_models": ["proposed"],
        "status": "complete" if complete else "partial",
        "complete": complete,
        "formal_design_complete": complete,
        "formal_training_seed_complete": set(loaded) == set(grid.training_seeds),
        "formal_mask_seed_complete": set(grid.mask_seeds) == set(range(101, 121)),
        "run_unit_complete": complete,
        "evidence_complete": complete,
        "finite_predictions": complete,
        "finite_event_metrics": complete,
        "checkpoint_contract_complete": set(loaded) == set(grid.training_seeds),
        "retryable_run_keys": exact["retryable_run_unit_keys"],
        **exact,
        **counts,
        "completed_daily_rows": len(daily),
        "completed_event_rows": len(events),
        "daily_rows": len(daily),
        "event_rows": len(events),
        "training_checkpoints": checkpoint_rows,
        "training_profile": runner.training_profile_name,
        "data_version": runner.data.data_version,
        "data_version_input_identity": runner.data_version_input_identity,
        "evaluation_split": runner.evaluation_split,
        "frontier_anchor_catalog_path": grid.frontier_anchor_catalog_path,
        "frontier_anchor_catalog_sha256": grid.frontier_anchor_catalog_sha256,
        "frontier_anchor_count": grid.frontier_anchor_count,
        "formal_grid_contract_complete": runner.formal_grid_contract is not None,
        "formal_grid_contract": runner.formal_grid_contract,
        "formal_evidence": complete,
        "evidence_role": "formal_development_evaluation",
        "formal_execution_authorization": runner.formal_authorization,
        "finalized_model_roster": {
            "path": roster.manifest_path,
            "sha256": roster.manifest_sha256,
            "selected_models": list(roster.selected_models),
            "proposed_decision": roster.proposed_decision,
        },
        **runner.evidence_contract,
        "code_provenance": runner.code_provenance,
    }
    _atomic_json(manifest, output / "run_manifest.json")
    return daily, events, skipped


__all__ = [
    "EXPERIMENT",
    "SUITE",
    "build_donor_falsification_grid",
    "run_donor_falsification",
    "transform_donor_values",
]
