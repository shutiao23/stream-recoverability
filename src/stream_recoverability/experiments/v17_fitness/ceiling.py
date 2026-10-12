"""Step 4 — ceiling analysis. The gate the v16 programme skipped.

Before any decision rule is fit, measure how much a rule with perfect foresight
could win inside each candidate action space, and compare that ceiling with the
resolution the confirmation experiment will actually have. If the ceiling is
smaller than a few times the resolvable margin, the action space is not a
decision problem and must not be studied as one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.paths import (
    NATURAL_SCALE_C,
    PRIMARY_TOLERANCE_C,
    TOLERANCES_C,
)
from stream_recoverability.experiments.v17_fitness.stats import (
    network_equal_mean,
    resolvable_margin,
)

RETENTION_GRID = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def mean_benefit_ceilings(cases: pd.DataFrame) -> pd.DataFrame:
    """Action spaces whose endpoint is the mean benefit over the named default."""

    rows = []
    specs = [
        ("deployed information-conditioned policy", "bq_policy"),
        ("oracle adopt/reject of that policy", "bq_adopt_reject"),
        ("oracle choice among reconstruction methods", "bq_oracle_method"),
    ]
    base = network_equal_mean(cases, "bq_policy")
    for label, column in specs:
        value = network_equal_mean(cases, column)
        rows.append(
            {
                "action_space": label,
                "network_equal_mean_bq_c": value,
                "headroom_over_deployed_c": value - base,
                "headroom_in_natural_sd": (value - base) / NATURAL_SCALE_C,
            }
        )
    return pd.DataFrame(rows)


def retention_ceiling(
    cases: pd.DataFrame,
    *,
    error_column: str = "abserr_policy",
    tolerance: float = PRIMARY_TOLERANCE_C,
    grid=RETENTION_GRID,
) -> pd.DataFrame:
    """Action space whose endpoint is the consequential-error rate among retained."""

    errors = pd.to_numeric(cases[error_column], errors="coerce").to_numpy(dtype=float)
    finite = np.isfinite(errors)
    errors = errors[finite]
    order = np.argsort(errors, kind="mergesort")
    rows = []
    for retention in grid:
        k = max(1, int(round(float(retention) * len(errors))))
        kept = errors[order[:k]]
        rows.append(
            {
                "retention": float(retention),
                "oracle_rate_above_tolerance": float((kept > tolerance).mean()),
                "oracle_mean_abs_error_c": float(kept.mean()),
                "retain_all_rate_above_tolerance": float((errors > tolerance).mean()),
                "retain_all_mean_abs_error_c": float(errors.mean()),
            }
        )
    frame = pd.DataFrame(rows)
    frame["headroom_rate_points"] = (
        frame["retain_all_rate_above_tolerance"] - frame["oracle_rate_above_tolerance"]
    ) * 100.0
    frame["tolerance_c"] = float(tolerance)
    return frame


def between_network_sd(cases: pd.DataFrame, column: str) -> float:
    per_network = cases.groupby("network_id")[column].mean()
    return float(per_network.std(ddof=1))


def confirmation_resolution(cases: pd.DataFrame, n_reserved_networks: int) -> pd.DataFrame:
    """What margin can the reserved panel actually resolve, per endpoint?"""

    rows = []
    for label, column, unit in [
        ("mean benefit B_q", "bq_policy", "deg C"),
        ("absolute metric error", "abserr_policy", "deg C"),
        ("indicator error > 0.5 C", "_above_tol", "rate"),
    ]:
        frame = cases.copy()
        if column == "_above_tol":
            frame[column] = (pd.to_numeric(frame["abserr_policy"], errors="coerce") > PRIMARY_TOLERANCE_C).astype(float)
        sd = between_network_sd(frame, column)
        rows.append(
            {
                "endpoint": label,
                "unit": unit,
                "between_network_sd": sd,
                "resolvable_margin_reserved": resolvable_margin(sd, int(n_reserved_networks)),
                "n_reserved_networks": int(n_reserved_networks),
            }
        )
    return pd.DataFrame(rows)


def gate_decision(mean_table: pd.DataFrame, retention_table: pd.DataFrame, resolution: pd.DataFrame) -> dict:
    """Proceed only with action spaces whose ceiling clears three times resolution."""

    bq_margin = float(
        resolution.loc[resolution["endpoint"].eq("mean benefit B_q"), "resolvable_margin_reserved"].iloc[0]
    )
    rate_margin = float(
        resolution.loc[resolution["endpoint"].eq("indicator error > 0.5 C"), "resolvable_margin_reserved"].iloc[0]
    )
    adopt = float(
        mean_table.loc[mean_table["action_space"].str.contains("adopt/reject"), "headroom_over_deployed_c"].iloc[0]
    )
    method = float(
        mean_table.loc[mean_table["action_space"].str.contains("among reconstruction"), "headroom_over_deployed_c"].iloc[0]
    )
    at_seventy = retention_table.loc[retention_table["retention"].eq(0.7)]
    retention_headroom = float(at_seventy["headroom_rate_points"].iloc[0]) / 100.0

    return {
        "resolvable_margin_bq_c": bq_margin,
        "resolvable_margin_rate": rate_margin,
        "gate_multiple": 3.0,
        "adopt_reject": {
            "ceiling_c": adopt,
            "required_c": 3.0 * bq_margin,
            "passes": bool(adopt > 3.0 * bq_margin),
        },
        "method_selection": {
            "ceiling_c": method,
            "required_c": 3.0 * bq_margin,
            "passes": bool(method > 3.0 * bq_margin),
        },
        "retain_exclude": {
            "ceiling_rate": retention_headroom,
            "required_rate": 3.0 * rate_margin,
            "passes": bool(retention_headroom > 3.0 * rate_margin),
        },
    }


def tolerance_table(cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in ("observed_days", "doy_climatology", "policy", "oracle_method"):
        column = f"abserr_{name}"
        if column not in cases.columns:
            continue
        values = pd.to_numeric(cases[column], errors="coerce")
        row = {"estimator": name, "availability": float(values.notna().mean()), "mean_abs_error_c": float(values.mean())}
        for tolerance in TOLERANCES_C:
            row[f"rate_above_{tolerance}"] = float((values > tolerance).mean())
        row["mean_error_in_natural_sd"] = float(values.mean() / NATURAL_SCALE_C)
        rows.append(row)
    return pd.DataFrame(rows)
