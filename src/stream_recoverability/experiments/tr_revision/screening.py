"""Vectorized published rules, preserving station-anchored calendar semantics."""
from __future__ import annotations
import numpy as np
import pandas as pd


def published_rules(c,chunk_size=4000):
    names=["complete_year","USGS_311_24","USGS_strict7","WMO_11_5","ETCCDI_15_3","GSIM_350","gap14","gap49","Oregon80","NorWest90","Beaufort_full","Dunham_full","warm_gap7","warm_gap14","warm_gap30"]
    names += ["Oregon80_as_written","NorWest90_as_written","Beaufort_full_as_written","Dunham_full_as_written"]
    result={name:np.zeros(len(c),bool) for name in names}
    month=np.zeros((2,366),int);month[0,:365]=pd.date_range("2001-01-01","2001-12-31").month;month[1]=pd.date_range("2000-01-01","2000-12-31").month
    boundaries=np.array([[0,31,59,90,120,151,181,212,243,273,304,334,365],[0,31,60,91,121,152,182,213,244,274,305,335,366]])
    for first in range(0,len(c),chunk_size):
        block=c.iloc[first:first+chunk_size];n=len(block);year=block.year.to_numpy(int)
        leap=((year%4==0)&((year%100!=0)|(year%400==0))).astype(int);days=365+leap
        mask=np.zeros((n,366),bool)
        for i,runs in enumerate(block.mask_runs):
            for item in str(runs).split(";"):
                if item:
                    start,length=map(int,item.split(":"));mask[i,start:start+length]=True
        cum=np.column_stack([np.zeros(n,dtype=np.int16),np.cumsum(mask,axis=1,dtype=np.int16)])
        idx=np.arange(n)[:,None];ends=boundaries[leap,1:];starts=boundaries[leap,:-1]
        missing_month=cum[idx,ends]-cum[idx,starts];observed_month=ends-starts-missing_month
        total=mask.sum(axis=1);observed=days-total
        same_month=month[leap,:-4]==month[leap,4:]
        five=mask[:,:-4]&mask[:,1:-3]&mask[:,2:-2]&mask[:,3:-1]&mask[:,4:]
        month_run5=(five&same_month).any(axis=1)
        seven=(cum[:,7:]-cum[:,:-7]).max(axis=1)
        warm_flags=np.array([sum(1<<int(m) for m in str(s).split(";") if m) for s in block.warm_months])
        warm=((1<<month[leap])&warm_flags[:,None])>0
        warm_mask=mask&warm
        position=np.arange(1,367)[None,:]
        last_clear=np.maximum.accumulate(np.where(~warm_mask,position,0),axis=1)
        warm_gap=(position-last_clear).max(axis=1)
        def peak_fraction(start,end,anchored=True):
            shift=block.peak_center_doy.to_numpy(int)-211 if anchored else np.zeros(n,int)
            lo=np.clip(start+shift-1,0,days);hi=np.clip(end+shift,0,days)
            missing=cum[np.arange(n),hi]-cum[np.arange(n),lo]
            return np.divide(hi-lo-missing,hi-lo,out=np.full(n,np.nan),where=hi>lo)
        values={"complete_year":total==0,"USGS_311_24":(observed>=311)&(observed_month.min(axis=1)>=24),"USGS_strict7":(observed>=311)&(observed_month.min(axis=1)>=26)&(seven<=1),"WMO_11_5":(missing_month.max(axis=1)<11)&~month_run5,"ETCCDI_15_3":(total<=15)&(missing_month.max(axis=1)<=3),"GSIM_350":observed>=350,"gap14":block.longest_run.to_numpy()<=14,"gap49":block.longest_run.to_numpy()<=49,"Oregon80":peak_fraction(182,273)>=.8,"NorWest90":peak_fraction(213,243)>=.9,"Beaufort_full":peak_fraction(182,243)>=1,"Dunham_full":peak_fraction(196,258)>=1,"warm_gap7":warm_gap<=7,"warm_gap14":warm_gap<=14,"warm_gap30":warm_gap<=30}
        values.update(Oregon80_as_written=peak_fraction(182,273,False)>=.8,NorWest90_as_written=peak_fraction(213,243,False)>=.9,Beaufort_full_as_written=peak_fraction(182,243,False)>=1,Dunham_full_as_written=peak_fraction(196,258,False)>=1)
        for name in names:
            result[name][first:first+n]=values[name]
    return result
