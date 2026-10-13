"""Prototype: regenerate outage masks for one network and validate vs stored columns."""
from __future__ import annotations
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import pandas as pd

from scripts_support import endpoint_jobs
from stream_recoverability.experiments.v17_fitness.cases import station_geometry_pool
from stream_recoverability.experiments.v17_fitness.estimators import StationModels
from stream_recoverability.experiments.v17_fitness.outages import (
    climatological_peak_window, design_for_year, peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import load_network_panel
from stream_recoverability.experiments.v17_fitness.paths import REALIZATIONS_PER_STATION_YEAR, stable_seed
from stream_recoverability.experiments.v18_closure.endpoints import hottest_k_window
from stream_recoverability.experiments.v18_closure.paths import SUPPORT_WIDTHS

jobs = endpoint_jobs()
net = sys.argv[1] if len(sys.argv) > 1 else "arso_bistrica"
sel = [j for j in jobs if j["network_id"] == net]
print("stations in network:", len(sel), "roots:", {j["source_root"] for j in sel})

t0 = time.time()
daily = load_network_panel(net, sel[0]["source_root"])
daily = daily.copy(); daily.columns = [str(c) for c in daily.columns]
t_load = time.time() - t0
t0 = time.time()
pool = station_geometry_pool(daily)
t_pool = time.time() - t0
print(f"panel {daily.shape} load {t_load:.2f}s pool {t_pool:.2f}s rows {len(pool)}")

rows = []
for j in sel[:3]:
    sid = str(j["station_id"])
    target = pd.to_numeric(daily[sid], errors="coerce")
    t0 = time.time()
    for year in j["complete_years"]:
        ymask = target.index.year == int(year)
        yidx = target.index[ymask]
        truth = target.loc[ymask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        train_mask = pd.Series(~ymask, index=target.index)
        models = StationModels(target=target, donors=daily.drop(columns=[sid]), air=None, train_mask=train_mask)
        peak_doys = climatological_peak_window(target.loc[target.index.year != int(year)], exclude_year=None)
        clim = models.smooth_climatology(yidx)
        rng = np.random.default_rng(stable_seed(net, sid, int(year), "leave_one_year_out"))
        reals = design_for_year(yidx, peak_doys, pool, rng=rng, n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3))
        for r in reals:
            mask = r.mask(len(yidx))
            row = {"network_id": net, "station_id": sid, "year": int(year), "realization_id": r.realization_id,
                   "arm": r.arm, "missing_fraction": float(mask.mean()),
                   "peak_overlap": peak_overlap_fraction(yidx, mask, peak_doys), "n_days": len(yidx)}
            for w in SUPPORT_WIDTHS:
                row[f"support_hidden_{w}"] = float(mask[hottest_k_window(clim, w)].mean())
            rows.append(row)
    print(f"  station {sid}: {time.time()-t0:.2f}s")

mine = pd.DataFrame(rows)
print("regenerated rows:", len(mine))
stored = pd.read_parquet(ROOT / "results/v18_closure/endpoint_cases.parquet")
stored["network_id"] = stored["network_id"].astype(str); stored["station_id"] = stored["station_id"].astype(str)
key = ["network_id", "station_id", "year", "realization_id"]
m = mine.merge(stored[key + ["split_role", "arm", "missing_fraction", "peak_overlap"] + [f"support_hidden_{w}" for w in SUPPORT_WIDTHS]],
               on=key, how="left", suffixes=("", "_stored"))
print("unmatched stored:", m["split_role"].isna().sum())
print("arm agree:", (m["arm"] == m["arm_stored"]).all())
print("missing_fraction maxdiff:", (m["missing_fraction"] - m["missing_fraction_stored"]).abs().max())
print("peak_overlap maxdiff:", (m["peak_overlap"] - m["peak_overlap_stored"]).abs().max())
for w in SUPPORT_WIDTHS:
    d = (m[f"support_hidden_{w}"] - m[f"support_hidden_{w}_stored"]).abs().max()
    print(f"support_hidden_{w} maxdiff {d:.3e}")
