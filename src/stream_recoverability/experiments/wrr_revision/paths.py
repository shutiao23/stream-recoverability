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
WARM_SEASON_MONTHS = (5, 6, 7, 8, 9)
JJA_MONTHS = (6, 7, 8)
UNIVERSE_AS_OF = "2026-09-07"
DEFAULT_HANDLER = "doy_climatology"
STEP1_UNIVERSE = RESULTS_ROOT / "step1_universe"
STEP2_HEADROOM = RESULTS_ROOT / "step2_simple_headroom"
STEP4_INFORMATION = RESULTS_ROOT / "step4_information"
STEP5_THERMAL_DECISION = RESULTS_ROOT / "step5_thermal_decision"
STEP6_ABLATIONS = RESULTS_ROOT / "step6_ablations"
STEP7_FAILURE_REPLAY = RESULTS_ROOT / "step7_failure_replay"
STEP8_HYDROLOGY = RESULTS_ROOT / "step8_hydrology"
STEP9_E2E_FREEZE = RESULTS_ROOT / "step9_e2e_freeze"
STEP10_UNSEEN = RESULTS_ROOT / "step10_unseen_confirmation"
SUCCESS_CRITERION = RESULTS_ROOT / "SUCCESS_CRITERION.json"
NON_INFERIORITY_EPSILON_C = 0.05
SEVERE_UNDERESTIMATE_C = 1.0
GAGES_II_ARCHIVE = (
    REPO_ROOT / "data" / "cache" / "regulation_panel_v1" / "basinchar_and_report_sept_2011.zip"
)
QC_SUMMARY = REPO_ROOT / "results" / "development_v11" / "confirmation_qc_summary.csv"
CANDIDATES = REPO_ROOT / "results" / "development_v11" / "confirmation_candidates.csv"
DEVELOPMENT_INVENTORY = REPO_ROOT / "results" / "development_v11" / "network_inventory.csv"
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
    "air_lag_ridge",
    "air2stream3",
    "air_flow_ridge",
    "air2stream",
)
