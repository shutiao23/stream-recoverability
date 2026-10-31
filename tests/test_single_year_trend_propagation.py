"""An interval extension must preserve support, medians and paired 90% endpoints."""
import importlib.util
import os
from pathlib import Path
import sys
import numpy as np
import pytest

scripts=Path(__file__).resolve().parents[1]/'scripts';sys.path.insert(0,str(scripts))
old_umask=os.umask(0o077)
try:
    spec=importlib.util.spec_from_file_location('trend_propagation',scripts/'677_single_year_trend_propagation.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
finally:os.umask(old_umask)


def test_two_shapes_share_endpoints_and_leave_complete_year_unchanged():
    q=np.array([[1.,2.,3.,4.,5.,6.,7.],[2.,3.,4.,5.,6.,7.,8.]])
    bound=np.array([0.,2.]);mask=np.array([True,False])
    endpoint=m.adjust_quantiles(q,bound,mask,2.,'endpoint_only')
    tapered=m.adjust_quantiles(q,bound,mask,2.,'tapered')
    np.testing.assert_allclose(endpoint[:,[0,-1]],tapered[:,[0,-1]])
    np.testing.assert_allclose(endpoint[:,3],q[:,3]);np.testing.assert_allclose(tapered[:,3],q[:,3])
    np.testing.assert_array_equal(endpoint[1],q[1]);np.testing.assert_array_equal(tapered[1],q[1])
    assert np.all(endpoint>=bound[:,None]) and np.all(tapered>=bound[:,None])
    assert np.all(np.diff(endpoint,axis=1)>=0) and np.all(np.diff(tapered,axis=1)>=0)
    assert endpoint[0,1]!=tapered[0,1]


def test_extension_rejects_reversed_quantiles_and_negative_radius():
    q=np.array([[1.,2.,3.,4.,5.,6.,7.]])
    with pytest.raises(ValueError,match='invalid'):
        m.adjust_quantiles(q,np.array([0.]),np.array([True]),-1.,'tapered')
    q[0,2]=.5
    with pytest.raises(ValueError,match='invalid'):
        m.adjust_quantiles(q,np.array([0.]),np.array([True]),1.,'tapered')
