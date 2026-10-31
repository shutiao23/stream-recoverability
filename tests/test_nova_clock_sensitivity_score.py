import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'nova_clock_score', Path(__file__).resolve().parents[1] / 'scripts/605_nova_clock_sensitivity_score.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_original_mask_replay_checks_bounds_and_overlap():
    mask = audit.mask_from_runs(365, '3:4;20:2')
    assert mask.sum() == 6 and mask[3:7].all() and mask[20:22].all()
    with pytest.raises(ValueError, match='invalid'):
        audit.mask_from_runs(365, '3:4;6:3')
    with pytest.raises(ValueError, match='invalid'):
        audit.mask_from_runs(365, '360:10')


def test_paired_case_scores_enforce_bounds_and_have_expected_degenerate_crps():
    f = pd.DataFrame({'eval_truth_h30': [5., 7.], 'observed_lower_bound__observed_days': [4., 4.],
                      'D2': [5., 5.], 'stochastic_cal_q50': [4., 7.]})
    for level in audit.LEVELS:
        f[f'D2_q{level:02d}'] = [5., 5.]
        f[f'stochastic_cal_q{level:02d}'] = [4., 7.]
    draw = lambda q, lower: np.repeat(q[:, [3]], 128, axis=1)
    scores = audit.score_casewise(f, draw)
    np.testing.assert_allclose(scores.D2_mae, [0., 2.])
    np.testing.assert_allclose(scores.D2_crps, [0., 2.])
    np.testing.assert_allclose(scores.stochastic_coverage90, [0., 1.])
    f.loc[0, 'D2_q05'] = 3.
    with pytest.raises(ValueError, match='support'):
        audit.score_casewise(f, draw)
    f = f.copy()
    f.loc[0, 'D2_q05'] = 5.
    f.loc[0, 'eval_truth_h30'] = 3.
    with pytest.raises(ValueError, match='reference below'):
        audit.score_casewise(f, draw)
