"""Gap transfers preserve the missingness budget and calendar feasibility."""
import importlib.util
from collections import Counter
from pathlib import Path
import sys
import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('heat_gap_matched',SCRIPTS/'734_gap_matched_heat_stress.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_transfer_preserves_templates_and_common_years():
    baseline={2011:'20:30',2012:'100:60',2013:'200:90'}
    result=m.transfer_gap_templates(baseline,[2012,2014,2015])
    assert set(result)=={2012,2014,2015}
    assert result[2012]==baseline[2012]
    assert Counter(result.values())==Counter(baseline.values())


def test_transfer_requires_equal_count_and_fitting_years():
    with pytest.raises(ValueError,match='count changed'):
        m.transfer_gap_templates({2012:'100:30'},[2013,2014])
    with pytest.raises(ValueError,match='Cannot place'):
        m.transfer_gap_templates({2012:'336:30'},[2013])
    assert m.transfer_gap_templates({2012:'336:30'},[2016])=={2016:'336:30'}


def test_transfer_rejects_invalid_source_template():
    with pytest.raises(ValueError,match='extends beyond'):
        m.transfer_gap_templates({2013:'336:30'},[2016])
