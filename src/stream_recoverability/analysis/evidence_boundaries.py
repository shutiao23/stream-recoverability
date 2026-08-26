"""Evidence-boundary helpers for overlap-aware inference and valid national metrics.

These functions do not reopen frozen design contracts.  They convert existing
tables into claim-safe outputs: withhold p-values and confidence intervals when
the independent cluster count is below the predeclared minimum, suppress
separated logistic coefficients, and compute fold-comparable discrimination
summaries that do not treat a defective pooled AUC as a valid estimand.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.inference_safeguards import (
    benjamini_hochberg_by_family,
)
from stream_recoverability.analysis.regulation_panel_auc_diagnosis import (
    FROZEN_PRIMARY_POOLED_AUC,
    fold_auc_table,
    pooled_oof_auc,
)

MIN_INDEPENDENT_CLUSTERS = 5
WITHHELD_STATUS = "withheld_insufficient_independent_clusters"
REFERENCE_STATUS = "reference_not_tested"
TESTED_STATUS = "tested"
NEAR_THRESHOLD_MARGIN = 0.05
SEPARATION_ABS_COEF = 10.0
CI_COLUMNS = (
    "raw_frontier_days_ci_lower",
    "raw_frontier_days_ci_upper",
    "monotone_frontier_days_ci_lower",
    "monotone_frontier_days_ci_upper",
    "skill_ci_lower",
    "skill_ci_upper",
    "impact_ci_lower",
    "impact_ci_upper",
    "ci_lower",
    "ci_upper",
)
P_COLUMNS = ("p_value", "p_bh")


def decide_inference_status(
    *,
    n_independent_clusters: int,
    is_reference: bool = False,
    minimum_clusters: int = MIN_INDEPENDENT_CLUSTERS,
) -> str:
    """Return the claim-safe hypothesis status for one contrast."""

    if is_reference:
        return REFERENCE_STATUS
    if int(n_independent_clusters) < int(minimum_clusters):
        return WITHHELD_STATUS
    return TESTED_STATUS


def independent_cluster_count(
    n_hypothesis_clusters: object,
    n_years: object | None = None,
    n_bootstrap_clusters: object | None = None,
) -> int:
    """Return the conservative independent-unit count.

    The inferential unit is a site-year or overlap component, never a nested
    anchor inside a connected mask.  The reported count is the minimum of the
    supplied cluster inventories so a 20-anchor/1-component table cannot be
    treated as n=20.
    """

    values = [n_hypothesis_clusters, n_years, n_bootstrap_clusters]
    finite = []
    for value in values:
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            finite.append(parsed)
    return int(min(finite)) if finite else 0


def withhold_overlap_inference(
    frame: pd.DataFrame,
    *,
    cluster_col: str = "n_hypothesis_clusters",
    year_col: str = "n_years",
    bootstrap_cluster_col: str = "n_bootstrap_clusters",
    family_col: str = "hypothesis_family",
    status_col: str = "hypothesis_status",
    minimum_clusters: int = MIN_INDEPENDENT_CLUSTERS,
    withhold_families: Sequence[str] | None = (
        "frontier_model_vs_climatology",
        "frontier_model_vs_best_simple",
    ),
) -> pd.DataFrame:
    """Withhold p-values and CIs when independent clusters are below the floor.

    Reference rows stay ``reference_not_tested``.  Families outside
    ``withhold_families`` are left unchanged except for the added audit columns.
    Statistical-frontier crossings that depend on a withheld confidence curve
    are cleared; descriptive point frontiers are retained.
    """

    result = frame.copy()
    result["n_independent_clusters"] = [
        independent_cluster_count(
            row[cluster_col] if cluster_col in result else np.nan,
            row[year_col] if year_col in result else np.nan,
            row[bootstrap_cluster_col] if bootstrap_cluster_col in result else np.nan,
        )
        for row in result.to_dict(orient="records")
    ]
    result["minimum_independent_clusters"] = int(minimum_clusters)
    result["inference_claim_allowed"] = False
    families = set(withhold_families or ())
    for position, row in result.iterrows():
        family = str(row.get(family_col, ""))
        if families and family not in families:
            continue
        current_status = str(row.get(status_col, "") or "")
        is_reference = current_status == REFERENCE_STATUS or (
            family == "frontier_model_vs_climatology"
            and str(row.get("model", "")) == "climatology"
        )
        status = decide_inference_status(
            n_independent_clusters=int(row["n_independent_clusters"]),
            is_reference=is_reference,
            minimum_clusters=minimum_clusters,
        )
        result.at[position, status_col] = status
        result.at[position, "inference_claim_allowed"] = status == TESTED_STATUS
        if status != TESTED_STATUS:
            for column in (*P_COLUMNS, *CI_COLUMNS):
                if column in result:
                    result.at[position, column] = np.nan
            if "bh_reject" in result:
                result.at[position, "bh_reject"] = False
            if "bh_finite_hypotheses" in result:
                result.at[position, "bh_finite_hypotheses"] = 0
            if status == WITHHELD_STATUS:
                if "statistical_frontier_days" in result:
                    result.at[position, "statistical_frontier_days"] = np.nan
                if "statistical_frontier_censoring" in result:
                    result.at[position, "statistical_frontier_censoring"] = None
                if "statistical_frontier_status" in result:
                    result.at[position, "statistical_frontier_status"] = (
                        WITHHELD_STATUS
                    )
                result.at[position, "inference_reason"] = (
                    "independent site-year/overlap clusters below "
                    f"{minimum_clusters}; p-values and CIs withheld"
                )
    if (
        family_col in result
        and "p_value" in result
        and families
        and result[family_col].isin(families).any()
    ):
        scoped = result.loc[result[family_col].isin(families)].copy()
        scoped = benjamini_hochberg_by_family(scoped)
        result.loc[scoped.index, ["p_bh", "bh_reject", "bh_finite_hypotheses"]] = (
            scoped[["p_bh", "bh_reject", "bh_finite_hypotheses"]]
        )
        if "bh_family_size" in scoped:
            result.loc[scoped.index, "bh_family_size"] = scoped["bh_family_size"]
    return result


def withhold_node_importance_intervals(
    frame: pd.DataFrame,
    *,
    year_col: str = "n_anchor_years",
    minimum_clusters: int = MIN_INDEPENDENT_CLUSTERS,
) -> pd.DataFrame:
    """Keep descriptive impacts but withhold CIs when years/clusters are few."""

    result = frame.copy()
    years = pd.to_numeric(result.get(year_col, 0), errors="coerce").fillna(0)
    result["n_independent_clusters"] = years.astype(int)
    result["minimum_independent_clusters"] = int(minimum_clusters)
    result["inference_status"] = np.where(
        years >= minimum_clusters, TESTED_STATUS, WITHHELD_STATUS
    )
    result["inference_claim_allowed"] = result["inference_status"].eq(TESTED_STATUS)
    withhold = result["inference_status"].eq(WITHHELD_STATUS)
    for column in ("impact_ci_lower", "impact_ci_upper"):
        if column in result:
            result.loc[withhold, column] = np.nan
    result.loc[withhold, "inference_reason"] = (
        "year/overlap clusters below the predeclared floor; "
        "point estimates remain descriptive only"
    )
    return result


def year_block_mean_interval(
    frame: pd.DataFrame,
    value_col: str,
    *,
    year_col: str,
    n_boot: int,
    seed: int,
    minimum_clusters: int = MIN_INDEPENDENT_CLUSTERS,
) -> tuple[float, float]:
    """Bootstrap a mean by resampling complete year blocks, or withhold."""

    years = [
        group[value_col].to_numpy(dtype=float)
        for _, group in frame.groupby(year_col, dropna=False, observed=True, sort=True)
    ]
    if len(years) < minimum_clusters:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot, dtype=float)
    for index in range(n_boot):
        chosen = rng.integers(0, len(years), size=len(years))
        draws[index] = float(np.mean(np.concatenate([years[position] for position in chosen])))
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def recoverability_type(donor_component: float, memory_component: float) -> str:
    """Hard label used by the frozen heuristic."""

    if not np.isfinite(donor_component) or not np.isfinite(memory_component):
        return "undefined"
    if float(donor_component) >= float(memory_component):
        return "donor_dominated"
    return "memory_dominated"


def type_classification_table(
    frame: pd.DataFrame,
    *,
    donor_col: str = "donor_component",
    memory_col: str = "memory_component",
    near_threshold: float = NEAR_THRESHOLD_MARGIN,
) -> pd.DataFrame:
    """Add signed type margins and a near-threshold flag.

    The margin is ``donor - memory``.  Positive values are donor-dominated.
    This is a descriptive distance-to-threshold table, not a classification
    probability, because the current records do not contain a block-bootstrap
    of the underlying anomaly series.
    """

    result = frame.copy()
    donor = pd.to_numeric(result[donor_col], errors="coerce")
    memory = pd.to_numeric(result[memory_col], errors="coerce")
    result["type_margin"] = donor - memory
    result["abs_type_margin"] = result["type_margin"].abs()
    result["recoverability_type"] = [
        recoverability_type(left, right) for left, right in zip(donor, memory, strict=True)
    ]
    result["near_classification_threshold"] = result["abs_type_margin"].lt(
        float(near_threshold)
    )
    result["classification_probability"] = np.nan
    result["classification_uncertainty"] = (
        "hard_label_only_margin_reported_no_component_bootstrap"
    )
    return result


def topology_confound_rows() -> pd.DataFrame:
    """Return the two-network topology confound inventory.

    Dam proximity, network endpoint, and donor direction are not separately
    identified in either case-study network.  This table is a mechanism
    audit, not a causal contrast.
    """

    return pd.DataFrame(
        [
            {
                "network": "Upper Jinsha",
                "station_id": "B1",
                "recoverability_type": "donor_dominated",
                "dam_role": "far_upstream_of_Guanyinyan",
                "network_endpoint": False,
                "endpoint_position": "upstream_interior",
                "donor_count": 2,
                "donor_direction": "both_downstream",
                "identifiability_note": (
                    "not dam-proximal; donors include the dam-proximal endpoint"
                ),
            },
            {
                "network": "Upper Jinsha",
                "station_id": "S2",
                "recoverability_type": "donor_dominated",
                "dam_role": "mid_network_upstream_of_Guanyinyan",
                "network_endpoint": False,
                "endpoint_position": "middle",
                "donor_count": 2,
                "donor_direction": "one_upstream_one_downstream",
                "identifiability_note": "not dam-proximal; mixed donor direction",
            },
            {
                "network": "Upper Jinsha",
                "station_id": "P3",
                "recoverability_type": "memory_dominated",
                "dam_role": "27_km_downstream_of_Guanyinyan",
                "network_endpoint": True,
                "endpoint_position": "downstream_terminus",
                "donor_count": 2,
                "donor_direction": "both_upstream",
                "identifiability_note": (
                    "dam proximity, downstream endpoint, and lowest donor R2 "
                    "are completely aliased"
                ),
            },
            {
                "network": "Upper--Middle Chattahoochee",
                "station_id": "02334430",
                "recoverability_type": "memory_dominated",
                "dam_role": "0.366_km_below_Buford",
                "network_endpoint": True,
                "endpoint_position": "upstream_origin",
                "donor_count": 4,
                "donor_direction": "all_downstream",
                "identifiability_note": (
                    "dam proximity and upstream network origin are aliased; "
                    "no upstream donor exists"
                ),
            },
            {
                "network": "Upper--Middle Chattahoochee",
                "station_id": "02335000",
                "recoverability_type": "donor_dominated",
                "dam_role": "downstream_of_Buford",
                "network_endpoint": False,
                "endpoint_position": "mainstem_interior",
                "donor_count": 4,
                "donor_direction": "mixed_upstream_and_downstream",
                "identifiability_note": "not the dam-proximal origin",
            },
            {
                "network": "Upper--Middle Chattahoochee",
                "station_id": "02335450",
                "recoverability_type": "donor_dominated",
                "dam_role": "downstream_of_Buford",
                "network_endpoint": False,
                "endpoint_position": "mainstem_interior",
                "donor_count": 4,
                "donor_direction": "mixed_upstream_and_downstream",
                "identifiability_note": "not the dam-proximal origin",
            },
            {
                "network": "Upper--Middle Chattahoochee",
                "station_id": "02336000",
                "recoverability_type": "donor_dominated",
                "dam_role": "downstream_of_Buford",
                "network_endpoint": False,
                "endpoint_position": "mainstem_interior",
                "donor_count": 4,
                "donor_direction": "mixed_upstream_and_downstream",
                "identifiability_note": "not the dam-proximal origin",
            },
            {
                "network": "Upper--Middle Chattahoochee",
                "station_id": "02337170",
                "recoverability_type": "donor_dominated",
                "dam_role": "downstream_of_Buford",
                "network_endpoint": True,
                "endpoint_position": "downstream_terminus",
                "donor_count": 4,
                "donor_direction": "all_upstream",
                "identifiability_note": (
                    "downstream endpoint but donor-dominated; endpoint alone "
                    "does not determine type"
                ),
            },
        ]
    )


def firth_logistic(
    y: np.ndarray,
    x: np.ndarray,
    *,
    max_iter: int = 80,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Fit a Firth-penalized logistic model and return coefficients and SEs."""

    response = np.asarray(y, dtype=float)
    design = np.asarray(x, dtype=float)
    if response.ndim != 1 or design.ndim != 2 or len(response) != len(design):
        raise ValueError("y must be one-dimensional and aligned with X")
    if not np.isfinite(response).all() or not np.isfinite(design).all():
        raise ValueError("Firth logistic requires finite y and X")
    n_obs, n_par = design.shape
    if n_obs < n_par + 1:
        raise ValueError("too few observations for Firth logistic")
    beta = np.zeros(n_par, dtype=float)
    covariance = np.full((n_par, n_par), np.nan)
    converged = False
    for _ in range(max_iter):
        eta = np.clip(design @ beta, -30.0, 30.0)
        probability = 1.0 / (1.0 + np.exp(-eta))
        weights = probability * (1.0 - probability)
        weighted = design.T * weights
        information = weighted @ design
        try:
            covariance = np.linalg.inv(information)
        except np.linalg.LinAlgError:
            covariance = np.linalg.pinv(information)
        hat = weights * np.sum((design @ covariance) * design, axis=1)
        working = response - probability + hat * (0.5 - probability)
        delta = covariance @ (design.T @ working)
        beta = beta + delta
        if float(np.max(np.abs(delta))) < tolerance:
            converged = True
            break
    standard_error = np.sqrt(np.clip(np.diag(covariance), 0.0, np.inf))
    with np.errstate(over="ignore", invalid="ignore"):
        odds = np.exp(beta)
        lower = np.exp(beta - 1.96 * standard_error)
        upper = np.exp(beta + 1.96 * standard_error)
        z_value = beta / standard_error
    from scipy.stats import norm

    p_value = 2.0 * (1.0 - norm.cdf(np.abs(z_value)))
    return {
        "coefficient": beta,
        "standard_error": standard_error,
        "odds_ratio": odds,
        "odds_ratio_ci_low": lower,
        "odds_ratio_ci_high": upper,
        "wald_p_value": p_value,
        "converged": converged,
        "n_observations": n_obs,
        "n_parameters": n_par,
    }


def flag_separated_coefficients(
    frame: pd.DataFrame,
    *,
    coefficient_col: str = "coefficient_log_odds",
    threshold: float = SEPARATION_ABS_COEF,
) -> pd.DataFrame:
    """Mark and suppress exploding coefficients under complete separation."""

    result = frame.copy()
    coefficient = pd.to_numeric(result[coefficient_col], errors="coerce")
    result["complete_separation_flag"] = coefficient.abs().ge(float(threshold))
    result["reporting_status"] = np.where(
        result["complete_separation_flag"],
        "suppressed_complete_separation",
        "reported",
    )
    for column in (
        "coefficient_log_odds",
        "robust_se",
        "wald_p_value",
        "coefficient_ci_low",
        "coefficient_ci_high",
        "odds_ratio",
        "odds_ratio_ci_low",
        "odds_ratio_ci_high",
    ):
        if column in result:
            result.loc[result["complete_separation_flag"], column] = np.nan
    return result


def valid_national_metrics(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
) -> dict[str, Any]:
    """Compute claim-safe national summaries without rewriting the freeze."""

    folds = fold_auc_table(predictions)
    defined = folds.loc[folds["within_fold_auc"].notna(), "within_fold_auc"]
    pooled = pooled_oof_auc(predictions)
    data = metrics.dropna(
        subset=["memory_range_index_per_degC", "upstream_major_dam_2009"]
    ).copy()
    data["z_memory_range_index"] = (
        data["memory_range_index_per_degC"] - data["memory_range_index_per_degC"].mean()
    ) / data["memory_range_index_per_degC"].std(ddof=0)
    y = data["upstream_major_dam_2009"].to_numpy(dtype=float)
    x = np.column_stack(
        [np.ones(len(data)), data["z_memory_range_index"].to_numpy(dtype=float)]
    )
    firth = firth_logistic(y, x)
    common = data.loc[
        pd.to_datetime(data["first_date"]).le(pd.Timestamp("2000-01-01"))
        & pd.to_datetime(data["last_date"]).ge(pd.Timestamp("2019-12-31"))
        & pd.to_numeric(data["n_qualifying_years"], errors="coerce").ge(20)
    ].copy()
    common_auc = np.nan
    common_or = np.nan
    if len(common) >= 20 and common["upstream_major_dam_2009"].nunique() == 2:
        common["z_index"] = (
            common["memory_range_index_per_degC"]
            - common["memory_range_index_per_degC"].mean()
        ) / common["memory_range_index_per_degC"].std(ddof=0)
        common_firth = firth_logistic(
            common["upstream_major_dam_2009"].to_numpy(dtype=float),
            np.column_stack(
                [np.ones(len(common)), common["z_index"].to_numpy(dtype=float)]
            ),
        )
        common_or = float(common_firth["odds_ratio"][1])
        common_ids = set(common["station_id"].astype(str))
        subset = predictions.loc[
            predictions["station_id"].astype(str).isin(common_ids)
        ]
        if subset["upstream_major_dam_2009"].nunique() == 2:
            from sklearn.metrics import roc_auc_score

            common_auc = float(
                roc_auc_score(
                    subset["upstream_major_dam_2009"], subset["oof_probability"]
                )
            )
    return {
        "schema_version": "national_valid_metrics_v1",
        "does_not_reopen_freeze": True,
        "frozen_primary_pooled_auc": FROZEN_PRIMARY_POOLED_AUC,
        "frozen_primary_status": "preregistered_defective_diagnostic",
        "pooled_oof_auc": float(pooled),
        "macro_within_fold_auc": (
            float(defined.mean()) if not defined.empty else float("nan")
        ),
        "median_within_fold_auc": (
            float(defined.median()) if not defined.empty else float("nan")
        ),
        "n_defined_folds": int(len(defined)),
        "firth_unadjusted_odds_ratio_per_index_sd": float(firth["odds_ratio"][1]),
        "firth_unadjusted_odds_ratio_ci_low": float(firth["odds_ratio_ci_low"][1]),
        "firth_unadjusted_odds_ratio_ci_high": float(firth["odds_ratio_ci_high"][1]),
        "firth_unadjusted_p_value": float(firth["wald_p_value"][1]),
        "firth_converged": bool(firth["converged"]),
        "common_period_n": int(len(common)),
        "common_period_regulated_n": int(common["upstream_major_dam_2009"].sum())
        if len(common)
        else 0,
        "common_period_firth_odds_ratio": common_or,
        "common_period_pooled_oof_auc": common_auc,
        "headline_estimand": "macro_within_fold_auc_plus_unadjusted_null",
        "note": (
            "Pooled LOEO AUC remains the frozen primary number but is not a "
            "valid standalone discrimination metric. Macro-AUC is the "
            "post-hoc valid level. No independent holdout was evaluated."
        ),
    }


def compact_fingerprint_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Publication Table 1: human-readable fingerprint without machine fields."""

    data = type_classification_table(
        frame.rename(
            columns={
                "donor_component_30d": "donor_component",
                "memory_component_30d": "memory_component",
            }
        )
        if "donor_component" not in frame
        else frame
    )
    columns = [
        "network",
        "station_id",
        "station_name",
        "recoverability_type",
        "donor_component",
        "memory_component",
        "type_margin",
        "near_classification_threshold",
        "acf30",
        "training_observed_range_degC",
        "memory_range_index_per_degC",
        "dam_distance_km",
        "regulation_context",
    ]
    available = [column for column in columns if column in data]
    return data[available].copy()


__all__ = [
    "MIN_INDEPENDENT_CLUSTERS",
    "NEAR_THRESHOLD_MARGIN",
    "REFERENCE_STATUS",
    "TESTED_STATUS",
    "WITHHELD_STATUS",
    "compact_fingerprint_table",
    "decide_inference_status",
    "firth_logistic",
    "flag_separated_coefficients",
    "independent_cluster_count",
    "recoverability_type",
    "topology_confound_rows",
    "type_classification_table",
    "valid_national_metrics",
    "withhold_node_importance_intervals",
    "withhold_overlap_inference",
    "year_block_mean_interval",
]
