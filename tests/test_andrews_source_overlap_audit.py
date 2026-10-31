import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('andrews_overlap', Path(__file__).resolve().parents[1] / 'scripts/624_andrews_source_overlap_audit.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def data():
    c = pd.DataFrame({'station_key': ['usgs|14161500', 'usgs|14161500', 'usgs|14162200', 'usgs|99999999'],
        'region': ['usgs_huc17'] * 4, 'independence_group': ['g1', 'g1', 'g1', 'g2'], 'year': [2013, 2014, 2014, 2014]})
    m = pd.DataFrame({'site_no': ['14161500', '14162200', '99999999'], 'station_nm': ['lookout', 'blue', 'other'],
        'dec_lat_va': [1., 2., 3.], 'dec_long_va': [4., 5., 6.], 'huc_cd': ['x', 'x', 'y']})
    return c, m


def test_overlap_audit_uses_connected_group_and_distinct_years():
    cases, meta = data()
    rows, target = module.summarize(cases, meta)
    assert set(rows.site_no) == {'14161500', '14162200'}
    assert target.unique_case_years == 2
    assert target.masked_case_rows == 2


def test_overlap_audit_rejects_ambiguous_source_identity():
    cases, meta = data()
    cases.loc[1, 'independence_group'] = 'g2'
    with pytest.raises(ValueError, match='group ambiguous'):
        module.summarize(cases, meta)
    cases, meta = data()
    with pytest.raises(ValueError, match='identifiers are not unique'):
        module.summarize(cases, pd.concat([meta, meta.iloc[[0]]]))
