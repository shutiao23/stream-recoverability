from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.data.rws_temperature import NETWORKS, RIVER_NETWORKS
from stream_recoverability.experiments.wrr_revision.headroom import oracle_gated_donor
from stream_recoverability.experiments.wrr_revision.universe import (
    classify_waterbody,
    evidence_use,
    exclusion_reason,
    station_year_coverage,
    year_has_ended,
)


def test_rws_networks_split_into_river_and_non_river() -> None:
    rivers = {classify_waterbody(nid)["waterbody_family"] for nid in RIVER_NETWORKS}
    assert rivers == {"river"}
    non_river = [nid for nid in NETWORKS if nid not in RIVER_NETWORKS]
    classes = {nid: classify_waterbody(nid) for nid in non_river}
    assert all(item["waterbody_family"] == "non_river" for item in classes.values())
    assert classify_waterbody("rws_noordzee")["waterbody_class"] == "sea"
    assert classify_waterbody("rws_waddenzee")["waterbody_class"] == "sea"
    assert classify_waterbody("rws_ijsselmeer_markermeer")["waterbody_class"] == "lake"
    assert classify_waterbody("rws_amsterdam_rijnkanaal")["waterbody_class"] == "canal"
    assert classify_waterbody("ccg_st_lawrence_ship_channel")["waterbody_class"] == "canal"
    assert classify_waterbody("arso_sava")["waterbody_class"] == "river"
    assert classify_waterbody("huc8_17090012")["waterbody_class"] == "river"


def test_legacy_qc_flag_does_not_override_explicit_river() -> None:
    out = classify_waterbody("rws_maas", qc_status="non_river_domain_excluded")
    assert out["waterbody_class"] == "river"


def test_year_ended_uses_as_of_date() -> None:
    assert year_has_ended(2025, as_of="2026-09-07")
    assert not year_has_ended(2026, as_of="2026-09-07")
    assert year_has_ended(2026, as_of="2026-12-31")


def test_station_year_coverage_does_not_impute_truth() -> None:
    index = pd.date_range("2020-01-01", "2021-06-30", freq="D")
    panel = pd.DataFrame(
        {
            "target": 10.0,
            "donor": 11.0,
        },
        index=index,
    )
    panel.loc["2020-02-01", "target"] = np.nan
    coverage = station_year_coverage(panel, "demo", as_of="2026-09-07")
    y2020 = coverage.loc[coverage["station_id"].eq("target") & coverage["year"].eq(2020)].iloc[0]
    y2021 = coverage.loc[coverage["station_id"].eq("target") & coverage["year"].eq(2021)].iloc[0]
    assert y2020["expected_days"] == 366
    assert y2020["missing_days"] == 1
    assert bool(y2020["full_calendar_year"]) is False
    assert np.isnan(y2020["annual_hottest_30"])
    assert y2021["expected_days"] == 365
    assert y2021["observed_days"] < 365
    assert bool(y2021["full_calendar_year"]) is False
    assert y2020["n_donors_any"] == 1


def test_exclusion_and_evidence_use() -> None:
    assert (
        exclusion_reason(
            has_temperature=True,
            waterbody_family="non_river",
            observed_days=365,
            full_calendar_year=True,
            year_ended=True,
        )
        == "non_river_waterbody"
    )
    assert evidence_use("v16_confirmation_scored", True) == "retrospective_opened"
    assert evidence_use("unscored_available", True) == "candidate_unseen"
    assert evidence_use("first_panel_development", False) == "excluded_from_annual_main"


def test_oracle_keeps_positive_gated_donor_benefit() -> None:
    series = pd.Series([0.2, -0.4, 0.0])
    out = oracle_gated_donor(series)
    assert list(out) == [0.2, 0.0, 0.0]


def test_donor_only_ignores_missing_right_boundary() -> None:
    from stream_recoverability.experiments.wrr_revision.features import base_feature_frame
    from stream_recoverability.experiments.wrr_revision.information import (
        donor_only_right_boundary_delta,
        recoverer_supported,
    )
    from stream_recoverability.experiments.wrr_revision.recoverers import fit_station_recoverers

    index = pd.date_range("2014-01-01", periods=365 * 6, freq="D")
    day = np.arange(len(index), dtype=float)
    season = 12.0 + 8.0 * np.sin(2.0 * np.pi * day / 365.25)
    panel = pd.DataFrame(
        {
            "target": season + 0.4 * np.sin(day / 19.0),
            "donor_a": season + 0.2 * np.cos(day / 11.0),
            "donor_b": 0.8 * season + 1.5,
        },
        index=index,
    )
    train = pd.Series(panel.index.year <= 2017, index=panel.index)
    features = base_feature_frame(panel, donors=("donor_a", "donor_b"))
    fitted = fit_station_recoverers(
        panel,
        target_station="target",
        donors=("donor_a", "donor_b"),
        train_mask=train,
        features=features,
        include_external=False,
        include_names=("doy_climatology", "donor_only_ridge", "linear_interp"),
    )
    start = 2000
    length = 30
    delta = donor_only_right_boundary_delta(
        fitted["donor_only_ridge"],
        panel=panel,
        target_station="target",
        donors=("donor_a", "donor_b"),
        start=start,
        gap_length=length,
    )
    assert delta < 1e-10
    assert recoverer_supported(
        fitted["donor_only_ridge"], donors_present=True, right_present=False, air_present=False
    )
    assert not recoverer_supported(
        fitted["linear_interp"], donors_present=True, right_present=False, air_present=False
    )
    assert not recoverer_supported(
        fitted["donor_only_ridge"], donors_present=False, right_present=True, air_present=False
    )


def test_air2stream3_tracks_air_without_discharge() -> None:
    from stream_recoverability.experiments.air2stream_equivalent import (
        fit_air2stream3,
        simulate_air2stream3,
    )

    index = pd.date_range("2015-01-01", periods=365 * 4, freq="D")
    air = 10.0 + 8.0 * np.sin(2.0 * np.pi * np.arange(len(index)) / 365.25)
    water = np.empty(len(index))
    water[0] = 10.0
    for i in range(len(index) - 1):
        water[i + 1] = water[i] + 0.25 * (2.0 + 0.9 * air[i] - water[i])
    fit = fit_air2stream3(index, water, air, minimum_training_observations=200, warmup_days=20, max_nfev=80)
    predicted = simulate_air2stream3(index, air, fit.parameters, initial_water_temperature_c=float(water[0]))
    rmse = float(np.sqrt(np.mean((predicted[365:] - water[365:]) ** 2)))
    assert rmse < 1.5
    assert not np.isfinite(fit.discharge_reference)
