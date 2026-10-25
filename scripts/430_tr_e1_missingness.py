#!/usr/bin/env python3
"""TR-E1: is real missingness related to hot and low-flow states?

Four analyses on the whole opened archive, complete and incomplete years:

1. Station-year: conditional logit of warm-season incompleteness on the
   within-station summer air anomaly (station fixed effects), with an
   independence-group bootstrap, plus a station + region-year mixed model.
2. Day-level gap onsets: time-stratified case-crossover (strata = station x
   year x month), exposure = 7-day air anomaly, lagged water anomaly and, for
   USGS, the daily flow percentile.
3. Gap duration against the onset state.
4. Hot summers and the representativeness of complete years, including the
   implied bias of a complete-years-only H30 climatology.

The fitted onset effects parameterise the state-dependent (MNAR) masks of the
case builder. Hidden water temperatures are never used here.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from joblib import Parallel, delayed
from statsmodels.discrete.conditional_models import ConditionalLogit
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

import wrr_tr_common as T

ARCHIVE = T.OUT / "e1_archive"
OUT = T.OUT / "e1_missingness"
warnings.filterwarnings("ignore", category=RuntimeWarning)


def regions(years: pd.DataFrame) -> pd.Series:
    sites = pd.read_csv(ARCHIVE / "usgs_site_metadata.csv", dtype={"site_no": str, "huc2": str}).set_index("site_no").huc2
    return pd.Series(
        [T.region_of(p, n, sites.get(s) if p == "usgs" else None) for p, n, s in zip(years.provider, years.network_id, years.station_id)],
        index=years.index,
    )


def flow_table(daily: pd.DataFrame, years: pd.DataFrame) -> pd.DataFrame:
    """Daily flow percentile within station and calendar month (USGS only)."""

    flows = pd.read_parquet(ARCHIVE / "usgs_flow.parquet")
    flows = flows.dropna(subset=["flow_cms"])
    flows["station_key"] = "usgs|" + flows.site.astype(str)
    flows = flows.loc[flows.station_key.isin(set(years.station_key))]
    flows["month"] = flows.date.dt.month
    flows["flow_percentile"] = flows.groupby(["station_key", "month"]).flow_cms.rank(pct=True)
    flows["log_flow"] = np.log(flows.flow_cms.clip(lower=1e-4))
    return flows[["station_key", "date", "flow_percentile", "log_flow"]]


def conditional_fit(frame: pd.DataFrame, outcome: str, covariates: list[str], group: str) -> dict:
    data = frame.dropna(subset=[outcome] + covariates)
    varying = data.groupby(group)[outcome].transform(lambda s: s.nunique() > 1)
    data = data.loc[varying]
    if data[outcome].sum() < 5:
        return {"n": len(data), "n_events": int(data[outcome].sum())}
    model = ConditionalLogit(data[outcome].astype(float).to_numpy(), data[covariates].to_numpy(dtype=float), groups=data[group].to_numpy())
    fit = model.fit(disp=False, method="bfgs", maxiter=200)
    params = np.asarray(fit.params)
    se = np.asarray(fit.bse)
    return {
        "n": len(data), "n_strata": int(data[group].nunique()), "n_events": int(data[outcome].sum()),
        **{f"beta__{name}": float(value) for name, value in zip(covariates, params)},
        **{f"se__{name}": float(value) for name, value in zip(covariates, se)},
    }


def bootstrap_conditional(frame: pd.DataFrame, outcome: str, covariates: list[str], stratum: str, draws: int, seed: int, workers: int) -> pd.DataFrame:
    groups = frame.independence_group.astype(str).unique()
    rng = np.random.default_rng(seed)
    choices = [rng.choice(groups, size=len(groups), replace=True) for _ in range(draws)]
    indexed = {label: block for label, block in frame.groupby(frame.independence_group.astype(str))}

    def one(chosen: np.ndarray, draw: int) -> dict:
        parts = []
        for copy, label in enumerate(chosen):
            block = indexed[label].copy()
            block[stratum] = block[stratum].astype(str) + f"#{copy}"
            parts.append(block)
        sample = pd.concat(parts, ignore_index=True)
        try:
            return {"draw": draw, **conditional_fit(sample, outcome, covariates, stratum)}
        except (np.linalg.LinAlgError, ValueError):
            return {"draw": draw}

    return pd.DataFrame(Parallel(n_jobs=workers)(delayed(one)(chosen, draw) for draw, chosen in enumerate(choices)))


def summarise(point: dict, boot: pd.DataFrame, covariates: list[str], label: str) -> list[dict]:
    rows = []
    for name in covariates:
        key = f"beta__{name}"
        values = boot[key].dropna() if key in boot else pd.Series(dtype=float)
        lower, upper = (np.quantile(values, [0.025, 0.975]) if len(values) > 20 else (np.nan, np.nan))
        rows.append(
            {
                "analysis": label, "covariate": name, "n": point.get("n"), "n_strata": point.get("n_strata"), "n_events": point.get("n_events"),
                "log_odds": point.get(key, np.nan), "odds_ratio": float(np.exp(point.get(key, np.nan))),
                "odds_ratio_lower95": float(np.exp(lower)), "odds_ratio_upper95": float(np.exp(upper)),
                "model_se": point.get(f"se__{name}", np.nan), "n_bootstrap": int(len(values)),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draws", type=int, default=400)
    parser.add_argument("--workers", type=int, default=64)
    args = parser.parse_args()
    settings = T.settings()
    OUT.mkdir(parents=True, exist_ok=True)
    years = pd.read_parquet(ARCHIVE / "station_years.parquet")
    years["region"] = regions(years)
    daily = pd.read_parquet(T.SCRATCH / "archive_daily.parquet")
    daily["station_key"] = daily.station_key.astype(str)
    flows = flow_table(daily, years)

    # ---- 1. station-year conditional logit -------------------------------------------------
    core = years.loc[~years.edge_year & years.fully_active & (years.year >= 1982)].copy()
    core = core.dropna(subset=["air_summer_mean_c"])
    core["z_air"] = core.groupby("station_key").air_summer_mean_c.transform(lambda s: (s - s.mean()) / s.std(ddof=1))
    core["trend"] = (core.year - 2000) / 10
    core["warm_incomplete"] = (~core.complete_warm).astype(int)
    core["warm_below90"] = (core.warm_observed_fraction < 0.9).astype(int)
    core["peak_missing"] = (~core.julaug_complete).astype(int)
    summer_flow = flows.loc[flows.date.dt.month.isin(settings["summer_months"])].assign(year=lambda f: f.date.dt.year)
    flow_year = summer_flow.groupby(["station_key", "year"]).agg(log_flow=("log_flow", "mean"), n_flow=("log_flow", "size")).reset_index()
    flow_year = flow_year.loc[flow_year.n_flow >= 0.8 * 92]
    core = core.merge(flow_year[["station_key", "year", "log_flow"]], on=["station_key", "year"], how="left")
    core["z_flow"] = core.groupby("station_key").log_flow.transform(lambda s: (s - s.mean()) / s.std(ddof=1))
    core.to_parquet(OUT / "station_year_sample.parquet", index=False)

    rows = []
    specs = [
        ("station_year_conditional_logit", "warm_incomplete", ["z_air", "trend"], core),
        ("station_year_conditional_logit_below90", "warm_below90", ["z_air", "trend"], core),
        ("station_year_conditional_logit_julaug", "peak_missing", ["z_air", "trend"], core),
        ("station_year_conditional_logit_usgs_flow", "warm_incomplete", ["z_air", "z_flow", "trend"], core.dropna(subset=["z_flow"])),
    ]
    for label, outcome, covariates, frame in specs:
        point = conditional_fit(frame, outcome, covariates, "station_key")
        boot = bootstrap_conditional(frame, outcome, covariates, "station_key", args.draws, settings["seed"], args.workers)
        boot.to_csv(OUT / f"bootstrap_{label}.csv", index=False)
        rows.extend(summarise(point, boot, covariates, label))
        print(f"[430] {label}: {point}", flush=True)

    # Mixed model with station and region-year random intercepts (variational Bayes).
    mixed = core.dropna(subset=["z_air"]).copy()
    mixed["region_year"] = mixed.region + "_" + mixed.year.astype(str)
    exog = sm.add_constant(mixed[["z_air", "trend"]].astype(float))
    exog_vc = pd.get_dummies(mixed[["station_key", "region_year"]].astype(str), sparse=False).astype(float)
    ident = np.array([0 if name.startswith("station_key") else 1 for name in exog_vc.columns])
    glmm = BinomialBayesMixedGLM(mixed.warm_incomplete.to_numpy(dtype=float), exog.to_numpy(), exog_vc.to_numpy(), ident, vcp_p=1.0, fe_p=2.0)
    fit = glmm.fit_vb()
    for position, name in enumerate(exog.columns):
        if name == "const":
            continue
        mean, sd = float(fit.fe_mean[position]), float(fit.fe_sd[position])
        rows.append({"analysis": "station_year_mixed_station_region_year", "covariate": name, "n": len(mixed), "n_events": int(mixed.warm_incomplete.sum()), "log_odds": mean, "odds_ratio": float(np.exp(mean)), "odds_ratio_lower95": float(np.exp(mean - 1.96 * sd)), "odds_ratio_upper95": float(np.exp(mean + 1.96 * sd)), "model_se": sd})

    # ---- 2. case-crossover of gap onsets ----------------------------------------------------
    daily = daily.loc[daily.active & daily.date.dt.month.isin(settings["warm_months"]) & (daily.date.dt.year >= 1982)].copy()
    daily = daily.sort_values(["station_key", "date"])
    missing = daily.water_c.isna().to_numpy()
    previous_missing = np.r_[True, missing[:-1]]
    new_station = np.r_[True, daily.station_key.to_numpy()[1:] != daily.station_key.to_numpy()[:-1]]
    previous_day = np.r_[pd.NaT, daily.date.to_numpy()[:-1]]
    contiguous = ~new_station & (pd.to_datetime(daily.date).to_numpy() - pd.to_datetime(previous_day).to_numpy() == np.timedelta64(1, "D"))
    at_risk = contiguous & ~previous_missing
    daily["onset"] = (missing & at_risk).astype(int)
    lagged = daily.groupby("station_key").water_anomaly_c.shift(1)
    daily["lag_water_anomaly"] = lagged.groupby(daily.station_key).transform(lambda s: s.rolling(3, min_periods=1).mean())
    risk = daily.loc[at_risk].copy()
    for column, name in (("air_week_anomaly_c", "z_air_week"), ("lag_water_anomaly", "z_water_lag")):
        scale = risk.groupby("station_key")[column].transform(lambda s: s.std(ddof=1))
        risk[name] = risk[column] / scale
    risk["stratum"] = risk.station_key + "_" + risk.date.dt.strftime("%Y-%m")
    meta = years.drop_duplicates("station_key").set_index("station_key")[["independence_group", "provider", "region"]]
    risk = risk.join(meta, on="station_key")
    risk = risk.merge(flows[["station_key", "date", "flow_percentile"]], on=["station_key", "date"], how="left")
    risk["low_flow"] = (risk.flow_percentile <= 0.2).astype(float).where(risk.flow_percentile.notna())
    events_by_stratum = risk.groupby("stratum").onset.transform("sum")
    risk = risk.loc[events_by_stratum > 0]
    risk.to_parquet(T.SCRATCH / "e1_case_crossover.parquet", index=False)
    crossover_specs = [
        ("onset_case_crossover_air", ["z_air_week"], risk),
        ("onset_case_crossover_air_water", ["z_air_week", "z_water_lag"], risk),
        ("onset_case_crossover_usgs_flow", ["z_air_week", "low_flow"], risk.dropna(subset=["low_flow"])),
    ]
    for label, covariates, frame in crossover_specs:
        point = conditional_fit(frame, "onset", covariates, "stratum")
        boot = bootstrap_conditional(frame, "onset", covariates, "stratum", max(100, args.draws // 2), settings["seed"] + 1, args.workers)
        boot.to_csv(OUT / f"bootstrap_{label}.csv", index=False)
        rows.extend(summarise(point, boot, covariates, label))
        print(f"[430] {label}: {point}", flush=True)
    by_provider = []
    for provider, frame in risk.groupby("provider"):
        point = conditional_fit(frame, "onset", ["z_air_week"], "stratum")
        by_provider.append({"provider": provider, **point})
    pd.DataFrame(by_provider).to_csv(OUT / "onset_case_crossover_by_provider.csv", index=False)

    # ---- 3. gap duration ---------------------------------------------------------------------
    gaps = pd.read_parquet(ARCHIVE / "gaps.parquet")
    gaps = gaps.loc[gaps.interior & gaps.start_month.isin(settings["warm_months"]) & (gaps.year >= 1982)].dropna(subset=["onset_air_week_anomaly_c"]).copy()
    scale = daily.groupby("station_key").air_week_anomaly_c.std(ddof=1)
    gaps["z_air_week"] = gaps.onset_air_week_anomaly_c / gaps.station_key.map(scale)
    gaps["log_length"] = np.log(gaps.length)
    gaps = gaps.dropna(subset=["z_air_week"])
    design = pd.get_dummies(gaps[["station_key"]].astype(str), drop_first=True).astype(float)
    design = pd.concat([gaps[["z_air_week"]], pd.get_dummies(gaps.start_month.astype(str), prefix="m", drop_first=True).astype(float), design], axis=1)
    duration = sm.OLS(gaps.log_length.to_numpy(), sm.add_constant(design).to_numpy()).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(gaps.independence_group)[0]})
    rows.append({"analysis": "gap_log_duration_station_fe", "covariate": "z_air_week", "n": len(gaps), "log_odds": float(duration.params[1]), "odds_ratio": float(np.exp(duration.params[1])), "odds_ratio_lower95": float(np.exp(duration.params[1] - 1.96 * duration.bse[1])), "odds_ratio_upper95": float(np.exp(duration.params[1] + 1.96 * duration.bse[1])), "model_se": float(duration.bse[1])})

    # ---- 4. hot summers and representativeness ----------------------------------------------
    region_year = core.groupby(["region", "year"]).agg(region_z_air=("z_air", "mean"), n=("z_air", "size")).reset_index()
    eligible = region_year.groupby("region").year.transform("size") >= 10
    region_year = region_year.loc[eligible]
    region_year["hot_summer"] = region_year.groupby("region").region_z_air.transform(lambda s: s >= s.quantile(settings["hot_summer_quantile"]))
    hot = core.merge(region_year[["region", "year", "hot_summer"]], on=["region", "year"], how="inner")

    def hot_contrast(frame: pd.DataFrame) -> float:
        return float(frame.loc[frame.hot_summer, "warm_incomplete"].mean() - frame.loc[~frame.hot_summer, "warm_incomplete"].mean())

    contrast = T.group_bootstrap(hot, "independence_group", hot_contrast, settings["bootstrap_draws"], settings["seed"])
    hot_summary = hot.groupby("hot_summer").agg(n=("warm_incomplete", "size"), warm_incomplete=("warm_incomplete", "mean"), warm_below90=("warm_below90", "mean"), peak_missing=("peak_missing", "mean")).reset_index()
    hot_summary.to_csv(OUT / "hot_summer_incompleteness.csv", index=False)
    hot.groupby(["region", "hot_summer"]).warm_incomplete.agg(["size", "mean"]).reset_index().to_csv(OUT / "hot_summer_incompleteness_by_region.csv", index=False)

    representativeness = core.groupby("complete_warm").agg(n=("z_air", "size"), mean_z_air=("z_air", "mean"), mean_z_flow=("z_flow", "mean"), mean_year=("year", "mean")).reset_index()
    representativeness.to_csv(OUT / "complete_year_representativeness.csv", index=False)

    # Implied bias of a complete-years-only H30 climatology, through the station H30-air relation.
    implied = []
    for station, frame in core.groupby("station_key"):
        complete = frame.dropna(subset=["truth_h30", "air_h30_c"])
        complete = complete.loc[complete.complete_year]
        everything = frame.dropna(subset=["air_h30_c"])
        if len(complete) < 5 or len(everything) == len(complete):
            continue
        slope = np.polyfit(complete.air_h30_c, complete.truth_h30, 1)[0]
        implied.append({"station_key": station, "independence_group": frame.independence_group.iloc[0], "region": frame.region.iloc[0], "n_complete": len(complete), "n_all": len(everything), "slope_h30_on_air": float(slope), "air_h30_gap_complete_minus_all": float(complete.air_h30_c.mean() - everything.air_h30_c.mean()), "implied_h30_bias_C": float(slope * (complete.air_h30_c.mean() - everything.air_h30_c.mean()))})
    implied = pd.DataFrame(implied)
    implied.to_csv(OUT / "implied_complete_year_h30_bias.csv", index=False)
    implied_ci = T.group_bootstrap(implied, "independence_group", lambda f: float(f.implied_h30_bias_C.mean()), settings["bootstrap_draws"], settings["seed"])

    # ---- generator parameters for state-dependent masks -------------------------------------
    results = pd.DataFrame(rows)
    results.to_csv(OUT / "missingness_models.csv", index=False)
    onset = results.loc[(results.analysis == "onset_case_crossover_air") & (results.covariate == "z_air_week")].iloc[0]
    base = risk.groupby(risk.date.dt.month).onset.mean() if len(risk) else pd.Series(dtype=float)
    warm_geometry = pd.read_parquet(ARCHIVE / "gaps.parquet")
    warm_geometry = warm_geometry.loc[warm_geometry.interior & warm_geometry.start_month.isin(settings["warm_months"])]
    generator = {
        "onset_log_odds_per_sd_air_week": float(onset.log_odds), "onset_log_odds_lower95": float(np.log(onset.odds_ratio_lower95)),
        "onset_log_odds_upper95": float(np.log(onset.odds_ratio_upper95)),
        "duration_log_ratio_per_sd_air_week": float(results.loc[results.analysis == "gap_log_duration_station_fe", "log_odds"].iloc[0]),
        "warm_gap_lengths": warm_geometry.length.astype(int).tolist(),
        "warm_gap_start_month_share": warm_geometry.start_month.value_counts(normalize=True).sort_index().to_dict(),
        "conditional_onset_rate_by_month_in_event_strata": {int(k): float(v) for k, v in base.items()},
    }
    T.write_json(OUT / "mnar_generator.json", generator)
    summary = {
        "n_station_years": int(len(core)), "n_stations": int(core.station_key.nunique()),
        "warm_incomplete_share": float(core.warm_incomplete.mean()),
        "hot_summer_contrast_warm_incomplete": float(hot_contrast(hot)),
        "hot_summer_contrast_lower95": float(np.quantile(contrast, 0.025)), "hot_summer_contrast_upper95": float(np.quantile(contrast, 0.975)),
        "implied_complete_year_h30_bias_mean_C": float(implied.implied_h30_bias_C.mean()) if len(implied) else None,
        "implied_bias_lower95": float(np.quantile(implied_ci, 0.025)) if len(implied) else None,
        "implied_bias_upper95": float(np.quantile(implied_ci, 0.975)) if len(implied) else None,
        "n_stations_implied_bias": int(len(implied)),
        "models": results.to_dict("records"),
    }
    T.write_json(OUT / "summary.json", summary)
    print(results[["analysis", "covariate", "n", "n_events", "odds_ratio", "odds_ratio_lower95", "odds_ratio_upper95"]].to_string(), flush=True)
    print({key: value for key, value in summary.items() if key != "models"}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
