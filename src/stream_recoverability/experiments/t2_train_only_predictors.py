"""Build the outcome-blind T2 operator and four-baseline predictor sidecar.

The sidecar reads only the open-role QC panels inventoried by the frozen T2
workload.  Every network is fit on its first 70% of calendar years.  No planted
gap outcome, recovery-model result, or sealed temperature path is accepted by
this module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.conditional_observability import (
    ridge_psd,
    spectral_radius,
    stationary_covariance,
    var1_gap_conditional_risk,
)
from stream_recoverability.experiments.recoverability_baselines import (
    acf_only,
    additive_heuristic,
    donor_r2_only,
    gap_length_only,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    discover_failure_closure_networks,
    read_panel,
)
from stream_recoverability.experiments.t2_result_aggregation import (
    PREDICTOR_SCHEMA,
    input_inventory_sha256,
)

FROZEN_GAPS = (7, 14, 30, 60, 90, 180, 365)
JOIN_KEYS = ("network_id", "station_id", "gap_length")
PREDICTOR_COLUMNS = (
    "predicted_conditional_risk",
    "gap_length_only",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
)
SIDECAR_SCHEMA = PREDICTOR_SCHEMA
ESTIMATOR_ID = "train70_doy_anomaly_var1_kalman_rts_B_union_D_v1"
MIN_DONOR_OVERLAP = 365
MIN_VAR_PAIRS = 365
STABILITY_RADIUS = 0.98


class PredictorContractError(ValueError):
    """Raised when an input could cross the frozen outcome/custody boundary."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _refuse_sealed_path(path: Path) -> None:
    if any("sealed" in part.lower() for part in path.resolve().parts):
        raise PredictorContractError(f"refusing a sealed-path predictor input: {path}")


def _year_split(index: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    years = np.asarray(sorted(pd.unique(index.year)), dtype=int)
    if years.size < 2:
        raise PredictorContractError("train-only predictors require at least two years")
    cut = min(years.size - 1, max(1, round(years.size * 0.7)))
    train_years = set(years[:cut].tolist())
    train = np.asarray([int(year) in train_years for year in index.year], dtype=bool)
    return train, ~train


def _train_doy_anomalies(panel: pd.DataFrame, train: np.ndarray) -> np.ndarray:
    """Return anomalies for train rows without consulting later-year values."""

    values = panel.to_numpy(dtype=float)
    train_values = values[train]
    train_doy = panel.index.dayofyear.to_numpy()[train]
    anomalies = np.full_like(train_values, np.nan, dtype=float)
    fallback = np.asarray(
        [
            float(np.mean(column[np.isfinite(column)]))
            if np.isfinite(column).any()
            else float("nan")
            for column in train_values.T
        ]
    )
    for day in np.unique(train_doy):
        rows = train_doy == day
        day_values = train_values[rows]
        means = np.asarray(
            [
                float(np.mean(column[np.isfinite(column)]))
                if np.isfinite(column).any()
                else float("nan")
                for column in day_values.T
            ]
        )
        means = np.where(np.isfinite(means), means, fallback)
        anomalies[rows] = day_values - means
    return anomalies


def _year_block_cv_r2(
    target: np.ndarray,
    donors: Sequence[np.ndarray],
    years: np.ndarray,
) -> float:
    """Leave-one-train-year-out R2, skipping folds with no complete test row."""

    y = np.asarray(target, dtype=float)
    donor_matrix = np.column_stack([np.asarray(value, dtype=float) for value in donors])
    residual = 0.0
    total = 0.0
    n_folds = 0
    for held in sorted(pd.unique(years)):
        fit = years != held
        test = years == held
        x_fit = np.column_stack([np.ones(int(fit.sum())), donor_matrix[fit]])
        x_test = np.column_stack([np.ones(int(test.sum())), donor_matrix[test]])
        fit_ok = np.isfinite(y[fit]) & np.isfinite(x_fit).all(axis=1)
        test_ok = np.isfinite(y[test]) & np.isfinite(x_test).all(axis=1)
        if int(fit_ok.sum()) < x_fit.shape[1] + 1 or int(test_ok.sum()) < 2:
            continue
        observed = y[test][test_ok]
        fold_total = float(np.square(observed - observed.mean()).sum())
        if fold_total <= 0:
            continue
        coefficients = np.linalg.lstsq(x_fit[fit_ok], y[fit][fit_ok], rcond=None)[0]
        predicted = x_test[test_ok] @ coefficients
        residual += float(np.square(observed - predicted).sum())
        total += fold_total
        n_folds += 1
    if n_folds < 2 or total <= 0:
        return float("nan")
    return float(np.clip(1.0 - residual / total, 0.0, 1.0))


def _lag_correlation(values: np.ndarray, lag: float) -> float:
    effective = max(1.0, float(lag))

    def at(integer_lag: int) -> float:
        if values.size <= integer_lag:
            return float("nan")
        left = values[:-integer_lag]
        right = values[integer_lag:]
        valid = np.isfinite(left) & np.isfinite(right)
        if int(valid.sum()) < 3:
            return float("nan")
        if float(np.std(left[valid])) == 0 or float(np.std(right[valid])) == 0:
            return float("nan")
        return float(np.corrcoef(left[valid], right[valid])[0, 1])

    lower = int(np.floor(effective))
    upper = int(np.ceil(effective))
    low = at(lower)
    if lower == upper:
        return low
    high = at(upper)
    if not np.isfinite(low) or not np.isfinite(high):
        return float("nan")
    weight = effective - lower
    return float((1.0 - weight) * low + weight * high)


def _eligible_donors(anomalies: np.ndarray, target: int) -> list[int]:
    target_ok = np.isfinite(anomalies[:, int(target)])
    return [
        donor
        for donor in range(anomalies.shape[1])
        if donor != int(target)
        and int((target_ok & np.isfinite(anomalies[:, donor])).sum())
        >= MIN_DONOR_OVERLAP
    ]


def _fit_var1(
    anomalies: np.ndarray,
    train_dates: pd.DatetimeIndex,
    target: int,
    donors: Sequence[int],
) -> tuple[np.ndarray, np.ndarray, list[int], int, bool]:
    """Fit a stable VAR(1), pruning only donors needed for estimability."""

    kept = [int(value) for value in donors]
    while kept:
        columns = [int(target), *kept]
        selected = anomalies[:, columns]
        adjacent = np.asarray(
            (train_dates[1:] - train_dates[:-1]) == pd.Timedelta(days=1), dtype=bool
        )
        valid_pairs = (
            adjacent
            & np.isfinite(selected[:-1]).all(axis=1)
            & np.isfinite(selected[1:]).all(axis=1)
        )
        required = max(MIN_VAR_PAIRS, len(columns) + 2)
        if int(valid_pairs.sum()) >= required:
            break
        if len(kept) == 1:
            kept = []
            break
        kept.remove(
            min(kept, key=lambda value: int(np.isfinite(anomalies[:, value]).sum()))
        )
    if not kept:
        raise PredictorContractError(
            "no donor roster has enough consecutive train-only observations"
        )

    columns = [int(target), *kept]
    selected = anomalies[:, columns]
    adjacent = np.asarray(
        (train_dates[1:] - train_dates[:-1]) == pd.Timedelta(days=1), dtype=bool
    )
    valid_pairs = (
        adjacent
        & np.isfinite(selected[:-1]).all(axis=1)
        & np.isfinite(selected[1:]).all(axis=1)
    )
    previous = selected[:-1][valid_pairs]
    following = selected[1:][valid_pairs]
    transition = np.linalg.lstsq(previous, following, rcond=None)[0].T
    radius = spectral_radius(transition)
    stabilized = bool(radius >= STABILITY_RADIUS)
    if stabilized:
        transition = transition * (STABILITY_RADIUS / max(radius, 1e-12))
    residual = following - previous @ transition.T
    process_noise = ridge_psd(np.cov(residual, rowvar=False), 1e-8)
    sigma = stationary_covariance(transition, process_noise)
    return transition, sigma, kept, int(valid_pairs.sum()), stabilized


def predict_network_panel(
    network_id: str,
    panel: pd.DataFrame,
    *,
    role: str,
    gaps: Sequence[int] = FROZEN_GAPS,
    skip_ineligible: bool = False,
) -> pd.DataFrame:
    """Compute one row per station and frozen gap from train years only."""

    if role not in {"development", "validation"}:
        raise PredictorContractError("predictor role must be development or validation")
    if tuple(int(value) for value in gaps) != FROZEN_GAPS:
        raise PredictorContractError("all seven frozen artificial gaps are required")
    wide = panel.copy()
    if not isinstance(wide.index, pd.DatetimeIndex):
        wide.index = pd.DatetimeIndex(pd.to_datetime(wide.index))
    wide = wide.apply(pd.to_numeric, errors="coerce").sort_index()
    if wide.index.has_duplicates or wide.shape[1] < 2:
        raise PredictorContractError("panel must have unique dates and at least two stations")
    train, _ = _year_split(wide.index)
    train_dates = wide.index[train]
    anomalies = _train_doy_anomalies(wide, train)
    years = train_dates.year.to_numpy()
    rows: list[dict[str, Any]] = []
    attrition: list[dict[str, str]] = []
    for target, station in enumerate(wide.columns.astype(str)):
        try:
            candidates = _eligible_donors(anomalies, target)
            transition, sigma, donors, n_pairs, stabilized = _fit_var1(
                anomalies, train_dates, target, candidates
            )
        except PredictorContractError as error:
            if not skip_ineligible:
                raise
            attrition.append(
                {
                    "network_id": str(network_id),
                    "station_id": str(station),
                    "reason": str(error),
                }
            )
            continue
        local_target = 0
        local_donors = list(range(1, len(donors) + 1))
        target_values = anomalies[:, target]
        donor_values = [anomalies[:, donor] for donor in donors]
        donor_cv = float(_year_block_cv_r2(target_values, donor_values, years))
        phi = float(_lag_correlation(target_values, 1.0))
        if not np.isfinite(donor_cv) or not np.isfinite(phi):
            raise PredictorContractError(
                f"non-finite train-only baseline for {network_id}/{station}"
            )
        donor_cv = float(np.clip(donor_cv, 0.0, 1.0))
        for gap in FROZEN_GAPS:
            rho_d4 = float(_lag_correlation(target_values, float(gap) / 4.0))
            if not np.isfinite(rho_d4):
                raise PredictorContractError(
                    f"non-finite d/4 ACF for {network_id}/{station}/gap_{gap}"
                )
            operator = var1_gap_conditional_risk(
                transition,
                sigma,
                target=local_target,
                donors=local_donors,
                gap_length=int(gap),
            )
            risk = float(operator["predicted_conditional_risk"])
            row = {
                "network_id": str(network_id),
                "station_id": str(station),
                "gap_length": int(gap),
                "predicted_conditional_risk": risk,
                "gap_length_only": gap_length_only(int(gap)),
                "acf_only": acf_only(phi, int(gap)),
                "donor_r2_only": donor_r2_only(donor_cv, int(gap)),
                "additive_d_over_4_heuristic": additive_heuristic(
                    donor_cv, rho_d4
                ),
                "role": role,
                "fit_role": role,
                "estimator_id": ESTIMATOR_ID,
                "train_start": str(train_dates.min().date()),
                "train_end": str(train_dates.max().date()),
                "n_train_years": len(pd.unique(years)),
                "n_var_pairs": n_pairs,
                "n_donors": len(donors),
                "donor_station_ids": "|".join(
                    str(wide.columns[donor]) for donor in donors
                ),
                "donor_r2_year_block_cv_raw": donor_cv,
                "acf1_raw": phi,
                "rho_d_over_4_raw": rho_d4,
                "transition_stabilized": stabilized,
            }
            if not all(np.isfinite(float(row[name])) for name in PREDICTOR_COLUMNS):
                raise PredictorContractError(
                    f"non-finite predictor for {network_id}/{station}/gap_{gap}"
                )
            rows.append(row)
    result = pd.DataFrame(rows)
    if result.duplicated(list(JOIN_KEYS)).any():
        raise PredictorContractError("predictor join keys are not unique")
    result.attrs["station_attrition"] = attrition
    return result


def build_train_only_predictor_sidecar(
    *,
    repo_root: str | Path,
    workload_manifest_path: str | Path,
    design_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build CSV/Parquet plus the aggregation-ready SHA-bound manifest."""

    repo = Path(repo_root).resolve()
    workload_path = Path(workload_manifest_path).resolve()
    design = Path(design_path).resolve()
    output = Path(output_dir).resolve()
    for path in (workload_path, design, output):
        _refuse_sealed_path(path)
    workload = json.loads(workload_path.read_text(encoding="utf-8"))
    workload_sha = _sha256_file(workload_path)
    design_sha = _sha256_file(design)
    if workload.get("manifest_schema") not in {
        "t2_v91_open_role_workload_v2",
        "t2_v91_open_role_workload_v3",
    }:
        raise PredictorContractError("unsupported T2 workload schema")
    if workload.get("design_sha256") != design_sha:
        raise PredictorContractError("workload/design SHA-256 mismatch")
    if workload.get("sealed_temperature_records_read") is not False:
        raise PredictorContractError("workload does not attest sealed outcomes stayed closed")
    if (workload.get("input_inventory") or {}).get("sealed_input_roots_allowed") != []:
        raise PredictorContractError("workload permits sealed input roots")
    if tuple(int(value) for value in (workload.get("tier_1") or {}).get("gaps", ())) != FROZEN_GAPS:
        raise PredictorContractError("workload does not bind all seven frozen gaps")

    networks, discovery = discover_failure_closure_networks(repo)
    expected_ids = [str(value) for value in workload.get("network_ids") or []]
    if set(expected_ids) != {item.network_id for item in networks}:
        raise PredictorContractError("discovered network inventory differs from workload")
    if int(workload.get("n_networks", -1)) != len(networks):
        raise PredictorContractError("workload network count differs from discovery")
    input_map = {item.network_id: item.wide_sha256 for item in networks}
    inventory_sha = input_inventory_sha256(input_map)

    frames: list[pd.DataFrame] = []
    station_attrition: list[dict[str, str]] = []
    for network in networks:
        _refuse_sealed_path(repo / network.wide_path)
        panel = read_panel(repo, network)
        frame = predict_network_panel(
            network.network_id,
            panel,
            role=network.role,
            skip_ineligible=True,
        )
        station_attrition.extend(frame.attrs.get("station_attrition", []))
        frames.append(frame)
    predictions = pd.concat(frames, ignore_index=True)
    eligible_stations = int(
        predictions[["network_id", "station_id"]].drop_duplicates().shape[0]
    )
    expected_rows = eligible_stations * len(FROZEN_GAPS)
    if len(predictions) != expected_rows:
        raise PredictorContractError(
            f"predictor sidecar incomplete: {len(predictions)} of {expected_rows} rows"
        )

    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "train_only_predictors.csv"
    parquet_path = output / "train_only_predictors.parquet"
    predictions.to_csv(csv_path, index=False)
    predictions.to_parquet(parquet_path, index=False)
    attrition_path = output / "predictor_station_attrition.csv"
    pd.DataFrame(
        station_attrition, columns=["network_id", "station_id", "reason"]
    ).to_csv(attrition_path, index=False)
    manifest: dict[str, Any] = {
        "manifest_schema": SIDECAR_SCHEMA,
        "workload_manifest_sha256": workload_sha,
        "design_sha256": design_sha,
        "catalog_split_sha256": (workload.get("input_inventory") or {}).get(
            "catalog_split_sha256"
        ),
        "input_inventory_sha256": inventory_sha,
        "input_sha256_by_network": dict(sorted(input_map.items())),
        "fit_role": "development",
        "fit_role_note": (
            "Reserved aggregation-contract role for any learned calibration; raw "
            "predictors use each open network's own first-70%-years fit window."
        ),
        "network_covariance_fit_scope": "within_network_first_70pct_calendar_years",
        "validation_application": "raw_frozen_formula_no_development_outcome_calibration",
        "learned_calibration": False,
        "calibration_status": "not_fit_raw_predictors_only",
        "trained_on_open_roles_only": True,
        "outcome_rows_read_during_fit": False,
        "recovery_result_rows_read": False,
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "operator_estimator": ESTIMATOR_ID,
        "operator_information_set": "B_union_D",
        "donor_r2_estimator": "leave_one_train_year_out_r2",
        "gaps": list(FROZEN_GAPS),
        "join_keys": list(JOIN_KEYS),
        "predictor_columns": list(PREDICTOR_COLUMNS),
        "n_networks": len(networks),
        "n_stations_inventory": int(sum(item.n_stations for item in networks)),
        "n_stations_predictor_eligible": eligible_stations,
        "n_stations_predictor_ineligible": len(station_attrition),
        "n_rows": len(predictions),
        "roles": discovery.get("roles"),
        "predictions_path": csv_path.name,
        "predictions_format": "csv",
        "predictions_sha256": _sha256_file(csv_path),
        "parquet_path": parquet_path.name,
        "parquet_sha256": _sha256_file(parquet_path),
        "station_attrition_path": attrition_path.name,
        "station_attrition_sha256": _sha256_file(attrition_path),
        "completeness": "complete",
        "formal_evidence": False,
        "purpose": "train_only_predictor_sidecar_not_t2_recovery_evidence",
    }
    manifest_path = output / "predictor_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


__all__ = [
    "ESTIMATOR_ID",
    "FROZEN_GAPS",
    "JOIN_KEYS",
    "PREDICTOR_COLUMNS",
    "PredictorContractError",
    "build_train_only_predictor_sidecar",
    "predict_network_panel",
]
