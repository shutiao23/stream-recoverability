#!/usr/bin/env python3
"""Source failure map with provenance-aware dam and zero-flow descriptors."""
from __future__ import annotations
import os
os.environ["MPLBACKEND"]="Agg"
import io
import json
import zipfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import wrr_tr_common as T

CONFIG=json.loads((T.ROOT/"configs/wrr_review_completion_20261024.json").read_text())
OUT=T.ROOT/CONFIG["out"]


def main():
    folder=OUT/"failure_map";folder.mkdir(parents=True,exist_ok=True)
    files=sorted((OUT/"refits/leave_one_year_out/seed_00").glob("*.parquet"))
    if len(files)!=27:
        raise RuntimeError("Require complete source seed 0 outer-region predictions")
    c=pd.concat([pd.read_parquet(f,columns=["station_key","station_id","provider","independence_group","design_family","D2","eval_truth_h30","peak_overlap"]) for f in files],ignore_index=True)
    c["error"]=c.D2-c.eval_truth_h30;c["failure"]=c.error.abs()>.5
    table=c.groupby(["design_family","station_key"]).agg(n=("error","size"),failure_rate=("failure","mean"),bias=("error","mean"),mae=("error",lambda s:s.abs().mean()),provider=("provider","first"),station_id=("station_id","first"),group=("independence_group","first")).reset_index()
    coordinates=pd.read_csv(T.ROOT/"data/interim/v18_station_coordinates.csv",dtype={"station_id":str})
    coordinates["station_key"]=coordinates.provider+"|"+coordinates.station_id
    sites=pd.read_csv(T.E1/"usgs_site_metadata.csv",dtype={"site_no":str})
    us=pd.DataFrame({"station_key":"usgs|"+sites.site_no,"latitude":sites.dec_lat_va,"longitude":sites.dec_long_va})
    coordinates=pd.concat([coordinates[["station_key","latitude","longitude"]],us]).drop_duplicates("station_key",keep="last")
    supplement_path=OUT/"inputs/source_coordinate_supplement.csv"
    if supplement_path.exists():
        supplement=pd.read_csv(supplement_path,dtype={"station_id":str})[["station_key","latitude","longitude"]]
        if supplement.station_key.duplicated().any():raise RuntimeError("Ambiguous supplementary coordinates")
        coordinates=coordinates.set_index("station_key").combine_first(supplement.set_index("station_key")).reset_index()
    table=table.merge(coordinates,on="station_key",how="left",validate="many_to_one")
    archive=T.ROOT/"data/cache/regulation_panel_v1/basinchar_and_report_sept_2011.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            data=z.read("spreadsheets-in-csv-format.zip")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            attributes=[]
            for prefix in ["conterm","AKHIPR"]:
                f=pd.read_csv(z.open(prefix+"_hydromod_dams.txt"),encoding="cp1252",dtype={"STAID":str})
                selected=[col for col in ["STAID","NDAMS_2009","MAJ_NDAMS_2009","STOR_NID_2009","RAW_DIS_NEAREST_MAJ_DAM"] if col in f]
                attributes.append(f[selected])
        gages=pd.concat(attributes).drop_duplicates("STAID");gages["STAID"]=gages.STAID.str.strip().str.zfill(8)
        table["STAID"]=table.station_id.where(table.provider.eq("usgs"))
        table=table.merge(gages,on="STAID",how="left",validate="many_to_one")
    if "MAJ_NDAMS_2009" in table:
        table["upstream_major_dam_snapshot"]=np.where(table.MAJ_NDAMS_2009.isna(),"unknown",np.where(table.MAJ_NDAMS_2009.gt(0),"one_or_more_2009","none_recorded_2009"))
    zero=pd.read_csv(OUT/"inputs/intermittency_proxy.csv",dtype={"site":str}).set_index("site").zero_days
    table["zero_flow_days_in_available_record"]=table.station_id.where(table.provider.eq("usgs")).map(zero)
    table["lake_outlet_status"]="not independently established"
    # Explicit agency designation is stronger than the mere occurrence of a
    # lake/town name. Unmatched stations are not classified as non-outlets.
    designated=sites.loc[sites.station_nm.str.contains(r"\bAT (?:THE )?OUTLET OF\b.*\b(?:LAKE|POND)\b",case=False,na=False),"site_no"]
    table.loc[table.provider.eq("usgs")&table.station_id.isin(designated),"lake_outlet_status"]="agency_designated_lake_outlet"
    table.to_csv(folder/"station_failures_and_metadata.csv",index=False)
    strata=[]
    for family,b in table.groupby("design_family"):
        if "upstream_major_dam_snapshot" in b:
            for label,s in b.groupby("upstream_major_dam_snapshot"):
                strata.append(dict(family=family,descriptor="GAGES_II_major_dam_2009",stratum=label,n_stations=len(s),station_equal_failure_rate=float(s.failure_rate.mean()),station_equal_bias=float(s.bias.mean())))
        for label,s in b.assign(zero_proxy=lambda f:np.where(f.zero_flow_days_in_available_record.isna(),"unknown",np.where(f.zero_flow_days_in_available_record.gt(0),"zero_flow_recorded","no_zero_in_available_flow"))).groupby("zero_proxy"):
            strata.append(dict(family=family,descriptor="zero_flow_proxy",stratum=label,n_stations=len(s),station_equal_failure_rate=float(s.failure_rate.mean()),station_equal_bias=float(s.bias.mean())))
        for label,s in b.groupby("lake_outlet_status"):
            strata.append(dict(family=family,descriptor="explicit_agency_lake_outlet",stratum=label,n_stations=len(s),station_equal_failure_rate=float(s.failure_rate.mean()),station_equal_bias=float(s.bias.mean())))
    pd.DataFrame(strata).to_csv(folder/"descriptor_strata.csv",index=False)
    fig,axes=plt.subplots(2,2,figsize=(11,7))
    for row,family in enumerate(["calendar","crossed"]):
        for col,(name,limits) in enumerate([("US",(-170,-60,15,73)),("Europe",(-15,36,34,73))]):
            ax=axes[row,col];b=table.loc[table.design_family.eq(family)&table.longitude.between(limits[0],limits[1])&table.latitude.between(limits[2],limits[3])]
            points=ax.scatter(b.longitude,b.latitude,c=b.failure_rate,cmap="YlOrRd",vmin=0,vmax=1,s=15,edgecolor="none")
            ax.set(xlim=limits[:2],ylim=limits[2:],xlabel="Longitude",ylabel="Latitude",title=f"{name}: {family} ({len(b)} stations)");ax.grid(alpha=.15)
    fig.colorbar(points,ax=axes.ravel().tolist(),label="D2 failure probability (seed 0, exploratory)",shrink=.8)
    fig.subplots_adjust(hspace=.35,wspace=.25,right=.85)
    fig.savefig(folder/"failure_map.pdf",bbox_inches="tight");fig.savefig(folder/"failure_map.png",dpi=150,bbox_inches="tight");plt.close(fig)
    T.write_json(folder/"status.json",{"seed":0,"n_stations":int(table.station_key.nunique()),"n_with_coordinates":int(table.loc[table.latitude.notna()&table.longitude.notna(),"station_key"].nunique()),"dam_source":"exact station join to cached GAGES-II hydromod_dams 2009 snapshot; archive acquired in earlier work; not a new contemporary NID classification","intermittency":"zero days are an available-record proxy, not a verified intermittent-river class","lake_outlets":"explicit agency outlet designation only; all other stations unknown, not a verified non-outlet class","n_agency_designated_lake_outlets":int(table.loc[table.lake_outlet_status.eq("agency_designated_lake_outlet"),"station_key"].nunique()),"causal_claim":False})
    return 0


if __name__=="__main__":
    raise SystemExit(main())
