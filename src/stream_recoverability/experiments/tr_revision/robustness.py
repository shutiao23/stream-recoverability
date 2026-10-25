"""Exact independent-group deletion checks for frozen admissions.

These are finite-archive sensitivity analyses, not refits after deleting data.
Integer counts preserve equality at a stated rational risk cap.
"""
from __future__ import annotations

from fractions import Fraction
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


def _counts(admitted, failed):
    a, b = np.asarray(admitted), np.asarray(failed)
    if a.ndim != 1 or b.shape != a.shape or not len(a):
        raise ValueError("Require aligned nonempty one-dimensional group counts")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Counts must be finite")
    if not np.equal(a, np.round(a)).all() or not np.equal(b, np.round(b)).all() or (b<0).any() or (a<b).any():
        raise ValueError("Require integer counts with 0 <= failed <= admitted")
    return a.astype(np.int64), b.astype(np.int64)


def minimum_risk_failure(admitted, failed, cap=.05):
    """Minimum groups removed until a nonempty frozen selection exceeds cap.

    Sorting the group contributions b_g-cap*a_g is exact for this additive
    ratio crossing. Empty selections fail the nonempty endpoint separately.
    """
    a, b = _counts(admitted, failed)
    q = Fraction(str(cap))
    if not 0 < q < 1:
        raise ValueError("Risk cap must lie strictly between zero and one")
    delta = q.denominator*b-q.numerator*a
    if a.sum()==0:
        return dict(status="already_empty", minimum_groups=0, removed=[])
    if delta.sum()>0:
        return dict(status="already_above_cap", minimum_groups=0, removed=[])
    order = np.argsort(delta, kind="stable")
    remaining = delta.sum()-np.cumsum(delta[order])
    valid = np.flatnonzero(remaining[:-1]>0)
    if not len(valid):
        return dict(status="no_nonempty_subset_exceeds_cap", minimum_groups=None, removed=[])
    k = int(valid[0]+1)
    removed = order[:k]
    keep = np.ones(len(a), bool); keep[removed] = False
    assert a[keep].sum()>0 and q.denominator*b[keep].sum()>q.numerator*a[keep].sum()
    return dict(status="exact", minimum_groups=k, removed=removed.tolist())


def minimum_retention_reversal(admitted, failed, reference_admitted, reference_failed, cap=.05):
    """Fewest group deletions removing a strict retention advantage.

    Both remaining selections must satisfy the same point-risk cap, and the
    reference must be nonempty. Cases share a denominator, so retention order
    is the order of admitted counts. Admissions and reference choice are fixed.
    The integer program supplies an optimality certificate or reports unknown.
    """
    a, b = _counts(admitted, failed)
    ar, br = _counts(reference_admitted, reference_failed)
    if ar.shape != a.shape:
        raise ValueError("Reference groups must align with learned-rule groups")
    q = Fraction(str(cap))
    if not 0<q<1:
        raise ValueError("Risk cap must lie strictly between zero and one")
    d, dl, dr = a-ar, q.denominator*b-q.numerator*a, q.denominator*br-q.numerator*ar
    if ar.sum()==0 or dr.sum()>0:
        raise ValueError("Full-data reference must be nonempty and satisfy the cap")
    if a.sum()==0 or dl.sum()>0 or d.sum()<=0:
        return dict(status="no_initial_qualified_advantage", minimum_groups=0, removed=[])
    # x_g=1 deletes group g. Convert each remaining-count condition to a
    # linear constraint on x; all coefficients and non-strict bounds are exact
    # integer counts. The reference nonempty constraint excludes empty success.
    matrix = np.vstack([d, dl, dr, ar]).astype(float)
    lower = np.array([d.sum(), dl.sum(), dr.sum(), -np.inf], float)
    upper = np.array([np.inf, np.inf, np.inf, ar.sum()-1], float)
    solution = milp(np.ones(len(a)), integrality=np.ones(len(a)), bounds=Bounds(0,1),
                    constraints=LinearConstraint(matrix, lower, upper),
                    options={"mip_rel_gap":0., "time_limit":30.})
    if solution.status==2:
        return dict(status="no_qualifying_reference_subset_reverses", minimum_groups=None, removed=[])
    if solution.status!=0:
        return dict(status="optimality_unproven", minimum_groups=None, removed=[], solver_status=int(solution.status))
    removed = np.flatnonzero(solution.x>.5)
    keep = np.ones(len(a), bool); keep[removed] = False
    assert ar[keep].sum()>0 and d[keep].sum()<=0 and dl[keep].sum()<=0 and dr[keep].sum()<=0
    assert int(np.round(solution.fun))==len(removed)
    return dict(status="exact", minimum_groups=len(removed), removed=removed.tolist())
