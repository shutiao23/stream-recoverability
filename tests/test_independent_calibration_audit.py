"""Independent weighted endpoint ranks, source fallback and projection order."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import numpy as np
import pandas as pd

SPEC=spec_from_file_location("independent_calibration",Path(__file__).resolve().parents[1]/"scripts/971_independent_calibration_audit.py")
M=module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def test_weighted_endpoints_use_order_ranks_rather_than_interpolation():
    values=np.asarray([1.,2.,3.])
    weights=np.asarray([2,1,1])
    assert M.weighted_endpoint(values,weights,.25)==1
    assert M.weighted_endpoint(values,weights,.5)==2
    assert M.weighted_endpoint(values,weights,.95)==3
    for p in M.LEVELS:
        reference=np.quantile(np.repeat(values,weights),p,method="higher" if p>=.5 else "lower")
        assert M.weighted_endpoint(values,weights,p)==reference


def test_fallback_threshold_counts_cases_before_integer_multiplicity():
    for n, expected_fallback, expected_upper in [(49,True,10.),(50,False,0.)]:
        source=pd.DataFrame({"peak_overlap":[0.]*(n+49),"policy_choice":["air_ridge"]*n+["donor_ridge"]*49,
                             "eval_truth_h30":[0.]*n+[10.]*49,"observed_lower_bound__observed_days":[0.]*(n+49)})
        result,diagnostic=M.derive_offsets(source,np.zeros((len(source),7)),np.r_[np.full(n,10),np.ones(49,int)],
                                            ["__pooled__","0|air_ridge"])
        assert diagnostic["0|air_ridge"]["positive_valid_cell_cases"]==n
        assert diagnostic["0|air_ridge"]["fallback"]==expected_fallback
        assert result["0|air_ridge"][-1]==expected_upper


def test_target_projection_is_before_offset_and_after_sort():
    raw=np.asarray([[0.,1.,2.,3.,4.,5.,6.]])
    bound=np.asarray([3.])
    correction={"__pooled__":np.asarray([5.,4.,3.,2.,1.,0.,-1.])}
    expected=np.asarray([[5.,5.,5.,5.,6.,7.,8.]])
    np.testing.assert_array_equal(M.apply_offsets(raw,bound,["unknown-cell"],correction),expected)
    correction={"__pooled__":np.full(7,-10.)}
    np.testing.assert_array_equal(M.apply_offsets(raw,bound,["unknown-cell"],correction),np.full((1,7),3.))
