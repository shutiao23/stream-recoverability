#!/usr/bin/env python3
"""Post-hoc per-archive equal-count release and downstream trend comparison.

The score-only comparator uses the three-output method's own numerical count
within each evaluated archive. This is transductive and is not a deployable
threshold or a safety guarantee. Inputs and choices are frozen before this
analysis; previous results and source data were already inspected.
"""
from __future__ import annotations
import os
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'
os.umask(0o077)

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import norm

from stream_recoverability.experiments.tr_revision.archive import slope
from stream_recoverability.experiments.tr_revision.statistics import interval_score, lower_bound_trend

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / 'results/wrr_review_response_20261027'
ARCHIVE = REV / 'whole_archive'
PREVIOUS = REV / 'integrated_release_trend'
OUT = REV / 'archive_matched_release_trend'
PRIVATE = ROOT / 'private/wrr_archive_matched_release_trend_20261027'
ARCHIVE_KEY = ['family', 'mode', 'station_key', 'replicate']

def input_paths():
    predictions = sorted(p for family in ('calendar', 'crossed') for mode in ('offline', 'forward')
                         for p in (ARCHIVE / family / mode).glob('replicate_*/*/annual_predictions.parquet'))
    return predictions, [PREVIOUS / 'annual_decisions.parquet', PREVIOUS / 'station_repetitions.csv',
                         ROOT / 'scripts/532_integrated_release_trend.py',
                         ROOT / 'src/stream_recoverability/experiments/tr_revision/statistics.py',
                         ROOT / 'src/stream_recoverability/experiments/tr_revision/archive.py', Path(__file__)] + [x for p in predictions for x in (p, p.parent / 'design.json')]

def freeze():
    if (OUT / 'plan.json').exists():
        raise FileExistsError('The post-hoc analysis plan already exists')
    paths, inputs = input_paths()
    if len(paths) != 3320:
        raise RuntimeError(f'Expected the complete 3,320 archive settings; found {len(paths)}')
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = [{'path': str(p.relative_to(ROOT)), } for p in inputs]
    manifest_path = PRIVATE / 'input_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    plan = {'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'post-hoc, following examination of original release and trend results; not prospective registration',
            'archive_settings': len(paths), 'method': 'Within each archive, select the same number of masked-year estimates as the existing rule by lowest finite raw risk score, breaking ties by calendar year. Apply the same detected-quality exclusion; other rejected years retain the same visible lower-bound eligibility or are unknown. Complete observed years are unchanged.',
            'scoring': 'After both selections, compare absolute annual error greater than 0.5 C and finite-record slope errors for released numeric years alone and for numerical years plus the same working censored likelihood. Both methods use the same underlying D2 predictions.',
            'uncertainty': '4,000 connected-group bootstrap resamples, paired squared trend error difference, seed 684; equal-group mean separately. Descriptive and conditional on available fits.',
            'limitations': 'Uses target archive numerical count and target scores without labels to select a comparator, so not a prospective threshold; equal numerical counts need not imply identical bounds, unknowns, or information. One model seed, sampled masks and reused archives do not establish safety, calibration or independent climates. Working likelihood treats selected estimates as exact and censoring can be informative.',
            'privacy': 'Input manifest and archive-level outcomes are local private; only aggregates are in the review package.'}
    (OUT / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print(f'Frozen {len(paths)} archive settings and {len(manifest)} local inputs', flush=True)

def verify_inputs():
    plan = json.loads((OUT / 'plan.json').read_text())
    path = PRIVATE / 'input_manifest.json'
    manifest = json.loads(path.read_text())
    return plan

def select_score(risk, point, quality, years, n):
    """Exact count, same quality exclusion as actual rule; labels not accepted."""
    risk, point, quality, years = map(np.asarray, (risk, point, quality, years))
    if len(np.unique(years)) != len(years):
        raise ValueError('Years must be unique')
    eligible = np.isfinite(risk) & np.isfinite(point) & (quality != 1)
    pos = np.flatnonzero(eligible)
    if n < 0 or n > len(pos):
        return None
    order = np.lexsort((years[pos], risk[pos]))
    answer = np.zeros(len(years), dtype=bool)
    answer[pos[order[:n]]] = True
    return answer

def fit(years, exact, lower, method, truth):
    if method == 'values_only':
        keep = np.isfinite(exact)
        available = keep.sum() >= 5
        estimate = float(slope(years[keep], exact[keep])) if available else np.nan
        return {'available': bool(available), 'slope': estimate, 'squared_error': (estimate - truth) ** 2 if available else np.nan}
    result = lower_bound_trend(years, exact, lower)
    if not result['converged']:
        return {'available': False, 'slope': np.nan, 'squared_error': np.nan, 'coverage': np.nan, 'width': np.nan, 'interval_score': np.nan}
    value, se = result['slope'], result['se']
    result = {'available': True, 'slope': value, 'squared_error': (value-truth)**2, 'coverage': np.nan, 'width': np.nan, 'interval_score': np.nan}
    if np.isfinite(se) and se > 0:
        half = norm.ppf(.975) * se
        lo, hi = value-half, value+half
        result.update(coverage=float(lo <= truth <= hi), width=hi-lo,
                      interval_score=float(interval_score(lo, hi, truth, alpha=.05)))
    return result

def one(path, annual, previous):
    family, mode, rep, _ = path.relative_to(ARCHIVE).parts[:4]
    replicate = int(rep.removeprefix('replicate_'))
    design = json.loads((path.parent / 'design.json').read_text())
    station = design['station_key']
    key = (family, mode, station, replicate)
    a = annual.get_group(key).sort_values('year').copy()
    pred = pd.read_parquet(path, columns=['year', 'D2', 'risk_score', 'observed_lower_bound__observed_days'])
    if pred.year.duplicated().any():
        raise ValueError(f'Duplicate prediction year: {key}')
    a = a.merge(pred, on='year', how='left', validate='one_to_one', indicator=True)
    if (a.loc[a.output_state.eq('complete_observed'), '_merge'] == 'both').any():
        raise ValueError(f'Unexpected prediction in complete year: {key}')
    numeric = a.output_state.eq('estimate').to_numpy()
    matched = select_score(a.risk_score.to_numpy(float), a.D2.to_numpy(float), a.quality_flag.to_numpy(float), a.year.to_numpy(int), int(numeric.sum()))
    meta = dict(zip(ARCHIVE_KEY, key)) | {'region': design['region'], 'independence_group': design['independence_group'],
            'n_years': len(a), 'n_masked': int(a.output_state.ne('complete_observed').sum()), 'n_numeric': int(numeric.sum()),
            'supported': matched is not None}
    if matched is None:
        return meta, []
    # This compares the saved original release against a fresh replay, including
    # cases that are not selected by either method; no truth enters selection.
    if not np.allclose(a.loc[numeric, 'D2'], a.loc[numeric, 'released_estimate'], rtol=0, atol=1e-10, equal_nan=False):
        raise ValueError(f'Saved estimates do not match annual prediction: {key}')
    bound = a.observed_lower_bound.to_numpy(float)
    original_bound = a.observed_lower_bound__observed_days.to_numpy(float)
    if not np.allclose(bound, original_bound, rtol=0, atol=1e-10, equal_nan=True):
        raise ValueError(f'Saved visible bounds do not match annual predictions: {key}')
    complete = a.output_state.eq('complete_observed').to_numpy()
    valid_bound = np.isfinite(bound) & (a.quality_flag.to_numpy(float) != 1) & ~complete
    baseline_bound = valid_bound & ~matched
    original_censor = a.output_state.eq('observed_bound').to_numpy()
    truth = a.eval_reference_h30.to_numpy(float)
    years = a.year.to_numpy(int)
    point = a.D2.to_numpy(float)
    expected = float(slope(years, truth))
    outcome = np.isfinite(point) & (np.abs(point-truth) > .5)
    meta.update(n_original_bound=int(original_censor.sum()), n_score_bound=int(baseline_bound.sum()),
                n_original_unknown=int((~complete & ~numeric & ~original_censor).sum()),
                n_score_unknown=int((~complete & ~matched & ~baseline_bound).sum()),
                n_original_bad=int((numeric & outcome).sum()), n_score_bad=int((matched & outcome).sum()),
                n_original_only=int((numeric & ~matched).sum()), n_score_only=int((matched & ~numeric).sum()))
    if meta['n_original_only'] != meta['n_score_only']:
        raise ValueError('Numerical retention is not matched')
    rows = []
    for label, selected, censored in [('original', numeric, original_censor), ('score', matched, baseline_bound)]:
        exact = np.where(complete, truth, np.where(selected, point, np.nan))
        lower = np.where(censored, bound, np.nan)
        for method in ('values_only', 'values_and_bounds'):
            result = fit(years, exact, lower, method, expected)
            if label == 'original':
                old = previous.loc[key + ('released_values_only' if method == 'values_only' else 'released_values_and_bounds',)]
                if bool(old.available) != result['available'] or not np.isclose(float(old.truth_slope), expected, rtol=0, atol=1e-8):
                    raise ValueError(f'Original trend availability or truth mismatch: {key}/{method}')
                if result['available'] and not np.isclose(float(old.slope), result['slope'], rtol=0, atol=1e-7):
                    raise ValueError(f'Original trend replay mismatch: {key}/{method}')
            rows.append(dict(zip(ARCHIVE_KEY, key)) | {'method': method, 'rule': label, **result})
    return meta, rows

def summarize(meta, rows):
    summaries, clusters = [], []
    rng = np.random.default_rng(684)
    for (family, mode), block in meta.groupby(['family', 'mode'], sort=True):
        ok = block[block.supported]
        entry = {'family': family, 'mode': mode, 'n_archives': len(block), 'n_matched_archives': len(ok),
                 'n_groups': ok.independence_group.nunique(), 'n_stations': ok.station_key.nunique()}
        for col in ['n_masked','n_numeric','n_original_bound','n_score_bound','n_original_unknown','n_score_unknown','n_original_bad','n_score_bad','n_original_only','n_score_only']:
            entry[col] = int(ok[col].sum())
        for method in ('values_only', 'values_and_bounds'):
            x = rows[(rows.family == family) & (rows['mode'] == mode) & (rows.method == method)]
            original = x[x.rule == 'original'].drop(columns='rule')
            score = x[x.rule == 'score'].drop(columns='rule')
            pair = original.merge(score, on=ARCHIVE_KEY + ['method'], suffixes=('_original','_score'), validate='one_to_one')
            pair = pair.merge(ok[ARCHIVE_KEY+['independence_group']], on=ARCHIVE_KEY, validate='one_to_one')
            common = pair[pair.available_original & pair.available_score].copy()
            diff = common.squared_error_original - common.squared_error_score
            group = common.assign(diff=diff).groupby('independence_group')['diff'].agg(['sum','count','mean'])
            draws = rng.integers(len(group), size=(4000, len(group))) if len(group) else np.empty((0,0),int)
            boot = group['sum'].to_numpy()[draws].sum(axis=1) / group['count'].to_numpy()[draws].sum(axis=1) if len(group) else np.array([])
            row = entry | {'method': method, 'n_original_available': int(pair.available_original.sum()), 'n_score_available': int(pair.available_score.sum()),
                           'n_common': len(common), 'n_common_groups': len(group),
                           'rmse_original': float(np.sqrt(common.squared_error_original.mean())) if len(common) else np.nan,
                           'rmse_score': float(np.sqrt(common.squared_error_score.mean())) if len(common) else np.nan,
                           'paired_mse_original_minus_score': float(diff.mean()) if len(common) else np.nan,
                           'group_equal_mse_difference': float(group['mean'].mean()) if len(group) else np.nan,
                           'bootstrap_low': float(np.quantile(boot,.025)) if len(boot) else np.nan,
                           'bootstrap_high': float(np.quantile(boot,.975)) if len(boot) else np.nan}
            if method == 'values_and_bounds':
                interval = common[common.coverage_original.notna() & common.coverage_score.notna()]
                row.update(n_common_intervals=len(interval), **{f'{measure}_{rule}':float(interval[f'{measure}_{rule}'].mean()) if len(interval) else np.nan for measure in ['coverage','width','interval_score'] for rule in ['original','score']})
            summaries.append(row)
            clusters.extend([{'family':family,'mode':mode,'method':method,'independence_group':g,'paired_sum':r['sum'],'paired_count':r['count'],'paired_mean':r['mean']} for g,r in group.iterrows()])
    return pd.DataFrame(summaries), pd.DataFrame(clusters)

def run(workers):
    verify_inputs()
    paths, _ = input_paths()
    annual = pd.read_parquet(PREVIOUS / 'annual_decisions.parquet').groupby(ARCHIVE_KEY, sort=False)
    previous = pd.read_csv(PREVIOUS / 'station_repetitions.csv').set_index(ARCHIVE_KEY+['method'])
    results = Parallel(n_jobs=workers, verbose=10)(delayed(one)(p, annual, previous) for p in paths)
    meta = pd.DataFrame([m for m,_ in results])
    rows = pd.DataFrame([r for _,rs in results for r in rs])
    if meta.duplicated(ARCHIVE_KEY).any() or len(meta) != 3320:
        raise ValueError('Incorrect archive cohort')
    meta.to_parquet(PRIVATE/'archive_choices.parquet', index=False)
    rows.to_parquet(PRIVATE/'trend_results.parquet', index=False)
    summary, groups = summarize(meta, rows)
    summary.to_csv(OUT/'summary.csv', index=False)
    groups.to_csv(OUT/'group_summary.csv', index=False)
    status = {'status':'computed', 'archives':len(meta), 'matched_archives':int(meta.supported.sum()),
              'original_trend_replayed':True, 'truth_used_to_select':False,
              'limitations':'Retrospective count matching uses the target archive and is not prospective. Aggregate bounds/unknowns may differ. Same source data, models and original likelihood; no new external reference.'}
    (OUT/'status.json').write_text(json.dumps(status, indent=2)+'\n')
    print(summary.to_string(index=False), flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['freeze','run'])
    p.add_argument('--workers', type=int, default=4)
    args = p.parse_args()
    freeze() if args.action == 'freeze' else run(args.workers)
