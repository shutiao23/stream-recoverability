"""The literature-inspired proxy must not use hidden target-year water."""
import importlib.util
from pathlib import Path
import numpy as np

path=Path(__file__).resolve().parents[1]/'scripts/761_beaufort_proxy_experiment.py'
spec=importlib.util.spec_from_file_location('beaufort_proxy',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_air_lags_are_right_aligned_and_include_june():
    air=np.tile(np.arange(71,dtype=float),(9,1));lags=m.lagged_air(air)
    assert lags.shape==(9,9,62)
    assert np.isclose(lags[0,0,0],np.mean([8.,9.]))
    assert np.isclose(lags[0,8,0],np.mean(np.arange(10,dtype=float)))
    assert np.isclose(lags[0,8,-1],np.mean(np.arange(61,71,dtype=float)))


def test_hidden_water_does_not_change_model_or_filled_prediction():
    rng=np.random.default_rng(13);air=rng.normal(size=(9,9,62));water=3+2*air[:,3,:]
    hidden=np.array([False,True,False,False,False,True,False,False,False])
    a=m.fit_and_estimate(water,air,hidden);altered=water.copy();altered[hidden]+=1000
    b=m.fit_and_estimate(altered,air,hidden)
    assert a==b and a['lag']==5 and a['train_days']==7*62
    assert np.isclose(a['training_r2'],1.)
    assert np.isclose(a['filled_mean'],np.mean([m.summer_peak(v) for v in water]))


def test_no_visible_years_or_constant_air_is_unavailable():
    water=np.arange(9*62,dtype=float).reshape(9,62);air=np.ones((9,9,62))
    assert m.fit_and_estimate(water,air,np.ones(9,dtype=bool)) is None
    assert m.fit_and_estimate(water,air,np.array([True]+[False]*8)) is None
