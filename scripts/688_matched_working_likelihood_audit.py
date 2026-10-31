#!/usr/bin/env python3
"""Reconstruct matched archive censored fits with a second likelihood routine.

The observations and selections are shared with the primary analysis. This
checks numerical reproduction, not the working likelihood's appropriateness,
prospective risk, physical observations or external independence.
"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import json
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from joblib import Parallel, delayed
from scipy.optimize import minimize
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT/'results/wrr_review_response_20261027'
ARCH = REV/'whole_archive'
OUT = REV/'archive_matched_release_trend'
PRIVATE = ROOT/'private/wrr_archive_matched_release_trend_20261027'
KEY = ['family','mode','station_key','replicate']

def independent_fit(years, exact, lower):
    valid = np.isfinite(exact)
    censored = ~valid & np.isfinite(lower)
    if valid.sum() < 5 or np.ptp(years[valid]) == 0:
        return False, np.nan
    x = (years - years.mean())/10
    gradient, intercept = np.polyfit(x[valid],exact[valid],1)
    log_sd = np.log(max(float(np.std(exact[valid]-intercept-gradient*x[valid])),.05))
    def objective(params):
        mu = params[0]+params[1]*x
        sd = np.exp(params[2])
        exact_logp = norm.logpdf(exact[valid],loc=mu[valid],scale=sd).sum()
        censor_logp = norm.logsf(lower[censored],loc=mu[censored],scale=sd).sum()
        return -float(exact_logp+censor_logp)
    fit = minimize(objective,[intercept,gradient,log_sd],method='BFGS',options={'gtol':1e-6})
    success = bool(np.isfinite(fit.fun) and fit.success or np.linalg.norm(fit.jac)<1e-3)
    return success, float(fit.x[1]) if success else np.nan

def one(path, years_group, saved):
    family,mode,rep,_ = path.relative_to(ARCH).parts[:4]
    design = json.loads((path.parent/'design.json').read_text())
    key = (family,mode,design['station_key'],int(rep.removeprefix('replicate_')))
    a = years_group.get_group(key).sort_values('year').set_index('year')
    if pq.read_schema(path).names:
        p = pd.read_parquet(path,columns=['year','D2','risk_score']).set_index('year')
    else:
        p = pd.DataFrame({'D2':pd.Series(dtype=float),'risk_score':pd.Series(dtype=float)},index=pd.Index([],name='year',dtype=int))
    a = a.join(p,how='left')
    original = a.output_state.eq('estimate').to_numpy()
    eligible = sorted((float(r.risk_score), int(y)) for y,r in a.iterrows()
                      if np.isfinite(r.risk_score) and np.isfinite(r.D2) and r.quality_flag != 1)
    selected = {year for _,year in eligible[:int(original.sum())]}
    if len(selected) != int(original.sum()): raise ValueError('Count matching failed')
    score = a.index.isin(selected)
    observed = a.output_state.eq('complete_observed').to_numpy()
    bound = a.observed_lower_bound.to_numpy(float)
    quality = a.quality_flag.to_numpy(float)
    score_bound = np.isfinite(bound) & ~observed & ~score & (quality != 1)
    out = []
    for rule, selected_mask, bound_mask in [('original',original,a.output_state.eq('observed_bound').to_numpy()),('score',score,score_bound)]:
        exact = np.where(observed,a.eval_reference_h30.to_numpy(float),np.where(selected_mask,a.D2.to_numpy(float),np.nan))
        lower = np.where(bound_mask,bound,np.nan)
        success, estimate = independent_fit(a.index.to_numpy(float),exact,lower)
        prior = saved.loc[key+('values_and_bounds',rule)]
        out.append({'rule':rule,'family':family,'mode':mode,'old_available':bool(prior.available),'new_available':success,
                    'old_slope':float(prior.slope),'new_slope':estimate,
                    'n_censored':int(bound_mask.sum())})
    return out

def main():
    spec = importlib.util.spec_from_file_location('frozen_plan',ROOT/'scripts/684_archive_matched_release_trend.py')
    plan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plan)
    plan.verify_inputs()
    amendment = json.loads((OUT/'empty_input_amendment.json').read_text())
    annual = pd.read_parquet(REV/'integrated_release_trend/annual_decisions.parquet').groupby(KEY,sort=False)
    saved = pd.read_parquet(PRIVATE/'trend_results.parquet').set_index(KEY+['method','rule'])
    paths = sorted(p for family in ('calendar','crossed') for mode in ('offline','forward')
                   for p in (ARCH/family/mode).glob('replicate_*/*/annual_predictions.parquet'))
    if len(paths) != 3320: raise ValueError('Archive cohort changed')
    results = Parallel(n_jobs=4,verbose=10)(delayed(one)(p,annual,saved) for p in paths)
    frame = pd.DataFrame([x for pair in results for x in pair])
    common = frame.old_available & frame.new_available
    delta = (frame.loc[common,'new_slope']-frame.loc[common,'old_slope']).abs()
    counts = {'archive_settings':len(paths),'working_fits_checked':len(frame),'common_converged':int(common.sum()),
              'original_only_converged':int((frame.old_available & ~frame.new_available).sum()),
              'independent_only_converged':int((~frame.old_available & frame.new_available).sum()),
              'neither_converged':int((~frame.old_available & ~frame.new_available).sum()),
              'common_difference_above_1e_5':int(delta.gt(1e-5).sum()),
              'common_difference_above_1e_3':int(delta.gt(1e-3).sum()),
              'max_absolute_slope_difference':float(delta.max()) if len(delta) else None,
              'scope':'Second BFGS likelihood calculation using normal log-density and survival function; same cached data, matched selection and likelihood assumption. This is numerical reproduction, not independent data or statistical validation.'}
    frame.to_parquet(PRIVATE/'independent_likelihood_fits.parquet',index=False)
    (OUT/'independent_likelihood_audit.json').write_text(json.dumps(counts,indent=2)+'\n')
    print(json.dumps(counts,indent=2),flush=True)

if __name__ == '__main__':
    main()
