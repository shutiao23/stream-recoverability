import numpy as np
import pandas as pd
from stream_recoverability.experiments.tr_revision.national_coverage import spatial_coverage,hot_year_frequencies


def test_grid_occupancy_distinguishes_station_count_and_unknown_eligibility():
    metadata=pd.DataFrame({"station_id":["a","b","c"],"latitude":[40.1,40.2,41.1],"longitude":[-100.1,-100.2,-101.1],"hydrologic_unit_code":["010100","010100","020100"]})
    eligibility=pd.DataFrame({"station_id":["a","b"],"rule":["retained","retained"],"eligible":[True,True]})
    coverage,regions=spatial_coverage(eligibility,metadata,{"c"})
    assert coverage.n_eligible_stations.iloc[0]==2
    assert coverage.occupied_cells_lower.iloc[0]==1 and coverage.occupied_cells_upper_allowing_unresolved.iloc[0]==2
    assert regions.huc2.iloc[0]=="01"


def test_unknown_coordinates_do_not_become_a_zero_degree_station():
    metadata=pd.DataFrame({"station_id":["a","b"],"latitude":[40.,np.nan],"longitude":[-100.,np.nan],"hydrologic_unit_code":["010100","020100"]})
    eligible=pd.DataFrame({"station_id":["a","b"],"rule":["retained"]*2,"eligible":[True,True]})
    coverage,_=spatial_coverage(eligible,metadata,set())
    assert coverage.occupied_cells_lower.iloc[0]==1 and coverage.n_without_coordinates.iloc[0]==1
    assert coverage.occupied_cells_upper_allowing_unresolved.iloc[0]==2


def fixture():
    years=[2000,2001,2002,2003,2004,2005,2018,2019]
    panel=pd.DataFrame({"station_id":["a"]*8,"year":years,"complete":[True]*7+[False],
        "observed_H30":[1.,2.,3.,4.,5.,6.,100.,np.nan],"observed_H30_lower_bound":[1.,2.,3.,4.,5.,6.,100.,8.],
        "huc2":["01"]*8,"independence_group":["g1"]*8})
    complete=pd.DataFrame({"a":[1.,2.,3.,4.,5.,6.,100.,np.nan]},index=years)
    retained=complete.copy();retained.loc[2019,"a"]=999.
    spec={"hot_year_reference_years":[1981,2010],"hot_year_reference_quantile":.9,"hot_year_minimum_complete_reference_years":5,
        "hot_year_periods":{"all":[1981,2025]},"hot_year_interpretation":"descriptive, not missing-truth validation"}
    return panel,{"complete15":complete,"retained_raw":retained},spec


def test_all_methods_share_a_reference_without_future_or_imputed_values():
    panel,values,spec=fixture();reference,detail,_,paired=hot_year_frequencies(panel,values,spec)
    assert reference.threshold.iloc[0]==5.5 and detail.threshold.nunique()==1
    complete=detail.loc[detail.rule.eq("complete15")].iloc[0]
    retained=detail.loc[detail.rule.eq("retained_raw")].iloc[0]
    assert complete.n_hot==2 and retained.n_hot==3
    assert retained.n_hot_incomplete==1
    assert retained.observed_window_frequency_lower_bound==3/8
    assert complete.observed_window_frequency_lower_bound==3/8
    assert paired.common_year_frequency_difference.iloc[0]==0


def test_insufficient_reference_is_unavailable_not_zero_hot_frequency():
    panel,values,spec=fixture();spec["hot_year_minimum_complete_reference_years"]=10
    reference,detail,summary,paired=hot_year_frequencies(panel,values,spec)
    assert not reference.reference_available.any()
    assert detail.frequency.isna().all() and detail.n_hot.isna().all()
    assert summary.pooled_frequency.isna().all() and paired.empty


def test_observed_hot_bound_survives_method_abstention():
    panel,values,spec=fixture();values["retained_raw"]["a"]=np.nan
    _,_,summary,_=hot_year_frequencies(panel,values,spec)
    retained=summary.loc[summary.rule.eq("retained_raw")&summary.huc2.eq("all")].iloc[0]
    assert np.isnan(retained.pooled_frequency)
    assert retained.observed_window_frequency_lower_bound==3/8
