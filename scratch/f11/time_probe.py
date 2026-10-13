import sys, time, json
from pathlib import Path
ROOT = Path("/home/lzq/workspace/parttime/stream-recoverability")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import pandas as pd
from stream_recoverability.experiments.v17_fitness.cases import build_station_cases
from stream_recoverability.experiments.v17_fitness.panel import station_jobs, station_roster
from stream_recoverability.experiments.v17_fitness.paths import STEP1_PANEL

roster = station_roster()
split = pd.read_csv(STEP1_PANEL / "network_split.csv")
split["network_id"] = split["network_id"].astype(str)
jobs = station_jobs(roster, split)
by = {}
for j in jobs:
    by.setdefault(j["split_role"], []).append(j)
print({k: len(v) for k, v in by.items()})
out = []
for role in ("development", "reserved"):
    for j in by[role][:6]:
        t0 = time.time()
        f = build_station_cases(j)
        dt = time.time() - t0
        out.append({"role": role, "net": j["network_id"], "station": j["station_id"], "sec": round(dt, 2), "rows": len(f)})
        print(out[-1], flush=True)
(ROOT / "scratch/f11/time_probe.json").write_text(json.dumps(out, indent=2))
