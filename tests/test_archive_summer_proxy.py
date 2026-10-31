"""The archive proxy must not fit on hidden or future/target-year water."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts';sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('archive_summer_proxy',SCRIPTS/'768_summer_proxy_archive.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_joint_mask_blocks_hidden_values_and_rejects_overlap():
    dates=pd.date_range('2011-01-01','2012-12-31');values=np.arange(len(dates),dtype=float)
    masks={2011:'100:30',2012:'120:60'};a=m.apply_masks(values,dates.year,masks)
    altered=values.copy();altered[np.isnan(a)]+=100000
    b=m.apply_masks(altered,dates.year,masks)
    assert np.array_equal(a,b,equal_nan=True)
    with pytest.raises(ValueError,match='Overlapping'):m.apply_masks(values,dates.year,{2011:'100:30;120:30'})
    with pytest.raises(ValueError,match='beyond year'):m.apply_masks(values,dates.year,{2011:'350:30'})


def test_forward_fit_excludes_target_and_all_post_cutoff_water():
    dates=pd.date_range('2006-01-01','2013-12-31');rng=np.random.default_rng(2027)
    predictors=rng.normal(size=(len(dates),9));water=4+2*predictors[:,3]
    masks={2011:'190:30',2012:'210:30'};visible=m.apply_masks(water,dates.year,masks)
    complete={2006,2007,2008,2009,2010,2013}
    first=m.fit_summer(visible,dates,predictors,2011,'forward',complete)
    changed=visible.copy();changed[dates.year>=2010]+=500
    second=m.fit_summer(changed,dates,predictors,2011,'forward',complete)
    assert first==second and first['lag']==5 and first['max_training_year']==2009


def test_proxy_respects_observed_bound_and_marks_missing_fit_unavailable():
    dates=pd.date_range('2011-01-01','2011-12-31');visible=np.full(len(dates),10.);visible[:31]=20.;visible[100:130]=np.nan
    air=np.full((len(dates),9),np.nan)
    result=m.predict_year(visible,dates,air,2011,'forward',set())
    assert result['reason']=='observed_bound_only' and result['estimate']==20.
    visible[190:220]=np.nan
    result=m.predict_year(visible,dates,air,2011,'forward',set())
    assert not result['available'] and result['reason']=='insufficient_training_support'
