import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

def module():
    path=Path(__file__).resolve().parents[1]/'scripts/720_groupmax_annual_calibration.py'
    if str(path.parent) not in sys.path:sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('groupmax_annual_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_finite_group_rank_requires_nine_groups_at_ninety_percent():
    m=module();group=np.array([f'g{i}' for i in range(9)])
    y=np.arange(1.,10.);lo=np.zeros(9);hi=np.zeros(9)
    fewer,_=m.group_max_radius(y[:8],lo[:8],hi[:8],group[:8])
    enough,_=m.group_max_radius(y,lo,hi,group)
    assert fewer['status']=='insufficient_source_groups' and fewer['rank']==9 and fewer['radius'] is None
    assert enough['status']=='supported_exploratory' and enough['rank']==9 and enough['radius']==9.

def test_group_maximum_not_average_and_zero_is_unsupported():
    m=module();group=np.repeat([f'g{i}' for i in range(9)],2)
    truth=np.zeros(18);truth[-1]=3.
    result,by=m.group_max_radius(truth,np.zeros(18),np.zeros(18),group)
    assert result['radius']==3. and by['max'].max()==3.
    zero,_=m.group_max_radius(np.zeros(18),np.zeros(18),np.zeros(18),group)
    assert zero['status']=='zero_source_correction'

def test_interval_expansion_respects_bound_and_score_penalizes_width():
    m=module();lo,hi=m.intervals([2.],[3.],[1.8],1.)
    assert lo[0]==pytest.approx(1.8) and hi[0]==pytest.approx(4.)
    base=m.scores(np.array([2.5]),np.array([2.]),np.array([3.]))
    wide=m.scores(np.array([2.5]),lo,hi)
    assert base['coverage90'][0]==wide['coverage90'][0]==1.
    assert wide['interval_score90'][0]>base['interval_score90'][0]

def test_summary_scopes_do_not_mutate_later_strata_support():
    path=Path(__file__).resolve().parents[1]/'scripts/722_groupmax_summary_correction.py'
    spec=importlib.util.spec_from_file_location('groupmax_summary_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    data=pd.DataFrame({'family':['crossed']*4,'estimator':['D2']*4,
        'stratum':['unobserved_peak_excess','unobserved_peak_excess','bound_matches_reference','bound_matches_reference'],
        'both_groupmax_supported':[True]*4,'both_empirical_supported':[True,False,True,False],
        'station_key':['a','b','a','b'],'region':['r1','r2','r1','r2'],'independence_group_old':['g1','g2','g1','g2'],
        'baseline_coverage90':[0.,0.,1.,1.],'groupmax_coverage90':[1.]*4,'empirical_coverage90':[1.]*4,
        'baseline_width90':[1.]*4,'groupmax_width90':[3.]*4,'empirical_width90':[2.]*4,
        'baseline_interval_score90':[4.]*4,'groupmax_interval_score90':[3.]*4,'empirical_interval_score90':[2.]*4})
    before=data.both_groupmax_supported.copy()
    summary,_=m.summarize(data)
    hidden=summary[summary.stratum.eq('unobserved_peak_excess')].set_index('scope')
    assert hidden.loc['both_groupmax_supported','n_supported']==2
    assert hidden.loc['both_groupmax_and_empirical_supported','n_supported']==1
    pd.testing.assert_series_equal(data.both_groupmax_supported,before)

def test_trend_alignment_checks_ranks_and_ignores_different_radii(tmp_path):
    module()
    path=Path(__file__).resolve().parents[1]/'scripts/724_groupmax_trend_propagation.py'
    spec=importlib.util.spec_from_file_location('groupmax_trend_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    fields=['years','truth','bounds','mask','q_D2','q_stochastic_calibrated',
            'rank_independent','rank_shared_parameters','rank_residual_blocks']
    data={key:np.array([1.,2.]) for key in fields};a=tmp_path/'a.npz';b=tmp_path/'b.npz'
    np.savez(a,**data,radius_D2=np.array(1.))
    np.savez(b,**data,radius_D2=np.array(3.))
    m.verify_previous(a,b)
    data['rank_independent']=np.array([1.,3.]);np.savez(b,**data,radius_D2=np.array(3.))
    with pytest.raises(ValueError,match='rank_independent'):m.verify_previous(a,b)

def test_bridge_repair_dependency_is_required_and_hash_checked(tmp_path):
    import hashlib
    module()
    path=Path(__file__).resolve().parents[1]/'scripts/721_groupmax_annual_audit.py'
    spec=importlib.util.spec_from_file_location('groupmax_audit_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    out=tmp_path/'result';out.mkdir();(tmp_path/'scripts').mkdir();(tmp_path/'data').mkdir()
    files={'repair_path':'data/repair.parquet','plan':'result/plan.json',
           'freeze':'result/source_freeze.json','effect':'result/source_repair_effect.csv',
           'audit_code':'scripts/729_bridge_repair_dependency.py'}
    for name in files.values():(tmp_path/name).write_text(name)
    record={'status':'passed','repaired_source_group_maxima_reproduced':True,'repair_path':files['repair_path'],
            'input_sha256':{name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in files.values()}}
    (out/'source_repair_dependency.json').write_text(json.dumps(record))
    m.verify_repair_dependency(tmp_path,out)
    (tmp_path/files['repair_path']).write_text('changed contents')
    with pytest.raises(ValueError,match='changed'):m.verify_repair_dependency(tmp_path,out)
    (tmp_path/files['repair_path']).write_text(files['repair_path'])
    (tmp_path/files['repair_path']).unlink()
    with pytest.raises(ValueError,match='missing'):m.verify_repair_dependency(tmp_path,out)
