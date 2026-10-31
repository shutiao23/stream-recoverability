"""Independently reconstructed normal quantiles must recover a known reference."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from scipy.special import ndtr, ndtri

path=Path(__file__).resolve().parents[1]/'scripts/678_audit_single_year_trend_propagation.py'
spec=importlib.util.spec_from_file_location('single_year_trend_audit',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_audit_normal_tails_and_observed_support():
    q=ndtri(m.LEVELS)[None,:]
    samples=m.draw(q,np.array([-10.]))[:,0]
    lo,hi=np.quantile(samples,[.025,.975])
    assert ndtr(hi)-ndtr(lo)==pytest.approx(.95,abs=.004)
    bounded=m.draw(q,np.array([-.5]))[:,0]
    assert np.min(bounded)>=-.5
