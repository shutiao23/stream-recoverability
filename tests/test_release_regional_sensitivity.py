"""Zero published values must stay undefined in regional risk comparisons."""
import importlib.util
from pathlib import Path
import math
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('release_regions',Path(__file__).resolve().parents[1]/'scripts/560_release_regional_sensitivity.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_unpublished_group_is_not_assigned_zero_conditional_risk():
    rows=[dict(region='a',design_family='crossed',independence_group='g1',n=10,score_kept=5,three_kept=4,score_bad=1,three_bad=2),
          dict(region='b',design_family='crossed',independence_group='g2',n=10,score_kept=8,three_kept=0,score_bad=0,three_bad=0)]
    region,groups,leave,equal,directions=m.summarize(pd.DataFrame(rows))
    assert math.isnan(region.set_index('region').loc['b','three_error'])
    assert equal.n_both_defined.iloc[0]==1 and equal.n_three_zero.iloc[0]==1
    assert equal.three_mean_group_error.iloc[0]==pytest.approx(.5)
    assert directions.n_undefined.iloc[0]==1
    assert math.isnan(leave.set_index('excluded_region').loc['a','conditional_error_difference'])
    rows[0]['three_bad']=5
    with pytest.raises(ValueError,match='exceed'):
        m.summarize(pd.DataFrame(rows))
