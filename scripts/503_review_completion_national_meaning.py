#!/usr/bin/env python3
"""National-frame completeness comparisons and model-dependent H30 trends.

The national frame is all metadata-selected USGS sites, not all physical rivers.
Unretrieved candidates remain unknown and supply explicit eligibility bounds.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.national_inference import (
    project_lower_bound,slope_summary,mi_slopes,basin_bootstrap,
)
from stream_recoverability.experiments.tr_revision.statistics import lower_bound_trend
from stream_recoverability.experiments.tr_revision.national_coverage import spatial_coverage,hot_year_frequencies
from stream_recoverability.seeds import plain_seed

OUT=T.ROOT/"results/wrr_review_completion_20261024/national_meaning"


def main():
    p=argparse.ArgumentParser();p.add_argument("--application",type=Path,default=OUT/"application");p.add_argument("--partial",action="store_true");p.add_argument("--bootstrap",type=int,default=2000);a=p.parse_args()
    status=json.loads((a.application/"status.json").read_text())
    acquisition=json.loads((OUT/"acquisition.json").read_text())
    full=bool(acquisition.get("all_planned_attempted") and not status.get("partial"))
    if not full and not a.partial:raise RuntimeError("A partial input/application check is not a completed national analysis")
    dest=a.application/"meaning";dest.mkdir(parents=True,exist_ok=True)
    c=pd.read_parquet(a.application/"annual_panel.parquet")
    c["retained_H30_projected"]=c.observed_H30.where(c.complete,project_lower_bound(c.D2,c.observed_H30_lower_bound))
    c["retained_H30_individual"]=c.retained_H30.where(c.individual_release)
    c["retained_stochastic"]=c.observed_H30.where(c.complete,c.get("stochastic_cal_q50",pd.Series(np.nan,index=c.index)))
    c["retained_MOVE1"]=c.observed_H30.where(c.complete,c.h30__move1_warm)
    rules={"complete15":("complete","observed_H30"),"annual90_15":("annual90","observed_days_H30"),
           "annual75_15":("annual75","observed_days_H30"),"MaySep90_15":("warm90","observed_days_H30"),
           "retained_raw":(None,"retained_H30"),"retained_bound_projected":(None,"retained_H30_projected"),
           "retained_individual":(None,"retained_H30_individual"),"retained_stochastic":(None,"retained_stochastic"),
           "retained_MOVE1":(None,"retained_MOVE1")}
    slopes=[];year_values={};eligibility=[];mi=[]
    for number,(rule,(flag,column)) in enumerate(rules.items()):
        chosen=[]
        for station,b in c.groupby("station_id",sort=True):
            values=b[column].where(b[flag]) if flag else b[column]
            fit=slope_summary(b.year,values)
            eligibility.append({"station_id":station,"rule":rule,"n_rule_years":int(b[flag].sum()) if flag else int(values.notna().sum()),
                                "n_statistic_years":int(values.notna().sum()),"eligible":fit is not None})
            if fit is None:continue
            slopes.append({"station_id":station,"station_key":b.station_key.iloc[0],"rule":rule,"huc2":b.huc2.iloc[0],"independence_group":b.independence_group.iloc[0],**fit})
            chosen.append(pd.Series(values.to_numpy(),index=b.year.to_numpy(),name=station))
            if rule in ["retained_raw","retained_bound_projected","retained_stochastic"]:
                draws=mi_slopes(b,prefix="stochastic_cal" if rule=="retained_stochastic" else "D2",seed=plain_seed(503,number,int(station[-7:])),project=rule=="retained_bound_projected")
                mi.append({"station_id":station,"rule":rule,"n_draws":len(draws),"n_finite_draws":int(np.isfinite(draws).sum()),
                           "imputation_slope_lower":float(np.nanquantile(draws,.025)) if np.isfinite(draws).any() else np.nan,
                           "imputation_slope_upper":float(np.nanquantile(draws,.975)) if np.isfinite(draws).any() else np.nan,
                           "scope":"conditional model sensitivity, not a calibrated95percent confidence interval"})
        year_values[rule]=pd.concat(chosen,axis=1).sort_index() if chosen else pd.DataFrame()
    slopes=pd.DataFrame(slopes);eligibility=pd.DataFrame(eligibility)
    slopes.to_csv(dest/"station_trends.csv",index=False);eligibility.to_csv(dest/"processed_station_eligibility.csv",index=False)
    pd.DataFrame(mi).to_csv(dest/"imputation_sensitivity.csv",index=False)
    meaning=T.load_script("national_source_field_significance",T.ROOT/"scripts/471_review_completion_meaning.py")
    summaries=[];field=[]
    if len(slopes):
        for i,(rule,b) in enumerate(slopes.groupby("rule")):
            positive=b.slope.gt(0)&b.pvalue.lt(.05)
            bh=meaning.bh(b.pvalue.to_numpy())
            summaries.append({"rule":rule,"n_stations":len(b),"median_slope":float(b.slope.median()),"n_positive_p005":int(positive.sum()),"n_positive_BH":int((bh&b.slope.gt(0)).sum()),**basin_bootstrap(b,draws=a.bootstrap,seed=plain_seed(503,i))})
            matrix=year_values[rule]
            if len(matrix) and len(matrix.columns)>=2:
                group=b.set_index("station_id").independence_group.to_dict()
                test=meaning.field_test(matrix,group,draws=a.bootstrap,seed=plain_seed(503,i,1))
                field.append({"rule":rule,**test})
        for (rule,huc),b in slopes.groupby(["rule","huc2"]):
            summaries.append({"rule":rule,"huc2":huc,"n_stations":len(b),"median_slope":float(b.slope.median()),**basin_bootstrap(b,draws=a.bootstrap,seed=plain_seed(503,int(huc) if str(huc).isdigit() else 99))})
    pd.DataFrame(summaries).to_csv(dest/"network_and_regional_summary.csv",index=False)
    pd.DataFrame(field).to_csv(dest/"field_significance.csv",index=False)
    paired=[];records=[]
    complete_ids=set(slopes.loc[slopes.rule.eq("complete15"),"station_id"]) if len(slopes) else set()
    for station,b in c.groupby("station_id"):
        if station in complete_ids:
            exact=b.loc[b.complete]
            for rule,column in [("retained_raw","retained_H30"),("retained_bound_projected","retained_H30_projected"),("retained_stochastic","retained_stochastic")]:
                span=b.year.between(exact.year.min(),exact.year.max())
                old=slope_summary(exact.year,exact.observed_H30)
                new=slope_summary(b.loc[span,"year"],b.loc[span,column])
                if old and new:paired.append({"station_id":station,"rule":rule,"independence_group":b.independence_group.iloc[0],"complete_slope":old["slope"],"retained_same_span_slope":new["slope"],"difference":new["slope"]-old["slope"]})
            maximum=float(exact.observed_H30.max())
            certificates=b.loc[~b.complete&b.observed_H30_lower_bound.gt(maximum+5e-6)]
            daily=None
            if len(certificates):
                path=T.ROOT/"data/external/wrr_review_national_20261024/daily"/(station+".parquet")
                daily=pd.read_parquet(path).set_index("date").water_c
                for reference in exact.itertuples(index=False):
                    values=daily.reindex(pd.date_range(f"{reference.year}-01-01",f"{reference.year}-12-31"))
                    if not values.notna().all() or abs(values.rolling(30,min_periods=30).mean().max()-reference.observed_H30)>5e-6:
                        raise RuntimeError("Complete-year record reference differs from native QC values")
            for row in certificates.itertuples(index=False):
                values=daily.reindex(pd.date_range(f"{row.year}-01-01",f"{row.year}-12-31"))
                windows=values.rolling(30,min_periods=30).mean();end=windows.idxmax();start=end-pd.Timedelta(days=29)
                witness=values.loc[start:end]
                if len(witness)!=30 or not witness.notna().all() or abs(witness.mean()-row.observed_H30_lower_bound)>5e-6:
                    raise RuntimeError("Record witness is not thirty consecutive original qualified days")
                records.append({"station_id":station,"year":row.year,"n_complete_years":len(exact),"maximum_complete_H30":maximum,
                                "incomplete_observed_window_lower_bound":row.observed_H30_lower_bound,"minimum_excess":row.observed_H30_lower_bound-maximum,
                                "window_start":str(start.date()),"window_end":str(end.date()),"daily_values":';'.join(format(v,'.9g') for v in witness),
                                "scope":"reported-source series in1981--2025; no imputation, no unique hottest-year or measurement-error-free claim"})
    pd.DataFrame(paired).to_csv(dest/"same_roster_same_span_trends.csv",index=False)
    pd.DataFrame(records).to_csv(dest/"observed_record_certificates.csv",index=False)
    # No annual point is substituted for a censoring bound. This comparator
    # uses its own working likelihood and reports nonconvergence explicitly.
    censor=[]
    for station,b in c.groupby("station_id"):
        if b.complete.sum()<5 or b.observed_H30_lower_bound.notna().sum()<15:continue
        fit=lower_bound_trend(b.year,b.observed_H30,b.observed_H30_lower_bound)
        censor.append({"station_id":station,"independence_group":b.independence_group.iloc[0],**fit})
    pd.DataFrame(censor).to_csv(dest/"censored_trend_comparator.csv",index=False)
    full_roster=pd.read_csv(OUT/"national_roster.csv",dtype={"station_id":str,"hydrologic_unit_code":str})
    candidate=pd.read_csv(OUT/"candidate_roster.csv",dtype={"station_id":str})
    processed=set(c.station_id)
    unresolved=len(set(candidate.station_id)-processed)
    supplement=json.loads((T.ROOT/"configs/wrr_review_national_supplement_20261024.json").read_text())
    T.write_json(dest/"spatial_and_hot_year_specification.json",supplement)
    coverage,regional_coverage=spatial_coverage(eligibility,full_roster,set(candidate.station_id)-processed,supplement["geographic_grid_degrees"])
    coverage.to_csv(dest/"spatial_coverage.csv",index=False)
    regional_coverage.to_csv(dest/"spatial_coverage_by_huc2.csv",index=False)
    thresholds,events,event_summary,event_paired=hot_year_frequencies(c,year_values,supplement)
    thresholds.to_csv(dest/"hot_year_reference_thresholds.csv",index=False)
    events.to_csv(dest/"hot_year_frequency_station.csv",index=False)
    event_summary.to_csv(dest/"hot_year_frequency_network_region.csv",index=False)
    event_paired.to_csv(dest/"hot_year_frequency_same_roster_span.csv",index=False)
    counts={rule:int(eligibility.loc[eligibility.rule.eq(rule),"eligible"].sum()) for rule in rules}
    summary={"complete":full and unresolved==0,"execution_complete_on_retrieved_panel":full,"partial":not full or unresolved>0,"n_catalog_sites":len(full_roster),"n_metadata_candidates":len(candidate),"n_numeric_processed_sites":len(processed),
        "unresolved_or_no_annual_record_candidates":unresolved,"eligibility_lower_counts":counts,
        "eligibility_upper_counts_allowing_unresolved":{rule:n+unresolved for rule,n in counts.items()},
        "observed_record_stations":len({r['station_id'] for r in records}),"observed_record_station_years":len(records),
        "spatial_measure":"occupied1degree station cells andHUC2counts,notdrainagearea; unresolved eligibility givesexplicitupperbounds",
        "hot_year_reference":supplement,"n_stations_with_hot_year_reference":int(thresholds.reference_available.sum()),
        "scientific_scope":"descriptive retrieved-monitoring-network sensitivity on a metadata-fixed national USGS frame; not all US rivers, a blind transfer test or verified natural-gap trend accuracy",
        "intervals":"basin block bootstrap for network stability and separate conditional imputation sensitivity. Exchangeability, temporal and observation-quality assumptions remain unverified; no empirical coverage can be measured on real missing years.",
        "source_annual_weights_retrained":False,"new_NZ_temperature_values_requested":False}
    T.write_json(dest/"summary.json",summary)
    if full:T.write_json(OUT/"status.json",summary)
    print(json.dumps({"partial":summary["partial"],"execution_complete_on_retrieved_panel":full,
        "unresolved_historical_candidates":unresolved,"processed":len(processed),"counts":counts,
        "record_stations":summary["observed_record_stations"]}))
    return 0


if __name__=="__main__":raise SystemExit(main())
