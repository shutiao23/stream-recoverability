import importlib.util
import json
import hashlib
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

def load():
    script=Path(__file__).resolve().parents[1]/'scripts/696_stress_source_compare.py'
    if str(script.parent) not in sys.path:sys.path.insert(0,str(script.parent))
    spec=importlib.util.spec_from_file_location('stress_six_way',script)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def test_common_cohort_excludes_unavailable_and_checks_interval_support():
    rows=[]
    for scenario in ['synchronized_donors','heat_associated_matched']:
        for i in range(205):
            for est in ['D2','stochastic_calibrated']:
                for dep in ['point','independent']:
                    for version in ['original','strict_original','candidate']:
                        for side in ['baseline','stress']:
                            special=scenario=='synchronized_donors' and est=='D2' and dep=='independent'
                            # One cell is unavailable; all other paired cells
                            # must remain available to test six-way exclusion.
                            available=not (special and i==0 and version=='candidate' and side=='stress')
                            interval=np.nan if special and i==1 and version=='strict_original' and side=='baseline' else .95
                            error=float(side=='stress')
                            rows.append({'scenario':scenario,'station_key':f's{i//5}','replicate':i%5,
                                         'independence_group':f'g{i%17:02d}','region':f'r{i%6}',
                                         'estimator':est,'dependence':dep,'version':version,'side':side,
                                         'available':available,'truth_slope':1.,'error':error,'squared_error':error**2,
                                         'missing_coverage95':interval,'width95':1.,'interval_score95':2.})
    summary,_=load().summarize(pd.DataFrame(rows))
    selected=summary[(summary.scenario=='synchronized_donors')&(summary.estimator=='D2')&
                     (summary.dependence=='independent')]
    assert selected.n_common_six_way.eq(204).all()
    assert selected.n_common_intervals.eq(203).all()
    assert selected.baseline_rmse.eq(0.).all() and selected.stress_rmse.eq(1.).all()
    assert int(selected.loc[selected.version.eq('candidate'),'stress_available'].iloc[0])==204

def test_candidate_baseline_receipt_detects_changed_calibration(tmp_path):
    load()  # Make the scripts directory importable for the dynamic audit module.
    path=Path(__file__).resolve().parents[1]/'scripts/699_stress_source_baseline_audit.py'
    spec=importlib.util.spec_from_file_location('source_baseline_audit',path)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    original=tmp_path/'old';target=tmp_path/'new';original.mkdir();target.mkdir()
    model=tmp_path/'model';calibration=tmp_path/'calibration'
    for item in [original/'annual_predictions.parquet',target/'annual_predictions.parquet',target/'trends.csv',model,calibration]:
        item.write_text(item.name)
    receipt={'same_masks':True,'hidden_target_values_present':0,
             'source_predictions_sha256':hashlib.sha256((original/'annual_predictions.parquet').read_bytes()).hexdigest(),
             'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
             'calibration_sha256':hashlib.sha256(calibration.read_bytes()).hexdigest(),
             'annual_predictions_sha256':hashlib.sha256((target/'annual_predictions.parquet').read_bytes()).hexdigest(),
             'trends_sha256':hashlib.sha256((target/'trends.csv').read_bytes()).hexdigest()}
    (target/'open_source_receipt.json').write_text(json.dumps(receipt))
    audit.verify_candidate_receipt(original,target,model,calibration)
    calibration.write_text('changed')
    with pytest.raises(ValueError,match='receipt'):
        audit.verify_candidate_receipt(original,target,model,calibration)
    calibration.write_text('calibration')
    receipt.pop('calibration_sha256')
    (target/'open_source_receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match='receipt'):
        audit.verify_candidate_receipt(original,target,model,calibration)
