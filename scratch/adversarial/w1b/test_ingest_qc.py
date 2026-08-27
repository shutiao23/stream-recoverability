"""Adversarial tests for W1-B competing ingest QC.

Must include Clearwater station 13343000 and the numeric 1% miss.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ingest_qc import (  # noqa: E402
    CLEARWATER_STATION,
    CLEARWATER_WIDE,
    RANGE_NA_REJECT_PROPORTION,
    REPO_ROOT,
    classify_approval,
    clearwater_one_percent_counterexample,
    covariance_poison_summary,
    is_nwis_numeric_sentinel,
    naive_one_percent_verdict,
    parse_qualifier_tokens,
    run_ingest_qc,
    write_ingest_qc_report,
)

CLEARWATER_LONG = REPO_ROOT / "data/public_rivers/nwis/13343000_2000-01-01_2024-12-31.csv"


def _long_frame(
    *,
    station: str = "99999999",
    dates: pd.DatetimeIndex | None = None,
    values: list[float] | np.ndarray | None = None,
    qualifier: list[str] | str | None = None,
    approval_status: list[str] | str | None = None,
    quality_approved: list[bool] | bool | None = None,
) -> pd.DataFrame:
    if dates is None:
        dates = pd.date_range("2020-01-01", periods=len(values or []), freq="D")
    n = len(dates)
    if values is None:
        values = [8.0] * n
    frame = pd.DataFrame(
        {
            "site_id": [station] * n,
            "date": dates,
            "temperature_c": values,
        }
    )
    if qualifier is not None:
        frame["qualifier"] = qualifier if isinstance(qualifier, list) else [qualifier] * n
    if approval_status is not None:
        frame["approval_status"] = (
            approval_status if isinstance(approval_status, list) else [approval_status] * n
        )
    if quality_approved is not None:
        frame["quality_approved"] = (
            quality_approved if isinstance(quality_approved, list) else [quality_approved] * n
        )
    return frame


def test_one_percent_rule_misses_clearwater_13343000_numerically() -> None:
    proof = clearwater_one_percent_counterexample()
    assert proof["station_id"] == "13343000"
    assert proof["n_numeric"] == 1848
    assert proof["n_sentinel"] == 2
    assert proof["n_physical_range_na"] == 2
    assert proof["sentinel_proportion"] == pytest.approx(2 / 1848)
    assert proof["sentinel_proportion"] == pytest.approx(0.0010822510822510823)
    assert proof["sentinel_proportion"] < RANGE_NA_REJECT_PROPORTION
    assert proof["sentinels_needed_to_trip_one_percent"] == 19
    assert proof["shortfall_vs_one_percent"] == 17
    assert proof["naive_verdict"] == "accepted"


def test_clearwater_13343000_is_rejected_sentinel_on_wide_file() -> None:
    report, _ = run_ingest_qc(CLEARWATER_WIDE)
    row = report.loc[report["station_id"].astype(str) == CLEARWATER_STATION].iloc[0]
    assert row["verdict"] == "rejected_sentinel"
    assert int(row["n_sentinel"]) == 2
    assert int(row["n_numeric"]) == 1848
    assert row["naive_one_percent_verdict"] == "accepted"
    assert row["layout"] == "wide"
    dest = HERE / "clearwater_qc.csv"
    write_ingest_qc_report(report, dest)
    write_ingest_qc_report(report, HERE / "ingest_qc_report.csv")
    assert dest.is_file()


def test_clearwater_13343000_rejected_on_nwis_long_file_too() -> None:
    report, _ = run_ingest_qc(CLEARWATER_LONG)
    assert list(report["station_id"]) == [CLEARWATER_STATION]
    assert report.iloc[0]["verdict"] == "rejected_sentinel"
    assert report.iloc[0]["layout"] == "long"
    assert report.iloc[0]["approval_source"] == "nwis_dv"
    assert int(report.iloc[0]["n_sentinel"]) == 2


def test_approval_first_filter_hides_the_two_sentinels() -> None:
    long = pd.read_csv(CLEARWATER_LONG)
    tokens = long["qualifier"].map(parse_qualifier_tokens)
    approved = tokens.map(lambda items: "A" in {token.upper() for token in items})
    values = pd.to_numeric(long["temperature_c"], errors="coerce")
    approved_values = values.loc[approved]
    assert int(approved_values.shape[0]) == 1846
    assert int(sum(is_nwis_numeric_sentinel(value) for value in approved_values)) == 0
    assert naive_one_percent_verdict(approved_values.tolist()) == "accepted"
    # Competing rule still rejects because the value field contained sentinels.
    report, _ = run_ingest_qc(long)
    assert report.iloc[0]["verdict"] == "rejected_sentinel"


def test_two_sentinels_poison_donor_covariance() -> None:
    summary = covariance_poison_summary()
    poisoned = summary["poisoned"]
    repaired = summary["sentinel_na_ized"]
    assert poisoned["corr"] == pytest.approx(0.07574141669133945, abs=1e-6)
    assert repaired["corr"] == pytest.approx(0.9971627847910749, abs=1e-6)
    assert poisoned["donor_mean"] < -1000
    assert 9.0 < repaired["donor_mean"] < 12.0
    assert poisoned["donor_std"] > 30000
    assert repaired["donor_std"] < 5.0


def test_only_station_13343000_is_rejected_not_the_whole_river() -> None:
    report, _ = run_ingest_qc(CLEARWATER_WIDE)
    assert set(report["station_id"].astype(str)) == {
        "13340000",
        "13341050",
        "13342500",
        "13343000",
    }
    by_station = report.set_index("station_id")["verdict"]
    assert by_station.loc["13343000"] == "rejected_sentinel"
    others = [by_station.loc[station] for station in ("13340000", "13341050", "13342500")]
    assert all(verdict in {"accepted", "accepted_with_flags"} for verdict in others)
    assert "rejected_river" not in set(report["verdict"])
    assert "network_id" not in report.columns


def test_zero_celsius_is_not_a_sentinel() -> None:
    assert is_nwis_numeric_sentinel(0) is False
    assert is_nwis_numeric_sentinel(0.0) is False
    assert is_nwis_numeric_sentinel(-0.0) is False
    dates = pd.date_range("2021-01-01", periods=30, freq="D")
    values = [0.0] * 20 + list(np.linspace(0.1, 2.0, 10))
    report, _ = run_ingest_qc(_long_frame(dates=dates, values=values))
    assert int(report.iloc[0]["n_sentinel"]) == 0
    assert report.iloc[0]["verdict"] != "rejected_sentinel"


@pytest.mark.parametrize(
    "code",
    [-999999, -99999, -9999, 9999, 99999, 999999, -999999.0],
)
def test_other_nwis_sentinels_reject(code: float) -> None:
    assert is_nwis_numeric_sentinel(code) is True
    dates = pd.date_range("2015-01-01", periods=365, freq="D")
    values = [8.0] * 364 + [float(code)]
    report, _ = run_ingest_qc(_long_frame(dates=dates, values=values))
    assert report.iloc[0]["verdict"] == "rejected_sentinel"
    assert report.iloc[0]["naive_one_percent_verdict"] == "accepted"
    assert float(report.iloc[0]["sentinel_proportion"]) < 0.01


def test_ice_qualifier_is_flagged_not_treated_as_numeric_sentinel() -> None:
    dates = pd.date_range("2021-01-01", periods=300, freq="D")
    values = [0.0] * 20 + list(np.linspace(0.2, 8.0, 280))
    qualifiers = ["['A', 'Ice']"] * 20 + ["['A']"] * 280
    report, _ = run_ingest_qc(_long_frame(dates=dates, values=values, qualifier=qualifiers))
    assert int(report.iloc[0]["n_sentinel"]) == 0
    assert "ice_affected" in str(report.iloc[0]["flags"])
    assert report.iloc[0]["verdict"] == "accepted_with_flags"


def test_constant_zero_ice_run_flags_does_not_auto_reject() -> None:
    dates = pd.date_range("2021-01-01", periods=300, freq="D")
    values = [0.0] * 20 + list(np.linspace(0.5, 8.0, 280))
    report, _ = run_ingest_qc(_long_frame(dates=dates, values=values, qualifier="['A']"))
    assert "suspect_constant_run" in str(report.iloc[0]["flags"])
    assert int(report.iloc[0]["max_constant_run_days"]) == 20
    assert report.iloc[0]["verdict"] == "accepted_with_flags"


def test_sensor_flatline_flags_not_reject_unless_other_rejects() -> None:
    dates = pd.date_range("2018-01-01", periods=300, freq="D")
    values = [12.0] * 20 + list(np.linspace(12.2, 18.0, 280))
    report, _ = run_ingest_qc(_long_frame(dates=dates, values=values))
    assert report.iloc[0]["verdict"] == "accepted_with_flags"
    assert "suspect_constant_run" in str(report.iloc[0]["flags"])
    mixed = list(values)
    mixed[3] = -999999.0
    rejected, _ = run_ingest_qc(_long_frame(dates=dates, values=mixed))
    assert rejected.iloc[0]["verdict"] == "rejected_sentinel"


def test_day_to_day_jump_flags_not_reject_and_is_not_median_distance() -> None:
    dates = pd.date_range("2020-01-01", periods=300, freq="D")
    # Slow seasonal rise: |x - median| > 10, but no calendar-day jump > 10.
    seasonal = list(np.linspace(0.0, 24.0, 300))
    median = float(np.median(seasonal))
    assert any(abs(value - median) > 10 for value in seasonal)
    seasonal_report, _ = run_ingest_qc(_long_frame(dates=dates, values=seasonal))
    assert int(seasonal_report.iloc[0]["n_jump_days"]) == 0
    assert "suspect_jump" not in str(seasonal_report.iloc[0]["flags"])

    front = [8.0] * 10 + [19.5] + list(np.linspace(19.6, 21.0, 289))
    jump_report, _ = run_ingest_qc(_long_frame(dates=dates, values=front))
    assert int(jump_report.iloc[0]["n_jump_days"]) == 1
    assert jump_report.iloc[0]["verdict"] == "accepted_with_flags"
    assert "suspect_jump" in str(jump_report.iloc[0]["flags"])


def test_nwis_dv_and_water_data_api_approval_codes() -> None:
    dates = pd.date_range("2019-01-01", periods=365, freq="D")
    values = (10.0 + 2.0 * np.sin(np.linspace(0, 2 * np.pi, 365))).tolist()

    nwis_approved, _ = run_ingest_qc(
        _long_frame(dates=dates, values=values, qualifier="['A']")
    )
    assert nwis_approved.iloc[0]["approval_source"] == "nwis_dv"
    assert nwis_approved.iloc[0]["verdict"] == "accepted"

    nwis_provisional, _ = run_ingest_qc(
        _long_frame(dates=dates, values=values, qualifier="['P']")
    )
    assert nwis_provisional.iloc[0]["verdict"] == "rejected_insufficient_years"
    assert int(nwis_provisional.iloc[0]["n_non_approved_na"]) == 365

    estimated_approved, _ = run_ingest_qc(
        _long_frame(dates=dates, values=values, qualifier="['A', 'e']")
    )
    assert estimated_approved.iloc[0]["verdict"] == "accepted_with_flags"
    assert "estimated_approved" in str(estimated_approved.iloc[0]["flags"])
    assert int(estimated_approved.iloc[0]["n_estimated_kept"]) == 365
    assert int(estimated_approved.iloc[0]["n_non_approved_na"]) == 0

    api_approved, _ = run_ingest_qc(
        _long_frame(dates=dates, values=values, approval_status="Approved")
    )
    assert api_approved.iloc[0]["approval_source"] == "water_data_api"
    assert api_approved.iloc[0]["verdict"] == "accepted"

    api_estimated, _ = run_ingest_qc(
        _long_frame(
            dates=dates,
            values=values,
            approval_status="Estimated",
            qualifier="Estimated",
        )
    )
    assert api_estimated.iloc[0]["verdict"] == "accepted_with_flags"
    assert "estimated_approved" in str(api_estimated.iloc[0]["flags"])

    api_provisional, _ = run_ingest_qc(
        _long_frame(dates=dates, values=values, approval_status="Provisional")
    )
    assert api_provisional.iloc[0]["verdict"] == "rejected_insufficient_years"


def test_quality_approved_is_not_usgs_approval() -> None:
    dates = pd.date_range("2019-01-01", periods=365, freq="D")
    values = (10.0 + 2.0 * np.sin(np.linspace(0, 2 * np.pi, 365))).tolist()
    # Presence-as-eligibility must not be read as USGS Approved.
    legacy, _ = run_ingest_qc(
        _long_frame(dates=dates, values=values, quality_approved=True)
    )
    assert legacy.iloc[0]["approval_source"] == "ignored_quality_approved_not_usgs"
    assert "quality_approved_ignored" in str(legacy.iloc[0]["flags"])

    # quality_approved=True cannot rescue Provisional rows.
    mixed = _long_frame(
        dates=dates,
        values=values,
        qualifier="['P']",
        quality_approved=True,
    )
    report, _ = run_ingest_qc(mixed)
    assert report.iloc[0]["approval_source"] == "nwis_dv"
    assert int(report.iloc[0]["n_non_approved_na"]) == 365
    assert report.iloc[0]["verdict"] == "rejected_insufficient_years"


def test_classify_approval_estimated_is_not_provisional_drop() -> None:
    estimated = classify_approval(("A", "e"), None)
    assert estimated.approved is True
    assert estimated.estimated is True
    assert estimated.provisional is False
    api = classify_approval((), "Estimated")
    assert api.approved is True
    assert api.estimated is True
    assert api.provisional is False
    ignored = classify_approval((), None, quality_approved=True)
    assert ignored.source == "absent"


def test_year_with_fewer_than_300_approved_days_is_not_evaluable() -> None:
    dates = pd.date_range("2016-01-01", periods=299, freq="D")
    report, _ = run_ingest_qc(
        _long_frame(dates=dates, values=[7.0] * 299, qualifier="['A']")
    )
    assert int(report.iloc[0]["n_evaluable_years"]) == 0
    assert int(report.iloc[0]["n_years_not_evaluable"]) == 1
    assert report.iloc[0]["verdict"] == "rejected_insufficient_years"

    dates_ok = pd.date_range("2016-01-01", periods=300, freq="D")
    varying = (7.0 + 0.05 * np.arange(300)).tolist()
    ok, _ = run_ingest_qc(
        _long_frame(dates=dates_ok, values=varying, qualifier="['A']")
    )
    assert int(ok.iloc[0]["n_evaluable_years"]) == 1
    assert ok.iloc[0]["verdict"] == "accepted"


def test_physical_range_over_one_percent_without_sentinel() -> None:
    dates = pd.date_range("2016-01-01", periods=400, freq="D")
    values = [10.0] * 395 + [50.0] * 5  # 5/400 = 1.25% > 1%, not a sentinel
    report, _ = run_ingest_qc(_long_frame(dates=dates, values=values))
    assert int(report.iloc[0]["n_sentinel"]) == 0
    assert int(report.iloc[0]["n_range_na"]) == 5
    assert report.iloc[0]["verdict"] == "rejected_sentinel"


def test_kelvin_converted_only_when_median_near_273() -> None:
    dates = pd.date_range("2016-01-01", periods=365, freq="D")
    celsius = np.linspace(4.0, 12.0, 365)
    c_report, _ = run_ingest_qc(_long_frame(dates=dates, values=celsius.tolist()))
    assert c_report.iloc[0]["unit_handling"] == "assumed_celsius"
    assert c_report.iloc[0]["verdict"] == "accepted"

    kelvin = (celsius + 273.15).tolist()
    k_report, _ = run_ingest_qc(_long_frame(dates=dates, values=kelvin))
    assert k_report.iloc[0]["unit_handling"] == "converted_kelvin_median_near_273"
    assert "unit_converted_kelvin" in str(k_report.iloc[0]["flags"])
    assert k_report.iloc[0]["verdict"] == "accepted_with_flags"
    # A lone 273 in an otherwise °C series is not a unit conversion.
    spiked = celsius.copy()
    spiked[10] = 273.15
    spike_report, _ = run_ingest_qc(_long_frame(dates=dates, values=spiked.tolist()))
    assert spike_report.iloc[0]["unit_handling"] == "assumed_celsius"


def test_wide_and_long_layouts_agree_on_sentinel_station() -> None:
    dates = pd.date_range("2017-01-01", periods=400, freq="D")
    good = np.linspace(6.0, 9.0, 400)
    poisoned = good.copy()
    poisoned[50] = -999999.0
    wide = pd.DataFrame({"date": dates, "11111111": good, "22222222": poisoned})
    long = pd.concat(
        [
            _long_frame(station="11111111", dates=dates, values=good.tolist()),
            _long_frame(station="22222222", dates=dates, values=poisoned.tolist()),
        ],
        ignore_index=True,
    )
    wide_report, _ = run_ingest_qc(wide)
    long_report, _ = run_ingest_qc(long)
    wide_map = wide_report.set_index("station_id")["verdict"]
    long_map = long_report.set_index("station_id")["verdict"]
    assert wide_map.loc["11111111"] == long_map.loc["11111111"] == "accepted"
    assert wide_map.loc["22222222"] == long_map.loc["22222222"] == "rejected_sentinel"
    assert set(wide_report["layout"]) == {"wide"}
    assert set(long_report["layout"]) == {"long"}
