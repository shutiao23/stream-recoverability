"""Guard the new-cohort boundary with synthetic metadata and OSF responses."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile

import numpy as np
import pandas as pd

import pytest

from stream_recoverability.experiments.tr_revision.independent import (
    accepted_public_registration, complete_hot_years_in_span, metadata_url,
    parse_metadata, verify_registration_attachments,
    evaluate_endpoints,require_acquisition_plan,sha256,
)


def test_metadata_transport_rejects_observations_before_any_request():
    with pytest.raises(ValueError):
        metadata_url("https://example.invalid/data", "GetData", Site="X")
    with pytest.raises(ValueError):
        metadata_url("https://example.invalid/data", "SiteList", service="SOS")
    url=metadata_url("https://example.invalid/data", "MeasurementList", Site="River at Gauge")
    assert "River%20at%20Gauge" in url and "+" not in url
    with pytest.raises(RuntimeError,match="Observation-bearing"):
        parse_metadata(b"<Hilltop><Data><E><T>2000</T><I1>12</I1></E></Data></Hilltop>")
    assert parse_metadata(b"<Hilltop><From>2000-01-01</From></Hilltop>").findtext("From")=="2000-01-01"


def test_metadata_year_count_uses_july_june_boundaries_including_leap_year():
    assert complete_hot_years_in_span("2020-07-01T00:00:00+12:00","2024-06-30T23:59:59+12:00")==4
    assert complete_hot_years_in_span("2024-01-01","2026-10-24")==2
    assert complete_hot_years_in_span("2020-07-02","2024-06-30")==3


def public_record():
    return {"data":{"id":"abc12","type":"registrations","attributes":{
        "public":True,"date_registered":"2020-01-01T00:00:00Z"},
        "relationships":{"files":{"links":{"related":{"href":"https://api.osf.io/v2/registrations/abc12/files/"}}}}}}


def test_registration_requires_correct_resource_and_real_accepted_timestamp():
    record=public_record()
    assert accepted_public_registration(record,"abc12").startswith("2020")
    record["data"]["type"]="nodes"
    with pytest.raises(RuntimeError,match="requested registration"):
        accepted_public_registration(record,"abc12")
    record["data"]["type"]="registrations";record["data"]["attributes"]["archiving"]=True
    with pytest.raises(RuntimeError,match="pending"):
        accepted_public_registration(record,"abc12")
    record["data"]["attributes"].pop("archiving");record["data"]["attributes"]["date_registered"]=None
    with pytest.raises(RuntimeError,match="timestamp"):
        accepted_public_registration(record,"abc12")


def attachment_session(payload):
    class Response:
        def __init__(self,data=None,body=None):self.data=data;self.body=body
        def raise_for_status(self):pass
        def json(self):return self.data
        def iter_content(self,chunk_size):yield self.body
    pages={
        "https://api.osf.io/v2/registrations/abc12/?version=2.20":public_record(),
        "https://api.osf.io/v2/registrations/abc12/files/":{"data":[{
            "id":"abc12:osfstorage","type":"files","attributes":{"kind":"folder","provider":"osfstorage"},
            "relationships":{"files":{"links":{"related":{"href":"https://api.osf.io/v2/registrations/abc12/files/osfstorage/"}}}}}],"links":{"next":None}},
        "https://api.osf.io/v2/registrations/abc12/files/osfstorage/":{"data":[{
            "id":"file123","type":"files","attributes":{"kind":"file","provider":"osfstorage","name":"protocol.json"},
            "links":{"download":"https://osf.io/download/file123/"}}],"links":{"next":None}},
    }
    class Session:
        calls=[]
        def get(self,url,**kwargs):
            self.calls.append(url)
            return Response(body=payload) if "download" in url else Response(data=pages[url])
    return Session()


def test_archive_attachment_names_alone_do_not_unlock_acquisition(tmp_path):
    path=tmp_path/"protocol.json";path.write_bytes(b"fixed protocol")
    with pytest.raises(RuntimeError,match="No exact archived"):
        verify_registration_attachments("abc12",[path],session=attachment_session(b"other protocol"))
    result=verify_registration_attachments("https://osf.io/abc12/",[path],session=attachment_session(path.read_bytes()))
    assert result["attachments"][0]["sha256"]==hashlib.sha256(path.read_bytes()).hexdigest()
    assert not result["water_temperature_values_requested"]
    assert path.read_bytes()==b"fixed protocol"


def endpoint_cases():
    return pd.DataFrame({"independence_group":np.repeat(["A","B","C"],40),
                         "design_family":"crossed","D2":10.,"risk_score":.02,
                         "eval_truth_h30":10.,"h30__policy":9.,"peak_overlap":.6,
                         "D2_q05":9.5,"D2_q95":10.5})


def test_independent_primary_endpoints_never_count_empty_or_unlabeled_as_success():
    c=endpoint_cases()
    result,groups=evaluate_endpoints(c,draws=100)
    assert result["joint_primary_passed"] and len(groups)==3
    c.loc[0,"eval_truth_h30"]=np.nan
    result,_=evaluate_endpoints(c,draws=100)
    assert result["n_admitted_without_labels"]==1 and not result["joint_primary_passed"]
    c["risk_score"]=.8
    result,_=evaluate_endpoints(c,draws=100)
    assert result["E1"]["risk"] is None and not result["E2"]["passed"]
    c=endpoint_cases();c.loc[c.independence_group.eq("A"),"D2"]=12.
    result,_=evaluate_endpoints(c,draws=100)
    assert not result["E2"]["passed"] and result["E2"]["fraction_above_10_percent"]==pytest.approx(1/3)
    result,_=evaluate_endpoints(c.iloc[:0],draws=100)
    assert not result["joint_primary_passed"] and result["E1"]["risk"] is None


def test_frozen_prediction_is_independent_of_evaluation_labels():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("independent_prediction_test",root/"scripts/495_review_completion_independent_analysis.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    c=endpoint_cases().assign(policy_choice="air_ridge",air_available=True,
                              law_hidden_shares=".5;.6",clim_peak=10.,train_h30_mean=10.)
    class Constant:
        def predict(self,x):return np.zeros(len(x))
    class Classifier:
        def predict_proba(self,x):return np.tile([.98,.02],(len(x),1))
    bundle={"features":["peak_overlap"],"quantile_models":[Constant() for _ in range(7)],
            "offsets":{"3|air_ridge":np.linspace(-.5,.5,7)},"classifier":Classifier()}
    a=module.predict(c,bundle)
    c["eval_truth_h30"]+=1000
    b=module.predict(c,bundle)
    pd.testing.assert_frame_equal(a[["D2","risk_score","D2_q05","D2_q95"]],b[["D2","risk_score","D2_q05","D2_q95"]])


def registered_study(tmp_path):
    from stream_recoverability.experiments.tr_revision.independent import REGISTERED_EXECUTION_REQUIRED
    root=tmp_path/"runtime";study=root/"study";study.mkdir(parents=True)
    files=[]
    for name in sorted(REGISTERED_EXECUTION_REQUIRED|{"src/extra_dependency.py"}):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("{}" if name.endswith(".json") else "# frozen execution fixture\n")
        files.append(path)
    fields={}
    for name,field in [("source_case_settings.json","source_case_settings_sha256"),("source_missingness_generator.json","source_generator_sha256")]:
        path=study/name;path.write_text('{}');files.append(path);fields[field]=sha256(path)
    for name,field in [("global_source_candidate.joblib","source_model_sha256"),("classical_calibration.json","classical_calibration_sha256")]:
        path=root/"results/wrr_review_completion_20261024/deployment"/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('frozen fixture');files.append(path);fields[field]=sha256(path)
    roster=study/"roster.csv";roster.write_text("station_key,independence_group\nnz|1,A\n")
    plan={"status":"metadata_roster_frozen","provider":"test", "metadata_roster_file":roster.name,
          "metadata_roster_sha256":sha256(roster),"qc_specification":{"codes":[600]},
          "native_time_zone":"UTC+12:00","independence_groups_verified":True,"prior_temperature_access_excluded":True,**fields}
    path=study/"acquisition_plan.json";path.write_text(json.dumps(plan));files.extend([roster,path])
    manifest=study/"file_sha256.json";manifest.write_text(json.dumps({str(p.relative_to(root)):sha256(p) for p in files}));files.append(manifest)
    archive=study/"registration_code_and_protocol.tar.gz"
    with tarfile.open(archive,"w:gz") as tar:
        for path in files:tar.add(path,arcname=str(path.relative_to(root)))
    status={"status":"public_registration_and_attachments_verified","attachments":[{"name":archive.name,"sha256":sha256(archive)}]}
    return root,study,status


def test_acquisition_plan_must_be_in_exact_public_archive(tmp_path):
    with pytest.raises(RuntimeError,match="public registration"):
        require_acquisition_plan(tmp_path,{"status":"not_publicly_registered"})
    root,study,status=registered_study(tmp_path)
    assert require_acquisition_plan(study,status,runtime_root=root)["provider"]=="test"
    path=study/"acquisition_plan.json";plan=json.loads(path.read_text())
    plan["qc_specification"]["codes"].append(500);path.write_text(json.dumps(plan))
    with pytest.raises(RuntimeError,match="differs from the registration snapshot"):
        require_acquisition_plan(study,status,runtime_root=root)


def test_runtime_source_edit_is_rejected_even_with_the_exact_archive(tmp_path):
    root,study,status=registered_study(tmp_path)
    (root/"src/extra_dependency.py").write_text("# edited after registration\n")
    with pytest.raises(RuntimeError,match="Execution file differs"):
        require_acquisition_plan(study,status,runtime_root=root)


def test_runtime_configuration_override_and_generation_input_edits_are_rejected(tmp_path):
    root,study,status=registered_study(tmp_path)
    alternative=root/"different_config.json";alternative.write_text('{"changed":true}')
    with pytest.raises(RuntimeError,match="Active source configuration"):
        require_acquisition_plan(study,status,runtime_root=root,runtime_config=alternative)
    (study/"source_case_settings.json").write_text('{"changed":true}')
    with pytest.raises(RuntimeError,match="Generation input differs"):
        require_acquisition_plan(study,status,runtime_root=root)


def native_xml(points,kind="StdSeries"):
    records="".join(f"<E><T>{stamp}</T><I1>{value}</I1></E>" for stamp,value in points)
    return (f'<Hilltop><Measurement SiteName="Synthetic river"><DataSource><TSType>{kind}</TSType>'
            '<ItemInfo><Units>°C</Units></ItemInfo></DataSource><Data NumItems="1">'
            +records+'</Data></Measurement></Hilltop>').encode()


def test_native_daily_reference_uses_fixed_nzst_even_at_daylight_saving_transition():
    from stream_recoverability.experiments.tr_revision.native_temperature import native_series,strict_daily_mean
    # The actual clock change in Auckland must not make this a 23-hour day.
    dates=pd.date_range("2024-09-28T12:00:00Z",periods=24,freq="h")
    raw=native_series(native_xml([(d.isoformat(),i) for i,d in enumerate(dates)]),site="Synthetic river",series_type="StdSeries")
    quality=native_series(native_xml([("2024-09-01T00:00:00",600)],"StdQualSeries"),site="Synthetic river",series_type="StdQualSeries")
    daily=strict_daily_mean(raw,quality,start="2024-09-29",end_exclusive="2024-09-30")
    assert daily.complete_native_day.all() and daily.water_c.iloc[0]==11.5
    assert daily.date.iloc[0]==pd.Timestamp("2024-09-29")


def test_unknown_quality_missing_samples_and_conflicting_duplicates_cannot_be_complete_days():
    from stream_recoverability.experiments.tr_revision.native_temperature import native_series,strict_daily_mean
    dates=pd.date_range("2024-02-28",periods=96*3,freq="15min")
    raw=native_series(native_xml([(d.isoformat(),10.) for d in dates]),site="Synthetic river",series_type="StdSeries")
    quality=native_series(native_xml([("2024-02-01",600),("2024-02-28T12:00:00",200),("2024-02-29",600)],"StdQualSeries"),site="Synthetic river",series_type="StdQualSeries")
    raw=raw.drop(raw.index[-2])
    daily=strict_daily_mean(raw,quality,start="2024-02-28",end_exclusive="2024-03-02")
    assert daily.complete_native_day.tolist()==[False,True,False]
    assert daily.water_c.isna().tolist()==[True,False,True]
    conflicting=native_series(native_xml([("2024-02-29T00:00:00",10),("2024-02-29T00:00:00",12)]),site="Synthetic river",series_type="StdSeries")
    assert conflicting.isna().all()
    with pytest.raises(ValueError,match="series type"):
        native_series(native_xml([("2024-02-29",10)],"CheckSeries"),site="Synthetic river",series_type="StdSeries")


def test_native_air_daily_has_exactly_24_hours_in_fixed_water_clock(monkeypatch):
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    monkeypatch.setenv("TR_CONFIG",str(root/"configs/wrr_target_recovery_20261022.json"))
    spec=importlib.util.spec_from_file_location("independent_native_air_test",root/"scripts/497_review_completion_independent_cases.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    hours=pd.date_range("2024-09-28T12:00",periods=48,freq="h")
    document={"hourly_units":{"temperature_2m":"°C"},"hourly":{"time":[d.isoformat() for d in hours],"temperature_2m":[10.]*48}}
    result=module.native_air_daily(document)
    assert result.index.tolist()==[pd.Timestamp("2024-09-29"),pd.Timestamp("2024-09-30")]
    assert result.eq(10).all()
    document["hourly"]["temperature_2m"][1]=None
    assert np.isnan(module.native_air_daily(document).iloc[0])
    row=pd.Series({"latitude":-41.,"longitude":175.,"to":"2026-10-24"})
    assert module.weather_parameters(row,2026,"2026-07-01")["end_date"]=="2026-06-30"


def test_acquisition_entry_stops_before_http_without_public_registration(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("independent_acquisition_gate_test",root/"scripts/496_review_completion_independent_acquisition.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    (tmp_path/"public_registration_status.json").write_text(json.dumps({"status":"not_publicly_registered"}))
    monkeypatch.setattr(sys,"argv",["496_review_completion_independent_acquisition.py","--study",str(tmp_path),"--acquire"])
    monkeypatch.setattr(module.requests,"get",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("No observation request is allowed")))
    with pytest.raises(RuntimeError,match="public registration"):
        module.main()
    assert not (tmp_path/"acquired").exists()


def test_registered_runtime_edit_stops_acquisition_before_http(tmp_path,monkeypatch):
    root,study,status=registered_study(tmp_path)
    (study/"public_registration_status.json").write_text(json.dumps(status))
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project/"scripts"))
    spec=importlib.util.spec_from_file_location("registered_runtime_http_gate_test",project/"scripts/496_review_completion_independent_acquisition.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module.T,"ROOT",root)
    monkeypatch.setattr(module.T,"CONFIG",root/"configs/wrr_target_recovery_20261022.json")
    (root/"scripts/497_review_completion_independent_cases.py").write_text("# changed after registration\n")
    monkeypatch.setattr(sys,"argv",["496_review_completion_independent_acquisition.py","--study",str(study),"--acquire"])
    monkeypatch.setattr(module.requests,"get",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("No observation request is allowed")))
    with pytest.raises(RuntimeError,match="Execution file differs"):
        module.main()
    assert not (study/"acquired").exists()


def test_independent_calendar_pool_keeps_own_network_and_handles_no_gaps(tmp_path):
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("independent_calendar_test",root/"scripts/431_tr_cases.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    dates=pd.date_range("2019-01-01","2023-12-31")
    path=tmp_path/"daily.csv"
    values=np.ones(len(dates));values[(dates>="2021-02-01")&(dates<"2021-02-06")]=np.nan
    pd.DataFrame({"date":dates,"A":values}).to_csv(path,index=False)
    job={"provider":"nz_gw","roster":"independent","input_path":str(path),"network_id":"one","station_key":"nz_gw|A","latitude":-41.}
    pools=module.calendar_pool("independent",[job])
    chosen=module.pool_for(job,pools)
    assert len(chosen)==1 and chosen[0]["key"].startswith("nz_gw|A:")
    assert chosen[0]["runs"][0][1]==5
    pd.DataFrame({"date":dates,"A":1.}).to_csv(path,index=False)
    assert module.calendar_pool("independent",[job])=={}
