from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.data.ingest_qc import (
    APPROVAL_COLUMN_ALIASES,
    VERDICT_ACCEPTED,
    VERDICT_ACCEPTED_WITH_FLAGS,
    VERDICT_REJECTED_OUT_OF_RANGE,
    VERDICT_REJECTED_SENTINEL,
    is_nwis_sentinel_value,
    qc_long_frame,
    qc_station_series,
    qc_wide_frame,
    write_ingest_qc_report,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CLEARWATER = (
    REPO_ROOT / "results/framework/public_rivers/clearwater_river_huc17_daily_wide.csv"
)
CLEARWATER_SITE = "13343000"


def test_nwis_sentinel_family_excludes_physical_out_of_range() -> None:
    assert is_nwis_sentinel_value(-999999.0)
    assert is_nwis_sentinel_value(-99999)
    assert is_nwis_sentinel_value(-9999)
    assert is_nwis_sentinel_value(99999)
    assert is_nwis_sentinel_value(999999)
    assert is_nwis_sentinel_value(9999)
    assert not is_nwis_sentinel_value(50.0)
    assert not is_nwis_sentinel_value(46.0)
    assert not is_nwis_sentinel_value(10.0)
    assert not is_nwis_sentinel_value(-4.0)
    assert not is_nwis_sentinel_value(0.0)
    assert not is_nwis_sentinel_value(0)
    assert not is_nwis_sentinel_value(-0.0)


def test_two_sentinels_under_one_percent_still_rejected_sentinel() -> None:
    """Clearwater hole: two -999999 values are ~0.1% of non-null, under the 1% rule."""

    n = 1848
    values = np.full(n, 8.0)
    values[0] = -999999.0
    values[1] = -999999.0
    dates = pd.date_range("2021-01-01", periods=n, freq="D")
    row = qc_station_series(dates, values, site_id=CLEARWATER_SITE)
    assert row["n_sentinel"] == 2
    assert row["n_out_of_range"] == 0
    assert row["n_sentinel"] / row["n_raw"] < 0.01
    assert row["verdict"] == VERDICT_REJECTED_SENTINEL


@pytest.mark.skipif(not CLEARWATER.is_file(), reason="Clearwater wide CSV is not present")
def test_clearwater_13343000_is_rejected_sentinel() -> None:
    wide = pd.read_csv(CLEARWATER)
    report = qc_wide_frame(wide)
    target = report.loc[report["site_id"].astype(str).eq(CLEARWATER_SITE)]
    assert len(target) == 1
    row = target.iloc[0]
    assert row["verdict"] == VERDICT_REJECTED_SENTINEL
    assert int(row["n_sentinel"]) >= 2


@pytest.mark.skipif(not CLEARWATER.is_file(), reason="Clearwater wide CSV is not present")
def test_clearwater_neighbors_not_rejected_sentinel_by_association() -> None:
    wide = pd.read_csv(CLEARWATER)
    report = qc_wide_frame(wide)
    others = report.loc[~report["site_id"].astype(str).eq(CLEARWATER_SITE)]
    assert not others.empty
    leaked = others.loc[others["n_sentinel"].eq(0) & others["verdict"].eq(VERDICT_REJECTED_SENTINEL)]
    assert leaked.empty
    sane = others.loc[others["n_sentinel"].eq(0)]
    assert not sane.empty
    assert sane["verdict"].ne(VERDICT_REJECTED_SENTINEL).all()


def test_two_percent_at_50c_is_rejected_out_of_range_not_sentinel() -> None:
    n = 1000
    values = np.full(n, 10.0)
    values[:20] = 50.0
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    row = qc_station_series(dates, values, site_id="oor")
    assert row["n_sentinel"] == 0
    assert row["n_out_of_range"] == 20
    assert row["verdict"] == VERDICT_REJECTED_OUT_OF_RANGE


def test_one_50c_in_1000_days_is_not_rejected_out_of_range() -> None:
    n = 1000
    values = np.full(n, 10.0)
    values[500] = 50.0
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    row = qc_station_series(dates, values, site_id="rare_oor")
    assert row["n_out_of_range"] == 1
    assert row["n_sentinel"] == 0
    assert row["verdict"] != VERDICT_REJECTED_OUT_OF_RANGE
    assert row["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS


def test_fifteen_day_constant_run_is_flagged() -> None:
    dates = pd.date_range("2020-01-01", periods=15, freq="D")
    values = np.full(15, 10.0)
    row = qc_station_series(dates, values, site_id="stuck")
    assert row["n_constant_run_days"] >= 15
    assert row["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS
    assert "suspect_constant_run" in row["notes"]


def test_fourteen_day_constant_run_is_not_flagged() -> None:
    dates = pd.date_range("2020-01-01", periods=14, freq="D")
    values = np.full(14, 10.0)
    row = qc_station_series(dates, values, site_id="ok_run")
    assert row["n_constant_run_days"] == 0
    assert row["verdict"] == VERDICT_ACCEPTED


def test_day_to_day_jump_over_10c_is_flagged() -> None:
    dates = pd.date_range("2020-06-01", periods=5, freq="D")
    values = np.array([10.0, 22.0, 11.0, 11.5, 12.0])
    row = qc_station_series(dates, values, site_id="jump")
    assert row["n_jump"] >= 1
    assert row["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS
    assert "suspect_jump" in row["notes"]


def test_intra_day_jump_is_flagged_when_pairs_exist() -> None:
    dates = pd.to_datetime(["2020-06-01", "2020-06-01", "2020-06-02"])
    values = np.array([8.0, 19.5, 9.0])
    codes = ["A", "A", "A"]
    row = qc_station_series(dates, values, site_id="intra", approval_codes=codes)
    assert row["n_jump"] >= 1
    assert row["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS


def test_provisional_approval_is_naized_and_excluded_from_qualified_years() -> None:
    dates = pd.date_range("2020-01-01", periods=300, freq="D")
    values = np.full(300, 12.0)
    codes = np.full(300, "P")
    row = qc_station_series(dates, values, site_id="prov", approval_codes=codes)
    assert row["n_provisional_dropped"] == 300
    assert row["qualified_years"] == 0
    assert row["n_raw"] == 300


def test_approved_300_days_count_as_a_qualified_year() -> None:
    dates = pd.date_range("2021-01-01", periods=300, freq="D")
    values = 10.0 + 0.02 * np.arange(300)
    codes = np.full(300, "A")
    row = qc_station_series(dates, values, site_id="approved", approval_codes=codes)
    assert row["n_provisional_dropped"] == 0
    assert row["qualified_years"] == 1
    assert row["n_constant_run_days"] == 0
    assert row["verdict"] == VERDICT_ACCEPTED


def test_299_approved_days_do_not_increment_qualified_years() -> None:
    short = pd.date_range("2020-01-01", periods=299, freq="D")
    long = pd.date_range("2021-01-01", periods=300, freq="D")
    dates = pd.DatetimeIndex(np.concatenate([short, long]))
    values = 9.0 + 0.01 * np.arange(len(dates))
    codes = np.full(len(dates), "Approved")
    row = qc_station_series(dates, values, site_id="years", approval_codes=codes)
    assert row["qualified_years"] == 1


def test_missing_approval_column_is_not_automatic_sentinel_accept() -> None:
    dates = pd.date_range("2021-01-01", periods=10, freq="D")
    values = np.full(10, 7.0)
    values[3] = -9999.0
    row = qc_station_series(dates, values, site_id="no_codes")
    assert row["n_provisional_dropped"] == 0
    assert "approval_codes_absent" in row["notes"]
    assert row["verdict"] == VERDICT_REJECTED_SENTINEL


def test_quality_approved_is_not_treated_as_usgs_approval() -> None:
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "site_id": "x",
            "value": np.full(5, 11.0),
            "quality_approved": True,
        }
    )
    report = qc_long_frame(frame)
    assert report.iloc[0]["n_provisional_dropped"] == 0
    assert "approval_codes_absent" in report.iloc[0]["notes"]


def test_wide_qc_is_station_level() -> None:
    dates = pd.date_range("2020-01-01", periods=20, freq="D")
    wide = pd.DataFrame(
        {
            "date": dates,
            "13343000": np.concatenate(([-999999.0, -999999.0], np.full(18, 8.0))),
            "13340000": np.linspace(1.0, 4.0, 20),
        }
    )
    report = qc_wide_frame(wide)
    by_site = report.set_index("site_id")
    assert by_site.loc["13343000", "verdict"] == VERDICT_REJECTED_SENTINEL
    assert by_site.loc["13340000", "verdict"] != VERDICT_REJECTED_SENTINEL
    assert int(by_site.loc["13340000", "n_sentinel"]) == 0


def test_write_ingest_qc_report(tmp_path: Path) -> None:
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    frame = qc_wide_frame(pd.DataFrame({"date": dates, "s1": [1.0, 2.0, 3.0]}))
    dest = tmp_path / "ingest_qc_report.csv"
    write_ingest_qc_report(frame, dest)
    loaded = pd.read_csv(dest)
    assert list(loaded.columns)[:8] == [
        "site_id",
        "n_raw",
        "n_sentinel",
        "n_out_of_range",
        "n_provisional_dropped",
        "n_constant_run_days",
        "n_jump",
        "qualified_years",
    ]
    assert "verdict" in loaded.columns
    assert loaded.iloc[0]["site_id"] == "s1"


def test_estimated_approved_is_kept_and_flagged() -> None:
    dates = pd.date_range("2021-01-01", periods=300, freq="D")
    values = 10.0 + 0.02 * np.arange(300)
    nwis = qc_station_series(
        dates, values, site_id="est_nwis", approval_codes=np.full(300, "A,e")
    )
    assert nwis["n_provisional_dropped"] == 0
    assert nwis["qualified_years"] == 1
    assert nwis["n_sentinel"] == 0
    assert "estimated_approved" in nwis["notes"]
    assert nwis["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS

    water_data = qc_station_series(
        dates,
        values,
        site_id="est_api",
        approval_codes=np.full(300, "Approved,Estimated"),
    )
    assert water_data["n_provisional_dropped"] == 0
    assert "estimated_approved" in water_data["notes"]
    assert water_data["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS

    frame = pd.DataFrame(
        {
            "date": dates,
            "site_id": "est_cols",
            "value": values,
            "approval_status": "Approved",
            "qualifier": "Estimated",
        }
    )
    combined = qc_long_frame(frame).iloc[0]
    assert combined["n_provisional_dropped"] == 0
    assert "estimated_approved" in combined["notes"]
    assert combined["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS


def test_zero_celsius_is_not_a_sentinel() -> None:
    dates = pd.date_range("2021-01-01", periods=30, freq="D")
    values = np.concatenate((np.zeros(20), np.linspace(0.1, 2.0, 10)))
    row = qc_station_series(dates, values, site_id="ice_zero")
    assert row["n_sentinel"] == 0
    assert row["verdict"] != VERDICT_REJECTED_SENTINEL
    assert row["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS
    assert "suspect_constant_run" in row["notes"]


def test_bare_cd_is_not_an_approval_alias() -> None:
    assert "cd" not in {alias.lower() for alias in APPROVAL_COLUMN_ALIASES}
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "site_id": "x",
            "value": np.full(5, 11.0),
            "cd": ["P"] * 5,
        }
    )
    report = qc_long_frame(frame).iloc[0]
    assert report["n_provisional_dropped"] == 0
    assert "approval_codes_absent" in report["notes"]
    assert report["verdict"] == VERDICT_ACCEPTED


def test_provisional_sentinels_still_rejected_before_approval_filter() -> None:
    dates = pd.date_range("2021-01-01", periods=100, freq="D")
    values = np.full(100, 8.0)
    values[0] = -999999.0
    values[1] = -999999.0
    codes = np.full(100, "A")
    codes[0] = "P"
    codes[1] = "['P', 'Dis']"
    row = qc_station_series(dates, values, site_id="13343000", approval_codes=codes)
    assert row["n_sentinel"] == 2
    assert row["verdict"] == VERDICT_REJECTED_SENTINEL
    assert row["n_provisional_dropped"] == 0


def test_dis_eqp_and_provisional_are_dropped() -> None:
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    values = np.full(10, 8.0)
    for code in ("P", "Dis", "Eqp", "Provisional"):
        row = qc_station_series(
            dates, values, site_id="drop", approval_codes=np.full(10, code)
        )
        assert row["n_provisional_dropped"] == 10
        assert "estimated_approved" not in row["notes"]
        assert row["n_sentinel"] == 0


def test_ice_qualifier_is_flagged_not_numeric_sentinel() -> None:
    dates = pd.date_range("2021-01-01", periods=300, freq="D")
    values = np.concatenate((np.zeros(10), np.linspace(0.2, 8.0, 290)))
    codes = ["['A', 'Ice']"] * 10 + ["['A']"] * 290
    row = qc_station_series(dates, values, site_id="ice", approval_codes=codes)
    assert row["n_sentinel"] == 0
    assert row["n_provisional_dropped"] == 0
    assert "ice_affected" in row["notes"]
    assert row["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS
    assert row["verdict"] != VERDICT_REJECTED_SENTINEL


def test_kelvin_median_is_flagged_not_sentinel() -> None:
    dates = pd.date_range("2016-01-01", periods=365, freq="D")
    kelvin = 273.15 + np.linspace(4.0, 12.0, 365)
    row = qc_station_series(dates, kelvin, site_id="kelvin")
    assert row["n_sentinel"] == 0
    assert "suspect_kelvin_units" in row["notes"]
    assert row["verdict"] != VERDICT_REJECTED_SENTINEL
    assert row["verdict"] == VERDICT_REJECTED_OUT_OF_RANGE

    celsius = np.linspace(4.0, 12.0, 365)
    spiked = celsius.copy()
    spiked[10] = 273.15
    spike_row = qc_station_series(dates, spiked, site_id="spike")
    assert "suspect_kelvin_units" not in spike_row["notes"]
    assert spike_row["n_sentinel"] == 0
    assert spike_row["verdict"] == VERDICT_ACCEPTED_WITH_FLAGS
