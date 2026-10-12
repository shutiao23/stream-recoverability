"""Paths and constants for the v18 closure programme."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RESULTS_ROOT = REPO_ROOT / "results" / "v18_closure"

E1_SEASONALITY = RESULTS_ROOT / "e1_outage_seasonality"
E2_DEPLOYMENT = RESULTS_ROOT / "e2_archive_deployment"
E3_SINE = RESULTS_ROOT / "e3_sine_endpoints"
E4_REPRESENTATIVENESS = RESULTS_ROOT / "e4_representativeness"
E5_AIR = RESULTS_ROOT / "e5_air_forcing"
E6_SUPPORT = RESULTS_ROOT / "e6_support_width"
E7_MISSINGNESS = RESULTS_ROOT / "e7_informative_missingness"
FIGURES = REPO_ROOT / "figures" / "v18"

STATION_COORDINATES = REPO_ROOT / "data" / "interim" / "v18_station_coordinates.csv"
AIR_FORCING_V18 = REPO_ROOT / "data" / "interim" / "v18_air_forcing.parquet"

# Johnson et al. (2021), Ecological Indicators 122, 107229.
#
# The abstract gives two limits and the v17 programme mis-stated the second.
# "datasets with less than seven weeks of consecutively missing data enabled
# estimation of all annual signal parameters with reasonable accuracy" and
# "imputation of missing data expanded this range to approximately 20 weeks".
# v17 used 91 days (thirteen weeks) for the filled limit; the source says 140.
JOHNSON_UNFILLED_DAYS = 49
JOHNSON_FILLED_DAYS = 140

# The support widths swept in E6. One day is the annual maximum, 365 the annual
# mean; the paper's primary endpoint sits at 30.
SUPPORT_WIDTHS = (1, 3, 7, 15, 30, 60, 90, 182, 365)

# The fraction of an endpoint's own interannual standard deviation at which a
# consequential error is declared. 0.5 C on a 1.06 C peak scale.
TOLERANCE_FRACTION = 0.5 / 1.06

WARM_MONTHS = (5, 6, 7, 8, 9)
RETENTION = 0.70
PRIMARY_TOLERANCE_C = 0.5
MIN_DAYS_IN_YEAR = 360
PEAK_WINDOW_DAYS = 30
MAX_PEAK_HIDDEN_FOR_ADMISSION = 0.10
