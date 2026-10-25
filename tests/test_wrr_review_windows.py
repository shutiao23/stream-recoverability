import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from stream_recoverability.experiments.tr_revision.windows import primary_view,native_view
from stream_recoverability.experiments.tr_revision.simulation import prepare_replay,replay_from_prepared


def script(name,path):
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location(name,root/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def test_native_h7_view_never_relabels_secondary_h30_values():
    c=pd.DataFrame({"primary_target":["h7"],"primary_window_days":[7],"eval_truth_h7":[10.],"eval_truth_h30":[3.],
                    "h7__policy":[9.],"h30__policy":[2.],"train_h7_mean":[8.],"train_h7_sd":[1.],"train_h7_q90":[9.],
                    "state_h7_q05":[7.],"state_h30_q05":[1.]})
    v=primary_view(c)
    assert v.eval_truth_h30.iloc[0]==10 and v.h30__policy.iloc[0]==9 and v.state_h30_q05.iloc[0]==7
    assert c.eval_truth_h30.iloc[0]==3 and native_view(v).eval_truth_h7.iloc[0]==10


def test_h7_draw_quantiles_and_failure_scores_use_seven_day_functional():
    m=script("window_draw_test","scripts/431_tr_cases.py")
    dates=pd.date_range("2001-01-01",periods=365)
    draws=np.zeros((20,365));draws[:,30:37]=10
    result=m.draw_summary("state",draws,dates,{"h7":10.,"h30":7/3},8.,("h7",),20.,primary="h7")
    assert result["state_h7_q50"]==10 and result["state_pfail_point_050"]==1
    assert all(f"state_h7_q{int(q*100):02d}" in result for q in m.QUANTILES)
    original=m.draw_summary("state",draws,dates,{"h30":7/3},7/3,("h30",),20.)
    np.testing.assert_allclose(original["state_h30_q50"],7/3)


def test_h7_replay_and_recovery_variance_use_seven_not_thirty():
    dates=pd.date_range("1999-01-01","2001-12-31")
    water=pd.Series(10+np.sin(np.arange(len(dates))/17),index=dates)
    residual=np.sin(np.arange(len(dates))/3)*.2
    fixtures=prepare_replay(water,residual,[1999,2000,2001],window=7)
    actual=replay_from_prepared(fixtures,tuple(range(100,108)),window=7)
    expected=[]
    for year in [1999,2000,2001]:
        good=dates.year==year;truth=water.to_numpy()[good];completed=truth.copy();hidden=np.isin(dates[good].dayofyear,range(100,108))
        completed[hidden]-=residual[good][hidden]
        expected.append(np.convolve(completed,np.ones(7)/7,'valid').max()-np.convolve(truth,np.ones(7)/7,'valid').max())
    np.testing.assert_allclose(actual,expected,atol=1e-10)
    law=script("window_law_test","scripts/wrr_tr_law.py")
    row=pd.Series({"law_sigma_a":2.,"law_sigma_r_warm":.8,"law_mu_r_warm":0.,"law_phi_r":0.,"law_phi_a":0.,"law_mu_r_peak":-.2,"law_sigma_r_peak":.8})
    _,sd,_=law.component_moments(np.array([1.]),np.array([1.]),row,"v2p",window=7)
    np.testing.assert_allclose(sd,.8/np.sqrt(7))
