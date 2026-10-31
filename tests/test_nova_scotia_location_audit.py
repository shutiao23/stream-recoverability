import importlib.util
from pathlib import Path

import numpy as np


spec = importlib.util.spec_from_file_location(
    'nova_location_audit', Path(__file__).resolve().parents[1] / 'scripts/594_nova_scotia_location_audit.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_haversine_is_zero_at_same_point_and_symmetric():
    a = audit.haversine(45., -64., [45., 46.], [-64., -60.])
    b = audit.haversine(46., -60., [45.], [-64.])
    assert a[0] == 0.
    np.testing.assert_allclose(a[1], b[0], rtol=1e-12)
