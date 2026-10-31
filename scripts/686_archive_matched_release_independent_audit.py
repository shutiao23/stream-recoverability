#!/usr/bin/env python3
"""Independently reconstruct selections, numerical trends and aggregate scores.

This checks the same cached predictions and reference records; it does not
independently reconstruct physical observations, fitted models or data rights.
The censored working-likelihood results are checked as stored, not refitted here.
"""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from joblib import Parallel, delayed

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / 'results/wrr_review_response_20261027'
ARCHIVE = REV / 'whole_archive'
PREVIOUS = REV / 'integrated_release_trend'
OUT = REV / 'archive_matched_release_trend'
PRIVATE = ROOT / 'private/wrr_archive_matched_release_trend_20261027'
KEY = ['family', 'mode', 'station_key', 'replicate']
spec = importlib.util.spec_from_file_location('selection_under_audit', ROOT / 'scripts/684_archive_matched_release_trend.py')
production = importlib.util.module_from_spec(spec)
spec.loader.exec_module(production)


def audit_one(path, by_year, meta, trends):
    family, mode, rep, _ = path.relative_to(ARCHIVE).parts[:4]
    design = json.loads((path.parent/'design.json').read_text())
    key = (family, mode, design['station_key'], int(rep.removeprefix('replicate_')))
    a = by_year.get_group(key).sort_values('year').set_index('year')
    columns = ['year', 'D2', 'risk_score']
    if pq.read_schema(path).names:
        p = pd.read_parquet(path, columns=columns).set_index('year')
    else:
        p = pd.DataFrame({'D2':pd.Series(dtype=float),'risk_score':pd.Series(dtype=float)}, index=pd.Index([], name='year', dtype=int))
    if p.index.has_duplicates or not p.index.isin(a.index).all():
        raise ValueError(f'Prediction alignment error: {key}')
    frame = a.join(p, how='left')
    original = frame.output_state.eq('estimate')
    # Python's sorted tuple ordering is independent of the production NumPy
    # lexsort; selection uses only score, quality, point availability and year.
    eligible = [(float(r.risk_score), int(y)) for y,r in frame.iterrows()
                if np.isfinite(r.risk_score) and np.isfinite(r.D2) and r.quality_flag != 1]
    chosen = {year for _,year in sorted(eligible)[:int(original.sum())]}
    if len(chosen) != int(original.sum()):
        raise ValueError(f'Unsupported comparator in checked cohort: {key}')
    score = frame.index.isin(chosen)
    prod = production.select_score(frame.risk_score.to_numpy(),frame.D2.to_numpy(),frame.quality_flag.to_numpy(),frame.index.to_numpy(),int(original.sum()))
    if not np.array_equal(score, prod):
        raise ValueError(f'Selection disagreement: {key}')
    observed = frame.output_state.eq('complete_observed').to_numpy()
    bounds = frame.observed_lower_bound.notna().to_numpy() & (frame.quality_flag.to_numpy() != 1) & ~observed & ~score
    ref = frame.eval_reference_h30.to_numpy(float)
    values = frame.D2.to_numpy(float)
    bad = np.isfinite(values) & (np.abs(values-ref) > .5)
    check = {'n_years':len(frame), 'n_masked':int((~observed).sum()), 'n_numeric':int(original.sum()),
             'n_original_bound':int(frame.output_state.eq('observed_bound').sum()), 'n_score_bound':int(bounds.sum()),
             'n_original_unknown':int(frame.output_state.eq('unknown').sum()),
             'n_score_unknown':int((~observed & ~score & ~bounds).sum()),
             'n_original_bad':int((original.to_numpy() & bad).sum()), 'n_score_bad':int((score & bad).sum()),
             'n_original_only':int((original.to_numpy() & ~score).sum()), 'n_score_only':int((score & ~original.to_numpy()).sum())}
    saved = meta.loc[key]
    for field,value in check.items():
        if int(saved[field]) != value:
            raise ValueError(f'Archive count mismatch {key}/{field}')
    # Independently solve ordinary least squares; common truth is a finite
    # archive statistic, not a long-term climate trend estimate.
    y = np.where(observed, ref, np.where(score, values, np.nan))
    keep = np.isfinite(y)
    old = trends.loc[key+('values_only','score')]
    if bool(old.available) != (int(keep.sum()) >= 5):
        raise ValueError(f'OLS availability mismatch: {key}')
    if old.available:
        x = frame.index.to_numpy(float)[keep]
        X = np.column_stack([np.ones(len(x)), (x-x.mean())/10])
        value = np.linalg.lstsq(X,y[keep],rcond=None)[0][1]
        if not np.isclose(value,float(old.slope),atol=1e-8,rtol=0):
            raise ValueError(f'OLS slope mismatch: {key}')
    return 1


def audit_summary(meta, trends, published):
    cells = 0
    for (family,mode,method), saved in published.groupby(['family','mode','method']):
        if len(saved) != 1:
            raise ValueError('Duplicate aggregate cell')
        row = saved.iloc[0]
        m = meta[(meta.family == family) & (meta['mode'] == mode) & meta.supported]
        t = trends[(trends.family == family) & (trends['mode'] == mode) & (trends.method == method)]
        o = t[t.rule == 'original'].set_index(KEY)
        s = t[t.rule == 'score'].set_index(KEY)
        if not o.index.equals(s.index):
            # Different row order is acceptable but membership must match.
            if set(o.index) != set(s.index): raise ValueError('Aggregate case identities differ')
            s = s.reindex(o.index)
        valid = o.available & s.available
        for col in ['n_masked','n_numeric','n_original_bound','n_score_bound','n_original_unknown','n_score_unknown','n_original_bad','n_score_bad','n_original_only','n_score_only']:
            if int(row[col]) != int(m[col].sum()): raise ValueError(f'Aggregate count differs: {col}')
        if int(row.n_common) != int(valid.sum()): raise ValueError('Common denominator differs')
        for rule, data in [('original',o),('score',s)]:
            rmse = np.sqrt(data.loc[valid,'squared_error'].mean())
            if not np.isclose(row['rmse_'+rule],rmse,rtol=0,atol=1e-12): raise ValueError('Aggregate RMSE differs')
        cells += 1
    return cells


def main():
    production.verify_inputs()
    annual = pd.read_parquet(PREVIOUS/'annual_decisions.parquet').groupby(KEY,sort=False)
    all_meta = pd.read_parquet(PRIVATE/'archive_choices.parquet')
    all_trends = pd.read_parquet(PRIVATE/'trend_results.parquet')
    meta = all_meta.set_index(KEY)
    trends = all_trends.set_index(KEY+['method','rule'])
    paths, _ = production.input_paths()
    checks = Parallel(n_jobs=4,verbose=10)(delayed(audit_one)(p,annual,meta,trends) for p in paths)
    cells = audit_summary(all_meta,all_trends,pd.read_csv(OUT/'summary.csv'))
    result = {'status':'passed', 'archive_settings_checked':sum(checks), 'selection_masks_checked':sum(checks),
              'score_ols_slopes_checked':int((all_trends.method.eq('values_only') & all_trends.rule.eq('score') & all_trends.available).sum()),
              'aggregate_cells_checked':cells,
              'scope':'Independent Python sorting and OLS reconstruction from the same saved cases, plus aggregate reconstruction; original likelihood replay performed during primary analysis. Censored likelihood slopes here are checked only in aggregate, not independently refitted.',
              'not_tested':'Physical sensors and original third-party data, model fitting, prospective thresholds, climate transfer, and data rights.'}
    (OUT/'independent_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    main()
