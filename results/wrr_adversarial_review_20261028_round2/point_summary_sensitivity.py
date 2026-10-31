"""Post-hoc review of median versus mean for squared-error slope evaluation.

Uses the already assumed bounded normal-spacing quantile representation.
This is not refitting, a new forecast method, or independent validation.
"""
from pathlib import Path
import io,json,zipfile
import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'results/wrr_review_response_20261027/whole_archive'
level=np.array([.05,.1,.25,.5,.75,.9,.95])
u=(np.arange(4096)+.5)/4096
z=norm.ppf(u); zq=norm.ppf(level)
low=u<.05;high=u>.95
def mean_quantile(q,bound):
    v=np.interp(u,level,q)
    v[low]=q[0]+(q[1]-q[0])/(zq[1]-zq[0])*(z[low]-zq[0])
    v[high]=q[-1]+(q[-1]-q[-2])/(zq[-1]-zq[-2])*(z[high]-zq[-1])
    if np.isfinite(bound):v=np.maximum(v,bound)
    return v.mean()
ref=pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',columns=['station_key','year','design_family','eval_truth_h30'])
ref=ref.loc[ref.design_family.eq('crossed')&ref.year.ge(2010)].drop_duplicates(['station_key','year'])
truth={s:g.set_index('year').eval_truth_h30.sort_index() for s,g in ref.groupby('station_key')}
trends=pd.read_csv(BASE/'trends.csv')
t=trends.loc[trends.family.eq('crossed')&trends['mode'].eq('forward')&trends.retention.eq('all')&trends.dependence.eq('point')&trends.available]
a=t.loc[t.estimator.eq('D2')].set_index(['station_key','replicate'])
b=t.loc[t.estimator.eq('stochastic_calibrated')].set_index(['station_key','replicate'])
common=a.index.intersection(b.index)
rows=[]
for station,replicate in common:
    r=truth[station];years=r.index.to_numpy();x=(years-years.mean())/10;weights=x/(x@x)
    folder=BASE/'crossed/forward'/f'replicate_{replicate:02d}'/station.replace('|','_')
    d=json.loads((folder/'design.json').read_text());masked=[int(y) for y in d['masks']]
    columns=['year','observed_lower_bound__observed_days']+[f'{method}_q{int(p*100):02d}' for method in ['D2','stochastic_cal'] for p in level]
    c=pd.read_parquet(folder/'annual_predictions.parquet',columns=columns) if masked else pd.DataFrame()
    for method,saved in [('D2',a),('stochastic_cal',b)]:
        ymedian=r.copy();ymean=r.copy()
        for row in c.itertuples(index=False):
            q=np.array([getattr(row,f'{method}_q{int(p*100):02d}') for p in level])
            assert np.isfinite(q).all()
            ymedian.loc[row.year]=q[3]
            ymean.loc[row.year]=mean_quantile(q,row.observed_lower_bound__observed_days)
        median_error=float(weights@(ymedian.to_numpy()-r.to_numpy()))
        mean_error=float(weights@(ymean.to_numpy()-r.to_numpy()))
        assert abs(median_error-saved.loc[(station,replicate),'error'])<1e-10
        rows.append({'station_key':station,'replicate':int(replicate),'method':method,'region':a.loc[(station,replicate),'region'],
            'independence_group':a.loc[(station,replicate),'independence_group'],'median_error':median_error,'mean_error':mean_error})
out=pd.DataFrame(rows)
out.to_csv(OUT/'point_summary_cases.csv',index=False)
summary=[]
for method,g in out.groupby('method'):
    summary.append({'method':method,'n':len(g),'median_rmse':float(np.sqrt(np.mean(g.median_error**2))),
                    'mean_rmse':float(np.sqrt(np.mean(g.mean_error**2))),
                    'median_bias':float(g.median_error.mean()),'mean_bias':float(g.mean_error.mean())})
s=pd.DataFrame(summary);s.to_csv(OUT/'point_summary_summary.csv',index=False)
with zipfile.ZipFile(OUT/'reviewed_candidate.zip') as archive:
    frozen=pd.read_csv(io.BytesIO(archive.read('results/wrr_review_response_20261027/whole_archive/paired_trend_estimators.csv')))
frozen=frozen.loc[frozen.family.eq('crossed')&frozen['mode'].eq('forward')&frozen.left.eq('D2')&frozen.right.eq('stochastic_calibrated')].iloc[0]
assert int(frozen.n_common)==len(common)==738
assert abs(s.loc[s.method.eq('D2'),'median_rmse'].iloc[0]-frozen.left_rmse)<1e-12
assert abs(s.loc[s.method.eq('stochastic_cal'),'median_rmse'].iloc[0]-frozen.right_rmse)<1e-12
print(s.to_string(index=False))
(OUT/'point_summary_status.json').write_text(json.dumps({'status':'computed_posthoc','cases_per_method':len(common),'frozen_original_point_scores_reproduced':True,
    'interpretation':'Conditional on the existing approximate quantile interpolation, normal-spacing tails and support projection. No new model training or external validation. Annual median is the original delivered point; mean is a review sensitivity for squared slope loss.'},indent=2)+'\n')
