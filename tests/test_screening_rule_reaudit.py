"""Longest missing run is computed on the true chronological sequence."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
spec=importlib.util.spec_from_file_location('rules_reaudit',Path(__file__).resolve().parents[1]/'scripts/571_reaudit_screening_rules.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_missing_run_keeps_separate_gaps_distinct():
    assert m.longest_missing([np.nan,np.nan,1.,np.nan,2.,np.nan,np.nan,np.nan])==3
    assert m.longest_missing([1.,2.,3.])==0
