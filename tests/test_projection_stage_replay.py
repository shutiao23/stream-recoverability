import importlib.util
from pathlib import Path

import numpy as np


spec = importlib.util.spec_from_file_location(
    "projection_stage_replay", Path(__file__).resolve().parents[1] / "scripts/577_replay_annual_projection_stages.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_projection_attribution_respects_correction_order_and_missing_support():
    raw = np.array([[-2, -1, 0, 1, 2, 3, 4], [5] * 7, [1, 2, 3, 4, 5, 6, 7]], dtype=float)
    bound = np.array([0., 3., 0.])
    labels = np.array(["a", "b", "missing"])
    a, first, pre, final = audit.stages(raw, bound, labels, {"a": [-5] * 7, "b": [0] * 7},
                                         supported=np.array([True, True, False]))
    np.testing.assert_allclose(first[0], [0, 0, 0, 1, 2, 3, 4])
    np.testing.assert_allclose(pre[0], [-5, -5, -5, -4, -3, -2, -1])
    np.testing.assert_allclose(final[0], [0] * 7)
    assert np.isnan(a[2]).all() and np.isnan(final[2]).all()
    s = audit.stage_summary(pre, final, bound, np.array([1., 5., 4.]))
    assert s['n'] == 2 and s['zero_created'] == 1 and s['zero_retained'] == 1
    assert s['final_zero_missed'] == 1 and s['created_zero_missed'] == 1
    assert s['pre_below_bound'] == 1 and s['final_projection_changed'] == 1


def test_pooled_offsets_apply_only_to_missing_cell():
    raw = np.array([[1.] * 7, [1.] * 7])
    _, _, pre, final = audit.stages(raw, np.array([0., 0.]), np.array(['known', 'other']),
                                     {'known': [1.] * 7}, fallback=[2.] * 7)
    np.testing.assert_allclose(pre[:, 0], [2., 3.])
    np.testing.assert_allclose(final, pre)
