"""Post-hoc diagnosis of pooled leave-one-ecoregion-out AUC.

This reader operates on already-written frozen OOF predictions.  It does not
refit the regulation panel, rewrite freeze artifacts, or replace the paper
primary pooled AUC.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
from sklearn.metrics import roc_auc_score

REQUIRED_PREDICTION_COLUMNS: tuple[str, ...] = (
    "station_id",
    "AGGECOREGION",
    "upstream_major_dam_2009",
    "oof_probability",
    "held_out_ecoregion",
)
FOLD_TABLE_COLUMNS: tuple[str, ...] = (
    "held_out_ecoregion",
    "n",
    "n_regulated",
    "n_unregulated",
    "base_rate",
    "oof_probability_median",
    "oof_probability_mean",
    "within_fold_auc",
)
FROZEN_PRIMARY_POOLED_AUC = 0.40749601275917063
DIAGNOSIS_LABEL = "post_hoc_metric_diagnosis"
DOES_NOT_REOPEN_FREEZE = True
MECHANISM = (
    "pooled LOEO AUC under heterogeneous group base rates mixes "
    "calibration drift with discrimination"
)
EVIDENCE_ROLE = "post_hoc"


def _require_columns(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_PREDICTION_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"frozen OOF predictions missing columns: {missing}")
    return frame


def _json_number(value: float) -> float | None:
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def within_fold_auc(labels: Sequence[object], scores: Sequence[object]) -> float:
    """Return sklearn ROC AUC, or NaN when ``labels`` has fewer than two classes."""

    y = pd.to_numeric(pd.Series(labels), errors="coerce")
    p = pd.to_numeric(pd.Series(scores), errors="coerce")
    if y.nunique(dropna=True) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


def pooled_oof_auc(predictions: pd.DataFrame) -> float:
    """Pooled sklearn ROC AUC on the full OOF table, or NaN if undefined."""

    data = _require_columns(predictions)
    y = pd.to_numeric(data["upstream_major_dam_2009"], errors="coerce")
    p = pd.to_numeric(data["oof_probability"], errors="coerce")
    if y.nunique(dropna=True) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


def assert_matches_frozen_primary_pooled_auc(auc: float) -> None:
    """Fail closed when a recomputed pooled AUC is not the frozen paper primary."""

    if auc != FROZEN_PRIMARY_POOLED_AUC:
        raise ValueError(
            f"pooled OOF AUC {auc!r} differs from frozen primary "
            f"{FROZEN_PRIMARY_POOLED_AUC!r}"
        )


def fold_auc_table(predictions: pd.DataFrame) -> pd.DataFrame:
    """Per-held-out-ecoregion counts, base rates, score location, and AUC."""

    data = _require_columns(predictions)
    rows: list[dict[str, Any]] = []
    for region, fold in data.groupby("held_out_ecoregion", observed=True):
        labels = pd.to_numeric(fold["upstream_major_dam_2009"], errors="coerce")
        scores = pd.to_numeric(fold["oof_probability"], errors="coerce")
        n = len(fold)
        n_regulated = int((labels == 1).sum())
        n_unregulated = int((labels == 0).sum())
        rows.append(
            {
                "held_out_ecoregion": str(region),
                "n": n,
                "n_regulated": n_regulated,
                "n_unregulated": n_unregulated,
                "base_rate": (n_regulated / n) if n else float("nan"),
                "oof_probability_median": float(scores.median()),
                "oof_probability_mean": float(scores.mean()),
                "within_fold_auc": within_fold_auc(labels, scores),
            }
        )
    table = pd.DataFrame(rows, columns=list(FOLD_TABLE_COLUMNS))
    return table.sort_values(
        "within_fold_auc",
        ascending=False,
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)


def diagnose_loeo_auc(
    predictions: pd.DataFrame,
    *,
    require_frozen_primary: bool = False,
) -> dict[str, Any]:
    """Return a machine-readable post-hoc diagnosis of pooled LOEO AUC."""

    data = _require_columns(predictions)
    folds = fold_auc_table(data)
    defined = folds.loc[folds["within_fold_auc"].notna(), "within_fold_auc"]
    pooled = pooled_oof_auc(data)
    if require_frozen_primary:
        assert_matches_frozen_primary_pooled_auc(pooled)
    if len(folds) >= 2:
        correlation = float(
            folds["base_rate"].corr(folds["oof_probability_median"])
        )
    else:
        correlation = float("nan")
    highest_median = folds.loc[folds["oof_probability_median"].idxmax()]
    lowest_median = folds.loc[folds["oof_probability_median"].idxmin()]
    min_auc_row = folds.loc[defined.idxmin()] if not defined.empty else None
    max_auc_row = folds.loc[defined.idxmax()] if not defined.empty else None
    diagnosis = {
        "schema_version": "regulation_panel_loeo_auc_metric_diagnosis_v1",
        "diagnosis": DIAGNOSIS_LABEL,
        "does_not_reopen_freeze": DOES_NOT_REOPEN_FREEZE,
        "evidence_role": EVIDENCE_ROLE,
        "formal_evidence": False,
        "frozen_primary_pooled_auc": FROZEN_PRIMARY_POOLED_AUC,
        "mechanism": MECHANISM,
        "summary": {
            "n": len(data),
            "n_folds": len(folds),
            "n_defined_within_fold_auc": len(defined),
            "pooled_oof_auc": _json_number(pooled),
            "pooled_oof_auc_matches_frozen_primary": pooled
            == FROZEN_PRIMARY_POOLED_AUC,
        },
        "post_hoc": {
            "mean_within_fold_auc": _json_number(float(defined.mean()))
            if not defined.empty
            else None,
            "median_within_fold_auc": _json_number(float(defined.median()))
            if not defined.empty
            else None,
            "min_within_fold_auc": _json_number(float(defined.min()))
            if not defined.empty
            else None,
            "max_within_fold_auc": _json_number(float(defined.max()))
            if not defined.empty
            else None,
            "min_within_fold_ecoregion": None
            if min_auc_row is None
            else str(min_auc_row["held_out_ecoregion"]),
            "max_within_fold_ecoregion": None
            if max_auc_row is None
            else str(max_auc_row["held_out_ecoregion"]),
            "base_rate_vs_oof_probability_median_pearson_r": _json_number(
                correlation
            ),
            "highest_oof_probability_median_ecoregion": str(
                highest_median["held_out_ecoregion"]
            ),
            "highest_oof_probability_median": _json_number(
                float(highest_median["oof_probability_median"])
            ),
            "lowest_oof_probability_median_ecoregion": str(
                lowest_median["held_out_ecoregion"]
            ),
            "lowest_oof_probability_median": _json_number(
                float(lowest_median["oof_probability_median"])
            ),
            "folds": [
                {
                    column: (
                        _json_number(float(row[column]))
                        if column
                        not in {"held_out_ecoregion", "n", "n_regulated", "n_unregulated"}
                        else (
                            str(row[column])
                            if column == "held_out_ecoregion"
                            else int(row[column])
                        )
                    )
                    for column in FOLD_TABLE_COLUMNS
                }
                for row in folds.to_dict(orient="records")
            ],
        },
    }
    return diagnosis


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        return _json_number(value)
    return value


__all__ = [
    "DIAGNOSIS_LABEL",
    "DOES_NOT_REOPEN_FREEZE",
    "EVIDENCE_ROLE",
    "FOLD_TABLE_COLUMNS",
    "FROZEN_PRIMARY_POOLED_AUC",
    "MECHANISM",
    "REQUIRED_PREDICTION_COLUMNS",
    "assert_matches_frozen_primary_pooled_auc",
    "diagnose_loeo_auc",
    "fold_auc_table",
    "json_safe",
    "pooled_oof_auc",
    "within_fold_auc",
]
