"""Check the independent annual interval and distribution-score arithmetic."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
spec=importlib.util.spec_from_file_location('independent_candidate_annual',scripts/'669_reaudit_open_source_annual.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_constant_predictive_distribution_with_known_miss():
    scores=m.independent_scores(np.full((1,7),3.0),np.array([4.0]),np.array([2.0]))
    assert scores['mae'][0]==pytest.approx(1.)
    assert scores['bias'][0]==pytest.approx(-1.)
    assert scores['coverage90'][0]==0.
    assert scores['width90'][0]==0.
    assert scores['interval_score90'][0]==pytest.approx(20.)
    assert scores['crps'][0]==pytest.approx(1.)
    assert scores['zero90'][0]==1.
