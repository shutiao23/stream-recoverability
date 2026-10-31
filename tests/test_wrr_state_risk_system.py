from pathlib import Path
import importlib
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
S = importlib.import_module("417_wrr_state_risk_system")


def test_changing_delivered_point_redefines_its_own_error_and_CDF_tolerance_event():
    base = pd.DataFrame({"reconstruction_point": [0., 0.], "policy_metric": [0., 0.],
                         "local_hot_threshold_C": [9., 9.], "truth_hottest30": [10., 10.],
                         "h30_samples_C": [np.full(32, 10.), np.full(32, 10.)]})
    first = S.point_frame(base, [0., np.nan])
    second = S.point_frame(base, [10., 10.])
    assert first.own_failure.tolist() == [True, True]
    assert second.own_failure.tolist() == [False, False]
    assert first.CDF_failure_probability.iloc[0] == 1.
    assert second.CDF_failure_probability.eq(0.).all()
    assert np.isnan(first.CDF_failure_probability.iloc[1])
    assert base.reconstruction_point.eq(0.).all()


def test_system_median_uses_the_same_first_32_draw_budget_and_retains_unavailability():
    values = np.r_[np.full(32, 10.), np.full(480, 30.)]
    frame = pd.DataFrame({"h30_samples_C": [values, None]})
    point = S.median_points(frame)
    assert point[0] == 10. and np.isnan(point[1])
