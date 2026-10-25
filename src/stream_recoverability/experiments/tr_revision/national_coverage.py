"""Geographical footprints and common-reference hot-year descriptions."""
from __future__ import annotations
import numpy as np
import pandas as pd


def coordinate_cells(frame,degrees=1.):
    if degrees<=0:raise ValueError("Positive geographic cell size required")
    lat=pd.to_numeric(frame.latitude,errors="coerce");lon=pd.to_numeric(frame.longitude,errors="coerce")
    valid=lat.between(-90,90)&lon.between(-180,180)
    cells=pd.Series(None,index=frame.index,dtype=object)
    for i in frame.index[valid]:
        north=min(float(lat.loc[i]),np.nextafter(90.,-np.inf))
        east=(float(lon.loc[i])+180)%360
        cells.loc[i]=(int(np.floor((north+90)/degrees)),int(np.floor(east/degrees)))
    return cells


def spatial_coverage(eligibility,metadata,unresolved_ids,degrees=1.):
    if metadata.station_id.duplicated().any():raise ValueError("Nonunique physical station metadata")
    m=metadata.copy();m["cell"]=coordinate_cells(m,degrees)
    m["huc2"]=m.hydrologic_unit_code.astype(str).str.extract(r"^(\d{2})",expand=False)
    m=m.set_index("station_id");unknown=m.loc[m.index.intersection(list(unresolved_ids))]
    rows=[];regional=[]
    total_cells=int(np.ceil(180/degrees)*np.ceil(360/degrees))
    for rule,b in eligibility.groupby("rule"):
        ids=b.loc[b.eligible,"station_id"].drop_duplicates()
        if not ids.isin(m.index).all():raise ValueError("Eligible station has no catalog identity")
        selected=m.loc[ids];known=set(selected.cell.dropna());missing=int(selected.cell.isna().sum())
        potential=set(unknown.cell.dropna());missing_unknown=int(unknown.cell.isna().sum())
        rows.append({"rule":rule,"n_eligible_stations":len(selected),"n_with_coordinates":len(selected)-missing,
            "n_without_coordinates":missing,"occupied_cells_lower":len(known),
            "occupied_cells_upper_allowing_unresolved":min(total_cells,len(known|potential)+missing+missing_unknown),
            "n_huc2_with_eligible_stations":int(selected.huc2.nunique()),"n_unresolved_candidates":len(unknown),"grid_degrees":degrees,
            "scope":"geographical station-grid occupancy; not watershed area or population representativeness"})
        for huc,region in selected.groupby("huc2",dropna=False):
            regional.append({"rule":rule,"huc2":huc,"n_stations":len(region),"occupied_cells":region.cell.nunique()})
    return pd.DataFrame(rows),pd.DataFrame(regional)


def hot_year_reference(panel,spec):
    rows=[];first,last=spec["hot_year_reference_years"]
    for station,b in panel.groupby("station_id"):
        ref=b.loc[b.complete&b.year.between(first,last),"observed_H30"].dropna()
        enough=len(ref)>=spec["hot_year_minimum_complete_reference_years"]
        rows.append({"station_id":station,"n_complete_reference_years":len(ref),"reference_first_year":first,"reference_last_year":last,
            "threshold":float(ref.quantile(spec["hot_year_reference_quantile"])) if enough else np.nan,
            "reference_available":enough,"quantile":spec["hot_year_reference_quantile"]})
    return pd.DataFrame(rows)


def hot_year_frequencies(panel,year_values,spec):
    if panel.duplicated(["station_id","year"]).any():raise ValueError("Duplicated station-year in national panel")
    reference=hot_year_reference(panel,spec);threshold=reference.set_index("station_id").threshold
    by_station={station:b.set_index("year") for station,b in panel.groupby("station_id")}
    rows=[]
    for rule,matrix in year_values.items():
        for station in matrix:
            b=by_station[station];cut=threshold.loc[station]
            for period,(first,last) in spec["hot_year_periods"].items():
                values=matrix.loc[(matrix.index>=first)&(matrix.index<=last),station].dropna()
                incomplete=~b.reindex(values.index).complete.fillna(False)
                hot=values.gt(cut) if np.isfinite(cut) else pd.Series(False,index=values.index)
                support=b.loc[b.index.to_series().between(first,last)]
                witness=support.observed_H30_lower_bound.gt(cut)
                rows.append({"station_id":station,"rule":rule,"period":period,"huc2":b.huc2.iloc[0],
                    "independence_group":b.independence_group.iloc[0],"reference_available":bool(np.isfinite(cut)),"threshold":cut,
                    "n_statistic_years":len(values),"n_incomplete_statistic_years":int(incomplete.sum()),
                    "n_hot":int(hot.sum()) if np.isfinite(cut) else np.nan,
                    "frequency":float(hot.mean()) if len(values) and np.isfinite(cut) else np.nan,
                    "n_hot_incomplete":int((hot&incomplete).sum()) if np.isfinite(cut) else np.nan,
                    "n_supported_years":len(support),
                    "n_observed_window_hot_all_supported_years":int(witness.sum()) if np.isfinite(cut) else np.nan,
                    "observed_window_frequency_lower_bound":float(witness.sum()/len(support)) if len(support) and np.isfinite(cut) else np.nan})
    detail=pd.DataFrame(rows);summaries=[]
    if len(detail):
        for (rule,period),b in detail.groupby(["rule","period"]):
            for region,s in [("all",b)]+[(str(h),v) for h,v in b.groupby("huc2")]:
                supported=s.loc[s.reference_available&s.n_statistic_years.gt(0)]
                observed=s.loc[s.reference_available]
                n=int(supported.n_statistic_years.sum())
                summaries.append({"rule":rule,"period":period,"huc2":region,"n_eligible_stations":len(s),"n_with_reference_and_values":len(supported),
                    "n_statistic_years":n,"n_incomplete_statistic_years":int(supported.n_incomplete_statistic_years.sum()),
                    "n_hot":int(supported.n_hot.sum()),"pooled_frequency":float(supported.n_hot.sum()/n) if n else np.nan,
                    "n_supported_years":int(observed.n_supported_years.sum()),
                    "observed_window_frequency_lower_bound":float(observed.n_observed_window_hot_all_supported_years.sum()/observed.n_supported_years.sum()) if observed.n_supported_years.sum() else np.nan,
                    "station_equal_frequency":float(supported.frequency.mean()),"scope":spec["hot_year_interpretation"]})
    paired=[]
    complete=year_values.get("complete15",pd.DataFrame());retained=year_values.get("retained_raw",pd.DataFrame())
    for station in sorted(set(complete)&set(retained)):
        cut=threshold.loc[station];old=complete[station].dropna()
        if not len(old) or not np.isfinite(cut):continue
        new=retained[station].loc[old.index.min():old.index.max()].dropna();common=old.index.intersection(new.index)
        paired.append({"station_id":station,"huc2":by_station[station].huc2.iloc[0],"threshold":cut,
            "first_year":int(old.index.min()),"last_year":int(old.index.max()),"n_complete_years":len(old),"n_retained_same_span_years":len(new),
            "complete_frequency":float(old.gt(cut).mean()),"retained_same_span_frequency":float(new.gt(cut).mean()),
            "frequency_difference":float(new.gt(cut).mean()-old.gt(cut).mean()),
            "common_year_frequency_difference":float(new.loc[common].gt(cut).mean()-old.loc[common].gt(cut).mean()) if len(common) else np.nan})
    return reference,detail,pd.DataFrame(summaries),pd.DataFrame(paired)
