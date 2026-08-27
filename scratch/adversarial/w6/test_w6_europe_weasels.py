"""W6 Europe weasel tests. Production code and audits are imported read-only.

A flag-only "W6 done" PR must fail these tests. Scratch pack does not edit
production files, download the USGS 98-list, open Loire/Swiss temperatures,
or retarget design_freeze_v4.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

W6 = Path(__file__).resolve().parent
REPO = W6.parents[2]
SRC = REPO / "src"
if str(W6) not in sys.path:
    sys.path.insert(0, str(W6))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spatial_cluster import (  # noqa: E402
    MAX_PAIR_KM,
    geodesic_km,
    name_clusters,
    spatial_clusters_50km,
    toy_too_wide_for_50km,
    toy_uk_stations,
)
from stream_recoverability.experiments.contracts import (  # noqa: E402
    DEFAULT_DESIGN_PATH,
    EXECUTABLE_DESIGN_VERSION,
    SUPPORTED_EXECUTABLE_DESIGN_VERSIONS,
)
from w6_contract import (  # noqa: E402
    CODE4_LIVE_N_POINTS,
    CODE4_LIVE_SITES,
    INFERENCE_WITHHELD,
    MIN_CONCURRENT_DAYS,
    MIN_STATIONS,
    NA_OPEN_6YR_FAILURE_CLOSURE,
    NA_OPEN_8YR,
    N_NETWORKS_MIN_T2,
    OVERLAPPING_DAILY_YEARS_MIN,
    REQUIRED_MANIFEST_KEYS,
    SANDRE_CORRECTE,
    SANDRE_NON_QUALIFIE,
    UK_EA_NAME_CLUSTER_RIVER,
    UK_EA_NAME_CLUSTERS_3PLUS,
    UK_EA_N_BLANK_RIVER,
    UK_EA_N_STATIONS,
    UK_EA_N_WITH_RIVER_NAME,
    assert_w6_not_done_contract,
    europe_adds_t8_not_t2,
    flag_only_w6_done_holes,
    naive_daily_years_from_date_opened,
    naive_relabel_code4_as_correcte,
    network_ci_status,
    sandre_code_is_t8_eligible,
    t8_countable,
    years_from_catalog_span,
)

CONTRACT = W6 / "manifest_contract.json"
FLAG_ONLY = W6 / "demo" / "flag_only_w6_done.json"
W6_MANIFEST = REPO / "results/framework/public_catalog/w6_europe_source_audit_manifest.json"
HUBEAU_SITES = REPO / "results/framework/public_catalog/w6_hubeau_correct_station_audit.csv"
HUBEAU_SPANS = REPO / "results/framework/public_catalog/hubeau_non_loire_chronicle_spans.csv"
UK_CATALOG = REPO / "results/framework/public_catalog/uk_ea_temperature_stations.csv"
UK_CATALOG_MANIFEST = REPO / "results/framework/public_catalog/uk_ea_catalog_manifest.json"
UK_CLUSTERS = REPO / "results/framework/public_catalog/uk_ea_river_clusters.csv"
UK_DAILY_MANIFEST = REPO / "results/framework/public_rivers_europe/uk_ea_daily_manifest.json"
UK_OVERLAP = REPO / "results/framework/public_rivers_europe/uk_ea_overlap.csv"
FOEN_AUDIT = REPO / "results/framework/public_catalog/w6_foen_public_api_audit.json"
FREEZE_V9 = REPO / "configs/design_freeze_v9.yaml"
QC_DEV = (
    REPO
    / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6/development/qc_manifest.json"
)
QC_VAL = (
    REPO
    / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6/validation/qc_manifest.json"
)


def _production_evidence() -> dict:
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    uk_daily = json.loads(UK_DAILY_MANIFEST.read_text(encoding="utf-8"))
    uk_cat = json.loads(UK_CATALOG_MANIFEST.read_text(encoding="utf-8"))
    return {
        "hubeau_n_sites_with_sandre_correcte_observations": int(
            w6.get("hubeau_n_sites_with_sandre_correcte_observations") or 0
        ),
        "uk_ea_n_complete_enough": int(uk_daily.get("n_complete_enough") or 0),
        "n_europe_complete_enough": int(w6.get("n_europe_complete_enough_added") or 0),
        "uk_ea_n_name_clusters_3plus": int(uk_cat.get("n_name_clusters_3plus") or 0),
        "uk_ea_spatial_50km_attempted": False,
    }


def test_manifest_contract_required_keys() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for key in REQUIRED_MANIFEST_KEYS:
        assert key in contract
    assert contract["countable_toward_t8"] is False
    assert contract["hubeau_correcte_t8_usable"] is False
    assert contract["europe_daily_years_invented"] is False
    assert contract["loire_downloaded"] is False
    assert contract["swiss_countable_toward_t8"] is False
    assert contract["catalog_98_name_huc2_downloaded"] is False
    assert contract["passed"] is False
    assert contract["t2_passed"] is False
    assert contract["n_networks_min_t2"] == N_NETWORKS_MIN_T2
    assert contract["network_interval"]["inference_status"] == INFERENCE_WITHHELD
    assert_w6_not_done_contract(contract)


def test_flag_only_w6_done_pr_is_rejected() -> None:
    lying = json.loads(FLAG_ONLY.read_text(encoding="utf-8"))
    evidence = _production_evidence()
    holes = flag_only_w6_done_holes(lying, evidence)
    assert "hubeau_correcte_zero_counted_as_t8" in holes
    assert "countable_toward_t8_without_3x8_daily" in holes
    assert "uk_ea_complete_enough_invented" in holes
    assert "name_only_clustering_stopped_after_derwent" in holes
    assert "w6_sold_as_t2_pass" in holes
    assert "network_ci_tested_at_n_lt_100" in holes
    with pytest.raises(
        AssertionError,
        match="hubeau_correcte_t8_usable|countable_toward_t8|passed|tested",
    ):
        assert_w6_not_done_contract(lying)


def test_honest_production_w6_audit_is_not_a_done_claim() -> None:
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    assert w6["hubeau_n_sites_with_sandre_correcte_observations"] == 0
    assert w6["hubeau_n_strict_8yr_concurrent_complete"] == 0
    assert w6["hubeau_unqualified_code_4_accepted"] is False
    assert w6["n_europe_complete_enough_added"] == 0
    assert w6["countable_toward_t8"] is False
    assert w6["loire_downloaded"] is False
    assert w6["swiss_countable_toward_t8"] is False
    assert w6["passed"] is False
    holes = flag_only_w6_done_holes(w6, _production_evidence())
    assert "hubeau_correcte_zero_counted_as_t8" not in holes
    assert "w6_sold_as_t2_pass" not in holes
    assert "name_only_clustering_stopped_after_derwent" in holes
    for key in ("hubeau_correcte_t8_usable", "europe_daily_years_invented"):
        assert key not in w6
    assert_w6_not_done_contract(w6, require_keys=False)
    patched = dict(w6)
    patched["hubeau_correcte_t8_usable"] = True
    patched["europe_daily_years_invented"] = False
    with pytest.raises(AssertionError, match="hubeau_correcte_t8_usable"):
        assert_w6_not_done_contract(patched, require_keys=False)


def test_hubeau_code4_live_sites_have_zero_correcte() -> None:
    sites = pd.read_csv(HUBEAU_SITES, dtype={"site_id": str})
    positive = (
        pd.to_numeric(sites["n_correct_instantaneous"], errors="coerce").fillna(0).gt(0).sum()
    )
    assert int(positive) == 0
    for site_id in CODE4_LIVE_SITES:
        row = sites.loc[sites["site_id"].astype(str).eq(site_id)]
        assert not row.empty, site_id
        assert int(row["n_correct_instantaneous"].iloc[0] or 0) == 0
        assert str(row["quality_code_required"].iloc[0]) == SANDRE_CORRECTE


def test_instantaneous_span_is_not_eight_daily_years() -> None:
    spans = pd.read_csv(HUBEAU_SPANS, dtype={"site_id": str})
    for site_id, n_points in CODE4_LIVE_N_POINTS.items():
        row = spans.loc[spans["site_id"].astype(str).eq(site_id)].iloc[0]
        assert int(float(row["n_points_reported"])) == n_points
        assert str(row["temporal_resolution"]) == "instantaneous_not_daily"
        assert bool(row["countable_public_daily"]) is False
        span_years = float(row["span_years"])
        assert span_years > OVERLAPPING_DAILY_YEARS_MIN
        assert (
            t8_countable(
                n_stations=3,
                overlapping_daily_years=span_years,
                days_with_min_stations=MIN_CONCURRENT_DAYS,
                quality_ok=True,
                instantaneous_span_years=span_years,
            )
            is False
        )


def test_relabeling_code4_as_correcte_is_not_t8() -> None:
    assert sandre_code_is_t8_eligible(SANDRE_NON_QUALIFIE) is False
    assert sandre_code_is_t8_eligible(SANDRE_CORRECTE) is True
    relabeled = naive_relabel_code4_as_correcte(SANDRE_NON_QUALIFIE)
    assert relabeled == SANDRE_CORRECTE
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            code_qualification=SANDRE_NON_QUALIFIE,
        )
        is False
    )
    # Naive relabel would make the *relabeled* token look eligible. Contract
    # still keys off the raw code 4.
    assert sandre_code_is_t8_eligible(SANDRE_NON_QUALIFIE) is False
    assert relabeled != SANDRE_NON_QUALIFIE


def test_hubeau_correcte_t8_usable_false_while_audit_is_zero() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    assert contract["hubeau_correcte_t8_usable"] is False
    assert w6["hubeau_n_sites_with_sandre_correcte_observations"] == 0
    usable = dict(contract)
    usable["hubeau_correcte_t8_usable"] = True
    with pytest.raises(AssertionError, match="hubeau_correcte_t8_usable"):
        assert_w6_not_done_contract(usable)


def test_uk_ea_catalog_is_metadata_not_daily_years() -> None:
    stations = pd.read_csv(UK_CATALOG)
    assert len(stations) == UK_EA_N_STATIONS
    river = stations["river"].fillna("").astype(str).str.strip()
    assert int(river.ne("").sum()) == UK_EA_N_WITH_RIVER_NAME
    assert int(river.eq("").sum()) == UK_EA_N_BLANK_RIVER
    lat = pd.to_numeric(stations["latitude"], errors="coerce")
    lon = pd.to_numeric(stations["longitude"], errors="coerce")
    assert int((lat.notna() & lon.notna()).sum()) == UK_EA_N_STATIONS
    assert bool(stations["has_public_daily_span"].fillna(False).astype(bool).any()) is False
    catalog = json.loads(UK_CATALOG_MANIFEST.read_text(encoding="utf-8"))
    assert catalog["n_stations"] == UK_EA_N_STATIONS
    assert catalog["n_with_river_name"] == UK_EA_N_WITH_RIVER_NAME
    assert catalog["n_name_clusters_3plus"] == UK_EA_NAME_CLUSTERS_3PLUS
    assert catalog["countable_toward_t8"] is False
    assert catalog["europe_daily_years_invented"] is False
    assert "dateOpened is not a daily-year span" in catalog["what_this_is_not"]


def test_date_opened_years_are_not_overlapping_daily_years() -> None:
    fake = naive_daily_years_from_date_opened("1964-01-01", "2026-08-26")
    assert fake > OVERLAPPING_DAILY_YEARS_MIN
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=fake,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            date_opened_years=fake,
        )
        is False
    )
    stations = pd.read_csv(UK_CATALOG)
    as_of = pd.Timestamp("2026-08-26")
    opened = pd.to_datetime(stations["date_opened"], errors="coerce")
    invented = (as_of - opened).dt.days / 365.25
    assert int((invented >= OVERLAPPING_DAILY_YEARS_MIN).sum()) >= 1000
    daily = json.loads(UK_DAILY_MANIFEST.read_text(encoding="utf-8"))
    assert daily["n_complete_enough"] == 0
    assert daily["europe_daily_years_invented"] is False


def test_derwent_download_is_not_complete_enough() -> None:
    overlap = pd.read_csv(UK_OVERLAP)
    row = overlap.iloc[0]
    assert str(row["river"]) == UK_EA_NAME_CLUSTER_RIVER
    assert int(row["n_stations"]) < MIN_STATIONS
    assert float(row["overlap_years"] or 0) < OVERLAPPING_DAILY_YEARS_MIN
    assert bool(row["complete_enough"]) is False
    assert bool(row["countable_toward_t8"]) is False
    daily = json.loads(UK_DAILY_MANIFEST.read_text(encoding="utf-8"))
    assert daily["n_complete_enough"] == 0
    assert daily["n_rivers_attempted"] == 1


def test_production_name_clustering_found_only_derwent_then_stopped() -> None:
    clusters = pd.read_csv(UK_CLUSTERS)
    assert len(clusters) == UK_EA_NAME_CLUSTERS_3PLUS
    assert str(clusters["river"].iloc[0]) == UK_EA_NAME_CLUSTER_RIVER
    assert int(clusters["n_stations"].iloc[0]) == 3
    assert bool(clusters["countable_public_daily"].iloc[0]) is False
    daily = json.loads(UK_DAILY_MANIFEST.read_text(encoding="utf-8"))
    assert daily["n_rivers_attempted"] == 1
    assert daily["n_complete_enough"] == 0


def test_toy_spatial_50km_recovers_blank_name_triplet_name_clustering_drops() -> None:
    toy = toy_uk_stations()
    named = name_clusters(toy)
    spatial = spatial_clusters_50km(toy)
    assert named.empty
    assert not spatial.empty
    assert int(spatial["n_stations"].min()) >= MIN_STATIONS
    unnamed = spatial.loc[spatial["site_ids"].str.contains("unnamed_a")]
    assert not unnamed.empty
    assert set(unnamed.iloc[0]["site_ids"].split(",")) >= {
        "unnamed_a",
        "unnamed_b",
        "unnamed_c",
    }
    assert float(unnamed.iloc[0]["max_pair_km"]) <= MAX_PAIR_KM
    assert bool(spatial["countable_toward_t8"].any()) is False
    assert bool(spatial["catalog_cluster_only"].all()) is True


def test_name_cluster_wider_than_50km_is_not_a_spatial_network() -> None:
    wide = toy_too_wide_for_50km()
    named = name_clusters(wide)
    spatial = spatial_clusters_50km(wide)
    assert len(named) == 1
    assert int(named["n_stations"].iloc[0]) == 3
    ab = geodesic_km(53.00, -1.00, 53.00, -1.90)
    ac = geodesic_km(53.00, -1.00, 53.80, -1.00)
    assert ab > MAX_PAIR_KM
    assert ac > MAX_PAIR_KM
    assert spatial.empty
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=0.0,
            catalog_cluster_only=True,
        )
        is False
    )


def test_spatial_catalog_cluster_still_not_t8() -> None:
    assert (
        t8_countable(
            n_stations=12,
            overlapping_daily_years=0.0,
            catalog_cluster_only=True,
            quality_ok=False,
        )
        is False
    )


def test_loire_swiss_98_list_cannot_pad_t8() -> None:
    freeze = yaml.safe_load(FREEZE_V9.read_text(encoding="utf-8"))
    assert freeze["split_rule"]["loire_swiss_still_not_countable_for_t8"] is True
    assert freeze["clustering_rule"]["do_not_download_name_huc2_98_list"] is True
    foen = json.loads(FOEN_AUDIT.read_text(encoding="utf-8"))
    assert foen["public_graphql_reachable"] is True
    assert foen["temperature_values_requested"] is False
    assert foen["swiss_countable_toward_t8"] is False
    assert "loire_swiss_still_not_countable_for_t8" in foen["swiss_exclusion_reason"]
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            loire=True,
        )
        is False
    )
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            swiss=True,
        )
        is False
    )
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            usgs_98_list=True,
        )
        is False
    )
    w6 = json.loads(W6_MANIFEST.read_text(encoding="utf-8"))
    assert w6["loire_downloaded"] is False
    assert w6["foen_temperature_values_requested"] is False
    padded = {
        "countable_toward_t8": False,
        "hubeau_correcte_t8_usable": False,
        "europe_daily_years_invented": False,
        "loire_downloaded": True,
    }
    with pytest.raises(AssertionError, match="loire_downloaded"):
        assert_w6_not_done_contract(padded)
    swiss_flag = {
        "countable_toward_t8": False,
        "hubeau_correcte_t8_usable": False,
        "europe_daily_years_invented": False,
        "loire_downloaded": False,
        "swiss_countable_toward_t8": True,
        "foen_temperature_values_requested": True,
    }
    holes = flag_only_w6_done_holes(swiss_flag, _production_evidence())
    assert "swiss_opened_or_counted" in holes


def test_design_freeze_v4_was_not_retargeted() -> None:
    assert EXECUTABLE_DESIGN_VERSION == "design_freeze_v4"
    assert DEFAULT_DESIGN_PATH == Path("configs/design_freeze_v4.yaml")
    assert "design_freeze_v9" not in SUPPORTED_EXECUTABLE_DESIGN_VERSIONS
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["design_freeze_v4_retargeted"] is False
    assert contract["catalog_98_name_huc2_downloaded"] is False
    assert contract["sealed_outcomes_opened"] is False


def test_europe_complete_enough_is_not_a_t2_pass() -> None:
    even_if_europe_adds = europe_adds_t8_not_t2(1)
    assert even_if_europe_adds["t2_passed"] is False
    assert even_if_europe_adds["n_after_europe_8yr"] == NA_OPEN_8YR + 1
    assert even_if_europe_adds["n_after_europe_6yr"] == NA_OPEN_6YR_FAILURE_CLOSURE + 1
    assert even_if_europe_adds["n_after_europe_8yr"] < N_NETWORKS_MIN_T2
    assert even_if_europe_adds["network_ci_allowed"] is False
    assert even_if_europe_adds["inference_status"] == INFERENCE_WITHHELD
    zero = europe_adds_t8_not_t2(0)
    assert zero["n_na_open_8yr"] == NA_OPEN_8YR
    assert zero["n_na_open_6yr_failure_closure"] == NA_OPEN_6YR_FAILURE_CLOSURE
    qc = json.loads(QC_DEV.read_text(encoding="utf-8"))
    val = json.loads(QC_VAL.read_text(encoding="utf-8"))
    assert qc["primary_8yr_counts"]["open_complete_enough_total"] == NA_OPEN_8YR
    assert (
        int(qc["n_networks_complete_enough"]) + int(val["n_networks_complete_enough"])
        == NA_OPEN_6YR_FAILURE_CLOSURE
    )
    assert network_ci_status(NA_OPEN_8YR) == INFERENCE_WITHHELD
    assert network_ci_status(NA_OPEN_6YR_FAILURE_CLOSURE) == INFERENCE_WITHHELD
    assert network_ci_status(N_NETWORKS_MIN_T2 - 1) == INFERENCE_WITHHELD


def test_passed_true_or_tested_ci_fails_w6_contract() -> None:
    base = json.loads(CONTRACT.read_text(encoding="utf-8"))
    sold = dict(base)
    sold["passed"] = True
    with pytest.raises(AssertionError, match="passed"):
        assert_w6_not_done_contract(sold)
    tested = dict(base)
    tested["inference_status"] = "tested"
    with pytest.raises(AssertionError, match="tested"):
        assert_w6_not_done_contract(tested)


def test_invented_europe_daily_years_fail_contract() -> None:
    base = json.loads(CONTRACT.read_text(encoding="utf-8"))
    invented = dict(base)
    invented["europe_daily_years_invented"] = True
    with pytest.raises(AssertionError, match="europe_daily_years_invented"):
        assert_w6_not_done_contract(invented)
    assert (
        t8_countable(
            n_stations=3,
            overlapping_daily_years=8.0,
            days_with_min_stations=MIN_CONCURRENT_DAYS,
            quality_ok=True,
            daily_years_invented=True,
        )
        is False
    )
    assert years_from_catalog_span("2008-10-14", "2023-09-27") > 8.0
