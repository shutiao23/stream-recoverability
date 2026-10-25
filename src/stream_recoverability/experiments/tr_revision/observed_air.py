"""NOAA GHCN-Daily TAVG, retaining quality and reported-day conventions."""
from __future__ import annotations
import calendar
import numpy as np
import pandas as pd


def parse_tavg(text):
    rows=[]
    for line in text.splitlines():
        if len(line)<21 or line[17:21]!="TAVG":continue
        year,month=int(line[11:15]),int(line[15:17])
        for day in range(1,calendar.monthrange(year,month)[1]+1):
            start=21+8*(day-1)
            if len(line)<start+8:raise ValueError("Truncated NOAA daily record")
            value=int(line[start:start+5]);quality=line[start+6];source=line[start+7]
            rows.append({"date":pd.Timestamp(year,month,day),"air_c":value/10 if value!=-9999 and quality==" " else np.nan,
                         "source_flag":source,"quality_flag":quality,"measurement_flag":line[start+5]})
    if not rows:return pd.DataFrame(columns=["date","air_c","source_flag","quality_flag","measurement_flag"])
    frame=pd.DataFrame(rows)
    if frame.date.duplicated().any():
        records=[]
        for date,block in frame.groupby("date"):
            values=block.air_c.dropna().unique();record=block.iloc[0].copy()
            record["air_c"]=float(values[0]) if len(values)==1 else np.nan
            records.append(record)
        frame=pd.DataFrame(records)
    return frame.sort_values("date").reset_index(drop=True)


def distance_km(latitude,longitude,other_latitude,other_longitude):
    a,b,c,d=np.deg2rad([latitude,longitude,other_latitude,other_longitude])
    h=np.sin((c-a)/2)**2+np.cos(a)*np.cos(c)*np.sin((d-b)/2)**2
    return float(6371.0088*2*np.arcsin(min(1,np.sqrt(h))))
