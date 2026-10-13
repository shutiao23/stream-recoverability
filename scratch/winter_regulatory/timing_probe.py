import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.panel import load_network_panel, station_jobs, station_roster
from stream_recoverability.experiments.v17_fitness.cases import station_geometry_pool
from stream_recoverability.experiments.v17_fitness.paths import (
    REALIZATIONS_PER_STATION_YEAR, stable_seed, STEP3_CASES, STEP1_PANEL,
)
from stream_recoverability.experiments.v17_fitness.outages import (
    climatological_peak_window, design_for_year, peak_overlap_fraction,
)

roster = station_roster()
split = pd.read_csv(STEP1_PANEL / "network_split.csv")
split["network_id"] = split["network_id"].astype(str)
jobs = station_jobs(roster, split)
jobs = [j for j in jobs if j["split_role"] == "development"]
print("n dev jobs", len(jobs))
t0 = time.time()
rows = []
for job in jobs[:5]:
    net, st = str(job["network_id"]), str(job["station_id"])
    daily = load_network_panel(net, str(job["source_root"]))
    daily = daily.copy(); daily.columns = [str(c) for c in daily.columns]
    target = pd.to_numeric(daily[st], errors="coerce")
    pool = station_geometry_pool(daily)
    for year in job["complete_years"]:
        ym = target.index.year == int(year)
        yi = daily.index[ym]
        truth = target.loc[ym].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        peak_doys = climatological_peak_window(target.loc[target.index.year != int(year)], exclude_year=None)
        rng = np.random.default_rng(stable_seed(net, st, int(year), "leave_one_year_out"))
        reals = design_for_year(yi, peak_doys, pool, rng=rng, n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3))
        for r in reals:
            m = r.mask(len(yi))
            if not m.any() or m.all():
                continue
            rows.append((net, st, year, r.realization_id, len(m), int(m.sum()),
                         peak_overlap_fraction(yi, m, peak_doys)))
print("elapsed", round(time.time()-t0, 2), "s for 5 stations;", len(rows), "realizations")
print(pd.DataFrame(rows[:5], columns=["net","st","year","rid","n","missing","peak_ov"]).to_string())
