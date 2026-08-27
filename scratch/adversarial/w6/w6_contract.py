"""W6 Europe T8/T2 contract. Scratch only. Production files are not edited.

A name cluster, a dateOpened span, an instantaneous Hub'Eau window, Sandre
code 4, FOEN GraphQL reachability, Loire last-check, or the USGS 98-list
cannot satisfy T8. Europe complete_enough cannot satisfy T2 at n << 100.
"""

from __future__ import annotations

from typing import Any, Mapping

SANDRE_CORRECTE = "1"
SANDRE_NON_QUALIFIE = "4"
SANDRE_LABEL = {
    "1": "Correcte",
    "2": "Incorrecte",
    "3": "Incertaine",
    "4": "Non qualifié",
}

MIN_STATIONS = 3
OVERLAPPING_DAILY_YEARS_MIN = 8
MIN_CONCURRENT_DAYS = 5 * 365
N_NETWORKS_MIN_T2 = 100
NA_OPEN_8YR = 59
NA_OPEN_6YR_FAILURE_CLOSURE = 67

CODE4_LIVE_SITES = ("06213500", "06175400", "06151000", "05223000")
CODE4_LIVE_N_POINTS = {
    "06213500": 10472,
    "06175400": 201121,
    "06151000": 69351,
}

UK_EA_N_STATIONS = 1964
UK_EA_N_WITH_RIVER_NAME = 16
UK_EA_N_BLANK_RIVER = 1948
UK_EA_NAME_CLUSTERS_3PLUS = 1
UK_EA_NAME_CLUSTER_RIVER = "River Derwent"

REQUIRED_MANIFEST_KEYS = (
    "countable_toward_t8",
    "hubeau_correcte_t8_usable",
    "europe_daily_years_invented",
    "loire_downloaded",
)

INFERENCE_WITHHELD = "withheld_n_lt_100_network_interval"


def sandre_code_is_t8_eligible(code: object) -> bool:
    """Only Sandre qualification 1 (Correcte) may enter a strict daily T8 path."""

    return str(code).strip() == SANDRE_CORRECTE


def naive_relabel_code4_as_correcte(code: object) -> str:
    """Weasel 1 naive patch: treat Non qualifié as Correcte. Forbidden."""

    token = str(code).strip()
    if token == SANDRE_NON_QUALIFIE:
        return SANDRE_CORRECTE
    return token


def years_from_catalog_span(begin: object, end: object) -> float:
    """Elapsed calendar years between two timestamps. Not overlapping daily years."""

    import pandas as pd

    start = pd.Timestamp(begin)
    stop = pd.Timestamp(end)
    if pd.isna(start) or pd.isna(stop) or stop < start:
        return 0.0
    return float((stop - start).days / 365.25)


def naive_daily_years_from_date_opened(date_opened: object, as_of: object) -> float:
    """Weasel 2 naive patch: dateOpened → as_of as if it were a daily-year span."""

    return years_from_catalog_span(date_opened, as_of)


def t8_countable(
    *,
    n_stations: int,
    overlapping_daily_years: float,
    days_with_min_stations: int = 0,
    quality_ok: bool = False,
    code_qualification: object | None = None,
    instantaneous_span_years: float | None = None,
    date_opened_years: float | None = None,
    catalog_cluster_only: bool = False,
    loire: bool = False,
    swiss: bool = False,
    usgs_98_list: bool = False,
    daily_years_invented: bool = False,
) -> bool:
    """True only for 3 stations × 8 overlapping *daily* years under provider QC.

    Instantaneous spans, dateOpened, name/spatial catalog clusters, Loire,
    Swiss, and the USGS 98-list never count.
    """

    if loire or swiss or usgs_98_list or daily_years_invented:
        return False
    if catalog_cluster_only:
        return False
    if instantaneous_span_years is not None:
        return False
    if date_opened_years is not None:
        return False
    if code_qualification is not None and not sandre_code_is_t8_eligible(
        code_qualification
    ):
        return False
    if not quality_ok:
        return False
    return (
        int(n_stations) >= MIN_STATIONS
        and float(overlapping_daily_years) >= OVERLAPPING_DAILY_YEARS_MIN
        and int(days_with_min_stations) >= MIN_CONCURRENT_DAYS
    )


def europe_adds_t8_not_t2(
    n_europe_complete_enough: int,
    *,
    n_na_8yr: int = NA_OPEN_8YR,
    n_na_6yr: int = NA_OPEN_6YR_FAILURE_CLOSURE,
    n_min: int = N_NETWORKS_MIN_T2,
) -> dict[str, Any]:
    """Europe complete_enough is a T8 candidate increment, never a T2 pass."""

    n_8 = int(n_na_8yr) + int(n_europe_complete_enough)
    n_6 = int(n_na_6yr) + int(n_europe_complete_enough)
    return {
        "n_europe_complete_enough": int(n_europe_complete_enough),
        "n_na_open_8yr": int(n_na_8yr),
        "n_na_open_6yr_failure_closure": int(n_na_6yr),
        "n_after_europe_8yr": n_8,
        "n_after_europe_6yr": n_6,
        "n_networks_min_t2": int(n_min),
        "t2_passed": False,
        "network_ci_allowed": False,
        "inference_status": INFERENCE_WITHHELD,
        "below_t2_floor": True,
    }


def network_ci_status(n_networks: int, *, n_min: int = N_NETWORKS_MIN_T2) -> str:
    if int(n_networks) >= int(n_min):
        return "eligible_only_after_t2_gates"
    return INFERENCE_WITHHELD


def _as_bool(value: object) -> bool:
    if value is True or value is False:
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes"}:
            return True
        if token in {"false", "0", "no", ""}:
            return False
    return False


def flag_only_w6_done_holes(
    manifest: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> list[str]:
    """Holes a flag-only 'W6 done' PR still ships. Non-empty ⇒ merge blocker."""

    holes: list[str] = []
    n_correcte = int(evidence.get("hubeau_n_sites_with_sandre_correcte_observations") or 0)
    n_uk_complete = int(evidence.get("uk_ea_n_complete_enough") or 0)
    n_europe = int(evidence.get("n_europe_complete_enough") or 0)
    n_name_clusters = int(evidence.get("uk_ea_n_name_clusters_3plus") or 0)
    spatial_attempted = _as_bool(evidence.get("uk_ea_spatial_50km_attempted"))
    code4_accepted = _as_bool(manifest.get("hubeau_unqualified_code_4_accepted"))
    loire = _as_bool(manifest.get("loire_downloaded"))
    swiss = _as_bool(manifest.get("swiss_countable_toward_t8"))
    invented = _as_bool(manifest.get("europe_daily_years_invented"))
    usgs98 = _as_bool(manifest.get("catalog_98_name_huc2_downloaded"))
    foen_values = _as_bool(manifest.get("foen_temperature_values_requested"))
    countable = _as_bool(manifest.get("countable_toward_t8"))
    hubeau_usable = _as_bool(manifest.get("hubeau_correcte_t8_usable"))
    passed = _as_bool(manifest.get("passed"))
    inference = str(manifest.get("inference_status") or "")
    claimed_complete = int(manifest.get("n_complete_enough") or 0)

    if n_correcte == 0 and (hubeau_usable or code4_accepted or countable):
        holes.append("hubeau_correcte_zero_counted_as_t8")
    if n_uk_complete == 0 and claimed_complete > 0:
        holes.append("uk_ea_complete_enough_invented")
    if n_europe == 0 and countable:
        holes.append("countable_toward_t8_without_3x8_daily")
    if n_name_clusters <= 1 and not spatial_attempted:
        holes.append("name_only_clustering_stopped_after_derwent")
    if loire:
        holes.append("loire_downloaded")
    if swiss or foen_values:
        holes.append("swiss_opened_or_counted")
    if usgs98:
        holes.append("usgs_98_list_downloaded")
    if invented:
        holes.append("europe_daily_years_invented")
    if passed:
        holes.append("w6_sold_as_t2_pass")
    if inference == "tested":
        holes.append("network_ci_tested_at_n_lt_100")
    if claimed_complete > 0 and n_europe == 0:
        holes.append("n_complete_enough_flag_without_daily_overlap")
    return holes


def assert_w6_not_done_contract(
    manifest: Mapping[str, Any], *, require_keys: bool = True
) -> None:
    """Honest W6 stop-loss. Raises if a done-claim leaks.

    ``require_keys`` is for the scratch contract JSON. Production's combined
    W6 audit currently omits ``hubeau_correcte_t8_usable`` and
    ``europe_daily_years_invented``; missing must be read as false, not as a
    license to add them as true.
    """

    if require_keys:
        missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
        if missing:
            raise AssertionError(f"missing W6 contract keys: {missing}")
    if _as_bool(manifest.get("europe_daily_years_invented")):
        raise AssertionError("europe_daily_years_invented must stay false")
    if _as_bool(manifest.get("loire_downloaded")):
        raise AssertionError("loire_downloaded must stay false")
    if _as_bool(manifest.get("hubeau_correcte_t8_usable")):
        raise AssertionError("hubeau_correcte_t8_usable is a lie while Correcte=0")
    if _as_bool(manifest.get("countable_toward_t8")):
        raise AssertionError(
            "countable_toward_t8 true requires 3 stations × 8 overlapping daily years"
        )
    if _as_bool(manifest.get("passed")):
        raise AssertionError("W6 must not write passed true")
    if str(manifest.get("inference_status") or "") == "tested":
        raise AssertionError("must not report network CI tested at n<<100")


__all__ = [
    "CODE4_LIVE_N_POINTS",
    "CODE4_LIVE_SITES",
    "INFERENCE_WITHHELD",
    "MIN_CONCURRENT_DAYS",
    "MIN_STATIONS",
    "NA_OPEN_6YR_FAILURE_CLOSURE",
    "NA_OPEN_8YR",
    "N_NETWORKS_MIN_T2",
    "OVERLAPPING_DAILY_YEARS_MIN",
    "REQUIRED_MANIFEST_KEYS",
    "SANDRE_CORRECTE",
    "SANDRE_LABEL",
    "SANDRE_NON_QUALIFIE",
    "UK_EA_NAME_CLUSTERS_3PLUS",
    "UK_EA_NAME_CLUSTER_RIVER",
    "UK_EA_N_BLANK_RIVER",
    "UK_EA_N_STATIONS",
    "UK_EA_N_WITH_RIVER_NAME",
    "assert_w6_not_done_contract",
    "europe_adds_t8_not_t2",
    "flag_only_w6_done_holes",
    "naive_daily_years_from_date_opened",
    "naive_relabel_code4_as_correcte",
    "network_ci_status",
    "sandre_code_is_t8_eligible",
    "t8_countable",
    "years_from_catalog_span",
]
