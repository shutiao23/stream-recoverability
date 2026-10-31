"""Common-cohort denominator and paired contrasts must respect availability."""
import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location('paired_diagnostics', Path(__file__).resolve().parents[1] / 'scripts/542_uncertainty_paired_diagnostics.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_common_cohort_excludes_missing_coupling_and_keeps_paired_tail_difference():
    rows, trends, tails = [], [], []
    for rep in (0, 1):
        key = dict(family='crossed', mode='forward', estimator='D2', station_key='site', replicate=rep)
        rows.append(key | dict(independence_group='g1', n_eligible=4, n_available=4, coverage90=.75, width90=1., mae=.2))
        for dep in ('independent', 'shared_parameters', 'residual_blocks'):
            trends.append(key | dict(retention='all', dependence=dep,
                                     available=not (rep == 1 and dep == 'residual_blocks'),
                                     missing_coverage95=1., width95=2., interval_score95=2.))
        for tail, coverage in [('constant', False), ('normal', True)]:
            tails.append(key | dict(tails=tail, coverage95=coverage, width95=2., interval_score95=2.))
    common, summary, contrasts, total = module.summarize_common(pd.DataFrame(rows), pd.DataFrame(trends), pd.DataFrame(tails))
    assert len(common) == 1
    assert total.n_all.iloc[0] == 2
    assert summary.n_common.iloc[0] == 1
    assert summary.fraction_common.iloc[0] == .5
    assert summary.annual_coverage90_weighted.iloc[0] == .75
    contrast = contrasts.loc[contrasts.contrast.eq('normal_minus_constant') & contrasts.metric.eq('coverage95')].iloc[0]
    assert contrast.difference == pytest.approx(1)
    assert contrast.cluster_bootstrap_lower == pytest.approx(1)
    assert contrast.cluster_bootstrap_upper == pytest.approx(1)
