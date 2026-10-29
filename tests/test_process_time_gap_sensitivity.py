"""Scientific invariants for exact year-subset and date-overlap diagnostics."""
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_process_experiments_20261029'
SPEC=importlib.util.spec_from_file_location('time_gap_969',ROOT/'scripts/969_time_gap_sensitivity.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def test_fixed_complete_years_change_the_strong_spacing_selection():
    candidates=[2001,2005,2010]
    selections=[]
    for complete in [2000,2011]:
        full=np.array(sorted([complete,*candidates]))
        options=[dict(chosen_incomplete=(year,),**M.year_geometry(np.array(sorted([complete,year])),full))
                 for year in candidates]
        _,index=M.select_geometry(options)
        selections.append(candidates[index])
    assert selections==[2010,2001]


def test_selection_criteria_cannot_read_temperature_or_error_fields():
    full=np.array([2000,2001,2003,2010,2012])
    options=[dict(chosen_incomplete=(year,),**M.year_geometry(np.array([2000,year]),full),estimate_error=float(i))
             for i,year in enumerate([2001,2003,2010,2012])]
    original=M.select_geometry(options)
    for i,row in enumerate(options):
        row['estimate_error']=1e9*(-1)**i
        row['hidden_reference_h30']=-1e6*i
    assert M.select_geometry(options)==original


def test_subset_scores_match_independent_regression_and_keep_the_cross_term():
    years=np.array([2000,2003,2008,2012,2015]);truth=np.array([4.,6.,7.,11.,10.])
    predicted=truth+np.array([0.,.5,-.7,0.,1.2]);selected=np.array([2000,2003,2008,2015])
    row=M.score_set(years,truth,predicted,selected);keep=np.isin(years,selected)
    target=np.polyfit(years,truth,1)[0]*10
    estimate=np.polyfit(years[keep],predicted[keep],1)[0]*10
    selected_truth=np.polyfit(years[keep],truth[keep],1)[0]*10
    np.testing.assert_allclose([row['estimate_error'],row['year_set_error'],row['reconstruction_error']],
                               [estimate-target,selected_truth-target,estimate-selected_truth],atol=1e-11)
    assert np.isclose(row['estimate_mse'],row['year_set_mse']+row['reconstruction_mse']+row['cross_term'])


def test_mask_runs_are_zero_based_and_join_adjacent_spans():
    mask=M.parse_mask('0:2;2:3;364:1',365)
    assert M.runs(mask)==[(0,5),(364,1)]
    assert mask[0] and mask[-1] and not mask[5]


def test_enumeration_is_normalized_per_archive_before_rmse():
    subsets=pd.read_parquet(OUT/'time_all_feasible_subsets.parquet')
    exact=pd.read_parquet(OUT/'time_exact_random_expectations.parquet').set_index(M.KEY)
    assert len(subsets)==5758 and len(exact)==807
    groups=subsets.groupby(M.KEY)
    np.testing.assert_allclose(groups.uniform_subset_probability.sum(),1.)
    for field in ['estimate_mse','year_set_mse','reconstruction_mse','cross_term']:
        np.testing.assert_allclose(groups[field].mean().sort_index(),exact[field].sort_index(),atol=1e-12)
    # Rows from archives with many feasible sets cannot gain more cohort weight.
    archive=pd.read_parquet(OUT/'time_archive_accounting.parquet').set_index(M.KEY)
    for key,part in groups:
        info=archive.loc[key]
        complete={int(year) for year in info.complete_years.split(';') if year}
        assert len(part)==math.comb(int(info.n_incomplete),int(info.k))
        for row in part.itertuples(index=False):
            kept={int(year) for year in row.retained_years.split(';')}
            assert complete.issubset(kept)
            assert len(kept)==int(info.n_complete+info.k)
    expected_rmse=np.sqrt(exact.loc[archive.index[archive.primary],'estimate_mse'].mean())
    summary=pd.read_csv(OUT/'time_sensitivity_summary.csv')
    saved=summary.loc[summary.scope.eq('actual_mask_common')&summary.weighting.eq('equal_archive')
                      &summary.scheme.eq('uniform_random_expected'),'estimate_rmse'].iloc[0]
    assert saved==expected_rmse


def test_all_real_geometry_selections_achieve_their_declared_objective():
    subsets=pd.read_parquet(OUT/'time_all_feasible_subsets.parquet')
    for _,part in subsets.groupby(M.KEY):
        cdf=part.loc[part.cdf_all_years_selected].iloc[0]
        spread=part.loc[part.sxx_all_years_selected].iloc[0]
        assert cdf.cdf_distance<=part.cdf_distance.min()+1e-13
        assert spread.sxx>=part.sxx.max()-1e-13


def test_two_hundred_random_draws_preserve_every_archive_and_subset_identity():
    draws=pd.read_parquet(OUT/'time_random_selection_draws.parquet')
    subsets=pd.read_parquet(OUT/'time_all_feasible_subsets.parquet')
    assert len(draws)==807*200
    assert draws.groupby(M.KEY).draw_seed.nunique().eq(200).all()
    joined=draws.merge(subsets[M.KEY+['subset_id','estimate_mse']],on=M.KEY+['subset_id'],validate='many_to_one')
    np.testing.assert_array_equal(joined.estimate_mse_x,joined.estimate_mse_y)
    a=np.random.default_rng(M.stable_seed('station|one',2,4)).integers(100,size=10)
    b=np.random.default_rng(M.stable_seed('station|one',2,4)).integers(100,size=10)
    np.testing.assert_array_equal(a,b)


def test_same_day_missingness_excludes_group_years_without_evaluable_peers():
    cases=pd.read_csv(OUT/'gap_overlap_station_year_cases.csv')
    summary=pd.read_csv(OUT/'gap_overlap_summary.csv')
    assert (~cases.peer_evaluable).any()
    for row in summary.itertuples(index=False):
        part=cases.loc[cases.source.eq(row.source)&cases.year.between(int(row.period[:4]),2025)]
        peer=part.loc[part.peer_evaluable]
        assert len(part)==row.n_incomplete_rows
        assert len(peer)==row.n_peer_evaluable_incomplete_rows
        assert row.n_no_evaluable_peer_excluded==int((~part.peer_evaluable).sum())
        assert row.shared_missing_station_days==int(peer.same_day_missing_peer_days.sum())
        assert row.peer_evaluable_missing_station_days==int(peer.missing_days.sum())
        assert row.same_day_overlap_fraction_peer_evaluable<=row.shared_year_fraction_peer_evaluable
