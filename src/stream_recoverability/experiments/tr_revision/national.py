"""National source-panel utilities: native dates, approval and honest absence."""
from __future__ import annotations
import numpy as np
import pandas as pd
from stream_recoverability.data.ingest_qc import qc_long_frame,clean_long_frame
from stream_recoverability.experiments.v17_fitness.estimators import observed_days_metric


def native_daily_dates(values,zone):
    dates=[]
    for value in values:
        text=str(value)
        if len(text)==10:
            stamp=pd.Timestamp(text)
        else:
            stamp=pd.Timestamp(text)
            if stamp.tzinfo is not None:
                if not zone:raise ValueError("Timestamp needs verified site timezone")
                stamp=stamp.tz_convert(zone).tz_localize(None)
        dates.append(stamp.normalize())
    return pd.DatetimeIndex(dates)


def hydrologic_blocks(code):
    text=str(code).strip().removesuffix(".0")
    if not text.isdigit():return "unknown","nat_unknown","unknown"
    if len(text) in [7,11]:text=text.zfill(len(text)+1)
    if len(text)<8:return "unknown","nat_unknown","unknown"
    huc2,huc8=text[:2],text[:8]
    # Conservative major-basin blocks; they are not a proof of independent
    # weather/errors. Predictor donor panels stay within a smaller HUC8.
    major=("Mississippi" if huc2 in {"05","06","07","08","10","11"} else
           "Colorado" if huc2 in {"14","15"} else "HUC"+huc2)
    return huc2,"nat_"+major,"nat_huc8_"+huc8


def clean_native_features(row,features):
    """Return reported-day flags and approved values on the provider's dates.

    Do not treat a reported provisional/null/contradictory value as an absent
    observation. Source ingest QC is applied before annual aggregation.
    """
    if not features:
        return pd.DataFrame(columns=["date","water_c","reported","unapproved","ambiguous","estimated"]),{"site_id":row["station_id"],"verdict":"no_public_daily_records"}
    frame=pd.DataFrame(features)
    if not {"time","value","approval_status"}.issubset(frame):raise ValueError("Not a numeric daily-value payload")
    frame["date"]=native_daily_dates(frame.time,row.get("native_zone"))
    frame=frame.loc[frame.date.between("1980-01-01","2026-01-02")].copy()
    if frame.empty:
        return pd.DataFrame(columns=["date","water_c","reported","unapproved","ambiguous","estimated"]),{"site_id":row["station_id"],"verdict":"no_records_in_analysis_padding"}
    frame["site_id"]=str(row["station_id"])
    frame["value"]=pd.to_numeric(frame.value,errors="coerce")
    if "qualifier" not in frame:frame["qualifier"]=""
    frame["qualifier"]=frame.qualifier.map(lambda q:";".join(map(str,q)) if isinstance(q,list) else (str(q) if q is not None else ""))
    # Contradictory duplicates are unavailable, never resolved by row order or
    # averaging sensors. Mixed approval also remains explicitly flagged.
    report=qc_long_frame(frame)
    if not frame.date.duplicated().any():
        unique=frame.sort_values("date").reset_index(drop=True)
        unique["ambiguous"]=False
    else:
        output=[]
        for date,block in frame.groupby("date",sort=True):
            approved=block.approval_status.fillna("").astype(str).str.lower().eq("approved")
            values=block.value.dropna().unique()
            ambiguous=len(values)>1
            chosen=block.iloc[0].copy()
            chosen["value"]=np.nan if ambiguous else (values[0] if len(values) else np.nan)
            if not approved.all():chosen["approval_status"]="Provisional"
            chosen["qualifier"]=';'.join(sorted(set(block.qualifier)))
            chosen["ambiguous"]=ambiguous
            output.append(chosen)
        unique=pd.DataFrame(output).reset_index(drop=True)
    clean=clean_long_frame(unique,report=report,min_qualified_years=0)
    result=unique[["date","ambiguous"]].copy()
    result["reported"]=True
    result["unapproved"]=~unique.approval_status.astype(str).str.lower().eq("approved")
    result["estimated"]=unique.qualifier.str.contains(r"(?i)(?:estimated|(?:^|;)e(?:;|$))",regex=True)
    lookup=clean.set_index("date").temperature_c if len(clean) else pd.Series(dtype=float)
    result["water_c"]=result.date.map(lookup)
    return result,report.iloc[0].to_dict()


def window_lower_bound(values,window=30):
    x=np.asarray(values,float)
    if len(x)<window:return np.nan
    good=np.isfinite(x)
    count=np.convolve(good.astype(int),np.ones(window,int),mode="valid")
    total=np.convolve(np.where(good,x,0),np.ones(window),mode="valid")
    candidates=total[count==window]/window
    return float(candidates.max()) if len(candidates) else np.nan


def annual_source_panel(row,daily,start=1981,end=2025):
    if daily.empty:return pd.DataFrame()
    daily=daily.set_index("date").sort_index()
    begin,finish=daily.index.min(),daily.index.max()
    first=row.get("first_full_year");last=row.get("last_full_year")
    first=int(first) if pd.notna(first) else max(start,begin.year+int(begin>pd.Timestamp(begin.year,1,1)))
    last=int(last) if pd.notna(last) else min(end,finish.year-int(finish<pd.Timestamp(finish.year,12,31)))
    huc2,group,network=hydrologic_blocks(row.get("hydrologic_unit_code"))
    result=[]
    for year in range(max(start,first),min(end,last)+1):
        index=pd.date_range(f"{year}-01-01",f"{year}-12-31")
        block=daily.reindex(index)
        water=block.water_c.to_numpy(float)
        reported=block.reported.fillna(False).to_numpy(bool)
        unapproved=block.unapproved.fillna(False).to_numpy(bool)
        finite=np.isfinite(water)
        n=len(index);qc_year=not unapproved.any() and not block.ambiguous.fillna(False).any()
        complete=bool(finite.all() and qc_year)
        warm=index.month.isin([5,6,7,8,9])
        result.append({"station_id":str(row["station_id"]),"station_key":"usgs|"+str(row["station_id"]),
            "series_id":row["series_id"],"year":year,"huc2":huc2,"independence_group":group,"network_id":network,
            "n_days":n,"n_reported":int(reported.sum()),"n_absent":int((~reported).sum()),
            "n_unapproved":int(unapproved.sum()),"n_usable":int(finite.sum()),"n_estimated":int(block.estimated.fillna(False).sum()),
            "qc_year":qc_year,"complete":complete,"annual90":bool(qc_year and finite.mean()>=.9),
            "annual75":bool(qc_year and finite.mean()>=.75),"warm90":bool(qc_year and finite[warm].mean()>=.9),
            "observed_H30_lower_bound":window_lower_bound(water),
            "observed_H30":window_lower_bound(water) if complete else np.nan,
            "observed_days_H30":observed_days_metric(water),
            "latitude":row["latitude"],"longitude":row["longitude"]})
    return pd.DataFrame(result)
