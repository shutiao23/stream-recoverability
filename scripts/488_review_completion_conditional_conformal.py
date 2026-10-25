#!/usr/bin/env python3
"""Authors' finite-basis conditional conformal comparator, with group units.

The prediction set concerns whether the frozen D2 value fails. Releasing only
the singleton {no failure} controls false-admission frequency under the paper's
exchangeability assumptions, not risk conditional on being admitted.
"""
from __future__ import annotations
import os
for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[variable]="1"
import argparse
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
from joblib import Parallel,delayed
from conditionalconformal import CondConf
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.tr_revision.conditional import finite_basis_cutoff

warnings.filterwarnings("ignore",category=FutureWarning,module="cvxpy")
CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text());OUT=T.ROOT/CONFIG["out"]


def river_groups():
    path=OUT/"failure_map/station_failures_and_metadata.csv"
    d=pd.read_csv(path,usecols=["group","MAJ_NDAMS_2009","zero_flow_days_in_available_record"])
    result={}
    for group,b in d.groupby("group"):
        dam=pd.to_numeric(b.MAJ_NDAMS_2009,errors="coerce");zero=pd.to_numeric(b.zero_flow_days_in_available_record,errors="coerce")
        result[group]=(1 if dam.gt(0).any() else 0 if dam.notna().any() else 2,
                       1 if zero.gt(0).any() else 0 if zero.notna().any() else 2)
    return result


def basis(frame,river):
    names=["intercept"];columns=[np.ones(len(frame))]
    categories={"macro_region":np.where(frame.region.str.startswith("usgs"),0,1),
                "tier":np.select([frame.policy_choice.eq("donor_ridge"),frame.policy_choice.eq("air_ridge")],[0,1],default=2),
                "peak_overlap":np.where(frame.peak_overlap.le(0),0,np.searchsorted([0,.25,.5,.75,1],frame.peak_overlap,side="left")),
                "historical_heat":np.searchsorted([15.,20.,25.],frame.train_h30_mean.to_numpy(),side="right"),
                "dam_group_proxy":np.array([river.get(g,(2,2))[0] for g in frame.independence_group]),
                "zero_flow_group_proxy":np.array([river.get(g,(2,2))[1] for g in frame.independence_group])}
    for name,size in [("macro_region",2),("tier",3),("peak_overlap",5),("historical_heat",4),("dam_group_proxy",3),("zero_flow_group_proxy",3)]:
        for value in range(size):
            names.append(f"{name}={value}");columns.append((categories[name]==value).astype(float))
    return np.column_stack(columns),names


def supported_span(calibration_phi,test_phi):
    _,s,vt=np.linalg.svd(calibration_phi,full_matrices=False)
    rank=int((s>1e-10).sum());row_basis=vt[:rank]
    residual=test_phi-test_phi@row_basis.T@row_basis
    return np.linalg.norm(residual,axis=1)<1e-8


def conditional_cutoffs(calibration,phi_cal,test_phi,quantile):
    """Cache the full conformal residual cutoff for each categorical basis.

    The augmented optimization depends on x only through Phi(x); the continuous
    failure score is restored after the residual cutoff is calculated.
    """
    patterns,inverse=np.unique(test_phi,axis=0,return_inverse=True)
    supported=supported_span(phi_cal,patterns)
    cut=np.full(len(patterns),np.inf);status=np.full(len(patterns),"outside_calibration_span",dtype=object)
    if len(calibration)<np.ceil(quantile/(1-quantile)-1e-9):
        status[: ]="too_few_independent_groups_at_nominal_level"
        return cut[inverse],status[inverse],len(patterns)
    # Every active binary group indicator needs at least tau/(1-tau)
    # representatives. Otherwise the boundary dual is infeasible, so the full
    # prediction set is mathematical conservatism, not a numerical failure.
    counts=phi_cal.sum(axis=0)
    enough=np.all((patterns==0)|(counts[None,:]+1e-9>=quantile/(1-quantile)),axis=1)
    status[supported&~enough]="insufficient_independent_group_membership_support"
    xcal=np.column_stack([calibration.risk_score.to_numpy(),phi_cal])
    c=CondConf(score_fn=lambda x,y:np.abs(np.asarray(y)-np.asarray(x)[:,0]),Phi_fn=lambda x:np.atleast_2d(x)[:,1:])
    c.setup_problem(xcal,calibration.failure.to_numpy(float))
    for i,pattern in enumerate(patterns):
        if not supported[i] or not enough[i]:continue
        try:
            x=np.r_[0.,pattern][None,:]
            value=c.predict(quantile,x,lambda s,x:float(np.asarray(s).ravel()[0]),S_min=0.,S_max=1.,randomize=False,exact=True)
            if np.isnan(value):raise ValueError("NaN conditional cutoff")
            cut[i]=value;status[i]="authors_exact_finite_basis" if np.isfinite(value) else "uninformative_full_set"
        except (ValueError,IndexError,np.linalg.LinAlgError,AttributeError) as error:
            try:
                cut[i],status[i]=finite_basis_cutoff(phi_cal,c.scores_calib,pattern,quantile)
            except ValueError:
                # A full binary set is a conservative computational fallback.
                status[i]="full_set_after_solver_failure:"+type(error).__name__
    return cut[inverse],status[inverse],len(patterns)


def randomized_cutoffs(calibration,phi_cal,test_phi,quantile,seed):
    """Casewise independent uniform dual thresholds, as in the authors' rule.

    The cutoff is nondecreasing in the test dual weight. Endpoint equality
    allows exact interval caching; a 1e-8 upper-end tolerance only enlarges a
    set. It never replaces casewise randomization with one shared group coin.
    """
    rng=np.random.default_rng(seed);gamma=rng.uniform(quantile-1,quantile,len(test_phi))
    patterns,inverse=np.unique(test_phi,axis=0,return_inverse=True);supported=supported_span(phi_cal,patterns)
    cuts=np.full(len(test_phi),np.inf);status=np.full(len(test_phi),"",dtype=object);n_lp=0
    scores=np.abs(calibration.failure.to_numpy(float)-calibration.risk_score.to_numpy())
    counts=phi_cal.sum(axis=0)
    for pi,pattern in enumerate(patterns):
        indices=np.flatnonzero(inverse==pi)
        if not supported[pi]:
            cuts[indices]=np.where(gamma[indices]>=0,np.inf,-np.inf);status[indices]="randomized_unidentified_basis"
            continue
        order=indices[np.argsort(gamma[indices],kind="stable")];cache={}
        maximum_positive=(1-quantile)*float(counts[pattern>0].min())
        def at(position):
            nonlocal n_lp
            if position not in cache:
                weight=gamma[order[position]]
                if weight>maximum_positive+1e-12:
                    cache[position]=(np.inf,"randomized_insufficient_membership_support")
                else:
                    try:
                        n_lp+=1;cache[position]=finite_basis_cutoff(phi_cal,scores,pattern,quantile,test_weight=weight)
                    except ValueError:
                        cache[position]=(np.inf,"full_set_after_solver_failure:boundary_LP")
            return cache[position]
        def fill(lo,hi):
            a,sa=at(lo);b,sb=at(hi)
            if lo==hi:
                cuts[order[lo]]=a;status[order[lo]]=sa;return
            failed=sa.startswith("full_set_after_solver_failure") or sb.startswith("full_set_after_solver_failure")
            equal=(a==b) or (np.isfinite(a+b) and 0<=b-a<=1e-8)
            if equal and not failed:
                cuts[order[lo:hi+1]]=b;status[order[lo:hi+1]]=sb;return
            mid=(lo+hi)//2;fill(lo,mid);fill(mid+1,hi)
        fill(0,len(order)-1)
    return cuts,status,gamma,n_lp


def analyse(seed):
    river=river_groups();rows=[];subgroups=[];cases=[]
    folder=OUT/f"refits/leave_one_year_out/seed_{seed:02d}"
    for ri,path in enumerate(sorted(folder.glob("*.parquet"))):
        target=pd.read_parquet(path,columns=["network_id","station_key","year","realization_id","mask_runs","independence_group","region","design_family","policy_choice","peak_overlap","train_h30_mean","risk_score","D2","eval_truth_h30"])
        source=pd.read_parquet(folder/"calibration"/path.name)
        for fi,family in enumerate(["calendar","crossed"]):
            b=target.loc[target.design_family.eq(family)].reset_index(drop=True)
            cal=source.loc[source.design_family.eq(family)].copy()
            if b.empty or cal.empty:continue
            rng=np.random.default_rng(plain_seed(88,seed,ri,fi))
            # One uniformly selected case per independent calibration group;
            # bootstrap copies and thousands of dependent masks are not units.
            selected=[int(rng.choice(np.asarray(index))) for _,index in cal.groupby("independence_group").groups.items()]
            cal=cal.loc[selected].iloc[rng.permutation(len(selected))].reset_index(drop=True)
            assert not set(cal.independence_group).intersection(b.independence_group)
            phi_cal,names=basis(cal,river);phi,names2=basis(b,river);assert names==names2
            failure=(b.D2-b.eval_truth_h30).abs().gt(.5).to_numpy()
            group_sizes=b.groupby("independence_group").size();weight=1/b.independence_group.map(group_sizes).to_numpy(float);weight/=weight.sum()
            for level in [.9,.95]:
                cutoff,status,n_patterns=conditional_cutoffs(cal,phi_cal,phi,level)
                probability=b.risk_score.to_numpy()
                good=probability<=cutoff+1e-8;bad=1-probability<=cutoff+1e-8
                admit=good&~bad;covered=np.where(failure,bad,good)
                random_cutoff,random_status,gamma,n_lp=randomized_cutoffs(cal,phi_cal,phi,level,plain_seed(880,seed,ri,fi,int(level*100)))
                rgood=probability<=random_cutoff+1e-8;rbad=1-probability<=random_cutoff+1e-8
                random_admit=rgood&~rbad;random_covered=np.where(failure,rbad,rgood)
                # An unseen region indicator permits only the trivial full or
                # empty set in the randomized finite-basis construction.
                full_region_covered=gamma>=0
                for mode,a,cov,set_size,local_cutoff,local_status in [("coarse_overlapping_groups",admit,covered,good.astype(int)+bad.astype(int),cutoff,status),
                                           ("coarse_overlapping_groups_randomized",random_admit,random_covered,rgood.astype(int)+rbad.astype(int),random_cutoff,random_status),
                                           ("held_region_group_required",np.zeros(len(b),bool),np.ones(len(b),bool),np.full(len(b),2),None,None),
                                           ("held_region_group_randomized",np.zeros(len(b),bool),full_region_covered,2*full_region_covered,None,None)]:
                    aw=float(weight[a].sum());bw=float(weight[a&failure].sum())
                    rows.append(dict(seed=seed,region=path.stem,family=family,method=mode,nominal_coverage=level,n_calibration_groups=len(cal),
                                     n_basis_features=phi.shape[1],n_categorical_patterns=n_patterns,n_test_cases=len(b),n_test_groups=b.independence_group.nunique(),
                                     n_admitted=int(a.sum()),retention_case_weighted=float(a.mean()),risk_case_weighted=float(failure[a].mean()) if a.any() else np.nan,
                                     retention_group_equal=aw,selected_risk_group_equal=bw/aw if aw else np.nan,false_admission_frequency_group_equal=bw,
                                     coverage_group_equal=float(weight@cov),set_size_group_equal=float(weight@set_size),
                                     finite_cutoff_fraction=float(np.isfinite(local_cutoff).mean()) if local_cutoff is not None else 0.,
                                     solver_fallback_fraction=float(np.char.startswith(local_status.astype(str),"full_set_after_solver_failure").mean()) if local_status is not None else 0.,randomized_boundary_lp_calls=n_lp if mode.endswith("groups_randomized") else 0))
                    for j,name in enumerate(names):
                        subset=phi[:,j]>0;mass=weight[subset].sum();selected_mass=weight[subset&a].sum()
                        if not mass:continue
                        subgroups.append(dict(seed=seed,region=path.stem,family=family,method=mode,nominal_coverage=level,subgroup=name,
                                              coverage_group_equal=float(weight[subset]@cov[subset]/mass),
                                              false_admission_frequency=float(weight[subset&a&failure].sum()/mass),
                                              selected_risk=float(weight[subset&a&failure].sum()/selected_mass) if selected_mass else np.nan,
                                              retention=float(selected_mass/mass)))
                delivered=b[["network_id","station_key","year","realization_id","design_family","policy_choice","mask_runs","independence_group"]].copy()
                delivered["nominal_coverage"]=level;delivered["admitted"]=admit;delivered["conformal_cutoff"]=cutoff;delivered["status"]=status
                delivered["randomized_admitted"]=random_admit;delivered["randomized_cutoff"]=random_cutoff;delivered["randomized_status"]=random_status
                cases.append(delivered)
    dest=OUT/f"conditional_conformal/seed_{seed:02d}";dest.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(dest/"rules.csv",index=False);pd.DataFrame(subgroups).to_csv(dest/"subgroup_coverage.csv",index=False)
    pd.concat(cases,ignore_index=True).to_parquet(dest/"cases.parquet",index=False)
    print(f"authors' conditional conformal seed {seed}: {len(rows)} rule rows",flush=True)
    return seed


def main():
    p=argparse.ArgumentParser();p.add_argument("--seeds",type=int,nargs="+",default=CONFIG["seeds"]);p.add_argument("--workers",type=int,default=8);a=p.parse_args()
    Parallel(n_jobs=a.workers,verbose=10)(delayed(analyse)(seed) for seed in a.seeds)
    d=pd.concat([pd.read_csv(OUT/f"conditional_conformal/seed_{seed:02d}/rules.csv") for seed in a.seeds],ignore_index=True)
    d.to_csv(OUT/"conditional_conformal/rules_all_seeds.csv",index=False)
    source=Path(inspect.getfile(CondConf))
    T.write_json(OUT/"conditional_conformal/design.json",{"source":"Gibbs, Cherian, Candes JRSSB 2025; authors' conditionalconformal exact finite-dimensional implementation","implementation_version":"group-units-v4-binary-LAC","package_version":importlib.metadata.version("conditionalconformal"),"package_core_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"seeds":a.seeds,"sampling":"one uniform case per unique source rule-calibration group; held group never in calibration","basis":"overlapping macro-region, information tier, peak-overlap, historical-heat, dam and zero-flow group proxies; no hidden target labels","score":"binary LAC abs(failure-risk_score), not a one-sided regression residual","randomization":"independent uniform dual weight per case; exact tilted boundary LP; monotone endpoint caching with conservative <=1e-8 numerical enlargement","full_region_basis":"held region absent from source calibration; full/empty randomized set, or conservative full set; no singleton release","guarantee_target":"conditional prediction-set coverage, hence false-admission frequency per eligible case; NOT failure probability conditional on release","assumptions":"exchangeable independent group representatives; arbitrary regional shift not covered","support_test":"nonrandomized active binary membership needs tau/(1-tau) representatives; randomized dual-weight bounds handled separately","solver_fallback":"equivalent tilted finite-basis boundary LP; mathematical unboundedness distinguished from numerical failure","unsupported_or_solver_failure":"full {no failure, failure} set on numerical failure; explicit status and no release"})
    return 0


if __name__=="__main__":raise SystemExit(main())
