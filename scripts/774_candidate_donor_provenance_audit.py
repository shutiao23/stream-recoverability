#!/usr/bin/env python3
"""Independent sample visibility and all-role checks for donor provenance."""
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.seeds import plain_seed

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026';SOURCE=PRIVATE/'candidate_cases'
SPLITS={'offline':'leave_one_year_out','forward':'before_2010'}


def mask_runs(text,n):
    mask=np.zeros(n,dtype=bool)
    for item in str(text).split(';'):
        if not item:continue
        start,length=map(int,item.split(':'))
        if start<0 or length<1 or start+length>n or mask[start:start+length].any():raise ValueError('Invalid saved mask')
        mask[start:start+length]=True
    if not mask.any():raise ValueError('Empty mask')
    return mask


def roles_independently(frame,region,shares,names):
    held=frame.region.eq(region)
    if 'training_partition' in frame:held &= frame.training_partition.eq('test')
    held_groups=set(frame.loc[held,'independence_group']);eligible=frame.loc[~frame.independence_group.isin(held_groups)]
    if 'training_partition' in frame:eligible=eligible.loc[eligible.training_partition.eq('train')]
    groups=np.array(sorted(eligible.independence_group.unique()));regions=sorted(frame.region.unique())
    rng=np.random.default_rng(plain_seed(7,0,regions.index(region)));rng.shuffle(groups)
    cuts=np.maximum.accumulate(np.round(np.cumsum(shares)[:-1]*len(groups)).astype(int));parts=np.split(groups,cuts)
    forbidden=set(frame.loc[frame.region.eq(region),'independence_group']);result={};selected={}
    for name,part in zip(names,parts):
        drawn=rng.choice(part,len(part),replace=True)
        result[name]=set(drawn)-forbidden;selected[name]=[str(x) for x in part if x not in forbidden]
    return result,selected


def main():
    status=json.loads((OUT/'donor_provenance_status.json').read_text())
    if status['status']!='completed_with_unresolved_provenance':raise ValueError('Main provenance audit incomplete')
    config=json.loads((ROOT/'configs/wrr_review_completion_20261024.json').read_text());plan=json.loads((OUT/'plan.json').read_text())
    roles_summary=pd.read_csv(OUT/'donor_provenance_roles.csv');case_summary=pd.read_csv(OUT/'donor_provenance_cases.csv')
    station=pd.read_parquet(T.E1/'station_years.parquet',columns=['network_id','provider','station_id'])
    coverage=pd.read_csv(T.COVERAGE,dtype=str,usecols=['network_id','provider','station_id'])
    # Construct independent string keys, rather than the tuple sets used by the first implementation.
    def keys(df):return set(df.network_id.astype(str)+'\t'+df.provider.astype(str)+'\t'+df.station_id.astype(str))
    station_keys=keys(station);all_keys=station_keys|keys(coverage)
    usgs=set(pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype={'site_no':str}).site_no.astype(str))
    jobs=T.load_script('independent_donor_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source')
    by_key={(j['network_id'],j['station_id']):j for j in jobs}
    total_cases=checked_roles=checked_cells=0
    for mode,split in SPLITS.items():
        frame=pd.read_parquet(SOURCE/split/'seed_00.parquet')
        frame=frame.loc[frame.policy_choice.ne('unavailable')&frame.eval_truth_h30.notna()].reset_index(drop=True)
        flags=pd.read_parquet(PRIVATE/'donor_provenance'/(mode+'_case_flags.parquet'))
        columns=['network_id','station_id','year','design_family','mask_runs','policy_choice']
        pd.testing.assert_frame_equal(frame[columns].reset_index(drop=True),flags[columns].reset_index(drop=True),check_dtype=False)
        merged=frame[['network_id','station_id','provider','region','independence_group','policy_choice']].copy()
        merged=merged.join(flags[['visible_outside_station_inventory','visible_outside_all_local_catalogs','finite_donor_estimate']])
        if 'training_partition' in frame:merged['training_partition']=frame.training_partition
        for provider,g in merged.groupby('provider',sort=True):
            actual=case_summary[(case_summary['mode']==mode)&(case_summary.provider==provider)]
            if len(actual)!=1:raise ValueError('Missing provider summary')
            r=actual.iloc[0];unresolved=g.visible_outside_all_local_catalogs
            counts=[len(g),int(g.visible_outside_station_inventory.sum()),int(unresolved.sum()),
                    int((unresolved&g.finite_donor_estimate).sum()),int((unresolved&g.policy_choice.eq('donor_ridge')).sum())]
            saved=[int(r.cases),int(r.visible_outside_station_inventory),int(r.visible_outside_all_local_catalogs),
                   int(r.finite_donor_estimate_outside_all_catalogs),int(r.policy_donor_outside_all_catalogs)]
            if counts!=saved:raise AssertionError('Provider case summary mismatch')
            checked_cells+=1
        for item in plan['target_mode_region_stations']:
            if item['mode']!=mode:continue
            region=item['region'];positive,selected=roles_independently(merged,region,config['fit_role_shares'],config['fit_role_names'])
            model=json.loads((PRIVATE/'refits'/split/'seed_00'/(region+'.json')).read_text())
            if model['roles']!=selected:raise AssertionError('Independent role assignments differ')
            for role,groups in positive.items():
                choose=merged.independence_group.isin(groups)
                if 'training_partition' in merged:choose &= merged.training_partition.eq('train')
                u=merged.visible_outside_all_local_catalogs;f=merged.finite_donor_estimate
                observed=[int(choose.sum()),int(merged.loc[choose,'independence_group'].nunique()),int((choose&u).sum()),int((choose&u&f).sum())]
                row=roles_summary[(roles_summary['mode']==mode)&(roles_summary.target_region==region)&(roles_summary.role==role)]
                if len(row)!=1:raise AssertionError('Missing role summary')
                r=row.iloc[0];saved=[int(r.positive_case_rows),int(r.positive_groups),int(r.visible_outside_all_local_catalogs),int(r.finite_donor_estimate_outside_all_catalogs)]
                if observed!=saved:raise AssertionError('Role contribution mismatch')
                checked_roles+=1
        # Preselect samples by provider/network/station/year/mask only, not error or donor-visibility result.
        for provider,g in frame.groupby('provider',sort=True):
            selected=g.sort_values(['network_id','station_id','year','mask_runs'],kind='mergesort').head(12)
            panels={}
            for i,r in selected.iterrows():
                job=by_key[(str(r.network_id),str(r.station_id))];path=job['input_path']
                if path not in panels:
                    panel=read_temperature_panel(path).asfreq('D');panel.columns=panel.columns.astype(str);panels[path]=panel
                panel=panels[path];block=panel[panel.index.year==int(r.year)];mask=mask_runs(r.mask_runs,len(block))
                donors=block.drop(columns=str(r.station_id));available=donors.loc[mask].notna().mean().ge(.90)
                visible=available.index[available].astype(str);missing1=[];missingall=[]
                for name in visible:
                    key=str(r.network_id)+'\t'+str(provider)+'\t'+name
                    missing1.append(key not in station_keys)
                    missingall.append(key not in all_keys and not (provider=='usgs' and name in usgs))
                if int(available.sum())!=int(r.n_visible_donors) or bool(any(missing1))!=bool(flags.loc[i,'visible_outside_station_inventory']) or bool(any(missingall))!=bool(flags.loc[i,'visible_outside_all_local_catalogs']):
                    raise AssertionError('Independent sample donor visibility mismatch')
                total_cases+=1
    report={'status':'passed','sampled_case_visibility_recomputed':total_cases,'source_role_cells_recomputed':checked_roles,
            'provider_summary_cells_recomputed':checked_cells,'sample_rule':'First 12 cases per provider and mode sorted by network, station, year and mask; selected without performance or visibility outcomes.',
            'limits':'Separate mask parser, pandas donor coverage and independently reconstructed group-role bootstrap; uses the same processed panels, station catalogs, candidate cases and group definitions. Not a legal, quality, original-provider or independent-climate validation.'}
    (OUT/'donor_provenance_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
