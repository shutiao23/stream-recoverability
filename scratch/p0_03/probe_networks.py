import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.panel import load_network_panel

REAL_SY = ROOT / "results/v18_closure/e2_archive_deployment/real_station_years.parquet"
SPLIT = ROOT / "results/v17_fitness/step1_panel/network_split.csv"
ROSTER = ROOT / "results/v17_fitness/step1_panel/station_roster.csv"
MAX_NETWORKS = 16
SEED = 41

real = pd.read_parquet(REAL_SY); split = pd.read_csv(SPLIT); roster = pd.read_csv(ROSTER)
dev = set(split.loc[split["split_role"].eq("development"), "network_id"].astype(str))
real = real.loc[real["network_id"].astype(str).isin(dev)].copy()
incomplete = real.loc[~real["complete"]].copy(); complete = real.loc[real["complete"]].copy()
counts = roster.groupby("network_id")["station_id"].nunique()
multi = set(counts.loc[counts >= 2].index.astype(str)) & dev
source_map = (roster.drop_duplicates("network_id")
    .set_index(roster.drop_duplicates("network_id")["network_id"].astype(str))["source_root"].astype(str).to_dict())
t0=time.time(); loadable=[]
for network_id in sorted(multi):
    source_root = source_map.get(network_id, "first")
    try:
        panel = load_network_panel(network_id, source_root)
    except Exception:
        continue
    stations = (set(incomplete.loc[incomplete.network_id.astype(str).eq(network_id), "station_id"].astype(str))
        & set(complete.loc[complete.network_id.astype(str).eq(network_id), "station_id"].astype(str))
        & set(map(str, panel.columns)))
    if len(stations) >= 1 and panel.shape[1] >= 2:
        loadable.append(network_id)
print("scan sec", round(time.time()-t0,1), "n multi", len(multi), "n loadable", len(loadable))
rng = np.random.default_rng(SEED)
nets = loadable
if len(nets) > MAX_NETWORKS:
    nets = list(rng.choice(nets, size=MAX_NETWORKS, replace=False))
print("selected", sorted(nets))
rows=[]
for nid in sorted(nets):
    p = load_network_panel(nid, source_map.get(nid,"first"))
    p.columns=[str(c) for c in p.columns]
    idx = p.index
    full = pd.date_range(idx.min(), idx.max(), freq="D")
    stns = (set(incomplete.loc[incomplete.network_id.astype(str).eq(nid),"station_id"].astype(str))
        & set(complete.loc[complete.network_id.astype(str).eq(nid),"station_id"].astype(str)) & set(p.columns))
    rows.append(dict(network=nid, n_stations_panel=p.shape[1], n_days=len(idx), n_full=len(full),
                     index_continuous=bool(len(full)==len(idx)), 
                     first=str(idx.min().date()), last=str(idx.max().date()),
                     n_usable_stations=len(stns), usable=",".join(sorted(stns)),
                     n_missing_any=int(p.isna().any(axis=1).sum())))
d=pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(d.to_string(index=False))
d.to_csv(ROOT/"scratch/p0_03/probe_networks.csv", index=False)
