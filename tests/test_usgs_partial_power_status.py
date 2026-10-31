import importlib.util,json
from pathlib import Path
import pandas as pd

def test_status_written_after_fake_response(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[1]/'scripts/891_usgs_partial_power_corrected.py'
    spec=importlib.util.spec_from_file_location('usgs_power_corrected',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    stage=tmp_path/'stage';stage.mkdir();private=tmp_path/'private';private.mkdir()
    (stage/'scoring_plan.json').write_text(json.dumps({}))
    pd.DataFrame([{'station_id':'00000001','latitude':35.,'longitude':-105.}]).to_csv(private/'continuous_target_roster.csv',index=False)
    dates=pd.date_range('2011-01-01','2024-12-31');doc={'properties':{'parameter':{'T2M':{d.strftime('%Y%m%d'):1.5 for d in dates}}}}
    class Response:
        status_code=200
        content=json.dumps(doc).encode()
        def raise_for_status(self):pass
        def json(self):return doc
    monkeypatch.setattr(m,'STAGE',stage);monkeypatch.setattr(m,'PRIVATE',private);monkeypatch.setattr(m,'POWER',stage/'power');monkeypatch.setattr(m.requests,'get',lambda *a,**kw:Response());monkeypatch.setattr(m.time,'sleep',lambda _:None)
    m.main();status=json.loads((stage/'forcing_status.json').read_text());assert status['status']=='completed' and status['returned_sites']==1 and status['finite_days']==len(dates)
