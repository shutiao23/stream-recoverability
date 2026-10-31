import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest


def load():
    path = Path(__file__).resolve().parents[1]/'scripts/689_fixed_count_heat_stress.py'
    if str(path.parent) not in sys.path:
        sys.path.insert(0,str(path.parent))
    spec = importlib.util.spec_from_file_location('matched_heat_stress',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matched_count_and_heat_weight_do_not_select_burn_in():
    choose = load().matched_heat_years
    baseline = [0.1,0.1,0.5,0.8,0.8]
    uniforms = [0.99,0.5,0.8,0.5,0.4]
    eligible = [False,True,True,True,True]
    hot = [True,False,False,True,False]
    actual = choose(baseline,uniforms,eligible,hot)
    assert actual.tolist() == [False,False,False,True,False]
    assert actual.sum() == ((np.array(baseline) < .35) & eligible).sum()


def test_matched_count_rejects_bad_draws_and_handles_zero():
    choose = load().matched_heat_years
    assert not choose([.5,.6],[.2,.3],[True,True],[True,False]).any()
    with pytest.raises(ValueError):
        choose([.2,.3],[.5,1.],[True,True],[True,False])
    with pytest.raises(ValueError):
        choose([.2],[.5],[True,True],[True])


def test_donor_information_loss_counts_only_observed_donor_values():
    path = Path(__file__).resolve().parents[1]/'scripts/691_expanded_stress_comparison.py'
    spec = importlib.util.spec_from_file_location('expanded_stress_audit',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    index = pd.date_range('2020-01-01', periods=5, freq='D')
    panel = pd.DataFrame({'target':[1.,2.,3.,4.,5.], 'donor_a':[np.nan,2.,3.,np.nan,5.],
                          'donor_b':[1.,np.nan,np.nan,np.nan,5.]},index=index)
    assert module.gap_observation_counts(panel,'target',{'2020':'1:3'}) == (3,2,1)
    assert module.gap_observation_counts(panel,'target',{'2020':'3:5'}) == (2,2,2)
