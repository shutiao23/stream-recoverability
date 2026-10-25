"""Unregularized finite-basis conformal cutoff via the boundary linear program.

The boundary dual fixes the test weight u (tau in the conservative version).
Its calibration primal is the pinball loss tilted by -u*Phi_test*beta. The smallest target prediction
among optimal tilted fits is the conservative unrandomized cutoff. This is
equivalent to the finite-dimensional sensitivity calculation in Gibbs et al.
"""
from __future__ import annotations
import numpy as np
from scipy.optimize import linprog


def finite_basis_cutoff(phi,scores,test_phi,quantile,test_weight=None):
    phi=np.asarray(phi,float);s=np.asarray(scores,float).ravel();x=np.asarray(test_phi,float).ravel()
    n,d=phi.shape
    weight=quantile if test_weight is None else float(test_weight)
    if len(s)!=n or len(x)!=d or not 0<quantile<1 or not np.isfinite(phi).all() or not np.isfinite(s).all():
        raise ValueError("Finite, aligned calibration scores and basis required")
    identity=np.eye(n);eq=np.column_stack([phi,identity,-identity])
    if not quantile-1<=weight<=quantile:raise ValueError("Test dual weight must lie in the quantile dual interval")
    objective=np.r_[-weight*x,np.full(n,quantile),np.full(n,1-quantile)]
    bounds=[(None,None)]*d+[(0,None)]*(2*n)
    result=linprog(objective,A_eq=eq,b_eq=s,bounds=bounds,method="highs")
    if result.status==3:return (np.inf if weight>=0 else -np.inf),"mathematically_unbounded"
    if result.status!=0:raise ValueError(f"Tilted calibration LP failed: {result.message}")
    target=np.r_[x,np.zeros(2*n)]
    # The lower endpoint of an optimal face handles exact quantile-rank ties.
    tie=linprog(target,A_eq=np.vstack([eq,objective]),b_eq=np.r_[s,result.fun],bounds=bounds,method="highs")
    if tie.status!=0:raise ValueError(f"Conformal boundary LP failed: {tie.message}")
    return float(tie.fun),"boundary_linear_program"
