"""Shared constants and on-disk paths for the WRR revision experiments."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RESULTS_ROOT = REPO_ROOT / "results" / "wrr_revision"
DOCS_REVIEW = REPO_ROOT / "docs" / "reviews" / "wrr_2026_09_06"

FIRST_PANEL_ROOT = REPO_ROOT / "results" / "development_v11" / "confirmation_daily_qc" / "networks"
SECOND_PANEL_ROOT = (
    REPO_ROOT / "results" / "development_v11" / "second_confirmation" / "daily_qc" / "networks"
)
HELD_OUT_QC_ROOT = FIRST_PANEL_ROOT

FIRST_PLACEMENTS = (
    REPO_ROOT / "results" / "development_v11" / "route_a_confirmation" / "placement_losses.csv"
)
SECOND_PLACEMENTS = (
    REPO_ROOT
    / "results"
    / "development_v11"
    / "second_confirmation"
    / "scoring"
    / "placement_losses.csv"
)
FIRST_FIT_LOSSES = (
    REPO_ROOT
    / "results"
    / "development_v11"
    / "reviewer_completion"
    / "confirmation_empirical_fit_losses.csv"
)
P0_FIRST = REPO_ROOT / "results" / "v14" / "p0_differential" / "placement_predictions_first.csv"
P0_SECOND = REPO_ROOT / "results" / "v14" / "p0_differential" / "placement_predictions_second.csv"
AIR2STREAM_FORCING = (
    REPO_ROOT
    / "results"
    / "development_v11"
    / "independent_air2stream_equivalent"
    / "daily_forcing.parquet"
)
AUXILIARY_CORPUS = (
    REPO_ROOT
    / "data_versions"
    / "global_network_corpus_v1"
    / "open_role_auxiliary"
    / "failure_closure6"
    / "development"
    / "networks"
)

GAP_GRID = (7, 14, 30, 60, 90, 120, 150, 180, 365)
ARCHIVED_GAPS = (7, 14, 30, 60, 90, 180, 365)
GENERATED_GAPS = (120, 150)
PRIMARY_METRIC = "hottest_30"
SECONDARY_METRIC = "exceed_days_20"
EXCEEDANCE_THRESHOLD_C = 20.0
HOTTEST_WINDOW_DAYS = 30
DEFAULT_HANDLER = "doy_climatology"
DEVELOPMENT_PANEL = "first"
CONFIRMATION_ROLE = "held_out_qc_not_in_first_or_second"

SAME_INFORMATION_RECOVERERS = (
    "xgb_neighbor_boundary",
    "xgb_longblock_boundary",
    "xgb_neighbor_noboundary",
    "xgb_longblock_noboundary",
    "ridge_neighbor_boundary",
    "donor_only_ridge",
    "linear_interp",
    "smooth_climatology",
    "doy_climatology",
)
EXTERNAL_INFORMATION_RECOVERERS = (
    "air_ridge",
    "air_flow_ridge",
    "air2stream",
)
