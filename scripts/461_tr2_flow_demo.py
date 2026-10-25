#!/usr/bin/env python3
"""TR2-S1: an exploratory annual 7-day minimum flow (7Q) illustration.

The daily model operates on log flow. Exponentiating its prediction is not a
conditional mean in original discharge units; the minimum's bias direction is
therefore an empirical question, not a direct Jensen-inequality conclusion.
On the USGS daily discharge downloaded for the
missingness audit (approved values, climatic years April-March, perennial
streams only), real gap calendars and controlled gaps are transplanted onto
complete climatic years. Gaps are filled by a ridge regression on up to three
correlated neighbours within 200 km (log-flow anomalies, leave-one-year-out),
or by interpolating the log anomaly when no neighbour is complete in the year.
Compared are the plug-in 7Q, the 7Q of recorded days, a distribution
regression of the plug-in error with the decision-time features of E4 (P5a
type, leave-one-HUC2-out), and the SWToolbox practice of skipping any
climatic year with a missing day. A simplified trend experiment degrades long
records at random with each station's real share of incomplete years.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.linear_model import Ridge

import wrr_tr_common as T
from stream_recoverability.experiments.v19_revision.design import contiguous_starts
from stream_recoverability.seeds import plain_seed, position_index

OUT = T.OUT / "s1_flow"
FLOW = T.E1 / "usgs_flow.parquet"
SITES = T.E1 / "usgs_site_metadata.csv"
E5 = T.load_script("tr2_e5_for_flow", T.ROOT / "scripts/436_tr_e5_rules.py")
E8 = T.load_script("tr2_e8_for_flow", T.ROOT / "scripts/440_tr_e8_downstream.py")
LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
LENGTHS = (30, 60, 90)
WINDOW, N_CALENDARS, JITTER, RADIUS_KM, MAX_DONORS, MIN_DONOR_R = 30, 6, 15, 200.0, 3, 0.6
FEATURES = [
    "missing_fraction", "n_runs", "longest_run", "lowflow_overlap", "edge_gap", "layer_donor", "n_donors", "donor_r2",
    "plugin_anom_z", "obs_minus_plugin", "donor_7q_anom", "train_sd_log7q", "gap_centre_distance", "visible_edge_anomaly",
]
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, n_jobs=4)


def climatic_year(index: pd.DatetimeIndex) -> np.ndarray:
    return np.where(index.month >= 4, index.year, index.year - 1)


def seven_day_min(values: np.ndarray) -> tuple[float, int]:
    """Minimum 7-day mean over windows inside the year with no missing day, and its start."""

    means = pd.Series(values).rolling(7).mean().to_numpy()[6:]
    if not np.isfinite(means).any():
        return np.nan, -1
    start = int(np.nanargmin(means))
    return float(means[start]), start


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
    return [(int(s), int(e - s)) for s, e in zip(starts, ends)]


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    flow = pd.read_parquet(FLOW)
    valid = flow.flow_code.astype(str).str.startswith("A") & flow.flow_cms.notna()
    zero = flow.loc[valid].groupby("site").flow_cms.apply(lambda s: bool((s <= 0).any()))
    perennial = zero.index[~zero]
    flow = flow.loc[valid & flow.site.isin(perennial)]
    panel = flow.pivot_table(index="date", columns="site", values="flow_cms", aggfunc="first").sort_index().asfreq("D")
    panel = np.log(panel)
    sites = pd.read_csv(SITES, dtype={"site_no": str, "huc2": str}).set_index("site_no")
    sites = sites.loc[sites.index.isin(panel.columns)]
    return panel, sites


def neighbours(sites: pd.DataFrame) -> dict[str, list[str]]:
    lat = np.radians(sites.dec_lat_va.astype(float).to_numpy())
    lon = np.radians(sites.dec_long_va.astype(float).to_numpy())
    d = 2 * 6371 * np.arcsin(np.sqrt(np.sin((lat[:, None] - lat[None]) / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None]) * np.sin((lon[:, None] - lon[None]) / 2) ** 2))
    names = sites.index.to_list()
    return {name: [names[j] for j in np.argsort(d[i]) if j != i and d[i, j] <= RADIUS_KM] for i, name in enumerate(names)}


def year_blocks(series: pd.Series) -> dict[int, np.ndarray]:
    labels = climatic_year(series.index)
    return {int(y): np.flatnonzero(labels == y) for y in np.unique(labels)}


def calendar_pool(panel: pd.DataFrame) -> list[list[tuple[int, int]]]:
    pool = []
    for site in panel:
        series = panel[site]
        observed = np.flatnonzero(series.notna().to_numpy())
        if not len(observed):
            continue
        blocks = year_blocks(series)
        years = sorted(blocks)
        first, last = climatic_year(series.index[[observed[0]]])[0], climatic_year(series.index[[observed[-1]]])[0]
        for year in years:
            if not first < year < last:
                continue
            missing = series.iloc[blocks[year]].isna().to_numpy()
            if missing.any() and (~missing).sum() >= 30:
                pool.append(runs(missing))
    return pool


def climatology(values: np.ndarray, offsets: np.ndarray, train: np.ndarray) -> np.ndarray:
    """Smoothed mean log flow by day of the climatic year (31-day circular window), training days only."""

    sums, counts = np.zeros(366), np.zeros(366)
    keep = train & np.isfinite(values)
    np.add.at(sums, offsets[keep], values[keep])
    np.add.at(counts, offsets[keep], 1)
    kernel = np.ones(31)
    padded_s = np.r_[sums[-15:], sums, sums[:15]]
    padded_c = np.r_[counts[-15:], counts, counts[:15]]
    smooth = np.convolve(padded_s, kernel, "valid") / np.maximum(np.convolve(padded_c, kernel, "valid"), 1)
    return smooth


def station_cases(site: str, panel: pd.DataFrame, near: list[str], pool: list, region: str, site_index: int, classical: bool = False) -> list[dict]:
    series = panel[site]
    values = series.to_numpy()
    index = series.index
    labels = climatic_year(index)
    offsets = (index - pd.to_datetime([f"{y}-04-01" for y in labels])).days.to_numpy()
    blocks = year_blocks(series)
    complete = [y for y, pos in blocks.items() if len(pos) >= 365 and np.isfinite(values[pos]).all()]
    if len(complete) < 4:
        return []
    donor_values = {d: panel[d].to_numpy() for d in near}
    rows = []
    for year in complete:
        pos = blocks[year]
        train = labels != year
        clim = climatology(values, offsets, train)
        anomaly = values - clim[offsets]
        truth_year = values[pos]
        truth, _ = seven_day_min(np.exp(truth_year))
        train_7q, train_starts = [], []
        for other in complete:
            if other != year:
                q, start = seven_day_min(np.exp(values[blocks[other]]))
                train_7q.append(np.log(q))
                train_starts.append(start + 3)
        mean7, sd7 = float(np.mean(train_7q)), float(np.std(train_7q, ddof=1))
        centre = int(np.median(train_starts))
        support = np.zeros(len(pos), dtype=bool)
        support[max(0, centre - WINDOW // 2) : min(len(pos), centre + WINDOW // 2)] = True
        # Neighbours complete in the target year, ranked by anomaly correlation on training days.
        candidates = []
        for donor in near:
            dv = donor_values[donor]
            if not np.isfinite(dv[pos]).all():
                continue
            dclim = climatology(dv, offsets, train)
            danom = dv - dclim[offsets]
            both = train & np.isfinite(anomaly) & np.isfinite(danom)
            if both.sum() < 3 * 365:
                continue
            r = float(np.corrcoef(anomaly[both], danom[both])[0, 1])
            if r >= MIN_DONOR_R:
                candidates.append((r, donor, danom))
        candidates = sorted(candidates, key=lambda item: -item[0])[:MAX_DONORS]
        model, r2, donor_anom_7q = None, np.nan, np.nan
        if candidates:
            stack = np.column_stack([item[2] for item in candidates])
            fit = train & np.isfinite(anomaly) & np.isfinite(stack).all(axis=1)
            model = Ridge(alpha=1.0).fit(stack[fit], anomaly[fit])
            r2 = float(model.score(stack[fit], anomaly[fit]))
            best = donor_values[candidates[0][1]]
            dblocks = [y for y in complete if y != year and np.isfinite(best[blocks[y]]).all()]
            if len(dblocks) >= 3:
                d7 = [np.log(seven_day_min(np.exp(best[blocks[y]]))[0]) for y in dblocks]
                donor_anom_7q = float(np.log(seven_day_min(np.exp(best[pos]))[0]) - np.mean(d7))
            predicted = model.predict(stack[pos]) + clim[offsets[pos]]
            if classical:
                from stream_recoverability.experiments.tr_revision.baselines import move1, ar1_bridge
                proxy = candidates[0][2]
                paired = train & np.isfinite(anomaly) & np.isfinite(proxy)
                single = Ridge(alpha=1.0).fit(proxy[paired, None], anomaly[paired])
                single_prediction = single.predict(proxy[pos, None]) + clim[offsets[pos]]
                move_prediction = move1(proxy[paired], anomaly[paired], proxy[pos]) + clim[offsets[pos]]
                residual_history = np.full(len(values), np.nan)
                residual_history[fit] = anomaly[fit] - model.predict(stack[fit])
        rng = np.random.default_rng(plain_seed(site_index, year))
        designs = []
        for length in LENGTHS:
            for name, starts in contiguous_starts(len(pos), length, support).items():
                if len(starts):
                    mask = np.zeros(len(pos), dtype=bool)
                    start = int(rng.choice(starts))
                    mask[start : start + length] = True
                    designs.append(("crossed", f"{length}_{name}", mask))
        for draw in rng.choice(len(pool), size=min(N_CALENDARS, len(pool)), replace=False):
            mask = np.zeros(len(pos), dtype=bool)
            for start, length in pool[int(draw)]:
                start = int(min(start, len(pos) - 1))
                length = int(min(length, len(pos) - start))
                low, high = max(0, start - JITTER), min(len(pos) - length, start + JITTER)
                onset = start if start == 0 or start + length >= len(pos) else int(rng.integers(low, high + 1))
                mask[onset : onset + length] = True
            if mask.all() or (~mask).sum() < 30:
                continue
            designs.append(("calendar", "observed", mask))
        year_anomaly = anomaly[pos]
        for design_index, (family, label, mask) in enumerate(designs):
            observed = np.where(mask, np.nan, truth_year)
            if model is not None:
                filled = np.where(mask, predicted, truth_year)
            else:
                visible = np.flatnonzero(~mask)
                filled_anomaly = np.interp(np.arange(len(pos)), visible, year_anomaly[visible])
                filled = np.where(mask, filled_anomaly + clim[offsets[pos]], truth_year)
            plugin, _ = seven_day_min(np.exp(filled))
            recorded, _ = seven_day_min(np.exp(observed))
            gap_runs = runs(mask)
            edge = np.zeros(len(pos), dtype=bool)
            for start, length in gap_runs:
                edge[max(0, start - 10) : start] = True
                edge[start + length : min(len(pos), start + length + 10)] = True
            edge &= ~mask
            centres = [start + length / 2 for start, length in gap_runs]
            rows.append({
                "site": site, "region": region, "year": int(year), "design_family": family, "design": label,
                "truth_log7q": float(np.log(truth)), "plugin_log7q": float(np.log(plugin)), "recorded_log7q": float(np.log(recorded)) if np.isfinite(recorded) else np.nan,
                "missing_fraction": float(mask.mean()), "n_runs": len(gap_runs), "longest_run": max(length for _, length in gap_runs),
                "lowflow_overlap": float(mask[support].mean()), "edge_gap": bool(mask[0] or mask[-1]), "layer_donor": int(model is not None),
                "n_donors": len(candidates), "donor_r2": r2, "plugin_anom_z": (float(np.log(plugin)) - mean7) / sd7 if sd7 > 0 else np.nan,
                "obs_minus_plugin": float(np.log(recorded) - np.log(plugin)) if np.isfinite(recorded) else np.nan,
                "donor_7q_anom": donor_anom_7q, "train_sd_log7q": sd7, "train_mean_log7q": mean7,
                "gap_centre_distance": float(min(abs(c - centre) for c in centres)), "visible_edge_anomaly": float(np.mean(year_anomaly[edge])) if edge.any() else np.nan,
                "observed_fraction": float((~mask).mean()), "lowflow_window_observed": bool(not mask[support].any()),
            })
            if classical:
                import hashlib
                extra = {"design_index": design_index,
                         "mask_sha256": hashlib.sha256(np.packbits(mask).tobytes()).hexdigest(),
                         "single_donor_ridge_log7q": np.nan, "move1_log7q": np.nan,
                         "stochastic_log7q_draws": [], "stochastic_log7q": np.nan}
                if model is not None:
                    for name, prediction in [("single_donor_ridge_log7q", single_prediction), ("move1_log7q", move_prediction)]:
                        path = np.where(mask, prediction, truth_year)
                        extra[name] = float(np.log(seven_day_min(np.exp(path))[0]))
                    paths = ar1_bridge(observed, predicted, residual_history,
                        plain_seed(517, site_index, year, design_index), draws=20)
                    means = np.lib.stride_tricks.sliding_window_view(np.exp(paths), 7, axis=1).mean(axis=-1)
                    draws = np.log(means.min(axis=1))
                    extra["stochastic_log7q_draws"] = draws.tolist()
                    extra["stochastic_log7q"] = float(np.median(draws))
                rows[-1].update(extra)
    return rows


def run_station(site: str, panel: pd.DataFrame, near: list[str], pool: list, region: str, site_index: int) -> list[dict]:
    """Worker entry point: the script is re-imported so module helpers resolve in the worker."""

    module = T.load_script("tr2_flow_worker", Path(__file__))
    return module.station_cases(site, panel, near, pool, region, site_index)


def build(workers: int, limit: int = 0) -> pd.DataFrame:
    panel, sites = load()
    near = {site: [d for d in items if d in panel.columns] for site, items in neighbours(sites).items()}
    pool = calendar_pool(panel)
    print(f"[461] {panel.shape[1]} perennial sites, calendar pool {len(pool)}", flush=True)
    site_positions = position_index(panel.columns)
    jobs = [(site, panel[[site] + near[site]], near[site], pool, f"usgs_huc{sites.huc2[site]}", site_positions[site]) for site in panel.columns if site in sites.index]
    jobs = jobs[:limit] if limit else jobs
    parts = Parallel(n_jobs=workers, verbose=5)(delayed(run_station)(*job) for job in jobs)
    cases = pd.DataFrame([row for part in parts for row in part])
    return cases


def cross_fit(cases: pd.DataFrame, seed: int) -> np.ndarray:
    """Leave-one-HUC2-out quantile regression of the plug-in error (log scale)."""

    error = cases.truth_log7q - cases.plugin_log7q
    out = np.full((len(cases), len(LEVELS)), np.nan)
    for region in sorted(cases.region.unique()):
        held = cases.region.eq(region).to_numpy()
        if held.all():
            continue
        x_train, x_test = cases.loc[~held, FEATURES].astype(float), cases.loc[held, FEATURES].astype(float)
        out[held] = np.column_stack([lgb.LGBMRegressor(objective="quantile", alpha=level, random_state=seed, **PARAMS).fit(x_train, error[~held]).predict(x_test) for level in LEVELS])
    return np.sort(out, axis=1) + cases.plugin_log7q.to_numpy()[:, None]


def trend_experiment(cases: pd.DataFrame, quantiles: np.ndarray, settings: dict, panel: pd.DataFrame) -> pd.DataFrame:
    """Random degradation of long records with each station's real share of incomplete years."""

    calendar = cases.loc[cases.design_family.eq("calendar")]
    site_positions = position_index(panel.columns)
    rows = []
    for site, block in calendar.groupby("site"):
        years = sorted(block.year.unique())
        if len(years) < 20:
            continue
        series = panel[site]
        labels = climatic_year(series.index)
        observed = np.flatnonzero(series.notna().to_numpy())
        first, last = labels[observed[0]], labels[observed[-1]]
        interior = [y for y in range(first + 1, last)]
        incomplete = [y for y in interior if series.loc[labels == y].isna().any()]
        share = float(np.clip(len(incomplete) / max(len(interior), 1), 0.05, 0.6))
        truth = block.groupby("year").truth_log7q.first().reindex(years).to_numpy()
        x = np.asarray(years, dtype=float)
        full = E8.ols(x, truth)[0]
        rng = np.random.default_rng(plain_seed(site_positions[site]))
        by_year = {year: np.flatnonzero((cases.site.eq(site) & cases.design_family.eq("calendar") & cases.year.eq(year)).to_numpy()) for year in years}
        for replicate in range(settings["trend_replicates"]):
            hit = rng.random(len(years)) < share
            values = {name: truth.copy() for name in ("A1", "B", "C1")}
            keep_a0 = ~hit
            keep_a1 = np.ones(len(years), dtype=bool)
            draws = np.repeat(truth[None], settings["multiple_imputations"], axis=0)
            for position in np.flatnonzero(hit):
                choice = int(rng.choice(by_year[years[position]]))
                case = cases.iloc[choice]
                keep_a1[position] = case.observed_fraction >= 0.9
                values["A1"][position] = case.recorded_log7q if np.isfinite(case.recorded_log7q) else case.plugin_log7q
                values["B"][position] = case.plugin_log7q
                values["C1"][position] = quantiles[choice, LEVELS.index(0.5)]
                draws[:, position] = E8.inverse_cdf(np.repeat(quantiles[choice][None], settings["multiple_imputations"], axis=0), np.asarray(LEVELS), rng.random((settings["multiple_imputations"], 1)))[:, 0]
            slopes = {"A0": E8.ols(x[keep_a0], truth[keep_a0])[0] if keep_a0.sum() >= 5 else np.nan, "A1": E8.ols(x[keep_a1], values["A1"][keep_a1])[0], "B": E8.ols(x, values["B"])[0], "C1": E8.ols(x, values["C1"])[0]}
            fits = [E8.ols(x, draws[m]) for m in range(settings["multiple_imputations"])]
            estimates = np.array([f[0] for f in fits])
            between = estimates.var(ddof=1)
            slopes["C"] = float(estimates.mean())
            missing_se = np.sqrt((1 + 1 / settings["multiple_imputations"]) * between)
            rows.append({"site": site, "region": block.region.iloc[0], "replicate": replicate, "n_years": len(years), "n_incomplete": int(hit.sum()), "full_slope": full,
                         **{f"slope_{k}": v for k, v in slopes.items()}, "cover_C": bool(abs(slopes["C"] - full) <= 1.96 * missing_se) if missing_se > 0 else True})
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="smoke test on the first sites; writes to scratch only")
    args = parser.parse_args()
    settings = T.settings()
    global OUT
    OUT = T.SCRATCH / "s1_flow_smoke" if args.limit else OUT
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "cases_smoke.parquet" if args.limit else T.SCRATCH / "s1_flow_cases.parquet"
    cases = pd.read_parquet(path) if args.reuse and path.exists() else build(args.workers, args.limit)
    cases.to_parquet(path, index=False)
    cases = cases.loc[np.isfinite(cases.plugin_log7q) & np.isfinite(cases.truth_log7q)].reset_index(drop=True)
    # Tolerance: half the median interannual standard deviation of log 7Q, as 0.5 C is for H30.
    sd = cases.drop_duplicates(["site", "year"]).groupby("site").truth_log7q.std(ddof=1)
    tolerance = float(0.5 * sd.median())
    quantiles = cross_fit(cases, settings["seed"])
    cases["d2_log7q"] = quantiles[:, LEVELS.index(0.5)]
    truth = cases.truth_log7q.to_numpy()
    estimators = {"P0 plug-in": cases.plugin_log7q.to_numpy(), "recorded days": cases.recorded_log7q.to_numpy(), "D2 target-aware": cases.d2_log7q.to_numpy()}
    strata = {
        "all": np.ones(len(cases), dtype=bool), "low-flow window not hidden": cases.lowflow_overlap.eq(0).to_numpy(),
        "low-flow window partly hidden": (cases.lowflow_overlap.gt(0) & cases.lowflow_overlap.lt(0.5)).to_numpy(), "low-flow window at least half hidden": cases.lowflow_overlap.ge(0.5).to_numpy(),
        "half hidden, neighbour layer": (cases.lowflow_overlap.ge(0.5) & cases.layer_donor.eq(1)).to_numpy(), "half hidden, interpolation layer": (cases.lowflow_overlap.ge(0.5) & cases.layer_donor.eq(0)).to_numpy(),
    }
    covered = (truth >= quantiles[:, 0]) & (truth <= quantiles[:, -1])
    rows = []
    for population, family in (("mech", "crossed"), ("deploy", "calendar")):
        in_family = cases.design_family.eq(family).to_numpy()
        for stratum, selected in strata.items():
            base = in_family & selected
            if base.sum() < 30:
                continue
            for name, value in estimators.items():
                keep = base & np.isfinite(value)
                error = value[keep] - truth[keep]
                rows.append({"population": population, "stratum": stratum, "estimator": name, "n": int(keep.sum()), "availability": float(keep.sum() / base.sum()),
                             "bias_log": float(error.mean()), "mae_log": float(np.abs(error).mean()), "failure_rate": float((np.abs(error) > tolerance).mean()),
                             "coverage90": float(covered[keep].mean()) if name.startswith("D2") else np.nan})
    metrics = pd.DataFrame(rows)
    metrics.to_csv(OUT / "estimator_metrics.csv", index=False)
    # Rules under real calendars: SWToolbox skips every incomplete climatic year.
    deploy = cases.design_family.eq("calendar").to_numpy()
    pfail = E5.predictive_pfail(quantiles, LEVELS, cases.d2_log7q.to_numpy(), tolerance)
    rule_rows, curve_frames = [], []
    for population, family in (("deploy", "calendar"), ("mech", "crossed")):
        weight = cases.design_family.eq(family).to_numpy().astype(float)
        fixed = {"SWToolbox (no missing day)": pd.Series(np.zeros(len(cases), dtype=bool)), "at least 90% of days": cases.observed_fraction.ge(0.9), "low-flow window complete": cases.lowflow_window_observed.astype(bool)}
        scores = {"missing fraction": cases.missing_fraction, "low-flow window hidden": cases.lowflow_overlap + 1e-3 * cases.missing_fraction, "target-aware failure probability": pd.Series(pfail)}
        delivered = {"P0": cases.plugin_log7q, "recorded": cases.recorded_log7q, "D2": cases.d2_log7q}
        frame, curves = E5.evaluate(cases.assign(eval_truth_h30=cases.truth_log7q, independence_group=cases.site), scores, fixed, delivered, weight, tolerance, [0.025, 0.05, 0.1])
        frame.insert(0, "population", population)
        curves.insert(0, "population", population)
        curve_frames.append(curves)
        rejected = (weight > 0) & ~fixed["at least 90% of days"].to_numpy()
        frame["usable_share_of_rejected_by_90pct_D2"] = float((np.abs(cases.d2_log7q.to_numpy() - truth)[rejected] <= tolerance).mean())
        frame["usable_share_of_rejected_by_SWToolbox_D2"] = float((np.abs(cases.d2_log7q.to_numpy() - truth)[weight > 0] <= tolerance).mean())
        rule_rows.append(frame)
    rules = pd.concat(rule_rows, ignore_index=True)
    rules.to_csv(OUT / "rules.csv", index=False)
    pd.concat(curve_frames, ignore_index=True).to_csv(OUT / "rule_curves.csv", index=False)
    keep = ["site", "region", "year", "design_family", "design", "lowflow_overlap", "layer_donor", "observed_fraction", "truth_log7q", "plugin_log7q", "recorded_log7q", "d2_log7q"]
    cases[keep].assign(d2_q05=quantiles[:, 0], d2_q95=quantiles[:, -1]).to_parquet(OUT / "case_predictions.parquet", index=False)
    panel = load()[0]
    trend = trend_experiment(cases, quantiles, settings, panel)
    trend.to_parquet(OUT / "trend_replicates.parquet", index=False)
    trend_rows = []
    for name in ("A0", "A1", "B", "C1", "C"):
        error = trend[f"slope_{name}"] - trend.full_slope
        trend_rows.append({"pipeline": name, "rmse_per_decade_log": float(np.sqrt(np.nanmean(error**2))), "bias_per_decade_log": float(np.nanmean(error)), "n_station_replicates": int(error.notna().sum())})
    trend_summary = pd.DataFrame(trend_rows)
    trend_summary.to_csv(OUT / "trend_summary.csv", index=False)
    mech_half = metrics.loc[(metrics.population == "mech") & (metrics.stratum == "low-flow window at least half hidden")].set_index("estimator")
    summary = {
        "n_sites": int(cases.site.nunique()), "n_complete_years": int(cases.drop_duplicates(["site", "year"]).shape[0]), "n_cases": len(cases),
        "n_regions": int(cases.region.nunique()), "tolerance_log": tolerance, "tolerance_percent": float(100 * (np.exp(tolerance) - 1)),
        "neighbour_layer_share": float(cases.layer_donor.mean()),
        "mech_half_hidden_bias_P0": float(mech_half.loc["P0 plug-in", "bias_log"]), "mech_half_hidden_bias_D2": float(mech_half.loc["D2 target-aware", "bias_log"]),
        "mech_half_hidden_coverage_D2": float(mech_half.loc["D2 target-aware", "coverage90"]),
        "deploy_failure": {name: float(metrics.loc[(metrics.population == "deploy") & (metrics.stratum == "all") & (metrics.estimator == name), "failure_rate"].iloc[0]) for name in estimators},
        "trend": trend_summary.to_dict("records"), "trend_stations": int(trend.site.nunique()), "trend_coverage_C": float(trend.cover_C.mean()) if len(trend) else None,
        "role": "post hoc demonstration requested by the second review (S1); not preregistered",
    }
    summary["mech_half_hidden_bias_reduction"] = float(1 - abs(summary["mech_half_hidden_bias_D2"]) / abs(summary["mech_half_hidden_bias_P0"]))
    T.write_json(OUT / "summary.json", summary)
    print(metrics.round(4).to_string(), flush=True)
    view = rules.loc[rules.delivered.isin(["P0", "recorded", "D2"])][["population", "delivered", "rule", "kind", "retention", "risk", "retention_at_050"]]
    print(view.round(4).to_string(), flush=True)
    print(trend_summary.round(4).to_string(), flush=True)
    print({k: v for k, v in summary.items() if k != "trend"}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
