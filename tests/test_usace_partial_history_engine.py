from pathlib import Path
import importlib.util
import sys
import numpy as np
import pandas as pd


def module():
    p=Path(__file__).resolve().parents[1]/'scripts/835_usace_partial_history_engine.py'
    if str(p.parent) not in sys.path:sys.path.insert(0,str(p.parent))
    spec=importlib.util.spec_from_file_location('usace_partial_engine',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_history_rule_requires_endpoints_and_limits_longest_gap():
    m=module();x=pd.Series(np.ones(365));x.iloc[100:145]=np.nan
    assert m.history_qualifies(x)
    x.iloc[145]=np.nan;assert not m.history_qualifies(x)
    x.iloc[100:146]=1;x.iloc[0]=np.nan;assert not m.history_qualifies(x)


def test_training_interpolation_does_not_fill_target_natural_gaps():
    m=module();dates=pd.date_range('2021-01-01','2024-12-31');values=np.full(len(dates),10.)
    for date in ['2021-06-01','2022-06-01','2023-06-01','2024-06-01']:
        values[dates.get_loc(pd.Timestamp(date))]=np.nan
    daily=pd.DataFrame({'resource_id':'r','day':dates,'mean_c':values}).dropna()
    panel,natural,history=m.prepare_panel(daily,'r',2024,[2021,2022,2023],placeholder=432.1)
    panel=panel.set_index('date').r
    assert panel.loc['2021-06-01']==10
    assert panel.loc['2024-06-01']==432.1
    assert natural[pd.Timestamp('2024-06-01').dayofyear-1]
    assert sum(x['interpolated_days'] for x in history)==3
