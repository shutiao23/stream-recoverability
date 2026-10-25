import numpy as np
import pandas as pd
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from stream_recoverability.experiments.tr_revision.national import (
    native_daily_dates,clean_native_features,annual_source_panel,hydrologic_blocks,
)
from stream_recoverability.experiments.tr_revision.national_inference import project_lower_bound,mi_slopes


def test_national_dates_preserve_native_date_and_convert_only_real_timestamps():
    result=native_daily_dates(["2020-01-01","2020-01-02T04:30:00Z"],"America/New_York")
    assert result.tolist()==[pd.Timestamp("2020-01-01"),pd.Timestamp("2020-01-01")]
    assert hydrologic_blocks("070801050101")[1]==hydrologic_blocks("110100010101")[1]
    assert hydrologic_blocks("140100010101")[1]==hydrologic_blocks("150100010101")[1]


def test_national_qc_never_averages_sensors_or_calls_provisional_data_missing():
    features=[{"time":"2020-01-01","value":0,"approval_status":"Approved","qualifier":None},
              {"time":"2020-01-02","value":10,"approval_status":"Provisional","qualifier":None},
              {"time":"2020-01-03","value":9,"approval_status":"Approved","qualifier":None},
              {"time":"2020-01-03","value":11,"approval_status":"Approved","qualifier":None}]
    row={"station_id":"001","series_id":"a","native_zone":"America/New_York","hydrologic_unit_code":"01010001","latitude":40,"longitude":-70,"first_full_year":2020,"last_full_year":2020}
    daily,qc=clean_native_features(row,features)
    assert daily.water_c.iloc[0]==0 and np.isnan(daily.water_c.iloc[1:]).all()
    annual=annual_source_panel(row,daily).iloc[0]
    assert annual.n_reported==3 and annual.n_absent==363 and annual.n_unapproved==1
    assert not annual.qc_year and not annual.complete


def test_national_complete_h30_requires_every_day_and_lower_bound_requires_30():
    dates=pd.date_range("2020-01-01","2020-12-31")
    daily=pd.DataFrame({"date":dates,"water_c":10.,"reported":True,"unapproved":False,"ambiguous":False,"estimated":False})
    row={"station_id":"001","series_id":"a","hydrologic_unit_code":"01010001","latitude":40,"longitude":-70,"first_full_year":2020,"last_full_year":2020}
    annual=annual_source_panel(row,daily).iloc[0]
    assert annual.complete and annual.observed_H30==10
    daily.loc[0,"water_c"]=np.nan
    annual=annual_source_panel(row,daily).iloc[0]
    assert not annual.complete and np.isnan(annual.observed_H30) and annual.observed_H30_lower_bound==10


def test_national_raw_sentinel_is_not_hidden_by_ambiguous_duplicate_removal():
    row={"station_id":"001","native_zone":"America/New_York"}
    raw=[{"time":"2020-01-01","value":0.,"approval_status":"Approved","qualifier":["Estimated"]}]
    daily,qc=clean_native_features(row,raw)
    assert daily.water_c.iloc[0]==0 and daily.estimated.iloc[0]
    raw.append({"time":"2020-01-01","value":-999999.,"approval_status":"Approved","qualifier":None})
    daily,qc=clean_native_features(row,raw)
    assert qc["verdict"]=="rejected_sentinel" and daily.water_c.isna().all()
    daily,qc=clean_native_features(row,[{"time":"1960-01-01","value":-999999.,"approval_status":"Approved"},
                                      {"time":"2000-01-01","value":0.,"approval_status":"Approved"}])
    assert qc["n_sentinel"]==0 and daily.water_c.iloc[0]==0


def national_input_module():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("national_input_test",root/"scripts/500_review_completion_national_inputs.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def test_existing_service_retry_deadline_is_retained_across_controller_change(tmp_path):
    m=national_input_module();m.AVAIL=tmp_path/"dates";m.OUT=tmp_path/"values"
    m.AVAIL.mkdir();m.OUT.mkdir()
    (m.AVAIL/"quota_status.json").write_text(json.dumps({"observed_utc":"2026-01-01T00:00:00Z","retry_after_seconds":120}))
    assert m.quota_deadline()==pd.Timestamp("2026-01-01T00:02:01Z").timestamp()


def test_full_legacy_sized_page_is_not_truncated_by_larger_requested_limit(tmp_path,monkeypatch):
    m=national_input_module();m.DATA=tmp_path;m.OLD=tmp_path/"old";(tmp_path/"raw").mkdir()
    monkeypatch.setattr(m.T,"ROOT",tmp_path)
    monkeypatch.setattr(m,"request_slot",lambda:None)
    class Response:
        status_code=200
        def __init__(self,n,next_url=None):self.n=n;self.next_url=next_url;self.url="https://example.invalid/page"+str(n)
        def raise_for_status(self):pass
        def json(self):return {"features":[{"properties":{"time":"2000-01-01","value":10.,"approval_status":"Approved"}}]*self.n,
                               "links":[{"rel":"next","href":self.next_url}] if self.next_url else []}
    responses=iter([Response(10000,"https://example.invalid/items?offset=10000"),Response(50)])
    monkeypatch.setattr(m.requests,"get",lambda *a,**kw:next(responses))
    result,_=m.fetch({"series_id":"a","station_id":"001"})
    assert len(result["features"])==10050 and len(result["requests"])==2


def test_logical_bound_never_supplies_an_unsupported_point_and_keeps_unknown_bounds():
    value=project_lower_bound([np.nan,10.,12.],[11.,np.nan,13.])
    np.testing.assert_allclose(value,[np.nan,10.,13.],equal_nan=True)
    years=np.arange(2000,2020);truth=10+.02*(years-2000)
    b=pd.DataFrame({"year":years,"complete":True,"observed_H30":truth,"observed_H30_lower_bound":truth})
    # Complete observed years have no imputation uncertainty, even with no
    # stored predictive quantiles for those rows.
    result=mi_slopes(b,draws=20)
    np.testing.assert_allclose(result,.2,atol=1e-12)


def test_driver_lags_are_calendar_days_when_input_dates_are_absent():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("driver_calendar_lag_test",root/"scripts/469_review_completion_inputs.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    dates=pd.to_datetime(["2020-12-30","2021-01-01","2021-01-02"])
    air=pd.Series([0.,2.,3.],index=dates);flow=pd.Series([1.,2.,3.],index=dates)
    design=m.design(air,pd.date_range("2020-12-30","2021-01-02"),flow)
    assert np.isnan(design.loc["2021-01-01","air_1"]) and np.isnan(design.loc["2021-01-01","log_flow_1"])
    assert design.loc["2021-01-02","air_1"]==2


def test_noaa_tavg_tenths_quality_flags_leap_day_and_source_convention():
    from stream_recoverability.experiments.tr_revision.observed_air import parse_tavg
    values=[]
    for day in range(1,32):
        value=-9999 if day==2 else 100
        quality="X" if day==3 else " "
        values.append(f"{value:5d} {quality}S")
    frame=parse_tavg("USW00000001202002TAVG"+''.join(values))
    assert len(frame)==29 and frame.date.iloc[-1]==pd.Timestamp("2020-02-29")
    assert frame.air_c.iloc[0]==10 and frame.air_c.iloc[1:3].isna().all()
    assert frame.source_flag.eq("S").all()


def national_reporting_fixture(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import wrr_review_national_reporting as reporting
    folder = tmp_path / "national_meaning"
    dest = folder / "application/meaning"
    dest.mkdir(parents=True)
    status = {"execution_complete_on_retrieved_panel": True, "complete": False,
              "n_metadata_candidates": 3, "n_numeric_processed_sites": 2,
              "unresolved_or_no_annual_record_candidates": 1,
              "eligibility_lower_counts": {"complete15": 1, "retained_raw": 2},
              "eligibility_upper_counts_allowing_unresolved": {"complete15": 2, "retained_raw": 3}}
    (folder / "status.json").write_text(json.dumps(status))
    (folder / "acquisition.json").write_text(json.dumps({"all_planned_attempted": True}))
    (folder / "application/status.json").write_text(json.dumps({"application_complete": True,
        "partial": False, "model_weights_unchanged": True, "n_processed_stations": 2}))
    pd.DataFrame({"station_id": ["a", "a", "b"]}).to_parquet(folder / "application/annual_panel.parquet")
    for name in ["network_and_regional_summary", "field_significance",
                 "hot_year_frequency_network_region", "same_roster_same_span_trends"]:
        pd.DataFrame({"example": [1]}).to_csv(dest / (name + ".csv"), index=False)
    pd.DataFrame({"rule": ["complete15", "retained_raw"], "n_eligible_stations": [1, 2]}).to_csv(dest / "spatial_coverage.csv", index=False)
    return reporting, folder, status


def test_national_reporting_preserves_unknown_sites_after_all_requests(tmp_path):
    reporting, _, _ = national_reporting_fixture(tmp_path)
    result = reporting.national_evidence(tmp_path)
    assert not result["status"]["complete"]
    assert result["status"]["unresolved_or_no_annual_record_candidates"] == 1


@pytest.mark.parametrize("error", ["partial_application", "incomplete_acquisition", "false_resolved_flag", "wrong_bounds"])
def test_national_reporting_rejects_incomplete_or_inconsistent_evidence(tmp_path, error):
    reporting, folder, status = national_reporting_fixture(tmp_path)
    if error == "partial_application":
        path = folder / "application/status.json"
        data = json.loads(path.read_text()); data["partial"] = True
    elif error == "incomplete_acquisition":
        path = folder / "acquisition.json"
        data = {"all_planned_attempted": False}
    else:
        path = folder / "status.json"; data = status
        if error == "false_resolved_flag":
            data["complete"] = True
        else:
            data["eligibility_upper_counts_allowing_unresolved"]["complete15"] = 1
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError):
        reporting.national_evidence(tmp_path)


def test_national_reporting_ignores_smoke_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from wrr_review_national_reporting import national_evidence
    smoke = tmp_path / "national_meaning/smoke_3/meaning"
    smoke.mkdir(parents=True)
    (smoke / "summary.json").write_text(json.dumps({"execution_complete_on_retrieved_panel": True}))
    assert national_evidence(tmp_path) is None
