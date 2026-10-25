"""Numerical and leakage checks for the fourth-review redesign."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
from stream_recoverability.experiments.tr_revision.baselines import move1, ar1_bridge
from stream_recoverability.experiments.tr_revision.statistics import ensemble_crps, interval_score, lower_bound_trend, removal_count, event_metrics, random_effects_ratio


def test_crps_matches_pairwise_definition_and_threshold_integral():
    x=np.array([[0.,1.,3.],[2.,4.,5.]])
    y=np.array([2.,1.])
    expected=np.abs(x-y[:,None]).mean(axis=1)-.5*np.abs(x[:,:,None]-x[:,None,:]).mean(axis=(1,2))
    np.testing.assert_allclose(ensemble_crps(x,y),expected)
    threshold=np.array([1.5,3.])
    np.testing.assert_allclose(ensemble_crps(x,y,threshold),ensemble_crps(np.maximum(x,threshold[:,None]),np.maximum(y,threshold)))
    assert ensemble_crps(np.array([[0.,1.]]),np.array([0.]),2.)[0]==0


def test_interval_score_penalizes_miss_in_correct_direction():
    np.testing.assert_allclose(interval_score([1,1,1],[3,3,3],[0,2,4]),[22,2,22])
    with pytest.raises(ValueError):
        interval_score(3,1,2)


def test_move1_preserves_training_mean_and_variance():
    rng=np.random.default_rng(31)
    x=rng.normal(size=500);y=2*x+rng.normal(size=500)
    z=move1(x,y,x)
    assert z.mean()==pytest.approx(y.mean())
    assert z.std(ddof=1)==pytest.approx(y.std(ddof=1))


def test_bridge_preserves_visible_values_and_conditions_on_boundaries():
    rng=np.random.default_rng(19)
    residual=np.zeros(20000)
    for i in range(1,len(residual)):
        residual[i]=.8*residual[i-1]+rng.normal(0,.6)
    observed=np.array([3.,np.nan,3.])
    draws=ar1_bridge(observed,np.zeros(3),residual,1,draws=10000)
    np.testing.assert_allclose(draws[:,[0,2]],3)
    # Conditional mean phi*(left+right)/(1+phi^2).
    assert draws[:,1].mean()==pytest.approx(.8*6/1.64,abs=.06)
    assert draws[:,1].std()<np.nanstd(residual)
    # A donor may be absent outside the gap even though visible target values
    # are available there. Such days must not reject an otherwise valid bridge.
    partial=ar1_bridge(observed,np.array([np.nan,0.,np.nan]),residual,1,draws=100)
    assert np.isfinite(partial).all()
    np.testing.assert_allclose(partial[:,[0,2]],3)


def test_lower_bounds_require_survival_likelihood():
    rng=np.random.default_rng(5)
    year=np.arange(1900,2100)
    y=12+.3*(year-2000)/10+rng.normal(0,.5,len(year))
    exact=y.copy();exact[y>np.median(y)]=np.nan
    # Fixed detection threshold is non-informative censoring; y-.1 would make
    # the bound itself outcome-dependent and would not identify this model.
    lower=np.where(np.isfinite(exact),np.nan,np.median(y))
    fit=lower_bound_trend(year,exact,lower)
    naive=np.polyfit((year[np.isfinite(exact)]-2000)/10,exact[np.isfinite(exact)],1)[0]
    assert fit["converged"]
    assert fit["slope"]>naive
    assert abs(fit["slope"]-.3)<.06
    assert not lower_bound_trend(year,np.full_like(y,np.nan),y)["converged"]


def test_exact_removal_count_agrees_with_exhaustive_subsets():
    from itertools import combinations
    a=np.array([1.,2.,8.,4.]);c=np.array([2.,1.,.1,3.])
    for reduction in [0,.2]:
        answer=None
        for k in range(len(a)):
            if any(sum(c[list(keep)])>(1-reduction)**2*sum(a[list(keep)]) for keep in combinations(range(len(a)),len(a)-k)):
                answer=k;break
        assert removal_count(a,c,reduction)==answer


def test_empty_events_are_undefined_and_re_meta_requires_three_units():
    metrics=event_metrics([False,False],[False,False])
    assert np.isnan(metrics["hit_rate"])
    assert np.isnan(metrics["sedi"])
    assert np.isnan(random_effects_ratio([1,2],[1,2])["upper"])


def test_group_roles_and_bootstrap_never_cross_outer_region():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("r4_refit_test",root/"scripts/466_review_completion_refit.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    frame=pd.DataFrame({"region":["held"]*5+["other"]*95,"independence_group":[f"g{i}" for i in range(100)]})
    # A target-connected group occurring outside the held region is also withheld.
    frame.loc[7,"independence_group"]="g0"
    held,roles,weights=module.roles(frame,"held",1)
    union=set()
    for groups in roles.values():
        assert not union.intersection(groups)
        assert not set(frame.loc[held,"independence_group"]).intersection(groups)
        union.update(groups)
    for w in weights.values():
        assert not w[held].any()
        assert w[7]==0


def test_cached_state_paths_are_identical_to_original_simulator():
    from stream_recoverability.experiments.tr_revision.simulation import prepare_states,prepared_draws
    from stream_recoverability.experiments.v19_revision.state_trajectory import state_conditioned_draws
    dates=pd.date_range("2000-01-01","2004-12-31")
    held=dates.year==2003
    rng=np.random.default_rng(8)
    residual=rng.normal(size=len(dates));residual[held]=np.nan
    state=rng.normal(size=(len(dates),1))
    center=np.sin(np.arange(365)/100)
    observed=center+rng.normal(size=365);observed[120:210]=np.nan
    prepared=prepare_states(dates[held],residual,dates,state)
    actual=prepared_draws(observed,center,prepared,seed=31,n_draws=20,target_states=state[held])
    expected=state_conditioned_draws(observed,center,dates[held],residual,dates,seed=31,n_draws=20,history_states=state,target_states=state[held])
    np.testing.assert_array_equal(actual,expected)


def test_fast_published_rules_match_original_month_and_run_semantics():
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/"scripts"))
    import wrr_tr_rules as old
    from stream_recoverability.experiments.tr_revision.screening import published_rules
    rng=np.random.default_rng(44);rows=[]
    for i in range(100):
        year=2000+i%4;n=366 if year==2000 else 365
        runs=[]
        for _ in range(3):
            start=int(rng.integers(n));length=int(rng.integers(1,70));runs.append(f"{start}:{min(length,n-start)}")
        mask=np.zeros(n,bool)
        for item in runs:
            s,l=map(int,item.split(":"));mask[s:s+l]=True
        starts=np.flatnonzero(mask&~np.r_[False,mask[:-1]]);ends=np.flatnonzero(mask&~np.r_[mask[1:],False])+1
        rows.append(dict(year=year,mask_runs=";".join(runs),peak_center_doy=int(rng.integers(160,240)),warm_months="5;6;7;8;9",longest_run=int((ends-starts).max())))
    frame=pd.DataFrame(rows);a=published_rules(frame);b=old.fixed_rules(old.mask_features(frame),frame,as_written=True)
    assert len(a)==len(b)
    for (name,left),(old_name,right) in zip(a.items(),b.items()):
        np.testing.assert_array_equal(left,right.to_numpy(),err_msg=f"{name} vs {old_name}")


def test_southern_shift_preserves_july_june_annual_boundaries_in_leap_years():
    # The translated annual grouping must never cut or duplicate a physical
    # hot-year day. Include century exceptions to the leap-year rule.
    for year in range(1899, 2101):
        start=pd.Timestamp(year,7,1)
        end=pd.Timestamp(year+1,6,30)
        assert start+pd.Timedelta(days=184)==pd.Timestamp(year+1,1,1)
        assert end+pd.Timedelta(days=184)==pd.Timestamp(year+1,12,31)
        assert (end-start).days+1==(pd.Timestamp(year+2,1,1)-pd.Timestamp(year+1,1,1)).days


def test_deep_reporting_keeps_unavailable_flow_out_of_failure_denominator(tmp_path):
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/"scripts"))
    from wrr_review_reporting import deep_tables
    folder=tmp_path/"deep/seed_00"
    folder.mkdir(parents=True)
    frame=pd.DataFrame({"network_id":["n"]*3,"station_key":["s"]*3,"year":[2000,2001,2002],
                        "design_family":["crossed"]*3,"realization_id":["m"]*3,
                        "policy_choice":["air_ridge"]*3,"peak_overlap":[.7]*3,
                        "h30_error":[.7,np.nan,.1]})
    frame.to_parquet(folder/"boosting_with_flow_cases.parquet")
    score,_=deep_tables(tmp_path)
    air=score.loc[score.scope.eq("air_danger")].iloc[0]
    assert air.n_eligible==3 and air.n_valid==2
    assert air.availability==pytest.approx(2/3)
    assert air.failure_rate==pytest.approx(.5)
    frame["h30_error"]=np.nan
    frame.to_parquet(folder/"boosting_with_flow_cases.parquet")
    score,_=deep_tables(tmp_path)
    assert score.failure_rate.isna().all()


def test_group_risk_deletions_match_exhaustive_subsets_and_strict_boundary():
    from itertools import combinations
    from stream_recoverability.experiments.tr_revision.robustness import minimum_risk_failure
    rng=np.random.default_rng(541)
    for _ in range(30):
        a=rng.integers(1,20,6);b=np.array([rng.integers(x+1) for x in a])
        exact=None
        for k in range(len(a)):
            for removed in combinations(range(len(a)),k):
                keep=np.ones(len(a),bool);keep[list(removed)]=False
                if b[keep].sum()*4>a[keep].sum():
                    exact=k;break
            if exact is not None:break
        assert minimum_risk_failure(a,b,.25)["minimum_groups"]==exact
    assert minimum_risk_failure([20,20],[1,0],.05)["minimum_groups"] is None
    assert minimum_risk_failure([20,20],[2,0],.05)["minimum_groups"]==1


def test_integer_group_retention_reversal_matches_exhaustive_risk_constrained_subsets():
    from itertools import combinations
    from stream_recoverability.experiments.tr_revision.robustness import minimum_retention_reversal
    rng=np.random.default_rng(274)
    for _ in range(20):
        ar=rng.integers(2,12,6);a=ar+rng.integers(-2,4,6)
        br=rng.binomial(ar,.1);b=rng.binomial(a,.1)
        if br.sum()*4>ar.sum():continue
        if a.sum()==0 or b.sum()*4>a.sum() or a.sum()<=ar.sum():
            exact=0
        else:
            exact=None
            for k in range(len(a)):
                for removed in combinations(range(len(a)),k):
                    keep=np.ones(len(a),bool);keep[list(removed)]=False
                    if ar[keep].sum()>0 and a[keep].sum()<=ar[keep].sum() and b[keep].sum()*4<=a[keep].sum() and br[keep].sum()*4<=ar[keep].sum():
                        exact=k;break
                if exact is not None:break
        actual=minimum_retention_reversal(a,b,ar,br,.25)
        assert actual["status"]!="optimality_unproven"
        assert actual["minimum_groups"]==exact


def test_wsr_bound_matches_known_betting_root_and_respects_corrected_support():
    from stream_recoverability.experiments.tr_revision.semisupervised import wsr_upper
    # At n=16 and all-zero observations, predictable bets hit their support
    # cap at every step, so the confidence-sequence crossing is analytic.
    expected=.05**(-1/16)-1
    assert wsr_upper(np.zeros(16))==pytest.approx(expected)
    assert wsr_upper(np.zeros(16),lower=-1,upper=2)==pytest.approx(3*expected)
    assert wsr_upper(np.ones(16))==1
    with pytest.raises(ValueError):wsr_upper([-1],lower=0,upper=1)


def test_ss_rcps_requires_distinct_unlabeled_units_and_stops_on_first_failed_test():
    from stream_recoverability.experiments.tr_revision.semisupervised import general_rcps,labeled_rcps
    candidates=[.01,.1]
    n=300
    loss=np.column_stack([np.zeros(n),np.ones(n)])
    result=general_rcps(loss,loss,loss.copy(),candidates)
    assert result["threshold"]==.01 and len(result["upper_bounds"])==2
    assert result["used_unlabeled_groups"]==n
    missing=general_rcps(loss,loss,loss[:-1],candidates)
    assert missing["status"]=="insufficient_distinct_unlabeled_groups"
    # Never search a later, apparently safe value after an earlier failure.
    result=labeled_rcps(loss[:,::-1],candidates)
    assert not np.isfinite(result["threshold"]) and len(result["upper_bounds"])==1


def test_conditional_conformal_requires_support_for_unseen_group_features():
    pytest.importorskip("conditionalconformal")
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("conditional_test",root/"scripts/488_review_completion_conditional_conformal.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    calibration=pd.DataFrame({"risk_score":np.linspace(.001,.24,24),"failure":np.zeros(24)})
    phi=np.column_stack([np.ones(24),np.zeros(24)])
    cut,status,_=m.conditional_cutoffs(calibration,phi,np.array([[1.,1.]]),.95)
    assert np.isinf(cut).all() and status[0]=="outside_calibration_span"


def test_conditional_conformal_intercept_recovers_finite_sample_rank_and_infinity():
    pytest.importorskip("conditionalconformal")
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("conditional_rank_test",root/"scripts/488_review_completion_conditional_conformal.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    calibration=pd.DataFrame({"risk_score":np.linspace(.001,.24,24),"failure":np.zeros(24)})
    cut,status,_=m.conditional_cutoffs(calibration,np.ones((24,1)),np.ones((1,1)),.95)
    assert cut[0]==pytest.approx(.24)
    cut,status,_=m.conditional_cutoffs(calibration.iloc[:12],np.ones((12,1)),np.ones((1,1)),.95)
    assert np.isinf(cut).all() and status[0]=="too_few_independent_groups_at_nominal_level"


def test_conditional_boundary_lp_matches_authors_code_with_overlapping_groups():
    pytest.importorskip("conditionalconformal")
    from conditionalconformal import CondConf
    from stream_recoverability.experiments.tr_revision.conditional import finite_basis_cutoff
    rng=np.random.default_rng(630)
    phi=np.column_stack([np.ones(100),rng.integers(0,2,(100,2))])
    scores=rng.normal(size=100);x=np.array([[1.,1.,1.]])
    c=CondConf(lambda x,y:y,lambda x:np.atleast_2d(x));c.setup_problem(phi,scores)
    for level in [.9,.95]:
        author=c.predict(level,x,lambda s,x:float(np.asarray(s).ravel()[0]))
        own,status=finite_basis_cutoff(phi,scores,x,level)
        assert status=="boundary_linear_program"
        assert own==pytest.approx(author,abs=1e-6)
    own,status=finite_basis_cutoff(np.ones((12,1)),np.arange(12),[1],.95)
    assert np.isinf(own) and status=="mathematically_unbounded"


def test_national_availability_preserves_native_dates_and_does_not_hide_provisional_observations():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("national_availability_test",root/"scripts/490_review_completion_national_availability.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    dates=m.native_dates(["2020-01-01","2020-01-01T05:00:00+00:00"],"America/New_York")
    assert list(dates)==[pd.Timestamp("2020-01-01")]*2
    row=dict(station_id="001",series_id="s",native_zone="America/New_York",first_full_year=2020,last_full_year=2020)
    features=[dict(time="2020-01-01",approval_status="Approved"),dict(time="2020-01-02",approval_status="Provisional"),dict(time="2020-01-03",approval_status="Approved")]
    result=m.calendar_counts(row,features)[0]
    assert result["n_days"]==366 and result["n_reported_dates"]==3
    assert result["n_actual_absent_dates"]==363 and result["n_unapproved_dates"]==1
    assert result["approved_observations_available"] is False


def test_observed_record_witness_requires_all_thirty_original_days():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("observed_record_test",root/"scripts/491_review_completion_observed_record_bounds.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    values=np.r_[np.nan,np.full(29,20.),0.]
    bound,start=m.observed_window(values)
    assert start==1 and bound==pytest.approx(29*20/30)
    # A partial-window mean of 20 would be an invalid annual lower bound if
    # the hidden day were cold; the complete window remains a valid witness.
    completed=values.copy();completed[0]=-100
    true_h30=np.lib.stride_tricks.sliding_window_view(completed,30).mean(axis=1).max()
    assert bound<=true_h30 and bound<np.nanmean(values[:30])


def test_randomized_conditional_boundary_matches_authors_dual_randomization():
    pytest.importorskip("conditionalconformal")
    from conditionalconformal import CondConf
    from types import SimpleNamespace
    from stream_recoverability.experiments.tr_revision.conditional import finite_basis_cutoff
    rng=np.random.default_rng(731);phi=np.column_stack([np.ones(80),rng.integers(0,2,80)])
    scores=rng.normal(size=80);x=np.array([[1.,1.]])
    for gamma in [-.02,.2,.7]:
        c=CondConf(lambda x,y:y,lambda x:np.atleast_2d(x));c.setup_problem(phi,scores)
        c.rng=SimpleNamespace(uniform=lambda **kwargs:gamma)
        author=c.predict(.95,x,lambda s,x:float(np.asarray(s).ravel()[0]),randomize=True)
        own,_=finite_basis_cutoff(phi,scores,x,.95,test_weight=gamma)
        assert own==pytest.approx(author,abs=1e-6)


def test_casewise_randomized_cutoff_cache_matches_individual_linear_programs():
    pytest.importorskip("conditionalconformal")
    from stream_recoverability.experiments.tr_revision.conditional import finite_basis_cutoff
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("randomized_batch_test",root/"scripts/488_review_completion_conditional_conformal.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rng=np.random.default_rng(745);phi=np.column_stack([np.ones(60),np.tile([0.,1.],30)])
    p=np.linspace(.01,.4,60);y=rng.random(60)<p
    calibration=pd.DataFrame({"risk_score":p,"failure":y})
    test=np.column_stack([np.ones(18),np.tile([0.,1.],9)])
    cut,status,gamma,_=m.randomized_cutoffs(calibration,phi,test,.9,124)
    assert len(np.unique(gamma))==len(test)
    for i in range(len(test)):
        single,_=finite_basis_cutoff(phi,np.abs(y-p),test[i],.9,test_weight=gamma[i])
        assert cut[i]>=single-1e-7
        assert cut[i]==pytest.approx(single,abs=1e-7)


def test_local_nonlinear_weather_fit_excludes_all_held_year_water():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("local_boosting_test",root/"scripts/493_review_completion_local_boosting.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    dates=pd.date_range("1999-01-01","2002-12-31");air=10+8*np.sin(2*np.pi*dates.dayofyear.to_numpy()/365.25)
    daily=pd.DataFrame({"air_c":air,"water_c":3+.7*air},index=dates)
    prediction,n=m.local_prediction(daily,2001,4)
    changed=daily.copy();changed.loc[changed.index.year==2001,"water_c"]+=100
    second,n2=m.local_prediction(changed,2001,4)
    assert n==n2 and np.isfinite(prediction).all()
    np.testing.assert_array_equal(prediction,second)


def test_osf_record_verification_does_not_rebuild_the_frozen_archive(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("registration_immutable_test",root/"scripts/472_review_completion_prereg.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.OUT=tmp_path;m.DOC=tmp_path/"docs"
    verified=[]
    monkeypatch.setattr(m,"verify_osf",lambda identifier:verified.append(identifier))
    monkeypatch.setattr(m,"prepare",lambda:(_ for _ in ()).throw(AssertionError("Must not repackage an uploaded archive")))
    monkeypatch.setattr(sys,"argv",["472_review_completion_prereg.py","--osf-registration","abc12"])
    assert m.main()==0 and verified==["abc12"]


def test_recorded_public_registration_preserves_existing_archive_bytes(tmp_path):
    import json
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("registration_guard_test",root/"scripts/472_review_completion_prereg.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.OUT=tmp_path;m.DOC=tmp_path/"docs"
    (tmp_path/"public_registration_status.json").write_text(json.dumps({"status":"public_record_found_requires_protocol_attachment_check"}))
    archive=tmp_path/"registration_code_and_protocol.tar.gz";archive.write_bytes(b"fixed uploaded bytes")
    with pytest.raises(RuntimeError,match="Preserve the existing"):
        m.prepare()
    assert archive.read_bytes()==b"fixed uploaded bytes"


def test_air_exposure_stress_changes_only_visible_warm_days_without_using_hidden_water():
    from stream_recoverability.experiments.tr_revision.simulation import visible_air_exposure
    observed=np.full(365,10.);observed[170:230]=np.nan
    air=20+10*np.sin(np.arange(365)*2*np.pi/365)
    warm=np.zeros(365,bool);warm[50:250]=True
    changed,exposed=visible_air_exposure(observed,air,warm,days=7,seed=4)
    assert exposed.sum()==7 and not exposed[170:230].any() and warm[exposed].all()
    np.testing.assert_allclose(changed[exposed],air[exposed])
    np.testing.assert_allclose(changed[~exposed],observed[~exposed],equal_nan=True)
    empty,flag=visible_air_exposure(np.full(20,np.nan),np.ones(20),np.ones(20,bool))
    assert np.isnan(empty).all() and not flag.any()


def test_omitting_invalid_censoring_under_exposure_preserves_other_random_streams():
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/"scripts"))
    spec=importlib.util.spec_from_file_location("exposure_trend_stream_test",root/"scripts/467_review_completion_analysis.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    years=np.arange(2000,2020);truth=10+.02*(years-2000)+np.sin(years)
    c=pd.DataFrame({"station_key":"test|1","year":years,"eval_truth_h30":truth,
                    "air_warm_z_mean":np.cos(years),"independence_group":"group1","region":"test",
                    "warm_observed_fraction":.8,"h30__observed_days":truth-.2,
                    "h30__policy":truth-.1,"D2":truth,"observed_lower_bound__observed_days":truth-.3})
    c["stochastic_h30_draws"]=[np.linspace(y-.5,y+.5,20) for y in truth]
    for prefix in ["D2","stochastic_cal"]:
        for level in m.LEVELS:c[f"{prefix}_q{int(100*level):02d}"]=truth+(level-.5)
    original=pd.DataFrame(m.station_trends(c,0,2,scenarios=["mcar"]))
    selected=pd.DataFrame(m.station_trends(c,0,2,scenarios=["mcar"],include_censored=False))
    pd.testing.assert_frame_equal(original.loc[original.pipeline.ne("censored_trend")].reset_index(drop=True),selected)
