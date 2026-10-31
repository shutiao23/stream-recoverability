from pathlib import Path
import importlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
E = importlib.import_module("418_wrr_state_risk_evidence")


def test_incomplete_discharge_remains_unknown_and_conditions_can_overlap():
    frame = pd.DataFrame({"warm_anomaly": [True, False, True, False],
                          "flow_coverage": [1., 1., .5, np.nan],
                          "gap_lowflow_fraction": [.5, .4, .9, np.nan]})
    masks = E.condition_masks(frame)
    np.testing.assert_array_equal(masks["low_flow"], [True, False, False, False])
    np.testing.assert_array_equal(masks["other_flow"], [False, True, False, False])
    np.testing.assert_array_equal(masks["unknown_flow"], [False, False, True, True])
    assert masks["warm"][0] and masks["low_flow"][0]


def test_unverified_warm_or_complete_flow_state_cannot_be_silently_classified():
    frame = pd.DataFrame({"warm_anomaly": [True], "flow_coverage": [1.], "gap_lowflow_fraction": [np.nan]})
    with pytest.raises(ValueError, match="verified gap-state"):
        E.condition_masks(frame)
    frame["warm_anomaly"] = None
    with pytest.raises(ValueError, match="Warm-year"):
        E.condition_masks(frame)
