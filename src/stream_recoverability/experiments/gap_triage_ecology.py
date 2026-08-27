"""Ecological bridge for T3(b): operator vs length-only safe-fill bias on annual metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.science_record import _annual
from stream_recoverability.experiments.gap_triage import (
    compare_operator_to_length_only,
    freeze_triage_thresholds,
    safe_fill_fraction,
)
from stream_recoverability.experiments.public_river_operator_ablation import (
    MIN_TRAIN_COMPLETE_FOR_OPERATOR,
    W2_PRIMARY_NETWORKS,
    _prune_donors_for_complete_cases,
    _usable_donor_indices,
    load_public_river_panels,
)
from stream_recoverability.experiments.real_river_checks import year_split


def _plant_index(wide: pd.DataFrame, plant_start: object) -> int | None:
    """Map W2 ``plant_start`` ISO date to a row index in the panel."""

    if plant_start is None or (isinstance(plant_start, float) and not np.isfinite(plant_start)):
        return None
    plant_ts = pd.Timestamp(plant_start)
    loc = wide.index.get_indexer([plant_ts], method=None)
    if int(loc[0]) < 0:
        return None
    return int(loc[0])


def _seven_day_adm(values: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.DataFrame({"date": dates, "value": values})
    frame["roll7_max"] = (
        frame["value"].rolling(window=7, min_periods=7).max().to_numpy(dtype=float)
    )
    grouped = frame.groupby(frame["date"].dt.year)["roll7_max"]
    return pd.DataFrame(
        {
            "year": grouped.max().index.astype(int),
            "seven_day_adm": grouped.max().to_numpy(dtype=float),
        }
    )


def ecological_bridge_for_scores(
    scores: pd.DataFrame,
    panels: dict[str, pd.DataFrame],
    *,
    freeze: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bias on annual max, amplitude, and 7DADM for declared-safe fills only."""

    thresholds = freeze_triage_thresholds(freeze)
    triage = compare_operator_to_length_only(scores, freeze=freeze)
    operator_threshold = triage["operator"]["threshold"]
    length_threshold = triage["length_only"]["threshold"]
    rows: list[dict[str, Any]] = []
    for row in scores.itertuples(index=False):
        network = str(row.network_id)
        if network not in panels:
            continue
        wide = panels[network]
        station_id = str(row.station_id)
        if station_id not in wide.columns:
            continue
        target = int(wide.columns.get_loc(station_id))
        values = wide.to_numpy(dtype=float)
        index = pd.DatetimeIndex(wide.index)
        train, test = year_split(index)
        gap = int(row.gap_length)
        plant = _plant_index(wide, getattr(row, "plant_start", None))
        if plant is None:
            continue
        in_gap = np.zeros(len(index), dtype=bool)
        in_gap[plant : plant + gap] = True
        fill_train = train & ~in_gap
        donors = _usable_donor_indices(values, target, train)
        donors = _prune_donors_for_complete_cases(
            values,
            fill_train,
            target,
            donors,
            min_complete=MIN_TRAIN_COMPLETE_FOR_OPERATOR,
        )
        if not donors:
            continue
        y = values[:, target].copy()
        x_train = np.column_stack([np.ones(int(fill_train.sum())), values[fill_train][:, donors]])
        y_train = y[fill_train]
        valid = np.isfinite(y_train) & np.isfinite(x_train).all(axis=1)
        if int(valid.sum()) < x_train.shape[1] + 1:
            continue
        coef = np.linalg.lstsq(x_train[valid], y_train[valid], rcond=None)[0]
        x_gap = np.column_stack([np.ones(int(in_gap.sum())), values[in_gap][:, donors]])
        pred = x_gap @ coef
        filled = y.copy()
        filled[in_gap] = pred
        true_annual = _annual(y, index)
        fill_annual = _annual(filled, index)
        true_7 = _seven_day_adm(y, index)
        fill_7 = _seven_day_adm(filled, index)
        merged = true_annual.merge(fill_annual, on="year", suffixes=("_true", "_fill"))
        merged = merged.merge(
            true_7.rename(columns={"seven_day_adm": "seven_day_adm_true"}),
            on="year",
        ).merge(
            fill_7.rename(columns={"seven_day_adm": "seven_day_adm_fill"}),
            on="year",
        )
        risk = float(row.predicted_conditional_risk)
        operator_safe = np.isfinite(operator_threshold) and risk <= float(operator_threshold)
        length_safe = np.isfinite(length_threshold) and gap <= float(length_threshold)
        for policy, safe in (
            ("operator", operator_safe),
            ("length_only", length_safe),
        ):
            if not safe:
                continue
            rows.append(
                {
                    "network_id": network,
                    "station_id": str(row.station_id),
                    "gap_length": gap,
                    "policy": policy,
                    "annual_max_bias_c": float(
                        np.mean(np.abs(merged["max_fill"] - merged["max_true"]))
                    ),
                    "annual_amplitude_bias_c": float(
                        np.mean(np.abs(merged["amplitude_fill"] - merged["amplitude_true"]))
                    ),
                    "seven_day_adm_bias_c": float(
                        np.mean(
                            np.abs(
                                merged["seven_day_adm_fill"] - merged["seven_day_adm_true"]
                            )
                        )
                    ),
                }
            )
    frame = pd.DataFrame(rows)
    summary = {}
    for policy in ("operator", "length_only"):
        if frame.empty or "policy" not in frame.columns:
            summary[policy] = {
                "n_safe_fills": 0,
                "mean_annual_max_bias_c": float("nan"),
                "mean_annual_amplitude_bias_c": float("nan"),
                "mean_seven_day_adm_bias_c": float("nan"),
            }
            continue
        piece = frame.loc[frame["policy"].eq(policy)]
        summary[policy] = {
            "n_safe_fills": int(len(piece)),
            "mean_annual_max_bias_c": float(piece["annual_max_bias_c"].mean())
            if not piece.empty
            else float("nan"),
            "mean_annual_amplitude_bias_c": float(
                piece["annual_amplitude_bias_c"].mean()
            )
            if not piece.empty
            else float("nan"),
            "mean_seven_day_adm_bias_c": float(piece["seven_day_adm_bias_c"].mean())
            if not piece.empty
            else float("nan"),
        }
    return {
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "n_fills_scored": int(len(scores)),
        "n_safe_rows": int(len(frame)),
        "policy_summary": summary,
        "rows": frame.to_dict(orient="records"),
        "purpose": "t3b_ecological_bridge_not_confirmatory",
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def run_ecological_bridge(
    *,
    scores_path: Path,
    panels_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    scores = pd.read_csv(scores_path)
    panels = load_public_river_panels(panels_root)
    panels = {name: panels[name] for name in W2_PRIMARY_NETWORKS if name in panels}
    payload = ecological_bridge_for_scores(scores, panels)
    output_dir.mkdir(parents=True, exist_ok=True)
    if payload["rows"]:
        pd.DataFrame(payload["rows"]).to_csv(
            output_dir / "ecological_bridge_rows.csv", index=False
        )
    (output_dir / "ecological_bridge.json").write_text(
        json.dumps(_jsonable({k: v for k, v in payload.items() if k != "rows"}), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return payload


__all__ = ["ecological_bridge_for_scores", "run_ecological_bridge"]
