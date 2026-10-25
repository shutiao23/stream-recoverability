#!/usr/bin/env python3
"""TR2-M5: where the downstream gain comes from, and the Baden-Wuerttemberg example.

E8 (degraded long records, truth known): the trend error is split into the
step from the warm-season rule to keeping every year with the plug-in
(A1 -> B, the value of keeping years) and the step from the plug-in to
multiple imputation from D2* (B -> C, the value of the estimator). Station
error ratios are reported with medians and quartiles, by the number of years
made incomplete, and on the scale of the sample's station trends (median
complete-record trend, detection of warming, interval width).

E9 (real incomplete years, no truth), Baden-Wuerttemberg: the regional H30
trend under A0, A1, B and C on the same stations, with independence-group
bootstrap intervals, without 2003 as a sensitivity, and the regional anomaly
series from a station and year fixed-effects model so that the set of
stations behind each year's value does not change its level.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
import pandas as pd

import wrr_tr_common as T

E8_OUT = T.OUT / "e8_downstream"
E9_OUT = T.OUT / "e9_application"
E8 = T.load_script("tr2_e8_for_decomposition", T.ROOT / "scripts/440_tr_e8_downstream.py")
BUNDLE = T.load_script("tr2_bundle_for_decomposition", T.ROOT / "scripts/455_tr2_final_models.py")
BINS = [(-0.5, 0.5, "0"), (0.5, 3.5, "1-3"), (3.5, 6.5, "4-6"), (6.5, 9.5, "7-9"), (9.5, 99, ">=10")]


def rmse(values: pd.Series) -> float:
    return float(np.sqrt(np.nanmean(np.square(values))))


def decomposition(settings: dict) -> dict:
    table = pd.read_parquet(E8_OUT / "replicates.parquet")
    table["error"] = table.slope - table.full_slope
    out = {}
    rows, bin_rows = [], []
    for scenario, block in table.groupby("scenario"):
        station = block.pivot_table(index=["group", "station_key"], columns="pipeline", values="error", aggfunc=rmse).reset_index()
        # A ratio is undefined where the denominator pipeline is exact (real calendars never reached the peak).
        station["ratio_B_A1"] = np.where(station.A1 > 1e-9, station.B / station.A1, np.nan)
        station["ratio_C_B"] = np.where(station.B > 1e-9, station.C / station.B, np.nan)
        station["ratio_C_A1"] = np.where(station.A1 > 1e-9, station.C / station.A1, np.nan)
        sq = block.assign(sq=block.error**2).pivot_table(index=["group", "station_key"], columns="pipeline", values="sq", aggfunc="mean").reset_index()

        def share_keep(frame: pd.DataFrame) -> float:
            a1, b, c = (np.sqrt(frame[name].mean()) for name in ("A1", "B", "C"))
            return float((a1 - b) / (a1 - c)) if a1 > c else np.nan

        boot = T.group_bootstrap(sq, "group", share_keep, settings["bootstrap_draws"], settings["seed"])
        a1, b, c = (rmse(block.loc[block.pipeline.eq(name), "error"]) for name in ("A1", "B", "C"))
        row = {"scenario": scenario, "n_stations": int(len(station)), "rmse_A1": a1, "rmse_B": b, "rmse_C": c,
               "share_of_gain_from_keeping_years": share_keep(sq), "share_lower95": float(np.nanquantile(boot, 0.025)), "share_upper95": float(np.nanquantile(boot, 0.975))}
        row["n_stations_B_exact"] = int((station.B <= 1e-9).sum())
        row["max_rmse_C_where_B_exact"] = float(station.loc[station.B <= 1e-9, "C"].max()) if (station.B <= 1e-9).any() else np.nan
        for name in ("ratio_B_A1", "ratio_C_B", "ratio_C_A1"):
            row[f"{name}_n"] = int(station[name].notna().sum())
            row[f"{name}_median"] = float(station[name].median())
            row[f"{name}_q25"] = float(station[name].quantile(0.25))
            row[f"{name}_q75"] = float(station[name].quantile(0.75))
            row[f"{name}_share_below_1"] = float((station[name].dropna() < 1).mean())
        # Scale: the sample's station trends, detection of warming and interval width.
        full = block.loc[block.pipeline.eq("C")].groupby("station_key").full_slope.first()
        row["median_station_trend"] = float(full.median())
        row["rmse_A1_over_median_trend"] = a1 / float(full.median())
        row["rmse_C_over_median_trend"] = c / float(full.median())
        for name in ("A0", "A1", "B", "C"):
            part = block.loc[block.pipeline.eq(name)]
            detected = part.full_detect_warming.astype(bool)
            row[f"detect_given_full_detects_{name}"] = float(part.loc[detected, "detect_warming"].astype(float).mean())
            row[f"detect_given_full_not_{name}"] = float(part.loc[~detected, "detect_warming"].astype(float).mean())
            row[f"ci_width_{name}"] = float(np.nanmean(2 * 1.96 * part.slope_se))
        rows.append(row)
        if scenario == "mnar1":
            out["stations"] = station
        for low, high, label in BINS:
            part = block.loc[block.n_incomplete.gt(low) & block.n_incomplete.le(high)]
            entry = {"scenario": scenario, "n_incomplete": label, "n_station_replicates": int(part.loc[part.pipeline.eq("C")].shape[0])}
            for name in ("A0", "A1", "A2", "B", "C1", "C"):
                entry[f"rmse_{name}"] = rmse(part.loc[part.pipeline.eq(name), "error"])
            bin_rows.append(entry)
    summary = pd.DataFrame(rows)
    summary.to_csv(E8_OUT / "decomposition_summary.csv", index=False)
    pd.DataFrame(bin_rows).to_csv(E8_OUT / "decomposition_by_incomplete_years.csv", index=False)
    out["stations"].to_csv(E8_OUT / "decomposition_station_ratios_mnar1.csv", index=False)
    return summary.set_index("scenario").loc["mnar1"].to_dict()


def station_slopes(base: pd.DataFrame, block: pd.DataFrame, quantiles: np.ndarray, levels: tuple, rng: np.random.Generator, imputations: int, exclude: set[int]) -> dict:
    """Station OLS trends (degrees C per decade) under A0, A1, B and C, optionally without some years."""

    base = base.loc[~base.year.isin(exclude)]
    keep = ~block.year.isin(exclude).to_numpy()
    block, quantiles = block.loc[keep], quantiles[keep]
    x0, y0 = base.year.to_numpy(dtype=float), base.truth_h30.to_numpy()
    a1 = block.warm_observed_fraction.to_numpy() >= 0.9
    a1_values = np.where(block.h30__observed_days.notna(), block.h30__observed_days, block.h30__policy)[a1]
    x_all = np.r_[x0, block.year.to_numpy(dtype=float)]
    slopes = {
        "A0": E8.ols(x0, y0)[0] if len(x0) >= 5 else np.nan,
        "A1": E8.ols(np.r_[x0, block.year.to_numpy(dtype=float)[a1]], np.r_[y0, a1_values])[0],
        "B": E8.ols(x_all, np.r_[y0, block.h30__policy.to_numpy()])[0],
    }
    if len(block):
        draws = E8.inverse_cdf(np.repeat(quantiles[None], imputations, axis=0).reshape(-1, len(levels)), np.asarray(levels), rng.random((imputations * len(block), 1))).reshape(imputations, len(block))
        slopes["C"] = float(np.mean([E8.ols(x_all, np.r_[y0, draws[m]])[0] for m in range(imputations)]))
    else:
        slopes["C"] = E8.ols(x0, y0)[0]
    return slopes


def year_effects(frame: pd.DataFrame) -> pd.Series:
    """Year effects of H30 = station + year + error (least squares, effects centred)."""

    stations = sorted(frame.station_key.unique())
    years = sorted(frame.year.unique())
    s_index = {s: i for i, s in enumerate(stations)}
    y_index = {y: i for i, y in enumerate(years)}
    design = np.zeros((len(frame), len(stations) + len(years) - 1))
    for row, (station, year) in enumerate(zip(frame.station_key, frame.year)):
        design[row, s_index[station]] = 1.0
        if y_index[year] > 0:
            design[row, len(stations) + y_index[year] - 1] = 1.0
    coefficients, *_ = np.linalg.lstsq(design, frame.h30.to_numpy(), rcond=None)
    effects = np.r_[0.0, coefficients[len(stations):]]
    return pd.Series(effects - effects.mean(), index=years)


def baden_wuerttemberg(settings: dict) -> dict:
    meta_levels = None
    real = pd.read_parquet(E9_OUT / "cases.parquet")
    real = real.loc[real.policy_choice.ne("unavailable") & real.state_h30_q50.notna()].reset_index(drop=True)
    real = real.drop_duplicates(["station_key", "year"]).reset_index(drop=True)
    real = real.loc[real.region.eq("lubw")].reset_index(drop=True)
    scored = BUNDLE.apply_bundle(real)
    meta_levels = tuple(float(c.split("_q")[1]) / 100 for c in scored.columns if c.startswith("d2_q"))
    quantiles = scored[[c for c in scored.columns if c.startswith("d2_q")]].to_numpy()
    years = pd.read_parquet(T.E1 / "station_years.parquet")
    complete = years.loc[years.complete_year & years.truth_h30.notna() & years.provider.eq("lubw"), ["station_key", "year", "truth_h30", "independence_group"] if "independence_group" in years else ["station_key", "year", "truth_h30"]]
    groups = real.groupby("station_key").independence_group.first()
    rng = np.random.default_rng(settings["seed"])
    rows = []
    for station, block in real.groupby("station_key"):
        base = complete.loc[complete.station_key.eq(station)]
        if len(base) + len(block) < 15 or len(base) < 5:
            continue
        positions = block.index.to_numpy()
        for label, exclude in (("all years", set()), ("without 2003", {2003})):
            slopes = station_slopes(base, block, quantiles[positions], meta_levels, rng, settings["multiple_imputations"], exclude)
            rows.append({"station_key": station, "group": groups[station], "years": label, "n_complete": len(base), "n_incomplete": len(block), **slopes})
    stations = pd.DataFrame(rows)
    stations.to_csv(E9_OUT / "bw_station_trends.csv", index=False)
    regional = []
    for label, block in stations.groupby("years"):
        for name in ("A0", "A1", "B", "C"):
            frame = block[["group", name]].rename(columns={name: "slope"})
            boot = T.group_bootstrap(frame, "group", lambda f: float(f.slope.mean()), settings["bootstrap_draws"], settings["seed"])
            regional.append({"years": label, "pipeline": name, "n_stations": int(block.station_key.nunique()), "n_groups": int(block.group.nunique()),
                             "regional_trend": float(frame.slope.mean()), "lower95": float(np.nanquantile(boot, 0.025)), "upper95": float(np.nanquantile(boot, 0.975))})
    regional = pd.DataFrame(regional)
    regional.to_csv(E9_OUT / "bw_regional_trends.csv", index=False)
    # Regional anomaly series from station and year fixed effects, on the same stations.
    members = set(stations.station_key)
    complete_rows = complete.loc[complete.station_key.isin(members), ["station_key", "year", "truth_h30"]].rename(columns={"truth_h30": "h30"})
    incomplete_rows = pd.DataFrame({"station_key": real.station_key, "year": real.year, "h30": scored.d2_point.to_numpy()})
    incomplete_rows = incomplete_rows.loc[incomplete_rows.station_key.isin(members)]
    series = pd.DataFrame({
        "A0_complete_years": year_effects(complete_rows),
        "C_all_years_D2_median": year_effects(pd.concat([complete_rows, incomplete_rows], ignore_index=True)),
    })
    counts = pd.concat([complete_rows.assign(kind="complete"), incomplete_rows.assign(kind="incomplete")]).groupby(["year", "kind"]).size().unstack(fill_value=0)
    series = series.join(counts, how="outer")
    series.index.name = "year"
    series.to_csv(E9_OUT / "bw_anomaly_series.csv")
    station_years = complete_rows.shape[0] + incomplete_rows.shape[0]
    return {
        "n_stations": int(stations.station_key.nunique()), "n_groups": int(stations.group.nunique()),
        "complete_share_station_years": float(complete_rows.shape[0] / station_years),
        "stations_incomplete_2003": int(incomplete_rows.year.eq(2003).sum()), "stations_complete_2003": int(complete_rows.year.eq(2003).sum()),
        "top3_years_C": [int(y) for y in series.C_all_years_D2_median.sort_values(ascending=False).index[:3]],
        "top3_years_A0": [int(y) for y in series.A0_complete_years.dropna().sort_values(ascending=False).index[:3]],
        "regional": regional.to_dict("records"),
    }


def main() -> int:
    settings = T.settings()
    e8 = decomposition(settings)
    bw = baden_wuerttemberg(settings)
    T.write_json(E8_OUT / "decomposition.json", {"mnar1": e8})
    T.write_json(E9_OUT / "bw_summary.json", bw)
    print({k: round(v, 4) if isinstance(v, float) else v for k, v in e8.items()}, flush=True)
    print(pd.DataFrame(bw["regional"]).round(3).to_string(), flush=True)
    print({k: v for k, v in bw.items() if k != "regional"}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
