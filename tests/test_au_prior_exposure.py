import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('au_prior_exposure',Path(__file__).resolve().parents[1]/'scripts/646_au_prior_exposure_audit.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_hot_year_overlap_includes_both_halves_of_calendar_year():
    ref=pd.DataFrame({'station_id':['01','02'],'year':[2020,2020],'role':['test','development'],'observed_sampling_reference_eligible':[True,True]})
    old=pd.DataFrame({'station_id':['01','01','02'],'year':[2020,2020,2019],'old_evaluation_case_eligible':[True,False,True]})
    hot=pd.DataFrame({'station_id':['01','01','02'],'hot_year_start':['2019-07-01','2020-07-01','2018-07-01'],
                      'hemisphere_shift_days':[184,184,184],'old_evaluation_case_eligible':[True,False,True]})
    out=m.audit_reference(ref,old,hot).set_index('station_id')
    assert out.loc['01','calendar_cases']==2 and out.loc['01','calendar_eligible']==1
    assert out.loc['01','hot_overlapping_windows']==2 and out.loc['01','hot_overlap_eligible']==1
    assert out.loc['02','calendar_cases']==0 and out.loc['02','hot_overlapping_windows']==0


def test_same_station_year_in_multiple_roles_is_not_silently_merged():
    ref=pd.DataFrame({'station_id':['01','01'],'year':[2020,2020],'role':['test','calibration'],'observed_sampling_reference_eligible':[True,True]})
    with pytest.raises(ValueError,match='multiple old roles'):
        m.audit_reference(ref,pd.DataFrame(),pd.DataFrame())
