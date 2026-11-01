#!/usr/bin/env python3
"""Machine-readable schema for the Stanford-review extension tables.

The replay verifier (983) reads this specification from the candidate package so
that table names, primary keys, label fields and legal missing values do not
drift from the generator.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA = "stanford_revision_table_spec_v1"

TABLES = {
    "retention_family_summary.csv": {
        "keys": ["family", "scheme"],
        "columns": [
            "family", "scheme", "n", "stations", "groups", "estimate_rmse",
            "year_set_rmse", "reconstruction_rmse",
            "iid_linear_working_year_set_rmse", "cross_term", "mean_years",
            "sign_disagreement_count", "sign_disagreement_expected_count",
        ],
        "numeric": [
            "n", "stations", "groups", "estimate_rmse", "year_set_rmse",
            "reconstruction_rmse", "iid_linear_working_year_set_rmse",
            "cross_term", "mean_years", "sign_disagreement_count",
            "sign_disagreement_expected_count",
        ],
        "labels": ["family", "scheme"],
        "nan_rules": [
            {"column": "sign_disagreement_count", "where": {"scheme": ["uniform_exact"]}},
            {"column": "sign_disagreement_expected_count", "where": {"scheme": ["warm90", "cdf_all_years", "sxx_all_years", "all"]}},
        ],
        "grain": "one row per gap family and retention rule",
        "unit": "RMSE in degrees C per decade; counts are archive-level sums",
        "source": "derived output",
    },
    "retention_paired_intervals.csv": {
        "keys": ["family", "scheme"],
        "columns": [
            "family", "scheme", "n", "stations", "groups", "contrast",
            "rmse_difference", "ci_low", "ci_high", "seed", "bootstraps",
        ],
        "numeric": ["n", "stations", "groups", "rmse_difference", "ci_low", "ci_high", "seed", "bootstraps"],
        "labels": ["family", "scheme", "contrast"],
        "nan_rules": [],
        "grain": "one row per family and rule contrast against warm-season screening",
        "unit": "RMSE difference and interval in degrees C per decade",
        "source": "derived output",
    },
    "retention_choice_counts.csv": {
        "keys": ["family", "station_key", "replicate"],
        "columns": [
            "family", "station_key", "replicate", "independence_group", "region",
            "n_full", "n_incomplete", "k", "n_subsets", "choice",
            "all_incomplete_kept", "no_incomplete_kept",
        ],
        "numeric": ["replicate", "n_full", "n_incomplete", "k", "n_subsets", "choice", "all_incomplete_kept", "no_incomplete_kept"],
        "labels": ["family", "station_key", "independence_group", "region"],
        "nan_rules": [],
        "grain": "one row per actual-mask archive",
        "unit": "counts of years and feasible same-count subsets",
        "source": "derived output",
    },
    "retention_geometry_cases.csv": {
        "keys": ["family", "station_key", "replicate", "scheme"],
        "columns": [
            "family", "station_key", "replicate", "independence_group", "region",
            "scheme", "estimate_error", "year_set_error", "reconstruction_error",
            "estimate_mse", "year_set_mse", "reconstruction_mse", "cross_term",
            "weight_distance_squared", "iid_linear_expected_year_set_mse",
            "reference_slope", "reference_residual_variance",
            "slope_sign_disagreement", "retained_years", "n_retained",
        ],
        "numeric": [
            "replicate", "estimate_error", "year_set_error", "reconstruction_error",
            "estimate_mse", "year_set_mse", "reconstruction_mse", "cross_term",
            "weight_distance_squared", "iid_linear_expected_year_set_mse",
            "reference_slope", "reference_residual_variance",
            "slope_sign_disagreement", "n_retained",
        ],
        "labels": ["family", "station_key", "independence_group", "region", "scheme", "retained_years"],
        "nan_rules": [
            {"column": "estimate_error", "where": {"scheme": ["uniform_exact"]}},
            {"column": "year_set_error", "where": {"scheme": ["uniform_exact"]}},
            {"column": "reconstruction_error", "where": {"scheme": ["uniform_exact"]}},
            {"column": "reference_residual_variance", "where": {"scheme": ["uniform_exact"]}},
            {"column": "retained_years", "where": {"scheme": ["uniform_exact"]}},
        ],
        "grain": "one row per archive and rule; uniform_exact row is the archive-level mean over every feasible same-count subset",
        "unit": "errors and RMSE contributions in degrees C per decade; squared terms in squared degrees C per squared decade",
        "source": "derived output",
    },
    "reference_truths.csv": {
        "keys": ["family", "station_key", "year"],
        "columns": ["family", "station_key", "year", "eval_truth_h30"],
        "numeric": ["year", "eval_truth_h30"],
        "labels": ["family", "station_key"],
        "nan_rules": [],
        "grain": "one row per station-year reference outcome and gap family",
        "unit": "H30 in degrees C",
        "source": "compact replay input derived from the evaluation reference roster",
    },
    "reference_year_sets.csv": {
        "keys": ["station_key"],
        "columns": [
            "station_key", "n_reference_years", "first_year", "last_year",
            "internal_gap_years", "n_internal_gap_years", "reference_years",
        ],
        "numeric": ["n_reference_years", "first_year", "last_year", "n_internal_gap_years"],
        "labels": ["station_key", "internal_gap_years", "reference_years"],
        "nan_rules": [],
        "grain": "one row per forward station",
        "unit": "years; internal_gap_years is 'none' or a semicolon-separated list",
        "source": "derived output",
    },
    "estimator_availability.csv": {
        "keys": ["family", "estimator"],
        "columns": ["family", "estimator", "available", "total", "available_rmse"],
        "numeric": ["available", "total", "available_rmse"],
        "labels": ["family", "estimator"],
        "nan_rules": [],
        "grain": "one row per gap family and point estimator at all-year retention",
        "unit": "counts and RMSE in degrees C per decade",
        "source": "derived output",
    },
    "estimator_paired_comparisons.csv": {
        "keys": ["family", "comparator"],
        "columns": [
            "family", "comparator", "D2_rmse", "comparator_rmse", "n",
            "stations", "groups", "contrast", "rmse_difference", "ci_low",
            "ci_high", "seed", "bootstraps",
        ],
        "numeric": ["D2_rmse", "comparator_rmse", "n", "stations", "groups", "rmse_difference", "ci_low", "ci_high", "seed", "bootstraps"],
        "labels": ["family", "comparator", "contrast"],
        "nan_rules": [],
        "grain": "one row per family and comparator on common finite point estimates",
        "unit": "RMSE and interval in degrees C per decade",
        "source": "derived output",
    },
    "estimator_unavailable_subset.csv": {
        "keys": ["family"],
        "columns": ["family", "classical_unavailable_D2_available", "D2_rmse_on_that_subset"],
        "numeric": ["classical_unavailable_D2_available", "D2_rmse_on_that_subset"],
        "labels": ["family"],
        "nan_rules": [],
        "grain": "one row per gap family",
        "unit": "archive count and D2 RMSE in degrees C per decade",
        "source": "derived output",
    },
    "case_designs.csv": {
        "keys": ["family", "station_key", "replicate"],
        "columns": ["family", "station_key", "replicate", "n_years", "masks"],
        "numeric": ["replicate", "n_years"],
        "labels": ["family", "station_key", "masks"],
        "nan_rules": [],
        "grain": "one row per archive; masks is a JSON list of masked years",
        "unit": "years and a JSON year list",
        "source": "compact replay input derived from saved designs",
    },
    "annual_predictions_compact.csv": {
        "keys": ["family", "station_key", "replicate", "year"],
        "columns": ["family", "station_key", "replicate", "year", "D2", "warm_observed_fraction"],
        "numeric": ["replicate", "year", "D2", "warm_observed_fraction"],
        "labels": ["family", "station_key"],
        "nan_rules": [],
        "grain": "one row per archive-year that the saved annual prediction file contains",
        "unit": "H30 in degrees C and a dimensionless observed fraction",
        "source": "compact replay input derived from saved annual predictions",
    },
}


def allowed_nan_mask(frame: pd.DataFrame, spec: dict) -> pd.DataFrame:
    mask = pd.DataFrame(False, index=frame.index, columns=frame.columns)
    for rule in spec["nan_rules"]:
        rows = pd.Series(True, index=frame.index)
        for column, values in rule["where"].items():
            rows &= frame[column].isin(values)
        mask[rule["column"]] |= rows
    return mask


def validate_frame(frame: pd.DataFrame, spec: dict, label: str) -> None:
    if list(frame.columns) != list(spec["columns"]):
        raise RuntimeError(f"{label} columns differ: {list(frame.columns)}")
    keys = spec["keys"]
    if frame[keys].isna().any().any():
        raise RuntimeError(f"{label} has a missing primary key")
    if frame.duplicated(keys).any():
        raise RuntimeError(f"{label} has duplicate primary keys")
    allowed = allowed_nan_mask(frame, spec)
    if (frame.isna() & ~allowed).any().any():
        bad = (frame.isna() & ~allowed).stack()
        raise RuntimeError(f"{label} has an unexpected NaN at {bad[bad].index[:3].tolist()}")
    for column in spec["numeric"]:
        values = pd.to_numeric(frame[column], errors="coerce")
        if (frame[column].notna() & values.isna()).any():
            raise RuntimeError(f"{label}.{column} contains non-numeric text")
        if np.isinf(values).any():
            raise RuntimeError(f"{label}.{column} contains infinity")


def spec_document() -> dict:
    return {
        "schema": SCHEMA,
        "tables": TABLES,
        "notes": [
            "NaN is allowed only where a nan_rule names the column and matching scheme.",
            "NaN positions must match between the frozen and replayed tables; Inf is never allowed.",
            "Numeric comparisons use rtol=0 and atol=1e-12. Label columns are compared exactly.",
            "reference_truths.csv, case_designs.csv and annual_predictions_compact.csv are compact replay inputs, not newly estimated results.",
        ],
    }


def write_spec(path: Path) -> None:
    path.write_text(json.dumps(spec_document(), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    args.path.parent.mkdir(parents=True, exist_ok=True)
    write_spec(args.path)
