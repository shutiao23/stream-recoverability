"""The input-panel audit distinguishes float32 rounding from value changes."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
spec=importlib.util.spec_from_file_location('panel_audit',Path(__file__).resolve().parents[1]/'scripts/574_input_panel_precision_audit.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_missingness_and_float32_cast_are_checked_separately():
    x=np.array([.1,np.nan,3.25]);stored=x.astype(np.float32).astype(float)
    missing,rounding,cast,n=m.compare_daily(x,stored)
    assert missing==0 and cast==0 and n==2 and 0<rounding<1e-6
    changed=stored.copy();changed[1]=1.;changed[2]=4.
    missing,_,cast,_=m.compare_daily(x,changed)
    assert missing==1 and cast==1
