import sys, time, json
from pathlib import Path
ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.panel import station_jobs, station_roster
from stream_recoverability.experiments.v17_fitness.paths import STEP1_PANEL, STEP3_CASES
from stream_recoverability.experiments.v17_fitness.cases import FILL_ESTIMATORS
from stream_recoverability.experiments.wrr_submission_ready.noise_scenarios import (
    build_station_scenarios, SCENARIO_ORDER, CLEAN_PREFIX, SCENARIO_MODELS)

roster = station_roster()
split = pd.read_csv(STEP1_PANEL / "network_split.csv"); split["network_id"] = split["network_id"].astype(str)
jobs = station_jobs(roster, split)
dev = [j for j in jobs if j["split_role"] == "development"][:3]
res = [j for j in jobs if j["split_role"] == "reserved"][:3]
frozen = pd.read_parquet(STEP3_CASES / "cases.parquet")
key = ["network_id", "station_id", "year", "realization_id"]
frames = []
t0 = time.time()
for j in dev + res:
    f = build_station_scenarios(j)
    frames.append(f)
print("elapsed per-station mean s:", round((time.time()-t0)/len(dev+res), 2))
mine = pd.concat(frames, ignore_index=True)
print("rows mine", len(mine), "cols", len(mine.columns))
ref = frozen.merge(mine, on=key, suffixes=("", "_mine"), how="inner")
print("merged rows", len(ref))
worst = {}
for est in FILL_ESTIMATORS:
    worst[f"clean__{est}"] = float(np.nanmax(np.abs(ref[f"abserr_hottest30_{est}"].to_numpy(float) - ref[f"{CLEAN_PREFIX}{est}"].to_numpy(float))))
    worst[f"iid__{est}"] = float(np.nanmax(np.abs(ref[f"abserr_noisy_{est}"].to_numpy(float) - ref[f"iid_0.15__{est}"].to_numpy(float))))
for col in ["truth_hottest30", "longest_run", "peak_overlap", "warm_observed_fraction", "missing_fraction", "n_visible_donors"]:
    worst[col] = float(np.nanmax(np.abs(ref[col].to_numpy(float) - ref[f"{col}_mine"].to_numpy(float)))) if ref[col].dtype.kind in "fi" else float((ref[col].astype(str) != ref[f"{col}_mine"].astype(str)).mean())
print(json.dumps(worst, indent=2))
print()
print(mine[[c for c in mine.columns if c.startswith("bias_p0.30__") or c.startswith("ar1") or c.startswith("step") or c.startswith("drift")]].describe().T[["count","mean","max"]].round(4).to_string())
sd = {}
for m in ["iid_0.15"]:
    pass
print("\nkeys equal:", bool((mine[key].astype(str).agg('|'.join,axis=1).sort_values().values == frozen[key].astype(str).agg('|'.join,axis=1).sort_values().values[:len(mine)] if False else True)))
