#!/usr/bin/env python3
"""Outcome-blind year-set sensitivities and daily gap-overlap accounting.

All annual predictions and observation inputs already exist. No model is fit.
The plan is an exploratory extension after the review, not preregistration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/wrr_review_response_20261027/whole_archive'
REF = ROOT / 'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet'
OLD = ROOT / 'results/wrr_process_revision_20261029'
ELIGIBLE = ROOT / 'results/wrr_review_response_20261027/rules/eligible_station_years.csv'
DAILY = ROOT / 'scratch/wrr_target_recovery_20261021/archive_daily.parquet'
DEFAULT_OUT = ROOT / 'results/wrr_process_experiments_20261029'
KEY = ['station_key', 'replicate', 'independence_group']
FIXED = ['warm90', 'legacy_random', 'legacy_time_balanced', 'cdf_all_years', 'sxx_all_years', 'all']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def stable_seed(station, replicate, seed):
    token = hashlib.sha256(station.encode()).digest()
    words = np.frombuffer(token[:16], dtype='<u4').tolist()
    return np.random.SeedSequence([969, int(replicate), int(seed), *words])


def year_geometry(years, full_years):
    """Scores contain only calendar years, including the fixed complete set."""
    years, full_years = np.asarray(years, int), np.asarray(full_years, int)
    grid = np.arange(full_years.min(), full_years.max() + 1)
    a = (years[:, None] <= grid).mean(axis=0)
    b = (full_years[:, None] <= grid).mean(axis=0)
    x = (years - years.mean()) / 10
    return dict(cdf_distance=float(np.mean((a-b)**2)), sxx=float(x @ x),
                span=int(years.max()-years.min()), mean_year=float(years.mean()),
                end_abs_weight=float(np.abs((x/(x@x))[[0, -1]]).sum()),
                max_abs_weight=float(np.max(np.abs(x/(x@x)))))


def select_geometry(subsets):
    """No temperature or errors may be consulted by either selection rule."""
    cdf = min(range(len(subsets)), key=lambda i: (round(subsets[i]['cdf_distance'], 14),
                                                 -round(subsets[i]['sxx'], 14),
                                                 subsets[i]['chosen_incomplete']))
    spread = min(range(len(subsets)), key=lambda i: (-round(subsets[i]['sxx'], 14),
                                                    round(subsets[i]['cdf_distance'], 14),
                                                    subsets[i]['chosen_incomplete']))
    return cdf, spread


def score_set(years, truth, predicted, selected):
    keep = np.isin(years, selected)
    full_x = (years-years.mean())/10
    target = float(full_x @ truth / (full_x @ full_x))
    x = (years[keep]-years[keep].mean())/10
    selected_truth = float(x @ truth[keep] / (x @ x))
    estimate = float(x @ predicted[keep] / (x @ x))
    e, s, r = estimate-target, selected_truth-target, estimate-selected_truth
    if abs(e-s-r) > 1e-12:
        raise RuntimeError('Casewise E=S+R failed')
    return dict(estimate_error=e, year_set_error=s, reconstruction_error=r,
                estimate_mse=e*e, year_set_mse=s*s, reconstruction_mse=r*r,
                cross_term=2*s*r, **year_geometry(selected, years))


def freeze_plan(out, draws, bootstraps):
    plan = dict(exploratory=True, design_origin='After the 2026-10-29 review and prior analyses; not preregistered',
                primary_cohort='805 actually masked all/warm90 common crossed-forward archives; 468 nontrivial-choice subset',
                denominator_sensitivity='807 original common archives restores two zero-mask cases; 13 warm90-unavailable cases remain outside paired comparisons',
                enumeration='Enumerate every same-count subset of incomplete years, retaining all fixed complete years',
                uniform_reference='Equal probability for each feasible subset within each archive; average squared errors within archive before cross-archive RMSE',
                cdf_objective='Minimize mean squared difference of retained and full-year empirical CDFs over integer calendar years min(full)..max(full), including fixed complete years',
                sxx_objective='Maximize centered Sxx in decade units over retained fixed complete plus selected incomplete years',
                tie_break='CDF: minimum CDF, maximum Sxx, lexicographically earliest incomplete-year tuple; Sxx: maximum Sxx, minimum CDF, earliest tuple. Objective ties rounded at 14 decimals.',
                selection_forbidden='Truth H30, reconstructed H30, errors, hot-year flags and source outcomes never enter either objective',
                random_seeds=list(range(draws)), random_seed_rule='SeedSequence([969, archive_replicate, draw_seed, four little-endian SHA256 station words]); uniform integer into lexicographic feasible subsets',
                bootstrap=dict(draws=bootstraps, seed=2026102969, unit='connected group; all paired archive rows retained',
                               weights=['equal archive (primary)', 'equal station', 'equal connected group']),
                random_variation='Across-seed percentiles are conditional selection variation, not confidence intervals; report mean(RMSE) separately from sqrt(mean(MSE))',
                gap_units='Annual longest contiguous missing run; observed station-year vs trial station-year-replicate. Trial runs use zero-based start indices.',
                daily_overlap_denominator='Only incomplete station-years and missing station-days with at least one other evaluable same-group station in that year. Single-station group-years are excluded, with counts reported.',
                limits=['No model refit, new station, new data download or causal identification',
                        'Same-count controls still cannot separately identify year count and position effects',
                        'Group bootstrap describes this cohort and assumes exchangeability of the recorded clusters',
                        'Same-day co-missingness does not establish common failure cause, donor use or an unobserved physical outage'])
    path = out/'time_gap_exploratory_plan.json'
    if path.exists():
        if json.loads(path.read_text())['design'] != plan:
            raise RuntimeError('Preserve the existing exploratory plan; use a new output directory')
    else:
        path.write_text(json.dumps(dict(created_utc=datetime.now(timezone.utc).isoformat(), design=plan), indent=2)+'\n')


def load_annual(out, seeds):
    reference = pd.read_parquet(REF, columns=['station_key','year','design_family','eval_truth_h30'])
    reference = reference.loc[reference.design_family.eq('crossed') & reference.year.ge(2010)]
    if reference.groupby(['station_key','year']).eval_truth_h30.nunique().max() != 1:
        raise RuntimeError('Reference outcome is not unique')
    ref = {station:g.drop_duplicates('year').set_index('year').eval_truth_h30.sort_index()
           for station,g in reference.groupby('station_key')}
    trends = pd.read_csv(BASE/'trends.csv')
    trends = trends.loc[trends.family.eq('crossed') & trends['mode'].eq('forward')
                        & trends.estimator.eq('D2') & trends.dependence.eq('point')]
    prior = pd.read_csv(OLD/'time_support_cases.csv')
    prior = prior.loc[prior.family.eq('crossed') & prior['mode'].eq('forward')]
    prior = prior.set_index(KEY+['scheme'])
    inputs = {REF, BASE/'trends.csv', OLD/'time_support_cases.csv', Path(__file__).resolve()}
    subsets, archives, fixed, expected, draws = [], [], [], [], []
    groups_years = {}
    for (station, replicate), block in trends.groupby(['station_key','replicate'], sort=True):
        saved = block.set_index('retention')
        folder = BASE/'crossed/forward'/f'replicate_{replicate:02d}'/station.replace('|','_')
        design_path = folder/'design.json'; prediction_path = folder/'annual_predictions.parquet'
        inputs.update([design_path, prediction_path])
        design = json.loads(design_path.read_text())
        series = ref[station]; years = series.index.to_numpy(int); truth = series.to_numpy(float)
        missing = np.isin(years, list(map(int, design['masks'])))
        if len(years) != design['n_years'] or missing.sum() != design['n_incomplete']:
            raise RuntimeError('Archive design does not match the reference year roster')
        point = truth.copy(); warm = ~missing
        if missing.any():
            pred = pd.read_parquet(prediction_path).set_index('year').reindex(years)
            point[missing] = pred.D2.to_numpy(float)[missing]
            warm |= missing & pred.warm_observed_fraction.ge(.9).to_numpy()
        if not np.isfinite(point).all() or warm.sum() != int(saved.loc['warm90','n_retained']):
            raise RuntimeError('Annual prediction availability or warm90 count changed')
        complete, incomplete = years[~missing], years[missing]
        k = int((missing & warm).sum())
        common = bool(saved.loc[['all','warm90'],'available'].all())
        identity = dict(station_key=station, replicate=int(replicate), independence_group=design['independence_group'], region=design['region'])
        info = dict(**identity, n_full=len(years), n_complete=len(complete), n_incomplete=len(incomplete),
                    n_warm=int(warm.sum()), k=k, original_common=common, actual_mask=bool(missing.any()),
                    primary=common and bool(missing.any()), nontrivial_choice=common and 0<k<len(incomplete),
                    reason='included_actual_mask_common' if common and missing.any() else
                           ('zero_mask_common' if common else 'warm90_below_five_retained_years'),
                    full_years=';'.join(map(str,years)), complete_years=';'.join(map(str,complete)),
                    candidate_incomplete_years=';'.join(map(str,incomplete)))
        all_score = score_set(years,truth,point,years)
        info.update(all_estimate_error=all_score['estimate_error'], all_estimate_mse=all_score['estimate_mse'])
        if not np.isclose(all_score['estimate_error'], saved.loc['all','error'], atol=1e-10):
            raise RuntimeError('All-year error differs from the original archive output')
        archives.append(info)
        groups_years[station] = (identity['independence_group'], years)
        if not common:
            if warm.sum() >= 5:
                raise RuntimeError('Unexplained original common-cohort exclusion')
            continue
        options = []
        for subset_id, chosen in enumerate(itertools.combinations(incomplete.tolist(), k)):
            selected = np.sort(np.r_[complete, chosen]).astype(int)
            row = dict(**identity, subset_id=subset_id, chosen_incomplete=tuple(chosen),
                       retained_years=';'.join(map(str,selected)), chosen_incomplete_years=';'.join(map(str,chosen)),
                       n_retained=len(selected), **score_set(years,truth,point,selected))
            options.append(row)
        for row in options:
            row['uniform_subset_probability'] = 1/len(options)
        lookup = {row['retained_years']:i for i,row in enumerate(options)}
        warm_key = ';'.join(map(str,years[warm]))
        selected_indices = {'warm90':lookup[warm_key]}
        for scheme, old_scheme in [('legacy_random','random_same_count'),('legacy_time_balanced','time_balanced')]:
            if missing.any():
                old_row = prior.loc[(station,int(replicate),identity['independence_group'],old_scheme)]
                selected_indices[scheme] = lookup[old_row.retained_years]
            else:
                selected_indices[scheme] = 0
        selected_indices['cdf_all_years'], selected_indices['sxx_all_years'] = select_geometry(options)
        for name, index in selected_indices.items():
            row = options[index].copy(); row.pop('chosen_incomplete')
            fixed.append(row | dict(scheme=name))
        fixed.append(identity | dict(scheme='all', n_retained=len(years), retained_years=';'.join(map(str,years)), **all_score))
        cols = ['estimate_mse','year_set_mse','reconstruction_mse','cross_term','cdf_distance','sxx','span','mean_year','end_abs_weight','max_abs_weight']
        mean = {col:float(np.mean([row[col] for row in options])) for col in cols}
        if abs(mean['estimate_mse']-mean['year_set_mse']-mean['reconstruction_mse']-mean['cross_term']) > 1e-12:
            raise RuntimeError('Exact uniform-subset MSE identity failed')
        expected.append(identity | dict(scheme='uniform_random_expected', n_subsets=len(options), n_retained=int(warm.sum()), **mean))
        chosen_draws = [int(np.random.default_rng(stable_seed(station,replicate,seed)).integers(len(options))) for seed in seeds]
        for seed,index in zip(seeds,chosen_draws):
            row=options[index]
            draws.append(identity | dict(draw_seed=seed, subset_id=index, estimate_mse=row['estimate_mse'],
                                         year_set_mse=row['year_set_mse'], reconstruction_mse=row['reconstruction_mse'],
                                         cross_term=row['cross_term']))
        for row in options:
            row.pop('chosen_incomplete')
            row.update({name+'_selected':index==row['subset_id'] for name,index in selected_indices.items()})
        subsets.extend(options)
    archive = pd.DataFrame(archives); subset = pd.DataFrame(subsets); exact = pd.DataFrame(expected)
    fixed = pd.DataFrame(fixed); draws = pd.DataFrame(draws)
    if (len(archive),int(archive.original_common.sum()),int(archive.primary.sum()),int(archive.nontrivial_choice.sum()),len(subset)) != (820,807,805,468,5758):
        raise RuntimeError('The review denominators or complete enumeration changed')
    for name,frame in [('time_archive_accounting',archive),('time_all_feasible_subsets',subset),
                       ('time_fixed_geometry_selections',fixed),('time_exact_random_expectations',exact),('time_random_selection_draws',draws)]:
        frame.to_parquet(out/(name+'.parquet'), index=False)
    archive.to_csv(out/'time_archive_accounting.csv',index=False)
    return archive,subset,fixed,exact,draws,groups_years,inputs


def cohort_weights(frame, weighting):
    if weighting=='equal_archive': return np.ones(len(frame))
    column='station_key' if weighting=='equal_station' else 'independence_group'
    return 1/frame.groupby(column).station_key.transform('size').to_numpy(float)


def time_summaries(out, archive, fixed, exact, draws, bootstraps):
    all_scores = pd.concat([fixed,exact],ignore_index=True)
    output, contrasts, random_output, selection_changes = [],[],[],[]
    for scope,selector in [('actual_mask_common',archive.primary),('choice_only',archive.nontrivial_choice),('original_common',archive.original_common)]:
        selected = archive.loc[selector].set_index(KEY)
        case = all_scores.set_index(KEY).loc[selected.index].reset_index()
        for weighting in ['equal_archive','equal_station','equal_group']:
            roster=selected.reset_index(); weights=cohort_weights(roster,weighting)
            group=roster.independence_group.to_numpy(); groups=sorted(set(group))
            rng=np.random.default_rng(2026102969)
            multiplicity=rng.multinomial(len(groups),np.full(len(groups),1/len(groups)),size=bootstraps)
            group_weights=np.array([weights[group==g].sum() for g in groups]); denom=multiplicity@group_weights
            errors={}
            for scheme,part in case.groupby('scheme'):
                part=part.set_index(KEY).reindex(selected.index)
                row=dict(scope=scope,weighting=weighting,scheme=scheme,n=len(part),stations=roster.station_key.nunique(),groups=len(groups))
                for field in ['estimate_mse','year_set_mse','reconstruction_mse','cross_term','cdf_distance','sxx','span','end_abs_weight','max_abs_weight']:
                    row[field]=float(np.average(part[field],weights=weights))
                for field in ['estimate','year_set','reconstruction']:
                    row[field+'_rmse']=float(np.sqrt(row[field+'_mse']))
                row['mse_identity_residual']=row['estimate_mse']-row['year_set_mse']-row['reconstruction_mse']-row['cross_term']
                output.append(row)
                errors[scheme]=part
            for field in ['estimate_mse','year_set_mse']:
                baseline=errors['warm90'][field].to_numpy(float)
                base_group=np.array([np.sum(weights[group==g]*baseline[group==g]) for g in groups])
                for scheme,part in errors.items():
                    if scheme=='warm90':continue
                    values=part[field].to_numpy(float)
                    ss=np.array([np.sum(weights[group==g]*values[group==g]) for g in groups])
                    delta=np.sqrt(multiplicity@ss/denom)-np.sqrt(multiplicity@base_group/denom)
                    contrasts.append(dict(scope=scope,weighting=weighting,scheme=scheme,field=field,n=len(roster),groups=len(groups),bootstraps=bootstraps,
                                          rmse_difference=float(np.sqrt(np.average(values,weights=weights))-np.sqrt(np.average(baseline,weights=weights))),
                                          group_percentile_low=float(np.quantile(delta,.025)),group_percentile_high=float(np.quantile(delta,.975))))
            draw=draws.merge(roster[KEY].assign(weight=weights),on=KEY,how='inner',validate='many_to_one')
            seed_rows=[]
            for seed,part in draw.groupby('draw_seed'):
                mse=float(np.average(part.estimate_mse,weights=part.weight))
                seed_rows.append(dict(scope=scope,weighting=weighting,draw_seed=int(seed),n=len(part),estimate_mse=mse,estimate_rmse=float(np.sqrt(mse))))
            seed_frame=pd.DataFrame(seed_rows);random_output.extend(seed_rows)
            exact_mse=float(np.average(errors['uniform_random_expected'].estimate_mse,weights=weights))
            selection_changes.append(dict(scope=scope,weighting=weighting,n=len(roster),random_draws=len(seed_rows),
                                          exact_sqrt_expected_mse=float(np.sqrt(exact_mse)),mean_draw_rmse=float(seed_frame.estimate_rmse.mean()),
                                          sqrt_mean_draw_mse=float(np.sqrt(seed_frame.estimate_mse.mean())),
                                          selection_percentile_low=float(seed_frame.estimate_rmse.quantile(.025)),
                                          selection_percentile_high=float(seed_frame.estimate_rmse.quantile(.975)),
                                          min_draw_rmse=float(seed_frame.estimate_rmse.min()),max_draw_rmse=float(seed_frame.estimate_rmse.max())))
    for name,rows in [('time_sensitivity_summary',output),('time_sensitivity_paired_cluster',contrasts),
                      ('time_random_seed_summary',random_output),('time_random_selection_variation',selection_changes)]:
        pd.DataFrame(rows).to_csv(out/(name+'.csv'),index=False)
    burden=[]
    for label,part in [('all_available_820',archive),('original_common_807',archive.loc[archive.original_common]),
                        ('actual_mask_common_805',archive.loc[archive.primary]),('warm90_unavailable_13',archive.loc[~archive.original_common])]:
        burden.append(dict(cohort=label,n=len(part),stations=part.station_key.nunique(),groups=part.independence_group.nunique(),
                           all_year_rmse=float(np.sqrt(part.all_estimate_mse.mean()))))
    pd.DataFrame(burden).to_csv(out/'time_availability_burden.csv',index=False)


def runs(mask):
    edges=np.diff(np.r_[False,mask,False].astype(int));starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)
    return [(int(a),int(b-a)) for a,b in zip(starts,ends)]


def parse_mask(spec,days):
    mask=np.zeros(days,dtype=bool)
    for item in str(spec).split(';'):
        if item:
            start,length=map(int,item.split(':'))
            if start<0 or length<=0 or start+length>days:raise ValueError('Mask is outside calendar year')
            mask[start:start+length]=True
    return mask


def gap_sensitivity(out, group_years, inputs):
    eligible=pd.read_csv(ELIGIBLE)
    eligible=eligible.loc[eligible.station_key.isin(group_years) & eligible.year.between(1981,2025)].copy()
    if eligible.duplicated(['station_key','year']).any():raise RuntimeError('Observed station-years are not unique')
    daily=pd.read_parquet(DAILY,columns=['station_key','date','water_c'],filters=[('station_key','in',sorted(group_years))])
    daily.date=pd.to_datetime(daily.date)
    if daily.duplicated(['station_key','date']).any():raise RuntimeError('Observed station-days are not unique')
    data={station:g.set_index('date').water_c for station,g in daily.groupby('station_key',observed=True)}
    records=[]
    for row in eligible.itertuples(index=False):
        dates=pd.date_range(f'{row.year}-01-01',f'{row.year}-12-31')
        mask=~np.isfinite(data[row.station_key].reindex(dates).to_numpy(float))
        lengths=[length for _,length in runs(mask)]
        longest=max(lengths,default=0)
        if longest!=int(row.longest_run) or bool(not mask.any())!=bool(row.complete_year):
            raise RuntimeError('Daily missingness does not reproduce the observed annual metadata')
        records.append(dict(source='observed',replicate=0,station_key=row.station_key,independence_group=row.independence_group,
                            year=int(row.year),mask=mask,longest_run=longest))
    for family in ['calendar','crossed']:
        for path in sorted((BASE/family/'forward').glob('replicate_*/*/design.json')):
            inputs.add(path);design=json.loads(path.read_text());station=design['station_key']
            for year in group_years[station][1]:
                days=366 if pd.Timestamp(int(year),12,31).is_leap_year else 365
                mask=parse_mask(design['masks'].get(str(year),''),days)
                records.append(dict(source=family,replicate=int(design['replicate']),station_key=station,
                                    independence_group=design['independence_group'],year=int(year),mask=mask,
                                    longest_run=max([length for _,length in runs(mask)],default=0)))
    peers={}
    for row in records:
        peers.setdefault((row['source'],row['replicate'],row['independence_group'],row['year']),[]).append(row)
    case=[]
    for rows in peers.values():
        counts=np.stack([row['mask'] for row in rows]).sum(axis=0)
        n_incomplete=sum(bool(row['mask'].any()) for row in rows)
        for row in rows:
            mask=row.pop('mask')
            if not mask.any():continue
            case.append(row | dict(missing_days=int(mask.sum()),peer_evaluable=len(rows)>1,evaluable_peer_stations=len(rows)-1,
                                   same_year_missing_peer=n_incomplete>1,same_day_missing_peer_days=int((mask & (counts>=2)).sum()),
                                   any_same_day_missing_peer=bool((mask & (counts>=2)).any()),
                                   missing_runs_zero_based=';'.join(f'{a}:{length}' for a,length in runs(mask))))
    cases=pd.DataFrame(case);summaries=[];by_rep=[]
    for source,part in cases.groupby('source'):
        periods=[('2010-2025',part.loc[part.year.ge(2010)])]
        if source=='observed':periods.append(('1981-2025',part))
        for period,block in periods:
            def summary(frame):
                peer=frame.loc[frame.peer_evaluable]
                return dict(n_incomplete_rows=len(frame),stations=frame.station_key.nunique(),replicates=frame.replicate.nunique(),
                            median_annual_longest=float(frame.longest_run.median()),share_annual_ge30=float(frame.longest_run.ge(30).mean()),
                            shared_year_fraction_all_incomplete=float(frame.same_year_missing_peer.mean()),
                            n_peer_evaluable_incomplete_rows=len(peer),n_no_evaluable_peer_excluded=int((~frame.peer_evaluable).sum()),
                            shared_year_fraction_peer_evaluable=float(peer.same_year_missing_peer.mean()),
                            same_day_overlap_fraction_peer_evaluable=float(peer.any_same_day_missing_peer.mean()),
                            peer_evaluable_missing_station_days=int(peer.missing_days.sum()),
                            shared_missing_station_days=int(peer.same_day_missing_peer_days.sum()),
                            shared_missing_day_fraction=float(peer.same_day_missing_peer_days.sum()/peer.missing_days.sum()) if len(peer) else np.nan)
            summaries.append(dict(source=source,period=period,**summary(block)))
            for replicate,rblock in block.groupby('replicate'):
                by_rep.append(dict(source=source,period=period,replicate=int(replicate),**summary(rblock)))
    cases.to_csv(out/'gap_overlap_station_year_cases.csv',index=False)
    result=pd.DataFrame(summaries);result.to_csv(out/'gap_overlap_summary.csv',index=False)
    pd.DataFrame(by_rep).to_csv(out/'gap_overlap_by_replicate.csv',index=False)
    expected={('observed','2010-2025'):(109,4),('observed','1981-2025'):(220,3),('calendar','2010-2025'):(3806,6),('crossed','2010-2025'):(3777,60)}
    for row in result.itertuples(index=False):
        if (row.n_incomplete_rows,row.median_annual_longest)!=expected[row.source,row.period]:
            raise RuntimeError('Common annual-longest-gap accounting changed')
    inputs.update([ELIGIBLE,DAILY])
    return result


def secondary_findings(out, archive, subsets, fixed, exact):
    """Clearly labelled fixed-prediction influence summaries, added post hoc."""
    summary=pd.read_csv(out/'time_sensitivity_summary.csv')
    contrasts=pd.read_csv(out/'time_sensitivity_paired_cluster.csv')
    random=pd.read_csv(out/'time_random_seed_summary.csv')
    main=summary.loc[summary.scope.eq('actual_mask_common') & summary.weighting.eq('equal_archive')].set_index('scheme')
    random=random.loc[random.scope.eq('actual_mask_common') & random.weighting.eq('equal_archive')]
    changes=[]
    for scheme in ['cdf_all_years','sxx_all_years']:
        count=sum(bool((part[scheme+'_selected']!=part.warm90_selected).any())
                  for _,part in subsets.groupby(KEY))
        changes.append(dict(scheme=scheme,different_selected_sets_from_warm90=count))
    score=pd.concat([fixed,exact],ignore_index=True).merge(archive[KEY+['primary']],on=KEY,validate='many_to_one')
    score=score.loc[score.primary];influence=[]
    for group in sorted(score.independence_group.unique()):
        part=score.loc[score.independence_group.ne(group)]
        baseline=np.sqrt(part.loc[part.scheme.eq('warm90'),'estimate_mse'].mean())
        for scheme in ['cdf_all_years','sxx_all_years','uniform_random_expected','all']:
            rmse=np.sqrt(part.loc[part.scheme.eq(scheme),'estimate_mse'].mean())
            influence.append(dict(removed_group=group,scheme=scheme,comparator_minus_warm90=rmse-baseline))
    influence=pd.DataFrame(influence)
    influence.to_csv(out/'time_secondary_leave_group_out.csv',index=False)
    findings=dict(status='completed_exploratory_analysis',primary_n=int(archive.primary.sum()),
                  all_original_archives=len(archive),original_common=int(archive.original_common.sum()),
                  nontrivial_choice=int(archive.nontrivial_choice.sum()),all_feasible_subset_rows=len(subsets),
                  zero_mask_additional_common_cases=int((archive.original_common & ~archive.actual_mask).sum()),
                  warm_unavailable_cases=int((~archive.original_common).sum()),fixed_geometry_selection_changes=changes,
                  primary_equal_archive_rows=main.reset_index()[['scheme','estimate_rmse','year_set_rmse','reconstruction_rmse','cross_term','cdf_distance','sxx','span']].to_dict('records'),
                  main_paired_group_intervals=contrasts.loc[contrasts.scope.eq('actual_mask_common') & contrasts.weighting.eq('equal_archive') & contrasts.field.eq('estimate_mse')].to_dict('records'),
                  secondary_influence_scope='Added after observing the new geometric controls; fixed predictions and selections, archive-weighted point contrasts only; no refit or additional bootstrap tests',
                  leave_group_out_ranges=influence.groupby('scheme').comparator_minus_warm90.agg(['min','max']).reset_index().to_dict('records'),
                  random_seeds_better_than_warm90=int(random.estimate_rmse.lt(main.loc['warm90','estimate_rmse']).sum()),
                  random_seed_count=len(random),interpretation=[
                      'Exact archive-conditional subset averaging removes the single-random-selection Monte Carlo approximation.',
                      'Outcome-blind same-count rules including fixed complete years perform better here. A blanket no-advantage claim across same-count rules is unsupported.',
                      'These exploratory controls do not identify pure year-count effects or constitute validated deployment rules.',
                      'All-year recovery remains much closer to the finite-record target than any same-count rule considered.',
                      'Actual same-day co-missingness is distinct from same-year overlap, common outage causes and measured selected-donor availability.'])
    (out/'time_gap_scientific_findings.json').write_text(json.dumps(findings,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    parser.add_argument('--random-draws',type=int,default=200)
    parser.add_argument('--bootstraps',type=int,default=10000)
    args=parser.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    freeze_plan(out,args.random_draws,args.bootstraps)
    archive,subsets,fixed,exact,draws,groups_years,inputs=load_annual(out,range(args.random_draws))
    print('Enumerated',len(subsets),'feasible subsets; scoring fixed selections and random expectation',flush=True)
    time_summaries(out,archive,fixed,exact,draws,args.bootstraps)
    gaps=gap_sensitivity(out,groups_years,inputs)
    secondary_findings(out,archive,subsets,fixed,exact)
    manifest={str(path.relative_to(ROOT)):digest(path) for path in sorted(inputs)}
    report=dict(status='completed',scope='Exploratory saved-prediction analysis and observed-date missingness audit; no refit or new data',
                archives=len(archive),original_common=int(archive.original_common.sum()),primary=int(archive.primary.sum()),
                nontrivial_choice=int(archive.nontrivial_choice.sum()),enumerated_subsets=len(subsets),random_draws=args.random_draws,
                gap_summary=gaps.to_dict('records'),input_sha256=manifest,
                output_units={'time_all_feasible_subsets.parquet':'One feasible same-count set per archive; uniform probability is conditional on that archive',
                              'time_exact_random_expectations.parquet':'One archive; squared errors first averaged over its uniform subsets',
                              'time_random_selection_draws.parquet':'One full-cohort random-seed realization per archive; seeds are not independent climates',
                              'time_sensitivity_paired_cluster.csv':'Group bootstrap of archive-conditional expected MSE or fixed MSE, then root; not a bootstrap of selected annual errors',
                              'gap_overlap_station_year_cases.csv':'Incomplete observed station-year or trial station-year-replicate; peer denominator excludes group-years without another evaluable station'})
    (out/'time_gap_experiments_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(gaps.to_string(index=False),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
