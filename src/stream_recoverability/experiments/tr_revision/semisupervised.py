"""General-loss semi-supervised RCPS with finite-sample betting bounds.

Implements Algorithms 1 and 4 of Einbinder, Ringel and Romano,
arXiv:2412.11174v2. Observations here are independent groups, not masks.
"""
from __future__ import annotations
import numpy as np
from scipy.optimize import brentq


def wsr_upper(values, delta=.05, lower=0., upper=1.):
    """Waudby-Smith--Ramdas UCB, paper Algorithm 4, on bounded losses.

    The returned risk is restricted to [0,1], the known range of the expected
    original loss, even when corrected observations lie in [-1,2].
    """
    w=np.asarray(values,float)
    if w.ndim!=1 or not len(w) or not np.isfinite(w).all():
        raise ValueError("Require finite nonempty independent observations")
    if not 0<delta<1 or not lower<upper or (w<lower-1e-12).any() or (w>upper+1e-12).any():
        raise ValueError("Invalid error budget or observations outside their bounds")
    n=len(w);nu=np.empty(n);variance=.25;total=0.;squared=0.
    for i,value in enumerate(w,1):
        nu[i-1]=min(1/(upper-lower),np.sqrt(2*np.log(1/delta)/(n*max(variance,1e-15))))
        total+=value
        mean=(.5+total)/(1+i)
        squared+=(value-mean)**2
        variance=(.25+squared)/(1+i)
    def crossing(risk):
        with np.errstate(divide="ignore",invalid="raise"):
            log_wealth=np.cumsum(np.log1p(nu*(risk-w)))
        return max(float(np.max(log_wealth)),-1e300)-np.log(1/delta)
    if crossing(0)>=0:return 0.
    if crossing(1)<=0:return 1.
    return float(brentq(crossing,0.,1.,xtol=1e-12))


def general_rcps(loss_labeled, pseudo_labeled, pseudo_unlabeled, candidates, *, alpha=.05, delta=.05):
    """Paper Algorithm 1 with distinct equally sized unlabeled blocks.

    Columns follow a fixed, prespecified testing sequence. Stop at the first
    failed test; searching later candidates would invalidate fixed-sequence
    error control. Unlabeled leftovers are discarded by index, not by value.
    """
    loss,pl,pu=map(lambda x:np.asarray(x,float),(loss_labeled,pseudo_labeled,pseudo_unlabeled))
    candidates=np.asarray(candidates,float)
    if loss.ndim!=2 or pl.shape!=loss.shape or pu.ndim!=2 or pu.shape[1]!=loss.shape[1] or len(candidates)!=loss.shape[1]:
        raise ValueError("Aligned group-by-candidate matrices required")
    if not len(loss) or not np.isfinite(loss).all() or not np.isfinite(pl).all() or not np.isfinite(pu).all():
        raise ValueError("Finite nonempty group observations required")
    if any(((x<0)|(x>1)).any() for x in [loss,pl,pu]):
        raise ValueError("Original and pseudo losses must lie in [0,1]")
    n=len(loss);m=len(pu)//n
    if m<1:
        return dict(status="insufficient_distinct_unlabeled_groups",threshold=-np.inf,used_unlabeled_groups=0,upper_bounds=[])
    corrected=pu[:n*m].reshape(n,m,len(candidates)).mean(axis=1)+loss-pl
    bounds=[];threshold=-np.inf
    for j,candidate in enumerate(candidates):
        bound=wsr_upper(corrected[:,j],delta,lower=-1.,upper=2.)
        bounds.append(bound)
        if bound>=alpha:break
        threshold=float(candidate)
    return dict(status="certified_under_iid_group_assumption" if np.isfinite(threshold) else "insufficient_calibration_evidence",
                threshold=threshold,used_unlabeled_groups=n*m,upper_bounds=bounds)


def labeled_rcps(loss_labeled, candidates, *, alpha=.05,delta=.05):
    loss=np.asarray(loss_labeled,float);bounds=[];threshold=-np.inf
    if loss.ndim!=2 or len(candidates)!=loss.shape[1]:
        raise ValueError("Aligned group-by-candidate matrix required")
    for j,candidate in enumerate(candidates):
        bound=wsr_upper(loss[:,j],delta)
        bounds.append(bound)
        if bound>=alpha:break
        threshold=float(candidate)
    return dict(status="certified_under_iid_group_assumption" if np.isfinite(threshold) else "insufficient_calibration_evidence",threshold=threshold,used_unlabeled_groups=0,upper_bounds=bounds)
