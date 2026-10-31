"""A conflicting or unapproved USGS day cannot become a reference value."""
import importlib.util
from pathlib import Path
import pandas as pd

spec=importlib.util.spec_from_file_location('usgs_reaudit',Path(__file__).resolve().parents[1]/'scripts/572_reaudit_usgs_witnesses.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_local_day_and_ambiguous_approval():
    assert m.local_day('2020-01-01T06:00:00Z','America/Chicago')==pd.Timestamp('2020-01-01')
    assert m.local_day('2020-01-01','America/Chicago')==pd.Timestamp('2020-01-01')
    a={'time':'2020-01-01','value':'5','approval_status':'Approved','qualifier':[]}
    b={'time':'2020-01-01','value':'6','approval_status':'Approved','qualifier':[]}
    out=m.approved_values([a,b],'America/Chicago')
    assert pd.isna(out.loc[pd.Timestamp('2020-01-01'),'value'])
    b['value']='5';b['approval_status']='Provisional'
    out=m.approved_values([a,b],'America/Chicago')
    assert pd.isna(out.loc[pd.Timestamp('2020-01-01'),'value'])
    assert m.has_estimate(['E']) and not m.has_estimate(['A'])
