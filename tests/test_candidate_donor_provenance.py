"""Coverage reconstruction must use the saved hidden days and exact threshold."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts';sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('candidate_donor_provenance',SCRIPTS/'773_candidate_donor_provenance.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_masked_day_coverage_uses_90_percent_and_ignores_other_days():
    data=np.ones((20,3),dtype=bool);mask=np.arange(20)<10
    data[0,1]=False;data[:2,2]=False;data[10:,0]=False
    assert m.visible_columns(data,mask).tolist()==[True,True,False]
    data[10:]=~data[10:]
    assert m.visible_columns(data,mask).tolist()==[True,True,False]


def test_empty_mask_is_not_silently_treated_as_visibility():
    with pytest.raises(ValueError,match='No hidden days'):
        m.visible_columns(np.ones((5,2),bool),np.zeros(5,bool))
