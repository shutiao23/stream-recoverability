"""T3(b) safe-fill triage: operator vs length-only at a fixed false-release rate.

Development diagnostic. Does not license a decision headline. Thresholds are
read from the v9 freeze when present; they are not tuned here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.study_freeze import load_study_freeze

FALSE_RELEASE_RATE = 0.05
FALSE_RELEASE_ERROR_C = 0.5
RELATIVE_IMPROVEMENT_MIN = 0.30
ABSOLUTE_IMPROVEMENT_MIN_PP = 15.0


def freeze_triage_thresholds(freeze: Mapping[str, Any] | None = None) -> dict[str, float]:
    document = freeze if freeze is not None else load_study_freeze()
    spec = (
        (document.get("decision_endpoints") or {}).get("b_gap_triage") or {}
    )
    return {
        "false_release_rate": float(spec.get("false_release_rate", FALSE_RELEASE_RATE)),
        "false_release_error_c": float(FALSE_RELEASE_ERROR_C),
        "safe_fill_relative_improvement_min": float(
            spec.get("safe_fill_relative_improvement_min", RELATIVE_IMPROVEMENT_MIN)
        ),
        "safe_fill_absolute_improvement_min_pp": float(
            spec.get("safe_fill_absolute_improvement_min_pp", ABSOLUTE_IMPROVEMENT_MIN_PP)
        ),
    }


def safe_fill_fraction(
    risk: np.ndarray,
    error: np.ndarray,
    *,
    false_release_rate: float = FALSE_RELEASE_RATE,
    error_threshold_c: float = FALSE_RELEASE_ERROR_C,
) -> dict[str, float]:
    """Largest share declared safe whose false-release rate stays at or below the cap.

    ``risk`` is higher for fills that should not be released. False release means
    a declared-safe fill has absolute error above ``error_threshold_c``.
    """

    score = np.asarray(risk, dtype=float)
    loss = np.asarray(error, dtype=float)
    valid = np.isfinite(score) & np.isfinite(loss)
    score = score[valid]
    loss = loss[valid]
    n = int(len(score))
    empty = {
        "n": float(n),
        "safe_fill_fraction": float("nan"),
        "false_release_rate": float("nan"),
        "n_declared_safe": float("nan"),
        "threshold": float("nan"),
    }
    if n == 0:
        return empty
    best_fraction = 0.0
    best_threshold = float("nan")
    best_fpr = float("nan")
    best_n_safe = 0
    for threshold in np.unique(score):
        declared = score <= float(threshold)
        n_safe = int(declared.sum())
        if n_safe == 0:
            continue
        fpr = float(np.mean(loss[declared] > float(error_threshold_c)))
        if fpr <= float(false_release_rate) and n_safe >= best_n_safe:
            best_fraction = float(n_safe / n)
            best_threshold = float(threshold)
            best_fpr = fpr
            best_n_safe = n_safe
    return {
        "n": float(n),
        "safe_fill_fraction": float(best_fraction),
        "false_release_rate": float(best_fpr) if best_n_safe else float("nan"),
        "n_declared_safe": float(best_n_safe),
        "threshold": best_threshold,
    }


def compare_operator_to_length_only(
    frame: pd.DataFrame,
    *,
    operator_risk_col: str = "predicted_conditional_risk",
    length_col: str = "gap_length",
    error_col: str = "fill_mae",
    freeze: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Operator vs length-only at the freeze false-release cap. Not confirmatory."""

    thresholds = freeze_triage_thresholds(freeze)
    usable = frame.loc[
        np.isfinite(pd.to_numeric(frame.get(operator_risk_col), errors="coerce"))
        & np.isfinite(pd.to_numeric(frame.get(length_col), errors="coerce"))
        & np.isfinite(pd.to_numeric(frame.get(error_col), errors="coerce"))
    ].copy()
    operator = safe_fill_fraction(
        usable[operator_risk_col].to_numpy(dtype=float),
        usable[error_col].to_numpy(dtype=float),
        false_release_rate=thresholds["false_release_rate"],
        error_threshold_c=thresholds["false_release_error_c"],
    )
    length_only = safe_fill_fraction(
        usable[length_col].to_numpy(dtype=float),
        usable[error_col].to_numpy(dtype=float),
        false_release_rate=thresholds["false_release_rate"],
        error_threshold_c=thresholds["false_release_error_c"],
    )
    op_frac = operator["safe_fill_fraction"]
    len_frac = length_only["safe_fill_fraction"]
    absolute_pp = float("nan")
    relative = float("nan")
    if np.isfinite(op_frac) and np.isfinite(len_frac):
        absolute_pp = 100.0 * (float(op_frac) - float(len_frac))
        if float(len_frac) > 0:
            relative = (float(op_frac) - float(len_frac)) / float(len_frac)
        elif float(op_frac) > 0:
            relative = float("inf")
    n_networks = (
        int(usable["network_id"].nunique()) if "network_id" in usable.columns else 0
    )
    passed_numeric = (
        np.isfinite(relative)
        and relative >= thresholds["safe_fill_relative_improvement_min"]
        and absolute_pp >= thresholds["safe_fill_absolute_improvement_min_pp"]
    )
    return {
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "n_fills": int(operator["n"]),
        "n_networks": n_networks,
        "operator": operator,
        "length_only": length_only,
        "absolute_improvement_pp": absolute_pp,
        "relative_improvement": relative,
        "passed_numeric_floors": bool(passed_numeric),
        "passed": False,
        "reason": (
            "numeric_floors_met_but_n_networks_below_confirmatory"
            if passed_numeric
            else "numeric_floors_not_met_or_undefined"
        ),
        "thresholds": thresholds,
        "false_release_definition": "fill_error_gt_0.5_degC",
        "vs": "gap_length_only",
    }


__all__ = [
    "ABSOLUTE_IMPROVEMENT_MIN_PP",
    "FALSE_RELEASE_ERROR_C",
    "FALSE_RELEASE_RATE",
    "RELATIVE_IMPROVEMENT_MIN",
    "compare_operator_to_length_only",
    "freeze_triage_thresholds",
    "safe_fill_fraction",
]
