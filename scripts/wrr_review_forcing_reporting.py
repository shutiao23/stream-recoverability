"""Select complete European source evidence while keeping the old pilot explicit."""
from __future__ import annotations
import json
import pandas as pd
import pyarrow.parquet as pq
import wrr_tr_common as T


def europe_evidence(out):
    folder=out/"europe_full_source_exact"
    path=folder/"analysis_summary.json"
    if path.exists():
        summary=json.loads(path.read_text())
        if summary.get("complete") and not summary.get("partial",True):
            roster=pd.read_csv(folder/"roster.csv",dtype={"station_id":str})
            source=pd.read_parquet(T.ROOT/"results/wrr_target_recovery_20261022/e2_cases/cases.parquet",columns=["provider","station_key","year"])
            source=source.loc[source.provider.ne("usgs")&source.year.between(1981,2025)]
            expected=set(source.station_key)
            if not roster.station_key.is_unique or set(roster.station_key)!=expected:raise RuntimeError("European full-source roster does not cover the original source population")
            if roster[["latitude","longitude"]].isna().any().any():raise RuntimeError("European source coordinates remain unresolved")
            acquisition=json.loads((folder/"acquisition.json").read_text())
            records=acquisition["records"]
            if acquisition["requested"]!=len(expected) or acquisition["retrieved"]!=len(expected) or acquisition.get("service_stop"):
                raise RuntimeError("Full European weather acquisition is incomplete")
            if len(records)!=len(expected) or {r["station_key"] for r in records}!=expected or any(r["status"]!="available" for r in records):
                raise RuntimeError("European weather records do not cover the exact source roster")
            audit=json.loads((folder/"original_core_control_audit.json").read_text())
            if not audit.get("exact_source_verified") or audit["case_rows"]!=len(source) or audit["availability_disagreements"] or audit["maximum_point_difference"]>1e-9:
                raise RuntimeError("European control has not reproduced every original source case")
            if pq.ParquetFile(folder/"cases.parquet").metadata.num_rows!=2*len(source):raise RuntimeError("Missing European arm/case denominators")
            pairs=pd.read_csv(folder/"paired_summary.csv").rename(columns={"n_paired":"n","alternative_mae":"ERA5_Land_mae"}).set_index("stratum")
            return {"full_source":True,"folder":folder,"selected":len(expected),"retrieved":acquisition["retrieved"],"errors":[],"pairs":pairs,"control":audit}
    folder=out/"europe_forcing"
    acquisition=json.loads((folder/"acquisition.json").read_text())
    pairs=pd.read_csv(folder/"paired_summary.csv").set_index("stratum")
    return {"full_source":False,"folder":folder,"selected":acquisition["selected"],"retrieved":acquisition["retrieved"],"errors":acquisition["errors"],"pairs":pairs,"control":None}
