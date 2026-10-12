"""Shared constants and on-disk paths for the v17 fitness-for-use study."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RESULTS_ROOT = REPO_ROOT / "results" / "v17_fitness"
REVIEW_DIR = REPO_ROOT / "docs" / "reviews" / "wrr_2026_09_23"

STEP1_PANEL = RESULTS_ROOT / "step1_panel"
STEP2_OUTAGES = RESULTS_ROOT / "step2_outages"
STEP3_CASES = RESULTS_ROOT / "step3_cases"
STEP4_CEILING = RESULTS_ROOT / "step4_ceiling"
STEP5_MECHANISM = RESULTS_ROOT / "step5_mechanism"
STEP6_SCREEN = RESULTS_ROOT / "step6_screen"
STEP7_FRONTIER = RESULTS_ROOT / "step7_frontier"
STEP8_DOWNSTREAM = RESULTS_ROOT / "step8_downstream"
STEP9_FREEZE = RESULTS_ROOT / "step9_freeze"
STEP10_CONFIRM = RESULTS_ROOT / "step10_confirmation"

TRUSTED_YEARS = (
    REPO_ROOT / "results" / "wrr_revision" / "step1_universe" / "trusted_river_complete_years.csv"
)
NETWORK_ROSTER = (
    REPO_ROOT / "results" / "wrr_revision" / "step1_universe" / "network_roster.csv"
)
FIRST_PANEL_ROOT = REPO_ROOT / "results" / "development_v11" / "confirmation_daily_qc" / "networks"
SECOND_PANEL_ROOT = (
    REPO_ROOT / "results" / "development_v11" / "second_confirmation" / "daily_qc" / "networks"
)
# The air-forcing table is overridable so that the v18 sensitivity analysis can
# rerun the same pipeline against a wider forcing set without a second copy of
# the pipeline. Unset, this is exactly the table the v17 results were built on.
_DEFAULT_AIR_FORCING = (
    REPO_ROOT
    / "results"
    / "development_v11"
    / "independent_air2stream_equivalent"
    / "daily_forcing.parquet"
)
AIR_FORCING = Path(os.environ.get("STREAM_AIR_FORCING", _DEFAULT_AIR_FORCING))

# Endpoint
HOTTEST_WINDOW_DAYS = 30
EXCEEDANCE_THRESHOLDS_C = (18.0, 20.0)
PRIMARY_METRIC = "hottest_30"

# Natural scale of the endpoint, recomputed in Step 1 and used to anchor every
# tolerance. The 2026-09-23 review computed 1.06 C across 457 stations.
NATURAL_SCALE_C = 1.06
TOLERANCES_C = (0.25, 0.5, 1.0)
PRIMARY_TOLERANCE_C = 0.5

# Station eligibility for the leave-one-year-out recovery protocol.
MIN_COMPLETE_YEARS = 4

# Pre-declared stratification.
DONOR_REGIMES = ("none", "sparse", "rich")
SPLIT_SEED = 20260923
RESERVED_NETWORK_FRACTION = 0.30

OUTAGE_LENGTHS = (14, 30, 60, 90, 120, 180, 270)
OVERLAP_CLASSES = ("none", "partial", "full")
REALIZATIONS_PER_STATION_YEAR = 12

NOMINAL_COVERAGE = 0.90


def donor_regime(n_donors: int) -> str:
    """Pre-declared donor regime strata. Declared before the split, not after."""

    count = int(n_donors)
    if count <= 0:
        return "none"
    if count <= 2:
        return "sparse"
    return "rich"


def stable_seed(*parts: object) -> int:
    """A process-independent seed.

    Python's ``hash()`` is randomised per process for str and bytes, so using it
    to seed an outage realisation makes the case table irreproducible between
    runs. This is deterministic across processes, machines and interpreter
    versions.
    """

    import hashlib

    key = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(key, digest_size=4).digest(), "big")


# Instrument error of an in-situ water-temperature logger, used to perturb the
# reference series so that every conclusion can be checked against it rather
# than assumed immune. Typical manufacturer accuracy is 0.1-0.2 C.
SENSOR_NOISE_C = 0.15

# Ecological thresholds swept in the exceedance analysis. The primary value is
# justified against a named standard in the manuscript; the sweep exists so the
# reader can see the conclusion is not an artefact of the choice.
EXCEEDANCE_SWEEP_C = (14.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 24.0)
