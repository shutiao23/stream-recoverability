#!/usr/bin/env python3
"""Verify code/model archive execution in a fresh root with networking disabled.

Uses previously opened source features and a synthetic daily-water fixture.
It does not verify public registration, open NZ observations, or alter weights.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[variable]="1"
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import joblib
import numpy as np
import pandas as pd
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024"

CHILD=r'''
import sys,json,socket
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
def no_network(*args,**kwargs):raise RuntimeError('Networking disabled in archive execution check')
socket.create_connection=no_network;socket.socket.connect=no_network
import pandas as pd
import numpy as np
import joblib
import stream_recoverability
import wrr_tr_common as T
assert T.ROOT.resolve()==root.resolve()
assert Path(stream_recoverability.__file__).resolve().is_relative_to(root/'src')
study=root/'results/wrr_review_completion_20261024/independent_study'
m=T.load_script('archive_frozen_predictor',root/'scripts/495_review_completion_independent_analysis.py')
fixture=Path(sys.argv[1]);c=pd.read_parquet(fixture/'source_cases.parquet')
bundle=joblib.load(root/'results/wrr_review_completion_20261024/deployment/global_source_candidate.joblib')
cal=json.loads((root/'results/wrr_review_completion_20261024/deployment/classical_calibration.json').read_text())
pred=m.classical_predictions(m.predict(c,bundle),cal)
columns=json.loads((fixture/'output_columns.json').read_text())
reference=pd.read_parquet(fixture/'expected_predictions.parquet')
np.testing.assert_allclose(pred[columns],reference[columns],rtol=1e-12,atol=1e-12,equal_nan=True)
core=T.load_script('archive_case_generator',root/'scripts/431_tr_cases.py')
settings=json.loads((fixture/'synthetic_settings.json').read_text())
generator=json.loads((study/'source_missingness_generator.json').read_text())
job=json.loads((fixture/'synthetic_job.json').read_text())
result=core.station_cases(job,settings,generator,[],False)
generated=pd.read_parquet(result['cache'])
assert len(generated)>0 and generated.h30__policy.notna().any()
assert generated.state_h30_q50.notna().any()
columns=json.loads((fixture/'synthetic_numeric_columns.json').read_text())
expected=pd.read_parquet(fixture/'expected_synthetic.parquet')
np.testing.assert_allclose(generated[columns].to_numpy(float),expected[columns].to_numpy(float),rtol=1e-9,atol=1e-9,equal_nan=True)
for name in ['policy_choice','mask_runs','realization_id']:assert generated[name].equals(expected[name])
print(json.dumps({'passed':True,'source_feature_cases':len(c),'synthetic_generated_cases':len(generated),
 'synthetic_numeric_columns_compared':len(columns),
 'network_disabled':True,'working_tree_code_imported':False,'new_NZ_water_values_requested':False}))
'''


def main():
    archive=OUT/"independent_study/registration_code_and_protocol.tar.gz"
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    m=T.load_script("workspace_archive_predictor",T.ROOT/"scripts/495_review_completion_independent_analysis.py")
    cases=pd.read_parquet(OUT/"cases/leave_one_year_out/seed_00.parquet")
    cases=cases.groupby(["region","policy_choice","design_family"],group_keys=False).head(2).reset_index(drop=True)
    repair=T.load_script("archive_source_fixture_repairs",T.ROOT/"scripts/467_review_completion_analysis.py")
    cases=repair.apply_bridge_repairs(cases,0,"leave_one_year_out")
    bundle=joblib.load(OUT/"deployment/global_source_candidate.joblib")
    calibration=json.loads((OUT/"deployment/classical_calibration.json").read_text())
    expected=m.classical_predictions(m.predict(cases,bundle),calibration)
    columns=["D2","P2","risk_score"]+[name for name in expected if name.startswith(("D2_q","stochastic_cal_q","state_cal_q"))]
    with tempfile.TemporaryDirectory(prefix="review_archive_",dir=T.ROOT/"scratch") as temporary:
        base=Path(temporary);root=base/"archive";root.mkdir();fixture=base/"fixture";fixture.mkdir()
        cases.to_parquet(fixture/"source_cases.parquet",index=False)
        expected[columns].to_parquet(fixture/"expected_predictions.parquet",index=False)
        (fixture/"output_columns.json").write_text(json.dumps(columns))
        dates=pd.date_range("2001-01-01","2005-12-31");rng=np.random.default_rng(516)
        phase=np.cos(2*np.pi*(dates.dayofyear.to_numpy()-200)/365.25)
        target=12+6*phase+rng.normal(0,.2,len(dates))
        water=pd.DataFrame({"target":target,"donor":target+rng.normal(0,.3,len(dates))},index=dates)
        water.index.name="date";water.to_csv(fixture/"water.csv")
        pd.DataFrame({"date":dates,"network_id":"synthetic_network","station_id":"target","air_temperature_c":10+9*phase+rng.normal(0,.5,len(dates))}).to_parquet(fixture/"air.parquet",index=False)
        settings=json.loads((OUT/"independent_study/source_case_settings.json").read_text())
        settings.update(version="archive_execution_synthetic_only",replication_seeds=[0],trajectory_draws=8,
            multiple_imputations=4,gap_lengths_days=[30],realizations_per_cell=1,classical_baselines=True,trajectory_targets=["h30"])
        job={"network_id":"synthetic_network","station_id":"target","station_key":"synthetic|target","provider":"synthetic",
            "region":"synthetic","independence_group":"synthetic","latitude":46.,"roster":"source","station_index":0,
            "input_path":str(fixture/"water.csv"),"air_input_path":str(fixture/"air.parquet"),"statistic_class":"daily_mean","regulation_status":"synthetic"}
        (fixture/"synthetic_settings.json").write_text(json.dumps(settings));(fixture/"synthetic_job.json").write_text(json.dumps(job))
        core=T.load_script("workspace_archive_case_generator",T.ROOT/"scripts/431_tr_cases.py")
        core.CACHE=fixture/"workspace_cache"
        generator=json.loads((OUT/"independent_study/source_missingness_generator.json").read_text())
        created=core.station_cases(job,settings,generator,[],False)
        expected_synthetic=pd.read_parquet(created["cache"])
        expected_synthetic.to_parquet(fixture/"expected_synthetic.parquet",index=False)
        numeric=list(expected_synthetic.select_dtypes(include=[np.number,"bool"]))
        (fixture/"synthetic_numeric_columns.json").write_text(json.dumps(numeric))
        with tarfile.open(archive) as handle:
            for member in handle.getmembers():
                path=Path(member.name)
                if path.is_absolute() or '..' in path.parts or not member.isfile():raise RuntimeError("Unexpected non-file/archive path")
            handle.extractall(root)
        code=base/"check.py";code.write_text(CHILD)
        runtime_tmp=root/"runtime_tmp";runtime_tmp.mkdir()
        env=os.environ|{"PYTHONPATH":str(root/"src"),"TMPDIR":str(runtime_tmp),"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1"};env.pop("TR_CONFIG",None)
        result=subprocess.run([sys.executable,str(code),str(fixture)],cwd=root,env=env,text=True,capture_output=True)
        record={"archive_sha256":sha,"returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr,
            "scope":"isolated code/model inference and synthetic case generation; no registration or target-outcome evidence"}
        if result.returncode==0:
            record.update(json.loads(result.stdout.strip().splitlines()[-1]))
        T.write_json(OUT/"evidence/archive_execution_smoke.json",record)
        if result.returncode:
            print(result.stderr[-6000:],flush=True);raise RuntimeError("Extracted archive execution failed")
        print(json.dumps({k:record[k] for k in ["passed","source_feature_cases","synthetic_generated_cases","network_disabled"]}),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
