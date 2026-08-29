#!/usr/bin/env python3
"""Agent A (adversarial pair): baseline ladder with same-unit paired comparisons.

Revision v12 task t03: build a 12-rung baseline ladder for the second panel
(1,446 units / 57 networks) and the first panel (1,440 units / 42 networks),
all rungs estimated on fitting-period-only data, with:

  * per-rung metrics on the SAME units: pooled Spearman, network-level
    Spearman, within-network Spearman (median over networks), R2, RMSE,
    equal-network-weighted calibration slope/intercept;
  * paired 2,000-network bootstrap DeltaRho (network-level) of the paper's
    empirical predictor and of the risk surface vs the strongest non-proposed
    baseline, and surface vs the empirical curve rung, on both subsets
    (874 direct / 1,446 full for the second panel; 1,440 / 858 for the first);
  * residualization controls: (i) per-horizon network Spearman, (ii)
    network-demeaned residualized pooled Spearman, (iii) MAE normalized by
    fitting-period thermal amplitude (temperature SD/IQR) and by climatology
    MAE on the first panel.

Rung definitions (all fitting-period-only; precise scopes below):
  1  global mean (pooled fitting MAE, all periods)
  2  gap-length mean (fallback: global)
  3  gap-length x season mean (fallback: gap -> global)
  4  network historical mean of fitting MAE (target panel's own fitting record)
  5  network x gap mean of fitting MAE (fallback: network mean)
  6  station x gap mean of fitting MAE (fallback: network-gap -> network mean)
  7  previous-period leave-one-period-out gap x season mean (previous periods
     only; fallback: previous-period gap -> global)
  8  simple structural descriptors (route-A model, fitting-period fit; t01)
  9  conditional covariance -> expected MAE (available for the development
     panel only; NA for first/second panels, reported as supplemental dev rows)
  10 generic blocked-CV mean (leave-one-network-out mean of fitting MAE)
  11 hierarchical risk surface (t04 frozen predictions, second panel; t04
     confirmation-refit file used as supplementary first-panel row)
  12 empirical+structural meta-model: OLS stack of simple + surface fitted on
     first-panel units, applied to the second panel

Read-only inputs (never modified): paper/, src/, configs/, data/, and all
existing files under results/ except this namespace. Writes only to:
  results/revision_v12/t03_baseline_ladder/agent_a/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import r2_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import read_temperature_panel  # noqa: E402

OUT = ROOT / "results/revision_v12/t03_baseline_ladder/agent_a"
DEV_OUTCOMES = ROOT / "results/development_v11/station_gap_outcomes.csv"
FIRST_PANEL = ROOT / "results/development_v11/route_a_confirmation/predictions.csv"
FIRST_EMPIRICAL = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_predictions.csv"
)
FIRST_FIT_LOSSES = (
    ROOT / "results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv"
)
DEV_FIT_LOSSES = (
    ROOT / "results/development_v11/reviewer_completion/development_empirical_fit_losses.csv"
)
SECOND = ROOT / "results/development_v11/second_confirmation"
SECOND_EMPIRICAL = SECOND / "scoring/empirical_predictions.csv"
SECOND_FIT_LOSSES = (
    ROOT / "results/revision_v12/t02_support_hierarchy/agent_a/second_fit_losses.csv"
)
T01_PREDICTIONS = (
    ROOT / "results/revision_v12/t01_paired_comparison/agent_a/predictions.csv"
)
T01B_SIMPLE = (
    ROOT / "results/revision_v12/t01_paired_comparison/agent_b/second_panel_simple_predictions.csv"
)
T04_SECOND = ROOT / "results/revision_v12/t04_risk_surface/agent_a/second_panel_predictions.csv"
T04_FIRST = ROOT / "results/revision_v12/t04_risk_surface/agent_a/first_panel_predictions.csv"
CONFIRMATION_DAILY_QC = ROOT / "results/development_v11/confirmation_daily_qc/networks"
SECOND_DAILY_QC = SECOND / "daily_qc/networks"

DIRECT_HORIZONS = (7, 30, 90, 180)
MODEL_COLUMNS = (
    "gap_length",
    "acf_only",
    "donor_r2_only",
    "additive_d_over_4_heuristic",
    "nearest_donor_correlation",
)
BOOTSTRAP_REPEATS = 2000
BOOTSTRAP_SEED = 0

NON_PROPOSED_RUNGS = ("r1_global", "r2_gap", "r3_gap_season", "r4_network",
                      "r5_network_gap", "r6_station_gap", "r7_prev_period",
                      "r8_simple", "r10_blocked_cv")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"network_id": str, "station_id": str})


def _fit_linear(design: np.ndarray, outcome: np.ndarray, weight: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(design * weight[:, None], outcome * weight, rcond=None)[0]


def _season_from_sincos(sin_series: pd.Series, cos_series: pd.Series) -> pd.Series:
    """Map mean placement phase (sin/cos) back to a meteorological season label."""
    phase = np.arctan2(sin_series.to_numpy(dtype=float), cos_series.to_numpy(dtype=float))
    phase = np.mod(phase, 2.0 * np.pi)
    doy = phase / (2.0 * np.pi) * 365.0
    month = np.select(
        [
            doy <= 31, doy <= 59, doy <= 90, doy <= 120, doy <= 151, doy <= 181,
            doy <= 212, doy <= 243, doy <= 273, doy <= 304, doy <= 334,
        ],
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        default=12,
    )
    return pd.Series(
        np.select(
            [
                np.isin(month, [12, 1, 2]),
                np.isin(month, [3, 4, 5]),
                np.isin(month, [6, 7, 8]),
            ],
            ["DJF", "MAM", "JJA"],
            default="SON",
        ),
        index=sin_series.index,
    )


def metrics(frame: pd.DataFrame, prediction: str, outcome: str) -> dict[str, float]:
    """Rank, equal-network calibration, R2, RMSE (matches t01 / script 124)."""
    usable = frame[["network_id", prediction, outcome]].dropna()
    predicted = usable[prediction].to_numpy(dtype=float)
    observed = usable[outcome].to_numpy(dtype=float)
    network = usable.groupby("network_id")[[prediction, outcome]].mean()
    counts = usable.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(usable)), predicted])
    constant_pred = bool(np.allclose(predicted, predicted[0]))
    if constant_pred:
        slope = float("nan")
        intercept = float(np.average(observed, weights=weight))
    else:
        intercept, slope = _fit_linear(design, observed, weight)
        intercept, slope = float(intercept), float(slope)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        station_spearman = float(spearmanr(predicted, observed).statistic)
        network_spearman = float(
            spearmanr(network[prediction], network[outcome]).statistic
        )
    return {
        "n": int(len(usable)),
        "n_networks": int(len(network)),
        "pooled_spearman": station_spearman,
        "network_spearman": network_spearman,
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "r2": float(r2_score(observed, predicted)),
        "rmse": float(np.sqrt(np.mean(np.square(observed - predicted)))),
    }


def within_network_spearman_median(
    frame: pd.DataFrame, prediction: str, outcome: str, min_units: int = 4
) -> dict[str, float]:
    rows = {}
    for network, values in frame.groupby("network_id"):
        if len(values) < min_units:
            continue
        predicted = values[prediction].to_numpy(dtype=float)
        observed = values[outcome].to_numpy(dtype=float)
        if np.allclose(predicted, predicted[0]) or np.allclose(observed, observed[0]):
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rows[network] = float(spearmanr(predicted, observed).statistic)
    series = pd.Series(rows)
    return {
        "n_networks_within_defined": int(len(series)),
        "within_network_spearman_median": float(series.median()) if len(series) else float("nan"),
    }


def residualized_spearman(frame: pd.DataFrame, prediction: str, outcome: str) -> float:
    usable = frame[["network_id", prediction, outcome]].dropna()
    predicted = usable[prediction] - usable.groupby("network_id")[prediction].transform("mean")
    observed = usable[outcome] - usable.groupby("network_id")[outcome].transform("mean")
    if np.allclose(predicted, predicted[0]) or np.allclose(observed, observed[0]):
        return float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(spearmanr(predicted, observed).statistic)


def paired_bootstrap(
    frame: pd.DataFrame,
    prediction_a: str,
    prediction_b: str,
    outcome: str,
    *,
    repeats: int,
    seed: int,
) -> dict[str, object]:
    """Network-cluster paired bootstrap: both methods on the same resampled networks."""
    rng = np.random.default_rng(seed)
    networks = np.asarray(sorted(frame["network_id"].unique()))
    by_network = {network: group for network, group in frame.groupby("network_id")}
    deltas_station: list[float] = []
    deltas_network: list[float] = []
    deltas_slope: list[float] = []
    skipped = 0
    for _ in range(repeats):
        sampled = rng.choice(networks, size=len(networks), replace=True)
        if len(np.unique(sampled)) < 2:
            skipped += 1
            continue
        parts = []
        for draw, network in enumerate(sampled):
            part = by_network[network].copy()
            part["network_id"] = f"draw_{draw}"
            parts.append(part)
        boot = pd.concat(parts, ignore_index=True)
        metric_a = metrics(boot, prediction_a, outcome)
        metric_b = metrics(boot, prediction_b, outcome)
        deltas_station.append(metric_a["pooled_spearman"] - metric_b["pooled_spearman"])
        deltas_network.append(metric_a["network_spearman"] - metric_b["network_spearman"])
        deltas_slope.append(metric_a["calibration_slope"] - metric_b["calibration_slope"])
    deltas_station = np.asarray(deltas_station)
    deltas_network = np.asarray(deltas_network)
    deltas_slope = np.asarray(deltas_slope)

    def _ci(values: np.ndarray) -> list[float]:
        return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]

    return {
        "repeats": repeats,
        "skipped_degenerate_draws": skipped,
        "delta_pooled_spearman_mean": float(np.mean(deltas_station)),
        "delta_pooled_spearman_ci95": _ci(deltas_station),
        "fraction_delta_pooled_positive": float(np.mean(deltas_station > 0.0)),
        "delta_network_spearman_mean": float(np.mean(deltas_network)),
        "delta_network_spearman_ci95": _ci(deltas_network),
        "fraction_delta_network_positive": float(np.mean(deltas_network > 0.0)),
        "delta_calibration_slope_mean": float(np.mean(deltas_slope)),
        "delta_calibration_slope_ci95": _ci(deltas_slope),
    }


def _panel_path(network_id: str) -> Path:
    second = SECOND_DAILY_QC / network_id / "daily_wide_temperature.csv"
    if second.is_file():
        return second
    first = CONFIRMATION_DAILY_QC / network_id / "daily_wide_temperature.csv"
    if first.is_file():
        return first
    raise FileNotFoundError(f"panel absent for {network_id}")


def panel_thermal_amplitude(network_id: str) -> dict[str, float]:
    """Temperature SD/IQR over the full daily QC panel (verification subset)."""
    panel = read_temperature_panel(str(_panel_path(network_id)))
    values = panel.to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    return {
        "network_id": network_id,
        "temp_sd_full_record": float(np.std(finite)),
        "temp_iqr_full_record": float(np.quantile(finite, 0.75) - np.quantile(finite, 0.25)),
        "n_stations": int(panel.shape[1]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-repeats", type=int, default=BOOTSTRAP_REPEATS)
    parser.add_argument("--quick", action="store_true", help="smoke test")
    args = parser.parse_args()
    repeats = 100 if args.quick else args.bootstrap_repeats
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    run_log: list[str] = []

    def log(message: str) -> None:
        print(message, flush=True)
        run_log.append(message)

    # ------------------------------------------------------------------ load
    dev = _read_csv(DEV_OUTCOMES)
    first_ra = _read_csv(FIRST_PANEL)
    first_empirical_placements = _read_csv(FIRST_EMPIRICAL)
    dev_fit = _read_csv(DEV_FIT_LOSSES)
    first_fit = _read_csv(FIRST_FIT_LOSSES)
    second_fit = _read_csv(SECOND_FIT_LOSSES)
    second_empirical = _read_csv(SECOND_EMPIRICAL)
    t01 = _read_csv(T01_PREDICTIONS)
    t01b = _read_csv(T01B_SIMPLE)
    t04_second = _read_csv(T04_SECOND)
    t04_first = _read_csv(T04_FIRST)

    # ------------------------------------------------------------------ verify
    verification: list[dict[str, object]] = []

    def verify(name: str, frame: pd.DataFrame, prediction: str, outcome: str) -> None:
        row = {"check": name, **metrics(frame, prediction, outcome)}
        verification.append(row)
        log(f"verify {name}: {row['network_spearman']:.4f} / {row['pooled_spearman']:.4f} / "
            f"{row['calibration_slope']:.4f} / {row['r2']:.4f} / {row['rmse']:.4f} (n={row['n']})")

    second_direct = second_empirical.loc[second_empirical["gap_length"].isin(DIRECT_HORIZONS)]
    verify("second_empirical_direct_874", second_direct, "empirical_transfer_prediction", "observed_recovery_loss")
    verify("second_empirical_all_1446", second_empirical, "empirical_transfer_prediction", "observed_recovery_loss")
    verify("second_simple_devonly_all_1446", t01, "simple_devonly", "observed_recovery_loss")
    verify("second_simple_fitperiod_all_1446", t01, "simple_fitperiod", "observed_recovery_loss")
    verify("second_surface_all_1446", t04_second, "surface_prediction_mae", "observed_recovery_loss")

    first_empirical_agg = (
        first_empirical_placements.groupby(
            ["network_id", "station_id", "gap_length"], as_index=False
        )
        .agg(
            empirical_transfer_prediction=("empirical_transfer_prediction", "mean"),
            observed_recovery_loss=("mae_deg_c", "mean"),
            climatology_mae=("climatology_mae_deg_c", "mean"),
        )
        .dropna(subset=["empirical_transfer_prediction"])
    )
    verify(
        "first_empirical_direct_858",
        first_empirical_agg.loc[first_empirical_agg["gap_length"].isin(DIRECT_HORIZONS)],
        "empirical_transfer_prediction",
        "observed_recovery_loss",
    )
    verify("first_empirical_all_1440", first_empirical_agg, "empirical_transfer_prediction", "observed_recovery_loss")
    verify("first_simple_all_1440", first_ra, "predicted_loss", "observed_recovery_loss")
    verify("first_surface_refit_all_1440", t04_first, "surface_prediction_mae", "observed_recovery_loss")

    # cross-source checks
    agreement = t01.merge(
        t01b[["network_id", "station_id", "gap_length", "simple_prediction_fitperiod"]],
        on=["network_id", "station_id", "gap_length"],
    )
    verification.append(
        {
            "check": "t01a_vs_t01b_simple_fitperiod_max_abs_diff",
            "value": float(np.abs(agreement["simple_fitperiod"] - agreement["simple_prediction_fitperiod"]).max()),
        }
    )
    obs_check = second_empirical.merge(
        t01[["network_id", "station_id", "gap_length", "observed_recovery_loss"]],
        on=["network_id", "station_id", "gap_length"],
        suffixes=("_scoring", "_t01"),
    )
    verification.append(
        {
            "check": "second_observed_scoring_vs_t01_max_abs_diff",
            "value": float(np.abs(obs_check["observed_recovery_loss_scoring"] - obs_check["observed_recovery_loss_t01"]).max()),
        }
    )
    fallback_check = t01.loc[t01["horizon_group"].eq("fallback")].groupby("network_id")[
        "empirical_transfer_prediction"
    ].nunique()
    verification.append(
        {
            "check": "second_networks_with_multiple_empirical_values_on_fallback_rows",
            "value": int((fallback_check > 1).sum()),
        }
    )
    netmean = second_fit.groupby("network_id")["mae_deg_c"].mean()
    fallback_rows = t01.loc[t01["horizon_group"].eq("fallback")]
    frozen_fallback = fallback_rows.groupby("network_id")["empirical_transfer_prediction"].first()
    verification.append(
        {
            "check": "second_network_mean_fallback_vs_fit_losses_max_abs_diff",
            "value": float(np.abs(frozen_fallback - netmean.loc[frozen_fallback.index]).max()),
            "n_networks": int(len(frozen_fallback)),
        }
    )

    # ------------------------------------------------------- fitting means
    log("building rung estimates")

    def gap_season_means(losses: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
        global_mean = float(losses["mae_deg_c"].mean())
        gap_mean = losses.groupby("gap_length")["mae_deg_c"].mean()
        gap_season_mean = losses.groupby(["gap_length", "season"])["mae_deg_c"].mean()
        return global_mean, gap_mean, gap_season_mean

    pooled_second = pd.concat([dev_fit, first_fit, second_fit], ignore_index=True)
    pooled_first = pd.concat([dev_fit, first_fit], ignore_index=True)

    def map_gap_season(
        frame: pd.DataFrame,
        global_mean: float,
        gap_mean: pd.Series,
        gap_season_mean: pd.Series,
        season_series: pd.Series,
    ) -> pd.Series:
        keys = list(zip(frame["gap_length"], season_series))
        values = np.full(len(frame), np.nan)
        for gap in gap_season_mean.index.get_level_values(0).unique():
            mask = frame["gap_length"].eq(gap)
            sub_seasons = gap_season_mean.loc[gap]
            for season in sub_seasons.index:
                sel = mask & season_series.eq(season)
                values[sel.to_numpy()] = sub_seasons.loc[season]
        for gap in gap_mean.index:
            sel = frame["gap_length"].eq(gap) & np.isnan(values)
            values[sel.to_numpy()] = gap_mean.loc[gap]
        values = np.where(np.isnan(values), global_mean, values)
        return pd.Series(values, index=frame.index)

    def add_level_means(
        frame: pd.DataFrame,
        losses: pd.DataFrame,
    ) -> pd.DataFrame:
        network_mean = losses.groupby("network_id")["mae_deg_c"].mean()
        network_gap_mean = losses.groupby(["network_id", "gap_length"])["mae_deg_c"].mean()
        station_gap_mean = losses.groupby(["network_id", "station_id", "gap_length"])["mae_deg_c"].mean()
        frame["r4_network"] = frame["network_id"].map(network_mean)
        ng = frame.set_index(["network_id", "gap_length"]).index.map(
            lambda key: network_gap_mean.get(key, np.nan)
        )
        frame["r5_network_gap"] = ng.to_numpy()
        sg = frame.set_index(["network_id", "station_id", "gap_length"]).index.map(
            lambda key: station_gap_mean.get(key, np.nan)
        )
        frame["r6_station_gap"] = sg.to_numpy()
        frame["r5_network_gap"] = frame["r5_network_gap"].fillna(frame["r4_network"])
        frame["r6_station_gap"] = frame["r6_station_gap"].fillna(frame["r5_network_gap"])
        return frame

    def blocked_cv_mean(frame: pd.DataFrame, losses: pd.DataFrame) -> pd.Series:
        network_mean = losses.groupby("network_id")["mae_deg_c"].mean()
        overall = float(losses["mae_deg_c"].mean())
        loo = {
            network: float((losses.loc[losses["network_id"].ne(network), "mae_deg_c"].mean()))
            for network in frame["network_id"].unique()
        }
        values = frame["network_id"].map(loo).fillna(overall)
        return values

    # ------------------------------------------------------- second panel
    second_season = _season_from_sincos(t01["placement_season_sin"], t01["placement_season_cos"])
    t01 = t01.assign(season=second_season)
    g_second, gap_second, gap_season_second = gap_season_means(pooled_second)
    g_prev, gap_prev, gap_season_prev = gap_season_means(pd.concat([dev_fit, first_fit], ignore_index=True))
    second = t01.merge(
        t04_second[
            ["network_id", "station_id", "gap_length", "surface_prediction_mae", "temp_sd", "temp_iqr"]
        ],
        on=["network_id", "station_id", "gap_length"],
        validate="one_to_one",
    )
    second["r1_global"] = g_second
    second["r2_gap"] = second["gap_length"].map(gap_second).fillna(g_second)
    second = add_level_means(second, second_fit)
    second["r3_gap_season"] = map_gap_season(second, g_second, gap_second, gap_season_second, second["season"])
    second["r3_gap_season"] = second["r3_gap_season"].fillna(second["r2_gap"])
    second["r7_prev_period"] = map_gap_season(second, g_prev, gap_prev, gap_season_prev, second["season"])
    second["r8_simple"] = second["simple_fitperiod"]
    second["r10_blocked_cv"] = blocked_cv_mean(second, second_fit)
    second["r11_surface"] = second["surface_prediction_mae"]
    second["empirical"] = second["empirical_transfer_prediction"]
    second["r9_conditional_covariance"] = np.nan

    # ------------------------------------------------------------ first panel
    first_season = _season_from_sincos(first_ra["placement_season_sin"], first_ra["placement_season_cos"])
    first = first_ra.merge(
        first_empirical_agg[
            ["network_id", "station_id", "gap_length", "empirical_transfer_prediction", "climatology_mae"]
        ],
        on=["network_id", "station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    first = first.assign(season=first_season)
    first = first.merge(
        t04_first[
            ["network_id", "station_id", "gap_length", "surface_prediction_mae"]
        ],
        on=["network_id", "station_id", "gap_length"],
        how="left",
        validate="one_to_one",
    )
    g_first, gap_first, gap_season_first = gap_season_means(pooled_first)
    g_dev, gap_dev, gap_season_dev = gap_season_means(dev_fit)
    first["r1_global"] = g_first
    first["r2_gap"] = first["gap_length"].map(gap_first).fillna(g_first)
    first = add_level_means(first, first_fit)
    first["r3_gap_season"] = map_gap_season(first, g_first, gap_first, gap_season_first, first["season"])
    first["r3_gap_season"] = first["r3_gap_season"].fillna(first["r2_gap"])
    first["r7_prev_period"] = map_gap_season(first, g_dev, gap_dev, gap_season_dev, first["season"])
    first["r7_prev_period"] = first["r7_prev_period"].fillna(g_dev)
    first["r8_simple"] = first["predicted_loss"]
    first["r10_blocked_cv"] = blocked_cv_mean(first, first_fit)
    first["empirical"] = first["empirical_transfer_prediction"]
    first["r9_conditional_covariance"] = np.nan
    first["r11_surface"] = first["surface_prediction_mae"]
    first["r12_stack"] = np.nan

    # ------------------------------------------------------------- rung 12
    # OLS stack of simple + surface fitted on first-panel units (fitting period
    # relative to the second panel), applied to the second panel.
    stack_fit = first.dropna(subset=["r8_simple", "r11_surface", "observed_recovery_loss"])
    design = np.column_stack([np.ones(len(stack_fit)), stack_fit["r8_simple"], stack_fit["r11_surface"]])
    counts = stack_fit.groupby("network_id")["network_id"].transform("size")
    weight = np.sqrt(1.0 / counts.to_numpy(dtype=float))
    stack_coefs = _fit_linear(design, stack_fit["observed_recovery_loss"].to_numpy(dtype=float), weight)
    stack_frame = second.dropna(subset=["r8_simple", "r11_surface"])
    stack_design = np.column_stack(
        [np.ones(len(stack_frame)), stack_frame["r8_simple"], stack_frame["r11_surface"]]
    )
    second["r12_stack"] = np.nan
    second.loc[stack_frame.index, "r12_stack"] = stack_design @ stack_coefs
    verification.append(
        {
            "check": "r12_stack_fit_first_panel",
            "n_units": int(len(stack_fit)),
            "n_networks": int(stack_fit["network_id"].nunique()),
            "intercept": float(stack_coefs[0]),
            "coef_simple": float(stack_coefs[1]),
            "coef_surface": float(stack_coefs[2]),
        }
    )

    # ------------------------------------------------------- dev rung 9
    dev_supplemental = dev[
        ["network_id", "station_id", "gap_length", "observed_recovery_loss", "complete_operator_risk"]
    ].rename(columns={"complete_operator_risk": "r9_conditional_covariance"})
    verification.append(
        {
            "check": "dev_supplemental_conditional_covariance_1260",
            "source": "station_gap_outcomes.csv (development panel; the only panel with conditional-covariance predictions)",
            **metrics(dev_supplemental, "r9_conditional_covariance", "observed_recovery_loss"),
        }
    )

    # ----------------------------------------------------------------- ladder
    rung_specs = [
        ("r1_global", "r1_global", "global mean (pooled fitting MAE)"),
        ("r2_gap", "r2_gap", "gap-length mean"),
        ("r3_gap_season", "r3_gap_season", "gap x season mean"),
        ("r4_network", "r4_network", "network historical mean (fitting-period)"),
        ("r5_network_gap", "r5_network_gap", "network x horizon mean"),
        ("r6_station_gap", "r6_station_gap", "station x horizon mean"),
        ("r7_prev_period", "r7_prev_period", "previous-period LOO gap x season"),
        ("r8_simple", "r8_simple", "simple structural descriptors (route-A, fit-period)"),
        ("r9_condcov", "r9_conditional_covariance", "conditional covariance -> MAE (NA)"),
        ("r10_blocked_cv", "r10_blocked_cv", "generic blocked-CV mean (LOO network)"),
        ("r11_surface", "r11_surface", "hierarchical risk surface (t04 frozen)"),
        ("r12_stack", "r12_stack", "meta-model (simple + surface stack)"),
        ("empirical", "empirical", "empirical transfer curve (proposed reference)"),
    ]

    ladder_rows: list[dict[str, object]] = []

    def ladder_block(
        panel_name: str, frame: pd.DataFrame, subset_name: str, subset: pd.DataFrame
    ) -> None:
        for rung, column, description in rung_specs:
            if rung == "r9_condcov":
                ladder_rows.append(
                    {
                        "panel": panel_name, "subset": subset_name, "rung": rung,
                        "description": description, "available": False,
                        "n": 0, "n_networks": 0,
                    }
                )
                continue
            if column not in subset.columns or subset[column].isna().all():
                ladder_rows.append(
                    {
                        "panel": panel_name, "subset": subset_name, "rung": rung,
                        "description": description, "available": False,
                        "n": 0, "n_networks": 0,
                    }
                )
                continue
            usable = subset.dropna(subset=[column])
            if len(usable) == 0:
                ladder_rows.append(
                    {
                        "panel": panel_name, "subset": subset_name, "rung": rung,
                        "description": description, "available": False,
                        "n": 0, "n_networks": 0,
                    }
                )
                continue
            row = {
                "panel": panel_name, "subset": subset_name, "rung": rung,
                "description": description, "available": True,
                **metrics(usable, column, "observed_recovery_loss"),
                **within_network_spearman_median(usable, column, "observed_recovery_loss"),
                "residualized_pooled_spearman": residualized_spearman(
                    usable, column, "observed_recovery_loss"
                ),
            }
            ladder_rows.append(row)

    second_subsets = {
        "direct_874": second.loc[second["gap_length"].isin(DIRECT_HORIZONS)],
        "all_1446": second,
    }
    first_subsets = {
        "direct_858": first.loc[first["gap_length"].isin(DIRECT_HORIZONS)],
        "all_1440": first,
    }
    for name, subset in second_subsets.items():
        ladder_block("second", second, name, subset)
    for name, subset in first_subsets.items():
        ladder_block("first", first, name, subset)

    ladder_df = pd.DataFrame(ladder_rows)
    ladder_df.to_csv(OUT / "master_ladder_table.csv", index=False)

    second.to_csv(OUT / "unit_predictions_second.csv", index=False)
    first.to_csv(OUT / "unit_predictions_first.csv", index=False)
    dev_supplemental.to_csv(OUT / "dev_supplemental_conditional_covariance.csv", index=False)

    # ------------------------------------------------- network composition diagnostic
    # On the full panel the empirical predictor = season curves on 874 direct
    # units + network-mean fallback (r4) on 572 fallback units. Decompose how the
    # two components rank against the full-panel observed network means.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        net_emp_full = second.groupby("network_id")[["empirical", "observed_recovery_loss"]].mean()
        net_r4_full = second.groupby("network_id")[["r4_network", "observed_recovery_loss"]].mean()
        direct_only = second.loc[second["gap_length"].isin(DIRECT_HORIZONS)]
        net_curve_direct = direct_only.groupby("network_id")[["empirical", "observed_recovery_loss"]].mean()
        curve_netmean = second.groupby("network_id")["empirical"].mean()
        curve_only_netmean = direct_only.groupby("network_id")["empirical"].mean()
        full_obs_netmean = second.groupby("network_id")["observed_recovery_loss"].mean()
        verification.append(
            {
                "check": "empirical_network_composition_full_panel",
                "network_rho_empirical_full_panel": float(
                    spearmanr(net_emp_full["empirical"], net_emp_full["observed_recovery_loss"]).statistic
                ),
                "network_rho_r4_full_panel": float(
                    spearmanr(net_r4_full["r4_network"], net_r4_full["observed_recovery_loss"]).statistic
                ),
                "network_rho_curve_only_netmeans_vs_full_observed": float(
                    spearmanr(curve_only_netmean, full_obs_netmean.loc[curve_only_netmean.index]).statistic
                ),
                "network_rho_empirical_netmeans_vs_direct_observed": float(
                    spearmanr(
                        net_curve_direct["empirical"], net_curve_direct["observed_recovery_loss"]
                    ).statistic
                ),
                "n_fallback_units": int((second["gap_length"].isin(DIRECT_HORIZONS) == False).sum()),
            }
        )

    # ------------------------------------------------------------ bootstrap
    log("running paired bootstrap")

    def rank_network_spearman(ladder_subset: pd.DataFrame) -> list[str]:
        ranking = (
            ladder_subset.loc[ladder_subset["available"], ["rung", "network_spearman"]]
            .sort_values("network_spearman", ascending=False)
        )
        return ranking["rung"].tolist()

    second_all_ranking = rank_network_spearman(
        ladder_df.loc[
            (ladder_df["panel"] == "second") & (ladder_df["subset"] == "all_1446")
        ]
    )
    first_all_ranking = rank_network_spearman(
        ladder_df.loc[
            (ladder_df["panel"] == "first") & (ladder_df["subset"] == "all_1440")
        ]
    )
    strongest_second = next(r for r in second_all_ranking if r in NON_PROPOSED_RUNGS)
    strongest_first = next(r for r in first_all_ranking if r in NON_PROPOSED_RUNGS)
    log(f"strongest non-proposed rung (second, network rho): {strongest_second}")
    log(f"strongest non-proposed rung (first, network rho): {strongest_first}")

    bootstrap_rows: list[dict[str, object]] = []

    def bootstrap_pair(
        panel_name: str,
        subset_name: str,
        frame: pd.DataFrame,
        method_a: str,
        method_b: str,
    ) -> None:
        usable = frame.dropna(subset=[method_a, method_b, "observed_recovery_loss"])
        if len(usable) < 4 or usable["network_id"].nunique() < 2:
            log(f"skip bootstrap {method_a} vs {method_b} on {panel_name}/{subset_name} (insufficient)")
            return
        row = {
            "panel": panel_name,
            "subset": subset_name,
            "method_a": method_a,
            "method_b": method_b,
            "n_units": int(len(usable)),
            "n_networks": int(usable["network_id"].nunique()),
            **paired_bootstrap(
                usable, method_a, method_b, "observed_recovery_loss",
                repeats=repeats, seed=BOOTSTRAP_SEED,
            ),
        }
        bootstrap_rows.append(row)
        log(
            f"bootstrap {method_a} vs {method_b} [{panel_name}/{subset_name}]: "
            f"DeltaRho_network {row['delta_network_spearman_mean']:+.4f} "
            f"{row['delta_network_spearman_ci95'][0]:+.4f}..{row['delta_network_spearman_ci95'][1]:+.4f}"
        )

    # second panel
    for subset_name, subset in second_subsets.items():
        bootstrap_pair("second", subset_name, subset, "empirical", strongest_second)
        bootstrap_pair("second", subset_name, subset, "empirical", "r8_simple")
        bootstrap_pair("second", subset_name, subset, "empirical", "r6_station_gap")
        bootstrap_pair("second", subset_name, subset, "empirical", "r5_network_gap")
        bootstrap_pair("second", subset_name, subset, "empirical", "r4_network")
        bootstrap_pair("second", subset_name, subset, "empirical", "r12_stack")
        bootstrap_pair("second", subset_name, subset, "r11_surface", "empirical")
        bootstrap_pair("second", subset_name, subset, "r11_surface", strongest_second)
        bootstrap_pair("second", subset_name, subset, "r11_surface", "r6_station_gap")
        bootstrap_pair("second", subset_name, subset, "r11_surface", "r8_simple")
        bootstrap_pair("second", subset_name, subset, "r11_surface", "r12_stack")
        bootstrap_pair("second", subset_name, subset, "r12_stack", strongest_second)
    # first panel
    for subset_name, subset in first_subsets.items():
        bootstrap_pair("first", subset_name, subset, "empirical", strongest_first)
        bootstrap_pair("first", subset_name, subset, "empirical", "r6_station_gap")
        bootstrap_pair("first", subset_name, subset, "empirical", "r8_simple")
        bootstrap_pair("first", subset_name, subset, "r11_surface", "empirical")
        bootstrap_pair("first", subset_name, subset, "r11_surface", strongest_first)

    bootstrap_df = pd.DataFrame(bootstrap_rows)
    bootstrap_df.to_csv(OUT / "paired_bootstrap.csv", index=False)

    # --------------------------------------------------- control (i): per-horizon
    horizon_rows: list[dict[str, object]] = []
    horizon_methods = [
        ("r2_gap", "r2_gap"), ("r4_network", "r4_network"),
        ("r5_network_gap", "r5_network_gap"), ("r6_station_gap", "r6_station_gap"),
        ("r7_prev_period", "r7_prev_period"), ("r8_simple", "r8_simple"),
        ("r11_surface", "r11_surface"), ("r12_stack", "r12_stack"),
        ("empirical", "empirical"),
    ]
    for horizon in sorted(second["gap_length"].unique()):
        subset = second.loc[second["gap_length"].eq(horizon)]
        row: dict[str, object] = {
            "horizon": int(horizon), "n_units": len(subset),
            "n_networks": int(subset["network_id"].nunique()),
        }
        for rung, column in horizon_methods:
            usable = subset.dropna(subset=[column])
            network = usable.groupby("network_id")[[column, "observed_recovery_loss"]].mean()
            if len(network) >= 2 and network[column].nunique() > 1:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    row[f"{rung}_network_spearman"] = float(
                        spearmanr(network[column], network["observed_recovery_loss"]).statistic
                    )
            else:
                row[f"{rung}_network_spearman"] = np.nan
        horizon_rows.append(row)
    pd.DataFrame(horizon_rows).to_csv(OUT / "per_horizon_network_spearman.csv", index=False)

    # -------------------------------------------- control (ii): residualized
    residual_rows: list[dict[str, object]] = []
    for panel_name, frame, subsets in (
        ("second", second, second_subsets),
        ("first", first, first_subsets),
    ):
        for subset_name, subset in subsets.items():
            row = {"panel": panel_name, "subset": subset_name}
            for rung, column, _desc in rung_specs:
                if column not in subset.columns or subset[column].isna().all():
                    continue
                usable = subset.dropna(subset=[column])
                row[f"{rung}_residualized_pooled_spearman"] = residualized_spearman(
                    usable, column, "observed_recovery_loss"
                )
                row[f"{rung}_pooled_spearman"] = metrics(usable, column, "observed_recovery_loss")[
                    "pooled_spearman"
                ]
            residual_rows.append(row)
    pd.DataFrame(residual_rows).to_csv(OUT / "residualized_spearman.csv", index=False)

    # ------------------------------ control (iii): normalized MAE (amplitude)
    # Primary: per-unit fitting-period temperature SD/IQR (t04, roster training
    # years). Direct verification: full-record SD/IQR from daily QC panels for a
    # subset of networks.
    verify_networks = [
        "chmi_berounka", "chmi_blanice", "nve_basin_2", "nve_basin_103",
        "nve_basin_26", "usgs2_huc2_08", "usgs2_huc2_12", "usgs2_huc2_14",
        "usgs2_huc2_15", "usgs2_huc2_18",
    ]
    amplitude_rows = []
    for network in verify_networks:
        try:
            amplitude_rows.append(panel_thermal_amplitude(network))
        except FileNotFoundError:
            log(f"panel missing for verification network {network}; skipping")
    amplitude_df = pd.DataFrame(amplitude_rows)
    if len(amplitude_df):
        amplitude_df = amplitude_df.merge(
            second[["network_id", "temp_sd", "temp_iqr"]].drop_duplicates("network_id"),
            on="network_id",
            how="left",
        ).rename(
            columns={"temp_sd": "t04_temp_sd_training_years", "temp_iqr": "t04_temp_iqr_training_years"}
        )
        sd_corr = (
            amplitude_df["temp_sd_full_record"].corr(amplitude_df["t04_temp_sd_training_years"])
            if len(amplitude_df) > 2
            else np.nan
        )
        amplitude_df["corr_sd_full_vs_training"] = sd_corr
        verification.append(
            {
                "check": "thermal_amplitude_verification_subset",
                "n_networks": int(len(amplitude_df)),
                "corr_sd_full_record_vs_training_years": float(sd_corr),
            }
        )
    amplitude_df.to_csv(OUT / "thermal_amplitude_verification.csv", index=False)

    def normalized_mae_block(
        panel_name: str,
        frame: pd.DataFrame,
        denom_columns: dict[str, str],
        subset_name: str,
        subset: pd.DataFrame,
    ) -> None:
        for denom_label, denom_column in denom_columns.items():
            usable = subset.dropna(subset=[denom_column]).copy()
            if len(usable) == 0:
                continue
            row: dict[str, object] = {
                "panel": panel_name, "subset": subset_name,
                "normalization": denom_label, "n": len(usable),
            }
            for rung, column, _desc in rung_specs:
                if column not in usable.columns or usable[column].isna().all():
                    continue
                valid = usable.dropna(subset=[column])
                if len(valid) == 0 or (valid[denom_column] <= 0).any():
                    continue
                ratio = (
                    (valid["observed_recovery_loss"] - valid[column]).abs()
                    / valid[denom_column]
                )
                row[f"{rung}_mean_abs_normalized"] = float(ratio.mean())
                row[f"{rung}_median_abs_normalized"] = float(ratio.median())
                rmse_norm = np.sqrt(np.mean(np.square(
                    (valid["observed_recovery_loss"] - valid[column]) / valid[denom_column]
                )))
                row[f"{rung}_rmse_normalized"] = float(rmse_norm)
            yield row

    normalized_rows = []
    # second panel: temperature SD / IQR (fitting-period, per unit, from t04)
    for name, subset in second_subsets.items():
        for row in normalized_mae_block(
            "second", second, {"temp_sd_fitperiod": "temp_sd", "temp_iqr_fitperiod": "temp_iqr"},
            name, subset,
        ):
            normalized_rows.append(row)
    # first panel: climatology MAE (per unit, mean over placements)
    for name, subset in first_subsets.items():
        for row in normalized_mae_block(
            "first", first, {"climatology_mae": "climatology_mae"}, name, subset,
        ):
            normalized_rows.append(row)
    pd.DataFrame(normalized_rows).to_csv(OUT / "normalized_mae.csv", index=False)

    # ------------------------------------------------------------- summary
    summary = {
        "task": "t03_baseline_ladder",
        "agent": "a",
        "runtime_seconds": round(time.time() - started, 1),
        "bootstrap_repeats": repeats,
        "strongest_non_proposed_second_all_1446": strongest_second,
        "strongest_non_proposed_first_all_1440": strongest_first,
        "second_ranking_by_network_rho_all_1446": second_all_ranking,
        "first_ranking_by_network_rho_all_1440": first_all_ranking,
        "verification": verification,
        "rung_specs": {rung: desc for rung, _, desc in rung_specs},
        "artifacts": [
            "master_ladder_table.csv",
            "unit_predictions_second.csv",
            "unit_predictions_first.csv",
            "dev_supplemental_conditional_covariance.csv",
            "paired_bootstrap.csv",
            "per_horizon_network_spearman.csv",
            "residualized_spearman.csv",
            "normalized_mae.csv",
            "thermal_amplitude_verification.csv",
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8"
    )
    (OUT / "run_log.txt").write_text("\n".join(run_log) + "\n", encoding="utf-8")
    log(f"done in {round(time.time() - started, 1)}s; artifacts in {OUT}")


if __name__ == "__main__":
    main()
