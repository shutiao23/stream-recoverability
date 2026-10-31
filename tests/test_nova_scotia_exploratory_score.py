import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'nova_exploratory_score', Path(__file__).resolve().parents[1] / 'scripts/598_nova_scotia_exploratory_score.py'
)
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def frame():
    values = pd.DataFrame({'design_family': ['crossed', 'crossed'], 'peak_overlap': [.6, 0.],
        'station_key': ['a', 'b'], 'year': [2010, 2011], 'eval_truth_h30': [5., 4.],
        'observed_lower_bound__observed_days': [4., 4.], 'h30__policy': [3., 4.],
        'D2': [5., 4.], 'stochastic_cal_q50': [4., 4.]})
    for level in score.LEVELS:
        values[f'D2_q{level:02d}'] = [5., 4.]
        values[f'stochastic_cal_q{level:02d}'] = [4., 4.]
    return values


def constant_draws(q, lower):
    return np.repeat(q[:, [3]], 128, axis=1)


def test_scores_are_paired_and_plugin_obeys_observation_bound():
    rows, paired, years = score.score_tables(frame(), constant_draws)
    all_rows = rows.loc[rows.stratum.eq('all')].set_index('estimator')
    assert all_rows.loc['plug_in', 'mae'] == pytest.approx(.5)
    assert all_rows.loc['D2', 'mae'] == pytest.approx(0.)
    assert all_rows.loc['stochastic_calibrated', 'mae'] == pytest.approx(.5)
    assert paired.loc[paired.stratum.eq('all'), 'n_common'].iloc[0] == 2
    assert paired.loc[paired.stratum.eq('danger'), 'n_common'].iloc[0] == 1
    assert len(years) == 2


def test_quantiles_below_the_observation_bound_are_rejected():
    x = frame()
    x.loc[0, 'D2_q05'] = 3.
    with pytest.raises(ValueError, match='support violation'):
        score.score_tables(x, constant_draws)
