import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    'strict_region_refit', Path(__file__).resolve().parents[1] / 'scripts/610_strict_region_refit.py'
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def test_full_region_groups_removed_without_reassigning_other_groups():
    cases = pd.DataFrame({'region': ['held', 'other', 'other', 'other', 'other'],
                          'independence_group': ['a', 'a', 'c', 'd', 'e']})
    roles = {'estimator': ['a', 'c', 'd'], 'interval': ['a', 'd', 'e'],
             'risk': ['a', 'c', 'e'], 'rule': ['a', 'c', 'd']}
    weights = {key: np.array([1., 2., 3., 4., 5.]) for key in roles}
    original = lambda c, region, seed: (np.array([True, False, False, False, False]), roles, weights)
    held, filtered, corrected = audit.filtered_roles(cases, 'held', 7, original)
    assert held.tolist() == [True, False, False, False, False]
    assert filtered['estimator'] == ['c', 'd'] and filtered['interval'] == ['d', 'e']
    for value in corrected.values():
        np.testing.assert_array_equal(value, [0., 0., 3., 4., 5.])

def test_cannot_claim_strict_refit_when_a_role_loses_source_support():
    cases = pd.DataFrame({'region': ['held', 'other'], 'independence_group': ['a', 'b']})
    original = lambda c, region, seed: (np.array([True, False]), {'estimator': ['a', 'b']}, {'estimator': np.ones(2)})
    with pytest.raises(ValueError, match='fewer than two groups'):
        audit.filtered_roles(cases, 'held', 7, original)

def load_script_module(name, filename):
    import sys
    scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, Path(scripts) / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_annual_replacement_joins_by_case_not_dataframe_index_or_order():
    annual = load_script_module('strict_annual_diagnostics_test', '617_strict_region_annual_diagnostics.py')
    old = pd.DataFrame({
        'family': ['crossed'] * 3, 'mode': ['forward'] * 3,
        'replicate': [0, 1, 0], 'station_key': ['a', 'a', 'b'],
        'year': [2011, 2012, 2013], 'region': ['usgs_huc17', 'usgs_huc17', 'other'],
        'D2_q50': [1., 2., 3.],
    }, index=[10, 20, 30])
    changed = old.iloc[[1, 0]][annual.KEY + ['D2_q50']].copy()
    changed['D2_q50'] = [22., 11.]
    result = annual.replace_annual_quantiles(old, changed, ['D2_q50'])
    assert result.D2_q50.tolist() == [11., 22., 3.]
    with pytest.raises(ValueError, match='replacement scope'):
        annual.replace_annual_quantiles(old, changed.iloc[:1], ['D2_q50'])

def test_zero_weight_group_can_still_change_risk_group_partition():
    effect = load_script_module('strict_effect_audit_test', '618_strict_region_effect_audit.py')
    cases = pd.DataFrame({'independence_group': ['a', 'b', 'c', 'd']})
    weights = {'risk_learning': np.array([0., 1., 1., 1.])}
    original = {'risk_learning': ['a', 'b', 'c', 'd']}
    filtered = {'risk_learning': ['b', 'c', 'd']}
    original_classifier, original_probability = effect.risk_masks(cases, original, weights)
    strict_classifier, strict_probability = effect.risk_masks(cases, filtered, weights)
    assert original_classifier.tolist() == [False, True, True, False]
    assert original_probability.tolist() == [False, False, False, True]
    assert strict_classifier.tolist() == [False, True, True, False]
    assert strict_probability.tolist() == [False, False, False, True]
    # Different ordering demonstrates that deleting a zero-weight name can
    # move a positive-weight group across the 75% split even though weights
    # themselves do not change.
    original = {'risk_learning': ['b', 'c', 'a', 'd']}
    oc, op = effect.risk_masks(cases, original, weights)
    filtered = {'risk_learning': ['b', 'c', 'd']}
    sc, sp = effect.risk_masks(cases, filtered, weights)
    assert np.array_equal(oc, sc) and np.array_equal(op, sp)
    # For five groups, removing the zero-weight entry changes the split size.
    cases = pd.DataFrame({'independence_group': ['a', 'b', 'c', 'd', 'e']})
    weights = {'risk_learning': np.array([0., 1., 1., 1., 1.])}
    oc, op = effect.risk_masks(cases, {'risk_learning': ['a','b','c','d','e']}, weights)
    sc, sp = effect.risk_masks(cases, {'risk_learning': ['b','c','d','e']}, weights)
    assert not np.array_equal(oc, sc) and not np.array_equal(op, sp)

def test_uncertainty_replacement_requires_same_keys_and_preserves_other_cases():
    diagnostics = load_script_module('strict_uncertainty_test', '622_strict_region_uncertainty_sensitivity.py')
    original = pd.DataFrame({'case': ['a', 'b', 'c'], 'region': ['held', 'held', 'other'], 'value': [1., 2., 3.]})
    strict = pd.DataFrame({'case': ['b', 'a'], 'region': ['held', 'held'], 'value': [22., 11.]})
    revised = diagnostics.replace(original, strict, ['case'], original.region.eq('held')).set_index('case')
    assert revised.loc['a', 'value'] == 11.
    assert revised.loc['b', 'value'] == 22.
    assert revised.loc['c', 'value'] == 3.
    with pytest.raises(ValueError, match='replacement keys differ'):
        diagnostics.replace(original, strict.iloc[:1], ['case'], original.region.eq('held'))

def test_group_bootstrap_preserves_constant_paired_difference():
    diagnostics = load_script_module('strict_uncertainty_bootstrap_test', '622_strict_region_uncertainty_sensitivity.py')
    mean, low, high, count = diagnostics.group_bootstrap_difference(['g1', 'g1', 'g2'], [.5, .5, .5])
    assert (mean, low, high, count) == (.5, .5, .5, 2)
    with pytest.raises(ValueError, match='invalid paired bootstrap'):
        diagnostics.group_bootstrap_difference(['g1'], [np.nan])

def test_scenario_cache_rejects_changed_model_or_calibration():
    scenario = load_script_module('strict_scenario_cache_test', '621_strict_region_scenario_sensitivity.py')
    inputs = {'model_sha256': 'a'*64, 'calibration_sha256': 'b'*64}
    scenario.require_matching_inputs({'inputs': inputs.copy()}, inputs)
    with pytest.raises(ValueError, match='input dependencies differ'):
        scenario.require_matching_inputs({'inputs': inputs.copy()}, inputs | {'model_sha256': 'c'*64})
    with pytest.raises(ValueError, match='input dependencies differ'):
        scenario.require_matching_inputs({'inputs': inputs.copy()}, inputs | {'calibration_sha256': 'd'*64})

def test_robustness_bootstrap_preserves_paired_group_shift():
    mod=load_script_module('strict_robustness_test','645_strict_region_robustness.py')
    frame=pd.DataFrame({'independence_group':['a','a','b'],
                        'old_difference':[0.1,0.2,-0.1],
                        'strict_difference':[0.6,0.7,0.4]})
    result=mod.bootstrap_pairs(frame,draws=1000,seed=1)
    assert result['strict_minus_old_low']==pytest.approx(.5)
    assert result['strict_minus_old_high']==pytest.approx(.5)
    assert result['old_pooled_low']<=result['old_pooled_high']

def test_robustness_bootstrap_rejects_empty_groups():
    mod=load_script_module('strict_robustness_empty_test','645_strict_region_robustness.py')
    frame=pd.DataFrame({'independence_group':pd.Series(dtype=str),'old_difference':pd.Series(dtype=float),'strict_difference':pd.Series(dtype=float)})
    with pytest.raises(ValueError,match='empty paired group'):
        mod.bootstrap_pairs(frame)

def test_robustness_bootstrap_rejects_unknown_group_or_missing_difference():
    mod=load_script_module('strict_robustness_invalid_test','645_strict_region_robustness.py')
    frame=pd.DataFrame({'independence_group':['a',None],'old_difference':[0.1,0.2],'strict_difference':[0.2,0.3]})
    with pytest.raises(ValueError,match='invalid paired group'):
        mod.bootstrap_pairs(frame)
