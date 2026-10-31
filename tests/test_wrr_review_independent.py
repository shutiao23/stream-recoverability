"""Guard the new-cohort boundary with synthetic metadata and OSF responses."""

import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
from stream_recoverability.experiments.tr_revision.independent import (
    accepted_public_registration,
    complete_hot_years_in_span,
    metadata_url,
    parse_metadata,
    evaluate_endpoints,
)


def test_metadata_transport_rejects_observations_before_any_request():
    with pytest.raises(ValueError):
        metadata_url("https://example.invalid/data", "GetData", Site="X")
    with pytest.raises(ValueError):
        metadata_url("https://example.invalid/data", "SiteList", service="SOS")
    url = metadata_url(
        "https://example.invalid/data", "MeasurementList", Site="River at Gauge"
    )
    assert "River%20at%20Gauge" in url and "+" not in url
    with pytest.raises(RuntimeError, match="Observation-bearing"):
        parse_metadata(b"<Hilltop><Data><E><T>2000</T><I1>12</I1></E></Data></Hilltop>")
    assert (
        parse_metadata(b"<Hilltop><From>2000-01-01</From></Hilltop>").findtext("From")
        == "2000-01-01"
    )


def test_metadata_year_count_uses_july_june_boundaries_including_leap_year():
    assert (
        complete_hot_years_in_span(
            "2020-07-01T00:00:00+12:00", "2024-06-30T23:59:59+12:00"
        )
        == 4
    )
    assert complete_hot_years_in_span("2024-01-01", "2026-10-24") == 2
    assert complete_hot_years_in_span("2020-07-02", "2024-06-30") == 3


def public_record():
    return {
        "data": {
            "id": "abc12",
            "type": "registrations",
            "attributes": {"public": True, "date_registered": "2020-01-01T00:00:00Z"},
            "relationships": {
                "files": {
                    "links": {
                        "related": {
                            "href": "https://api.osf.io/v2/registrations/abc12/files/"
                        }
                    }
                }
            },
        }
    }


def test_registration_requires_correct_resource_and_real_accepted_timestamp():
    record = public_record()
    assert accepted_public_registration(record, "abc12").startswith("2020")
    record["data"]["type"] = "nodes"
    with pytest.raises(RuntimeError, match="requested registration"):
        accepted_public_registration(record, "abc12")
    record["data"]["type"] = "registrations"
    record["data"]["attributes"]["archiving"] = True
    with pytest.raises(RuntimeError, match="pending"):
        accepted_public_registration(record, "abc12")
    record["data"]["attributes"].pop("archiving")
    record["data"]["attributes"]["date_registered"] = None
    with pytest.raises(RuntimeError, match="timestamp"):
        accepted_public_registration(record, "abc12")


def test_independent_primary_endpoints_never_count_empty_or_unlabeled_as_success():
    c = endpoint_cases()
    result, groups = evaluate_endpoints(c, draws=100)
    assert result["joint_primary_passed"] and len(groups) == 3
    c.loc[0, "eval_truth_h30"] = np.nan
    result, _ = evaluate_endpoints(c, draws=100)
    assert result["n_admitted_without_labels"] == 1 and (
        not result["joint_primary_passed"]
    )
    c["risk_score"] = 0.8
    result, _ = evaluate_endpoints(c, draws=100)
    assert result["E1"]["risk"] is None and (not result["E2"]["passed"])
    c = endpoint_cases()
    c.loc[c.independence_group.eq("A"), "D2"] = 12.0
    result, _ = evaluate_endpoints(c, draws=100)
    assert not result["E2"]["passed"] and result["E2"][
        "fraction_above_10_percent"
    ] == pytest.approx(1 / 3)
    result, _ = evaluate_endpoints(c.iloc[:0], draws=100)
    assert not result["joint_primary_passed"] and result["E1"]["risk"] is None


def test_frozen_prediction_is_independent_of_evaluation_labels():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "independent_prediction_test",
        root / "scripts/495_review_completion_independent_analysis.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    c = endpoint_cases().assign(
        policy_choice="air_ridge",
        air_available=True,
        law_hidden_shares=".5;.6",
        clim_peak=10.0,
        train_h30_mean=10.0,
    )

    class Constant:
        def predict(self, x):
            return np.zeros(len(x))

    class Classifier:
        def predict_proba(self, x):
            return np.tile([0.98, 0.02], (len(x), 1))

    bundle = {
        "features": ["peak_overlap"],
        "quantile_models": [Constant() for _ in range(7)],
        "offsets": {"3|air_ridge": np.linspace(-0.5, 0.5, 7)},
        "classifier": Classifier(),
    }
    a = module.predict(c, bundle)
    c["eval_truth_h30"] += 1000
    b = module.predict(c, bundle)
    pd.testing.assert_frame_equal(
        a[["D2", "risk_score", "D2_q05", "D2_q95"]],
        b[["D2", "risk_score", "D2_q05", "D2_q95"]],
    )
    # A post-calibration correction must not publish a value below a known
    # fully observed window; both annual distribution methods share support.
    c["observed_lower_bound__observed_days"] = 11.0
    for prefix in ("stochastic", "state"):
        for level in (5, 10, 25, 50, 75, 90, 95):
            c[f"{prefix}_h30_q{level:02d}"] = 9.0
    supported = module.predict(c, bundle)
    supported = module.classical_predictions(supported, {"offsets": {
        "stochastic": {"__pooled__": [-2.0] * 7},
        "state": {"__pooled__": [-2.0] * 7},
    }})
    assert (supported.D2 >= 11.0).all()
    for prefix in ("D2", "stochastic_cal", "state_cal"):
        for level in (5, 10, 25, 50, 75, 90, 95):
            assert (supported[f"{prefix}_q{level:02d}"] >= 11.0).all()


def test_native_daily_reference_uses_fixed_nzst_even_at_daylight_saving_transition():
    from stream_recoverability.experiments.tr_revision.native_temperature import (
        native_series,
        strict_daily_mean,
    )

    dates = pd.date_range("2024-09-28T12:00:00Z", periods=24, freq="h")
    raw = native_series(
        native_xml([(d.isoformat(), i) for i, d in enumerate(dates)]),
        site="Synthetic river",
        series_type="StdSeries",
    )
    quality = native_series(
        native_xml([("2024-09-01T00:00:00", 600)], "StdQualSeries"),
        site="Synthetic river",
        series_type="StdQualSeries",
    )
    daily = strict_daily_mean(
        raw, quality, start="2024-09-29", end_exclusive="2024-09-30"
    )
    assert daily.complete_native_day.all() and daily.water_c.iloc[0] == 11.5
    assert daily.date.iloc[0] == pd.Timestamp("2024-09-29")


def test_unknown_quality_missing_samples_and_conflicting_duplicates_cannot_be_complete_days():
    from stream_recoverability.experiments.tr_revision.native_temperature import (
        native_series,
        strict_daily_mean,
    )

    dates = pd.date_range("2024-02-28", periods=96 * 3, freq="15min")
    raw = native_series(
        native_xml([(d.isoformat(), 10.0) for d in dates]),
        site="Synthetic river",
        series_type="StdSeries",
    )
    quality = native_series(
        native_xml(
            [("2024-02-01", 600), ("2024-02-28T12:00:00", 200), ("2024-02-29", 600)],
            "StdQualSeries",
        ),
        site="Synthetic river",
        series_type="StdQualSeries",
    )
    raw = raw.drop(raw.index[-2])
    daily = strict_daily_mean(
        raw, quality, start="2024-02-28", end_exclusive="2024-03-02"
    )
    assert daily.complete_native_day.tolist() == [False, True, False]
    assert daily.water_c.isna().tolist() == [True, False, True]
    conflicting = native_series(
        native_xml([("2024-02-29T00:00:00", 10), ("2024-02-29T00:00:00", 12)]),
        site="Synthetic river",
        series_type="StdSeries",
    )
    assert conflicting.isna().all()
    with pytest.raises(ValueError, match="series type"):
        native_series(
            native_xml([("2024-02-29", 10)], "CheckSeries"),
            site="Synthetic river",
            series_type="StdSeries",
        )


def test_native_air_daily_has_exactly_24_hours_in_fixed_water_clock(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    monkeypatch.setenv(
        "TR_CONFIG", str(root / "configs/wrr_target_recovery_20261022.json")
    )
    spec = importlib.util.spec_from_file_location(
        "independent_native_air_test",
        root / "scripts/497_review_completion_independent_cases.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hours = pd.date_range("2024-09-28T12:00", periods=48, freq="h")
    document = {
        "hourly_units": {"temperature_2m": "°C"},
        "hourly": {
            "time": [d.isoformat() for d in hours],
            "temperature_2m": [10.0] * 48,
        },
    }
    result = module.native_air_daily(document)
    assert result.index.tolist() == [
        pd.Timestamp("2024-09-29"),
        pd.Timestamp("2024-09-30"),
    ]
    assert result.eq(10).all()
    document["hourly"]["temperature_2m"][1] = None
    assert np.isnan(module.native_air_daily(document).iloc[0])
    row = pd.Series({"latitude": -41.0, "longitude": 175.0, "to": "2026-10-24"})
    assert (
        module.weather_parameters(row, 2026, "2026-07-01")["end_date"] == "2026-06-30"
    )


def test_independent_calendar_pool_keeps_own_network_and_handles_no_gaps(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "independent_calendar_test", root / "scripts/431_tr_cases.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dates = pd.date_range("2019-01-01", "2023-12-31")
    path = tmp_path / "daily.csv"
    values = np.ones(len(dates))
    values[(dates >= "2021-02-01") & (dates < "2021-02-06")] = np.nan
    pd.DataFrame({"date": dates, "A": values}).to_csv(path, index=False)
    job = {
        "provider": "nz_gw",
        "roster": "independent",
        "input_path": str(path),
        "network_id": "one",
        "station_key": "nz_gw|A",
        "latitude": -41.0,
    }
    pools = module.calendar_pool("independent", [job])
    chosen = module.pool_for(job, pools)
    assert len(chosen) == 1 and chosen[0]["key"].startswith("nz_gw|A:")
    assert chosen[0]["runs"][0][1] == 5
    pd.DataFrame({"date": dates, "A": 1.0}).to_csv(path, index=False)
    assert module.calendar_pool("independent", [job]) == {}


def endpoint_cases():
    return pd.DataFrame(
        {
            "independence_group": np.repeat(["A", "B", "C"], 40),
            "design_family": "crossed",
            "D2": 10.0,
            "risk_score": 0.02,
            "eval_truth_h30": 10.0,
            "h30__policy": 9.0,
            "peak_overlap": 0.6,
            "D2_q05": 9.5,
            "D2_q95": 10.5,
        }
    )


def native_xml(points, kind="StdSeries"):
    records = "".join(
        (f"<E><T>{stamp}</T><I1>{value}</I1></E>" for stamp, value in points)
    )
    return (
        f'<Hilltop><Measurement SiteName="Synthetic river"><DataSource><TSType>{kind}</TSType><ItemInfo><Units>°C</Units></ItemInfo></DataSource><Data NumItems="1">'
        + records
        + "</Data></Measurement></Hilltop>"
    ).encode()
