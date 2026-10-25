"""Fixed-clock native Hilltop parsing and strict observed-day aggregation.

Functions are transport-free and tested on synthetic observations. An XML
record is not accessed by the new-cohort workflow until its public gate passes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd

NZST=timezone(timedelta(hours=12))


def native_series(content: bytes, *, site: str, series_type: str) -> pd.Series:
    root=ET.fromstring(content)
    measurements=root.findall("Measurement")
    if len(measurements)!=1 or measurements[0].get("SiteName")!=site:
        raise ValueError("Expected exactly the requested site's measurement")
    measurement=measurements[0]
    source=measurement.find("DataSource")
    if source is None or source.findtext("TSType")!=series_type:
        raise ValueError("Unexpected native series type")
    if series_type=="StdSeries":
        units=source.findtext("ItemInfo/Units")
        if units not in {"°C","C","degC"}:
            raise ValueError("Native temperature units are not degrees Celsius")
    data=measurement.find("Data")
    if data is None or int(data.get("NumItems","1"))!=1:
        raise ValueError("Expected one native measurement item")
    dates,values=[],[]
    for event in data.findall("E"):
        stamp=event.findtext("T")
        if not stamp:raise ValueError("Native observation has no time")
        instant=datetime.fromisoformat(stamp.replace("Z","+00:00"))
        if instant.tzinfo is None:instant=instant.replace(tzinfo=NZST)
        dates.append(instant.astimezone(NZST))
        try:value=float(event.findtext("I1"))
        except (TypeError,ValueError):value=np.nan
        values.append(value)
    if not dates:return pd.Series([],index=pd.DatetimeIndex([],tz=NZST),dtype=float)
    result=pd.Series(values,index=pd.DatetimeIndex(dates),dtype=float).sort_index()
    # Conflicting duplicate records have no unique reported value; do not choose
    # whichever version happened to be returned first.
    if result.index.has_duplicates:
        result=result.groupby(level=0).agg(lambda a:float(a.iloc[0]) if len(a.unique())==1 else np.nan)
    return result


def strict_daily_mean(raw: pd.Series, quality: pd.Series, *, accepted_codes=(600,),
                      start: str, end_exclusive: str) -> pd.DataFrame:
    """Require a full regular native day with known accepted agency quality.

    Cadence is the most common positive timestamp interval <=60 minutes within
    that station-month (ties choose the shorter interval), using timestamps
    irrespective of temperature values or quality. It must divide 24 hours.
    No gaps, unknown quality, interpolation or synthetic values enter a primary
    complete-reference day. Equal-interval means describe the reported series,
    not error-free physical water temperature.
    """
    raw=raw.sort_index();quality=quality.sort_index()
    if raw.index.tz is None or quality.index.tz is None:
        raise ValueError("Raw and quality timestamps require an explicit native timezone")
    raw.index=raw.index.tz_convert(NZST);quality.index=quality.index.tz_convert(NZST)
    beginning=pd.Timestamp(start)
    finish=pd.Timestamp(end_exclusive)
    beginning=beginning.tz_localize(NZST) if beginning.tzinfo is None else beginning.tz_convert(NZST)
    finish=finish.tz_localize(NZST) if finish.tzinfo is None else finish.tz_convert(NZST)
    index=pd.date_range(beginning.normalize(),finish.normalize(),freq="D",inclusive="left")
    raw=raw.loc[(raw.index>=beginning)&(raw.index<finish)]
    q=quality.reindex(raw.index,method="ffill")
    accepted=raw.notna()&q.isin(accepted_codes)
    cadence={}
    for month,block in raw.groupby(raw.index.strftime("%Y-%m")):
        delta=np.diff(block.index.asi8)/1e9
        delta=delta[(delta>0)&(delta<=3600)]
        if len(delta)<3:cadence[month]=np.nan;continue
        steps,counts=np.unique(delta,return_counts=True)
        seconds=float(steps[np.argmax(counts)])
        cadence[month]=seconds if np.isclose(86400/seconds,round(86400/seconds)) else np.nan
    grouped={day:block for day,block in raw.groupby(raw.index.normalize())}
    rows=[]
    for day in index:
        block=grouped.get(day)
        step=cadence.get(day.strftime("%Y-%m"),np.nan)
        expected=round(86400/step) if np.isfinite(step) else 0
        good=block.index[accepted.reindex(block.index).to_numpy()] if block is not None else pd.DatetimeIndex([],tz=NZST)
        n_good=len(good)
        valid=bool(expected and n_good==expected and block is not None and len(block)==expected)
        if valid:
            edges=np.r_[day.value,good.asi8,(day+pd.Timedelta(days=1)).value]
            valid=bool(np.all(np.diff(edges)/1e9<=step+1e-6))
        rows.append({"date":day.tz_localize(None),"water_c":float(block.loc[good].mean()) if valid else np.nan,
                     "complete_native_day":valid,"n_raw":len(block) if block is not None else 0,
                     "n_accepted":n_good,"expected_samples":expected or np.nan,
                     "cadence_minutes":step/60,"quality_codes":';'.join(map(str,sorted(set(q.reindex(block.index).dropna())))) if block is not None else ''})
    return pd.DataFrame(rows)
