"""W7 T2 contract. Scratch only. Production files are not edited.

n=67 (6-year failure_closure) and n=59 (8-year) cannot satisfy confirmatory
T2. Europe catalog clusters, a 5.91-year UK EA overlap, Hub'Eau code 4,
sealed HUC8, FOEN/Loire, and M/H-blocked cells cannot pad n or the grid.
Incremental R² vs donor_r2 below 0.05 is a W8 retitle, not a retune.
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
NA_OPEN_8YR_DEVELOPMENT = 43
NA_OPEN_8YR_VALIDATION = 16
NA_OPEN_6YR_FAILURE_CLOSURE = 67
NA_OPEN_6YR_DEVELOPMENT = 47
NA_OPEN_6YR_VALIDATION = 20

WORKLOAD_SHA256 = "c08129ad71a96a56a1610a1eacbbb93be9dd5ccd646b21e9ba7dc431f412fa19"
GO_NO_GO = "NO_GO_T2_PRIMARY_EVIDENCE"
INFERENCE_WITHHELD = "withheld_n_lt_100_network_interval"
W7_PURPOSE = "development_slice_not_evidence"
W7_FIRST_LAYER = ("B", "D", "B_union_D")
MH_BLOCKED = ("B_union_D_union_M", "B_union_D_union_M_union_H")
INCREMENTAL_R2_W8_FLOOR = 0.05

UK_EA_BEST_OVERLAP_YEARS = 5.908281998631074
UK_EA_BEST_OVERLAP_NETWORK = "uk_ea_s50_002"
UK_EA_BEST_OVERLAP_N_STATIONS = 4
UK_EA_BEST_OVERLAP_CONCURRENT_DAYS = 2139
UK_EA_N_COMPLETE_ENOUGH = 0
UK_EA_HYDROMETRIC_CLUSTERS_50KM = 6
UK_EA_SPATIAL_CATALOG_CLUSTERS_50KM = 85

N_EXECUTABLE_BD = 294460
N_MH_STRUCTURAL_NOT_APPLICABLE = 403424
N_MH_AUXILIARY_TERMINAL = 13
N_MH_AUXILIARY_EXPECTED = 67

CODE4_LIVE_SITES = ("06213500", "06175400", "06151000", "05223000")

NEVER_SEALED_TOKENS = (
    "jinsha_upper",
    "chattahoochee_upper_middle",
    "delaware_river_huc20",
    "willamette_river_huc17",
    "suwannee_river_huc31",
    "yellowstone_river_huc10",
    "rio_grande_huc13",
    "madison_river_huc10",
    "cahaba_river_huc31",
    "mckenzie_river_huc17",
    "mahoning_river_huc50",
    "roanoke_river_huc30",
    "santa_fe_river_huc31",
    "clearwater_river_huc17",
)

SEALED_HUC8_PAD_EXAMPLE = "huc8_03050201"

REQUIRED_MANIFEST_KEYS = (
    "passed",
    "n_networks",
    "purpose",
    "formal_evidence",
    "confirmatory_eligible",
    "go_no_go",
    "evaluate_success",
    "network_interval",
    "sealed_outcomes_opened",
    "europe_complete_enough_used",
    "mh_blocked_cells_relabeled_executable",
    "operator_retuned_because_incremental_r2_lt_005",
)


def sandre_code_is_t8_eligible(code: object) -> bool:
    return str(code).strip() == SANDRE_CORRECTE


def naive_relabel_code4_as_correcte(code: object) -> str:
    """Weasel 3 naive patch: Non qualifié as Correcte. Forbidden."""

    token = str(code).strip()
    if token == SANDRE_NON_QUALIFIE:
        return SANDRE_CORRECTE
    return token


def t8_countable(
    *,
    n_stations: int,
    overlapping_daily_years: float,
    days_with_min_stations: int = 0,
    quality_ok: bool = False,
    code_qualification: object | None = None,
    catalog_cluster_only: bool = False,
    loire: bool = False,
    swiss: bool = False,
    foen_values: bool = False,
    usgs_98_list: bool = False,
    sealed_huc8: bool = False,
) -> bool:
    """True only for 3 stations × 8 overlapping daily years under provider QC."""

    if loire or swiss or foen_values or usgs_98_list or sealed_huc8:
        return False
    if catalog_cluster_only:
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


def europe_does_not_increment_t2(
    *,
    n_catalog_clusters: int = 0,
    overlap_years: float = 0.0,
    n_europe_complete_enough: int = 0,
    n_na: int = NA_OPEN_6YR_FAILURE_CLOSURE,
    n_min: int = N_NETWORKS_MIN_T2,
) -> dict[str, Any]:
    """Catalog clusters and 5.91-year overlap add 0 to T8/T2 n."""

    increment = 0
    if int(n_europe_complete_enough) > 0:
        # Even a real Europe T8 candidate is not a T2 pass at n << 100.
        increment = 0
    n_after = int(n_na) + increment
    return {
        "n_catalog_clusters": int(n_catalog_clusters),
        "overlap_years": float(overlap_years),
        "n_europe_complete_enough": int(n_europe_complete_enough),
        "t8_or_t2_n_increment": increment,
        "n_after": n_after,
        "t2_passed": False,
        "network_ci_allowed": False,
        "inference_status": INFERENCE_WITHHELD,
        "below_t2_floor": n_after < int(n_min),
    }


def t2_confirmatory_eligible(n_networks: int, *, n_min: int = N_NETWORKS_MIN_T2) -> bool:
    return int(n_networks) >= int(n_min)


def network_ci_status(n_networks: int, *, n_min: int = N_NETWORKS_MIN_T2) -> str:
    if int(n_networks) >= int(n_min):
        return "eligible_only_after_t2_gates"
    return INFERENCE_WITHHELD


def w7_information_is_first_layer(condition: object) -> bool:
    return str(condition) in W7_FIRST_LAYER


def mh_cell_is_blocked(
    condition: object,
    *,
    meteorology_bound: bool = False,
    hydraulics_bound: bool = False,
    n_terminal: int = N_MH_AUXILIARY_TERMINAL,
    n_expected: int = N_MH_AUXILIARY_EXPECTED,
) -> bool:
    token = str(condition)
    if token == "B_union_D_union_M":
        return (not meteorology_bound) or int(n_terminal) < int(n_expected)
    if token == "B_union_D_union_M_union_H":
        return (
            (not meteorology_bound)
            or (not hydraulics_bound)
            or int(n_terminal) < int(n_expected)
        )
    return False


def naive_relabel_mh_as_executable(category: object, condition: object) -> str:
    """Weasel 6 naive patch: M/H-blocked cells rewritten as executable."""

    if str(condition) in MH_BLOCKED:
        return "executable"
    return str(category)


def executable_count_after_mh_relabel(
    n_executable: int = N_EXECUTABLE_BD,
    n_mh_blocked: int = N_MH_STRUCTURAL_NOT_APPLICABLE,
    *,
    relabel: bool,
) -> int:
    if relabel:
        return int(n_executable) + int(n_mh_blocked)
    return int(n_executable)


def w8_failure_closure_action(incremental_r2_vs_donor: float) -> str:
    """W8 trigger is retitle, never retune, when incremental R² < 0.05."""

    if float(incremental_r2_vs_donor) < INCREMENTAL_R2_W8_FLOOR:
        return "retitle_to_predictability"
    return "keep_operator_title_still_not_t2"


def operator_or_phi_retune_licensed(
    incremental_r2_vs_donor: float | None = None,
) -> bool:
    """Retuning is never licensed. Incremental R² below 0.05 is a retitle."""

    return False


def n_cannot_reach_floor_by_padding(
    *,
    n_open: int = NA_OPEN_6YR_FAILURE_CLOSURE,
    europe_clusters: int = 0,
    uk_ea_overlap_years: float = 0.0,
    sealed_huc8: int = 0,
    loire: int = 0,
    swiss: int = 0,
    code4_sites: int = 0,
    n_min: int = N_NETWORKS_MIN_T2,
) -> dict[str, Any]:
    """Padding sources add 0. Honest n stays the open-role stock."""

    del europe_clusters, uk_ea_overlap_years, sealed_huc8, loire, swiss, code4_sites
    n_honest = int(n_open)
    return {
        "n_honest": n_honest,
        "n_after_illegal_padding": n_honest,
        "padding_increment": 0,
        "clears_floor": n_honest >= int(n_min),
        "inference_status": network_ci_status(n_honest, n_min=n_min),
    }


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


def _nested(mapping: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = mapping.get(key)
    return value if isinstance(value, Mapping) else {}


def _inference_token(manifest: Mapping[str, Any]) -> str:
    nested = _nested(manifest, "network_interval")
    evaluate = _nested(manifest, "evaluate_success")
    return str(
        nested.get("inference_status")
        or evaluate.get("spearman_inference_status")
        or evaluate.get("inference_status")
        or manifest.get("network_inference_status")
        or manifest.get("inference_status")
        or ""
    )


def flag_only_w7_t2_done_holes(
    manifest: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> list[str]:
    """Holes a flag-only 'T2 done' PR still ships. Non-empty ⇒ merge blocker."""

    holes: list[str] = []

    def _hole(name: str) -> None:
        if name not in holes:
            holes.append(name)
    n_claimed = int(manifest.get("n_networks") or 0)
    n_open = int(evidence.get("n_open") or NA_OPEN_6YR_FAILURE_CLOSURE)
    n_europe = int(evidence.get("n_europe_complete_enough") or 0)
    n_correcte = int(
        evidence.get("hubeau_n_sites_with_sandre_correcte_observations") or 0
    )
    n_uk = int(evidence.get("uk_ea_n_complete_enough") or 0)
    evaluate_live_passed = _as_bool(evidence.get("evaluate_success_live_passed"))
    meteorology_bound = _as_bool(evidence.get("meteorology_M"))
    hydraulics_bound = _as_bool(evidence.get("hydraulics_H"))
    n_terminal = int(evidence.get("n_mh_auxiliary_terminal") or N_MH_AUXILIARY_TERMINAL)

    passed = _as_bool(manifest.get("passed"))
    evaluate = _nested(manifest, "evaluate_success")
    evaluate_flag = _as_bool(evaluate.get("passed"))
    inference = _inference_token(manifest)
    go = str(manifest.get("go_no_go") or "")
    confirmatory = _as_bool(manifest.get("confirmatory_eligible"))
    europe_used = _as_bool(manifest.get("europe_complete_enough_used"))
    counted_overlap = _as_bool(manifest.get("uk_ea_best_overlap_counted_as_t8"))
    europe_added = int(manifest.get("n_europe_complete_enough_added") or 0)
    hubeau_usable = _as_bool(manifest.get("hubeau_correcte_t8_usable"))
    code4_accepted = _as_bool(manifest.get("hubeau_unqualified_code_4_accepted"))
    loire = _as_bool(manifest.get("loire_downloaded"))
    swiss = _as_bool(manifest.get("swiss_countable_toward_t8"))
    foen_values = _as_bool(manifest.get("foen_temperature_values_requested"))
    sealed = _as_bool(manifest.get("sealed_outcomes_opened"))
    sealed_roots = manifest.get("sealed_input_roots_allowed") or []
    mh_relabel = _as_bool(manifest.get("mh_blocked_cells_relabeled_executable"))
    claimed_executable = manifest.get("n_executable")
    retuned = _as_bool(
        manifest.get("operator_retuned_because_incremental_r2_lt_005")
    ) or _as_bool(manifest.get("twin_e_retuned"))
    incremental = manifest.get("incremental_r2_vs_donor_r2")
    freeze_retarget = _as_bool(manifest.get("design_freeze_v4_retargeted"))
    usgs98 = _as_bool(manifest.get("catalog_98_name_huc2_downloaded"))

    if passed or confirmatory or go not in {"", GO_NO_GO}:
        if n_claimed < N_NETWORKS_MIN_T2 or n_open < N_NETWORKS_MIN_T2:
            _hole("n_lt_100_sold_as_confirmatory_t2")
    if inference == "tested" and n_open < N_NETWORKS_MIN_T2:
        _hole("network_ci_tested_at_n_lt_100")
    if n_claimed > n_open:
        _hole("n_padded_above_open_role_stock")
    if (
        europe_used
        or counted_overlap
        or europe_added > n_europe
        or (n_europe == 0 and europe_added > 0)
        or (n_uk == 0 and counted_overlap)
    ):
        _hole("europe_catalog_or_5_91_counted_as_t8_or_t2")
    if n_correcte == 0 and (hubeau_usable or code4_accepted):
        _hole("hubeau_code4_counted_as_correcte_t8")
    if (passed or evaluate_flag) and not evaluate_live_passed:
        _hole("passed_true_while_evaluate_success_fails")
    if sealed or loire or swiss or foen_values or sealed_roots:
        _hole("sealed_huc8_foen_loire_opened_to_pad_n")
    if mh_relabel or (
        claimed_executable is not None
        and int(claimed_executable) > N_EXECUTABLE_BD
        and (
            not meteorology_bound
            or not hydraulics_bound
            or n_terminal < N_MH_AUXILIARY_EXPECTED
        )
    ):
        _hole("mh_blocked_relabeled_executable")
    if retuned:
        _hole("operator_or_phi_retuned_for_incremental_r2")
    if incremental is not None and float(incremental) < INCREMENTAL_R2_W8_FLOOR:
        action = str(manifest.get("w8_failure_closure_action") or "")
        if action != "retitle_to_predictability" or retuned:
            _hole("w8_failure_closure_was_retune_not_retitle")
    if freeze_retarget:
        _hole("design_freeze_v4_retargeted")
    if usgs98:
        _hole("usgs_98_list_downloaded")
    return holes


def assert_w7_not_t2_contract(
    manifest: Mapping[str, Any], *, require_keys: bool = True
) -> None:
    """Honest W7 stop-loss. Raises if a confirmatory T2 claim leaks."""

    if require_keys:
        missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
        if missing:
            raise AssertionError(f"missing W7 contract keys: {missing}")
    n_networks = int(manifest.get("n_networks") or 0)
    if _as_bool(manifest.get("passed")):
        raise AssertionError("W7 must not write passed true at n<<100")
    evaluate = _nested(manifest, "evaluate_success")
    if _as_bool(evaluate.get("passed")):
        raise AssertionError("evaluate_success.passed must stay false")
    if _as_bool(manifest.get("confirmatory_eligible")):
        raise AssertionError("confirmatory_eligible true requires n>=100")
    if str(manifest.get("go_no_go") or GO_NO_GO) != GO_NO_GO:
        raise AssertionError("go_no_go must stay NO_GO_T2_PRIMARY_EVIDENCE")
    if _inference_token(manifest) == "tested":
        raise AssertionError("must not report network CI tested at n<<100")
    if n_networks >= N_NETWORKS_MIN_T2:
        raise AssertionError("claimed n>=100 without a real T2 stock of 100")
    if _as_bool(manifest.get("europe_complete_enough_used")):
        raise AssertionError("Europe catalog/5.91 overlap is not a T2 n increment")
    if _as_bool(manifest.get("hubeau_correcte_t8_usable")):
        raise AssertionError("hubeau_correcte_t8_usable is a lie while Correcte=0")
    if _as_bool(manifest.get("sealed_outcomes_opened")):
        raise AssertionError("sealed HUC8 / FOEN / Loire must stay closed")
    if _as_bool(manifest.get("mh_blocked_cells_relabeled_executable")):
        raise AssertionError("M/H-blocked cells must not be relabeled executable")
    if _as_bool(manifest.get("operator_retuned_because_incremental_r2_lt_005")):
        raise AssertionError("incremental R² < 0.05 is W8 retitle, not retune")
    if _as_bool(manifest.get("twin_e_retuned")):
        raise AssertionError("Twin E / φ retune is forbidden")
    if _as_bool(manifest.get("design_freeze_v4_retargeted")):
        raise AssertionError("design_freeze_v4 must not be retargeted")


__all__ = [
    "CODE4_LIVE_SITES",
    "GO_NO_GO",
    "INCREMENTAL_R2_W8_FLOOR",
    "INFERENCE_WITHHELD",
    "MH_BLOCKED",
    "MIN_CONCURRENT_DAYS",
    "MIN_STATIONS",
    "NA_OPEN_6YR_DEVELOPMENT",
    "NA_OPEN_6YR_FAILURE_CLOSURE",
    "NA_OPEN_6YR_VALIDATION",
    "NA_OPEN_8YR",
    "NA_OPEN_8YR_DEVELOPMENT",
    "NA_OPEN_8YR_VALIDATION",
    "NEVER_SEALED_TOKENS",
    "N_EXECUTABLE_BD",
    "N_MH_AUXILIARY_EXPECTED",
    "N_MH_AUXILIARY_TERMINAL",
    "N_MH_STRUCTURAL_NOT_APPLICABLE",
    "N_NETWORKS_MIN_T2",
    "OVERLAPPING_DAILY_YEARS_MIN",
    "REQUIRED_MANIFEST_KEYS",
    "SANDRE_CORRECTE",
    "SANDRE_LABEL",
    "SANDRE_NON_QUALIFIE",
    "SEALED_HUC8_PAD_EXAMPLE",
    "UK_EA_BEST_OVERLAP_CONCURRENT_DAYS",
    "UK_EA_BEST_OVERLAP_NETWORK",
    "UK_EA_BEST_OVERLAP_N_STATIONS",
    "UK_EA_BEST_OVERLAP_YEARS",
    "UK_EA_HYDROMETRIC_CLUSTERS_50KM",
    "UK_EA_N_COMPLETE_ENOUGH",
    "UK_EA_SPATIAL_CATALOG_CLUSTERS_50KM",
    "W7_FIRST_LAYER",
    "W7_PURPOSE",
    "WORKLOAD_SHA256",
    "assert_w7_not_t2_contract",
    "europe_does_not_increment_t2",
    "executable_count_after_mh_relabel",
    "flag_only_w7_t2_done_holes",
    "mh_cell_is_blocked",
    "n_cannot_reach_floor_by_padding",
    "naive_relabel_code4_as_correcte",
    "naive_relabel_mh_as_executable",
    "network_ci_status",
    "operator_or_phi_retune_licensed",
    "sandre_code_is_t8_eligible",
    "t2_confirmatory_eligible",
    "t8_countable",
    "w7_information_is_first_layer",
    "w8_failure_closure_action",
]
