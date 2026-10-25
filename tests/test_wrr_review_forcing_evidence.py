"""Full-source labels must be supported by the actual source roster and arms."""
import importlib.util
import json
from pathlib import Path
import sys
import pandas as pd
import pytest
from datetime import datetime
from types import SimpleNamespace


def helper():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("forcing_evidence_test",root/"scripts/wrr_review_forcing_reporting.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))


def study(tmp_path,monkeypatch):
    m=helper();monkeypatch.setattr(m.T,"ROOT",tmp_path)
    source=tmp_path/"results/wrr_target_recovery_20261022/e2_cases";source.mkdir(parents=True)
    pd.DataFrame({"provider":["arso","hubeau"],"station_key":["arso|1","hubeau|03248401"],"year":[2001,2002]}).to_parquet(source/"cases.parquet",index=False)
    out=tmp_path/"results/review";full=out/"europe_full_source_exact";full.mkdir(parents=True)
    roster=pd.DataFrame({"station_id":["1","03248401"],"station_key":["arso|1","hubeau|03248401"],"latitude":[46.,48.],"longitude":[15.,-.8]})
    roster.to_csv(full/"roster.csv",index=False)
    write(full/"analysis_summary.json",{"complete":True,"partial":False})
    write(full/"acquisition.json",{"requested":2,"retrieved":2,"service_stop":False,"records":[{"station_key":key,"status":"available"} for key in roster.station_key]})
    write(full/"original_core_control_audit.json",{"exact_source_verified":True,"case_rows":2,"availability_disagreements":0,"maximum_point_difference":0.})
    pd.DataFrame({"arm":["POWER","ERA5_Land"]*2}).to_parquet(full/"cases.parquet",index=False)
    pd.DataFrame({"stratum":["all","danger","air_layer_danger"],"n_paired":[2,2,1],"POWER_mae":[.4,.5,.6],"alternative_mae":[.3,.4,.5]}).to_csv(full/"paired_summary.csv",index=False)
    return m,out,full


def test_partial_expansion_keeps_the_pilot_label(tmp_path,monkeypatch):
    m,out,full=study(tmp_path,monkeypatch)
    write(full/"analysis_summary.json",{"complete":True,"partial":True})
    pilot=out/"europe_forcing";pilot.mkdir()
    write(pilot/"acquisition.json",{"selected":1,"retrieved":1,"errors":[]})
    pd.DataFrame({"stratum":["all"],"n":[1],"POWER_mae":[.7],"ERA5_Land_mae":[.8]}).to_csv(pilot/"paired_summary.csv",index=False)
    result=m.europe_evidence(out)
    assert result["full_source"] is False and result["selected"]==1
    assert result["pairs"].loc["all","ERA5_Land_mae"]==.8


def test_green_flag_cannot_cover_a_missing_source_station(tmp_path,monkeypatch):
    m,out,full=study(tmp_path,monkeypatch)
    pd.read_csv(full/"roster.csv").iloc[:1].to_csv(full/"roster.csv",index=False)
    with pytest.raises(RuntimeError,match="source population"):m.europe_evidence(out)


@pytest.mark.parametrize("rows,accepted",[(4,True),(2,False)])
def test_full_source_requires_both_case_arms(tmp_path,monkeypatch,rows,accepted):
    m,out,full=study(tmp_path,monkeypatch)
    pd.DataFrame({"arm":["POWER","ERA5_Land"]*(rows//2)}).to_parquet(full/"cases.parquet",index=False)
    if accepted:
        result=m.europe_evidence(out)
        assert result["full_source"] and result["pairs"].loc["all","n"]==2
    else:
        with pytest.raises(RuntimeError,match="denominators"):m.europe_evidence(out)


def quota_helper():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("forcing_quota_test",root/"scripts/510_review_completion_europe_full.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("kind,observed,expected",[
    ("Hourly","2026-10-24T06:19:24+00:00",2496),
    ("Daily","2026-10-24T06:19:24+00:00",63696),
    ("Hourly","2026-10-24T06:00:15+00:00",45),
])
def test_provider_period_reset_keeps_the_entire_utc_reset_minute(kind,observed,expected):
    response=SimpleNamespace(headers={},text=kind+" API request limit exceeded")
    delay,source=quota_helper().quota_delay(response,datetime.fromisoformat(observed))
    assert delay==expected and "documented UTC" in source


@pytest.mark.parametrize("header,expected",[("120",120),("Sat, 24 Oct 2026 06:24:24 GMT",300)])
def test_explicit_retry_after_overrides_inferred_reset(header,expected):
    response=SimpleNamespace(headers={"Retry-After":header},text="Hourly API request limit exceeded")
    delay,source=quota_helper().quota_delay(response,datetime.fromisoformat("2026-10-24T06:19:24+00:00"))
    assert delay==expected and source.startswith("Retry-After")
