#!/usr/bin/env python3
"""Agent B: downstream thermal-regime metrics for the v12 revision.

For <=15 daily-QC confirmation networks, every artificial evaluation-period
gap (horizons 7/30/90 days, <=5 placements per station-gap) is reconstructed
with the fixed XGBoost boundary+donor pipeline.  The truth series, the
reconstructed series, the no-fill (gap days dropped) series, and a
climatology-fill series are summarized into ecologically relevant thermal
regime metrics computed over a 365-day window centred on the gap:

  annual mean, summer (JJA) mean, annual amplitude (mean July - mean January),
  phase (day of year of the smoothed peak), 90th percentile, summer maximum,
  threshold-exceedance days (>20 and >25 degC), cumulative degree days
  (>10 degC base), trend slope.

Deliverables (results/revision_v12/t08_downstream_metrics/agent_b/):
  placement_metrics.csv        per-placement truth/recon/missing/clim metrics
  station_gap_metrics.csv      station-gap aggregates + empirical risk scores
  metric_error_summary.csv     aggregate distortion tables
  risk_correlation.csv         network-level (and pooled) Spearman correlations
  network_metric_distortion.csv  per-network mean distortions and risk
  budget_comparison.csv        top-20% budget experiment
  budget_reduction.png         plot of budget reductions
  REPORT.md                    narrative report

Run: PYTHONPATH=$PWD/src python3 scripts/rev_v12_t08_downstream_metrics_b.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    XGBOOST_PARAMETERS,
    _boundary_values,
    _candidate_starts,
    _climatology_prediction,
    _model_frame,
    read_temperature_panel,
    select_placements,
    year_split,
)
from stream_recoverability.experiments.development_data import (  # noqa: E402
    joint_complete_feature_rosters,
)

NETWORK_ROOT = ROOT / "results/development_v11/confirmation_daily_qc/networks"
EMPIRICAL_PREDICTIONS = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_predictions.csv"
)
FIT_LOSSES = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv"
)
OUTPUT = ROOT / "results/revision_v12/t08_downstream_metrics/agent_b"

HORIZONS = (7, 30, 90)
PLACEMENTS_PER_GAP = 5
MIN_TRAIN_DAYS = 365
TRAINING_FRACTION = 0.7

NETWORKS = (
    "arso_bistrica",
    "arso_sava",
    "arso_savinja",
    "foen_aare_aaregebiet",
    "gkd_bayern_donau",
    "gkd_bayern_isar",
    "gkd_bayern_main",
    "huc8_02040101",
    "huc8_05030103",
    "huc8_17090004",
    "lubw_neckar",
    "lubw_rhein",
    "rws_rijn_lek_nederrijn",
    "usgs_missouri_river_huc10",
    "usgs_snake_river_huc4_1706",
)

METRICS = (
    "annual_mean",
    "summer_mean",
    "amplitude",
    "phase_doy",
    "p90",
    "summer_max",
    "exceed_days_20",
    "exceed_days_25",
    "cdd10",
    "trend_slope",
)

METRIC_LABELS = {
    "annual_mean": "annual mean (degC)",
    "summer_mean": "summer JJA mean (degC)",
    "amplitude": "amplitude Jul-Jan (degC)",
    "phase_doy": "phase (day of peak)",
    "p90": "90th percentile (degC)",
    "summer_max": "summer maximum (degC)",
    "exceed_days_20": "days > 20 degC",
    "exceed_days_25": "days > 25 degC",
    "cdd10": "degree days > 10 degC",
    "trend_slope": "trend slope (degC/yr)",
}


def season_label(day: pd.Timestamp) -> str:
    month = day.month
    if month in (12, 1, 2):
        return "DJF"
    if month in (3, 4, 5):
        return "MAM"
    if month in (6, 7, 8):
        return "JJA"
    return "SON"


def thermal_metrics(values: pd.Series) -> dict[str, float]:
    """Summarise one daily temperature series into thermal regime metrics."""

    out = {metric: np.nan for metric in METRICS}
    present = values.dropna()
    if len(present) < 30:
        return out
    out["annual_mean"] = float(present.mean())
    jja = present.loc[present.index.month.isin((6, 7, 8))]
    if len(jja) >= 20:
        out["summer_mean"] = float(jja.mean())
        out["summer_max"] = float(jja.max())
    july = present.loc[present.index.month == 7]
    january = present.loc[present.index.month == 1]
    if len(july) >= 15 and len(january) >= 15:
        out["amplitude"] = float(july.mean() - january.mean())
    out["p90"] = float(present.quantile(0.9))
    out["exceed_days_20"] = float((present > 20.0).sum())
    out["exceed_days_25"] = float((present > 25.0).sum())
    out["cdd10"] = float(((present - 10.0).clip(lower=0.0)).sum())
    if len(present) >= 60:
        days = (present.index - present.index[0]).days.to_numpy(dtype=float)
        slope_per_day = float(np.polyfit(days, present.to_numpy(dtype=float), 1)[0])
        out["trend_slope"] = slope_per_day * 365.0
    smoothed = values.rolling(15, center=True, min_periods=7).mean().dropna()
    if len(smoothed) >= 60:
        peak = smoothed.idxmax()
        out["phase_doy"] = float(peak.dayofyear)
    return out


def metric_error(truth: dict[str, float], alternative: dict[str, float]) -> dict[str, float]:
    error = {}
    for metric in METRICS:
        t = truth[metric]
        a = alternative[metric]
        if np.isnan(t) or np.isnan(a):
            error[metric] = np.nan
            continue
        if metric == "phase_doy":
            raw = abs(t - a)
            error[metric] = float(min(raw, 365.0 - raw))
        else:
            error[metric] = float(abs(t - a))
    return error


def score_network_with_daily(network_id: str, panel: pd.DataFrame) -> pd.DataFrame:
    """Fit the B_union_D XGBoost models and score evaluation-period gaps,
    returning per-placement daily truth / prediction / climatology."""

    panel = panel.copy().sort_index()
    daily_index = pd.date_range(panel.index.min(), panel.index.max(), freq="D")
    panel = panel.reindex(daily_index)
    panel.index.name = "date"
    panel.columns = panel.columns.astype(str)
    train_mask, training_years, evaluation_years = year_split(
        panel.index, training_fraction=TRAINING_FRACTION
    )
    evaluation_mask = ~train_mask
    model_parameters = {**XGBOOST_PARAMETERS, "n_jobs": 4}

    rows: list[dict[str, object]] = []
    for target in panel.columns:
        fitting_frame = panel.loc[train_mask]
        donors, _, _ = joint_complete_feature_rosters(
            fitting_frame,
            target=str(target),
            donor_candidates=tuple(
                str(column) for column in panel.columns if str(column) != str(target)
            ),
            meteorology_candidates=(),
            hydraulics_candidates=(),
            min_pairs=MIN_TRAIN_DAYS,
        )
        train_target_days = int((train_mask & panel[target].notna()).sum())
        if train_target_days < MIN_TRAIN_DAYS or not donors:
            continue
        frame = _model_frame(
            panel,
            pd.DataFrame(index=panel.index),
            target_station=str(target),
            donors=donors,
            meteorology=(),
            hydraulics=(),
            train_mask=train_mask,
        )
        fitting = train_mask & panel[target].notna()
        model = XGBRegressor(**dict(model_parameters))
        model.fit(frame.loc[fitting], panel.loc[fitting, target])
        climatology = _climatology_prediction(panel[target], train_mask, panel.index)

        for gap_length in HORIZONS:
            candidates = _candidate_starts(
                panel,
                pd.DataFrame(index=panel.index),
                target_station=str(target),
                donors=donors,
                meteorology=(),
                hydraulics=(),
                evaluation_mask=evaluation_mask,
                gap_length=int(gap_length),
            )
            selected = select_placements(candidates, count=PLACEMENTS_PER_GAP)
            for placement, start in enumerate(selected):
                start = int(start)
                stop = start + int(gap_length)
                prediction_frame = frame.iloc[start:stop].copy()
                prediction_frame["B__boundary_temperature"] = _boundary_values(
                    panel[target], start, gap_length
                )
                predicted = model.predict(prediction_frame)
                truth = panel[target].iloc[start:stop].to_numpy(dtype=float)
                climate = climatology[start:stop]
                gap_index = panel.index[start:stop]
                center = gap_index[len(gap_index) // 2]
                window_start = center - pd.Timedelta(days=182)
                window_end = center + pd.Timedelta(days=182)
                year_index = panel.index[
                    (panel.index >= window_start) & (panel.index <= window_end)
                ]
                truth_year = panel.loc[year_index, target].astype(float)
                recon_year = truth_year.copy()
                clim_year = truth_year.copy()
                missing_year = truth_year.copy()
                overlap = gap_index.intersection(year_index)
                if len(overlap) != len(gap_index):
                    continue
                positions = np.searchsorted(year_index, gap_index)
                recon_year.iloc[positions] = predicted
                clim_year.iloc[positions] = climate
                missing_year.iloc[positions] = np.nan

                truth_metrics = thermal_metrics(truth_year)
                scenarios = {
                    "recon": thermal_metrics(recon_year),
                    "missing": thermal_metrics(missing_year),
                    "clim": thermal_metrics(clim_year),
                }
                row: dict[str, object] = {
                    "network_id": str(network_id),
                    "station_id": str(target),
                    "gap_length": int(gap_length),
                    "placement": int(placement),
                    "gap_start": gap_index[0],
                    "gap_end": gap_index[-1],
                    "season": season_label(gap_index[0]),
                    "mae_deg_c": float(np.mean(np.abs(predicted - truth))),
                    "training_years": "|".join(map(str, training_years)),
                    "evaluation_years": "|".join(map(str, evaluation_years)),
                    "donor_station_ids": "|".join(donors),
                    "n_window_days": len(year_index),
                    "window_start": window_start,
                    "window_end": window_end,
                }
                for metric in METRICS:
                    row[f"{metric}_truth"] = truth_metrics[metric]
                for scenario, metrics in scenarios.items():
                    for metric in METRICS:
                        row[f"{metric}_{scenario}"] = metrics[metric]
                for scenario in scenarios:
                    errors = metric_error(truth_metrics, scenarios[scenario])
                    for metric in METRICS:
                        row[f"{metric}_err_{scenario}"] = errors[metric]
                rows.append(row)
    return pd.DataFrame(rows)


def circular_mean_phase(errors: pd.Series) -> float:
    """Mean phase error in days using circular averaging on [0, 365)."""

    radians = 2.0 * np.pi * errors.to_numpy(dtype=float) / 365.0
    mean_radians = np.arctan2(np.mean(np.sin(radians)), np.mean(np.cos(radians)))
    return float(np.mod(mean_radians, 2.0 * np.pi) * 365.0 / (2.0 * np.pi))


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    empirical = pd.read_csv(EMPIRICAL_PREDICTIONS)
    fit_losses = pd.read_csv(FIT_LOSSES)
    empirical["network_id"] = empirical["network_id"].astype(str)
    empirical["station_id"] = empirical["station_id"].astype(str)
    fit_losses["network_id"] = fit_losses["network_id"].astype(str)
    fit_losses["station_id"] = fit_losses["station_id"].astype(str)

    risk_station_gap = (
        empirical.groupby(
            ["network_id", "station_id", "gap_length"], as_index=False
        )["empirical_transfer_prediction"]
        .mean()
        .rename(columns={"empirical_transfer_prediction": "risk_transfer"})
    )
    fit_station_gap = (
        fit_losses.groupby(
            ["network_id", "station_id", "gap_length"], as_index=False
        )["mae_deg_c"]
        .mean()
        .rename(columns={"mae_deg_c": "risk_fit_loss"})
    )
    risk = risk_station_gap.merge(fit_station_gap, on=["network_id", "station_id", "gap_length"])

    placement_parts = []
    attrition = []
    for network_id in NETWORKS:
        panel_path = NETWORK_ROOT / network_id / "daily_wide_temperature.csv"
        if not panel_path.is_file():
            attrition.append({"network_id": network_id, "reason": "missing_panel"})
            continue
        panel = read_temperature_panel(str(panel_path))
        scored = score_network_with_daily(network_id, panel)
        if scored.empty:
            attrition.append({"network_id": network_id, "reason": "no_placements"})
            continue
        placement_parts.append(scored)
        print(f"scored {network_id}: {len(scored)} placements", flush=True)

    placements = pd.concat(placement_parts, ignore_index=True)
    print(f"total placements: {len(placements)}", flush=True)

    station_gap = (
        placements.groupby(["network_id", "station_id", "gap_length"], as_index=False)
        .agg(
            n_placements=("placement", "size"),
            mae_deg_c=("mae_deg_c", "mean"),
            first_gap_start=("gap_start", "min"),
            last_gap_end=("gap_end", "max"),
        )
        .merge(risk, on=["network_id", "station_id", "gap_length"], how="left")
    )
    for metric in METRICS:
        columns = [f"{metric}_err_{scenario}" for scenario in ("recon", "missing", "clim")]
        common = placements[columns].notna().all(axis=1)
        subset = placements.loc[common]
        for scenario in ("recon", "missing", "clim"):
            column = f"{metric}_err_{scenario}"
            if metric == "phase_doy":
                aggs = (
                    subset.groupby(
                        ["network_id", "station_id", "gap_length"], as_index=False
                    )[column]
                    .agg([("circular_mean_phase", circular_mean_phase), ("count", "count")])
                    .rename(columns={"circular_mean_phase": column})
                    .drop(columns=["count"])
                )
            else:
                aggs = (
                    subset.groupby(
                        ["network_id", "station_id", "gap_length"], as_index=False
                    )[column]
                    .mean()
                )
            station_gap = station_gap.merge(
                aggs, on=["network_id", "station_id", "gap_length"], how="left"
            )

    placements.to_csv(OUTPUT / "placement_metrics.csv", index=False)
    uncomputable = []
    for metric in METRICS:
        uncomputable.append(
            {
                "metric": metric,
                "n_placements": int(
                    (placements[f"{metric}_err_recon"].notna() & placements[f"{metric}_err_missing"].isna()).sum()
                ),
                "n_placements_total": len(placements),
            }
        )
    pd.DataFrame(uncomputable).to_csv(OUTPUT / "uncomputable_no_fill.csv", index=False)
    station_gap.to_csv(OUTPUT / "station_gap_metrics.csv", index=False)

    metric_rows = []
    for metric in METRICS:
        recon = station_gap[f"{metric}_err_recon"]
        missing = station_gap[f"{metric}_err_missing"]
        clim = station_gap[f"{metric}_err_clim"]
        finite = recon.notna() & missing.notna()
        row = {
            "metric": metric,
            "label": METRIC_LABELS[metric],
            "units": "days" if metric == "phase_doy" else "degC" if metric in (
                "annual_mean", "summer_mean", "amplitude", "p90", "summer_max",
            ) else "count" if metric in ("exceed_days_20", "exceed_days_25") else (
                "degC-days" if metric == "cdd10" else "degC/yr"
            ),
            "n_units": int(finite.sum()),
            "n_networks": int(station_gap.loc[finite, "network_id"].nunique()),
            "mean_err_recon": float(recon.loc[finite].mean()),
            "median_err_recon": float(recon.loc[finite].median()),
            "mean_err_missing": float(missing.loc[finite].mean()),
            "median_err_missing": float(missing.loc[finite].median()),
            "mean_err_clim": float(clim.loc[finite].mean()),
            "median_err_clim": float(clim.loc[finite].median()),
            "mean_recon_over_missing": float(recon.loc[finite].mean() / missing.loc[finite].mean()),
        }
        metric_rows.append(row)
    metric_summary = pd.DataFrame(metric_rows)
    metric_summary.to_csv(OUTPUT / "metric_error_summary.csv", index=False)

    network_rows = []
    for metric in METRICS:
        for network in station_gap["network_id"].unique():
            subset = station_gap.loc[station_gap["network_id"].eq(network)]
            finite = subset[f"{metric}_err_recon"].notna() & subset["risk_transfer"].notna()
            if not finite.any():
                continue
            network_rows.append(
                {
                    "network_id": network,
                    "metric": metric,
                    "mean_err_recon": float(subset.loc[finite, f"{metric}_err_recon"].mean()),
                    "mean_err_missing": float(subset.loc[finite, f"{metric}_err_missing"].mean()),
                    "mean_risk_transfer": float(subset.loc[finite, "risk_transfer"].mean()),
                    "mean_risk_fit_loss": float(subset.loc[finite, "risk_fit_loss"].mean()),
                    "n_units": int(finite.sum()),
                }
            )
    network_metrics = pd.DataFrame(network_rows)
    network_metrics.to_csv(OUTPUT / "network_metric_distortion.csv", index=False)

    correlation_rows = []
    for metric in METRICS:
        net = network_metrics.loc[network_metrics["metric"].eq(metric)].dropna(
            subset=["mean_err_recon", "mean_risk_transfer"]
        )
        pooled = station_gap.dropna(subset=[f"{metric}_err_recon", "risk_transfer"])
        row = {"metric": metric, "label": METRIC_LABELS[metric], "n_networks": len(net)}
        if len(net) >= 5:
            rho, pvalue = stats.spearmanr(
                net["mean_risk_transfer"], net["mean_err_recon"]
            )
            row["network_spearman_risk"] = float(rho)
            row["network_spearman_risk_p"] = float(pvalue)
            rho, pvalue = stats.spearmanr(
                net["mean_risk_fit_loss"], net["mean_err_recon"]
            )
            row["network_spearman_fitloss"] = float(rho)
            row["network_spearman_fitloss_p"] = float(pvalue)
        if len(pooled) >= 10:
            rho, pvalue = stats.spearmanr(
                pooled["risk_transfer"], pooled[f"{metric}_err_recon"]
            )
            row["pooled_spearman_risk"] = float(rho)
            row["pooled_spearman_risk_p"] = float(pvalue)
            rho, pvalue = stats.spearmanr(
                pooled["risk_fit_loss"], pooled[f"{metric}_err_recon"]
            )
            row["pooled_spearman_fitloss"] = float(rho)
            row["pooled_spearman_fitloss_p"] = float(pvalue)
        correlation_rows.append(row)
    correlations = pd.DataFrame(correlation_rows)
    correlations.to_csv(OUTPUT / "risk_correlation.csv", index=False)

    budget_rows = []
    random_rows = []
    rng = np.random.default_rng(20260828)
    n_random_repeats = 20
    for metric in METRICS:
        err_recon = f"{metric}_err_recon"
        err_missing = f"{metric}_err_missing"
        units = station_gap.dropna(
            subset=[err_recon, err_missing, "risk_transfer"]
        ).copy()
        if len(units) < 10:
            continue
        no_treatment = float(units[err_missing].sum())
        n_treat = max(1, int(np.ceil(0.20 * len(units))))
        policy_sets = {
            "top20_risk": units.nlargest(n_treat, "risk_transfer").index,
            "top20_length": units.nlargest(n_treat, "gap_length").index,
        }
        for policy, treated in policy_sets.items():
            aggregate = float(units.loc[~units.index.isin(treated), err_missing].sum())
            aggregate += float(units.loc[units.index.isin(treated), err_recon].sum())
            budget_rows.append(
                {
                    "policy": policy,
                    "metric": metric,
                    "label": METRIC_LABELS[metric],
                    "n_units": len(units),
                    "n_treated": n_treat,
                    "aggregate_no_treatment": no_treatment,
                    "aggregate_treated": aggregate,
                    "reduction": float(1.0 - aggregate / no_treatment),
                    "reduction_sd": np.nan,
                }
            )
        reductions = []
        for _ in range(n_random_repeats):
            treated = rng.choice(units.index, size=n_treat, replace=False)
            aggregate = float(units.loc[~units.index.isin(treated), err_missing].sum())
            aggregate += float(units.loc[units.index.isin(treated), err_recon].sum())
            reductions.append(1.0 - aggregate / no_treatment)
        budget_rows.append(
            {
                "policy": "random20",
                "metric": metric,
                "label": METRIC_LABELS[metric],
                "n_units": len(units),
                "n_treated": n_treat,
                "aggregate_no_treatment": no_treatment,
                "aggregate_treated": float(no_treatment * (1.0 - np.mean(reductions))),
                "reduction": float(np.mean(reductions)),
                "reduction_sd": float(np.std(reductions)),
            }
        )
    budget = pd.DataFrame(budget_rows)
    budget.to_csv(OUTPUT / "budget_comparison.csv", index=False)

    figure, axis = plt.subplots(figsize=(11.5, 5.6))
    metric_order = budget["metric"].unique()
    policies = ("top20_risk", "top20_length", "random20")
    colors = {"top20_risk": "#2962a3", "top20_length": "#b37400", "random20": "#8a8a8a"}
    width = 0.27
    positions = np.arange(len(metric_order))
    for offset, policy in enumerate(policies):
        values = []
        errors = []
        for metric in metric_order:
            row = budget.loc[(budget["policy"].eq(policy)) & (budget["metric"].eq(metric))]
            if row.empty:
                values.append(np.nan)
                errors.append(np.nan)
            else:
                values.append(float(row["reduction"].iloc[0]))
                errors.append(float(row["reduction_sd"].iloc[0]))
        axis.bar(
            positions + (offset - 1.0) * width,
            values,
            width,
            yerr=errors if policy == "random20" else None,
            capsize=3,
            color=colors[policy],
            label=policy.replace("_", " "),
        )
    axis.axhline(0.0, color="black", linewidth=0.9)
    axis.set_xticks(positions)
    axis.set_xticklabels([METRIC_LABELS.get(m, m) for m in metric_order], rotation=28, ha="right", fontsize=8)
    axis.set_ylabel("Reduction in aggregate thermal-metric distortion")
    axis.set_title(
        "Top-20% recovery budget: reduction vs no gap treatment (agent B)"
    )
    axis.legend(frameon=False, fontsize=8)
    figure.tight_layout()
    figure.savefig(OUTPUT / "budget_reduction.png", dpi=200)
    plt.close(figure)

    summary = {
        "n_networks_requested": len(NETWORKS),
        "n_networks_scored": int(placements["network_id"].nunique()),
        "n_stations_scored": int(placements[["network_id", "station_id"]].drop_duplicates().shape[0]),
        "n_placements": len(placements),
        "n_station_gaps": len(station_gap),
        "attrition": attrition,
        "metric_error_summary": metric_summary[["metric", "n_units", "mean_err_recon", "mean_err_missing", "mean_recon_over_missing"]].to_dict("records"),
        "network_spearman_risk": {
            row["metric"]: {
                "rho": row.get("network_spearman_risk"),
                "p": row.get("network_spearman_risk_p"),
            }
            for row in correlation_rows
        },
        "network_spearman_fitloss": {
            row["metric"]: {
                "rho": row.get("network_spearman_fitloss"),
                "p": row.get("network_spearman_fitloss_p"),
            }
            for row in correlation_rows
        },
        "budget_top20_risk": {
            row["metric"]: row["reduction"]
            for row in budget_rows
            if row["policy"] == "top20_risk"
        },
        "budget_top20_length": {
            row["metric"]: row["reduction"]
            for row in budget_rows
            if row["policy"] == "top20_length"
        },
        "budget_random20": {
            row["metric"]: (row["reduction"], row["reduction_sd"])
            for row in budget_rows
            if row["policy"] == "random20"
        },
        "output_dir": str(OUTPUT),
    }
    (OUTPUT / "summary.json").write_text(
        __import__("json").dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print("--- metric error summary ---")
    print(metric_summary.to_string(index=False))
    print("--- network spearman (risk transfer) ---")
    print(correlations[["metric", "network_spearman_risk", "network_spearman_risk_p", "pooled_spearman_risk", "pooled_spearman_risk_p"]].to_string(index=False))
    print("--- budget reductions ---")
    print(budget[["policy", "metric", "n_units", "n_treated", "reduction", "reduction_sd"]].to_string(index=False))


if __name__ == "__main__":
    main()
