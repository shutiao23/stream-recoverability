"""Recon: regenerate outage masks and check them against the stored case table."""
import os, sys, time
os.environ.setdefault("STREAM_AIR_FORCING", "data/interim/v18_air_forcing.parquet")
sys.path.insert(0, "src")
import numpy as np, pandas as pd
from stream_recoverability.experiments.v17_fitness.cases import station_geometry_pool
from stream_recoverability.experiments.v17_fitness.outages import climatological_peak_window, design_for_year, peak_overlap_fraction
from stream_recoverability.experiments.v17_fitness.panel import air_series_for, load_network_panel, trusted_years
from stream_recoverability.experiments.v17_fitness.paths import stable_seed, REALIZATIONS_PER_STATION_YEAR
from stream_recoverability.experiments.v17_fitness.estimators import StationModels, hottest_window_mean

CASES = "results/v17_fitness/step3_cases/cases_air.parquet"
df = pd.read_parquet(CASES)
dev = df[df.split_role == "development"].copy()
years = trusted_years()
complete = years.groupby(["network_id","station_id"])["year"].apply(lambda v: tuple(sorted(int(x) for x in v)))

NETS = sorted(dev.network_id.unique())[:4]
sub = dev[dev.network_id.isin(NETS)]
print("recon networks", NETS, "cases", len(sub))

t0 = time.time()
bad = 0; checked = 0; air_dev = []; miss = 0
for (net, sta), block in sub.groupby(["network_id","station_id"], sort=True):
    source_root = "first" if True else "first"
    # find source root from ... try both
    panel = None
    for root in ("first","second"):
        try:
            panel = load_network_panel(str(net), root); break
        except Exception:
            continue
    if panel is None:
        print("no panel", net); continue
    panel = panel.copy(); panel.columns=[str(c) for c in panel.columns]
    target = pd.to_numeric(panel[str(sta)], errors="coerce")
    donors = panel.drop(columns=[str(sta)])
    air = air_series_for(str(net), str(sta), panel.index)
    pool = station_geometry_pool(panel)
    cyears = complete.loc[(str(net), str(sta))]
    for year in sorted(block.year.unique()):
        year_mask = target.index.year == int(year)
        year_index = panel.index[year_mask]
        truth = target.loc[year_mask].to_numpy(float)
        peak_source = target.loc[target.index.year != int(year)]
        peak_doys = climatological_peak_window(peak_source, exclude_year=None)
        rng = np.random.default_rng(stable_seed(str(net), str(sta), int(year), "leave_one_year_out"))
        real = design_for_year(year_index, peak_doys, pool, rng=rng, n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR//3))
        stored = block[block.year.eq(int(year))].set_index("realization_id")
        for r in real:
            if r.realization_id not in stored.index:
                miss += 1; continue
            row = stored.loc[r.realization_id]
            mask = r.mask(len(year_index))
            checked += 1
            checks = {
                "total_missing": int(row["total_missing"]) == int(mask.sum()),
                "longest_run": int(row["longest_run"]) == int(max([l for _,l in r.runs], default=0)),
                "n_runs": int(row["n_runs"]) == len(r.runs),
                "peak_overlap": abs(float(row["peak_overlap"]) - peak_overlap_fraction(year_index, mask, peak_doys)) < 1e-12,
            }
            if not all(checks.values()):
                bad += 1
                if bad < 3: print("MISMATCH", net, sta, year, r.realization_id, checks)
            # library air_ridge reproduction on a subsample
            if checked % 37 == 0:
                obs = truth.copy(); obs[mask] = np.nan
                models = StationModels(target=target, donors=donors, air=air,
                                       train_mask=pd.Series(~year_mask, index=panel.index))
                fill = models.air_predict(year_index) if air is not None else np.full(len(year_index), np.nan)
                completed = obs.copy(); completed[mask] = fill[mask]
                got = hottest_window_mean(completed)
                air_dev.append(abs(got - float(row["hottest30_air_ridge"])))
print(f"checked {checked} masks, mismatches {bad}, missing stored {miss}, elapsed {time.time()-t0:.1f}s")
ad = np.array(air_dev, dtype=float)
print("air_ridge reproduction n=", ad.size, "finite", np.isfinite(ad).sum(), "max abs dev", np.nanmax(ad) if ad.size else None)
