"""Local Ridge residual histories excluding both target and validation years.

Sufficient statistics avoid refitting the same unordered year pair repeatedly.
The intercept is unpenalized, matching sklearn Ridge(alpha=1).
"""
from __future__ import annotations
import numpy as np


class YearExcludedRidge:
    def __init__(self,x,y,years,alpha=1.,min_rows=120):
        self.x=np.asarray(x,float);self.y=np.asarray(y,float);self.years=np.asarray(years,int)
        if self.x.ndim!=2 or len(self.x)!=len(self.y) or len(self.y)!=len(self.years):raise ValueError("Inconsistent daily model arrays")
        self.alpha=float(alpha);self.min_rows=int(min_rows)
        self.valid=np.isfinite(self.x).all(axis=1)&np.isfinite(self.y)
        self.total=self._statistics(self.valid)
        self.by_year={year:self._statistics(self.valid&(self.years==year)) for year in np.unique(self.years)}
        self.cache={}

    def _statistics(self,mask):
        x=self.x[mask];y=self.y[mask]
        return (int(mask.sum()),x.sum(axis=0),float(y.sum()),x.T@x,x.T@y)

    def coefficients(self,excluded):
        key=tuple(sorted(set(int(v) for v in excluded)))
        if key in self.cache:return self.cache[key]
        n,sx,sy,xx,xy=[v.copy() if isinstance(v,np.ndarray) else v for v in self.total]
        for year in key:
            if year not in self.by_year:continue
            a,b,c,d,e=self.by_year[year];n-=a;sx-=b;sy-=c;xx-=d;xy-=e
        if n<self.min_rows:self.cache[key]=None;return None
        centered=xx-np.outer(sx,sx)/n
        centered=(centered+centered.T)/2+self.alpha*np.eye(self.x.shape[1])
        slope=np.linalg.solve(centered,xy-sx*sy/n)
        result=(float(sy/n-sx@slope/n),slope)
        self.cache[key]=result
        return result

    def predict(self,positions,excluded):
        positions=np.asarray(positions,bool);x=self.x[positions]
        out=np.full(len(x),np.nan);fit=self.coefficients(excluded)
        if fit is not None:
            good=np.isfinite(x).all(axis=1)
            out[good]=fit[0]+x[good]@fit[1]
        return out

    def residual_history(self,target_year,validation_years):
        residual=np.full(len(self.y),np.nan)
        for year in validation_years:
            if int(year)==int(target_year):continue
            positions=self.years==int(year)
            residual[positions]=self.y[positions]-self.predict(positions,[target_year,year])
        return residual
