"""Case-summary comparison must reject changed or missing rows."""
import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('case_audit',Path(__file__).resolve().parents[1]/'scripts/569_verify_private_case_evidence.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_comparison_is_keyed_and_detects_missing_or_changed_values():
    a=pd.DataFrame({'key':['a','b'],'value':[1.,float('nan')]})
    b=pd.DataFrame({'key':['b','a'],'value':[float('nan'),1.]})
    assert m.compare(a,b,['key'],['value'])==2
    with pytest.raises(ValueError,match='missing'):
        m.compare(a,b.iloc[:1],['key'],['value'])
    b.loc[b.key.eq('a'),'value']=2.
    with pytest.raises(ValueError,match='differs'):
        m.compare(a,b,['key'],['value'])
